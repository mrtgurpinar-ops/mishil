from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.db.models import SleepLog, Baby, FamilyGroup, SleepType, User
from app.core.logging import get_logger

logger = get_logger("sleep_endpoint")
router = APIRouter()


class SleepLogCreateRequest(BaseModel):
    family_code: Optional[str] = Field(None, description="6-character family code")
    baby_id: Optional[int] = Field(None, description="Baby ID")
    start_time: Optional[datetime] = Field(None, description="Sleep start timestamp")
    end_time: Optional[datetime] = Field(None, description="Sleep end timestamp")
    duration_minutes: Optional[int] = Field(None, description="Duration in minutes")
    sleep_type: Optional[str] = Field("nap", description="Type: nap or night")
    notes: Optional[str] = Field(None, description="Notes")


class SleepLogResponse(BaseModel):
    id: int
    baby_id: int
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    sleep_type: str
    created_at: datetime


@router.post("/log", response_model=SleepLogResponse)
def create_or_update_sleep_log(req: SleepLogCreateRequest, db: Session = Depends(get_db)):
    """Record live sleep start or completion to PostgreSQL database."""
    try:
        baby_id = req.baby_id
        if not baby_id and req.family_code:
            family = db.query(FamilyGroup).filter(FamilyGroup.invite_code == req.family_code.upper()).first()
            if family and family.babies:
                baby_id = family.babies[0].id

        if not baby_id:
            baby = db.query(Baby).first()
            if not baby:
                user = db.query(User).first()
                if not user:
                    user = User(email="parent@mishil.app", hashed_password="default_hash", full_name="Ebeveyn")
                    db.add(user)
                    db.commit()
                    db.refresh(user)
                baby = Baby(user_id=user.id, name="Mina", birth_date=datetime(2026, 4, 11))
                db.add(baby)
                db.commit()
                db.refresh(baby)
            baby_id = baby.id

        # Determine start time and duration
        start = req.start_time or datetime.now(timezone.utc)
        duration = req.duration_minutes
        if req.end_time and not duration:
            diff = (req.end_time - start).total_seconds()
            duration = max(1, int(diff / 60))

        stype = SleepType.NIGHT if req.sleep_type == "night" else SleepType.NAP

        log = SleepLog(
            baby_id=baby_id,
            start_time=start,
            end_time=req.end_time,
            duration_minutes=duration,
            sleep_type=stype,
            notes=req.notes
        )
        db.add(log)
        db.commit()
        db.refresh(log)

        logger.info(f"Sleep log recorded in live DB: {log.id} for baby {baby_id} ({duration} mins)")

        return SleepLogResponse(
            id=log.id,
            baby_id=log.baby_id,
            start_time=log.start_time,
            end_time=log.end_time,
            duration_minutes=log.duration_minutes,
            sleep_type=log.sleep_type.value if hasattr(log.sleep_type, 'value') else str(log.sleep_type),
            created_at=log.created_at or datetime.now(timezone.utc)
        )
    except Exception as exc:
        db.rollback()
        logger.error(f"Error recording sleep log: {str(exc)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Uyku kaydı kaydedilirken hata oluştu: {str(exc)}"
        )


@router.get("/logs/{identifier}", response_model=List[SleepLogResponse])
def get_recent_sleep_logs(identifier: str, limit: int = 10, db: Session = Depends(get_db)):
    """List recent sleep logs for a baby or family group."""
    family = db.query(FamilyGroup).filter(FamilyGroup.invite_code == identifier.upper()).first()
    baby_id = None
    if family and family.babies:
        baby_id = family.babies[0].id

    if not baby_id and identifier.isdigit():
        baby_id = int(identifier)

    if not baby_id:
        baby = db.query(Baby).first()
        baby_id = baby.id if baby else 1

    logs = (
        db.query(SleepLog)
        .filter(SleepLog.baby_id == baby_id)
        .order_by(SleepLog.start_time.desc())
        .limit(limit)
        .all()
    )

    return [
        SleepLogResponse(
            id=l.id,
            baby_id=l.baby_id,
            start_time=l.start_time,
            end_time=l.end_time,
            duration_minutes=l.duration_minutes,
            sleep_type=l.sleep_type.value if hasattr(l.sleep_type, 'value') else str(l.sleep_type),
            created_at=l.created_at or datetime.now(timezone.utc)
        )
        for l in logs
    ]
