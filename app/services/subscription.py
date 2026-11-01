from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import User, Subscription, SubscriberLedger, SubscriptionLifecycleEvent
from app.models.enums import SubscriptionStatus, SubscriptionPlan
from app.models.schemas import SubscriptionResponse

logger = get_logger("subscription")


class SubscriptionService:
    """Subscription lifecycle, 3-day trial and RevenueCat webhook synchronization."""

    @classmethod
    def calculate_status(cls, user: User, subscription: Optional[Subscription]) -> Dict[str, Any]:
        """Determine active status, remaining trial days, and effective subscription tier."""
        now = datetime.now(timezone.utc)
        
        # Check active paid subscription (or cancelled/grace-period subscription still within paid period)
        if subscription and subscription.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.GRACE_PERIOD):
            return {
                "status": subscription.status,
                "plan": subscription.plan,
                "trial_ends_at": subscription.trial_ends_at,
                "is_active": True,
                "days_left_in_trial": None,
            }
        if subscription and subscription.status == SubscriptionStatus.CANCELLED and subscription.trial_ends_at:
            end_dt = subscription.trial_ends_at
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)
            if end_dt > now:
                delta = end_dt - now
                days_left = max(0, delta.days + (1 if delta.seconds > 0 else 0))
                return {
                    "status": SubscriptionStatus.CANCELLED,
                    "plan": subscription.plan,
                    "trial_ends_at": end_dt,
                    "is_active": True,
                    "days_left_in_trial": days_left,
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
        """Start a 7-day free trial for user if not previously used."""
        now = datetime.now(timezone.utc)
        trial_ends_at = now + timedelta(days=settings.TRIAL_DURATION_DAYS)

        # Check existing subscription
        sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
        if sub and sub.trial_ends_at and sub.trial_ends_at < now:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Daha önce 7 günlük ücretsiz deneme süresi kullanılmış."
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
        app_user_id = event_data.get("app_user_id") or event_data.get("original_app_user_id")
        product_id = str(event_data.get("product_id") or "")
        store_raw = str(event_data.get("store") or "").upper()
        period_type = str(event_data.get("period_type") or "NORMAL").upper()
        country_code = str(event_data.get("country_code") or "TR").upper()
        currency_code = str(event_data.get("currency") or "TRY").upper()
        price_in_purchased_currency = float(event_data.get("price_in_purchased_currency") or event_data.get("price") or 0.0)
        fx_rates = {"TRY": 1.0, "EUR": 37.50, "USD": 34.50, "GBP": 43.50, "AUD": 22.50, "CAD": 25.00, "CHF": 39.50}
        price_in_try = round(price_in_purchased_currency * fx_rates.get(currency_code, 1.0), 2)
        takehome_pct = float(event_data.get("takehome_percentage") or (0.727 if "PLAY" in store_raw else 0.55417))
        if takehome_pct > 1.0:
            takehome_pct = takehome_pct / 100.0

        logger.info(f"Processing RevenueCat event {event_type} for user_id={app_user_id} store={store_raw} product={product_id}")

        if not app_user_id:
            return {"status": "ignored", "reason": "No app_user_id in payload"}

        pid_low = product_id.lower().strip()
        is_annual_prod = (
            "yearly" in pid_low
            or "annual" in pid_low
            or pid_low in ("misil", "6809228257")
            or pid_low.startswith("misil:")
        )
        platform_str = "android" if ("PLAY" in store_raw or pid_low in ("misil", "misilaylik") or pid_low.startswith("misil")) and not pid_low.startswith("misil_") else "ios"
        if "APP_STORE" in store_raw or "MAC_APP_STORE" in store_raw:
            platform_str = "ios"
        elif "PLAY_STORE" in store_raw:
            platform_str = "android"

        # Upsert SubscriberLedger & SubscriptionLifecycleEvent for Founder Dashboard (even for anonymous users)
        try:
            sub_uid = str(event_data.get("original_transaction_id") or event_data.get("transaction_id") or app_user_id)
            now_dt = datetime.now(timezone.utc)
            purchased_ms = event_data.get("purchased_at_ms")
            exp_ms = event_data.get("expiration_at_ms")
            start_dt = datetime.fromtimestamp(float(purchased_ms) / 1000.0, tz=timezone.utc) if purchased_ms else now_dt
            exp_dt = (
                datetime.fromtimestamp(float(exp_ms) / 1000.0, tz=timezone.utc)
                if exp_ms
                else (start_dt + timedelta(days=7 if period_type == "TRIAL" else (365 if is_annual_prod else 30)))
            )
            start_str = start_dt.strftime("%Y-%m-%d")
            exp_str = exp_dt.strftime("%Y-%m-%d")

            exp_gross = 599.99 if is_annual_prod else 149.99
            exp_net = round(exp_gross * (0.727 if platform_str == "android" else 0.55417), 2)

            if event_type in ("CANCELLATION", "EXPIRATION"):
                ledger_status = "cancelled"
                auto_renew = False
            elif period_type == "TRIAL" or (price_in_purchased_currency <= 0.0 and event_type == "INITIAL_PURCHASE"):
                ledger_status = "intro_free_trial"
                auto_renew = True
            elif period_type == "PROMOTIONAL":
                ledger_status = "offer_code_trial"
                auto_renew = True
            else:
                ledger_status = "paid_active"
                auto_renew = True

            realized_gross = round(price_in_try, 2) if ledger_status == "paid_active" and price_in_try > 0 else (exp_gross if ledger_status == "paid_active" else 0.0)
            realized_net = round(realized_gross * takehome_pct, 2) if realized_gross > 0 else 0.0
            plan_lbl = (
                ("Mışıl Baby Yıllık VIP (Android)" if is_annual_prod else "Mışıl Baby Aylık VIP (Android)")
                if platform_str == "android"
                else ("Mışıl Yıllık VIP" if is_annual_prod else "Mışıl Aylık Esnek")
            )

            ledger_row = db.query(SubscriberLedger).filter(SubscriberLedger.subscriber_id == sub_uid).first()
            offer_type_val = (
                "offer_code"
                if ledger_status == "offer_code_trial"
                else ("intro_7d_trial" if ledger_status == "intro_free_trial" else "standard_paid")
            )
            prod_id_resolved = product_id or (
                "misil"
                if platform_str == "android" and is_annual_prod
                else ("misilaylik" if platform_str == "android" else ("misil_annual" if is_annual_prod else "misil_monthly"))
            )
            if not ledger_row:
                ledger_row = SubscriberLedger(
                    subscriber_id=sub_uid,
                    platform=platform_str,
                    product_id=prod_id_resolved,
                    plan_label=plan_lbl,
                    status=ledger_status,
                    offer_type=offer_type_val,
                    offer_code_name=event_data.get("presented_offering_id") if ledger_status == "offer_code_trial" else None,
                    started_date=start_str,
                    converted_or_renewed_date=start_str,
                    maturity_or_renewal_date=exp_str,
                    customer_price_try=realized_gross,
                    developer_proceeds_try=realized_net,
                    expected_next_price_try=exp_gross if auto_renew else 0.0,
                    expected_next_proceeds_try=exp_net if auto_renew else 0.0,
                    country=country_code,
                    device_type="Android" if platform_str == "android" else "iPhone",
                    auto_renew_enabled=auto_renew,
                )
                db.add(ledger_row)
            else:
                # Out-of-order koruması: daha eski bir olayın daha yeni bir iptal/dönüşüm durumunu ezmesini engelle
                is_stale_event = bool(
                    ledger_row.converted_or_renewed_date
                    and start_str < ledger_row.converted_or_renewed_date
                    and ledger_row.status == "cancelled"
                    and event_type == "INITIAL_PURCHASE"
                )
                if not is_stale_event:
                    ledger_row.platform = platform_str
                    ledger_row.status = ledger_status
                    ledger_row.offer_type = offer_type_val
                    ledger_row.auto_renew_enabled = auto_renew
                    ledger_row.converted_or_renewed_date = start_str
                    ledger_row.maturity_or_renewal_date = exp_str
                    if realized_gross > 0:
                        ledger_row.customer_price_try = realized_gross
                        ledger_row.developer_proceeds_try = realized_net
                    ledger_row.expected_next_price_try = exp_gross if auto_renew else 0.0
                    ledger_row.expected_next_proceeds_try = exp_net if auto_renew else 0.0

            evt_type_key = f"RC:{event_type}:{sub_uid}"[:128]
            if not (
                db.query(SubscriptionLifecycleEvent)
                .filter(
                    SubscriptionLifecycleEvent.event_date == start_str,
                    SubscriptionLifecycleEvent.event_type == evt_type_key,
                    SubscriptionLifecycleEvent.product_id == prod_id_resolved,
                )
                .first()
            ):
                db.add(
                    SubscriptionLifecycleEvent(
                        event_date=start_str,
                        platform=platform_str,
                        event_type=evt_type_key,
                        product_id=prod_id_resolved,
                        plan_label=plan_lbl,
                        offer_code_name=ledger_row.offer_code_name,
                        country=country_code,
                        device_type="Android" if platform_str == "android" else "iPhone",
                        quantity=1,
                    )
                )
            db.commit()
        except Exception as ledger_err:
            db.rollback()
            logger.warning(f"SubscriberLedger upsert failed inside RevenueCat webhook: {ledger_err}")

        # Find user
        user = None
        if str(app_user_id).isdigit():
            user = db.query(User).filter(User.id == int(app_user_id)).first()
        if not user:
            user = db.query(User).filter(User.email == str(app_user_id)).first()

        if not user:
            logger.warning(f"User not found for RevenueCat webhook: {app_user_id} (SubscriberLedger updated)")
            return {"status": "user_not_found", "app_user_id": app_user_id, "ledger_synced": True}

        sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
        if not sub:
            sub = Subscription(user_id=user.id)
            db.add(sub)

        sub.provider_ref = event_data.get("original_transaction_id") or str(app_user_id)

        # Map product_id to Plan
        if is_annual_prod:
            sub.plan = SubscriptionPlan.YEARLY
        elif "weekly" in pid_low:
            sub.plan = SubscriptionPlan.WEEKLY
        elif "lifetime" in pid_low:
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
