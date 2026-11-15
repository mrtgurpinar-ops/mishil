from datetime import datetime, timezone
import hmac
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.endpoints.family import (
    authenticate_family_member,
    ensure_device_user,
    hash_member_token,
    sanitize_code,
    sanitize_device_uid,
    sanitize_plain_text,
)
from app.core.logging import get_logger
from app.core.security import decode_access_token
from app.db.base import get_db
from app.db.models import Baby, FamilyGroup, FamilyMember, generate_room_key


def verify_non_family_baby_owner(
    baby: Baby,
    clean_dev: str,
    authorization: Optional[str] = None,
) -> bool:
    """Verify ownership of a non-family Baby via Bearer JWT user_id OR constant-time device_uid match."""
    raw_auth = authorization if isinstance(authorization, str) else None
    if raw_auth and raw_auth.lower().startswith("bearer "):
        jwt_tok = raw_auth.split(" ", 1)[1].strip()
        if jwt_tok:
            try:
                claims = decode_access_token(jwt_tok)
                if str(claims.get("sub") or "") == str(baby.user_id):
                    return True
            except Exception:
                pass
    if baby.device_uid and clean_dev and hmac.compare_digest(baby.device_uid, clean_dev):
        return True
    return False

logger = get_logger("baby_endpoint")
router = APIRouter()


class BabyProfileRequest(BaseModel):
    family_code: Optional[str] = Field(None, max_length=20, description="Family invite code")
    device_uid: Optional[str] = Field(None, max_length=128, description="Isolated device UID")
    member_token: Optional[str] = Field(None, max_length=256, description="Family member auth token")
    name: str = Field("Bebeğim", min_length=1, max_length=80, description="Baby name")
    birth_date: str = Field("2026-04-11", max_length=16, description="Birth date in YYYY-MM-DD format")
    gender: Optional[str] = Field(None, max_length=20, description="Gender (boy/girl/unspecified)")
    premature_weeks: Optional[int] = Field(default=0, ge=0, le=20)


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
def save_or_update_baby_profile(
    req: BabyProfileRequest,
    db: Session = Depends(get_db),
    x_family_member_token: Optional[str] = Header(None, alias="X-Family-Member-Token"),
):
    """Save or update baby profile with strict tenant isolation (zero cross-user fallback)."""
    raw_header_tok = x_family_member_token if isinstance(x_family_member_token, str) else None
    raw_tok = (raw_header_tok or req.member_token or "").strip() or None

    try:
        bdate = datetime.strptime(req.birth_date.strip()[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Doğum tarihi YYYY-MM-DD biçiminde olmalıdır.",
        )

    try:
        today = datetime.now(timezone.utc).date()
        diff_days = max(1, (today - bdate.date()).days)
        current_week = max(1, diff_days // 7)
        safe_name = sanitize_plain_text(req.name, max_len=60, default="Bebeğim")
        user, clean_uid = ensure_device_user(db, req.device_uid, display_name="Ebeveyn")

        clean_fcode = sanitize_code(req.family_code)
        if clean_fcode == "MSL782":
            clean_fcode = ""

        family: Optional[FamilyGroup] = None
        if clean_fcode and len(clean_fcode) >= 4:
            family = db.query(FamilyGroup).filter(FamilyGroup.invite_code == clean_fcode).first()
            if family:
                active_members = [m for m in family.members if m.is_active is not False]
                has_protected_members = any(bool(m.member_token_hash) for m in active_members)
                if has_protected_members:
                    authed = authenticate_family_member(db, family, raw_tok, clean_uid)
                    if not authed:
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="Bu aile grubundaki bebek profilini güncelleme yetkiniz yok.",
                        )
            else:
                family = FamilyGroup(
                    name=f"{safe_name}'in Ailesi",
                    invite_code=clean_fcode,
                    room_key=generate_room_key(),
                    max_members=3,
                    created_by_user_id=user.id,
                )
                db.add(family)
                db.flush()
                tok_init = "mft_" + secrets.token_urlsafe(24)
                db.add(
                    FamilyMember(
                        family_id=family.id,
                        user_id=user.id,
                        role="mother",
                        nickname="Ebeveyn",
                        device_uid=clean_uid,
                        member_token_hash=hash_member_token(tok_init) if req.device_uid else None,
                        is_active=True,
                        can_edit=True,
                    )
                )
                db.flush()

        baby: Optional[Baby] = None
        if family and family.babies:
            baby = family.babies[0]
        elif not family and req.device_uid:
            baby = (
                db.query(Baby)
                .filter(Baby.device_uid == clean_uid, Baby.family_id.is_(None))
                .first()
            )

        if not baby:
            baby = Baby(
                user_id=family.created_by_user_id if family else user.id,
                family_id=family.id if family else None,
                device_uid=clean_uid,
                name=safe_name,
                birth_date=bdate,
                gender=sanitize_plain_text(req.gender, max_len=20) if req.gender else None,
                premature_weeks=req.premature_weeks or 0,
                development_score=84,
            )
            db.add(baby)
        else:
            baby.name = safe_name
            baby.birth_date = bdate
            if req.gender:
                baby.gender = sanitize_plain_text(req.gender, max_len=20)
            if req.premature_weeks is not None:
                baby.premature_weeks = req.premature_weeks
            if family and not baby.family_id:
                baby.family_id = family.id

        db.commit()
        db.refresh(baby)
        logger.info(f"Baby profile saved for ID={baby.id} in live database.")

        return BabyProfileResponse(
            status="ok",
            message=f"{baby.name} bebeğin profili başarıyla kaydedildi.",
            baby_id=baby.id,
            name=baby.name,
            birth_date=baby.birth_date.strftime("%Y-%m-%d"),
            age_days=diff_days,
            current_week=current_week,
            family_code=family.invite_code if family else (clean_fcode or None),
            created_at=baby.created_at or datetime.now(timezone.utc),
        )
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.error(f"Error saving baby profile: {str(exc)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Bebek profili kaydedilirken beklenmeyen bir hata oluştu.",
        )


@router.get("/profile/{identifier}", response_model=BabyProfileResponse)
def get_baby_profile(
    identifier: str,
    device_uid: Optional[str] = Query(None, max_length=128),
    x_family_member_token: Optional[str] = Header(None, alias="X-Family-Member-Token"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    """Retrieve baby profile strictly for an authorized family or owning device (NEVER falls back to Baby.first())."""
    raw_tok = x_family_member_token if isinstance(x_family_member_token, str) else None
    clean_dev = sanitize_device_uid(device_uid) if isinstance(device_uid, str) else ""

    code = sanitize_code(identifier)
    family = db.query(FamilyGroup).filter(FamilyGroup.invite_code == code).first() if code else None
    baby: Optional[Baby] = None

    if family:
        active_members = [m for m in family.members if m.is_active is not False]
        if any(bool(m.member_token_hash) for m in active_members):
            member = authenticate_family_member(db, family, raw_tok, clean_dev)
            if not member:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Bebek profilini görüntülemek için aile üyeliği doğrulanmalıdır.",
                )
        if family.babies:
            baby = family.babies[0]
    elif identifier.isdigit():
        candidate = db.query(Baby).filter(Baby.id == int(identifier)).first()
        if candidate:
            if candidate.family_id:
                fam = db.query(FamilyGroup).filter(FamilyGroup.id == candidate.family_id).first()
                if not fam:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Bu bebek profiline erişim yetkiniz yok.",
                    )
                if any(bool(m.member_token_hash) for m in fam.members if m.is_active is not False):
                    if not authenticate_family_member(db, fam, raw_tok, clean_dev):
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="Bu bebek profiline erişim yetkiniz yok.",
                        )
            elif not verify_non_family_baby_owner(candidate, clean_dev, authorization):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Bu bebek profiline erişim yetkiniz yok.",
                )
            baby = candidate

    if not baby:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kayıtlı bebek profili bulunamadı.",
        )

    today = datetime.now(timezone.utc).date()
    diff_days = max(1, (today - baby.birth_date.date()).days)
    current_week = max(1, diff_days // 7)

    return BabyProfileResponse(
        status="ok",
        message="Bebek profili yüklendi.",
        baby_id=baby.id,
        name=baby.name,
        birth_date=baby.birth_date.strftime("%Y-%m-%d"),
        age_days=diff_days,
        current_week=current_week,
        family_code=family.invite_code if family else None,
        created_at=baby.created_at or datetime.now(timezone.utc),
    )
