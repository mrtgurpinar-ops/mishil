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
from sqlalchemy import desc

try:
    import jwt
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
}

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
        "daily_store_series": {},
        "store_reviews": [],
    }


OFFICIAL_STORE_BASELINE: Dict[str, Any] = _empty_store_state()


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


def sync_live_store_apis(days_back: int = 12) -> Dict[str, Any]:
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
    asc_key_id = os.environ.get("ASC_KEY_ID", detected_key_id)
    asc_issuer_id = os.environ.get("ASC_ISSUER_ID", "7d2413c6-ea40-4bd9-9334-8313a514b0e6" if p8_path else "")
    asc_priv_key = os.environ.get("ASC_PRIVATE_KEY")

    if not asc_priv_key and p8_path:
        try:
            with open(p8_path, "r", encoding="utf-8") as f:
                asc_priv_key = f.read()
        except Exception as e:
            logger.warning("Failed to read Apple .p8 key file: %s", e)

    if asc_priv_key:
        asc_priv_key = asc_priv_key.replace("\\n", "\n")

    synced_sources: List[str] = []
    fetched_apple_reviews: List[Dict[str, Any]] = []
    fetched_gp_reviews: List[Dict[str, Any]] = []
    country_totals: Counter = Counter()
    latest_sub_state: Dict[str, int] = {}
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

                # 2) SUBSCRIPTION Durum Özeti -> Aktif abone sayıları
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
                                    paid_cnt += int(float(sd.get("Active Standard Price Subscriptions", "0") or 0))
                                    code_cnt += int(float(sd.get("Free Trial Offer Code Subscriptions", "0") or 0))
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
                                        std_price_try = 599.99 if is_annual else 149.99
                                        std_proc_try = 332.50 if is_annual else 83.12

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
                                        else:
                                            try:
                                                dt_st = datetime.strptime(ev_date, "%Y-%m-%d")
                                                mat_date = (dt_st + timedelta(days=365 if is_annual else 7)).strftime("%Y-%m-%d")
                                            except Exception:
                                                mat_date = ev_date
                                            st_val = "paid_active" if c_price_try > 0 else ("offer_code_trial" if is_annual or (offer_name and "Default_Intro" not in offer_name) else "intro_free_trial")
                                            of_type = "standard_paid" if c_price_try > 0 else ("offer_code" if st_val == "offer_code_trial" else "intro_7d_trial")
                                            ccy_suffix = f" ({c_ccy})" if c_ccy != "TRY" else ""
                                            of_lbl = (offer_name if (offer_name and "Default_Intro" not in offer_name) else ("Standart Ücretli" if c_price_try > 0 else "7 Günlük Deneme")) + ccy_suffix
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
                                                    expected_next_price_try=c_price_try if c_price_try > 0 else std_price_try,
                                                    expected_next_proceeds_try=d_proc_try if d_proc_try > 0 else std_proc_try,
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
    }


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
    except Exception:
        try:
            Base.metadata.create_all(bind=engine, checkfirst=True)
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
          <circle cx="70" cy="70" r="{radius}" fill="transparent" stroke="rgba(255,255,255,0.06)" stroke-width="16" />
          {circles_svg}
          <text x="70" y="66" text-anchor="middle" fill="#FFFFFF" font-family="Sora, sans-serif" font-size="20" font-weight="800">{html.escape(str(center_val))}</text>
          <text x="70" y="84" text-anchor="middle" fill="#94A3B8" font-family="Plus Jakarta Sans, sans-serif" font-size="10" font-weight="700">{html.escape(str(center_lbl))}</text>
        </svg>
      </div>
      <div class="donut-legend">
        {legend_html}
      </div>
    </div>
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

    # Uygulama İçi Cihaz Sinyalleri (app.html tarafından gönderilen tüm 7 event türü)
    first_opens = [s for s in signals if s.event_type == "first_open"]
    daily_actives = [s for s in signals if s.event_type == "daily_active"]
    store_jumps = [s for s in signals if s.event_type == "store_jump"]
    baby_created_signals = [s for s in signals if s.event_type == "baby_created"]
    vip_started_signals = [s for s in signals if s.event_type == "vip_started"]
    sleep_sound_signals = [s for s in signals if s.event_type == "sleep_sound_play"]
    cry_analysis_signals = [s for s in signals if s.event_type == "cry_analysis"]
    unmatched_organic_opens = len([
        s for s in first_opens if (s.match_confidence or "unmatched") == "unmatched"
    ])
    distinct_signal_devices = len({
        s.device_uid for s in signals
        if s.device_uid and s.event_type in (
            "first_open", "daily_active", "baby_created", "vip_started", "sleep_sound_play", "cry_analysis"
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

    # P0-4: Dinamik Tarihsel & Canlı Kümülatif Zaman Serisi (Sabit 18-28 Ekim tarihleri kaldırıldı)
    candidate_dates = list(daily_series_merged.keys()) + list(clicks_by_date.keys())
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
        day_and_dl = int(st_day.get("android_downloads", 0) or 0)
        day_bridge = clicks_by_date.get(d_str, 0)

        day_tot_touch = day_pv + day_bridge

        cum_imp += day_imp
        cum_vis_clicks += day_tot_touch
        cum_ios_dl += day_ios_dl
        cum_and_dl += day_and_dl

        unallocated_android = max(0, google_play_downloads - cum_and_dl) if i == num_days - 1 else 0
        cum_total_dl = cum_ios_dl + cum_and_dl + unallocated_android

        timeline_days.append({
            "date": d_str,
            "label": d_short,
            "daily_impressions": day_imp,
            "daily_visits_clicks": day_tot_touch,
            "daily_bridge_clicks": day_bridge,
            "daily_page_views": day_pv,
            "daily_downloads": day_ios_dl + day_and_dl,
            "cum_ios_downloads": cum_ios_dl,
            "cum_impressions": cum_imp,
            "cum_visits_clicks": cum_vis_clicks,
            "cum_downloads": cum_total_dl,
        })

    meta_live_clicks = len(meta_unique)
    meta_android_leak_pct = round((len(meta_android) / max(1, meta_live_clicks)) * 100, 1) if meta_live_clicks > 0 else 0.0
    active_human_count = len(active_human_set)

    # ========================================================================
    # FAZ 2: KURUMSAL GELİR, MRR, ABONE DEFTERİ VE TAHSİLAT TAKVİMİ (SIFIR STATİK VERİ)
    # ========================================================================
    ledger_rows_db: List[SubscriberLedger] = (
        db.query(SubscriberLedger)
        .order_by(SubscriberLedger.maturity_or_renewal_date.asc(), SubscriberLedger.started_date.asc())
        .all()
    )
    subscriber_ledger_list = []
    realized_gross_try = 0.0
    realized_net_try = 0.0
    active_paid_mrr_gross = 0.0
    active_paid_mrr_net = 0.0
    pipeline_7d_gross = 0.0
    pipeline_7d_net = 0.0
    paid_subs_cnt = 0
    offer_code_cnt = 0
    intro_trial_cnt = 0
    cancelled_cnt = 0

    renewal_by_date: Dict[str, Dict[str, Any]] = {}
    cohort_by_start_date: Dict[str, Dict[str, Any]] = {}

    for r in ledger_rows_db:
        realized_gross_try += float(r.customer_price_try or 0.0)
        realized_net_try += float(r.developer_proceeds_try or 0.0)
        if not r.auto_renew_enabled or r.status == "cancelled":
            cancelled_cnt += 1
        if r.status == "paid_active":
            paid_subs_cnt += 1
            if r.auto_renew_enabled:
                # P1-1: MRR hesabı kümülatif LTV (customer_price_try) üzerinden değil,
                # yalnızca tek dönemlik yinelenen fiyat (expected_next_price_try) üzerinden yapılır.
                rec_gross = float(r.expected_next_price_try or 0.0)
                rec_net = float(r.expected_next_proceeds_try or 0.0)
                if "annual" in (r.product_id or "").lower():
                    active_paid_mrr_gross += rec_gross / 12.0
                    active_paid_mrr_net += rec_net / 12.0
                else:
                    active_paid_mrr_gross += rec_gross
                    active_paid_mrr_net += rec_net
        elif r.status == "offer_code_trial":
            offer_code_cnt += 1
        elif r.status == "intro_free_trial":
            intro_trial_cnt += 1
            if r.auto_renew_enabled:
                next_gross = float(r.expected_next_price_try or 0.0)
                next_net = float(r.expected_next_proceeds_try or 0.0)
                pipeline_7d_gross += next_gross
                pipeline_7d_net += next_net
                m_dt = r.maturity_or_renewal_date or "-"
                if m_dt not in renewal_by_date:
                    renewal_by_date[m_dt] = {
                        "date": m_dt,
                        "count": 0,
                        "expected_gross_try": 0.0,
                        "expected_net_try": 0.0,
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
        elif r.status == "intro_free_trial":
            cohort_by_start_date[s_dt]["intro_trial"] += 1

        subscriber_ledger_list.append({
            "subscriber_id": r.subscriber_id,
            "subscriber_short": f"#{r.subscriber_id[-6:]}",
            "platform": r.platform,
            "product_id": r.product_id,
            "plan_label": r.plan_label,
            "status": r.status,
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

    apple_vip = max(int(sb.get("apple_vip_activations_total", 0) or 0), len(ledger_rows_db), db_subs_count, len(vip_started_signals))
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
        "projected_total_mrr_net_try": round(active_paid_mrr_net + pipeline_7d_net, 2),
        "projected_total_arr_net_try": round((active_paid_mrr_net + pipeline_7d_net) * 12, 2),
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
        if (s.matched_channel and ("meta" in s.matched_channel.lower() or "ios" in s.matched_channel.lower()))
    ])
    matched_ig_installs = len([
        s for s in first_opens
        if (s.matched_channel and ("instagram" in s.matched_channel.lower() or "download" in s.matched_channel.lower()))
    ])

    r3_search = max(
        int(sb.get("apple_downloads_search", 0) or 0),
        int(asa_cfg.reported_installs if asa_cfg else 0),
    )
    r3_ref = max(
        int(sb.get("apple_downloads_referrer", 0) or 0),
        int(meta_cfg.reported_installs if meta_cfg else 0),
        matched_meta_installs,
    )
    r3_browse = max(
        int(sb.get("apple_downloads_browse", 0) or 0),
        int(ig_cfg.reported_installs if ig_cfg else 0),
        matched_ig_installs,
    )
    asa_clicks_val = max(apple_taps, int(asa_cfg.reported_clicks if asa_cfg else 0))

    recent_ios_dl = max(0, apple_downloads - (r3_search + r3_ref + r3_browse))
    imp_search_val = int(sb.get("apple_impressions_search", 0) or apple_impressions)
    imp_browse_val = int(sb.get("apple_impressions_browse", 0) or 0)
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

    product_retention = {
        "apple_official_sessions": apple_official_sessions,
        "total_tracked_sessions": apple_sessions,
        "optin_active_devices": max(int(sb.get("apple_sessions_optin_devices", 0) or 0), distinct_signal_devices, db_babies_count),
        "avg_session_duration_sec": (
            round(int(sb.get("apple_sessions_duration_sec", 0) or 0) / apple_official_sessions)
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
        "cumulative_kpis": {
            "impressions_total": total_cumulative_impressions,
            "impressions_unique": int(sb.get("apple_impressions_unique", 0) or 0),
            "visits_and_clicks_total": total_cumulative_visits_and_clicks,
            "store_page_views": apple_page_views,
            "bridge_unique_clicks": len(unique_human),
            "store_taps": apple_taps,
            "downloads_total": total_cumulative_downloads,
            "ios_downloads": apple_downloads,
            "android_downloads": google_play_downloads,
            "active_sessions": apple_sessions,
            "vip_activations": apple_vip,
            "distinct_live_devices": max(int(sb.get("apple_sessions_optin_devices", 0) or 0), distinct_signal_devices, db_babies_count),
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
            "total_store_installs": total_cumulative_downloads,
            "first_open_signals": len(first_opens),
            "daily_active_signals": len(daily_actives),
            "baby_created_signals": len(baby_created_signals),
            "vip_started_signals": len(vip_started_signals),
            "sleep_sound_signals": len(sleep_sound_signals),
            "cry_analysis_signals": len(cry_analysis_signals),
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
    s = _build_analytics_summary(db, period=period)

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

    cum_bars_html = ""
    daily_bars_html = ""
    for d in t_days:
        dl_h = max(10, round((d["cum_downloads"] / max_cum_dl) * 100)) if d["cum_downloads"] > 0 else 5
        is_today = d["date"] == t_days[-1]["date"]
        cum_ios_val = d.get("cum_ios_downloads", d["cum_downloads"])
        cum_tip = (
            f"{d['label']}: Toplam {d['cum_downloads']} İndirme ({cum_ios_val} iOS + {kpis['android_downloads']} Google Play)"
            if is_today
            else f"{d['label']}: Kümülatif {d['cum_downloads']} İndirme"
        )

        cum_bars_html += f"""
        <div class="t-col {'t-today' if is_today else ''}" title="{html.escape(cum_tip)}">
          <div class="t-top-val" style="color:#34D399;">{d['cum_downloads']}</div>
          <div class="t-bars-pair">
            <div class="t-bar" style="height:{dl_h}%; background:linear-gradient(180deg, #34D399 0%, #059669 100%);"></div>
          </div>
          <div class="t-lbl">{html.escape(d['label'])}</div>
        </div>
        """

        d_dl_h = max(12, round((d["daily_downloads"] / max_daily_dl) * 100)) if d["daily_downloads"] > 0 else 5
        d_dl_str = f"+{d['daily_downloads']}" if d["daily_downloads"] > 0 else "0"
        d_touch_tip = f" • +{d['daily_visits_clicks']} Sayfa/Sosyal Tık" if d["daily_visits_clicks"] > 0 else ""

        daily_bars_html += f"""
        <div class="t-col {'t-today' if is_today else ''}" title="{html.escape(d['label'])}: +{d['daily_downloads']} Yeni İndirme{html.escape(d_touch_tip)}">
          <div class="t-top-val" style="color:#E8A855;">{d_dl_str}</div>
          <div class="t-bars-pair">
            <div class="t-bar" style="height:{d_dl_h}%; background:linear-gradient(180deg, #E8A855 0%, #D48828 100%);"></div>
          </div>
          <div class="t-lbl">{html.escape(d['label'])}</div>
        </div>
        """

    # Mağaza Yorumları Balonları (P2: rating 1..5 aralığına sınırlandırılır)
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
        reviews_html += f"""
        <div class="review-bubble">
          <div class="review-head">
            <div>
              <span class="badge {'badge-meta' if 'iOS' in badge_txt else 'badge-gp'}">{html.escape(badge_txt)}</span>
              <strong style="color:#FFF; margin-left:6px;">{html.escape(str(rv.get('title', '')))}</strong>
            </div>
            <span style="font-size:11.5px; color:#FBBF24; font-weight:700;">{stars} • {html.escape(str(rv.get('date', '')))}</span>
          </div>
          <p class="review-body">“{html.escape(str(rv.get('body', '')))}”</p>
          <div class="review-foot">👤 {html.escape(str(rv.get('author', 'Kullanıcı')))} — {html.escape(str(rv.get('store', '')))}</div>
        </div>
        """
    if not reviews_html:
        reviews_html = """
        <div class="bento-card" style="grid-column: 1 / -1; text-align:center; color:#94A3B8;">
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
        store_str = "App Store (iPhone)" if c.target_store == "app_store" else "Google Play (Android)"

        rows_html += f"""
        <tr>
          <td style="color:#CBD5E1; font-weight:600;">{dt_tr}</td>
          <td>{'🍏 ' + safe_detail if c.os_family == 'ios' else '🤖 ' + safe_detail}</td>
          <td>{safe_webview}</td>
          <td style="color:#34D399; font-weight:700;">{store_str}</td>
          <td style="color:#94A3B8;">{safe_country}</td>
        </tr>
        """

    f_imp = kpis["impressions_total"]
    f_vis = kpis["visits_and_clicks_total"]
    f_dl = kpis["downloads_total"]
    f_vip = kpis["vip_activations"]

    vis_of_imp_pct = round((f_vis / f_imp) * 100) if f_imp > 0 else 0
    dl_of_vis_pct = round((f_dl / f_vis) * 100) if f_vis > 0 else 0
    vip_of_dl_pct = round((f_vip / f_dl) * 100) if f_dl > 0 else 0

    paid_conv = fl["paid_subs_count"]
    paid_cust_try = fl["realized_gross_try"]
    paid_try = fl["realized_net_proceeds_try"]
    offer_code_subs = fl["offer_code_subs_count"]
    offer_code_name = str(sb.get("apple_vip_offer_code_name") or "-")
    active_trials = fl["pipeline_7d_trials_count"]
    imp_search = int(sb.get("apple_impressions_search", 0) or 0)
    imp_browse = int(sb.get("apple_impressions_browse", 0) or 0)

    # SEKME 2: 7 Günlük Deneme -> Ücretli Tahsilat Takvimi Kartları
    renewal_calendar_html = ""
    for rc in fl["renewal_forecast_calendar"]:
        subs_badges = " • ".join(html.escape(x) for x in rc["subscribers"])
        renewal_calendar_html += f"""
        <div class="step-box" style="border-left: 4px solid #34D399;">
          <div class="step-num" style="color:#34D399;">📅 VADE: {html.escape(str(rc['date']))}</div>
          <div class="step-val">{rc['count']} Abone</div>
          <div class="step-sub">Beklenen Tahsilat: <strong>{rc['expected_gross_try']:.2f} ₺ Brüt</strong> / <strong style="color:#34D399;">{rc['expected_net_try']:.2f} ₺ Net</strong></div>
          <span class="step-rate">👤 {subs_badges}</span>
        </div>
        """

    # SEKME 2: Doğrulanmış Abone Defteri Satırları
    ledger_rows_html = ""
    for idx_sub, sl in enumerate(sub_ledger, start=1):
        if sl["status"] == "paid_active":
            st_badge = '<span class="badge" style="background:rgba(16,185,129,0.2); color:#34D399;">💳 Ücretli Aktif</span>'
        elif sl["status"] == "offer_code_trial":
            st_badge = f'<span class="badge" style="background:rgba(192,132,252,0.2); color:#C084FC;">🎟️ Kodlu ({html.escape(str(sl["offer_code_name"]))})</span>'
        elif sl["status"] == "cancelled":
            st_badge = '<span class="badge" style="background:rgba(248,113,113,0.2); color:#F87171;">✖ İptal</span>'
        else:
            st_badge = '<span class="badge" style="background:rgba(232,168,85,0.2); color:#E8A855;">⏳ 7 Günlük Deneme</span>'

        ar_badge = (
            '<span style="color:#34D399; font-weight:700;">✔ Açık (Aktif)</span>'
            if sl["auto_renew_enabled"]
            else '<span style="color:#F87171; font-weight:700;">✖ İptal</span>'
        )
        paid_str = (
            f"<strong style='color:#34D399;'>{sl['customer_price_try']:.2f} ₺</strong> <span style='color:#94A3B8;'>(Net {sl['developer_proceeds_try']:.2f} ₺)</span>"
            if sl["customer_price_try"] > 0
            else "<span style='color:#94A3B8;'>0.00 ₺ (Deneme / Kod)</span>"
        )
        next_str = f"{sl['expected_next_price_try']:.2f} ₺ (Net {sl['expected_next_proceeds_try']:.2f} ₺)"
        ledger_rows_html += f"""
        <tr>
          <td style="color:#94A3B8; font-weight:700;">{idx_sub}</td>
          <td style="font-family:monospace; color:#F8FAFC; font-weight:700;" title="Tam Subscriber ID: {html.escape(str(sl['subscriber_id']))}">{html.escape(str(sl['subscriber_short']))}</td>
          <td><strong>{html.escape(str(sl['plan_label']))}</strong></td>
          <td>{st_badge}</td>
          <td>{html.escape(str(sl['started_date']))}</td>
          <td>{html.escape(str(sl['converted_or_renewed_date']))}</td>
          <td style="color:#E8A855; font-weight:700;">{html.escape(str(sl['maturity_or_renewal_date']))}</td>
          <td>{ar_badge}</td>
          <td>{paid_str}</td>
          <td style="color:#CBD5E1;">{next_str}</td>
          <td>{html.escape(str(sl['country']))} • {html.escape(str(sl['device_type']))}</td>
        </tr>
        """

    # SEKME 3: Kanal, ASO & Kod Attribution Matrisi Satırları
    aso_rows_html = ""
    for am in aso_matrix:
        cvr_cell = (
            f"<strong style='color:#34D399;'>%{am['cvr_pct']}</strong> <span style='font-size:11px; color:#94A3B8;'>({html.escape(str(am['cvr_basis']))})</span>"
            if am["cvr_pct"] is not None
            else f"<span style='color:#94A3B8;'>{html.escape(str(am['cvr_basis']))}</span>"
        )
        aso_rows_html += f"""
        <tr>
          <td><strong>{html.escape(str(am['channel']))}</strong></td>
          <td><span class="badge badge-meta">{html.escape(str(am['source_badge']))}</span></td>
          <td style="font-weight:700; color:#E8A855;">{html.escape(str(am['impressions']))}</td>
          <td style="color:#CBD5E1;">{html.escape(str(am['page_views_or_clicks']))}</td>
          <td style="font-family:'Sora',sans-serif; font-weight:800; color:#34D399; font-size:15px;">{am['downloads']}</td>
          <td>{cvr_cell}</td>
          <td style="color:#C084FC; font-weight:600;">{html.escape(str(am['vip_attributed']))}</td>
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
          <td style="font-weight:800; color:#34D399;">{c_cnt} İndirme</td>
          <td style="color:#94A3B8;">%{c_pct}</td>
        </tr>
        """

    # SEKME 4: Günlük Abone Kohort Tutundurma Satırları
    cohort_rows_html = ""
    for ch in pr["subscriber_cohorts"]:
        cohort_rows_html += f"""
        <tr>
          <td style="font-weight:700; color:#F8FAFC;">📅 {html.escape(str(ch['start_date']))} Kohortu</td>
          <td style="font-weight:800; color:#60A5FA;">{ch['started_total']} Abone</td>
          <td style="color:#34D399; font-weight:700;">{ch['paid_converted']} Ücretli</td>
          <td style="color:#C084FC; font-weight:700;">{ch['offer_code']} Yıllık Kodlu</td>
          <td style="color:#E8A855; font-weight:700;">{ch['intro_trial']} 7G Denemede</td>
          <td style="color:#94A3B8;">{ch['cancelled']} İptal</td>
          <td><span class="badge" style="background:rgba(16,185,129,0.2); color:#34D399;">%{ch['retention_pct']} Aktif Korundu</span></td>
        </tr>
        """

    # P1-2: Dönem Filtresi Barı (Tüm Zamanlar / Bugün / Dün / Son 7 Gün)
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

    dashboard_response = HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="tr">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <meta name="referrer" content="no-referrer">
      <title>Mışıl Baby — Kurumsal Büyüme, Abone Defteri & Ürün Analitiği Kokpiti</title>
      <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Sora:wght@600;700;800&display=swap" rel="stylesheet">
      <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
          background: #07090E radial-gradient(circle at 50% 0%, #151E36 0%, #07090E 70%);
          color: #F8FAFC;
          font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
          min-height: 100vh;
          padding: 24px 18px 80px;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}

        /* ÜST BAŞLIK */
        .topbar {{
          display: flex;
          flex-wrap: wrap;
          justify-content: space-between;
          align-items: center;
          gap: 14px;
          margin-bottom: 16px;
          padding-bottom: 18px;
          border-bottom: 1px solid rgba(255,255,255,0.08);
        }}
        .brand {{ display: flex; align-items: center; gap: 14px; }}
        .brand-icon {{
          width: 52px; height: 52px; border-radius: 16px;
          background: linear-gradient(135deg, rgba(232, 168, 85, 0.25), rgba(52, 211, 153, 0.18));
          border: 1px solid rgba(232, 168, 85, 0.45);
          display: flex; align-items: center; justify-content: center;
          font-size: 26px;
        }}
        .brand h1 {{ font-family: 'Sora', sans-serif; font-size: 22px; font-weight: 800; color: #FFF; }}
        .brand p {{ font-size: 13px; color: #94A3B8; margin-top: 3px; }}
        .actions {{ display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }}
        .btn {{
          padding: 10px 15px;
          border-radius: 12px;
          font-size: 12.5px;
          font-weight: 700;
          text-decoration: none;
          display: inline-flex;
          align-items: center;
          gap: 6px;
          border: 1px solid rgba(255,255,255,0.12);
          background: rgba(255,255,255,0.05);
          color: #F8FAFC;
          cursor: pointer;
        }}
        .btn:hover {{ background: rgba(255,255,255,0.12); }}
        .live-pill {{
          display: inline-flex;
          align-items: center;
          gap: 7px;
          padding: 9px 14px;
          border-radius: 99px;
          background: rgba(16, 185, 129, 0.14);
          border: 1px solid rgba(16, 185, 129, 0.35);
          color: #34D399;
          font-size: 12.5px;
          font-weight: 700;
          cursor: pointer;
        }}
        .pulse-dot {{
          width: 8px; height: 8px; border-radius: 50%;
          background: #34D399;
          box-shadow: 0 0 10px #34D399;
        }}

        /* DÖNEM FİLTRESİ BARI */
        .period-bar {{
          display: flex;
          flex-wrap: wrap;
          justify-content: space-between;
          align-items: center;
          gap: 10px;
          margin-bottom: 18px;
          padding: 10px 14px;
          background: rgba(13, 18, 32, 0.75);
          border: 1px solid rgba(255,255,255,0.08);
          border-radius: 14px;
        }}
        .period-pills {{ display: flex; gap: 8px; flex-wrap: wrap; }}
        .period-pill {{
          padding: 7px 13px;
          border-radius: 10px;
          font-size: 12px;
          font-weight: 700;
          text-decoration: none;
          color: #94A3B8;
          background: rgba(255,255,255,0.03);
          border: 1px solid rgba(255,255,255,0.07);
        }}
        .period-pill.active {{
          color: #07090E;
          background: #E8A855;
          border-color: #E8A855;
        }}

        /* 1. BLOK: 4 SABİT KUZEY YILDIZI ÖZET KARTI */
        .kpi-grid {{
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(255px, 1fr));
          gap: 16px;
          margin-bottom: 20px;
        }}
        .bento-card {{
          background: rgba(18, 24, 41, 0.9);
          border: 1px solid rgba(255,255,255,0.09);
          border-radius: 22px;
          padding: 24px 22px;
          box-shadow: 0 12px 32px rgba(0,0,0,0.32);
          margin-bottom: 22px;
        }}
        .kpi-grid .bento-card {{ margin-bottom: 0; }}
        .card-label {{
          font-size: 12.5px;
          font-weight: 800;
          color: #CBD5E1;
          margin-bottom: 10px;
          display: flex;
          align-items: center;
          gap: 8px;
          letter-spacing: 0.3px;
        }}
        .big-num {{
          font-family: 'Sora', sans-serif;
          font-size: 40px;
          font-weight: 800;
          color: #FFF;
          line-height: 1.05;
          margin-bottom: 10px;
        }}
        .card-desc {{
          font-size: 13px;
          color: #94A3B8;
          line-height: 1.5;
        }}
        .card-desc strong {{ color: #F8FAFC; }}

        /* 5 SEKMELİ KURUMSAL NAVİGASYON BARI */
        .tabs-nav {{
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
          margin-bottom: 22px;
          padding: 8px;
          background: rgba(13, 18, 32, 0.85);
          border: 1px solid rgba(255,255,255,0.09);
          border-radius: 18px;
        }}
        .tab-btn {{
          flex: 1;
          min-width: 195px;
          padding: 12px 14px;
          border-radius: 12px;
          border: 1px solid transparent;
          background: transparent;
          color: #94A3B8;
          font-family: 'Plus Jakarta Sans', sans-serif;
          font-size: 13px;
          font-weight: 700;
          cursor: pointer;
          text-align: center;
          transition: all 0.18s ease;
        }}
        .tab-btn:hover {{
          color: #FFF;
          background: rgba(255,255,255,0.05);
        }}
        .tab-btn.active {{
          background: linear-gradient(135deg, rgba(232, 168, 85, 0.22), rgba(52, 211, 153, 0.16));
          border-color: rgba(232, 168, 85, 0.55);
          color: #FFF;
          box-shadow: 0 6px 18px rgba(0,0,0,0.28);
        }}
        .tab-pane {{ display: none; }}
        .tab-pane.active {{ display: block; }}

        /* YAN YANA ADIM KUTULARI */
        .section-head {{
          font-family: 'Sora', sans-serif;
          font-size: 17px;
          font-weight: 700;
          color: #FFF;
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
          background: rgba(255,255,255,0.03);
          border: 1px solid rgba(255,255,255,0.08);
          border-radius: 18px;
          padding: 18px;
          position: relative;
        }}
        .step-num {{
          font-size: 11.5px;
          font-weight: 800;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          margin-bottom: 6px;
        }}
        .step-val {{
          font-family: 'Sora', sans-serif;
          font-size: 26px;
          font-weight: 800;
          color: #FFF;
          margin-bottom: 4px;
        }}
        .step-sub {{ font-size: 12.5px; color: #94A3B8; line-height: 1.45; }}
        .step-rate {{
          display: inline-block;
          margin-top: 10px;
          padding: 4px 10px;
          border-radius: 99px;
          font-size: 11.5px;
          font-weight: 700;
          background: rgba(255,255,255,0.06);
          color: #E2E8F0;
        }}

        /* TEK ÇUBUKLU KÜMÜLATİF İNDİRME GRAFİĞİ */
        .chart-toggle {{ display: flex; gap: 8px; }}
        .chart-toggle button {{
          padding: 8px 14px;
          border-radius: 10px;
          border: 1px solid rgba(255,255,255,0.14);
          background: rgba(255,255,255,0.04);
          color: #CBD5E1;
          font-size: 12px;
          font-weight: 700;
          cursor: pointer;
        }}
        .chart-toggle button.active {{
          background: #34D399;
          color: #07090E;
          border-color: #34D399;
        }}
        .timeline-grid {{
          display: grid;
          grid-template-columns: repeat({max(1, len(t_days))}, 1fr);
          gap: 10px;
          height: 210px;
          align-items: end;
          padding-top: 26px;
        }}
        .t-col {{
          display: flex;
          flex-direction: column;
          align-items: center;
          height: 100%;
          padding: 8px 4px;
          border-radius: 14px;
        }}
        .t-today {{
          background: rgba(52, 211, 153, 0.09);
          border: 1px dashed rgba(52, 211, 153, 0.45);
        }}
        .t-top-val {{ font-family: 'Sora', sans-serif; font-size: 14px; font-weight: 800; margin-bottom: 6px; }}
        .t-bars-pair {{
          flex: 1;
          width: 100%;
          display: flex;
          align-items: flex-end;
          justify-content: center;
        }}
        .t-bar {{ width: 65%; max-width: 34px; border-radius: 8px 8px 3px 3px; }}
        .t-lbl {{ font-size: 12px; color: #CBD5E1; margin-top: 8px; font-weight: 700; }}

        /* 3 YAN YANA GÖRSEL HALKA (DONUT) */
        .donuts-grid {{
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(330px, 1fr));
          gap: 16px;
          margin-bottom: 22px;
        }}
        .donuts-grid .bento-card {{ margin-bottom: 0; }}
        .donut-wrap {{
          display: flex;
          align-items: center;
          gap: 18px;
          flex-wrap: wrap;
        }}
        .donut-legend {{ flex: 1; min-width: 160px; display: flex; flex-direction: column; gap: 8px; }}
        .donut-leg-row {{
          display: flex;
          justify-content: space-between;
          align-items: center;
          font-size: 13px;
          padding: 7px 10px;
          border-radius: 10px;
          background: rgba(255,255,255,0.03);
        }}
        .donut-leg-left {{ display: flex; align-items: center; gap: 8px; }}
        .donut-dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
        .donut-pct {{ color: #94A3B8; font-size: 11.5px; margin-left: 3px; }}

        /* YORUMLAR & TABLOLAR */
        .reviews-grid {{
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
          gap: 14px;
        }}
        .review-bubble {{
          background: rgba(13, 18, 31, 0.92);
          border: 1px solid rgba(232, 168, 85, 0.28);
          border-radius: 16px;
          padding: 18px;
        }}
        .review-head {{ display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }}
        .review-body {{ font-size: 14px; color: #F8FAFC; line-height: 1.55; margin-bottom: 8px; }}
        .review-foot {{ font-size: 11.5px; color: #94A3B8; font-weight: 600; }}

        .badge {{
          display: inline-flex;
          align-items: center;
          padding: 4px 10px;
          border-radius: 99px;
          font-size: 11.5px;
          font-weight: 700;
        }}
        .badge-meta {{ background: rgba(59, 130, 246, 0.18); color: #60A5FA; }}
        .badge-gp {{ background: rgba(34, 197, 94, 0.18); color: #4ADE80; }}
        .toast-banner {{
          background: rgba(16,185,129,0.16);
          border: 1px solid rgba(16,185,129,0.4);
          color: #34D399;
          padding: 14px 18px;
          border-radius: 16px;
          margin-bottom: 18px;
          font-size: 13.5px;
          font-weight: 600;
        }}
        .table-wrap {{ overflow-x: auto; margin-top: 10px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
        th {{ text-align: left; padding: 11px 10px; color: #94A3B8; border-bottom: 1px solid rgba(255,255,255,0.1); font-weight: 700; }}
        td {{ padding: 11px 10px; border-bottom: 1px solid rgba(255,255,255,0.05); }}
        tr:hover td {{ background: rgba(255,255,255,0.02); }}
      </style>
    </head>
    <body>
      <div class="container">
        <!-- ÜST BAŞLIK -->
        <div class="topbar">
          <div class="brand">
            <div class="brand-icon">🌙</div>
            <div>
              <h1>Mışıl Baby — Kurumsal Büyüme, Abone Defteri & Ürün Analitiği</h1>
              <p>Resmi Apple App Store API + Google Play API + Canlı PostgreSQL Veri Ambarı ({html.escape(str(sb.get('last_synced_at', '')))})</p>
            </div>
          </div>
          <div class="actions">
            <div class="live-pill" onclick="toggleAutoRefresh()" id="liveToggleBtn">
              <span class="pulse-dot" id="liveDot"></span>
              <span id="liveCountdown">Canlı: 15s</span>
            </div>
            <a href="/api/v1/analytics/export.csv" class="btn">📥 CSV İndir</a>
            <a href="/api/v1/analytics/dashboard?sync=1&period={clean_period}" class="btn">🔄 Mağazaları Güncelle</a>
          </div>
        </div>

        {sync_banner}

        <!-- P1-2: AKTİF DÖNEM FİLTRESİ BARI -->
        <div class="period-bar">
          <div style="font-size:12.5px; color:#CBD5E1; font-weight:700;">
            🔎 Köprü & Etkileşim Dönem Filtresi: <strong style="color:#E8A855;">{html.escape(s['period_label'])}</strong>
            <span style="color:#94A3B8; margin-left:8px;">({s['active_human_count']} Tekil İnsan • Bugün: {s['today_unique_clicks']} • Dün: {s['yesterday_unique_clicks']})</span>
          </div>
          <div class="period-pills">
            {period_pills_html}
          </div>
        </div>

        <!-- SABİT ÜST BLOK: 4 KUZEY YILDIZI KARTI -->
        <div class="kpi-grid">
          <div class="bento-card" style="border-top: 3px solid #E8A855;">
            <div class="card-label">👁️ APP STORE GÖRÜNTÜLENMESİ</div>
            <div class="big-num" style="color: #E8A855;">{f_imp:,}</div>
            <div class="card-desc">
              Apple API kanıtlı: <strong>{kpis['impressions_unique']:,} tekil cihazda</strong> görüldü (<strong>{imp_search:,}</strong> Arama + <strong>{imp_browse}</strong> Keşfet).
            </div>
          </div>

          <div class="bento-card" style="border-top: 3px solid #60A5FA;">
            <div class="card-label">👆 İNCELEYEN & TIKLAYAN</div>
            <div class="big-num" style="color: #60A5FA;">{f_vis}</div>
            <div class="card-desc">
              <strong>{kpis['store_page_views']} kez</strong> (<strong>{sb.get('apple_page_views_unique', 0)} tekil cihaz</strong>) mağaza sayfası açıldı, <strong>{s['total_raw']} kez</strong> (<strong>{kpis['bridge_unique_clicks']} tekil kişi</strong>) sosyal medyadan tıkladı.
            </div>
          </div>

          <div class="bento-card" style="border-top: 3px solid #34D399;">
            <div class="card-label">📲 TELEFONUNA İNDİREN</div>
            <div class="big-num" style="color: #34D399;">{f_dl}</div>
            <div class="card-desc">
              <strong>{kpis['ios_downloads']} iPhone</strong> (App Store Sales API) ve <strong>{kpis['android_downloads']} Android</strong> (Google Play / Sinyal DB) telefona kuruldu.
            </div>
          </div>

          <div class="bento-card" style="border-top: 3px solid #C084FC;">
            <div class="card-label">👑 DOĞRULANMIŞ VIP, MRR & PUAN</div>
            <div class="big-num" style="color: #C084FC;">{f_vip} VIP</div>
            <div class="card-desc">
              <strong>{paid_conv} Ücretli Satış</strong> ({paid_cust_try:.2f} ₺ / Net {paid_try:.2f} ₺) • <strong>{offer_code_subs} Kodlu</strong> ({html.escape(offer_code_name)}) • <strong>{active_trials} Deneme</strong> (Beklenen Net {fl['pipeline_7d_mrr_net_try']:.2f} ₺) • <strong>{avg_stars_label}</strong> ({reviews_total_cnt} yorum).
            </div>
          </div>
        </div>

        <!-- 5 SEKMELİ KURUMSAL NAVİGASYON BARI -->
        <div class="tabs-nav" role="tablist">
          <button class="tab-btn active" id="tabBtn_tab1" onclick="switchTab('tab1')">🌟 1. Yönetici Özeti (3 Sn)</button>
          <button class="tab-btn" id="tabBtn_tab2" onclick="switchTab('tab2')">💎 2. Gelir, MRR & Abone Defteri ({len(sub_ledger)} VIP)</button>
          <button class="tab-btn" id="tabBtn_tab3" onclick="switchTab('tab3')">🎯 3. Kanal, ASO & Kod Attribution</button>
          <button class="tab-btn" id="tabBtn_tab4" onclick="switchTab('tab4')">👶 4. Ürün Nabzı & Kohort Tutundurma</button>
          <button class="tab-btn" id="tabBtn_tab5" onclick="switchTab('tab5')">⚡ 5. Yorumlar ({avg_stars_label}) & Canlı Akış</button>
        </div>

        <!-- SEKME 1: YÖNETİCİ ÖZETİ -->
        <div id="tabPane_tab1" class="tab-pane active">
          <div class="bento-card">
            <div class="section-head">
              <span>🧭 Ebeveynlerin 4 Adımlı Yolculuğu (Görmeden ➔ Doğrulanmış VIP Aboneliğe)</span>
            </div>
            <div class="steps-grid">
              <div class="step-box" style="border-left: 4px solid #E8A855;">
                <div class="step-num" style="color:#E8A855;">1. ADIM • KARŞILAŞMA</div>
                <div class="step-val">{f_imp:,}</div>
                <div class="step-sub">App Store'da Mışıl Baby görüntülendi ({imp_search:,} Arama + {imp_browse} Keşfet)</div>
                <span class="step-rate">👥 {kpis['impressions_unique']:,} Tekil Cihaz</span>
              </div>

              <div class="step-box" style="border-left: 4px solid #60A5FA;">
                <div class="step-num" style="color:#60A5FA;">2. ADIM • İNCELEME</div>
                <div class="step-val">{f_vis}</div>
                <div class="step-sub">Mağaza sayfası açıldı ({kpis['store_page_views']}) veya sosyal linke tıklandı ({kpis['bridge_unique_clicks']})</div>
                <span class="step-rate">➔ İlgilenme Oranı: %{vis_of_imp_pct}</span>
              </div>

              <div class="step-box" style="border-left: 4px solid #34D399;">
                <div class="step-num" style="color:#34D399;">3. ADIM • İNDİRME</div>
                <div class="step-val">{f_dl}</div>
                <div class="step-sub">Uygulamayı telefonuna indirdi ({kpis['ios_downloads']} iOS + {kpis['android_downloads']} Android)</div>
                <span class="step-rate">➔ İndirmeye Dönüşüm: %{dl_of_vis_pct}</span>
              </div>

              <div class="step-box" style="border-left: 4px solid #C084FC;">
                <div class="step-num" style="color:#C084FC;">4. ADIM • VIP & MEMNUNİYET</div>
                <div class="step-val">{f_vip} VIP • {avg_stars_label}</div>
                <div class="step-sub">{paid_conv} ücretli ({paid_cust_try:.2f} ₺) + {offer_code_subs} kodlu ({html.escape(offer_code_name)}) + {active_trials} deneme</div>
                <span class="step-rate">➔ Aktif VIP Oranı: %{vip_of_dl_pct}</span>
              </div>
            </div>
          </div>

          <div class="bento-card">
            <div class="section-head">
              <div>
                <span>📈 Gün-Gün Toplam İndirme Yükselişi ({html.escape(timeline_range_lbl)}: {f_dl} İndirme — {kpis['ios_downloads']} iOS + {kpis['android_downloads']} Android)</span>
              </div>
              <div class="chart-toggle">
                <button id="btnCumChart" class="active" onclick="switchChartMode('cum')">📈 Toplam Birikimli ({f_dl} İndirme)</button>
                <button id="btnDailyChart" onclick="switchChartMode('daily')">📊 Günlük Yeni İndirme ({kpis['ios_downloads']} iOS)</button>
              </div>
            </div>

            <div id="chartCumWrap" class="timeline-grid">
              {cum_bars_html}
            </div>
            <div id="chartDailyWrap" class="timeline-grid" style="display:none;">
              {daily_bars_html}
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
            <div class="bento-card" style="border-left: 4px solid #34D399;">
              <div class="card-label">💵 TAHSİL EDİLEN GERÇEK GELİR & MRR</div>
              <div class="big-num" style="color:#34D399;">{fl['realized_net_proceeds_try']:.2f} ₺ <span style="font-size:16px; color:#94A3B8;">Net</span></div>
              <div class="card-desc">
                Brüt Tahsilat: <strong>{fl['realized_gross_try']:.2f} ₺</strong> • Aktif Yinelenen MRR: <strong>{fl['active_paid_mrr_net_try']:.2f} ₺ Net/Ay</strong> (<strong>{fl['paid_subs_count']} Ücretli Abone</strong>).
              </div>
            </div>

            <div class="bento-card" style="border-left: 4px solid #E8A855;">
              <div class="card-label">⏳ 7 GÜNLÜK DENEME HATTI (PIPELINE MRR)</div>
              <div class="big-num" style="color:#E8A855;">{fl['pipeline_7d_mrr_net_try']:.2f} ₺ <span style="font-size:16px; color:#94A3B8;">Net</span></div>
              <div class="card-desc">
                <strong>{fl['pipeline_7d_trials_count']} aktif 7 günlük deneme</strong> (Brüt <strong>{fl['pipeline_7d_mrr_gross_try']:.2f} ₺</strong>) • Otomatik yenilemesi açık beklenen vade hattı.
              </div>
            </div>

            <div class="bento-card" style="border-left: 4px solid #60A5FA;">
              <div class="card-label">🎯 OLGUNLAŞAN DENEME ➔ ÜCRETLİ DÖNÜŞÜM</div>
              <div class="big-num" style="color:#60A5FA;">{html.escape(fl['matured_trial_to_paid_cvr_str'])}</div>
              <div class="card-desc">
                Kesim tarihi (<code>&lt;= {html.escape(fl['matured_cutoff_date'])}</code>): Olgunlaşan <strong>{fl['matured_trials_total']} aboneden {fl['matured_trials_converted']} tanesi</strong> ücretli pakete geçti (<strong>{fl['cancelled_subs_count']} İptal</strong>).
              </div>
            </div>

            <div class="bento-card" style="border-left: 4px solid #C084FC;">
              <div class="card-label">🎟️ KAMPANYA KODU & OTO-YENİLEME SAĞLIĞI</div>
              <div class="big-num" style="color:#C084FC;">%{fl['auto_renew_on_pct']} <span style="font-size:16px; color:#94A3B8;">Aktif</span></div>
              <div class="card-desc">
                <strong>{fl['offer_code_subs_count']} Kodlu VIP</strong> (<code>{html.escape(offer_code_name)}</code>) • Toplam <strong>{len(sub_ledger)} Tekil Abone</strong> defterde kayıtlı.
              </div>
            </div>
          </div>

          <div class="bento-card">
            <div class="section-head">
              <span>📅 7 Günlük Deneme ➔ Ücretli Tahsilat Takvimi (Apple SUBSCRIBER 1_3 Vade Projeksiyonu)</span>
              <span class="badge" style="background:rgba(16,185,129,0.18); color:#34D399;">Toplam Beklenen: +{fl['pipeline_7d_mrr_gross_try']:.2f} ₺ Brüt / +{fl['pipeline_7d_mrr_net_try']:.2f} ₺ Net</span>
            </div>
            <div class="steps-grid">
              {renewal_calendar_html}
            </div>
          </div>

          <div class="bento-card">
            <div class="section-head">
              <span>📒 Doğrulanmış Tekil Abone Defteri ({len(sub_ledger)} Kayıtlı VIP • Apple SUBSCRIBER 1_3 API)</span>
              <span class="badge badge-meta">Vendor #94806500 • Dinamik DB</span>
            </div>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Abone ID</th>
                    <th>Paket</th>
                    <th>Durum / Kampanya</th>
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
                <div class="step-box" style="border-left: 4px solid #60A5FA;">
                  <div class="step-num" style="color:#60A5FA;">META REKLAM KÖPRÜSÜ (/ios)</div>
                  <div class="step-val">{meta['unique_clicks']} Tekil Kişi</div>
                  <div class="step-sub"><strong>{meta['ios_clicks']} iPhone</strong> App Store'a + <strong>{meta['android_clicks']} Android</strong> telefon otomatik Google Play'e yönlendirildi.</div>
                  <span class="step-rate">Toplam {meta['raw_hits']} Ham İstek</span>
                </div>
                <div class="step-box" style="border-left: 4px solid #C084FC;">
                  <div class="step-num" style="color:#C084FC;">INSTAGRAM BIO (/download)</div>
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
            <div class="bento-card" style="border-left: 4px solid #60A5FA;">
              <div class="card-label">📱 RESMİ UYGULAMA OTURUMLARI</div>
              <div class="big-num" style="color:#60A5FA;">{pr['total_tracked_sessions']}</div>
              <div class="card-desc">
                Apple r4 API doğrulanmış <strong>{pr['apple_official_sessions']} oturum</strong> / canlı telemetri maksimumu • Ortalama süre: <strong>{pr['avg_session_duration_sec']} saniye</strong>.
              </div>
            </div>

            <div class="bento-card" style="border-left: 4px solid #34D399;">
              <div class="card-label">👶 AKTİF CİHAZ & BEBEK PROFİLİ</div>
              <div class="big-num" style="color:#34D399;">{pr['optin_active_devices']} Cihaz</div>
              <div class="card-desc">
                Telemetri paylaşımı açık <strong>{sb.get('apple_sessions_optin_devices', 0)} iOS cihaz</strong> • Veritabanı kayıtlı bebek profili: <strong>{pr['babies_count']}</strong>.
              </div>
            </div>

            <div class="bento-card" style="border-left: 4px solid #A855F7;">
              <div class="card-label">🌙 GECE NÖBETİ KULLANIMI (21:00–04:00)</div>
              <div class="big-num" style="color:#A855F7;">%{nvd['night_pct']}</div>
              <div class="card-desc">
                <strong>{nvd['night_clicks']} Gece</strong> vs <strong>{nvd['day_clicks']} Gündüz</strong> ebeveyn etkileşimi • En yoğun saatler: <strong>{top_h1}</strong> ve <strong>{top_h2}</strong>.
              </div>
            </div>

            <div class="bento-card" style="border-left: 4px solid #E8A855;">
              <div class="card-label">🛡️ ABONE KOHORT TUTUNDURMA (RETENTION)</div>
              <div class="big-num" style="color:#E8A855;">{html.escape(pr['overall_retention_str'])}</div>
              <div class="card-desc">
                Toplam <strong>{len(pr['subscriber_cohorts'])} ayrı günlük kohorttaki {len(sub_ledger)} abonenin</strong> aktif tutundurma oranı (<strong>{fl['cancelled_subs_count']} İptal</strong>).
              </div>
            </div>
          </div>

          <div class="bento-card">
            <div class="section-head">
              <span>📊 Günlük Abone Kohort Tutundurma Matrisi (Başlangıç Tarihine Göre Yaşam Döngüsü)</span>
              <span class="badge" style="background:rgba(16,185,129,0.2); color:#34D399;">{len(pr['subscriber_cohorts'])} Kohort • Tutundurma: {html.escape(pr['overall_retention_str'])}</span>
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
              <div class="step-box" style="border-left: 4px solid #34D399;">
                <div class="step-num" style="color:#34D399;">UYKU & SES MOTORU</div>
                <div class="step-val">{pr['sleep_logs_count']} Kayıt</div>
                <div class="step-sub">Bulut senkronizasyonlu uyku seansı ve <code>sleep_sound_play</code> canlı sinyal kancası aktif.</div>
              </div>
              <div class="step-box" style="border-left: 4px solid #60A5FA;">
                <div class="step-num" style="color:#60A5FA;">AĞLAMA ANALİZİ (AI)</div>
                <div class="step-val">{pr['cry_events_count']} Analiz</div>
                <div class="step-sub">Yapay zeka ağlama tespiti ve <code>cry_analysis</code> telemetri sayacı aktif.</div>
              </div>
              <div class="step-box" style="border-left: 4px solid #E8A855;">
                <div class="step-num" style="color:#E8A855;">GÜNLÜK RUTİN & DADI AI</div>
                <div class="step-val">{pr['routine_logs_count'] + pr['dadi_chats_count']} Etkileşim</div>
                <div class="step-sub">{pr['routine_logs_count']} rutin kaydı + {pr['dadi_chats_count']} Bilge Dadı sohbet mesajı.</div>
              </div>
              <div class="step-box" style="border-left: 4px solid #C084FC;">
                <div class="step-num" style="color:#C084FC;">GERÇEK ZAMANLI VIP SİNYALİ</div>
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
              <span class="badge" style="background:rgba(251,191,36,0.2); color:#FBBF24;">{avg_stars_label} Puan</span>
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
          var cumW = document.getElementById('chartCumWrap');
          var dailyW = document.getElementById('chartDailyWrap');
          var bCum = document.getElementById('btnCumChart');
          var bDaily = document.getElementById('btnDailyChart');
          if (mode === 'daily') {{
            cumW.style.display = 'none';
            dailyW.style.display = 'grid';
            bCum.classList.remove('active');
            bDaily.classList.add('active');
          }} else {{
            cumW.style.display = 'grid';
            dailyW.style.display = 'none';
            bCum.classList.add('active');
            bDaily.classList.remove('active');
          }}
          localStorage.setItem('mishil_dash_chart_mode', mode);
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

          var savedChartMode = localStorage.getItem('mishil_dash_chart_mode');
          if (savedChartMode === 'daily' || savedChartMode === 'cum') {{
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
              try {{ sessionStorage.setItem('mishil_dash_scroll_y', String(window.scrollY || 0)); }} catch (_se) {{}}
              window.location.reload();
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
