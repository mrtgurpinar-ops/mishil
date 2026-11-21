"""
Mışıl Baby — Hardened PostgreSQL Family, Co-Parenting (Max 3 Members),
Partner Whisper & Night-Watch Solidarity API Endpoints (v4.52.0).
"""
import base64
from collections import deque
import concurrent.futures
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import urllib.request
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db.base import get_db
from app.db.models import (
    Baby,
    FamilyGroup,
    FamilyMember,
    FamilyWhisper,
    NightWatchPresence,
    RoutineLog,
    SleepLog,
    SubscriberLedger,
    Subscription,
    User,
    generate_family_code,
    generate_room_key,
)
from app.models.enums import RoutineType, SleepType
from app.services.ai_sleep_coach import normalize_lang
from app.services.subscription import SubscriptionService

logger = get_logger("family_endpoint")
router = APIRouter()

MAX_FAMILY_MEMBERS_DEFAULT = 3
ALLOWED_MEMBER_ROLES = {"mother", "father", "nanny", "grandparent"}
ACTIVE_LEDGER_STATUSES = {"paid_active", "offer_code_trial", "intro_free_trial"}

# Brute-force rate limiter for /family/join (max 10 failed attempts / 10 min per IP)
_JOIN_FAIL_BUCKETS: Dict[str, deque] = {}
_JOIN_FAIL_LOCK = threading.Lock()
_JOIN_WINDOW_SEC = 600.0
_JOIN_MAX_FAILURES = 10
_RELAY_NOTIFY_POOL = concurrent.futures.ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="mishil-relay-notify",
)
_RELAY_INFLIGHT_SEM = threading.BoundedSemaphore(16)

WHISPER_TEMPLATES_TR = {
    "tea_water": "☕ Bebek uyudu ama kıpırdayamıyorum; sessizce bir su/çay getirir misin?",
    "next_shift_yours": "🌙 Bebek uyudu, ben biraz dinleniyorum. Sonraki uyanma nöbeti sende 💛",
    "trapped_under_baby": "🤫 Kucağımda uyuyakaldı! Şarjım/suyum uzakta, sessizce bakar mısın?",
    "thank_you_love": "💛 İyi ki varsın, bu geceki desteğin bana çok iyi geldi.",
    "nursing_water": "🤱 Emziriyorum ve kıpırdayamıyorum; sessizce bir su/çay getirir misin?",
    "nursing_burp_help": "🤱 Emzirme bitmek üzere; gazını çıkarmak için devralabilir misin? 💛",
    "handoff_fed_burped": "🤱 Beslendi ve gazı çıkarıldı; sıradaki uyanış nöbeti sende 💛",
}
WHISPER_TEMPLATES_EN = {
    "tea_water": "☕ Baby is asleep and I can't move—could you quietly bring some water or tea?",
    "next_shift_yours": "🌙 Baby is down, I'm resting now. You're on the next wake shift 💛",
    "trapped_under_baby": "🤫 Nap-trapped! Could you quietly check on me with water/charger?",
    "thank_you_love": "💛 Thank you for having my back tonight—it means so much.",
    "nursing_water": "🤱 I'm nursing and can't move right now—could you quietly bring some water or tea?",
    "nursing_burp_help": "🤱 Almost done nursing—could you take over for burping? 💛",
    "handoff_fed_burped": "🤱 Fed and burped—the next wake-up shift is yours 💛",
}
WHISPER_TEMPLATES_DE = {
    "tea_water": "☕ Das Baby schläft und ich kann mich kaum bewegen – bringst du mir leise Wasser/Tee?",
    "next_shift_yours": "🌙 Baby schläft, ich ruhe mich kurz aus. Die nächste Aufwach-Schicht gehört dir 💛",
    "trapped_under_baby": "🤫 Baby schläft auf meinem Arm! Kannst du leise kurz nach mir schauen?",
    "thank_you_love": "💛 Danke, dass du heute Nacht für uns da bist – das tut so gut.",
    "nursing_water": "🤱 Ich stille gerade und kann mich kaum bewegen – bringst du mir leise Wasser/Tee?",
    "nursing_burp_help": "🤱 Fast fertig mit dem Stillen – übernimmst du kurz das Bäuerchen? 💛",
    "handoff_fed_burped": "🤱 Gefüttert und Bäuerchen gemacht – die nächste Aufwach-Schicht gehört dir 💛",
}


def sanitize_code(raw_code: Optional[str]) -> str:
    cleaned = re.sub(r"[^A-Z0-9-]", "", (raw_code or "").strip().upper())
    return cleaned[:20]


def sanitize_device_uid(raw_uid: Optional[str]) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.:-]", "", (raw_uid or "").strip())
    return cleaned[:120]


def sanitize_plain_text(raw: Optional[str], max_len: int = 100, default: str = "") -> str:
    if not raw:
        return default
    cleaned = re.sub(r"[\x00-\x1f\x7f]+", " ", str(raw)).strip()
    return cleaned[:max_len] if cleaned else default


def hash_member_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def verify_token_hash(raw_token: Optional[str], expected_hash: Optional[str]) -> bool:
    if not raw_token or not expected_hash:
        return False
    actual_hash = hash_member_token(raw_token.strip())
    return hmac.compare_digest(actual_hash, expected_hash)


_DEFAULT_DEV_JWT_SECRET = "mishil_default_dev_jwt_secret_key_change_in_production_32_bytes"
_EPHEMERAL_PROD_RELAY_SECRET = secrets.token_hex(32)


def get_relay_hmac_secret() -> str:
    explicit = (os.getenv("RELAY_HMAC_SECRET") or getattr(settings, "RELAY_HMAC_SECRET", "") or "").strip()
    if explicit and explicit != _DEFAULT_DEV_JWT_SECRET:
        return explicit
    if settings.JWT_SECRET and settings.JWT_SECRET != _DEFAULT_DEV_JWT_SECRET:
        return settings.JWT_SECRET
    if settings.ENVIRONMENT.strip().lower() == "production" or os.getenv("RAILWAY_ENVIRONMENT"):
        return _EPHEMERAL_PROD_RELAY_SECRET
    return settings.JWT_SECRET


def make_realtime_token(room_key: str, role: str, name: str, ttl_sec: int = 3600) -> str:
    """Issue HMAC-SHA256 signed WebSocket room token encoding internal room_key (never public invite_code)."""
    payload_obj = {
        "rk": room_key,
        "role": role if role in ALLOWED_MEMBER_ROLES else "mother",
        "name": sanitize_plain_text(name, max_len=40, default="Ebeveyn"),
        "exp": int(time.time()) + ttl_sec,
    }
    payload_json = json.dumps(payload_obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_json).decode("ascii").rstrip("=")
    sig = hmac.new(
        get_relay_hmac_secret().encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload_b64}.{sig}"


def verify_realtime_token(token: Optional[str]) -> Optional[Dict[str, Any]]:
    if not token or "." not in token:
        return None
    try:
        payload_b64, sig_hex = token.split(".", 1)
        expected_sig = hmac.new(
            get_relay_hmac_secret().encode("utf-8"),
            payload_b64.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(sig_hex.strip().lower(), expected_sig.lower()):
            return None
        pad = "=" * (-len(payload_b64) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload_b64 + pad).decode("utf-8"))
        if int(data.get("exp") or 0) < int(time.time()):
            return None
        if not data.get("rk"):
            return None
        return data
    except Exception:
        return None


def ensure_device_user(db: Session, device_uid: Optional[str], display_name: str = "Ebeveyn") -> Tuple[User, str]:
    """Return an isolated anonymous User record bound to this device_uid (never shared across strangers)."""
    clean_uid = sanitize_device_uid(device_uid)
    if not clean_uid:
        clean_uid = "anon_" + secrets.token_hex(10)
    uid_digest = hashlib.sha256(clean_uid.encode("utf-8")).hexdigest()[:24]
    anon_email = f"dev_{uid_digest}@anon.mishil.local"
    user = db.query(User).filter(User.email == anon_email).first()
    if not user:
        user = User(
            email=anon_email,
            hashed_password="device_token_bound",
            full_name=sanitize_plain_text(display_name, max_len=80, default="Ebeveyn"),
        )
        db.add(user)
        db.flush()
    return user, clean_uid


def _infer_plan_from_product_id(product_id: Optional[str]) -> str:
    low = (product_id or "").strip().lower()
    if "annual" in low or "year" in low or low == "misil" or low.startswith("misil:"):
        return "yearly"
    return "monthly"


def _is_ledger_row_currently_active(row: SubscriberLedger) -> bool:
    if not row or row.status not in ACTIVE_LEDGER_STATUSES:
        return False
    mat = (row.maturity_or_renewal_date or "").strip()[:10]
    if len(mat) == 10:
        try:
            mat_date = datetime.strptime(mat, "%Y-%m-%d").date()
            cutoff = (datetime.now(timezone.utc) - timedelta(days=2)).date()
            if mat_date < cutoff:
                return False
        except Exception:
            pass
    return True


def verify_server_vip_entitlement(
    db: Session,
    subscriber_id: Optional[str] = None,
    original_transaction_id: Optional[str] = None,
    purchase_token: Optional[str] = None,
    device_uid: Optional[str] = None,
    owner_user_id: Optional[int] = None,
) -> Tuple[bool, str, Optional[str]]:
    """
    Strictly verify VIP status against PostgreSQL SubscriberLedger / Subscription
    (and live RevenueCat / Google Play APIs outside offline tests).
    Client-supplied `subscription_active=True` WITHOUT server proof is ALWAYS rejected.
    """
    candidate_ids: List[str] = []
    for raw_cand in (subscriber_id, original_transaction_id):
        cleaned = re.sub(r"[^a-zA-Z0-9_.:$-]", "", (raw_cand or "").strip())[:128]
        if cleaned and not cleaned.upper().startswith("DEV_"):
            candidate_ids.append(cleaned)
            if not cleaned.startswith("RC_T0_"):
                candidate_ids.append(f"RC_T0_{cleaned}"[:128])

    if purchase_token:
        tok_clean = re.sub(r"[^a-zA-Z0-9_.:-]", "", purchase_token.strip())
        if tok_clean:
            candidate_ids.append(f"GPA_TOKEN_{tok_clean[:24]}")

    for cid in candidate_ids:
        row = (
            db.query(SubscriberLedger)
            .filter((SubscriberLedger.subscriber_id == cid) | (SubscriberLedger.rc_app_user_id == cid))
            .order_by(SubscriberLedger.id.desc())
            .first()
        )
        if row and _is_ledger_row_currently_active(row):
            return True, _infer_plan_from_product_id(row.product_id), row.subscriber_id

    clean_dev = sanitize_device_uid(device_uid)
    if clean_dev:
        dev_row = (
            db.query(SubscriberLedger)
            .filter(SubscriberLedger.device_uid == clean_dev)
            .order_by(SubscriberLedger.id.desc())
            .first()
        )
        if dev_row and _is_ledger_row_currently_active(dev_row):
            return True, _infer_plan_from_product_id(dev_row.product_id), dev_row.subscriber_id

    if owner_user_id:
        owner_user = db.query(User).filter(User.id == owner_user_id).first()
        owner_sub = db.query(Subscription).filter(Subscription.user_id == owner_user_id).first()
        if owner_user and owner_sub:
            st = SubscriptionService.calculate_status(owner_user, owner_sub)
            if st.get("is_active"):
                plan_val = st.get("plan")
                plan_str = plan_val.value if hasattr(plan_val, "value") else str(plan_val or "yearly").lower()
                return True, ("yearly" if "year" in plan_str else "monthly"), f"USER_SUB_{owner_user_id}"

    # Live store fallback for T-0 purchases not yet written to SubscriberLedger
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        try:
            from app.api.v1.endpoints.analytics import (
                verify_google_play_subscription_token,
                verify_revenuecat_v2_customer,
            )
            if purchase_token:
                gp_v2 = verify_google_play_subscription_token(purchase_token.strip())
                if isinstance(gp_v2, dict):
                    sub_state = str(gp_v2.get("subscriptionState") or "")
                    if sub_state not in ("SUBSCRIPTION_STATE_CANCELED", "SUBSCRIPTION_STATE_EXPIRED", ""):
                        items = gp_v2.get("lineItems") or []
                        prod_id = str(items[0].get("productId") or "misil") if items else "misil"
                        resolved_sid = f"GPA_LIVE_{hashlib.sha256(purchase_token.encode()).hexdigest()[:20]}"
                        return True, _infer_plan_from_product_id(prod_id), resolved_sid

            raw_rc = (subscriber_id or "").strip()
            if raw_rc and "RCANONYMOUSID" in raw_rc.upper():
                rc_v2 = verify_revenuecat_v2_customer(raw_rc)
                if isinstance(rc_v2, dict) and rc_v2.get("store_subscription_identifier"):
                    if rc_v2.get("rc_status") not in ("expired", "unsubscribed"):
                        store_sid = str(rc_v2["store_subscription_identifier"])[:120]
                        return True, _infer_plan_from_product_id(rc_v2.get("product_id")), f"RC_T0_{store_sid}"
        except Exception as live_err:
            logger.warning(f"Live entitlement verification skipped: {live_err}")

    return False, "free", None


def refresh_family_vip_from_ledger(db: Session, family: FamilyGroup) -> None:
    """Re-validate family VIP status against SubscriberLedger so expired trials/subs auto-revoke."""
    if not family.vip_active and not family.vip_subscriber_id:
        return
    if family.vip_subscriber_id:
        is_ok, plan_resolved, _ = verify_server_vip_entitlement(
            db,
            subscriber_id=family.vip_subscriber_id,
            owner_user_id=family.created_by_user_id,
        )
        family.vip_active = is_ok
        family.vip_plan = plan_resolved if is_ok else "free"
        if not is_ok:
            family.vip_subscriber_id = None


def authenticate_family_member(
    db: Session,
    family: FamilyGroup,
    raw_token: Optional[str],
    device_uid: Optional[str] = None,
) -> Optional[FamilyMember]:
    """Return active FamilyMember matching raw_token (constant-time hash check)."""
    if not raw_token:
        return None
    active_members = [m for m in family.members if m.is_active is not False]
    for m in active_members:
        if verify_token_hash(raw_token, m.member_token_hash):
            if device_uid:
                clean_dev = sanitize_device_uid(device_uid)
                if clean_dev and not m.device_uid:
                    m.device_uid = clean_dev
            m.last_seen_at = datetime.now(timezone.utc)
            return m
    return None


def _ensure_family_room_key(family: FamilyGroup) -> str:
    if not family.room_key:
        family.room_key = generate_room_key()
    return family.room_key


_ROUTINE_ID_EPOCH_RE = re.compile(r"^(?:slp|rt)_(\d{12,14})(?:_|$)")


def _as_utc_dt(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _extract_routine_id_created_ms(cid: Optional[str]) -> Optional[int]:
    if not cid:
        return None
    m = _ROUTINE_ID_EPOCH_RE.match(str(cid).strip())
    if not m:
        return None
    try:
        val = int(m.group(1))
        return val if 946684800000 <= val <= 9999999999999 else None
    except Exception:
        return None


def _safe_epoch_ms(val: Any, fallback: int = 0) -> int:
    if val is None or isinstance(val, bool):
        return fallback
    try:
        parsed = int(float(val))
        return parsed if 0 < parsed <= 9999999999999 else fallback
    except Exception:
        return fallback


def _safe_pos_int(val: Any, fallback: int = 0, max_val: int = 2880) -> int:
    if val is None or isinstance(val, bool):
        return fallback
    try:
        parsed = int(round(float(val)))
        return parsed if 0 < parsed <= max_val else fallback
    except Exception:
        return fallback


def _serialize_routines_for_family(db: Session, baby_id: int, limit: int = 80) -> List[Dict[str, Any]]:
    rows = (
        db.query(RoutineLog)
        .filter(RoutineLog.baby_id == baby_id)
        .order_by(RoutineLog.start_time.desc(), RoutineLog.id.desc())
        .limit(limit)
        .all()
    )
    sleep_rows = (
        db.query(SleepLog)
        .filter(SleepLog.baby_id == baby_id, SleepLog.client_id.isnot(None))
        .order_by(SleepLog.id.asc())
        .all()
    )
    sleep_by_cid: Dict[str, SleepLog] = {str(s.client_id): s for s in sleep_rows if s.client_id}

    dirty_healed = False
    out: List[Dict[str, Any]] = []
    for r in rows:
        details = dict(r.details_json or {})
        cid = r.client_id or details.get("id") or f"rt_{r.id}"
        rtype_val = r.routine_type.value if hasattr(r.routine_type, "value") else str(r.routine_type)
        resolved_type = details.get("type") or (
            "sleep" if rtype_val in ("custom", "mood") and details.get("sleepKind") else rtype_val
        )

        id_created_ms = _extract_routine_id_created_ms(cid)
        db_created_dt = _as_utc_dt(getattr(r, "created_at", None))
        created_at_ms = id_created_ms or (int(db_created_dt.timestamp() * 1000) if db_created_dt else None)
        edited_at_ms = _safe_epoch_ms(details.get("editedAtMs"), 0) or None

        row_start_utc = _as_utc_dt(r.start_time) or datetime.now(timezone.utc)
        row_start_ms = int(row_start_utc.timestamp() * 1000)
        ts_ms = _safe_epoch_ms(details.get("timestamp"), row_start_ms)

        # Self-heal poisoned sleep rows from authoritative SleepLog table when not user-edited
        if resolved_type == "sleep" and not edited_at_ms and cid in sleep_by_cid:
            sl = sleep_by_cid[cid]
            sl_end_utc = _as_utc_dt(sl.end_time)
            sl_start_utc = _as_utc_dt(sl.start_time)
            if sl_end_utc is not None:
                sl_end_ms = int(sl_end_utc.timestamp() * 1000)
                fallback_span = (
                    max(1, round((sl_end_ms - int(sl_start_utc.timestamp() * 1000)) / 60000))
                    if sl_start_utc is not None
                    else 45
                )
                sl_dur = (
                    _safe_pos_int(sl.duration_minutes, 0)
                    or _safe_pos_int(details.get("durationMins"), 0)
                    or fallback_span
                )
                sl_start_ms = (
                    int(sl_start_utc.timestamp() * 1000)
                    if sl_start_utc is not None
                    else (sl_end_ms - sl_dur * 60000)
                )
                stored_end_ms = _safe_epoch_ms(details.get("endTs"), ts_ms)
                if abs(stored_end_ms - sl_end_ms) > 5 * 60 * 1000:
                    ts_ms = sl_end_ms
                    details["timestamp"] = sl_end_ms
                    details["endTs"] = sl_end_ms
                    details["startTs"] = sl_start_ms
                    details["durationMins"] = sl_dur
                    r.start_time = sl_end_utc
                    r.details_json = dict(details)
                    dirty_healed = True

        actor_name_val = r.actor_name or details.get("actorName") or ""
        actor_role_val = r.actor_role or details.get("actorRole") or ""
        try:
            logged_iso = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat()
        except Exception:
            logged_iso = row_start_utc.isoformat()

        item: Dict[str, Any] = {
            "id": cid,
            "client_id": cid,
            "type": resolved_type,
            "category": resolved_type,
            "icon": details.get("icon") or ("🍼" if resolved_type == "feeding" else ("🚼" if resolved_type == "diaper" else "🌙")),
            "title": details.get("title") or "",
            "detail": details.get("detail") or (r.notes or ""),
            "time": details.get("time") or row_start_utc.strftime("%H:%M"),
            "timestamp": ts_ms,
            "timestamp_ms": ts_ms,
            "logged_at": logged_iso,
            "actorName": actor_name_val,
            "actor_name": actor_name_val,
            "actorRole": actor_role_val,
            "actor_role": actor_role_val,
            "deleted": bool(r.is_deleted),
        }
        if created_at_ms is not None:
            item["createdAtMs"] = created_at_ms
        for opt_key in (
            "start",
            "end",
            "startTs",
            "endTs",
            "durationMins",
            "durationMin",
            "method",
            "side",
            "leftMin",
            "rightMin",
            "note",
            "quality",
            "sleepKind",
            "amountMl",
            "diaperStatus",
            "editedAtMs",
            "repairedAtMs",
        ):
            if opt_key in details:
                item[opt_key] = details[opt_key]
        if "startTs" in item and item["startTs"] is not None:
            item["start_ts"] = item["startTs"]
        if "endTs" in item and item["endTs"] is not None:
            item["end_ts"] = item["endTs"]
        if resolved_type == "sleep" and "durationMins" in item and item["durationMins"] is not None:
            item["duration_minutes"] = item["durationMins"]
        elif resolved_type == "feeding" and "durationMin" in item and item["durationMin"] is not None:
            item["duration_minutes"] = item["durationMin"]
        out.append(item)

    if dirty_healed:
        try:
            db.flush()
        except Exception:
            db.rollback()
        out.sort(key=lambda x: _safe_epoch_ms(x.get("endTs") or x.get("timestamp"), 0), reverse=True)
    return out


def _upsert_family_routines(
    db: Session,
    baby_id: int,
    routines_payload: Optional[List[Dict[str, Any]]],
    default_actor_name: str = "Ebeveyn",
    default_actor_role: str = "mother",
) -> None:
    if not routines_payload:
        return
    for raw_item in routines_payload[:100]:
        if not isinstance(raw_item, dict):
            continue
        cid = sanitize_device_uid(str(raw_item.get("id") or raw_item.get("client_id") or ""))[:120]
        if not cid:
            continue
        existing = (
            db.query(RoutineLog)
            .filter(RoutineLog.baby_id == baby_id, RoutineLog.client_id == cid)
            .first()
        )
        is_del = bool(raw_item.get("deleted") is True)
        if is_del:
            if existing:
                existing.is_deleted = True
                existing.updated_at = datetime.now(timezone.utc)
            continue

        raw_type = str(raw_item.get("type") or raw_item.get("category") or "custom").lower().strip()
        if raw_type == "feeding":
            rtype_enum = RoutineType.FEEDING
        elif raw_type == "diaper":
            rtype_enum = RoutineType.DIAPER
        elif raw_type == "sleep":
            rtype_enum = RoutineType.SLEEP
        elif raw_type == "bath":
            rtype_enum = RoutineType.BATH
        elif raw_type == "tummy_time":
            rtype_enum = RoutineType.TUMMY_TIME
        else:
            # Store custom/medication routines safely using existing PG enum MOOD while preserving exact client `type` in details_json
            rtype_enum = RoutineType.MOOD

        ts_ms = (
            raw_item.get("timestamp")
            or raw_item.get("timestamp_ms")
            or raw_item.get("startTs")
            or raw_item.get("start_ts")
        )
        try:
            start_dt = (
                datetime.fromtimestamp(float(ts_ms) / 1000.0, tz=timezone.utc)
                if ts_ms
                else datetime.now(timezone.utc)
            )
        except Exception:
            start_dt = datetime.now(timezone.utc)

        actor_nm = sanitize_plain_text(
            raw_item.get("actorName") or raw_item.get("actor_name"),
            max_len=60,
            default=default_actor_name,
        )
        actor_rl = str(raw_item.get("actorRole") or raw_item.get("actor_role") or default_actor_role).lower()[:32]
        safe_icon_raw = re.sub(r"<[^>]*>", "", str(raw_item.get("icon") or ""))
        safe_details: Dict[str, Any] = {
            "id": cid,
            "type": sanitize_plain_text(raw_type, max_len=24, default="custom"),
            "icon": sanitize_plain_text(
                safe_icon_raw,
                max_len=12,
                default=("🍼" if raw_type == "feeding" else ("🚼" if raw_type == "diaper" else "🌙")),
            ),
            "title": sanitize_plain_text(raw_item.get("title"), max_len=120, default="Rutin"),
            "detail": sanitize_plain_text(raw_item.get("detail"), max_len=240, default=""),
            "time": sanitize_plain_text(raw_item.get("time"), max_len=16, default=start_dt.strftime("%H:%M")),
            "timestamp": int(start_dt.timestamp() * 1000),
            "actorName": actor_nm,
            "actorRole": actor_rl,
        }

        normalized_opts: Dict[str, Any] = {
            "start": raw_item.get("start"),
            "end": raw_item.get("end"),
            "startTs": raw_item.get("startTs") if raw_item.get("startTs") is not None else raw_item.get("start_ts"),
            "endTs": raw_item.get("endTs") if raw_item.get("endTs") is not None else raw_item.get("end_ts"),
            "durationMins": (
                raw_item.get("durationMins")
                if raw_item.get("durationMins") is not None
                else (raw_item.get("duration_minutes") if raw_type == "sleep" else None)
            ),
            "durationMin": (
                raw_item.get("durationMin")
                if raw_item.get("durationMin") is not None
                else (raw_item.get("duration_minutes") if raw_type == "feeding" else None)
            ),
            "method": raw_item.get("method") or (raw_item.get("sub_type") if raw_type == "feeding" else None),
            "side": raw_item.get("side"),
            "leftMin": raw_item.get("leftMin"),
            "rightMin": raw_item.get("rightMin"),
            "note": raw_item.get("note") if raw_item.get("note") is not None else raw_item.get("notes"),
            "quality": raw_item.get("quality"),
            "sleepKind": raw_item.get("sleepKind") or (raw_item.get("sub_type") if raw_type == "sleep" else None),
            "amountMl": raw_item.get("amountMl") if raw_item.get("amountMl") is not None else raw_item.get("amount_ml"),
            "diaperStatus": raw_item.get("diaperStatus") or (raw_item.get("sub_type") if raw_type == "diaper" else None),
            "editedAtMs": raw_item.get("editedAtMs") if raw_item.get("editedAtMs") is not None else raw_item.get("edited_at_ms"),
            "repairedAtMs": raw_item.get("repairedAtMs") if raw_item.get("repairedAtMs") is not None else raw_item.get("repaired_at_ms"),
        }

        for opt_k, val in normalized_opts.items():
            if val is None or val == "":
                continue
            if opt_k == "side":
                side_norm = str(val).strip().lower()
                if side_norm in ("left", "right", "both"):
                    safe_details["side"] = side_norm
                continue
            if opt_k in ("durationMins", "durationMin", "leftMin", "rightMin", "amountMl"):
                if isinstance(val, bool):
                    continue
                try:
                    num_val = int(round(float(val)))
                    if 0 <= num_val <= 2880:
                        safe_details[opt_k] = num_val
                except Exception:
                    pass
                continue
            if opt_k in ("startTs", "endTs", "editedAtMs", "repairedAtMs"):
                if isinstance(val, bool):
                    continue
                try:
                    ts_int = int(float(val))
                    if 0 < ts_int <= 9999999999999:
                        safe_details[opt_k] = ts_int
                except Exception:
                    pass
                continue
            if opt_k == "note":
                no_tags = re.sub(r"<[^>]*>", "", str(val))
                clean_note = sanitize_plain_text(no_tags, max_len=160)
                if clean_note:
                    safe_details["note"] = clean_note
                continue
            if isinstance(val, (int, float, bool)):
                safe_details[opt_k] = val
            else:
                safe_details[opt_k] = sanitize_plain_text(str(val), max_len=40)

        if existing:
            prev_det = dict(existing.details_json or {})
            prev_start_utc = _as_utc_dt(existing.start_time)
            prev_fallback_ms = int(prev_start_utc.timestamp() * 1000) if prev_start_utc else 0
            prev_ts_ms = _safe_epoch_ms(prev_det.get("timestamp"), prev_fallback_ms)
            inc_ts_ms = _safe_epoch_ms(safe_details.get("endTs") or safe_details.get("timestamp"), 0)
            same_clock_labels = (
                (safe_details.get("time") or "") == (prev_det.get("time") or "")
                and (safe_details.get("start") or "") == (prev_det.get("start") or "")
                and (safe_details.get("end") or "") == (prev_det.get("end") or "")
            )
            # Block stale client Date.now() poisoning when user neither edited nor repaired the routine
            if (
                prev_ts_ms > 0
                and inc_ts_ms > prev_ts_ms + 10 * 60 * 1000
                and same_clock_labels
                and not safe_details.get("editedAtMs")
                and not safe_details.get("repairedAtMs")
            ):
                safe_details["timestamp"] = prev_ts_ms
                if "startTs" in prev_det:
                    safe_details["startTs"] = prev_det["startTs"]
                if "endTs" in prev_det:
                    safe_details["endTs"] = prev_det["endTs"]
                if prev_start_utc is not None:
                    start_dt = prev_start_utc

            existing.routine_type = rtype_enum
            existing.start_time = start_dt
            existing.details_json = safe_details
            existing.notes = safe_details["detail"]
            existing.actor_name = actor_nm
            existing.actor_role = actor_rl
            existing.is_deleted = False
            existing.updated_at = datetime.now(timezone.utc)
        else:
            db.add(
                RoutineLog(
                    baby_id=baby_id,
                    client_id=cid,
                    actor_name=actor_nm,
                    actor_role=actor_rl,
                    is_deleted=False,
                    routine_type=rtype_enum,
                    start_time=start_dt,
                    details_json=safe_details,
                    notes=safe_details["detail"],
                )
            )


def _serialize_unread_whispers(
    db: Session,
    family_id: int,
    viewer_device_uid: Optional[str],
) -> List[Dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=12)
    rows = (
        db.query(FamilyWhisper)
        .filter(FamilyWhisper.family_id == family_id, FamilyWhisper.created_at >= cutoff)
        .order_by(FamilyWhisper.id.desc())
        .limit(10)
        .all()
    )
    clean_viewer = sanitize_device_uid(viewer_device_uid)
    unread: List[Dict[str, Any]] = []
    for w in rows:
        acked = list(w.acked_by_json or [])
        if clean_viewer and w.sender_device_uid and w.sender_device_uid == clean_viewer:
            continue
        if clean_viewer and clean_viewer in acked:
            continue
        unread.append(
            {
                "id": w.id,
                "sender_name": w.sender_name,
                "sender_role": w.sender_role,
                "template_key": w.template_key,
                "message_text": w.message_text,
                "message": w.message_text,
                "created_at": w.created_at.isoformat() if w.created_at else datetime.now(timezone.utc).isoformat(),
            }
        )
    return list(reversed(unread))


def build_family_snapshot(
    db: Session,
    family: FamilyGroup,
    viewer_device_uid: Optional[str] = None,
) -> Dict[str, Any]:
    baby = family.babies[0] if family.babies else None
    active_members = [m for m in family.members if m.is_active is not False]
    active_members.sort(key=lambda x: x.id or 0)

    members_out = [
        {
            "id": m.id,
            "role": m.role,
            "name": m.nickname or "Ebeveyn",
            "is_self": bool(viewer_device_uid and m.device_uid and m.device_uid == sanitize_device_uid(viewer_device_uid)),
            "joined_at": m.joined_at.isoformat() if m.joined_at else datetime.now(timezone.utc).isoformat(),
        }
        for m in active_members
    ]

    bdate_str = "2026-04-11"
    if baby and baby.birth_date:
        bdate_str = baby.birth_date.strftime("%Y-%m-%d")

    routines_out = _serialize_routines_for_family(db, baby.id) if baby else []
    whispers_out = _serialize_unread_whispers(db, family.id, viewer_device_uid)

    return {
        "id": family.id,
        "name": family.name,
        "invite_code": family.invite_code,
        "max_members": family.max_members or MAX_FAMILY_MEMBERS_DEFAULT,
        "member_count": len(members_out),
        "subscription_active": bool(family.vip_active),
        "subscription_plan": family.vip_plan if family.vip_active else "free",
        "members": members_out,
        "baby": {
            "id": baby.id if baby else None,
            "name": baby.name if baby else "Bebeğim",
            "birth_date": bdate_str,
            "gender": (baby.gender or "unspecified") if baby else "unspecified",
            "premature_weeks": (baby.premature_weeks or 0) if baby else 0,
            "development_score": (baby.development_score or 84) if baby else 84,
            "manual_leap": baby.manual_active_leap if baby else None,
            "is_early_leap_active": bool(baby.is_early_leap_active) if baby else False,
        },
        "routines": routines_out,
        "checked_vaccines": list(family.checked_vaccines_json or []),
        "checked_leaps": list(family.checked_leaps_json or []),
        "active_sleep_start_iso": family.active_sleep_start_iso,
        "active_sleep_actor": family.active_sleep_actor,
        "whispers": whispers_out,
        "pending_whispers": whispers_out,
        "created_at": family.created_at.isoformat() if family.created_at else datetime.now(timezone.utc).isoformat(),
    }


def _notify_relay_best_effort(room_key: str, event_type: str, payload: Dict[str, Any]) -> None:
    relay_base = (os.getenv("FUNCTION_BUN_URL") or "").strip().rstrip("/")
    if not relay_base or os.environ.get("PYTEST_CURRENT_TEST"):
        return
    try:
        body_bytes = json.dumps(
            {"room_key": room_key, "event_type": event_type, "payload": payload}
        ).encode("utf-8")
        secret_hdr = get_relay_hmac_secret()
    except Exception:
        return

    if not _RELAY_INFLIGHT_SEM.acquire(blocking=False):
        return

    def _send_relay(raw_body: bytes, relay_url: str, relay_secret: str) -> None:
        try:
            req = urllib.request.Request(
                f"{relay_url}/api/realtime/broadcast",
                data=raw_body,
                headers={
                    "Content-Type": "application/json",
                    "X-Mishil-Relay-Secret": relay_secret,
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=1.5):
                pass
        except Exception:
            pass
        finally:
            _RELAY_INFLIGHT_SEM.release()

    try:
        _RELAY_NOTIFY_POOL.submit(_send_relay, body_bytes, relay_base, secret_hdr)
    except Exception:
        _RELAY_INFLIGHT_SEM.release()


# ============================================================
# Request Models
# ============================================================


class FamilyCreateRequest(BaseModel):
    invite_code: Optional[str] = Field(None, max_length=20)
    device_uid: Optional[str] = Field(None, max_length=128)
    member_token: Optional[str] = Field(None, max_length=256)
    family_name: Optional[str] = Field(None, max_length=100)
    creator_role: str = Field(default="mother", max_length=32)
    creator_name: str = Field(default="Anne", max_length=80)
    baby_name: str = Field(default="Bebeğim", max_length=80)
    birth_date: str = Field(default="2026-04-11", max_length=16)
    gender: Optional[str] = Field(default=None, max_length=20)
    premature_weeks: Optional[int] = Field(default=0, ge=0, le=20)
    subscription_active: bool = Field(default=False)
    subscription_plan: str = Field(default="free", max_length=32)
    subscriber_id: Optional[str] = Field(default=None, max_length=128)
    original_transaction_id: Optional[str] = Field(default=None, max_length=128)
    purchase_token: Optional[str] = Field(default=None, max_length=512)
    routines: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    checked_vaccines: Optional[Union[List[str], Dict[str, Any]]] = Field(default=None)
    checked_leaps: Optional[Union[List[str], Dict[str, Any]]] = Field(default=None)
    manual_leap: Optional[int] = Field(default=None)
    active_sleep_start_iso: Optional[str] = Field(default=None, max_length=64)


class FamilyJoinRequest(BaseModel):
    invite_code: str = Field(..., min_length=4, max_length=20)
    role: str = Field(default="father", max_length=32)
    name: str = Field(default="Baba", max_length=80)
    device_uid: Optional[str] = Field(default=None, max_length=128)
    member_token: Optional[str] = Field(default=None, max_length=256)
    lang: Optional[str] = Field(default="tr", max_length=12)


class FamilySyncUpdateRequest(BaseModel):
    invite_code: str = Field(..., min_length=4, max_length=20)
    device_uid: Optional[str] = Field(default=None, max_length=128)
    member_token: Optional[str] = Field(default=None, max_length=256)
    actor_name: Optional[str] = Field(default=None, max_length=80)
    actor_role: Optional[str] = Field(default=None, max_length=32)
    baby_name: Optional[str] = Field(default=None, max_length=80)
    birth_date: Optional[str] = Field(default=None, max_length=16)
    premature_weeks: Optional[int] = Field(default=None, ge=0, le=20)
    routines: Optional[List[Dict[str, Any]]] = Field(default=None)
    deleted_routine_ids: Optional[List[str]] = Field(default=None)
    checked_vaccines: Optional[Union[List[str], Dict[str, Any]]] = Field(default=None)
    checked_leaps: Optional[Union[List[str], Dict[str, Any]]] = Field(default=None)
    manual_leap: Optional[int] = Field(default=None)
    active_sleep_start_iso: Optional[str] = Field(default="__UNCHANGED__", max_length=64)
    active_sleep_actor: Optional[str] = Field(default=None, max_length=80)
    subscriber_id: Optional[str] = Field(default=None, max_length=128)
    original_transaction_id: Optional[str] = Field(default=None, max_length=128)
    purchase_token: Optional[str] = Field(default=None, max_length=512)


class LeapOverrideRequest(BaseModel):
    invite_code: str = Field(..., min_length=4, max_length=20)
    leap_number: Optional[int] = Field(None, ge=1, le=10)
    is_active: bool = Field(True)
    member_token: Optional[str] = Field(default=None, max_length=256)
    device_uid: Optional[str] = Field(default=None, max_length=128)


class FamilyWhisperRequest(BaseModel):
    invite_code: str = Field(..., min_length=4, max_length=20)
    member_token: Optional[str] = Field(default=None, max_length=256)
    device_uid: Optional[str] = Field(default=None, max_length=128)
    template_key: Optional[
        Literal[
            "tea_water",
            "next_shift_yours",
            "trapped_under_baby",
            "thank_you_love",
            "nursing_water",
            "nursing_burp_help",
            "handoff_fed_burped",
            "custom",
        ]
    ] = Field(default="next_shift_yours")
    custom_note: Optional[str] = Field(default=None, max_length=140)
    message: Optional[str] = Field(default=None, max_length=140)
    lang: Optional[str] = Field(default="tr", max_length=12)


class FamilyWhisperAckRequest(BaseModel):
    invite_code: str = Field(..., min_length=4, max_length=20)
    whisper_id: int = Field(..., ge=1)
    member_token: Optional[str] = Field(default=None, max_length=256)
    device_uid: Optional[str] = Field(default=None, max_length=128)


class NightWatchPulseRequest(BaseModel):
    device_uid: str = Field(..., min_length=4, max_length=128)
    is_sleeping_watch: bool = Field(default=True)
    send_heart: bool = Field(default=False)
    send_cheer: Optional[bool] = Field(default=None)


def _parse_birth_date(raw_bdate: Optional[str]) -> datetime:
    try:
        dt = datetime.strptime((raw_bdate or "2026-04-11").strip()[:10], "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime(2026, 4, 11, tzinfo=timezone.utc)


def _sanitize_key_list(items: Optional[Union[List[str], Dict[str, Any]]]) -> List[str]:
    if items is None:
        return []
    raw_seq: List[Any]
    if isinstance(items, dict):
        raw_seq = [k for k, v in items.items() if v]
    elif isinstance(items, list):
        raw_seq = items
    else:
        return []
    seen = set()
    out: List[str] = []
    for raw in raw_seq[:150]:
        cleaned = sanitize_plain_text(str(raw), max_len=64)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            out.append(cleaned)
    return out


def _check_join_rate_limit(request: Optional[Request], failed: bool = False) -> None:
    if request is None:
        return
    forwarded = request.headers.get("x-forwarded-for") or ""
    ip = (forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")) or "unknown"
    now = time.monotonic()
    with _JOIN_FAIL_LOCK:
        if len(_JOIN_FAIL_BUCKETS) >= 2048 and ip not in _JOIN_FAIL_BUCKETS:
            stale_ips = [k for k, dq in list(_JOIN_FAIL_BUCKETS.items()) if not dq or (now - dq[-1]) > _JOIN_WINDOW_SEC]
            for s_ip in stale_ips:
                _JOIN_FAIL_BUCKETS.pop(s_ip, None)
            while len(_JOIN_FAIL_BUCKETS) >= 2048:
                oldest_ip = next(iter(_JOIN_FAIL_BUCKETS))
                _JOIN_FAIL_BUCKETS.pop(oldest_ip, None)
        bucket = _JOIN_FAIL_BUCKETS.setdefault(ip, deque())
        while bucket and (now - bucket[0]) > _JOIN_WINDOW_SEC:
            bucket.popleft()
        if len(bucket) >= _JOIN_MAX_FAILURES:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Çok fazla hatalı aile kodu denemesi yapıldı. Lütfen birkaç dakika sonra tekrar deneyin.",
            )
        if failed:
            bucket.append(now)


# ============================================================
# Endpoints
# ============================================================


@router.post("/create", summary="Yeni Aile & Eş/Bakıcı Paylaşım Grubu Oluştur veya Güncelle (Maks. 3 Üye)")
def create_family(
    payload: FamilyCreateRequest,
    db: Session = Depends(get_db),
    x_family_member_token: Optional[str] = Header(None, alias="X-Family-Member-Token"),
):
    role = payload.creator_role.strip().lower() if payload.creator_role else "mother"
    if role not in ALLOWED_MEMBER_ROLES:
        role = "mother"
    creator_name = sanitize_plain_text(payload.creator_name, max_len=60, default="Anne")
    baby_name = sanitize_plain_text(payload.baby_name, max_len=60, default="Bebeğim")
    fam_name = sanitize_plain_text(payload.family_name, max_len=90, default=f"{baby_name}'in Ailesi")
    bdate_dt = _parse_birth_date(payload.birth_date)
    raw_token_in = (x_family_member_token or payload.member_token or "").strip() or None

    req_code = sanitize_code(payload.invite_code)
    if req_code == "MSL782":
        req_code = ""

    existing_family: Optional[FamilyGroup] = None
    if req_code and len(req_code) >= 4:
        existing_family = db.query(FamilyGroup).filter(FamilyGroup.invite_code == req_code).first()

    issued_member_token: Optional[str] = None

    if existing_family:
        caller_member = authenticate_family_member(db, existing_family, raw_token_in, payload.device_uid)
        if not caller_member:
            # Anti-hijack: never allow an unauthenticated caller to overwrite another family's invite_code!
            active_members = [m for m in existing_family.members if m.is_active is not False]
            has_any_token = any(bool(m.member_token_hash) for m in active_members)
            clean_dev = sanitize_device_uid(payload.device_uid)
            matching_legacy_member = next(
                (m for m in active_members if not m.member_token_hash and clean_dev and m.device_uid == clean_dev),
                None,
            )
            if has_any_token or not matching_legacy_member:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Bu aile kodunu güncelleme yetkiniz bulunmuyor.",
                )
            issued_member_token = "mft_" + secrets.token_urlsafe(24)
            matching_legacy_member.member_token_hash = hash_member_token(issued_member_token)
            caller_member = matching_legacy_member

        family = existing_family
        family.name = fam_name
        _ensure_family_room_key(family)
        caller_member.role = role
        caller_member.nickname = creator_name
        caller_member.last_seen_at = datetime.now(timezone.utc)
        clean_uid = caller_member.device_uid or sanitize_device_uid(payload.device_uid)
    else:
        user, clean_uid = ensure_device_user(db, payload.device_uid, display_name=creator_name)
        if req_code and len(req_code) >= 4:
            code = req_code
        else:
            code = generate_family_code()
            while db.query(FamilyGroup).filter(FamilyGroup.invite_code == code).first() is not None:
                code = generate_family_code()

        family = FamilyGroup(
            name=fam_name,
            invite_code=code,
            room_key=generate_room_key(),
            max_members=MAX_FAMILY_MEMBERS_DEFAULT,
            vip_active=False,
            vip_plan="free",
            created_by_user_id=user.id,
        )
        db.add(family)
        db.flush()

        issued_member_token = "mft_" + secrets.token_urlsafe(24)
        caller_member = FamilyMember(
            family_id=family.id,
            user_id=user.id,
            role=role,
            nickname=creator_name,
            device_uid=clean_uid,
            member_token_hash=hash_member_token(issued_member_token),
            is_active=True,
            can_edit=True,
        )
        db.add(caller_member)
        db.flush()

    # Upsert single shared baby profile for this family
    baby = family.babies[0] if family.babies else None
    if not baby:
        baby = Baby(
            user_id=family.created_by_user_id,
            family_id=family.id,
            device_uid=clean_uid,
            name=baby_name,
            birth_date=bdate_dt,
            gender=sanitize_plain_text(payload.gender, max_len=20) if payload.gender else None,
            premature_weeks=payload.premature_weeks or 0,
            development_score=84,
        )
        db.add(baby)
        db.flush()
    else:
        baby.name = baby_name
        baby.birth_date = bdate_dt
        if payload.gender:
            baby.gender = sanitize_plain_text(payload.gender, max_len=20)
        if payload.premature_weeks is not None:
            baby.premature_weeks = payload.premature_weeks

    # Strict Server-Side VIP Verification (never trust bare client boolean!)
    if payload.subscription_active or payload.subscriber_id or payload.purchase_token or payload.original_transaction_id:
        verified_ok, verified_plan, verified_sid = verify_server_vip_entitlement(
            db,
            subscriber_id=payload.subscriber_id,
            original_transaction_id=payload.original_transaction_id,
            purchase_token=payload.purchase_token,
            device_uid=clean_uid,
            owner_user_id=family.created_by_user_id,
        )
        if verified_ok:
            family.vip_active = True
            family.vip_plan = verified_plan
            family.vip_subscriber_id = verified_sid
        elif not family.vip_subscriber_id:
            family.vip_active = False
            family.vip_plan = "free"
    else:
        refresh_family_vip_from_ledger(db, family)

    if payload.checked_vaccines is not None:
        family.checked_vaccines_json = _sanitize_key_list(payload.checked_vaccines)
    if payload.checked_leaps is not None:
        family.checked_leaps_json = _sanitize_key_list(payload.checked_leaps)
    if payload.active_sleep_start_iso is not None:
        family.active_sleep_start_iso = sanitize_plain_text(payload.active_sleep_start_iso, max_len=64) or None
        family.active_sleep_actor = creator_name if family.active_sleep_start_iso else None

    if payload.routines:
        _upsert_family_routines(db, baby.id, payload.routines, creator_name, role)

    db.commit()
    db.refresh(family)

    effective_token = issued_member_token or raw_token_in
    rt_token = make_realtime_token(_ensure_family_room_key(family), role=role, name=creator_name)
    snap = build_family_snapshot(db, family, viewer_device_uid=clean_uid)

    return {
        "success": True,
        "message": f"Aile grubu başarıyla kaydedildi. Davet Kodu: {family.invite_code}",
        "invite_code": family.invite_code,
        "member_token": effective_token,
        "realtime_token": rt_token,
        "family": snap,
    }


@router.post("/join", summary="Aile Davet Kodu ile Ortak Bebek Takibine Katıl (Maks. 3 Üye)")
def join_family(
    payload: FamilyJoinRequest,
    request: Request,
    db: Session = Depends(get_db),
    x_family_member_token: Optional[str] = Header(None, alias="X-Family-Member-Token"),
):
    lang_norm = normalize_lang(payload.lang)
    _check_join_rate_limit(request, failed=False)

    code = sanitize_code(payload.invite_code)
    family = db.query(FamilyGroup).filter(FamilyGroup.invite_code == code).first()
    if not family:
        _check_join_rate_limit(request, failed=True)
        not_found_msg = (
            f"Familiengruppe mit Code '{code}' wurde nicht gefunden."
            if lang_norm == "de"
            else (
                f"Family group with code '{code}' was not found."
                if lang_norm == "en"
                else f"'{code}' kodlu aile grubu bulunamadı. Lütfen eşinizin ekranındaki kodu kontrol ediniz."
            )
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found_msg)

    refresh_family_vip_from_ledger(db, family)
    _ensure_family_room_key(family)

    role = (payload.role or "father").strip().lower()
    if role not in ALLOWED_MEMBER_ROLES:
        role = "father"
    member_name = sanitize_plain_text(payload.name, max_len=60, default="Ebeveyn")
    raw_token_in = (x_family_member_token or payload.member_token or "").strip() or None
    clean_dev = sanitize_device_uid(payload.device_uid)

    active_members = [m for m in family.members if m.is_active is not False]

    # 1) Check if caller is already an authenticated member of this family (idempotent re-join)
    existing_member = authenticate_family_member(db, family, raw_token_in, clean_dev)
    if not existing_member and clean_dev:
        # Match same device_uid ONLY if same device previously joined and presents token or had no token yet
        dev_match = next((m for m in active_members if m.device_uid == clean_dev), None)
        if dev_match and not dev_match.member_token_hash:
            existing_member = dev_match

    issued_token: Optional[str] = None
    max_cap = family.max_members or MAX_FAMILY_MEMBERS_DEFAULT

    if existing_member:
        existing_member.role = role
        existing_member.nickname = member_name
        existing_member.last_seen_at = datetime.now(timezone.utc)
        if not existing_member.member_token_hash:
            issued_token = "mft_" + secrets.token_urlsafe(24)
            existing_member.member_token_hash = hash_member_token(issued_token)
        effective_uid = existing_member.device_uid or clean_dev
    else:
        # 2) Enforce max_members = 3 strictly!
        if len(active_members) >= max_cap:
            full_msg = (
                f"Diese Familiengruppe hat das Limit von {max_cap} Mitgliedern erreicht (z. B. Mama, Papa, Betreuung)."
                if lang_norm == "de"
                else (
                    f"This family group has reached its maximum of {max_cap} members (e.g., Mom, Dad, Caregiver)."
                    if lang_norm == "en"
                    else f"Bu aile grubu maksimum {max_cap} üye sınırına (Anne, Baba, Bakıcı) ulaştı."
                )
            )
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "success": False,
                    "error_code": "FAMILY_FULL",
                    "detail": full_msg,
                    "message": full_msg,
                    "max_members": max_cap,
                },
            )

        user, effective_uid = ensure_device_user(db, clean_dev, display_name=member_name)
        issued_token = "mft_" + secrets.token_urlsafe(24)
        new_member = FamilyMember(
            family_id=family.id,
            user_id=user.id,
            role=role,
            nickname=member_name,
            device_uid=effective_uid,
            member_token_hash=hash_member_token(issued_token),
            is_active=True,
            can_edit=True,
        )
        db.add(new_member)

    db.commit()
    db.refresh(family)

    rt_token = make_realtime_token(family.room_key, role=role, name=member_name)
    snap = build_family_snapshot(db, family, viewer_device_uid=effective_uid)
    _notify_relay_best_effort(
        family.room_key,
        "MEMBER_JOINED",
        {"name": member_name, "role": role, "member_count": snap["member_count"]},
    )

    return {
        "success": True,
        "message": f"{member_name} başarıyla {family.name} grubuna katıldı!",
        "invite_code": family.invite_code,
        "member_token": issued_token or raw_token_in,
        "realtime_token": rt_token,
        "family": snap,
    }


@router.get("/sync/{invite_code}", summary="Doğrulanmış Üye İçin Canlı Aile & Bebek Senkronizasyonu")
def sync_family_get(
    invite_code: str,
    device_uid: Optional[str] = Query(None, max_length=128),
    x_family_member_token: Optional[str] = Header(None, alias="X-Family-Member-Token"),
    db: Session = Depends(get_db),
):
    code = sanitize_code(invite_code)
    family = db.query(FamilyGroup).filter(FamilyGroup.invite_code == code).first()
    if not family:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aile grubu bulunamadı.")

    member = authenticate_family_member(db, family, x_family_member_token, device_uid)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Aile verilerine erişim için geçerli üye anahtarı gereklidir.",
        )

    refresh_family_vip_from_ledger(db, family)
    room_key = _ensure_family_room_key(family)
    db.commit()
    db.refresh(family)

    rt_token = make_realtime_token(room_key, role=member.role, name=member.nickname or "Ebeveyn")
    return {
        "success": True,
        "realtime_token": rt_token,
        "family": build_family_snapshot(db, family, viewer_device_uid=member.device_uid or device_uid),
    }


@router.post("/sync", summary="Çift Yönlü İdempotent Rutin, Aşı, Atak ve Canlı Uyku Eşitlemesi")
def sync_family_bidirectional(
    payload: FamilySyncUpdateRequest,
    x_family_member_token: Optional[str] = Header(None, alias="X-Family-Member-Token"),
    db: Session = Depends(get_db),
):
    code = sanitize_code(payload.invite_code)
    family = db.query(FamilyGroup).filter(FamilyGroup.invite_code == code).first()
    if not family:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aile grubu bulunamadı.")

    raw_tok = (x_family_member_token or payload.member_token or "").strip() or None
    member = authenticate_family_member(db, family, raw_tok, payload.device_uid)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Aile senkronizasyonu için geçerli üye anahtarı gereklidir.",
        )

    actor_name = sanitize_plain_text(payload.actor_name or member.nickname, max_len=60, default="Ebeveyn")
    actor_role = (payload.actor_role or member.role or "mother").strip().lower()
    if actor_role not in ALLOWED_MEMBER_ROLES:
        actor_role = member.role or "mother"

    baby = family.babies[0] if family.babies else None
    if baby:
        if payload.baby_name:
            baby.name = sanitize_plain_text(payload.baby_name, max_len=60, default=baby.name)
        if payload.birth_date:
            baby.birth_date = _parse_birth_date(payload.birth_date)
        if payload.premature_weeks is not None:
            baby.premature_weeks = payload.premature_weeks
        if payload.routines is not None:
            _upsert_family_routines(db, baby.id, payload.routines, actor_name, actor_role)
        if payload.deleted_routine_ids:
            clean_del_ids = [
                sanitize_device_uid(str(did))[:120]
                for did in payload.deleted_routine_ids[:150]
                if did
            ]
            clean_del_ids = [d for d in clean_del_ids if d]
            if clean_del_ids:
                del_rows = (
                    db.query(RoutineLog)
                    .filter(RoutineLog.baby_id == baby.id, RoutineLog.client_id.in_(clean_del_ids))
                    .all()
                )
                now_del_utc = datetime.now(timezone.utc)
                for dr in del_rows:
                    dr.is_deleted = True
                    dr.updated_at = now_del_utc

    if payload.checked_vaccines is not None:
        merged_vax = set(family.checked_vaccines_json or []) | set(_sanitize_key_list(payload.checked_vaccines))
        family.checked_vaccines_json = sorted(merged_vax)[:150]

    if payload.checked_leaps is not None:
        merged_leaps = set(family.checked_leaps_json or []) | set(_sanitize_key_list(payload.checked_leaps))
        family.checked_leaps_json = sorted(merged_leaps)[:150]

    if payload.active_sleep_start_iso != "__UNCHANGED__":
        clean_sleep_iso = sanitize_plain_text(payload.active_sleep_start_iso, max_len=64) if payload.active_sleep_start_iso else ""
        family.active_sleep_start_iso = clean_sleep_iso or None
        family.active_sleep_actor = actor_name if clean_sleep_iso else None

    if payload.subscriber_id or payload.purchase_token or payload.original_transaction_id:
        is_ok, plan_res, sid_res = verify_server_vip_entitlement(
            db,
            subscriber_id=payload.subscriber_id,
            original_transaction_id=payload.original_transaction_id,
            purchase_token=payload.purchase_token,
            device_uid=member.device_uid or payload.device_uid,
            owner_user_id=family.created_by_user_id,
        )
        if is_ok:
            family.vip_active = True
            family.vip_plan = plan_res
            family.vip_subscriber_id = sid_res
    else:
        refresh_family_vip_from_ledger(db, family)

    room_key = _ensure_family_room_key(family)
    db.commit()
    db.refresh(family)

    if payload.routines or payload.checked_vaccines is not None or payload.active_sleep_start_iso != "__UNCHANGED__":
        _notify_relay_best_effort(
            room_key,
            "FAMILY_SYNC_UPDATED",
            {"by_name": actor_name, "by_role": actor_role},
        )

    rt_token = make_realtime_token(room_key, role=member.role, name=member.nickname or actor_name)
    return {
        "success": True,
        "realtime_token": rt_token,
        "family": build_family_snapshot(db, family, viewer_device_uid=member.device_uid or payload.device_uid),
    }


@router.post("/leap-override", summary="Manuel Erken Atak Başlat / Otomatik Takvime Dön")
def set_leap_override(
    payload: LeapOverrideRequest,
    x_family_member_token: Optional[str] = Header(None, alias="X-Family-Member-Token"),
    db: Session = Depends(get_db),
):
    code = sanitize_code(payload.invite_code)
    family = db.query(FamilyGroup).filter(FamilyGroup.invite_code == code).first()
    if not family:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aile grubu bulunamadı.")

    raw_tok = (x_family_member_token or payload.member_token or "").strip() or None
    member = authenticate_family_member(db, family, raw_tok, payload.device_uid)
    if not member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Yetkisiz işlem.")

    baby = family.babies[0] if family.babies else None
    if not baby:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bebek profili bulunamadı.")

    baby.manual_active_leap = payload.leap_number if payload.is_active else None
    baby.is_early_leap_active = bool(payload.is_active)
    room_key = _ensure_family_room_key(family)
    db.commit()

    _notify_relay_best_effort(
        room_key,
        "LEAP_OVERRIDE",
        {"leap": baby.manual_active_leap, "is_active": baby.is_early_leap_active},
    )

    status_msg = (
        f"{payload.leap_number}. Sıçrama Erken Atak olarak manuel başlatıldı!"
        if payload.is_active
        else "Otomatik Wonder Weeks takvimine geri dönüldü."
    )
    return {
        "success": True,
        "message": status_msg,
        "baby": {
            "name": baby.name,
            "birth_date": baby.birth_date.strftime("%Y-%m-%d"),
            "manual_leap": baby.manual_active_leap,
            "is_early_leap_active": baby.is_early_leap_active,
        },
    }


@router.post("/whisper", summary="Eşime Fısılda & Sessiz Nöbet Devri Gönder (Yalnızca Kapalı Aile İçi)")
def send_family_whisper(
    payload: FamilyWhisperRequest,
    x_family_member_token: Optional[str] = Header(None, alias="X-Family-Member-Token"),
    db: Session = Depends(get_db),
):
    code = sanitize_code(payload.invite_code)
    family = db.query(FamilyGroup).filter(FamilyGroup.invite_code == code).first()
    if not family:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aile grubu bulunamadı.")

    raw_tok = (x_family_member_token or payload.member_token or "").strip() or None
    member = authenticate_family_member(db, family, raw_tok, payload.device_uid)
    if not member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Fısıltı göndermek için aile üyeliği doğrulanmalıdır.")

    lang_norm = normalize_lang(payload.lang)
    tpl_map = WHISPER_TEMPLATES_DE if lang_norm == "de" else (WHISPER_TEMPLATES_EN if lang_norm == "en" else WHISPER_TEMPLATES_TR)
    tkey = payload.template_key or "tea_water"

    def _strip_html(raw_note: Optional[str], max_len: int) -> str:
        if not raw_note:
            return ""
        no_tags = re.sub(r"<[^>]*>", "", str(raw_note))
        return sanitize_plain_text(no_tags, max_len=max_len)

    raw_custom_input = payload.custom_note if payload.custom_note is not None else payload.message
    if tkey == "custom" and raw_custom_input:
        msg_text = _strip_html(raw_custom_input, 140)
    else:
        msg_text = tpl_map.get(tkey) or _strip_html(raw_custom_input, 140)
        if payload.custom_note and tkey != "custom":
            extra = _strip_html(payload.custom_note, 80)
            if extra:
                msg_text = f"{msg_text} ({extra})"[:190]

    if not msg_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mesaj boş olamaz.")

    # Prune stale whispers (>48h) for this family
    prune_cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    db.query(FamilyWhisper).filter(
        FamilyWhisper.family_id == family.id,
        FamilyWhisper.created_at < prune_cutoff,
    ).delete(synchronize_session=False)

    sender_uid = member.device_uid or sanitize_device_uid(payload.device_uid) or None
    sender_name = sanitize_plain_text(member.nickname, max_len=60, default="Ebeveyn")
    whisper = FamilyWhisper(
        family_id=family.id,
        sender_device_uid=sender_uid,
        sender_name=sender_name,
        sender_role=member.role or "mother",
        template_key=tkey,
        message_text=msg_text,
        acked_by_json=[sender_uid] if sender_uid else [],
    )
    db.add(whisper)
    room_key = _ensure_family_room_key(family)
    db.commit()
    db.refresh(whisper)

    whisper_out = {
        "id": whisper.id,
        "sender_name": whisper.sender_name,
        "sender_role": whisper.sender_role,
        "template_key": whisper.template_key,
        "message_text": whisper.message_text,
        "message": whisper.message_text,
        "created_at": whisper.created_at.isoformat(),
    }
    _notify_relay_best_effort(room_key, "PARTNER_WHISPER", whisper_out)

    return {"success": True, "whisper": whisper_out}


@router.post("/whisper/ack", summary="Alınan Eş Fısıltısını Okundu İşaretle")
def ack_family_whisper(
    payload: FamilyWhisperAckRequest,
    x_family_member_token: Optional[str] = Header(None, alias="X-Family-Member-Token"),
    db: Session = Depends(get_db),
):
    code = sanitize_code(payload.invite_code)
    family = db.query(FamilyGroup).filter(FamilyGroup.invite_code == code).first()
    if not family:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aile grubu bulunamadı.")

    raw_tok = (x_family_member_token or payload.member_token or "").strip() or None
    member = authenticate_family_member(db, family, raw_tok, payload.device_uid)
    if not member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Yetkisiz işlem.")

    whisper = (
        db.query(FamilyWhisper)
        .filter(FamilyWhisper.id == payload.whisper_id, FamilyWhisper.family_id == family.id)
        .first()
    )
    if whisper:
        viewer_uid = member.device_uid or sanitize_device_uid(payload.device_uid)
        if viewer_uid:
            acked = list(whisper.acked_by_json or [])
            if viewer_uid not in acked:
                acked.append(viewer_uid)
                whisper.acked_by_json = acked
                db.commit()

    return {"success": True}


@router.post("/night-watch/pulse", summary="Anonim Gece Nöbeti Dayanışma Feneri & Sessiz Kalp Selamı (Sıfır PII / Sıfır Metin)")
def night_watch_solidarity_pulse(
    payload: NightWatchPulseRequest,
    db: Session = Depends(get_db),
):
    clean_uid = sanitize_device_uid(payload.device_uid)
    if len(clean_uid) < 4:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz cihaz kimliği.")

    dev_hash = hashlib.sha256(f"nw:{clean_uid}".encode("utf-8")).hexdigest()[:48]
    now = datetime.now(timezone.utc)

    # Prune stale presence older than 2 hours
    stale_cutoff = now - timedelta(hours=2)
    db.query(NightWatchPresence).filter(NightWatchPresence.last_seen_at < stale_cutoff).delete(
        synchronize_session=False
    )

    row = db.query(NightWatchPresence).filter(NightWatchPresence.device_hash == dev_hash).first()
    wants_heart = bool(payload.send_heart or payload.send_cheer)
    heart_recorded = False
    if not row:
        row = NightWatchPresence(
            device_hash=dev_hash,
            is_sleeping_watch=bool(payload.is_sleeping_watch),
            hearts_sent=1 if wants_heart else 0,
            last_heart_sent_at=now if wants_heart else None,
            last_seen_at=now,
        )
        heart_recorded = wants_heart
        db.add(row)
    else:
        row.is_sleeping_watch = bool(payload.is_sleeping_watch)
        row.last_seen_at = now
        if wants_heart:
            last_h = row.last_heart_sent_at
            if last_h and last_h.tzinfo is None:
                last_h = last_h.replace(tzinfo=timezone.utc)
            if not last_h or (now - last_h).total_seconds() >= 10:
                row.hearts_sent = (row.hearts_sent or 0) + 1
                row.last_heart_sent_at = now
                heart_recorded = True

    db.commit()

    active_cutoff = now - timedelta(minutes=45)
    active_watchers = (
        db.query(NightWatchPresence)
        .filter(
            NightWatchPresence.last_seen_at >= active_cutoff,
            NightWatchPresence.is_sleeping_watch.is_(True),
        )
        .count()
    )
    hearts_recent = (
        db.query(NightWatchPresence)
        .filter(
            NightWatchPresence.last_heart_sent_at.isnot(None),
            NightWatchPresence.last_heart_sent_at >= active_cutoff,
            NightWatchPresence.device_hash != dev_hash,
        )
        .count()
    )

    return {
        "success": True,
        "active_watchers": max(1 if payload.is_sleeping_watch else 0, active_watchers),
        "peer_hearts_recent": hearts_recent,
        "heart_sent": heart_recorded,
    }


@router.delete("/membership", summary="Aileden Ayrıl / Sunucu Verilerini Sil (Apple Guideline 5.1.1v Uyumlu)")
def delete_family_membership(
    invite_code: str = Query(..., min_length=4, max_length=20),
    device_uid: Optional[str] = Query(None, max_length=128),
    x_family_member_token: Optional[str] = Header(None, alias="X-Family-Member-Token"),
    db: Session = Depends(get_db),
):
    code = sanitize_code(invite_code)
    family = db.query(FamilyGroup).filter(FamilyGroup.invite_code == code).first()
    if not family:
        return {"success": True, "status": "already_removed"}

    member = authenticate_family_member(db, family, x_family_member_token, device_uid)
    if not member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Üyelik silme yetkisi doğrulanamadı.")

    remaining_others = [
        m for m in family.members if m.id != member.id and (m.is_active is not False)
    ]
    if not remaining_others:
        # Last member leaving: purge entire FamilyGroup, Baby, RoutineLogs, SleepLogs, FamilyWhispers
        for b in list(family.babies):
            db.delete(b)
        db.delete(family)
        db.commit()
        return {"success": True, "status": "family_and_baby_purged"}

    # Transfer VIP / ownership cleanly if needed, otherwise remove only this member's record & whispers
    if member.device_uid:
        db.query(FamilyWhisper).filter(
            FamilyWhisper.family_id == family.id,
            FamilyWhisper.sender_device_uid == member.device_uid,
        ).delete(synchronize_session=False)
    if member.user_id == family.created_by_user_id:
        family.created_by_user_id = remaining_others[0].user_id
        family.vip_active = False
        family.vip_plan = "free"
        family.vip_subscriber_id = None

    db.delete(member)
    db.commit()
    return {"success": True, "status": "member_removed", "remaining_members": len(remaining_others)}
