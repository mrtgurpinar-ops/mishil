from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.db.models import Baby, FamilyGroup, FamilyMember, DevelopmentLog, User
from app.core.logging import get_logger

logger = get_logger("baby_endpoint")
router = APIRouter()


class BabyProfileRequest(BaseModel):
    family_code: Optional[str] = Field(None, description="6-character family sync code")
    name: str = Field("Mina", description="Baby name")
    birth_date: str = Field("2026-04-11", description="Birth date in YYYY-MM-DD format")
    gender: Optional[str] = Field(None, description="Gender (boy/girl/unspecified)")


class BabyProfileResponse(BaseModel):
    status: str
    message: str
    baby_id: int
    name: str
    birth_date: str
    age_days: int
    current_week: int
    family_code: Optional[str] = None
    created_at: datetime


@router.post("/profile", response_model=BabyProfileResponse)
def save_or_update_baby_profile(req: BabyProfileRequest, db: Session = Depends(get_db)):
    """Save or update baby profile in live PostgreSQL database."""
    try:
        bdate = datetime.strptime(req.birth_date, "%Y-%m-%d")
        today = datetime.now(timezone.utc).date()
        diff_days = max(1, (today - bdate.date()).days)
        current_week = max(1, diff_days // 7)

        # Look up by family code or create default user & family
        family = None
        if req.family_code:
            family = db.query(FamilyGroup).filter(FamilyGroup.invite_code == req.family_code.upper()).first()

        baby = None
        if family and family.babies:
            baby = family.babies[0]

        if not baby:
            baby = db.query(Baby).filter(Baby.name == req.name).first()

        if not baby:
            # Ensure at least one user exists
            user = db.query(User).first()
            if not user:
                user = User(email="parent@mishil.app", hashed_password="default_hash", full_name="Ebeveyn")
                db.add(user)
                db.commit()
                db.refresh(user)

            baby = Baby(
                user_id=user.id,
                family_id=family.id if family else None,
                name=req.name,
                birth_date=bdate,
                gender=req.gender,
                development_score=84
            )
            db.add(baby)
            db.commit()
            db.refresh(baby)
        else:
            baby.name = req.name
            baby.birth_date = bdate
            if req.gender:
                baby.gender = req.gender
            if family and not baby.family_id:
                baby.family_id = family.id
            db.commit()
            db.refresh(baby)

        logger.info(f"Baby profile saved for {baby.name} (ID: {baby.id}) in live database.")

        return BabyProfileResponse(
            status="ok",
            message=f"{baby.name} bebeğin profili canlı veritabanına başarıyla kaydedildi.",
            baby_id=baby.id,
            name=baby.name,
            birth_date=baby.birth_date.strftime("%Y-%m-%d"),
            age_days=diff_days,
            current_week=current_week,
            family_code=family.invite_code if family else req.family_code,
            created_at=baby.created_at or datetime.now(timezone.utc)
        )
    except Exception as exc:
        db.rollback()
        logger.error(f"Error saving baby profile: {str(exc)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bebek profili kaydedilirken hata oluştu: {str(exc)}"
        )


@router.get("/profile/{identifier}", response_model=BabyProfileResponse)
def get_baby_profile(identifier: str, db: Session = Depends(get_db)):
    """Retrieve baby profile by Baby ID or Family Invite Code."""
    family = db.query(FamilyGroup).filter(FamilyGroup.invite_code == identifier.upper()).first()
    baby = None
    if family and family.babies:
        baby = family.babies[0]

    if not baby and identifier.isdigit():
        baby = db.query(Baby).filter(Baby.id == int(identifier)).first()

    if not baby:
        baby = db.query(Baby).first()

    if not baby:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kayıtlı bebek profili bulunamadı."
        )

    today = datetime.now(timezone.utc).date()
    diff_days = max(1, (today - baby.birth_date.date()).days)
    current_week = max(1, diff_days // 7)

    return BabyProfileResponse(
        status="ok",
        message="Bebek profili canlı veritabanından yüklendi.",
        baby_id=baby.id,
        name=baby.name,
        birth_date=baby.birth_date.strftime("%Y-%m-%d"),
        age_days=diff_days,
        current_week=current_week,
        family_code=family.invite_code if family else None,
        created_at=baby.created_at or datetime.now(timezone.utc)
    )
