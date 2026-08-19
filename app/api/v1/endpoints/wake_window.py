from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.db.models import User, Baby
from app.models.schemas import WakeWindowCalculateRequest, WakeWindowResponse
from app.services.wake_window import WakeWindowService
from app.services.notification import PushNotificationService
from .auth import get_current_user

router = APIRouter(prefix="/wake-window", tags=["Wake Window & Sleep Budget"])


@router.post("/calculate", response_model=WakeWindowResponse)
async def calculate_wake_window(
    payload: WakeWindowCalculateRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Calculate dynamic wake window and remaining daily sleep projections for 0-36 months old infant.
    Includes overtired detection (<30 mins nap reduction) and 15-min pre-sleep notification timing.
    """
    response = WakeWindowService.calculate(payload)

    # Trigger push notification scheduling in background abstraction
    await PushNotificationService.send_wake_window_reminder(
        user_id=current_user.id,
        baby_name="Bebeğiniz",
        sleep_time=response.next_sleep_time,
        notification_time=response.notification_time,
    )

    return response


@router.get("/calculate/baby/{baby_id}", response_model=WakeWindowResponse)
async def calculate_for_baby(
    baby_id: int,
    previous_nap_duration: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Helper endpoint: Auto-fetch baby age from database and calculate current wake window.
    """
    from datetime import datetime, timezone

    baby = db.query(Baby).filter(Baby.id == baby_id, Baby.user_id == current_user.id).first()
    if not baby:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bebek profili bulunamadı."
        )

    req = WakeWindowCalculateRequest(
        baby_age_months=baby.age_in_months,
        last_wake_time=datetime.now(timezone.utc),
        previous_nap_duration_minutes=previous_nap_duration,
    )
    
    response = WakeWindowService.calculate(req)
    return response
