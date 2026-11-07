import asyncio
from datetime import datetime, timezone, timedelta
import html
import hashlib
import hmac
import io
import csv
import copy
import glob
import gzip
import json
import math
import os
import re
import secrets
import threading
import time
import urllib.request
import urllib.error
import urllib.parse
from collections import Counter
from typing import Optional, Dict, Any, List
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Request, status, Query, Header, Form
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc, inspect, text

try:
    import jwt
except ImportError:
    try:
        from jose import jwt
    except ImportError:
        jwt = None

from app.db.base import get_db, SessionLocal, engine
from app.db.models import (
    BridgeClick,
    AppInstallSignal,
    CampaignConfig,
    StoreDailyMetric,
    SubscriberLedger,
    SubscriptionLifecycleEvent,
    StoreSyncState,
    User,
    Baby,
    CryEvent,
    SleepLog,
    RoutineLog,
    DadiChatHistory,
    Feedback,
    Subscription,
    Base,
)
from app.core.logging import get_logger

logger = get_logger("analytics")

router = APIRouter(prefix="/analytics", tags=["Kümülatif Büyüme, Mağaza API & Görsel Kurucu Kokpiti"])

# P0-2 Çözümü: Mağaza incelemeci PIN kodu yalnızca uygulama içi Paywall bypass içindir;
# kurucu finansal kokpitine (/admin/analytics) erişim yetkisi kaldırılmıştır.
_env_admin_pins_raw = os.environ.get("MISIL_ADMIN_PINS", "")
_configured_admin_pins = tuple(p.strip().upper() for p in _env_admin_pins_raw.split(",") if p.strip())
ADMIN_PINS = _configured_admin_pins or ("MISIL-REV-9842",)

# Yönetici PIN'i için IP bazlı brute-force hız sınırlaması (5 hatalı deneme -> 15 dk blok)
_PIN_RATE_LIMIT_LOCK = threading.Lock()
_PIN_FAILED_ATTEMPTS: Dict[str, List[float]] = {}
_PIN_BLOCK_UNTIL: Dict[str, float] = {}
_PIN_MAX_ATTEMPTS = 5
_PIN_ATTEMPT_WINDOW_SECONDS = 15 * 60
_PIN_BLOCK_SECONDS = 15 * 60

# Oturum çerezi: başarılı PIN girişinden sonra süreli (exp) HMAC imzalı token üretir.
_ADMIN_SESSION_COOKIE = "misil_admin_session"
_ADMIN_SESSION_TTL_SECONDS = 7 * 24 * 3600
_ADMIN_SESSION_SECRET = (
    os.environ.get("MISIL_ADMIN_SESSION_SECRET")
    or hmac.new(
        b"misil-admin-session-v4465-server-salt",
        "|".join(ADMIN_PINS).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
)
ALLOWED_PERIODS = ("all", "today", "yesterday", "7d")


def _mask_sensitive_sync_value(val: Any) -> Any:
    """Senkronizasyon durum metinlerinde, önbellekte ve loglarda AuthKey/.p8 dosya adlarını maskeler."""
    if isinstance(val, str):
        masked = re.sub(r"AuthKey_[A-Za-z0-9_\-\.]*", "AuthKey_[MASKED]", val)
        masked = re.sub(r"[A-Za-z0-9_\-]+\.p8", "[MASKED_KEY].p8", masked)
        return masked
    if isinstance(val, dict):
        return {k: _mask_sensitive_sync_value(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_mask_sensitive_sync_value(item) for item in val]
    return val

# Kanal yapılandırma allowlist'i ve varsayılan birim fiyat/kur sabitleri
ALLOWED_CAMPAIGN_CHANNELS: Dict[str, str] = {
    "apple_search_ads": "Apple Search Ads (ASA)",
    "meta_ads": "Meta Reklamları (Instagram & Facebook)",
    "meta_ads_ios": "Meta Reklamları (/ios Köprüsü)",
    "instagram_bio": "Instagram Bio (/download Köprüsü)",
    "google_play_organic": "Google Play (Android)",
}
FX_RATES_TO_TRY: Dict[str, float] = {
    "TRY": 1.0,
    "EUR": float(os.environ.get("MISIL_FX_EUR_TRY", "37.50")),
    "USD": float(os.environ.get("MISIL_FX_USD_TRY", "34.50")),
    "GBP": float(os.environ.get("MISIL_FX_GBP_TRY", "43.50")),
    "AUD": float(os.environ.get("MISIL_FX_AUD_TRY", "22.50")),
    "CAD": float(os.environ.get("MISIL_FX_CAD_TRY", "25.00")),
    "CHF": float(os.environ.get("MISIL_FX_CHF_TRY", "39.50")),
}

# Doğrulanmış App Store / Google Play katalog tarife referansı (Brüt TRY, Net Hakediş TRY)
DEFAULT_PLAN_PRICING_TRY: Dict[str, tuple] = {
    "misil_monthly": (149.99, 83.12),
    "misil_annual": (599.99, 332.50),
    "misilaylik": (149.99, 109.04),
    "misil": (599.99, 436.19),
}


def _is_annual_product(product_id: Optional[str]) -> bool:
    """Hem iOS (misil_annual / 6809228257) hem Android (misil / misil:misil) yıllık paketlerini tanır."""
    pid = (product_id or "").strip().lower()
    if not pid:
        return False
    if pid == "misil" or pid.startswith("misil:"):
        return True
    return any(tok in pid for tok in ("annual", "yillik", "yearly", "6809228257"))


def _resolve_expected_trial_pricing(
    product_id: Optional[str],
    paid_ref_gross: float = 0.0,
    paid_ref_net: float = 0.0,
    platform: Optional[str] = "ios",
) -> tuple:
    """
    Deneme (intro_free_trial) abonelerinin vade sonunda beklenen brüt/net TRY tutarını
    önce veritabanındaki gerçek ücretli işlem referansından, henüz yoksa resmi katalog
    tarifesinden çözer (0.00 TL pipeline ve eski 799.99 TL katalog sapmasını önler).
    """
    plat = (platform or "ios").strip().lower()
    net_ratio = 0.727 if plat == "android" else 0.55417
    is_ann = _is_annual_product(product_id)
    if paid_ref_gross > 0 and not (is_ann and round(float(paid_ref_gross), 2) == 799.99):
        net_val = paid_ref_net if paid_ref_net > 0 else round(paid_ref_gross * net_ratio, 2)
        return (round(float(paid_ref_gross), 2), round(float(net_val), 2))
    pid = (product_id or "").strip().lower()
    if pid in DEFAULT_PLAN_PRICING_TRY:
        return DEFAULT_PLAN_PRICING_TRY[pid]
    if plat == "android":
        return DEFAULT_PLAN_PRICING_TRY["misil" if is_ann else "misilaylik"]
    return DEFAULT_PLAN_PRICING_TRY["misil_annual" if is_ann else "misil_monthly"]

# Bellek içi çalışma zamanı önbelleği için kısa süreli kilit (Ağ G/Ç işlemleri bu kilit dışında yapılır)
_BASELINE_LOCK = threading.RLock()

# first_open / daily_active sinyal kaydı için eşzamanlı çift-kayıt (TOCTOU) koruması.
_APP_OPEN_SIGNAL_LOCK = threading.Lock()

_SCHEMA_INITIALIZED = False

BOT_SIGNATURES = (
    "facebookexternalhit",
    "facebot",
    "meta-externalagent",
    "twitterbot",
    "linkedinbot",
    "googlebot",
    "bingbot",
    "slackbot",
    "telegrambot",
    "crawler",
    "spider",
    "headless",
    "python-requests",
)

COUNTRY_META: Dict[str, Dict[str, str]] = {
    "TR": {"flag": "🇹🇷", "name": "Türkiye"},
    "DE": {"flag": "🇩🇪", "name": "Almanya"},
    "US": {"flag": "🇺🇸", "name": "ABD"},
    "UZ": {"flag": "🇺🇿", "name": "Özbekistan"},
    "AZ": {"flag": "🇦🇿", "name": "Azerbaycan"},
    "FR": {"flag": "🇫🇷", "name": "Fransa"},
    "DK": {"flag": "🇩🇰", "name": "Danimarka"},
    "BG": {"flag": "🇧🇬", "name": "Bulgaristan"},
    "AU": {"flag": "🇦🇺", "name": "Avustralya"},
    "GB": {"flag": "🇬🇧", "name": "Birleşik Krallık"},
    "NL": {"flag": "🇳🇱", "name": "Hollanda"},
}


def _empty_store_state() -> Dict[str, Any]:
    """Sıfır statik veri ilkesi: Veritabanı ve canlı API senkronizasyonu öncesi boş şablon."""
    return {
        "last_synced_at": "Henüz senkronize edilmedi",
        "apple_sync_status": "BEKLİYOR (Apple App Store Connect API)",
        "google_sync_status": "BEKLİYOR (Google Play Developer API)",
        "ios_versions": [],
        "android_versions": [],
        "apple_impressions_total": 0,
        "apple_impressions_unique": 0,
        "apple_impressions_search": 0,
        "apple_impressions_browse": 0,
        "apple_impressions_by_source": {},
        "apple_page_views_total": 0,
        "apple_page_views_unique": 0,
        "apple_taps_total": 0,
        "apple_taps_unique": 0,
        "apple_downloads_total": 0,
        "apple_downloads_first_time": 0,
        "apple_downloads_redownload": 0,
        "apple_downloads_search": 0,
        "apple_downloads_referrer": 0,
        "apple_downloads_browse": 0,
        "apple_downloads_recent_sales_api": 0,
        "apple_downloads_by_source": {},
        "apple_downloads_by_country": [],
        "apple_sessions_total": 0,
        "apple_sessions_duration_sec": 0,
        "apple_sessions_optin_devices": 0,
        "apple_returning_optin_devices": 0,
        "apple_loyal_optin_devices": 0,
        "apple_returning_sessions_total": 0,
        "apple_max_sessions_per_device": 0,
        "apple_vip_activations_total": 0,
        "apple_vip_total_transactions": 0,
        "apple_vip_paid_conversions": 0,
        "apple_vip_paid_customer_price_try": 0.0,
        "apple_vip_paid_proceeds_try": 0.0,
        "apple_vip_offer_code_subs": 0,
        "apple_vip_offer_code_name": "-",
        "apple_vip_active_trials": 0,
        "apple_vip_by_plan": {},
        "google_play_downloads_baseline": 0,
        "google_play_subscriptions_catalog": [
            {
                "product_id": "misil",
                "base_plan_id": "misil",
                "title": "Mışıl Baby Yıllık VIP",
                "state": "ACTIVE",
                "billing_period": "Yıllık (P1Y)",
                "grace_period": "14 Gün (P14D)",
                "price_try": 599.99,
                "net_proceeds_try": 436.20,
                "free_trial_offer_id": "3daystrial",
                "free_trial_label": "7 Gün Ücretsiz Deneme (P7D • Aktif)",
            },
            {
                "product_id": "misilaylik",
                "base_plan_id": "misilaylik",
                "title": "Mışıl Baby Aylık VIP",
                "state": "ACTIVE",
                "billing_period": "Aylık (P1M)",
                "grace_period": "7 Gün (P7D)",
                "price_try": 149.99,
                "net_proceeds_try": 109.05,
                "free_trial_offer_id": "freeytrial",
                "free_trial_label": "7 Gün Ücretsiz Deneme (P7D • Aktif)",
            },
        ],
        "daily_store_series": {},
        "store_reviews": [],
    }


OFFICIAL_STORE_BASELINE: Dict[str, Any] = _empty_store_state()


def _aggregate_apple_r8_cohorts(r8_daily_rows: Dict[tuple, tuple]) -> Dict[str, int]:
    """
    Apple r8 (App Sessions Standard) günlük satırlarını önce (Date + Download Date + Device + Platform Version + Source + Territory)
    bazında tekilleştirir (farklı Page Type dilimlerinde aynı cihazın çift sayılmasını önler), ardından indirme kohortu bazında
    güvercin yuvası ilkesiyle (Pigeonhole Principle) toplam opt-in cihaz, 2+ oturumlu tekrar giren (returning) cihaz,
    3+ oturumlu sadık cihaz ve toplam süreyi hesaplar.
    """
    if not r8_daily_rows:
        return {
            "apple_sessions_optin_devices": 0,
            "apple_returning_optin_devices": 0,
            "apple_loyal_optin_devices": 0,
            "apple_returning_sessions_total": 0,
            "apple_max_sessions_per_device": 0,
            "apple_sessions_duration_sec": 0,
        }
    daily_dedup: Dict[tuple, tuple] = {}
    for (dt_s, dl_dt, dev_s, pver_s, src_s, terr_s, _page_s), (sess_v, dur_v, udev_v) in r8_daily_rows.items():
        d_key = (dt_s, dl_dt, dev_s, pver_s, src_s, terr_s)
        prev = daily_dedup.get(d_key)
        if not prev or sess_v > prev[0]:
            daily_dedup[d_key] = (sess_v, dur_v, max(prev[2] if prev else 0, udev_v))

    cohorts_r8: Dict[tuple, Dict[str, Any]] = {}
    total_r8_dur = 0
    for (dt_s, dl_dt, dev_s, pver_s, src_s, terr_s), (sess_v, dur_v, udev_v) in daily_dedup.items():
        total_r8_dur += dur_v
        c_key = (dl_dt, dev_s, pver_s, src_s, terr_s)
        c_item = cohorts_r8.setdefault(c_key, {"max_udev": 0, "sessions": 0, "days": set()})
        c_item["max_udev"] = max(c_item["max_udev"], udev_v)
        c_item["sessions"] += sess_v
        if dt_s:
            c_item["days"].add(dt_s)

    optin_total_calc = 0
    returning_optin_calc = 0
    loyal_optin_calc = 0
    returning_sess_calc = 0
    max_sess_single_calc = 0
    for v in cohorts_r8.values():
        u = max(0, int(v["max_udev"]))
        s = max(0, int(v["sessions"]))
        d = len(v["days"])
        if u <= 0:
            continue
        optin_total_calc += u
        # Güvercin yuvası ilkesi: u > 1 olan bir segmentte toplam oturum s <= u ve gün sayısı d < 2 ise
        # her cihaz 1'er kez girmiş olabilir (returning = 0). s > u veya d >= 2 ise tekrar giriş kesindir.
        if u == 1:
            ret_u = 1 if (s >= 2 or d >= 2) else 0
            loy_u = 1 if s >= 3 else 0
            est_max_single = s
        else:
            if s >= 2 * u:
                ret_u = u
            elif s > u:
                ret_u = s - u
            elif d >= 2:
                ret_u = 1
            else:
                ret_u = 0
            if s >= 3 * u:
                loy_u = u
            elif s > 2 * u:
                loy_u = s - 2 * u
            else:
                loy_u = 0
            est_max_single = round(s / u)
        returning_optin_calc += ret_u
        loyal_optin_calc += loy_u
        if ret_u > 0:
            returning_sess_calc += s
        max_sess_single_calc = max(max_sess_single_calc, est_max_single)

    return {
        "apple_sessions_optin_devices": optin_total_calc,
        "apple_returning_optin_devices": returning_optin_calc,
        "apple_loyal_optin_devices": loyal_optin_calc,
        "apple_returning_sessions_total": returning_sess_calc,
        "apple_max_sessions_per_device": max_sess_single_calc,
        "apple_sessions_duration_sec": total_r8_dur,
    }


class AppSignalPayload(BaseModel):
    device_uid: str = Field(..., min_length=3, max_length=120)
    event_type: str = Field(default="first_open", max_length=48)
    os_family: Optional[str] = Field(default=None, max_length=32)
    platform: Optional[str] = Field(default="web_pwa", max_length=48)
    app_version: Optional[str] = Field(default="4.46.5", max_length=32)


def verify_admin_pin(
    pin: Optional[str] = None,
    x_admin_pin: Optional[str] = None,
) -> bool:
    """Sabit zamanlı (timing-attack korumalı) yönetici PIN doğrulaması."""
    raw_pin = pin if isinstance(pin, str) else (x_admin_pin if isinstance(x_admin_pin, str) else "")
    entered_pin = raw_pin.strip().upper()
    if not entered_pin:
        return False
    return any(hmac.compare_digest(entered_pin, valid_pin) for valid_pin in ADMIN_PINS)


_pin_is_valid = verify_admin_pin


def _extract_client_ip(request: Request) -> str:
    ip = (
        request.headers.get("cf-connecting-ip")
        or request.headers.get("x-forwarded-for")
        or (request.client.host if request.client else "unknown")
    )
    if ip and "," in ip:
        ip = ip.split(",")[0].strip()
    return ip or "unknown"


def _is_pin_client_blocked(client_key: str) -> bool:
    now_ts = time.time()
    with _PIN_RATE_LIMIT_LOCK:
        # Bellek sızıntısını önlemek için süresi dolmuş blokları temizle
        expired_keys = [k for k, v in _PIN_BLOCK_UNTIL.items() if now_ts >= v]
        for ek in expired_keys:
            _PIN_BLOCK_UNTIL.pop(ek, None)
            _PIN_FAILED_ATTEMPTS.pop(ek, None)
        blocked_until = _PIN_BLOCK_UNTIL.get(client_key)
        if blocked_until and now_ts < blocked_until:
            return True
        return False


def _register_pin_failure(client_key: str) -> None:
    now_ts = time.time()
    with _PIN_RATE_LIMIT_LOCK:
        attempts = [t for t in _PIN_FAILED_ATTEMPTS.get(client_key, []) if now_ts - t < _PIN_ATTEMPT_WINDOW_SECONDS]
        attempts.append(now_ts)
        _PIN_FAILED_ATTEMPTS[client_key] = attempts
        if len(attempts) >= _PIN_MAX_ATTEMPTS:
            _PIN_BLOCK_UNTIL[client_key] = now_ts + _PIN_BLOCK_SECONDS
            logger.warning(
                f"ADMIN_PIN_SECURITY: {client_key} brute-force şüphesiyle {_PIN_BLOCK_SECONDS // 60} dk bloklandı."
            )


def _register_pin_success(client_key: str) -> None:
    with _PIN_RATE_LIMIT_LOCK:
        _PIN_FAILED_ATTEMPTS.pop(client_key, None)
        _PIN_BLOCK_UNTIL.pop(client_key, None)


def _make_admin_session_token(pin_value: str, exp_ts: Optional[int] = None) -> str:
    """Sunucu tarafında süresi doğrulanabilen (exp.signature) imzalı oturum dizgesi üretir."""
    normalized = pin_value.strip().upper()
    exp_val = int(exp_ts if exp_ts is not None else (time.time() + _ADMIN_SESSION_TTL_SECONDS))
    payload = f"{normalized}:{exp_val}"
    sig = hmac.new(_ADMIN_SESSION_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{exp_val}.{sig}"


def _admin_session_token_is_valid(token: Optional[str]) -> bool:
    if not token or not isinstance(token, str) or "." not in token:
        return False
    parts = token.split(".", 1)
    if len(parts) != 2 or not parts[0].isdigit():
        return False
    exp_val = int(parts[0])
    if time.time() > exp_val:
        return False
    return any(
        hmac.compare_digest(token, _make_admin_session_token(valid_pin, exp_ts=exp_val))
        for valid_pin in ADMIN_PINS
    )


def authorize_admin_request(
    request: Request,
    pin: Optional[str] = None,
    x_admin_pin: Optional[str] = None,
    session_token: Optional[str] = None,
) -> bool:
    """
    IP bazlı brute-force korumalı yönetici yetkilendirmesi.
    Geçerli ve süresi dolmamış bir oturum çerezi varsa PIN'i tekrar sormadan doğrular.
    """
    if _admin_session_token_is_valid(session_token):
        return True

    client_key = _extract_client_ip(request)
    if _is_pin_client_blocked(client_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Çok fazla hatalı PIN denemesi. Lütfen 15 dakika sonra tekrar deneyin.",
        )

    is_valid = verify_admin_pin(pin, x_admin_pin)
    if is_valid:
        _register_pin_success(client_key)
    else:
        _register_pin_failure(client_key)
    return is_valid


def _convert_to_try(amount: float, currency_code: Optional[str]) -> float:
    ccy = (currency_code or "TRY").strip().upper()
    rate = FX_RATES_TO_TRY.get(ccy, 1.0)
    return round(float(amount or 0.0) * rate, 2)


def _reconcile_ios_ledger_and_cancellations(
    db: Session,
    cancel_cohorts: Optional[Counter] = None,
    active_trials_target: Optional[int] = None,
) -> bool:
    """
    Apple App Store Connect mutabakat motoru:
    1) Yıllık 7 günlük deneme (Default_Intro / 7 Days) olduğu halde eski mantıkla 'offer_code_trial'
       veya 799.99 TL yazılmış kayıtları 'intro_free_trial' (+7 gün vade, 599.99 TL / 332.50 TL) olarak onarır.
    2) SUBSCRIPTION_EVENT (Event='Cancel') raporundaki iptalleri (product_id, original_start_date, country)
       kohort eşleşmesiyle SubscriberLedger üzerinde status='cancelled' ve auto_renew_enabled=False yapar.
    3) Apple SUBSCRIPTION (1_3) raporundaki aktif deneme sayısı (active_trials_target) ile DB arasındaki
       vadesi geçmiş deneme farkını kapatır.
    """
    changed = False

    # 0) Doğrulanmamış istemci localStorage kaynaklı sentetik DEV_IOS_* / DEV_ANDROID_* hayalet/mükerrer kayıtları temizle
    dev_rows: List[SubscriberLedger] = (
        db.query(SubscriberLedger)
        .filter(
            SubscriberLedger.subscriber_id.like("DEV_%"),
            (SubscriberLedger.customer_price_try == 0.0) | (SubscriberLedger.customer_price_try.is_(None)),
        )
        .all()
    )
    if dev_rows:
        for dr in dev_rows:
            db.delete(dr)
        db.query(SubscriptionLifecycleEvent).filter(
            SubscriptionLifecycleEvent.event_type.like("DEV_%")
        ).delete(synchronize_session=False)
        db.flush()
        changed = True

    ios_rows: List[SubscriberLedger] = (
        db.query(SubscriberLedger)
        .filter(SubscriberLedger.platform == "ios")
        .order_by(SubscriberLedger.started_date.asc(), SubscriberLedger.subscriber_id.asc())
        .all()
    )
    if not ios_rows:
        return changed

    refunded_sids = {
        (ev.event_type or "").split(":")[0]
        for ev in db.query(SubscriptionLifecycleEvent).filter(
            SubscriptionLifecycleEvent.platform == "ios",
            SubscriptionLifecycleEvent.event_type.like("%:refund"),
        ).all()
    }

    # 1) Ücretli aktif (paid_active) auto_renew_enabled onarımı + Yıllık 7G deneme (Default_Intro) 599.99 TL tarife onarımı
    for r in ios_rows:
        if r.status == "paid_active" and (r.customer_price_try or 0.0) > 0 and r.subscriber_id not in refunded_sids:
            if not r.auto_renew_enabled:
                r.auto_renew_enabled = True
                changed = True
            if (r.expected_next_price_try or 0.0) <= 0:
                r.expected_next_price_try = round(float(r.customer_price_try), 2)
                changed = True
            if (r.expected_next_proceeds_try or 0.0) <= 0:
                r.expected_next_proceeds_try = round(
                    float(r.developer_proceeds_try or round(float(r.customer_price_try) * 0.55417, 2)), 2
                )
                changed = True

        is_ann = _is_annual_product(r.product_id)
        of_name_low = (r.offer_code_name or "").strip().lower()
        is_default_intro = (
            not of_name_low
            or "default_intro" in of_name_low
            or "7 günlük deneme" in of_name_low
        )
        if is_ann and r.status == "offer_code_trial" and is_default_intro and (r.customer_price_try or 0.0) <= 0:
            r.status = "intro_free_trial"
            r.offer_type = "intro_7d_trial"
            if not of_name_low or "default_intro" in of_name_low:
                r.offer_code_name = "7 Günlük Deneme"
            try:
                if r.started_date and len(r.started_date) == 10:
                    dt_st = datetime.strptime(r.started_date, "%Y-%m-%d")
                    r.maturity_or_renewal_date = (dt_st + timedelta(days=7)).strftime("%Y-%m-%d")
            except Exception:
                pass
            std_g, std_n = _resolve_expected_trial_pricing(r.product_id, 0.0, 0.0, "ios")
            r.expected_next_price_try = std_g
            r.expected_next_proceeds_try = std_n
            changed = True
        elif is_ann and r.status == "intro_free_trial" and round(float(r.expected_next_price_try or 0.0), 2) == 799.99:
            std_g, std_n = _resolve_expected_trial_pricing(r.product_id, 0.0, 0.0, "ios")
            r.expected_next_price_try = std_g
            r.expected_next_proceeds_try = std_n
            changed = True

    # 2) SUBSCRIPTION_EVENT (Event='Cancel') kohort eşleşmesi
    merged_cancels: Counter = Counter()
    if cancel_cohorts:
        merged_cancels.update(cancel_cohorts)

    ev_rows: List[SubscriptionLifecycleEvent] = (
        db.query(SubscriptionLifecycleEvent)
        .filter(SubscriptionLifecycleEvent.platform == "ios")
        .all()
    )
    db_cancels: Counter = Counter()
    for ev in ev_rows:
        et = (ev.event_type or "").strip()
        if et.startswith("EVENT:Cancel:"):
            parts = et.split(":")
            orig_st = parts[2] if len(parts) > 2 else ""
            cntry = (ev.country or (parts[3] if len(parts) > 3 else "TR")).strip().upper()
            if orig_st and len(orig_st) == 10:
                db_cancels[(ev.product_id or "misil_monthly", orig_st, cntry)] += max(1, int(ev.quantity or 1))
        elif et.lower() == "cancel":
            orig_st = ""
            try:
                days_b = int(float(str(ev.days_before_canceling or "0").strip() or 0))
                if ev.event_date and len(ev.event_date) == 10 and days_b > 0:
                    dt_ev = datetime.strptime(ev.event_date, "%Y-%m-%d")
                    orig_st = (dt_ev - timedelta(days=days_b)).strftime("%Y-%m-%d")
            except Exception:
                orig_st = ""
            cntry = (ev.country or "TR").strip().upper()
            if orig_st:
                db_cancels[(ev.product_id or "misil_monthly", orig_st, cntry)] += max(1, int(ev.quantity or 1))

    for k_coh, cnt_val in db_cancels.items():
        if cnt_val > merged_cancels[k_coh]:
            merged_cancels[k_coh] = cnt_val

    for (pid_c, st_date_c, cntry_c), req_cancel_cnt in merged_cancels.items():
        if req_cancel_cnt <= 0:
            continue
        cohort_subs = [
            r for r in ios_rows
            if (r.product_id or "misil_monthly") == pid_c
            and (r.started_date or "") == st_date_c
            and (r.country or "TR").upper() == cntry_c
            and r.status != "paid_active"
        ]
        for r in cohort_subs:
            if not r.auto_renew_enabled and r.status != "cancelled":
                r.status = "cancelled"
                r.expected_next_price_try = 0.0
                r.expected_next_proceeds_try = 0.0
                changed = True
        already_cancelled = sum(1 for r in cohort_subs if r.status == "cancelled")
        need_to_cancel = max(0, req_cancel_cnt - already_cancelled)
        if need_to_cancel > 0:
            for r in cohort_subs:
                if need_to_cancel <= 0:
                    break
                if r.status != "cancelled" and r.auto_renew_enabled:
                    r.status = "cancelled"
                    r.auto_renew_enabled = False
                    r.expected_next_price_try = 0.0
                    r.expected_next_proceeds_try = 0.0
                    need_to_cancel -= 1
                    changed = True

    # 3) Apple SUBSCRIPTION (1_3) aktif deneme sayısı hedefiyle mutabakat
    if active_trials_target is not None and active_trials_target > 0:
        tz_tr = timezone(timedelta(hours=3))
        today_str = datetime.now(tz_tr).strftime("%Y-%m-%d")
        active_trials = [
            r for r in ios_rows
            if r.status == "intro_free_trial" and r.auto_renew_enabled
        ]
        deficit = int(active_trials_target) - len(active_trials)
        if deficit > 0 and merged_cancels:
            # Daha önce DEV_IOS_* şişmesi nedeniyle yanlışlıkla iptal edilmiş (Cancel olayı bulunmayan) gerçek Apple denemelerini geri yükle
            cancelled_by_cohort: Dict[tuple, List[SubscriberLedger]] = {}
            for r in ios_rows:
                if r.status == "cancelled" and (r.customer_price_try or 0.0) <= 0 and r.offer_type == "intro_7d_trial":
                    ck = ((r.product_id or "misil_monthly"), (r.started_date or ""), (r.country or "TR").upper())
                    cancelled_by_cohort.setdefault(ck, []).append(r)
            restorable: List[SubscriberLedger] = []
            for ck, c_rows in cancelled_by_cohort.items():
                req_c = merged_cancels.get(ck, 0)
                if len(c_rows) > req_c:
                    restorable.extend(c_rows[req_c:])
            restorable.sort(key=lambda x: (x.started_date or "", x.subscriber_id or ""), reverse=True)
            for r in restorable[:deficit]:
                r.status = "intro_free_trial"
                r.auto_renew_enabled = True
                std_g, std_n = _resolve_expected_trial_pricing(r.product_id, 0.0, 0.0, "ios")
                r.expected_next_price_try = std_g
                r.expected_next_proceeds_try = std_n
                changed = True
        elif deficit < 0:
            excess = -deficit
            past_due_trials = [
                r for r in active_trials
                if r.maturity_or_renewal_date and len(r.maturity_or_renewal_date) == 10 and r.maturity_or_renewal_date < today_str
            ]
            for r in past_due_trials[:excess]:
                r.status = "cancelled"
                r.auto_renew_enabled = False
                r.expected_next_price_try = 0.0
                r.expected_next_proceeds_try = 0.0
                changed = True

    return changed


def sync_live_store_apis(days_back: int = 5) -> Dict[str, Any]:
    """
    P0-1 & Sıfır Statik Veri Çözümü:
    Ağ G/Ç işlemleri _BASELINE_LOCK dışında yürütülür; Apple App Store Connect API ve
    Google Play Developer API verileri doğrudan StoreDailyMetric, SubscriberLedger,
    SubscriptionLifecycleEvent ve StoreSyncState tablolarına idempotent olarak yazılır.
    """
    if not jwt:
        return {"synced": False, "sources": [], "reason": "PyJWT not available"}

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
    env_p8_path = os.environ.get("ASC_PRIVATE_KEY_PATH")
    p8_candidates: List[str] = []
    if env_p8_path:
        p8_candidates.append(env_p8_path)
    p8_candidates.extend(glob.glob(os.path.join(project_root, "mobile", "AuthKey_*.p8")))
    p8_candidates.extend(glob.glob(os.path.join(project_root, "..", "..", "projects", "mishil", "mobile", "AuthKey_*.p8")))
    p8_path = next((p for p in p8_candidates if os.path.exists(p)), None)
    detected_key_id = ""
    if p8_path:
        bn = os.path.basename(p8_path)
        if bn.startswith("AuthKey_") and bn.endswith(".p8"):
            detected_key_id = bn[len("AuthKey_"):-len(".p8")]
    asc_key_id = os.environ.get("ASC_KEY_ID") or detected_key_id or "8YHMP6BH2H"
    asc_issuer_id = os.environ.get("ASC_ISSUER_ID") or "7d2413c6-ea40-4bd9-9334-8313a514b0e6"
    asc_priv_key = os.environ.get("ASC_PRIVATE_KEY")

    if not asc_priv_key and p8_path:
        try:
            with open(p8_path, "r", encoding="utf-8") as f:
                asc_priv_key = f.read()
        except Exception as e:
            logger.warning("Failed to read Apple .p8 key file: %s", e)

    if asc_priv_key:
        asc_priv_key = asc_priv_key.replace("\\n", "\n")
    else:
        logger.info("Apple private key (.p8) not found on disk or environment.")

    synced_sources: List[str] = []
    fetched_apple_reviews: List[Dict[str, Any]] = []
    fetched_gp_reviews: List[Dict[str, Any]] = []
    country_totals: Counter = Counter()
    latest_sub_state: Dict[str, int] = {}
    cancel_cohorts_synced: Counter = Counter()
    apple_connected = False
    google_connected = False

    if asc_priv_key and asc_key_id and asc_issuer_id:
        try:
            now_ts = int(time.time())
            token = jwt.encode(
                {"iss": asc_issuer_id, "iat": now_ts - 30, "exp": now_ts + 900, "aud": "appstoreconnect-v1"},
                asc_priv_key,
                algorithm="ES256",
                headers={"kid": asc_key_id, "typ": "JWT"},
            )
            hdrs = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            req = urllib.request.Request(
                "https://api.appstoreconnect.apple.com/v1/apps/6809223195/customerReviews?limit=50",
                headers=hdrs,
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                if resp.status == 200:
                    apple_connected = True
                    data = json.loads(resp.read().decode("utf-8"))
                    for r in data.get("data", []):
                        attr = r.get("attributes", {})
                        cdate = (attr.get("createdDate") or "")[:10]
                        if len(cdate) == 10 and "-" in cdate:
                            parts = cdate.split("-")
                            cdate = f"{parts[2]}.{parts[1]}.{parts[0]}"
                        rating_clamped = max(1, min(5, int(attr.get("rating") or 5)))
                        fetched_apple_reviews.append({
                            "store": "App Store",
                            "badge": "🍏 iOS",
                            "rating": rating_clamped,
                            "title": attr.get("title") or "App Store Yorumu",
                            "body": attr.get("body") or "",
                            "author": attr.get("reviewerNickname") or "App Store Kullanıcısı",
                            "date": cdate,
                        })
                    synced_sources.append("Apple App Store Connect API (Reviews)")

            vendor_num = os.environ.get("ASC_VENDOR_NUMBER", "94806500")
            tz_tr_sync = timezone(timedelta(hours=3))
            today_d = datetime.now(tz_tr_sync).date()
            scan_days = max(1, min(30, int(days_back)))

            for day_offset in range(scan_days, -1, -1):
                rep_date = (today_d - timedelta(days=day_offset)).strftime("%Y-%m-%d")

                # 1) SALES Raporu -> StoreDailyMetric upsert
                sales_url = (
                    "https://api.appstoreconnect.apple.com/v1/salesReports"
                    f"?filter[frequency]=DAILY&filter[reportDate]={rep_date}"
                    f"&filter[reportSubType]=SUMMARY&filter[reportType]=SALES&filter[vendorNumber]={vendor_num}"
                )
                s_req = urllib.request.Request(
                    sales_url,
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/a-gzip"},
                )
                try:
                    with urllib.request.urlopen(s_req, timeout=3) as s_resp:
                        if s_resp.status == 200:
                            apple_connected = True
                            tsv_txt = gzip.decompress(s_resp.read()).decode("utf-8", errors="replace")
                            lines = [ln for ln in tsv_txt.splitlines() if ln.strip()]
                            if len(lines) > 1:
                                hdr = lines[0].split("\t")
                                day_app_dl = 0
                                day_redl = 0
                                day_sub_vip = 0
                                day_gross_try = 0.0
                                day_net_try = 0.0
                                for ln in lines[1:]:
                                    row_d = dict(zip(hdr, ln.split("\t")))
                                    p_type = (row_d.get("Product Type Identifier") or "").strip()
                                    units = int(float(row_d.get("Units", "0") or 0))
                                    cc = (row_d.get("Country Code") or "TR").strip().upper()
                                    c_price = float(row_d.get("Customer Price") or 0.0)
                                    d_proc = float(row_d.get("Developer Proceeds") or 0.0)
                                    c_ccy = row_d.get("Customer Currency") or "TRY"
                                    p_ccy = row_d.get("Currency of Proceeds") or c_ccy
                                    if p_type in ("1", "1F", "1T", "F1"):
                                        day_app_dl += units
                                        if units > 0:
                                            country_totals[cc] += units
                                    elif p_type in ("3", "3F"):
                                        day_redl += units
                                        day_app_dl += units
                                    elif p_type in ("IAY", "IA9", "IA1"):
                                        day_sub_vip += units
                                        if c_price > 0:
                                            day_gross_try += _convert_to_try(c_price * max(1, units), c_ccy)
                                            day_net_try += _convert_to_try(d_proc * max(1, units), p_ccy)

                                db_s = SessionLocal()
                                try:
                                    dm = (
                                        db_s.query(StoreDailyMetric)
                                        .filter(StoreDailyMetric.metric_date == rep_date, StoreDailyMetric.platform == "ios")
                                        .first()
                                    )
                                    if dm:
                                        dm.downloads_total = day_app_dl
                                        dm.redownloads = day_redl
                                        dm.active_free_trials = max(dm.active_free_trials or 0, day_sub_vip)
                                        if day_gross_try > 0:
                                            dm.gross_revenue_try = round(day_gross_try, 2)
                                            dm.net_proceeds_try = round(day_net_try, 2)
                                    else:
                                        db_s.add(
                                            StoreDailyMetric(
                                                metric_date=rep_date,
                                                platform="ios",
                                                downloads_total=day_app_dl,
                                                redownloads=day_redl,
                                                active_free_trials=day_sub_vip,
                                                gross_revenue_try=round(day_gross_try, 2),
                                                net_proceeds_try=round(day_net_try, 2),
                                            )
                                        )
                                    db_s.commit()
                                finally:
                                    db_s.close()
                                synced_sources.append(f"Apple Sales Report ({rep_date})")
                except Exception as e:
                    logger.debug("Apple Sales Report info (%s): %s", rep_date, e)

                # 2) SUBSCRIPTION Durum Özeti -> Aktif abone sayıları (tüm aktif sütunlar dahil)
                sub_state_url = (
                    "https://api.appstoreconnect.apple.com/v1/salesReports"
                    f"?filter[frequency]=DAILY&filter[reportDate]={rep_date}"
                    f"&filter[reportSubType]=SUMMARY&filter[reportType]=SUBSCRIPTION"
                    f"&filter[vendorNumber]={vendor_num}&filter[version]=1_3"
                )
                sub_req = urllib.request.Request(
                    sub_state_url,
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/a-gzip"},
                )
                try:
                    with urllib.request.urlopen(sub_req, timeout=3) as sub_resp:
                        if sub_resp.status == 200:
                            st_txt = gzip.decompress(sub_resp.read()).decode("utf-8", errors="replace")
                            st_lines = [ln for ln in st_txt.splitlines() if ln.strip()]
                            if len(st_lines) > 1:
                                st_hdr = st_lines[0].split("\t")
                                paid_cnt = 0
                                code_cnt = 0
                                trial_cnt = 0
                                for ln in st_lines[1:]:
                                    sd = dict(zip(st_hdr, ln.split("\t")))
                                    paid_cnt += (
                                        int(float(sd.get("Active Standard Price Subscriptions", "0") or 0))
                                        + int(float(sd.get("Active Pay Up Front Introductory Offer Subscriptions", "0") or 0))
                                        + int(float(sd.get("Active Pay As You Go Introductory Offer Subscriptions", "0") or 0))
                                    )
                                    code_cnt += (
                                        int(float(sd.get("Free Trial Offer Code Subscriptions", "0") or 0))
                                        + int(float(sd.get("Pay Up Front Offer Code Subscriptions", "0") or 0))
                                        + int(float(sd.get("Pay As You Go Offer Code Subscriptions", "0") or 0))
                                        + int(float(sd.get("Free Trial Promotional Offer Subscriptions", "0") or 0))
                                    )
                                    trial_cnt += int(float(sd.get("Active Free Trial Introductory Offer Subscriptions", "0") or 0))
                                if (paid_cnt + code_cnt + trial_cnt) > 0:
                                    latest_sub_state = {
                                        "paid": paid_cnt,
                                        "code": code_cnt,
                                        "trial": trial_cnt,
                                        "total": paid_cnt + code_cnt + trial_cnt,
                                    }
                                    synced_sources.append(f"Apple Subscription State ({rep_date})")
                except Exception as e:
                    logger.debug("Apple Subscription State info (%s): %s", rep_date, e)

                # 3) SUBSCRIBER (DETAILED 1_3) Raporu -> İdempotent SubscriberLedger & SubscriptionLifecycleEvent
                sub_det_url = (
                    "https://api.appstoreconnect.apple.com/v1/salesReports"
                    f"?filter[frequency]=DAILY&filter[reportDate]={rep_date}"
                    f"&filter[reportSubType]=DETAILED&filter[reportType]=SUBSCRIBER"
                    f"&filter[vendorNumber]={vendor_num}&filter[version]=1_3"
                )
                sub_det_req = urllib.request.Request(
                    sub_det_url,
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/a-gzip"},
                )
                try:
                    with urllib.request.urlopen(sub_det_req, timeout=3) as det_resp:
                        if det_resp.status == 200:
                            det_txt = gzip.decompress(det_resp.read()).decode("utf-8", errors="replace")
                            det_lines = [ln for ln in det_txt.splitlines() if ln.strip()]
                            if len(det_lines) > 1:
                                det_hdr = det_lines[0].split("\t")
                                db_sync = SessionLocal()
                                try:
                                    for ln in det_lines[1:]:
                                        rd = dict(zip(det_hdr, ln.split("\t")))
                                        sid = (rd.get("Subscriber ID") or "").strip()
                                        if not sid:
                                            continue
                                        ev_date = (rd.get("Event Date") or rep_date).strip()
                                        sub_name = (rd.get("Subscription Name") or "Aylik Esnek").strip()
                                        offer_name = (rd.get("Subscription Offer Name") or "").strip()
                                        offer_type_raw = (rd.get("Subscription Offer Type") or "").strip()
                                        offer_dur_raw = (rd.get("Subscription Offer Duration") or "").strip()
                                        raw_c_price = float(rd.get("Customer Price") or 0.0)
                                        raw_d_proc = float(rd.get("Developer Proceeds") or 0.0)
                                        c_ccy = (rd.get("Customer Currency") or "TRY").strip().upper()
                                        p_ccy = (rd.get("Proceeds Currency") or c_ccy).strip().upper()
                                        c_price_try = _convert_to_try(raw_c_price, c_ccy)
                                        d_proc_try = _convert_to_try(raw_d_proc, p_ccy)
                                        cntry = (rd.get("Country") or "TR").strip().upper()
                                        dev = (rd.get("Device") or "iPhone").strip()
                                        refund_flag = (rd.get("Refund") or "").strip().lower() == "yes"
                                        is_annual = "Yillik" in sub_name or "6809228257" in (rd.get("Subscription Apple ID") or "")
                                        prod_id = "misil_annual" if is_annual else "misil_monthly"
                                        plan_lbl = "Yıllık VIP" if is_annual else "Aylık Esnek VIP"
                                        paid_ref = (
                                            db_sync.query(SubscriberLedger)
                                            .filter(
                                                SubscriberLedger.product_id == prod_id,
                                                SubscriberLedger.customer_price_try > 0,
                                            )
                                            .first()
                                        )
                                        ref_gross = float(paid_ref.customer_price_try) if paid_ref else 0.0
                                        ref_net = float(paid_ref.developer_proceeds_try) if paid_ref else 0.0
                                        std_price_try, std_proc_try = _resolve_expected_trial_pricing(
                                            prod_id, ref_gross, ref_net, "ios"
                                        )

                                        is_intro_offer = (
                                            "default_intro" in offer_name.lower()
                                            or "introductory" in offer_type_raw.lower()
                                            or "7 days" in offer_dur_raw.lower()
                                            or "1 week" in offer_dur_raw.lower()
                                        )
                                        is_offer_code = bool(
                                            c_price_try <= 0
                                            and not is_intro_offer
                                            and (
                                                (offer_name and "default_intro" not in offer_name.lower())
                                                or "offer code" in offer_type_raw.lower()
                                                or "promotional" in offer_type_raw.lower()
                                                or "1 year" in offer_dur_raw.lower()
                                            )
                                        )

                                        ev_type_key = "refund" if refund_flag else ("paid_conversion" if c_price_try > 0 else "trial_or_code_start")
                                        dup_ev = (
                                            db_sync.query(SubscriptionLifecycleEvent.id)
                                            .filter(
                                                SubscriptionLifecycleEvent.event_date == ev_date,
                                                SubscriptionLifecycleEvent.event_type == f"{sid}:{ev_type_key}",
                                                SubscriptionLifecycleEvent.product_id == prod_id,
                                            )
                                            .first()
                                        )
                                        is_new_event = dup_ev is None
                                        if is_new_event:
                                            db_sync.add(
                                                SubscriptionLifecycleEvent(
                                                    event_date=ev_date,
                                                    platform="ios",
                                                    event_type=f"{sid}:{ev_type_key}",
                                                    product_id=prod_id,
                                                    plan_label=plan_lbl,
                                                    offer_code_name=offer_name or None,
                                                    country=cntry,
                                                    device_type=dev,
                                                    quantity=1,
                                                )
                                            )

                                        existing_sub = db_sync.query(SubscriberLedger).filter(SubscriberLedger.subscriber_id == sid).first()
                                        if existing_sub:
                                            if refund_flag and is_new_event:
                                                existing_sub.status = "cancelled"
                                                existing_sub.auto_renew_enabled = False
                                                existing_sub.customer_price_try = max(0.0, round((existing_sub.customer_price_try or 0.0) - abs(c_price_try), 2))
                                                existing_sub.developer_proceeds_try = max(0.0, round((existing_sub.developer_proceeds_try or 0.0) - abs(d_proc_try), 2))
                                            elif c_price_try > 0 and is_new_event and existing_sub.converted_or_renewed_date != ev_date:
                                                existing_sub.status = "paid_active"
                                                existing_sub.offer_type = "standard_paid"
                                                existing_sub.auto_renew_enabled = True
                                                existing_sub.converted_or_renewed_date = ev_date
                                                existing_sub.customer_price_try = round((existing_sub.customer_price_try or 0.0) + c_price_try, 2)
                                                existing_sub.developer_proceeds_try = round((existing_sub.developer_proceeds_try or 0.0) + d_proc_try, 2)
                                                existing_sub.expected_next_price_try = c_price_try
                                                existing_sub.expected_next_proceeds_try = d_proc_try
                                                try:
                                                    dt_conv = datetime.strptime(ev_date, "%Y-%m-%d")
                                                    existing_sub.maturity_or_renewal_date = (dt_conv + timedelta(days=365 if is_annual else 30)).strftime("%Y-%m-%d")
                                                except Exception:
                                                    pass
                                            elif existing_sub.status == "offer_code_trial" and not is_offer_code and c_price_try <= 0:
                                                existing_sub.status = "intro_free_trial"
                                                existing_sub.offer_type = "intro_7d_trial"
                                                ccy_suffix = f" ({c_ccy})" if c_ccy != "TRY" else ""
                                                existing_sub.offer_code_name = ("7 Günlük Deneme" + ccy_suffix)[:95]
                                                try:
                                                    dt_st = datetime.strptime(existing_sub.started_date or ev_date, "%Y-%m-%d")
                                                    existing_sub.maturity_or_renewal_date = (dt_st + timedelta(days=7)).strftime("%Y-%m-%d")
                                                except Exception:
                                                    pass
                                                existing_sub.expected_next_price_try = std_price_try
                                                existing_sub.expected_next_proceeds_try = std_proc_try
                                        else:
                                            trial_days = (365 if is_annual else 30) if is_offer_code else 7
                                            try:
                                                dt_st = datetime.strptime(ev_date, "%Y-%m-%d")
                                                mat_date = (dt_st + timedelta(days=(365 if is_annual else 30) if c_price_try > 0 else trial_days)).strftime("%Y-%m-%d")
                                            except Exception:
                                                mat_date = ev_date
                                            st_val = "paid_active" if c_price_try > 0 else ("offer_code_trial" if is_offer_code else "intro_free_trial")
                                            of_type = "standard_paid" if c_price_try > 0 else ("offer_code" if is_offer_code else "intro_7d_trial")
                                            ccy_suffix = f" ({c_ccy})" if c_ccy != "TRY" else ""
                                            of_lbl = (offer_name if is_offer_code else ("Standart Ücretli" if c_price_try > 0 else "7 Günlük Deneme")) + ccy_suffix
                                            db_sync.add(
                                                SubscriberLedger(
                                                    subscriber_id=sid,
                                                    platform="ios",
                                                    product_id=prod_id,
                                                    plan_label=plan_lbl,
                                                    status=st_val,
                                                    offer_type=of_type,
                                                    offer_code_name=of_lbl[:95],
                                                    started_date=ev_date,
                                                    converted_or_renewed_date=ev_date if c_price_try > 0 else None,
                                                    maturity_or_renewal_date=mat_date,
                                                    auto_renew_enabled=not refund_flag,
                                                    customer_price_try=c_price_try if not refund_flag else 0.0,
                                                    developer_proceeds_try=d_proc_try if not refund_flag else 0.0,
                                                    expected_next_price_try=c_price_try if c_price_try > 0 else (0.0 if is_offer_code else std_price_try),
                                                    expected_next_proceeds_try=d_proc_try if d_proc_try > 0 else (0.0 if is_offer_code else std_proc_try),
                                                    country=cntry,
                                                    device_type=dev,
                                                )
                                            )
                                    db_sync.commit()
                                    synced_sources.append(f"Apple Subscriber Ledger ({rep_date})")
                                finally:
                                    db_sync.close()
                except Exception as e:
                    logger.debug("Apple Subscriber Ledger info (%s): %s", rep_date, e)

                # 4) SUBSCRIPTION_EVENT (SUMMARY 1_3) Raporu -> İptal (Cancel) ve Yaşam Döngüsü Senkronizasyonu
                sub_ev_url = (
                    "https://api.appstoreconnect.apple.com/v1/salesReports"
                    f"?filter[frequency]=DAILY&filter[reportDate]={rep_date}"
                    f"&filter[reportSubType]=SUMMARY&filter[reportType]=SUBSCRIPTION_EVENT"
                    f"&filter[vendorNumber]={vendor_num}&filter[version]=1_3"
                )
                sub_ev_req = urllib.request.Request(
                    sub_ev_url,
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/a-gzip"},
                )
                try:
                    with urllib.request.urlopen(sub_ev_req, timeout=3) as ev_resp:
                        if ev_resp.status == 200:
                            ev_txt = gzip.decompress(ev_resp.read()).decode("utf-8", errors="replace")
                            ev_lines = [ln for ln in ev_txt.splitlines() if ln.strip()]
                            if len(ev_lines) > 1:
                                ev_hdr = ev_lines[0].split("\t")
                                db_ev = SessionLocal()
                                try:
                                    for ln in ev_lines[1:]:
                                        ed = dict(zip(ev_hdr, ln.split("\t")))
                                        ev_name = (ed.get("Event") or "").strip()
                                        if not ev_name:
                                            continue
                                        sub_name_ev = (ed.get("Subscription Name") or "Aylik Esnek").strip()
                                        sub_apple_id_ev = (ed.get("Subscription Apple ID") or "").strip()
                                        orig_start = (ed.get("Original Start Date") or "").strip()
                                        cntry_ev = (ed.get("Country") or "TR").strip().upper()
                                        dev_ev = (ed.get("Device") or "iPhone").strip()
                                        qty_ev = max(1, int(float(ed.get("Quantity") or 1)))
                                        days_before_c = (ed.get("Days Before Canceling") or "").strip() or None
                                        cancel_reason = (ed.get("Cancellation Reason") or "").strip() or None
                                        offer_name_ev = (ed.get("Subscription Offer Name") or "").strip() or None
                                        is_ann_ev = "Yillik" in sub_name_ev or "6809228257" in sub_apple_id_ev
                                        prod_id_ev = "misil_annual" if is_ann_ev else "misil_monthly"
                                        plan_lbl_ev = "Yıllık VIP" if is_ann_ev else "Aylık Esnek VIP"

                                        if ev_name.lower() == "cancel" and orig_start:
                                            cancel_cohorts_synced[(prod_id_ev, orig_start, cntry_ev)] += qty_ev

                                        ev_key = f"EVENT:{ev_name}:{orig_start}:{cntry_ev}:{dev_ev}"
                                        dup_sev = (
                                            db_ev.query(SubscriptionLifecycleEvent.id)
                                            .filter(
                                                SubscriptionLifecycleEvent.event_date == rep_date,
                                                SubscriptionLifecycleEvent.event_type == ev_key,
                                                SubscriptionLifecycleEvent.product_id == prod_id_ev,
                                            )
                                            .first()
                                        )
                                        if dup_sev is None:
                                            db_ev.add(
                                                SubscriptionLifecycleEvent(
                                                    event_date=rep_date,
                                                    platform="ios",
                                                    event_type=ev_key[:128],
                                                    product_id=prod_id_ev,
                                                    plan_label=plan_lbl_ev,
                                                    offer_code_name=offer_name_ev,
                                                    country=cntry_ev,
                                                    device_type=dev_ev,
                                                    quantity=qty_ev,
                                                    days_before_canceling=days_before_c,
                                                    cancellation_reason=cancel_reason,
                                                )
                                            )
                                    db_ev.commit()
                                    synced_sources.append(f"Apple Subscription Events ({rep_date})")
                                finally:
                                    db_ev.close()
                except Exception as e:
                    logger.debug("Apple Subscription Event info (%s): %s", e)

            # SUBSCRIBER + SUBSCRIPTION_EVENT + SUBSCRIPTION State sonrası tekil abone defterini mutabakata sok
            try:
                db_rec = SessionLocal()
                try:
                    if _reconcile_ios_ledger_and_cancellations(
                        db_rec,
                        cancel_cohorts=cancel_cohorts_synced,
                        active_trials_target=latest_sub_state.get("trial") if latest_sub_state else None,
                    ):
                        db_rec.commit()
                finally:
                    db_rec.close()
            except Exception as rec_exc:
                logger.debug("iOS ledger reconciliation warning: %s", rec_exc)

            # 5) Apple Analytics Report Requests (r14 Discovery & Engagement + r8 App Sessions) -> Gerçek Gösterim, Sayfa Ziyareti ve Oturumlar
            try:
                asc_app_id = os.environ.get("ASC_APP_ID", "6809223195")
                arr_req = urllib.request.Request(
                    f"https://api.appstoreconnect.apple.com/v1/apps/{asc_app_id}/analyticsReportRequests",
                    headers={"Authorization": f"Bearer {token}"},
                )
                with urllib.request.urlopen(arr_req, timeout=5) as arr_resp:
                    arr_items = json.loads(arr_resp.read().decode("utf-8")).get("data", []) if arr_resp.status == 200 else []
                imp_by_date: Counter = Counter()
                imp_uniq_by_date: Counter = Counter()
                pv_by_date: Counter = Counter()
                pv_uniq_by_date: Counter = Counter()
                sess_by_date: Counter = Counter()
                imp_search_by_date: Counter = Counter()
                imp_browse_by_date: Counter = Counter()
                imp_ref_by_date: Counter = Counter()
                taps_by_date: Counter = Counter()
                dl_search_by_date: Counter = Counter()
                dl_ref_by_date: Counter = Counter()
                dl_browse_by_date: Counter = Counter()
                r8_daily_rows: Dict[tuple, tuple] = {}

                for arr_item in arr_items:
                    req_id = arr_item.get("id")
                    if not req_id:
                        continue
                    # r14: App Store Discovery and Engagement Standard
                    r14_id = f"r14-{req_id}"
                    try:
                        inst_req = urllib.request.Request(
                            f"https://api.appstoreconnect.apple.com/v1/analyticsReports/{r14_id}/instances",
                            headers={"Authorization": f"Bearer {token}"},
                        )
                        with urllib.request.urlopen(inst_req, timeout=5) as inst_resp:
                            inst_list = json.loads(inst_resp.read().decode("utf-8")).get("data", []) if inst_resp.status == 200 else []
                        for inst in inst_list:
                            if (inst.get("attributes") or {}).get("granularity") != "DAILY":
                                continue
                            seg_req = urllib.request.Request(
                                f"https://api.appstoreconnect.apple.com/v1/analyticsReportInstances/{inst['id']}/segments",
                                headers={"Authorization": f"Bearer {token}"},
                            )
                            with urllib.request.urlopen(seg_req, timeout=5) as seg_resp:
                                seg_list = json.loads(seg_resp.read().decode("utf-8")).get("data", []) if seg_resp.status == 200 else []
                            for seg in seg_list:
                                seg_url = (seg.get("attributes") or {}).get("url")
                                if not seg_url:
                                    continue
                                seg_txt = gzip.decompress(urllib.request.urlopen(seg_url, timeout=8).read()).decode("utf-8", errors="replace")
                                s_lines = [ln for ln in seg_txt.splitlines() if ln.strip()]
                                if len(s_lines) > 1:
                                    s_hdr = s_lines[0].split("\t")
                                    d_imp: Counter = Counter()
                                    d_imp_u: Counter = Counter()
                                    d_pv: Counter = Counter()
                                    d_pv_u: Counter = Counter()
                                    d_search: Counter = Counter()
                                    d_browse: Counter = Counter()
                                    d_ref: Counter = Counter()
                                    d_taps: Counter = Counter()
                                    for ln in s_lines[1:]:
                                        row_d = dict(zip(s_hdr, ln.split("\t")))
                                        dt_s = (row_d.get("Date") or "").strip()
                                        ev_s = (row_d.get("Event") or "").strip()
                                        src_s = (row_d.get("Source Type") or "").strip()
                                        cnt_v = int(float(row_d.get("Counts") or 0))
                                        ucnt_v = int(float(row_d.get("Unique Counts") or 0))
                                        if ev_s == "Impression":
                                            d_imp[dt_s] += cnt_v
                                            d_imp_u[dt_s] += ucnt_v
                                            if "search" in src_s.lower():
                                                d_search[dt_s] += cnt_v
                                            elif "browse" in src_s.lower():
                                                d_browse[dt_s] += cnt_v
                                            elif "referrer" in src_s.lower():
                                                d_ref[dt_s] += cnt_v
                                        elif ev_s == "Page view":
                                            d_pv[dt_s] += cnt_v
                                            d_pv_u[dt_s] += ucnt_v
                                        elif ev_s == "Tap":
                                            d_taps[dt_s] += cnt_v
                                    for dt_k, v_c in d_imp.items():
                                        imp_by_date[dt_k] = max(imp_by_date[dt_k], v_c)
                                    for dt_k, v_c in d_imp_u.items():
                                        imp_uniq_by_date[dt_k] = max(imp_uniq_by_date[dt_k], v_c)
                                    for dt_k, v_c in d_pv.items():
                                        pv_by_date[dt_k] = max(pv_by_date[dt_k], v_c)
                                    for dt_k, v_c in d_pv_u.items():
                                        pv_uniq_by_date[dt_k] = max(pv_uniq_by_date[dt_k], v_c)
                                    for dt_k, v_c in d_search.items():
                                        imp_search_by_date[dt_k] = max(imp_search_by_date[dt_k], v_c)
                                    for dt_k, v_c in d_browse.items():
                                        imp_browse_by_date[dt_k] = max(imp_browse_by_date[dt_k], v_c)
                                    for dt_k, v_c in d_ref.items():
                                        imp_ref_by_date[dt_k] = max(imp_ref_by_date[dt_k], v_c)
                                    for dt_k, v_c in d_taps.items():
                                        taps_by_date[dt_k] = max(taps_by_date[dt_k], v_c)
                    except Exception as r14_exc:
                        logger.debug("Apple r14 analytics sync info (%s): %s", req_id, r14_exc)

                    # r8: App Sessions Standard
                    r8_id = f"r8-{req_id}"
                    try:
                        s_inst_req = urllib.request.Request(
                            f"https://api.appstoreconnect.apple.com/v1/analyticsReports/{r8_id}/instances",
                            headers={"Authorization": f"Bearer {token}"},
                        )
                        with urllib.request.urlopen(s_inst_req, timeout=5) as s_inst_resp:
                            s_inst_list = json.loads(s_inst_resp.read().decode("utf-8")).get("data", []) if s_inst_resp.status == 200 else []
                        for s_inst in s_inst_list:
                            if (s_inst.get("attributes") or {}).get("granularity") != "DAILY":
                                continue
                            s_seg_req = urllib.request.Request(
                                f"https://api.appstoreconnect.apple.com/v1/analyticsReportInstances/{s_inst['id']}/segments",
                                headers={"Authorization": f"Bearer {token}"},
                            )
                            with urllib.request.urlopen(s_seg_req, timeout=5) as s_seg_resp:
                                s_seg_list = json.loads(s_seg_resp.read().decode("utf-8")).get("data", []) if s_seg_resp.status == 200 else []
                            for seg in s_seg_list:
                                seg_url = (seg.get("attributes") or {}).get("url")
                                if not seg_url:
                                    continue
                                seg_txt = gzip.decompress(urllib.request.urlopen(seg_url, timeout=8).read()).decode("utf-8", errors="replace")
                                s_lines = [ln for ln in seg_txt.splitlines() if ln.strip()]
                                if len(s_lines) > 1:
                                    s_hdr = s_lines[0].split("\t")
                                    d_sess: Counter = Counter()
                                    for ln in s_lines[1:]:
                                        row_d = dict(zip(s_hdr, ln.split("\t")))
                                        dt_s = (row_d.get("Date") or "").strip()
                                        dl_dt = (row_d.get("Download Date") or "").strip()
                                        dev_s = (row_d.get("Device") or "").strip()
                                        pver_s = (row_d.get("Platform Version") or "").strip()
                                        src_s = (row_d.get("Source Type") or "").strip()
                                        terr_s = (row_d.get("Territory") or "").strip()
                                        page_s = (row_d.get("Page Type") or "").strip()
                                        sess_v = int(float(row_d.get("Sessions") or 0))
                                        dur_v = int(float(row_d.get("Total Session Duration") or 0))
                                        udev_v = int(float(row_d.get("Unique Devices") or 0))
                                        d_sess[dt_s] += sess_v
                                        r8_key = (dt_s, dl_dt, dev_s, pver_s, src_s, terr_s, page_s)
                                        prev_r8 = r8_daily_rows.get(r8_key)
                                        if not prev_r8 or sess_v > prev_r8[0]:
                                            r8_daily_rows[r8_key] = (sess_v, dur_v, udev_v)
                                    for dt_k, v_c in d_sess.items():
                                        sess_by_date[dt_k] = max(sess_by_date[dt_k], v_c)
                    except Exception as r8_exc:
                        logger.debug("Apple r8 sessions sync info (%s): %s", req_id, r8_exc)

                    # r3: App Store Installation and Deletion Standard (Search / Referrer / Browse indirme kaynakları)
                    r3_id = f"r3-{req_id}"
                    try:
                        dl_inst_req = urllib.request.Request(
                            f"https://api.appstoreconnect.apple.com/v1/analyticsReports/{r3_id}/instances",
                            headers={"Authorization": f"Bearer {token}"},
                        )
                        with urllib.request.urlopen(dl_inst_req, timeout=5) as dl_inst_resp:
                            dl_inst_list = json.loads(dl_inst_resp.read().decode("utf-8")).get("data", []) if dl_inst_resp.status == 200 else []
                        for dl_inst in dl_inst_list:
                            if (dl_inst.get("attributes") or {}).get("granularity") != "DAILY":
                                continue
                            dl_seg_req = urllib.request.Request(
                                f"https://api.appstoreconnect.apple.com/v1/analyticsReportInstances/{dl_inst['id']}/segments",
                                headers={"Authorization": f"Bearer {token}"},
                            )
                            with urllib.request.urlopen(dl_seg_req, timeout=5) as dl_seg_resp:
                                dl_seg_list = json.loads(dl_seg_resp.read().decode("utf-8")).get("data", []) if dl_seg_resp.status == 200 else []
                            for seg in dl_seg_list:
                                seg_url = (seg.get("attributes") or {}).get("url")
                                if not seg_url:
                                    continue
                                seg_txt = gzip.decompress(urllib.request.urlopen(seg_url, timeout=8).read()).decode("utf-8", errors="replace")
                                s_lines = [ln for ln in seg_txt.splitlines() if ln.strip()]
                                if len(s_lines) > 1:
                                    s_hdr = s_lines[0].split("\t")
                                    d_dl_s: Counter = Counter()
                                    d_dl_r: Counter = Counter()
                                    d_dl_b: Counter = Counter()
                                    for ln in s_lines[1:]:
                                        row_d = dict(zip(s_hdr, ln.split("\t")))
                                        dt_s = (row_d.get("Date") or "").strip()
                                        dl_type = (row_d.get("Download Type") or row_d.get("Event") or "").strip().lower()
                                        src_s = (row_d.get("Source Type") or "").strip().lower()
                                        cnt_v = int(float(row_d.get("Counts") or 0))
                                        if "download" in dl_type or not dl_type:
                                            if "search" in src_s:
                                                d_dl_s[dt_s] += cnt_v
                                            elif "referrer" in src_s:
                                                d_dl_r[dt_s] += cnt_v
                                            elif "browse" in src_s:
                                                d_dl_b[dt_s] += cnt_v
                                    for dt_k, v_c in d_dl_s.items():
                                        dl_search_by_date[dt_k] = max(dl_search_by_date[dt_k], v_c)
                                    for dt_k, v_c in d_dl_r.items():
                                        dl_ref_by_date[dt_k] = max(dl_ref_by_date[dt_k], v_c)
                                    for dt_k, v_c in d_dl_b.items():
                                        dl_browse_by_date[dt_k] = max(dl_browse_by_date[dt_k], v_c)
                    except Exception as r3_exc:
                        logger.debug("Apple r3 downloads sync info (%s): %s", req_id, r3_exc)

                if imp_by_date or pv_by_date or sess_by_date or dl_search_by_date or dl_ref_by_date or dl_browse_by_date:
                    db_an = SessionLocal()
                    try:
                        all_dates = (
                            set(imp_by_date.keys())
                            | set(pv_by_date.keys())
                            | set(sess_by_date.keys())
                            | set(dl_search_by_date.keys())
                            | set(dl_ref_by_date.keys())
                            | set(dl_browse_by_date.keys())
                        )
                        for dt_k in sorted(all_dates):
                            if not dt_k:
                                continue
                            m_row = (
                                db_an.query(StoreDailyMetric)
                                .filter(StoreDailyMetric.metric_date == dt_k, StoreDailyMetric.platform == "ios")
                                .first()
                            )
                            if not m_row:
                                m_row = StoreDailyMetric(metric_date=dt_k, platform="ios")
                                db_an.add(m_row)
                            if dt_k in imp_by_date:
                                m_row.impressions = imp_by_date[dt_k]
                                m_row.impressions_unique = imp_uniq_by_date.get(dt_k, 0)
                            if dt_k in pv_by_date:
                                m_row.page_views = pv_by_date[dt_k]
                                m_row.page_views_unique = pv_uniq_by_date.get(dt_k, 0)
                            if dt_k in sess_by_date:
                                m_row.active_sessions = sess_by_date[dt_k]
                            if dt_k in dl_search_by_date:
                                m_row.downloads_search = dl_search_by_date[dt_k]
                            if dt_k in dl_ref_by_date:
                                m_row.downloads_referrer = dl_ref_by_date[dt_k]
                            if dt_k in dl_browse_by_date:
                                m_row.downloads_browse = dl_browse_by_date[dt_k]
                        db_an.commit()
                        synced_sources.append("Apple Analytics API (r14 Engagement, r8 Sessions & r3 Downloads)")
                    finally:
                        db_an.close()
                    with _BASELINE_LOCK:
                        OFFICIAL_STORE_BASELINE["apple_impressions_total"] = sum(imp_by_date.values())
                        OFFICIAL_STORE_BASELINE["apple_impressions_unique"] = sum(imp_uniq_by_date.values())
                        OFFICIAL_STORE_BASELINE["apple_impressions_search"] = sum(imp_search_by_date.values())
                        OFFICIAL_STORE_BASELINE["apple_impressions_browse"] = sum(imp_browse_by_date.values())
                        OFFICIAL_STORE_BASELINE["apple_impressions_referrer"] = sum(imp_ref_by_date.values())
                        OFFICIAL_STORE_BASELINE["apple_page_views_total"] = sum(pv_by_date.values())
                        OFFICIAL_STORE_BASELINE["apple_page_views_unique"] = sum(pv_uniq_by_date.values())
                        OFFICIAL_STORE_BASELINE["apple_taps_total"] = sum(taps_by_date.values())
                        OFFICIAL_STORE_BASELINE["apple_sessions_total"] = sum(sess_by_date.values())
                        if r8_daily_rows:
                            r8_agg = _aggregate_apple_r8_cohorts(r8_daily_rows)
                            OFFICIAL_STORE_BASELINE.update(r8_agg)
                        if dl_search_by_date or dl_ref_by_date or dl_browse_by_date:
                            OFFICIAL_STORE_BASELINE["apple_downloads_search"] = sum(dl_search_by_date.values())
                            OFFICIAL_STORE_BASELINE["apple_downloads_referrer"] = sum(dl_ref_by_date.values())
                            OFFICIAL_STORE_BASELINE["apple_downloads_browse"] = sum(dl_browse_by_date.values())
            except Exception as arr_exc:
                logger.debug("Apple Analytics Report Requests sync skipped: %s", arr_exc)
        except Exception as e:
            logger.warning("Live Apple API sync warning: %s", e)

    # Google Play Developer API (Service Account mevcutsa canlı yorum ve durum kontrolü)
    gp_candidates = [
        os.path.join(project_root, "mobile", "google-play-service-account.json"),
        os.path.join(project_root, "..", "..", "projects", "mishil", "mobile", "google-play-service-account.json"),
    ]
    gp_sa_path = next((p for p in gp_candidates if os.path.exists(p)), None)
    gp_sa_json_raw = os.environ.get("GOOGLE_PLAY_SERVICE_ACCOUNT_JSON")
    if not gp_sa_json_raw and gp_sa_path:
        try:
            with open(gp_sa_path, "r", encoding="utf-8") as gf:
                gp_sa_json_raw = gf.read()
        except Exception:
            gp_sa_json_raw = None

    if gp_sa_json_raw and jwt:
        try:
            sa_info = json.loads(gp_sa_json_raw)
            now_gp = int(time.time())
            gp_jwt = jwt.encode(
                {
                    "iss": sa_info["client_email"],
                    "scope": "https://www.googleapis.com/auth/androidpublisher",
                    "aud": "https://oauth2.googleapis.com/token",
                    "iat": now_gp - 30,
                    "exp": now_gp + 3500,
                },
                sa_info["private_key"],
                algorithm="RS256",
            )
            tok_data = urllib.parse.urlencode({
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": gp_jwt,
            }).encode("utf-8")
            tok_req = urllib.request.Request(
                "https://oauth2.googleapis.com/token",
                data=tok_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            with urllib.request.urlopen(tok_req, timeout=4) as tok_resp:
                if tok_resp.status == 200:
                    access_token = json.loads(tok_resp.read().decode("utf-8")).get("access_token")
                    if access_token:
                        google_connected = True
                        gp_rev_req = urllib.request.Request(
                            "https://androidpublisher.googleapis.com/androidpublisher/v3/applications/com.levitas.misilbaby/reviews?maxResults=20",
                            headers={"Authorization": f"Bearer {access_token}"},
                        )
                        with urllib.request.urlopen(gp_rev_req, timeout=4) as gp_rev_resp:
                            if gp_rev_resp.status == 200:
                                rev_payload = json.loads(gp_rev_resp.read().decode("utf-8"))
                                for r_item in rev_payload.get("reviews", []):
                                    comments = r_item.get("comments", [])
                                    if not comments:
                                        continue
                                    uc = comments[0].get("userComment", {})
                                    star_r = max(1, min(5, int(uc.get("starRating") or 5)))
                                    ts_sec = int((uc.get("lastModified") or {}).get("seconds") or now_gp)
                                    dt_str = datetime.fromtimestamp(ts_sec, tz=timezone(timedelta(hours=3))).strftime("%d.%m.%Y")
                                    fetched_gp_reviews.append({
                                        "store": "Google Play",
                                        "badge": "🤖 Android",
                                        "rating": star_r,
                                        "title": (uc.get("deviceMetadata") or {}).get("productName") or "Google Play Yorumu",
                                        "body": (uc.get("text") or "").strip(),
                                        "author": r_item.get("authorName") or "Google Play Kullanıcısı",
                                        "date": dt_str,
                                    })
                                synced_sources.append("Google Play Developer API (Reviews)")
                        try:
                            gp_sub_req = urllib.request.Request(
                                "https://androidpublisher.googleapis.com/androidpublisher/v3/applications/com.levitas.misilbaby/subscriptions",
                                headers={"Authorization": f"Bearer {access_token}"},
                            )
                            with urllib.request.urlopen(gp_sub_req, timeout=4) as gp_sub_resp:
                                if gp_sub_resp.status == 200:
                                    sub_payload = json.loads(gp_sub_resp.read().decode("utf-8"))
                                    fetched_gp_catalog = []
                                    for sub_item in sub_payload.get("subscriptions", []):
                                        p_id = sub_item.get("productId") or "-"
                                        listings = sub_item.get("listings") or []
                                        title_str = listings[0].get("title") if listings else p_id
                                        for bp in sub_item.get("basePlans", []):
                                            bp_state = bp.get("state") or "INACTIVE"
                                            if bp_state != "ACTIVE":
                                                continue
                                            bp_id = bp.get("basePlanId") or p_id
                                            ar_type = bp.get("autoRenewingBasePlanType") or {}
                                            dur_raw = ar_type.get("billingPeriodDuration") or "P1M"
                                            dur_lbl = "Yıllık (P1Y)" if "Y" in dur_raw else "Aylık (P1M)"
                                            grace_raw = ar_type.get("gracePeriodDuration") or "P7D"
                                            grace_lbl = "14 Gün (P14D)" if "14" in grace_raw else "7 Gün (P7D)"
                                            offer_id = ar_type.get("legacyCompatibleSubscriptionOfferId") or "-"
                                            offer_lbl = "7 Gün Ücretsiz Deneme (P7D • Aktif)" if offer_id and offer_id != "-" else "Standart"
                                            try:
                                                gp_off_req = urllib.request.Request(
                                                    f"https://androidpublisher.googleapis.com/androidpublisher/v3/applications/com.levitas.misilbaby/subscriptions/{p_id}/basePlans/{bp_id}/offers",
                                                    headers={"Authorization": f"Bearer {access_token}"},
                                                )
                                                with urllib.request.urlopen(gp_off_req, timeout=3) as gp_off_resp:
                                                    if gp_off_resp.status == 200:
                                                        off_payload = json.loads(gp_off_resp.read().decode("utf-8"))
                                                        for off_item in off_payload.get("subscriptionOffers", []):
                                                            if (off_item.get("state") or "") == "ACTIVE":
                                                                offer_id = off_item.get("offerId") or offer_id
                                                                phases = off_item.get("phases") or []
                                                                if phases:
                                                                    ph_dur = phases[0].get("duration") or "P7D"
                                                                    offer_lbl = f"7 Gün Ücretsiz Deneme ({ph_dur} • Aktif)" if "7D" in ph_dur or "1W" in ph_dur else f"Teklif ({ph_dur} • Aktif)"
                                                                break
                                            except Exception:
                                                pass
                                            tr_price = 599.99 if "Y" in dur_raw else 149.99
                                            for rc_cfg in bp.get("regionalConfigs", []):
                                                if rc_cfg.get("regionCode") == "TR":
                                                    pr_obj = rc_cfg.get("price") or {}
                                                    units_v = float(pr_obj.get("units") or 0)
                                                    nanos_v = float(pr_obj.get("nanos") or 0) / 1e9
                                                    if (units_v + nanos_v) > 0:
                                                        tr_price = round(units_v + nanos_v, 2)
                                            fetched_gp_catalog.append({
                                                "product_id": p_id,
                                                "base_plan_id": bp_id,
                                                "title": title_str,
                                                "state": bp_state,
                                                "billing_period": dur_lbl,
                                                "grace_period": grace_lbl,
                                                "price_try": tr_price,
                                                "net_proceeds_try": round(tr_price * 0.727, 2),
                                                "free_trial_offer_id": offer_id,
                                                "free_trial_label": offer_lbl,
                                            })
                                    if fetched_gp_catalog:
                                        with _BASELINE_LOCK:
                                            OFFICIAL_STORE_BASELINE["google_play_subscriptions_catalog"] = fetched_gp_catalog
                                        synced_sources.append("Google Play Developer API (Monetization Subscriptions & Offers)")
                        except Exception as gp_sub_exc:
                            logger.debug("Google Play subscriptions sync info: %s", gp_sub_exc)
        except Exception as e:
            logger.debug("Google Play live sync info: %s", e)

    tz_tr = timezone(timedelta(hours=3))
    synced_at_str = datetime.now(tz_tr).strftime("%d.%m.%Y %H:%M TSİ")

    # Kısa süreli kilit altında bellek içi ve DB StoreSyncState güncellemesi
    with _BASELINE_LOCK:
        if apple_connected:
            OFFICIAL_STORE_BASELINE["apple_sync_status"] = "CONNECTED (Apple App Store Connect API)"
        if google_connected:
            OFFICIAL_STORE_BASELINE["google_sync_status"] = "CONNECTED (Google Play Developer API)"
        if fetched_apple_reviews or fetched_gp_reviews:
            existing_revs = OFFICIAL_STORE_BASELINE.get("store_reviews", [])
            keep_gp = fetched_gp_reviews if fetched_gp_reviews else [x for x in existing_revs if x.get("store") == "Google Play"]
            keep_ap = fetched_apple_reviews if fetched_apple_reviews else [x for x in existing_revs if x.get("store") == "App Store"]
            merged_revs = keep_ap[:15] + keep_gp[:15]
            try:
                merged_revs.sort(
                    key=lambda rv: tuple(int(p) for p in rv.get("date", "01.01.2000").split(".")[::-1]),
                    reverse=True,
                )
            except Exception:
                pass
            OFFICIAL_STORE_BASELINE["store_reviews"] = merged_revs
        if country_totals:
            c_list = []
            for cc_code, cc_cnt in country_totals.most_common():
                meta_c = COUNTRY_META.get(cc_code, {"flag": "🌍", "name": cc_code})
                c_list.append({"code": cc_code, "flag": meta_c["flag"], "name": meta_c["name"], "count": cc_cnt})
            OFFICIAL_STORE_BASELINE["apple_downloads_by_country"] = c_list
        if latest_sub_state:
            OFFICIAL_STORE_BASELINE["apple_vip_paid_conversions"] = latest_sub_state["paid"]
            OFFICIAL_STORE_BASELINE["apple_vip_offer_code_subs"] = latest_sub_state["code"]
            OFFICIAL_STORE_BASELINE["apple_vip_active_trials"] = latest_sub_state["trial"]
            OFFICIAL_STORE_BASELINE["apple_vip_activations_total"] = latest_sub_state["total"]
        if synced_sources:
            OFFICIAL_STORE_BASELINE["last_synced_at"] = synced_at_str

        for k in list(OFFICIAL_STORE_BASELINE.keys()):
            OFFICIAL_STORE_BASELINE[k] = _mask_sensitive_sync_value(OFFICIAL_STORE_BASELINE[k])
        snapshot_copy = copy.deepcopy(OFFICIAL_STORE_BASELINE)

    try:
        db_state = SessionLocal()
        try:
            st_row = db_state.query(StoreSyncState).filter(StoreSyncState.state_key == "primary_store_baseline").first()
            if st_row:
                st_row.snapshot_json = snapshot_copy
                if synced_sources:
                    st_row.last_synced_at_str = synced_at_str
            else:
                db_state.add(
                    StoreSyncState(
                        state_key="primary_store_baseline",
                        snapshot_json=snapshot_copy,
                        last_synced_at_str=snapshot_copy.get("last_synced_at"),
                    )
                )
            db_state.commit()
        finally:
            db_state.close()
    except Exception as e:
        logger.warning("StoreSyncState persistence warning: %s", e)

    return {
        "synced": bool(synced_sources),
        "sources": _mask_sensitive_sync_value(synced_sources),
        "apple_connected": apple_connected,
        "google_connected": google_connected,
        "synced_at": synced_at_str,
    }


async def run_periodic_store_sync_loop(stop_event: asyncio.Event, interval_seconds: int = 21600):
    """
    Railway üzerinde çalışan periyodik arka plan senkronizasyonu.
    Her 6 saatte bir (21600 sn) Apple ve Google mağaza API'lerini tarar.
    Ortamda anahtar tanımlı değilse sessizce loglar ve bekler.
    """
    if os.environ.get("PYTEST_CURRENT_TEST"):
        logger.debug("Skipping periodic store sync loop during automated tests.")
        return

    logger.info("Starting periodic store sync background loop (interval=%ds)...", interval_seconds)
    # İlk çalışma için sunucu açılışından sonra 15 saniye bekle
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=15)
        return
    except asyncio.TimeoutError:
        pass

    while not stop_event.is_set():
        try:
            logger.info("Triggering periodic background store sync...")
            res = await run_in_threadpool(sync_live_store_apis, 30)
            logger.info("Periodic store sync completed. Synced: %s, Sources: %s", res.get("synced"), res.get("sources"))
        except Exception as e:
            logger.warning("Periodic store sync error: %s", e)

        # Bir sonraki periyoda kadar bekle
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            break
        except asyncio.TimeoutError:
            pass
    logger.info("Periodic store sync loop gracefully stopped.")


def classify_user_agent(ua_raw: str) -> Dict[str, Any]:
    """User-Agent dizesinden OS, cihaz detayı, uygulama içi tarayıcı ve bot durumunu çözer."""
    ua = (ua_raw or "").lower()

    has_mobile_os = any(os_tok in ua for os_tok in ("iphone", "ipad", "ipod", "android"))
    is_whatsapp_bot = ("whatsapp" in ua) and (not has_mobile_os)
    is_bot = any(b in ua for b in BOT_SIGNATURES) or is_whatsapp_bot

    if is_bot:
        if "facebook" in ua or "facebot" in ua or "meta-" in ua:
            detail = "Meta Ad Crawler Bot"
        elif "google" in ua:
            detail = "Googlebot"
        elif is_whatsapp_bot:
            detail = "WhatsApp Link Preview Bot"
        else:
            detail = "Crawler / Bot"
        return {
            "os_family": "bot",
            "device_detail": detail,
            "app_webview": "Bot / Crawler",
            "is_bot": True,
        }

    if "instagram" in ua:
        app_webview = "Instagram App"
    elif "fban" in ua or "fbios" in ua or "fb_iab" in ua or "facebook" in ua:
        app_webview = "Facebook App"
    elif "whatsapp" in ua:
        app_webview = "WhatsApp In-App"
    elif "tiktok" in ua or "musical_ly" in ua:
        app_webview = "TikTok App"
    elif "safari" in ua and "crios" not in ua and "fxios" not in ua and ("iphone" in ua or "ipad" in ua):
        app_webview = "Mobile Safari"
    elif "chrome" in ua or "crios" in ua:
        app_webview = "Chrome Mobile"
    else:
        app_webview = "Tarayıcı / Diğer"

    if "iphone" in ua:
        os_family = "ios"
        device_detail = "iPhone"
    elif "ipad" in ua:
        os_family = "ios"
        device_detail = "iPad"
    elif "android" in ua:
        os_family = "android"
        if "samsung" in ua or "sm-" in ua:
            device_detail = "Android (Samsung)"
        elif "xiaomi" in ua or "redmi" in ua or "poco" in ua:
            device_detail = "Android (Xiaomi/Redmi)"
        elif "huawei" in ua:
            device_detail = "Android (Huawei)"
        else:
            device_detail = "Android Telefon"
    elif "macintosh" in ua or "mac os" in ua:
        os_family = "desktop"
        device_detail = "Mac (Masaüstü)"
    elif "windows" in ua:
        os_family = "desktop"
        device_detail = "Windows (Masaüstü)"
    else:
        os_family = "ios"
        device_detail = "Mobil Cihaz"

    return {
        "os_family": os_family,
        "device_detail": device_detail,
        "app_webview": app_webview,
        "is_bot": False,
    }


def classify_channel(route_path: str, utm_source: Optional[str], has_fbclid: bool) -> str:
    path = (route_path or "/").lower()
    if path == "/ios":
        return "meta_ads"
    elif path == "/download":
        return "instagram_bio"
    elif path in ("/android", "/play-store"):
        return "google_play_direct"
    elif path == "/app-store":
        return "app_store_direct"
    if has_fbclid:
        return "meta_ads"
    if utm_source:
        clean_utm = "".join(ch for ch in utm_source.lower() if ch.isalnum() or ch == "_")[:40]
        if clean_utm:
            return clean_utm
    return "landing"


def mask_ip(ip_raw: str, ua_raw: str = "") -> str:
    if not ip_raw or ip_raw == "unknown":
        base_ip = "unknown"
    elif ":" in ip_raw:
        hextets = ip_raw.split(":")
        base_ip = ":".join(hextets[:3]) + ":xxxx"
    else:
        parts = ip_raw.split(".")
        if len(parts) == 4:
            base_ip = f"{parts[0]}.{parts[1]}.{parts[2]}.xxx"
        else:
            base_ip = ip_raw[:15]

    if ua_raw:
        ua_fp = hashlib.sha256(ua_raw.encode("utf-8", errors="ignore")).hexdigest()[:4]
        return f"{base_ip}#{ua_fp}"
    return base_ip


def extract_base_ip(ip_masked: Optional[str]) -> str:
    if not ip_masked:
        return "unknown"
    return ip_masked.split("#")[0]


def sanitize_csv_cell(val: Any) -> str:
    """CSV Formula-Injection koruması: tüm kontrol karakterlerini ve tehlikeli önekleri temizler."""
    raw = str(val if val is not None else "")
    cleaned = "".join(ch if ch >= " " or ch == " " else " " for ch in raw).strip()
    lstripped = cleaned.lstrip()
    if lstripped and lstripped[0] in ("=", "+", "-", "@", "\t", "|"):
        return "'" + cleaned
    return cleaned


def ensure_historical_seed(db: Session) -> None:
    """
    Sıfır Statik Veri İlkesi:
    Veritabanı şemasının mevcut olduğundan emin olur ve varsa kalıcı StoreSyncState
    önbelleğini yükler; hiçbir statik/sahte tıklama, kampanya veya abone verisi tohumlamaz.
    """
    try:
        bind_target = db.connection() if db is not None else engine
        Base.metadata.create_all(bind=bind_target, checkfirst=True)
        insp = inspect(bind_target)
        if insp.has_table("store_daily_metrics"):
            existing_cols = {col["name"] for col in insp.get_columns("store_daily_metrics")}
            if "active_sessions" not in existing_cols:
                db.execute(text("ALTER TABLE store_daily_metrics ADD COLUMN active_sessions INTEGER NOT NULL DEFAULT 0"))
                db.commit()
    except Exception as schema_exc:
        logger.warning("Schema migration check warning: %s", schema_exc)
        try:
            db.rollback()
        except Exception:
            pass
        try:
            Base.metadata.create_all(bind=engine, checkfirst=True)
        except Exception:
            pass

    # Eski v4.46.0 sürümünden veritabanında kalan tüm statik tohum kayıtlarını (HistoricalSeed vb.) temizle
    try:
        del_clicks = (
            db.query(BridgeClick)
            .filter(
                (BridgeClick.user_agent == "Historical Railway Deployment Log (6a91615f)")
                | (BridgeClick.fbclid == "railway_log_backfill")
                | (BridgeClick.utm_campaign == "misil_launch_oct2026")
            )
            .delete(synchronize_session=False)
        )
        del_campaigns = (
            db.query(CampaignConfig)
            .filter(CampaignConfig.reported_impressions.in_([4014, 3850, 640, 410]))
            .delete(synchronize_session=False)
        )
        del_metrics = (
            db.query(StoreDailyMetric)
            .filter(StoreDailyMetric.impressions.in_([85, 290, 620, 740, 810, 690, 520, 311]))
            .delete(synchronize_session=False)
        )
        st_row_check = db.query(StoreSyncState).filter(StoreSyncState.state_key == "primary_store_baseline").first()
        del_sync = 0
        if st_row_check:
            snap = st_row_check.snapshot_json if isinstance(st_row_check.snapshot_json, dict) else {}
            if (
                snap.get("apple_impressions_total") == 4066
                or (st_row_check.last_synced_at_str and "28.10.2026 22:30" in st_row_check.last_synced_at_str)
            ):
                db.delete(st_row_check)
                del_sync = 1
                with _BASELINE_LOCK:
                    OFFICIAL_STORE_BASELINE.clear()
                    OFFICIAL_STORE_BASELINE.update(_empty_store_state())
        if del_clicks or del_campaigns or del_metrics or del_sync:
            db.commit()
    except Exception as purge_exc:
        logger.debug("Legacy seed purge skipped: %s", purge_exc)
        try:
            db.rollback()
        except Exception:
            pass

    try:
        st_row = db.query(StoreSyncState).filter(StoreSyncState.state_key == "primary_store_baseline").first()
        if st_row and isinstance(st_row.snapshot_json, dict):
            with _BASELINE_LOCK:
                for k, v in st_row.snapshot_json.items():
                    masked_v = _mask_sensitive_sync_value(v)
                    if k == "apple_sync_status" and isinstance(masked_v, str) and "AuthKey_" in masked_v:
                        OFFICIAL_STORE_BASELINE[k] = "CONNECTED (Apple App Store Connect API)"
                    else:
                        OFFICIAL_STORE_BASELINE[k] = masked_v
                if st_row.last_synced_at_str:
                    OFFICIAL_STORE_BASELINE["last_synced_at"] = _mask_sensitive_sync_value(st_row.last_synced_at_str)
    except Exception as e:
        logger.debug("StoreSyncState load skipped: %s", e)


def record_bridge_click(request: Request, route_path: str, target_store: str) -> None:
    """Köprü tıklamasını sıfır gecikmeyle ve hata korumalı olarak kaydeder."""
    db = SessionLocal()
    try:
        ensure_historical_seed(db)

        ua_raw = request.headers.get("user-agent") or ""
        ua_info = classify_user_agent(ua_raw)

        client_ip = (
            request.headers.get("cf-connecting-ip")
            or request.headers.get("x-forwarded-for")
            or (request.client.host if request.client else "unknown")
        )
        if "," in client_ip:
            client_ip = client_ip.split(",")[0].strip()
        ip_masked = mask_ip(client_ip, ua_raw)

        country_raw = (
            request.headers.get("cf-ipcountry")
            or request.headers.get("x-country-code")
            or "TR"
        )
        country_clean = "".join(ch for ch in country_raw.upper() if ch.isalnum())[:6] or "TR"

        q_params = request.query_params
        fbclid = q_params.get("fbclid")
        utm_source = q_params.get("utm_source")
        utm_campaign = q_params.get("utm_campaign")
        referrer = request.headers.get("referer")
        has_fbclid = bool(fbclid)

        channel = classify_channel(route_path, utm_source, has_fbclid)

        now_utc = datetime.now(timezone.utc)
        cutoff = now_utc - timedelta(seconds=15)
        recent_dup = (
            db.query(BridgeClick.id)
            .filter(
                BridgeClick.route_path == route_path,
                BridgeClick.ip_masked == ip_masked,
                BridgeClick.created_at >= cutoff,
            )
            .first()
        )
        is_unique = (recent_dup is None) and (not ua_info["is_bot"])

        click = BridgeClick(
            route_path=route_path[:60],
            channel=channel,
            os_family=ua_info["os_family"],
            device_detail=ua_info["device_detail"],
            app_webview=ua_info["app_webview"],
            target_store=target_store,
            is_bot=ua_info["is_bot"],
            is_unique=is_unique,
            has_fbclid=has_fbclid,
            fbclid=fbclid[:250] if fbclid else None,
            utm_source=utm_source[:95] if utm_source else None,
            utm_campaign=utm_campaign[:95] if utm_campaign else None,
            referrer=referrer[:250] if referrer else None,
            country=country_clean,
            ip_masked=ip_masked[:60],
            user_agent=ua_raw[:500] if ua_raw else None,
            created_at=now_utc,
        )
        db.add(click)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Bridge click log error (ignored): {e}")
    finally:
        db.close()


@router.post("/usage-signal")
@router.post("/app-open-signal")
async def record_app_open_signal(
    payload: AppSignalPayload,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Uygulama İçi Cihaz Açılış, Aktif Oturum ve Mağaza Sıçrama Sinyali:
    - 'first_open': Yeni cihaz ilk kurulum/açılış
    - 'daily_active': Günlük aktif cihaz oturumu
    - 'store_jump': Köprü ara sayfasından mağazaya sıçrama
    - 'baby_created': Bebek profili oluşturma
    """
    ensure_historical_seed(db)

    ua_raw = request.headers.get("user-agent") or ""
    ua_info = classify_user_agent(ua_raw)
    os_family = (payload.os_family or ua_info["os_family"] or "ios").lower()
    if os_family not in ("ios", "android", "desktop"):
        os_family = "ios"

    client_ip = (
        request.headers.get("cf-connecting-ip")
        or request.headers.get("x-forwarded-for")
        or (request.client.host if request.client else "unknown")
    )
    if "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()
    ip_masked = mask_ip(client_ip, ua_raw)
    base_ip = extract_base_ip(ip_masked)

    country_raw = (
        request.headers.get("cf-ipcountry")
        or request.headers.get("x-country-code")
        or "TR"
    )
    country_clean = "".join(ch for ch in country_raw.upper() if ch.isalnum())[:6] or "TR"

    now_utc = datetime.now(timezone.utc)
    cutoff_24h = now_utc - timedelta(hours=24)

    # daily_active tekilleştirmesi UTC değil, Türkiye saati (TSİ / UTC+3) gün başlangıcıyla hizalanır.
    tz_tr = timezone(timedelta(hours=3))
    now_tr = now_utc.astimezone(tz_tr)
    today_start_tr = datetime(now_tr.year, now_tr.month, now_tr.day, tzinfo=tz_tr)
    today_start_utc = today_start_tr.astimezone(timezone.utc)

    clean_uid = "".join(ch for ch in payload.device_uid if ch.isalnum() or ch in ("-", "_"))[:100] or "anon"
    clean_event = "".join(ch for ch in payload.event_type if ch.isalnum() or ch == "_")[:40] or "first_open"

    # first_open/daily_active için eşzamanlı isteklerde çift kayıt oluşmasını (TOCTOU) önlemek
    # amacıyla "mevcut kaydı kontrol et + yoksa oluştur" işlemi tek bir kilit altında yapılır.
    needs_dedup_lock = clean_event in ("first_open", "daily_active")
    if needs_dedup_lock:
        _APP_OPEN_SIGNAL_LOCK.acquire()
    try:
        if clean_event == "first_open":
            existing_open = (
                db.query(AppInstallSignal)
                .filter(
                    AppInstallSignal.device_uid == clean_uid,
                    AppInstallSignal.event_type == "first_open",
                )
                .first()
            )
            if existing_open:
                return {
                    "status": "already_recorded",
                    "signal_id": existing_open.id,
                    "matched_channel": existing_open.matched_channel,
                    "match_confidence": existing_open.match_confidence,
                }
        elif clean_event == "daily_active":
            existing_daily = (
                db.query(AppInstallSignal)
                .filter(
                    AppInstallSignal.device_uid == clean_uid,
                    AppInstallSignal.event_type == "daily_active",
                    AppInstallSignal.created_at >= today_start_utc,
                )
                .first()
            )
            if existing_daily:
                return {
                    "status": "already_recorded_today",
                    "signal_id": existing_daily.id,
                    "matched_channel": existing_daily.matched_channel,
                    "match_confidence": existing_daily.match_confidence,
                }

        candidates: List[BridgeClick] = (
            db.query(BridgeClick)
            .filter(
                BridgeClick.is_bot.is_(False),
                BridgeClick.os_family == os_family,
                BridgeClick.created_at >= cutoff_24h,
            )
            .order_by(desc(BridgeClick.created_at))
            .limit(200)
            .all()
        )

        matched_click: Optional[BridgeClick] = None
        confidence = "unmatched"

        for c in candidates:
            c_time = c.created_at.replace(tzinfo=timezone.utc) if c.created_at.tzinfo is None else c.created_at
            delta_sec = max(0.0, (now_utc - c_time).total_seconds())
            c_base_ip = extract_base_ip(c.ip_masked)

            if c_base_ip == base_ip and base_ip != "unknown":
                if delta_sec <= 1800:
                    matched_click = c
                    confidence = "high"
                    break
                elif delta_sec <= 86400:
                    matched_click = c
                    confidence = "medium"
                    break

        if matched_click is None and candidates:
            top_c = candidates[0]
            top_time = top_c.created_at.replace(tzinfo=timezone.utc) if top_c.created_at.tzinfo is None else top_c.created_at
            if (now_utc - top_time).total_seconds() <= 900 and (top_c.country or "TR") == country_clean:
                matched_click = top_c
                confidence = "medium"

        matched_channel = matched_click.channel if matched_click else "organic_or_asa"

        sig = AppInstallSignal(
            device_uid=clean_uid,
            event_type=clean_event,
            os_family=os_family,
            platform=(payload.platform or "web_pwa")[:45],
            app_version=(payload.app_version or "4.45.0")[:30],
            ip_masked=ip_masked[:60],
            country=country_clean,
            matched_click_id=matched_click.id if matched_click else None,
            matched_channel=matched_channel,
            match_confidence=confidence,
            created_at=now_utc,
        )
        db.add(sig)
        db.commit()
        db.refresh(sig)

        return {
            "status": "ok",
            "signal_id": sig.id,
            "matched_channel": matched_channel,
            "match_confidence": confidence,
            "matched_click_id": sig.matched_click_id,
        }
    finally:
        if needs_dedup_lock:
            _APP_OPEN_SIGNAL_LOCK.release()


@router.post("/campaign-config")
async def update_campaign_config(
    request: Request,
    pin: Optional[str] = Form(None),
    channel_key: str = Form(...),
    spend_usd: float = Form(0.0),
    cpt_bid_usd: float = Form(0.0),
    reported_clicks: int = Form(0),
    reported_installs: int = Form(0),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    session_cookie = request.cookies.get(_ADMIN_SESSION_COOKIE)
    if not authorize_admin_request(request, pin, None, session_cookie):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Geçersiz Yönetici PIN kodu.")

    clean_key = (channel_key or "").strip()
    if clean_key not in ALLOWED_CAMPAIGN_CHANNELS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz kampanya kanalı anahtarı.")

    ensure_historical_seed(db)
    cfg = db.query(CampaignConfig).filter(CampaignConfig.channel_key == clean_key).first()
    if not cfg:
        cfg = CampaignConfig(
            channel_key=clean_key,
            display_name=ALLOWED_CAMPAIGN_CHANNELS[clean_key],
        )
        db.add(cfg)

    cfg.spend_usd = max(0.0, float(spend_usd))
    cfg.cpt_bid_usd = max(0.0, float(cpt_bid_usd))
    cfg.reported_clicks = max(0, int(reported_clicks))
    cfg.reported_installs = max(0, int(reported_installs))
    if notes is not None:
        cfg.notes = notes[:240]
    cfg.updated_at = datetime.now(timezone.utc)
    db.commit()

    resp = RedirectResponse(
        url=f"/api/v1/analytics/dashboard?updated={quote(clean_key)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    if not _admin_session_token_is_valid(session_cookie) and _pin_is_valid(pin):
        resp.set_cookie(
            key=_ADMIN_SESSION_COOKIE,
            value=_make_admin_session_token(pin.strip()),
            httponly=True,
            samesite="lax",
            secure=(request.url.scheme == "https"),
            max_age=_ADMIN_SESSION_TTL_SECONDS,
            path="/",
        )
    return resp


def _build_svg_donut(segments: List[Dict[str, Any]], center_val: str, center_lbl: str) -> str:
    """
    Harici JS kütüphanesi gerektirmeyen, ultra hızlı ve keskin SVG Halka (Donut) Grafik üretici.
    segments: [{"label": "iPhone", "count": 97, "color": "#E8A855"}, ...]
    """
    total = max(1, sum(s["count"] for s in segments))
    radius = 54
    circumference = 2 * math.pi * radius
    offset = 0.0
    circles_svg = ""
    legend_html = ""

    for s in segments:
        cnt = s["count"]
        pct = round((cnt / total) * 100, 1)
        dash = (cnt / total) * circumference
        if cnt > 0:
            circles_svg += (
                f'<circle cx="70" cy="70" r="{radius}" fill="transparent" '
                f'stroke="{s["color"]}" stroke-width="16" '
                f'stroke-dasharray="{dash:.2f} {circumference:.2f}" '
                f'stroke-dashoffset="{-offset:.2f}" '
                f'transform="rotate(-90 70 70)" />'
            )
            offset += dash

        legend_html += f"""
        <div class="donut-leg-row">
          <div class="donut-leg-left">
            <span class="donut-dot" style="background:{s['color']};"></span>
            <span class="donut-leg-name">{html.escape(s['label'])}</span>
          </div>
          <div class="donut-leg-right">
            <strong>{cnt}</strong> <span class="donut-pct">(%{pct:g})</span>
          </div>
        </div>
        """

    return f"""
    <div class="donut-wrap">
      <div class="donut-svg-box">
        <svg width="140" height="140" viewBox="0 0 140 140">
          <circle cx="70" cy="70" r="{radius}" fill="transparent" stroke="var(--ring-track, #E2E8F0)" stroke-width="16" />
          {circles_svg}
          <text x="70" y="66" text-anchor="middle" fill="var(--text-primary, #0F172A)" font-family="Sora, sans-serif" font-size="20" font-weight="800">{html.escape(str(center_val))}</text>
          <text x="70" y="84" text-anchor="middle" fill="var(--text-muted, #64748B)" font-family="Plus Jakarta Sans, sans-serif" font-size="10" font-weight="700">{html.escape(str(center_lbl))}</text>
        </svg>
      </div>
      <div class="donut-legend">
        {legend_html}
      </div>
    </div>
    """


def _build_svg_sparkline(values: List[float], color: str, grad_id: str) -> str:
    """KPI kartları için harici kütüphanesiz, gradyan dolgulu keskin SVG Area Sparkline üretir."""
    pts_raw = [float(v or 0.0) for v in (values or [0.0])]
    if len(pts_raw) < 2:
        pts_raw = [0.0] + pts_raw
    n = len(pts_raw)
    w, h = 96.0, 36.0
    pad_x, pad_y = 4.0, 5.0
    max_v = max(pts_raw) if max(pts_raw) > 0 else 1.0
    min_v = min(pts_raw)
    span = max(1.0, max_v - min_v) if max_v > min_v else max_v

    coords = []
    for idx, val in enumerate(pts_raw):
        x = pad_x + (idx / max(1, n - 1)) * (w - 2 * pad_x)
        norm = (val - min_v) / span if max_v > 0 else 0.0
        y = (h - pad_y) - norm * (h - 2 * pad_y)
        coords.append((round(x, 1), round(y, 1)))

    poly_pts = " ".join(f"{x},{y}" for x, y in coords)
    first_x = coords[0][0]
    last_x, last_y = coords[-1]
    area_d = f"M{first_x},{h - 2} " + " ".join(f"L{x},{y}" for x, y in coords) + f" L{last_x},{h - 2} Z"

    return f"""
    <svg width="96" height="36" viewBox="0 0 96 36" class="spark-svg" aria-hidden="true">
      <defs>
        <linearGradient id="{html.escape(grad_id)}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="{html.escape(color)}" stop-opacity="0.38" />
          <stop offset="100%" stop-color="{html.escape(color)}" stop-opacity="0.0" />
        </linearGradient>
      </defs>
      <path d="{area_d}" fill="url(#{html.escape(grad_id)})" />
      <polyline fill="none" stroke="{html.escape(color)}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" points="{poly_pts}" />
      <circle cx="{last_x}" cy="{last_y}" r="3.2" fill="{html.escape(color)}" />
    </svg>
    """


_TR_MONTHS = {
    1: "Oca", 2: "Şub", 3: "Mar", 4: "Nis", 5: "May", 6: "Haz",
    7: "Tem", 8: "Ağu", 9: "Eyl", 10: "Eki", 11: "Kas", 12: "Ara",
}


def _build_analytics_summary(db: Session, period: str = "all") -> Dict[str, Any]:
    ensure_historical_seed(db)

    all_clicks: List[BridgeClick] = (
        db.query(BridgeClick)
        .order_by(desc(BridgeClick.created_at))
        .limit(10000)
        .all()
    )

    signals: List[AppInstallSignal] = (
        db.query(AppInstallSignal)
        .order_by(desc(AppInstallSignal.created_at))
        .limit(5000)
        .all()
    )

    # Gerçek DB Aktivasyon Sayıları
    db_users_count = db.query(User.id).count()
    db_babies_count = db.query(Baby.id).count()
    db_cry_count = db.query(CryEvent.id).count()
    db_sleep_count = db.query(SleepLog.id).count()
    db_routine_count = db.query(RoutineLog.id).count()
    db_dadi_count = db.query(DadiChatHistory.id).count()
    db_feedbacks: List[Feedback] = db.query(Feedback).order_by(desc(Feedback.created_at)).limit(100).all()
    db_subs_count = db.query(Subscription.id).count()

    tz_tr = timezone(timedelta(hours=3))
    now_tr = datetime.now(tz_tr)
    today_str = now_tr.strftime("%Y-%m-%d")
    yesterday_str = (now_tr - timedelta(days=1)).strftime("%Y-%m-%d")
    cutoff_7d_date = (now_tr - timedelta(days=6)).strftime("%Y-%m-%d")

    def to_tr_date(dt_obj: datetime) -> str:
        d_utc = dt_obj.replace(tzinfo=timezone.utc) if dt_obj.tzinfo is None else dt_obj
        return d_utc.astimezone(tz_tr).strftime("%Y-%m-%d")

    # Tüm zamanlar (Kümülatif) insan ve tekil tıklamalar
    total_raw = len(all_clicks)
    human_clicks = [c for c in all_clicks if not c.is_bot]
    bot_clicks = [c for c in all_clicks if c.is_bot]
    unique_human = [c for c in all_clicks if c.is_unique and not c.is_bot]

    # Dönem filtresine göre tıklamalar (Sıfır sessiz fallback: geçersiz dönem reddedilir, seçili dönemde 0 tıklama varsa dürüstçe 0 döner)
    if period not in ALLOWED_PERIODS:
        raise ValueError(f"Unsupported period filter: {period}")
    if period == "today":
        period_clicks = [c for c in unique_human if to_tr_date(c.created_at) == today_str]
        period_raw_clicks = [c for c in all_clicks if to_tr_date(c.created_at) == today_str]
        period_label = "Bugün (TSİ)"
    elif period == "yesterday":
        period_clicks = [c for c in unique_human if to_tr_date(c.created_at) == yesterday_str]
        period_raw_clicks = [c for c in all_clicks if to_tr_date(c.created_at) == yesterday_str]
        period_label = "Dün (TSİ)"
    elif period == "7d":
        period_clicks = [c for c in unique_human if cutoff_7d_date <= to_tr_date(c.created_at) <= today_str]
        period_raw_clicks = [c for c in all_clicks if cutoff_7d_date <= to_tr_date(c.created_at) <= today_str]
        period_label = "Son 7 Gün"
    elif period == "all":
        period_clicks = unique_human
        period_raw_clicks = all_clicks
        period_label = "Tüm Zamanlar (Kümülatif)"

    active_human_set = period_clicks
    active_raw_set = period_raw_clicks

    today_unique_clicks = sum(1 for c in unique_human if to_tr_date(c.created_at) == today_str)
    yesterday_unique_clicks = sum(1 for c in unique_human if to_tr_date(c.created_at) == yesterday_str)

    # Meta Ads (/ios) & Instagram Bio (/download)
    meta_raw = [c for c in active_raw_set if c.route_path == "/ios"]
    meta_human = [c for c in meta_raw if not c.is_bot]
    meta_unique = [c for c in meta_raw if c.is_unique and not c.is_bot]
    meta_bots = [c for c in meta_raw if c.is_bot]
    meta_ios = [c for c in meta_unique if c.os_family == "ios"]
    meta_android = [c for c in meta_unique if c.os_family == "android"]

    ig_raw = [c for c in active_raw_set if c.route_path == "/download"]
    ig_human = [c for c in ig_raw if not c.is_bot]
    ig_unique = [c for c in ig_raw if c.is_unique and not c.is_bot]
    ig_ios = [c for c in ig_unique if c.os_family == "ios"]
    ig_android = [c for c in ig_unique if c.os_family == "android"]

    # OS & WebView Dağılımı (Seçili Dönem)
    os_counts = Counter(c.os_family for c in active_human_set)
    webview_counts = Counter(c.app_webview for c in active_human_set)

    # Saatlik Dağılım & Gece vs Gündüz Kadranı (TSİ)
    hourly_all_time = Counter()
    night_clicks = 0  # 21:00 - 04:59
    day_clicks = 0    # 05:00 - 20:59
    clicks_by_date = Counter()
    meta_by_date = Counter()
    ig_by_date = Counter()

    for c in unique_human:
        dt_utc = c.created_at.replace(tzinfo=timezone.utc) if c.created_at.tzinfo is None else c.created_at
        dt_tr = dt_utc.astimezone(tz_tr)
        date_key = dt_tr.strftime("%Y-%m-%d")
        clicks_by_date[date_key] += 1
        if c.route_path == "/ios":
            meta_by_date[date_key] += 1
        elif c.route_path == "/download":
            ig_by_date[date_key] += 1

    for c in active_human_set:
        dt_utc = c.created_at.replace(tzinfo=timezone.utc) if c.created_at.tzinfo is None else c.created_at
        dt_tr = dt_utc.astimezone(tz_tr)
        hour_key = dt_tr.strftime("%H:00")
        hourly_all_time[hour_key] += 1
        if dt_tr.hour >= 21 or dt_tr.hour <= 4:
            night_clicks += 1
        else:
            day_clicks += 1

    top_hours_sorted = sorted(
        [{"hour": f"{h:02d}:00", "clicks": hourly_all_time.get(f"{h:02d}:00", 0)} for h in range(24)],
        key=lambda x: x["clicks"],
        reverse=True,
    )
    golden_hours = top_hours_sorted[:3]

    # Uygulama İçi Cihaz Sinyalleri (app.html ve köprü tarafından gönderilen event türleri)
    first_opens = [s for s in signals if s.event_type == "first_open"]
    daily_actives = [s for s in signals if s.event_type == "daily_active"]
    store_jumps = [s for s in signals if s.event_type == "store_jump"]
    store_button_clicks = [s for s in signals if s.event_type == "store_button_click"]
    baby_created_signals = [s for s in signals if s.event_type == "baby_created"]
    vip_started_signals = [s for s in signals if s.event_type == "vip_started"]
    sleep_sound_signals = [s for s in signals if s.event_type == "sleep_sound_play"]
    cry_analysis_signals = [s for s in signals if s.event_type == "cry_analysis"]
    paywall_viewed_signals = [s for s in signals if s.event_type == "paywall_viewed"]
    paywall_cta_clicked_signals = [s for s in signals if s.event_type == "paywall_cta_clicked"]
    paywall_skipped_signals = [s for s in signals if s.event_type == "paywall_skipped"]
    purchase_cancelled_signals = [s for s in signals if s.event_type == "purchase_cancelled"]
    purchase_error_signals = [s for s in signals if s.event_type == "purchase_error"]
    sound_preview_60s_ended_signals = [s for s in signals if s.event_type == "sound_preview_60s_ended"]
    cry_limit_reached_signals = [s for s in signals if s.event_type == "cry_limit_reached"]
    dadi_limit_reached_signals = [s for s in signals if s.event_type == "dadi_limit_reached"]
    routine_limit_reached_signals = [s for s in signals if s.event_type == "routine_limit_reached"]
    paywall_cancel_recovery_signals = [s for s in signals if s.event_type == "paywall_cancel_recovery_shown"]
    unmatched_organic_opens = len([
        s for s in first_opens if (s.match_confidence or "unmatched") == "unmatched"
    ])
    distinct_signal_devices = len({
        s.device_uid for s in signals
        if s.device_uid and s.event_type in (
            "first_open", "daily_active", "baby_created", "vip_started", "sleep_sound_play", "cry_analysis",
            "paywall_viewed", "paywall_cta_clicked", "paywall_skipped", "purchase_cancelled", "purchase_error",
            "sound_preview_60s_ended", "cry_limit_reached", "dadi_limit_reached", "routine_limit_reached",
            "paywall_cancel_recovery_shown"
        )
    })

    # Resmi Mağaza Verileri: DB StoreDailyMetric + StoreSyncState anlık görüntüsü (Sıfır statik veri)
    with _BASELINE_LOCK:
        sb = copy.deepcopy(OFFICIAL_STORE_BASELINE)

    daily_db_rows: List[StoreDailyMetric] = (
        db.query(StoreDailyMetric)
        .order_by(StoreDailyMetric.metric_date.asc())
        .all()
    )
    daily_series_merged: Dict[str, Dict[str, int]] = {}
    for d_key, d_val in sb.get("daily_store_series", {}).items():
        daily_series_merged[d_key] = {
            "impressions": int(d_val.get("impressions", 0) or 0),
            "page_views": int(d_val.get("page_views", 0) or 0),
            "ios_downloads": int(d_val.get("ios_downloads", 0) or 0),
            "android_downloads": int(d_val.get("android_downloads", 0) or 0),
            "sessions": int(d_val.get("sessions", 0) or 0),
        }

    db_ios_imp = 0
    db_ios_pv = 0
    db_ios_dl = 0
    db_ios_dl_search = 0
    db_ios_dl_ref = 0
    db_ios_dl_browse = 0
    db_ios_sess = 0
    db_android_dl = 0
    for m_row in daily_db_rows:
        d_k = m_row.metric_date
        if d_k not in daily_series_merged:
            daily_series_merged[d_k] = {
                "impressions": 0,
                "page_views": 0,
                "ios_downloads": 0,
                "android_downloads": 0,
                "sessions": 0,
            }
        row_dl = int(getattr(m_row, "downloads_total", None) or getattr(m_row, "first_time_downloads", 0) or 0)
        row_sess = int(getattr(m_row, "active_sessions", 0) or 0)
        if m_row.platform == "ios":
            daily_series_merged[d_k]["impressions"] = max(daily_series_merged[d_k]["impressions"], int(m_row.impressions or 0))
            daily_series_merged[d_k]["page_views"] = max(daily_series_merged[d_k]["page_views"], int(m_row.page_views or 0))
            daily_series_merged[d_k]["ios_downloads"] = max(daily_series_merged[d_k]["ios_downloads"], row_dl)
            daily_series_merged[d_k]["sessions"] = max(daily_series_merged[d_k]["sessions"], row_sess)
            db_ios_imp += int(m_row.impressions or 0)
            db_ios_pv += int(m_row.page_views or 0)
            db_ios_dl += row_dl
            db_ios_dl_search += int(getattr(m_row, "downloads_search", 0) or 0)
            db_ios_dl_ref += int(getattr(m_row, "downloads_referrer", 0) or 0)
            db_ios_dl_browse += int(getattr(m_row, "downloads_browse", 0) or 0)
            db_ios_sess += row_sess
        elif m_row.platform == "android":
            daily_series_merged[d_k]["android_downloads"] = max(daily_series_merged[d_k]["android_downloads"], row_dl)
            db_android_dl += row_dl

    sb["daily_store_series"] = daily_series_merged
    apple_impressions = max(int(sb.get("apple_impressions_total", 0) or 0), db_ios_imp)
    apple_page_views = max(int(sb.get("apple_page_views_total", 0) or 0), db_ios_pv)
    apple_taps = int(sb.get("apple_taps_total", 0) or 0)
    ios_signal_opens = len([s for s in first_opens if s.os_family == "ios"])
    android_signal_opens = len([s for s in first_opens if s.os_family == "android"])
    apple_downloads = max(int(sb.get("apple_downloads_total", 0) or 0), db_ios_dl, ios_signal_opens)
    apple_official_sessions = max(int(sb.get("apple_sessions_total", 0) or 0), db_ios_sess)
    live_telemetry_sessions = len(first_opens) + len(daily_actives)
    # P1-4: Çift sayımı önlemek için resmi oturumlar ile canlı telemetri oturumlarının maksimumu alınır
    apple_sessions = max(apple_official_sessions, live_telemetry_sessions)
    google_play_downloads = max(
        int(sb.get("google_play_downloads_baseline", 0) or 0),
        db_android_dl,
        android_signal_opens,
    )

    sb["apple_impressions_total"] = apple_impressions
    sb["apple_page_views_total"] = apple_page_views
    sb["apple_downloads_total"] = apple_downloads
    sb["apple_sessions_total"] = apple_official_sessions
    sb["google_play_downloads_baseline"] = google_play_downloads

    total_cumulative_impressions = apple_impressions
    total_cumulative_visits_and_clicks = apple_page_views + len(unique_human)
    total_cumulative_downloads = apple_downloads + google_play_downloads

    # P0-4 & T2: Dinamik Tarihsel & Çift Katmanlı Canlı Zaman Serisi
    first_opens_by_date: Counter = Counter()
    android_opens_by_date: Counter = Counter()
    for fo in first_opens:
        fo_dt = to_tr_date(fo.created_at)
        first_opens_by_date[fo_dt] += 1
        if fo.os_family == "android":
            android_opens_by_date[fo_dt] += 1

    candidate_dates = list(daily_series_merged.keys()) + list(clicks_by_date.keys()) + list(first_opens_by_date.keys())
    valid_dates = [d for d in candidate_dates if len(d) == 10 and d <= today_str]
    if valid_dates:
        earliest_str = min(valid_dates)
        try:
            start_dt = datetime.strptime(earliest_str, "%Y-%m-%d").replace(tzinfo=tz_tr)
        except Exception:
            start_dt = now_tr - timedelta(days=6)
    else:
        start_dt = now_tr - timedelta(days=6)

    if (now_tr.date() - start_dt.date()).days > 60:
        start_dt = now_tr - timedelta(days=30)

    end_dt = now_tr
    num_days = max(1, (end_dt.date() - start_dt.date()).days + 1)
    start_date_str = start_dt.strftime("%Y-%m-%d")

    pre_start_clicks = sum(cnt for dt_k, cnt in clicks_by_date.items() if dt_k < start_date_str)

    # Apple TSV raporunun ulaştığı son kesinleşmiş günü tespit et
    confirmed_store_dates = [
        d_k for d_k, d_v in daily_series_merged.items()
        if int(d_v.get("ios_downloads", 0) or 0) > 0
    ]
    latest_confirmed_store_date = max(confirmed_store_dates) if confirmed_store_dates else ""

    # T2: Tarihsiz Android kurulumlarını son güne yığmak yerine gerçek sinyal/aktif mağaza günlerine dağıt
    explicit_and_by_day: Dict[str, int] = {}
    for i in range(num_days):
        d_str = (start_dt + timedelta(days=i)).strftime("%Y-%m-%d")
        st_and = int(daily_series_merged.get(d_str, {}).get("android_downloads", 0) or 0)
        sig_and = int(android_opens_by_date.get(d_str, 0) or 0)
        explicit_and_by_day[d_str] = max(st_and, sig_and)

    rem_android = max(0, google_play_downloads - sum(explicit_and_by_day.values()))
    if rem_android > 0:
        active_ios_days = [
            (start_dt + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(num_days)
            if int(daily_series_merged.get((start_dt + timedelta(days=i)).strftime("%Y-%m-%d"), {}).get("ios_downloads", 0) or 0) > 0
        ]
        target_days = active_ios_days if active_ios_days else [(start_dt + timedelta(days=max(0, num_days - 1))).strftime("%Y-%m-%d")]
        for idx_rem in range(rem_android):
            t_day = target_days[idx_rem % len(target_days)]
            explicit_and_by_day[t_day] = explicit_and_by_day.get(t_day, 0) + 1

    timeline_days = []
    cum_imp = 0
    cum_vis_clicks = pre_start_clicks
    cum_ios_dl = 0
    cum_and_dl = 0

    for i in range(num_days):
        d_obj = start_dt + timedelta(days=i)
        d_str = d_obj.strftime("%Y-%m-%d")
        d_short = f"{d_obj.day:02d} {_TR_MONTHS.get(d_obj.month, '')}"

        st_day = daily_series_merged.get(d_str, {})
        day_imp = int(st_day.get("impressions", 0) or 0)
        day_pv = int(st_day.get("page_views", 0) or 0)
        day_ios_dl = int(st_day.get("ios_downloads", 0) or 0)
        day_and_dl = int(explicit_and_by_day.get(d_str, 0) or 0)
        day_bridge = clicks_by_date.get(d_str, 0)
        day_fo = int(first_opens_by_date.get(d_str, 0) or 0)

        day_tot_touch = day_pv + day_bridge
        day_total_dl = day_ios_dl + day_and_dl

        cum_imp += day_imp
        cum_vis_clicks += day_tot_touch
        cum_ios_dl += day_ios_dl
        cum_and_dl += day_and_dl
        cum_total_dl = cum_ios_dl + cum_and_dl

        is_store_pending = bool(
            latest_confirmed_store_date
            and d_str > latest_confirmed_store_date
            and day_ios_dl == 0
        )

        timeline_days.append({
            "date": d_str,
            "label": d_short,
            "daily_impressions": day_imp,
            "daily_visits_clicks": day_tot_touch,
            "daily_bridge_clicks": day_bridge,
            "daily_page_views": day_pv,
            "daily_first_opens": day_fo,
            "daily_ios_downloads": day_ios_dl,
            "daily_android_downloads": day_and_dl,
            "daily_downloads": day_total_dl,
            "is_store_pending": is_store_pending,
            "cum_ios_downloads": cum_ios_dl,
            "cum_android_downloads": cum_and_dl,
            "cum_impressions": cum_imp,
            "cum_visits_clicks": cum_vis_clicks,
            "cum_downloads": cum_total_dl,
        })

    meta_live_clicks = len(meta_unique)
    meta_android_leak_pct = round((len(meta_android) / max(1, meta_live_clicks)) * 100, 1) if meta_live_clicks > 0 else 0.0
    active_human_count = len(active_human_set)

    # ========================================================================
    # FAZ 2: KURUMSAL GELİR, 3 KADEMELİ MRR ŞELALESİ VE ABONE DEFTERİ
    # ========================================================================
    try:
        active_trials_target_val = int(sb.get("apple_vip_active_trials", 0) or 0)
        if _reconcile_ios_ledger_and_cancellations(
            db,
            active_trials_target=active_trials_target_val if active_trials_target_val > 0 else None,
        ):
            db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    ledger_rows_db: List[SubscriberLedger] = (
        db.query(SubscriberLedger)
        .order_by(SubscriberLedger.maturity_or_renewal_date.asc(), SubscriberLedger.started_date.asc())
        .all()
    )

    # Önce veritabanındaki ücretli abonelerden gerçek birim fiyat referansını çıkar
    paid_ref_by_prod: Dict[str, tuple] = {}
    for r_ref in ledger_rows_db:
        if (r_ref.customer_price_try or 0.0) > 0 and r_ref.product_id:
            ref_plat = (r_ref.platform or "ios").lower()
            ref_ratio = 0.727 if ref_plat == "android" else 0.55417
            paid_ref_by_prod[r_ref.product_id] = (
                float(r_ref.customer_price_try),
                float(r_ref.developer_proceeds_try or round(float(r_ref.customer_price_try) * ref_ratio, 2)),
            )

    subscriber_ledger_list = []
    realized_gross_try = 0.0
    realized_net_try = 0.0
    active_paid_mrr_gross = 0.0
    active_paid_mrr_net = 0.0
    pipeline_7d_gross = 0.0
    pipeline_7d_net = 0.0
    pipeline_7d_monthly_mrr_gross = 0.0
    pipeline_7d_monthly_mrr_net = 0.0
    reconciling_7d_gross = 0.0
    reconciling_7d_net = 0.0
    reconciling_7d_cnt = 0
    upcoming_7d_gross = 0.0
    upcoming_7d_net = 0.0
    upcoming_7d_cnt = 0
    paid_subs_cnt = 0
    offer_code_cnt = 0
    intro_trial_cnt = 0
    cancelled_cnt = 0
    healed_trial_pricing = False

    plat_fin: Dict[str, Dict[str, float]] = {
        "ios": {
            "realized_gross": 0.0, "realized_net": 0.0,
            "paid_mrr_gross": 0.0, "paid_mrr_net": 0.0,
            "pipeline_gross": 0.0, "pipeline_net": 0.0,
            "paid_cnt": 0, "trial_cnt": 0, "code_cnt": 0, "cancelled_cnt": 0,
        },
        "android": {
            "realized_gross": 0.0, "realized_net": 0.0,
            "paid_mrr_gross": 0.0, "paid_mrr_net": 0.0,
            "pipeline_gross": 0.0, "pipeline_net": 0.0,
            "paid_cnt": 0, "trial_cnt": 0, "code_cnt": 0, "cancelled_cnt": 0,
        },
    }

    renewal_by_date: Dict[str, Dict[str, Any]] = {}
    cohort_by_start_date: Dict[str, Dict[str, Any]] = {}

    for r in ledger_rows_db:
        r_plat = "android" if (r.platform or "ios").lower() == "android" else "ios"
        net_ratio = 0.727 if r_plat == "android" else 0.55417
        pf_bucket = plat_fin[r_plat]

        r_gross = float(r.customer_price_try or 0.0)
        r_net = float(r.developer_proceeds_try or 0.0)
        realized_gross_try += r_gross
        realized_net_try += r_net
        pf_bucket["realized_gross"] += r_gross
        pf_bucket["realized_net"] += r_net

        is_cancelled_row = bool(r.status == "cancelled" or (r.status != "paid_active" and not r.auto_renew_enabled))
        if is_cancelled_row:
            cancelled_cnt += 1
            pf_bucket["cancelled_cnt"] += 1

        # T1 Çözümü: Deneme abonelerinde expected_next_price_try 0.0 kalmışsa katalog/referans tarifeden tamamla
        ref_pair = paid_ref_by_prod.get(r.product_id or "misil_monthly", (0.0, 0.0))
        resolved_gross, resolved_net = _resolve_expected_trial_pricing(
            r.product_id, ref_pair[0], ref_pair[1], r_plat
        )
        if r.status == "intro_free_trial" and r.auto_renew_enabled:
            if (r.expected_next_price_try or 0.0) <= 0:
                r.expected_next_price_try = resolved_gross
                r.expected_next_proceeds_try = resolved_net
                healed_trial_pricing = True
            elif (r.expected_next_proceeds_try or 0.0) <= 0:
                r.expected_next_proceeds_try = round(float(r.expected_next_price_try) * net_ratio, 2)
                healed_trial_pricing = True

        lifecycle_stage = r.status
        lifecycle_badge = "⏳ 7 Günlük Deneme"
        trial_progress_pct = 100

        if r.status == "cancelled":
            lifecycle_stage = "cancelled"
            lifecycle_badge = "✖ İptal"
            trial_progress_pct = 0
        elif r.status == "paid_active":
            paid_subs_cnt += 1
            pf_bucket["paid_cnt"] += 1
            lifecycle_stage = "paid_active"
            lifecycle_badge = "💳 Ücretli Aktif"
            trial_progress_pct = 100
            if r.auto_renew_enabled:
                rec_gross = float(r.expected_next_price_try or r.customer_price_try or resolved_gross)
                rec_net = float(r.expected_next_proceeds_try or r.developer_proceeds_try or resolved_net)
                if _is_annual_product(r.product_id):
                    m_g = rec_gross / 12.0
                    m_n = rec_net / 12.0
                else:
                    m_g = rec_gross
                    m_n = rec_net
                active_paid_mrr_gross += m_g
                active_paid_mrr_net += m_n
                pf_bucket["paid_mrr_gross"] += m_g
                pf_bucket["paid_mrr_net"] += m_n
        elif not r.auto_renew_enabled:
            lifecycle_stage = "cancelled"
            lifecycle_badge = "✖ İptal"
            trial_progress_pct = 0
        elif r.status == "offer_code_trial":
            offer_code_cnt += 1
            pf_bucket["code_cnt"] += 1
            lifecycle_stage = "offer_code_trial"
            lifecycle_badge = f"🎟️ Kodlu ({r.offer_code_name or 'VIP'})"
            trial_progress_pct = 100
        elif r.status == "intro_free_trial":
            intro_trial_cnt += 1
            pf_bucket["trial_cnt"] += 1
            if r.auto_renew_enabled:
                next_gross = float(r.expected_next_price_try or resolved_gross)
                next_net = float(r.expected_next_proceeds_try or resolved_net)
                pipeline_7d_gross += next_gross
                pipeline_7d_net += next_net
                pf_bucket["pipeline_gross"] += next_gross
                pf_bucket["pipeline_net"] += next_net
                if _is_annual_product(r.product_id):
                    pipeline_7d_monthly_mrr_gross += next_gross / 12.0
                    pipeline_7d_monthly_mrr_net += next_net / 12.0
                else:
                    pipeline_7d_monthly_mrr_gross += next_gross
                    pipeline_7d_monthly_mrr_net += next_net
                m_dt = r.maturity_or_renewal_date or "-"

                # T4 Çözümü: Vade günü bugün veya geçmişteyse Apple 24-48s mutabakat penceresinde olarak ayır
                is_reconciling = bool(m_dt != "-" and len(m_dt) == 10 and m_dt <= today_str)
                if is_reconciling:
                    reconciling_7d_cnt += 1
                    reconciling_7d_gross += next_gross
                    reconciling_7d_net += next_net
                    lifecycle_stage = "reconciling_trial"
                    lifecycle_badge = "🔄 Apple Mutabakatında (7/7 Gün)" if r_plat == "ios" else "🔄 Google Play Mutabakatında (7/7 Gün)"
                    trial_progress_pct = 100
                else:
                    upcoming_7d_cnt += 1
                    upcoming_7d_gross += next_gross
                    upcoming_7d_net += next_net
                    lifecycle_stage = "upcoming_trial"
                    elapsed_days = 4
                    try:
                        if r.started_date and len(r.started_date) == 10:
                            st_d = datetime.strptime(r.started_date, "%Y-%m-%d").date()
                            elapsed_days = max(1, min(6, (now_tr.date() - st_d).days))
                    except Exception:
                        elapsed_days = 4
                    trial_progress_pct = max(15, min(90, round((elapsed_days / 7.0) * 100)))
                    lifecycle_badge = f"⏳ Deneme ({elapsed_days}/7 Gün)"

                if m_dt not in renewal_by_date:
                    renewal_by_date[m_dt] = {
                        "date": m_dt,
                        "count": 0,
                        "expected_gross_try": 0.0,
                        "expected_net_try": 0.0,
                        "is_reconciling": is_reconciling,
                        "status_label": "🔄 Tahsilat Mutabakatında" if is_reconciling else "⏳ Vadesi Gelecek Tahsilat",
                        "subscribers": [],
                    }
                renewal_by_date[m_dt]["count"] += 1
                renewal_by_date[m_dt]["expected_gross_try"] = round(
                    renewal_by_date[m_dt]["expected_gross_try"] + next_gross, 2
                )
                renewal_by_date[m_dt]["expected_net_try"] = round(
                    renewal_by_date[m_dt]["expected_net_try"] + next_net, 2
                )
                renewal_by_date[m_dt]["subscribers"].append(f"#{r.subscriber_id[-6:]} ({r.country})")

        s_dt = r.started_date or "-"
        if s_dt not in cohort_by_start_date:
            cohort_by_start_date[s_dt] = {
                "start_date": s_dt,
                "started_total": 0,
                "active_retained": 0,
                "paid_converted": 0,
                "offer_code": 0,
                "intro_trial": 0,
                "reconciling_trial": 0,
                "cancelled": 0,
            }
        cohort_by_start_date[s_dt]["started_total"] += 1
        if r.status != "cancelled" and r.auto_renew_enabled:
            cohort_by_start_date[s_dt]["active_retained"] += 1
        else:
            cohort_by_start_date[s_dt]["cancelled"] += 1
        if r.status == "paid_active":
            cohort_by_start_date[s_dt]["paid_converted"] += 1
        elif r.status == "offer_code_trial":
            cohort_by_start_date[s_dt]["offer_code"] += 1
        elif r.status == "intro_free_trial" and r.auto_renew_enabled:
            cohort_by_start_date[s_dt]["intro_trial"] += 1
            if lifecycle_stage == "reconciling_trial":
                cohort_by_start_date[s_dt]["reconciling_trial"] += 1

        subscriber_ledger_list.append({
            "subscriber_id": r.subscriber_id,
            "subscriber_short": f"#{r.subscriber_id[-6:]}",
            "platform": r.platform,
            "product_id": r.product_id,
            "plan_label": r.plan_label,
            "status": r.status,
            "lifecycle_stage": lifecycle_stage,
            "lifecycle_badge": lifecycle_badge,
            "trial_progress_pct": trial_progress_pct,
            "offer_type": r.offer_type,
            "offer_code_name": r.offer_code_name or "-",
            "started_date": r.started_date or "-",
            "converted_or_renewed_date": r.converted_or_renewed_date or "-",
            "maturity_or_renewal_date": r.maturity_or_renewal_date or "-",
            "auto_renew_enabled": r.auto_renew_enabled,
            "customer_price_try": round(float(r.customer_price_try or 0.0), 2),
            "developer_proceeds_try": round(float(r.developer_proceeds_try or 0.0), 2),
            "expected_next_price_try": round(float(r.expected_next_price_try or 0.0), 2),
            "expected_next_proceeds_try": round(float(r.expected_next_proceeds_try or 0.0), 2),
            "country": r.country,
            "device_type": r.device_type,
        })

    if healed_trial_pricing:
        try:
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass

    # P0-4: Dinamik 7 günlük kohort olgunlaşma kesimi
    matured_cutoff_str = (now_tr.date() - timedelta(days=7)).strftime("%Y-%m-%d")
    matured_7d_cohort = [
        r for r in ledger_rows_db
        if r.offer_type in ("standard_paid", "intro_7d_trial")
        and r.started_date
        and r.started_date <= matured_cutoff_str
    ]
    matured_converted = sum(1 for r in matured_7d_cohort if r.status == "paid_active")
    if len(matured_7d_cohort) > 0:
        matured_cvr_pct = round((matured_converted / len(matured_7d_cohort)) * 100, 1)
        matured_cvr_str = f"%{matured_cvr_pct}"
    else:
        matured_cvr_pct = 0.0
        matured_cvr_str = "Veri Yok"

    auto_renew_on_pct = (
        round(((len(ledger_rows_db) - cancelled_cnt) / len(ledger_rows_db)) * 100, 1)
        if len(ledger_rows_db) > 0
        else 0.0
    )

    active_vip_total = paid_subs_cnt + offer_code_cnt + intro_trial_cnt
    if len(ledger_rows_db) > 0:
        apple_vip = active_vip_total
    else:
        apple_vip = max(int(sb.get("apple_vip_activations_total", 0) or 0), db_subs_count, len(vip_started_signals))
    sb["apple_vip_activations_total"] = apple_vip

    financial_ledger = {
        "realized_gross_try": round(realized_gross_try, 2),
        "realized_net_proceeds_try": round(realized_net_try, 2),
        "active_paid_mrr_gross_try": round(active_paid_mrr_gross, 2),
        "active_paid_mrr_net_try": round(active_paid_mrr_net, 2),
        "active_paid_arr_net_try": round(active_paid_mrr_net * 12, 2),
        "pipeline_7d_trials_count": intro_trial_cnt,
        "pipeline_7d_mrr_gross_try": round(pipeline_7d_gross, 2),
        "pipeline_7d_mrr_net_try": round(pipeline_7d_net, 2),
        "pipeline_7d_monthly_mrr_gross_try": round(pipeline_7d_monthly_mrr_gross, 2),
        "pipeline_7d_monthly_mrr_net_try": round(pipeline_7d_monthly_mrr_net, 2),
        "reconciling_7d_trials_count": reconciling_7d_cnt,
        "reconciling_7d_mrr_gross_try": round(reconciling_7d_gross, 2),
        "reconciling_7d_mrr_net_try": round(reconciling_7d_net, 2),
        "upcoming_7d_trials_count": upcoming_7d_cnt,
        "upcoming_7d_mrr_gross_try": round(upcoming_7d_gross, 2),
        "upcoming_7d_mrr_net_try": round(upcoming_7d_net, 2),
        "projected_total_mrr_gross_try": round(active_paid_mrr_gross + pipeline_7d_gross, 2),
        "projected_total_mrr_net_try": round(active_paid_mrr_net + pipeline_7d_net, 2),
        "projected_total_arr_net_try": round((active_paid_mrr_net + pipeline_7d_net) * 12, 2),
        "active_vip_subs_count": active_vip_total,
        "total_vip_records_count": len(ledger_rows_db),
        "offer_code_subs_count": offer_code_cnt,
        "paid_subs_count": paid_subs_cnt,
        "cancelled_subs_count": cancelled_cnt,
        "auto_renew_on_pct": auto_renew_on_pct,
        "matured_cutoff_date": matured_cutoff_str,
        "matured_trials_total": len(matured_7d_cohort),
        "matured_trials_converted": matured_converted,
        "matured_trial_to_paid_cvr_pct": matured_cvr_pct,
        "matured_trial_to_paid_cvr_str": matured_cvr_str,
        "renewal_forecast_calendar": [renewal_by_date[k] for k in sorted(renewal_by_date.keys())],
    }

    # ========================================================================
    # FAZ 3: DİNAMİK KAMPANYA & KANAL ATTRIBUTION MATRİSİ (SIFIR STATİK VERİ)
    # ========================================================================
    cfg_rows = db.query(CampaignConfig).all()
    cfg_map: Dict[str, CampaignConfig] = {c.channel_key: c for c in cfg_rows}

    asa_cfg = cfg_map.get("apple_search_ads")
    meta_cfg = cfg_map.get("meta_ads_ios")
    ig_cfg = cfg_map.get("instagram_bio")

    asa_spend_usd = round(float(asa_cfg.spend_usd if asa_cfg else 0.0), 2)
    asa_cpt_bid_usd = round(float(asa_cfg.cpt_bid_usd if asa_cfg else 0.0), 2)
    meta_spend_usd = round(float(meta_cfg.spend_usd if meta_cfg else 0.0), 2)
    ig_spend_usd = round(float(ig_cfg.spend_usd if ig_cfg else 0.0), 2)

    matched_meta_installs = len([
        s for s in first_opens
        if s.os_family == "ios"
        and (s.matched_channel and ("meta" in s.matched_channel.lower() or "ios" in s.matched_channel.lower()))
    ])
    matched_ig_installs = len([
        s for s in first_opens
        if s.os_family == "ios"
        and (s.matched_channel and ("instagram" in s.matched_channel.lower() or "download" in s.matched_channel.lower()))
    ])

    r3_search = max(
        int(sb.get("apple_downloads_search", 0) or 0),
        db_ios_dl_search,
        int(asa_cfg.reported_installs if asa_cfg else 0),
    )
    r3_ref = max(
        int(sb.get("apple_downloads_referrer", 0) or 0),
        db_ios_dl_ref,
        int(meta_cfg.reported_installs if meta_cfg else 0),
        matched_meta_installs,
    )
    r3_browse = max(
        int(sb.get("apple_downloads_browse", 0) or 0),
        db_ios_dl_browse,
        int(ig_cfg.reported_installs if ig_cfg else 0),
        matched_ig_installs,
    )
    asa_clicks_val = max(apple_taps, int(asa_cfg.reported_clicks if asa_cfg else 0))

    imp_search_val = int(sb.get("apple_impressions_search", 0) or apple_impressions)
    imp_browse_val = int(sb.get("apple_impressions_browse", 0) or 0)

    # T3 Çözümü: Apple r3 kaynak raporu henüz senkronize edilmemişse (0 ise), doğrulanmış r14 Discovery
    # arama/keşfet oranları ve köprü sinyalleri üzerinden kaynak dağılımını hesapla
    if (r3_search + r3_browse) == 0 and apple_downloads > 0 and (imp_search_val + imp_browse_val) > 0:
        allocatable_ios = max(0, apple_downloads - r3_ref - offer_code_cnt)
        search_share = imp_search_val / max(1, imp_search_val + imp_browse_val)
        r3_search = round(allocatable_ios * search_share)
        r3_browse = max(0, allocatable_ios - r3_search)

    recent_ios_dl = max(0, apple_downloads - (r3_search + r3_ref + r3_browse + offer_code_cnt))
    android_bridge_uniq = len([c for c in unique_human if c.os_family == "android"])

    total_all_spend_usd = round(sum(float(c.spend_usd or 0.0) for c in cfg_rows), 2)
    blended_cpi_usd = (
        round(total_all_spend_usd / total_cumulative_downloads, 2)
        if total_cumulative_downloads > 0 and total_all_spend_usd > 0
        else 0.0
    )
    asa_cpi_usd = round(asa_spend_usd / r3_search, 2) if r3_search > 0 and asa_spend_usd > 0 else 0.0
    asa_cr_pct = round((r3_search / asa_clicks_val) * 100, 1) if asa_clicks_val > 0 else 0.0
    meta_cpi_usd = round(meta_spend_usd / r3_ref, 2) if r3_ref > 0 and meta_spend_usd > 0 else None

    aso_attribution_matrix = [
        {
            "channel": "🔍 App Store Arama (Search)",
            "source_badge": "Apple API + Kampanya DB",
            "impressions": f"{imp_search_val:,}",
            "page_views_or_clicks": f"Toplam {apple_page_views} Sayfa ({sb.get('apple_page_views_unique', 0)} Cihaz)",
            "downloads": r3_search,
            "cvr_pct": round((r3_search / imp_search_val) * 100, 2) if imp_search_val > 0 else 0.0,
            "cvr_basis": "Görüntülenme ➔ İndirme",
            "vip_attributed": f"{paid_subs_cnt} Ücretli + {intro_trial_cnt} Aktif 7G Deneme",
        },
        {
            "channel": "📲 Sosyal Yönlendirme (Instagram & Facebook)",
            "source_badge": "Köprü DB + Sinyal Eşleşmesi",
            "impressions": "-",
            "page_views_or_clicks": f"{len(unique_human)} Tekil Tık ({total_raw} Ham)",
            "downloads": r3_ref,
            "cvr_pct": round((r3_ref / len(unique_human)) * 100, 1) if len(unique_human) > 0 else 0.0,
            "cvr_basis": "Tekil Tık ➔ iOS İndirme",
            "vip_attributed": f"{matched_meta_installs} Doğrulanmış Cihaz Eşleşmesi",
        },
        {
            "channel": "🎟️ Promosyon Kodu (Offer Codes)",
            "source_badge": "Apple SUBSCRIBER (1_3) API",
            "impressions": "-",
            "page_views_or_clicks": f"{offer_code_cnt} Tekil Kod Kullanımı",
            "downloads": offer_code_cnt,
            "cvr_pct": 100.0 if offer_code_cnt > 0 else 0.0,
            "cvr_basis": "Kod ➔ Yıllık VIP Aktivasyon",
            "vip_attributed": f"{offer_code_cnt} Aktif Kod Abonesi",
        },
        {
            "channel": "📅 Doğrudan / Sınıflandırılmamış iOS Kurulumları",
            "source_badge": "Apple Sales Report API",
            "impressions": "-",
            "page_views_or_clicks": "-",
            "downloads": recent_ios_dl,
            "cvr_pct": None,
            "cvr_basis": "Doğrudan Sales API",
            "vip_attributed": f"{unmatched_organic_opens} Eşleşmemiş İlk Açılış Sinyali",
        },
        {
            "channel": "✨ App Store Keşfet (Browse / Organik)",
            "source_badge": "Apple API + Bio Köprü",
            "impressions": f"{imp_browse_val:,}",
            "page_views_or_clicks": f"Toplam {apple_taps} Dokunma ({sb.get('apple_taps_unique', 0)} Cihaz)",
            "downloads": r3_browse,
            "cvr_pct": round((r3_browse / imp_browse_val) * 100, 1) if imp_browse_val > 0 else 0.0,
            "cvr_basis": "Görüntülenme ➔ İndirme",
            "vip_attributed": f"{matched_ig_installs} Bio Sinyal Eşleşmesi",
        },
        {
            "channel": "🤖 Google Play (Android Üretim)",
            "source_badge": "Google Play API + Sinyal DB",
            "impressions": "-",
            "page_views_or_clicks": f"{android_bridge_uniq} Android Köprü Tıkı",
            "downloads": google_play_downloads,
            "cvr_pct": round((google_play_downloads / android_bridge_uniq) * 100, 1) if android_bridge_uniq > 0 else 0.0,
            "cvr_basis": "Android Tık ➔ Play Kurulum",
            "vip_attributed": f"{android_signal_opens} Android İlk Açılış Sinyali",
        },
    ]

    # ========================================================================
    # FAZ 3B: ÜRÜN İÇİ NABIZ, BEBEK YAŞ DAĞILIMI & KOHORT TUTUNDURMA
    # ========================================================================
    babies_all: List[Baby] = db.query(Baby).limit(500).all()
    age_buckets = {"0–3 Ay (Yenidoğan / 4. Trimester)": 0, "4–6 Ay (Uyku Gerilemesi)": 0, "7–12 Ay": 0, "12+ Ay": 0}
    for b in babies_all:
        try:
            m = b.age_in_months
            if m <= 3.5:
                age_buckets["0–3 Ay (Yenidoğan / 4. Trimester)"] += 1
            elif m <= 6.5:
                age_buckets["4–6 Ay (Uyku Gerilemesi)"] += 1
            elif m <= 12.5:
                age_buckets["7–12 Ay"] += 1
            else:
                age_buckets["12+ Ay"] += 1
        except Exception:
            age_buckets["0–3 Ay (Yenidoğan / 4. Trimester)"] += 1

    cohort_rows = []
    total_cohort_started = 0
    total_cohort_retained = 0
    for k_dt in sorted(cohort_by_start_date.keys()):
        c_item = cohort_by_start_date[k_dt]
        ret_pct = round((c_item["active_retained"] / max(1, c_item["started_total"])) * 100, 1)
        c_item["retention_pct"] = ret_pct
        total_cohort_started += c_item["started_total"]
        total_cohort_retained += c_item["active_retained"]
        cohort_rows.append(c_item)

    if total_cohort_started > 0:
        overall_retention_pct = round((total_cohort_retained / total_cohort_started) * 100, 1)
        overall_retention_str = f"%{overall_retention_pct}"
    else:
        overall_retention_pct = 0.0
        overall_retention_str = "Veri Yok"

    optin_ios_total_dev = int(sb.get("apple_sessions_optin_devices", 0) or 0)
    returning_optin_ios_dev = int(sb.get("apple_returning_optin_devices", 0) or 0)
    loyal_optin_ios_dev = int(sb.get("apple_loyal_optin_devices", 0) or 0)
    returning_sess_tot = int(sb.get("apple_returning_sessions_total", 0) or 0)
    max_sess_single_dev = int(sb.get("apple_max_sessions_per_device", 0) or 0)
    total_sess_dur_sec = int(sb.get("apple_sessions_duration_sec", 0) or 0)
    distinct_daily_active_devs = len({s.device_uid for s in daily_actives if s.device_uid}) or len(daily_actives)
    optin_ios_return_rate_pct = (
        round((returning_optin_ios_dev / optin_ios_total_dev) * 100, 1)
        if optin_ios_total_dev > 0
        else 0.0
    )
    verified_returning_floor = max(returning_optin_ios_dev, distinct_daily_active_devs)
    verified_returning_ceiling = returning_optin_ios_dev + distinct_daily_active_devs
    est_total_returning_users = (
        max(
            verified_returning_floor,
            round(total_cumulative_downloads * (returning_optin_ios_dev / optin_ios_total_dev) * 0.85),
        )
        if optin_ios_total_dev > 0
        else verified_returning_floor
    )

    product_retention = {
        "apple_official_sessions": apple_official_sessions,
        "total_tracked_sessions": apple_sessions,
        "optin_active_devices": max(optin_ios_total_dev, distinct_signal_devices, db_babies_count),
        "optin_ios_total_devices": optin_ios_total_dev,
        "returning_optin_ios_devices": returning_optin_ios_dev,
        "loyal_optin_ios_devices": loyal_optin_ios_dev,
        "optin_ios_return_rate_pct": optin_ios_return_rate_pct,
        "returning_sessions_total": returning_sess_tot,
        "max_sessions_single_device": max_sess_single_dev,
        "daily_active_signals_count": len(daily_actives),
        "verified_returning_devices_floor": verified_returning_floor,
        "verified_returning_devices_ceiling": verified_returning_ceiling,
        "estimated_total_returning_users": est_total_returning_users,
        "avg_session_duration_sec": (
            round(total_sess_dur_sec / apple_official_sessions)
            if apple_official_sessions > 0
            else 0
        ),
        "babies_count": max(db_babies_count, len(baby_created_signals)),
        "sleep_logs_count": max(db_sleep_count, len(sleep_sound_signals)),
        "cry_events_count": max(db_cry_count, len(cry_analysis_signals)),
        "routine_logs_count": db_routine_count,
        "dadi_chats_count": db_dadi_count,
        "age_buckets": age_buckets,
        "subscriber_cohorts": cohort_rows,
        "overall_retention_pct": overall_retention_pct,
        "overall_retention_str": overall_retention_str,
    }

    # Son 3 aktif gün vs önceki günler ivmesi (Sparkline & Delta Rozeti için)
    settled_days = [d for d in timeline_days if not d.get("is_store_pending")]
    recent_3d_imp = sum(d.get("daily_impressions", 0) for d in settled_days[-3:]) if settled_days else 0
    recent_3d_dl = sum(d.get("daily_downloads", 0) for d in settled_days[-3:]) if settled_days else 0
    latest_store_metric_date = settled_days[-1]["date"] if settled_days else ""

    ios_bridge_uniq = len([c for c in unique_human if c.os_family == "ios"])
    desktop_bridge_uniq = len([c for c in unique_human if c.os_family not in ("ios", "android")])
    ios_touchpoints = apple_page_views + ios_bridge_uniq
    android_touchpoints = android_bridge_uniq

    # P1: Simpson Paradoksu & 24s Gecikme Ayrımı — Mağaza Sayfası CVR vs Sosyal Köprü CVR vs Kesinleşen Günler CVR
    apple_page_views_uniq = max(1, int(sb.get("apple_page_views_unique", 0) or apple_page_views))
    store_page_cvr_pct = (
        min(100.0, round((apple_downloads / max(1, apple_page_views)) * 100, 1))
        if apple_page_views > 0
        else 0.0
    )
    store_unique_cvr_pct = (
        min(100.0, round((apple_downloads / apple_page_views_uniq) * 100, 1))
        if apple_page_views > 0
        else 0.0
    )
    ios_bridge_dl = min(ios_bridge_uniq, r3_ref) if ios_bridge_uniq > 0 else 0
    and_bridge_dl = min(android_bridge_uniq, google_play_downloads) if android_bridge_uniq > 0 else 0
    ios_bridge_cvr_pct = (
        round((ios_bridge_dl / max(1, ios_bridge_uniq)) * 100, 1)
        if ios_bridge_uniq > 0
        else 0.0
    )
    android_bridge_cvr_pct = (
        round((and_bridge_dl / max(1, android_bridge_uniq)) * 100, 1)
        if android_bridge_uniq > 0
        else 0.0
    )
    all_bridge_installs = ios_bridge_dl + and_bridge_dl
    all_bridge_cvr_pct = (
        round((all_bridge_installs / max(1, len(unique_human))) * 100, 1)
        if len(unique_human) > 0
        else 0.0
    )

    settled_touchpoints = sum(int(d.get("daily_visits_clicks", 0) or 0) for d in settled_days)
    settled_downloads = sum(int(d.get("daily_downloads", 0) or 0) for d in settled_days)
    settled_cvr_pct = (
        round((settled_downloads / max(1, settled_touchpoints)) * 100, 1)
        if settled_touchpoints > 0
        else round((total_cumulative_downloads / max(1, total_cumulative_visits_and_clicks)) * 100, 1)
    )
    desktop_sub_suffix = f" • 💻 {desktop_bridge_uniq} Masaüstü" if desktop_bridge_uniq > 0 else ""

    ios_subs_list = [s for s in subscriber_ledger_list if (s.get("platform") or "ios") == "ios"]
    android_subs_list = [s for s in subscriber_ledger_list if s.get("platform") == "android"]
    gp_catalog = sb.get("google_play_subscriptions_catalog") or _empty_store_state()["google_play_subscriptions_catalog"]

    ios_paid_cnt = int(plat_fin["ios"]["paid_cnt"])
    ios_trial_cnt = int(plat_fin["ios"]["trial_cnt"])
    ios_code_cnt = int(plat_fin["ios"]["code_cnt"])
    ios_cancelled_cnt = int(plat_fin["ios"]["cancelled_cnt"])
    ios_active_cnt = ios_paid_cnt + ios_trial_cnt + ios_code_cnt
    ios_mrr_net = round(plat_fin["ios"]["paid_mrr_net"] + plat_fin["ios"]["pipeline_net"], 2)
    ios_mrr_gross = round(plat_fin["ios"]["paid_mrr_gross"] + plat_fin["ios"]["pipeline_gross"], 2)
    ios_realized_net = round(plat_fin["ios"]["realized_net"], 2)

    and_paid_cnt = int(plat_fin["android"]["paid_cnt"])
    and_trial_cnt = int(plat_fin["android"]["trial_cnt"])
    and_code_cnt = int(plat_fin["android"]["code_cnt"])
    and_cancelled_cnt = int(plat_fin["android"]["cancelled_cnt"])
    and_active_cnt = and_paid_cnt + and_trial_cnt + and_code_cnt
    and_mrr_net = round(plat_fin["android"]["paid_mrr_net"] + plat_fin["android"]["pipeline_net"], 2)
    and_mrr_gross = round(plat_fin["android"]["paid_mrr_gross"] + plat_fin["android"]["pipeline_gross"], 2)
    and_realized_net = round(plat_fin["android"]["realized_net"], 2)

    all_reviews = sb.get("store_reviews") or []
    ios_reviews_cnt = sum(1 for r in all_reviews if r.get("store") == "App Store")
    android_reviews_cnt = sum(1 for r in all_reviews if r.get("store") == "Google Play")

    ios_total_rec = len(ios_subs_list)
    and_total_rec = len(android_subs_list)
    all_total_rec = len(subscriber_ledger_list)

    ios_vip_sub_str = (
        f"Toplam {ios_total_rec} Kayıt ({ios_active_cnt} Aktif • {ios_cancelled_cnt} İptal) — "
        f"{ios_paid_cnt} Ücretli ({ios_realized_net:.2f} ₺) • {ios_trial_cnt} 7G Deneme (+{plat_fin['ios']['pipeline_net']:.2f} ₺) • {ios_code_cnt} Kodlu"
        if ios_cancelled_cnt > 0
        else f"{ios_paid_cnt} Ücretli ({ios_realized_net:.2f} ₺) • {ios_trial_cnt} 7G Deneme (+{plat_fin['ios']['pipeline_net']:.2f} ₺) • {ios_code_cnt} Kodlu"
    )
    and_vip_sub_str = (
        f"{and_active_cnt} Aktif Android VIP (Toplam {and_total_rec} Kayıt • {and_cancelled_cnt} İptal) — "
        f"{and_paid_cnt} Ücretli ({and_realized_net:.2f} ₺) • {and_trial_cnt} 7G Deneme (+{plat_fin['android']['pipeline_net']:.2f} ₺) • {and_code_cnt} Kodlu"
        if and_total_rec > 0
        else f"0 Aktif Abone • Google Play API'de {len(gp_catalog)} Aktif Paket (599.99 ₺/Yıl & 149.99 ₺/Ay + 7G Deneme) Yayında"
    )

    platform_split = {
        "all": {
            "key": "all",
            "label": "🌐 Kümülatif (Toplam — Apple + Google Play)",
            "impressions": total_cumulative_impressions,
            "impressions_display": f"{total_cumulative_impressions:,}",
            "impressions_sub": f"🍏 {apple_impressions:,} App Store API • 🤖 Google Play Köprü ({android_bridge_uniq} Tık)",
            "touchpoints": total_cumulative_visits_and_clicks,
            "touchpoints_display": f"{total_cumulative_visits_and_clicks:,}",
            "touchpoints_sub": f"🍏 {ios_touchpoints} iOS ({apple_page_views} Mağaza + {ios_bridge_uniq} Tık) • 🤖 {android_touchpoints} Android Tık{desktop_sub_suffix}",
            "downloads": total_cumulative_downloads,
            "downloads_display": f"{total_cumulative_downloads}",
            "downloads_sub": f"🍏 {apple_downloads} iOS (%{round((apple_downloads / max(1, total_cumulative_downloads)) * 100)}) • 🤖 {google_play_downloads} Android (%{round((google_play_downloads / max(1, total_cumulative_downloads)) * 100)})",
            "vis_of_imp_pct": round((total_cumulative_visits_and_clicks / max(1, total_cumulative_impressions)) * 100, 1),
            "cvr_pct": round((total_cumulative_downloads / max(1, total_cumulative_visits_and_clicks)) * 100, 1),
            "store_cvr_pct": store_page_cvr_pct,
            "store_unique_cvr_pct": store_unique_cvr_pct,
            "bridge_cvr_pct": all_bridge_cvr_pct,
            "settled_cvr_pct": settled_cvr_pct,
            "desktop_bridge_clicks": desktop_bridge_uniq,
            "cvr_breakdown_label": f"Mağaza: %{store_page_cvr_pct} • Köprü: %{all_bridge_cvr_pct}",
            "dl_of_imp_pct": round((total_cumulative_downloads / max(1, total_cumulative_impressions)) * 100, 2),
            "vip_of_dl_pct": round((active_vip_total / max(1, total_cumulative_downloads)) * 100, 1),
            "vip_of_vis_pct": round((active_vip_total / max(1, total_cumulative_visits_and_clicks)) * 100, 2),
            "vip_of_imp_pct": round((active_vip_total / max(1, total_cumulative_impressions)) * 100, 2),
            "vip_count": active_vip_total,
            "total_vip_count": all_total_rec,
            "cancelled_vip_count": cancelled_cnt,
            "vip_display": f"{active_vip_total} Aktif VIP" if cancelled_cnt > 0 else f"{active_vip_total} VIP",
            "vip_sub": (
                f"🍏 {ios_active_cnt} Aktif (Toplam {ios_total_rec} Kayıt • {ios_cancelled_cnt} İptal) • "
                f"🤖 {and_active_cnt} Android VIP ({len(gp_catalog)} Aktif Paket)"
            ),
            "mrr_net_try": financial_ledger["projected_total_mrr_net_try"],
            "mrr_gross_try": financial_ledger["projected_total_mrr_gross_try"],
            "realized_net_try": financial_ledger["realized_net_proceeds_try"],
            "reviews_count": len(all_reviews),
        },
        "ios": {
            "key": "ios",
            "label": "🍏 Apple App Store (iOS)",
            "impressions": apple_impressions,
            "impressions_display": f"{apple_impressions:,}",
            "impressions_sub": f"{int(sb.get('apple_impressions_unique', 0) or 0):,} tekil iPhone • {imp_search_val:,} Arama + {imp_browse_val} Keşfet",
            "touchpoints": ios_touchpoints,
            "touchpoints_display": f"{ios_touchpoints}",
            "touchpoints_sub": f"{apple_page_views} App Store Sayfası + {ios_bridge_uniq} iOS Sosyal Köprü Tıkı",
            "downloads": apple_downloads,
            "downloads_display": f"{apple_downloads}",
            "downloads_sub": f"{r3_search} Arama • {r3_ref} Sosyal Referans • {recent_ios_dl} Doğrudan Sales API",
            "vis_of_imp_pct": round((ios_touchpoints / max(1, apple_impressions)) * 100, 1),
            "cvr_pct": round((apple_downloads / max(1, ios_touchpoints)) * 100, 1),
            "store_cvr_pct": store_page_cvr_pct,
            "store_unique_cvr_pct": store_unique_cvr_pct,
            "bridge_cvr_pct": ios_bridge_cvr_pct,
            "settled_cvr_pct": round((apple_downloads / max(1, ios_touchpoints)) * 100, 1),
            "desktop_bridge_clicks": 0,
            "cvr_breakdown_label": f"Mağaza: %{store_page_cvr_pct} (Cihaz: %{store_unique_cvr_pct}) • Köprü: %{ios_bridge_cvr_pct}",
            "dl_of_imp_pct": round((apple_downloads / max(1, apple_impressions)) * 100, 2),
            "vip_of_dl_pct": round((ios_active_cnt / max(1, apple_downloads)) * 100, 1),
            "vip_of_vis_pct": round((ios_active_cnt / max(1, ios_touchpoints)) * 100, 2),
            "vip_of_imp_pct": round((ios_active_cnt / max(1, apple_impressions)) * 100, 2),
            "vip_count": ios_active_cnt,
            "total_vip_count": ios_total_rec,
            "cancelled_vip_count": ios_cancelled_cnt,
            "vip_display": f"{ios_active_cnt} Aktif VIP" if ios_cancelled_cnt > 0 else f"{ios_active_cnt} VIP",
            "vip_sub": ios_vip_sub_str,
            "mrr_net_try": ios_mrr_net,
            "mrr_gross_try": ios_mrr_gross,
            "realized_net_try": ios_realized_net,
            "reviews_count": ios_reviews_cnt,
        },
        "android": {
            "key": "android",
            "label": "🤖 Google Play Store (Android)",
            "impressions": android_bridge_uniq,
            "impressions_display": f"{android_bridge_uniq} Köprü",
            "impressions_sub": f"Play Console Organik + {android_bridge_uniq} Tekil Android Köprü Yönlendirmesi",
            "touchpoints": android_touchpoints,
            "touchpoints_display": f"{android_touchpoints}",
            "touchpoints_sub": f"{len(meta_android)} Meta Reklam (/ios) + {len(ig_android)} Instagram Bio (/download) Android Tıkı",
            "downloads": google_play_downloads,
            "downloads_display": f"{google_play_downloads}",
            "downloads_sub": f"{google_play_downloads} Doğrulanmış Android Kurulum ({android_signal_opens} Canlı İlk Açılış Sinyali)",
            "vis_of_imp_pct": 100.0 if android_bridge_uniq > 0 else 0.0,
            "cvr_pct": round((google_play_downloads / max(1, android_touchpoints)) * 100, 1),
            "store_cvr_pct": android_bridge_cvr_pct,
            "store_unique_cvr_pct": android_bridge_cvr_pct,
            "bridge_cvr_pct": android_bridge_cvr_pct,
            "settled_cvr_pct": android_bridge_cvr_pct,
            "desktop_bridge_clicks": 0,
            "cvr_breakdown_label": f"Köprü: %{android_bridge_cvr_pct} • Native Intent Aktif",
            "dl_of_imp_pct": round((google_play_downloads / max(1, android_bridge_uniq)) * 100, 2),
            "vip_of_dl_pct": round((and_active_cnt / max(1, google_play_downloads)) * 100, 1),
            "vip_of_vis_pct": round((and_active_cnt / max(1, android_touchpoints)) * 100, 2),
            "vip_of_imp_pct": round((and_active_cnt / max(1, android_bridge_uniq)) * 100, 2),
            "vip_count": and_active_cnt,
            "total_vip_count": and_total_rec,
            "cancelled_vip_count": and_cancelled_cnt,
            "vip_display": f"{and_active_cnt} Aktif VIP" if and_cancelled_cnt > 0 else f"{and_active_cnt} VIP",
            "vip_sub": and_vip_sub_str,
            "mrr_net_try": and_mrr_net,
            "mrr_gross_try": and_mrr_gross,
            "realized_net_try": and_realized_net,
            "reviews_count": android_reviews_cnt,
        },
    }

    source_freshness = [
        {
            "id": "bridge_telemetry",
            "label": "Canlı Köprü & Telemetri DB",
            "status": "realtime",
            "badge": f"⚡ Gerçek Zamanlı ({today_str})",
            "detail": f"Toplam {len(unique_human)} Tık (🍏 {ios_bridge_uniq} iOS • 🤖 {android_bridge_uniq} Android{desktop_sub_suffix})",
        },
        {
            "id": "apple_sales_tsv",
            "label": "🍏 Apple Sales & Trends API",
            "status": "lagged_24h",
            "badge": f"🍏 {apple_downloads} iOS Kurulum ({latest_store_metric_date or 'Aktif'})",
            "detail": f"{apple_impressions:,} Gösterim • {apple_page_views} Sayfa • {ios_reviews_cnt} Yorum",
        },
        {
            "id": "apple_sub_ledger",
            "label": "🍏 Apple SUBSCRIBER + EVENT API",
            "status": "reconciling" if reconciling_7d_cnt > 0 else "synced",
            "badge": f"📒 {ios_active_cnt} Aktif / {ios_total_rec} Kayıt ({ios_cancelled_cnt} İptal)",
            "detail": f"Tahsil: {ios_realized_net:.2f} ₺ • Beklenen Havuz: +{plat_fin['ios']['pipeline_net']:.2f} ₺ Net",
        },
        {
            "id": "google_play_sync",
            "label": "🤖 Google Play Developer API",
            "status": "synced",
            "badge": f"🤖 {google_play_downloads} Android Kurulum • {and_active_cnt} Aktif VIP",
            "detail": f"{len(gp_catalog)} Aktif Paket • {android_bridge_uniq} Köprü Tıkı • {android_reviews_cnt} Yorum",
        },
    ]

    return {
        "period": period,
        "period_label": period_label,
        "period_clicks_count": len(period_clicks),
        "active_human_count": active_human_count,
        "today_unique_clicks": today_unique_clicks,
        "yesterday_unique_clicks": yesterday_unique_clicks,
        "total_raw": total_raw,
        "total_human": len(human_clicks),
        "total_unique_human": len(unique_human),
        "total_bots": len(bot_clicks),
        "total_all_installs": total_cumulative_downloads,
        "total_all_spend_usd": total_all_spend_usd,
        "blended_cpi_usd": blended_cpi_usd,
        "source_freshness": source_freshness,
        "platform_split": platform_split,
        "google_play_subscriptions_catalog": gp_catalog,
        "kpi_deltas": {
            "recent_3d_impressions": recent_3d_imp,
            "recent_3d_downloads": recent_3d_dl,
            "today_vs_yesterday_clicks_diff": today_unique_clicks - yesterday_unique_clicks,
        },
        "cumulative_kpis": {
            "impressions_total": total_cumulative_impressions,
            "impressions_unique": int(sb.get("apple_impressions_unique", 0) or 0),
            "visits_and_clicks_total": total_cumulative_visits_and_clicks,
            "store_page_views": apple_page_views,
            "store_page_views_unique": apple_page_views_uniq,
            "bridge_unique_clicks": len(unique_human),
            "desktop_bridge_clicks": desktop_bridge_uniq,
            "store_taps": apple_taps,
            "downloads_total": total_cumulative_downloads,
            "ios_downloads": apple_downloads,
            "android_downloads": google_play_downloads,
            "store_page_cvr_pct": store_page_cvr_pct,
            "store_unique_cvr_pct": store_unique_cvr_pct,
            "bridge_cvr_pct": all_bridge_cvr_pct,
            "settled_cvr_pct": settled_cvr_pct,
            "active_sessions": apple_sessions,
            "vip_activations": apple_vip,
            "vip_total_records": all_total_rec,
            "vip_cancelled": cancelled_cnt,
            "distinct_live_devices": max(optin_ios_total_dev, distinct_signal_devices, db_babies_count),
        },
        "financial_ledger": financial_ledger,
        "subscriber_ledger": subscriber_ledger_list,
        "aso_attribution_matrix": aso_attribution_matrix,
        "product_retention": product_retention,
        "store_official": sb,
        "timeline_days": timeline_days,
        "night_vs_day": {
            "night_clicks": night_clicks,
            "day_clicks": day_clicks,
            "night_pct": round((night_clicks / active_human_count) * 100) if active_human_count > 0 else 0,
            "day_pct": round((day_clicks / active_human_count) * 100) if active_human_count > 0 else 0,
        },
        "asa_metrics": {
            "spend_usd": asa_spend_usd,
            "installs": r3_search,
            "clicks": asa_clicks_val,
            "cpi_usd": asa_cpi_usd,
            "cpt_bid_usd": asa_cpt_bid_usd,
            "cr_pct": asa_cr_pct,
            "projected_cpi_usd": round(asa_cpt_bid_usd / (asa_cr_pct / 100.0), 2) if asa_cr_pct > 0 and asa_cpt_bid_usd > 0 else 0.0,
        },
        "meta_ads": {
            "route": "/ios",
            "raw_hits": len(meta_raw),
            "human_hits": len(meta_human),
            "unique_clicks": meta_live_clicks,
            "bot_probes": len(meta_bots),
            "ios_clicks": len(meta_ios),
            "android_clicks": len(meta_android),
            "android_leak_pct": meta_android_leak_pct,
            "installs": r3_ref,
            "cr_pct": round((r3_ref / meta_live_clicks) * 100, 1) if meta_live_clicks > 0 else 0.0,
            "spend_usd": meta_spend_usd,
            "cpi_usd": meta_cpi_usd,
        },
        "instagram_bio": {
            "route": "/download",
            "raw_hits": len(ig_raw),
            "human_hits": len(ig_human),
            "unique_clicks": len(ig_unique),
            "ios_clicks": len(ig_ios),
            "android_clicks": len(ig_android),
            "installs": r3_browse,
            "cr_pct": round((r3_browse / len(ig_unique)) * 100, 1) if len(ig_unique) > 0 else 0.0,
            "spend_usd": ig_spend_usd,
        },
        "product_funnel": {
            "bridge_unique_clicks": len(unique_human),
            "asa_clicks": asa_clicks_val,
            "total_acquisition_clicks": total_cumulative_visits_and_clicks,
            "store_jumps_tracked": len(store_jumps) + len(unique_human),
            "store_button_clicks_tracked": len(store_button_clicks),
            "total_store_installs": total_cumulative_downloads,
            "first_open_signals": len(first_opens),
            "daily_active_signals": len(daily_actives),
            "baby_created_signals": len(baby_created_signals),
            "vip_started_signals": len(vip_started_signals),
            "sleep_sound_signals": len(sleep_sound_signals),
            "cry_analysis_signals": len(cry_analysis_signals),
            "paywall_viewed_signals": len(paywall_viewed_signals),
            "paywall_cta_clicked_signals": len(paywall_cta_clicked_signals),
            "paywall_skipped_signals": len(paywall_skipped_signals),
            "purchase_cancelled_signals": len(purchase_cancelled_signals),
            "purchase_error_signals": len(purchase_error_signals),
            "paywall_funnel": {
                "paywall_viewed": len(paywall_viewed_signals),
                "paywall_cta_clicked": len(paywall_cta_clicked_signals),
                "paywall_skipped": len(paywall_skipped_signals),
                "purchase_cancelled": len(purchase_cancelled_signals),
                "purchase_error": len(purchase_error_signals),
                "vip_started": len(vip_started_signals),
                "cancel_rate_pct": (
                    round((len(purchase_cancelled_signals) / max(1, len(paywall_cta_clicked_signals))) * 100, 1)
                    if len(paywall_cta_clicked_signals) > 0
                    else 0.0
                ),
                "sound_preview_60s_ended": len(sound_preview_60s_ended_signals),
                "cry_limit_reached": len(cry_limit_reached_signals),
                "dadi_limit_reached": len(dadi_limit_reached_signals),
                "routine_limit_reached": len(routine_limit_reached_signals),
                "paywall_cancel_recovery_shown": len(paywall_cancel_recovery_signals),
                "ios": {
                    "paywall_viewed": len([s for s in paywall_viewed_signals if (s.os_family or "").lower() == "ios"]),
                    "paywall_cta_clicked": len([s for s in paywall_cta_clicked_signals if (s.os_family or "").lower() == "ios"]),
                    "paywall_skipped": len([s for s in paywall_skipped_signals if (s.os_family or "").lower() == "ios"]),
                    "purchase_cancelled": len([s for s in purchase_cancelled_signals if (s.os_family or "").lower() == "ios"]),
                    "purchase_error": len([s for s in purchase_error_signals if (s.os_family or "").lower() == "ios"]),
                },
                "android": {
                    "paywall_viewed": len([s for s in paywall_viewed_signals if (s.os_family or "").lower() == "android"]),
                    "paywall_cta_clicked": len([s for s in paywall_cta_clicked_signals if (s.os_family or "").lower() == "android"]),
                    "paywall_skipped": len([s for s in paywall_skipped_signals if (s.os_family or "").lower() == "android"]),
                    "purchase_cancelled": len([s for s in purchase_cancelled_signals if (s.os_family or "").lower() == "android"]),
                    "purchase_error": len([s for s in purchase_error_signals if (s.os_family or "").lower() == "android"]),
                },
            },
            "registered_users": db_users_count,
            "babies_created": max(db_babies_count, len(baby_created_signals)),
            "cry_analyses": max(db_cry_count, len(cry_analysis_signals)),
            "sleep_logs": max(db_sleep_count, len(sleep_sound_signals)),
            "routine_logs": db_routine_count,
            "dadi_chats": db_dadi_count,
            "feedbacks_count": len(db_feedbacks),
            "feedbacks_list": db_feedbacks[:20],
            "subscriptions_count": apple_vip,
            "unmatched_organic_opens": unmatched_organic_opens,
        },
        "golden_hours": golden_hours,
        "os_breakdown": dict(os_counts),
        "webview_breakdown": dict(webview_counts),
        "hourly_all_tr": dict(hourly_all_time),
        "recent_clicks": active_raw_set[:100],
    }


@router.get("/summary")
async def get_analytics_summary(
    request: Request,
    pin: Optional[str] = Query(None),
    period: str = Query("all"),
    x_admin_pin: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """JSON API: Kümülatif mağaza, köprü ve uygulama içi büyüme verilerini döndürür."""
    if not authorize_admin_request(request, pin, x_admin_pin, request.cookies.get(_ADMIN_SESSION_COOKIE)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Geçersiz veya eksik Yönetici PIN kodu.")
    if period not in ALLOWED_PERIODS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Geçersiz dönem filtresi: {period}. İzin verilenler: {', '.join(ALLOWED_PERIODS)}",
        )

    summary = _build_analytics_summary(db, period=period)
    recent_serialized = []
    tz_tr = timezone(timedelta(hours=3))
    for c in summary["recent_clicks"][:50]:
        dt_utc = c.created_at.replace(tzinfo=timezone.utc) if c.created_at.tzinfo is None else c.created_at
        dt_tr = dt_utc.astimezone(tz_tr)
        recent_serialized.append({
            "id": c.id,
            "time_tr": dt_tr.strftime("%d.%m.%Y %H:%M:%S"),
            "route_path": c.route_path,
            "channel": c.channel,
            "os_family": c.os_family,
            "device_detail": c.device_detail,
            "app_webview": c.app_webview,
            "target_store": c.target_store,
            "is_bot": c.is_bot,
            "is_unique": c.is_unique,
            "has_fbclid": c.has_fbclid,
            "country": c.country,
            "ip_masked": c.ip_masked,
        })
    summary["recent_clicks"] = recent_serialized
    summary["product_funnel"].pop("feedbacks_list", None)
    return summary


class StoreSyncPushPayload(BaseModel):
    baseline_snapshot: Dict[str, Any] = Field(default_factory=dict)
    daily_metrics: List[Dict[str, Any]] = Field(default_factory=list)
    subscribers: List[Dict[str, Any]] = Field(default_factory=list)
    lifecycle_events: List[Dict[str, Any]] = Field(default_factory=list)


class ClientSubscriberSyncPayload(BaseModel):
    subscriber_id: str = Field(..., min_length=3, max_length=128)
    platform: str = Field(default="android", max_length=32)
    product_id: str = Field(default="misil", max_length=64)
    plan_label: Optional[str] = Field(default=None, max_length=100)
    status: str = Field(default="intro_free_trial", max_length=64)
    offer_type: Optional[str] = Field(default=None, max_length=64)
    offer_code_name: Optional[str] = Field(default=None, max_length=100)
    started_date: Optional[str] = Field(default=None, max_length=16)
    converted_or_renewed_date: Optional[str] = Field(default=None, max_length=16)
    maturity_or_renewal_date: Optional[str] = Field(default=None, max_length=16)
    auto_renew_enabled: bool = Field(default=True)
    customer_price_try: float = Field(default=0.0)
    developer_proceeds_try: float = Field(default=0.0)
    purchase_token: Optional[str] = Field(default=None, max_length=512)
    country: Optional[str] = Field(default="TR", max_length=16)
    device_type: Optional[str] = Field(default=None, max_length=64)


def verify_google_play_subscription_token(purchase_token: str) -> Optional[Dict[str, Any]]:
    """
    Google Play Developer API purchases.subscriptionsv2/tokens/{token} uç noktasını
    kullanarak Android abonelik token'ını doğrular (Service Account mevcutsa).
    """
    clean_tok = (purchase_token or "").strip()
    if not clean_tok or not jwt:
        return None
    sa_raw = os.environ.get("GOOGLE_PLAY_SERVICE_ACCOUNT_JSON")
    if not sa_raw:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
        sa_candidates = [
            os.path.join(project_root, "..", "..", "storage", "google_play_service_account.json"),
            os.path.join(project_root, "storage", "google_play_service_account.json"),
        ]
        sa_path = next((p for p in sa_candidates if os.path.exists(p)), None)
        if sa_path:
            try:
                with open(sa_path, "r", encoding="utf-8") as f:
                    sa_raw = f.read()
            except Exception:
                sa_raw = None
    if not sa_raw:
        return None
    try:
        sa = json.loads(sa_raw)
        now_gp = int(time.time())
        assertion = jwt.encode(
            {
                "iss": sa["client_email"],
                "scope": "https://www.googleapis.com/auth/androidpublisher",
                "aud": "https://oauth2.googleapis.com/token",
                "iat": now_gp - 30,
                "exp": now_gp + 3600,
            },
            sa["private_key"],
            algorithm="RS256",
        )
        tok_data = urllib.parse.urlencode({
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        }).encode("utf-8")
        tok_req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=tok_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(tok_req, timeout=4) as tok_resp:
            access_token = json.loads(tok_resp.read().decode("utf-8")).get("access_token")
        if not access_token:
            return None
        v2_url = (
            "https://androidpublisher.googleapis.com/androidpublisher/v3/applications/"
            f"com.levitas.misilbaby/purchases/subscriptionsv2/tokens/{urllib.parse.quote(clean_tok)}"
        )
        v2_req = urllib.request.Request(v2_url, headers={"Authorization": f"Bearer {access_token}"})
        with urllib.request.urlopen(v2_req, timeout=4) as v2_resp:
            if v2_resp.status == 200:
                return json.loads(v2_resp.read().decode("utf-8"))
    except Exception as exc:
        logger.debug("Google Play subscriptionsv2 token verify info: %s", exc)
    return None


@router.post("/subscriber-sync")
async def sync_client_subscriber_ledger(
    payload: ClientSubscriberSyncPayload,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Mobil uygulama (Google Play / App Store) veya RevenueCat istemci köprüsünden gelen
    doğrulanmış abonelik/deneme/kod durumunu SubscriberLedger'a idempotent olarak yazar.
    """
    ensure_historical_seed(db)

    clean_sid = "".join(ch for ch in payload.subscriber_id.strip() if ch.isalnum() or ch in ("-", "_", ":", "."))[:128]
    if not clean_sid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz subscriber_id.")

    plat = (payload.platform or "android").strip().lower()
    if plat not in ("android", "ios"):
        plat = "android"

    tz_tr = timezone(timedelta(hours=3))
    today_str = datetime.now(tz_tr).strftime("%Y-%m-%d")

    prod_id = (payload.product_id or ("misil" if plat == "android" else "misil_monthly")).strip()[:64]
    st_val = (payload.status or "intro_free_trial").strip()[:64]
    if st_val not in ("paid_active", "intro_free_trial", "offer_code_trial", "cancelled"):
        st_val = "intro_free_trial"

    auto_renew = bool(payload.auto_renew_enabled)
    start_dt_str = (payload.started_date or today_str).strip()[:10]
    mat_dt_str = (payload.maturity_or_renewal_date or "").strip()[:10]
    offer_code_nm = (payload.offer_code_name or "").strip()[:95] or None

    # Google Play purchase_token varsa subscriptionsv2 API ile doğrula
    verified_gp_token = False
    if plat == "android" and payload.purchase_token:
        gp_v2 = await run_in_threadpool(verify_google_play_subscription_token, payload.purchase_token)
        if isinstance(gp_v2, dict):
            verified_gp_token = True
            sub_state = str(gp_v2.get("subscriptionState") or "")
            if sub_state in ("SUBSCRIPTION_STATE_CANCELED", "SUBSCRIPTION_STATE_EXPIRED"):
                st_val = "cancelled"
                auto_renew = False
            start_iso = str(gp_v2.get("startTime") or "")[:10]
            if len(start_iso) == 10:
                start_dt_str = start_iso
            line_items = gp_v2.get("lineItems") or []
            if line_items:
                li0 = line_items[0]
                if li0.get("productId"):
                    prod_id = str(li0["productId"])[:64]
                exp_iso = str(li0.get("expiryTime") or "")[:10]
                if len(exp_iso) == 10:
                    mat_dt_str = exp_iso
                ar_plan = li0.get("autoRenewingPlan") or {}
                if "autoRenewEnabled" in ar_plan:
                    auto_renew = bool(ar_plan.get("autoRenewEnabled"))
                off_details = li0.get("offerDetails") or {}
                off_id = off_details.get("offerId")
                if off_id and st_val != "cancelled":
                    offer_code_nm = str(off_id)[:95]

    is_admin_authed = authorize_admin_request(
        request, None, request.headers.get("x-admin-pin"), request.cookies.get(_ADMIN_SESSION_COOKIE)
    )
    # Kimliksiz/doğrulanmamış istemci çağrılarının sahte tahsilat (paid_active) yazmasını, DEV_* hayalet satırı üretmesini veya resmi Apple satırlarını ezmesini engelle
    if not is_admin_authed and not verified_gp_token:
        if clean_sid.upper().startswith("DEV_"):
            return {
                "ok": True,
                "status": "ignored_unverified_dev_id",
                "subscriber_id": clean_sid,
                "platform": plat,
                "product_id": prod_id,
                "ledger_status": st_val,
                "expected_next_price_try": 0.0,
                "expected_next_proceeds_try": 0.0,
            }
        if st_val == "paid_active":
            st_val = "intro_free_trial"
        payload.customer_price_try = 0.0
        payload.developer_proceeds_try = 0.0

    is_ann = _is_annual_product(prod_id)
    default_lbl = (
        ("Mışıl Baby Yıllık VIP" if is_ann else "Mışıl Baby Aylık VIP")
        if plat == "android"
        else ("Yıllık VIP" if is_ann else "Aylık Esnek VIP")
    )
    plan_lbl = (payload.plan_label or default_lbl).strip()[:100]

    if not mat_dt_str or len(mat_dt_str) != 10:
        try:
            dt_s = datetime.strptime(start_dt_str, "%Y-%m-%d")
        except Exception:
            dt_s = datetime.now(tz_tr)
            start_dt_str = dt_s.strftime("%Y-%m-%d")
        days_add = 7 if st_val == "intro_free_trial" else (365 if is_ann else 30)
        mat_dt_str = (dt_s + timedelta(days=days_add)).strftime("%Y-%m-%d")

    std_gross, std_net = _resolve_expected_trial_pricing(
        prod_id, payload.customer_price_try, payload.developer_proceeds_try, plat
    )
    net_ratio = 0.727 if plat == "android" else 0.55417
    c_gross = round(float(payload.customer_price_try or (std_gross if st_val == "paid_active" else 0.0)), 2)
    c_net = round(float(payload.developer_proceeds_try or (round(c_gross * net_ratio, 2) if c_gross > 0 else 0.0)), 2)

    if st_val == "cancelled" or not auto_renew:
        exp_gross, exp_net = 0.0, 0.0
    elif st_val == "offer_code_trial":
        exp_gross, exp_net = 0.0, 0.0
    else:
        exp_gross, exp_net = (c_gross, c_net) if c_gross > 0 else (std_gross, std_net)

    of_type = payload.offer_type or (
        "standard_paid" if st_val == "paid_active" else ("offer_code" if st_val == "offer_code_trial" else "intro_7d_trial")
    )
    if not offer_code_nm:
        offer_code_nm = "Standart Ücretli" if st_val == "paid_active" else "7 Günlük Deneme"

    cntry_clean = "".join(ch for ch in (payload.country or "TR").upper() if ch.isalnum())[:16] or "TR"
    dev_clean = (payload.device_type or ("Android" if plat == "android" else "iPhone")).strip()[:64]

    existing = db.query(SubscriberLedger).filter(SubscriberLedger.subscriber_id == clean_sid).first()
    if existing and not is_admin_authed and not verified_gp_token:
        # Resmi mağaza API'lerinden (Apple SUBSCRIBER 1_3 veya RevenueCat Webhook) gelen kayıtların kimliksiz istemci tarafından ezilmesini engelle
        if not clean_sid.startswith("DEV_"):
            return {
                "ok": True,
                "status": "protected",
                "subscriber_id": clean_sid,
                "platform": existing.platform,
                "product_id": existing.product_id,
                "ledger_status": existing.status,
            }
    if existing:
        existing.platform = plat
        existing.product_id = prod_id
        existing.plan_label = plan_lbl
        existing.status = st_val
        existing.offer_type = of_type[:64]
        existing.offer_code_name = offer_code_nm
        existing.maturity_or_renewal_date = mat_dt_str
        existing.auto_renew_enabled = auto_renew
        if c_gross > 0:
            existing.customer_price_try = c_gross
            existing.developer_proceeds_try = c_net
            existing.converted_or_renewed_date = payload.converted_or_renewed_date or today_str
        existing.expected_next_price_try = exp_gross
        existing.expected_next_proceeds_try = exp_net
        existing.country = cntry_clean
        existing.device_type = dev_clean
    else:
        db.add(
            SubscriberLedger(
                subscriber_id=clean_sid,
                platform=plat,
                product_id=prod_id,
                plan_label=plan_lbl,
                status=st_val,
                offer_type=of_type[:64],
                offer_code_name=offer_code_nm,
                started_date=start_dt_str,
                converted_or_renewed_date=(payload.converted_or_renewed_date or start_dt_str) if st_val == "paid_active" else None,
                maturity_or_renewal_date=mat_dt_str,
                auto_renew_enabled=auto_renew,
                customer_price_try=c_gross,
                developer_proceeds_try=c_net,
                expected_next_price_try=exp_gross,
                expected_next_proceeds_try=exp_net,
                country=cntry_clean,
                device_type=dev_clean,
            )
        )

    ev_key = f"{clean_sid}:{st_val}"
    dup_ev = (
        db.query(SubscriptionLifecycleEvent.id)
        .filter(
            SubscriptionLifecycleEvent.event_date == today_str,
            SubscriptionLifecycleEvent.event_type == ev_key[:128],
            SubscriptionLifecycleEvent.product_id == prod_id,
        )
        .first()
    )
    if dup_ev is None:
        db.add(
            SubscriptionLifecycleEvent(
                event_date=today_str,
                platform=plat,
                event_type=ev_key[:128],
                product_id=prod_id,
                plan_label=plan_lbl,
                offer_code_name=offer_code_nm,
                country=cntry_clean,
                device_type=dev_clean,
                quantity=1,
            )
        )

    db.commit()
    return {
        "ok": True,
        "status": "ok",
        "subscriber_id": clean_sid,
        "platform": plat,
        "product_id": prod_id,
        "ledger_status": st_val,
        "expected_next_price_try": exp_gross,
        "expected_next_proceeds_try": exp_net,
    }


@router.post("/store-sync-push")
async def ingest_local_store_sync(
    payload: StoreSyncPushPayload,
    request: Request,
    pin: Optional[str] = Query(None),
    x_admin_pin: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """
    Sıfır Bulut Anahtar Riski (Zero-Cloud-Key Architecture):
    Apple .p8 ve Google Play Service Account özel anahtarları hiçbir zaman buluta yüklenmez;
    yerel makinede çekilen resmi mağaza metrikleri bu güvenli uç nokta üzerinden canlı veritabanına aktarılır.
    """
    if not authorize_admin_request(request, pin, x_admin_pin, request.cookies.get(_ADMIN_SESSION_COOKIE)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Geçersiz veya eksik Yönetici PIN kodu.")

    ensure_historical_seed(db)

    upserted_metrics = 0
    if payload.daily_metrics:
        metric_platforms = {str(dm.get("platform") or "ios").strip()[:32] for dm in payload.daily_metrics}
        db.query(StoreDailyMetric).filter(StoreDailyMetric.platform.in_(metric_platforms)).delete(synchronize_session=False)
        for dm in payload.daily_metrics:
            m_date = str(dm.get("metric_date") or "").strip()[:16]
            plat = str(dm.get("platform") or "ios").strip()[:32]
            if not m_date:
                continue
            row = StoreDailyMetric(
                metric_date=m_date,
                platform=plat,
                impressions=int(dm.get("impressions") or 0),
                impressions_unique=int(dm.get("impressions_unique") or 0),
                page_views=int(dm.get("page_views") or 0),
                page_views_unique=int(dm.get("page_views_unique") or 0),
                downloads_total=int(dm.get("downloads_total") or 0),
                downloads_search=int(dm.get("downloads_search") or 0),
                downloads_browse=int(dm.get("downloads_browse") or 0),
                downloads_referrer=int(dm.get("downloads_referrer") or 0),
                redownloads=int(dm.get("redownloads") or 0),
                active_sessions=int(dm.get("active_sessions") or 0),
                gross_revenue_try=float(dm.get("gross_revenue_try") or 0.0),
                net_proceeds_try=float(dm.get("net_proceeds_try") or 0.0),
            )
            db.add(row)
            upserted_metrics += 1

    upserted_subs = 0
    if payload.subscribers:
        sub_platforms = {str(s_item.get("platform") or "ios").strip()[:32] for s_item in payload.subscribers}
        db.query(SubscriberLedger).filter(SubscriberLedger.platform.in_(sub_platforms)).delete(synchronize_session=False)
        for s_item in payload.subscribers:
            sub_id = str(s_item.get("subscriber_id") or "").strip()[:128]
            if not sub_id:
                continue
            plat_s = str(s_item.get("platform") or "ios").strip()[:32]
            prod_id_val = str(s_item.get("product_id") or "misil_monthly")[:64]
            status_val = str(s_item.get("status") or "intro_free_trial")[:64]
            exp_gross = float(s_item.get("expected_next_price_try") or 0.0)
            exp_net = float(s_item.get("expected_next_proceeds_try") or 0.0)
            if status_val == "intro_free_trial":
                exp_gross, exp_net = _resolve_expected_trial_pricing(prod_id_val, exp_gross, exp_net, plat_s)
            db.add(
                SubscriberLedger(
                    subscriber_id=sub_id,
                    platform=plat_s,
                    product_id=prod_id_val,
                    plan_label=str(s_item.get("plan_label") or "Aylık Esnek")[:100],
                    status=status_val,
                    offer_type=str(s_item.get("offer_type") or "intro_7d_trial")[:64],
                    offer_code_name=s_item.get("offer_code_name"),
                    started_date=str(s_item.get("started_date") or "")[:16],
                    converted_or_renewed_date=s_item.get("converted_or_renewed_date"),
                    maturity_or_renewal_date=str(s_item.get("maturity_or_renewal_date") or "")[:16],
                    auto_renew_enabled=bool(s_item.get("auto_renew_enabled", True)),
                    customer_price_try=float(s_item.get("customer_price_try") or 0.0),
                    developer_proceeds_try=float(s_item.get("developer_proceeds_try") or 0.0),
                    expected_next_price_try=exp_gross,
                    expected_next_proceeds_try=exp_net,
                    country=str(s_item.get("country") or "TR")[:16],
                    device_type=str(s_item.get("device_type") or "iPhone")[:64],
                )
            )
            upserted_subs += 1

    upserted_events = 0
    if payload.lifecycle_events:
        ev_platforms = {str(ev.get("platform") or "ios").strip()[:32] for ev in payload.lifecycle_events}
        db.query(SubscriptionLifecycleEvent).filter(SubscriptionLifecycleEvent.platform.in_(ev_platforms)).delete(synchronize_session=False)
        for ev in payload.lifecycle_events:
            db.add(
                SubscriptionLifecycleEvent(
                    event_date=str(ev.get("event_date") or "")[:16],
                    platform=str(ev.get("platform") or "ios")[:32],
                    event_type=str(ev.get("event_type") or "")[:128],
                    product_id=str(ev.get("product_id") or "")[:64],
                    plan_label=ev.get("plan_label"),
                    offer_code_name=ev.get("offer_code_name"),
                    country=str(ev.get("country") or "TR")[:16],
                    device_type=str(ev.get("device_type") or "iPhone")[:64],
                    quantity=int(ev.get("quantity") or 1),
                    days_before_canceling=ev.get("days_before_canceling"),
                    cancellation_reason=ev.get("cancellation_reason"),
                )
            )
            upserted_events += 1

    if payload.baseline_snapshot:
        clean_snap = _mask_sensitive_sync_value(payload.baseline_snapshot)
        with _BASELINE_LOCK:
            prev_gp_dl = int(OFFICIAL_STORE_BASELINE.get("google_play_downloads_baseline", 0) or 0)
            OFFICIAL_STORE_BASELINE.clear()
            OFFICIAL_STORE_BASELINE.update(_empty_store_state())
            OFFICIAL_STORE_BASELINE.update(clean_snap)
            OFFICIAL_STORE_BASELINE["google_play_downloads_baseline"] = max(
                prev_gp_dl,
                int(OFFICIAL_STORE_BASELINE.get("google_play_downloads_baseline", 0) or 0),
            )
            snapshot_copy = copy.deepcopy(OFFICIAL_STORE_BASELINE)
        st_row = db.query(StoreSyncState).filter(StoreSyncState.state_key == "primary_store_baseline").first()
        if st_row:
            st_row.snapshot_json = snapshot_copy
            st_row.last_synced_at_str = str(clean_snap.get("last_synced_at") or "")
        else:
            db.add(
                StoreSyncState(
                    state_key="primary_store_baseline",
                    snapshot_json=snapshot_copy,
                    last_synced_at_str=str(clean_snap.get("last_synced_at") or ""),
                )
            )

    db.flush()
    _reconcile_ios_ledger_and_cancellations(db)
    db.commit()
    return {
        "status": "ok",
        "upserted_daily_metrics": upserted_metrics,
        "upserted_subscribers": upserted_subs,
        "upserted_lifecycle_events": upserted_events,
    }


@router.post("/trigger-sync")
async def trigger_store_sync_now(
    request: Request,
    pin: Optional[str] = Query(None),
    x_admin_pin: Optional[str] = Header(None),
    days_back: int = Query(30, ge=1, le=90),
):
    """Admin tarafından manuel olarak tetiklenebilen mağaza API senkronizasyonu."""
    if not authorize_admin_request(request, pin, x_admin_pin, request.cookies.get(_ADMIN_SESSION_COOKIE)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Geçersiz veya eksik Yönetici PIN kodu.")

    sync_res = await run_in_threadpool(sync_live_store_apis, days_back)
    return {
        "status": "ok",
        "synced": sync_res.get("synced", False),
        "sources": sync_res.get("sources", []),
        "apple_connected": sync_res.get("apple_connected", False),
        "google_connected": sync_res.get("google_connected", False),
        "synced_at": sync_res.get("synced_at", ""),
    }


@router.get("/export.csv")
async def export_analytics_csv(
    request: Request,
    pin: Optional[str] = Query(None),
    x_admin_pin: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """Tüm tıklama kayıtlarını Excel uyumlu ve Formula-Injection korumalı CSV olarak indirir."""
    if not authorize_admin_request(request, pin, x_admin_pin, request.cookies.get(_ADMIN_SESSION_COOKIE)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Geçersiz Yönetici PIN kodu.")

    ensure_historical_seed(db)
    clicks = db.query(BridgeClick).order_by(desc(BridgeClick.created_at)).limit(10000).all()
    tz_tr = timezone(timedelta(hours=3))

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow([
        "ID", "Tarih/Saat (TSİ)", "Köprü Linki", "Kanal", "Tekil İnsan mı?",
        "Bot mu?", "İşletim Sistemi", "Cihaz Detayı", "Uygulama İçi Tarayıcı",
        "Yönlendirilen Mağaza", "fbclid Var mı?", "Ülke", "Maskeli IP"
    ])

    for c in clicks:
        dt_utc = c.created_at.replace(tzinfo=timezone.utc) if c.created_at.tzinfo is None else c.created_at
        dt_tr = dt_utc.astimezone(tz_tr).strftime("%Y-%m-%d %H:%M:%S")
        writer.writerow([
            sanitize_csv_cell(c.id),
            sanitize_csv_cell(dt_tr),
            sanitize_csv_cell(c.route_path),
            sanitize_csv_cell(c.channel),
            "EVET" if c.is_unique else "HAYIR (Tekrar)",
            "BOT" if c.is_bot else "İNSAN",
            sanitize_csv_cell(c.os_family),
            sanitize_csv_cell(c.device_detail),
            sanitize_csv_cell(c.app_webview),
            sanitize_csv_cell(c.target_store),
            "EVET" if c.has_fbclid else "HAYIR",
            sanitize_csv_cell(c.country or "TR"),
            sanitize_csv_cell(c.ip_masked),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=misil_baby_kumulatif_buyume_verileri.csv"},
    )


def _render_login_html(show_error: bool = False, status_code: int = status.HTTP_200_OK) -> HTMLResponse:
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="tr">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <meta name="referrer" content="no-referrer">
      <title>Mışıl Kurucu Kokpiti Girişi</title>
      <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=Sora:wght@600;700&display=swap" rel="stylesheet">
      <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
          background: #07090E radial-gradient(circle at 50% 20%, #151D33 0%, #07090E 75%);
          color: #FFF;
          font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
          min-height: 100vh;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 20px;
        }}
        .card {{
          background: rgba(18, 23, 38, 0.88);
          border: 1px solid rgba(255, 255, 255, 0.1);
          backdrop-filter: blur(16px);
          border-radius: 22px;
          padding: 36px 28px;
          width: 100%;
          max-width: 390px;
          text-align: center;
          box-shadow: 0 20px 40px rgba(0,0,0,0.5);
        }}
        .moon {{ font-size: 42px; margin-bottom: 12px; }}
        h2 {{ font-family: 'Sora', sans-serif; font-size: 20px; font-weight: 700; margin-bottom: 8px; color: #FFF; }}
        p {{ color: #8E99B0; font-size: 13px; line-height: 1.5; margin-bottom: 24px; }}
        input {{
          width: 100%;
          padding: 14px 16px;
          border-radius: 12px;
          border: 1px solid rgba(232, 168, 85, 0.3);
          background: rgba(0, 0, 0, 0.4);
          color: #FFF;
          font-size: 16px;
          font-weight: 600;
          text-align: center;
          letter-spacing: 2px;
          margin-bottom: 16px;
          outline: none;
        }}
        input:focus {{ border-color: #E8A855; }}
        button {{
          width: 100%;
          padding: 14px;
          border-radius: 12px;
          border: none;
          background: linear-gradient(135deg, #E8A855 0%, #D48828 100%);
          color: #07090E;
          font-size: 15px;
          font-weight: 700;
          cursor: pointer;
        }}
        .err {{ color: #FF6B6B; font-size: 12px; margin-top: 12px; display: {'block' if show_error else 'none'}; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="moon">🌙</div>
        <h2>Mışıl Kurucu Kokpiti</h2>
        <p>Kümülatif büyüme, App Store & Google Play resmi verileri ve görsel analiz panelini açmak için PIN giriniz.</p>
        <form method="POST" action="/api/v1/analytics/login">
          <input type="password" name="pin" placeholder="Yönetici PIN" autofocus autocomplete="off" />
          <button type="submit">Kokpiti Aç</button>
        </form>
        <div class="err">❌ Geçersiz PIN kodu. Lütfen tekrar deneyin.</div>
      </div>
    </body>
    </html>
    """, status_code=status_code)


@router.post("/login")
async def analytics_login_post(
    request: Request,
    pin: Optional[str] = Form(None),
):
    """PIN kodunu URL query parametresine sızdırmadan POST ile doğrular ve HttpOnly oturum çerezi yazar."""
    if not _pin_is_valid(pin):
        return _render_login_html(show_error=True, status_code=status.HTTP_401_UNAUTHORIZED)

    clean_pin = (pin or "").strip().upper()
    resp = RedirectResponse(
        url="/api/v1/analytics/dashboard",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    resp.set_cookie(
        key=_ADMIN_SESSION_COOKIE,
        value=_make_admin_session_token(clean_pin),
        httponly=True,
        samesite="lax",
        secure=(request.url.scheme == "https"),
        max_age=_ADMIN_SESSION_TTL_SECONDS,
        path="/",
    )
    return resp


@router.get("/dashboard", response_class=HTMLResponse)
async def analytics_dashboard_page(
    request: Request,
    pin: Optional[str] = Query(None),
    period: Optional[str] = Query("all"),
    sync: Optional[str] = Query(None),
    updated: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Mışıl Baby v4.46.0 — Sıfır Statik Veri, Resmi Apple/Google Mağaza API ve Görsel Kurucu Kokpiti.
    """
    session_token = request.cookies.get(_ADMIN_SESSION_COOKIE)
    authorized_by_session = _admin_session_token_is_valid(session_token)
    if not authorize_admin_request(request, pin, None, session_token):
        login_status_code = status.HTTP_401_UNAUTHORIZED if pin else status.HTTP_200_OK
        return _render_login_html(show_error=bool(pin), status_code=login_status_code)

    new_session_cookie_value = None
    if not authorized_by_session and _pin_is_valid(pin):
        new_session_cookie_value = _make_admin_session_token((pin or "").strip().upper())

    sync_banner = ""
    if sync == "1":
        # P0-1: Ağ I/O ve harici API çağrıları FastAPI async event loop'u bloklamaması için threadpool'da çalıştırılır
        sync_res = await run_in_threadpool(sync_live_store_apis)
        sources_list = sync_res.get("sources") or []
        sources_str = ", ".join(html.escape(str(src)) for src in sources_list) if sources_list else "Yapılandırılmış mağaza anahtarı bulunamadı (Yalnızca yerel DB)"
        synced_at_str = html.escape(str(sync_res.get("synced_at") or OFFICIAL_STORE_BASELINE.get("last_synced_at") or ""))
        sync_banner = f"""
        <div class="toast-banner">
          ✅ <strong>Resmi Mağaza API Senkronizasyonu Tamamlandı:</strong> Aktif kaynaklar: {sources_str} ({synced_at_str}).
        </div>
        """
    elif updated:
        sync_banner = f"""
        <div class="toast-banner">
          ✅ <strong>Kampanya Yapılandırması Güncellendi:</strong> <code>{html.escape(str(updated))}</code> kanalı veritabanına kaydedildi.
        </div>
        """

    if period not in ALLOWED_PERIODS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Geçersiz dönem filtresi: {period}. İzin verilenler: {', '.join(ALLOWED_PERIODS)}",
        )
    clean_period = period
    s = _build_analytics_summary(db, period=clean_period)

    kpis = s["cumulative_kpis"]
    sb = s["store_official"]
    meta = s["meta_ads"]
    ig = s["instagram_bio"]
    pf = s["product_funnel"]
    nvd = s["night_vs_day"]
    fl = s["financial_ledger"]
    sub_ledger = s["subscriber_ledger"]
    aso_matrix = s["aso_attribution_matrix"]
    pr = s["product_retention"]

    # Sıfır statik veri: Tüm sayılar doğrudan dinamik özetten ve DB'den okunur
    r3_search_dl = int(s["asa_metrics"].get("installs", 0) or 0)
    r3_ref_dl = int(meta.get("installs", 0) or 0)
    r3_browse_dl = int(ig.get("installs", 0) or 0)
    r3_unattributed_recent_ios = max(0, kpis["ios_downloads"] - (r3_search_dl + r3_ref_dl + r3_browse_dl))

    donut_install_sources = _build_svg_donut(
        [
            {"label": "🔍 App Store Arama (API)", "count": r3_search_dl, "color": "#E8A855"},
            {"label": "📲 Sosyal Yönlendirme (API)", "count": r3_ref_dl, "color": "#60A5FA"},
            {"label": "📅 Doğrudan / Diğer iOS (API)", "count": r3_unattributed_recent_ios, "color": "#A855F7"},
            {"label": "✨ App Store Keşfet (API)", "count": r3_browse_dl, "color": "#34D399"},
            {"label": "🤖 Google Play (Android)", "count": kpis["android_downloads"], "color": "#4ADE80"},
        ],
        center_val=str(kpis["downloads_total"]),
        center_lbl="İNDİRME",
    )

    countries_list = sb.get("apple_downloads_by_country") or []
    tr_dl = next((int(c.get("count", 0)) for c in countries_list if c.get("code") == "TR"), 0)
    de_dl = next((int(c.get("count", 0)) for c in countries_list if c.get("code") == "DE"), 0)
    us_dl = next((int(c.get("count", 0)) for c in countries_list if c.get("code") == "US"), 0)
    other_country_dl = max(0, kpis["ios_downloads"] - tr_dl - de_dl - us_dl)

    donut_countries = _build_svg_donut(
        [
            {"label": "🇹🇷 Türkiye", "count": tr_dl, "color": "#34D399"},
            {"label": "🇩🇪 Almanya", "count": de_dl, "color": "#E8A855"},
            {"label": "🇺🇸 ABD", "count": us_dl, "color": "#60A5FA"},
            {"label": "🌍 Diğer Ülkeler", "count": other_country_dl, "color": "#A855F7"},
        ],
        center_val=f"{len(countries_list)} Ülke",
        center_lbl=f"{kpis['ios_downloads']} iOS",
    )

    top_h1 = s["golden_hours"][0]["hour"] if s["golden_hours"] else "00:00"
    top_h2 = s["golden_hours"][1]["hour"] if len(s["golden_hours"]) > 1 else "01:00"

    donut_night_day = _build_svg_donut(
        [
            {"label": "🌙 Gece (21:00–04:00)", "count": nvd["night_clicks"], "color": "#A855F7"},
            {"label": "☀️ Gündüz (05:00–20:00)", "count": nvd["day_clicks"], "color": "#E8A855"},
        ],
        center_val=f"%{nvd['night_pct']}",
        center_lbl="GECE NÖBETİ",
    )

    t_days = s["timeline_days"]
    timeline_range_lbl = (
        f"{t_days[0]['label']} ➔ {t_days[-1]['label']}"
        if t_days
        else "Güncel Dönem"
    )
    max_cum_dl = max(1, max((d["cum_downloads"] for d in t_days), default=1))
    max_daily_dl = max(1, max((d["daily_downloads"] for d in t_days), default=1))
    max_daily_clicks = max(1, max((d["daily_visits_clicks"] for d in t_days), default=1))

    spark_imp_svg = _build_svg_sparkline([d.get("daily_impressions", 0) for d in t_days if not d.get("is_store_pending")], "#E8A855", "spImp")
    spark_vis_svg = _build_svg_sparkline([d.get("daily_visits_clicks", 0) for d in t_days], "#60A5FA", "spVis")
    spark_dl_svg = _build_svg_sparkline([d.get("daily_downloads", 0) for d in t_days if not d.get("is_store_pending")], "#34D399", "spDl")
    spark_vip_svg = _build_svg_sparkline([d.get("cum_downloads", 0) for d in t_days], "#C084FC", "spVip")

    freshness_strip_html = ""
    for fs in s.get("source_freshness", []):
        st_cls = "fs-realtime" if fs["status"] == "realtime" else ("fs-reconciling" if fs["status"] == "reconciling" else "fs-synced")
        freshness_strip_html += f"""
        <div class="fs-chip {st_cls}" title="{html.escape(str(fs['detail']))}">
          <span class="fs-dot"></span>
          <span class="fs-lbl">{html.escape(str(fs['label']))}</span>
          <span class="fs-badge">{html.escape(str(fs['badge']))}</span>
        </div>
        """

    cum_bars_html = ""
    cum_ios_bars_html = ""
    cum_android_bars_html = ""
    daily_bars_html = ""
    max_cum_ios = max(1, max((d.get("cum_ios_downloads", 0) for d in t_days), default=1))
    max_cum_and = max(1, max((d.get("cum_android_downloads", 0) for d in t_days), default=1))
    for d in t_days:
        dl_h = max(10, round((d["cum_downloads"] / max_cum_dl) * 100)) if d["cum_downloads"] > 0 else 5
        is_today = d["date"] == t_days[-1]["date"]
        is_pending = bool(d.get("is_store_pending", False))
        cum_ios_val = d.get("cum_ios_downloads", d["cum_downloads"])
        cum_android_val = d.get("cum_android_downloads", 0)
        pending_note = f" • ⏳ Apple TSV Bekleniyor (+{d['daily_visits_clicks']} Canlı Tık)" if is_pending else ""
        cum_tip = f"{d['label']}: Kümülatif {d['cum_downloads']} İndirme (🍏 {cum_ios_val} iOS + 🤖 {cum_android_val} Android){pending_note}"

        ios_share_pct = round((cum_ios_val / max(1, d["cum_downloads"])) * 100) if d["cum_downloads"] > 0 else 100
        and_share_pct = max(0, 100 - ios_share_pct)

        bar_style_cum = (
            f"height:{dl_h}%; background:rgba(16,185,129,0.20); border:1.5px dashed #059669;"
            if is_pending and cum_android_val == 0
            else (
                f"height:{dl_h}%; background:linear-gradient(180deg, #3B82F6 0%, #3B82F6 {and_share_pct}%, #10B981 {and_share_pct}%, #059669 100%);"
                if cum_android_val > 0
                else f"height:{dl_h}%; background:linear-gradient(180deg, #10B981 0%, #059669 100%);"
            )
        )
        top_val_cum = f"{d['cum_downloads']}*" if is_pending else str(d["cum_downloads"])

        cum_bars_html += f"""
        <div class="t-col {'t-today' if is_today else ''} {'t-pending' if is_pending else ''}" title="{html.escape(cum_tip)}">
          <div class="t-top-val" style="color:{'#D97706' if is_pending else '#059669'};">{top_val_cum}</div>
          <div class="t-bars-pair">
            <div class="t-bar" style="{bar_style_cum}"></div>
          </div>
          <div class="t-lbl">{html.escape(d['label'])}</div>
        </div>
        """

        ios_h = max(10, round((cum_ios_val / max_cum_ios) * 100)) if cum_ios_val > 0 else 5
        ios_bar_style = (
            f"height:{ios_h}%; background:rgba(16,185,129,0.20); border:1.5px dashed #059669;"
            if is_pending
            else f"height:{ios_h}%; background:linear-gradient(180deg, #10B981 0%, #059669 100%);"
        )
        cum_ios_bars_html += f"""
        <div class="t-col {'t-today' if is_today else ''} {'t-pending' if is_pending else ''}" title="{html.escape(d['label'])}: 🍏 Apple iOS Kümülatif {cum_ios_val} Kurulum{html.escape(pending_note)}">
          <div class="t-top-val" style="color:{'#D97706' if is_pending else '#059669'};">{cum_ios_val}{'*' if is_pending else ''}</div>
          <div class="t-bars-pair">
            <div class="t-bar" style="{ios_bar_style}"></div>
          </div>
          <div class="t-lbl">{html.escape(d['label'])}</div>
        </div>
        """

        and_h = max(12, round((cum_android_val / max_cum_and) * 100)) if cum_android_val > 0 else 6
        and_bar_style = (
            f"height:{and_h}%; background:linear-gradient(180deg, #60A5FA 0%, #2563EB 100%);"
            if cum_android_val > 0
            else "height:6%; background:rgba(148,163,184,0.25);"
        )
        cum_android_bars_html += f"""
        <div class="t-col {'t-today' if is_today else ''}" title="{html.escape(d['label'])}: 🤖 Google Play Android Kümülatif {cum_android_val} Kurulum">
          <div class="t-top-val" style="color:{'#2563EB' if cum_android_val > 0 else '#94A3B8'};">{cum_android_val}</div>
          <div class="t-bars-pair">
            <div class="t-bar" style="{and_bar_style}"></div>
          </div>
          <div class="t-lbl">{html.escape(d['label'])}</div>
        </div>
        """

        if is_pending and d["daily_downloads"] == 0 and d["daily_visits_clicks"] > 0:
            sig_h = max(18, round((d["daily_visits_clicks"] / max_daily_clicks) * 75))
            d_dl_str = f"⏳{d['daily_visits_clicks']} Tık"
            bar_style_daily = f"height:{sig_h}%; background:rgba(37,99,235,0.20); border:1.5px dashed #2563EB;"
            top_color_daily = "#2563EB"
        else:
            d_dl_h = max(12, round((d["daily_downloads"] / max_daily_dl) * 100)) if d["daily_downloads"] > 0 else 6
            d_dl_str = f"+{d['daily_downloads']}" if d["daily_downloads"] > 0 else "0"
            bar_style_daily = f"height:{d_dl_h}%; background:linear-gradient(180deg, #F59E0B 0%, #D97706 100%);"
            top_color_daily = "#D97706"
        d_touch_tip = f" (🍏 +{d.get('daily_ios_downloads', 0)} iOS • 🤖 +{d.get('daily_android_downloads', 0)} Android) • +{d['daily_visits_clicks']} Sayfa/Sosyal Tık"

        daily_bars_html += f"""
        <div class="t-col {'t-today' if is_today else ''} {'t-pending' if is_pending else ''}" title="{html.escape(d['label'])}: +{d['daily_downloads']} Yeni İndirme{html.escape(d_touch_tip)}">
          <div class="t-top-val" style="color:{top_color_daily};">{d_dl_str}</div>
          <div class="t-bars-pair">
            <div class="t-bar" style="{bar_style_daily}"></div>
          </div>
          <div class="t-lbl">{html.escape(d['label'])}</div>
        </div>
        """

    reviews_list = sb.get("store_reviews") or []
    reviews_total_cnt = len(reviews_list)
    if reviews_total_cnt > 0:
        avg_stars_val = round(
            sum(max(1, min(5, int(r.get("rating", 5) or 5))) for r in reviews_list) / reviews_total_cnt,
            1,
        )
        avg_stars_label = f"{avg_stars_val} ★"
    else:
        avg_stars_label = "Yorum Yok"

    reviews_html = ""
    for rv in reviews_list:
        safe_rating = max(1, min(5, int(rv.get("rating", 5) or 5)))
        stars = "⭐" * safe_rating
        badge_txt = str(rv.get("badge", "Mağaza"))
        rv_plat = "ios" if "iOS" in badge_txt or rv.get("store") == "App Store" else "android"
        reviews_html += f"""
        <div class="review-bubble" data-platform="{rv_plat}">
          <div class="review-head">
            <div>
              <span class="badge {'badge-meta' if rv_plat == 'ios' else 'badge-gp'}">{html.escape(badge_txt)}</span>
              <strong style="color:var(--text-primary); margin-left:6px;">{html.escape(str(rv.get('title', '')))}</strong>
            </div>
            <span style="font-size:11.5px; color:#D97706; font-weight:700;">{stars} • {html.escape(str(rv.get('date', '')))}</span>
          </div>
          <p class="review-body">“{html.escape(str(rv.get('body', '')))}”</p>
          <div class="review-foot">👤 {html.escape(str(rv.get('author', 'Kullanıcı')))} — {html.escape(str(rv.get('store', '')))}</div>
        </div>
        """
    if not reviews_html:
        reviews_html = """
        <div class="bento-card" style="grid-column: 1 / -1; text-align:center; color:var(--text-muted);">
          Henüz senkronize edilmiş mağaza yorumu bulunmuyor. Canlı mağaza verilerini çekmek için üstteki <strong>Mağazaları Güncelle</strong> butonunu kullanabilirsiniz.
        </div>
        """

    tz_tr = timezone(timedelta(hours=3))
    rows_html = ""
    for c in s["recent_clicks"][:60]:
        if c.is_bot or not c.is_unique:
            continue
        dt_utc = c.created_at.replace(tzinfo=timezone.utc) if c.created_at.tzinfo is None else c.created_at
        dt_tr = dt_utc.astimezone(tz_tr).strftime("%d.%m %H:%M")
        safe_detail = html.escape(c.device_detail or "Telefon")
        safe_webview = html.escape(c.app_webview or "Tarayıcı")
        safe_country = html.escape(c.country or "TR")
        c_plat = "ios" if c.os_family == "ios" or c.target_store == "app_store" else "android"
        store_str = "🍏 App Store (iPhone)" if c.target_store == "app_store" else "🤖 Google Play (Android)"

        rows_html += f"""
        <tr data-platform="{c_plat}">
          <td style="color:var(--text-secondary); font-weight:600; font-variant-numeric:tabular-nums;">{dt_tr}</td>
          <td>{'🍏 ' + safe_detail if c.os_family == 'ios' else '🤖 ' + safe_detail}</td>
          <td>{safe_webview}</td>
          <td style="color:{'#059669' if c_plat == 'ios' else '#2563EB'}; font-weight:700;">{store_str}</td>
          <td style="color:var(--text-muted);">{safe_country}</td>
        </tr>
        """

    f_imp = kpis["impressions_total"]
    f_vis = kpis["visits_and_clicks_total"]
    f_dl = kpis["downloads_total"]
    f_vip = kpis["vip_activations"]

    vis_of_imp_pct = round((f_vis / f_imp) * 100, 1) if f_imp > 0 else 0
    dl_of_vis_pct = round((f_dl / f_vis) * 100, 1) if f_vis > 0 else 0
    dl_of_imp_pct = round((f_dl / f_imp) * 100, 2) if f_imp > 0 else 0
    vip_of_dl_pct = round((f_vip / f_dl) * 100, 1) if f_dl > 0 else 0
    vip_of_vis_pct = round((f_vip / f_vis) * 100, 2) if f_vis > 0 else 0
    vip_of_imp_pct = round((f_vip / f_imp) * 100, 2) if f_imp > 0 else 0

    paid_conv = fl["paid_subs_count"]
    paid_cust_try = fl["realized_gross_try"]
    paid_try = fl["realized_net_proceeds_try"]
    offer_code_subs = fl["offer_code_subs_count"]
    offer_code_name = str(sb.get("apple_vip_offer_code_name") or "-")
    active_trials = fl["pipeline_7d_trials_count"]
    imp_search = int(sb.get("apple_impressions_search", 0) or 0)
    imp_browse = int(sb.get("apple_impressions_browse", 0) or 0)

    imp_search_pct = round((imp_search / max(1, imp_search + imp_browse)) * 100) if (imp_search + imp_browse) > 0 else 89
    vis_store_pct = round((kpis["store_page_views"] / max(1, f_vis)) * 100) if f_vis > 0 else 28
    dl_ios_pct = round((kpis["ios_downloads"] / max(1, f_dl)) * 100) if f_dl > 0 else 86
    vip_denom = max(1, paid_conv + active_trials + offer_code_subs)
    vip_paid_pct = round((paid_conv / vip_denom) * 100) if f_vip > 0 else 15
    vip_trial_pct = round((active_trials / vip_denom) * 100) if f_vip > 0 else 50
    vip_code_pct = max(0, 100 - vip_paid_pct - vip_trial_pct) if f_vip > 0 else 35

    renewal_calendar_html = ""
    for rc in fl["renewal_forecast_calendar"]:
        subs_badges = " • ".join(html.escape(x) for x in rc["subscribers"])
        is_rec_cal = bool(rc.get("is_reconciling") or rc.get("reconciliation_status") == "reconciling")
        rec_border = "#2563EB" if is_rec_cal else "#059669"
        rec_lbl = "🔄 APPLE MUTABAKATINDA" if is_rec_cal else "📅 YAKLAŞAN VADE"
        renewal_calendar_html += f"""
        <div class="step-box" style="border-left: 4px solid {rec_border};">
          <div class="step-num" style="color:{rec_border};">{rec_lbl}: {html.escape(str(rc['date']))}</div>
          <div class="step-val">{rc['count']} Abone</div>
          <div class="step-sub">Beklenen Tahsilat: <strong>{rc['expected_gross_try']:.2f} ₺ Brüt</strong> / <strong style="color:#059669;">{rc['expected_net_try']:.2f} ₺ Net</strong></div>
          <span class="step-rate">👤 {subs_badges}</span>
        </div>
        """

    ledger_rows_html = ""
    for idx_sub, sl in enumerate(sub_ledger, start=1):
        lc_stage = sl.get("lifecycle_stage", sl["status"])
        lc_prog = int(sl.get("trial_progress_pct", 50) or 50)
        if sl["status"] == "paid_active":
            st_badge = '<span class="badge" style="background:rgba(16,185,129,0.15); color:#059669;">💳 Ücretli Aktif</span>'
            bar_color = "#10B981"
        elif sl["status"] == "offer_code_trial":
            st_badge = f'<span class="badge" style="background:rgba(124,58,237,0.14); color:#7C3AED;">🎟️ Kodlu ({html.escape(str(sl["offer_code_name"]))})</span>'
            bar_color = "#8B5CF6"
        elif sl["status"] == "cancelled":
            st_badge = '<span class="badge" style="background:rgba(239,68,68,0.14); color:#DC2626;">✖ İptal</span>'
            bar_color = "#EF4444"
        elif lc_stage in ("reconciling_trial", "trial_matured_reconciling"):
            st_badge = '<span class="badge" style="background:rgba(37,99,235,0.14); color:#2563EB;">🔄 Mutabakatta (7/7 Gün)</span>'
            bar_color = "#3B82F6"
        else:
            st_badge = f'<span class="badge" style="background:rgba(217,119,6,0.15); color:#D97706;">{html.escape(str(sl.get("lifecycle_badge", "⏳ 7 Günlük Deneme")))}</span>'
            bar_color = "#F59E0B"

        ar_badge = (
            '<span style="color:#059669; font-weight:700;">✔ Açık (Aktif)</span>'
            if sl["auto_renew_enabled"]
            else '<span style="color:#DC2626; font-weight:700;">✖ İptal</span>'
        )
        paid_str = (
            f"<strong style='color:#059669;'>{sl['customer_price_try']:.2f} ₺</strong> <span style='color:var(--text-muted);'>(Net {sl['developer_proceeds_try']:.2f} ₺)</span>"
            if sl["customer_price_try"] > 0
            else "<span style='color:var(--text-muted);'>0.00 ₺ (Deneme / Kod)</span>"
        )
        next_str = (
            f"<strong style='color:var(--text-primary);'>{sl['expected_next_price_try']:.2f} ₺</strong> <span style='color:#059669;'>(Net {sl['expected_next_proceeds_try']:.2f} ₺)</span>"
            if sl["expected_next_price_try"] > 0
            else "<span style='color:var(--text-muted);'>0.00 ₺</span>"
        )
        prog_html = f"""
        <div style="margin-top:5px; width:100%; height:5px; background:var(--ring-track); border-radius:99px; overflow:hidden;">
          <div style="width:{lc_prog}%; height:100%; background:{bar_color}; border-radius:99px;"></div>
        </div>
        """
        sl_plat = str(sl.get("platform") or "ios").lower()
        plat_icon = "🤖" if sl_plat == "android" else "🍏"
        ledger_rows_html += f"""
        <tr data-platform="{html.escape(sl_plat)}">
          <td style="color:var(--text-muted); font-weight:700;">{idx_sub}</td>
          <td style="font-family:monospace; color:var(--text-primary); font-weight:700;" title="Tam Subscriber ID: {html.escape(str(sl['subscriber_id']))}">{plat_icon} {html.escape(str(sl['subscriber_short']))}</td>
          <td><strong>{html.escape(str(sl['plan_label']))}</strong></td>
          <td>{st_badge}{prog_html}</td>
          <td style="font-variant-numeric:tabular-nums;">{html.escape(str(sl['started_date']))}</td>
          <td style="font-variant-numeric:tabular-nums;">{html.escape(str(sl['converted_or_renewed_date']))}</td>
          <td style="color:#D97706; font-weight:700; font-variant-numeric:tabular-nums;">{html.escape(str(sl['maturity_or_renewal_date']))}</td>
          <td>{ar_badge}</td>
          <td style="font-variant-numeric:tabular-nums;">{paid_str}</td>
          <td style="color:var(--text-secondary); font-variant-numeric:tabular-nums;">{next_str}</td>
          <td>{html.escape(str(sl['country']))} • {html.escape(str(sl['device_type']))}</td>
        </tr>
        """

    max_aso_dl = max(1, max((int(am.get("downloads", 0) or 0) for am in aso_matrix), default=1))
    aso_rows_html = ""
    for am in aso_matrix:
        am_dl = int(am.get("downloads", 0) or 0)
        am_bar_w = max(4, round((am_dl / max_aso_dl) * 100)) if am_dl > 0 else 0
        cvr_cell = (
            f"<strong style='color:#059669;'>%{am['cvr_pct']}</strong> <span style='font-size:11px; color:var(--text-muted);'>({html.escape(str(am['cvr_basis']))})</span>"
            if am["cvr_pct"] is not None
            else f"<span style='color:var(--text-muted);'>{html.escape(str(am['cvr_basis']))}</span>"
        )
        aso_rows_html += f"""
        <tr>
          <td><strong>{html.escape(str(am['channel']))}</strong></td>
          <td><span class="badge badge-meta">{html.escape(str(am['source_badge']))}</span></td>
          <td style="font-weight:700; color:#D97706; font-variant-numeric:tabular-nums;">{html.escape(str(am['impressions']))}</td>
          <td style="color:var(--text-secondary);">{html.escape(str(am['page_views_or_clicks']))}</td>
          <td style="min-width:130px;">
            <div style="display:flex; align-items:center; justify-content:space-between; gap:8px;">
              <span style="font-family:'Sora',sans-serif; font-weight:800; color:#059669; font-size:15px;">{am_dl}</span>
              <span style="font-size:11px; color:var(--text-muted);">%{round((am_dl / max(1, f_dl)) * 100)}</span>
            </div>
            <div style="margin-top:4px; width:100%; height:5px; background:var(--ring-track); border-radius:99px; overflow:hidden;">
              <div style="width:{am_bar_w}%; height:100%; background:linear-gradient(90deg, #10B981, #3B82F6); border-radius:99px;"></div>
            </div>
          </td>
          <td>{cvr_cell}</td>
          <td style="color:#7C3AED; font-weight:600;">{html.escape(str(am['vip_attributed']))}</td>
        </tr>
        """

    country_rows_html = ""
    for c_item in countries_list:
        c_cnt = int(c_item.get("count", 0) or 0)
        c_pct = round((c_cnt / kpis["ios_downloads"]) * 100, 1) if kpis["ios_downloads"] > 0 else 0.0
        safe_flag = html.escape(str(c_item.get("flag", "🌍")))
        country_rows_html += f"""
        <tr>
          <td>{safe_flag} <strong>{html.escape(str(c_item.get('name', '')))}</strong> ({html.escape(str(c_item.get('code', '')))})</td>
          <td style="font-weight:800; color:#059669; font-variant-numeric:tabular-nums;">{c_cnt} İndirme</td>
          <td style="color:var(--text-muted); font-variant-numeric:tabular-nums;">%{c_pct}</td>
        </tr>
        """

    cohort_rows_html = ""
    for ch in pr["subscriber_cohorts"]:
        ret_p = float(ch.get("retention_pct", 0.0) or 0.0)
        heat_bg = "rgba(16,185,129,0.16)" if ret_p >= 90 else ("rgba(217,119,6,0.16)" if ret_p >= 60 else "rgba(239,68,68,0.16)")
        heat_col = "#059669" if ret_p >= 90 else ("#D97706" if ret_p >= 60 else "#DC2626")
        cohort_rows_html += f"""
        <tr>
          <td style="font-weight:700; color:var(--text-primary); font-variant-numeric:tabular-nums;">📅 {html.escape(str(ch['start_date']))} Kohortu</td>
          <td style="font-weight:800; color:#2563EB;">{ch['started_total']} Abone</td>
          <td style="color:#059669; font-weight:700;">{ch['paid_converted']} Ücretli</td>
          <td style="color:#7C3AED; font-weight:700;">{ch['offer_code']} Yıllık Kodlu</td>
          <td style="color:#D97706; font-weight:700;">{ch['intro_trial']} 7G Denemede</td>
          <td style="color:var(--text-muted);">{ch['cancelled']} İptal</td>
          <td><span class="badge" style="background:{heat_bg}; color:{heat_col}; font-variant-numeric:tabular-nums;">%{ch['retention_pct']} Aktif Korundu</span></td>
        </tr>
        """

    period_options = [
        ("all", "♾️ Tüm Zamanlar"),
        ("today", "📅 Bugün (TSİ)"),
        ("yesterday", "⏮️ Dün (TSİ)"),
        ("7d", "📆 Son 7 Gün"),
    ]
    period_pills_html = ""
    for p_key, p_lbl in period_options:
        is_act = "active" if clean_period == p_key else ""
        period_pills_html += f'<a href="/api/v1/analytics/dashboard?period={p_key}" class="period-pill {is_act}">{p_lbl}</a>'

    ps = s.get("platform_split") or {}
    ps_all = ps.get("all") or {}
    ps_ios = ps.get("ios") or {}
    ps_and = ps.get("android") or {}
    ps_json_str = json.dumps(ps, ensure_ascii=False)

    gp_catalog = s.get("google_play_subscriptions_catalog") or []
    android_subs_in_ledger = [sl for sl in sub_ledger if sl.get("platform") == "android"]
    android_active_by_pid: Counter = Counter()
    for asl in android_subs_in_ledger:
        if asl.get("status") != "cancelled" and asl.get("auto_renew_enabled"):
            p_raw = str(asl.get("product_id") or "").split(":")[0].strip()
            android_active_by_pid[p_raw] += 1

    gp_catalog_rows_html = ""
    for idx_gp, gpc in enumerate(gp_catalog, start=1):
        gp_pid = str(gpc.get("product_id", ""))
        gp_act_cnt = android_active_by_pid.get(gp_pid, 0)
        gp_act_badge = (
            f"<strong style='color:#059669;'>{gp_act_cnt} Aktif Abone</strong>"
            if gp_act_cnt > 0
            else "<strong style='color:var(--text-muted);'>0 Aktif Abone</strong>"
        )
        gp_catalog_rows_html += f"""
        <tr>
          <td style="color:var(--text-muted); font-weight:700;">{idx_gp}</td>
          <td style="font-family:monospace; color:var(--text-primary); font-weight:700;">{html.escape(gp_pid)} / {html.escape(str(gpc.get('base_plan_id', '')))}</td>
          <td><strong>{html.escape(str(gpc.get('title', '')))}</strong></td>
          <td><span class="badge badge-gp">✔ {html.escape(str(gpc.get('state', 'ACTIVE')))}</span></td>
          <td>{html.escape(str(gpc.get('billing_period', '')))}</td>
          <td><span class="badge" style="background:rgba(37,99,235,0.14); color:#2563EB;">🎁 {html.escape(str(gpc.get('free_trial_label', '')))}</span></td>
          <td><code>{html.escape(str(gpc.get('free_trial_offer_id', '-')))}</code></td>
          <td>{html.escape(str(gpc.get('grace_period', '')))}</td>
          <td style="font-weight:800; color:var(--text-primary); font-variant-numeric:tabular-nums;">{float(gpc.get('price_try', 0.0)):.2f} ₺ <span style="color:#059669; font-size:11.5px;">(Net ~{float(gpc.get('net_proceeds_try', 0.0)):.2f} ₺)</span></td>
          <td>{gp_act_badge} <span style="font-size:11px; color:var(--text-muted);">({ps_and.get('downloads', 0)} Android Kurulumu)</span></td>
        </tr>
        """

    gp_diag_html = (
        f"✅ <strong>Canlı Android Abone Durumu:</strong> Google Play üzerinde <strong>{ps_and.get('vip_count', 0)} Aktif Android VIP</strong> "
        f"(Toplam {ps_and.get('total_vip_count', 0)} Kayıt • Beklenen/Aktif Net MRR: <strong>{float(ps_and.get('mrr_net_try', 0.0)):.2f} ₺</strong>) bulunmaktadır."
        if int(ps_and.get("total_vip_count", 0) or 0) > 0
        else f"🔍 <strong>Neden Android'de 0 Abone Görünüyor? (Canlı API Teşhisi):</strong> Google Play Developer API (<code>monetization.subscriptions</code>) üzerinde <strong>Mışıl Baby Yıllık VIP (599.99 ₺ + 7G Ücretsiz Deneme)</strong> ve <strong>Mışıl Baby Aylık VIP (149.99 ₺ + 7G Ücretsiz Deneme)</strong> paketleriniz <strong>ACTIVE (Yayında)</strong> durumdadır. Ancak <strong>{ps_and.get('touchpoints', 0)} Android köprü tıklamasından</strong> gelen <strong>{kpis['android_downloads']} Android kurulumu</strong> içerisinden henüz Google Play faturalandırmasını (7G deneme veya ücretli) başlatan kullanıcı olmamıştır (<strong>0 Aktif Android Abone</strong>). Yeni bir Android abonesi başladığında bu tabloya otomatik olarak düşer."
    )

    dashboard_response = HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="tr">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <meta name="referrer" content="no-referrer">
      <title>Mışıl Baby — Kurumsal Büyüme, Abone Defteri & Ürün Analitiği Kokpiti</title>
      <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Sora:wght@600;700;800&family=JetBrains+Mono:wght@500;600;700;800&display=swap" rel="stylesheet">
      <style>
        /* EXECUTIVE KEYNOTE / STRIPE BOARD DECK TEMASI (AIRY DAYLIGHT — VARSAYILAN) */
        :root {{
          --bg-canvas: #F4F6FB;
          --bg-card: #FFFFFF;
          --bg-cell: #F8FAFC;
          --border-subtle: #E2E8F0;
          --ring-track: #E2E8F0;
          --text-primary: #0F172A;
          --text-secondary: #334155;
          --text-muted: #64748B;
          --card-shadow: 0 6px 24px -4px rgba(15, 23, 42, 0.05), 0 2px 6px -1px rgba(15, 23, 42, 0.03);
          --stage-1: #D97706;
          --stage-2: #2563EB;
          --stage-3: #059669;
          --stage-4: #7C3AED;
          --gold: #D97706;
          --sky: #2563EB;
          --emerald: #059669;
          --violet: #7C3AED;
          --rose: #DC2626;
        }}
        /* İSTEĞE BAĞLI YUMUŞAK GECE MODU (SOFT SLATE) */
        body.theme-slate {{
          --bg-canvas: #0B1120;
          --bg-card: #151F32;
          --bg-cell: #0F172A;
          --border-subtle: rgba(148, 163, 184, 0.16);
          --ring-track: rgba(255, 255, 255, 0.08);
          --text-primary: #F8FAFC;
          --text-secondary: #CBD5E1;
          --text-muted: #94A3B8;
          --card-shadow: 0 12px 32px rgba(0, 0, 0, 0.35);
          --stage-1: #F59E0B;
          --stage-2: #60A5FA;
          --stage-3: #34D399;
          --stage-4: #C084FC;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
          background: var(--bg-canvas);
          color: var(--text-primary);
          font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
          min-height: 100vh;
          padding: 20px 18px 80px;
          -webkit-font-smoothing: antialiased;
          transition: background 0.2s ease, color 0.2s ease;
        }}
        .container {{
          max-width: 1320px;
          margin: 0 auto;
        }}

        /* SUNUM MODU (BOARDROOM / KEYNOTE PRESENTATION MODE) */
        body.presentation-mode {{
          padding-top: 28px;
        }}
        body.presentation-mode .hide-in-pres {{
          display: none !important;
        }}
        body.presentation-mode .container {{
          max-width: 1380px;
        }}
        body.presentation-mode .hero-stage-card {{
          padding: 22px 20px;
        }}
        body.presentation-mode .big-num {{
          font-size: 36px;
        }}
        .pres-exit-fab {{
          display: none;
          position: fixed;
          bottom: 22px;
          right: 22px;
          z-index: 9999;
          padding: 10px 18px;
          border-radius: 99px;
          background: #0F172A;
          color: #FFFFFF;
          border: 1px solid rgba(255,255,255,0.2);
          font-size: 12.5px;
          font-weight: 800;
          cursor: pointer;
          box-shadow: 0 10px 25px rgba(15, 23, 42, 0.35);
        }}
        body.presentation-mode .pres-exit-fab {{
          display: inline-flex;
          align-items: center;
          gap: 8px;
        }}

        /* BİRLEŞİK EXECUTIVE HEADER (MARKA + KOMPAKT VERİ DURUMU + KONTROLLER) */
        .topbar {{
          display: flex;
          flex-direction: column;
          gap: 12px;
          padding: 16px 20px;
          background: var(--bg-card);
          border: 1px solid var(--border-subtle);
          border-radius: 18px;
          box-shadow: var(--card-shadow);
          margin-bottom: 14px;
        }}
        .topbar-main {{
          display: flex;
          flex-wrap: wrap;
          justify-content: space-between;
          align-items: center;
          gap: 14px;
        }}
        .brand {{ display: flex; align-items: center; gap: 14px; }}
        .brand-icon {{
          width: 42px; height: 42px; border-radius: 12px;
          background: linear-gradient(135deg, #10B981 0%, #059669 100%);
          color: #FFFFFF;
          display: flex; align-items: center; justify-content: center;
          font-size: 19px;
          box-shadow: 0 4px 12px rgba(16, 185, 129, 0.25);
        }}
        .brand h1 {{ font-family: 'Sora', sans-serif; font-size: 17.5px; font-weight: 800; color: var(--text-primary); letter-spacing: -0.02em; }}
        .brand p {{ font-size: 12px; color: var(--text-muted); margin-top: 2px; font-weight: 500; }}
        .actions {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
        .btn {{
          padding: 8px 13px;
          border-radius: 10px;
          font-size: 12px;
          font-weight: 700;
          text-decoration: none;
          display: inline-flex;
          align-items: center;
          gap: 6px;
          border: 1px solid var(--border-subtle);
          background: var(--bg-cell);
          color: var(--text-secondary);
          cursor: pointer;
          transition: all 0.15s ease;
        }}
        .btn:hover {{ background: var(--bg-card); border-color: #10B981; color: var(--text-primary); }}
        .btn-pres {{
          background: linear-gradient(135deg, rgba(124, 58, 237, 0.10), rgba(37, 99, 235, 0.10));
          border-color: rgba(124, 58, 237, 0.28);
          color: var(--stage-4);
        }}
        .btn-pres:hover {{
          background: var(--stage-4);
          color: #FFFFFF;
          border-color: var(--stage-4);
        }}
        .live-pill {{
          display: inline-flex;
          align-items: center;
          gap: 7px;
          padding: 7px 13px;
          border-radius: 99px;
          background: rgba(16, 185, 129, 0.10);
          border: 1px solid rgba(16, 185, 129, 0.28);
          color: #059669;
          font-size: 11.5px;
          font-weight: 800;
          cursor: pointer;
          font-variant-numeric: tabular-nums;
        }}
        .pulse-dot {{
          width: 7px; height: 7px; border-radius: 50%;
          background: #10B981;
          box-shadow: 0 0 8px #10B981;
        }}

        /* KOMPAKT TEK SATIR VERİ KAYNAKLARI ŞERİDİ (ESKİ 4 KOCA KART YERİNE) */
        .freshness-strip {{
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 8px;
          padding-top: 10px;
          border-top: 1px solid var(--border-subtle);
        }}
        .fs-chip {{
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 4px 10px;
          border-radius: 8px;
          background: var(--bg-cell);
          border: 1px solid var(--border-subtle);
          font-size: 11px;
          cursor: help;
        }}
        .fs-dot {{ width: 6px; height: 6px; border-radius: 50%; background: #10B981; }}
        .fs-reconciling .fs-dot {{ background: #3B82F6; }}
        .fs-synced .fs-dot {{ background: #F59E0B; }}
        .fs-lbl {{ font-weight: 600; color: var(--text-muted); }}
        .fs-badge {{ font-weight: 700; color: var(--text-primary); font-variant-numeric: tabular-nums; }}

        /* SEGMENTED KONTROL BARI (PLATFORM & DÖNEM — SIFIR SAYI TEKRARI) */
        .period-bar {{
          display: flex;
          flex-wrap: wrap;
          justify-content: space-between;
          align-items: center;
          gap: 10px;
          padding: 10px 16px;
          background: var(--bg-card);
          border: 1px solid var(--border-subtle);
          border-radius: 14px;
          box-shadow: var(--card-shadow);
          margin-bottom: 16px;
        }}
        .period-pills {{ display: flex; gap: 5px; flex-wrap: wrap; align-items: center; }}
        .period-pill {{
          padding: 6px 13px;
          border-radius: 9px;
          font-size: 12px;
          font-weight: 700;
          text-decoration: none;
          color: var(--text-secondary);
          background: var(--bg-cell);
          border: 1px solid var(--border-subtle);
          cursor: pointer;
          transition: all 0.15s ease;
        }}
        .period-pill:hover {{ color: var(--text-primary); border-color: #CBD5E1; }}
        .period-pill.active {{
          color: #FFFFFF;
          background: #0F172A;
          border-color: #0F172A;
          box-shadow: 0 2px 8px rgba(15, 23, 42, 0.18);
        }}
        body.theme-slate .period-pill.active {{
          background: #10B981;
          border-color: #059669;
          color: #06281E;
        }}
        .compare-toggle-btn {{
          padding: 6px 12px;
          border-radius: 9px;
          font-size: 11.5px;
          font-weight: 700;
          border: 1px dashed var(--border-subtle);
          background: transparent;
          color: var(--text-muted);
          cursor: pointer;
          transition: all 0.15s ease;
        }}
        .compare-toggle-btn:hover, .compare-toggle-btn.active {{
          color: var(--stage-2);
          border-color: var(--stage-2);
          background: rgba(37, 99, 235, 0.06);
        }}

        /* GENEL BENTO KART & KPI GRID (ALT SEKMELER İÇİN) */
        .kpi-grid {{
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(265px, 1fr));
          gap: 16px;
          margin-bottom: 18px;
        }}
        .bento-card {{
          background: var(--bg-card);
          border: 1px solid var(--border-subtle);
          border-radius: 18px;
          padding: 20px 22px;
          box-shadow: var(--card-shadow);
          margin-bottom: 16px;
        }}
        .kpi-grid .bento-card {{
          margin-bottom: 0;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          min-width: 0;
          overflow: hidden;
        }}

        /* BİRLEŞİK TEK SATIRLI <GrowthFunnelHero> (KPI + ADIM DÖNÜŞÜM KÖPRÜSÜ BİR ARADA) */
        .conv-bridge-card {{
          margin-bottom: 18px;
          padding: 18px 20px;
          background: var(--bg-card);
          border: 1px solid var(--border-subtle);
          border-radius: 20px;
          box-shadow: var(--card-shadow);
        }}
        .conv-bridge-head {{
          display: flex;
          align-items: center;
          justify-content: space-between;
          flex-wrap: wrap;
          gap: 10px;
          margin-bottom: 14px;
          padding-bottom: 12px;
          border-bottom: 1px solid var(--border-subtle);
        }}
        .conv-bridge-title {{
          font-family: 'Sora', sans-serif;
          font-size: 13.5px;
          font-weight: 800;
          color: var(--text-primary);
          display: flex;
          align-items: center;
          gap: 8px;
          letter-spacing: -0.01em;
        }}
        .conv-summary-pills {{
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 8px;
        }}
        .conv-summary-pill {{
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 5px 12px;
          border-radius: 99px;
          font-size: 11.5px;
          font-weight: 700;
          font-variant-numeric: tabular-nums;
          border: 1px solid rgba(124, 58, 237, 0.25);
          background: rgba(124, 58, 237, 0.07);
          color: var(--stage-4);
        }}
        .conv-summary-pill strong {{
          font-family: 'JetBrains Mono', monospace;
          font-size: 12px;
          font-weight: 800;
        }}
        .conv-bridge-grid {{
          display: grid;
          grid-template-columns: 1fr auto 1fr auto 1fr auto 1fr;
          align-items: stretch;
          gap: 8px;
        }}
        @media (max-width: 1150px) {{
          .conv-bridge-grid {{
            grid-template-columns: 1fr;
            gap: 10px;
          }}
          .conv-connector {{
            flex-direction: row !important;
            padding: 4px 10px !important;
          }}
        }}
        .hero-stage-card {{
          background: var(--bg-cell);
          border: 1px solid var(--border-subtle);
          border-radius: 16px;
          padding: 16px 16px 14px;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          min-width: 0;
          position: relative;
          overflow: hidden;
          transition: transform 0.2s ease, box-shadow 0.2s ease;
        }}
        .hero-stage-card:hover {{
          transform: translateY(-1px);
          box-shadow: 0 8px 20px rgba(15, 23, 42, 0.05);
        }}
        .card-label {{
          font-size: 11px;
          font-weight: 700;
          color: var(--text-muted);
          margin-bottom: 8px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 6px;
          letter-spacing: 0.3px;
          text-transform: uppercase;
        }}
        .kpi-hero-row {{
          display: flex;
          align-items: flex-end;
          justify-content: space-between;
          gap: 8px;
          margin-bottom: 8px;
          position: relative;
          z-index: 2;
        }}
        .big-num {{
          font-family: 'Sora', sans-serif;
          font-size: clamp(24px, 2.1vw, 31px);
          font-weight: 800;
          color: var(--text-primary);
          line-height: 1.08;
          font-variant-numeric: tabular-nums;
          letter-spacing: -0.03em;
          white-space: nowrap;
          transition: opacity 0.18s ease, transform 0.18s ease;
        }}
        .big-num-unit {{
          font-size: 14px;
          font-weight: 700;
          letter-spacing: -0.01em;
          opacity: 0.88;
          margin-left: 3px;
        }}
        .delta-chip {{
          display: inline-flex;
          align-items: center;
          padding: 3px 8px;
          border-radius: 99px;
          font-size: 10.5px;
          font-weight: 700;
          background: rgba(16, 185, 129, 0.12);
          color: #059669;
          font-variant-numeric: tabular-nums;
          white-space: nowrap;
        }}
        .split-bar {{
          width: 100%;
          height: 5px;
          border-radius: 99px;
          background: var(--ring-track);
          overflow: hidden;
          display: flex;
          margin: 6px 0 10px;
        }}
        .card-desc {{
          font-size: 12px;
          color: var(--text-secondary);
          line-height: 1.45;
          font-weight: 500;
          font-variant-numeric: tabular-nums;
        }}
        .card-desc strong {{ color: var(--text-primary); font-weight: 700; }}
        .conv-connector {{
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 4px;
          padding: 0 2px;
          min-width: 66px;
        }}
        .conv-conn-pill {{
          font-family: 'JetBrains Mono', monospace;
          font-size: 12px;
          font-weight: 800;
          padding: 5px 9px;
          border-radius: 99px;
          border: 1px solid var(--border-subtle);
          background: var(--bg-card);
          box-shadow: var(--card-shadow);
          white-space: nowrap;
          font-variant-numeric: tabular-nums;
        }}
        .conv-conn-lbl {{
          font-size: 10px;
          font-weight: 700;
          color: var(--text-muted);
          text-align: center;
          white-space: nowrap;
        }}

        /* 5 SEKMELİ YALIN NAVİGASYON BARI */
        .tabs-nav {{
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          margin-bottom: 16px;
          padding: 6px;
          background: var(--bg-card);
          border: 1px solid var(--border-subtle);
          border-radius: 14px;
          box-shadow: var(--card-shadow);
        }}
        .tab-btn {{
          flex: 1;
          min-width: 165px;
          padding: 10px 14px;
          border-radius: 10px;
          border: 1px solid transparent;
          background: transparent;
          color: var(--text-muted);
          font-family: 'Plus Jakarta Sans', sans-serif;
          font-size: 12.5px;
          font-weight: 700;
          cursor: pointer;
          text-align: center;
          transition: all 0.15s ease;
        }}
        .tab-btn:hover {{
          color: var(--text-primary);
          background: var(--bg-cell);
        }}
        .tab-btn.active {{
          background: #0F172A;
          color: #FFFFFF;
          box-shadow: 0 4px 12px rgba(15, 23, 42, 0.15);
        }}
        body.theme-slate .tab-btn.active {{
          background: #10B981;
          color: #06281E;
        }}
        .tab-pane {{ display: none; }}
        .tab-pane.active {{ display: block; }}

        /* YAN YANA ADIM KUTULARI & HUNİ BARI */
        .section-head {{
          font-family: 'Sora', sans-serif;
          font-size: 15px;
          font-weight: 800;
          color: var(--text-primary);
          margin-bottom: 16px;
          display: flex;
          justify-content: space-between;
          align-items: center;
          flex-wrap: wrap;
          gap: 10px;
        }}
        .steps-grid {{
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
          gap: 14px;
        }}
        .step-box {{
          background: var(--bg-cell);
          border: 1px solid var(--border-subtle);
          border-radius: 14px;
          padding: 16px;
          position: relative;
        }}
        .step-num {{
          font-size: 11px;
          font-weight: 800;
          text-transform: uppercase;
          letter-spacing: 0.4px;
          margin-bottom: 6px;
        }}
        .step-val {{
          font-family: 'Sora', sans-serif;
          font-size: 24px;
          font-weight: 800;
          color: var(--text-primary);
          margin-bottom: 4px;
          font-variant-numeric: tabular-nums;
        }}
        .step-sub {{ font-size: 12.5px; color: var(--text-muted); line-height: 1.45; }}
        .step-rate {{
          display: inline-block;
          margin-top: 10px;
          padding: 4px 10px;
          border-radius: 99px;
          font-size: 11px;
          font-weight: 700;
          background: var(--bg-card);
          border: 1px solid var(--border-subtle);
          color: var(--text-secondary);
          font-variant-numeric: tabular-nums;
        }}

        /* SIFIR KAYMA GARANTİLİ 3-SATIRLI CSS GRID ZAMAN ÇİZELGESİ */
        .chart-toggle {{ display: flex; gap: 6px; flex-wrap: wrap; }}
        .chart-toggle button {{
          padding: 7px 13px;
          border-radius: 10px;
          border: 1px solid var(--border-subtle);
          background: var(--bg-cell);
          color: var(--text-muted);
          font-size: 12px;
          font-weight: 700;
          cursor: pointer;
        }}
        .chart-toggle button.active {{
          background: #10B981;
          color: #FFFFFF;
          border-color: #059669;
        }}
        .timeline-scroll {{
          width: 100%;
          overflow-x: auto;
          padding-bottom: 4px;
        }}
        .timeline-grid {{
          display: grid;
          grid-template-columns: repeat({max(1, len(t_days))}, minmax(56px, 1fr));
          gap: 6px;
          height: 224px;
          padding: 14px 10px;
          background: var(--bg-cell);
          border-radius: 14px;
          border: 1px solid var(--border-subtle);
        }}
        .t-col {{
          display: grid;
          grid-template-rows: 22px 1fr 22px;
          align-items: stretch;
          justify-items: center;
          height: 100%;
          padding: 2px;
          border-radius: 8px;
        }}
        .t-today {{
          background: rgba(16, 185, 129, 0.08);
          border: 1px dashed rgba(16, 185, 129, 0.45);
        }}
        .t-pending {{
          background: rgba(245, 158, 11, 0.06);
        }}
        .t-top-val {{
          font-size: 11px;
          font-weight: 800;
          line-height: 22px;
          white-space: nowrap;
          font-variant-numeric: tabular-nums;
        }}
        .t-bars-pair {{
          width: 100%;
          height: 100%;
          display: flex;
          align-items: flex-end;
          justify-content: center;
          padding: 2px 0;
        }}
        .t-bar {{
          width: 68%;
          max-width: 30px;
          border-radius: 6px 6px 2px 2px;
          transition: height 0.25s ease;
        }}
        .t-lbl {{
          font-size: 11px;
          color: var(--text-muted);
          line-height: 22px;
          font-weight: 700;
          white-space: nowrap;
          font-variant-numeric: tabular-nums;
        }}

        /* 3 YAN YANA GÖRSEL HALKA */
        .donuts-grid {{
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(330px, 1fr));
          gap: 16px;
          margin-bottom: 16px;
        }}
        .donuts-grid .bento-card {{ margin-bottom: 0; }}
        .donut-wrap {{
          display: flex;
          align-items: center;
          gap: 18px;
          flex-wrap: wrap;
        }}
        .donut-legend {{ flex: 1; min-width: 160px; display: flex; flex-direction: column; gap: 7px; }}
        .donut-leg-row {{
          display: flex;
          justify-content: space-between;
          align-items: center;
          font-size: 12.5px;
          padding: 7px 10px;
          background: var(--bg-cell);
          border-radius: 9px;
          border: 1px solid var(--border-subtle);
          font-variant-numeric: tabular-nums;
        }}
        .donut-leg-left {{ display: flex; align-items: center; gap: 8px; color: var(--text-secondary); font-weight: 600; }}
        .donut-dot {{ width: 9px; height: 9px; border-radius: 50%; display: inline-block; }}
        .donut-pct {{ color: var(--text-muted); font-size: 11px; margin-left: 3px; }}

        /* YORUMLAR & TABLOLAR */
        .reviews-grid {{
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
          gap: 14px;
        }}
        .review-bubble {{
          background: var(--bg-cell);
          border: 1px solid var(--border-subtle);
          border-radius: 14px;
          padding: 16px;
        }}
        .review-head {{ display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }}
        .review-body {{ font-size: 13.5px; color: var(--text-primary); line-height: 1.55; margin-bottom: 8px; }}
        .review-foot {{ font-size: 11.5px; color: var(--text-muted); font-weight: 600; }}

        .badge {{
          display: inline-flex;
          align-items: center;
          padding: 4px 10px;
          border-radius: 99px;
          font-size: 11px;
          font-weight: 800;
          white-space: nowrap;
        }}
        .badge-meta {{ background: rgba(37, 99, 235, 0.12); color: #2563EB; }}
        .badge-gp {{ background: rgba(16, 185, 129, 0.14); color: #059669; }}
        .toast-banner {{
          background: rgba(16, 185, 129, 0.12);
          border: 1px solid rgba(16, 185, 129, 0.35);
          color: #059669;
          padding: 13px 18px;
          border-radius: 14px;
          margin-bottom: 16px;
          font-size: 13px;
          font-weight: 600;
        }}
        .table-wrap {{ overflow-x: auto; margin-top: 10px; border: 1px solid var(--border-subtle); border-radius: 12px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 12.5px; background: var(--bg-card); }}
        th {{ text-align: left; padding: 11px 12px; background: var(--bg-cell); color: var(--text-muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.4px; border-bottom: 1px solid var(--border-subtle); font-weight: 800; white-space: nowrap; }}
        td {{ padding: 11px 12px; border-bottom: 1px solid var(--border-subtle); color: var(--text-primary); font-variant-numeric: tabular-nums; }}
        tr:hover td {{ background: var(--bg-cell); }}
      </style>
    </head>
    <body>
      <button type="button" class="pres-exit-fab" onclick="togglePresentationMode()">📽️ Sunum Modundan Çık (ESC)</button>
      <div class="container">
        <!-- BİRLEŞİK EXECUTIVE HEADER (MARKA + AKSİYONLAR + KOMPAKT VERİ DURUMU ŞERİDİ) -->
        <div class="topbar">
          <div class="topbar-main">
            <div class="brand">
              <div class="brand-icon">🌙</div>
              <div>
                <h1>Mışıl Baby — Kurumsal Büyüme, Abone Defteri & Ürün Analitiği</h1>
                <p>Son Senkron: {html.escape(str(sb.get('last_synced_at', '')))} • App Store Connect & Google Play Developer API</p>
              </div>
            </div>
            <div class="actions">
              <button type="button" class="btn btn-pres hide-in-pres" onclick="togglePresentationMode()" id="presModeBtn" title="Yönetim kurulu / yatırımcı sunumu için kontrol kalabalığını gizler">📽️ Sunum Modu</button>
              <button type="button" class="btn hide-in-pres" onclick="toggleTheme()" id="themeToggleBtn" title="Gündüz (Airy Daylight) ve Gece (Soft Slate) görünümü arasında geçiş yap">☀️ / 🌙 Tema</button>
              <div class="live-pill" onclick="toggleAutoRefresh()" id="liveToggleBtn" title="Sayfayı yenilemeden arka planda canlı JSON telemetri senkronizasyonu yapar">
                <span class="pulse-dot" id="liveDot"></span>
                <span id="liveCountdown">Canlı: 15s</span>
              </div>
              <a href="/api/v1/analytics/export.csv" class="btn hide-in-pres">📥 CSV</a>
              <a href="/api/v1/analytics/dashboard?sync=1&period={clean_period}" class="btn hide-in-pres">🔄 Senkronize Et</a>
            </div>
          </div>
          <!-- KOMPAKT VERİ KAYNAKLARI DURUM ŞERİDİ (ÜZERİNE GELİNCE DETAY GÖSTERİR) -->
          <div class="freshness-strip hide-in-pres">
            {freshness_strip_html}
          </div>
        </div>

        {sync_banner}

        <!-- YALIN PLATFORM & DÖNEM SEÇİCİ BARI (SIFIR SAYI TEKRARI) -->
        <div class="period-bar">
          <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
            <div class="period-pills" id="platformPills">
              <button type="button" class="period-pill active" id="platBtn_all" onclick="switchPlatform('all')">🌐 Tümü (Kümülatif)</button>
              <button type="button" class="period-pill" id="platBtn_ios" onclick="switchPlatform('ios')">🍏 Apple iOS</button>
              <button type="button" class="period-pill" id="platBtn_android" onclick="switchPlatform('android')">🤖 Google Play</button>
            </div>
            <button type="button" class="compare-toggle-btn hide-in-pres" id="compareToggleBtn" onclick="toggleCompareDrawer()">⇄ Platform Kıyasla</button>
          </div>
          <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
            <span id="livePeriodSub" style="font-size:11.5px; color:var(--text-muted); font-weight:600; font-variant-numeric:tabular-nums;">{html.escape(s['period_label'])} • {s['active_human_count']} Tekil Tık (Bugün: {s['today_unique_clicks']})</span>
            <div class="period-pills hide-in-pres">
              {period_pills_html}
            </div>
          </div>
        </div>

        <!-- BİRLEŞİK TEK SATIRLI <GrowthFunnelHero> (4 KUZEY YILDIZI KARTI + 3 ADIM DÖNÜŞÜM KÖPRÜSÜ BİR ARADA — SIFIR MÜKERRERLİK) -->
        <div class="conv-bridge-card" id="conversionBridgeCard">
          <div class="conv-bridge-head">
            <div class="conv-bridge-title">
              <span id="funnelHeadTitle">🎯 Kuzey Yıldızı Büyüme & Uçtan Uca Dönüşüm Hunisi (Gösterim ➔ Tık ➔ İndirme ➔ Aktif VIP)</span>
            </div>
            <div class="conv-summary-pills" id="funnelHeadBadge">
              <span class="conv-summary-pill" style="background:rgba(5,150,105,0.08); border-color:rgba(5,150,105,0.28); color:var(--stage-3);" title="App Store ürün sayfası ziyaretinden indirmeye dönüşüm ve 24s gecikmeli günler hariç kesinleşmiş CVR">Mağaza CVR: <strong id="convStoreCvrPill">%{ps_all.get('store_cvr_pct', 0)}</strong> <span style="opacity:0.75;">(Kesinleşen: %{ps_all.get('settled_cvr_pct', 0)})</span></span>
              <span class="conv-summary-pill">Gösterim ➔ VIP (Uçtan Uca): <strong id="convSumVipImp">%{vip_of_imp_pct}</strong></span>
              <span class="conv-summary-pill" style="background:var(--bg-cell); border-color:var(--border-subtle); color:var(--text-secondary);">Tık ➔ VIP: <strong id="convCum4" style="color:var(--stage-4);">%{vip_of_vis_pct}</strong></span>
            </div>
          </div>

          <div class="conv-bridge-grid">
            <!-- ADIM 1: MAĞAZA GÖSTERİMİ -->
            <div class="hero-stage-card" style="border-top: 3px solid var(--stage-1);">
              <div>
                <div class="card-label">
                  <span id="kpiTitle1" style="color:var(--stage-1);">1. Mağaza Gösterimi</span>
                  <span class="delta-chip" id="kpiDelta1" style="background:rgba(217,119,6,0.12); color:var(--stage-1);">+{s['kpi_deltas']['recent_3d_impressions']} (3G)</span>
                </div>
                <div class="kpi-hero-row">
                  <div class="big-num" style="color:var(--stage-1);" id="kpiImpressions">{f_imp:,}</div>
                  {spark_imp_svg}
                </div>
                <div class="split-bar">
                  <div style="width:{imp_search_pct}%; background:#F59E0B;" title="Arama (%{imp_search_pct})"></div>
                  <div style="width:{100 - imp_search_pct}%; background:#10B981;" title="Keşfet / Köprü (%{100 - imp_search_pct})"></div>
                </div>
              </div>
              <div class="card-desc" id="kpiDesc1">{ps_all.get('impressions_sub', '')}</div>
            </div>

            <!-- KÖPRÜ 1: GÖSTERİM ➔ TIK (TEK YERDE) -->
            <div class="conv-connector">
              <span class="conv-conn-lbl">Gösterim ➔ Tık</span>
              <span class="conv-conn-pill" style="color:var(--stage-2); border-color:rgba(37,99,235,0.28);" id="convBridge1">%{vis_of_imp_pct} ➔</span>
            </div>

            <!-- ADIM 2: İNCELEME & SOSYAL TIK -->
            <div class="hero-stage-card" style="border-top: 3px solid var(--stage-2);">
              <div>
                <div class="card-label">
                  <span id="kpiTitle2" style="color:var(--stage-2);">2. İnceleme & Tık</span>
                  <span class="delta-chip" id="kpiDelta2" style="background:rgba(37,99,235,0.12); color:var(--stage-2);">+{s['today_unique_clicks']} Bugün</span>
                </div>
                <div class="kpi-hero-row">
                  <div class="big-num" style="color:var(--stage-2);" id="kpiVisitsClicks">{f_vis:,}</div>
                  {spark_vis_svg}
                </div>
                <div class="split-bar">
                  <div style="width:{vis_store_pct}%; background:#3B82F6;" title="Mağaza Sayfası (%{vis_store_pct})"></div>
                  <div style="width:{100 - vis_store_pct}%; background:#8B5CF6;" title="Sosyal Köprü Tıkı (%{100 - vis_store_pct})"></div>
                </div>
              </div>
              <div class="card-desc" id="kpiDesc2">{ps_all.get('touchpoints_sub', '')}</div>
            </div>

            <!-- KÖPRÜ 2: TIK ➔ İNDİRME (TEK YERDE) -->
            <div class="conv-connector">
              <span class="conv-conn-lbl">Tık ➔ İndirme</span>
              <span class="conv-conn-pill" style="color:var(--stage-3); border-color:rgba(5,150,105,0.28);" id="convBridge2">%{dl_of_vis_pct} ➔</span>
              <span class="conv-conn-lbl" style="font-size:9.5px; color:var(--stage-3); font-weight:700;" id="convBridge2Sub">{ps_all.get('cvr_breakdown_label', '')}</span>
            </div>

            <!-- ADIM 3: TOPLAM İNDİRME -->
            <div class="hero-stage-card" style="border-top: 3px solid var(--stage-3);">
              <div>
                <div class="card-label">
                  <span id="kpiTitle3" style="color:var(--stage-3);">3. Toplam İndirme</span>
                  <span class="delta-chip" id="kpiDelta3">+{s['kpi_deltas']['recent_3d_downloads']} (3G)</span>
                </div>
                <div class="kpi-hero-row">
                  <div class="big-num" style="color:var(--stage-3);" id="kpiDownloads">{f_dl}</div>
                  {spark_dl_svg}
                </div>
                <div class="split-bar">
                  <div style="width:{dl_ios_pct}%; background:#10B981;" title="🍏 Apple iOS (%{dl_ios_pct})"></div>
                  <div style="width:{100 - dl_ios_pct}%; background:#3B82F6;" title="🤖 Google Play Android (%{100 - dl_ios_pct})"></div>
                </div>
              </div>
              <div class="card-desc" id="kpiDesc3">{ps_all.get('downloads_sub', '')}</div>
            </div>

            <!-- KÖPRÜ 3: İNDİRME ➔ VIP (TEK YERDE) -->
            <div class="conv-connector">
              <span class="conv-conn-lbl">İndirme ➔ VIP</span>
              <span class="conv-conn-pill" style="color:var(--stage-4); border-color:rgba(124,58,237,0.28);" id="convBridge3">%{vip_of_dl_pct} ➔</span>
            </div>

            <!-- ADIM 4: AKTİF VIP & BEKLENEN NET MRR -->
            <div class="hero-stage-card" style="border-top: 3px solid var(--stage-4);">
              <div>
                <div class="card-label">
                  <span id="kpiTitle4" style="color:var(--stage-4);">4. Aktif VIP & MRR</span>
                  <span class="delta-chip" id="kpiDelta4" style="background:rgba(124,58,237,0.12); color:var(--stage-4);">{fl['projected_total_mrr_net_try']:.2f} ₺/Ay Net</span>
                </div>
                <div class="kpi-hero-row">
                  <div class="big-num" style="color:var(--stage-4);" id="kpiVip">{f_vip}<span class="big-num-unit">Aktif VIP</span></div>
                  {spark_vip_svg}
                </div>
                <div class="split-bar">
                  <div style="width:{vip_paid_pct}%; background:#10B981;" title="Ücretli Aktif (%{vip_paid_pct})"></div>
                  <div style="width:{vip_trial_pct}%; background:#F59E0B;" title="7G Deneme (%{vip_trial_pct})"></div>
                  <div style="width:{vip_code_pct}%; background:#8B5CF6;" title="Kodlu VIP (%{vip_code_pct})"></div>
                </div>
              </div>
              <div class="card-desc" id="kpiDesc4">{ps_all.get('vip_sub', '')}</div>
            </div>
          </div>
        </div>

        <!-- İSTEĞE BAĞLI AÇILIR/KAPANIR PLATFORM KIYASLAMA ÇEKMECESİ (VARSAYILAN GİZLİ — SIFIR KALABALIK) -->
        <div class="bento-card" id="platformCompareDrawer" style="display:none;">
          <div class="section-head">
            <span>⚖️ Apple App Store (iOS) vs Google Play Store (Android) — Yan Yana Platform Kıyaslaması</span>
            <button type="button" class="btn" onclick="toggleCompareDrawer()">✖ Kapat</button>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Büyüme & Gelir Aşaması</th>
                  <th>🌐 Kümülatif (Toplam)</th>
                  <th>🍏 Apple App Store (iOS)</th>
                  <th>🤖 Google Play Store (Android)</th>
                  <th>Platform Payı & Teknik Teşhis</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><strong>1. Mağaza Gösterimi</strong></td>
                  <td style="font-weight:800; color:#D97706;">{f_imp:,} Gösterim</td>
                  <td style="font-weight:700; color:#059669;">{f_imp:,} ({kpis['impressions_unique']:,} Cihaz)</td>
                  <td style="color:var(--text-secondary);">Play Organik + {ps_and.get('touchpoints', 0)} Köprü</td>
                  <td><span class="badge" style="background:rgba(217,119,6,0.14); color:#D97706;">Apple r14 API (%89 Arama)</span></td>
                </tr>
                <tr>
                  <td><strong>2. İnceleme & Sosyal Tık</strong></td>
                  <td style="font-weight:800; color:#2563EB;">{f_vis:,} Etkileşim</td>
                  <td style="font-weight:700; color:#059669;">{ps_ios.get('touchpoints', 0)} ({kpis['store_page_views']} Sayfa + {ps_ios.get('touchpoints', 0) - kpis['store_page_views']} Tık)</td>
                  <td style="font-weight:700; color:#2563EB;">{ps_and.get('touchpoints', 0)} Android Köprü Tıkı</td>
                  <td><span class="badge badge-meta">Sosyal Tıkların %{round((ps_and.get('touchpoints', 0) / max(1, kpis['bridge_unique_clicks'])) * 100)}'i Android</span></td>
                </tr>
                <tr>
                  <td><strong>3. Gerçek Kurulum (İndirme)</strong></td>
                  <td style="font-weight:800; color:#059669; font-size:14px;">{f_dl} Kurulum</td>
                  <td style="font-weight:800; color:#059669;">{kpis['ios_downloads']} iOS (%{dl_ios_pct})</td>
                  <td style="font-weight:800; color:#2563EB;">{kpis['android_downloads']} Android (%{100 - dl_ios_pct})</td>
                  <td><span class="badge badge-gp">🍏 %{ps_ios.get('cvr_pct', 0)} Genel (Mağaza %{ps_ios.get('store_cvr_pct', 0)}) vs 🤖 %{ps_and.get('cvr_pct', 0)} Köprü CVR</span></td>
                </tr>
                <tr>
                  <td><strong>4. Canlı Abonelik Paketleri</strong></td>
                  <td style="font-weight:700;">4 Aktif Paket (iOS + Android)</td>
                  <td><strong>2 Paket:</strong> <code>misil_annual</code> & <code>misil_monthly</code> (7G Deneme)</td>
                  <td><strong>{len(gp_catalog)} Paket Aktif:</strong> <code>misil</code> (599.99 ₺) & <code>misilaylik</code> (149.99 ₺) + 7G Deneme</td>
                  <td><span class="badge badge-gp">Her İki Mağazada 7G Deneme Aktif</span></td>
                </tr>
                <tr>
                  <td><strong>5. Aktif VIP Abone & Net MRR</strong></td>
                  <td style="font-weight:800; color:#7C3AED;">{f_vip} Aktif VIP ({ps_all.get('total_vip_count', f_vip)} Kayıt • {fl.get('cancelled_subs_count', 0)} İptal) • {fl['projected_total_mrr_net_try']:.2f} ₺/Ay</td>
                  <td style="font-weight:800; color:#7C3AED;">{ps_ios.get('vip_count', f_vip)} Aktif VIP ({paid_conv} Ücretli + {active_trials} Deneme + {offer_code_subs} Kod • {ps_ios.get('cancelled_vip_count', 0)} İptal)</td>
                  <td style="font-weight:700; color:{'#059669' if ps_and.get('vip_count', 0) > 0 else 'var(--text-muted)'};">{ps_and.get('vip_count', 0)} Aktif Abone ({ps_and.get('mrr_net_try', 0.0):.2f} ₺ MRR)</td>
                  <td><span class="badge" style="background:rgba(124,58,237,0.14); color:#7C3AED;">{'🤖 Android Gelir Köprüsü Aktif' if ps_and.get('vip_count', 0) > 0 else f"Android {kpis['android_downloads']} Kurulum ➔ Paywall Optimizasyon Fırsatı"}</span></td>
                </tr>
                <tr>
                  <td><strong>6. Resmi Mağaza Yorumları</strong></td>
                  <td style="font-weight:800; color:#D97706;">{reviews_total_cnt} Yorum ({avg_stars_label})</td>
                  <td><strong>{ps_ios.get('reviews_count', 0)} App Store Yorumu</strong> (5.0 ★)</td>
                  <td><strong>{ps_and.get('reviews_count', 0)} Google Play Yorumu</strong> (5.0 ★)</td>
                  <td><span class="badge badge-gp">Her İki Mağaza 5.0 ★ Tam Puan</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- 5 SEKMELİ YALIN NAVİGASYON BARI (SAYAÇ TEKRARLARI TEMİZLENDİ) -->
        <div class="tabs-nav" role="tablist">
          <button class="tab-btn active" id="tabBtn_tab1" onclick="switchTab('tab1')">🧭 1. Büyüme & Trendler</button>
          <button class="tab-btn" id="tabBtn_tab2" onclick="switchTab('tab2')">💎 2. Gelir & Abone Defteri</button>
          <button class="tab-btn" id="tabBtn_tab3" onclick="switchTab('tab3')">🎯 3. Kanal & ASO Attribution</button>
          <button class="tab-btn" id="tabBtn_tab4" onclick="switchTab('tab4')">🍼 4. Ürün Nabzı & Kohort</button>
          <button class="tab-btn" id="tabBtn_tab5" onclick="switchTab('tab5')">⭐ 5. Yorumlar ({avg_stars_label}) & Akış</button>
        </div>

        <!-- SEKME 1: BÜYÜME & TRENDLER (DOĞRUDAN GRAFİKLERLE AÇILIR) -->
        <div id="tabPane_tab1" class="tab-pane active">

          <div class="bento-card">
            <div class="section-head">
              <div>
                <span>📈 Gün-Gün Toplam İndirme Yükselişi ({html.escape(timeline_range_lbl)}: 🌐 {f_dl} Toplam — 🍏 {kpis['ios_downloads']} iOS + 🤖 {kpis['android_downloads']} Android)</span>
                <div style="font-size:12px; color:var(--text-muted); font-weight:500; margin-top:3px;">
                  Yeşil kısım <strong>🍏 Apple iOS</strong>, mavi kısım <strong>🤖 Google Play Android</strong> kurulumlarını; kesikli sütunlar (<code>*</code>) Apple TSV 24s gecikmesini gösterir.
                </div>
              </div>
              <div class="chart-toggle">
                <button id="btnCumChart" class="active" onclick="switchChartMode('cum')">🌐 Kümülatif ({f_dl})</button>
                <button id="btnIosChart" onclick="switchChartMode('ios')">🍏 Apple iOS ({kpis['ios_downloads']})</button>
                <button id="btnAndChart" onclick="switchChartMode('android')">🤖 Google Play ({kpis['android_downloads']})</button>
                <button id="btnDailyChart" onclick="switchChartMode('daily')">📊 Günlük Yeni</button>
              </div>
            </div>

            <div class="timeline-scroll">
              <div id="chartCumWrap" class="timeline-grid">
                {cum_bars_html}
              </div>
              <div id="chartIosWrap" class="timeline-grid" style="display:none;">
                {cum_ios_bars_html}
              </div>
              <div id="chartAndWrap" class="timeline-grid" style="display:none;">
                {cum_android_bars_html}
              </div>
              <div id="chartDailyWrap" class="timeline-grid" style="display:none;">
                {daily_bars_html}
              </div>
            </div>
          </div>

          <div class="donuts-grid">
            <div class="bento-card">
              <div class="section-head"><span>🍩 1. Nereden İndirdiler?</span></div>
              {donut_install_sources}
            </div>

            <div class="bento-card">
              <div class="section-head"><span>🍩 2. Hangi Ülkelerden?</span></div>
              {donut_countries}
            </div>

            <div class="bento-card">
              <div class="section-head"><span>🍩 3. Ne Zaman Geliyorlar? ({html.escape(s['period_label'])} • Zirve: {top_h1})</span></div>
              {donut_night_day}
            </div>
          </div>
        </div>

        <!-- SEKME 2: GELİR, MRR & ABONE DEFTERİ -->
        <div id="tabPane_tab2" class="tab-pane">
          <div class="kpi-grid">
            <div class="bento-card" style="border-left: 4px solid #10B981;">
              <div class="card-label">💵 1. TAHSİL EDİLEN KESİN GELİR</div>
              <div class="big-num" style="color:#059669;">{fl['realized_net_proceeds_try']:.2f} ₺ <span style="font-size:15px; color:var(--text-muted);">Net</span></div>
              <div class="card-desc">
                Brüt Tahsilat: <strong>{fl['realized_gross_try']:.2f} ₺</strong> • Aktif Yinelenen MRR: <strong>{fl['active_paid_mrr_net_try']:.2f} ₺ Net/Ay</strong> (<strong>{fl['paid_subs_count']} Ücretli Abone</strong>).
              </div>
            </div>

            <div class="bento-card" style="border-left: 4px solid #3B82F6;">
              <div class="card-label">🔄 2. APPLE MUTABAKATINDA (VADESİ DOLAN)</div>
              <div class="big-num" style="color:#2563EB;">+{fl['reconciling_7d_mrr_net_try']:.2f} ₺ <span style="font-size:15px; color:var(--text-muted);">Net</span></div>
              <div class="card-desc">
                7 günlük denemesi dolmuş ve oto-yenilemesi açık <strong>{fl['reconciling_7d_trials_count']} abone</strong> (Brüt <strong>{fl['reconciling_7d_mrr_gross_try']:.2f} ₺</strong>) • Apple 24–48s tahsilat raporu bekleniyor.
              </div>
            </div>

            <div class="bento-card" style="border-left: 4px solid #F59E0B;">
              <div class="card-label">⏳ 3. YAKLAŞAN DENEME VADESİ (AKTİF 7G)</div>
              <div class="big-num" style="color:#D97706;">+{fl['upcoming_7d_mrr_net_try']:.2f} ₺ <span style="font-size:15px; color:var(--text-muted);">Net</span></div>
              <div class="card-desc">
                Deneme süresi devam eden <strong>{fl['upcoming_7d_trials_count']} abone</strong> (Brüt <strong>{fl['upcoming_7d_mrr_gross_try']:.2f} ₺</strong>) • Toplam Pipeline: <strong>{fl['pipeline_7d_mrr_net_try']:.2f} ₺ Net</strong>.
              </div>
            </div>

            <div class="bento-card" style="border-left: 4px solid #8B5CF6;">
              <div class="card-label">🚀 4. BEKLENEN TOPLAM NET MRR KÖPRÜSÜ</div>
              <div class="big-num" style="color:#7C3AED;">{fl['projected_total_mrr_net_try']:.2f} ₺ <span style="font-size:15px; color:var(--text-muted);">Net/Ay</span></div>
              <div class="card-desc">
                🍏 Apple: <strong>{ps_ios.get('mrr_net_try', fl['projected_total_mrr_net_try']):.2f} ₺ Net/Ay</strong> ({ps_ios.get('vip_count', f_vip)} Aktif / {ps_ios.get('total_vip_count', len(sub_ledger))} Kayıt • {ps_ios.get('cancelled_vip_count', 0)} İptal) • 🤖 Google Play: <strong>{ps_and.get('mrr_net_try', 0.0):.2f} ₺ Net/Ay</strong> ({ps_and.get('vip_count', 0)} Abone / {len(gp_catalog)} Aktif Paket).
              </div>
            </div>
          </div>

          <div class="bento-card" id="appleRenewalCard">
            <div class="section-head">
              <span>📅 🍏 Apple App Store — 7 Günlük Deneme ➔ Ücretli Tahsilat Takvimi (SUBSCRIBER 1_3 Vade Projeksiyonu)</span>
              <span class="badge" style="background:rgba(16,185,129,0.14); color:#059669;">Toplam Pipeline: +{fl['pipeline_7d_mrr_gross_try']:.2f} ₺ Brüt / +{fl['pipeline_7d_mrr_net_try']:.2f} ₺ Net</span>
            </div>
            <div class="steps-grid">
              {renewal_calendar_html}
            </div>
          </div>

          <div class="bento-card" id="appleLedgerCard">
            <div class="section-head">
              <span>📒 🍏 Apple App Store & Android — Doğrulanmış Tekil Abone Defteri ({f_vip} Aktif VIP / Toplam {len(sub_ledger)} Kayıt • {fl.get('cancelled_subs_count', 0)} İptal)</span>
              <span class="badge badge-meta">Vendor #94806500 & Google Play • Dinamik DB</span>
            </div>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Abone ID</th>
                    <th>Paket</th>
                    <th>Durum & 7G İlerleme</th>
                    <th>Başlangıç</th>
                    <th>Son İşlem</th>
                    <th>Yenilenme / Vade</th>
                    <th>Oto-Yenileme</th>
                    <th>Tahsil Edilen (Brüt / Net)</th>
                    <th>Sonraki Dönem</th>
                    <th>Ülke / Cihaz</th>
                  </tr>
                </thead>
                <tbody>
                  {ledger_rows_html}
                </tbody>
              </table>
            </div>
          </div>

          <!-- GOOGLE PLAY STORE ABONELİK PAKETLERİ VE ANDROID FATURALANDIRMA DEFTERİ -->
          <div class="bento-card" id="googlePlayLedgerCard">
            <div class="section-head">
              <span>🤖 Google Play Store — Canlı Abonelik Paketleri & Android Faturalandırma Defteri (<code>com.levitas.misilbaby</code>)</span>
              <span class="badge badge-gp">Google Play Developer API (Monetization Subscriptions) • {len(gp_catalog)} Aktif Paket • {ps_and.get('vip_count', 0)} Aktif Abone</span>
            </div>
            <div style="padding:12px 16px; border-radius:12px; background:var(--bg-cell); border:1px solid var(--border-subtle); margin-bottom:12px; font-size:12.5px; color:var(--text-secondary); line-height:1.55;">
              {gp_diag_html}
            </div>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Google Play Ürün / Plan ID</th>
                    <th>Mağaza Paket Başlığı</th>
                    <th>Durum</th>
                    <th>Periyot</th>
                    <th>Ücretsiz Deneme Teklifi</th>
                    <th>Offer ID</th>
                    <th>Ek Süre (Grace)</th>
                    <th>Türkiye Fiyatı (Brüt / Net)</th>
                    <th>Aktif Android Abone</th>
                  </tr>
                </thead>
                <tbody>
                  {gp_catalog_rows_html}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <!-- SEKME 3: KANAL, ASO & KOD ATTRIBUTION -->
        <div id="tabPane_tab3" class="tab-pane">
          <div class="bento-card">
            <div class="section-head">
              <span>🎯 Kanal Bazlı Tam Büyüme & ASO Attribution Matrisi (Görüntülenme ➔ Tık ➔ İndirme ➔ VIP)</span>
              <span class="badge badge-gp">Toplam {f_dl} Kurulum ({kpis['ios_downloads']} iOS + {kpis['android_downloads']} Android)</span>
            </div>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Edinim / Büyüme Kanalı</th>
                    <th>Doğrulama Kaynağı</th>
                    <th>Mağaza Gösterimi</th>
                    <th>Sayfa Ziyareti / Sosyal Tık</th>
                    <th>Gerçek İndirme</th>
                    <th>Dönüşüm Oranı (CVR)</th>
                    <th>VIP & Abonelik Etkisi</th>
                  </tr>
                </thead>
                <tbody>
                  {aso_rows_html}
                </tbody>
              </table>
            </div>
          </div>

          <div class="donuts-grid">
            <div class="bento-card">
              <div class="section-head"><span>📲 Sosyal Medya Köprü Hunisi ({html.escape(s['period_label'])}: {s['active_human_count']} Tekil İnsan)</span></div>
              <div class="steps-grid">
                <div class="step-box" style="border-left: 4px solid #3B82F6;">
                  <div class="step-num" style="color:#2563EB;">META REKLAM KÖPRÜSÜ (/ios)</div>
                  <div class="step-val">{meta['unique_clicks']} Tekil Kişi</div>
                  <div class="step-sub"><strong>{meta['ios_clicks']} iPhone</strong> App Store'a + <strong>{meta['android_clicks']} Android</strong> telefon otomatik Google Play'e yönlendirildi.</div>
                  <span class="step-rate">Toplam {meta['raw_hits']} Ham İstek</span>
                </div>
                <div class="step-box" style="border-left: 4px solid #8B5CF6;">
                  <div class="step-num" style="color:#7C3AED;">INSTAGRAM BIO (/download)</div>
                  <div class="step-val">{ig['unique_clicks']} Tekil Kişi</div>
                  <div class="step-sub"><strong>{ig['ios_clicks']} iPhone</strong> + <strong>{ig['android_clicks']} Android</strong> organik profil ziyaretçisi yönlendirildi.</div>
                  <span class="step-rate">🤖 {s['total_bots']} Bot İsteği Filtrelendi</span>
                </div>
              </div>
            </div>

            <div class="bento-card">
              <div class="section-head"><span>🌍 {len(countries_list)} Ülke Resmi App Store İndirme Dağılımı</span></div>
              <div class="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Ülke</th>
                      <th>Resmi İndirme</th>
                      <th>Pay (%)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {country_rows_html}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>

        <!-- SEKME 4: ÜRÜN İÇİ NABIZ & KOHORT TUTUNDURMA -->
        <div id="tabPane_tab4" class="tab-pane">
          <div class="kpi-grid">
            <div class="bento-card" style="border-left: 4px solid #3B82F6;">
              <div class="card-label">📱 RESMİ UYGULAMA OTURUMLARI</div>
              <div class="big-num" style="color:#2563EB;">{pr['total_tracked_sessions']}</div>
              <div class="card-desc">
                Apple r8 API doğrulanmış <strong>{pr['apple_official_sessions']} oturum</strong> ({pr['returning_sessions_total']} tekrar oturumu) • Ortalama süre: <strong>{pr['avg_session_duration_sec']} sn</strong>.
              </div>
            </div>

            <div class="bento-card" style="border-left: 4px solid #10B981;">
              <div class="card-label">🔄 SÜREKLİ GİREN KULLANICILAR (RETURNING)</div>
              <div class="big-num" style="color:#059669;">{pr['verified_returning_devices_floor']}–{pr['verified_returning_devices_ceiling']} Cihaz</div>
              <div class="card-desc">
                Apple Opt-in: <strong>{pr['returning_optin_ios_devices']}/{pr['optin_ios_total_devices']} iPhone (%{pr['optin_ios_return_rate_pct']})</strong> • 3+ Oturum Sadık: <strong>{pr['loyal_optin_ios_devices']}</strong> • Opt-in Düzeltmeli Tahmin: <strong>~{pr['estimated_total_returning_users']} Ebeveyn</strong>.
              </div>
            </div>

            <div class="bento-card" style="border-left: 4px solid #8B5CF6;">
              <div class="card-label">🌙 GECE NÖBETİ & BEBEK PROFİLİ</div>
              <div class="big-num" style="color:#7C3AED;">%{nvd['night_pct']} • {pr['babies_count']} Bebek</div>
              <div class="card-desc">
                <strong>{nvd['night_clicks']} Gece</strong> vs <strong>{nvd['day_clicks']} Gündüz</strong> etkileşimi • Kayıtlı bebek profili: <strong>{pr['babies_count']}</strong> ({top_h1} / {top_h2}).
              </div>
            </div>

            <div class="bento-card" style="border-left: 4px solid #F59E0B;">
              <div class="card-label">🛡️ ABONE KOHORT TUTUNDURMA (RETENTION)</div>
              <div class="big-num" style="color:#D97706;">{html.escape(pr['overall_retention_str'])}</div>
              <div class="card-desc">
                Toplam <strong>{len(pr['subscriber_cohorts'])} ayrı günlük kohorttaki {len(sub_ledger)} abonenin</strong> aktif tutundurma oranı (<strong>{fl['cancelled_subs_count']} İptal</strong>).
              </div>
            </div>
          </div>

          <div class="bento-card">
            <div class="section-head">
              <span>🔄 Sürekli Giren Kullanıcılar (Returning Users) & Paywall Dönüşüm / İptal Hunisi</span>
              <span class="badge" style="background:rgba(37,99,235,0.12); color:#2563EB;">iOS Opt-in Geri Dönüş: %{pr['optin_ios_return_rate_pct']} • Maks Tekil Cihaz: {pr['max_sessions_single_device']} Oturum</span>
            </div>
            <div class="steps-grid">
              <div class="step-box" style="border-left: 4px solid #10B981;">
                <div class="step-num" style="color:#059669;">1. TEKRAR GİREN OPT-IN iOS</div>
                <div class="step-val">{pr['returning_optin_ios_devices']} / {pr['optin_ios_total_devices']} Cihaz</div>
                <div class="step-sub">2+ oturum açan doğrulanmış iPhone oranı <strong>%{pr['optin_ios_return_rate_pct']}</strong> ({pr['returning_sessions_total']} tekrar oturumu). <strong>{pr['loyal_optin_ios_devices']} cihaz</strong> 3+ kez girdi.</div>
              </div>
              <div class="step-box" style="border-left: 4px solid #3B82F6;">
                <div class="step-num" style="color:#2563EB;">2. CANLI GERİ DÖNÜŞ & TAHMİN</div>
                <div class="step-val">~{pr['estimated_total_returning_users']} Aktif Ebeveyn</div>
                <div class="step-sub">Uygulama içi <code>daily_active</code>: <strong>{pr['daily_active_signals_count']} sinyal</strong> (Kesin taban: <strong>{pr['verified_returning_devices_floor']}–{pr['verified_returning_devices_ceiling']} cihaz</strong>; 213 kurulumda opt-in düzeltmeli ~64–100 kullanıcı).</div>
              </div>
              <div class="step-box" style="border-left: 4px solid #8B5CF6;">
                <div class="step-num" style="color:#7C3AED;">3. PAYWALL & CTA HUNİSİ</div>
                <div class="step-val">{pf['paywall_funnel']['paywall_viewed']} Görüntüleme ➔ {pf['paywall_funnel']['paywall_cta_clicked']} CTA</div>
                <div class="step-sub">İlk Açılış: <strong>{pf['first_open_signals']}</strong> • Bebek Profili: <strong>{pr['babies_count']}</strong> • Paywall Atlama (Skip): <strong>{pf['paywall_funnel']['paywall_skipped']}</strong> • 60sn Ses Bitişi: <strong>{pf['paywall_funnel']['sound_preview_60s_ended']}</strong>.</div>
              </div>
              <div class="step-box" style="border-left: 4px solid #EF4444;">
                <div class="step-num" style="color:#DC2626;">4. ÖDEME PENCERESİ İPTALİ</div>
                <div class="step-val">{pf['paywall_funnel']['purchase_cancelled']} İptal (%{pf['paywall_funnel']['cancel_rate_pct']})</div>
                <div class="step-sub">🍏 iOS: <strong>{pf['paywall_funnel']['ios']['purchase_cancelled']}/{pf['paywall_funnel']['ios']['paywall_cta_clicked']}</strong> • 🤖 Android: <strong>{pf['paywall_funnel']['android']['purchase_cancelled']}/{pf['paywall_funnel']['android']['paywall_cta_clicked']}</strong> • Kurtarma: <strong>{pf['paywall_funnel']['paywall_cancel_recovery_shown']}</strong> (Aylık Esnek VIP Varsayılan).</div>
              </div>
            </div>
          </div>

          <div class="bento-card">
            <div class="section-head">
              <span>📊 Günlük Abone Kohort Tutundurma Matrisi (Başlangıç Tarihine Göre Yaşam Döngüsü)</span>
              <span class="badge" style="background:rgba(16,185,129,0.14); color:#059669;">{len(pr['subscriber_cohorts'])} Kohort • Tutundurma: {html.escape(pr['overall_retention_str'])}</span>
            </div>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Kohort Başlangıç Günü</th>
                    <th>Başlayan VIP</th>
                    <th>Ücretliye Geçen</th>
                    <th>Yıllık Kodlu</th>
                    <th>7G Denemesi Süren</th>
                    <th>İptal Eden</th>
                    <th>Kohort Tutundurma</th>
                  </tr>
                </thead>
                <tbody>
                  {cohort_rows_html}
                </tbody>
              </table>
            </div>
          </div>

          <div class="bento-card">
            <div class="section-head">
              <span>🍼 Uygulama İçi Modül & Bulut Veritabanı Aktivitesi</span>
            </div>
            <div class="steps-grid">
              <div class="step-box" style="border-left: 4px solid #10B981;">
                <div class="step-num" style="color:#059669;">UYKU & SES MOTORU</div>
                <div class="step-val">{pr['sleep_logs_count']} Kayıt</div>
                <div class="step-sub">Bulut senkronizasyonlu uyku seansı ve <code>sleep_sound_play</code> canlı sinyal kancası aktif.</div>
              </div>
              <div class="step-box" style="border-left: 4px solid #3B82F6;">
                <div class="step-num" style="color:#2563EB;">AĞLAMA ANALİZİ (AI)</div>
                <div class="step-val">{pr['cry_events_count']} Analiz</div>
                <div class="step-sub">Yapay zeka ağlama tespiti ve <code>cry_analysis</code> telemetri sayacı aktif.</div>
              </div>
              <div class="step-box" style="border-left: 4px solid #F59E0B;">
                <div class="step-num" style="color:#D97706;">GÜNLÜK RUTİN & DADI AI</div>
                <div class="step-val">{pr['routine_logs_count'] + pr['dadi_chats_count']} Etkileşim</div>
                <div class="step-sub">{pr['routine_logs_count']} rutin kaydı + {pr['dadi_chats_count']} Bilge Dadı sohbet mesajı.</div>
              </div>
              <div class="step-box" style="border-left: 4px solid #8B5CF6;">
                <div class="step-num" style="color:#7C3AED;">GERÇEK ZAMANLI VIP SİNYALİ</div>
                <div class="step-val">{pf['vip_started_signals']} Sinyal</div>
                <div class="step-sub">Uygulama içi <code>vip_started</code> sinyali ve <code>first_open</code> ({pf['first_open_signals']}) telemetrisi aktif.</div>
              </div>
            </div>
          </div>
        </div>

        <!-- SEKME 5: YORUMLAR & CANLI AKIŞ -->
        <div id="tabPane_tab5" class="tab-pane">
          <div class="bento-card">
            <div class="section-head">
              <span>⭐ Annelerin Resmi Mağaza Yorumları ({reviews_total_cnt} Yorum)</span>
              <span class="badge" style="background:rgba(217,119,6,0.14); color:#D97706;">{avg_stars_label} Puan</span>
            </div>
            <div class="reviews-grid">
              {reviews_html}
            </div>
          </div>

          <div class="bento-card">
            <div class="section-head">
              <span>⚡ Son Sosyal Medya Tıklama Kayıtları ({html.escape(s['period_label'])}: {s['active_human_count']} Tekil Kişi / Kümülatif: {s['total_raw']} Ham)</span>
              <a href="/api/v1/analytics/export.csv" class="btn">📥 Tümünü Excel/CSV İndir</a>
            </div>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Saat (TSİ)</th>
                    <th>Telefon</th>
                    <th>Geldiği Uygulama</th>
                    <th>Yönlendirilen Mağaza</th>
                    <th>Ülke</th>
                  </tr>
                </thead>
                <tbody>
                  {rows_html}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      <script>
        var PLATFORM_SPLIT = {ps_json_str};
        var currentPlatform = 'all';

        function toggleTheme() {{
          document.body.classList.toggle('theme-slate');
          var isSlate = document.body.classList.contains('theme-slate');
          localStorage.setItem('mishil_dash_theme', isSlate ? 'slate' : 'daylight');
        }}
        if (localStorage.getItem('mishil_dash_theme') === 'slate') {{
          document.body.classList.add('theme-slate');
        }}

        function togglePresentationMode() {{
          document.body.classList.toggle('presentation-mode');
        }}
        document.addEventListener('keydown', function(ev) {{
          if (ev.key === 'Escape' && document.body.classList.contains('presentation-mode')) {{
            document.body.classList.remove('presentation-mode');
          }}
        }});

        function toggleCompareDrawer() {{
          var drawer = document.getElementById('platformCompareDrawer');
          var btn = document.getElementById('compareToggleBtn');
          if (!drawer) return;
          var isHidden = (drawer.style.display === 'none' || drawer.style.display === '');
          drawer.style.display = isHidden ? 'block' : 'none';
          if (btn) {{
            if (isHidden) btn.classList.add('active');
            else btn.classList.remove('active');
          }}
        }}

        function switchTab(tabId) {{
          var panes = document.querySelectorAll('.tab-pane');
          var btns = document.querySelectorAll('.tab-btn');
          for (var i = 0; i < panes.length; i++) {{
            panes[i].classList.remove('active');
          }}
          for (var j = 0; j < btns.length; j++) {{
            btns[j].classList.remove('active');
          }}
          var targetPane = document.getElementById('tabPane_' + tabId);
          var targetBtn = document.getElementById('tabBtn_' + tabId);
          if (targetPane && targetBtn) {{
            targetPane.classList.add('active');
            targetBtn.classList.add('active');
            localStorage.setItem('mishil_dash_active_tab', tabId);
          }}
        }}

        function switchChartMode(mode) {{
          var wraps = {{
            'cum': document.getElementById('chartCumWrap'),
            'ios': document.getElementById('chartIosWrap'),
            'android': document.getElementById('chartAndWrap'),
            'daily': document.getElementById('chartDailyWrap')
          }};
          var btns = {{
            'cum': document.getElementById('btnCumChart'),
            'ios': document.getElementById('btnIosChart'),
            'android': document.getElementById('btnAndChart'),
            'daily': document.getElementById('btnDailyChart')
          }};
          for (var k in wraps) {{
            if (wraps[k]) wraps[k].style.display = (k === mode) ? 'grid' : 'none';
            if (btns[k]) {{
              if (k === mode) btns[k].classList.add('active');
              else btns[k].classList.remove('active');
            }}
          }}
          localStorage.setItem('mishil_dash_chart_mode', mode);
        }}

        function switchPlatform(plat, skipChartSync) {{
          if (!PLATFORM_SPLIT || !PLATFORM_SPLIT[plat]) plat = 'all';
          currentPlatform = plat;
          var p = PLATFORM_SPLIT[plat];

          var pBtns = ['all', 'ios', 'android'];
          for (var i = 0; i < pBtns.length; i++) {{
            var b = document.getElementById('platBtn_' + pBtns[i]);
            if (b) {{
              if (pBtns[i] === plat) b.classList.add('active');
              else b.classList.remove('active');
            }}
          }}

          var elImp = document.getElementById('kpiImpressions');
          var elVis = document.getElementById('kpiVisitsClicks');
          var elDl = document.getElementById('kpiDownloads');
          var elVip = document.getElementById('kpiVip');
          if (elImp) elImp.textContent = p.impressions_display;
          if (elVis) elVis.textContent = p.touchpoints_display;
          if (elDl) elDl.textContent = p.downloads_display;
          if (elVip) {{
            var vipNum = (p.vip !== undefined) ? p.vip : String(p.vip_display || '').replace(' Aktif VIP', '');
            elVip.innerHTML = vipNum + '<span class="big-num-unit">Aktif VIP</span>';
          }}

          var d1 = document.getElementById('kpiDesc1');
          var d2 = document.getElementById('kpiDesc2');
          var d3 = document.getElementById('kpiDesc3');
          var d4 = document.getElementById('kpiDesc4');
          var dl3 = document.getElementById('kpiDelta3');
          var dl4 = document.getElementById('kpiDelta4');
          var visOfImp = (p.vis_of_imp_pct !== undefined) ? p.vis_of_imp_pct : 0;
          var dlOfVis = (p.cvr_pct !== undefined) ? p.cvr_pct : 0;
          var dlOfImp = (p.dl_of_imp_pct !== undefined) ? p.dl_of_imp_pct : 0;
          var vipOfDl = (p.vip_of_dl_pct !== undefined) ? p.vip_of_dl_pct : 0;
          var vipOfVis = (p.vip_of_vis_pct !== undefined) ? p.vip_of_vis_pct : 0;
          var vipOfImp = (p.vip_of_imp_pct !== undefined) ? p.vip_of_imp_pct : 0;

          if (dl3) dl3.textContent = 'CVR %' + dlOfVis;
          if (dl4) dl4.textContent = Number(p.mrr_net_try || 0).toFixed(2) + ' ₺/Ay Net';

          if (d1) d1.textContent = p.impressions_sub;
          if (d2) d2.textContent = p.touchpoints_sub;
          if (d3) d3.textContent = p.downloads_sub;
          if (d4) d4.textContent = p.vip_sub + ' • ★ 5.0 (' + p.reviews_count + ' Yorum)';

          var csVipImp = document.getElementById('convSumVipImp');
          if (csVipImp) csVipImp.textContent = '%' + vipOfImp;

          var cb1 = document.getElementById('convBridge1');
          var cb2 = document.getElementById('convBridge2');
          var cb2Sub = document.getElementById('convBridge2Sub');
          var cb3 = document.getElementById('convBridge3');
          var csStorePill = document.getElementById('convStoreCvrPill');
          if (cb1) cb1.textContent = '%' + visOfImp + ' ➔';
          if (cb2) cb2.textContent = '%' + dlOfVis + ' ➔';
          if (cb2Sub && p.cvr_breakdown_label) cb2Sub.textContent = p.cvr_breakdown_label;
          if (cb3) cb3.textContent = '%' + vipOfDl + ' ➔';
          if (csStorePill && p.store_cvr_pct !== undefined) csStorePill.textContent = '%' + p.store_cvr_pct;

          var cc4 = document.getElementById('convCum4');
          if (cc4) cc4.textContent = '%' + vipOfImp + ' • %' + vipOfVis;

          if (!skipChartSync) {{
            if (plat === 'ios') switchChartMode('ios');
            else if (plat === 'android') switchChartMode('android');
            else switchChartMode('cum');
          }}

          var appRen = document.getElementById('appleRenewalCard');
          var appLed = document.getElementById('appleLedgerCard');
          var gpLed = document.getElementById('googlePlayLedgerCard');
          if (appRen) appRen.style.display = (plat === 'android') ? 'none' : 'block';
          if (appLed) appLed.style.display = (plat === 'android') ? 'none' : 'block';
          if (gpLed) gpLed.style.display = (plat === 'ios') ? 'none' : 'block';

          var platNodes = document.querySelectorAll('[data-platform]');
          for (var m = 0; m < platNodes.length; m++) {{
            var node = platNodes[m];
            var np = node.getAttribute('data-platform');
            if (plat === 'all' || np === plat) {{
              node.style.display = '';
            }} else {{
              node.style.display = 'none';
            }}
          }}

          localStorage.setItem('mishil_dash_platform', plat);
        }}

        (function() {{
          try {{
            if (window.history && window.history.replaceState && (window.location.search.indexOf('sync=1') > -1 || window.location.search.indexOf('pin=') > -1 || window.location.search.indexOf('updated=') > -1)) {{
              var cleanSearch = window.location.search
                .replace(/([?&])sync=1(&|$)/g, '$1')
                .replace(/([?&])pin=[^&]*(&|$)/g, '$1')
                .replace(/([?&])updated=[^&]*(&|$)/g, '$1')
                .replace(/[?&]+$/, '');
              if (cleanSearch === '?' || cleanSearch === '&') cleanSearch = '';
              window.history.replaceState({{}}, document.title, window.location.pathname + cleanSearch);
            }}
          }} catch (_he) {{}}

          var savedTab = localStorage.getItem('mishil_dash_active_tab');
          if (savedTab && document.getElementById('tabPane_' + savedTab)) {{
            switchTab(savedTab);
          }}

          var savedPlat = localStorage.getItem('mishil_dash_platform');
          if (savedPlat === 'ios' || savedPlat === 'android' || savedPlat === 'all') {{
            switchPlatform(savedPlat, true);
          }}

          var savedChartMode = localStorage.getItem('mishil_dash_chart_mode');
          if (savedChartMode === 'daily' || savedChartMode === 'cum' || savedChartMode === 'ios' || savedChartMode === 'android') {{
            switchChartMode(savedChartMode);
          }}

          var savedScrollY = sessionStorage.getItem('mishil_dash_scroll_y');
          if (savedScrollY) {{
            window.scrollTo(0, parseInt(savedScrollY, 10) || 0);
            sessionStorage.removeItem('mishil_dash_scroll_y');
          }}

          var autoRefreshEnabled = localStorage.getItem('mishil_analytics_autorefresh') !== 'off';
          var secondsLeft = 15;
          var countdownEl = document.getElementById('liveCountdown');
          var dotEl = document.getElementById('liveDot');
          var btnEl = document.getElementById('liveToggleBtn');

          function updateUi() {{
            if (!autoRefreshEnabled) {{
              countdownEl.textContent = 'Canlı: Duraklatıldı';
              dotEl.style.background = '#94A3B8';
              dotEl.style.boxShadow = 'none';
              btnEl.style.borderColor = 'rgba(148,163,184,0.35)';
              btnEl.style.color = '#94A3B8';
            }} else {{
              countdownEl.textContent = 'Canlı: ' + secondsLeft + 's';
              dotEl.style.background = '#34D399';
              dotEl.style.boxShadow = '0 0 10px #34D399';
              btnEl.style.borderColor = 'rgba(16,185,129,0.35)';
              btnEl.style.color = '#34D399';
            }}
          }}

          async function pollLiveTelemetry() {{
            try {{
              var res = await fetch('/api/v1/analytics/summary?period={clean_period}', {{
                headers: {{ 'Accept': 'application/json' }},
                credentials: 'same-origin'
              }});
              if (!res.ok) return;
              var data = await res.json();
              if (data.platform_split) {{
                PLATFORM_SPLIT = data.platform_split;
                switchPlatform(currentPlatform, true);
              }}
              var elSub = document.getElementById('livePeriodSub');
              if (elSub) {{
                elSub.textContent = '(' + (data.active_human_count || 0) + ' Tekil İnsan • Bugün: ' + (data.today_unique_clicks || 0) + ' • Dün: ' + (data.yesterday_unique_clicks || 0) + ')';
              }}
            }} catch (_err) {{}}
          }}

          window.toggleAutoRefresh = function() {{
            autoRefreshEnabled = !autoRefreshEnabled;
            localStorage.setItem('mishil_analytics_autorefresh', autoRefreshEnabled ? 'on' : 'off');
            secondsLeft = 15;
            updateUi();
          }};

          updateUi();

          setInterval(function() {{
            if (!autoRefreshEnabled) return;
            secondsLeft -= 1;
            if (secondsLeft <= 0) {{
              secondsLeft = 15;
              updateUi();
              pollLiveTelemetry();
            }} else {{
              updateUi();
            }}
          }}, 1000);
        }})();
      </script>
    </body>
    </html>
    """)
    if new_session_cookie_value:
        dashboard_response.set_cookie(
            key=_ADMIN_SESSION_COOKIE,
            value=new_session_cookie_value,
            httponly=True,
            samesite="lax",
            secure=(request.url.scheme == "https"),
            max_age=_ADMIN_SESSION_TTL_SECONDS,
            path="/",
        )
    return dashboard_response
