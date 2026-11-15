from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.endpoints.baby import verify_non_family_baby_owner
from app.api.v1.endpoints.family import (
    authenticate_family_member,
    ensure_device_user,
    sanitize_code,
    sanitize_device_uid,
    sanitize_plain_text,
)
from app.core.logging import get_logger
from app.db.base import get_db
from app.db.models import Baby, FamilyGroup, SleepLog, SleepType

logger = get_logger("sleep_endpoint")
router = APIRouter()


class SleepLogCreateRequest(BaseModel):
    family_code: Optional[str] = Field(None, max_length=20, description="Family invite code")
    device_uid: Optional[str] = Field(None, max_length=128, description="Device UID")
    member_token: Optional[str] = Field(None, max_length=256, description="Family member token")
    actor_name: Optional[str] = Field(None, max_length=80, description="Parent/caregiver name")
    actor_role: Optional[str] = Field(None, max_length=32, description="Parent/caregiver role")
    baby_id: Optional[int] = Field(None, description="Baby ID")
    client_id: Optional[str] = Field(None, max_length=128, description="Client-side routine ID (e.g., slp_1730...)")
    original_start_time: Optional[datetime] = Field(None, description="Original start timestamp before edit")
    start_time: Optional[datetime] = Field(None, description="Sleep start timestamp")
    end_time: Optional[datetime] = Field(None, description="Sleep end timestamp")
    duration_minutes: Optional[int] = Field(None, ge=1, le=1440, description="Duration in minutes")
    sleep_type: Optional[str] = Field("nap", max_length=16, description="Type: nap or night")
    notes: Optional[str] = Field(None, max_length=500, description="Notes")
    is_update: Optional[bool] = Field(False, description="Update matching sleep log if True")


class SleepLogResponse(BaseModel):
    id: int
    baby_id: int
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    sleep_type: str
    created_at: datetime


@router.post("/log", response_model=SleepLogResponse)
def create_or_update_sleep_log(
    req: SleepLogCreateRequest,
    db: Session = Depends(get_db),
    x_family_member_token: Optional[str] = Header(None, alias="X-Family-Member-Token"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """Record live sleep start or completion to PostgreSQL with strict family/device isolation."""
    raw_header_tok = x_family_member_token if isinstance(x_family_member_token, str) else None
    raw_tok = (raw_header_tok or req.member_token or "").strip() or None
    clean_dev = sanitize_device_uid(req.device_uid)

    try:
        if req.start_time and req.end_time and req.end_time < req.start_time:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bitiş zamanı başlangıç zamanından önce olamaz.",
            )

        baby_id = req.baby_id
        clean_fcode = sanitize_code(req.family_code)
        if clean_fcode == "MSL782":
            clean_fcode = ""

        if clean_fcode:
            family = db.query(FamilyGroup).filter(FamilyGroup.invite_code == clean_fcode).first()
            if not family:
                raise HTTPException(status_code=404, detail="Aile kodu bulunamadı.")

            active_members = [m for m in family.members if m.is_active is not False]
            if any(bool(m.member_token_hash) for m in active_members):
                member = authenticate_family_member(db, family, raw_tok, clean_dev)
                if not member:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Bu aileye uyku kaydı eklemek için geçerli üye anahtarı gereklidir.",
                    )

            family_baby_ids = {b.id for b in family.babies}
            if baby_id is not None:
                if baby_id not in family_baby_ids:
                    raise HTTPException(status_code=403, detail="Bu bebek belirtilen aileye ait değil.")
            else:
                if not family_baby_ids:
                    raise HTTPException(status_code=404, detail="Aileye kayıtlı bebek bulunamadı.")
                baby_id = family.babies[0].id
        elif baby_id is not None:
            baby_obj = db.query(Baby).filter(Baby.id == baby_id).first()
            if not baby_obj:
                raise HTTPException(status_code=404, detail="Bebek bulunamadı.")
            if baby_obj.family_id:
                fam = db.query(FamilyGroup).filter(FamilyGroup.id == baby_obj.family_id).first()
                if not fam:
                    raise HTTPException(status_code=403, detail="Bu bebeğe uyku yazma yetkiniz yok.")
                if any(bool(m.member_token_hash) for m in fam.members if m.is_active is not False):
                    if not authenticate_family_member(db, fam, raw_tok, clean_dev):
                        raise HTTPException(status_code=403, detail="Bu bebeğe uyku yazma yetkiniz yok.")
            elif not verify_non_family_baby_owner(baby_obj, clean_dev, authorization):
                raise HTTPException(status_code=403, detail="Bu bebeğe uyku yazma yetkiniz yok.")
        elif clean_dev:
            # Isolated per-device baby (never touches another user's baby!)
            baby_obj = db.query(Baby).filter(Baby.device_uid == clean_dev, Baby.family_id.is_(None)).first()
            if not baby_obj:
                user, _ = ensure_device_user(db, clean_dev, display_name="Ebeveyn")
                baby_obj = Baby(
                    user_id=user.id,
                    device_uid=clean_dev,
                    name="Bebeğim",
                    birth_date=datetime(2026, 4, 11, tzinfo=timezone.utc),
                )
                db.add(baby_obj)
                db.flush()
            baby_id = baby_obj.id
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uyku kaydı için baby_id, family_code veya device_uid gereklidir.",
            )

        start = req.start_time or datetime.now(timezone.utc)
        duration = req.duration_minutes
        if req.start_time and req.end_time:
            diff = (req.end_time - req.start_time).total_seconds()
            if diff > 0:
                duration = max(1, min(1440, int(round(diff / 60))))
        elif req.end_time and not duration:
            diff = (req.end_time - start).total_seconds()
            if diff > 0:
                duration = max(1, min(1440, int(diff / 60)))

        stype = SleepType.NIGHT if req.sleep_type == "night" else SleepType.NAP
        clean_cid = sanitize_device_uid(req.client_id)[:120] if req.client_id else None
        cid_tag = f"[cid:{clean_cid}]" if clean_cid else ""
        merged_notes = sanitize_plain_text(req.notes, max_len=400) if req.notes else ""
        if cid_tag and cid_tag not in merged_notes:
            merged_notes = f"{merged_notes} {cid_tag}".strip()

        actor_nm = sanitize_plain_text(req.actor_name, max_len=60) if req.actor_name else None
        actor_rl = sanitize_plain_text(req.actor_role, max_len=32) if req.actor_role else None

        log: Optional[SleepLog] = None
        if clean_cid:
            # Exact indexed lookup first
            log = (
                db.query(SleepLog)
                .filter(SleepLog.baby_id == baby_id, SleepLog.client_id == clean_cid)
                .order_by(SleepLog.id.desc())
                .first()
            )

        if not log and req.is_update:
            if cid_tag:
                escaped_cid_tag = (
                    cid_tag.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                )
                candidates = (
                    db.query(SleepLog)
                    .filter(
                        SleepLog.baby_id == baby_id,
                        SleepLog.notes.like(f"%{escaped_cid_tag}%", escape="\\"),
                    )
                    .order_by(SleepLog.id.desc())
                    .all()
                )
                for candidate in candidates:
                    if cid_tag in (candidate.notes or "").split():
                        log = candidate
                        break
            if not log and req.original_start_time:
                log = (
                    db.query(SleepLog)
                    .filter(SleepLog.baby_id == baby_id, SleepLog.start_time == req.original_start_time)
                    .order_by(SleepLog.id.desc())
                    .first()
                )

        if log:
            if req.start_time:
                log.start_time = req.start_time
            if req.end_time:
                log.end_time = req.end_time
            if duration is not None:
                log.duration_minutes = duration
            if req.sleep_type is not None:
                log.sleep_type = stype
            if clean_cid and not log.client_id:
                log.client_id = clean_cid
            if actor_nm:
                log.actor_name = actor_nm
            if actor_rl:
                log.actor_role = actor_rl
            if merged_notes:
                log.notes = merged_notes
            db.commit()
            db.refresh(log)
            logger.info(f"Sleep log updated in live DB: {log.id} for baby {baby_id} ({duration} mins, cid={clean_cid})")
        else:
            log = SleepLog(
                baby_id=baby_id,
                client_id=clean_cid,
                actor_name=actor_nm,
                actor_role=actor_rl,
                is_deleted=False,
                start_time=start,
                end_time=req.end_time,
                duration_minutes=duration,
                sleep_type=stype,
                notes=merged_notes or None,
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
            sleep_type=log.sleep_type.value if hasattr(log.sleep_type, "value") else str(log.sleep_type),
            created_at=log.created_at or datetime.now(timezone.utc),
        )
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.error(f"Error recording sleep log: {str(exc)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Uyku kaydı kaydedilirken beklenmeyen bir hata oluştu.",
        )


@router.get("/logs/{identifier}", response_model=List[SleepLogResponse])
def get_recent_sleep_logs(
    identifier: str,
    limit: int = Query(10, ge=1, le=100),
    device_uid: Optional[str] = Query(None, max_length=128),
    x_family_member_token: Optional[str] = Header(None, alias="X-Family-Member-Token"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    """List recent sleep logs strictly for an authorized baby or family group."""
    raw_tok = x_family_member_token if isinstance(x_family_member_token, str) else None
    clean_dev = sanitize_device_uid(device_uid) if isinstance(device_uid, str) else ""
    safe_limit = max(1, min(100, int(limit) if isinstance(limit, int) else 10))

    if identifier.isdigit():
        baby_id = int(identifier)
        baby = db.query(Baby).filter(Baby.id == baby_id).first()
        if not baby:
            raise HTTPException(status_code=404, detail="Bebek bulunamadı.")
        if baby.family_id:
            fam = db.query(FamilyGroup).filter(FamilyGroup.id == baby.family_id).first()
            if not fam:
                raise HTTPException(status_code=403, detail="Uyku geçmişine erişim yetkiniz yok.")
            if any(bool(m.member_token_hash) for m in fam.members if m.is_active is not False):
                if not authenticate_family_member(db, fam, raw_tok, clean_dev):
                    raise HTTPException(status_code=403, detail="Uyku geçmişine erişim yetkiniz yok.")
        elif not verify_non_family_baby_owner(baby, clean_dev, authorization):
            raise HTTPException(status_code=403, detail="Uyku geçmişine erişim yetkiniz yok.")
    else:
        code = sanitize_code(identifier)
        family = db.query(FamilyGroup).filter(FamilyGroup.invite_code == code).first()
        if not family:
            raise HTTPException(status_code=404, detail="Aile kodu bulunamadı.")
        if any(bool(m.member_token_hash) for m in family.members if m.is_active is not False):
            if not authenticate_family_member(db, family, raw_tok, clean_dev):
                raise HTTPException(status_code=403, detail="Uyku geçmişine erişim yetkiniz yok.")
        if not family.babies:
            raise HTTPException(status_code=404, detail="Aileye kayıtlı bebek bulunamadı.")
        baby_id = family.babies[0].id

    logs = (
        db.query(SleepLog)
        .filter(SleepLog.baby_id == baby_id, (SleepLog.is_deleted.is_(False)) | (SleepLog.is_deleted.is_(None)))
        .order_by(SleepLog.start_time.desc())
        .limit(safe_limit)
        .all()
    )

    return [
        SleepLogResponse(
            id=l.id,
            baby_id=l.baby_id,
            start_time=l.start_time,
            end_time=l.end_time,
            duration_minutes=l.duration_minutes,
            sleep_type=l.sleep_type.value if hasattr(l.sleep_type, "value") else str(l.sleep_type),
            created_at=l.created_at or datetime.now(timezone.utc),
        )
        for l in logs
    ]
