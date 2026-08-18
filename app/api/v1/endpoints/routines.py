from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Path
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.db.models import User, Baby, RoutineLog, SleepLog
from app.models.enums import RoutineType, SleepType
from app.models.schemas import RoutineLogCreateRequest, RoutineLogResponse
from .auth import get_current_user

router = APIRouter(prefix="/routines", tags=["Baby Routines & Logs"])


@router.post("/{routine_type}", response_model=RoutineLogResponse, status_code=status.HTTP_201_CREATED)
def create_routine_log(
    routine_type: RoutineType = Path(..., description="Rutin türü: feeding, diaper, sleep, bath, mood, tummy_time"),
    payload: RoutineLogCreateRequest = ...,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Log a daily baby routine event (feeding amount/duration, diaper wet/dirty, bath, mood, sleep).
    """
    baby = db.query(Baby).filter(Baby.id == payload.baby_id, Baby.user_id == current_user.id).first()
    if not baby:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bebek bulunamadı veya bu hesaba ait değil."
        )

    start_time = payload.start_time or datetime.now(timezone.utc)
    
    log = RoutineLog(
        baby_id=payload.baby_id,
        routine_type=routine_type,
        start_time=start_time,
        end_time=payload.end_time,
        details_json=payload.details,
        notes=payload.notes,
    )
    db.add(log)

    # If routine_type is sleep, also record in sleep_logs table
    if routine_type == RoutineType.SLEEP:
        duration = None
        if payload.end_time:
            duration = int((payload.end_time - start_time).total_seconds() // 60)
        
        sleep_log = SleepLog(
            baby_id=payload.baby_id,
            start_time=start_time,
            end_time=payload.end_time,
            duration_minutes=duration,
            sleep_type=SleepType.NAP if (duration is None or duration < 240) else SleepType.NIGHT,
            notes=payload.notes,
        )
        db.add(sleep_log)

    db.commit()
    db.refresh(log)

    return RoutineLogResponse(
        id=log.id,
        baby_id=log.baby_id,
        routine_type=log.routine_type,
        start_time=log.start_time,
        end_time=log.end_time,
        details=log.details_json,
        notes=log.notes,
        created_at=log.created_at,
    )


@router.get("/baby/{baby_id}", response_model=List[RoutineLogResponse])
def get_baby_routines(
    baby_id: int,
    routine_type: Optional[RoutineType] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve logged daily routines for specific baby.
    """
    baby = db.query(Baby).filter(Baby.id == baby_id, Baby.user_id == current_user.id).first()
    if not baby:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bebek bulunamadı veya bu hesaba ait değil."
        )

    query = db.query(RoutineLog).filter(RoutineLog.baby_id == baby_id)
    if routine_type:
        query = query.filter(RoutineLog.routine_type == routine_type)

    logs = query.order_by(RoutineLog.start_time.desc()).limit(limit).all()

    return [
        RoutineLogResponse(
            id=l.id,
            baby_id=l.baby_id,
            routine_type=l.routine_type,
            start_time=l.start_time,
            end_time=l.end_time,
            details=l.details_json,
            notes=l.notes,
            created_at=l.created_at,
        )
        for l in logs
    ]
