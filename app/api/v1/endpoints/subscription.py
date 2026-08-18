from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.db.models import User, Subscription
from app.models.schemas import SubscriptionResponse, StartTrialRequest
from app.services.subscription import SubscriptionService
from .auth import get_current_user

router = APIRouter(prefix="/subscription", tags=["Subscription & RevenueCat"])


@router.post("/start-trial", response_model=SubscriptionResponse)
def start_free_trial(
    payload: Optional[StartTrialRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Activate 3-day free trial period for the authenticated user.
    """
    return SubscriptionService.start_trial(db=db, user=current_user)


@router.get("/status", response_model=SubscriptionResponse)
def get_subscription_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Check current user's subscription tier, trial days left, and active status.
    """
    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    state = SubscriptionService.calculate_status(current_user, sub)

    return SubscriptionResponse(
        user_id=current_user.id,
        status=state["status"],
        plan=state["plan"],
        trial_ends_at=state["trial_ends_at"],
        is_active=state["is_active"],
        days_left_in_trial=state["days_left_in_trial"],
    )


@router.post("/webhook")
def revenuecat_webhook(
    payload: Dict[str, Any],
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    """
    RevenueCat server-to-server webhook endpoint for auto-syncing purchases, renewals, and cancellations.
    """
    result = SubscriptionService.process_revenuecat_webhook(
        db=db, payload=payload, auth_header=authorization
    )
    return result
