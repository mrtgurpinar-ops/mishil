from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import User, Subscription
from app.models.enums import SubscriptionStatus, SubscriptionPlan
from app.models.schemas import SubscriptionResponse

logger = get_logger("subscription")


class SubscriptionService:
    """Subscription lifecycle, 3-day trial and RevenueCat webhook synchronization."""

    @classmethod
    def calculate_status(cls, user: User, subscription: Optional[Subscription]) -> Dict[str, Any]:
        """Determine active status, remaining trial days, and effective subscription tier."""
        now = datetime.now(timezone.utc)
        
        # Check active paid subscription
        if subscription and subscription.status == SubscriptionStatus.ACTIVE:
            return {
                "status": SubscriptionStatus.ACTIVE,
                "plan": subscription.plan,
                "trial_ends_at": subscription.trial_ends_at,
                "is_active": True,
                "days_left_in_trial": None,
            }

        # Check trial
        trial_ends_at = None
        if subscription and subscription.trial_ends_at:
            trial_ends_at = subscription.trial_ends_at
        elif user.trial_ends_at:
            trial_ends_at = user.trial_ends_at

        if trial_ends_at:
            if trial_ends_at.tzinfo is None:
                trial_ends_at = trial_ends_at.replace(tzinfo=timezone.utc)
                
            if trial_ends_at > now:
                delta = trial_ends_at - now
                days_left = max(0, delta.days + (1 if delta.seconds > 0 else 0))
                return {
                    "status": SubscriptionStatus.TRIAL,
                    "plan": subscription.plan if subscription else SubscriptionPlan.YEARLY,
                    "trial_ends_at": trial_ends_at,
                    "is_active": True,
                    "days_left_in_trial": days_left,
                }
            else:
                return {
                    "status": SubscriptionStatus.EXPIRED,
                    "plan": subscription.plan if subscription else None,
                    "trial_ends_at": trial_ends_at,
                    "is_active": False,
                    "days_left_in_trial": 0,
                }

        # No subscription or trial registered
        return {
            "status": SubscriptionStatus.EXPIRED,
            "plan": None,
            "trial_ends_at": None,
            "is_active": False,
            "days_left_in_trial": 0,
        }

    @classmethod
    def start_trial(cls, db: Session, user: User) -> SubscriptionResponse:
        """Start a 3-day free trial for user if not previously used."""
        now = datetime.now(timezone.utc)
        trial_ends_at = now + timedelta(days=settings.TRIAL_DURATION_DAYS)

        # Check existing subscription
        sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
        if sub and sub.trial_ends_at and sub.trial_ends_at < now:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Daha önce 3 günlük ücretsiz deneme süresi kullanılmış."
            )

        if not sub:
            sub = Subscription(
                user_id=user.id,
                plan=SubscriptionPlan.YEARLY,
                status=SubscriptionStatus.TRIAL,
                trial_ends_at=trial_ends_at,
                provider_ref="mishil_direct_trial",
            )
            db.add(sub)
        else:
            sub.status = SubscriptionStatus.TRIAL
            sub.trial_ends_at = trial_ends_at

        user.subscription_status = SubscriptionStatus.TRIAL
        user.trial_ends_at = trial_ends_at
        db.commit()
        db.refresh(sub)
        db.refresh(user)

        state = cls.calculate_status(user, sub)
        return SubscriptionResponse(
            user_id=user.id,
            status=state["status"],
            plan=state["plan"],
            trial_ends_at=state["trial_ends_at"],
            is_active=state["is_active"],
            days_left_in_trial=state["days_left_in_trial"],
        )

    @classmethod
    def process_revenuecat_webhook(
        cls, db: Session, payload: Dict[str, Any], auth_header: Optional[str]
    ) -> Dict[str, Any]:
        """
        Verify webhook authorization header and process RevenueCat event types.
        Event types: INITIAL_PURCHASE, RENEWAL, CANCELLATION, EXPIRATION, PRODUCT_CHANGE
        """
        # Validate Webhook Authorization Secret
        expected_secret = settings.REVENUECAT_WEBHOOK_SECRET
        if expected_secret:
            if not auth_header or (auth_header != expected_secret and auth_header != f"Bearer {expected_secret}"):
                logger.warning(f"Unauthorized RevenueCat webhook attempt: auth_header={auth_header}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid RevenueCat webhook secret authorization."
                )

        event_data = payload.get("event", {})
        event_type = event_data.get("type")
        app_user_id = event_data.get("app_user_id")  # In Mishil, this maps to user.id or email
        product_id = event_data.get("product_id", "")
        
        logger.info(f"Processing RevenueCat event {event_type} for user_id={app_user_id}")

        if not app_user_id:
            return {"status": "ignored", "reason": "No app_user_id in payload"}

        # Find user
        user = None
        if str(app_user_id).isdigit():
            user = db.query(User).filter(User.id == int(app_user_id)).first()
        if not user:
            user = db.query(User).filter(User.email == str(app_user_id)).first()

        if not user:
            logger.warning(f"User not found for RevenueCat webhook: {app_user_id}")
            return {"status": "user_not_found", "app_user_id": app_user_id}

        sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
        if not sub:
            sub = Subscription(user_id=user.id)
            db.add(sub)

        sub.provider_ref = event_data.get("original_transaction_id") or str(app_user_id)
        
        # Map product_id to Plan
        if "yearly" in product_id.lower() or "annual" in product_id.lower():
            sub.plan = SubscriptionPlan.YEARLY
        elif "weekly" in product_id.lower():
            sub.plan = SubscriptionPlan.WEEKLY
        elif "lifetime" in product_id.lower():
            sub.plan = SubscriptionPlan.LIFETIME
        else:
            sub.plan = SubscriptionPlan.MONTHLY

        # Update status based on event type
        if event_type in ["INITIAL_PURCHASE", "RENEWAL", "NON_RENEWING_PURCHASE", "UNCANCELLATION"]:
            sub.status = SubscriptionStatus.ACTIVE
            user.subscription_status = SubscriptionStatus.ACTIVE
        elif event_type == "CANCELLATION":
            sub.status = SubscriptionStatus.CANCELLED
            user.subscription_status = SubscriptionStatus.CANCELLED  # Still valid until period ends
        elif event_type == "EXPIRATION":
            sub.status = SubscriptionStatus.EXPIRED
            user.subscription_status = SubscriptionStatus.EXPIRED
        elif event_type == "BILLING_ISSUE":
            sub.status = SubscriptionStatus.GRACE_PERIOD
            # user.subscription_status stays ACTIVE during grace period

        db.commit()
        return {"status": "success", "event_type": event_type, "user_id": user.id}
