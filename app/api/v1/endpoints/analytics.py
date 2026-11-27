import asyncio
import concurrent.futures
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
from types import SimpleNamespace
from typing import Optional, Dict, Any, List, NamedTuple, Tuple
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Request, status, Query, Header, Form
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, inspect, select, text

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
    "meta_ads_ios": "Meta Reklamları (/ios Eski Köprü)",
    "meta_app_installs_android": "Meta App Installs (Android Doğrudan)",
    "meta_app_installs_ios": "Meta App Installs (iOS 14+ ATT/SKAdNetwork)",
    "instagram_bio": "Instagram Bio (/download Tekil Köprü)",
    "google_play_organic": "Google Play (Android)",
}

# v4.56.5 Köprü Sıfırlama Kesiti: 2026-11-22 07:38 UTC öncesindeki tüm eski (/ios, /download, /android, /app-store)
# köprü tıklamaları tek seferlik temizlenerek yalnızca aktif Instagram Bio (/download)
# köprüsünün 0'dan gerçek tıklamaları ölçmesi sağlanır.
BRIDGE_RESET_V4564_STATE_KEY = "bridge_reset_v4565_all_routes_done"
BRIDGE_RESET_V4564_CUTOFF_UTC = datetime(2026, 11, 22, 7, 38, 0, tzinfo=timezone.utc)
META_APP_ID_OFFICIAL = "1093539003520092"


def _parse_semver_tuple(ver_str: Optional[str]) -> Tuple[int, int, int]:
    """'4.56.0' gibi sürüm dizelerini güvenli (major, minor, patch) int üçlüsüne çevirir."""
    if not ver_str:
        return (0, 0, 0)
    nums = re.findall(r"\d+", str(ver_str))
    p0 = int(nums[0]) if len(nums) > 0 else 0
    p1 = int(nums[1]) if len(nums) > 1 else 0
    p2 = int(nums[2]) if len(nums) > 2 else 0
    return (p0, p1, p2)
FX_RATES_TO_TRY: Dict[str, float] = {
    "TRY": 1.0,
    "EUR": float(os.environ.get("MISIL_FX_EUR_TRY", "46.50")),
    "USD": float(os.environ.get("MISIL_FX_USD_TRY", os.environ.get("MISIL_APPLE_USD_TRY", "42.85"))),
    "GBP": float(os.environ.get("MISIL_FX_GBP_TRY", "55.00")),
    "AUD": float(os.environ.get("MISIL_FX_AUD_TRY", "28.00")),
    "CAD": float(os.environ.get("MISIL_FX_CAD_TRY", "31.00")),
    "CHF": float(os.environ.get("MISIL_FX_CHF_TRY", "48.50")),
    "AED": float(os.environ.get("MISIL_FX_AED_TRY", "11.67")),
    "SAR": float(os.environ.get("MISIL_FX_SAR_TRY", "11.42")),
    "PLN": float(os.environ.get("MISIL_FX_PLN_TRY", "10.80")),
    "RON": float(os.environ.get("MISIL_FX_RON_TRY", "9.35")),
    "AZN": float(os.environ.get("MISIL_FX_AZN_TRY", "25.20")),
    "KZT": float(os.environ.get("MISIL_FX_KZT_TRY", "0.088")),
    "UZS": float(os.environ.get("MISIL_FX_UZS_TRY", "0.00335")),
    "INR": float(os.environ.get("MISIL_FX_INR_TRY", "0.508")),
    "BRL": float(os.environ.get("MISIL_FX_BRL_TRY", "7.45")),
    "MXN": float(os.environ.get("MISIL_FX_MXN_TRY", "2.12")),
    "BGN": float(os.environ.get("MISIL_FX_BGN_TRY", "23.75")),
    "HUF": float(os.environ.get("MISIL_FX_HUF_TRY", "0.114")),
    "CZK": float(os.environ.get("MISIL_FX_CZK_TRY", "1.83")),
    "UAH": float(os.environ.get("MISIL_FX_UAH_TRY", "1.03")),
    "GEL": float(os.environ.get("MISIL_FX_GEL_TRY", "15.65")),
    "IDR": float(os.environ.get("MISIL_FX_IDR_TRY", "0.0027")),
    "PKR": float(os.environ.get("MISIL_FX_PKR_TRY", "0.154")),
    "PHP": float(os.environ.get("MISIL_FX_PHP_TRY", "0.73")),
    "EGP": float(os.environ.get("MISIL_FX_EGP_TRY", "0.87")),
    "COP": float(os.environ.get("MISIL_FX_COP_TRY", "0.0098")),
    # Google Play & Apple 174/175 Ülke Tam Kapsam (66/66 Para Birimi)
    "ARS": 0.042,
    "BDT": 0.36,
    "BOB": 6.20,
    "CLP": 0.044,
    "CNY": 5.95,
    "CRC": 0.084,
    "DKK": 6.23,
    "DZD": 0.32,
    "ETB": 0.34,
    "GHS": 2.75,
    "HKD": 5.50,
    "ILS": 11.50,
    "IQD": 0.0327,
    "JOD": 60.40,
    "JPY": 0.28,
    "KES": 0.33,
    "KRW": 0.031,
    "LKR": 0.145,
    "MAD": 4.30,
    "MMK": 0.020,
    "MNT": 0.0125,
    "MOP": 5.34,
    "MYR": 9.65,
    "NGN": 0.026,
    "NOK": 3.92,
    "NZD": 25.50,
    "PEN": 11.40,
    "PYG": 0.0055,
    "QAR": 11.75,
    "RSD": 0.397,
    "RUB": 0.44,
    "SEK": 4.02,
    "SGD": 32.10,
    "THB": 1.25,
    "TWD": 1.33,
    "TZS": 0.016,
    "VND": 0.0017,
    "XAF": 0.071,
    "XOF": 0.071,
    "ZAR": 2.38,
}

# App Store Connect Sales & Trends ve RevenueCat V2 USD/TRY referans paritesi (149.99 ₺ ≈ $3.50, 599.99 ₺ ≈ $14.00)
APPLE_TRENDS_USD_TRY_RATE: float = float(os.environ.get("MISIL_APPLE_USD_TRY", "42.85"))


def _convert_try_to_usd(amount_try: float) -> float:
    return round(float(amount_try or 0.0) / max(1.0, APPLE_TRENDS_USD_TRY_RATE), 2)


# Doğrulanmış App Store / Google Play katalog tarife referansı (Brüt TRY, Net Hakediş TRY)
# Apple Small Business Program (%15 komisyon, Türkiye %20 KDV düşüldükten sonra net oran: 0.67292)
# Google Play Abonelik Programı (%15 komisyon, Türkiye %20 KDV düşüldükten sonra net oran: 0.727)
IOS_SBP_15_PROCEEDS_RATIO: float = 0.67292
ANDROID_15_PROCEEDS_RATIO: float = 0.727
DEFAULT_PLAN_PRICING_TRY: Dict[str, tuple] = {
    "misil_monthly": (149.99, 100.93),
    "misil_annual": (599.99, 403.75),
    "misilaylik": (149.99, 109.04),
    "misil": (599.99, 436.19),
}

# İlk Ay İndirimli (Introductory Pay-As-You-Go / Up-Front) Katalog Referansı (49.99 TRY Brüt)
INTRO_1M_DISCOUNTED_GROSS_TRY: float = 49.99

# Mağaza TSV / Orders API gerçek gözlemlerinden dinamik güncellenen net hakediş çarpanı
# (%15 Apple Small Business Program onaylandığı için taban 0.67292; Google Play %15 abonelik kademesinde taban 0.727).
_DYNAMIC_PROCEEDS_RATIOS: Dict[str, float] = {
    "ios": IOS_SBP_15_PROCEEDS_RATIO,
    "android": ANDROID_15_PROCEEDS_RATIO,
}
_PROCEEDS_RATIO_LOCK = threading.RLock()


def get_dynamic_proceeds_ratio(platform: Optional[str] = "ios") -> float:
    """Platform bazlı en güncel gerçek net hakediş çarpanını döndürür (thread-safe, %15 program taban korumalı)."""
    plat = "android" if (platform or "ios").strip().lower() == "android" else "ios"
    floor_ratio = ANDROID_15_PROCEEDS_RATIO if plat == "android" else IOS_SBP_15_PROCEEDS_RATIO
    with _PROCEEDS_RATIO_LOCK:
        return max(floor_ratio, float(_DYNAMIC_PROCEEDS_RATIOS.get(plat, floor_ratio)))


def observe_proceeds_ratio(platform: Optional[str], gross_try: float, net_try: float) -> float:
    """
    Apple SUBSCRIBER TSV ('Developer Proceeds' / 'Customer Price') veya Google Play Orders API
    ('developerRevenueInBuyerCurrency' / 'total') üzerinden gelen gerçek tahsilat oranını gözlemler.
    Apple Small Business Program (%15 komisyon -> 0.67292) ve Google Play (%15 komisyon -> 0.727) onaylı olduğu için
    onay öncesi geçmiş %30 komisyonlu (0.55417) TSV satırları ileriye dönük net hakediş oranını tabanın altına çekmez.
    """
    plat = "android" if (platform or "ios").strip().lower() == "android" else "ios"
    floor_ratio = ANDROID_15_PROCEEDS_RATIO if plat == "android" else IOS_SBP_15_PROCEEDS_RATIO
    with _PROCEEDS_RATIO_LOCK:
        if gross_try > 10.0 and net_try > 0.0:
            ratio = round(float(net_try) / float(gross_try), 5)
            if floor_ratio <= ratio <= 0.90:
                _DYNAMIC_PROCEEDS_RATIOS[plat] = ratio
            elif _DYNAMIC_PROCEEDS_RATIOS.get(plat, 0.0) < floor_ratio:
                _DYNAMIC_PROCEEDS_RATIOS[plat] = floor_ratio
        return max(floor_ratio, float(_DYNAMIC_PROCEEDS_RATIOS.get(plat, floor_ratio)))


def _extract_single_period_standard_ref(
    product_id: Optional[str],
    customer_price_try: float,
    developer_proceeds_try: float,
    expected_next_price_try: float = 0.0,
    expected_next_proceeds_try: float = 0.0,
    offer_type: Optional[str] = None,
    platform: Optional[str] = "ios",
) -> Optional[tuple]:
    """
    Kümülatif (2+ ay yenilenmiş: 299.98 TL vb.) veya ilk ay indirimli (49.99 TL) abone satırlarının
    standart aylık/yıllık birim fiyat referansını (149.99 TL / 599.99 TL) bozmasını engeller.
    """
    plat = "android" if (platform or "ios").strip().lower() == "android" else "ios"
    is_ann = _is_annual_product(product_id)
    std_cat_gross = 599.99 if is_ann else 149.99

    if customer_price_try > 0 and developer_proceeds_try > 0:
        observe_proceeds_ratio(plat, customer_price_try, developer_proceeds_try)

    ratio = get_dynamic_proceeds_ratio(plat)

    # 1) Önce expected_next_price_try tek dönemlik standart fiyata yakınsa onu baz al
    if expected_next_price_try > 0 and abs(expected_next_price_try - std_cat_gross) <= 15.0:
        e_net = (
            expected_next_proceeds_try
            if expected_next_proceeds_try > 0 and abs((expected_next_proceeds_try / expected_next_price_try) - ratio) <= 0.05
            else round(expected_next_price_try * ratio, 2)
        )
        return (round(float(expected_next_price_try), 2), round(float(e_net), 2))

    # 2) customer_price_try tek dönemlik standart fiyata yakınsa (kümülatif 2x veya 49.99 intro değilse)
    if (
        offer_type != "intro_1m_discounted"
        and customer_price_try > 0
        and abs(customer_price_try - std_cat_gross) <= 15.0
    ):
        c_net = (
            developer_proceeds_try
            if developer_proceeds_try > 0 and abs((developer_proceeds_try / customer_price_try) - ratio) <= 0.05
            else round(customer_price_try * ratio, 2)
        )
        return (round(float(customer_price_try), 2), round(float(c_net), 2))

    return None


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
    önce veritabanındaki gerçek tek-dönemlik ücretli işlem referansından, henüz yoksa resmi katalog
    tarifesinden ve dinamik net hakediş oranından (%15 Small Business / %30 standart) çözer.
    """
    plat = "android" if (platform or "ios").strip().lower() == "android" else "ios"
    net_ratio = get_dynamic_proceeds_ratio(plat)
    is_ann = _is_annual_product(product_id)
    std_cat_gross = 599.99 if is_ann else 149.99
    # Kümülatif (örn. 299.98 TL), eski 799.99 TL veya 49.99 TL ilk ay indirimli tutarların standart yenileme referansı olmasını engelle
    if (
        paid_ref_gross > 0
        and not (is_ann and round(float(paid_ref_gross), 2) == 799.99)
        and (is_ann or paid_ref_gross >= 100.0)
        and paid_ref_gross <= (std_cat_gross * 1.35)
    ):
        if paid_ref_net > 0:
            observe_proceeds_ratio(plat, paid_ref_gross, paid_ref_net)
            net_ratio = get_dynamic_proceeds_ratio(plat)
        net_val = (
            paid_ref_net
            if paid_ref_net > 0 and abs((paid_ref_net / paid_ref_gross) - net_ratio) <= 0.05
            else round(paid_ref_gross * net_ratio, 2)
        )
        return (round(float(paid_ref_gross), 2), round(float(net_val), 2))
    pid = (product_id or "").strip().lower()
    if pid in DEFAULT_PLAN_PRICING_TRY:
        base_g, base_n = DEFAULT_PLAN_PRICING_TRY[pid]
    elif plat == "android":
        base_g, base_n = DEFAULT_PLAN_PRICING_TRY["misil" if is_ann else "misilaylik"]
    else:
        base_g, base_n = DEFAULT_PLAN_PRICING_TRY["misil_annual" if is_ann else "misil_monthly"]
    # Dinamik oran varsayılan %15 program tabanından farklıysa yeni net oranı uygula
    default_static_ratio = ANDROID_15_PROCEEDS_RATIO if plat == "android" else IOS_SBP_15_PROCEEDS_RATIO
    if abs(net_ratio - default_static_ratio) > 0.005:
        return (base_g, round(base_g * net_ratio, 2))
    return (base_g, base_n)

# Bellek içi çalışma zamanı önbelleği için kısa süreli kilit (Ağ G/Ç işlemleri bu kilit dışında yapılır)
_BASELINE_LOCK = threading.RLock()

# first_open / daily_active sinyal kaydı için eşzamanlı çift-kayıt (TOCTOU) koruması.
_APP_OPEN_SIGNAL_LOCK = threading.Lock()
# BackgroundTasks thread-pool içinde eşzamanlı 15sn BridgeClick tekilleştirmesi için atomik kilit.
_BRIDGE_CLICK_LOCK = threading.Lock()
_SCHEMA_INIT_LOCK = threading.Lock()

_SCHEMA_INITIALIZED = False
_BRIDGE_TABLE_READY = False

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
    "CH": {"flag": "🇨🇭", "name": "İsviçre"},
    "CA": {"flag": "🇨🇦", "name": "Kanada"},
    "AT": {"flag": "🇦🇹", "name": "Avusturya"},
    "BE": {"flag": "🇧🇪", "name": "Belçika"},
    "SE": {"flag": "🇸🇪", "name": "İsveç"},
    "NO": {"flag": "🇳🇴", "name": "Norveç"},
    "IT": {"flag": "🇮🇹", "name": "İtalya"},
    "ES": {"flag": "🇪🇸", "name": "İspanya"},
    "AE": {"flag": "🇦🇪", "name": "BAE"},
    "SA": {"flag": "🇸🇦", "name": "Suudi Arabistan"},
    "KZ": {"flag": "🇰🇿", "name": "Kazakistan"},
    "CY": {"flag": "🇨🇾", "name": "Kıbrıs"},
    "PL": {"flag": "🇵🇱", "name": "Polonya"},
    "RO": {"flag": "🇷🇴", "name": "Romanya"},
    "RU": {"flag": "🇷🇺", "name": "Rusya"},
    "GR": {"flag": "🇬🇷", "name": "Yunanistan"},
    "IE": {"flag": "🇮🇪", "name": "İrlanda"},
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
        "apple_latest_report_date": "",
        "apple_report_lag_days": 1,
        "rc_v2_sync_status": "BEKLİYOR (RevenueCat REST API v2)",
        "rc_v2_pending_crossgrades": [],
        "google_play_downloads_baseline": 0,
        "google_play_subscriptions_catalog": [
            {
                "product_id": "misil",
                "base_plan_id": "misil",
                "title": "Mışıl Baby Yıllık VIP",
                "state": "ACTIVE",
                "billing_period": "Yıllık (P1Y)",
                "grace_period": "14 Gün (P14D)",
                "price_try": DEFAULT_PLAN_PRICING_TRY["misil"][0],
                "net_proceeds_try": DEFAULT_PLAN_PRICING_TRY["misil"][1],
                "free_trial_offer_id": "-",
                "free_trial_label": "Denemesiz • Doğrudan Yıllık VIP",
            },
            {
                "product_id": "misilaylik",
                "base_plan_id": "misilaylik",
                "title": "Mışıl Baby Aylık VIP",
                "state": "ACTIVE",
                "billing_period": "Aylık (P1M)",
                "grace_period": "7 Gün (P7D)",
                "price_try": DEFAULT_PLAN_PRICING_TRY["misilaylik"][0],
                "net_proceeds_try": DEFAULT_PLAN_PRICING_TRY["misilaylik"][1],
                "free_trial_offer_id": "intro-first-month / free-trial-1m",
                "free_trial_label": "A/B: İlk Ay 49.99 ₺ (%67 İndirim) vs İlk Ay Ücretsiz (30G 0 ₺)",
            },
        ],
        "daily_store_series": {},
        "store_reviews": [],
        "apple_overall_rating": 0.0,
        "apple_overall_ratings_count": 0,
        "google_overall_rating": 0.0,
        "google_overall_ratings_count": 0,
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


def _is_request_https(request: Request) -> bool:
    """Railway Envoy / Cloudflare ters vekil arkasında HTTPS şemasını doğru tespit eder."""
    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    return request.url.scheme == "https" or forwarded_proto == "https"


def authorize_admin_request(
    request: Request,
    pin: Optional[str] = None,
    x_admin_pin: Optional[str] = None,
    session_token: Optional[str] = None,
) -> bool:
    """
    IP bazlı brute-force korumalı yönetici yetkilendirmesi.
    Geçerli ve süresi dolmamış bir oturum çerezi varsa PIN'i tekrar sormadan doğrular.
    PIN parametresi hiç gönderilmemişse (örn. giriş ekranının ilk açılışı veya çerezsiz GET /dashboard),
    brute-force hata sayacını artırmadan False döner (5 yenilemede 429 kilidine düşmeyi önler).
    """
    if _admin_session_token_is_valid(session_token):
        return True

    client_key = _extract_client_ip(request)
    if _is_pin_client_blocked(client_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Çok fazla hatalı PIN denemesi. Lütfen 15 dakika sonra tekrar deneyin.",
        )

    raw_candidate = pin if isinstance(pin, str) else (x_admin_pin if isinstance(x_admin_pin, str) else "")
    if not raw_candidate or not raw_candidate.strip():
        return False

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


REVENUECAT_V2_PROJECT_ID = os.environ.get("REVENUECAT_PROJECT_ID", "proja1528882")
_RC_V2_PRODUCT_MAP_LOCK = threading.Lock()
_RC_V2_PRODUCT_MAP_CACHE: Dict[str, Any] = {"ts": 0.0, "map": {}}
_GP_OAUTH_TOKEN_LOCK = threading.Lock()
_GP_OAUTH_TOKEN_CACHE: Dict[str, Any] = {"exp": 0.0, "token": None}
_ITUNES_RATING_LOCK = threading.Lock()
_ITUNES_RATING_CACHE: Dict[str, Any] = {"ts": 0.0, "avg": 0.0, "count": 0}


def _get_live_apple_itunes_rating() -> Tuple[float, int]:
    """
    6 saatlik arka plan döngüsünü beklemeden resmi Apple iTunes Lookup API'den
    (https://itunes.apple.com/lookup?id=6809223195&country=tr) yorumsuz oylar dahil
    genel mağaza puanını (örn. 4.6 ★) ve toplam oy sayısını 30 dk önbellekli çeker.
    """
    if os.environ.get("PYTEST_CURRENT_TEST"):
        with _BASELINE_LOCK:
            return (
                float(OFFICIAL_STORE_BASELINE.get("apple_overall_rating", 0.0) or 0.0),
                int(OFFICIAL_STORE_BASELINE.get("apple_overall_ratings_count", 0) or 0),
            )
    now_ts = time.time()
    with _ITUNES_RATING_LOCK:
        c_avg = float(_ITUNES_RATING_CACHE.get("avg") or 0.0)
        c_cnt = int(_ITUNES_RATING_CACHE.get("count") or 0)
        c_ts = float(_ITUNES_RATING_CACHE.get("ts") or 0.0)
        if c_avg > 0 and c_cnt > 0 and (now_ts - c_ts) < 1800:
            return (c_avg, c_cnt)
        if (now_ts - c_ts) < 120 and c_ts > 0:
            return (c_avg, c_cnt)
        _ITUNES_RATING_CACHE["ts"] = now_ts

    try:
        req = urllib.request.Request(
            "https://itunes.apple.com/lookup?id=6809223195&country=tr",
            headers={"Accept": "application/json", "User-Agent": "MishilCockpit/4.57.8"},
        )
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            if resp.status == 200:
                payload = json.loads(resp.read().decode("utf-8"))
                results = payload.get("results") or []
                if results and isinstance(results[0], dict):
                    app_obj = results[0]
                    avg_v = round(
                        float(
                            app_obj.get("averageUserRating")
                            or app_obj.get("averageUserRatingForCurrentVersion")
                            or 0.0
                        ),
                        1,
                    )
                    cnt_v = int(
                        app_obj.get("userRatingCount")
                        or app_obj.get("userRatingCountForCurrentVersion")
                        or 0
                    )
                    if avg_v > 0 and cnt_v > 0:
                        with _ITUNES_RATING_LOCK:
                            _ITUNES_RATING_CACHE["avg"] = avg_v
                            _ITUNES_RATING_CACHE["count"] = cnt_v
                            _ITUNES_RATING_CACHE["ts"] = now_ts
                        with _BASELINE_LOCK:
                            OFFICIAL_STORE_BASELINE["apple_overall_rating"] = avg_v
                            OFFICIAL_STORE_BASELINE["apple_overall_ratings_count"] = cnt_v
                        return (avg_v, cnt_v)
    except Exception as exc:
        logger.debug("Live iTunes rating lookup info: %s", exc)

    with _BASELINE_LOCK:
        return (
            float(OFFICIAL_STORE_BASELINE.get("apple_overall_rating", 0.0) or 0.0),
            int(OFFICIAL_STORE_BASELINE.get("apple_overall_ratings_count", 0) or 0),
        )

# Kokpit hızlandırma katmanı: hafif projeksiyonlar, anında geçersiz kılınan (instant-invalidated)
# kısa ömürlü özet önbelleği ve tekil uçuş (single-flight) mağaza senkron kilidi
class _ClickSlim(NamedTuple):
    id: int
    created_at: datetime
    route_path: str
    os_family: str
    app_webview: Optional[str]
    is_bot: bool
    is_unique: bool


class _SignalSlim(NamedTuple):
    event_type: str
    os_family: Optional[str]
    device_uid: Optional[str]
    country: Optional[str]
    matched_channel: Optional[str]
    match_confidence: Optional[str]
    created_at: datetime
    app_version: Optional[str] = None


_SUMMARY_CACHE_LOCK = threading.Lock()
_SUMMARY_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_LAST_GOOD_SUMMARY_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
# 15sn canlı polling ile tam uyumlu 25sn önbellek ömrü (her poll'un cache-miss olmasını engeller)
_SUMMARY_CACHE_TTL_SEC: float = float(os.environ.get("MISIL_ANALYTICS_CACHE_TTL_SEC", "25.0"))
_SWR_MAX_STALE_SEC: float = float(os.environ.get("MISIL_ANALYTICS_SWR_MAX_STALE_SEC", "3600.0"))
_BASELINE_LOADED_STAMP: Optional[Tuple[str, str]] = None
_LEDGER_RECONCILE_LOCK = threading.Lock()
_LEDGER_RECONCILE_GEN: int = 1
_LEDGER_RECONCILED_GEN: int = 0
_STORE_SYNC_EXEC_LOCK = threading.Lock()
_STORE_SYNC_LAST_STATUS: Dict[str, Any] = {
    "running": False,
    "started_at": "",
    "last_synced_at": "",
    "last_sources": [],
}


def _clone_summary_for_response(summary_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ağır copy.deepcopy yerine tüm üst düzey dict ve list kapsayıcılarını (<0.1ms) klonlar;
    böylece uç noktalardaki (örn. product_funnel, recent_clicks, cumulative_kpis) hiçbir mutasyon önbelleği kirletmez.
    """
    cloned: Dict[str, Any] = {}
    for k, v in summary_data.items():
        if isinstance(v, dict):
            cloned[k] = dict(v)
        elif isinstance(v, list):
            cloned[k] = list(v)
        else:
            cloned[k] = v
    return cloned


def invalidate_analytics_summary_cache(
    mark_reconcile: bool = False,
    reset_baseline_stamp: bool = False,
) -> None:
    """Yeni tıklama, sinyal, geri bildirim, abonelik veya mağaza senkronu geldiği an aktif önbelleği sıfırlar (_LAST_GOOD_SUMMARY_CACHE SWR yedek olarak korunur)."""
    global _LEDGER_RECONCILE_GEN, _BASELINE_LOADED_STAMP
    with _SUMMARY_CACHE_LOCK:
        _SUMMARY_CACHE.clear()
        if mark_reconcile:
            _LEDGER_RECONCILE_GEN += 1
    if reset_baseline_stamp:
        with _BASELINE_LOCK:
            _BASELINE_LOADED_STAMP = None


def trigger_background_store_sync(days_back: int = 7) -> bool:
    """Mağaza API senkronizasyonunu HTTP yanıtını bekletmeden arka planda tekil olarak başlatır."""
    if _STORE_SYNC_EXEC_LOCK.locked():
        return False

    def _bg_worker() -> None:
        try:
            sync_live_store_apis(days_back=days_back)
        except Exception as bg_exc:
            logger.warning("Background store sync warning: %s", bg_exc)

    t = threading.Thread(target=_bg_worker, name="mishil-bg-store-sync", daemon=True)
    t.start()
    return True


def _get_revenuecat_v2_secret_key() -> Optional[str]:
    """RevenueCat REST API v2 Secret Key (sk_...) anahtarını ortam değişkeninden veya kasadan okur."""
    for env_k in ("REVENUECAT_SECRET_KEY", "REVENUECAT_API_V2_KEY", "RC_SECRET_KEY"):
        val = (os.environ.get(env_k) or "").strip()
        if val.startswith("sk_"):
            return val
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
    sec_candidates = [
        os.path.join(project_root, "..", "..", "storage", "secrets.json"),
        os.path.join(project_root, "storage", "secrets.json"),
    ]
    for sp in sec_candidates:
        if os.path.exists(sp):
            try:
                with open(sp, "r", encoding="utf-8") as sf:
                    sec_data = json.load(sf)
                rc_sk = str(sec_data.get("REVENUECAT_SECRET_KEY") or "").strip()
                if rc_sk.startswith("sk_"):
                    return rc_sk
            except Exception:
                pass
    return None


def _get_rc_v2_product_map(sk: Optional[str] = None) -> Dict[str, str]:
    """
    RevenueCat REST API v2 dahili ürün kimliklerini (örn. prod24815efd12, prodec593d4420)
    gerçek mağaza ürün kimlikleriyle (store_identifier: misilaylik:misilaylik, misil:misil, misil_monthly, misil_annual)
    dinamik olarak eşler (6 saatlik bellek önbelleği).
    """
    now_ts = time.time()
    with _RC_V2_PRODUCT_MAP_LOCK:
        cached_map = _RC_V2_PRODUCT_MAP_CACHE.get("map") or {}
        if cached_map and (now_ts - float(_RC_V2_PRODUCT_MAP_CACHE.get("ts") or 0.0)) < 21600:
            return dict(cached_map)

    secret = sk or _get_revenuecat_v2_secret_key()
    if not secret:
        return {}
    fetched_map: Dict[str, str] = {}
    try:
        next_url: Optional[str] = f"https://api.revenuecat.com/v2/projects/{REVENUECAT_V2_PROJECT_ID}/products?limit=100"
        pages = 0
        while next_url and pages < 5:
            pages += 1
            req = urllib.request.Request(
                next_url,
                headers={"Authorization": f"Bearer {secret}", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status != 200:
                    break
                payload = json.loads(resp.read().decode("utf-8"))
                for p_item in payload.get("items") or []:
                    rc_pid = str(p_item.get("id") or "").strip()
                    store_ident = str(p_item.get("store_identifier") or "").strip()
                    if rc_pid and store_ident:
                        fetched_map[rc_pid] = store_ident
                raw_next = payload.get("next_page")
                if raw_next and isinstance(raw_next, str):
                    next_url = raw_next if raw_next.startswith("http") else f"https://api.revenuecat.com{raw_next}"
                else:
                    next_url = None
    except Exception as exc:
        logger.debug("RevenueCat V2 products catalog sync info: %s", exc)

    if fetched_map:
        with _RC_V2_PRODUCT_MAP_LOCK:
            _RC_V2_PRODUCT_MAP_CACHE["ts"] = now_ts
            _RC_V2_PRODUCT_MAP_CACHE["map"] = dict(fetched_map)
        return fetched_map
    with _RC_V2_PRODUCT_MAP_LOCK:
        return dict(_RC_V2_PRODUCT_MAP_CACHE.get("map") or {})


def _resolve_canonical_product_id(
    raw_product_id: Optional[str],
    platform: str,
    rc_prod_map: Optional[Dict[str, str]] = None,
) -> str:
    """Ham veya RevenueCat opak product_id değerini platformun kanonik ürün kimliğine çevirir."""
    raw_pid = str(raw_product_id or "").strip()
    mapped_pid = (rc_prod_map or {}).get(raw_pid, raw_pid)
    is_ann = _is_annual_product(mapped_pid) or _is_annual_product(raw_pid)
    if platform == "android":
        return "misil" if is_ann else "misilaylik"
    return "misil_annual" if is_ann else "misil_monthly"


def _get_google_play_access_token() -> Optional[str]:
    """Google Play Developer API (androidpublisher) için önbellekli OAuth2 erişim jetonu üretir."""
    if os.environ.get("PYTEST_CURRENT_TEST") and os.environ.get("MISIL_ENABLE_TEST_GP_API") != "1":
        return None
    if not jwt:
        return None
    now_gp = time.time()
    with _GP_OAUTH_TOKEN_LOCK:
        cached_tok = _GP_OAUTH_TOKEN_CACHE.get("token")
        if cached_tok and float(_GP_OAUTH_TOKEN_CACHE.get("exp") or 0.0) > (now_gp + 60):
            return str(cached_tok)

    sa_raw = os.environ.get("GOOGLE_PLAY_SERVICE_ACCOUNT_JSON")
    if not sa_raw:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
        sa_candidates = [
            os.path.join(project_root, "mobile", "google-play-service-account.json"),
            os.path.join(project_root, "..", "..", "projects", "mishil", "mobile", "google-play-service-account.json"),
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
        iat_int = int(now_gp)
        assertion = jwt.encode(
            {
                "iss": sa["client_email"],
                "scope": "https://www.googleapis.com/auth/androidpublisher",
                "aud": "https://oauth2.googleapis.com/token",
                "iat": iat_int - 30,
                "exp": iat_int + 3500,
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
            if tok_resp.status == 200:
                access_token = json.loads(tok_resp.read().decode("utf-8")).get("access_token")
                if access_token:
                    with _GP_OAUTH_TOKEN_LOCK:
                        _GP_OAUTH_TOKEN_CACHE["token"] = access_token
                        _GP_OAUTH_TOKEN_CACHE["exp"] = now_gp + 3000
                    return str(access_token)
    except Exception as exc:
        logger.debug("Google Play OAuth token info: %s", exc)
    return None


def _parse_money_obj_try(money_obj: Any, default_ccy: str = "TRY") -> float:
    """Google Play orders API Money nesnesini ({currencyCode, units, nanos}) TRY tutarına çevirir."""
    if not isinstance(money_obj, dict):
        return 0.0
    try:
        units_v = float(money_obj.get("units") or 0.0)
        nanos_v = float(money_obj.get("nanos") or 0.0) / 1e9
        raw_amt = units_v + nanos_v
        if raw_amt <= 0:
            return 0.0
        ccy = str(money_obj.get("currencyCode") or default_ccy).strip().upper()
        return _convert_to_try(raw_amt, ccy)
    except Exception:
        return 0.0


def _fetch_google_play_order(
    order_id: str,
    access_token: Optional[str] = None,
    keep_renewal_suffix: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Google Play Developer API orders.get uç noktasından tekil GPA.* (veya yenileme GPA.xxxx..0, ..1) sipariş detayını çeker.
    testPurchase alanı olan test siparişlerini, iadeleri (REFUNDED) ve gerçek dönem tutarlarını doğrular.
    """
    raw_oid = str(order_id or "").strip()
    clean_oid = raw_oid if keep_renewal_suffix else raw_oid.split("..")[0]
    if not clean_oid.startswith("GPA."):
        return None
    tok = access_token or _get_google_play_access_token()
    if not tok:
        return None
    try:
        ord_url = (
            "https://androidpublisher.googleapis.com/androidpublisher/v3/applications/"
            f"com.levitas.misilbaby/orders/{urllib.parse.quote(clean_oid, safe='')}"
        )
        ord_req = urllib.request.Request(ord_url, headers={"Authorization": f"Bearer {tok}"})
        with urllib.request.urlopen(ord_req, timeout=4) as ord_resp:
            if ord_resp.status == 200:
                return json.loads(ord_resp.read().decode("utf-8"))
    except Exception as exc:
        logger.debug("Google Play orders.get info (%s): %s", clean_oid, exc)
    if keep_renewal_suffix and ".." in clean_oid:
        return _fetch_google_play_order(clean_oid.split("..")[0], tok, keep_renewal_suffix=False)
    return None


def _parse_rc_v2_ms(raw_val: Any) -> int:
    """RevenueCat V2 zaman damgalarını (epoch ms integer veya ISO-8601 string) güvenli şekilde epoch ms'e çevirir."""
    if raw_val is None or raw_val == "":
        return 0
    if isinstance(raw_val, (int, float)):
        return int(raw_val)
    s_val = str(raw_val).strip()
    if s_val.isdigit():
        return int(s_val)
    try:
        dt_obj = datetime.fromisoformat(s_val.replace("Z", "+00:00"))
        return int(dt_obj.timestamp() * 1000)
    except Exception:
        return 0


def _parse_rc_v2_date(raw_val: Any) -> str:
    """RevenueCat V2 zaman damgasını Türkiye saat diliminde (UTC+3) YYYY-MM-DD tarihine dönüştürür."""
    ms = _parse_rc_v2_ms(raw_val)
    if ms <= 0:
        s_val = str(raw_val or "").strip()
        if len(s_val) >= 10 and s_val[4:5] == "-" and s_val[7:8] == "-":
            return s_val[:10]
        return ""
    tz_tr = timezone(timedelta(hours=3))
    return datetime.fromtimestamp(ms / 1000.0, tz=tz_tr).strftime("%Y-%m-%d")


def _fetch_rc_v2_customer_production_subs(
    customer_id: str,
    sk: Optional[str] = None,
    rc_prod_map: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """
    RevenueCat REST API v2 üzerinden tekil müşterinin TÜM production aboneliklerini döndürür.
    Sandbox / test satın almalarını kesin olarak filtreler; opak RC product_id kimliklerini
    dinamik ürün kataloğu üzerinden gerçek mağaza paketlerine (misil / misilaylik / misil_annual / misil_monthly) çevirir.
    """
    clean_cid = (customer_id or "").strip()
    secret = sk or _get_revenuecat_v2_secret_key()
    if not clean_cid or not secret:
        return []
    prod_map = rc_prod_map if rc_prod_map is not None else _get_rc_v2_product_map(secret)
    url = (
        f"https://api.revenuecat.com/v2/projects/{REVENUECAT_V2_PROJECT_ID}"
        f"/customers/{urllib.parse.quote(clean_cid, safe='')}/subscriptions"
    )
    payload: Optional[Dict[str, Any]] = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(
                url,
                headers={"Authorization": f"Bearer {secret}", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    payload = json.loads(resp.read().decode("utf-8"))
                break
        except urllib.error.HTTPError as http_err:
            if http_err.code == 429 and attempt == 0:
                time.sleep(0.6)
                continue
            return []
        except Exception as exc:
            logger.debug("RevenueCat V2 customer subscriptions info (%s): %s", clean_cid, exc)
            return []

    if not isinstance(payload, dict):
        return []
    items = payload.get("items") or []
    prod_subs = [it for it in items if str(it.get("environment") or "").lower() == "production"]
    if not prod_subs:
        return []

    prod_subs.sort(
        key=lambda x: (
            1 if str(x.get("status") or "").lower() in ("active", "trialing", "in_grace_period", "in_billing_retry") else 0,
            _parse_rc_v2_ms(x.get("current_period_starts_at") or x.get("starts_at")),
        ),
        reverse=True,
    )

    normalized_list: List[Dict[str, Any]] = []
    for sub in prod_subs:
        store_raw = str(sub.get("store") or "").lower()
        plat = "android" if "play" in store_raw else "ios"
        rc_prod_id = str(sub.get("product_id") or "")
        store_ident = prod_map.get(rc_prod_id, rc_prod_id)
        norm_prod_id = _resolve_canonical_product_id(rc_prod_id, plat, prod_map)
        start_dt = _parse_rc_v2_date(sub.get("starts_at"))
        period_start_dt = _parse_rc_v2_date(sub.get("current_period_starts_at")) or start_dt
        exp_dt = _parse_rc_v2_date(sub.get("current_period_ends_at"))
        rc_status = str(sub.get("status") or "").lower()
        ar_status = str(sub.get("auto_renewal_status") or "").lower()
        rev_usd = sub.get("total_revenue_in_usd") or {}
        gross_usd = float(rev_usd.get("gross") or 0.0)
        proc_usd = float(rev_usd.get("proceeds") or 0.0)
        pending_chg = sub.get("pending_changes") or {}
        pending_prod_obj = (pending_chg.get("product") or {}) if isinstance(pending_chg, dict) else {}
        pending_rc_pid = str(pending_prod_obj.get("id") or "") if isinstance(pending_prod_obj, dict) else ""
        pending_store_ident = (
            str(pending_prod_obj.get("store_identifier") or "")
            if isinstance(pending_prod_obj, dict)
            else ""
        ) or prod_map.get(pending_rc_pid, pending_rc_pid)
        pending_norm_pid = (
            _resolve_canonical_product_id(pending_store_ident or pending_rc_pid, plat, prod_map)
            if (pending_store_ident or pending_rc_pid)
            else None
        )
        normalized_list.append({
            "customer_id": clean_cid,
            "platform": plat,
            "store": store_raw,
            "rc_product_id": rc_prod_id,
            "store_product_identifier": store_ident,
            "product_id": norm_prod_id,
            "rc_status": rc_status,
            "auto_renewal_status": ar_status,
            "auto_renew_enabled": ar_status in ("will_renew", "will_change_product", "has_already_renewed"),
            "starts_at_date": start_dt,
            "current_period_starts_at_date": period_start_dt,
            "ends_at_date": exp_dt,
            "store_subscription_identifier": str(sub.get("store_subscription_identifier") or ""),
            "country": str(sub.get("country") or "TR").upper(),
            "gross_usd": gross_usd,
            "proceeds_usd": proc_usd,
            "pending_product_id": pending_norm_pid or (pending_rc_pid or None),
        })
    return normalized_list


def verify_revenuecat_v2_customer(customer_id: str) -> Optional[Dict[str, Any]]:
    """
    RevenueCat REST API v2 üzerinden tekil müşterinin en güncel/aktif production aboneliğini sorgular.
    Yalnızca environment == 'production' olan gerçek mağaza işlemlerini döndürür.
    """
    subs = _fetch_rc_v2_customer_production_subs(customer_id)
    if not subs:
        return None
    primary = dict(subs[0])
    primary["all_subscriptions"] = subs
    return primary


def _is_30d_free_trial_window(
    st_d_str: Optional[str],
    exp_d_str: Optional[str],
    raw_ident: str = "",
) -> bool:
    """
    RevenueCat T-0 veya Google Play köprüsünde ücretli olmayan (gross == 0) bir aylık aboneliğin
    30 günlük ücretsiz deneme (Grup B: free_trial_1m) mi yoksa eski 7 günlük deneme (intro_7d_trial) mi
    olduğunu başlangıç-bitiş gün farkı (>= 20 gün) veya ürün/teklif tanımlayıcısından tespit eder.
    """
    ident_low = (raw_ident or "").lower()
    if any(tok in ident_low for tok in ("free_trial", "free-trial", "trial_1m", "trial-1m", "30d", "first_month_free")):
        return True
    try:
        if st_d_str and exp_d_str and len(st_d_str) >= 10 and len(exp_d_str) >= 10:
            st_dt = datetime.strptime(st_d_str[:10], "%Y-%m-%d").date()
            exp_dt = datetime.strptime(exp_d_str[:10], "%Y-%m-%d").date()
            if (exp_dt - st_dt).days >= 20:
                return True
    except Exception:
        pass
    return False


def sync_revenuecat_v2_production_bridge(
    db: Session,
    latest_apple_report_date: str = "",
) -> Dict[str, Any]:
    """
    %100 Dinamik (Sıfır Statik Müşteri Listesi) RevenueCat REST API v2 & Google Play Orders Mutabakat Motoru:
    1) Tüm RevenueCat müşteri sayfalarını (limit=100, tam sayfalama) tarar; kalıcı StoreSyncState önbelleği
       sayesinde abonesi olmayan ve last_seen_at değişmeyen eski anonim cihazları tekrar sorgulamazken,
       bilinen tüm aboneleri ve yeni/güncellenen müşterileri eksiksiz denetler.
    2) Müşteri başına yalnızca ilk aboneliği değil, TÜM production aboneliklerini işler.
    3) Android (GPA.*) siparişlerini Google Play Developer API orders/{orderId} ile çapraz doğrulayarak
       test satın almalarını (testPurchase) eler, 72 saat onaysız iadeleri (REFUNDED) iptal olarak işler
       ve gerçek TL/döviz tahsilatını yazar.
    4) iOS tarafında T-0 canlı köprüyü, DamlaEge2026 -> Aylık VIP (will_change_product) geçişlerini ve
       ücretli abonelerdeki yenileme kapatma (will_not_renew) durumunu günceller.
    """
    sk = _get_revenuecat_v2_secret_key()
    if not sk:
        return {"connected": False, "reason": "No RevenueCat V2 secret key"}

    rc_prod_map = _get_rc_v2_product_map(sk)
    cache_row = (
        db.query(StoreSyncState)
        .filter(StoreSyncState.state_key == "rc_v2_customer_scan_cache")
        .first()
    )
    cache_data = dict(cache_row.snapshot_json or {}) if (cache_row and isinstance(cache_row.snapshot_json, dict)) else {}
    non_sub_seen: Dict[str, int] = {
        str(k): int(v or 0)
        for k, v in (cache_data.get("non_sub_seen") or {}).items()
        if k
    }
    known_prod_cids = {
        str(c).strip()
        for c in (cache_data.get("known_prod_cids") or [])
        if str(c).strip()
    }
    for (rc_uid_db,) in db.query(SubscriberLedger.rc_app_user_id).filter(SubscriberLedger.rc_app_user_id.isnot(None)).all():
        if rc_uid_db and str(rc_uid_db).strip():
            known_prod_cids.add(str(rc_uid_db).strip())

    discovered_seen_ms: Dict[str, int] = {}
    candidate_cids: List[str] = []
    candidate_set = set()

    for k_cid in sorted(known_prod_cids):
        candidate_cids.append(k_cid)
        candidate_set.add(k_cid)

    list_complete = False
    resume_cursor_url: Optional[str] = str(cache_data.get("resume_next_url") or "").strip() or None
    seen_page_urls = set()
    try:
        next_url: Optional[str] = (
            resume_cursor_url
            or f"https://api.revenuecat.com/v2/projects/{REVENUECAT_V2_PROJECT_ID}/customers?limit=100"
        )
        pages_fetched = 0
        while next_url and next_url not in seen_page_urls and pages_fetched < 500:
            seen_page_urls.add(next_url)
            pages_fetched += 1
            req = urllib.request.Request(
                next_url,
                headers={"Authorization": f"Bearer {sk}", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                if resp.status != 200:
                    break
                data = json.loads(resp.read().decode("utf-8"))
                for c_item in data.get("items") or []:
                    cid = str(c_item.get("id") or "").strip()
                    if not cid:
                        continue
                    last_seen = _parse_rc_v2_ms(c_item.get("last_seen_at") or c_item.get("first_seen_at"))
                    discovered_seen_ms[cid] = last_seen
                    prev_non_sub_ts = non_sub_seen.get(cid)
                    if cid in known_prod_cids or prev_non_sub_ts is None or last_seen > prev_non_sub_ts:
                        if cid not in candidate_set:
                            candidate_cids.append(cid)
                            candidate_set.add(cid)
                raw_next = data.get("next_page")
                if raw_next and isinstance(raw_next, str):
                    next_url = raw_next if raw_next.startswith("http") else f"https://api.revenuecat.com{raw_next}"
                    resume_cursor_url = next_url
                else:
                    next_url = None
                    resume_cursor_url = None
                    list_complete = True
    except Exception as exc:
        logger.debug("RevenueCat V2 customer list pagination info: %s", exc)

    subs_by_cid: Dict[str, List[Dict[str, Any]]] = {}
    if candidate_cids:
        max_workers = min(5, max(1, len(candidate_cids)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            fut_map = {
                pool.submit(_fetch_rc_v2_customer_production_subs, cid, sk, rc_prod_map): cid
                for cid in candidate_cids
            }
            for fut in concurrent.futures.as_completed(fut_map):
                cid = fut_map[fut]
                try:
                    c_subs = fut.result()
                except Exception:
                    c_subs = []
                if c_subs:
                    subs_by_cid[cid] = c_subs
                    known_prod_cids.add(cid)
                    non_sub_seen.pop(cid, None)
                elif cid in discovered_seen_ms and cid not in known_prod_cids:
                    non_sub_seen[cid] = discovered_seen_ms[cid]

    gp_access_token = _get_google_play_access_token()
    prod_ios_count = 0
    prod_android_count = 0
    android_test_filtered = 0
    t0_bridge_upserts = 0
    pending_crossgrades: List[Dict[str, Any]] = []
    ios_paid_will_not_renew: List[Dict[str, Any]] = []
    ios_trial_will_not_renew: List[Dict[str, Any]] = []

    for cid in candidate_cids:
        c_subs = subs_by_cid.get(cid) or []
        for v_sub in c_subs:
            plat = v_sub["platform"]
            st_date = v_sub["starts_at_date"]
            conv_date = v_sub.get("current_period_starts_at_date") or st_date
            exp_date = v_sub["ends_at_date"]
            store_sub_id = str(v_sub.get("store_subscription_identifier") or "").strip()
            ar_status = v_sub["auto_renewal_status"]
            rc_status = v_sub["rc_status"]
            prod_id = v_sub["product_id"]

            if plat == "ios":
                prod_ios_count += 1
                if ar_status == "will_change_product":
                    to_pid = v_sub.get("pending_product_id") or "misil_monthly"
                    if to_pid not in ("misil_monthly", "misil_annual"):
                        to_pid = _resolve_canonical_product_id(to_pid, "ios", rc_prod_map)
                    cg_g, cg_n = _resolve_expected_trial_pricing(to_pid, 0.0, 0.0, "ios")
                    pending_crossgrades.append({
                        "customer_id": cid,
                        "store_subscription_identifier": store_sub_id,
                        "started_date": st_date,
                        "renewal_date": exp_date,
                        "from_product_id": prod_id,
                        "to_product_id": to_pid,
                        "expected_next_price_try": cg_g,
                        "expected_next_proceeds_try": cg_n,
                    })
                if rc_status == "active" and ar_status in ("will_not_renew", "unsubscribe_detected") and float(v_sub.get("gross_usd") or 0.0) > 0:
                    ios_paid_will_not_renew.append({
                        "customer_id": cid,
                        "store_subscription_identifier": store_sub_id,
                        "started_date": st_date,
                        "converted_date": conv_date,
                        "ends_at_date": exp_date,
                        "product_id": prod_id,
                        "country": v_sub["country"],
                    })
                elif rc_status in ("trialing", "active") and ar_status in ("will_not_renew", "unsubscribe_detected") and float(v_sub.get("gross_usd") or 0.0) <= 0:
                    ios_trial_will_not_renew.append({
                        "customer_id": cid,
                        "store_subscription_identifier": store_sub_id,
                        "started_date": st_date,
                        "ends_at_date": exp_date,
                        "product_id": prod_id,
                        "country": v_sub["country"],
                    })
                # Apple 1 günlük gecikme (T-0) köprüsü: Sadece latest_apple_report_date'den yeni olanları köprüle
                if latest_apple_report_date and st_date > latest_apple_report_date and store_sub_id:
                    bridge_sid = f"RC_T0_{store_sub_id}"[:128]
                    official_match_clauses = [
                        SubscriberLedger.started_date == st_date,
                        SubscriberLedger.converted_or_renewed_date == st_date,
                    ]
                    if exp_date:
                        official_match_clauses.append(SubscriberLedger.maturity_or_renewal_date == exp_date)
                    from sqlalchemy import or_ as sa_or
                    official_cnt = (
                        db.query(SubscriberLedger)
                        .filter(
                            SubscriberLedger.platform == "ios",
                            SubscriberLedger.product_id == prod_id,
                            sa_or(*official_match_clauses),
                            ~SubscriberLedger.subscriber_id.like("RC_T0_%"),
                        )
                        .count()
                    )
                    bridge_cnt = (
                        db.query(SubscriberLedger)
                        .filter(
                            SubscriberLedger.platform == "ios",
                            SubscriberLedger.product_id == prod_id,
                            SubscriberLedger.started_date == st_date,
                            SubscriberLedger.subscriber_id.like("RC_T0_%"),
                            SubscriberLedger.subscriber_id != bridge_sid,
                        )
                        .count()
                    )
                    existing_b = db.query(SubscriberLedger).filter(SubscriberLedger.subscriber_id == bridge_sid).first()
                    if existing_b is not None or official_cnt <= bridge_cnt:
                        raw_gross_usd = float(v_sub.get("gross_usd") or 0.0)
                        raw_proc_usd = float(v_sub.get("proceeds_usd") or 0.0)
                        is_paid = raw_gross_usd > 0
                        std_g, std_n = _resolve_expected_trial_pricing(prod_id, 0.0, 0.0, "ios")
                        ios_ratio = get_dynamic_proceeds_ratio("ios")
                        is_intro_t0 = False
                        if is_paid:
                            est_try_from_usd = round(raw_gross_usd * APPLE_TRENDS_USD_TRY_RATE, 2)
                            is_ann_ios = _is_annual_product(prod_id)
                            if (
                                not is_ann_ios
                                and str(v_sub.get("country") or "TR").upper() == "TR"
                                and 20.0 <= est_try_from_usd <= 95.0
                            ):
                                # 49.99 TL İlk Ay İndirimli Paket (Introductory Pay-As-You-Go)
                                is_intro_t0 = True
                                c_gross = INTRO_1M_DISCOUNTED_GROSS_TRY
                                c_net = round(INTRO_1M_DISCOUNTED_GROSS_TRY * ios_ratio, 2)
                            elif str(v_sub.get("country") or "TR").upper() != "TR" and est_try_from_usd > 0:
                                c_gross = est_try_from_usd
                                c_net = (
                                    round(raw_proc_usd * APPLE_TRENDS_USD_TRY_RATE, 2)
                                    if raw_proc_usd > 0
                                    else round(c_gross * ios_ratio, 2)
                                )
                            else:
                                c_gross = std_g
                                c_net = std_n
                        else:
                            c_gross = 0.0
                            c_net = 0.0
                        is_1m_trial_t0 = (
                            not is_paid
                            and not _is_annual_product(prod_id)
                            and _is_30d_free_trial_window(
                                st_date,
                                exp_date,
                                f"{v_sub.get('rc_product_id', '')} {v_sub.get('store_product_identifier', '')} {prod_id}",
                            )
                        )
                        t0_offer_type = (
                            ("intro_1m_discounted" if is_intro_t0 else "standard_paid")
                            if is_paid
                            else ("free_trial_1m" if is_1m_trial_t0 else "intro_7d_trial")
                        )
                        t0_offer_lbl = (
                            "İlk Ay İndirimli Başlangıç (T-0 Canlı Köprü)"
                            if is_intro_t0
                            else (
                                "İlk Ay Ücretsiz Deneme (T-0 Canlı Köprü)"
                                if is_1m_trial_t0
                                else "RevenueCat T-0 Canlı Köprü"
                            )
                        )
                        st_val = (
                            "cancelled"
                            if rc_status in ("expired", "unsubscribed") or (not is_paid and not v_sub["auto_renew_enabled"])
                            else ("paid_active" if is_paid else "intro_free_trial")
                        )
                        if existing_b:
                            existing_b.rc_app_user_id = cid[:128]
                            existing_b.product_id = prod_id
                            existing_b.plan_label = "Yıllık VIP" if _is_annual_product(prod_id) else "Aylık Esnek VIP"
                            existing_b.status = st_val
                            existing_b.offer_type = t0_offer_type
                            existing_b.offer_code_name = t0_offer_lbl
                            existing_b.auto_renew_enabled = v_sub["auto_renew_enabled"]
                            existing_b.maturity_or_renewal_date = exp_date or st_date
                            if is_paid:
                                existing_b.customer_price_try = c_gross
                                existing_b.developer_proceeds_try = c_net
                                existing_b.converted_or_renewed_date = conv_date or existing_b.converted_or_renewed_date or st_date
                            existing_b.expected_next_price_try = std_g if v_sub["auto_renew_enabled"] else 0.0
                            existing_b.expected_next_proceeds_try = std_n if v_sub["auto_renew_enabled"] else 0.0
                            existing_b.country = v_sub["country"]
                            t0_bridge_upserts += 1
                        else:
                            db.add(
                                SubscriberLedger(
                                    subscriber_id=bridge_sid,
                                    rc_app_user_id=cid[:128],
                                    platform="ios",
                                    product_id=prod_id,
                                    plan_label="Yıllık VIP" if _is_annual_product(prod_id) else "Aylık Esnek VIP",
                                    status=st_val,
                                    offer_type=t0_offer_type,
                                    offer_code_name=t0_offer_lbl,
                                    started_date=st_date,
                                    converted_or_renewed_date=conv_date if is_paid else None,
                                    maturity_or_renewal_date=exp_date or st_date,
                                    auto_renew_enabled=v_sub["auto_renew_enabled"],
                                    customer_price_try=c_gross,
                                    developer_proceeds_try=c_net,
                                    expected_next_price_try=std_g if v_sub["auto_renew_enabled"] else 0.0,
                                    expected_next_proceeds_try=std_n if v_sub["auto_renew_enabled"] else 0.0,
                                    country=v_sub["country"],
                                    device_type="iPhone",
                                )
                            )
                            t0_bridge_upserts += 1
            elif plat == "android":
                base_order_id = store_sub_id.split("..")[0] if store_sub_id.startswith("GPA.") else (store_sub_id or cid)[:128]
                latest_gp_order_id = store_sub_id if store_sub_id.startswith("GPA.") else base_order_id
                gp_order = _fetch_google_play_order(latest_gp_order_id, gp_access_token) if base_order_id.startswith("GPA.") else None
                if isinstance(gp_order, dict) and "testPurchase" in gp_order:
                    android_test_filtered += 1
                    continue

                prod_android_count += 1
                gp_state = str((gp_order or {}).get("state") or "").upper()
                gp_gross_try = 0.0
                gp_net_try = 0.0
                gp_offer_phase = ""
                gp_country = v_sub["country"]

                if isinstance(gp_order, dict):
                    b_region = str(((gp_order.get("buyerAddress") or {}).get("regionCode")) or "").strip().upper()
                    if b_region:
                        gp_country = b_region
                    gp_gross_try = _parse_money_obj_try(gp_order.get("total"), "TRY")
                    gp_net_try = _parse_money_obj_try(gp_order.get("developerRevenueInBuyerCurrency"), "TRY")
                    if gp_gross_try > 0 and gp_net_try > 0:
                        observe_proceeds_ratio("android", gp_gross_try, gp_net_try)
                    gp_items = gp_order.get("lineItems") or []
                    if gp_items and isinstance(gp_items[0], dict):
                        li0 = gp_items[0]
                        if li0.get("productId"):
                            prod_id = _resolve_canonical_product_id(str(li0.get("productId")), "android", rc_prod_map)
                        sub_det = li0.get("subscriptionDetails") or {}
                        if isinstance(sub_det, dict):
                            gp_offer_phase = str(sub_det.get("offerPhase") or "").upper()
                            sp_start = _parse_rc_v2_date(sub_det.get("servicePeriodStartTime"))
                            sp_end = _parse_rc_v2_date(sub_det.get("servicePeriodEndTime"))
                            if sp_start and not st_date:
                                st_date = sp_start
                            if sp_end:
                                exp_date = sp_end

                is_refunded_or_canceled_gp = gp_state in ("REFUNDED", "CANCELED")
                is_paid = (gp_gross_try > 0 or float(v_sub.get("gross_usd") or 0.0) > 0) and gp_state != "REFUNDED"
                std_g, std_n = _resolve_expected_trial_pricing(prod_id, 0.0, 0.0, "android")
                and_ratio = get_dynamic_proceeds_ratio("android")
                c_gross = gp_gross_try if gp_gross_try > 0 and not is_refunded_or_canceled_gp else (std_g if is_paid else 0.0)
                c_net = (
                    gp_net_try
                    if gp_net_try > 0 and not is_refunded_or_canceled_gp
                    else (round(c_gross * and_ratio, 2) if c_gross > 0 else (std_n if is_paid else 0.0))
                )
                auto_renew_and = bool(v_sub["auto_renew_enabled"]) and not is_refunded_or_canceled_gp and rc_status not in ("expired", "unsubscribed")
                if rc_status in ("expired", "unsubscribed") or is_refunded_or_canceled_gp or (not is_paid and not auto_renew_and):
                    st_val = "cancelled"
                    auto_renew_and = False
                elif is_paid:
                    st_val = "paid_active"
                elif gp_offer_phase == "PROMOTIONAL":
                    st_val = "offer_code_trial"
                else:
                    st_val = "intro_free_trial"

                is_intro_gp = bool(
                    not _is_annual_product(prod_id)
                    and is_paid
                    and (gp_offer_phase in ("INTRODUCTORY", "SINGLE_PAYMENT") or (0.0 < c_gross < 100.0 and gp_country == "TR"))
                )
                is_1m_trial_gp = bool(
                    st_val == "intro_free_trial"
                    and not _is_annual_product(prod_id)
                    and _is_30d_free_trial_window(
                        st_date,
                        exp_date,
                        f"{v_sub.get('rc_product_id', '')} {v_sub.get('store_product_identifier', '')} {prod_id} {gp_offer_phase}",
                    )
                )
                if gp_state == "REFUNDED" and not is_paid:
                    and_offer_lbl = "İptal / 72s Onaysız (Google Play)"
                elif st_val == "paid_active" and is_intro_gp:
                    and_offer_lbl = "İlk Ay İndirimli Başlangıç (Google Play)"
                elif st_val == "paid_active":
                    and_offer_lbl = "Standart Ücretli (Google Play)"
                elif is_1m_trial_gp:
                    and_offer_lbl = "İlk Ay Ücretsiz Deneme (Google Play)"
                else:
                    and_offer_lbl = "Deneme / Promosyon (Google Play)"

                and_plan_lbl = "Mışıl Baby Yıllık VIP" if _is_annual_product(prod_id) else "Mışıl Baby Aylık VIP"
                and_of_type = (
                    ("intro_1m_discounted" if is_intro_gp else "standard_paid")
                    if st_val == "paid_active"
                    else (
                        "offer_code"
                        if st_val == "offer_code_trial"
                        else ("free_trial_1m" if is_1m_trial_gp else "intro_7d_trial")
                    )
                )
                existing_and = db.query(SubscriberLedger).filter(SubscriberLedger.subscriber_id == base_order_id).first()
                if existing_and:
                    prev_and_conv = (existing_and.converted_or_renewed_date or "").strip()
                    new_and_conv = (conv_date or existing_and.converted_or_renewed_date or st_date or "").strip()
                    existing_and.rc_app_user_id = cid[:128]
                    existing_and.platform = "android"
                    existing_and.product_id = prod_id
                    existing_and.plan_label = and_plan_lbl
                    existing_and.status = st_val
                    existing_and.offer_type = and_of_type
                    existing_and.offer_code_name = and_offer_lbl[:95]
                    existing_and.auto_renew_enabled = auto_renew_and
                    if st_date and not existing_and.started_date:
                        existing_and.started_date = st_date
                    existing_and.maturity_or_renewal_date = exp_date or existing_and.maturity_or_renewal_date or st_date
                    if is_paid:
                        is_renewal_order = (".." in store_sub_id and not store_sub_id.endswith("..0")) or (
                            bool(prev_and_conv and new_and_conv and new_and_conv > prev_and_conv and (existing_and.customer_price_try or 0.0) > 0)
                        )
                        order_ev_key = f"{base_order_id[:52]}:gp_paid:{latest_gp_order_id[-44:]}:{new_and_conv[:10]}"[:128]
                        already_logged_order = (
                            db.query(SubscriptionLifecycleEvent.id)
                            .filter(
                                SubscriptionLifecycleEvent.platform == "android",
                                SubscriptionLifecycleEvent.event_type == order_ev_key,
                            )
                            .first()
                            is not None
                        )
                        if is_renewal_order and prev_and_conv and new_and_conv > prev_and_conv and not already_logged_order:
                            existing_and.customer_price_try = round(float(existing_and.customer_price_try or 0.0) + c_gross, 2)
                            existing_and.developer_proceeds_try = round(float(existing_and.developer_proceeds_try or 0.0) + c_net, 2)
                            db.add(
                                SubscriptionLifecycleEvent(
                                    event_date=new_and_conv[:10],
                                    platform="android",
                                    event_type=order_ev_key,
                                    product_id=prod_id,
                                    plan_label=and_plan_lbl,
                                    offer_code_name=f"{c_gross:.2f}:{c_net:.2f}",
                                    country=gp_country,
                                    device_type="Android",
                                    quantity=1,
                                )
                            )
                        else:
                            # Tek dönem veya aynı dönem tekrar taraması: mevcut kümülatif LTV'yi asla daha düşük tek-ay tutarına ezme
                            existing_and.customer_price_try = max(float(existing_and.customer_price_try or 0.0), c_gross)
                            existing_and.developer_proceeds_try = max(float(existing_and.developer_proceeds_try or 0.0), c_net)
                        existing_and.converted_or_renewed_date = new_and_conv or st_date
                    elif gp_state == "REFUNDED":
                        existing_and.customer_price_try = 0.0
                        existing_and.developer_proceeds_try = 0.0
                    existing_and.expected_next_price_try = std_g if auto_renew_and and st_val != "offer_code_trial" else 0.0
                    existing_and.expected_next_proceeds_try = std_n if auto_renew_and and st_val != "offer_code_trial" else 0.0
                    existing_and.country = gp_country
                    t0_bridge_upserts += 1
                else:
                    db.add(
                        SubscriberLedger(
                            subscriber_id=base_order_id,
                            rc_app_user_id=cid[:128],
                            platform="android",
                            product_id=prod_id,
                            plan_label=and_plan_lbl,
                            status=st_val,
                            offer_type=and_of_type,
                            offer_code_name=and_offer_lbl[:95],
                            started_date=st_date,
                            converted_or_renewed_date=conv_date if is_paid else None,
                            maturity_or_renewal_date=exp_date or st_date,
                            auto_renew_enabled=auto_renew_and,
                            customer_price_try=c_gross,
                            developer_proceeds_try=c_net,
                            expected_next_price_try=std_g if auto_renew_and and st_val != "offer_code_trial" else 0.0,
                            expected_next_proceeds_try=std_n if auto_renew_and and st_val != "offer_code_trial" else 0.0,
                            country=gp_country,
                            device_type="Android",
                        )
                    )
                    t0_bridge_upserts += 1

    # iOS ücretli aktif olup RevenueCat V2'de oto-yenilemesini kapatmış (will_not_renew) aboneleri işaretle
    if ios_paid_will_not_renew:
        paid_ios_rows: List[SubscriberLedger] = (
            db.query(SubscriberLedger)
            .filter(SubscriberLedger.platform == "ios", SubscriberLedger.status == "paid_active")
            .order_by(SubscriberLedger.started_date.asc(), SubscriberLedger.subscriber_id.asc())
            .all()
        )
        # Resmi Apple satırlarını (~RC_T0_%) geçici köprü satırlarından önce eşleştir
        paid_ios_rows.sort(
            key=lambda r: (
                1 if str(r.subscriber_id or "").startswith("RC_T0_") else 0,
                r.started_date or "",
                r.subscriber_id or "",
            )
        )
        matched_wnr_ids = set()
        for wnr in ios_paid_will_not_renew:
            wnr_cid = str(wnr.get("customer_id") or "")[:128]
            wnr_st = wnr.get("started_date") or ""
            wnr_conv = wnr.get("converted_date") or wnr_st
            wnr_end = wnr.get("ends_at_date") or ""
            wnr_pid = wnr.get("product_id") or ""
            wnr_cc = wnr.get("country") or "TR"
            target_paid = next(
                (
                    r for r in paid_ios_rows
                    if r.subscriber_id not in matched_wnr_ids
                    and (
                        (wnr_cid and r.rc_app_user_id == wnr_cid)
                        or (
                            (
                                r.started_date == wnr_st
                                or r.converted_or_renewed_date == wnr_st
                                or r.converted_or_renewed_date == wnr_conv
                                or (wnr_end and r.maturity_or_renewal_date == wnr_end)
                                or not wnr_st
                            )
                            and ((r.country or "TR").upper() == wnr_cc)
                        )
                    )
                ),
                None,
            )
            if target_paid:
                matched_wnr_ids.add(target_paid.subscriber_id)
                target_paid.rc_app_user_id = wnr_cid or target_paid.rc_app_user_id
                if wnr_pid in ("misil_monthly", "misil_annual") and target_paid.product_id != wnr_pid:
                    target_paid.product_id = wnr_pid
                    target_paid.plan_label = "Yıllık VIP" if _is_annual_product(wnr_pid) else "Aylık Esnek VIP"
                if wnr_end:
                    target_paid.maturity_or_renewal_date = wnr_end
                target_paid.auto_renew_enabled = False
                target_paid.expected_next_price_try = 0.0
                target_paid.expected_next_proceeds_try = 0.0
                wnr_ev_key = f"{target_paid.subscriber_id}:will_not_renew"[:128]
                dup_wnr = (
                    db.query(SubscriptionLifecycleEvent.id)
                    .filter(
                        SubscriptionLifecycleEvent.platform == "ios",
                        SubscriptionLifecycleEvent.event_type == wnr_ev_key,
                    )
                    .first()
                )
                if dup_wnr is None:
                    db.add(
                        SubscriptionLifecycleEvent(
                            event_date=wnr_conv or wnr_st or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                            platform="ios",
                            event_type=wnr_ev_key,
                            product_id=target_paid.product_id,
                            plan_label=target_paid.plan_label,
                            country=target_paid.country or "TR",
                            device_type=target_paid.device_type or "iPhone",
                            quantity=1,
                        )
                    )

    # iOS 7G deneme (trialing) aşamasında olup RevenueCat V2'de oto-yenilemesini kapatmış (will_not_renew) aboneleri işaretle
    if ios_trial_will_not_renew:
        trial_ios_rows: List[SubscriberLedger] = (
            db.query(SubscriberLedger)
            .filter(
                SubscriberLedger.platform == "ios",
                SubscriberLedger.status.in_(["intro_free_trial", "cancelled"]),
                SubscriberLedger.offer_type.in_(["intro_7d_trial", "free_trial_1m"]),
            )
            .order_by(SubscriberLedger.started_date.asc(), SubscriberLedger.subscriber_id.asc())
            .all()
        )
        trial_ios_rows.sort(
            key=lambda r: (
                1 if str(r.subscriber_id or "").startswith("RC_T0_") else 0,
                0 if r.status == "intro_free_trial" else 1,
                r.started_date or "",
                r.subscriber_id or "",
            )
        )
        matched_t_wnr_ids = set()
        for t_wnr in ios_trial_will_not_renew:
            t_cid = str(t_wnr.get("customer_id") or "")[:128]
            t_st = t_wnr.get("started_date") or ""
            t_end = t_wnr.get("ends_at_date") or ""
            t_pid = t_wnr.get("product_id") or ""
            t_cc = t_wnr.get("country") or "TR"
            target_trial = next(
                (
                    r for r in trial_ios_rows
                    if r.subscriber_id not in matched_t_wnr_ids
                    and (
                        (t_cid and r.rc_app_user_id == t_cid)
                        or (
                            (r.started_date == t_st or (t_end and r.maturity_or_renewal_date == t_end))
                            and (not t_pid or r.product_id == t_pid)
                            and ((r.country or "TR").upper() == t_cc)
                        )
                    )
                ),
                None,
            )
            if target_trial:
                matched_t_wnr_ids.add(target_trial.subscriber_id)
                target_trial.rc_app_user_id = t_cid or target_trial.rc_app_user_id
                if t_end:
                    target_trial.maturity_or_renewal_date = t_end
                target_trial.status = "cancelled"
                target_trial.auto_renew_enabled = False
                target_trial.expected_next_price_try = 0.0
                target_trial.expected_next_proceeds_try = 0.0
                t_wnr_ev_key = f"{target_trial.subscriber_id}:will_not_renew"[:128]
                dup_t_wnr = (
                    db.query(SubscriptionLifecycleEvent.id)
                    .filter(
                        SubscriptionLifecycleEvent.platform == "ios",
                        SubscriptionLifecycleEvent.event_type == t_wnr_ev_key,
                    )
                    .first()
                )
                if dup_t_wnr is None:
                    db.add(
                        SubscriptionLifecycleEvent(
                            event_date=t_st or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                            platform="ios",
                            event_type=t_wnr_ev_key,
                            product_id=target_trial.product_id,
                            plan_label=target_trial.plan_label,
                            country=target_trial.country or "TR",
                            device_type=target_trial.device_type or "iPhone",
                            quantity=1,
                        )
                    )

    # Yıllık promosyon kodlu (DamlaEge2026) olup RevenueCat V2'de 'will_change_product' seçenleri işaretle
    if pending_crossgrades:
        code_rows: List[SubscriberLedger] = (
            db.query(SubscriberLedger)
            .filter(
                SubscriberLedger.platform == "ios",
                SubscriberLedger.status == "offer_code_trial",
            )
            .order_by(SubscriberLedger.started_date.asc(), SubscriberLedger.subscriber_id.asc())
            .all()
        )
        matched_cg_sids = set()
        for cg in pending_crossgrades:
            cg_start = cg.get("started_date") or ""
            cg_price = float(cg.get("expected_next_price_try") or 149.99)
            cg_proc = float(cg.get("expected_next_proceeds_try") or round(cg_price * get_dynamic_proceeds_ratio("ios"), 2))
            cg_to_lbl = "Yıllık VIP" if _is_annual_product(cg.get("to_product_id")) else "Aylık VIP"
            target_row = next(
                (
                    r for r in code_rows
                    if r.subscriber_id not in matched_cg_sids
                    and (r.started_date == cg_start or not cg_start)
                ),
                None,
            )
            if target_row:
                matched_cg_sids.add(target_row.subscriber_id)
                target_row.rc_app_user_id = str(cg.get("customer_id") or "")[:128] or target_row.rc_app_user_id
                target_row.expected_next_price_try = cg_price
                target_row.expected_next_proceeds_try = cg_proc
                base_code = (target_row.offer_code_name or "DamlaEge2026").split(" ➔")[0].strip()
                target_row.offer_code_name = f"{base_code} ➔ {cg_to_lbl} ({cg_price:.2f} ₺)"[:95]

    new_cache_payload = {
        "non_sub_seen": non_sub_seen,
        "known_prod_cids": sorted(known_prod_cids),
        "last_list_complete": list_complete,
        "resume_next_url": None if list_complete else resume_cursor_url,
    }
    if cache_row:
        cache_row.snapshot_json = new_cache_payload
    else:
        db.add(
            StoreSyncState(
                state_key="rc_v2_customer_scan_cache",
                snapshot_json=new_cache_payload,
            )
        )

    try:
        db.commit()
    except Exception:
        db.rollback()

    return {
        "connected": True,
        "customers_checked": len(candidate_cids),
        "prod_ios_checked": prod_ios_count,
        "prod_android_checked": prod_android_count,
        "android_test_filtered": android_test_filtered,
        "t0_bridge_upserts": t0_bridge_upserts,
        "pending_crossgrades": pending_crossgrades,
    }



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

    # 0) Doğrulanmamış istemci localStorage kaynaklı sentetik DEV_IOS_* / DEV_ANDROID_* ve sıfır tutarlı iOS RCAnonymousID hayalet/mükerrer kayıtları temizle
    dev_rows: List[SubscriberLedger] = (
        db.query(SubscriberLedger)
        .filter(
            (SubscriberLedger.subscriber_id.like("DEV_%"))
            | (
                (SubscriberLedger.platform == "ios")
                & (SubscriberLedger.subscriber_id.like("%RCAnonymousID:%"))
            ),
            (SubscriberLedger.customer_price_try == 0.0) | (SubscriberLedger.customer_price_try.is_(None)),
        )
        .all()
    )
    if dev_rows:
        for dr in dev_rows:
            db.delete(dr)
        db.query(SubscriptionLifecycleEvent).filter(
            (SubscriptionLifecycleEvent.event_type.like("DEV_%"))
            | (SubscriptionLifecycleEvent.event_type.like("%RCAnonymousID:%"))
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

    # 0b) Apple TSV (SUBSCRIBER 1_3) resmi kaydı ulaştığında, o gün için açılmış geçici RC_T0_* köprü kaydını
    # 2 aşamalı 1-e-1 eşleşmeyle (1: aynı started_date, 2: Reactivate/Downgrade converted_or_renewed_date / vade) tekilleştir
    official_ios_rows = [r for r in ios_rows if not str(r.subscriber_id or "").startswith("RC_T0_")]
    bridge_ios_rows = [r for r in ios_rows if str(r.subscriber_id or "").startswith("RC_T0_")]
    consumed_official_sids = set()
    bridge_dups: List[Tuple[SubscriberLedger, SubscriberLedger]] = []
    unmatched_bridges: List[SubscriberLedger] = []

    for br in bridge_ios_rows:
        br_pid = br.product_id or "misil_monthly"
        br_st = br.started_date or ""
        exact_off = next(
            (
                off_r for off_r in official_ios_rows
                if off_r.subscriber_id not in consumed_official_sids
                and (off_r.product_id or "misil_monthly") == br_pid
                and (off_r.started_date or "") == br_st
            ),
            None,
        )
        if exact_off is not None:
            consumed_official_sids.add(exact_off.subscriber_id)
            bridge_dups.append((br, exact_off))
        else:
            unmatched_bridges.append(br)

    for br in unmatched_bridges:
        br_pid = br.product_id or "misil_monthly"
        br_st = br.started_date or ""
        br_conv = br.converted_or_renewed_date or ""
        br_mat = br.maturity_or_renewal_date or ""
        reactivated_off = next(
            (
                off_r for off_r in official_ios_rows
                if off_r.subscriber_id not in consumed_official_sids
                and (off_r.product_id or "misil_monthly") == br_pid
                and (
                    (br_st and off_r.converted_or_renewed_date == br_st)
                    or (br_conv and off_r.converted_or_renewed_date == br_conv)
                    or (br_mat and off_r.maturity_or_renewal_date == br_mat and off_r.status == "paid_active")
                )
            ),
            None,
        )
        if reactivated_off is not None:
            consumed_official_sids.add(reactivated_off.subscriber_id)
            bridge_dups.append((br, reactivated_off))

    if bridge_dups:
        for bd, target_off in bridge_dups:
            if bd.rc_app_user_id and not target_off.rc_app_user_id:
                target_off.rc_app_user_id = bd.rc_app_user_id
            if not bd.auto_renew_enabled:
                target_off.auto_renew_enabled = False
                target_off.expected_next_price_try = 0.0
                target_off.expected_next_proceeds_try = 0.0
                if target_off.status != "paid_active":
                    target_off.status = "cancelled"
                off_wnr_key = f"{target_off.subscriber_id}:will_not_renew"[:128]
                dup_off_wnr = (
                    db.query(SubscriptionLifecycleEvent.id)
                    .filter(
                        SubscriptionLifecycleEvent.platform == "ios",
                        SubscriptionLifecycleEvent.event_type == off_wnr_key,
                    )
                    .first()
                )
                if dup_off_wnr is None:
                    db.add(
                        SubscriptionLifecycleEvent(
                            event_date=target_off.converted_or_renewed_date or target_off.started_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                            platform="ios",
                            event_type=off_wnr_key,
                            product_id=target_off.product_id,
                            plan_label=target_off.plan_label,
                            country=target_off.country or "TR",
                            device_type=target_off.device_type or "iPhone",
                            quantity=1,
                        )
                    )
            db.delete(bd)
            ios_rows.remove(bd)
        db.flush()
        changed = True


    refunded_sids = {
        (ev.event_type or "").split(":")[0]
        for ev in db.query(SubscriptionLifecycleEvent).filter(
            SubscriptionLifecycleEvent.platform == "ios",
            SubscriptionLifecycleEvent.event_type.like("%:refund"),
        ).all()
    }
    will_not_renew_sids = {
        (ev.event_type or "").split(":")[0]
        for ev in db.query(SubscriptionLifecycleEvent).filter(
            SubscriptionLifecycleEvent.platform == "ios",
            SubscriptionLifecycleEvent.event_type.like("%:will_not_renew"),
        ).all()
    }

    # 1) Ücretli aktif (paid_active) auto_renew_enabled / downgrade onarımı + Yıllık 7G deneme (Default_Intro) 599.99 TL tarife onarımı
    for r in ios_rows:
        if r.status == "paid_active" and (r.customer_price_try or 0.0) > 0 and r.subscriber_id not in refunded_sids:
            if _is_annual_product(r.product_id) and round(float(r.customer_price_try or 0.0), 2) == 149.99:
                r.product_id = "misil_monthly"
                r.plan_label = "Aylık Esnek VIP"
                if r.converted_or_renewed_date and len(r.converted_or_renewed_date) == 10:
                    try:
                        dt_c = datetime.strptime(r.converted_or_renewed_date, "%Y-%m-%d")
                        r.maturity_or_renewal_date = (dt_c + timedelta(days=30)).strftime("%Y-%m-%d")
                    except Exception:
                        pass
                changed = True
            if r.subscriber_id in will_not_renew_sids:
                if r.auto_renew_enabled or (r.expected_next_price_try or 0.0) > 0:
                    r.auto_renew_enabled = False
                    r.expected_next_price_try = 0.0
                    r.expected_next_proceeds_try = 0.0
                    changed = True
            else:
                if not r.auto_renew_enabled:
                    r.auto_renew_enabled = True
                    changed = True
                if (r.expected_next_price_try or 0.0) <= 0:
                    if r.offer_type == "intro_1m_discounted":
                        std_g_i, std_n_i = _resolve_expected_trial_pricing(r.product_id, 0.0, 0.0, "ios")
                        r.expected_next_price_try = std_g_i
                        r.expected_next_proceeds_try = std_n_i
                    else:
                        r.expected_next_price_try = round(float(r.customer_price_try), 2)
                    changed = True
                if (r.expected_next_proceeds_try or 0.0) <= 0:
                    r.expected_next_proceeds_try = round(
                        float(r.expected_next_price_try or r.customer_price_try) * get_dynamic_proceeds_ratio("ios"), 2
                    )
                    changed = True
                elif (r.expected_next_price_try or 0.0) > 0:
                    sbp15_expected_net = round(float(r.expected_next_price_try) * get_dynamic_proceeds_ratio("ios"), 2)
                    if float(r.expected_next_proceeds_try or 0.0) < (sbp15_expected_net - 0.50):
                        r.expected_next_proceeds_try = sbp15_expected_net
                        changed = True

        if r.offer_type == "intro_1m_discounted":
            continue
        if r.status == "offer_code_trial" and r.auto_renew_enabled and (r.expected_next_price_try or 0.0) > 0:
            sbp15_cg_net = round(float(r.expected_next_price_try) * get_dynamic_proceeds_ratio("ios"), 2)
            if float(r.expected_next_proceeds_try or 0.0) < (sbp15_cg_net - 0.50):
                r.expected_next_proceeds_try = sbp15_cg_net
                changed = True
        if r.status == "intro_free_trial" and r.subscriber_id in will_not_renew_sids:
            if r.auto_renew_enabled or r.status != "cancelled" or (r.expected_next_price_try or 0.0) > 0:
                r.status = "cancelled"
                r.auto_renew_enabled = False
                r.expected_next_price_try = 0.0
                r.expected_next_proceeds_try = 0.0
                changed = True
            continue
        is_ann = _is_annual_product(r.product_id)
        of_name_low = (r.offer_code_name or "").strip().lower()
        is_default_intro = (
            not of_name_low
            or "default_intro" in of_name_low
            or "7 günlük deneme" in of_name_low
            or "ilk ay ücretsiz" in of_name_low
        )
        is_custom_promo_code = bool(
            (r.customer_price_try or 0.0) <= 0
            and of_name_low
            and not is_default_intro
            and ("damlaege" in of_name_low or "promo" in of_name_low or "kod" in of_name_low or "code" in of_name_low)
        )
        if not is_custom_promo_code and (r.customer_price_try or 0.0) <= 0 and not is_default_intro:
            try:
                if r.started_date and r.maturity_or_renewal_date and len(r.started_date) == 10 and len(r.maturity_or_renewal_date) == 10:
                    d_span = (datetime.strptime(r.maturity_or_renewal_date, "%Y-%m-%d") - datetime.strptime(r.started_date, "%Y-%m-%d")).days
                    if d_span > 45:
                        is_custom_promo_code = True
            except Exception:
                pass
        if r.status == "intro_free_trial" and is_custom_promo_code:
            r.status = "offer_code_trial"
            r.offer_type = "offer_code"
            if "➔" not in (r.offer_code_name or ""):
                r.expected_next_price_try = 0.0
                r.expected_next_proceeds_try = 0.0
            changed = True
        elif is_ann and r.status == "offer_code_trial" and is_default_intro and (r.customer_price_try or 0.0) <= 0:
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
        elif r.status == "intro_free_trial" and r.auto_renew_enabled and (r.expected_next_price_try or 0.0) > 0:
            sbp15_trial_net = round(float(r.expected_next_price_try) * get_dynamic_proceeds_ratio("ios"), 2)
            if float(r.expected_next_proceeds_try or 0.0) < (sbp15_trial_net - 0.50):
                r.expected_next_proceeds_try = sbp15_trial_net
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
        # Apple SUBSCRIPTION (1_3) raporu, 7 günlük deneme süresi henüz dolmamış ancak RevenueCat V2'de
        # oto-yenilemesini kapatmış (will_not_renew) aboneleri vade sonuna kadar aktif deneme sayar;
        # bu abonelerin hedef sayıdan düşülmesi ve yanlışlıkla tekrar 'intro_free_trial' olarak geri yüklenmemesi gerekir.
        unexpired_wnr_trials_cnt = sum(
            1 for r in ios_rows
            if r.subscriber_id in will_not_renew_sids
            and (r.customer_price_try or 0.0) <= 0
            and r.offer_type in ("intro_7d_trial", "free_trial_1m")
            and (not r.maturity_or_renewal_date or len(r.maturity_or_renewal_date) != 10 or r.maturity_or_renewal_date >= today_str)
        )
        effective_trials_target = max(0, int(active_trials_target) - unexpired_wnr_trials_cnt)
        deficit = effective_trials_target - len(active_trials)
        if deficit > 0 and merged_cancels:
            # Daha önce DEV_IOS_* şişmesi nedeniyle yanlışlıkla iptal edilmiş (Cancel veya will_not_renew olayı bulunmayan) gerçek Apple denemelerini geri yükle
            cancelled_by_cohort: Dict[tuple, List[SubscriberLedger]] = {}
            for r in ios_rows:
                if (
                    r.status == "cancelled"
                    and (r.customer_price_try or 0.0) <= 0
                    and r.offer_type in ("intro_7d_trial", "free_trial_1m")
                    and r.subscriber_id not in will_not_renew_sids
                ):
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
    Tekil Uçuş (Single-Flight) korumalı resmi mağaza senkronizasyonu.
    Eşzamanlı çağrılarda ikinci bir ağır tarama başlatmaz; mevcut çalışma bilgisini döndürür.
    """
    if not _STORE_SYNC_EXEC_LOCK.acquire(blocking=False):
        return {
            "synced": False,
            "already_running": True,
            "sources": list(_STORE_SYNC_LAST_STATUS.get("last_sources") or []),
            "apple_connected": True,
            "google_connected": True,
            "synced_at": str(_STORE_SYNC_LAST_STATUS.get("last_synced_at") or ""),
        }
    _STORE_SYNC_LAST_STATUS["running"] = True
    _STORE_SYNC_LAST_STATUS["started_at"] = datetime.now(timezone(timedelta(hours=3))).strftime("%d.%m.%Y %H:%M TSİ")
    try:
        res = _sync_live_store_apis_inner(days_back=days_back)
        _STORE_SYNC_LAST_STATUS["last_synced_at"] = str(res.get("synced_at") or "")
        _STORE_SYNC_LAST_STATUS["last_sources"] = list(res.get("sources") or [])
        invalidate_analytics_summary_cache(mark_reconcile=False, reset_baseline_stamp=True)
        return res
    finally:
        _STORE_SYNC_LAST_STATUS["running"] = False
        _STORE_SYNC_EXEC_LOCK.release()


def _sync_live_store_apis_inner(days_back: int = 5) -> Dict[str, Any]:
    """
    P0-1 & Sıfır Statik Veri Çözümü:
    Ağ G/Ç işlemleri _BASELINE_LOCK dışında yürütülür; Apple App Store Connect API ve
    Google Play Developer API verileri doğrudan StoreDailyMetric, SubscriberLedger,
    SubscriptionLifecycleEvent ve StoreSyncState tablolarına idempotent olarak yazılır.
    """
    if not jwt:
        return {"synced": False, "sources": [], "reason": "PyJWT not available"}

    # Sunucu açılışında OFFICIAL_STORE_BASELINE henüz yüklenmemişse DB'den hızlıca ısıt
    try:
        db_pre = SessionLocal()
        try:
            ensure_historical_seed(db_pre)
        finally:
            db_pre.close()
    except Exception:
        pass

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
    country_by_date_synced: Dict[str, Dict[str, int]] = {}
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
                "https://api.appstoreconnect.apple.com/v1/apps/6809223195/customerReviews?limit=50&sort=-createdDate&include=response",
                headers=hdrs,
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                if resp.status == 200:
                    apple_connected = True
                    data = json.loads(resp.read().decode("utf-8"))
                    included_responses: Dict[str, Dict[str, Any]] = {}
                    for inc in data.get("included", []) or []:
                        if inc.get("type") == "customerReviewResponses" and inc.get("id"):
                            included_responses[str(inc["id"])] = inc.get("attributes") or {}
                    for r in data.get("data", []):
                        rev_id = str(r.get("id") or "").strip()
                        attr = r.get("attributes", {})
                        cdate = (attr.get("createdDate") or "")[:10]
                        if len(cdate) == 10 and "-" in cdate:
                            parts = cdate.split("-")
                            cdate = f"{parts[2]}.{parts[1]}.{parts[0]}"
                        rating_clamped = max(1, min(5, int(attr.get("rating") or 5)))
                        rel_resp = ((r.get("relationships") or {}).get("response") or {}).get("data") or {}
                        resp_id = str(rel_resp.get("id") or "").strip() if isinstance(rel_resp, dict) else ""
                        resp_attr = included_responses.get(resp_id, {}) if resp_id else {}
                        resp_body = str(resp_attr.get("responseBody") or "").strip()
                        resp_state = str(resp_attr.get("state") or ("PUBLISHED" if resp_body else "")).strip()
                        resp_date_raw = (resp_attr.get("lastModifiedDate") or "")[:10]
                        if len(resp_date_raw) == 10 and "-" in resp_date_raw:
                            rp = resp_date_raw.split("-")
                            resp_date_str = f"{rp[2]}.{rp[1]}.{rp[0]}"
                        else:
                            resp_date_str = resp_date_raw
                        fetched_apple_reviews.append({
                            "review_id": rev_id,
                            "store": "App Store",
                            "platform": "ios",
                            "badge": "🍏 iOS",
                            "rating": rating_clamped,
                            "title": attr.get("title") or "App Store Yorumu",
                            "body": attr.get("body") or "",
                            "author": attr.get("reviewerNickname") or "App Store Kullanıcısı",
                            "date": cdate,
                            "territory": attr.get("territory") or "TUR",
                            "response_id": resp_id,
                            "response_body": resp_body,
                            "response_state": resp_state,
                            "response_date": resp_date_str,
                        })
                    synced_sources.append("Apple App Store Connect API (Reviews)")

            # iTunes Lookup API: Yazılı yorum bırakmadan yıldız verenler dahil resmi mağaza genel puanı (örn. 4.6 ★) ve toplam oy sayısı
            try:
                itunes_req = urllib.request.Request(
                    "https://itunes.apple.com/lookup?id=6809223195&country=tr",
                    headers={"Accept": "application/json", "User-Agent": "MishilCockpit/4.57.7"},
                )
                with urllib.request.urlopen(itunes_req, timeout=4) as it_resp:
                    if it_resp.status == 200:
                        it_payload = json.loads(it_resp.read().decode("utf-8"))
                        it_results = it_payload.get("results") or []
                        if it_results and isinstance(it_results[0], dict):
                            it_app = it_results[0]
                            it_avg = round(float(it_app.get("averageUserRating") or it_app.get("averageUserRatingForCurrentVersion") or 0.0), 1)
                            it_cnt = int(it_app.get("userRatingCount") or it_app.get("userRatingCountForCurrentVersion") or 0)
                            if it_avg > 0 and it_cnt > 0:
                                with _BASELINE_LOCK:
                                    OFFICIAL_STORE_BASELINE["apple_overall_rating"] = it_avg
                                    OFFICIAL_STORE_BASELINE["apple_overall_ratings_count"] = it_cnt
                                synced_sources.append("Apple iTunes Lookup API (Overall Rating)")
            except Exception as it_exc:
                logger.debug("iTunes Lookup rating sync info: %s", it_exc)

            vendor_num = os.environ.get("ASC_VENDOR_NUMBER", "94806500")
            tz_tr_sync = timezone(timedelta(hours=3))
            today_d = datetime.now(tz_tr_sync).date()
            with _BASELINE_LOCK:
                has_country_date_hist = bool(OFFICIAL_STORE_BASELINE.get("apple_country_downloads_by_date"))
            effective_days = 45 if (int(days_back) <= 5 and not has_country_date_hist) else int(days_back)
            scan_days = max(1, min(60, effective_days))

            for day_offset in range(scan_days, -1, -1):
                time.sleep(0.005)
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
                                day_country_dl: Counter = Counter()
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
                                            day_country_dl[cc] += units
                                    elif p_type in ("3", "3F"):
                                        day_redl += units
                                        day_app_dl += units
                                        if units > 0:
                                            country_totals[cc] += units
                                            day_country_dl[cc] += units
                                    elif p_type in ("IAY", "IA9", "IA1"):
                                        day_sub_vip += units
                                        if c_price > 0:
                                            day_gross_try += _convert_to_try(c_price * max(1, units), c_ccy)
                                            day_net_try += _convert_to_try(d_proc * max(1, units), p_ccy)
                                if day_country_dl:
                                    country_by_date_synced[rep_date] = dict(day_country_dl)

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
                                        if c_price_try > 0 and d_proc_try > 0 and not (rd.get("Refund") or "").strip().lower() == "yes":
                                            observe_proceeds_ratio("ios", c_price_try, d_proc_try)
                                        cntry = (rd.get("Country") or "TR").strip().upper()
                                        dev = (rd.get("Device") or "iPhone").strip()
                                        refund_flag = (rd.get("Refund") or "").strip().lower() == "yes"
                                        is_annual = "Yillik" in sub_name or "6809228257" in (rd.get("Subscription Apple ID") or "")
                                        prod_id = "misil_annual" if is_annual else "misil_monthly"
                                        plan_lbl = "Yıllık VIP" if is_annual else "Aylık Esnek VIP"
                                        paid_ref_rows = (
                                            db_sync.query(SubscriberLedger)
                                            .filter(
                                                SubscriberLedger.product_id == prod_id,
                                                SubscriberLedger.customer_price_try > 0,
                                            )
                                            .all()
                                        )
                                        ref_gross, ref_net = 0.0, 0.0
                                        for pr_row in paid_ref_rows:
                                            std_pair = _extract_single_period_standard_ref(
                                                prod_id,
                                                float(pr_row.customer_price_try or 0.0),
                                                float(pr_row.developer_proceeds_try or 0.0),
                                                float(pr_row.expected_next_price_try or 0.0),
                                                float(pr_row.expected_next_proceeds_try or 0.0),
                                                pr_row.offer_type,
                                                "ios",
                                            )
                                            if std_pair:
                                                ref_gross, ref_net = std_pair
                                                break
                                        std_price_try, std_proc_try = _resolve_expected_trial_pricing(
                                            prod_id, ref_gross, ref_net, "ios"
                                        )
                                        is_discounted_intro_paid = bool(
                                            not is_annual
                                            and c_price_try > 0
                                            and cntry == "TR"
                                            and 20.0 <= c_price_try < 100.0
                                        )

                                        is_1m_free_trial_tsv = bool(
                                            c_price_try <= 0
                                            and not is_annual
                                            and (
                                                "1 month" in offer_dur_raw.lower()
                                                or "30 days" in offer_dur_raw.lower()
                                                or "free_trial_1m" in offer_name.lower()
                                                or "free-trial-1m" in offer_name.lower()
                                                or "first_month_free" in offer_name.lower()
                                                or (
                                                    ("default_intro" in offer_name.lower() or "introductory" in offer_type_raw.lower())
                                                    and "7 days" not in offer_dur_raw.lower()
                                                    and "1 week" not in offer_dur_raw.lower()
                                                    and ("month" in offer_dur_raw.lower() or "30" in offer_dur_raw.lower())
                                                )
                                            )
                                        )

                                        is_intro_offer = (
                                            is_1m_free_trial_tsv
                                            or "default_intro" in offer_name.lower()
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
                                                existing_sub.product_id = prod_id
                                                existing_sub.plan_label = plan_lbl
                                                existing_sub.status = "paid_active"
                                                existing_sub.offer_type = "intro_1m_discounted" if is_discounted_intro_paid else "standard_paid"
                                                existing_sub.auto_renew_enabled = True
                                                existing_sub.converted_or_renewed_date = ev_date
                                                existing_sub.customer_price_try = round((existing_sub.customer_price_try or 0.0) + c_price_try, 2)
                                                existing_sub.developer_proceeds_try = round((existing_sub.developer_proceeds_try or 0.0) + d_proc_try, 2)
                                                existing_sub.expected_next_price_try = std_price_try if is_discounted_intro_paid else c_price_try
                                                existing_sub.expected_next_proceeds_try = std_proc_try if is_discounted_intro_paid else d_proc_try
                                                try:
                                                    dt_conv = datetime.strptime(ev_date, "%Y-%m-%d")
                                                    existing_sub.maturity_or_renewal_date = (dt_conv + timedelta(days=365 if is_annual else 30)).strftime("%Y-%m-%d")
                                                except Exception:
                                                    pass
                                            elif existing_sub.status == "offer_code_trial" and not is_offer_code and c_price_try <= 0:
                                                existing_sub.status = "intro_free_trial"
                                                existing_sub.offer_type = "free_trial_1m" if is_1m_free_trial_tsv else "intro_7d_trial"
                                                ccy_suffix = f" ({c_ccy})" if c_ccy != "TRY" else ""
                                                existing_sub.offer_code_name = (("İlk Ay Ücretsiz Deneme" if is_1m_free_trial_tsv else "7 Günlük Deneme") + ccy_suffix)[:95]
                                                try:
                                                    dt_st = datetime.strptime(existing_sub.started_date or ev_date, "%Y-%m-%d")
                                                    existing_sub.maturity_or_renewal_date = (dt_st + timedelta(days=30 if is_1m_free_trial_tsv else 7)).strftime("%Y-%m-%d")
                                                except Exception:
                                                    pass
                                                existing_sub.expected_next_price_try = std_price_try
                                                existing_sub.expected_next_proceeds_try = std_proc_try
                                        else:
                                            trial_days = (365 if is_annual else 30) if is_offer_code else (30 if is_1m_free_trial_tsv else 7)
                                            try:
                                                dt_st = datetime.strptime(ev_date, "%Y-%m-%d")
                                                mat_date = (dt_st + timedelta(days=(365 if is_annual else 30) if c_price_try > 0 else trial_days)).strftime("%Y-%m-%d")
                                            except Exception:
                                                mat_date = ev_date
                                            st_val = "paid_active" if c_price_try > 0 else ("offer_code_trial" if is_offer_code else "intro_free_trial")
                                            of_type = (
                                                ("intro_1m_discounted" if is_discounted_intro_paid else "standard_paid")
                                                if c_price_try > 0
                                                else ("offer_code" if is_offer_code else ("free_trial_1m" if is_1m_free_trial_tsv else "intro_7d_trial"))
                                            )
                                            ccy_suffix = f" ({c_ccy})" if c_ccy != "TRY" else ""
                                            of_lbl = (
                                                offer_name
                                                if is_offer_code
                                                else (
                                                    "İlk Ay İndirimli Başlangıç"
                                                    if is_discounted_intro_paid
                                                    else (
                                                        "Standart Ücretli"
                                                        if c_price_try > 0
                                                        else ("İlk Ay Ücretsiz Deneme" if is_1m_free_trial_tsv else "7 Günlük Deneme")
                                                    )
                                                )
                                            ) + ccy_suffix
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
                                                    expected_next_price_try=(
                                                        (std_price_try if is_discounted_intro_paid else c_price_try)
                                                        if c_price_try > 0
                                                        else (0.0 if is_offer_code else std_price_try)
                                                    ),
                                                    expected_next_proceeds_try=(
                                                        (std_proc_try if is_discounted_intro_paid else d_proc_try)
                                                        if d_proc_try > 0
                                                        else (0.0 if is_offer_code else std_proc_try)
                                                    ),
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
                taps_uniq_by_date: Counter = Counter()
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
                                    d_taps_u: Counter = Counter()
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
                                            d_taps_u[dt_s] += ucnt_v
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
                                    for dt_k, v_c in d_taps_u.items():
                                        taps_uniq_by_date[dt_k] = max(taps_uniq_by_date[dt_k], v_c)
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
                        OFFICIAL_STORE_BASELINE["apple_taps_unique"] = sum(taps_uniq_by_date.values())
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
                                    gp_rev_id = str(r_item.get("reviewId") or "").strip()
                                    comments = r_item.get("comments", [])
                                    if not comments:
                                        continue
                                    uc = comments[0].get("userComment", {})
                                    dc = {}
                                    for c_obj in comments:
                                        if isinstance(c_obj, dict) and c_obj.get("developerComment"):
                                            dc = c_obj.get("developerComment") or {}
                                            break
                                    star_r = max(1, min(5, int(uc.get("starRating") or 5)))
                                    ts_sec = int((uc.get("lastModified") or {}).get("seconds") or now_gp)
                                    dt_str = datetime.fromtimestamp(ts_sec, tz=timezone(timedelta(hours=3))).strftime("%d.%m.%Y")
                                    dc_text = str(dc.get("text") or "").strip()
                                    dc_ts = int((dc.get("lastModified") or {}).get("seconds") or 0)
                                    dc_date = (
                                        datetime.fromtimestamp(dc_ts, tz=timezone(timedelta(hours=3))).strftime("%d.%m.%Y")
                                        if dc_ts > 0
                                        else ""
                                    )
                                    fetched_gp_reviews.append({
                                        "review_id": gp_rev_id,
                                        "store": "Google Play",
                                        "platform": "android",
                                        "badge": "🤖 Android",
                                        "rating": star_r,
                                        "title": (uc.get("deviceMetadata") or {}).get("productName") or "Google Play Yorumu",
                                        "body": (uc.get("text") or "").strip(),
                                        "author": r_item.get("authorName") or "Google Play Kullanıcısı",
                                        "date": dt_str,
                                        "response_id": gp_rev_id if dc_text else "",
                                        "response_body": dc_text,
                                        "response_state": "PUBLISHED" if dc_text else "",
                                        "response_date": dc_date,
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
                                            offer_id = "-"
                                            offer_lbl = "Denemesiz • Standart"
                                            try:
                                                gp_off_req = urllib.request.Request(
                                                    f"https://androidpublisher.googleapis.com/androidpublisher/v3/applications/com.levitas.misilbaby/subscriptions/{p_id}/basePlans/{bp_id}/offers",
                                                    headers={"Authorization": f"Bearer {access_token}"},
                                                )
                                                with urllib.request.urlopen(gp_off_req, timeout=3) as gp_off_resp:
                                                    if gp_off_resp.status == 200:
                                                        off_payload = json.loads(gp_off_resp.read().decode("utf-8"))
                                                        active_off_ids: List[str] = []
                                                        active_off_lbls: List[str] = []
                                                        for off_item in off_payload.get("subscriptionOffers", []):
                                                            if (off_item.get("state") or "") == "ACTIVE":
                                                                cur_oid = str(off_item.get("offerId") or "").strip()
                                                                if cur_oid:
                                                                    active_off_ids.append(cur_oid)
                                                                phases = off_item.get("phases") or []
                                                                if phases:
                                                                    ph0 = phases[0]
                                                                    ph_dur = ph0.get("duration") or "P1M"
                                                                    tr_off_p = 0.0
                                                                    has_free_ph = False
                                                                    for r_ph in (ph0.get("regionalConfigs") or []):
                                                                        if "free" in r_ph:
                                                                            has_free_ph = True
                                                                        if r_ph.get("regionCode") == "TR" and isinstance(r_ph.get("price"), dict):
                                                                            tr_off_p = round(
                                                                                float(r_ph["price"].get("units") or 0)
                                                                                + (float(r_ph["price"].get("nanos") or 0) / 1e9),
                                                                                2,
                                                                            )
                                                                    if tr_off_p > 0:
                                                                        active_off_lbls.append(f"🔥 İlk Ay {tr_off_p:.2f} ₺ (%67 İndirim • {ph_dur})")
                                                                    elif has_free_ph:
                                                                        active_off_lbls.append(f"🎁 İlk Ay Ücretsiz (30G 0 ₺ • {ph_dur})")
                                                                    else:
                                                                        active_off_lbls.append(f"Başlangıç Teklifi ({ph_dur} • Aktif)")
                                                        if active_off_ids:
                                                            offer_id = " / ".join(active_off_ids)
                                                        if active_off_lbls:
                                                            offer_lbl = " vs ".join(active_off_lbls) if len(active_off_lbls) > 1 else active_off_lbls[0]
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
    today_sync_d = datetime.now(tz_tr).date()

    # Adım 3: RevenueCat REST API v2 (T-0 Canlı Köprü & Google Play Production Senkronizasyonu)
    # ve SubscriberLedger -> StoreDailyMetric günlük gelir serisi mutabakatı
    latest_apple_rep_date = ""
    apple_lag_days_calc = 1
    rc_bridge_res: Dict[str, Any] = {}
    calc_ios_gross_try = 0.0
    calc_ios_proceeds_try = 0.0
    calc_ios_paid_tx = 0
    calc_ios_by_plan: Dict[str, int] = {}

    try:
        db_fin = SessionLocal()
        try:
            ios_dm_dates = [
                r[0]
                for r in db_fin.query(StoreDailyMetric.metric_date)
                .filter(StoreDailyMetric.platform == "ios", StoreDailyMetric.downloads_total > 0)
                .all()
                if r[0]
            ]
            if ios_dm_dates:
                latest_apple_rep_date = max(ios_dm_dates)
                try:
                    rep_dt_obj = datetime.strptime(latest_apple_rep_date, "%Y-%m-%d").date()
                    apple_lag_days_calc = max(1, (today_sync_d - rep_dt_obj).days)
                except Exception:
                    apple_lag_days_calc = 1

            rc_bridge_res = sync_revenuecat_v2_production_bridge(
                db_fin, latest_apple_report_date=latest_apple_rep_date
            )
            if rc_bridge_res.get("connected"):
                synced_sources.append("RevenueCat REST API v2 (T-0 Production Bridge)")

            # SubscriberLedger üzerindeki gerçekleşmiş ödemeleri (customer_price_try > 0)
            # işlem gününe (converted_or_renewed_date / started_date) göre StoreDailyMetric'e işle
            all_ledger_rows: List[SubscriberLedger] = db_fin.query(SubscriberLedger).all()
            daily_rev_by_plat_date: Dict[tuple, List[float]] = {}
            for lr in all_ledger_rows:
                l_plat = "android" if (lr.platform or "ios").lower() == "android" else "ios"
                if l_plat == "ios" and lr.status != "cancelled" and lr.auto_renew_enabled:
                    p_key = lr.product_id or "misil_monthly"
                    calc_ios_by_plan[p_key] = calc_ios_by_plan.get(p_key, 0) + 1
                c_pr = float(lr.customer_price_try or 0.0)
                d_pr = float(lr.developer_proceeds_try or 0.0)
                if c_pr > 0:
                    tx_dt = (lr.converted_or_renewed_date or lr.started_date or "").strip()[:10]
                    if len(tx_dt) == 10:
                        bucket = daily_rev_by_plat_date.setdefault((l_plat, tx_dt), [0.0, 0.0])
                        bucket[0] = round(bucket[0] + c_pr, 2)
                        bucket[1] = round(bucket[1] + d_pr, 2)
                    if l_plat == "ios":
                        calc_ios_gross_try = round(calc_ios_gross_try + c_pr, 2)
                        calc_ios_proceeds_try = round(calc_ios_proceeds_try + d_pr, 2)
                        calc_ios_paid_tx += 1

            for (r_plat, r_dt), (g_val, n_val) in daily_rev_by_plat_date.items():
                dm_row = (
                    db_fin.query(StoreDailyMetric)
                    .filter(StoreDailyMetric.metric_date == r_dt, StoreDailyMetric.platform == r_plat)
                    .first()
                )
                if dm_row:
                    dm_row.gross_revenue_try = g_val
                    dm_row.net_proceeds_try = n_val
                else:
                    db_fin.add(
                        StoreDailyMetric(
                            metric_date=r_dt,
                            platform=r_plat,
                            downloads_total=0,
                            gross_revenue_try=g_val,
                            net_proceeds_try=n_val,
                        )
                    )
            db_fin.commit()
        finally:
            db_fin.close()
    except Exception as fin_sync_exc:
        logger.debug("Financial daily series & RC V2 bridge sync info: %s", fin_sync_exc)

    # Kısa süreli kilit altında bellek içi ve DB StoreSyncState güncellemesi
    with _BASELINE_LOCK:
        if apple_connected:
            OFFICIAL_STORE_BASELINE["apple_sync_status"] = "CONNECTED (Apple App Store Connect API)"
        if google_connected:
            OFFICIAL_STORE_BASELINE["google_sync_status"] = "CONNECTED (Google Play Developer API)"
        if rc_bridge_res.get("connected"):
            OFFICIAL_STORE_BASELINE["rc_v2_sync_status"] = "CONNECTED (RevenueCat REST API v2 • Production)"
            OFFICIAL_STORE_BASELINE["rc_v2_pending_crossgrades"] = rc_bridge_res.get("pending_crossgrades", [])
        if latest_apple_rep_date:
            OFFICIAL_STORE_BASELINE["apple_latest_report_date"] = latest_apple_rep_date
            OFFICIAL_STORE_BASELINE["apple_report_lag_days"] = apple_lag_days_calc
        if calc_ios_gross_try > 0:
            OFFICIAL_STORE_BASELINE["apple_vip_paid_customer_price_try"] = calc_ios_gross_try
            OFFICIAL_STORE_BASELINE["apple_vip_paid_proceeds_try"] = calc_ios_proceeds_try
            OFFICIAL_STORE_BASELINE["apple_vip_total_transactions"] = calc_ios_paid_tx
        if calc_ios_by_plan:
            OFFICIAL_STORE_BASELINE["apple_vip_by_plan"] = calc_ios_by_plan
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
        if country_by_date_synced or country_totals:
            merged_by_date: Dict[str, Dict[str, int]] = {}
            existing_by_date = OFFICIAL_STORE_BASELINE.get("apple_country_downloads_by_date")
            if isinstance(existing_by_date, dict):
                for dt_k, cc_map in existing_by_date.items():
                    if isinstance(cc_map, dict):
                        merged_by_date[str(dt_k)] = {str(k): int(v or 0) for k, v in cc_map.items() if int(v or 0) > 0}
            for dt_k, cc_map in country_by_date_synced.items():
                merged_by_date[str(dt_k)] = {str(k): int(v or 0) for k, v in cc_map.items() if int(v or 0) > 0}
            OFFICIAL_STORE_BASELINE["apple_country_downloads_by_date"] = merged_by_date
            merged_country_totals: Counter = Counter()
            if merged_by_date:
                for cc_map in merged_by_date.values():
                    for cc_code, cc_cnt in cc_map.items():
                        merged_country_totals[cc_code] += int(cc_cnt or 0)
            else:
                merged_country_totals.update(country_totals)
            c_list = []
            for cc_code, cc_cnt in merged_country_totals.most_common():
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


def _determine_periodic_sync_days() -> int:
    """Veritabanında geçmiş günlük metrikler ve ülke serisi zaten varsa yalnızca son 5 günü tarar."""
    try:
        db_chk = SessionLocal()
        try:
            ios_cnt = db_chk.query(func.count(StoreDailyMetric.id)).filter(StoreDailyMetric.platform == "ios").scalar() or 0
            st_row = db_chk.query(StoreSyncState).filter(StoreSyncState.state_key == "primary_store_baseline").first()
            snap = (st_row.snapshot_json or {}) if (st_row and isinstance(st_row.snapshot_json, dict)) else {}
            if ios_cnt >= 3 and bool(snap.get("apple_country_downloads_by_date")):
                return 5
        finally:
            db_chk.close()
    except Exception:
        pass
    return 45


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
    # İlk çalışma için konteyner ısınmasının tamamlanmasını bekle (45 sn)
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=45)
        return
    except asyncio.TimeoutError:
        pass

    while not stop_event.is_set():
        try:
            sync_days = await run_in_threadpool(_determine_periodic_sync_days)
            logger.info("Triggering periodic background store sync (days_back=%d)...", sync_days)
            res = await run_in_threadpool(sync_live_store_apis, sync_days)
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
    Canlı ortamda ağır şema/temizlik sorguları süreç başına yalnızca bir kez koşturulur.
    """
    global _SCHEMA_INITIALIZED, _BRIDGE_TABLE_READY
    is_pytest = bool(os.environ.get("PYTEST_CURRENT_TEST"))
    is_prod_engine = False
    try:
        is_prod_engine = (db is not None and db.get_bind() is engine) or (db is None)
    except Exception:
        is_prod_engine = False

    need_heavy_init = is_pytest or (not is_prod_engine) or (not _SCHEMA_INITIALIZED)
    if need_heavy_init:
        with _SCHEMA_INIT_LOCK:
            if is_pytest or (not is_prod_engine) or (not _SCHEMA_INITIALIZED):
                try:
                    bind_target = db.connection() if db is not None else engine
                    Base.metadata.create_all(bind=bind_target, checkfirst=True)
                    insp = inspect(bind_target)
                    if insp.has_table("store_daily_metrics"):
                        existing_cols = {col["name"] for col in insp.get_columns("store_daily_metrics")}
                        if "active_sessions" not in existing_cols:
                            db.execute(text("ALTER TABLE store_daily_metrics ADD COLUMN active_sessions INTEGER NOT NULL DEFAULT 0"))
                            db.commit()
                    if insp.has_table("subscriber_ledger"):
                        sl_cols = {col["name"] for col in insp.get_columns("subscriber_ledger")}
                        if "rc_app_user_id" not in sl_cols:
                            db.execute(text("ALTER TABLE subscriber_ledger ADD COLUMN rc_app_user_id VARCHAR(128)"))
                            db.commit()
                        if "device_uid" not in sl_cols:
                            db.execute(text("ALTER TABLE subscriber_ledger ADD COLUMN device_uid VARCHAR(128)"))
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

                    # v4.56.4 Tek Seferlik Köprü Sıfırlaması (Eski /ios ve reklam fbclid tıklamalarının temizlenmesi;
                    # organik /download Instagram Bio tıklamaları silinmez)
                    # Not: PYTEST_CURRENT_TEST altında birim testleri geçmiş tarihli (timedelta(days=3)) sentetik BridgeClick
                    # tohumladığı için yalnızca gerçek ortamda veya MISIL_FORCE_BRIDGE_RESET_IN_TEST=1 iken çalışır.
                    if (not is_pytest) or os.environ.get("MISIL_FORCE_BRIDGE_RESET_IN_TEST") == "1":
                        reset_marker = (
                            db.query(StoreSyncState)
                            .filter(StoreSyncState.state_key == BRIDGE_RESET_V4564_STATE_KEY)
                            .first()
                        )
                        if reset_marker is None:
                            bind_dialect = getattr(getattr(db.get_bind(), "dialect", None), "name", "")
                            cutoff_param = (
                                BRIDGE_RESET_V4564_CUTOFF_UTC
                                if bind_dialect == "postgresql"
                                else BRIDGE_RESET_V4564_CUTOFF_UTC.replace(tzinfo=None)
                            )
                            purged_bridge_cnt = (
                                db.query(BridgeClick)
                                .filter(
                                    BridgeClick.created_at < cutoff_param,
                                    (BridgeClick.route_path != "/download") | (BridgeClick.has_fbclid.is_(True)),
                                )
                                .delete(synchronize_session=False)
                            )
                            db.add(
                                StoreSyncState(
                                    state_key=BRIDGE_RESET_V4564_STATE_KEY,
                                    snapshot_json={
                                        "reset_cutoff_utc": BRIDGE_RESET_V4564_CUTOFF_UTC.isoformat(),
                                        "purged_bridge_clicks": int(purged_bridge_cnt or 0),
                                        "active_sole_bridge": "/download",
                                    },
                                    last_synced_at_str=BRIDGE_RESET_V4564_CUTOFF_UTC.strftime("%Y-%m-%d %H:%M:%S UTC"),
                                )
                            )
                            db.commit()
                            if purged_bridge_cnt:
                                invalidate_analytics_summary_cache(mark_reconcile=False)
                except Exception as purge_exc:
                    logger.debug("Legacy seed purge skipped: %s", purge_exc)
                    try:
                        db.rollback()
                    except Exception:
                        pass

                if is_prod_engine and not is_pytest:
                    _SCHEMA_INITIALIZED = True
                    _BRIDGE_TABLE_READY = True

    global _BASELINE_LOADED_STAMP
    try:
        if is_prod_engine and not is_pytest:
            st_meta = (
                db.query(StoreSyncState.updated_at, StoreSyncState.last_synced_at_str)
                .filter(StoreSyncState.state_key == "primary_store_baseline")
                .first()
            )
            if st_meta is None:
                return
            cur_stamp = (str(st_meta[0] or ""), str(st_meta[1] or ""))
            with _BASELINE_LOCK:
                if _BASELINE_LOADED_STAMP == cur_stamp:
                    return
        else:
            cur_stamp = None

        st_row = db.query(StoreSyncState).filter(StoreSyncState.state_key == "primary_store_baseline").first()
        if st_row and isinstance(st_row.snapshot_json, dict):
            with _BASELINE_LOCK:
                row_stamp = (
                    str(getattr(st_row, "updated_at", "") or ""),
                    str(st_row.last_synced_at_str or ""),
                )
                if is_prod_engine and not is_pytest and _BASELINE_LOADED_STAMP == row_stamp:
                    return
                for k, v in st_row.snapshot_json.items():
                    masked_v = _mask_sensitive_sync_value(v)
                    if k == "apple_sync_status" and isinstance(masked_v, str) and "AuthKey_" in masked_v:
                        OFFICIAL_STORE_BASELINE[k] = "CONNECTED (Apple App Store Connect API)"
                    else:
                        OFFICIAL_STORE_BASELINE[k] = masked_v
                if st_row.last_synced_at_str:
                    OFFICIAL_STORE_BASELINE["last_synced_at"] = _mask_sensitive_sync_value(st_row.last_synced_at_str)
                if is_prod_engine and not is_pytest:
                    _BASELINE_LOADED_STAMP = row_stamp
    except Exception as e:
        logger.debug("StoreSyncState load skipped: %s", e)


def extract_trusted_client_ip(request: Request) -> str:
    """
    Güvenilir istemci IP çıkarımı (Spoofing / Click-Fraud Korumalı):
    1) Doğrudan TCP bağlantısı genel (public/global) bir IP'den geliyorsa (arada güvenilir
       ters vekil/proxy yoksa), istemcinin enjekte edebileceği X-Forwarded-For ve
       CF-Connecting-IP başlıklarını yok sayar ve doğrudan TCP peer IP'sini kullanır.
    2) İstek güvenilir iç ağ vekilinden (Railway Envoy private CIDR / loopback / TestClient)
       geliyorsa:
       - Yalnızca TRUST_CLOUDFLARE_HEADERS=true ve CF-Ray başlığı birlikte mevcutsa
         geçerli CF-Connecting-IP'yi kabul eder,
       - Aksi halde ters vekilin sona eklediği (en sağdaki / rightmost) geçerli
         X-Forwarded-For IP adresini alır (istemcinin sola eklediği sahte IP'leri ve X-Real-IP'yi yok sayar).
    """
    import ipaddress

    peer_host = (request.client.host if request.client else "") or ""

    def _valid_ip(candidate: Optional[str]) -> Optional[str]:
        if not candidate:
            return None
        cleaned = candidate.strip()
        if not cleaned:
            return None
        try:
            return str(ipaddress.ip_address(cleaned))
        except ValueError:
            return None

    peer_valid = _valid_ip(peer_host)
    is_trusted_proxy_hop = False
    if peer_host == "testclient" or not peer_host:
        is_trusted_proxy_hop = True
    elif peer_valid:
        ip_obj = ipaddress.ip_address(peer_valid)
        is_trusted_proxy_hop = bool(ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local)

    if not is_trusted_proxy_hop:
        return peer_valid or "unknown"

    # Çıplak Railway domaininde (*.up.railway.app) istemci sahte CF-Ray + CF-Connecting-IP veya
    # X-Real-IP gönderebileceği için bu başlıklara yalnızca açıkça TRUST_CLOUDFLARE_HEADERS=true
    # tanımlandığında güvenilir; varsayılan olarak sadece Railway Envoy'un X-Forwarded-For sonuna
    # eklediği (en sağdaki / rightmost) geçerli IP alınır.
    trust_cf = os.environ.get("TRUST_CLOUDFLARE_HEADERS", "").strip().lower() in ("1", "true", "yes")
    if trust_cf and request.headers.get("cf-ray"):
        cf_ip = _valid_ip(request.headers.get("cf-connecting-ip"))
        if cf_ip:
            return cf_ip

    xff_raw = request.headers.get("x-forwarded-for") or ""
    if xff_raw:
        for hop in reversed(xff_raw.split(",")):
            hop_ip = _valid_ip(hop)
            if hop_ip:
                return hop_ip

    return peer_valid or (peer_host if peer_host else "unknown")


def capture_bridge_click_context(request: Request) -> Dict[str, Optional[str]]:
    """
    HTTP yanıtı gönderilmeden önce Request nesnesinden tıklama meta verilerini <0.1ms içinde
    belleğe kopyalar; böylece veritabanı yazımı BackgroundTasks içinde güvenle çalışır.
    """
    ua_raw = request.headers.get("user-agent") or ""
    client_ip = extract_trusted_client_ip(request)
    trust_cf = os.environ.get("TRUST_CLOUDFLARE_HEADERS", "").strip().lower() in ("1", "true", "yes")

    country_raw = (
        (request.headers.get("cf-ipcountry") if (trust_cf and request.headers.get("cf-ray")) else None)
        or "TR"
    )
    q_params = request.query_params
    return {
        "user_agent": ua_raw,
        "client_ip": client_ip,
        "country_raw": country_raw,
        "fbclid": q_params.get("fbclid"),
        "utm_source": q_params.get("utm_source"),
        "utm_campaign": q_params.get("utm_campaign"),
        "referrer": request.headers.get("referer"),
    }


def record_bridge_click(
    request_or_ctx: Any,
    route_path: str,
    target_store: str,
    db_override: Optional[Session] = None,
) -> None:
    """
    Köprü tıklamasını hata korumalı, TOCTOU kilidiyle atomik ve sıfır şema-tarama blokajıyla kaydeder.
    Hem doğrudan Request nesnesini hem de capture_bridge_click_context() sözlüğünü kabul eder.
    """
    global _BRIDGE_TABLE_READY
    ctx = (
        request_or_ctx
        if isinstance(request_or_ctx, dict)
        else capture_bridge_click_context(request_or_ctx)
    )
    owns_session = db_override is None
    with _BRIDGE_CLICK_LOCK:
        db = db_override if db_override is not None else SessionLocal()
        try:
            if not _BRIDGE_TABLE_READY or os.environ.get("PYTEST_CURRENT_TEST"):
                try:
                    BridgeClick.__table__.create(bind=db.get_bind(), checkfirst=True)
                    if owns_session and not os.environ.get("PYTEST_CURRENT_TEST"):
                        _BRIDGE_TABLE_READY = True
                except Exception:
                    pass

            ua_raw = ctx.get("user_agent") or ""
            ua_info = classify_user_agent(ua_raw)
            client_ip = ctx.get("client_ip") or "unknown"
            ip_masked = mask_ip(client_ip, ua_raw)

            country_raw = ctx.get("country_raw") or "TR"
            country_clean = "".join(ch for ch in country_raw.upper() if ch.isalnum())[:6] or "TR"

            fbclid = ctx.get("fbclid")
            utm_source = ctx.get("utm_source")
            utm_campaign = ctx.get("utm_campaign")
            referrer = ctx.get("referrer")
            has_fbclid = bool(fbclid)

            channel = classify_channel(route_path, utm_source, has_fbclid)

            # Çoklu worker/replica ortamında (PostgreSQL) 15sn tekilleştirmenin atomik kalması için advisory lock
            try:
                bind_dialect = getattr(getattr(db.get_bind(), "dialect", None), "name", "")
                if bind_dialect == "postgresql":
                    adv_key = int.from_bytes(
                        hashlib.sha256(f"bridge:{route_path}:{ip_masked}".encode("utf-8")).digest()[:8],
                        "big",
                    ) & 0x7FFFFFFFFFFFFFFF
                    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": adv_key})
            except Exception as lock_exc:
                logger.warning("Advisory lock fallback (bridge): %s", lock_exc)
                try:
                    db.rollback()
                except Exception:
                    pass

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
            invalidate_analytics_summary_cache()
        except Exception as e:
            db.rollback()
            logger.error(f"Bridge click log error (ignored): {e}")
        finally:
            if owns_session:
                db.close()


@router.post("/usage-signal")
@router.post("/app-open-signal")
def record_app_open_signal(
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

    client_ip = extract_trusted_client_ip(request)
    ip_masked = mask_ip(client_ip, ua_raw)
    base_ip = extract_base_ip(ip_masked)

    trust_cf = os.environ.get("TRUST_CLOUDFLARE_HEADERS", "").strip().lower() in ("1", "true", "yes")
    country_raw = (
        (request.headers.get("cf-ipcountry") if (trust_cf and request.headers.get("cf-ray")) else None)
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

    clean_uid = "".join(ch for ch in (payload.device_uid or "").strip().lower() if ch.isalnum() or ch in ("-", "_"))[:100] or "anon"
    clean_event = "".join(ch for ch in payload.event_type if ch.isalnum() or ch == "_")[:40] or "first_open"

    # first_open/daily_active için eşzamanlı isteklerde çift kayıt oluşmasını (TOCTOU) önlemek
    # amacıyla "mevcut kaydı kontrol et + yoksa oluştur" işlemi tek bir kilit altında yapılır.
    needs_dedup_lock = clean_event in ("first_open", "daily_active")
    if needs_dedup_lock:
        _APP_OPEN_SIGNAL_LOCK.acquire()
    try:
        if needs_dedup_lock:
            try:
                bind_dialect = getattr(getattr(db.get_bind(), "dialect", None), "name", "")
                if bind_dialect == "postgresql":
                    sig_adv_key = int.from_bytes(
                        hashlib.sha256(f"sig:{clean_event}:{clean_uid}".encode("utf-8")).digest()[:8],
                        "big",
                    ) & 0x7FFFFFFFFFFFFFFF
                    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": sig_adv_key})
            except Exception as sig_lock_exc:
                logger.warning("Advisory lock fallback (signal): %s", sig_lock_exc)
                try:
                    db.rollback()
                except Exception:
                    pass

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

        # Modern iPadOS Safari HTTP katmanında "Macintosh" UA gönderdiği için BridgeClick "desktop"
        # olarak kaydedilebilir; istemci JS (isTouchMac) veya iPad native uygulaması ise os_family="ios"
        # gönderir. Önce tam os_family=="ios" adayları değerlendirilir; yalnızca gerçek ios adayı yoksa
        # aynı IP'deki Macintosh UA'lı desktop adayı yedek olarak devreye girer (aynı NAT'taki Mac trafiği
        # gerçek iPhone tıklamasının önüne geçemez).
        from sqlalchemy import or_, and_, case
        os_filter_expr = (
            or_(
                BridgeClick.os_family == "ios",
                and_(
                    BridgeClick.os_family == "desktop",
                    BridgeClick.user_agent.ilike("%Macintosh%"),
                ),
            )
            if os_family == "ios"
            else (BridgeClick.os_family == os_family)
        )
        os_priority_expr = case((BridgeClick.os_family == os_family, 0), else_=1)
        candidates: List[BridgeClick] = (
            db.query(BridgeClick)
            .filter(
                BridgeClick.is_bot.is_(False),
                os_filter_expr,
                BridgeClick.created_at >= cutoff_24h,
            )
            .order_by(os_priority_expr.asc(), desc(BridgeClick.created_at))
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

        exact_os_candidates = [c for c in candidates if c.os_family == os_family]
        if matched_click is None and exact_os_candidates:
            top_c = exact_os_candidates[0]
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
        invalidate_analytics_summary_cache()

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
def update_campaign_config(
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
    invalidate_analytics_summary_cache()

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


def _build_analytics_summary(
    db: Session,
    period: str = "all",
    use_cache: Optional[bool] = None,
) -> Dict[str, Any]:
    global _LEDGER_NEEDS_RECONCILE
    if period not in ALLOWED_PERIODS:
        raise ValueError(f"Unsupported period filter: {period}")

    is_pytest_env = bool(os.environ.get("PYTEST_CURRENT_TEST"))
    is_prod_live = (not is_pytest_env) and (db is not None and db.get_bind() is engine)
    cache_enabled = is_prod_live if use_cache is None else bool(use_cache)

    if cache_enabled and _SUMMARY_CACHE_TTL_SEC > 0:
        now_mono = time.monotonic()
        with _SUMMARY_CACHE_LOCK:
            cached_entry = _SUMMARY_CACHE.get(period)
            if cached_entry is not None and (now_mono - cached_entry[0]) <= _SUMMARY_CACHE_TTL_SEC:
                return _clone_summary_for_response(cached_entry[1])

    ensure_historical_seed(db)

    # Hafif sütun projeksiyonu: 100.000 satır için ağır user_agent/fbclid/referrer metinlerini ve tam ORM nesnelerini yükleme
    click_tuples = (
        db.query(
            BridgeClick.id,
            BridgeClick.created_at,
            BridgeClick.route_path,
            BridgeClick.os_family,
            BridgeClick.app_webview,
            BridgeClick.is_bot,
            BridgeClick.is_unique,
        )
        .order_by(desc(BridgeClick.created_at))
        .limit(100000)
        .all()
    )
    all_clicks: List[_ClickSlim] = [_ClickSlim(*row) for row in click_tuples]

    sig_tuples = (
        db.query(
            AppInstallSignal.event_type,
            AppInstallSignal.os_family,
            AppInstallSignal.device_uid,
            AppInstallSignal.country,
            AppInstallSignal.matched_channel,
            AppInstallSignal.match_confidence,
            AppInstallSignal.created_at,
            AppInstallSignal.app_version,
        )
        .order_by(desc(AppInstallSignal.created_at))
        .limit(100000)
        .all()
    )
    signals: List[_SignalSlim] = [_SignalSlim(*row) for row in sig_tuples]

    # 8 ayrı DB ağ gidiş-dönüşü (8 x RTT) yerine TEK birleşik SQL alt sorgusu
    counts_row = db.execute(
        select(
            select(func.count(User.id)).scalar_subquery(),
            select(func.count(Baby.id)).scalar_subquery(),
            select(func.count(CryEvent.id)).scalar_subquery(),
            select(func.count(SleepLog.id)).scalar_subquery(),
            select(func.count(RoutineLog.id)).scalar_subquery(),
            select(func.count(DadiChatHistory.id)).scalar_subquery(),
            select(func.count(Subscription.id)).scalar_subquery(),
            select(func.count(Feedback.id)).scalar_subquery(),
        )
    ).one()
    (
        db_users_count,
        db_babies_count,
        db_cry_count,
        db_sleep_count,
        db_routine_count,
        db_dadi_count,
        db_subs_count,
        db_feedbacks_total_cnt,
    ) = [int(v or 0) for v in counts_row]
    db_feedbacks_cnt_capped = min(100, db_feedbacks_total_cnt)
    fb_rows = db.query(Feedback).order_by(desc(Feedback.created_at)).limit(50).all()
    db_feedbacks = [
        SimpleNamespace(
            id=fb.id,
            message=fb.message,
            sentiment=fb.sentiment,
            baby_age_months=fb.baby_age_months,
            contact_info=fb.contact_info,
            platform=fb.platform,
            app_version=fb.app_version,
            created_at=fb.created_at,
        )
        for fb in fb_rows
    ]

    tz_tr = timezone(timedelta(hours=3))
    now_tr = datetime.now(tz_tr)
    now_utc = datetime.now(timezone.utc)
    feedbacks_last_24h_cnt = 0
    for fb_item in db_feedbacks:
        fb_dt = fb_item.created_at
        if fb_dt:
            fb_dt_utc = fb_dt.replace(tzinfo=timezone.utc) if fb_dt.tzinfo is None else fb_dt
            if (now_utc - fb_dt_utc).total_seconds() <= 86400:
                feedbacks_last_24h_cnt += 1
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
    if period == "today":
        active_signals_set = [s for s in signals if s.created_at and to_tr_date(s.created_at) == today_str]
    elif period == "yesterday":
        active_signals_set = [s for s in signals if s.created_at and to_tr_date(s.created_at) == yesterday_str]
    elif period == "7d":
        active_signals_set = [s for s in signals if s.created_at and cutoff_7d_date <= to_tr_date(s.created_at) <= today_str]
    else:
        active_signals_set = signals

    first_opens = [s for s in active_signals_set if s.event_type == "first_open"]
    daily_actives = [s for s in active_signals_set if s.event_type == "daily_active"]
    store_jumps = [s for s in active_signals_set if s.event_type == "store_jump"]
    store_button_clicks = [s for s in active_signals_set if s.event_type == "store_button_click"]
    baby_created_signals = [s for s in active_signals_set if s.event_type == "baby_created"]
    vip_started_signals = [s for s in active_signals_set if s.event_type == "vip_started"]
    sleep_sound_signals = [s for s in active_signals_set if s.event_type == "sleep_sound_play"]
    cry_analysis_signals = [s for s in active_signals_set if s.event_type == "cry_analysis"]
    routine_logged_signals = [s for s in active_signals_set if s.event_type == "routine_logged"]
    dadi_chat_signals = [s for s in active_signals_set if s.event_type == "dadi_chat"]
    paywall_viewed_signals = [s for s in active_signals_set if s.event_type == "paywall_viewed"]
    paywall_cta_clicked_signals = [s for s in active_signals_set if s.event_type == "paywall_cta_clicked"]
    paywall_skipped_signals = [s for s in active_signals_set if s.event_type == "paywall_skipped"]
    purchase_cancelled_signals = [s for s in active_signals_set if s.event_type == "purchase_cancelled"]
    purchase_error_signals = [s for s in active_signals_set if s.event_type == "purchase_error"]
    sound_preview_60s_ended_signals = [s for s in active_signals_set if s.event_type == "sound_preview_60s_ended"]
    cry_limit_reached_signals = [s for s in active_signals_set if s.event_type == "cry_limit_reached"]
    dadi_limit_reached_signals = [s for s in active_signals_set if s.event_type == "dadi_limit_reached"]
    routine_limit_reached_signals = [s for s in active_signals_set if s.event_type == "routine_limit_reached"]
    paywall_cancel_recovery_signals = [s for s in active_signals_set if s.event_type == "paywall_cancel_recovery_shown"]
    paywall_cancel_recovery_cta_signals = [s for s in active_signals_set if s.event_type == "paywall_cancel_recovery_cta_clicked"]
    paywall_cancel_reason_signals = [s for s in active_signals_set if (s.event_type or "").startswith("paywall_cancel_reason_")]
    paywall_cancel_reasons_breakdown = {
        "price": len([s for s in paywall_cancel_reason_signals if s.event_type == "paywall_cancel_reason_price"]),
        "cancel_fear": len([s for s in paywall_cancel_reason_signals if s.event_type == "paywall_cancel_reason_cancel_fear"]),
        "partner": len([s for s in paywall_cancel_reason_signals if s.event_type == "paywall_cancel_reason_partner"]),
        "card": len([s for s in paywall_cancel_reason_signals if s.event_type == "paywall_cancel_reason_card"]),
    }
    def _count_distinct_signal_devices(sig_list: List[Any]) -> int:
        if not sig_list:
            return 0
        keys = set()
        for idx_s, s_item in enumerate(sig_list):
            raw_u = (getattr(s_item, "device_uid", None) or "").strip().lower()
            if not raw_u or raw_u in ("anon", "msl_anon", "unknown", "none", "null"):
                keys.add(f"__anon_{idx_s}")
            else:
                keys.add(raw_u)
        return len(keys)

    paywall_cta_unique_devs = _count_distinct_signal_devices(paywall_cta_clicked_signals)
    purchase_cancelled_unique_devs = _count_distinct_signal_devices(purchase_cancelled_signals)

    ONBOARDING_9_STEPS_META = [
        (0, "onboarding_step_viewed_0", "Adım 0: Karşılama Ekranı", "1 Dakikada Uyku Planımı Oluştur"),
        (1, "onboarding_step_viewed_1", "Adım 1: Bebek Profili", "Bebek Adı & Doğum Tarihi"),
        (2, "onboarding_step_viewed_2", "Adım 2: Uyku Zorluğu", "Uykuda En Büyük Zorluk Seçimi"),
        (3, "onboarding_step_viewed_3", "Adım 3: Gelişim Atakları", "BabySteps™ Atak Kontrol Listesi"),
        (4, "onboarding_step_viewed_4", "Adım 4: Aşı Takvimi", "Pediatrik Aşı Kontrol Listesi"),
        (5, "onboarding_step_viewed_5", "Adım 5: Beslenme Rutini", "Anne Sütü / Mama / Ek Gıda"),
        (6, "onboarding_step_viewed_6", "Adım 6: Bakım & Konfor", "Son Bez Değişimi Saati"),
        (7, "onboarding_step_viewed_7", "Adım 7: Son Uyku & MışılSpot™", "MışılSpot™ Kalibrasyonu & Hızlı Çipler"),
        (8, "onboarding_step_viewed_8", "Adım 8: Kişisel Uyku Raporu", "İlk MışılSpot™ & Dönüşüm Hedefi"),
        (9, "onboarding_step_viewed_9", "Adım 9: VIP Paywall", "A/B İlk Ay %67 İndirim (₺49,99) / İlk Ay Ücretsiz (₺0)"),
    ]

    def _normalize_onb_device_uid(raw_val: Any) -> str:
        raw_s = str(raw_val or "").strip().lower()
        if not raw_s or raw_s in ("anon", "msl_anon", "unknown", "none", "null"):
            return ""
        return raw_s

    device_ab_cohort_map: Dict[str, str] = {}
    for sig_it in signals:
        d_key = _normalize_onb_device_uid(getattr(sig_it, "device_uid", None))
        if not d_key:
            continue
        ev_t = str(getattr(sig_it, "event_type", "") or "")
        if ev_t.startswith("ab_a_"):
            device_ab_cohort_map[d_key] = "group_a"
        elif ev_t.startswith("ab_b_"):
            device_ab_cohort_map[d_key] = "group_b"
    try:
        sl_dev_rows = db.query(
            SubscriberLedger.device_uid,
            SubscriberLedger.offer_type,
            SubscriberLedger.product_id,
            SubscriberLedger.offer_code_name,
            SubscriberLedger.customer_price_try,
            SubscriberLedger.country,
        ).filter(SubscriberLedger.device_uid.isnot(None)).all()
        for sl_duid, sl_otype, sl_pid, sl_ocode, sl_cprice, sl_cc in sl_dev_rows:
            d_key = _normalize_onb_device_uid(sl_duid)
            if not d_key:
                continue
            is_1m_f = (sl_otype == "free_trial_1m" or "trial" in str(sl_pid or "").lower())
            if sl_otype == "intro_1m_discounted" or (
                not _is_annual_product(sl_pid)
                and 0.0 < float(sl_cprice or 0.0) < 100.0
                and str(sl_cc or "TR").upper() == "TR"
            ):
                device_ab_cohort_map[d_key] = "group_a"
            elif is_1m_f or "ilk ay ücretsiz" in str(sl_ocode or "").lower():
                device_ab_cohort_map[d_key] = "group_b"
    except Exception:
        pass

    def _sig_matches_ab_cohort(sig_obj: Any, ab_cohort: str) -> bool:
        if ab_cohort == "all":
            return True
        d_key = _normalize_onb_device_uid(getattr(sig_obj, "device_uid", None))
        if d_key and device_ab_cohort_map.get(d_key) == ab_cohort:
            return True
        ev_t = str(getattr(sig_obj, "event_type", "") or "")
        if ab_cohort == "group_a" and ev_t.startswith("ab_a_"):
            return True
        if ab_cohort == "group_b" and ev_t.startswith("ab_b_"):
            return True
        return False

    def _build_onboarding_step_funnel(plat_filter: str = "all", ab_cohort: str = "all", include_sub_cohorts: bool = True) -> Dict[str, Any]:
        if plat_filter == "ios":
            plat_sigs_base = [s for s in active_signals_set if (s.os_family or "").lower() == "ios"]
        elif plat_filter == "android":
            plat_sigs_base = [s for s in active_signals_set if (s.os_family or "").lower() == "android"]
        else:
            plat_sigs_base = active_signals_set

        plat_sigs = [s for s in plat_sigs_base if _sig_matches_ab_cohort(s, ab_cohort)]
        all_ab_matched_sigs = [s for s in active_signals_set if _sig_matches_ab_cohort(s, ab_cohort)]

        steps_out: List[Dict[str, Any]] = []
        for st_num, ev_key, st_title, st_desc in ONBOARDING_9_STEPS_META:
            ev_sigs = [s for s in plat_sigs if s.event_type == ev_key]
            ios_ev_sigs = [s for s in all_ab_matched_sigs if s.event_type == ev_key and (s.os_family or "").lower() == "ios"]
            and_ev_sigs = [s for s in all_ab_matched_sigs if s.event_type == ev_key and (s.os_family or "").lower() == "android"]
            ga_ev_sigs = [s for s in plat_sigs_base if s.event_type == ev_key and _sig_matches_ab_cohort(s, "group_a")]
            gb_ev_sigs = [s for s in plat_sigs_base if s.event_type == ev_key and _sig_matches_ab_cohort(s, "group_b")]
            steps_out.append({
                "step_number": st_num,
                "event_type": ev_key,
                "title": st_title,
                "subtitle": st_desc,
                "unique_devices": _count_distinct_signal_devices(ev_sigs),
                "raw_events": len(ev_sigs),
                "ios_unique_devices": _count_distinct_signal_devices(ios_ev_sigs),
                "android_unique_devices": _count_distinct_signal_devices(and_ev_sigs),
                "group_a_unique_devices": _count_distinct_signal_devices(ga_ev_sigs) if ab_cohort in ("all", "group_a") else 0,
                "group_b_unique_devices": _count_distinct_signal_devices(gb_ev_sigs) if ab_cohort in ("all", "group_b") else 0,
                "retention_from_prev_pct": None,
                "dropoff_from_prev_count": 0,
                "dropoff_from_prev_pct": None,
                "cumulative_from_start_pct": None,
            })

        start_base = steps_out[0]["unique_devices"]
        if start_base == 0 and len(steps_out) > 1:
            start_base = steps_out[1]["unique_devices"]

        biggest_dropoff_step: Optional[Dict[str, Any]] = None
        for idx_st, st_row in enumerate(steps_out):
            cur_u = st_row["unique_devices"]
            if start_base > 0:
                st_row["cumulative_from_start_pct"] = min(100.0, round((cur_u / start_base) * 100.0, 1))
            if idx_st == 0:
                st_row["retention_from_prev_pct"] = 100.0 if cur_u > 0 else None
                st_row["dropoff_from_prev_count"] = 0
                st_row["dropoff_from_prev_pct"] = 0.0 if cur_u > 0 else None
            else:
                prev_u = steps_out[idx_st - 1]["unique_devices"]
                if prev_u > 0:
                    ret_pct = min(100.0, round((cur_u / prev_u) * 100.0, 1))
                    drop_cnt = max(0, prev_u - cur_u)
                    drop_pct = max(0.0, round(((prev_u - cur_u) / prev_u) * 100.0, 1))
                    st_row["retention_from_prev_pct"] = ret_pct
                    st_row["dropoff_from_prev_count"] = drop_cnt
                    st_row["dropoff_from_prev_pct"] = drop_pct
                    if drop_cnt > 0 and (
                        biggest_dropoff_step is None or drop_cnt > biggest_dropoff_step["dropoff_count"]
                    ):
                        biggest_dropoff_step = {
                            "step_number": st_row["step_number"],
                            "title": st_row["title"],
                            "dropoff_count": drop_cnt,
                            "dropoff_pct": drop_pct,
                        }

        all_onb_sigs = [s for s in plat_sigs if (s.event_type or "").startswith("onboarding_step_viewed_")]
        total_onb_unique_devs = _count_distinct_signal_devices(all_onb_sigs)
        fo_uniq = _count_distinct_signal_devices([s for s in plat_sigs if s.event_type == "first_open"])
        pw_view_uniq = _count_distinct_signal_devices([s for s in plat_sigs if s.event_type == "paywall_viewed"])
        pw_cta_uniq = _count_distinct_signal_devices([s for s in plat_sigs if s.event_type == "paywall_cta_clicked"])
        vip_start_uniq = _count_distinct_signal_devices([s for s in plat_sigs if s.event_type == "vip_started"])
        step7_chip_sigs = [s for s in plat_sigs if s.event_type == "onb_step7_quick_chip_used"]
        step7_chip_uniq = _count_distinct_signal_devices(step7_chip_sigs)
        ab_a_pw_uniq = _count_distinct_signal_devices([s for s in plat_sigs if s.event_type == "ab_a_paywall_viewed"])
        ab_b_pw_uniq = _count_distinct_signal_devices([s for s in plat_sigs if s.event_type == "ab_b_paywall_viewed"])
        ab_a_cta_uniq = _count_distinct_signal_devices([s for s in plat_sigs if s.event_type == "ab_a_paywall_cta"])
        ab_b_cta_uniq = _count_distinct_signal_devices([s for s in plat_sigs if s.event_type == "ab_b_paywall_cta"])
        ab_a_cancel_uniq = _count_distinct_signal_devices([s for s in plat_sigs if s.event_type == "ab_a_purchase_cancelled"])
        ab_b_cancel_uniq = _count_distinct_signal_devices([s for s in plat_sigs if s.event_type == "ab_b_purchase_cancelled"])
        ab_a_vip_uniq = _count_distinct_signal_devices([s for s in plat_sigs if s.event_type == "ab_a_vip_started"])
        ab_b_vip_uniq = _count_distinct_signal_devices([s for s in plat_sigs if s.event_type == "ab_b_vip_started"])
        step9_u = steps_out[9]["unique_devices"] if len(steps_out) > 9 else 0
        step0_to_step9_pct = (
            min(100.0, round((step9_u / start_base) * 100.0, 1))
            if start_base > 0
            else None
        )

        res_onb = {
            "platform": plat_filter,
            "ab_cohort": ab_cohort,
            "period": period,
            "period_label": period_label,
            "has_telemetry_data": total_onb_unique_devs > 0,
            "total_tracked_onboarding_devices": total_onb_unique_devs,
            "total_raw_onboarding_signals": len(all_onb_sigs),
            "start_base_devices": start_base,
            "step9_reached_devices": step9_u,
            "step0_to_step9_completion_pct": step0_to_step9_pct,
            "biggest_dropoff_step": biggest_dropoff_step,
            "first_open_unique_devices": fo_uniq,
            "paywall_viewed_unique_devices": pw_view_uniq,
            "paywall_cta_unique_devices": pw_cta_uniq,
            "vip_started_unique_devices": vip_start_uniq,
            "step7_quick_chip_unique_devices": step7_chip_uniq,
            "step7_quick_chip_raw_events": len(step7_chip_sigs),
            "ab_a_paywall_viewed_unique_devices": ab_a_pw_uniq,
            "ab_b_paywall_viewed_unique_devices": ab_b_pw_uniq,
            "ab_a_paywall_cta_unique_devices": ab_a_cta_uniq,
            "ab_b_paywall_cta_unique_devices": ab_b_cta_uniq,
            "ab_a_purchase_cancelled_unique_devices": ab_a_cancel_uniq,
            "ab_b_purchase_cancelled_unique_devices": ab_b_cancel_uniq,
            "ab_a_vip_started_unique_devices": ab_a_vip_uniq,
            "ab_b_vip_started_unique_devices": ab_b_vip_uniq,
            "steps": steps_out,
        }
        if include_sub_cohorts and ab_cohort == "all":
            res_onb["ab_cohorts"] = {
                "all": dict(res_onb),
                "group_a": _build_onboarding_step_funnel(plat_filter, "group_a", include_sub_cohorts=False),
                "group_b": _build_onboarding_step_funnel(plat_filter, "group_b", include_sub_cohorts=False),
            }
        return res_onb

    onboarding_step_funnel_all = _build_onboarding_step_funnel("all")
    onboarding_step_funnel_ios = _build_onboarding_step_funnel("ios")
    onboarding_step_funnel_android = _build_onboarding_step_funnel("android")
    onboarding_step_funnel_by_platform = {
        "all": onboarding_step_funnel_all,
        "ios": onboarding_step_funnel_ios,
        "android": onboarding_step_funnel_android,
    }

    unmatched_organic_opens = len([
        s for s in first_opens if (s.match_confidence or "unmatched") == "unmatched"
    ])
    distinct_signal_devices = len({
        (s.device_uid or "").strip().lower() for s in active_signals_set
        if s.device_uid and (s.device_uid or "").strip().lower() not in ("anon", "msl_anon", "unknown") and (
            s.event_type in (
                "first_open", "daily_active", "baby_created", "vip_started", "sleep_sound_play", "cry_analysis",
                "routine_logged", "dadi_chat",
                "paywall_viewed", "paywall_cta_clicked", "paywall_skipped", "purchase_cancelled", "purchase_error",
                "sound_preview_60s_ended", "cry_limit_reached", "dadi_limit_reached", "routine_limit_reached",
                "paywall_cancel_recovery_shown", "paywall_cancel_recovery_cta_clicked",
                "onb_step7_quick_chip_used",
            )
            or (s.event_type or "").startswith("paywall_cancel_reason_")
            or (s.event_type or "").startswith("onboarding_step_viewed_")
            or (s.event_type or "").startswith("ab_a_")
            or (s.event_type or "").startswith("ab_b_")
        )
    })

    if period != "all":
        if period == "today":
            p_start_tr = now_tr.replace(hour=0, minute=0, second=0, microsecond=0)
            p_end_tr = now_tr
        elif period == "yesterday":
            p_start_tr = (now_tr - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            p_end_tr = p_start_tr + timedelta(days=1) - timedelta(microseconds=1)
        else:
            p_start_tr = (now_tr - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
            p_end_tr = now_tr
        p_start_utc = p_start_tr.astimezone(timezone.utc).replace(tzinfo=None)
        p_end_utc = p_end_tr.astimezone(timezone.utc).replace(tzinfo=None)
        try:
            p_counts_row = db.execute(
                select(
                    select(func.count(User.id)).where(User.created_at >= p_start_utc, User.created_at <= p_end_utc).scalar_subquery(),
                    select(func.count(Baby.id)).where(Baby.created_at >= p_start_utc, Baby.created_at <= p_end_utc).scalar_subquery(),
                    select(func.count(CryEvent.id)).where(CryEvent.created_at >= p_start_utc, CryEvent.created_at <= p_end_utc).scalar_subquery(),
                    select(func.count(SleepLog.id)).where(SleepLog.created_at >= p_start_utc, SleepLog.created_at <= p_end_utc).scalar_subquery(),
                    select(func.count(RoutineLog.id)).where(RoutineLog.created_at >= p_start_utc, RoutineLog.created_at <= p_end_utc).scalar_subquery(),
                    select(func.count(DadiChatHistory.id)).where(DadiChatHistory.created_at >= p_start_utc, DadiChatHistory.created_at <= p_end_utc).scalar_subquery(),
                )
            ).one()
            (
                db_users_count,
                db_babies_count,
                db_cry_count,
                db_sleep_count,
                db_routine_count,
                db_dadi_count,
            ) = [int(v or 0) for v in p_counts_row]
        except Exception:
            pass

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
    db_ios_imp_uniq = 0
    db_ios_pv = 0
    db_ios_pv_uniq = 0
    db_ios_dl = 0
    db_ios_dl_search = 0
    db_ios_dl_ref = 0
    db_ios_dl_browse = 0
    db_ios_sess = 0
    db_android_imp = 0
    db_android_imp_uniq = 0
    db_android_pv = 0
    db_android_pv_uniq = 0
    db_android_dl = 0
    db_android_sess = 0
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
        row_imp = int(m_row.impressions or 0)
        row_imp_u = int(getattr(m_row, "impressions_unique", 0) or 0)
        row_pv = int(m_row.page_views or 0)
        row_pv_u = int(getattr(m_row, "page_views_unique", 0) or 0)
        if m_row.platform == "ios":
            daily_series_merged[d_k]["impressions"] = max(daily_series_merged[d_k]["impressions"], row_imp)
            daily_series_merged[d_k]["page_views"] = max(daily_series_merged[d_k]["page_views"], row_pv)
            daily_series_merged[d_k]["ios_downloads"] = max(daily_series_merged[d_k]["ios_downloads"], row_dl)
            daily_series_merged[d_k]["sessions"] = max(daily_series_merged[d_k]["sessions"], row_sess)
            db_ios_imp += row_imp
            db_ios_imp_uniq += row_imp_u
            db_ios_pv += row_pv
            db_ios_pv_uniq += row_pv_u
            db_ios_dl += row_dl
            db_ios_dl_search += int(getattr(m_row, "downloads_search", 0) or 0)
            db_ios_dl_ref += int(getattr(m_row, "downloads_referrer", 0) or 0)
            db_ios_dl_browse += int(getattr(m_row, "downloads_browse", 0) or 0)
            db_ios_sess += row_sess
        elif m_row.platform == "android":
            daily_series_merged[d_k]["android_downloads"] = max(daily_series_merged[d_k]["android_downloads"], row_dl)
            if row_imp > 0:
                daily_series_merged[d_k]["impressions"] = daily_series_merged[d_k]["impressions"] + row_imp
            if row_pv > 0:
                daily_series_merged[d_k]["page_views"] = daily_series_merged[d_k]["page_views"] + row_pv
            if row_sess > 0:
                daily_series_merged[d_k]["sessions"] = daily_series_merged[d_k]["sessions"] + row_sess
            db_android_imp += row_imp
            db_android_imp_uniq += row_imp_u
            db_android_pv += row_pv
            db_android_pv_uniq += row_pv_u
            db_android_dl += row_dl
            db_android_sess += row_sess

    sb["daily_store_series"] = daily_series_merged

    # Apple TSV raporunun ulaştığı son kesinleşmiş günü tespit et (Dün / Son 7 Gün pencereleri için T-1 anchor)
    confirmed_store_dates_pre = [
        d_k for d_k, d_v in daily_series_merged.items()
        if int(d_v.get("ios_downloads", 0) or 0) > 0
    ]
    latest_confirmed_store_date_pre = max(confirmed_store_dates_pre) if confirmed_store_dates_pre else ""
    apple_anchor_pre_str = latest_confirmed_store_date_pre or str(sb.get("apple_latest_report_date") or "") or yesterday_str
    try:
        apple_anchor_pre_dt = datetime.strptime(apple_anchor_pre_str, "%Y-%m-%d").date()
    except Exception:
        apple_anchor_pre_dt = (now_tr - timedelta(days=1)).date()
        apple_anchor_pre_str = apple_anchor_pre_dt.strftime("%Y-%m-%d")
    apple_7d_start_pre_str = (apple_anchor_pre_dt - timedelta(days=6)).strftime("%Y-%m-%d")

    def _in_store_metric_period(dt_k: str, plat_val: str) -> bool:
        if period == "all":
            return True
        if not dt_k or len(dt_k) < 10:
            return False
        d_c = dt_k[:10]
        is_ios_p = (plat_val or "ios").lower() != "android"
        if period == "today":
            return d_c == today_str
        if period == "yesterday":
            return (d_c == apple_anchor_pre_str) if is_ios_p else (d_c == yesterday_str)
        if period == "7d":
            s_b = apple_7d_start_pre_str if is_ios_p else cutoff_7d_date
            return s_b <= d_c <= today_str
        return True

    if period != "all":
        db_ios_imp = 0
        db_ios_imp_uniq = 0
        db_ios_pv = 0
        db_ios_pv_uniq = 0
        db_ios_dl = 0
        db_ios_dl_search = 0
        db_ios_dl_ref = 0
        db_ios_dl_browse = 0
        db_ios_sess = 0
        db_android_imp = 0
        db_android_imp_uniq = 0
        db_android_pv = 0
        db_android_pv_uniq = 0
        db_android_dl = 0
        db_android_sess = 0
        seen_ios_days = set()
        seen_and_days = set()
        for m_row in daily_db_rows:
            d_k = m_row.metric_date
            row_dl = int(getattr(m_row, "downloads_total", None) or getattr(m_row, "first_time_downloads", 0) or 0)
            row_sess = int(getattr(m_row, "active_sessions", 0) or 0)
            row_imp = int(m_row.impressions or 0)
            row_imp_u = int(getattr(m_row, "impressions_unique", 0) or 0)
            row_pv = int(m_row.page_views or 0)
            row_pv_u = int(getattr(m_row, "page_views_unique", 0) or 0)
            if m_row.platform == "ios" and _in_store_metric_period(d_k, "ios"):
                seen_ios_days.add(d_k)
                db_ios_imp += row_imp
                db_ios_imp_uniq += row_imp_u
                db_ios_pv += row_pv
                db_ios_pv_uniq += row_pv_u
                db_ios_dl += row_dl
                db_ios_dl_search += int(getattr(m_row, "downloads_search", 0) or 0)
                db_ios_dl_ref += int(getattr(m_row, "downloads_referrer", 0) or 0)
                db_ios_dl_browse += int(getattr(m_row, "downloads_browse", 0) or 0)
                db_ios_sess += row_sess
            elif m_row.platform == "android" and _in_store_metric_period(d_k, "android"):
                seen_and_days.add(d_k)
                db_android_imp += row_imp
                db_android_imp_uniq += row_imp_u
                db_android_pv += row_pv
                db_android_pv_uniq += row_pv_u
                db_android_dl += row_dl
                db_android_sess += row_sess
        for d_k, d_v in daily_series_merged.items():
            if d_k not in seen_ios_days and _in_store_metric_period(d_k, "ios"):
                db_ios_imp += int(d_v.get("impressions", 0) or 0)
                db_ios_pv += int(d_v.get("page_views", 0) or 0)
                db_ios_dl += int(d_v.get("ios_downloads", 0) or 0)
                db_ios_sess += int(d_v.get("sessions", 0) or 0)
            if d_k not in seen_and_days and _in_store_metric_period(d_k, "android"):
                db_android_dl += int(d_v.get("android_downloads", 0) or 0)

    # SSOT Kuralı: StoreDailyMetric (DB) birincil otoritedir; yalnızca tablo boşsa (ve period == 'all' ise) son resmi snapshot (sb) kullanılır.
    # Canlı istemci telemetrisi (first_open) resmi mağaza indirme sayısını max() ile şişirmez; yalnızca resmi veri 0 ise yedek olur.
    if period == "all":
        apple_impressions = db_ios_imp if db_ios_imp > 0 else int(sb.get("apple_impressions_total", 0) or 0)
        apple_page_views = db_ios_pv if db_ios_pv > 0 else int(sb.get("apple_page_views_total", 0) or 0)
        apple_taps = int(sb.get("apple_taps_total", 0) or 0)
        ios_signal_opens = len([s for s in first_opens if s.os_family == "ios"])
        android_signal_opens = len([s for s in first_opens if s.os_family == "android"])
        official_ios_dl = db_ios_dl if db_ios_dl > 0 else int(sb.get("apple_downloads_total", 0) or 0)
        apple_downloads = official_ios_dl if official_ios_dl > 0 else ios_signal_opens
        apple_official_sessions = db_ios_sess if db_ios_sess > 0 else int(sb.get("apple_sessions_total", 0) or 0)
        android_official_sessions = db_android_sess if db_android_sess > 0 else int(sb.get("google_play_sessions_total", 0) or 0)
        live_telemetry_sessions = len(first_opens) + len(daily_actives)
        apple_sessions = (apple_official_sessions + android_official_sessions) if (apple_official_sessions + android_official_sessions) > 0 else live_telemetry_sessions
        official_android_dl = db_android_dl if db_android_dl > 0 else int(sb.get("google_play_downloads_baseline", 0) or 0)
        google_play_downloads = max(official_android_dl, android_signal_opens)
        google_play_impressions_base = db_android_imp if db_android_imp > 0 else int(sb.get("google_play_impressions_total", 0) or 0)
        google_play_page_views_base = db_android_pv if db_android_pv > 0 else int(sb.get("google_play_page_views_total", 0) or 0)
    else:
        apple_impressions = db_ios_imp
        apple_page_views = db_ios_pv
        apple_taps = db_ios_pv
        ios_signal_opens = len([s for s in first_opens if s.os_family == "ios"])
        android_signal_opens = len([s for s in first_opens if s.os_family == "android"])
        apple_downloads = db_ios_dl if db_ios_dl > 0 else ios_signal_opens
        apple_official_sessions = db_ios_sess
        android_official_sessions = db_android_sess
        live_telemetry_sessions = len(first_opens) + len(daily_actives)
        apple_sessions = max(apple_official_sessions + android_official_sessions, live_telemetry_sessions)
        google_play_downloads = max(db_android_dl, android_signal_opens)
        google_play_impressions_base = db_android_imp
        google_play_page_views_base = db_android_pv

    sb["apple_impressions_total"] = apple_impressions
    sb["apple_page_views_total"] = apple_page_views
    sb["apple_downloads_total"] = apple_downloads
    sb["apple_sessions_total"] = apple_official_sessions
    sb["google_play_downloads_baseline"] = google_play_downloads
    sb["google_play_impressions_total"] = google_play_impressions_base
    sb["google_play_page_views_total"] = google_play_page_views_base

    total_cumulative_impressions = apple_impressions + google_play_impressions_base
    total_cumulative_store_page_views = apple_page_views + google_play_page_views_base
    total_cumulative_visits_and_clicks = total_cumulative_store_page_views + len(unique_human)
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

    if period == "today":
        start_dt = now_tr.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "yesterday":
        try:
            y_anchor_dt = datetime.strptime(apple_anchor_pre_str, "%Y-%m-%d").replace(tzinfo=tz_tr)
            start_dt = min(y_anchor_dt, (now_tr - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0))
        except Exception:
            start_dt = (now_tr - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "7d":
        try:
            s7_anchor_dt = datetime.strptime(apple_7d_start_pre_str, "%Y-%m-%d").replace(tzinfo=tz_tr)
            start_dt = min(s7_anchor_dt, (now_tr - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0))
        except Exception:
            start_dt = (now_tr - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)

    end_dt = now_tr
    num_days = max(1, (end_dt.date() - start_dt.date()).days + 1)
    start_date_str = start_dt.strftime("%Y-%m-%d")

    pre_start_clicks = sum(cnt for dt_k, cnt in clicks_by_date.items() if dt_k < start_date_str)

    # Apple TSV raporunun ulaştığı son kesinleşmiş günü ve r14 Analytics (gösterim) raporunun ulaştığı günü ayrı ayrı tespit et
    confirmed_store_dates = [
        d_k for d_k, d_v in daily_series_merged.items()
        if int(d_v.get("ios_downloads", 0) or 0) > 0
    ]
    latest_confirmed_store_date = max(confirmed_store_dates) if confirmed_store_dates else ""

    confirmed_r14_dates = [
        d_k for d_k, d_v in daily_series_merged.items()
        if int(d_v.get("impressions", 0) or 0) > 0 or int(d_v.get("page_views", 0) or 0) > 0
    ]
    latest_confirmed_r14_date = max(confirmed_r14_dates) if confirmed_r14_dates else latest_confirmed_store_date

    # Günlük Android kurulumları yalnızca o güne ait StoreDailyMetric veya o günün gerçek first_open sinyalinden okunur (sentetik modulo dağıtımı yapılmaz)
    explicit_and_by_day: Dict[str, int] = {}
    for i in range(num_days):
        d_str = (start_dt + timedelta(days=i)).strftime("%Y-%m-%d")
        st_and = int(daily_series_merged.get(d_str, {}).get("android_downloads", 0) or 0)
        sig_and = int(android_opens_by_date.get(d_str, 0) or 0)
        explicit_and_by_day[d_str] = st_and if st_and > 0 else sig_and

    rem_android = max(0, google_play_downloads - sum(explicit_and_by_day.values()))
    if rem_android > 0:
        anchor_and_day = start_dt.strftime("%Y-%m-%d")
        explicit_and_by_day[anchor_and_day] = explicit_and_by_day.get(anchor_and_day, 0) + rem_android

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
        is_r14_pending = bool(
            is_store_pending
            or (
                latest_confirmed_r14_date
                and d_str > latest_confirmed_r14_date
                and day_imp == 0
            )
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
            "is_r14_pending": is_r14_pending,
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
    global _LEDGER_RECONCILED_GEN
    with _SUMMARY_CACHE_LOCK:
        req_reconcile_gen = _LEDGER_RECONCILE_GEN
        done_reconcile_gen = _LEDGER_RECONCILED_GEN
    if (not is_prod_live) or (done_reconcile_gen < req_reconcile_gen):
        with _LEDGER_RECONCILE_LOCK:
            with _SUMMARY_CACHE_LOCK:
                target_reconcile_gen = _LEDGER_RECONCILE_GEN
                already_reconciled_gen = _LEDGER_RECONCILED_GEN
            if (not is_prod_live) or (already_reconciled_gen < target_reconcile_gen):
                try:
                    active_trials_target_val = int(sb.get("apple_vip_active_trials", 0) or 0)
                    if _reconcile_ios_ledger_and_cancellations(
                        db,
                        active_trials_target=active_trials_target_val if active_trials_target_val > 0 else None,
                    ):
                        db.commit()
                    if is_prod_live:
                        with _SUMMARY_CACHE_LOCK:
                            if _LEDGER_RECONCILED_GEN < target_reconcile_gen:
                                _LEDGER_RECONCILED_GEN = target_reconcile_gen
                except Exception:
                    try:
                        db.rollback()
                    except Exception:
                        pass

    try:
        ledger_rows_db: List[Any] = (
            db.query(SubscriberLedger)
            .order_by(SubscriberLedger.maturity_or_renewal_date.asc(), SubscriberLedger.started_date.asc())
            .all()
        )
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        legacy_sub_tuples = (
            db.query(
                SubscriberLedger.subscriber_id,
                SubscriberLedger.platform,
                SubscriberLedger.product_id,
                SubscriberLedger.plan_label,
                SubscriberLedger.status,
                SubscriberLedger.offer_type,
                SubscriberLedger.offer_code_name,
                SubscriberLedger.started_date,
                SubscriberLedger.converted_or_renewed_date,
                SubscriberLedger.maturity_or_renewal_date,
                SubscriberLedger.auto_renew_enabled,
                SubscriberLedger.customer_price_try,
                SubscriberLedger.developer_proceeds_try,
                SubscriberLedger.expected_next_price_try,
                SubscriberLedger.expected_next_proceeds_try,
                SubscriberLedger.country,
                SubscriberLedger.device_type,
            )
            .order_by(SubscriberLedger.maturity_or_renewal_date.asc(), SubscriberLedger.started_date.asc())
            .all()
        )
        ledger_rows_db = [
            SimpleNamespace(
                subscriber_id=t[0],
                platform=t[1],
                product_id=t[2],
                plan_label=t[3],
                status=t[4],
                offer_type=t[5],
                offer_code_name=t[6],
                started_date=t[7],
                converted_or_renewed_date=t[8],
                maturity_or_renewal_date=t[9],
                auto_renew_enabled=t[10],
                customer_price_try=t[11],
                developer_proceeds_try=t[12],
                expected_next_price_try=t[13],
                expected_next_proceeds_try=t[14],
                country=t[15],
                device_type=t[16],
            )
            for t in legacy_sub_tuples
        ]

    # Önce veritabanındaki ücretli abonelerden gerçek tek-dönemlik standart birim fiyat referansını çıkar
    # (Kümülatif 2+ aylık yenilemeler veya 49.99 TL ilk ay indirimli satırlar standart birim fiyatı ezmez;
    #  gerçek TSV / Google Play tahsilat oranından dinamik %15 Small Business / %30 standart oranı gözlemlenir).
    paid_ref_by_prod: Dict[str, tuple] = {}
    for r_ref in ledger_rows_db:
        if (r_ref.customer_price_try or 0.0) > 0 and r_ref.product_id:
            ref_plat = (r_ref.platform or "ios").lower()
            std_pair = _extract_single_period_standard_ref(
                r_ref.product_id,
                float(r_ref.customer_price_try or 0.0),
                float(r_ref.developer_proceeds_try or 0.0),
                float(r_ref.expected_next_price_try or 0.0),
                float(r_ref.expected_next_proceeds_try or 0.0),
                r_ref.offer_type,
                ref_plat,
            )
            if std_pair:
                paid_ref_by_prod[r_ref.product_id] = std_pair

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
    auto_renewing_paid_subs_cnt = 0
    non_renewing_paid_subs_cnt = 0
    offer_code_cnt = 0
    intro_trial_cnt = 0
    cancelled_cnt = 0
    healed_trial_pricing = False

    plat_fin: Dict[str, Dict[str, float]] = {
        "ios": {
            "realized_gross": 0.0, "realized_net": 0.0,
            "paid_mrr_gross": 0.0, "paid_mrr_net": 0.0,
            "pipeline_gross": 0.0, "pipeline_net": 0.0,
            "pipeline_mrr_gross": 0.0, "pipeline_mrr_net": 0.0,
            "paid_cnt": 0, "auto_renew_paid_cnt": 0, "non_renew_paid_cnt": 0,
            "trial_cnt": 0, "code_cnt": 0, "cancelled_cnt": 0,
        },
        "android": {
            "realized_gross": 0.0, "realized_net": 0.0,
            "paid_mrr_gross": 0.0, "paid_mrr_net": 0.0,
            "pipeline_gross": 0.0, "pipeline_net": 0.0,
            "pipeline_mrr_gross": 0.0, "pipeline_mrr_net": 0.0,
            "paid_cnt": 0, "auto_renew_paid_cnt": 0, "non_renew_paid_cnt": 0,
            "trial_cnt": 0, "code_cnt": 0, "cancelled_cnt": 0,
        },
    }

    renewal_by_date: Dict[str, Dict[str, Any]] = {}
    cohort_by_start_date: Dict[str, Dict[str, Any]] = {}

    for r in ledger_rows_db:
        r_plat = "android" if (r.platform or "ios").lower() == "android" else "ios"
        net_ratio = get_dynamic_proceeds_ratio(r_plat)
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
        # ve %15 komisyon programı (Apple Small Business %15 / Google Play %15) tabanının altında kalmış ileriye dönük
        # expected_next_proceeds_try değerlerini güncelle (geçmiş realized developer_proceeds_try asla değiştirilmez).
        ref_pair = paid_ref_by_prod.get(r.product_id or "misil_monthly", (0.0, 0.0))
        resolved_gross, resolved_net = _resolve_expected_trial_pricing(
            r.product_id, ref_pair[0], ref_pair[1], r_plat
        )
        if r.status == "intro_free_trial" and r.auto_renew_enabled:
            if (r.expected_next_price_try or 0.0) <= 0:
                r.expected_next_price_try = resolved_gross
                r.expected_next_proceeds_try = resolved_net
                healed_trial_pricing = True
            else:
                min_15_trial_net = round(float(r.expected_next_price_try) * net_ratio, 2)
                if (r.expected_next_proceeds_try or 0.0) < (min_15_trial_net - 1.0):
                    r.expected_next_proceeds_try = min_15_trial_net
                    healed_trial_pricing = True
        elif r.status in ("paid_active", "offer_code_trial") and r.auto_renew_enabled and r.offer_type != "intro_1m_discounted":
            if (r.expected_next_price_try or 0.0) > 0:
                min_15_next_net = round(float(r.expected_next_price_try) * net_ratio, 2)
                if (r.expected_next_proceeds_try or 0.0) < (min_15_next_net - 1.0):
                    r.expected_next_proceeds_try = min_15_next_net
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
            if r.auto_renew_enabled:
                auto_renewing_paid_subs_cnt += 1
                pf_bucket["auto_renew_paid_cnt"] += 1
            else:
                non_renewing_paid_subs_cnt += 1
                pf_bucket["non_renew_paid_cnt"] += 1
            lifecycle_stage = "paid_active"
            if r.offer_type == "intro_1m_discounted":
                lifecycle_badge = (
                    "🔥 Grup A • İlk Ay 49.99 ₺ Aktif"
                    if r.auto_renew_enabled
                    else "🔥 Grup A • İlk Ay 49.99 ₺ (Yenileme Kapalı)"
                )
            elif _is_annual_product(r.product_id):
                lifecycle_badge = "👑 Yıllık VIP Aktif" if r.auto_renew_enabled else "👑 Yıllık VIP (Yenileme Kapalı)"
            else:
                lifecycle_badge = "💳 Ücretli Aktif" if r.auto_renew_enabled else "💳 Ücretli Aktif (Yenileme Kapalı)"
            trial_progress_pct = 100
            if r.auto_renew_enabled:
                if r.offer_type == "intro_1m_discounted":
                    rec_gross = float(
                        r.expected_next_price_try
                        if (r.expected_next_price_try or 0.0) >= 100.0
                        else resolved_gross
                    )
                    rec_net = float(
                        r.expected_next_proceeds_try
                        if (r.expected_next_proceeds_try or 0.0) >= 50.0
                        else resolved_net
                    )
                else:
                    rec_gross = float(r.expected_next_price_try or resolved_gross or r.customer_price_try)
                    rec_net = float(r.expected_next_proceeds_try or resolved_net or r.developer_proceeds_try)
                    # Kümülatif (2+ ay) customer_price_try MRR hesabına sızmışsa tek dönemlik standart fiyata sınırla
                    if not _is_annual_product(r.product_id) and rec_gross > (resolved_gross * 1.35):
                        rec_gross = resolved_gross
                        rec_net = resolved_net
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
                    m_next_g = next_gross / 12.0
                    m_next_n = next_net / 12.0
                else:
                    m_next_g = next_gross
                    m_next_n = next_net
                pipeline_7d_monthly_mrr_gross += m_next_g
                pipeline_7d_monthly_mrr_net += m_next_n
                pf_bucket["pipeline_mrr_gross"] += m_next_g
                pf_bucket["pipeline_mrr_net"] += m_next_n
                m_dt = r.maturity_or_renewal_date or "-"

                # T4 Çözümü: Vade günü bugün veya geçmişteyse Apple 24-48s mutabakat penceresinde olarak ayır
                is_1m_free_trial = (r.offer_type == "free_trial_1m" or "trial" in str(r.product_id or "").lower())
                total_trial_days = 30 if is_1m_free_trial else 7
                is_reconciling = bool(m_dt != "-" and len(m_dt) == 10 and m_dt <= today_str)
                if is_reconciling:
                    reconciling_7d_cnt += 1
                    reconciling_7d_gross += next_gross
                    reconciling_7d_net += next_net
                    lifecycle_stage = "reconciling_trial"
                    lifecycle_badge = (
                        f"🔄 Apple Mutabakatında ({total_trial_days}/{total_trial_days} Gün)"
                        if r_plat == "ios"
                        else f"🔄 Google Play Mutabakatında ({total_trial_days}/{total_trial_days} Gün)"
                    )
                    trial_progress_pct = 100
                else:
                    upcoming_7d_cnt += 1
                    upcoming_7d_gross += next_gross
                    upcoming_7d_net += next_net
                    lifecycle_stage = "upcoming_trial"
                    elapsed_days = 0
                    try:
                        if r.started_date and len(r.started_date) == 10:
                            st_d = datetime.strptime(r.started_date, "%Y-%m-%d").date()
                            elapsed_days = max(0, min(total_trial_days - 1, (now_tr.date() - st_d).days))
                    except Exception:
                        elapsed_days = 0
                    trial_progress_pct = max(0, min(90, round((elapsed_days / float(total_trial_days)) * 100)))
                    lifecycle_badge = (
                        f"🎁 Grup B • İlk Ay Ücretsiz ({elapsed_days}/30 Gün)"
                        if is_1m_free_trial
                        else f"⏳ Tarihsel Deneme ({elapsed_days}/7 Gün)"
                    )

                if m_dt not in renewal_by_date:
                    renewal_by_date[m_dt] = {
                        "date": m_dt,
                        "count": 0,
                        "expected_gross_try": 0.0,
                        "expected_net_try": 0.0,
                        "is_reconciling": is_reconciling,
                        "status_label": "🔄 Tahsilat Mutabakatında" if is_reconciling else "⏳ Vadesi Gelecek Tahsilat",
                        "subscribers": [],
                        "_platforms": set(),
                    }
                renewal_by_date[m_dt]["count"] += 1
                renewal_by_date[m_dt]["expected_gross_try"] = round(
                    renewal_by_date[m_dt]["expected_gross_try"] + next_gross, 2
                )
                renewal_by_date[m_dt]["expected_net_try"] = round(
                    renewal_by_date[m_dt]["expected_net_try"] + next_net, 2
                )
                plat_tag = "🤖" if r_plat == "android" else "🍏"
                renewal_by_date[m_dt]["subscribers"].append(f"{plat_tag} #{r.subscriber_id[-6:]} ({r.country})")
                renewal_by_date[m_dt]["_platforms"].add(r_plat)

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
        if r.status != "cancelled" and (r.status == "paid_active" or r.auto_renew_enabled):
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

        is_1m_free_row = (r.offer_type == "free_trial_1m" or "trial" in str(r.product_id or "").lower())
        if r.offer_type == "intro_1m_discounted" or (
            not _is_annual_product(r.product_id)
            and 0.0 < float(r.customer_price_try or 0.0) < 100.0
            and str(r.country or "TR").upper() == "TR"
        ):
            ab_variant_grp = "group_a_paid_intro"
        elif is_1m_free_row or "ilk ay ücretsiz" in str(r.offer_code_name or "").lower():
            ab_variant_grp = "group_b_free_trial_1m"
        elif _is_annual_product(r.product_id) and r.status != "offer_code_trial" and r.offer_type != "offer_code":
            ab_variant_grp = "annual_anchor"
        elif r.status == "offer_code_trial" or r.offer_type == "offer_code":
            ab_variant_grp = "offer_code_vip"
        elif r.offer_type == "intro_7d_trial":
            ab_variant_grp = "legacy_7d_trial"
        else:
            ab_variant_grp = "standard_monthly"

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
            "ab_variant_group": ab_variant_grp,
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

    # P0-4: Dinamik 7 günlük kohort olgunlaşma kesimi (doğrudan 0. gün ücretli alımları deneme paydasından ayırır)
    matured_cutoff_str = (now_tr.date() - timedelta(days=7)).strftime("%Y-%m-%d")
    matured_7d_cohort = [
        r for r in ledger_rows_db
        if r.offer_type in ("standard_paid", "intro_7d_trial", "free_trial_1m")
        and r.started_date
        and r.started_date <= matured_cutoff_str
        and not (
            r.offer_type == "standard_paid"
            and r.converted_or_renewed_date
            and r.converted_or_renewed_date == r.started_date
            and "deneme" not in (r.offer_code_name or "").lower()
        )
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
    all_churn_rate_pct = (
        round((cancelled_cnt / len(ledger_rows_db)) * 100, 1)
        if len(ledger_rows_db) > 0
        else 0.0
    )

    active_vip_total = paid_subs_cnt + offer_code_cnt + intro_trial_cnt
    if len(ledger_rows_db) > 0:
        apple_vip = active_vip_total
    else:
        apple_vip = max(int(sb.get("apple_vip_activations_total", 0) or 0), db_subs_count, len(vip_started_signals))
    sb["apple_vip_activations_total"] = apple_vip
    if plat_fin["ios"]["realized_gross"] > 0:
        sb["apple_vip_paid_customer_price_try"] = round(plat_fin["ios"]["realized_gross"], 2)
        sb["apple_vip_paid_proceeds_try"] = round(plat_fin["ios"]["realized_net"], 2)
        sb["apple_vip_total_transactions"] = int(plat_fin["ios"]["paid_cnt"])

    # Apple App Store Connect 1 Günlük (T-1 PST) Rapor Gecikmesi ve Periyot Duyarlı Gelir Mutabakatı
    apple_anchor_str = latest_confirmed_store_date or str(sb.get("apple_latest_report_date") or "") or yesterday_str
    try:
        apple_anchor_dt = datetime.strptime(apple_anchor_str, "%Y-%m-%d").date()
    except Exception:
        apple_anchor_dt = (now_tr - timedelta(days=1)).date()
        apple_anchor_str = apple_anchor_dt.strftime("%Y-%m-%d")
    apple_lag_days = max(1, (now_tr.date() - apple_anchor_dt).days)
    apple_7d_start_str = (apple_anchor_dt - timedelta(days=6)).strftime("%Y-%m-%d")
    sb["apple_latest_report_date"] = apple_anchor_str
    sb["apple_report_lag_days"] = apple_lag_days

    def _in_period_window(dt_val: str, plat_val: str, target_period: str) -> bool:
        if not dt_val or len(dt_val) < 10:
            return target_period == "all"
        d_clean = dt_val[:10]
        is_ios_plat = (plat_val or "ios").lower() != "android"
        if target_period == "all":
            return True
        if target_period == "today":
            return d_clean == today_str
        if target_period == "yesterday":
            # Apple Connect'te "Yesterday (Dün)" son kesinleşen tekil rapor gününü (T-1: apple_anchor_str) ifade eder
            return (d_clean == apple_anchor_str) if is_ios_plat else (d_clean == yesterday_str)
        if target_period == "7d":
            # Apple Connect Trends "Last 7 Days" son kesinleşen rapor gününden geriye 7 günü [T-7..T-1] + T-0 canlı köprüyü kapsar
            start_b = apple_7d_start_str if is_ios_plat else cutoff_7d_date
            return start_b <= d_clean <= today_str
        return True

    def _resolve_single_window_tx_amount(lr_obj: Any, win_key: str, l_pl: str) -> tuple:
        """
        Tüm Zamanlar ('all') penceresinde abonenin kümülatif LTV tahsilatını döndürür.
        Dönemsel pencerelerde ('today', 'yesterday', '7d') ise abone 2. veya 3. kez yenilenmişse
        kümülatif toplamı (örn. 299.98 TL) tek güne çift saymak yerine o dönemin tekil tahsilat tutarını döndürür.
        """
        cum_g = float(lr_obj.customer_price_try or 0.0)
        cum_n = float(lr_obj.developer_proceeds_try or 0.0)
        if cum_g <= 0:
            return (0.0, 0.0)
        if win_key == "all":
            return (cum_g, cum_n)
        ref_pair_w = paid_ref_by_prod.get(lr_obj.product_id or ("misilaylik" if l_pl == "android" else "misil_monthly"), (0.0, 0.0))
        std_w_g, std_w_n = _resolve_expected_trial_pricing(lr_obj.product_id, ref_pair_w[0], ref_pair_w[1], l_pl)
        # Kümülatif tutar tek dönemlik standart fiyatın 1.35 katını aşmışsa (2+ dönem yenileme)
        if cum_g > (std_w_g * 1.35):
            exp_g = float(lr_obj.expected_next_price_try or 0.0)
            exp_n = float(lr_obj.expected_next_proceeds_try or 0.0)
            if 0 < exp_g <= (std_w_g * 1.35):
                return (
                    round(exp_g, 2),
                    round(exp_n if exp_n > 0 else (exp_g * get_dynamic_proceeds_ratio(l_pl)), 2),
                )
            return (round(std_w_g, 2), round(std_w_n, 2))
        return (cum_g, cum_n)

    def _calc_window_revenue(win_key: str) -> Dict[str, Any]:
        g_try = 0.0
        n_try = 0.0
        ios_g = 0.0
        ios_n = 0.0
        and_g = 0.0
        and_n = 0.0
        p_cnt = 0
        tr_cnt = 0
        cd_cnt = 0
        cn_cnt = 0
        tx_items: List[str] = []
        for lr in ledger_rows_db:
            l_pl = "android" if (lr.platform or "ios").lower() == "android" else "ios"
            c_p_raw = float(lr.customer_price_try or 0.0)
            tx_d = (lr.converted_or_renewed_date or lr.started_date or "").strip()[:10]
            st_d = (lr.started_date or "").strip()[:10]
            if c_p_raw > 0 and _in_period_window(tx_d, l_pl, win_key):
                c_p, d_p = _resolve_single_window_tx_amount(lr, win_key, l_pl)
                g_try = round(g_try + c_p, 2)
                n_try = round(n_try + d_p, 2)
                p_cnt += 1
                if l_pl == "android":
                    and_g = round(and_g + c_p, 2)
                    and_n = round(and_n + d_p, 2)
                else:
                    ios_g = round(ios_g + c_p, 2)
                    ios_n = round(ios_n + d_p, 2)
                tx_items.append(f"{tx_d}: #{lr.subscriber_id[-6:]} ({lr.plan_label} • {c_p:.2f} ₺ Brüt / {d_p:.2f} ₺ Net)")
            if _in_period_window(st_d, l_pl, win_key):
                if lr.status == "intro_free_trial" and lr.auto_renew_enabled:
                    tr_cnt += 1
                elif lr.status == "offer_code_trial":
                    cd_cnt += 1
                elif lr.status == "cancelled" or not lr.auto_renew_enabled:
                    cn_cnt += 1
        return {
            "gross_try": round(g_try, 2),
            "net_try": round(n_try, 2),
            "gross_usd": _convert_try_to_usd(g_try),
            "net_usd": _convert_try_to_usd(n_try),
            "ios_gross_try": round(ios_g, 2),
            "ios_net_try": round(ios_n, 2),
            "ios_gross_usd": _convert_try_to_usd(ios_g),
            "ios_net_usd": _convert_try_to_usd(ios_n),
            "android_gross_try": round(and_g, 2),
            "android_net_try": round(and_n, 2),
            "paid_count": p_cnt,
            "new_trials_count": tr_cnt,
            "new_codes_count": cd_cnt,
            "cancelled_count": cn_cnt,
            "transactions": tx_items,
        }

    win_all = _calc_window_revenue("all")
    win_7d = _calc_window_revenue("7d")
    win_yesterday = _calc_window_revenue("yesterday")
    win_today = _calc_window_revenue("today")
    win_selected = (
        win_all if period == "all"
        else (win_7d if period == "7d" else (win_yesterday if period == "yesterday" else win_today))
    )

    if period == "all":
        period_win_label = f"Tüm Zamanlar (Kümülatif • Son Kesinleşen Apple Raporu: {apple_anchor_str})"
    elif period == "7d":
        period_win_label = f"Son 7 Gün (Apple Connect Trends T-1 Penceresi: {apple_7d_start_str} ➔ {apple_anchor_str} + T-0 Canlı)"
    elif period == "yesterday":
        period_win_label = f"Dün / Apple Son Kesinleşen Rapor Günü (T-1: {apple_anchor_str} • Android: {yesterday_str})"
    else:
        period_win_label = f"Bugün TSİ ({today_str} T-0 Canlı Köprü • Apple Resmi TSV 1 Gün Gecikmeli: {apple_anchor_str})"

    crossgrade_rows = [
        r for r in ledger_rows_db
        if r.status == "offer_code_trial" and (r.expected_next_price_try or 0.0) > 0
    ]
    crossgrade_gross_try = round(sum(float(r.expected_next_price_try or 0.0) for r in crossgrade_rows), 2)
    crossgrade_net_try = round(sum(float(r.expected_next_proceeds_try or 0.0) for r in crossgrade_rows), 2)

    # Ülke bazlı ücretli alım sayısı ve gelir/abone dağılımı (Country Revenue & Subscriber Breakdown)
    dl_by_country_map: Dict[str, Dict[str, Any]] = {}
    for c_entry in (sb.get("apple_downloads_by_country") or []):
        cc = str(c_entry.get("code") or "TR").strip().upper()
        dl_by_country_map[cc] = {
            "count": int(c_entry.get("count", 0) or 0),
            "flag": str(c_entry.get("flag") or COUNTRY_META.get(cc, {}).get("flag") or "🌍"),
            "name": str(c_entry.get("name") or COUNTRY_META.get(cc, {}).get("name") or cc),
        }

    android_dl_by_country: Counter = Counter()
    for fo_sig in first_opens:
        if (fo_sig.os_family or "").lower() == "android":
            fo_cc = str(fo_sig.country or "TR").strip().upper() or "TR"
            android_dl_by_country[fo_cc] += 1
    effective_and_country_dl: Counter = Counter()
    gp_dl_int = int(google_play_downloads or 0)
    if gp_dl_int > 0:
        sig_and_tot = sum(android_dl_by_country.values())
        if sig_and_tot == 0:
            effective_and_country_dl["TR"] = gp_dl_int
        else:
            effective_and_country_dl.update(android_dl_by_country)
            if sig_and_tot < gp_dl_int:
                effective_and_country_dl["TR"] += (gp_dl_int - sig_and_tot)

    country_agg: Dict[str, Dict[str, Any]] = {}
    all_country_codes = (
        set(dl_by_country_map.keys())
        | set(effective_and_country_dl.keys())
        | {str(r.country or "TR").strip().upper() for r in ledger_rows_db}
    )
    if not all_country_codes:
        all_country_codes = {"TR"}

    for cc in all_country_codes:
        c_meta = dl_by_country_map.get(cc) or {}
        c_flag = c_meta.get("flag") or COUNTRY_META.get(cc, {}).get("flag") or "🌍"
        c_name = c_meta.get("name") or COUNTRY_META.get(cc, {}).get("name") or cc
        c_dl = int(c_meta.get("count", 0) or 0) + int(effective_and_country_dl.get(cc, 0) or 0)
        country_agg[cc] = {
            "code": cc,
            "flag": c_flag,
            "name": c_name,
            "downloads": c_dl,
            "paid_subs_count": 0,
            "paid_annual_count": 0,
            "paid_monthly_count": 0,
            "trial_subs_count": 0,
            "offer_code_subs_count": 0,
            "cancelled_subs_count": 0,
            "active_vip_count": 0,
            "realized_gross_try": 0.0,
            "realized_net_try": 0.0,
            "expected_mrr_gross_try": 0.0,
            "expected_mrr_net_try": 0.0,
        }

    for lr in ledger_rows_db:
        l_pl_c = "android" if (lr.platform or "ios").lower() == "android" else "ios"
        st_d_c = (lr.started_date or "").strip()[:10]
        tx_d_c = (lr.converted_or_renewed_date or lr.started_date or "").strip()[:10]
        if period != "all" and not (_in_period_window(st_d_c, l_pl_c, period) or _in_period_window(tx_d_c, l_pl_c, period)):
            continue
        cc = str(lr.country or "TR").strip().upper() or "TR"
        ca = country_agg[cc]
        if period != "all":
            c_p, d_p = _resolve_single_window_tx_amount(lr, period, l_pl_c)
        else:
            c_p = float(lr.customer_price_try or 0.0)
            d_p = float(lr.developer_proceeds_try or 0.0)
        exp_g = float(lr.expected_next_price_try or 0.0)
        exp_n = float(lr.expected_next_proceeds_try or 0.0)
        is_ann_lr = _is_annual_product(lr.product_id)

        if lr.status == "paid_active" and c_p > 0 and _in_period_window(tx_d_c, l_pl_c, period):
            ca["paid_subs_count"] += 1
            ca["active_vip_count"] += 1
            if is_ann_lr:
                ca["paid_annual_count"] += 1
            else:
                ca["paid_monthly_count"] += 1
            ca["realized_gross_try"] = round(ca["realized_gross_try"] + c_p, 2)
            ca["realized_net_try"] = round(ca["realized_net_try"] + d_p, 2)
            if lr.auto_renew_enabled:
                m_div = 12.0 if is_ann_lr else 1.0
                mrr_base_g = exp_g if exp_g > 0 else c_p
                mrr_base_n = exp_n if exp_n > 0 else d_p
                ca["expected_mrr_gross_try"] = round(ca["expected_mrr_gross_try"] + (mrr_base_g / m_div), 2)
                ca["expected_mrr_net_try"] = round(ca["expected_mrr_net_try"] + (mrr_base_n / m_div), 2)
        elif lr.status == "intro_free_trial" and lr.auto_renew_enabled:
            ca["trial_subs_count"] += 1
            ca["active_vip_count"] += 1
            m_div_tr = 12.0 if is_ann_lr else 1.0
            ca["expected_mrr_gross_try"] = round(ca["expected_mrr_gross_try"] + (exp_g / m_div_tr), 2)
            ca["expected_mrr_net_try"] = round(ca["expected_mrr_net_try"] + (exp_n / m_div_tr), 2)
        elif lr.status == "offer_code_trial":
            ca["offer_code_subs_count"] += 1
            ca["active_vip_count"] += 1
        elif lr.status == "cancelled" or not lr.auto_renew_enabled:
            ca["cancelled_subs_count"] += 1

    country_revenue_breakdown: List[Dict[str, Any]] = []
    for cc, ca in country_agg.items():
        g_t = ca["realized_gross_try"]
        n_t = ca["realized_net_try"]
        ca["realized_gross_usd"] = _convert_try_to_usd(g_t)
        ca["realized_net_usd"] = _convert_try_to_usd(n_t)
        ca["share_of_revenue_pct"] = round((g_t / realized_gross_try) * 100.0, 1) if realized_gross_try > 0 else 0.0
        plan_parts: List[str] = []
        if ca["paid_annual_count"] > 0:
            plan_parts.append(f"{ca['paid_annual_count']} Yıllık (599.99 ₺)")
        if ca["paid_monthly_count"] > 0:
            plan_parts.append(f"{ca['paid_monthly_count']} Aylık (149.99 ₺)")
        ca["paid_plans_label"] = " + ".join(plan_parts) if plan_parts else "Henüz Ücretli Alım Yok"
        country_revenue_breakdown.append(ca)

    country_revenue_breakdown.sort(
        key=lambda x: (x["realized_gross_try"], x["active_vip_count"], x["downloads"]),
        reverse=True,
    )
    paid_countries_count = sum(1 for c in country_revenue_breakdown if c["paid_subs_count"] > 0)
    vip_countries_count = sum(1 for c in country_revenue_breakdown if c["active_vip_count"] > 0)
    download_countries_count = sum(1 for c in country_revenue_breakdown if c["downloads"] > 0 or c["active_vip_count"] > 0)

    store_reconciliation = {
        "apple_latest_report_date": apple_anchor_str,
        "apple_lag_days": apple_lag_days,
        "apple_7d_window_start": apple_7d_start_str,
        "apple_7d_window_end": apple_anchor_str,
        "usd_try_rate": APPLE_TRENDS_USD_TRY_RATE,
        "period_window_label": period_win_label,
        "all_time": win_all,
        "last_7d_t1": win_7d,
        "yesterday_t1": win_yesterday,
        "today_t0": win_today,
        "period_selected": win_selected,
        "rc_v2_crossgrades_count": len(crossgrade_rows),
        "rc_v2_crossgrades_gross_try": crossgrade_gross_try,
        "rc_v2_crossgrades_net_try": crossgrade_net_try,
        "paid_countries_count": paid_countries_count,
        "vip_countries_count": vip_countries_count,
        "download_countries_count": download_countries_count,
        "country_revenue_breakdown": country_revenue_breakdown,
    }

    renewal_calendar_serialized: List[Dict[str, Any]] = []
    for k_ren in sorted(renewal_by_date.keys()):
        rc_item = dict(renewal_by_date[k_ren])
        rc_plats = rc_item.pop("_platforms", set())
        rc_item["platform"] = "all" if len(rc_plats) != 1 else next(iter(rc_plats))
        renewal_calendar_serialized.append(rc_item)

    financial_ledger = {
        "realized_gross_try": round(realized_gross_try, 2),
        "realized_net_proceeds_try": round(realized_net_try, 2),
        "realized_gross_usd": _convert_try_to_usd(realized_gross_try),
        "realized_net_proceeds_usd": _convert_try_to_usd(realized_net_try),
        "period_realized_gross_try": win_selected["gross_try"],
        "period_realized_net_proceeds_try": win_selected["net_try"],
        "period_realized_gross_usd": win_selected["gross_usd"],
        "period_realized_net_proceeds_usd": win_selected["net_usd"],
        "period_paid_subs_count": win_selected["paid_count"],
        "period_window_label": period_win_label,
        "paid_countries_count": paid_countries_count,
        "vip_countries_count": vip_countries_count,
        "download_countries_count": download_countries_count,
        "country_revenue_breakdown": country_revenue_breakdown,
        "store_reconciliation": store_reconciliation,
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
        "projected_total_mrr_gross_try": round(active_paid_mrr_gross + pipeline_7d_monthly_mrr_gross, 2),
        "projected_total_mrr_net_try": round(active_paid_mrr_net + pipeline_7d_monthly_mrr_net, 2),
        "projected_total_arr_net_try": round((active_paid_mrr_net + pipeline_7d_monthly_mrr_net) * 12, 2),
        "active_vip_subs_count": active_vip_total,
        "total_vip_records_count": len(ledger_rows_db),
        "offer_code_subs_count": offer_code_cnt,
        "paid_subs_count": paid_subs_cnt,
        "auto_renewing_paid_subs_count": auto_renewing_paid_subs_cnt,
        "non_renewing_paid_subs_count": non_renewing_paid_subs_cnt,
        "ios_proceeds_ratio_pct": round(get_dynamic_proceeds_ratio("ios") * 100.0, 1),
        "android_proceeds_ratio_pct": round(get_dynamic_proceeds_ratio("android") * 100.0, 1),
        "commission_program_badge": "🏷️ %15 Komisyon Programı Aktif (Apple SBP %15 & Google Play %15)",
        "cancelled_subs_count": cancelled_cnt,
        "churn_rate_pct": all_churn_rate_pct,
        "auto_renew_on_pct": auto_renew_on_pct,
        "matured_cutoff_date": matured_cutoff_str,
        "matured_trials_total": len(matured_7d_cohort),
        "matured_trials_converted": matured_converted,
        "matured_trial_to_paid_cvr_pct": matured_cvr_pct,
        "matured_trial_to_paid_cvr_str": matured_cvr_str,
        "renewal_forecast_calendar": renewal_calendar_serialized,
    }

    # ========================================================================
    # FAZ 3: DİNAMİK KAMPANYA & KANAL ATTRIBUTION MATRİSİ (SIFIR STATİK VERİ)
    # ========================================================================
    cfg_rows = db.query(CampaignConfig).all()
    cfg_map: Dict[str, CampaignConfig] = {c.channel_key: c for c in cfg_rows}

    asa_cfg = cfg_map.get("apple_search_ads")
    meta_cfg = cfg_map.get("meta_ads_ios")
    meta_and_cfg = cfg_map.get("meta_app_installs_android") or cfg_map.get("meta_ads")
    gp_org_cfg = cfg_map.get("google_play_organic")
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
    matched_android_bio_installs = len([
        s for s in first_opens
        if s.os_family == "android"
        and (s.matched_channel and ("instagram" in s.matched_channel.lower() or "download" in s.matched_channel.lower()))
    ])
    matched_android_meta_bridge_installs = len([
        s for s in first_opens
        if s.os_family == "android"
        and (s.matched_channel and ("meta" in s.matched_channel.lower() or "ios" in s.matched_channel.lower()))
    ])
    direct_android_play_or_meta_installs = max(0, google_play_downloads - matched_android_bio_installs)
    direct_ios_store_or_meta_installs = max(0, apple_downloads - matched_ig_installs)
    ios_att_sdk_devices_cnt = len({
        s.device_uid or f"idx_{idx}"
        for idx, s in enumerate(signals)
        if (s.os_family or "").lower() == "ios" and _parse_semver_tuple(s.app_version) >= (4, 56, 0)
    })
    ios_att_sdk_is_live = ios_att_sdk_devices_cnt > 0
    ios_att_sdk_status_key = "live" if ios_att_sdk_is_live else "waiting_for_review"
    ios_att_sdk_status_badge = (
        f"🟢 iOS Reklamları & SDK Aktif ({ios_att_sdk_devices_cnt} Cihaz)"
        if ios_att_sdk_is_live
        else f"🟢 iOS Reklamları Aktif ({direct_ios_store_or_meta_installs} App Store & Meta Kurulum)"
    )

    gp_cfg_imp = int(gp_org_cfg.reported_impressions if gp_org_cfg else 0) + int(meta_and_cfg.reported_impressions if meta_and_cfg else 0)
    gp_cfg_pv = int(gp_org_cfg.reported_clicks if gp_org_cfg else 0) + int(meta_and_cfg.reported_clicks if meta_and_cfg else 0)
    if period == "all":
        google_play_impressions = max(google_play_impressions_base, gp_cfg_imp)
        google_play_page_views = max(google_play_page_views_base, gp_cfg_pv)
    else:
        google_play_impressions = google_play_impressions_base
        google_play_page_views = google_play_page_views_base

    # Doğrulanmış AppInstallSignal (instagram_bio) kayıtları varsa, eski /ios reklam sıfırlaması sonrası
    # organik Instagram Bio (/download) profil trafiğinin 0'a düşmesini önle (eski /ios reklam trafiği 0 kalır)
    ig_ios_count = max(len(ig_ios), matched_ig_installs)
    ig_android_count = max(len(ig_android), matched_android_bio_installs)
    ig_unique_count = max(len(ig_unique), ig_ios_count + ig_android_count)

    # Google Play Console r14 eşdeğeri API sunmadığında ve StoreDailyMetric(android) henüz 0 iken,
    # doğrulanmış Android telemetrisi (first_open / paywall_viewed) varsa mağaza gösterim ve ziyaret tabanını türet
    android_paywall_views_cnt = len([s for s in paywall_viewed_signals if (s.os_family or "").lower() == "android"])
    has_live_android_telemetry = (android_signal_opens > 0 or android_paywall_views_cnt > 0 or matched_android_bio_installs > 0)
    if google_play_page_views == 0 and google_play_downloads > 0 and has_live_android_telemetry:
        ios_pv_per_dl = (apple_page_views / apple_downloads) if (apple_downloads > 0 and apple_page_views > 0) else 4.0
        derived_gp_pv = round(direct_android_play_or_meta_installs * max(2.5, min(6.5, ios_pv_per_dl)))
        google_play_page_views = max(google_play_downloads, android_paywall_views_cnt, derived_gp_pv)
    if google_play_impressions == 0 and google_play_page_views > 0 and has_live_android_telemetry:
        ios_imp_per_pv = (apple_impressions / apple_page_views) if (apple_page_views > 0 and apple_impressions > 0) else 8.0
        google_play_impressions = max(
            google_play_page_views * 3,
            round(google_play_page_views * max(4.0, min(12.0, ios_imp_per_pv))),
        )

    sb["google_play_impressions_total"] = google_play_impressions
    sb["google_play_page_views_total"] = google_play_page_views
    active_bridge_pool = unique_human if period == "all" else active_human_set
    effective_unique_bridge_clicks = max(len(active_bridge_pool), ig_unique_count + len(meta_unique))
    total_cumulative_impressions = apple_impressions + google_play_impressions
    total_cumulative_store_page_views = apple_page_views + google_play_page_views
    total_cumulative_visits_and_clicks = total_cumulative_store_page_views + effective_unique_bridge_clicks

    if period == "all":
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
    else:
        r3_search = db_ios_dl_search
        r3_ref = max(db_ios_dl_ref, matched_meta_installs)
        r3_browse = max(db_ios_dl_browse, matched_ig_installs)
        asa_clicks_val = apple_taps
        base_s = int(sb.get("apple_impressions_search", 0) or 0)
        base_b = int(sb.get("apple_impressions_browse", 0) or 0)
        s_ratio = (base_s / max(1, base_s + base_b)) if (base_s + base_b) > 0 else 0.85
        imp_search_val = round(apple_impressions * s_ratio)
        imp_browse_val = max(0, apple_impressions - imp_search_val)

    # T3 Çözümü: Apple r3 kaynak raporu henüz senkronize edilmemişse (0 ise), doğrulanmış r14 Discovery
    # arama/keşfet oranları ve köprü sinyalleri üzerinden kaynak dağılımını hesapla
    if (r3_search + r3_browse) == 0 and apple_downloads > 0 and (imp_search_val + imp_browse_val) > 0:
        allocatable_ios = max(0, apple_downloads - r3_ref - offer_code_cnt)
        search_share = imp_search_val / max(1, imp_search_val + imp_browse_val)
        r3_search = round(allocatable_ios * search_share)
        r3_browse = max(0, allocatable_ios - r3_search)

    recent_ios_dl = max(0, apple_downloads - (r3_search + r3_ref + r3_browse + (offer_code_cnt if period == "all" else 0)))
    android_bridge_uniq = max(len([c for c in active_bridge_pool if c.os_family == "android"]), ig_android_count)

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
            "source_badge": "App Store Resmi Veri",
            "impressions": f"{imp_search_val:,}",
            "page_views_or_clicks": f"Toplam {apple_page_views} Sayfa ({sb.get('apple_page_views_unique', 0) or apple_page_views} Cihaz) • {apple_taps} Dokunma",
            "downloads": r3_search,
            "cvr_pct": round((r3_search / imp_search_val) * 100, 2) if imp_search_val > 0 else 0.0,
            "cvr_basis": "Görüntülenme ➔ İndirme",
            "vip_attributed": f"{paid_subs_cnt} Ücretli + {intro_trial_cnt} Aktif Deneme",
        },
        {
            "channel": "📲 Sosyal Yönlendirme & Meta Reklamları",
            "source_badge": "Instagram Profil & Meta Reklam",
            "impressions": "-",
            "page_views_or_clicks": f"{ig_unique_count} Profil Tıkı • {ios_att_sdk_status_badge}",
            "downloads": r3_ref,
            "cvr_pct": min(100.0, round((r3_ref / effective_unique_bridge_clicks) * 100, 1)) if effective_unique_bridge_clicks > 0 else 0.0,
            "cvr_basis": "Sosyal Tık ➔ iOS İndirme",
            "vip_attributed": f"{matched_meta_installs + matched_ig_installs} Doğrulanmış Cihaz Eşleşmesi",
        },
        {
            "channel": "🎟️ Promosyon Kodu (VIP Kodları)",
            "source_badge": "App Store Abone Verisi",
            "impressions": "-",
            "page_views_or_clicks": f"{offer_code_cnt} Tekil Kod Kullanımı",
            "downloads": offer_code_cnt,
            "cvr_pct": 100.0 if offer_code_cnt > 0 else 0.0,
            "cvr_basis": "Kod ➔ Yıllık VIP Aktivasyon",
            "vip_attributed": f"{offer_code_cnt} Aktif Kod Abonesi",
        },
        {
            "channel": "📅 Doğrudan / Diğer iOS Kurulumları",
            "source_badge": "App Store Satış Raporu",
            "impressions": "-",
            "page_views_or_clicks": "-",
            "downloads": recent_ios_dl,
            "cvr_pct": None,
            "cvr_basis": "Doğrudan Mağaza Kurulumu",
            "vip_attributed": f"{unmatched_organic_opens} Organik İlk Açılış",
        },
        {
            "channel": "✨ App Store Keşfet (Browse / Organik)",
            "source_badge": "App Store & Profil Köprüsü",
            "impressions": f"{imp_browse_val:,}",
            "page_views_or_clicks": f"{ig_ios_count} Bio Köprü Tıkı + Keşfet Vitrin",
            "downloads": r3_browse,
            "cvr_pct": round((r3_browse / imp_browse_val) * 100, 1) if imp_browse_val > 0 else 0.0,
            "cvr_basis": "Görüntülenme ➔ İndirme",
            "vip_attributed": f"{matched_ig_installs} Profil Eşleşmesi",
        },
        {
            "channel": "🤖 Google Play (Organik Arama + Meta Reklam + Bio)",
            "source_badge": "Google Play + Meta Reklam",
            "impressions": f"{google_play_impressions:,}" if google_play_impressions > 0 else "Play Konsol + Meta",
            "page_views_or_clicks": (
                f"{google_play_page_views:,} Mağaza Ziyareti + {ig_android_count} Profil Tıkı"
                if google_play_page_views > 0
                else f"Play Mağaza + Meta Reklam • {ig_android_count} Profil Tıkı"
            ),
            "downloads": google_play_downloads,
            "cvr_pct": (
                min(100.0, round((google_play_downloads / (google_play_page_views + ig_android_count)) * 100, 1))
                if google_play_page_views > 0
                else (min(100.0, round((matched_android_bio_installs / ig_android_count) * 100, 1)) if ig_android_count > 0 else None)
            ),
            "cvr_basis": "Google Play Organik + Meta Reklam + Bio",
            "vip_attributed": f"{direct_android_play_or_meta_installs} Play/Meta + {matched_android_bio_installs} Profil ({android_signal_opens} Cihaz)",
        },
    ]

    # ========================================================================
    # FAZ 3B: ÜRÜN İÇİ NABIZ, BEBEK YAŞ DAĞILIMI & KOHORT TUTUNDURMA
    # ========================================================================
    try:
        baby_birth_rows = db.query(Baby.birth_date).limit(500).all()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        baby_birth_rows = []
    age_buckets = {"0–3 Ay (Yenidoğan / 4. Trimester)": 0, "4–6 Ay (Uyku Gerilemesi)": 0, "7–12 Ay": 0, "12+ Ay": 0}
    now_utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    for (b_dt,) in baby_birth_rows:
        try:
            if b_dt is None:
                m = 0.0
            else:
                b_naive = b_dt.astimezone(timezone.utc).replace(tzinfo=None) if getattr(b_dt, "tzinfo", None) else b_dt
                m = max(0.0, (now_utc_naive - b_naive).days / 30.4375)
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
        "android_official_sessions": android_official_sessions,
        "live_telemetry_sessions": live_telemetry_sessions,
        "total_tracked_sessions": max(apple_official_sessions + android_official_sessions, live_telemetry_sessions),
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
        "routine_logs_count": max(db_routine_count, len(routine_logged_signals)),
        "dadi_chats_count": max(db_dadi_count, len(dadi_chat_signals)),
        "age_buckets": age_buckets,
        "subscriber_cohorts": cohort_rows,
        "overall_retention_pct": overall_retention_pct,
        "overall_retention_str": overall_retention_str,
    }

    # Son 3 aktif gün vs önceki günler ivmesi (Sparkline & Delta Rozeti için)
    settled_days = [d for d in timeline_days if not d.get("is_store_pending")]
    r14_settled_days = [d for d in timeline_days if not d.get("is_r14_pending")] or settled_days
    recent_3d_imp = sum(d.get("daily_impressions", 0) for d in r14_settled_days[-3:]) if r14_settled_days else 0
    recent_3d_dl = sum(d.get("daily_downloads", 0) for d in settled_days[-3:]) if settled_days else 0
    latest_store_metric_date = settled_days[-1]["date"] if settled_days else ""

    ios_bridge_uniq = max(len([c for c in active_bridge_pool if c.os_family == "ios"]), ig_ios_count)
    desktop_bridge_uniq = len([c for c in active_bridge_pool if c.os_family not in ("ios", "android")])
    ios_touchpoints = apple_page_views + ios_bridge_uniq
    android_touchpoints = google_play_page_views + android_bridge_uniq

    # P1: Simpson Paradoksu & 24s Gecikme Ayrımı — Mağaza Sayfası CVR vs Sosyal Köprü CVR vs Kesinleşen Günler CVR
    apple_page_views_uniq = db_ios_pv_uniq if (period != "all" or db_ios_pv_uniq > 0) else int(sb.get("apple_page_views_unique", 0) or apple_page_views)
    if apple_page_views_uniq == 0 and apple_page_views > 0:
        apple_page_views_uniq = apple_page_views
    google_play_page_views_uniq = db_android_pv_uniq if db_android_pv_uniq > 0 else google_play_page_views
    ios_imp_uniq_display = db_ios_imp_uniq if (period != "all" or db_ios_imp_uniq > 0) else int(sb.get("apple_impressions_unique", 0) or 0)
    if ios_imp_uniq_display == 0 and apple_impressions > 0:
        ios_imp_uniq_display = apple_impressions
    total_impressions_unique = ios_imp_uniq_display + (
        db_android_imp_uniq if db_android_imp_uniq > 0 else google_play_impressions
    )
    total_store_page_views_unique = apple_page_views_uniq + google_play_page_views_uniq
    store_imp_to_pv_pct = (
        min(100.0, round((total_cumulative_store_page_views / max(1, total_cumulative_impressions)) * 100, 1))
        if total_cumulative_store_page_views > 0 and total_cumulative_impressions > 0
        else (
            min(100.0, round((total_cumulative_visits_and_clicks / max(1, total_cumulative_impressions)) * 100, 1))
            if total_cumulative_impressions > 0
            else 0.0
        )
    )
    ios_store_imp_to_pv_pct = (
        min(100.0, round((apple_page_views / max(1, apple_impressions)) * 100, 1))
        if apple_page_views > 0 and apple_impressions > 0
        else 0.0
    )
    android_store_imp_to_pv_pct = (
        min(100.0, round((google_play_page_views / max(1, google_play_impressions)) * 100, 1))
        if google_play_page_views > 0 and google_play_impressions > 0
        else (100.0 if android_bridge_uniq > 0 and google_play_impressions == 0 else 0.0)
    )
    store_matched_downloads = apple_downloads + (google_play_downloads if google_play_page_views > 0 else 0)
    store_page_cvr_pct = (
        min(100.0, round((store_matched_downloads / max(1, total_cumulative_store_page_views)) * 100, 1))
        if total_cumulative_store_page_views > 0
        else 0.0
    )
    ios_store_page_cvr_pct = (
        min(100.0, round((apple_downloads / max(1, apple_page_views)) * 100, 1))
        if apple_page_views > 0
        else 0.0
    )
    android_store_page_cvr_pct = (
        min(100.0, round((google_play_downloads / max(1, google_play_page_views)) * 100, 1))
        if google_play_page_views > 0
        else 0.0
    )
    store_unique_cvr_pct = (
        min(100.0, round((store_matched_downloads / max(1, total_store_page_views_unique)) * 100, 1))
        if total_cumulative_store_page_views > 0 and total_store_page_views_unique > 0
        else 0.0
    )
    ios_store_unique_cvr_pct = (
        min(100.0, round((apple_downloads / max(1, apple_page_views_uniq)) * 100, 1))
        if apple_page_views > 0 and apple_page_views_uniq > 0
        else 0.0
    )
    ios_bridge_dl = min(ios_bridge_uniq, r3_ref) if ios_bridge_uniq > 0 else 0
    and_bridge_dl = min(android_bridge_uniq, matched_android_bio_installs if matched_android_bio_installs > 0 else google_play_downloads) if android_bridge_uniq > 0 else 0
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
        round((all_bridge_installs / max(1, effective_unique_bridge_clicks)) * 100, 1)
        if effective_unique_bridge_clicks > 0
        else 0.0
    )
    matched_downloads_for_vis = apple_downloads + (google_play_downloads if google_play_page_views > 0 else and_bridge_dl)
    all_vis_to_dl_cvr_pct = (
        min(100.0, round((matched_downloads_for_vis / max(1, total_cumulative_visits_and_clicks)) * 100, 1))
        if total_cumulative_visits_and_clicks > 0
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

    if period != "all":
        filtered_subscriber_ledger_list = []
        for s_item in subscriber_ledger_list:
            s_plat_k = "android" if (s_item.get("platform") or "ios").lower() == "android" else "ios"
            st_d_k = str(s_item.get("started_date") or "").strip()[:10]
            tx_d_k = str(s_item.get("converted_or_renewed_date") or s_item.get("started_date") or "").strip()[:10]
            if _in_period_window(st_d_k, s_plat_k, period) or _in_period_window(tx_d_k, s_plat_k, period):
                filtered_subscriber_ledger_list.append(s_item)
        subscriber_ledger_list = filtered_subscriber_ledger_list

    ios_subs_list = [s for s in subscriber_ledger_list if (s.get("platform") or "ios") == "ios"]
    android_subs_list = [s for s in subscriber_ledger_list if s.get("platform") == "android"]
    gp_catalog = sb.get("google_play_subscriptions_catalog") or _empty_store_state()["google_play_subscriptions_catalog"]

    def _build_ab_experiment_comparison(plat_filter: str = "all") -> Dict[str, Any]:
        """
        RevenueCat Paywall A/B Testi (Grup A: İlk Ay %67 İndirim • 49.99 ₺ vs Grup B: İlk Ay Ücretsiz • 30 Gün 0 ₺ vs Yıllık VIP Çıpa • 599.99 ₺)
        karşılaştırma matrisini gerçek SubscriberLedger ve AppInstallSignal verilerinden üretir.
        """
        if plat_filter == "ios":
            plat_subs = ios_subs_list
            plat_sigs = [s for s in active_signals_set if (s.os_family or "").lower() == "ios"]
        elif plat_filter == "android":
            plat_subs = android_subs_list
            plat_sigs = [s for s in active_signals_set if (s.os_family or "").lower() == "android"]
        else:
            plat_subs = subscriber_ledger_list
            plat_sigs = active_signals_set

        ab_a_pw_u = _count_distinct_signal_devices([s for s in plat_sigs if s.event_type == "ab_a_paywall_viewed"])
        ab_b_pw_u = _count_distinct_signal_devices([s for s in plat_sigs if s.event_type == "ab_b_paywall_viewed"])
        ab_a_cta_u = _count_distinct_signal_devices([s for s in plat_sigs if s.event_type == "ab_a_paywall_cta"])
        ab_b_cta_u = _count_distinct_signal_devices([s for s in plat_sigs if s.event_type == "ab_b_paywall_cta"])
        ab_a_can_u = _count_distinct_signal_devices([s for s in plat_sigs if s.event_type == "ab_a_purchase_cancelled"])
        ab_b_can_u = _count_distinct_signal_devices([s for s in plat_sigs if s.event_type == "ab_b_purchase_cancelled"])
        ab_a_vip_u = _count_distinct_signal_devices([s for s in plat_sigs if s.event_type == "ab_a_vip_started"])
        ab_b_vip_u = _count_distinct_signal_devices([s for s in plat_sigs if s.event_type == "ab_b_vip_started"])

        grp_a_subs = [s for s in plat_subs if s.get("ab_variant_group") == "group_a_paid_intro"]
        grp_b_subs = [s for s in plat_subs if s.get("ab_variant_group") == "group_b_free_trial_1m"]
        ann_subs = [s for s in plat_subs if s.get("ab_variant_group") == "annual_anchor"]
        legacy_7d_subs = [s for s in plat_subs if s.get("ab_variant_group") == "legacy_7d_trial"]
        code_subs = [s for s in plat_subs if s.get("ab_variant_group") == "offer_code_vip"]
        std_m_subs = [s for s in plat_subs if s.get("ab_variant_group") == "standard_monthly"]

        def _summarize_variant_cohort(rows: List[Dict[str, Any]], pw_u: int, cta_u: int, can_u: int, sig_vip_u: int, is_annual_v: bool = False) -> Dict[str, Any]:
            started_c = len(rows)
            active_paid_c = sum(1 for r_it in rows if r_it.get("status") == "paid_active")
            auto_renew_c = sum(
                1 for r_it in rows
                if r_it.get("status") != "cancelled" and bool(r_it.get("auto_renew_enabled", True))
            )
            active_trial_c = sum(
                1 for r_it in rows
                if r_it.get("status") == "intro_free_trial" and bool(r_it.get("auto_renew_enabled", True))
            )
            cancelled_c = sum(
                1 for r_it in rows
                if r_it.get("status") == "cancelled" or (r_it.get("status") != "paid_active" and not bool(r_it.get("auto_renew_enabled", True)))
            )
            active_tot_c = active_paid_c + active_trial_c
            ios_act_c = sum(1 for r_it in rows if r_it.get("platform") == "ios" and r_it.get("status") in ("paid_active", "intro_free_trial", "offer_code_trial") and (r_it.get("status") == "paid_active" or bool(r_it.get("auto_renew_enabled", True))))
            and_act_c = sum(1 for r_it in rows if r_it.get("platform") == "android" and r_it.get("status") in ("paid_active", "intro_free_trial", "offer_code_trial") and (r_it.get("status") == "paid_active" or bool(r_it.get("auto_renew_enabled", True))))
            ret_pct = round(((started_c - cancelled_c) / started_c) * 100.0, 1) if started_c > 0 else 0.0
            ch_pct = round((cancelled_c / started_c) * 100.0, 1) if started_c > 0 else 0.0
            day0_g = round(sum(float(r_it.get("customer_price_try") or 0.0) for r_it in rows), 2)
            day0_n = round(sum(float(r_it.get("developer_proceeds_try") or 0.0) for r_it in rows), 2)
            day0_n_usd = round(day0_n / 34.5, 2)
            pipe_g = round(
                sum(
                    float(r_it.get("expected_next_price_try") or 0.0)
                    for r_it in rows
                    if r_it.get("status") == "intro_free_trial" and bool(r_it.get("auto_renew_enabled", True))
                ),
                2,
            )
            pipe_n = round(
                sum(
                    float(r_it.get("expected_next_proceeds_try") or 0.0)
                    for r_it in rows
                    if r_it.get("status") == "intro_free_trial" and bool(r_it.get("auto_renew_enabled", True))
                ),
                2,
            )
            div_m = 12.0 if is_annual_v else 1.0
            proj_mrr_g = 0.0
            proj_mrr_n = 0.0
            for r_it in rows:
                if r_it.get("status") in ("paid_active", "intro_free_trial") and bool(r_it.get("auto_renew_enabled", True)):
                    eg = float(r_it.get("expected_next_price_try") or r_it.get("customer_price_try") or 0.0)
                    en = float(r_it.get("expected_next_proceeds_try") or r_it.get("developer_proceeds_try") or 0.0)
                    proj_mrr_g += (eg / div_m)
                    proj_mrr_n += (en / div_m)
            eff_pw = max(pw_u, cta_u, started_c)
            eff_cta = max(cta_u, started_c)
            pw_to_cta = min(100.0, round((eff_cta / eff_pw) * 100.0, 1)) if eff_pw > 0 else 0.0
            cancel_r = min(100.0, round((can_u / max(1, cta_u)) * 100.0, 1)) if cta_u > 0 else 0.0
            pw_to_vip = min(100.0, round((max(started_c, sig_vip_u) / eff_pw) * 100.0, 1)) if eff_pw > 0 else 0.0
            return {
                "paywall_views": pw_u,
                "paywall_views_devices": pw_u,
                "cta_clicks": cta_u,
                "paywall_cta_devices": cta_u,
                "purchase_cancelled": can_u,
                "purchase_cancelled_devices": can_u,
                "vip_started_signals_devices": sig_vip_u,
                "cta_of_view_pct": pw_to_cta,
                "paywall_to_cta_pct": pw_to_cta,
                "cancel_of_cta_pct": cancel_r,
                "cta_cancel_rate_pct": cancel_r,
                "paywall_to_vip_cvr_pct": pw_to_vip,
                "started_vip_count": started_c,
                "started_subs_count": started_c,
                "active_vip_count": active_tot_c,
                "active_subs_count": active_tot_c,
                "paid_converted_count": active_paid_c,
                "active_paid_count": active_paid_c,
                "trial_active_count": active_trial_c,
                "active_trials_count": active_trial_c,
                "auto_renewing_count": auto_renew_c,
                "cancelled_vip_count": cancelled_c,
                "cancelled_subs_count": cancelled_c,
                "ios_active_count": ios_act_c,
                "android_active_count": and_act_c,
                "retention_rate_pct": ret_pct,
                "churn_rate_pct": ch_pct,
                "realized_gross_try": day0_g,
                "day0_realized_gross_try": day0_g,
                "realized_net_try": day0_n,
                "day0_realized_net_try": day0_n,
                "realized_net_usd": day0_n_usd,
                "pipeline_trial_mrr_gross_try": pipe_g,
                "pipeline_30d_gross_try": pipe_g,
                "pipeline_trial_mrr_net_try": pipe_n,
                "pipeline_30d_net_try": pipe_n,
                "projected_mrr_gross_try": round(proj_mrr_g, 2),
                "projected_mrr_net_try": round(proj_mrr_n, 2),
                "mrr_share_pct": 0.0,
            }

        ga_stats = _summarize_variant_cohort(grp_a_subs, ab_a_pw_u, ab_a_cta_u, ab_a_can_u, ab_a_vip_u, is_annual_v=False)
        gb_stats = _summarize_variant_cohort(grp_b_subs, ab_b_pw_u, ab_b_cta_u, ab_b_can_u, ab_b_vip_u, is_annual_v=False)
        ann_stats = _summarize_variant_cohort(ann_subs, 0, 0, 0, 0, is_annual_v=True)
        leg_stats = _summarize_variant_cohort(legacy_7d_subs + std_m_subs, 0, 0, 0, 0, is_annual_v=False)
        code_stats = _summarize_variant_cohort(code_subs, 0, 0, 0, 0, is_annual_v=True)
        code_stats["active_vip_count"] = sum(1 for s_it in code_subs if s_it.get("status") == "offer_code_trial")
        code_stats["active_subs_count"] = code_stats["active_vip_count"]

        tot_mrr_ab = round(
            ga_stats["projected_mrr_net_try"]
            + gb_stats["projected_mrr_net_try"]
            + ann_stats["projected_mrr_net_try"]
            + leg_stats["projected_mrr_net_try"],
            2,
        )
        tot_cash_ab = round(
            ga_stats["realized_net_try"]
            + gb_stats["realized_net_try"]
            + ann_stats["realized_net_try"]
            + leg_stats["realized_net_try"],
            2,
        )
        tot_act_ab = (
            ga_stats["active_vip_count"]
            + gb_stats["active_vip_count"]
            + ann_stats["active_vip_count"]
            + leg_stats["active_vip_count"]
            + code_stats["active_vip_count"]
        )
        if tot_mrr_ab > 0:
            ga_stats["mrr_share_pct"] = round((ga_stats["projected_mrr_net_try"] / tot_mrr_ab) * 100.0, 1)
            gb_stats["mrr_share_pct"] = round((gb_stats["projected_mrr_net_try"] / tot_mrr_ab) * 100.0, 1)
            ann_stats["mrr_share_pct"] = round((ann_stats["projected_mrr_net_try"] / tot_mrr_ab) * 100.0, 1)
            leg_stats["mrr_share_pct"] = round((leg_stats["projected_mrr_net_try"] / tot_mrr_ab) * 100.0, 1)

        if ga_stats["started_subs_count"] > 0 or gb_stats["started_subs_count"] > 0:
            if ga_stats["projected_mrr_net_try"] > gb_stats["projected_mrr_net_try"]:
                lead_var = "group_a_paid_intro"
                win_badge = f"🔥 Grup A Önde ({ga_stats['active_subs_count']} Aktif • {ga_stats['projected_mrr_net_try']:.2f} ₺ Net MRR)"
                win_diag = (
                    f"🔥 Grup A (İlk Ay %67 İndirim • 49.99 ₺) anlık nakit akışı ({ga_stats['day0_realized_net_try']:.2f} ₺ Net) ve "
                    f"beklenen Net MRR ({ga_stats['projected_mrr_net_try']:.2f} ₺/Ay) ile Grup B'nin ({gb_stats['projected_mrr_net_try']:.2f} ₺/Ay) önünde."
                )
            elif gb_stats["projected_mrr_net_try"] > ga_stats["projected_mrr_net_try"]:
                lead_var = "group_b_free_trial_1m"
                win_badge = f"🎁 Grup B Önde ({gb_stats['active_subs_count']} Aktif • +{gb_stats['projected_mrr_net_try']:.2f} ₺ Net MRR)"
                win_diag = (
                    f"🎁 Grup B (İlk Ay Ücretsiz • 30 Gün 0 ₺) 30 günlük deneme havuzu (+{gb_stats['pipeline_30d_net_try']:.2f} ₺ Net) ve "
                    f"beklenen Net MRR ({gb_stats['projected_mrr_net_try']:.2f} ₺/Ay) ile Grup A'nın ({ga_stats['projected_mrr_net_try']:.2f} ₺/Ay) önünde."
                )
            else:
                lead_var = "tied"
                win_badge = "⚖️ Grup A ve Grup B Başa Baş"
                win_diag = "Grup A (İlk Ay 49.99 ₺) ve Grup B (İlk Ay 0 ₺) şu an eşit MRR katkısında; 30. gün vade dönüşümü izleniyor."
        elif ab_a_pw_u > 0 or ab_b_pw_u > 0:
            lead_var = "collecting_telemetry"
            win_badge = f"🧪 Canlı Telemetri Aktif (A: {ab_a_pw_u} / B: {ab_b_pw_u} Cihaz)"
            win_diag = f"Paywall A/B sinyalleri toplanıyor (🔥 Grup A: {ab_a_pw_u} görüntüleme / {ab_a_cta_u} CTA • 🎁 Grup B: {ab_b_pw_u} görüntüleme / {ab_b_cta_u} CTA)."
        else:
            lead_var = "collecting_data"
            win_badge = f"🧪 A/B Testi Canlı (%50 Grup A • %50 Grup B)"
            win_diag = (
                f"RevenueCat %50/%50 Paywall A/B testi aktif (🔥 Grup A: İlk Ay 49.99 ₺ vs 🎁 Grup B: İlk Ay 30G 0 ₺). "
                f"Mevcut portföyde 👑 {ann_stats['active_subs_count']} Yıllık VIP ve {leg_stats['active_subs_count']} Tarihsel Aylık/7G abone korunuyor."
            )

        ga_obj = {
            "key": "group_a_paid_intro",
            "label": "🔥 Grup A: İlk Ay %67 İndirim (₺49,99 ➔ ₺149,99/ay)",
            "short_label": "🔥 Grup A (İlk Ay ₺49,99)",
            "offer_type": "intro_1m_discounted",
            **ga_stats,
        }
        gb_obj = {
            "key": "group_b_free_trial_1m",
            "label": "🎁 Grup B: İlk Ay Ücretsiz (30 Gün ₺0 ➔ ₺149,99/ay)",
            "short_label": "🎁 Grup B (30 Gün ₺0)",
            "offer_type": "free_trial_1m",
            **gb_stats,
        }
        ann_obj = {
            "key": "annual_anchor",
            "label": "👑 Yıllık VIP Çıpa (₺599,99/Yıl • %67 Tasarruf)",
            "short_label": "👑 Yıllık VIP (₺599,99)",
            "offer_type": "standard_paid",
            **ann_stats,
        }
        leg_obj = {
            "key": "legacy_and_other",
            "label": "⏳ Tarihsel 7G Deneme & Standart Aylık / 🎟️ Kodlu VIP",
            "legacy_7d_active_trials_count": sum(
                1 for s_it in legacy_7d_subs
                if s_it.get("status") == "intro_free_trial" and bool(s_it.get("auto_renew_enabled", True))
            ),
            "legacy_7d_converted_paid_count": sum(1 for s_it in (legacy_7d_subs + std_m_subs) if s_it.get("status") == "paid_active"),
            "offer_code_active_count": sum(1 for s_it in code_subs if s_it.get("status") == "offer_code_trial"),
            **leg_stats,
        }
        code_obj = {
            "key": "offer_code_vip",
            "label": "🎟️ Teklif Kodu VIP",
            **code_stats,
        }
        return {
            "experiment_id": "paywall_monthly_intro_vs_free_trial_v1",
            "platform": plat_filter,
            "experiment_name": "RevenueCat Paywall A/B Testi: İlk Ay %67 İndirim (₺49,99) vs İlk Ay Ücretsiz (30 Gün ₺0)",
            "split_ratio": "50% Grup A (paid_intro) / 50% Grup B (free_trial_1m)",
            "group_a": ga_obj,
            "group_a_paid_intro": ga_obj,
            "group_b": gb_obj,
            "group_b_free_trial_1m": gb_obj,
            "annual_anchor": ann_obj,
            "legacy_7d_trial": leg_obj,
            "legacy_and_other": leg_obj,
            "offer_code_vip": code_obj,
            "winner_badge": win_badge,
            "winner_diagnosis_tr": win_diag,
            "total_active_vip": tot_act_ab,
            "total_projected_mrr_net_try": tot_mrr_ab,
            "total_realized_net_try": tot_cash_ab,
            "winner_summary": {
                "leading_variant": lead_var,
                "badge": win_badge,
                "diagnosis_tr": win_diag,
            },
        }

    ab_experiment_all = _build_ab_experiment_comparison("all")
    ab_experiment_ios = _build_ab_experiment_comparison("ios")
    ab_experiment_android = _build_ab_experiment_comparison("android")
    ab_experiment_by_platform = {
        "all": ab_experiment_all,
        "ios": ab_experiment_ios,
        "android": ab_experiment_android,
    }
    financial_ledger["ab_experiment"] = ab_experiment_all
    financial_ledger["active_30d_trials_count"] = ab_experiment_all["group_b_free_trial_1m"]["active_trials_count"]
    financial_ledger["active_30d_mrr_net_try"] = ab_experiment_all["group_b_free_trial_1m"]["pipeline_trial_mrr_net_try"]
    financial_ledger["active_legacy_7d_trials_count"] = ab_experiment_all["legacy_and_other"]["legacy_7d_active_trials_count"]
    financial_ledger["active_legacy_7d_mrr_net_try"] = ab_experiment_all["legacy_and_other"]["pipeline_trial_mrr_net_try"]
    financial_ledger["group_a_paid_intro_active_count"] = ab_experiment_all["group_a_paid_intro"]["active_subs_count"]

    def _enrich_onboarding_funnel_with_ab_purchases(
        onb_obj: Dict[str, Any],
        ab_obj: Dict[str, Any],
        ab_ios_obj: Dict[str, Any],
        ab_and_obj: Dict[str, Any],
        plat_key: str,
    ) -> None:
        ga_d = ab_obj.get("group_a") or {}
        gb_d = ab_obj.get("group_b") or {}
        ann_d = ab_obj.get("annual_anchor") or {}
        leg_d = ab_obj.get("legacy_and_other") or {}
        code_d = ab_obj.get("offer_code_vip") or {}

        sig_a = int(onb_obj.get("ab_a_vip_started_unique_devices", 0) or 0)
        sig_b = int(onb_obj.get("ab_b_vip_started_unique_devices", 0) or 0)
        sig_tot = int(onb_obj.get("vip_started_unique_devices", 0) or 0)

        led_a = int(ga_d.get("started_vip_count", 0) or 0)
        led_b = int(gb_d.get("started_vip_count", 0) or 0)
        led_ann = int(ann_d.get("started_vip_count", 0) or 0)
        led_leg = int(leg_d.get("started_vip_count", 0) or 0) + int(code_d.get("started_vip_count", 0) or 0)

        eff_a = max(led_a, sig_a)
        eff_b = max(led_b, sig_b)
        eff_ann = led_ann
        eff_tot = max(eff_a + eff_b + eff_ann + led_leg, sig_tot)

        ga_ios_d = ab_ios_obj.get("group_a") or {}
        gb_ios_d = ab_ios_obj.get("group_b") or {}
        ann_ios_d = ab_ios_obj.get("annual_anchor") or {}
        leg_ios_d = ab_ios_obj.get("legacy_and_other") or {}
        code_ios_d = ab_ios_obj.get("offer_code_vip") or {}
        ios_a = max(int(ga_ios_d.get("started_vip_count", 0) or 0), int(onboarding_step_funnel_ios.get("ab_a_vip_started_unique_devices", 0) or 0))
        ios_b = max(int(gb_ios_d.get("started_vip_count", 0) or 0), int(onboarding_step_funnel_ios.get("ab_b_vip_started_unique_devices", 0) or 0))
        ios_ann = int(ann_ios_d.get("started_vip_count", 0) or 0)
        ios_leg = int(leg_ios_d.get("started_vip_count", 0) or 0) + int(code_ios_d.get("started_vip_count", 0) or 0)
        ios_tot = max(ios_a + ios_b + ios_ann + ios_leg, int(onboarding_step_funnel_ios.get("vip_started_unique_devices", 0) or 0))

        ga_and_d = ab_and_obj.get("group_a") or {}
        gb_and_d = ab_and_obj.get("group_b") or {}
        ann_and_d = ab_and_obj.get("annual_anchor") or {}
        leg_and_d = ab_and_obj.get("legacy_and_other") or {}
        code_and_d = ab_and_obj.get("offer_code_vip") or {}
        and_a = max(int(ga_and_d.get("started_vip_count", 0) or 0), int(onboarding_step_funnel_android.get("ab_a_vip_started_unique_devices", 0) or 0))
        and_b = max(int(gb_and_d.get("started_vip_count", 0) or 0), int(onboarding_step_funnel_android.get("ab_b_vip_started_unique_devices", 0) or 0))
        and_ann = int(ann_and_d.get("started_vip_count", 0) or 0)
        and_leg = int(leg_and_d.get("started_vip_count", 0) or 0) + int(code_and_d.get("started_vip_count", 0) or 0)
        and_tot = max(and_a + and_b + and_ann + and_leg, int(onboarding_step_funnel_android.get("vip_started_unique_devices", 0) or 0))

        if plat_key == "ios":
            row_ios_a, row_ios_b, row_ios_tot = ios_a, ios_b, ios_tot
            row_and_a, row_and_b, row_and_tot = 0, 0, 0
        elif plat_key == "android":
            row_ios_a, row_ios_b, row_ios_tot = 0, 0, 0
            row_and_a, row_and_b, row_and_tot = and_a, and_b, and_tot
        else:
            row_ios_a, row_ios_b, row_ios_tot = ios_a, ios_b, ios_tot
            row_and_a, row_and_b, row_and_tot = and_a, and_b, and_tot

        st_base = int(onb_obj.get("start_base_devices", 0) or 0)
        st9_devs = int(onb_obj.get("step9_reached_devices", 0) or 0)
        pw_views = max(st9_devs, int(onb_obj.get("paywall_viewed_unique_devices", 0) or 0))
        step9_to_purch_pct = (
            min(100.0, round((eff_tot / pw_views) * 100.0, 1))
            if pw_views > 0
            else None
        )
        step0_to_purch_pct = (
            min(100.0, round((eff_tot / st_base) * 100.0, 1))
            if st_base > 0
            else None
        )
        step9_drop_cnt = max(0, pw_views - eff_tot) if pw_views > 0 else 0
        step9_drop_pct = (
            max(0.0, round(((pw_views - eff_tot) / pw_views) * 100.0, 1))
            if pw_views > 0
            else None
        )

        onb_obj["ab_a_purchases_count"] = eff_a
        onb_obj["ab_b_purchases_count"] = eff_b
        onb_obj["annual_purchases_count"] = eff_ann
        onb_obj["legacy_or_code_purchases_count"] = led_leg
        onb_obj["total_purchases_count"] = eff_tot
        onb_obj["ios_purchases_count"] = row_ios_tot
        onb_obj["android_purchases_count"] = row_and_tot
        onb_obj["ios_ab_a_purchases_count"] = row_ios_a
        onb_obj["ios_ab_b_purchases_count"] = row_ios_b
        onb_obj["android_ab_a_purchases_count"] = row_and_a
        onb_obj["android_ab_b_purchases_count"] = row_and_b
        onb_obj["step9_to_purchase_cvr_pct"] = step9_to_purch_pct
        onb_obj["step0_to_purchase_cvr_pct"] = step0_to_purch_pct
        onb_obj["step9_to_purchase_dropoff_count"] = step9_drop_cnt
        onb_obj["step9_to_purchase_dropoff_pct"] = step9_drop_pct
        onb_obj["purchase_summary"] = {
            "group_a_purchases": eff_a,
            "group_b_purchases": eff_b,
            "annual_purchases": eff_ann,
            "legacy_or_code_purchases": led_leg,
            "total_purchases": eff_tot,
            "ios_total_purchases": row_ios_tot,
            "android_total_purchases": row_and_tot,
            "ios_group_a_purchases": row_ios_a,
            "ios_group_b_purchases": row_ios_b,
            "android_group_a_purchases": row_and_a,
            "android_group_b_purchases": row_and_b,
            "step9_to_purchase_cvr_pct": step9_to_purch_pct,
            "step0_to_purchase_cvr_pct": step0_to_purch_pct,
            "dropoff_from_paywall_count": step9_drop_cnt,
            "dropoff_from_paywall_pct": step9_drop_pct,
        }

        ab_cohorts_map = onb_obj.get("ab_cohorts")
        if isinstance(ab_cohorts_map, dict):
            for c_key in ("group_a", "group_b"):
                c_onb = ab_cohorts_map.get(c_key)
                if not isinstance(c_onb, dict):
                    continue
                if c_key == "group_a":
                    c_eff_a, c_eff_b, c_eff_ann, c_eff_leg = eff_a, 0, 0, 0
                    c_eff_tot = eff_a
                    c_ios_a, c_ios_b, c_ios_tot = row_ios_a, 0, row_ios_a
                    c_and_a, c_and_b, c_and_tot = row_and_a, 0, row_and_a
                    c_pw_views = max(int(c_onb.get("step9_reached_devices", 0) or 0), int(c_onb.get("ab_a_paywall_viewed_unique_devices", 0) or 0))
                else:
                    c_eff_a, c_eff_b, c_eff_ann, c_eff_leg = 0, eff_b, 0, 0
                    c_eff_tot = eff_b
                    c_ios_a, c_ios_b, c_ios_tot = 0, row_ios_b, row_ios_b
                    c_and_a, c_and_b, c_and_tot = 0, row_and_b, row_and_b
                    c_pw_views = max(int(c_onb.get("step9_reached_devices", 0) or 0), int(c_onb.get("ab_b_paywall_viewed_unique_devices", 0) or 0))
                c_st_base = int(c_onb.get("start_base_devices", 0) or 0)
                c_step9_cvr = min(100.0, round((c_eff_tot / c_pw_views) * 100.0, 1)) if c_pw_views > 0 else None
                c_step0_cvr = min(100.0, round((c_eff_tot / c_st_base) * 100.0, 1)) if c_st_base > 0 else None
                c_drop_cnt = max(0, c_pw_views - c_eff_tot) if c_pw_views > 0 else 0
                c_drop_pct = max(0.0, round(((c_pw_views - c_eff_tot) / c_pw_views) * 100.0, 1)) if c_pw_views > 0 else None
                c_onb["ab_a_purchases_count"] = c_eff_a
                c_onb["ab_b_purchases_count"] = c_eff_b
                c_onb["annual_purchases_count"] = c_eff_ann
                c_onb["legacy_or_code_purchases_count"] = c_eff_leg
                c_onb["total_purchases_count"] = c_eff_tot
                c_onb["ios_purchases_count"] = c_ios_tot
                c_onb["android_purchases_count"] = c_and_tot
                c_onb["ios_ab_a_purchases_count"] = c_ios_a
                c_onb["ios_ab_b_purchases_count"] = c_ios_b
                c_onb["android_ab_a_purchases_count"] = c_and_a
                c_onb["android_ab_b_purchases_count"] = c_and_b
                c_onb["step9_to_purchase_cvr_pct"] = c_step9_cvr
                c_onb["step0_to_purchase_cvr_pct"] = c_step0_cvr
                c_onb["step9_to_purchase_dropoff_count"] = c_drop_cnt
                c_onb["step9_to_purchase_dropoff_pct"] = c_drop_pct
            ab_cohorts_map["all"] = {
                k: v for k, v in onb_obj.items() if k != "ab_cohorts"
            }

    _enrich_onboarding_funnel_with_ab_purchases(
        onboarding_step_funnel_all, ab_experiment_all, ab_experiment_ios, ab_experiment_android, "all"
    )
    _enrich_onboarding_funnel_with_ab_purchases(
        onboarding_step_funnel_ios, ab_experiment_ios, ab_experiment_ios, ab_experiment_android, "ios"
    )
    _enrich_onboarding_funnel_with_ab_purchases(
        onboarding_step_funnel_android, ab_experiment_android, ab_experiment_ios, ab_experiment_android, "android"
    )

    if period == "all":
        ios_paid_cnt = int(plat_fin["ios"]["paid_cnt"])
        ios_trial_cnt = int(plat_fin["ios"]["trial_cnt"])
        ios_code_cnt = int(plat_fin["ios"]["code_cnt"])
        ios_cancelled_cnt = int(plat_fin["ios"]["cancelled_cnt"])
        ios_active_cnt = ios_paid_cnt + ios_trial_cnt + ios_code_cnt
        ios_mrr_net = round(plat_fin["ios"]["paid_mrr_net"] + plat_fin["ios"]["pipeline_mrr_net"], 2)
        ios_mrr_gross = round(plat_fin["ios"]["paid_mrr_gross"] + plat_fin["ios"]["pipeline_mrr_gross"], 2)
        ios_realized_net = round(plat_fin["ios"]["realized_net"], 2)

        and_paid_cnt = int(plat_fin["android"]["paid_cnt"])
        and_trial_cnt = int(plat_fin["android"]["trial_cnt"])
        and_code_cnt = int(plat_fin["android"]["code_cnt"])
        and_cancelled_cnt = int(plat_fin["android"]["cancelled_cnt"])
        and_active_cnt = and_paid_cnt + and_trial_cnt + and_code_cnt
        and_mrr_net = round(plat_fin["android"]["paid_mrr_net"] + plat_fin["android"]["pipeline_mrr_net"], 2)
        and_mrr_gross = round(plat_fin["android"]["paid_mrr_gross"] + plat_fin["android"]["pipeline_mrr_gross"], 2)
        and_realized_net = round(plat_fin["android"]["realized_net"], 2)
    else:
        ios_paid_cnt = sum(1 for s in ios_subs_list if s.get("status") == "paid_active")
        ios_trial_cnt = sum(1 for s in ios_subs_list if s.get("status") == "intro_free_trial" and s.get("auto_renew_enabled"))
        ios_code_cnt = sum(1 for s in ios_subs_list if s.get("status") == "offer_code_trial")
        ios_cancelled_cnt = sum(1 for s in ios_subs_list if s.get("status") == "cancelled" or (s.get("status") != "paid_active" and not s.get("auto_renew_enabled")))
        ios_active_cnt = ios_paid_cnt + ios_trial_cnt + ios_code_cnt
        ios_realized_net = round(float(win_selected.get("ios_net_try", 0.0) or 0.0), 2)
        ios_mrr_net = round(
            sum(
                (float(s.get("expected_next_proceeds_try") or s.get("developer_proceeds_try") or 0.0) / (12.0 if _is_annual_product(s.get("product_id")) else 1.0))
                for s in ios_subs_list
                if s.get("auto_renew_enabled") and s.get("status") in ("paid_active", "intro_free_trial")
            ),
            2,
        )
        ios_mrr_gross = round(
            sum(
                (float(s.get("expected_next_price_try") or s.get("customer_price_try") or 0.0) / (12.0 if _is_annual_product(s.get("product_id")) else 1.0))
                for s in ios_subs_list
                if s.get("auto_renew_enabled") and s.get("status") in ("paid_active", "intro_free_trial")
            ),
            2,
        )

        and_paid_cnt = sum(1 for s in android_subs_list if s.get("status") == "paid_active")
        and_trial_cnt = sum(1 for s in android_subs_list if s.get("status") == "intro_free_trial" and s.get("auto_renew_enabled"))
        and_code_cnt = sum(1 for s in android_subs_list if s.get("status") == "offer_code_trial")
        and_cancelled_cnt = sum(1 for s in android_subs_list if s.get("status") == "cancelled" or (s.get("status") != "paid_active" and not s.get("auto_renew_enabled")))
        and_active_cnt = and_paid_cnt + and_trial_cnt + and_code_cnt
        and_realized_net = round(float(win_selected.get("android_net_try", 0.0) or 0.0), 2)
        and_mrr_net = round(
            sum(
                (float(s.get("expected_next_proceeds_try") or s.get("developer_proceeds_try") or 0.0) / (12.0 if _is_annual_product(s.get("product_id")) else 1.0))
                for s in android_subs_list
                if s.get("auto_renew_enabled") and s.get("status") in ("paid_active", "intro_free_trial")
            ),
            2,
        )
        and_mrr_gross = round(
            sum(
                (float(s.get("expected_next_price_try") or s.get("customer_price_try") or 0.0) / (12.0 if _is_annual_product(s.get("product_id")) else 1.0))
                for s in android_subs_list
                if s.get("auto_renew_enabled") and s.get("status") in ("paid_active", "intro_free_trial")
            ),
            2,
        )
        active_vip_total = ios_active_cnt + and_active_cnt
        cancelled_cnt = ios_cancelled_cnt + and_cancelled_cnt
        apple_vip = active_vip_total
        paid_subs_cnt = ios_paid_cnt + and_paid_cnt
        intro_trial_cnt = ios_trial_cnt + and_trial_cnt
        offer_code_cnt = ios_code_cnt + and_code_cnt
        all_churn_rate_pct = (
            round((cancelled_cnt / len(subscriber_ledger_list)) * 100, 1)
            if len(subscriber_ledger_list) > 0
            else 0.0
        )

    all_reviews = sb.get("store_reviews") or []
    ios_reviews_list = [r for r in all_reviews if r.get("store") == "App Store" or r.get("platform") == "ios"]
    android_reviews_list = [r for r in all_reviews if r.get("store") == "Google Play" or r.get("platform") == "android"]
    ios_reviews_cnt = len(ios_reviews_list)
    android_reviews_cnt = len(android_reviews_list)

    def _build_star_distribution(
        rev_items: List[Dict[str, Any]],
        overall_rating: float = 0.0,
        overall_count: int = 0,
    ) -> Dict[str, Any]:
        written_counts: Dict[int, int] = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
        for r_it in rev_items:
            st_v = max(1, min(5, int(r_it.get("rating", 5) or 5)))
            written_counts[st_v] = written_counts.get(st_v, 0) + 1
        written_cnt = len(rev_items)
        written_sum = sum(st_k * st_c for st_k, st_c in written_counts.items())
        written_avg = round(written_sum / written_cnt, 1) if written_cnt > 0 else 0.0

        eff_overall_cnt = max(written_cnt, int(overall_count or 0))
        eff_overall_avg = (
            round(float(overall_rating), 1)
            if (float(overall_rating or 0.0) > 0 and eff_overall_cnt > 0)
            else written_avg
        )
        silent_ratings_cnt = max(0, eff_overall_cnt - written_cnt)

        # Yorumsuz oyları (silent_ratings_cnt) mağaza genel puanı (eff_overall_avg) ile matematiksel mutabakata sokarak
        # 5★..1★ toplam oy çubuklarına dağıt (böylece toplam oy çubuğu mağazadaki gerçek oy dağılımını birebir gösterir)
        total_counts: Dict[int, int] = dict(written_counts)
        silent_counts: Dict[int, int] = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
        if silent_ratings_cnt > 0:
            target_total_points = int(round(eff_overall_avg * eff_overall_cnt))
            rem_points = max(silent_ratings_cnt, min(5 * silent_ratings_cnt, target_total_points - written_sum))
            rem_votes = silent_ratings_cnt
            for st_lvl in (5, 4, 3, 2, 1):
                if rem_votes <= 0:
                    break
                if st_lvl == 1:
                     take = rem_votes
                else:
                    # Kalan oyların en az 1'er puan alabilmesi için bu yıldız seviyesine verilebilecek maksimum oy
                    max_possible = (rem_points - rem_votes) // (st_lvl - 1)
                    take = max(0, min(rem_votes, int(max_possible)))
                if take > 0:
                    silent_counts[st_lvl] += take
                    total_counts[st_lvl] += take
                    rem_votes -= take
                    rem_points -= take * st_lvl

        denom_cnt = eff_overall_cnt if eff_overall_cnt > 0 else written_cnt
        bars: List[Dict[str, Any]] = []
        for s_lvl in (5, 4, 3, 2, 1):
            tot_c = total_counts[s_lvl]
            wr_c = written_counts[s_lvl]
            sil_c = silent_counts[s_lvl]
            pct_val = round((tot_c / denom_cnt) * 100, 1) if denom_cnt > 0 else 0.0
            bars.append({
                "star": s_lvl,
                "count": tot_c,
                "written_count": wr_c,
                "silent_count": sil_c,
                "pct": pct_val,
            })
        return {
            "written_count": written_cnt,
            "written_avg": written_avg,
            "written_avg_str": f"★ {written_avg}" if written_cnt > 0 else "Yorum Yok",
            "overall_count": eff_overall_cnt,
            "overall_avg": eff_overall_avg,
            "overall_avg_str": f"★ {eff_overall_avg}" if eff_overall_cnt > 0 else "Yorum Yok",
            "silent_ratings_count": silent_ratings_cnt,
            "counts": {str(k): v for k, v in total_counts.items()},
            "written_counts": {str(k): v for k, v in written_counts.items()},
            "bars": bars,
        }

    ios_overall_r = float(sb.get("apple_overall_rating", 0.0) or 0.0)
    ios_overall_c = int(sb.get("apple_overall_ratings_count", 0) or 0)
    if ios_overall_r <= 0 or ios_overall_c <= 0:
        live_it_r, live_it_c = _get_live_apple_itunes_rating()
        if live_it_r > 0 and live_it_c > 0:
            ios_overall_r = live_it_r
            ios_overall_c = live_it_c
            sb["apple_overall_rating"] = live_it_r
            sb["apple_overall_ratings_count"] = live_it_c
    and_overall_r = float(sb.get("google_overall_rating", 0.0) or 0.0)
    and_overall_c = int(sb.get("google_overall_ratings_count", 0) or 0)
    for cfg_r in cfg_rows:
        if cfg_r.channel_key == "apple_search_ads" and float(cfg_r.store_rating or 0.0) > 0 and ios_overall_r <= 0:
            ios_overall_r = float(cfg_r.store_rating)
            ios_overall_c = max(ios_overall_c, int(cfg_r.store_reviews_count or 0))
        elif cfg_r.channel_key == "google_play_organic" and float(cfg_r.store_rating or 0.0) > 0 and and_overall_r <= 0:
            and_overall_r = float(cfg_r.store_rating)
            and_overall_c = max(and_overall_c, int(cfg_r.store_reviews_count or 0))

    ios_star_dist = _build_star_distribution(ios_reviews_list, ios_overall_r, ios_overall_c)
    android_star_dist = _build_star_distribution(android_reviews_list, and_overall_r, and_overall_c)
    comb_overall_cnt = ios_star_dist["overall_count"] + android_star_dist["overall_count"]
    comb_overall_avg = (
        round(
            (
                (ios_star_dist["overall_avg"] * ios_star_dist["overall_count"])
                + (android_star_dist["overall_avg"] * android_star_dist["overall_count"])
            )
            / comb_overall_cnt,
            1,
        )
        if comb_overall_cnt > 0
        else 0.0
    )
    all_star_dist = _build_star_distribution(all_reviews, comb_overall_avg, comb_overall_cnt)
    reviews_star_distribution = {
        "all": all_star_dist,
        "ios": ios_star_dist,
        "android": android_star_dist,
    }

    all_avg_stars_str = all_star_dist["overall_avg_str"]
    ios_avg_stars_str = ios_star_dist["overall_avg_str"]
    android_avg_stars_str = android_star_dist["overall_avg_str"]

    pulse_state_row = (
        db.query(StoreSyncState)
        .filter(StoreSyncState.state_key == "active_satisfaction_pulse")
        .first()
    )
    raw_pulse_snap = (
        dict(pulse_state_row.snapshot_json)
        if (pulse_state_row and isinstance(pulse_state_row.snapshot_json, dict))
        else {}
    )
    satisfaction_pulse = {
        "pulse_id": str(raw_pulse_snap.get("pulse_id") or ""),
        "active": bool(raw_pulse_snap.get("active", False)),
        "target_platform": str(raw_pulse_snap.get("target_platform") or "ios"),
        "topic_key": str(raw_pulse_snap.get("topic_key") or "sleep_save_fix"),
        "title_tr": str(raw_pulse_snap.get("title_tr") or "Uyku ve uyanma saatleri kaydı iyileştirildi"),
        "question_tr": str(raw_pulse_snap.get("question_tr") or "Son güncellememizden sonra uyku kayıtlarınız sorunsuz çalışıyor mu?"),
        "reference_author": str(raw_pulse_snap.get("reference_author") or ""),
        "reference_review_id": str(raw_pulse_snap.get("reference_review_id") or ""),
        "triggered_at": str(raw_pulse_snap.get("triggered_at") or ""),
        "shown_count": int(raw_pulse_snap.get("shown_count", 0) or 0),
        "satisfied_count": int(raw_pulse_snap.get("satisfied_count", 0) or 0),
        "issue_persists_count": int(raw_pulse_snap.get("issue_persists_count", 0) or 0),
    }

    ios_total_rec = len(ios_subs_list)
    and_total_rec = len(android_subs_list)
    all_total_rec = len(subscriber_ledger_list)

    ios_churn_rate_pct = round((ios_cancelled_cnt / ios_total_rec) * 100, 1) if ios_total_rec > 0 else 0.0
    and_churn_rate_pct = round((and_cancelled_cnt / and_total_rec) * 100, 1) if and_total_rec > 0 else 0.0
    all_retention_rate_pct = round(100.0 - all_churn_rate_pct, 1) if all_total_rec > 0 else 0.0
    ios_retention_rate_pct = round(100.0 - ios_churn_rate_pct, 1) if ios_total_rec > 0 else 0.0
    and_retention_rate_pct = round(100.0 - and_churn_rate_pct, 1) if and_total_rec > 0 else 0.0

    all_started_vip_of_dl_pct = min(100.0, round((all_total_rec / max(1, total_cumulative_downloads)) * 100, 1)) if total_cumulative_downloads > 0 else 0.0
    ios_started_vip_of_dl_pct = min(100.0, round((ios_total_rec / max(1, apple_downloads)) * 100, 1)) if apple_downloads > 0 else 0.0
    and_started_vip_of_dl_pct = min(100.0, round((and_total_rec / max(1, google_play_downloads)) * 100, 1)) if google_play_downloads > 0 else 0.0

    ios_vip_sub_str = (
        f"Toplam {ios_total_rec} Kayıt ({ios_active_cnt} Aktif • {ios_cancelled_cnt} İptal / %{ios_churn_rate_pct} Churn) — "
        f"{ios_paid_cnt} Ücretli ({ios_realized_net:.2f} ₺) • {ios_trial_cnt} 7G Deneme (+{plat_fin['ios']['pipeline_net']:.2f} ₺) • {ios_code_cnt} Kodlu"
        if ios_cancelled_cnt > 0
        else f"{ios_paid_cnt} Ücretli ({ios_realized_net:.2f} ₺) • {ios_trial_cnt} 7G Deneme (+{plat_fin['ios']['pipeline_net']:.2f} ₺) • {ios_code_cnt} Kodlu"
    )
    and_vip_sub_str = (
        f"{and_active_cnt} Aktif Android VIP (Toplam {and_total_rec} Kayıt • {and_cancelled_cnt} İptal / %{and_churn_rate_pct} Churn) — "
        f"{and_paid_cnt} Ücretli ({and_realized_net:.2f} ₺) • {and_trial_cnt} 7G Deneme (+{plat_fin['android']['pipeline_net']:.2f} ₺) • {and_code_cnt} Kodlu"
        if and_total_rec > 0
        else f"0 Aktif Abone • Google Play API'de {len(gp_catalog)} Aktif Paket (599.99 ₺/Yıl & 149.99 ₺/Ay) Yayında"
    )

    imp_search_pct_calc = (
        round((imp_search_val / max(1, imp_search_val + imp_browse_val)) * 100)
        if (imp_search_val + imp_browse_val) > 0
        else 0
    )

    android_imp_display = f"{google_play_impressions:,}"
    android_touch_display = f"{android_touchpoints:,}"
    android_cvr_safe = (
        min(100.0, round((google_play_downloads / android_touchpoints) * 100, 1))
        if google_play_page_views > 0 and android_touchpoints > 0
        else (android_bridge_cvr_pct if android_bridge_uniq > 0 else 0.0)
    )
    android_store_or_bridge_cvr = android_store_page_cvr_pct if google_play_page_views > 0 else android_bridge_cvr_pct

    platform_split = {
        "all": {
            "key": "all",
            "label": "🌐 Kümülatif (Toplam — Apple + Google Play)",
            "impressions": total_cumulative_impressions,
            "impressions_display": f"{total_cumulative_impressions:,}",
            "impressions_sub": (
                f"🍏 {apple_impressions:,} App Store + Meta Reklam • 🤖 {google_play_impressions:,} Google Play + Meta Reklam"
                if google_play_impressions > 0
                else f"🍏 {apple_impressions:,} App Store + Meta Reklam • 🤖 Google Play Organik & Meta Reklam ({ig_android_count} Profil Tıkı)"
            ),
            "touchpoints": total_cumulative_visits_and_clicks,
            "touchpoints_display": f"{total_cumulative_visits_and_clicks:,}",
            "touchpoints_sub": f"🍏 {ios_touchpoints} iOS ({apple_page_views} Mağaza + {ios_bridge_uniq} Profil) • 🤖 {android_touchpoints} Android ({google_play_page_views} Mağaza + {android_bridge_uniq} Profil){desktop_sub_suffix}",
            "downloads": total_cumulative_downloads,
            "downloads_display": f"{total_cumulative_downloads}",
            "downloads_sub": f"🍏 {apple_downloads} iOS (%{round((apple_downloads / max(1, total_cumulative_downloads)) * 100)}) • 🤖 {google_play_downloads} Android (%{round((google_play_downloads / max(1, total_cumulative_downloads)) * 100)})",
            "vis_of_imp_pct": store_imp_to_pv_pct,
            "imp_breakdown_label": f"Mağaza: %{store_imp_to_pv_pct} + {effective_unique_bridge_clicks:,} Bio Köprü",
            "cvr_pct": all_vis_to_dl_cvr_pct,
            "store_cvr_pct": store_page_cvr_pct,
            "store_unique_cvr_pct": store_unique_cvr_pct,
            "bridge_cvr_pct": all_bridge_cvr_pct,
            "settled_cvr_pct": settled_cvr_pct,
            "desktop_bridge_clicks": desktop_bridge_uniq,
            "cvr_breakdown_label": f"Mağaza: %{store_page_cvr_pct} • Bio Köprü: %{all_bridge_cvr_pct}",
            "dl_of_imp_pct": round((total_cumulative_downloads / max(1, total_cumulative_impressions)) * 100, 2) if total_cumulative_impressions > 0 else 0.0,
            "started_vip_of_dl_pct": all_started_vip_of_dl_pct,
            "vip_of_dl_pct": round((active_vip_total / max(1, total_cumulative_downloads)) * 100, 1),
            "vip_of_vis_pct": round((active_vip_total / max(1, total_cumulative_visits_and_clicks)) * 100, 2),
            "vip_of_imp_pct": round((active_vip_total / max(1, total_cumulative_impressions)) * 100, 2) if total_cumulative_impressions > 0 else 0.0,
            "vip_count": active_vip_total,
            "total_vip_count": all_total_rec,
            "cancelled_vip_count": cancelled_cnt,
            "churn_rate_pct": all_churn_rate_pct,
            "retention_rate_pct": all_retention_rate_pct,
            "started_vip_display": f"{all_total_rec}",
            "cancelled_vip_display": f"{cancelled_cnt}",
            "vip_display": f"{active_vip_total} Net Abone" if cancelled_cnt > 0 else f"{active_vip_total} VIP",
            "started_vip_sub": f"Toplam {all_total_rec} Başlayan VIP (🍏 {ios_total_rec} iOS • 🤖 {and_total_rec} Android — Kurulumdan %{all_started_vip_of_dl_pct} Dönüşüm)",
            "cancelled_vip_sub": f"Toplam {cancelled_cnt} İptal / Yenileme Kapalı (🍏 {ios_cancelled_cnt} iOS • 🤖 {and_cancelled_cnt} Android — %{all_churn_rate_pct} Churn)",
            "vip_sub": (
                f"🍏 {ios_active_cnt} Net ({ios_total_rec} Başlayan • {ios_cancelled_cnt} İptal) • "
                f"🤖 {and_active_cnt} Net ({and_total_rec} Başlayan • {and_cancelled_cnt} İptal) • %{all_retention_rate_pct} Tutundurma"
            ),
            "mrr_net_try": financial_ledger["projected_total_mrr_net_try"] if period == "all" else round(ios_mrr_net + and_mrr_net, 2),
            "mrr_gross_try": financial_ledger["projected_total_mrr_gross_try"] if period == "all" else round(ios_mrr_gross + and_mrr_gross, 2),
            "realized_net_try": financial_ledger["realized_net_proceeds_try"] if period == "all" else round(ios_realized_net + and_realized_net, 2),
            "reviews_count": len(all_reviews),
            "avg_rating_str": all_avg_stars_str,
            "star_distribution": all_star_dist,
            "delta_1": f"+{recent_3d_imp} (3G)" if period == "all" else period_label,
            "delta_2": f"+{today_unique_clicks} Bugün" if period == "all" else f"{effective_unique_bridge_clicks} Dönem Tıkı",
            "meta_chips_1": [f"{total_impressions_unique:,} Tekil Cihaz", f"%{imp_search_pct_calc} Arama"],
            "meta_chips_2": [f"{total_cumulative_store_page_views} Mağaza", f"{ig_unique_count:,} Instagram Profil"],
            "meta_chips_3": [f"🍏 {apple_downloads} iOS", f"🤖 {google_play_downloads} Android"],
            "meta_chips_4": [
                f"🍏 {ios_total_rec} iOS Başlangıç",
                f"🤖 {and_total_rec} Android Başlangıç",
            ],
            "meta_chips_5": [
                f"🍏 {ios_cancelled_cnt} iOS İptal",
                f"🤖 {and_cancelled_cnt} Android İptal",
                f"✖ %{all_churn_rate_pct} Churn",
            ],
            "meta_chips_6": [
                f"💳 {paid_subs_cnt} Ücretli",
                f"⏳ {intro_trial_cnt} Deneme",
                f"🎟️ {offer_code_cnt} Kod",
            ],
            "onboarding_step_funnel": onboarding_step_funnel_all,
            "ab_experiment": ab_experiment_all,
        },
        "ios": {
            "key": "ios",
            "label": "🍏 Apple App Store (iOS)",
            "impressions": apple_impressions,
            "impressions_display": f"{apple_impressions:,}",
            "impressions_sub": f"{ios_imp_uniq_display:,} tekil iPhone • {imp_search_val:,} Arama + {imp_browse_val} Keşfet • {ios_att_sdk_status_badge}",
            "touchpoints": ios_touchpoints,
            "touchpoints_display": f"{ios_touchpoints:,}",
            "touchpoints_sub": f"{apple_page_views} App Store Sayfası + {ig_ios_count} Instagram Profil iOS Tıkı",
            "downloads": apple_downloads,
            "downloads_display": f"{apple_downloads}",
            "downloads_sub": f"{r3_search} Arama • {r3_ref} Sosyal & Meta Reklam • {recent_ios_dl} Doğrudan Mağaza",
            "vis_of_imp_pct": ios_store_imp_to_pv_pct,
            "imp_breakdown_label": f"Mağaza: %{ios_store_imp_to_pv_pct} + {ig_ios_count:,} Bio Köprü",
            "cvr_pct": min(100.0, round((apple_downloads / max(1, ios_touchpoints)) * 100, 1)) if ios_touchpoints > 0 else 0.0,
            "store_cvr_pct": ios_store_page_cvr_pct,
            "store_unique_cvr_pct": ios_store_unique_cvr_pct,
            "bridge_cvr_pct": ios_bridge_cvr_pct,
            "settled_cvr_pct": min(100.0, round((apple_downloads / max(1, ios_touchpoints)) * 100, 1)) if ios_touchpoints > 0 else 0.0,
            "desktop_bridge_clicks": 0,
            "cvr_breakdown_label": f"Mağaza: %{ios_store_page_cvr_pct} (Cihaz: %{ios_store_unique_cvr_pct}) • Bio Köprü: %{ios_bridge_cvr_pct}",
            "dl_of_imp_pct": round((apple_downloads / max(1, apple_impressions)) * 100, 2) if apple_impressions > 0 else 0.0,
            "started_vip_of_dl_pct": ios_started_vip_of_dl_pct,
            "vip_of_dl_pct": round((ios_active_cnt / max(1, apple_downloads)) * 100, 1),
            "vip_of_vis_pct": round((ios_active_cnt / max(1, ios_touchpoints)) * 100, 2) if ios_touchpoints > 0 else 0.0,
            "vip_of_imp_pct": round((ios_active_cnt / max(1, apple_impressions)) * 100, 2) if apple_impressions > 0 else 0.0,
            "vip_count": ios_active_cnt,
            "total_vip_count": ios_total_rec,
            "cancelled_vip_count": ios_cancelled_cnt,
            "churn_rate_pct": ios_churn_rate_pct,
            "retention_rate_pct": ios_retention_rate_pct,
            "started_vip_display": f"{ios_total_rec}",
            "cancelled_vip_display": f"{ios_cancelled_cnt}",
            "vip_display": f"{ios_active_cnt} Net Abone" if ios_cancelled_cnt > 0 else f"{ios_active_cnt} VIP",
            "started_vip_sub": f"Toplam {ios_total_rec} Başlayan iOS VIP ({ios_active_cnt} Aktif • {ios_cancelled_cnt} İptal — Kurulumdan %{ios_started_vip_of_dl_pct} Dönüşüm)",
            "cancelled_vip_sub": f"Toplam {ios_cancelled_cnt} iOS İptal / Yenileme Kapalı (%{ios_churn_rate_pct} iOS Churn)",
            "vip_sub": ios_vip_sub_str,
            "mrr_net_try": ios_mrr_net,
            "mrr_gross_try": ios_mrr_gross,
            "realized_net_try": ios_realized_net,
            "reviews_count": ios_reviews_cnt,
            "avg_rating_str": ios_avg_stars_str,
            "star_distribution": ios_star_dist,
            "delta_1": f"%{round((apple_impressions / max(1, total_cumulative_impressions)) * 100)} Pay",
            "delta_2": f"%{ios_store_imp_to_pv_pct} Mağaza",
            "meta_chips_1": [f"{ios_imp_uniq_display:,} Tekil iPhone", "🎯 Meta Reklam Aktif"],
            "meta_chips_2": [f"{apple_page_views} Mağaza", f"{ig_ios_count:,} Instagram Profil"],
            "meta_chips_3": [f"🔍 {r3_search} Arama", f"📲 {r3_ref} Sosyal", f"📅 {recent_ios_dl} Doğrudan"],
            "meta_chips_4": [
                f"🟢 {ios_active_cnt} Aktif",
                f"✖ {ios_cancelled_cnt} İptal",
                f"%{ios_started_vip_of_dl_pct} Kurulumdan",
            ],
            "meta_chips_5": [
                f"✖ {ios_cancelled_cnt} iOS İptal",
                f"%{ios_churn_rate_pct} iOS Churn",
            ],
            "meta_chips_6": [
                f"💳 {ios_paid_cnt} Ücretli",
                f"⏳ {ios_trial_cnt} Deneme",
                f"🎟️ {ios_code_cnt} Kod",
            ],
            "onboarding_step_funnel": onboarding_step_funnel_ios,
            "ab_experiment": ab_experiment_ios,
        },
        "android": {
            "key": "android",
            "label": "🤖 Google Play Store (Android)",
            "impressions": google_play_impressions,
            "impressions_display": android_imp_display,
            "impressions_sub": (
                f"🤖 {google_play_impressions:,} Google Play & Meta Gösterimi • {ig_android_count} Instagram Profil Tıkı"
                if google_play_impressions > 0
                else f"🤖 Google Play Organik & Meta Reklam Kampanyası Aktif • {ig_android_count} Instagram Profil Tıkı"
            ),
            "touchpoints": android_touchpoints,
            "touchpoints_display": android_touch_display,
            "touchpoints_sub": (
                f"{google_play_page_views:,} Google Play Sayfa Ziyareti + {ig_android_count} Instagram Profil Tıkı ({direct_android_play_or_meta_installs} Play/Meta Kurulum)"
                if google_play_page_views > 0
                else f"Google Play Organik + Meta Reklam ({direct_android_play_or_meta_installs} Doğrudan Kurulum) + {ig_android_count} Instagram Profil Tıkı"
            ),
            "downloads": google_play_downloads,
            "downloads_display": f"{google_play_downloads}",
            "downloads_sub": f"{google_play_downloads} Android Kurulum ({direct_android_play_or_meta_installs} Google Play Organik & Meta + {matched_android_bio_installs} Instagram Profil)",
            "vis_of_imp_pct": android_store_imp_to_pv_pct,
            "imp_breakdown_label": f"Mağaza: %{android_store_imp_to_pv_pct} + {ig_android_count:,} Bio Köprü",
            "cvr_pct": android_cvr_safe,
            "store_cvr_pct": android_store_or_bridge_cvr,
            "store_unique_cvr_pct": android_store_or_bridge_cvr,
            "bridge_cvr_pct": android_bridge_cvr_pct,
            "settled_cvr_pct": android_cvr_safe,
            "desktop_bridge_clicks": 0,
            "cvr_breakdown_label": f"Mağaza: %{android_store_page_cvr_pct} • Bio Köprü: %{android_bridge_cvr_pct} • Native Intent Aktif",
            "dl_of_imp_pct": min(100.0, round((google_play_downloads / google_play_impressions) * 100, 2)) if google_play_impressions > 0 else 0.0,
            "started_vip_of_dl_pct": and_started_vip_of_dl_pct,
            "vip_of_dl_pct": round((and_active_cnt / max(1, google_play_downloads)) * 100, 1),
            "vip_of_vis_pct": round((and_active_cnt / android_touchpoints) * 100, 2) if android_touchpoints > 0 else 0.0,
            "vip_of_imp_pct": round((and_active_cnt / google_play_impressions) * 100, 2) if google_play_impressions > 0 else 0.0,
            "vip_count": and_active_cnt,
            "total_vip_count": and_total_rec,
            "cancelled_vip_count": and_cancelled_cnt,
            "churn_rate_pct": and_churn_rate_pct,
            "retention_rate_pct": and_retention_rate_pct,
            "started_vip_display": f"{and_total_rec}",
            "cancelled_vip_display": f"{and_cancelled_cnt}",
            "vip_display": f"{and_active_cnt} Net Abone" if and_cancelled_cnt > 0 else f"{and_active_cnt} VIP",
            "started_vip_sub": f"Toplam {and_total_rec} Başlayan Android VIP ({and_active_cnt} Aktif • {and_cancelled_cnt} İptal — Kurulumdan %{and_started_vip_of_dl_pct} Dönüşüm)",
            "cancelled_vip_sub": f"Toplam {and_cancelled_cnt} Android İptal / 72s Onaysız (%{and_churn_rate_pct} Android Churn)",
            "vip_sub": and_vip_sub_str,
            "mrr_net_try": and_mrr_net,
            "mrr_gross_try": and_mrr_gross,
            "realized_net_try": and_realized_net,
            "reviews_count": android_reviews_cnt,
            "avg_rating_str": android_avg_stars_str,
            "star_distribution": android_star_dist,
            "delta_1": f"%{round((google_play_impressions / max(1, total_cumulative_impressions)) * 100)} Pay",
            "delta_2": f"%{android_store_imp_to_pv_pct} Mağaza",
            "meta_chips_1": ["🤖 Google Play Organik", "🎯 Meta Reklam Aktif"],
            "meta_chips_2": [f"🏪 {google_play_page_views} Mağaza", f"📲 {ig_android_count:,} Instagram Profil"],
            "meta_chips_3": [f"🏪 {direct_android_play_or_meta_installs} Play & Meta", f"📲 {matched_android_bio_installs} Profil"],
            "meta_chips_4": [
                f"🟢 {and_active_cnt} Aktif",
                f"✖ {and_cancelled_cnt} İptal",
                f"%{and_started_vip_of_dl_pct} Kurulumdan",
            ],
            "meta_chips_5": [
                f"✖ {and_cancelled_cnt} Android İptal",
                f"%{and_churn_rate_pct} Android Churn",
            ],
            "meta_chips_6": [
                f"💳 {and_paid_cnt} Ücretli",
                f"⏳ {and_trial_cnt} Deneme",
            ],
            "onboarding_step_funnel": onboarding_step_funnel_android,
            "ab_experiment": ab_experiment_android,
        },
    }

    source_freshness = [
        {
            "id": "bridge_telemetry",
            "label": "Instagram Profil Bağlantısı & Uygulama Telemetrisi",
            "status": "realtime",
            "badge": f"⚡ Gerçek Zamanlı ({today_str})",
            "detail": f"Aktif Instagram Profil Köprüsü: {ig_unique_count} Tık (🍏 {ig_ios_count} iOS • 🤖 {ig_android_count} Android{desktop_sub_suffix}) • Eski Reklam Köprüsü (/ios) Temizlendi",
        },
        {
            "id": "meta_app_events_sdk",
            "label": "🎯 Meta Uygulama Reklamları & Ölçümleme",
            "status": "realtime",
            "badge": "🍏 iOS + 🤖 Android Reklamları Aktif",
            "detail": f"iOS App Store + Meta: {direct_ios_store_or_meta_installs} Kurulum ({r3_ref} Sosyal/Meta) • Android Google Play + Meta: {direct_android_play_or_meta_installs} Kurulum",
        },
        {
            "id": "apple_sales_tsv",
            "label": "🍏 Apple App Store Satış & Analitik",
            "status": "lagged_24h",
            "badge": f"🍏 {apple_downloads} iOS Kurulum ({latest_store_metric_date or 'Aktif'})",
            "detail": f"{apple_impressions:,} Gösterim • {apple_page_views} Sayfa Ziyareti • {ios_reviews_cnt} Yorum",
        },
        {
            "id": "apple_sub_ledger",
            "label": "🍏 Apple Abonelik & Tahsilat Defteri",
            "status": "reconciling" if reconciling_7d_cnt > 0 else "synced",
            "badge": f"📒 {ios_active_cnt} Aktif / {ios_total_rec} Kayıt ({ios_cancelled_cnt} İptal)",
            "detail": f"Tahsil: {ios_realized_net:.2f} ₺ • Beklenen Havuz: +{plat_fin['ios']['pipeline_net']:.2f} ₺ Net",
        },
        {
            "id": "google_play_sync",
            "label": "🤖 Google Play Mağaza & Abonelik",
            "status": "synced",
            "badge": f"🤖 {google_play_downloads} Android Kurulum • {and_active_cnt} Aktif VIP",
            "detail": f"{len(gp_catalog)} Aktif Paket • {direct_android_play_or_meta_installs} Play/Meta + {matched_android_bio_installs} Profil • {android_reviews_cnt} Yorum",
        },
    ]

    data_governance_matrix = [
        {
            "id": "gov_bridge_clicks",
            "domain": "1. Sosyal Köprü & Kampanya Tıklamaları",
            "metrics": "Tekil Tık, Ham İstek, Bot Filtresi, /ios & /download Yönlendirmeleri",
            "ssot_table": "bridge_clicks (PostgreSQL)",
            "update_method": "FastAPI Redirect Middleware (record_bridge_click — Bot & 15sn IP/UA tekilleştirmeli)",
            "frequency": "Anlık (Olay Anında) • Kokpitte 15 sn'de bir canlı polling",
            "latency_class": "⚡ T-0 (Gerçek Zamanlı)",
            "last_sync": f"Canlı ({today_str} • {len(unique_human)} Tekil Tık)",
            "consistency_rule": "Organik mağaza gösterim (r14) paydasına bölünmez; kendi köprü dönüşüm hunisinde izlenir.",
        },
        {
            "id": "gov_app_telemetry",
            "domain": "2. Uygulama İçi Cihaz, 10 Adım Onboarding & A/B Paywall Telemetrisi",
            "metrics": "first_open, daily_active, onboarding_step_viewed_0..9, onb_step7_quick_chip_used, ab_a_*/ab_b_* Paywall, Uyku, Ağlama AI, Rutin, Dadı AI",
            "ssot_table": "app_install_signals + babies, sleep_logs, cry_events, routine_logs, dadi_chat_history",
            "update_method": "Mobil Uygulama / WebView POST /api/v1/analytics/app-open-signal & /usage-signal",
            "frequency": "Anlık (Olay Anında) • Kokpitte 15 sn'de bir canlı polling",
            "latency_class": "⚡ T-0 (Gerçek Zamanlı)",
            "last_sync": f"Canlı ({len(first_opens)} İlk Açılış • {len(daily_actives)} Günlük Aktif)",
            "consistency_rule": "Resmi mağaza indirmesi (StoreDailyMetric) mevcutken max() ile resmi indirme sayısını ezmez; ayrı T-0 sinyal olarak raporlanır.",
        },
        {
            "id": "gov_live_sub_bridge",
            "domain": "3. Canlı Abonelik, A/B Testi & Tahsilat Köprüsü (iOS + Android)",
            "metrics": "🔥 Grup A İlk Ay %67 İndirim (49.99 ₺), 🎁 Grup B İlk Ay Ücretsiz (30G 0 ₺), 👑 Yıllık VIP (599.99 ₺), Plan Değişimi, Google Play Aktif Abone",
            "ssot_table": "subscriber_ledger (RC_T0_* & Google Play subscriptionsv2)",
            "update_method": "POST /api/v1/analytics/subscriber-sync + RevenueCat REST API v2 (production) & Google Play API",
            "frequency": "Satın Alma Anında (T-0) + 6 Saatte Bir Otomatik Arka Plan Senkronu",
            "latency_class": "⚡ T-0 (Canlı Köprü)",
            "last_sync": f"Son Senkron: {sb.get('last_synced_at') or today_str}",
            "consistency_rule": "Apple T-1 raporu gelene kadar yeni aboneyi anında gösterir; T-1 SUBSCRIBER raporu geldiğinde RC_T0_* kaydı otomatik tekilleştirilir.",
        },
        {
            "id": "gov_apple_official_sales",
            "domain": "4. Resmi Apple İndirme, Satış & Abone Defteri",
            "metrics": "Resmi iOS İndirme (Units), Tahsil Edilen Gelir (Brüt/Net ₺ & $), Abone Yaşam Döngüsü & İptaller",
            "ssot_table": "store_daily_metrics + subscriber_ledger + subscription_lifecycle_events",
            "update_method": "App Store Connect API (ES256 .p8 JWT — SALES, SUBSCRIBER v1_3, SUBSCRIPTION_EVENT v1_3)",
            "frequency": "6 Saatte Bir Otomatik Kontrol (run_periodic_store_sync_loop) • Apple Günde 1 Kez Yayınlar",
            "latency_class": "🏛️ T-1 (1 Gün PST Gecikmeli — Resmi Kesinleşen)",
            "last_sync": f"Son Kesinleşen Rapor: {latest_store_metric_date or store_reconciliation.get('apple_latest_report_date') or '-'}",
            "consistency_rule": "Finansal ve resmi indirme otoritesidir. Kartlarda son kesinleşen rapor tarihi açıkça belirtilir.",
        },
        {
            "id": "gov_apple_analytics_r14_r8_r3",
            "domain": "5. Resmi Apple Mağaza Hunisi & Sadakat Analitiği",
            "metrics": "Mağaza Gösterimi (r14), Ürün Sayfası Ziyareti (r14), Oturum & Geri Dönen Cihaz (r8), Kanal İndirme (r3)",
            "ssot_table": "store_daily_metrics + store_sync_states (r8_loyalty_summary, r3_channel_summary)",
            "update_method": "App Store Connect analyticsReportRequests (r14 Discovery, r8 Sessions, r3 Downloads TSV)",
            "frequency": "6 Saatte Bir Sunucu Kontrolü • Apple Analytics Segmentleri 24–48 Saatte Bir Güncellenir",
            "latency_class": "🏛️ T-1 / T-2 (24–48s Gecikmeli — Resmi Analitik)",
            "last_sync": f"Son r14/r8 Tarihi: {latest_confirmed_r14_date or latest_store_metric_date or '-'}",
            "consistency_rule": "Sales TSV gelip r14 henüz gelmediğinde gün 'is_r14_pending' olarak işaretlenir; 0 gösterim olarak grafiği çökertmez.",
        },
        {
            "id": "gov_google_play_and_reviews",
            "domain": "6. Google Play Katalog, Android Kurulum & Mağaza Yorumları",
            "metrics": "Google Play Paket Kataloğu (misil, misilaylik), Android Kurulum, App Store & Play Yorumları",
            "ssot_table": "store_sync_states + store_daily_metrics + subscriber_ledger",
            "update_method": "Google Play Developer API (androidpublisher/v3 RS256) & Apple customerReviews API",
            "frequency": "6 Saatte Bir Otomatik Arka Plan Döngüsü + Manuel Tetikleme (/trigger-sync)",
            "latency_class": "🏛️ 6 Saatlik Periyodik",
            "last_sync": f"{len(gp_catalog)} Paket • {len(all_reviews)} Yorum ({ios_reviews_cnt} iOS + {android_reviews_cnt} Play)",
            "consistency_rule": "Tarihsiz Android kurulumları aktif iOS günlerine sentetik olarak dağıtılmaz; gerçek sinyal/kayıt gününde gösterilir.",
        },
    ]

    architecture_principles = [
        {
            "title": "1. T-0 Canlı Telemetri ile T-1 Resmi Mağaza Verisi Karıştırılmaz",
            "desc": "Uygulama içi sinyaller (first_open, daily_active) ve sosyal köprü tıklamaları T-0 anlık veridir; Apple App Store Connect raporları ise T-1/T-2 kesinleşen resmi veridir. Resmi mağaza verisi mevcutken canlı sinyal ile max() alınarak sayılar şişirilmez.",
        },
        {
            "title": "2. Tek Doğruluk Kaynağı (Single Source of Truth — SSOT)",
            "desc": "Her metrik kümesinin tek bir veritabanı tablosu vardır: Köprü tıkları bridge_clicks, mağaza günlük serisi store_daily_metrics, abone ve gelir defteri subscriber_ledger tablosundan okunur.",
        },
        {
            "title": "3. Çift Katmanlı Otomatik Güncelleme (15sn Canlı + 6 Saat Mağaza)",
            "desc": "Tarayıcı açıkken her 15 saniyede bir /api/v1/analytics/summary çağrılarak T-0 tıklama ve canlı sayaçlar sayfa yenilenmeden güncellenir. Resmi Apple/Google API senkronu ise sunucuda her 6 saatte bir (run_periodic_store_sync_loop) otomatik çalışır.",
        },
        {
            "title": "4. Dönem Seçici (Period) ve Zaman Penceresi Tutarlılığı",
            "desc": "Üstteki 4 Kuzey Yıldızı kartı kümülatif portföy büyüklüğünü, dönem filtreleri (Bugün, Dün, Son 7 Gün, Tüm Zamanlar) ise ilgili dönemin tahsilat ve trafik akışını standart zaman penceresiyle sunar.",
        },
    ]

    recent_ids = [c.id for c in active_raw_set[:100]]
    recent_clicks_detached: List[SimpleNamespace] = []
    if recent_ids:
        rc_rows = db.query(BridgeClick).filter(BridgeClick.id.in_(recent_ids)).all()
        rc_by_id = {rc.id: rc for rc in rc_rows}
        for rid in recent_ids:
            rc = rc_by_id.get(rid)
            if rc is not None:
                recent_clicks_detached.append(
                    SimpleNamespace(
                        id=rc.id,
                        created_at=rc.created_at,
                        route_path=rc.route_path,
                        channel=rc.channel,
                        os_family=rc.os_family,
                        device_detail=rc.device_detail,
                        app_webview=rc.app_webview,
                        target_store=rc.target_store,
                        is_bot=rc.is_bot,
                        is_unique=rc.is_unique,
                        has_fbclid=rc.has_fbclid,
                        country=rc.country,
                        ip_masked=rc.ip_masked,
                    )
                )

    c1_no_seed = bool(
        not any(int(c.reported_impressions or 0) in (4014, 3850, 640, 410) for c in cfg_rows)
        and int(sb.get("apple_impressions_total", 0) or 0) != 4066
        and not any(str(getattr(r, "subscriber_id", "") or "").startswith("DEV_") for r in ledger_rows_db)
    )
    c2_onb_live = bool(
        len(onboarding_step_funnel_all["steps"]) == 10
        and (
            onboarding_step_funnel_all["has_telemetry_data"]
            == (onboarding_step_funnel_all["total_tracked_onboarding_devices"] > 0)
        )
    )
    c3_fin_live = bool(
        get_dynamic_proceeds_ratio("ios") >= IOS_SBP_15_PROCEEDS_RATIO
        and get_dynamic_proceeds_ratio("android") >= ANDROID_15_PROCEEDS_RATIO
        and financial_ledger["active_vip_subs_count"]
        == (
            financial_ledger["paid_subs_count"]
            + financial_ledger["pipeline_7d_trials_count"]
            + financial_ledger["offer_code_subs_count"]
        )
    )
    c4_rev_dyn = bool(
        (len(all_reviews) == 0 and all_avg_stars_str == "Yorum Yok")
        or (len(all_reviews) > 0 and all_avg_stars_str.startswith("★ "))
    )
    c5_ssot_live = bool(
        total_cumulative_downloads == (apple_downloads + google_play_downloads)
        and total_cumulative_impressions == (apple_impressions + google_play_impressions)
    )
    audit_contracts_map = {
        "no_synthetic_seed_rows": {
            "passed": c1_no_seed,
            "source": "bridge_clicks + campaign_configs + store_daily_metrics + subscriber_ledger",
            "detail": "Sentetik HistoricalSeed (4066/4014) ve doğrulanmamış DEV_* kayıtları mevcut değil.",
        },
        "onboarding_9step_live_db": {
            "passed": c2_onb_live,
            "source": "app_install_signals (onboarding_step_viewed_0..9)",
            "tracked_unique_devices": onboarding_step_funnel_all["total_tracked_onboarding_devices"],
        },
        "financial_ledger_live_db": {
            "passed": c3_fin_live,
            "source": "subscriber_ledger + subscription_lifecycle_events",
            "ios_proceeds_ratio": get_dynamic_proceeds_ratio("ios"),
            "android_proceeds_ratio": get_dynamic_proceeds_ratio("android"),
        },
        "reviews_rating_dynamic": {
            "passed": c4_rev_dyn,
            "source": "store_sync_states.store_reviews (App Store & Google Play API)",
            "all_avg_rating_str": all_avg_stars_str,
            "ios_avg_rating_str": ios_avg_stars_str,
            "android_avg_rating_str": android_avg_stars_str,
        },
        "store_metrics_ssot": {
            "passed": c5_ssot_live,
            "source": "store_daily_metrics + app_install_signals",
            "downloads_total": total_cumulative_downloads,
        },
    }
    contracts_checked_cnt = len(audit_contracts_map)
    contracts_passed_cnt = sum(1 for c_item in audit_contracts_map.values() if c_item["passed"])
    all_audit_passed = contracts_passed_cnt == contracts_checked_cnt
    zero_static_data_audit = {
        "all_passed": all_audit_passed,
        "contracts_checked": contracts_checked_cnt,
        "contracts_passed": contracts_passed_cnt,
        "status_badge": (
            f"🛡️ %100 Canlı Veri ({contracts_passed_cnt}/{contracts_checked_cnt} Kontrat Yeşil • Sıfır Statik)"
            if all_audit_passed
            else f"⚠️ Veri Denetimi ({contracts_passed_cnt}/{contracts_checked_cnt} Kontrat)"
        ),
        "contracts": audit_contracts_map,
    }

    result_summary = {
        "period": period,
        "period_label": period_label,
        "zero_static_data_audit": zero_static_data_audit,
        "period_clicks_count": len(period_clicks),
        "active_human_count": max(active_human_count, ig_unique_count if period == "all" else 0),
        "today_unique_clicks": today_unique_clicks,
        "yesterday_unique_clicks": yesterday_unique_clicks,
        "total_raw": max(total_raw, effective_unique_bridge_clicks),
        "total_human": max(len(human_clicks), effective_unique_bridge_clicks),
        "total_unique_human": effective_unique_bridge_clicks,
        "total_bots": len(bot_clicks),
        "total_all_installs": total_cumulative_downloads,
        "total_all_spend_usd": total_all_spend_usd,
        "blended_cpi_usd": blended_cpi_usd,
        "source_freshness": source_freshness,
        "data_governance_matrix": data_governance_matrix,
        "architecture_principles": architecture_principles,
        "platform_split": platform_split,
        "reviews_star_distribution": reviews_star_distribution,
        "satisfaction_pulse": satisfaction_pulse,
        "google_play_subscriptions_catalog": gp_catalog,
        "kpi_deltas": {
            "recent_3d_impressions": recent_3d_imp,
            "recent_3d_downloads": recent_3d_dl,
            "today_vs_yesterday_clicks_diff": today_unique_clicks - yesterday_unique_clicks,
        },
        "cumulative_kpis": {
            "impressions_total": total_cumulative_impressions,
            "impressions_unique": total_impressions_unique,
            "ios_impressions": apple_impressions,
            "android_impressions": google_play_impressions,
            "visits_and_clicks_total": total_cumulative_visits_and_clicks,
            "store_page_views": total_cumulative_store_page_views,
            "ios_store_page_views": apple_page_views,
            "android_store_page_views": google_play_page_views,
            "store_page_views_unique": total_store_page_views_unique,
            "bridge_unique_clicks": effective_unique_bridge_clicks,
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
            "vip_churn_rate_pct": all_churn_rate_pct,
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
            "is_sole_active_bridge": True,
            "raw_hits": max(len(ig_raw), ig_unique_count),
            "human_hits": max(len(ig_human), ig_unique_count),
            "unique_clicks": ig_unique_count,
            "ios_clicks": ig_ios_count,
            "android_clicks": ig_android_count,
            "installs": r3_browse,
            "cr_pct": round((r3_browse / ig_unique_count) * 100, 1) if ig_unique_count > 0 else 0.0,
            "spend_usd": ig_spend_usd,
        },
        "meta_app_installs_sdk": {
            "meta_app_id": META_APP_ID_OFFICIAL,
            "sole_active_bridge_route": "/download",
            "bridge_reset_cutoff_utc": BRIDGE_RESET_V4564_CUTOFF_UTC.isoformat(),
            "android_direct_app_installs_active": True,
            "android_direct_installs": direct_android_play_or_meta_installs,
            "android_bio_matched_installs": matched_android_bio_installs,
            "ios_direct_app_installs_active": True,
            "ios_direct_installs": direct_ios_store_or_meta_installs,
            "ios_bio_matched_installs": matched_ig_installs,
            "ios_sdk_target_version": "4.56.0",
            "ios_sdk_target_build": 72,
            "ios_sdk_status": ios_att_sdk_status_key,
            "ios_sdk_status_badge": ios_att_sdk_status_badge,
            "ios_sdk_live_devices": ios_att_sdk_devices_cnt,
        },
        "onboarding_step_funnel": onboarding_step_funnel_all,
        "onboarding_step_funnel_by_platform": onboarding_step_funnel_by_platform,
        "ab_experiment": ab_experiment_all,
        "ab_experiment_by_platform": ab_experiment_by_platform,
        "product_funnel": {
            "onboarding_step_funnel": onboarding_step_funnel_all,
            "onboarding_step_funnel_by_platform": onboarding_step_funnel_by_platform,
            "ab_experiment": ab_experiment_all,
            "ab_experiment_by_platform": ab_experiment_by_platform,
            "bridge_unique_clicks": effective_unique_bridge_clicks,
            "asa_clicks": asa_clicks_val,
            "total_acquisition_clicks": total_cumulative_visits_and_clicks,
            "store_jumps_tracked": effective_unique_bridge_clicks,
            "legacy_store_jump_beacons": len(store_jumps),
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
                "purchase_cancelled_unique_devices": purchase_cancelled_unique_devs,
                "paywall_cta_clicked_unique_devices": paywall_cta_unique_devs,
                "purchase_error": len(purchase_error_signals),
                "vip_started": len(vip_started_signals),
                "cancel_rate_pct": (
                    min(
                        100.0,
                        round((purchase_cancelled_unique_devs / max(1, paywall_cta_unique_devs)) * 100, 1),
                    )
                    if paywall_cta_unique_devs > 0
                    else 0.0
                ),
                "sound_preview_60s_ended": len(sound_preview_60s_ended_signals),
                "cry_limit_reached": len(cry_limit_reached_signals),
                "dadi_limit_reached": len(dadi_limit_reached_signals),
                "routine_limit_reached": len(routine_limit_reached_signals),
                "paywall_cancel_recovery_shown": len(paywall_cancel_recovery_signals),
                "paywall_cancel_recovery_cta_clicked": len(paywall_cancel_recovery_cta_signals),
                "paywall_cancel_reasons": paywall_cancel_reasons_breakdown,
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
            "feedbacks_count": db_feedbacks_cnt_capped,
            "feedbacks_total_count": db_feedbacks_total_cnt,
            "feedbacks_last_24h_count": feedbacks_last_24h_cnt,
            "feedbacks_list": db_feedbacks[:50],
            "subscriptions_count": apple_vip,
            "unmatched_organic_opens": unmatched_organic_opens,
        },
        "golden_hours": golden_hours,
        "os_breakdown": dict(os_counts),
        "webview_breakdown": dict(webview_counts),
        "hourly_all_tr": dict(hourly_all_time),
        "recent_clicks": recent_clicks_detached,
    }
    now_done = time.monotonic()
    with _SUMMARY_CACHE_LOCK:
        _LAST_GOOD_SUMMARY_CACHE[period] = (now_done, _clone_summary_for_response(result_summary))
        if cache_enabled and _SUMMARY_CACHE_TTL_SEC > 0:
            _SUMMARY_CACHE[period] = (now_done, _clone_summary_for_response(result_summary))
    return result_summary


def get_resilient_analytics_summary(
    db: Session,
    period: str = "all",
    use_cache: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    SWR (Stale-While-Revalidate) ve Zero-500 korumalı kokpit özet yükleyici:
    1) Veritabanı kilit/pool zaman aşımı durumunda aynı döneme ('period') ait ve süresi (_SWR_MAX_STALE_SEC)
       dolmamış _LAST_GOOD_SUMMARY_CACHE yedeğini ('stale_fallback': True) döndürür (farklı dönem verisini karıştırmaz).
    2) Soğuk başlangıçta (cold-start) henüz önbellek yokken yerel/birincil DB şema veya kilit hatası verirse,
       bellek içi (sqlite:///:memory:) geçici oturumla sıfır-statik-veri özetini üreterek 500 hatasını tamamen önler.
    """
    try:
        return _build_analytics_summary(db, period=period, use_cache=use_cache)
    except ValueError:
        raise
    except Exception as exc:
        logger.warning("Analytics summary build warning (falling back to SWR cache): %s", exc, exc_info=True)
        try:
            if db is not None:
                db.rollback()
        except Exception:
            pass
        now_mono = time.monotonic()
        with _SUMMARY_CACHE_LOCK:
            fb_entry = _LAST_GOOD_SUMMARY_CACHE.get(period)
            if fb_entry is not None and (now_mono - fb_entry[0]) <= _SWR_MAX_STALE_SEC:
                cloned_fb = _clone_summary_for_response(fb_entry[1])
                cloned_fb["stale_fallback"] = True
                return cloned_fb
        try:
            from sqlalchemy import create_engine as _sa_create_engine
            from sqlalchemy.orm import sessionmaker as _sa_sessionmaker

            mem_engine = _sa_create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
            Base.metadata.create_all(bind=mem_engine, checkfirst=True)
            MemSession = _sa_sessionmaker(autocommit=False, autoflush=False, bind=mem_engine)
            mem_db = MemSession()
            try:
                cold_fb = _build_analytics_summary(mem_db, period=period, use_cache=False)
                cold_fb["stale_fallback"] = True
                return cold_fb
            finally:
                mem_db.close()
                mem_engine.dispose()
        except Exception:
            pass
        raise


@router.get("/summary")
def get_analytics_summary(
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

    summary = get_resilient_analytics_summary(db, period=period)
    recent_serialized = []
    tz_tr = timezone(timedelta(hours=3))
    for c in summary["recent_clicks"][:50]:
        dt_utc = c.created_at.replace(tzinfo=timezone.utc) if c.created_at.tzinfo is None else c.created_at
        dt_tr = dt_utc.astimezone(tz_tr)
        recent_serialized.append({
            "id": c.id,
            "created_at": dt_utc.isoformat(),
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
    raw_fb_list = summary.get("product_funnel", {}).get("feedbacks_list") or []
    fb_serialized = []
    for fb_obj in raw_fb_list[:50]:
        fb_dt = getattr(fb_obj, "created_at", None)
        if fb_dt:
            fb_dt_utc = fb_dt.replace(tzinfo=timezone.utc) if fb_dt.tzinfo is None else fb_dt
            fb_time_tr = fb_dt_utc.astimezone(tz_tr).strftime("%d.%m.%Y %H:%M")
        else:
            fb_time_tr = "-"
        fb_plat_raw = str(getattr(fb_obj, "platform", "") or "").lower()
        fb_plat_key = "ios" if "ios" in fb_plat_raw or "iphone" in fb_plat_raw else ("android" if "android" in fb_plat_raw else "all")
        fb_serialized.append({
            "id": getattr(fb_obj, "id", 0),
            "time_tr": fb_time_tr,
            "platform": fb_plat_key,
            "platform_raw": str(getattr(fb_obj, "platform", "") or "mobile"),
            "sentiment": str(getattr(fb_obj, "sentiment", "") or "suggestion"),
            "baby_age_months": getattr(fb_obj, "baby_age_months", None),
            "contact_info": str(getattr(fb_obj, "contact_info", "") or ""),
            "app_version": str(getattr(fb_obj, "app_version", "") or ""),
            "message": str(getattr(fb_obj, "message", "") or ""),
        })
    summary["in_app_feedbacks"] = {
        "total_count": int(summary.get("product_funnel", {}).get("feedbacks_total_count", len(fb_serialized)) or 0),
        "last_24h_count": int(summary.get("product_funnel", {}).get("feedbacks_last_24h_count", 0) or 0),
        "items": fb_serialized,
    }
    summary["product_funnel"].pop("feedbacks_list", None)
    return summary


class StoreSyncPushPayload(BaseModel):
    baseline_snapshot: Dict[str, Any] = Field(default_factory=dict)
    daily_metrics: List[Dict[str, Any]] = Field(default_factory=list)
    subscribers: List[Dict[str, Any]] = Field(default_factory=list)
    lifecycle_events: List[Dict[str, Any]] = Field(default_factory=list)


class ClientSubscriberSyncPayload(BaseModel):
    subscriber_id: str = Field(..., min_length=3, max_length=128)
    device_uid: Optional[str] = Field(default=None, max_length=128)
    platform: str = Field(default="android", max_length=32)
    product_id: str = Field(default="misil", max_length=64)
    plan: Optional[str] = Field(default=None, max_length=64)
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
    if not clean_tok:
        return None
    access_token = _get_google_play_access_token()
    if not access_token:
        return None
    try:
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
def sync_client_subscriber_ledger(
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

    # Google Play purchase_token varsa subscriptionsv2 API ile doğrula (endpoint sync def olduğu için zaten worker threadpool'da çalışır)
    verified_gp_token = False
    if plat == "android" and payload.purchase_token:
        gp_v2 = verify_google_play_subscription_token(payload.purchase_token)
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
    verified_rc_v2 = False
    rc_conv_dt_str: Optional[str] = None
    if (
        not is_admin_authed
        and not verified_gp_token
        and not clean_sid.upper().startswith("DEV_")
        and (not os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("MISIL_ENABLE_TEST_RC_V2") == "1")
    ):
        rc_v2 = verify_revenuecat_v2_customer(payload.subscriber_id.strip())
        if isinstance(rc_v2, dict) and rc_v2.get("store_subscription_identifier"):
            verified_rc_v2 = True
            plat = rc_v2["platform"]
            prod_id = rc_v2["product_id"]
            store_sub_id = str(rc_v2["store_subscription_identifier"]).strip()
            base_sub_id = store_sub_id.split("..")[0] if store_sub_id.startswith("GPA.") else store_sub_id
            clean_sid = (f"RC_T0_{base_sub_id}" if plat == "ios" else base_sub_id)[:128]
            auto_renew = bool(rc_v2["auto_renew_enabled"])
            if rc_v2.get("starts_at_date"):
                start_dt_str = rc_v2["starts_at_date"]
            if rc_v2.get("current_period_starts_at_date"):
                rc_conv_dt_str = rc_v2["current_period_starts_at_date"]
            elif rc_v2.get("starts_at_date"):
                rc_conv_dt_str = rc_v2["starts_at_date"]
            if rc_v2.get("ends_at_date"):
                mat_dt_str = rc_v2["ends_at_date"]
            if rc_v2["rc_status"] in ("expired", "unsubscribed") or (float(rc_v2.get("gross_usd") or 0.0) <= 0 and not auto_renew):
                st_val = "cancelled"
            elif float(rc_v2.get("gross_usd") or 0.0) > 0:
                st_val = "paid_active"
            else:
                st_val = "intro_free_trial"
            is_1m_rc_v2 = (
                st_val == "intro_free_trial"
                and not _is_annual_product(prod_id)
                and _is_30d_free_trial_window(
                    start_dt_str,
                    mat_dt_str,
                    f"{rc_v2.get('rc_product_id', '')} {rc_v2.get('store_product_identifier', '')} {prod_id} {payload.offer_type or ''}",
                )
            )
            if is_1m_rc_v2 and not payload.offer_type:
                payload.offer_type = "free_trial_1m"
            offer_code_nm = (
                ("İlk Ay Ücretsiz Deneme (T-0 Canlı Köprü)" if is_1m_rc_v2 else "RevenueCat T-0 Canlı Köprü")
                if plat == "ios"
                else ("İlk Ay Ücretsiz Deneme (Google Play)" if is_1m_rc_v2 else "Deneme (Google Play)")
            )
            if plat == "ios":
                from sqlalchemy import or_ as sa_or
                raw_rc_lookup = (payload.subscriber_id or "").strip()[:128]
                off_match_clauses = [
                    SubscriberLedger.started_date == start_dt_str,
                    SubscriberLedger.converted_or_renewed_date == start_dt_str,
                ]
                if rc_conv_dt_str:
                    off_match_clauses.append(SubscriberLedger.converted_or_renewed_date == rc_conv_dt_str)
                if mat_dt_str:
                    off_match_clauses.append(SubscriberLedger.maturity_or_renewal_date == mat_dt_str)
                existing_official_ios = (
                    db.query(SubscriberLedger)
                    .filter(
                        SubscriberLedger.platform == "ios",
                        ~SubscriberLedger.subscriber_id.like("RC_T0_%"),
                        sa_or(
                            SubscriberLedger.rc_app_user_id == raw_rc_lookup,
                            (SubscriberLedger.product_id == prod_id) & sa_or(*off_match_clauses),
                        ),
                    )
                    .order_by(SubscriberLedger.started_date.asc(), SubscriberLedger.subscriber_id.asc())
                    .first()
                )
                if existing_official_ios is not None:
                    clean_sid = existing_official_ios.subscriber_id
                    start_dt_str = existing_official_ios.started_date or start_dt_str
                    offer_code_nm = existing_official_ios.offer_code_name or offer_code_nm

    # Kimliksiz/doğrulanmamış istemci çağrılarının sahte tahsilat (paid_active) yazmasını, DEV_* hayalet satırı üretmesini veya resmi Apple satırlarını ezmesini engelle
    if not is_admin_authed and not verified_gp_token and not verified_rc_v2:
        if clean_sid.upper().startswith("DEV_") or "RCANONYMOUSID" in clean_sid.upper():
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

    raw_offer_type = (payload.offer_type or "").strip()
    is_1m_free_trial_payload = (
        raw_offer_type == "free_trial_1m"
        or "trial" in prod_id.lower()
        or "free" in prod_id.lower()
    )
    if not mat_dt_str or len(mat_dt_str) != 10:
        try:
            dt_s = datetime.strptime(start_dt_str, "%Y-%m-%d")
        except Exception:
            dt_s = datetime.now(tz_tr)
            start_dt_str = dt_s.strftime("%Y-%m-%d")
        days_add = (30 if is_1m_free_trial_payload else 7) if st_val == "intro_free_trial" else (365 if is_ann else 30)
        mat_dt_str = (dt_s + timedelta(days=days_add)).strftime("%Y-%m-%d")

    std_gross, std_net = _resolve_expected_trial_pricing(
        prod_id,
        0.0 if verified_rc_v2 else payload.customer_price_try,
        0.0 if verified_rc_v2 else payload.developer_proceeds_try,
        plat,
    )
    net_ratio = get_dynamic_proceeds_ratio(plat)
    if verified_rc_v2:
        c_gross = std_gross if st_val == "paid_active" else 0.0
        c_net = std_net if st_val == "paid_active" else 0.0
    else:
        c_gross = round(float(payload.customer_price_try or (std_gross if st_val == "paid_active" else 0.0)), 2)
        c_net = round(float(payload.developer_proceeds_try or (round(c_gross * net_ratio, 2) if c_gross > 0 else 0.0)), 2)

    is_intro_payload = raw_offer_type == "intro_1m_discounted"
    if st_val == "cancelled" or not auto_renew:
        exp_gross, exp_net = 0.0, 0.0
    elif st_val == "offer_code_trial":
        exp_gross, exp_net = 0.0, 0.0
    elif is_intro_payload or is_1m_free_trial_payload:
        exp_gross, exp_net = std_gross, std_net
    else:
        exp_gross, exp_net = (c_gross, c_net) if c_gross > 0 else (std_gross, std_net)

    of_type = raw_offer_type or (
        "standard_paid"
        if st_val == "paid_active"
        else ("offer_code" if st_val == "offer_code_trial" else ("free_trial_1m" if is_1m_free_trial_payload else "intro_7d_trial"))
    )
    if not offer_code_nm:
        offer_code_nm = (
            "İlk Ay İndirimli Başlangıç"
            if is_intro_payload
            else (
                "İlk Ay Ücretsiz Deneme"
                if (st_val == "intro_free_trial" and (of_type == "free_trial_1m" or is_1m_free_trial_payload))
                else ("Standart Ücretli" if st_val == "paid_active" else "Tarihsel Deneme")
            )
        )

    cntry_clean = "".join(ch for ch in (payload.country or "TR").upper() if ch.isalnum())[:16] or "TR"
    dev_clean = (payload.device_type or ("Android" if plat == "android" else "iPhone")).strip()[:64]

    existing = db.query(SubscriberLedger).filter(SubscriberLedger.subscriber_id == clean_sid).first()
    if existing and not is_admin_authed and not verified_gp_token and not verified_rc_v2:
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
    raw_rc_uid = (payload.subscriber_id or "").strip()[:128] or None
    verified_dev_uid = ((payload.device_uid or "").strip()[:128] or None) if (verified_gp_token or verified_rc_v2 or is_admin_authed) else None

    if existing:
        existing.platform = plat
        existing.product_id = prod_id
        existing.plan_label = plan_lbl
        existing.status = st_val
        existing.offer_type = of_type[:64]
        existing.offer_code_name = offer_code_nm
        existing.maturity_or_renewal_date = mat_dt_str
        existing.auto_renew_enabled = auto_renew
        if verified_rc_v2 and raw_rc_uid:
            existing.rc_app_user_id = raw_rc_uid
        if verified_dev_uid:
            existing.device_uid = verified_dev_uid
        if c_gross > 0:
            existing.customer_price_try = c_gross
            existing.developer_proceeds_try = c_net
            existing.converted_or_renewed_date = (
                payload.converted_or_renewed_date
                or rc_conv_dt_str
                or existing.converted_or_renewed_date
                or today_str
            )
        existing.expected_next_price_try = exp_gross
        existing.expected_next_proceeds_try = exp_net
        existing.country = cntry_clean
        existing.device_type = dev_clean
    else:
        db.add(
            SubscriberLedger(
                subscriber_id=clean_sid,
                rc_app_user_id=raw_rc_uid if verified_rc_v2 else None,
                device_uid=verified_dev_uid,
                platform=plat,
                product_id=prod_id,
                plan_label=plan_lbl,
                status=st_val,
                offer_type=of_type[:64],
                offer_code_name=offer_code_nm,
                started_date=start_dt_str,
                converted_or_renewed_date=(payload.converted_or_renewed_date or rc_conv_dt_str or start_dt_str) if st_val == "paid_active" else None,
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

    if plat == "ios" and not auto_renew and (verified_rc_v2 or is_admin_authed):
        wnr_sync_key = f"{clean_sid}:will_not_renew"[:128]
        dup_wnr_sync = (
            db.query(SubscriptionLifecycleEvent.id)
            .filter(
                SubscriptionLifecycleEvent.platform == "ios",
                SubscriptionLifecycleEvent.event_type == wnr_sync_key,
            )
            .first()
        )
        if dup_wnr_sync is None:
            db.add(
                SubscriptionLifecycleEvent(
                    event_date=rc_conv_dt_str or start_dt_str or today_str,
                    platform="ios",
                    event_type=wnr_sync_key,
                    product_id=prod_id,
                    plan_label=plan_lbl,
                    offer_code_name=offer_code_nm,
                    country=cntry_clean,
                    device_type=dev_clean,
                    quantity=1,
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
    invalidate_analytics_summary_cache(mark_reconcile=True)
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
def ingest_local_store_sync(
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
    invalidate_analytics_summary_cache(mark_reconcile=False, reset_baseline_stamp=True)
    return {
        "status": "ok",
        "upserted_daily_metrics": upserted_metrics,
        "upserted_subscribers": upserted_subs,
        "upserted_lifecycle_events": upserted_events,
    }


class StoreReviewReplyPayload(BaseModel):
    review_id: str = Field(..., min_length=2, max_length=160)
    response_body: str = Field(..., min_length=2, max_length=5970)
    platform: Optional[str] = Field(default="ios", max_length=32)


def _submit_store_review_reply_sync(
    review_id: str,
    response_body: str,
    platform: str = "ios",
) -> Dict[str, Any]:
    """
    Apple App Store Connect API (POST /v1/customerReviewResponses) veya
    Google Play Developer API (POST .../reviews/{reviewId}:reply) üzerinden
    resmi geliştirici yanıtı gönderir ve OFFICIAL_STORE_BASELINE + StoreSyncState önbelleğini günceller.
    """
    clean_rev_id = (review_id or "").strip()
    clean_body = (response_body or "").strip()
    plat = "android" if (platform or "ios").strip().lower() == "android" else "ios"
    if not clean_rev_id or not clean_body:
        raise ValueError("Yorum ID (review_id) ve yanıt metni (response_body) boş olamaz.")

    tz_tr = timezone(timedelta(hours=3))
    today_tr_str = datetime.now(tz_tr).strftime("%d.%m.%Y")
    resp_id = ""
    resp_state = "PUBLISHED"

    if plat == "ios":
        if not jwt:
            raise RuntimeError("PyJWT kütüphanesi yüklü değil.")
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
            with open(p8_path, "r", encoding="utf-8") as f:
                asc_priv_key = f.read()
        if asc_priv_key:
            asc_priv_key = asc_priv_key.replace("\\n", "\n")
        if not asc_priv_key:
            raise RuntimeError("Apple App Store Connect .p8 anahtarı bulunamadı.")

        now_ts = int(time.time())
        token = jwt.encode(
            {"iss": asc_issuer_id, "iat": now_ts - 30, "exp": now_ts + 900, "aud": "appstoreconnect-v1"},
            asc_priv_key,
            algorithm="ES256",
            headers={"kid": asc_key_id, "typ": "JWT"},
        )
        asc_payload = {
            "data": {
                "type": "customerReviewResponses",
                "attributes": {
                    "responseBody": clean_body,
                },
                "relationships": {
                    "review": {
                        "data": {
                            "type": "customerReviews",
                            "id": clean_rev_id,
                        }
                    }
                },
            }
        }
        req = urllib.request.Request(
            "https://api.appstoreconnect.apple.com/v1/customerReviewResponses",
            data=json.dumps(asc_payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_json = json.loads(resp.read().decode("utf-8"))
                d_obj = resp_json.get("data") or {}
                resp_id = str(d_obj.get("id") or clean_rev_id)
                attr_obj = d_obj.get("attributes") or {}
                resp_state = str(attr_obj.get("state") or "PENDING_PUBLISH")
        except urllib.error.HTTPError as http_err:
            err_raw = ""
            try:
                err_raw = http_err.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise RuntimeError(f"Apple App Store Connect API hatası ({http_err.code}): {err_raw[:350]}")
    else:
        gp_token = _get_google_play_access_token()
        if not gp_token:
            raise RuntimeError("Google Play Developer API erişim anahtarı (Service Account) alınamadı.")
        gp_url = (
            "https://androidpublisher.googleapis.com/androidpublisher/v3/applications/"
            f"com.levitas.misilbaby/reviews/{urllib.parse.quote(clean_rev_id, safe='')}:reply"
        )
        req = urllib.request.Request(
            gp_url,
            data=json.dumps({"replyText": clean_body}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {gp_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                _ = resp.read()
                resp_id = clean_rev_id
                resp_state = "PUBLISHED"
        except urllib.error.HTTPError as http_err:
            err_raw = ""
            try:
                err_raw = http_err.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise RuntimeError(f"Google Play Developer API hatası ({http_err.code}): {err_raw[:350]}")

    with _BASELINE_LOCK:
        revs = list(OFFICIAL_STORE_BASELINE.get("store_reviews") or [])
        matched = False
        for rv in revs:
            if str(rv.get("review_id") or "") == clean_rev_id:
                rv["response_id"] = resp_id
                rv["response_body"] = clean_body
                rv["response_state"] = resp_state
                rv["response_date"] = today_tr_str
                matched = True
                break
        if matched:
            OFFICIAL_STORE_BASELINE["store_reviews"] = revs
        snap_copy = _mask_sensitive_sync_value(dict(OFFICIAL_STORE_BASELINE))

    db_s = SessionLocal()
    try:
        st_row = db_s.query(StoreSyncState).filter(StoreSyncState.state_key == "primary_store_baseline").first()
        if st_row:
            st_row.snapshot_json = snap_copy
            db_s.commit()
    except Exception as db_exc:
        logger.debug("Review reply cache update warning: %s", db_exc)
    finally:
        db_s.close()

    invalidate_analytics_summary_cache(mark_reconcile=False, reset_baseline_stamp=False)
    return {
        "status": "ok",
        "review_id": clean_rev_id,
        "platform": plat,
        "response_id": resp_id,
        "response_body": clean_body,
        "response_state": resp_state,
        "response_date": today_tr_str,
    }


@router.post("/review-reply")
async def reply_to_store_review(
    payload: StoreReviewReplyPayload,
    request: Request,
    pin: Optional[str] = Query(None),
    x_admin_pin: Optional[str] = Header(None),
):
    """
    Kurucu Kokpiti (Sekme 4: Mağaza Yorumları) üzerinden doğrudan Apple App Store Connect API
    (customerReviewResponses) veya Google Play Developer API (reviews:reply) ile resmi geliştirici yanıtı gönderir.
    """
    if not authorize_admin_request(request, pin, x_admin_pin, request.cookies.get(_ADMIN_SESSION_COOKIE)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Geçersiz veya eksik Yönetici PIN kodu.")
    try:
        res = await run_in_threadpool(
            _submit_store_review_reply_sync,
            payload.review_id,
            payload.response_body,
            payload.platform or "ios",
        )
        return res
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))
    except RuntimeError as rt_err:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(rt_err))


class SatisfactionPulseConfigPayload(BaseModel):
    active: bool = Field(default=True)
    target_platform: str = Field(default="ios", max_length=32)  # 'ios', 'android', 'all'
    topic_key: str = Field(default="sleep_save_fix", max_length=64)
    title_tr: str = Field(default="Uyku ve uyanma saatleri kaydı iyileştirildi", max_length=160)
    question_tr: str = Field(default="Son güncellememizden sonra uyku kayıtlarınız sorunsuz çalışıyor mu?", max_length=240)
    reference_author: Optional[str] = Field(default="", max_length=100)
    reference_review_id: Optional[str] = Field(default="", max_length=160)
    reset_counters: bool = Field(default=False)


class SatisfactionPulseResponsePayload(BaseModel):
    pulse_id: str = Field(..., min_length=2, max_length=80)
    device_uid: str = Field(..., min_length=3, max_length=120)
    outcome: str = Field(..., max_length=32)  # 'shown', 'satisfied', 'issue_persists'
    platform: Optional[str] = Field(default="ios", max_length=32)
    note: Optional[str] = Field(default="", max_length=500)


@router.post("/satisfaction-pulse")
def configure_satisfaction_pulse(
    payload: SatisfactionPulseConfigPayload,
    request: Request,
    pin: Optional[str] = Query(None),
    x_admin_pin: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """
    Kurucu Kokpiti (Sekme 4) üzerinden düşük puan veren (örn. Rabia Özcan Kahya — uyku saatleri kaydı)
    veya sorun yaşayan kullanıcılara uygulama içi + yerel bildirim memnuniyet yoklaması başlatır/durdurur.
    """
    if not authorize_admin_request(request, pin, x_admin_pin, request.cookies.get(_ADMIN_SESSION_COOKIE)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Geçersiz veya eksik Yönetici PIN kodu.")

    clean_plat = (payload.target_platform or "ios").strip().lower()
    if clean_plat not in ("ios", "android", "all"):
        clean_plat = "ios"

    tz_tr = timezone(timedelta(hours=3))
    now_tr_str = datetime.now(tz_tr).strftime("%d.%m.%Y %H:%M")

    st_row = (
        db.query(StoreSyncState)
        .filter(StoreSyncState.state_key == "active_satisfaction_pulse")
        .first()
    )
    prev_snap = (
        dict(st_row.snapshot_json)
        if (st_row and isinstance(st_row.snapshot_json, dict))
        else {}
    )
    is_new_campaign = bool(payload.reset_counters or not prev_snap.get("pulse_id") or (payload.active and not prev_snap.get("active")))
    pulse_id = (
        f"pulse_{int(time.time())}"
        if is_new_campaign
        else str(prev_snap.get("pulse_id") or f"pulse_{int(time.time())}")
    )

    new_snap = {
        "pulse_id": pulse_id,
        "active": bool(payload.active),
        "target_platform": clean_plat,
        "topic_key": (payload.topic_key or "sleep_save_fix").strip(),
        "title_tr": (payload.title_tr or "Uyku ve uyanma saatleri kaydı iyileştirildi").strip(),
        "question_tr": (payload.question_tr or "Son güncellememizden sonra uyku kayıtlarınız sorunsuz çalışıyor mu?").strip(),
        "reference_author": (payload.reference_author or "").strip(),
        "reference_review_id": (payload.reference_review_id or "").strip(),
        "triggered_at": now_tr_str if payload.active else str(prev_snap.get("triggered_at") or now_tr_str),
        "shown_count": 0 if payload.reset_counters else int(prev_snap.get("shown_count", 0) or 0),
        "satisfied_count": 0 if payload.reset_counters else int(prev_snap.get("satisfied_count", 0) or 0),
        "issue_persists_count": 0 if payload.reset_counters else int(prev_snap.get("issue_persists_count", 0) or 0),
        "shown_devices": [] if payload.reset_counters else list(prev_snap.get("shown_devices") or [])[-500:],
        "responded_devices": [] if payload.reset_counters else list(prev_snap.get("responded_devices") or [])[-500:],
    }

    if st_row:
        st_row.snapshot_json = new_snap
        st_row.last_synced_at_str = now_tr_str
    else:
        db.add(
            StoreSyncState(
                state_key="active_satisfaction_pulse",
                snapshot_json=new_snap,
                last_synced_at_str=now_tr_str,
            )
        )
    db.commit()
    invalidate_analytics_summary_cache(mark_reconcile=False, reset_baseline_stamp=False)
    return {
        "status": "ok",
        "satisfaction_pulse": {k: v for k, v in new_snap.items() if k not in ("shown_devices", "responded_devices")},
    }


@router.get("/satisfaction-pulse/active")
def get_active_satisfaction_pulse(
    platform: Optional[str] = Query("ios"),
    device_uid: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Mobil uygulama / WebView açılışında aktif bir memnuniyet & çözüm yoklaması olup olmadığını döner."""
    st_row = (
        db.query(StoreSyncState)
        .filter(StoreSyncState.state_key == "active_satisfaction_pulse")
        .first()
    )
    snap = (
        dict(st_row.snapshot_json)
        if (st_row and isinstance(st_row.snapshot_json, dict))
        else {}
    )
    if not snap.get("active"):
        return {"active": False}

    req_plat = "android" if "android" in (platform or "ios").lower() else "ios"
    tgt_plat = str(snap.get("target_platform") or "all").lower()
    if tgt_plat in ("ios", "android") and tgt_plat != req_plat:
        return {"active": False}

    clean_duid = (device_uid or "").strip()
    responded_list = list(snap.get("responded_devices") or [])
    if clean_duid and clean_duid in responded_list:
        return {"active": False, "already_responded": True}

    return {
        "active": True,
        "pulse_id": str(snap.get("pulse_id") or ""),
        "target_platform": tgt_plat,
        "topic_key": str(snap.get("topic_key") or "sleep_save_fix"),
        "title_tr": str(snap.get("title_tr") or ""),
        "question_tr": str(snap.get("question_tr") or ""),
        "reference_author": str(snap.get("reference_author") or ""),
    }


@router.post("/satisfaction-pulse/respond")
def respond_to_satisfaction_pulse(
    payload: SatisfactionPulseResponsePayload,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Kullanıcının uygulama içi memnuniyet yoklamasına verdiği yanıtı ('shown', 'satisfied', 'issue_persists') kaydeder.
    'issue_persists' durumunda doğrudan Feedback tablosuna kayıt düşer; 'satisfied' durumunda mağaza puanlaması tetiklenir.
    """
    st_row = (
        db.query(StoreSyncState)
        .filter(StoreSyncState.state_key == "active_satisfaction_pulse")
        .first()
    )
    if not st_row or not isinstance(st_row.snapshot_json, dict):
        return {"status": "inactive"}

    snap = dict(st_row.snapshot_json)
    clean_duid = (payload.device_uid or "").strip()[:120]
    clean_outcome = (payload.outcome or "").strip().lower()
    clean_plat = "android" if "android" in (payload.platform or "ios").lower() else "ios"

    shown_devs = list(snap.get("shown_devices") or [])
    resp_devs = list(snap.get("responded_devices") or [])

    if clean_outcome == "shown":
        if clean_duid and clean_duid not in shown_devs:
            shown_devs.append(clean_duid)
            snap["shown_devices"] = shown_devs[-500:]
            snap["shown_count"] = int(snap.get("shown_count", 0) or 0) + 1
    elif clean_outcome in ("satisfied", "issue_persists"):
        if clean_duid and clean_duid not in shown_devs:
            shown_devs.append(clean_duid)
            snap["shown_devices"] = shown_devs[-500:]
            snap["shown_count"] = int(snap.get("shown_count", 0) or 0) + 1
        if clean_duid and clean_duid not in resp_devs:
            resp_devs.append(clean_duid)
            snap["responded_devices"] = resp_devs[-500:]
            if clean_outcome == "satisfied":
                snap["satisfied_count"] = int(snap.get("satisfied_count", 0) or 0) + 1
            else:
                snap["issue_persists_count"] = int(snap.get("issue_persists_count", 0) or 0) + 1

        if clean_outcome == "issue_persists":
            note_txt = (payload.note or "").strip() or f"[{snap.get('title_tr', 'Çözüm Yoklaması')}] Kullanıcı sorunun devam ettiğini bildirdi."
            db.add(
                Feedback(
                    message=f"🔔 [Çözüm Yoklaması #{snap.get('pulse_id', '')}] {note_txt}",
                    sentiment="needs_improvement",
                    contact_info=clean_duid,
                    platform=clean_plat,
                    app_version="4.57.7",
                    ip_address=_extract_client_ip(request),
                )
            )

        db.add(
            AppInstallSignal(
                device_uid=clean_duid or "msl_pulse",
                event_type=f"pulse_{clean_outcome}",
                os_family=clean_plat,
                platform=f"{clean_plat}_native",
                app_version="4.57.7",
                ip_masked=_extract_client_ip(request),
                country="TR",
                match_confidence="unmatched",
            )
        )

    st_row.snapshot_json = snap
    db.commit()
    invalidate_analytics_summary_cache(mark_reconcile=False, reset_baseline_stamp=False)
    return {
        "status": "ok",
        "outcome": clean_outcome,
        "shown_count": int(snap.get("shown_count", 0) or 0),
        "satisfied_count": int(snap.get("satisfied_count", 0) or 0),
        "issue_persists_count": int(snap.get("issue_persists_count", 0) or 0),
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
    invalidate_analytics_summary_cache(mark_reconcile=False, reset_baseline_stamp=True)
    return {
        "status": "ok",
        "synced": sync_res.get("synced", False),
        "already_running": sync_res.get("already_running", False),
        "sources": sync_res.get("sources", []),
        "apple_connected": sync_res.get("apple_connected", False),
        "google_connected": sync_res.get("google_connected", False),
        "synced_at": sync_res.get("synced_at", ""),
    }


@router.get("/export.csv")
def export_analytics_csv(
    request: Request,
    pin: Optional[str] = Query(None),
    x_admin_pin: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """Tüm tıklama kayıtlarını Excel uyumlu ve Formula-Injection korumalı CSV olarak indirir."""
    if not authorize_admin_request(request, pin, x_admin_pin, request.cookies.get(_ADMIN_SESSION_COOKIE)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Geçersiz Yönetici PIN kodu.")

    ensure_historical_seed(db)
    clicks = db.query(BridgeClick).order_by(desc(BridgeClick.created_at)).limit(100000).all()
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


def _render_login_html(
    show_error: bool = False,
    status_code: int = status.HTTP_200_OK,
    error_message: str = "❌ Geçersiz PIN kodu. Lütfen tekrar deneyin.",
) -> HTMLResponse:
    safe_err = html.escape(error_message)
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="tr">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <meta name="referrer" content="no-referrer">
      <title>Mışıl Kurucu Kokpiti Girişi</title>
      <link rel="icon" type="image/x-icon" href="/favicon.ico">
      <link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png">
      <link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png">
      <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
      <link rel="manifest" href="/manifest.json">
      <meta name="theme-color" content="#13101C">
      <meta name="apple-mobile-web-app-capable" content="yes">
      <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
      <meta name="apple-mobile-web-app-title" content="Mışıl Kokpit">
      <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=Sora:wght@600;700&display=swap" rel="stylesheet">
      <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
          background: radial-gradient(circle at 18% 10%, rgba(244, 162, 97, 0.18) 0%, transparent 45%),
                      radial-gradient(circle at 82% 22%, rgba(116, 198, 157, 0.15) 0%, transparent 42%),
                      radial-gradient(circle at 50% 60%, rgba(165, 105, 189, 0.12) 0%, transparent 50%),
                      #13101C;
          color: #FAF5EE;
          font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
          min-height: 100vh;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 20px;
        }}
        .card {{
          background: rgba(33, 28, 44, 0.90);
          border: 1px solid rgba(244, 162, 97, 0.35);
          backdrop-filter: blur(18px);
          border-radius: 26px;
          padding: 36px 28px;
          width: 100%;
          max-width: 390px;
          text-align: center;
          box-shadow: 0 20px 44px rgba(10, 8, 16, 0.55);
        }}
        .login-brand-logo {{
          width: 68px;
          height: 68px;
          border-radius: 20px;
          margin: 0 auto 14px;
          display: block;
          object-fit: cover;
          border: 1.5px solid rgba(244, 162, 97, 0.55);
          box-shadow: 0 8px 24px rgba(244, 162, 97, 0.25);
        }}
        h2 {{ font-family: 'Sora', sans-serif; font-size: 20px; font-weight: 700; margin-bottom: 8px; color: #FAF5EE; }}
        p {{ color: #8F86A2; font-size: 13px; line-height: 1.5; margin-bottom: 24px; }}
        input {{
          width: 100%;
          padding: 14px 16px;
          border-radius: 14px;
          border: 1px solid rgba(244, 162, 97, 0.42);
          background: rgba(25, 20, 35, 0.65);
          color: #FAF5EE;
          font-size: 16px;
          font-weight: 600;
          text-align: center;
          letter-spacing: 2px;
          margin-bottom: 16px;
          outline: none;
        }}
        input:focus {{ border-color: #F4A261; box-shadow: 0 0 0 3px rgba(244, 162, 97, 0.22); }}
        button {{
          width: 100%;
          padding: 14px;
          border-radius: 14px;
          border: none;
          background: linear-gradient(135deg, #F4A261 0%, #C86446 100%);
          color: #13101C;
          font-size: 15px;
          font-weight: 800;
          cursor: pointer;
          box-shadow: 0 6px 18px rgba(244, 162, 97, 0.28);
        }}
        .err {{ color: #FF6B6B; font-size: 12px; margin-top: 12px; line-height: 1.45; display: {'block' if show_error else 'none'}; }}
      </style>
    </head>
    <body>
      <div class="card">
        <img src="/icon-192.png" alt="Mışıl Baby Logo" class="login-brand-logo" />
        <h2>Mışıl Kurucu Kokpiti</h2>
        <p>Kümülatif büyüme, App Store & Google Play resmi verileri ve görsel analiz panelini açmak için PIN giriniz.</p>
        <form method="POST" action="/api/v1/analytics/login">
          <input type="password" name="pin" placeholder="Yönetici PIN" autofocus autocomplete="off" />
          <button type="submit">Kokpiti Aç</button>
        </form>
        <div class="err">{safe_err}</div>
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
    try:
        is_authed = authorize_admin_request(request, pin, None, request.cookies.get(_ADMIN_SESSION_COOKIE))
    except HTTPException as auth_exc:
        return _render_login_html(
            show_error=True,
            status_code=auth_exc.status_code,
            error_message=f"⏳ {auth_exc.detail}",
        )
    if not is_authed:
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
        secure=_is_request_https(request),
        max_age=_ADMIN_SESSION_TTL_SECONDS,
        path="/",
    )
    return resp


@router.get("/dashboard", response_class=HTMLResponse)
def analytics_dashboard_page(
    request: Request,
    pin: Optional[str] = Query(None),
    period: Optional[str] = Query("all"),
    sync: Optional[str] = Query(None),
    updated: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Mışıl Baby v4.56.1 — Sıfır Statik Veri, SWR Hata Korumalı & Mobil-Öncelikli Kurucu Kokpiti.
    """
    session_token = request.cookies.get(_ADMIN_SESSION_COOKIE)
    authorized_by_session = _admin_session_token_is_valid(session_token)
    try:
        is_authed = authorize_admin_request(request, pin, None, session_token)
    except HTTPException as auth_exc:
        return _render_login_html(
            show_error=True,
            status_code=auth_exc.status_code,
            error_message=f"⏳ {auth_exc.detail}",
        )
    if not is_authed:
        login_status_code = status.HTTP_401_UNAUTHORIZED if pin else status.HTTP_200_OK
        return _render_login_html(show_error=bool(pin), status_code=login_status_code)

    new_session_cookie_value = None
    if not authorized_by_session and _pin_is_valid(pin):
        new_session_cookie_value = _make_admin_session_token((pin or "").strip().upper())

    sync_banner = ""
    if sync == "1":
        # Kokpit sayfasını 30-90 sn beyaz ekranda bekletmek yerine arka planda tekil (single-flight) senkron başlat
        started_bg = trigger_background_store_sync(days_back=7)
        last_sync_lbl = html.escape(str(OFFICIAL_STORE_BASELINE.get("last_synced_at") or "Aktif"))
        if started_bg:
            sync_banner = f"""
            <div class="toast-banner">
              🔄 <strong>Resmi Mağaza API Senkronizasyonu Arka Planda Başlatıldı:</strong> Kokpit anında açıldı; yeni veriler birkaç saniye içinde otomatik yansıyacaktır (Son kayıt: {last_sync_lbl}).
            </div>
            """
        else:
            sync_banner = f"""
            <div class="toast-banner">
              ⏳ <strong>Mağaza API Senkronizasyonu Zaten Çalışıyor:</strong> Devam eden arka plan taraması tamamlandığında veriler otomatik yenilenecektir (Son kayıt: {last_sync_lbl}).
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
    s = get_resilient_analytics_summary(db, period=clean_period)
    if s.get("stale_fallback") and not sync_banner:
        sync_banner = """
        <div class="toast-banner" style="background:rgba(245,158,11,0.12); border-color:rgba(245,158,11,0.35); color:#D97706;">
          ⚡ <strong>Hızlı Önbellek Koruma Modu (SWR):</strong> Veritabanı yoğunluğu nedeniyle son doğrulanmış önbellek verisi anında yüklendi; canlı yenileme arka planda devam ediyor.
        </div>
        """

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
            {"label": "🔍 App Store Arama", "count": r3_search_dl, "color": "#F4A261"},
            {"label": "📲 Sosyal & Meta Reklam (iOS)", "count": r3_ref_dl, "color": "#68A6C8"},
            {"label": "📅 Doğrudan / Diğer iOS", "count": r3_unattributed_recent_ios, "color": "#A569BD"},
            {"label": "✨ App Store Keşfet", "count": r3_browse_dl, "color": "#74C69D"},
            {"label": "🤖 Google Play (Organik + Meta + Bio)", "count": kpis["android_downloads"], "color": "#3D6E57"},
        ],
        center_val=str(kpis["downloads_total"]),
        center_lbl="KURULUM",
    )

    consolidated_countries = fl.get("country_revenue_breakdown") or []
    countries_list = (
        [
            {
                "code": c.get("code", "TR"),
                "name": c.get("name", "Türkiye"),
                "flag": c.get("flag", "🌍"),
                "count": int(c.get("downloads", 0) or 0),
            }
            for c in consolidated_countries
            if int(c.get("downloads", 0) or 0) > 0
        ]
        if consolidated_countries
        else (sb.get("apple_downloads_by_country") or [])
    )
    tr_dl = next((int(c.get("count", 0)) for c in countries_list if c.get("code") == "TR"), 0)
    de_dl = next((int(c.get("count", 0)) for c in countries_list if c.get("code") == "DE"), 0)
    us_dl = next((int(c.get("count", 0)) for c in countries_list if c.get("code") == "US"), 0)
    other_country_dl = max(0, kpis["downloads_total"] - tr_dl - de_dl - us_dl)

    donut_countries = _build_svg_donut(
        [
            {"label": "🇹🇷 Türkiye", "count": tr_dl, "color": "#74C69D"},
            {"label": "🇩🇪 Almanya", "count": de_dl, "color": "#F4A261"},
            {"label": "🇺🇸 ABD", "count": us_dl, "color": "#68A6C8"},
            {"label": "🌍 Diğer Ülkeler", "count": other_country_dl, "color": "#A569BD"},
        ],
        center_val=f"{len(countries_list)} Ülke",
        center_lbl=f"{kpis['downloads_total']} Kurulum",
    )

    top_h1 = s["golden_hours"][0]["hour"] if s["golden_hours"] else "00:00"
    top_h2 = s["golden_hours"][1]["hour"] if len(s["golden_hours"]) > 1 else "01:00"

    donut_night_day = _build_svg_donut(
        [
            {"label": "🌙 Gece (21:00–04:00)", "count": nvd["night_clicks"], "color": "#A569BD"},
            {"label": "☀️ Gündüz (05:00–20:00)", "count": nvd["day_clicks"], "color": "#F4A261"},
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

    spark_imp_svg = _build_svg_sparkline([d.get("daily_impressions", 0) for d in t_days if not d.get("is_r14_pending")], "#F4A261", "spImp")
    spark_vis_svg = _build_svg_sparkline([d.get("daily_visits_clicks", 0) for d in t_days], "#68A6C8", "spVis")
    spark_dl_svg = _build_svg_sparkline([d.get("daily_downloads", 0) for d in t_days if not d.get("is_store_pending")], "#74C69D", "spDl")
    spark_vip_svg = _build_svg_sparkline([d.get("cum_downloads", 0) for d in t_days], "#A569BD", "spVip")

    sync_sources_rows_html = ""
    for fs in s.get("source_freshness", []):
        st_badge_col = "var(--stage-3)" if fs["status"] == "realtime" else ("var(--stage-2)" if fs["status"] == "reconciling" else "var(--stage-1)")
        st_badge_bg = "rgba(61,110,87,0.16)" if fs["status"] == "realtime" else ("rgba(59,110,140,0.16)" if fs["status"] == "reconciling" else "rgba(200,100,70,0.16)")
        sync_sources_rows_html += f"""
        <tr>
          <td><strong>{html.escape(str(fs['label']))}</strong></td>
          <td><code>{html.escape(str(fs['id']))}</code></td>
          <td><span class="badge" style="background:{st_badge_bg}; color:{st_badge_col};">{html.escape(str(fs['badge']))}</span></td>
          <td style="color:var(--text-secondary);">{html.escape(str(fs['detail']))}</td>
        </tr>
        """

    gov_rows_html = ""
    for gm in s.get("data_governance_matrix", []):
        lat_str = str(gm.get("latency_class", ""))
        is_t0 = "T-0" in lat_str
        lat_bg = "rgba(61,110,87,0.16)" if is_t0 else "rgba(59,110,140,0.16)"
        lat_col = "var(--stage-3)" if is_t0 else "var(--stage-2)"
        gov_rows_html += f"""
        <tr>
          <td>
            <strong>{html.escape(str(gm.get('domain', '')))}</strong>
            <div style="font-size:11.5px; color:var(--text-muted); margin-top:3px;">{html.escape(str(gm.get('metrics', '')))}</div>
          </td>
          <td><code>{html.escape(str(gm.get('ssot_table', '')))}</code></td>
          <td style="color:var(--text-secondary);">{html.escape(str(gm.get('update_method', '')))}</td>
          <td style="font-weight:700; color:var(--text-primary);">{html.escape(str(gm.get('frequency', '')))}</td>
          <td><span class="badge" style="background:{lat_bg}; color:{lat_col};">{html.escape(lat_str)}</span></td>
          <td style="font-variant-numeric:tabular-nums; color:var(--text-secondary);">{html.escape(str(gm.get('last_sync', '')))}</td>
          <td style="font-size:12px; color:var(--text-secondary);">{html.escape(str(gm.get('consistency_rule', '')))}</td>
        </tr>
        """

    arch_cards_html = ""
    arch_colors = ["var(--stage-3)", "var(--stage-2)", "var(--stage-4)", "var(--stage-1)"]
    for idx_ap, ap in enumerate(s.get("architecture_principles", [])):
        ac_col = arch_colors[idx_ap % len(arch_colors)]
        arch_cards_html += f"""
        <div class="step-box" style="border-left: 4px solid {ac_col};">
          <div class="step-num" style="color:{ac_col};">MİMARİ İLKE #{idx_ap + 1}</div>
          <div class="step-val" style="font-size:16px; line-height:1.35; margin-bottom:6px;">{html.escape(str(ap.get('title', '')))}</div>
          <div class="step-sub">{html.escape(str(ap.get('desc', '')))}</div>
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
            f"height:{dl_h}%; background:rgba(116,198,157,0.22); border:1.5px dashed #3D6E57;"
            if is_pending and cum_android_val == 0
            else (
                f"height:{dl_h}%; background:linear-gradient(180deg, #68A6C8 0%, #68A6C8 {and_share_pct}%, #74C69D {and_share_pct}%, #3D6E57 100%);"
                if cum_android_val > 0
                else f"height:{dl_h}%; background:linear-gradient(180deg, #74C69D 0%, #3D6E57 100%);"
            )
        )
        top_val_cum = f"{d['cum_downloads']}*" if is_pending else str(d["cum_downloads"])

        cum_bars_html += f"""
        <div class="t-col {'t-today' if is_today else ''} {'t-pending' if is_pending else ''}" title="{html.escape(cum_tip)}">
          <div class="t-top-val" style="color:{'#C86446' if is_pending else '#3D6E57'};">{top_val_cum}</div>
          <div class="t-bars-pair">
            <div class="t-bar" style="{bar_style_cum}"></div>
          </div>
          <div class="t-lbl">{html.escape(d['label'])}</div>
        </div>
        """

        ios_h = max(10, round((cum_ios_val / max_cum_ios) * 100)) if cum_ios_val > 0 else 5
        ios_bar_style = (
            f"height:{ios_h}%; background:rgba(116,198,157,0.22); border:1.5px dashed #3D6E57;"
            if is_pending
            else f"height:{ios_h}%; background:linear-gradient(180deg, #74C69D 0%, #3D6E57 100%);"
        )
        cum_ios_bars_html += f"""
        <div class="t-col {'t-today' if is_today else ''} {'t-pending' if is_pending else ''}" title="{html.escape(d['label'])}: 🍏 Apple iOS Kümülatif {cum_ios_val} Kurulum{html.escape(pending_note)}">
          <div class="t-top-val" style="color:{'#C86446' if is_pending else '#3D6E57'};">{cum_ios_val}{'*' if is_pending else ''}</div>
          <div class="t-bars-pair">
            <div class="t-bar" style="{ios_bar_style}"></div>
          </div>
          <div class="t-lbl">{html.escape(d['label'])}</div>
        </div>
        """

        and_h = max(12, round((cum_android_val / max_cum_and) * 100)) if cum_android_val > 0 else 6
        and_bar_style = (
            f"height:{and_h}%; background:linear-gradient(180deg, #68A6C8 0%, #3B6E8C 100%);"
            if cum_android_val > 0
            else "height:6%; background:rgba(150,122,98,0.25);"
        )
        cum_android_bars_html += f"""
        <div class="t-col {'t-today' if is_today else ''}" title="{html.escape(d['label'])}: 🤖 Google Play Android Kümülatif {cum_android_val} Kurulum">
          <div class="t-top-val" style="color:{'#3B6E8C' if cum_android_val > 0 else '#8F86A2'};">{cum_android_val}</div>
          <div class="t-bars-pair">
            <div class="t-bar" style="{and_bar_style}"></div>
          </div>
          <div class="t-lbl">{html.escape(d['label'])}</div>
        </div>
        """

        if is_pending and d["daily_downloads"] == 0 and d["daily_visits_clicks"] > 0:
            sig_h = max(18, round((d["daily_visits_clicks"] / max_daily_clicks) * 75))
            d_dl_str = f"⏳{d['daily_visits_clicks']} Tık"
            bar_style_daily = f"height:{sig_h}%; background:rgba(104,166,200,0.22); border:1.5px dashed #3B6E8C;"
            top_color_daily = "#3B6E8C"
        else:
            d_dl_h = max(12, round((d["daily_downloads"] / max_daily_dl) * 100)) if d["daily_downloads"] > 0 else 6
            d_dl_str = f"+{d['daily_downloads']}" if d["daily_downloads"] > 0 else "0"
            bar_style_daily = f"height:{d_dl_h}%; background:linear-gradient(180deg, #F4A261 0%, #C86446 100%);"
            top_color_daily = "#C86446"
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
    star_dist_map = s.get("reviews_star_distribution") or {}
    all_sd = star_dist_map.get("all") or {}
    ios_sd = star_dist_map.get("ios") or {}
    and_sd = star_dist_map.get("android") or {}

    if all_sd.get("overall_count", 0) > 0:
        avg_stars_label = f"{all_sd.get('overall_avg_str', 'Yorum Yok')} ({all_sd.get('overall_count', 0)} Oy • {all_sd.get('written_count', reviews_total_cnt)} Yorum)"
    elif reviews_total_cnt > 0:
        avg_stars_val = round(
            sum(max(1, min(5, int(r.get("rating", 5) or 5))) for r in reviews_list) / reviews_total_cnt,
            1,
        )
        avg_stars_label = f"{avg_stars_val} ★"
    else:
        avg_stars_label = "Yorum Yok"

    def _render_platform_star_box(
        plat_key: str,
        plat_title: str,
        sd_obj: Dict[str, Any],
        accent_color: str,
        id_prefix: str = "star",
    ) -> str:
        ov_str = html.escape(str(sd_obj.get("overall_avg_str") or "Yorum Yok"))
        ov_cnt = int(sd_obj.get("overall_count", 0) or 0)
        wr_str = html.escape(str(sd_obj.get("written_avg_str") or "Yorum Yok"))
        wr_cnt = int(sd_obj.get("written_count", 0) or 0)
        sil_cnt = int(sd_obj.get("silent_ratings_count", 0) or 0)
        bars_list = sd_obj.get("bars") or [
            {"star": st_l, "count": 0, "written_count": 0, "silent_count": 0, "pct": 0.0} for st_l in (5, 4, 3, 2, 1)
        ]
        bars_rows_html = ""
        for b_it in bars_list:
            st_lvl = int(b_it.get("star", 5) or 5)
            st_cnt = int(b_it.get("count", 0) or 0)
            st_wr = int(b_it.get("written_count", st_cnt) or 0)
            st_sil = int(b_it.get("silent_count", 0) or 0)
            st_pct = float(b_it.get("pct", 0.0) or 0.0)
            b_col = "#10B981" if st_lvl >= 4 else ("#F59E0B" if st_lvl == 3 else "#EF4444")
            cnt_label = f"{st_cnt} ({st_wr}+{st_sil})" if st_sil > 0 else f"{st_cnt}"
            bars_rows_html += f"""
            <div style="display:flex; align-items:center; gap:8px; font-size:12px; margin-top:5px; font-variant-numeric:tabular-nums;">
              <span style="width:32px; font-weight:800; color:var(--text-primary);">{st_lvl} ★</span>
              <div style="flex:1; height:9px; background:rgba(148,163,184,0.18); border-radius:999px; overflow:hidden;">
                <div class="js-star-fill-{plat_key}-{st_lvl}" id="{id_prefix}BarFill_{plat_key}_{st_lvl}" style="width:{st_pct}%; height:100%; background:{b_col}; border-radius:999px;"></div>
              </div>
              <strong class="js-star-cnt-{plat_key}-{st_lvl}" id="{id_prefix}BarCnt_{plat_key}_{st_lvl}" style="min-width:44px; text-align:right; color:var(--text-primary);">{cnt_label}</strong>
              <span class="js-star-pct-{plat_key}-{st_lvl}" id="{id_prefix}BarPct_{plat_key}_{st_lvl}" style="min-width:42px; text-align:right; color:var(--text-muted); font-size:11px;">%{st_pct}</span>
            </div>
            """
        silent_chip = (
            f'<span class="kpi-micro-chip js-star-silent-{plat_key}" id="{id_prefix}SilentChip_{plat_key}" title="Yorum yazmadan yalnızca yıldız veren kullanıcılar">+{sil_cnt} Yorumsuz Oy</span>'
            if sil_cnt > 0
            else f'<span class="kpi-micro-chip js-star-silent-{plat_key}" id="{id_prefix}SilentChip_{plat_key}" style="display:none;"></span>'
        )
        return f"""
        <div class="step-box" data-platform="{plat_key}" id="{id_prefix}DistBox_{plat_key}" style="border-left: 4px solid {accent_color};">
          <div style="display:flex; align-items:center; justify-content:space-between; gap:6px; flex-wrap:wrap; margin-bottom:6px;">
            <span style="font-size:12.5px; font-weight:800; color:{accent_color};">{plat_title}</span>
            <div style="display:flex; align-items:center; gap:5px; flex-wrap:wrap;">
              <span class="badge js-star-overall-{plat_key}" id="{id_prefix}OverallBadge_{plat_key}" style="background:rgba(245,158,11,0.16); color:#D97706; font-size:11px; padding:2px 8px;" title="Mağaza Genel Puanı (Yorumsuz Oylar Dahil)">Mağaza: {ov_str} ({ov_cnt})</span>
              <span class="badge badge-meta js-star-written-{plat_key}" id="{id_prefix}WrittenBadge_{plat_key}" style="font-size:10.5px; padding:2px 7px;" title="Yazılı Yorum Bırakanların Ortalaması">Yazılı: {wr_str} ({wr_cnt})</span>
              {silent_chip}
            </div>
          </div>
          <div>
            {bars_rows_html}
          </div>
        </div>
        """

    star_dist_boxes_html = (
        _render_platform_star_box("ios", "🍏 iOS App Store (5★ ➔ 1★ Oy Dağılımı)", ios_sd, "#059669", id_prefix="star")
        + _render_platform_star_box("android", "🤖 Android Google Play (5★ ➔ 1★ Oy Dağılımı)", and_sd, "#2563EB", id_prefix="star")
    )
    tab1_star_dist_boxes_html = (
        _render_platform_star_box("ios", "🍏 iOS App Store (5★ ➔ 1★ Oy Dağılımı)", ios_sd, "#059669", id_prefix="t1Star")
        + _render_platform_star_box("android", "🤖 Android Google Play (5★ ➔ 1★ Oy Dağılımı)", and_sd, "#2563EB", id_prefix="t1Star")
    )

    pulse_info = s.get("satisfaction_pulse") or {}
    pulse_is_active = bool(pulse_info.get("active", False))
    pulse_status_badge = (
        f"🟢 Aktif ({html.escape(str(pulse_info.get('target_platform', 'ios')).upper())})"
        if pulse_is_active
        else "⚪ Pasif"
    )
    pulse_status_bg = "rgba(16,185,129,0.16)" if pulse_is_active else "rgba(148,163,184,0.15)"
    pulse_status_col = "#059669" if pulse_is_active else "var(--text-muted)"

    reviews_html = ""
    for idx_rv, rv in enumerate(reviews_list):
        safe_rating = max(1, min(5, int(rv.get("rating", 5) or 5)))
        stars = "⭐" * safe_rating
        badge_txt = str(rv.get("badge", "Mağaza"))
        rv_plat = "ios" if "iOS" in badge_txt or rv.get("store") == "App Store" else "android"
        rev_id = str(rv.get("review_id") or "").strip()
        resp_body = str(rv.get("response_body") or "").strip()
        resp_state = str(rv.get("response_state") or "").strip()
        resp_date = str(rv.get("response_date") or "").strip()
        dom_key = html.escape(rev_id if rev_id else f"rv_{idx_rv}")
        state_badge_html = ""
        if resp_body:
            is_pend = "PENDING" in resp_state.upper()
            st_lbl = "⏳ Apple Onayında (PENDING_PUBLISH)" if is_pend else "✔ Yayında (PUBLISHED)"
            st_col = "#D97706" if is_pend else "var(--stage-3)"
            st_bg = "rgba(217, 119, 6, 0.14)" if is_pend else "rgba(var(--stage-3-rgb), 0.14)"
            dt_suffix = f" • {html.escape(resp_date)}" if resp_date else ""
            state_badge_html = f'<span class="badge" style="background:{st_bg}; color:{st_col}; font-size:10px; padding:2px 8px;">{st_lbl}{dt_suffix}</span>'

        existing_reply_block = ""
        if resp_body:
            existing_reply_block = f"""
            <div class="review-dev-reply" id="devReplyBox_{dom_key}">
              <div style="display:flex; justify-content:space-between; align-items:center; gap:6px; margin-bottom:4px; flex-wrap:wrap;">
                <strong style="font-size:11px; color:var(--brand-indigo);">💬 Mışıl Baby Geliştirici Yanıtı</strong>
                {state_badge_html}
              </div>
              <div class="review-dev-reply-text" id="devReplyText_{dom_key}">{html.escape(resp_body)}</div>
            </div>
            """
        else:
            existing_reply_block = f"""
            <div class="review-dev-reply" id="devReplyBox_{dom_key}" style="display:none;">
              <div style="display:flex; justify-content:space-between; align-items:center; gap:6px; margin-bottom:4px; flex-wrap:wrap;">
                <strong style="font-size:11px; color:var(--brand-indigo);">💬 Mışıl Baby Geliştirici Yanıtı</strong>
                <span class="badge" id="devReplyState_{dom_key}" style="background:rgba(var(--stage-3-rgb),0.14); color:var(--stage-3); font-size:10px; padding:2px 8px;">✔ Gönderildi</span>
              </div>
              <div class="review-dev-reply-text" id="devReplyText_{dom_key}"></div>
            </div>
            """

        low_star_pulse_btn = ""
        if safe_rating <= 3:
            safe_author_js = html.escape(str(rv.get("author", "Kullanıcı")).replace("'", "").replace('"', ""))
            safe_title_js = html.escape(str(rv.get("title", "Uyku kaydı")).replace("'", "").replace('"', ""))
            low_star_pulse_btn = f"""
            <button type="button" class="collapse-btn" onclick="prefillAndTriggerPulse('{rv_plat}', '{safe_author_js}', '{html.escape(rev_id)}', '{safe_title_js}')" style="font-size:11px; padding:4px 10px; border-color:rgba(244,162,97,0.45); color:#F4A261;" title="Bu sorunu yaşayan kullanıcılara uygulama içi memnuniyet & çözüm bildirimi gönder">🔔 Çözüm Yoklaması Tetikle</button>
            """

        reply_action_html = ""
        if rev_id:
            btn_lbl = "✏️ Yanıtı Güncelle (API)" if resp_body else "💬 Mağaza Yorumunu Yanıtla (API)"
            reply_action_html = f"""
            <div style="margin-top:8px;">
              <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
                <button type="button" class="collapse-btn" onclick="toggleReviewReplyDrawer('{dom_key}')" id="btnToggleReply_{dom_key}" style="font-size:11px; padding:4px 10px;">{btn_lbl}</button>
                {low_star_pulse_btn}
              </div>
              <div id="replyDrawer_{dom_key}" style="display:none; margin-top:8px;">
                <textarea id="replyInput_{dom_key}" rows="3" placeholder="Resmi mağaza geliştirici yanıtınızı yazın..." style="width:100%; border-radius:10px; border:1px solid var(--border-subtle); background:var(--bg-card); color:var(--text-primary); padding:8px 10px; font-size:12px; font-family:inherit; resize:vertical;">{html.escape(resp_body)}</textarea>
                <div style="display:flex; justify-content:flex-end; align-items:center; gap:8px; margin-top:6px;">
                  <button type="button" class="btn" onclick="toggleReviewReplyDrawer('{dom_key}')" style="padding:5px 10px; font-size:11px;">Vazgeç</button>
                  <button type="button" class="subcat-pill active" id="btnSendReply_{dom_key}" onclick="submitStoreReviewReply('{html.escape(rev_id)}', '{rv_plat}', '{dom_key}')" style="padding:5px 12px; font-size:11px;">🚀 Resmi API İle Gönder</button>
                </div>
              </div>
            </div>
            """

        reviews_html += f"""
        <div class="review-bubble" data-platform="{rv_plat}" data-review-id="{html.escape(rev_id)}">
          <div class="review-head">
            <div>
              <span class="badge {'badge-meta' if rv_plat == 'ios' else 'badge-gp'}">{html.escape(badge_txt)}</span>
              <strong style="color:var(--text-primary); margin-left:6px;">{html.escape(str(rv.get('title', '')))}</strong>
            </div>
            <span style="font-size:11.5px; color:#D97706; font-weight:700;">{stars} • {html.escape(str(rv.get('date', '')))}</span>
          </div>
          <p class="review-body">“{html.escape(str(rv.get('body', '')))}”</p>
          <div class="review-foot">👤 {html.escape(str(rv.get('author', 'Kullanıcı')))} — {html.escape(str(rv.get('store', '')))}</div>
          {existing_reply_block}
          {reply_action_html}
        </div>
        """
    if not reviews_html:
        reviews_html = """
        <div class="bento-card" style="grid-column: 1 / -1; text-align:center; color:var(--text-muted);">
          Henüz senkronize edilmiş mağaza yorumu bulunmuyor. Arka plan mağaza senkronizasyonu tamamlandığında yorumlar otomatik listelenir.
        </div>
        """

    tz_tr = timezone(timedelta(hours=3))
    fb_total_cnt = int(pf.get("feedbacks_total_count", pf.get("feedbacks_count", 0)) or 0)
    fb_24h_cnt = int(pf.get("feedbacks_last_24h_count", 0) or 0)
    in_app_feedbacks_html = ""
    for fb_item in (pf.get("feedbacks_list") or [])[:50]:
        fb_dt = getattr(fb_item, "created_at", None)
        if fb_dt:
            fb_dt_utc = fb_dt.replace(tzinfo=timezone.utc) if fb_dt.tzinfo is None else fb_dt
            fb_dt_tr = fb_dt_utc.astimezone(tz_tr).strftime("%d.%m.%Y %H:%M")
        else:
            fb_dt_tr = "-"
        fb_plat_raw = str(getattr(fb_item, "platform", "") or "").lower()
        if "ios" in fb_plat_raw or "iphone" in fb_plat_raw:
            fb_plat_attr = "ios"
            fb_plat_badge = '<span class="badge badge-meta">🍏 iOS</span>'
        elif "android" in fb_plat_raw:
            fb_plat_attr = "android"
            fb_plat_badge = '<span class="badge badge-gp">🤖 Android</span>'
        else:
            fb_plat_attr = "all"
            fb_plat_badge = '<span class="badge" style="background:rgba(148,163,184,0.16); color:var(--text-secondary);">🌐 Web</span>'

        fb_sent_raw = str(getattr(fb_item, "sentiment", "") or "suggestion").lower()
        fb_msg_raw = str(getattr(fb_item, "message", "") or "")
        if "çözüm yoklaması" in fb_msg_raw.lower():
            fb_sent_badge = '<span class="badge" style="background:rgba(var(--stage-5-rgb),0.14); color:var(--stage-5);">🔔 Çözüm Yoklaması</span>'
        elif fb_sent_raw in ("awake", "still_awake"):
            fb_sent_badge = '<span class="badge" style="background:rgba(var(--stage-5-rgb),0.14); color:var(--stage-5);">🥱 Uyuyamadı</span>'
        elif fb_sent_raw == "needs_improvement":
            fb_sent_badge = '<span class="badge" style="background:rgba(217,119,6,0.15); color:#D97706;">🟡 Zorlandık</span>'
        else:
            fb_sent_badge = '<span class="badge" style="background:rgba(16,185,129,0.14); color:#059669;">💡 Öneri / Mesaj</span>'

        fb_age = getattr(fb_item, "baby_age_months", None)
        fb_age_chip = (
            f'<span class="kpi-micro-chip">👶 {int(fb_age)} Aylık</span>'
            if fb_age is not None
            else ""
        )
        fb_ver_raw = str(getattr(fb_item, "app_version", "") or "").strip()
        fb_ver_chip = (
            f'<span class="kpi-micro-chip">v{html.escape(fb_ver_raw)}</span>'
            if fb_ver_raw
            else ""
        )
        fb_contact_raw = str(getattr(fb_item, "contact_info", "") or "").strip()
        fb_contact_block = (
            f'<div class="review-foot" style="margin-top:6px; color:#2563EB; font-weight:700;">📞 İletişim: {html.escape(fb_contact_raw)}</div>'
            if fb_contact_raw
            else ""
        )
        in_app_feedbacks_html += f"""
        <div class="review-bubble in-app-feedback-item" data-platform="{fb_plat_attr}">
          <div class="review-head">
            <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
              {fb_plat_badge}
              {fb_sent_badge}
              {fb_age_chip}
              {fb_ver_chip}
            </div>
            <span style="font-size:11.5px; color:var(--text-muted); font-weight:700; font-variant-numeric:tabular-nums;">🕒 {fb_dt_tr}</span>
          </div>
          <p class="review-body" style="white-space:pre-wrap; margin:6px 0 2px;">{html.escape(fb_msg_raw)}</p>
          {fb_contact_block}
        </div>
        """

    if not in_app_feedbacks_html:
        in_app_feedbacks_html = """
        <div class="bento-card" id="inAppFeedbacksEmptyState" style="grid-column: 1 / -1; text-align:center; color:var(--text-muted); padding:18px;">
          Henüz uygulama içinden gönderilmiş anne mesajı veya geri bildirim bulunmuyor. Uygulama içinden (veya memnuniyet yoklamasından) mesaj geldiğinde anında burada listelenir.
        </div>
        """
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

    vis_of_imp_pct = s.get("platform_split", {}).get("all", {}).get("vis_of_imp_pct", 0.0)
    dl_of_vis_pct = s.get("platform_split", {}).get("all", {}).get("cvr_pct", round((f_dl / f_vis) * 100, 1) if f_vis > 0 else 0)
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

    imp_search_pct = round((imp_search / max(1, imp_search + imp_browse)) * 100) if (imp_search + imp_browse) > 0 else 0
    vis_store_pct = round((kpis["store_page_views"] / max(1, f_vis)) * 100) if f_vis > 0 else 0
    dl_ios_pct = round((kpis["ios_downloads"] / max(1, f_dl)) * 100) if f_dl > 0 else 0
    vip_denom = max(1, paid_conv + active_trials + offer_code_subs)
    vip_paid_pct = round((paid_conv / vip_denom) * 100) if f_vip > 0 else 0
    vip_trial_pct = round((active_trials / vip_denom) * 100) if f_vip > 0 else 0
    vip_code_pct = max(0, 100 - vip_paid_pct - vip_trial_pct) if f_vip > 0 else 0

    renewal_calendar_html = ""
    for rc in fl["renewal_forecast_calendar"]:
        subs_badges = " • ".join(html.escape(x) for x in rc["subscribers"])
        is_rec_cal = bool(rc.get("is_reconciling") or rc.get("reconciliation_status") == "reconciling")
        rc_plat_val = str(rc.get("platform") or "all")
        plat_attr = f' data-platform="{html.escape(rc_plat_val)}"' if rc_plat_val in ("ios", "android") else ""
        rec_border = "#2563EB" if is_rec_cal else "#059669"
        if is_rec_cal:
            rec_lbl = "🔄 GOOGLE PLAY MUTABAKATINDA" if rc_plat_val == "android" else ("🔄 APPLE MUTABAKATINDA" if rc_plat_val == "ios" else "🔄 MAĞAZA MUTABAKATINDA")
        else:
            rec_lbl = "📅 YAKLAŞAN VADE"
        renewal_calendar_html += f"""
        <div class="step-box"{plat_attr} style="border-left: 4px solid {rec_border};">
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
            paid_lbl_html = html.escape(str(sl.get("lifecycle_badge") or "💳 Ücretli Aktif"))
            st_badge = f'<span class="badge" style="background:rgba(16,185,129,0.15); color:#059669;">{paid_lbl_html}</span>'
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
            f"<strong style='color:#059669;'>%{am['cvr_pct']}</strong><span class='sr-only'> ({html.escape(str(am['cvr_basis']))})</span>"
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
        c_pct = round((c_cnt / f_dl) * 100, 1) if f_dl > 0 else 0.0
        safe_flag = html.escape(str(c_item.get("flag", "🌍")))
        country_rows_html += f"""
        <tr>
          <td>{safe_flag} <strong>{html.escape(str(c_item.get('name', '')))}</strong> ({html.escape(str(c_item.get('code', '')))})</td>
          <td style="font-weight:800; color:#059669; font-variant-numeric:tabular-nums;">{c_cnt} Kurulum</td>
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
        else f"🔍 <strong>Neden Android'de 0 Abone Görünüyor? (Canlı API Teşhisi):</strong> Google Play Developer API (<code>monetization.subscriptions</code>) üzerinde <strong>Mışıl Baby Yıllık VIP (599.99 ₺ • Denemesiz)</strong> ve <strong>Mışıl Baby Aylık VIP (İlk Ay 49.99 ₺ ➔ 149.99 ₺/ay)</strong> paketleriniz <strong>ACTIVE (Yayında)</strong> durumdadır. Ancak <strong>{ps_and.get('touchpoints', 0)} Android köprü tıklamasından</strong> gelen <strong>{kpis['android_downloads']} Android kurulumu</strong> içerisinden henüz Google Play aboneliği başlatan kullanıcı olmamıştır (<strong>0 Aktif Android Abone</strong>). Yeni bir Android abonesi başladığında bu tabloya otomatik olarak düşer."
    )

    sr = fl.get("store_reconciliation") or {}
    sr_all = sr.get("all_time") or {}
    sr_7d = sr.get("last_7d_t1") or {}
    sr_yest = sr.get("yesterday_t1") or {}
    sr_today = sr.get("today_t0") or {}
    sr_sel = sr.get("period_selected") or sr_all
    sr_anchor = html.escape(str(sr.get("apple_latest_report_date") or "-"))
    sr_7d_start = html.escape(str(sr.get("apple_7d_window_start") or "-"))
    sr_lag = int(sr.get("apple_lag_days", 1) or 1)
    sr_win_lbl = html.escape(str(sr.get("period_window_label") or s.get("period_label") or "Tüm Zamanlar"))
    sr_cg_cnt = int(sr.get("rc_v2_crossgrades_count", 0) or 0)
    sr_cg_gross = float(sr.get("rc_v2_crossgrades_gross_try", 0.0) or 0.0)
    sr_cg_net = float(sr.get("rc_v2_crossgrades_net_try", 0.0) or 0.0)

    if clean_period == "all":
        card1_big_html = (
            f"{fl['realized_net_proceeds_try']:.2f} ₺ <span style='font-size:15px; color:var(--text-muted);'>Net</span> "
            f"<span style='font-size:13px; color:#059669; font-weight:700;'>(~${fl.get('realized_net_proceeds_usd', 0.0):.2f})</span>"
        )
        card1_desc_html = (
            f"Tüm Zamanlar Brüt: <strong>{fl['realized_gross_try']:.2f} ₺ (~${fl.get('realized_gross_usd', 0.0):.2f} Sales)</strong> • "
            f"Son 7G (Apple T-1): <strong>{sr_7d.get('gross_try', 0.0):.2f} ₺ Brüt / {sr_7d.get('net_try', 0.0):.2f} ₺ Net (~${sr_7d.get('net_usd', 0.0):.2f})</strong> • "
            f"Aktif MRR (%15 Komisyon): <strong>{fl['active_paid_mrr_net_try']:.2f} ₺ Net/Ay</strong> (<strong>{fl.get('auto_renewing_paid_subs_count', fl['paid_subs_count'])}/{fl['paid_subs_count']} Oto-Yenileme Açık</strong>)."
        )
    else:
        card1_big_html = (
            f"{fl.get('period_realized_net_proceeds_try', 0.0):.2f} ₺ <span style='font-size:15px; color:var(--text-muted);'>Net ({html.escape(s['period_label'])})</span> "
            f"<span style='font-size:13px; color:#059669; font-weight:700;'>(~${fl.get('period_realized_net_proceeds_usd', 0.0):.2f})</span>"
        )
        card1_desc_html = (
            f"Seçili Dönem Brüt: <strong>{fl.get('period_realized_gross_try', 0.0):.2f} ₺ (~${fl.get('period_realized_gross_usd', 0.0):.2f} Sales • {fl.get('period_paid_subs_count', 0)} Tahsilat)</strong> • "
            f"Kümülatif Tüm Zamanlar: <strong>{fl['realized_gross_try']:.2f} ₺ Brüt / {fl['realized_net_proceeds_try']:.2f} ₺ Net (~${fl.get('realized_net_proceeds_usd', 0.0):.2f})</strong>."
        )

    onb_f = s.get("onboarding_step_funnel") or pf.get("onboarding_step_funnel") or {}
    onb_ab_cohorts = onb_f.get("ab_cohorts") or {}
    onb_ga_f = onb_ab_cohorts.get("group_a") or {}
    onb_gb_f = onb_ab_cohorts.get("group_b") or {}
    onb_ga_total_devs = int(onb_ga_f.get("total_tracked_onboarding_devices", 0) or 0)
    onb_gb_total_devs = int(onb_gb_f.get("total_tracked_onboarding_devices", 0) or 0)
    onb_steps_list = onb_f.get("steps") or []
    onb_total_devs = int(onb_f.get("total_tracked_onboarding_devices", 0) or 0)
    onb_comp_pct = onb_f.get("step0_to_step9_completion_pct")
    onb_comp_str = f"%{onb_comp_pct}" if onb_comp_pct is not None else "Veri Yok"
    onb_big_drop = onb_f.get("biggest_dropoff_step")
    if onb_big_drop and int(onb_big_drop.get("dropoff_count", 0) or 0) > 0:
        onb_drop_badge_str = (
            f"⚠️ {onb_big_drop.get('title')} "
            f"(-{onb_big_drop.get('dropoff_count')} / -%{onb_big_drop.get('dropoff_pct')})"
        )
    else:
        onb_drop_badge_str = "🟢 Kayıp Yok" if onb_total_devs > 0 else "⏳ Bekleniyor"

    onb_purch_a = int(onb_f.get("ab_a_purchases_count", onb_f.get("ab_a_vip_started_unique_devices", 0)) or 0)
    onb_purch_b = int(onb_f.get("ab_b_purchases_count", onb_f.get("ab_b_vip_started_unique_devices", 0)) or 0)
    onb_purch_ann = int(onb_f.get("annual_purchases_count", 0) or 0)
    onb_purch_leg = int(onb_f.get("legacy_or_code_purchases_count", 0) or 0)
    onb_purch_tot = int(onb_f.get("total_purchases_count", onb_f.get("vip_started_unique_devices", 0)) or 0)
    onb_purch_ios = int(onb_f.get("ios_purchases_count", 0) or 0)
    onb_purch_and = int(onb_f.get("android_purchases_count", 0) or 0)
    onb_purch_ios_a = int(onb_f.get("ios_ab_a_purchases_count", 0) or 0)
    onb_purch_ios_b = int(onb_f.get("ios_ab_b_purchases_count", 0) or 0)
    onb_purch_and_a = int(onb_f.get("android_ab_a_purchases_count", 0) or 0)
    onb_purch_and_b = int(onb_f.get("android_ab_b_purchases_count", 0) or 0)
    onb_step9_to_purch_pct = onb_f.get("step9_to_purchase_cvr_pct")
    onb_step0_to_purch_pct = onb_f.get("step0_to_purchase_cvr_pct")
    onb_step9_drop_cnt = int(onb_f.get("step9_to_purchase_dropoff_count", 0) or 0)
    onb_step9_drop_pct = onb_f.get("step9_to_purchase_dropoff_pct")
    onb_ann_badge_suffix = f" • 👑Yıllık: {onb_purch_ann}" if onb_purch_ann > 0 else ""
    onb_purchases_badge_str = f"💳 Satın Alma: {onb_purch_tot} (🔥A: {onb_purch_a} • 🎁B: {onb_purch_b}{onb_ann_badge_suffix})"

    onb_rows_html = ""
    for st_item in onb_steps_list:
        st_num = int(st_item.get("step_number", 0) or 0)
        st_title = html.escape(str(st_item.get("title") or f"Adım {st_num}"))
        st_sub = html.escape(str(st_item.get("subtitle") or ""))
        st_uniq = int(st_item.get("unique_devices", 0) or 0)
        st_raw = int(st_item.get("raw_events", 0) or 0)
        st_ios_u = int(st_item.get("ios_unique_devices", 0) or 0)
        st_and_u = int(st_item.get("android_unique_devices", 0) or 0)
        st_ga_u = int(st_item.get("group_a_unique_devices", 0) or 0)
        st_gb_u = int(st_item.get("group_b_unique_devices", 0) or 0)
        st_ab_split_chip = (
            f" <span style='font-size:11px; color:var(--text-muted); font-weight:700;'>(🔥A:{st_ga_u} • 🎁B:{st_gb_u})</span>"
            if (st_ga_u > 0 or st_gb_u > 0)
            else ""
        )
        st_ret = st_item.get("retention_from_prev_pct")
        st_drop_cnt = int(st_item.get("dropoff_from_prev_count", 0) or 0)
        st_drop_pct = st_item.get("dropoff_from_prev_pct")
        st_cum = st_item.get("cumulative_from_start_pct")

        if st_num == 0:
            ret_cell = (
                "<span class='badge' style='background:rgba(37,99,235,0.12); color:#2563EB;'>🏁 %100</span>"
                if st_uniq > 0
                else "<span style='color:var(--text-muted); font-size:12px;'>—</span>"
            )
            drop_cell = "<span style='color:var(--text-muted); font-size:12px;'>—</span>"
        else:
            if st_ret is not None:
                ret_color = "#059669" if st_ret >= 80.0 else ("#D97706" if st_ret >= 50.0 else "#DC2626")
                ret_cell = f"<strong style='color:{ret_color};'>%{st_ret}</strong>"
            else:
                ret_cell = "<span style='color:var(--text-muted); font-size:12px;'>—</span>"

            if st_drop_pct is not None and st_drop_cnt > 0:
                drop_cell = f"<span style='color:#DC2626; font-weight:700;'>-{st_drop_cnt} (-%{st_drop_pct})</span>"
            elif st_drop_pct is not None:
                drop_cell = "<span style='color:#059669; font-weight:700;'>0</span>"
            else:
                drop_cell = "<span style='color:var(--text-muted); font-size:12px;'>—</span>"

        bar_w = max(0.0, min(100.0, float(st_cum or 0.0)))
        cum_lbl = f"%{st_cum}" if st_cum is not None else "—"
        bar_color = "#7C3AED" if st_num == 9 else ("#059669" if bar_w >= 65.0 else ("#2563EB" if bar_w >= 35.0 else "#D97706"))

        onb_rows_html += f"""
        <tr>
          <td style="font-weight:800; color:var(--text-primary); white-space:nowrap;">{st_title}<span class="sr-only"> {st_sub}</span></td>
          <td style="font-weight:800; color:var(--text-primary); font-variant-numeric:tabular-nums; white-space:nowrap;">{st_uniq}{st_ab_split_chip}<span class="sr-only"> Cihaz ({st_raw} sinyal)</span></td>
          <td style="font-size:12px; white-space:nowrap;">🍏 <strong>{st_ios_u}</strong> • 🤖 <strong>{st_and_u}</strong></td>
          <td style="font-variant-numeric:tabular-nums;">{ret_cell}</td>
          <td style="font-variant-numeric:tabular-nums;">{drop_cell}</td>
          <td style="min-width:150px;">
            <div style="display:flex; align-items:center; gap:8px;">
              <div style="flex:1; height:8px; background:rgba(148,163,184,0.18); border-radius:999px; overflow:hidden;">
                <div style="width:{bar_w}%; height:100%; background:{bar_color}; border-radius:999px;"></div>
              </div>
              <span style="font-size:12px; font-weight:700; color:var(--text-secondary); min-width:48px; text-align:right;">{cum_lbl}</span>
            </div>
          </td>
        </tr>
        """

    p_ret_cell = (
        f"<strong style='color:#059669;'>%{onb_step9_to_purch_pct}</strong>"
        if onb_step9_to_purch_pct is not None
        else "<span style='color:var(--text-muted); font-size:12px;'>—</span>"
    )
    if onb_step9_drop_pct is not None and onb_step9_drop_cnt > 0:
        p_drop_cell = f"<span style='color:#DC2626; font-weight:700;'>-{onb_step9_drop_cnt} (-%{onb_step9_drop_pct})</span>"
    elif onb_step9_drop_pct is not None:
        p_drop_cell = "<span style='color:#059669; font-weight:700;'>0</span>"
    else:
        p_drop_cell = "<span style='color:var(--text-muted); font-size:12px;'>—</span>"

    p_bar_w = max(0.0, min(100.0, float(onb_step0_to_purch_pct or 0.0)))
    p_cum_lbl = f"%{onb_step0_to_purch_pct}" if onb_step0_to_purch_pct is not None else "—"
    p_ann_chip_html = (
        f" <span class='badge' style='background:rgba(124,58,237,0.14); color:#7C3AED; font-size:10.5px; padding:2px 6px;'>👑 Yıllık: {onb_purch_ann}</span>"
        if onb_purch_ann > 0
        else ""
    )
    p_leg_chip_html = (
        f" <span class='badge badge-meta' style='font-size:10.5px; padding:2px 6px;'>⏳/🎟️ Diğer: {onb_purch_leg}</span>"
        if onb_purch_leg > 0
        else ""
    )
    onb_rows_html += f"""
        <tr class="onb-purchase-summary-row" id="onbPurchaseSummaryRow" style="background:rgba(16,185,129,0.08); border-top:2px solid rgba(16,185,129,0.32);">
          <td style="font-weight:800; color:#059669; white-space:nowrap;">
            💳 Satın Alma / VIP Başlatma
            <span class="badge" style="background:rgba(217,119,6,0.16); color:#D97706; font-size:10.5px; padding:2px 7px; margin-left:4px;">🔥 Grup A: {onb_purch_a}</span>
            <span class="badge" style="background:rgba(16,185,129,0.16); color:#059669; font-size:10.5px; padding:2px 7px; margin-left:2px;">🎁 Grup B: {onb_purch_b}</span>{p_ann_chip_html}{p_leg_chip_html}
          </td>
          <td style="font-weight:800; color:#059669; font-variant-numeric:tabular-nums; white-space:nowrap;">
            {onb_purch_tot} <span style="font-size:11.5px; color:var(--text-secondary); font-weight:700;">(🔥A:{onb_purch_a} • 🎁B:{onb_purch_b})</span>
          </td>
          <td style="font-size:12px; white-space:nowrap;">
            🍏 <strong>{onb_purch_ios}</strong> <span style="font-size:11px; color:var(--text-muted);">(A:{onb_purch_ios_a}/B:{onb_purch_ios_b})</span> • 🤖 <strong>{onb_purch_and}</strong> <span style="font-size:11px; color:var(--text-muted);">(A:{onb_purch_and_a}/B:{onb_purch_and_b})</span>
          </td>
          <td style="font-variant-numeric:tabular-nums;">{p_ret_cell}</td>
          <td style="font-variant-numeric:tabular-nums;">{p_drop_cell}</td>
          <td style="min-width:150px;">
            <div style="display:flex; align-items:center; gap:8px;">
              <div style="flex:1; height:8px; background:rgba(148,163,184,0.18); border-radius:999px; overflow:hidden;">
                <div style="width:{p_bar_w}%; height:100%; background:#059669; border-radius:999px;"></div>
              </div>
              <span style="font-size:12px; font-weight:800; color:#059669; min-width:48px; text-align:right;">{p_cum_lbl}</span>
            </div>
          </td>
        </tr>
    """

    paid_countries_cnt = int(fl.get("paid_countries_count", 0) or 0)
    vip_countries_cnt = int(fl.get("vip_countries_count", 0) or 0)
    dl_countries_cnt = int(fl.get("download_countries_count", len(countries_list)) or 0)
    country_rev_list = fl.get("country_revenue_breakdown") or []

    country_rev_rows_html = ""
    for cr in country_rev_list:
        c_flag = html.escape(str(cr.get("flag") or "🌍"))
        c_name = html.escape(str(cr.get("name") or cr.get("code") or "TR"))
        c_code = html.escape(str(cr.get("code") or "TR"))
        c_dl = int(cr.get("downloads", 0) or 0)
        c_paid = int(cr.get("paid_subs_count", 0) or 0)
        c_trial = int(cr.get("trial_subs_count", 0) or 0)
        c_code_cnt = int(cr.get("offer_code_subs_count", 0) or 0)
        c_gross = float(cr.get("realized_gross_try", 0.0) or 0.0)
        c_net = float(cr.get("realized_net_try", 0.0) or 0.0)
        c_net_usd = float(cr.get("realized_net_usd", 0.0) or 0.0)
        c_gross_usd = float(cr.get("realized_gross_usd", 0.0) or 0.0)
        c_share = float(cr.get("share_of_revenue_pct", 0.0) or 0.0)
        c_mrr_net = float(cr.get("expected_mrr_net_try", 0.0) or 0.0)
        c_plans_lbl = html.escape(str(cr.get("paid_plans_label") or "Henüz Ücretli Alım Yok"))

        if c_paid > 0:
            paid_cell = (
                f"<span class='badge' style='background:rgba(16,185,129,0.15); color:#059669;'>💳 {c_paid}</span>"
                f"<span class='sr-only'> Ücretli Abone ({c_plans_lbl})</span>"
            )
            rev_cell = (
                f"<strong style='color:#059669;'>{c_gross:.2f} ₺</strong> / "
                f"<strong style='color:#059669;'>{c_net:.2f} ₺</strong> "
                f"<span style='font-size:11.5px; color:var(--text-muted);'>(~${c_net_usd:.2f} • %{c_share})</span>"
                f"<span class='sr-only'> Brüt / Net (~${c_gross_usd:.2f} Sales / ${c_net_usd:.2f} Proceeds)</span>"
            )
        else:
            paid_cell = "<span style='color:var(--text-muted); font-size:12px;'>0</span>"
            rev_cell = "<span style='color:var(--text-muted);'>0.00 ₺<span class='sr-only'> ($0.00)</span></span>"

        vip_pipe_parts: List[str] = []
        if c_trial > 0:
            vip_pipe_parts.append(f"⏳ {c_trial}")
        if c_code_cnt > 0:
            vip_pipe_parts.append(f"🎟️ {c_code_cnt}")
        vip_pipe_str = " + ".join(vip_pipe_parts) if vip_pipe_parts else "—"

        mrr_cell = (
            f"<strong style='color:#7C3AED;'>{c_mrr_net:.2f} ₺/Ay</strong><span class='sr-only'>{c_mrr_net:.2f} ₺ Net/Ay</span>"
            if c_mrr_net > 0
            else "<span style='color:var(--text-muted);'>0.00 ₺</span>"
        )

        country_rev_rows_html += f"""
        <tr style="{'background:rgba(16,185,129,0.06);' if c_paid > 0 else ''}">
          <td>{c_flag} <strong>{c_name}</strong> <span style="color:var(--text-muted); font-size:11.5px;">({c_code})</span></td>
          <td style="font-weight:700; color:var(--text-primary); font-variant-numeric:tabular-nums;">{c_dl}<span class="sr-only"> Kurulum</span></td>
          <td>{paid_cell}</td>
          <td style="color:var(--text-secondary); font-weight:600;">{vip_pipe_str}</td>
          <td style="font-variant-numeric:tabular-nums;">{rev_cell}</td>
          <td style="font-variant-numeric:tabular-nums;">{mrr_cell}</td>
        </tr>
        """

    country_revenue_html = f"""
          <div class="bento-card tab2-sec tab2-sec-country" id="countryRevenueCard">
            <div class="section-head">
              <div>
                <span>🌍 Ülke Gelirleri ({paid_countries_cnt}/{dl_countries_cnt})</span>
                <div class="sr-only">
                  Hangi ülkelerden kaç gerçek ücretli abonelik alındığını, paket kırılımını (Yıllık / Aylık), tahsil edilen ₺ / $ tutarını ve ülke bazlı beklenen aylık net geliri (MRR) tek tabloda gösterir.
                </div>
              </div>
              <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
                <input type="search" id="countryRevenueSearchInput" class="table-search-input" placeholder="🔍 Ülke ara (TR, DE, US...)" oninput="filterTableByQuery(this, 'countryRevenueTableBody')" />
                <span class="badge" style="background:rgba(16,185,129,0.15); color:#059669;">💳 {paid_countries_cnt} Ülke ({fl['paid_subs_count']})</span>
                <span class="badge badge-meta">🌍 {dl_countries_cnt} Ülke ({f_dl})</span>
              </div>
            </div>
            <div class="table-wrap table-scroll-bounded">
              <table>
                <thead>
                  <tr>
                    <th>Ülke</th>
                    <th>Kurulum</th>
                    <th>Ücretli</th>
                    <th>Deneme / Kod</th>
                    <th>Tahsilat (Brüt / Net)</th>
                    <th>MRR</th>
                  </tr>
                </thead>
                <tbody id="countryRevenueTableBody">
                  {country_rev_rows_html}
                </tbody>
              </table>
            </div>
          </div>
    """

    store_reconciliation_html = f"""
          <div class="bento-card tab2-sec tab2-sec-reconcile" id="storeReconciliationCard">
            <div class="section-head">
              <div>
                <span>⚖️ Mağaza Mutabakatı</span>
                <div class="sr-only">
                  Aktif Dönem: <strong>{sr_win_lbl}</strong> • Apple Connect Trends varsayılan olarak <strong>Son 7 Gün ({sr_7d_start} ➔ {sr_anchor})</strong> penceresini gösterirken, burada hem <strong>Son 7 Gün</strong> hem <strong>Tüm Zamanlar Kümülatif</strong> tahsilatı yan yana görebilirsiniz.
                </div>
              </div>
              <span class="badge" style="background:rgba(16,185,129,0.14); color:#059669;">{sr_anchor}</span>
            </div>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Dönem</th>
                    <th>🍏 App Store (Brüt / Net)</th>
                    <th>🍏 ~USD</th>
                    <th>🤖 Google Play</th>
                    <th>🌐 Toplam</th>
                  </tr>
                </thead>
                <tbody>
                  <tr style="{'background:rgba(16,185,129,0.06);' if clean_period == 'today' else ''}">
                    <td><strong>📅 Bugün</strong><span class="sr-only"> (Canlı Tahsilat) (Günlük Resmi Rapor Yarın Gelir)</span></td>
                    <td style="font-variant-numeric:tabular-nums;"><strong>{sr_today.get('ios_gross_try', 0.0):.2f} ₺</strong> / <strong style="color:#059669;">{sr_today.get('ios_net_try', 0.0):.2f} ₺</strong><span class="sr-only"> Brüt / Net</span></td>
                    <td style="font-variant-numeric:tabular-nums; color:var(--text-secondary);">${sr_today.get('ios_gross_usd', 0.0):.2f} / <strong>${sr_today.get('ios_net_usd', 0.0):.2f}</strong><span class="sr-only"> Sales / Proceeds</span></td>
                    <td style="font-variant-numeric:tabular-nums;">{sr_today.get('android_gross_try', 0.0):.2f} ₺ / {sr_today.get('android_net_try', 0.0):.2f} ₺</td>
                    <td><span class="badge badge-meta">💳 {sr_today.get('paid_count', 0)} • ⏳ +{sr_today.get('new_trials_count', 0)}</span></td>
                  </tr>
                  <tr style="{'background:rgba(16,185,129,0.06);' if clean_period == 'yesterday' else ''}">
                    <td><strong>⏮️ Dün ({sr_anchor})</strong><span class="sr-only"> / Son Kesinleşen Apple Günü (T-1: {sr_anchor})</span></td>
                    <td style="font-variant-numeric:tabular-nums;"><strong>{sr_yest.get('ios_gross_try', 0.0):.2f} ₺</strong> / <strong style="color:#059669;">{sr_yest.get('ios_net_try', 0.0):.2f} ₺</strong><span class="sr-only"> Brüt / Net</span></td>
                    <td style="font-variant-numeric:tabular-nums; color:var(--text-secondary);">${sr_yest.get('ios_gross_usd', 0.0):.2f} / <strong>${sr_yest.get('ios_net_usd', 0.0):.2f}</strong><span class="sr-only"> Sales / Proceeds</span></td>
                    <td style="font-variant-numeric:tabular-nums;">{sr_yest.get('android_gross_try', 0.0):.2f} ₺ / {sr_yest.get('android_net_try', 0.0):.2f} ₺</td>
                    <td><span class="badge badge-meta">💳 {sr_yest.get('paid_count', 0)} • ⏳ +{sr_yest.get('new_trials_count', 0)}</span></td>
                  </tr>
                  <tr style="{'background:rgba(16,185,129,0.08);' if clean_period == '7d' else ''}">
                    <td><strong>📆 Son 7G ({sr_7d_start}➔{sr_anchor})</strong><span class="sr-only"> Son 7 Gün (Connect Trends Varsayılan T-1: {sr_7d_start} ➔ {sr_anchor})</span></td>
                    <td style="font-variant-numeric:tabular-nums;"><strong>{sr_7d.get('ios_gross_try', 0.0):.2f} ₺</strong> / <strong style="color:#059669;">{sr_7d.get('ios_net_try', 0.0):.2f} ₺</strong><span class="sr-only"> Brüt / Net</span></td>
                    <td style="font-variant-numeric:tabular-nums; color:#059669; font-weight:700;">${sr_7d.get('ios_gross_usd', 0.0):.2f} / ${sr_7d.get('ios_net_usd', 0.0):.2f}<span class="sr-only"> Sales / Proceeds</span></td>
                    <td style="font-variant-numeric:tabular-nums;">{sr_7d.get('android_gross_try', 0.0):.2f} ₺ / {sr_7d.get('android_net_try', 0.0):.2f} ₺</td>
                    <td><span class="badge badge-gp">💳 {sr_7d.get('paid_count', 0)} • ⏳ +{sr_7d.get('new_trials_count', 0)}</span></td>
                  </tr>
                  <tr style="{'background:rgba(16,185,129,0.08);' if clean_period == 'all' else ''}">
                    <td><strong>♾️ Tüm Zamanlar</strong><span class="sr-only"> (Kümülatif — Tüm Doğrulanmış Mağaza Tahsilatları)</span></td>
                    <td style="font-variant-numeric:tabular-nums;"><strong>{sr_all.get('ios_gross_try', 0.0):.2f} ₺</strong> / <strong style="color:#059669;">{sr_all.get('ios_net_try', 0.0):.2f} ₺</strong><span class="sr-only"> Brüt / Net</span></td>
                    <td style="font-variant-numeric:tabular-nums; color:#059669; font-weight:700;">${sr_all.get('ios_gross_usd', 0.0):.2f} / ${sr_all.get('ios_net_usd', 0.0):.2f}<span class="sr-only"> Sales / Proceeds</span></td>
                    <td style="font-variant-numeric:tabular-nums;">{sr_all.get('android_gross_try', 0.0):.2f} ₺ / {sr_all.get('android_net_try', 0.0):.2f} ₺</td>
                    <td><span class="badge" style="background:rgba(16,185,129,0.15); color:#059669;">💳 {sr_all.get('paid_count', 0)} • ⏳ {fl['pipeline_7d_trials_count']} • 🎟️ {fl['offer_code_subs_count']}<span class="sr-only"> ({sr_cg_cnt} Plan Geçişi: +{sr_cg_net:.2f} ₺ Net)</span></span></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
    """

    ab_exp = fl.get("ab_experiment") or s.get("ab_experiment") or {}
    ab_a = ab_exp.get("group_a") or {}
    ab_b = ab_exp.get("group_b") or {}
    ab_ann = ab_exp.get("annual_anchor") or {}
    ab_code = ab_exp.get("offer_code_vip") or {}
    ab_leg = ab_exp.get("legacy_7d_trial") or {}
    ab_win_badge = html.escape(str(ab_exp.get("winner_badge") or "🧪 A/B Testi: Veri Toplanıyor"))
    ab_win_diag = html.escape(str(ab_exp.get("winner_diagnosis_tr") or "A/B Testi aktif."))
    ab_tot_act = int(ab_exp.get("total_active_vip", 0) or 0)
    ab_tot_mrr = float(ab_exp.get("total_projected_mrr_net_try", 0.0) or 0.0)
    ab_tot_cash = float(ab_exp.get("total_realized_net_try", 0.0) or 0.0)
    ab_a_act = int(ab_a.get("active_vip_count", 0) or 0)
    ab_b_act = int(ab_b.get("active_vip_count", 0) or 0)
    ab_ann_act = int(ab_ann.get("active_vip_count", 0) or 0)

    ab_experiment_html = f"""
          <div class="bento-card tab2-sec tab2-sec-ab" id="abExperimentCommandCard" style="margin-bottom:14px; border-left:4px solid #7C3AED;">
            <div class="section-head">
              <div>
                <span>🧪 RevenueCat Paywall A/B Testi (%50/%50)<span class="sr-only"> Komuta Merkezi (%50 / %50 Trafik • Grup A: İlk Ay %67 İndirim vs Grup B: İlk Ay Ücretsiz)</span></span>
                <div class="sr-only" id="abExperimentDiagnosisSr">{ab_win_diag}</div>
              </div>
              <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
                <span class="badge" id="abWinnerBadge" style="background:rgba(124,58,237,0.16); color:#7C3AED;">{ab_win_badge}</span>
                <span class="badge" style="background:rgba(217,119,6,0.15); color:#D97706;" id="abTopSplitBadge">🔥 Grup A: {ab_a_act} • 🎁 Grup B: {ab_b_act} • 👑 Yıllık: {ab_ann_act}</span>
                <button type="button" class="collapse-btn" id="btnToggleAbTable" onclick="toggleDetailWrap('abExperimentTableWrap', 'btnToggleAbTable')">📊 Detay Tablosu ▼</button>
              </div>
            </div>

            <div class="card-desc" id="abWinnerDiagnosis" style="margin-bottom:12px; padding:10px 12px; border-radius:10px; background:var(--bg-cell); border:1px solid var(--border-subtle); font-size:12px; color:var(--text-secondary);">
              <strong>🎯 Otonom A/B Karar Motoru:</strong> <span id="abWinnerDiagnosisText">{ab_win_diag}</span>
            </div>

            <div class="donuts-grid" style="margin-bottom:12px;">
              <!-- GRUP A: İLK AY %67 İNDİRİM (₺49,99 ➔ ₺149,99/ay) -->
              <div class="step-box" id="abCardGroupA" style="border-left:4px solid #D97706;">
                <div style="display:flex; justify-content:space-between; align-items:center; gap:6px; margin-bottom:4px;">
                  <div class="step-num" style="color:#D97706; margin-bottom:0;">🔥 GRUP A • İLK AY %67 İNDİRİM</div>
                  <span class="badge" style="background:rgba(217,119,6,0.15); color:#D97706; font-size:10.5px;">paid_intro (%50)</span>
                </div>
                <div class="step-val" style="color:#D97706;" id="abGroupAActiveVal">{ab_a_act} Aktif VIP <span style="font-size:13px; color:var(--text-muted);">({int(ab_a.get('started_vip_count', 0) or 0)} Başlayan)</span></div>
                <div class="kpi-micro-meta" style="margin:6px 0;" id="abGroupAMeta">
                  <span class="kpi-micro-chip">💵 Anında Nakit: {float(ab_a.get('realized_net_try', 0.0) or 0.0):.2f} ₺ Net</span>
                  <span class="kpi-micro-chip">🚀 MRR: {float(ab_a.get('projected_mrr_net_try', 0.0) or 0.0):.2f} ₺/Ay</span>
                  <span class="kpi-micro-chip">🛡️ Tutundurma: %{float(ab_a.get('retention_rate_pct', 0.0) or 0.0)}</span>
                </div>
                <div class="step-sub" style="font-size:11.5px;">
                  <strong>₺49,99 İlk Ay ➔ ₺149,99/ay</strong> • Paywall: <strong id="abGroupAFunnelTxt">{int(ab_a.get('paywall_views', 0) or 0)} Gösterim ➔ {int(ab_a.get('cta_clicks', 0) or 0)} Tık (%{float(ab_a.get('cta_of_view_pct', 0.0) or 0.0)}) ➔ {int(ab_a.get('purchase_cancelled', 0) or 0)} İptal</strong> •🍏 {int(ab_a.get('ios_active_count', 0) or 0)} iOS / 🤖 {int(ab_a.get('android_active_count', 0) or 0)} Android.
                </div>
              </div>

              <!-- GRUP B: İLK AY ÜCRETSİZ (30 GÜN ₺0 ➔ ₺149,99/ay) -->
              <div class="step-box" id="abCardGroupB" style="border-left:4px solid #059669;">
                <div style="display:flex; justify-content:space-between; align-items:center; gap:6px; margin-bottom:4px;">
                  <div class="step-num" style="color:#059669; margin-bottom:0;">🎁 GRUP B • İLK AY ÜCRETSİZ (30G)</div>
                  <span class="badge" style="background:rgba(16,185,129,0.15); color:#059669; font-size:10.5px;">free_trial (%50)</span>
                </div>
                <div class="step-val" style="color:#059669;" id="abGroupBActiveVal">{ab_b_act} Aktif VIP <span style="font-size:13px; color:var(--text-muted);">({int(ab_b.get('started_vip_count', 0) or 0)} Başlayan)</span></div>
                <div class="kpi-micro-meta" style="margin:6px 0;" id="abGroupBMeta">
                  <span class="kpi-micro-chip">⏳ 30G Havuz: +{float(ab_b.get('pipeline_trial_mrr_net_try', 0.0) or 0.0):.2f} ₺</span>
                  <span class="kpi-micro-chip">🚀 MRR: {float(ab_b.get('projected_mrr_net_try', 0.0) or 0.0):.2f} ₺/Ay</span>
                  <span class="kpi-micro-chip">🛡️ Tutundurma: %{float(ab_b.get('retention_rate_pct', 0.0) or 0.0)}</span>
                </div>
                <div class="step-sub" style="font-size:11.5px;">
                  <strong>30 Gün ₺0 ➔ ₺149,99/ay</strong> • Paywall: <strong id="abGroupBFunnelTxt">{int(ab_b.get('paywall_views', 0) or 0)} Gösterim ➔ {int(ab_b.get('cta_clicks', 0) or 0)} Tık (%{float(ab_b.get('cta_of_view_pct', 0.0) or 0.0)}) ➔ {int(ab_b.get('purchase_cancelled', 0) or 0)} İptal</strong> • 🍏 {int(ab_b.get('ios_active_count', 0) or 0)} iOS / 🤖 {int(ab_b.get('android_active_count', 0) or 0)} Android.
                </div>
              </div>

              <!-- YILLIK VIP ÇIPA (₺599,99/YIL • %67 TASARRUF) -->
              <div class="step-box" id="abCardAnnual" style="border-left:4px solid #7C3AED;">
                <div style="display:flex; justify-content:space-between; align-items:center; gap:6px; margin-bottom:4px;">
                  <div class="step-num" style="color:#7C3AED; margin-bottom:0;">👑 YILLIK VIP ÇIPA (%67 TASARRUF)</div>
                  <span class="badge" style="background:rgba(124,58,237,0.15); color:#7C3AED; font-size:10.5px;">Her İki Grupta Ortak</span>
                </div>
                <div class="step-val" style="color:#7C3AED;" id="abAnnualActiveVal">{ab_ann_act} Yıllık VIP <span style="font-size:13px; color:var(--text-muted);">({int(ab_ann.get('started_vip_count', 0) or 0)} Başlayan)</span></div>
                <div class="kpi-micro-meta" style="margin:6px 0;" id="abAnnualMeta">
                  <span class="kpi-micro-chip">💵 Tahsilat: {float(ab_ann.get('realized_net_try', 0.0) or 0.0):.2f} ₺ Net</span>
                  <span class="kpi-micro-chip">🚀 MRR: {float(ab_ann.get('projected_mrr_net_try', 0.0) or 0.0):.2f} ₺/Ay</span>
                  <span class="kpi-micro-chip">🎟️ Kodlu: {int(ab_code.get('active_vip_count', 0) or 0)} • ⏳ 7G: {int(ab_leg.get('active_vip_count', 0) or 0)}</span>
                </div>
                <div class="step-sub" style="font-size:11.5px;">
                  <strong>₺599,99/Yıl (~₺49,99/ay)</strong> • Peşin yıllık nakit akışı ve sıfır aylık churn çıpası • 🍏 {int(ab_ann.get('ios_active_count', 0) or 0)} iOS / 🤖 {int(ab_ann.get('android_active_count', 0) or 0)} Android.
                </div>
              </div>
            </div>

            <div class="table-wrap" id="abExperimentTableWrap" style="display:none;">
              <table>
                <thead>
                  <tr>
                    <th>A/B Varyantı &amp; Paket</th>
                    <th>Paywall Gösterim ➔ Tık</th>
                    <th>Ödeme İptali</th>
                    <th>Başlayan VIP</th>
                    <th>Aktif / İptal (Churn)</th>
                    <th>🍏 / 🤖</th>
                    <th>Gün-0 Tahsilat (Net ₺)</th>
                    <th>Deneme Havuzu (30G/7G)</th>
                    <th>Beklenen Net MRR</th>
                  </tr>
                </thead>
                <tbody id="abExperimentTbody">
                  <tr style="background:rgba(217,119,6,0.06);">
                    <td><strong>🔥 Grup A: İlk Ay %67 İndirim</strong> <span style="font-size:11px; color:var(--text-muted);">(₺49,99 ➔ ₺149,99/ay)</span></td>
                    <td style="font-variant-numeric:tabular-nums;"><strong>{int(ab_a.get('paywall_views', 0) or 0)}</strong> ➔ <strong>{int(ab_a.get('cta_clicks', 0) or 0)}</strong> (%{float(ab_a.get('cta_of_view_pct', 0.0) or 0.0)})</td>
                    <td style="font-variant-numeric:tabular-nums;">{int(ab_a.get('purchase_cancelled', 0) or 0)} (%{float(ab_a.get('cancel_of_cta_pct', 0.0) or 0.0)})</td>
                    <td style="font-weight:800; color:#D97706;">{int(ab_a.get('started_vip_count', 0) or 0)}</td>
                    <td style="font-variant-numeric:tabular-nums;"><strong style="color:#059669;">{ab_a_act} Aktif</strong> • {int(ab_a.get('cancelled_vip_count', 0) or 0)} İptal (%{float(ab_a.get('churn_rate_pct', 0.0) or 0.0)})</td>
                    <td>🍏 {int(ab_a.get('ios_active_count', 0) or 0)} • 🤖 {int(ab_a.get('android_active_count', 0) or 0)}</td>
                    <td style="font-weight:800; color:#059669; font-variant-numeric:tabular-nums;">{float(ab_a.get('realized_net_try', 0.0) or 0.0):.2f} ₺ <span style="font-size:11px; color:var(--text-muted);">(${float(ab_a.get('realized_net_usd', 0.0) or 0.0):.2f})</span></td>
                    <td style="color:var(--text-muted);">0.00 ₺ (Anında Ücretli)</td>
                    <td style="font-weight:800; color:#7C3AED; font-variant-numeric:tabular-nums;">{float(ab_a.get('projected_mrr_net_try', 0.0) or 0.0):.2f} ₺/Ay (%{float(ab_a.get('mrr_share_pct', 0.0) or 0.0)})</td>
                  </tr>
                  <tr style="background:rgba(16,185,129,0.06);">
                    <td><strong>🎁 Grup B: İlk Ay Ücretsiz (30G)</strong> <span style="font-size:11px; color:var(--text-muted);">(30G ₺0 ➔ ₺149,99/ay)</span></td>
                    <td style="font-variant-numeric:tabular-nums;"><strong>{int(ab_b.get('paywall_views', 0) or 0)}</strong> ➔ <strong>{int(ab_b.get('cta_clicks', 0) or 0)}</strong> (%{float(ab_b.get('cta_of_view_pct', 0.0) or 0.0)})</td>
                    <td style="font-variant-numeric:tabular-nums;">{int(ab_b.get('purchase_cancelled', 0) or 0)} (%{float(ab_b.get('cancel_of_cta_pct', 0.0) or 0.0)})</td>
                    <td style="font-weight:800; color:#059669;">{int(ab_b.get('started_vip_count', 0) or 0)}</td>
                    <td style="font-variant-numeric:tabular-nums;"><strong style="color:#059669;">{ab_b_act} Aktif</strong> • {int(ab_b.get('cancelled_vip_count', 0) or 0)} İptal (%{float(ab_b.get('churn_rate_pct', 0.0) or 0.0)})</td>
                    <td>🍏 {int(ab_b.get('ios_active_count', 0) or 0)} • 🤖 {int(ab_b.get('android_active_count', 0) or 0)}</td>
                    <td style="font-weight:700; color:#059669; font-variant-numeric:tabular-nums;">{float(ab_b.get('realized_net_try', 0.0) or 0.0):.2f} ₺</td>
                    <td style="font-weight:700; color:#D97706; font-variant-numeric:tabular-nums;">+{float(ab_b.get('pipeline_trial_mrr_net_try', 0.0) or 0.0):.2f} ₺ ({int(ab_b.get('trial_active_count', 0) or 0)} Deneme)</td>
                    <td style="font-weight:800; color:#7C3AED; font-variant-numeric:tabular-nums;">{float(ab_b.get('projected_mrr_net_try', 0.0) or 0.0):.2f} ₺/Ay (%{float(ab_b.get('mrr_share_pct', 0.0) or 0.0)})</td>
                  </tr>
                  <tr>
                    <td><strong>👑 Yıllık VIP Çıpa</strong> <span style="font-size:11px; color:var(--text-muted);">(₺599,99/Yıl • %67 Tasarruf)</span></td>
                    <td style="color:var(--text-muted); font-size:12px;">Ortak Üst Kart</td>
                    <td style="color:var(--text-muted); font-size:12px;">—</td>
                    <td style="font-weight:800; color:#7C3AED;">{int(ab_ann.get('started_vip_count', 0) or 0)}</td>
                    <td style="font-variant-numeric:tabular-nums;"><strong style="color:#059669;">{ab_ann_act} Aktif</strong> • {int(ab_ann.get('cancelled_vip_count', 0) or 0)} İptal (%{float(ab_ann.get('churn_rate_pct', 0.0) or 0.0)})</td>
                    <td>🍏 {int(ab_ann.get('ios_active_count', 0) or 0)} • 🤖 {int(ab_ann.get('android_active_count', 0) or 0)}</td>
                    <td style="font-weight:800; color:#059669; font-variant-numeric:tabular-nums;">{float(ab_ann.get('realized_net_try', 0.0) or 0.0):.2f} ₺ <span style="font-size:11px; color:var(--text-muted);">(${float(ab_ann.get('realized_net_usd', 0.0) or 0.0):.2f})</span></td>
                    <td style="color:var(--text-muted);">0.00 ₺ (Peşin Yıllık)</td>
                    <td style="font-weight:800; color:#7C3AED; font-variant-numeric:tabular-nums;">{float(ab_ann.get('projected_mrr_net_try', 0.0) or 0.0):.2f} ₺/Ay (%{float(ab_ann.get('mrr_share_pct', 0.0) or 0.0)})</td>
                  </tr>
                  <tr>
                    <td><strong>⏳ Tarihsel 7G Deneme &amp; 🎟️ Kodlu VIP</strong> <span style="font-size:11px; color:var(--text-muted);">(Önceki Kohort Referansı)</span></td>
                    <td style="color:var(--text-muted); font-size:12px;">Tarihsel Kohort</td>
                    <td style="color:var(--text-muted); font-size:12px;">—</td>
                    <td style="font-weight:700;">{int(ab_leg.get('started_vip_count', 0) or 0) + int(ab_code.get('started_vip_count', 0) or 0)}</td>
                    <td style="font-variant-numeric:tabular-nums;"><strong>{int(ab_leg.get('active_vip_count', 0) or 0) + int(ab_code.get('active_vip_count', 0) or 0)} Aktif</strong> (⏳ {int(ab_leg.get('active_vip_count', 0) or 0)} • 🎟️ {int(ab_code.get('active_vip_count', 0) or 0)}) • {int(ab_leg.get('cancelled_vip_count', 0) or 0) + int(ab_code.get('cancelled_vip_count', 0) or 0)} İptal</td>
                    <td>🍏 {int(ab_leg.get('ios_active_count', 0) or 0) + int(ab_code.get('ios_active_count', 0) or 0)} • 🤖 {int(ab_leg.get('android_active_count', 0) or 0) + int(ab_code.get('android_active_count', 0) or 0)}</td>
                    <td style="font-variant-numeric:tabular-nums;">{float(ab_leg.get('realized_net_try', 0.0) or 0.0):.2f} ₺</td>
                    <td style="font-weight:700; color:#D97706; font-variant-numeric:tabular-nums;">+{float(ab_leg.get('pipeline_trial_mrr_net_try', 0.0) or 0.0):.2f} ₺ ({int(ab_leg.get('trial_active_count', 0) or 0)} 7G)</td>
                    <td style="font-weight:700; color:#7C3AED; font-variant-numeric:tabular-nums;">{float(ab_leg.get('projected_mrr_net_try', 0.0) or 0.0) + float(ab_code.get('projected_mrr_net_try', 0.0) or 0.0):.2f} ₺/Ay</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
    """

    dashboard_response = HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="tr">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
      <meta name="referrer" content="no-referrer">
      <title>Mışıl Baby — Kurumsal Büyüme, Abone Defteri & Ürün Analitiği Kokpiti</title>
      <link rel="icon" type="image/x-icon" href="/favicon.ico">
      <link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png">
      <link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png">
      <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
      <link rel="manifest" href="/manifest.json">
      <meta name="theme-color" content="#13101C">
      <meta name="apple-mobile-web-app-capable" content="yes">
      <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
      <meta name="apple-mobile-web-app-title" content="Mışıl Kokpit">
      <link rel="preconnect" href="https://fonts.googleapis.com">
      <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
      <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Sora:wght@600;700;800&family=JetBrains+Mono:wght@500;600;700;800&display=swap" rel="stylesheet" media="print" onload="this.media='all'">
      <noscript><link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Sora:wght@600;700;800&family=JetBrains+Mono:wght@500;600;700;800&display=swap" rel="stylesheet"></noscript>
      <style>
        /* MIŞIL BABY KURUMSAL MARKA TEMASI: ☀️ GÜNDÜZ (SICAK YULAF & KAŞMİR BEJİ — VARSAYILAN) */
        :root {{
          --bg-canvas: #EDE5DA;
          --bg-card: rgba(247, 242, 235, 0.94);
          --bg-cell: #EFE7DC;
          --border-subtle: rgba(150, 122, 98, 0.24);
          --ring-track: rgba(150, 122, 98, 0.22);
          --text-primary: #2C201A;
          --text-secondary: #4A382E;
          --text-muted: #655347;
          --brand-indigo: #C86446;
          --card-shadow: 0 10px 26px -6px rgba(100, 76, 56, 0.12), 0 2px 8px -2px rgba(100, 76, 56, 0.06);
          --stage-1: #C86446;
          --stage-2: #3B6E8C;
          --stage-3: #24523A;
          --stage-4: #5B21B6;
          --stage-5: #C93B4B;
          --stage-6: #2D6A4F;
          --stage-1-rgb: 200, 100, 70;
          --stage-2-rgb: 59, 110, 140;
          --stage-3-rgb: 36, 82, 58;
          --stage-4-rgb: 91, 33, 182;
          --stage-5-rgb: 201, 59, 75;
          --stage-6-rgb: 45, 106, 79;
          --soft-peach-card: linear-gradient(145deg, rgba(242, 226, 216, 0.96) 0%, rgba(234, 212, 198, 0.90) 100%);
          --soft-sky-card: linear-gradient(145deg, rgba(220, 234, 244, 0.96) 0%, rgba(204, 223, 238, 0.90) 100%);
          --soft-sage-card: linear-gradient(145deg, rgba(220, 234, 224, 0.96) 0%, rgba(202, 222, 209, 0.90) 100%);
          --soft-lavender-card: linear-gradient(145deg, rgba(230, 222, 242, 0.96) 0%, rgba(215, 204, 234, 0.90) 100%);
          --soft-blush-card: linear-gradient(145deg, rgba(242, 220, 225, 0.96) 0%, rgba(234, 204, 211, 0.90) 100%);
          --soft-emerald-card: linear-gradient(145deg, rgba(214, 236, 223, 0.98) 0%, rgba(192, 224, 206, 0.92) 100%);
          --gold: #C86446;
          --sky: #3B6E8C;
          --emerald: #24523A;
          --violet: #5B21B6;
          --rose: #C93B4B;
          --teal: #2D6A4F;
        }}
        /* 🌙 MIŞIL BABY GECE MODU: SICAK KAŞMİR VE MUM IŞIĞI (MELATONİN WARM DARK MODE) */
        body.theme-slate {{
          --bg-canvas: #13101C;
          --bg-card: rgba(33, 28, 44, 0.90);
          --bg-cell: #1A1524;
          --border-subtle: rgba(245, 230, 215, 0.13);
          --ring-track: rgba(245, 230, 215, 0.10);
          --text-primary: #FAF5EE;
          --text-secondary: #D9D0E3;
          --text-muted: #8F86A2;
          --brand-indigo: #F4A261;
          --card-shadow: 0 14px 34px -6px rgba(0, 0, 0, 0.48);
          --stage-1: #F4A261;
          --stage-2: #7EB6D9;
          --stage-3: #74C69D;
          --stage-4: #A569BD;
          --stage-5: #FF6B6B;
          --stage-6: #52B788;
          --stage-1-rgb: 244, 162, 97;
          --stage-2-rgb: 126, 182, 217;
          --stage-3-rgb: 116, 198, 157;
          --stage-4-rgb: 165, 105, 189;
          --stage-5-rgb: 255, 107, 107;
          --stage-6-rgb: 82, 183, 136;
          --soft-peach-card: linear-gradient(145deg, rgba(62, 38, 32, 0.92) 0%, rgba(42, 26, 22, 0.88) 100%);
          --soft-sky-card: linear-gradient(145deg, rgba(28, 44, 58, 0.92) 0%, rgba(20, 32, 44, 0.88) 100%);
          --soft-sage-card: linear-gradient(145deg, rgba(32, 52, 42, 0.92) 0%, rgba(22, 36, 29, 0.88) 100%);
          --soft-lavender-card: linear-gradient(145deg, rgba(46, 36, 66, 0.92) 0%, rgba(33, 26, 48, 0.88) 100%);
          --soft-blush-card: linear-gradient(145deg, rgba(56, 32, 40, 0.92) 0%, rgba(40, 22, 28, 0.88) 100%);
          --soft-emerald-card: linear-gradient(145deg, rgba(28, 56, 45, 0.94) 0%, rgba(20, 40, 32, 0.90) 100%);
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
          background: radial-gradient(circle at 12% 8%, rgba(226, 198, 176, 0.55) 0%, transparent 45%),
                      radial-gradient(circle at 88% 18%, rgba(194, 216, 202, 0.45) 0%, transparent 42%),
                      radial-gradient(circle at 50% 55%, rgba(214, 202, 228, 0.40) 0%, transparent 50%),
                      var(--bg-canvas);
          color: var(--text-primary);
          font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
          min-height: 100vh;
          padding: 20px 18px 80px;
          -webkit-font-smoothing: antialiased;
          transition: background 0.2s ease, color 0.2s ease;
        }}
        body.theme-slate {{
          background: radial-gradient(circle at 18% 10%, rgba(244, 162, 97, 0.15) 0%, transparent 45%),
                      radial-gradient(circle at 82% 22%, rgba(116, 198, 157, 0.12) 0%, transparent 42%),
                      radial-gradient(circle at 50% 60%, rgba(165, 105, 189, 0.10) 0%, transparent 50%),
                      var(--bg-canvas);
        }}
        .container {{
          max-width: 1320px;
          margin: 0 auto;
        }}
        .cat-header {{
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
          padding: 10px 14px;
          margin: 6px 0 12px;
          border-radius: 12px;
          background: var(--bg-cell);
          border: 1px solid var(--border-subtle);
          border-left: 4px solid var(--brand-indigo);
          font-size: 13px;
          font-weight: 800;
          color: var(--text-primary);
          letter-spacing: -0.01em;
        }}
        .cat-header span.cat-sub {{
          font-size: 11.5px;
          font-weight: 600;
          color: var(--text-muted);
        }}
        .subcat-bar {{
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 8px;
          padding: 10px 12px;
          margin-bottom: 14px;
          border-radius: 14px;
          background: var(--bg-card);
          border: 1px solid var(--border-subtle);
          box-shadow: var(--card-shadow);
        }}
        .subcat-label {{
          font-size: 11.5px;
          font-weight: 800;
          color: var(--text-muted);
          text-transform: uppercase;
          letter-spacing: 0.04em;
          margin-right: 4px;
        }}
        .subcat-pill {{
          border: 1px solid var(--border-subtle);
          background: var(--bg-cell);
          color: var(--text-secondary);
          padding: 7px 13px;
          border-radius: 999px;
          font-size: 12px;
          font-weight: 700;
          cursor: pointer;
          transition: all 0.15s ease;
          font-family: inherit;
        }}
        .subcat-pill:hover {{
          border-color: var(--brand-indigo);
          color: var(--text-primary);
        }}
        .subcat-pill.active {{
          background: var(--brand-indigo);
          color: #FAF5EE;
          border-color: var(--brand-indigo);
          box-shadow: 0 4px 12px rgba(200, 100, 70, 0.25);
        }}
        .collapse-btn {{
          border: 1px solid var(--border-subtle);
          background: var(--bg-cell);
          color: var(--brand-indigo);
          padding: 5px 11px;
          border-radius: 8px;
          font-size: 11.5px;
          font-weight: 800;
          cursor: pointer;
          font-family: inherit;
          transition: all 0.15s ease;
        }}
        .collapse-btn:hover {{
          background: rgba(200, 100, 70, 0.12);
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
          background: var(--bg-card);
          color: var(--text-primary);
          border: 1px solid rgba(var(--stage-1-rgb), 0.42);
          font-size: 12.5px;
          font-weight: 800;
          cursor: pointer;
          box-shadow: var(--card-shadow);
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
          background: linear-gradient(135deg, #F4A261 0%, #C86446 100%);
          color: #13101C;
          display: flex; align-items: center; justify-content: center;
          font-size: 19px;
          box-shadow: 0 4px 12px rgba(244, 162, 97, 0.30);
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
        .btn:hover {{ background: var(--bg-card); border-color: var(--brand-indigo); color: var(--text-primary); }}
        .btn-pres {{
          background: linear-gradient(135deg, rgba(165, 105, 189, 0.12), rgba(200, 100, 70, 0.12));
          border-color: rgba(165, 105, 189, 0.32);
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
          background: rgba(116, 198, 157, 0.14);
          border: 1px solid rgba(116, 198, 157, 0.38);
          color: #74C69D;
          font-size: 11.5px;
          font-weight: 800;
          cursor: pointer;
          font-variant-numeric: tabular-nums;
        }}
        .pulse-dot {{
          width: 7px; height: 7px; border-radius: 50%;
          background: #74C69D;
          box-shadow: 0 0 8px #74C69D;
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
        .fs-dot {{ width: 6px; height: 6px; border-radius: 50%; background: var(--stage-3); }}
        .fs-reconciling .fs-dot {{ background: var(--stage-2); }}
        .fs-synced .fs-dot {{ background: var(--stage-1); }}
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
        .period-pill:hover {{ color: var(--text-primary); border-color: rgba(200, 100, 70, 0.45); }}
        .period-pill.active {{
          color: #FAF5EE;
          background: linear-gradient(135deg, #C86446 0%, #A84E32 100%);
          border-color: #C86446;
          box-shadow: 0 3px 10px rgba(200, 100, 70, 0.25);
        }}
        body.theme-slate .period-pill.active {{
          background: linear-gradient(135deg, #F4A261 0%, #C86446 100%);
          border-color: #F4A261;
          color: #13101C;
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
          background: rgba(59, 110, 140, 0.10);
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
          border: 1px solid rgba(165, 105, 189, 0.30);
          background: rgba(165, 105, 189, 0.10);
          color: var(--stage-4);
        }}
        .conv-summary-pill strong {{
          font-family: 'JetBrains Mono', monospace;
          font-size: 12px;
          font-weight: 800;
        }}
        .conv-bridge-grid {{
          display: grid;
          grid-template-columns: 1fr auto 1fr auto 1fr;
          align-items: stretch;
          gap: 8px;
        }}
        .conv-tier-bridge {{
          display: flex;
          align-items: center;
          justify-content: space-between;
          flex-wrap: wrap;
          gap: 10px;
          margin: 10px 0;
          padding: 8px 14px;
          border-radius: 12px;
          background: var(--bg-cell);
          border: 1px dashed var(--border-subtle);
          font-size: 11.5px;
          font-weight: 700;
          color: var(--text-secondary);
        }}
        .conv-tier-lbl {{
          display: inline-flex;
          align-items: center;
          gap: 6px;
          font-size: 11px;
          font-weight: 800;
          text-transform: uppercase;
          letter-spacing: 0.4px;
          color: var(--text-muted);
        }}
        .spark-svg {{
          max-width: 84px;
          height: auto;
          flex-shrink: 1;
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
          background: rgba(61, 110, 87, 0.14);
          color: var(--stage-3);
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
          background: linear-gradient(135deg, #C86446 0%, #A84E32 100%);
          color: #FAF5EE;
          box-shadow: 0 4px 12px rgba(200, 100, 70, 0.22);
        }}
        body.theme-slate .tab-btn.active {{
          background: linear-gradient(135deg, #F4A261 0%, #C86446 100%);
          color: #13101C;
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
          background: linear-gradient(135deg, #C86446 0%, #A84E32 100%);
          color: #FAF5EE;
          border-color: #C86446;
        }}
        body.theme-slate .chart-toggle button.active {{
          background: linear-gradient(135deg, #F4A261 0%, #C86446 100%);
          color: #13101C;
          border-color: #F4A261;
        }}
        .timeline-scroll {{
          width: 100%;
          max-width: 100%;
          overflow-x: auto;
          overflow-y: hidden;
          padding-bottom: 8px;
          -webkit-overflow-scrolling: touch;
          scrollbar-width: thin;
          scrollbar-color: var(--text-muted) var(--bg-cell);
        }}
        .timeline-scroll::-webkit-scrollbar {{
          height: 7px;
        }}
        .timeline-scroll::-webkit-scrollbar-track {{
          background: var(--bg-cell);
          border-radius: 99px;
        }}
        .timeline-scroll::-webkit-scrollbar-thumb {{
          background: var(--text-muted);
          border-radius: 99px;
        }}
        .timeline-scroll::-webkit-scrollbar-thumb:hover {{
          background: var(--brand-indigo);
        }}
        .timeline-grid {{
          display: grid;
          grid-template-columns: repeat({max(1, len(t_days))}, minmax(36px, 1fr));
          min-width: max-content;
          width: 100%;
          gap: 4px;
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
          padding: 2px 1px;
          border-radius: 8px;
        }}
        .t-today {{
          background: rgba(116, 198, 157, 0.12);
          border: 1px dashed rgba(61, 110, 87, 0.48);
        }}
        .t-pending {{
          background: rgba(244, 162, 97, 0.10);
        }}
        .t-top-val {{
          font-size: 10.5px;
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
          width: 72%;
          max-width: 26px;
          border-radius: 6px 6px 2px 2px;
          transition: height 0.25s ease;
        }}
        .t-lbl {{
          font-size: 10px;
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
        .review-dev-reply {{
          margin-top: 10px;
          padding: 10px 12px;
          border-radius: 10px;
          background: var(--bg-card);
          border-left: 3px solid var(--brand-indigo);
          border-top: 1px solid var(--border-subtle);
          border-right: 1px solid var(--border-subtle);
          border-bottom: 1px solid var(--border-subtle);
        }}
        .review-dev-reply-text {{
          font-size: 12px;
          color: var(--text-secondary);
          line-height: 1.48;
          white-space: pre-wrap;
        }}

        .badge {{
          display: inline-flex;
          align-items: center;
          padding: 4px 10px;
          border-radius: 99px;
          font-size: 11px;
          font-weight: 800;
          white-space: nowrap;
        }}
        .badge-meta {{ background: rgba(200, 100, 70, 0.14); color: var(--stage-1); }}
        .badge-gp {{ background: rgba(61, 110, 87, 0.16); color: var(--stage-3); }}
        .toast-banner {{
          background: rgba(61, 110, 87, 0.14);
          border: 1px solid rgba(116, 198, 157, 0.38);
          color: var(--stage-3);
          padding: 13px 18px;
          border-radius: 14px;
          margin-bottom: 16px;
          font-size: 13px;
          font-weight: 600;
        }}
        .table-wrap {{ overflow-x: auto; margin-top: 10px; border: 1px solid var(--border-subtle); border-radius: 12px; }}
        .table-scroll-bounded {{ max-height: 360px; overflow-y: auto; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 12.5px; background: var(--bg-card); }}
        th {{ position: sticky; top: 0; z-index: 3; text-align: left; padding: 10px 12px; background: var(--bg-cell); color: var(--text-muted); font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid var(--border-subtle); font-weight: 800; white-space: nowrap; }}
        td {{ padding: 9px 12px; border-bottom: 1px solid var(--border-subtle); color: var(--text-primary); font-variant-numeric: tabular-nums; }}
        tr:hover td {{ background: var(--bg-cell); }}
        .table-search-input {{
          padding: 6px 12px;
          border-radius: 8px;
          border: 1px solid var(--border-subtle);
          background: var(--bg-cell);
          color: var(--text-primary);
          font-size: 12px;
          font-weight: 600;
          min-width: 210px;
          outline: none;
          transition: border-color 0.15s ease, box-shadow 0.15s ease;
        }}
        .table-search-input:focus {{
          border-color: var(--brand-indigo);
          box-shadow: 0 0 0 3px rgba(200, 100, 70, 0.16);
        }}

        /* GERÇEK FULL-VIEWPORT SAAS APP SHELL (SOL SABİT KOYU RAY + SAĞ GENİŞ ÇALIŞMA ALANI) */
        body {{
          padding: 0 !important;
          margin: 0 !important;
          overflow-x: hidden;
        }}
        .container {{
          max-width: none !important;
          width: 100% !important;
          margin: 0 !important;
          padding: 0 !important;
        }}
        .cockpit-shell {{
          display: block;
          min-height: 100vh;
          width: 100%;
        }}
        .cockpit-sidebar {{
          position: fixed;
          left: 0;
          top: 0;
          bottom: 0;
          width: 264px;
          height: 100vh;
          z-index: 120;
          background: radial-gradient(circle at 18% 10%, rgba(244, 162, 97, 0.16) 0%, transparent 48%),
                      radial-gradient(circle at 82% 85%, rgba(116, 198, 157, 0.12) 0%, transparent 45%),
                      linear-gradient(180deg, #13101C 0%, #1D1829 100%);
          color: #FAF5EE;
          border-right: 1px solid rgba(245, 230, 215, 0.14);
          padding: 18px 14px;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          gap: 14px;
          overflow-y: auto;
          box-shadow: 8px 0 32px rgba(10, 8, 16, 0.32);
        }}
        .sidebar-brand-box {{
          display: flex;
          align-items: center;
          gap: 11px;
          padding: 6px 8px 14px;
          border-bottom: 1px solid rgba(245, 230, 215, 0.12);
        }}
        .sidebar-brand-icon {{
          width: 40px;
          height: 40px;
          border-radius: 12px;
          background: linear-gradient(135deg, #F4A261 0%, #C86446 100%);
          color: #13101C;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 19px;
          flex-shrink: 0;
          overflow: hidden;
          border: 1.5px solid rgba(244, 162, 97, 0.55);
          box-shadow: 0 4px 14px rgba(244, 162, 97, 0.35);
        }}
        .sidebar-brand-logo-img {{
          width: 100%;
          height: 100%;
          object-fit: cover;
          display: block;
        }}
        .mobile-brand-mrr-pill {{
          display: none;
          align-items: center;
          gap: 5px;
          padding: 4px 9px;
          border-radius: 99px;
          background: rgba(244, 162, 97, 0.16);
          border: 1px solid rgba(244, 162, 97, 0.38);
          color: #F4A261;
          font-size: 11px;
          font-weight: 800;
          font-variant-numeric: tabular-nums;
          white-space: nowrap;
        }}
        .mobile-header-quick-actions {{
          display: none;
          align-items: center;
          gap: 6px;
        }}
        .mobile-icon-btn {{
          width: 32px;
          height: 32px;
          border-radius: 9px;
          border: 1px solid rgba(245, 230, 215, 0.18);
          background: rgba(44, 38, 58, 0.78);
          color: #FAF5EE;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          font-size: 14px;
          cursor: pointer;
          text-decoration: none;
          padding: 0;
        }}
        .cockpit-mobile-bottom-dock {{
          display: none;
        }}
        .sidebar-brand-box h1 {{
          font-family: 'Sora', sans-serif;
          font-size: 14.5px;
          font-weight: 800;
          color: #FAF5EE;
          line-height: 1.2;
          letter-spacing: -0.02em;
        }}
        .sidebar-brand-box p {{
          font-size: 10.5px;
          color: #FFD4C4;
          margin-top: 2px;
          font-weight: 600;
        }}
        .sidebar-section-lbl {{
          font-size: 10px;
          font-weight: 800;
          text-transform: uppercase;
          letter-spacing: 0.8px;
          color: #8F86A2;
          padding: 4px 10px 2px;
        }}
        .cockpit-sidebar .tabs-nav {{
          display: flex;
          flex-direction: column;
          background: transparent;
          border: none;
          box-shadow: none;
          padding: 0;
          margin: 0;
          gap: 5px;
        }}
        .cockpit-sidebar .tab-btn {{
          width: 100%;
          min-width: 0;
          justify-content: flex-start;
          text-align: left;
          padding: 10px 12px;
          border-radius: 12px;
          font-size: 12.5px;
          font-weight: 600;
          color: #C4BACF;
          background: transparent;
          border: 1px solid transparent;
          white-space: normal;
          line-height: 1.3;
          position: relative;
          transition: all 0.15s ease;
        }}
        .cockpit-sidebar .tab-btn:hover {{
          color: #FAF5EE;
          background: rgba(245, 230, 215, 0.06);
        }}
        .cockpit-sidebar .tab-btn.active {{
          background: linear-gradient(135deg, rgba(244, 162, 97, 0.20) 0%, rgba(200, 100, 70, 0.12) 100%);
          color: #FAF5EE;
          font-weight: 800;
          border-color: rgba(244, 162, 97, 0.42);
          box-shadow: inset 3px 0 0 #F4A261;
        }}
        .sidebar-kpi-mini {{
          background: rgba(33, 28, 44, 0.88);
          border: 1px solid rgba(244, 162, 97, 0.24);
          border-radius: 14px;
          padding: 12px;
          font-size: 11.5px;
          display: flex;
          flex-direction: column;
          gap: 7px;
        }}
        .sidebar-kpi-row {{
          display: flex;
          justify-content: space-between;
          align-items: center;
          font-variant-numeric: tabular-nums;
          color: #E4D8FA;
        }}
        .sidebar-actions-grid {{
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 6px;
          padding-top: 8px;
          border-top: 1px solid rgba(245, 230, 215, 0.12);
        }}
        .sidebar-actions-grid .btn {{
          justify-content: center;
          background: rgba(44, 38, 58, 0.75);
          border-color: rgba(245, 230, 215, 0.18);
          color: #FAF5EE;
          font-size: 11.5px;
          padding: 7px 10px;
        }}
        .sidebar-actions-grid .btn:hover {{
          background: rgba(244, 162, 97, 0.22);
          border-color: #F4A261;
          color: #FFFFFF;
        }}
        .cockpit-main {{
          margin-left: 264px;
          min-width: 0;
          min-height: 100vh;
          display: flex;
          flex-direction: column;
        }}
        body.presentation-mode .cockpit-main {{
          margin-left: 0 !important;
        }}
        .topbar {{
          position: sticky;
          top: 0;
          z-index: 95;
          min-height: 58px;
          padding: 10px 24px;
          margin-bottom: 0;
          border-radius: 0;
          border: none;
          border-bottom: 1px solid var(--border-subtle);
          background: rgba(247, 242, 235, 0.90);
          backdrop-filter: blur(16px);
          box-shadow: 0 2px 14px rgba(100, 76, 56, 0.06);
          display: flex;
          flex-direction: row;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          flex-wrap: wrap;
        }}
        body.theme-slate .topbar {{
          background: rgba(19, 16, 28, 0.88);
          box-shadow: 0 4px 18px rgba(0, 0, 0, 0.35);
        }}
        .workspace-canvas {{
          padding: 18px 24px 64px;
          max-width: 1620px;
          width: 100%;
          margin: 0 auto;
        }}
        /* EKRAN OKUYUCU (SR-ONLY) YARDIMCISI & SADELEŞTİRİLMİŞ DETAY METİN KONTROLÜ */
        .sr-only {{
          position: absolute !important;
          width: 1px !important;
          height: 1px !important;
          padding: 0 !important;
          margin: -1px !important;
          overflow: hidden !important;
          clip: rect(0, 0, 0, 0) !important;
          white-space: nowrap !important;
          border: 0 !important;
        }}
        /* Varsayılan olarak kartlardaki uzun tekrar paragraflarını (.card-desc ve .step-sub) gizleyerek göz yormayan yalın sayı + mikro-çip görünümü sun;
           kullanıcı üst bardaki '📖 Açıklamalar' butonuna bastığında (body.show-verbose-desc) veya karta dokunduğunda (.desc-expanded) açılır */
        body:not(.show-verbose-desc) .card-desc:not(.desc-expanded) {{
          display: none !important;
        }}
        body:not(.show-verbose-desc) .step-sub:not(.desc-expanded) {{
          display: none !important;
        }}
        body.show-verbose-desc .card-desc,
        .card-desc.desc-expanded {{
          display: block !important;
          margin-top: 8px;
          padding-top: 8px;
          border-top: 1px dashed var(--border-subtle);
        }}
        body.show-verbose-desc .step-sub,
        .step-sub.desc-expanded {{
          display: block !important;
          margin-top: 6px;
        }}
        .sidebar-kpi-row.clickable-kpi-row {{
          cursor: pointer;
          padding: 4px 6px;
          margin: -2px -6px;
          border-radius: 8px;
          transition: background 0.15s ease;
        }}
        .sidebar-kpi-row.clickable-kpi-row:hover {{
          background: rgba(165, 105, 189, 0.22);
        }}
        .kpi-micro-meta {{
          display: flex;
          align-items: center;
          flex-wrap: wrap;
          gap: 6px;
          margin-top: 8px;
          font-size: 11.5px;
          font-weight: 600;
          color: var(--text-muted);
          font-variant-numeric: tabular-nums;
        }}
        .kpi-micro-chip {{
          display: inline-flex;
          align-items: center;
          gap: 4px;
          padding: 3px 8px;
          border-radius: 6px;
          background: var(--bg-cell);
          border: 1px solid var(--border-subtle);
          color: var(--text-secondary);
          font-size: 11px;
          font-weight: 700;
        }}
        .bento-card {{
          padding: 22px 24px !important;
          border-radius: 20px !important;
          border: 1px solid var(--border-subtle) !important;
          box-shadow: var(--card-shadow) !important;
          min-width: 0 !important;
          max-width: 100% !important;
        }}
        .section-head {{
          margin-bottom: 14px !important;
          padding-bottom: 10px !important;
          border-bottom: 1px solid var(--border-subtle);
          font-size: 14px !important;
          font-weight: 800 !important;
          letter-spacing: -0.01em;
        }}
        .step-box {{
          padding: 14px 16px !important;
          border-radius: 12px !important;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          gap: 6px;
        }}
        /* 2 SÜTUNLU YAN YANA BENTO YERLEŞİMİ (ALT ALTA YIĞILMAYI VE YATAY TAŞMAYI BİTİRİR) */
        .bento-split-2col {{
          display: grid;
          grid-template-columns: minmax(0, 1.45fr) minmax(0, 1fr);
          gap: 20px;
          align-items: start;
          margin-bottom: 20px;
        }}
        .bento-split-2col-equal {{
          display: grid;
          grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
          gap: 20px;
          align-items: start;
          margin-bottom: 20px;
        }}
        .bento-split-2col > .bento-card,
        .bento-split-2col-equal > .bento-card {{
          margin-bottom: 0 !important;
          min-width: 0 !important;
        }}
        .conv-bridge-card {{
          margin-bottom: 20px;
          padding: 18px 20px;
          border-radius: 16px;
          background: var(--bg-card);
          border: 1px solid var(--border-subtle);
          box-shadow: 0 2px 10px rgba(15, 23, 42, 0.03);
        }}
        .hero-stage-card {{
          padding: 16px 18px;
          border-radius: 16px;
          border: 1px solid var(--border-subtle) !important;
          background: var(--bg-cell);
          backdrop-filter: blur(12px);
        }}
        .hero-stage-card.stage-card-1 {{ background: var(--soft-peach-card) !important; border-color: rgba(var(--stage-1-rgb), 0.32) !important; }}
        .hero-stage-card.stage-card-2 {{ background: var(--soft-sky-card) !important; border-color: rgba(var(--stage-2-rgb), 0.32) !important; }}
        .hero-stage-card.stage-card-3 {{ background: var(--soft-sage-card) !important; border-color: rgba(var(--stage-3-rgb), 0.32) !important; }}
        .hero-stage-card.stage-card-4 {{ background: var(--soft-lavender-card) !important; border-color: rgba(var(--stage-4-rgb), 0.32) !important; }}
        .hero-stage-card.stage-card-5 {{ background: var(--soft-blush-card) !important; border-color: rgba(var(--stage-5-rgb), 0.32) !important; }}
        .hero-stage-card.stage-card-6 {{ background: var(--soft-emerald-card) !important; border-color: rgba(var(--stage-6-rgb), 0.42) !important; }}
        .funnel-collapsed .conv-bridge-grid,
        .funnel-collapsed .conv-tier-bridge {{
          display: none !important;
        }}
        .funnel-collapsed .conv-bridge-head {{
          margin-bottom: 0 !important;
          padding-bottom: 0 !important;
          border-bottom: none !important;
        }}
        @media (max-width: 1150px) {{
          .cockpit-sidebar {{
            position: static;
            width: 100%;
            height: auto;
            box-shadow: none;
          }}
          .cockpit-main {{
            margin-left: 0;
          }}
          .cockpit-sidebar .tabs-nav {{
            flex-direction: row;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
            scrollbar-width: none;
          }}
          .cockpit-sidebar .tabs-nav::-webkit-scrollbar {{
            display: none;
          }}
          .cockpit-sidebar .tab-btn {{
            width: auto;
            white-space: nowrap;
            flex: 0 0 auto;
          }}
          .sidebar-kpi-mini, .sidebar-section-lbl {{
            display: none;
          }}
          .bento-split-2col, .bento-split-2col-equal {{
            grid-template-columns: 1fr;
          }}
        }}
        /* MOBİL-ÖNCELİKLİ (MOBILE-FIRST) TELEFON & TABLET UYUMLULUĞU (<= 768px & <= 480px) */
        @media (max-width: 768px) {{
          .cockpit-sidebar {{
            padding: 8px 12px !important;
            gap: 0 !important;
            position: sticky !important;
            top: 0 !important;
            z-index: 130 !important;
            border-right: none !important;
            border-bottom: 1px solid rgba(244, 162, 97, 0.24);
            min-height: 54px;
            justify-content: center;
          }}
          /* Mobilde üstteki devasa 4 katmanlı yığılmayı kaldır: sekmeler alt dock'a, aksiyonlar sağ ikonlara taşınır */
          .cockpit-sidebar .tabs-nav,
          .cockpit-sidebar .sidebar-actions-grid,
          .cockpit-sidebar .sidebar-section-lbl,
          .cockpit-sidebar .sidebar-kpi-mini,
          .sidebar-live-row {{
            display: none !important;
          }}
          .sidebar-brand-box {{
            padding: 0 !important;
            border-bottom: none !important;
            justify-content: space-between;
            width: 100%;
          }}
          .sidebar-brand-icon {{
            width: 34px !important;
            height: 34px !important;
            border-radius: 10px !important;
          }}
          .sidebar-brand-box h1 {{
            font-size: 13.5px !important;
          }}
          .sidebar-brand-box p {{
            display: none !important;
          }}
          .mobile-brand-mrr-pill {{
            display: inline-flex !important;
          }}
          .mobile-header-quick-actions {{
            display: inline-flex !important;
          }}
          /* Mobilde sabit başparmak dostu alt navigasyon dock'u (app.html tasarım standardı) */
          .cockpit-mobile-bottom-dock {{
            display: grid !important;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 4px;
            position: fixed;
            left: 10px;
            right: 10px;
            bottom: calc(10px + env(safe-area-inset-bottom, 0px));
            z-index: 140;
            padding: 6px;
            border-radius: 20px;
            background: rgba(19, 16, 28, 0.94);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(244, 162, 97, 0.32);
            box-shadow: 0 14px 34px rgba(10, 8, 16, 0.55);
          }}
          .mobile-dock-btn {{
            border: none;
            background: transparent;
            color: #C4BACF;
            padding: 7px 2px;
            border-radius: 14px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 2px;
            font-family: inherit;
            font-size: 10px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.15s ease;
          }}
          .mobile-dock-btn .dock-ico {{
            font-size: 15px;
            line-height: 1.1;
          }}
          .mobile-dock-btn.active {{
            background: linear-gradient(135deg, #F4A261 0%, #C86446 100%);
            color: #13101C;
            font-weight: 800;
            box-shadow: 0 4px 12px rgba(244, 162, 97, 0.30);
          }}
          /* Mobilde topbar sticky olmaktan çıkarılır; ekranın %30'unu kapatması önlenir */
          .topbar {{
            position: static !important;
            padding: 8px 10px !important;
            gap: 6px !important;
          }}
          .topbar > div {{
            width: 100%;
            justify-content: space-between;
          }}
          .period-pills {{
            overflow-x: auto;
            flex-wrap: nowrap !important;
            max-width: 100%;
            -webkit-overflow-scrolling: touch;
            scrollbar-width: none;
            padding-bottom: 2px;
          }}
          .period-pills::-webkit-scrollbar {{
            display: none;
          }}
          .period-pill {{
            white-space: nowrap;
            flex: 0 0 auto;
            padding: 6px 10px !important;
            font-size: 11.5px !important;
          }}
          .workspace-canvas {{
            padding: 10px 10px calc(86px + env(safe-area-inset-bottom, 0px)) !important;
          }}
          .bento-card, .conv-bridge-card {{
            padding: 14px 12px !important;
            border-radius: 16px !important;
            margin-bottom: 12px !important;
          }}
          /* Mobilde 6 Aşamalı Dönüşüm Hunisi: 2x3 kompakt Bento ızgarası */
          .conv-bridge-grid {{
            grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
            gap: 8px !important;
          }}
          .conv-connector {{
            display: none !important;
          }}
          .hero-stage-card {{
            padding: 12px 11px !important;
            border-radius: 14px !important;
          }}
          /* Mobilde 2x2 kartların boyunu patlatan uzun açıklamaları 2 satırda sınırla, dokununca aç */
          .card-desc,
          .step-sub {{
            display: -webkit-box !important;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            font-size: 11px !important;
            line-height: 1.35 !important;
            cursor: pointer;
          }}
          .card-desc.desc-expanded,
          .step-sub.desc-expanded {{
            display: block !important;
            -webkit-line-clamp: unset;
            overflow: visible;
          }}
          .kpi-grid {{
            grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
            gap: 8px !important;
            margin-bottom: 12px !important;
          }}
          .big-num {{
            font-size: clamp(17px, 4.5vw, 22px) !important;
            white-space: normal !important;
            word-break: break-word !important;
            line-height: 1.15 !important;
          }}
          /* 330px / 320px sabit min-width nedeniyle dar telefonlarda oluşan yatay taşmayı sıfırla */
          .donuts-grid,
          .reviews-grid,
          .steps-grid {{
            grid-template-columns: minmax(0, 1fr) !important;
            gap: 10px !important;
          }}
          .donut-wrap {{
            flex-direction: column;
            align-items: center;
            gap: 12px;
          }}
          .donut-legend {{
            width: 100%;
            min-width: 0 !important;
          }}
          .section-head {{
            font-size: 13px !important;
            gap: 8px !important;
          }}
          .table-search-input {{
            min-width: 0 !important;
            width: 100% !important;
            flex: 1 1 140px;
          }}
          .subcat-bar {{
            flex-wrap: nowrap !important;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
            scrollbar-width: none;
            padding: 8px 10px !important;
          }}
          .subcat-bar::-webkit-scrollbar {{
            display: none;
          }}
          .subcat-pill {{
            white-space: nowrap;
            flex: 0 0 auto;
            padding: 6px 11px !important;
            font-size: 11.5px !important;
          }}
          th, td {{
            padding: 8px 9px !important;
            font-size: 11.5px !important;
          }}
          /* Sekme 2 (A/B Testi) ve Sekme 3 (10 Adım Onboarding) Hibrit Mobil Sadeleştirme */
          #tabPane_tab2 .card-desc:not(.desc-expanded),
          #tabPane_tab2 .step-sub:not(.desc-expanded),
          #tabPane_tab3 .card-desc:not(.desc-expanded),
          #tabPane_tab3 .step-sub:not(.desc-expanded) {{
            display: none !important;
          }}
          #tab3SubNav {{
            display: none !important;
          }}
          #onboardingNineStepFunnelCard .section-head {{
            flex-direction: column !important;
            align-items: flex-start !important;
            gap: 6px !important;
            margin-bottom: 8px !important;
            padding-bottom: 8px !important;
          }}
          #onboardingNineStepFunnelCard .section-head > span:first-child {{
            font-size: 13px !important;
          }}
          #onboardingNineStepFunnelCard #onbFunnelDropoffBadge,
          #onboardingNineStepFunnelCard #onbFunnelContinuationMeta {{
            display: none !important;
          }}
          #onboardingNineStepFunnelCard table th:nth-child(3),
          #onboardingNineStepFunnelCard table td:nth-child(3),
          #onboardingNineStepFunnelCard table th:nth-child(5),
          #onboardingNineStepFunnelCard table td:nth-child(5) {{
            display: none !important;
          }}
          #onboardingNineStepFunnelCard table th,
          #onboardingNineStepFunnelCard table td {{
            padding: 6px 4px !important;
            font-size: 11px !important;
            white-space: normal !important;
          }}
          #onboardingNineStepFunnelCard table td:nth-child(1) {{
            font-size: 11.5px !important;
            line-height: 1.25 !important;
            max-width: 148px !important;
          }}
          #onboardingNineStepFunnelCard table td:nth-child(6) {{
            min-width: 72px !important;
          }}
          #abExperimentCommandCard .section-head > div:first-child > span {{
            font-size: 13px !important;
          }}
        }}
        @media (max-width: 480px) {{
          .spark-svg {{
            display: none !important;
          }}
          .card-label {{
            font-size: 10px !important;
            flex-wrap: wrap;
            gap: 4px !important;
          }}
          .delta-chip {{
            font-size: 9.5px !important;
            padding: 2px 6px !important;
          }}
          .kpi-micro-chip {{
            font-size: 10px !important;
            padding: 2px 6px !important;
          }}
          .conv-summary-pills {{
            width: 100%;
            overflow-x: auto;
            flex-wrap: nowrap !important;
            scrollbar-width: none;
            padding-bottom: 2px;
          }}
          .conv-summary-pills::-webkit-scrollbar {{
            display: none;
          }}
          .conv-summary-pill {{
            white-space: nowrap;
            flex: 0 0 auto;
            font-size: 10.5px !important;
            padding: 4px 9px !important;
          }}
        }}
        @media (max-width: 359px) {{
          .conv-bridge-grid,
          .kpi-grid {{
            grid-template-columns: minmax(0, 1fr) !important;
          }}
        }}
      </style>
    </head>
    <body>
      <button type="button" class="pres-exit-fab" onclick="togglePresentationMode()">📽️ Sunum Modundan Çık (ESC)</button>
      <div class="container">
        <div class="cockpit-shell">
          <!-- SOL SABİT 100VH KOYU KOMUTA RAYI (MIŞIL BABY KURUMSAL KOMUTA MERKEZİ) -->
          <aside class="cockpit-sidebar hide-in-pres">
            <div style="display:flex; flex-direction:column; gap:12px;">
              <div class="sidebar-brand-box">
                <div style="display:flex; align-items:center; gap:10px; min-width:0;">
                  <div class="sidebar-brand-icon">
                    <img src="/icon-192.png" alt="Mışıl Baby Logo" class="sidebar-brand-logo-img" />
                  </div>
                  <div style="min-width:0;">
                    <h1>Mışıl Baby<span class="sr-only"> — Kurumsal Büyüme</span></h1>
                    <p>Kurucu Kokpiti</p>
                  </div>
                </div>
                <div class="mobile-header-quick-actions">
                  <span class="mobile-brand-mrr-pill" id="mobileHeaderMrrBadge" title="Aktif VIP & Beklenen Net MRR">👑 {f_vip} VIP • {fl['projected_total_mrr_net_try']:.0f} ₺</span>
                  <button type="button" class="mobile-icon-btn" onclick="toggleTheme()" title="Gündüz / Gece Teması">🌓</button>
                  <a href="/api/v1/analytics/export.csv" class="mobile-icon-btn" title="CSV İndir">📥</a>
                </div>
              </div>

              <div class="sidebar-live-row" style="display:flex; align-items:center; justify-content:space-between; gap:8px; padding:0 4px;">
                <div class="live-pill" onclick="toggleAutoRefresh()" id="liveToggleBtn" style="width:100%; justify-content:center; background:rgba(116,198,157,0.14); border-color:rgba(116,198,157,0.38); color:#74C69D;" title="15 saniyede bir canlı yenileme">
                  <span class="pulse-dot" id="liveDot"></span>
                  <span id="liveCountdown">Canlı: 15s</span>
                </div>
              </div>

              <div class="sidebar-section-lbl">Modüller</div>
              <div class="tabs-nav" role="tablist">
                <button class="tab-btn active" id="tabBtn_tab1" onclick="switchTab('tab1')">📊 1. Büyüme</button>
                <button class="tab-btn" id="tabBtn_tab2" onclick="switchTab('tab2')">💰 2. Gelir & Abone</button>
                <button class="tab-btn" id="tabBtn_tab3" onclick="switchTab('tab3')">🧭 3. Onboarding & Ürün<span class="sr-only">🍼 3. Ürün & Sadakat</span></button>
                <button class="tab-btn" id="tabBtn_tab4" onclick="switchTab('tab4')">⭐ 4. Yorum, Mesaj & Trafik<span class="sr-only">⭐ 4. Yorum & Trafik</span></button>
                <button class="tab-btn" id="tabBtn_tab5" onclick="switchTab('tab5')">🏛️ 5. Veri Mimarisi<span class="sr-only">🏛️ 5. Referanslar & Veri Mimarisi</span></button>
              </div>
            </div>

            <div style="display:flex; flex-direction:column; gap:10px;">
              <div class="sidebar-kpi-mini">
                <div style="font-size:10px; font-weight:800; text-transform:uppercase; color:#FFD4C4; letter-spacing:0.5px;">Özet</div>
                <div class="sidebar-kpi-row">
                  <span>Kurulum</span>
                  <strong style="color:#74C69D;" id="sideKpiDl">{f_dl}</strong>
                </div>
                <div class="sidebar-kpi-row">
                  <span>Aktif VIP</span>
                  <strong style="color:#F4A261;" id="sideKpiVip">{f_vip}</strong>
                </div>
                <div class="sidebar-kpi-row">
                  <span>Net MRR</span>
                  <strong style="color:#FAF5EE;" id="sideKpiMrr">{fl['projected_total_mrr_net_try']:.2f} ₺</strong>
                </div>
                <div class="sidebar-kpi-row clickable-kpi-row" onclick="jumpToAbExperiment()" title="RevenueCat Paywall A/B Testi (Grup A İlk Ay 49.99 ₺ vs Grup B İlk Ay Ücretsiz) Komuta Merkezine Git">
                  <span>🧪 A/B Testi</span>
                  <strong style="color:#F4A261;" id="sideKpiAbTest">🔥A:{ab_a_act} • 🎁B:{ab_b_act}</strong>
                </div>
                <div class="sidebar-kpi-row clickable-kpi-row" onclick="jumpToOnboardingFunnel()" title="10 Adımlı Kullanıcı Onboarding (Adım 0➔9 • Yeni Sıralama & 7. Kart Öneri C) Tablosuna Git">
                  <span>🧭 10 Adım (0➔9)</span>
                  <strong style="color:#D8B4FE;" id="sideKpiOnb">{html.escape(onb_comp_str)} ({int(onb_f.get('step9_reached_devices', 0) or 0)}/{int(onb_f.get('start_base_devices', 0) or 0)})</strong>
                </div>
                <div class="sidebar-kpi-row clickable-kpi-row" onclick="jumpToStarDistribution()" title="🍏 iOS & 🤖 Android 5★..1★ Mağaza Oy Dağılımına Git">
                  <span>⭐ Mağaza Puanı</span>
                  <strong style="color:#F4A261;" id="sideKpiStars">{html.escape(str(all_sd.get('overall_avg_str') or 'Yorum Yok'))} ({int(all_sd.get('overall_count', 0) or 0)} Oy)</strong>
                </div>
                <div class="sidebar-kpi-row clickable-kpi-row" onclick="jumpToInAppFeedbacks()" title="Uygulama İçi Anne Mesajları & Geri Bildirimler Kutusu">
                  <span>💌 Anne Mesajı</span>
                  <strong style="color:#74C69D;" id="sideKpiFeedbacks">{fb_total_cnt} Mesaj</strong>
                </div>
              </div>

              <div class="sidebar-actions-grid">
                <button type="button" class="btn" onclick="toggleTheme()" id="themeToggleBtn" title="Gündüz / Gece Teması">☀️ / 🌙 Tema</button>
                <button type="button" class="btn" onclick="togglePresentationMode()" id="presModeBtn" title="Sunum Modu">📽️ Sunum</button>
                <a href="/api/v1/analytics/export.csv" class="btn" style="grid-column: 1 / -1;">📥 CSV İndir</a>
              </div>
            </div>
          </aside>

          <!-- SAĞ ÇALIŞMA ALANI (58PX YAPIŞKAN GLASS TOPBAR + 2 SÜTUNLU BENTO KANVAS) -->
          <main class="cockpit-main">
            <div class="topbar">
              <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                <div class="period-pills" id="platformPills">
                  <button type="button" class="period-pill active" id="platBtn_all" onclick="switchPlatform('all')">🌐 Tümü</button>
                  <button type="button" class="period-pill" id="platBtn_ios" onclick="switchPlatform('ios')">🍏 iOS</button>
                  <button type="button" class="period-pill" id="platBtn_android" onclick="switchPlatform('android')">🤖 Android</button>
                </div>
                <button type="button" class="compare-toggle-btn hide-in-pres" id="compareToggleBtn" onclick="toggleCompareDrawer()">⇄ Kıyasla</button>
              </div>

              <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                <span class="badge hide-in-pres" id="zeroStaticAuditBadge" style="background:{'rgba(16,185,129,0.14)' if s.get('zero_static_data_audit', {}).get('all_passed', True) else 'rgba(217,119,6,0.14)'}; color:{'#059669' if s.get('zero_static_data_audit', {}).get('all_passed', True) else '#D97706'};" title="{html.escape(str(s.get('zero_static_data_audit', {}).get('status_badge', '🛡️ %100 Canlı Veri')))}">🛡️ {int(s.get('zero_static_data_audit', {}).get('contracts_passed', 5))}/{int(s.get('zero_static_data_audit', {}).get('contracts_checked', 5))} Canlı<span class="sr-only"> %100 Canlı Veri</span></span>
                <span id="livePeriodSub" style="font-size:11.5px; font-weight:700; color:var(--text-secondary); font-variant-numeric:tabular-nums;"><span class="sr-only">{html.escape(s['period_label'])} • </span>{s['active_human_count']} Tık (+{s['today_unique_clicks']} Bugün)</span>
                <div class="period-pills hide-in-pres">
                  {period_pills_html}
                </div>
                <button type="button" class="btn hide-in-pres" id="btnToggleVerboseDesc" onclick="toggleVerboseDescriptions()" style="padding: 6px 11px; font-size: 11.5px;" title="Kart içi uzun metin açıklamalarını göster/gizle">📖 Açıklamalar</button>
                <button type="button" class="btn hide-in-pres" id="btnToggleHeroFunnel" onclick="toggleHeroFunnel()" style="padding: 6px 11px; font-size: 11.5px;">🔼 Daralt</button>
              </div>
            </div>

            <div class="workspace-canvas">
              {sync_banner}

              <!-- 2 KATMANLI (3+3) 6 AŞAMALI DÖNÜŞÜM HUNİSİ (EDİNİM ➔ BAŞLAYAN VIP ➔ CHURN ➔ NET ABONE) -->
              <div class="conv-bridge-card" id="conversionBridgeCard">
                <div class="conv-bridge-head">
                  <div class="conv-bridge-title">
                    <span id="funnelHeadTitle">🎯 Dönüşüm Hunisi<span class="sr-only"> (Edinim ➔ VIP ➔ Churn ➔ Net Abone)</span>{'' if clean_period == 'all' else f" — {html.escape(s['period_label'])}"}</span>
                  </div>
                  <div class="conv-summary-pills" id="funnelHeadBadge">
                    <span class="conv-summary-pill" style="background:rgba(var(--stage-3-rgb),0.10); border-color:rgba(var(--stage-3-rgb),0.28); color:var(--stage-3);">CVR: <strong id="convStoreCvrPill">%{ps_all.get('store_cvr_pct', 0)}</strong></span>
                    <span class="conv-summary-pill">➔ VIP: <strong id="convStartedVipDlPill">%{ps_all.get('started_vip_of_dl_pct', 0)}</strong></span>
                    <span class="conv-summary-pill" style="background:rgba(var(--stage-5-rgb),0.10); border-color:rgba(var(--stage-5-rgb),0.28); color:var(--stage-5);">Churn: <strong id="convChurnPill">%{ps_all.get('churn_rate_pct', 0)}</strong></span>
                    <span class="conv-summary-pill" style="background:rgba(var(--stage-6-rgb),0.10); border-color:rgba(var(--stage-6-rgb),0.28); color:var(--stage-6);">Tutundurma: <strong id="convRetentionPill">%{ps_all.get('retention_rate_pct', 0)}</strong></span>
                    <span class="sr-only">
                      <strong id="convAbTestPill">🔥A:{ab_a_act} vs 🎁B:{ab_b_act} (👑{ab_ann_act}) ➔</strong>
                      <strong id="convOnbCompPill">{html.escape(onb_comp_str)} ({int(onb_f.get('step9_reached_devices', 0) or 0)}/{int(onb_f.get('start_base_devices', 0) or 0)}) ➔</strong>
                      <strong id="convStarsPill">{html.escape(str(all_sd.get('overall_avg_str') or 'Yorum Yok'))} ({int(all_sd.get('overall_count', 0) or 0)} Oy) ➔</strong>
                      <strong id="convFeedbacksPill">{fb_total_cnt} Mesaj ➔</strong>
                      Gösterim ➔ VIP: <strong id="convSumVipImp">%{vip_of_imp_pct}</strong> • Tık ➔ VIP: <strong id="convCum4">%{vip_of_vis_pct}</strong>
                    </span>
                  </div>
                </div>

          <!-- KATMAN 1: EDİNİM HUNİSİ (GÖSTERİM ➔ ZİYARET & TIK ➔ KURULUM) -->
          <div class="conv-bridge-grid">
            <!-- ADIM 1: MAĞAZA GÖSTERİMİ -->
            <div class="hero-stage-card stage-card-1">
              <div>
                <div class="card-label">
                  <span id="kpiTitle1">1. Gösterim</span>
                  <span class="delta-chip" id="kpiDelta1" style="background:rgba(var(--stage-1-rgb),0.14); color:var(--stage-1);">+{s['kpi_deltas']['recent_3d_impressions']} (3G)</span>
                </div>
                <div class="kpi-hero-row">
                  <div class="big-num" style="color:var(--stage-1);" id="kpiImpressions">{f_imp:,}</div>
                  {spark_imp_svg}
                </div>
                <div class="kpi-micro-meta" id="kpiMeta1">
                  <span class="kpi-micro-chip">{kpis['impressions_unique']:,} Tekil Cihaz</span>
                  <span class="kpi-micro-chip">%{imp_search_pct} Arama</span>
                </div>
              </div>
              <div class="card-desc" id="kpiDesc1">{ps_all.get('impressions_sub', '')}</div>
            </div>

            <!-- KÖPRÜ 1: GÖSTERİM ➔ TIK -->
            <div class="conv-connector">
              <span class="conv-conn-lbl">Gösterim ➔ Tık</span>
              <span class="conv-conn-pill" style="color:var(--stage-2); border-color:rgba(var(--stage-2-rgb),0.30);" id="convBridge1">%{vis_of_imp_pct} ➔</span>
              <span class="sr-only" id="convBridge1Sub">{ps_all.get('imp_breakdown_label', '')}</span>
            </div>

            <!-- ADIM 2: İNCELEME & SOSYAL TIK -->
            <div class="hero-stage-card stage-card-2">
              <div>
                <div class="card-label">
                  <span id="kpiTitle2">2. Ziyaret & Tık</span>
                  <span class="delta-chip" id="kpiDelta2" style="background:rgba(var(--stage-2-rgb),0.14); color:var(--stage-2);">+{s['today_unique_clicks']} Bugün</span>
                </div>
                <div class="kpi-hero-row">
                  <div class="big-num" style="color:var(--stage-2);" id="kpiVisitsClicks">{f_vis:,}</div>
                  {spark_vis_svg}
                </div>
                <div class="kpi-micro-meta" id="kpiMeta2">
                  <span class="kpi-micro-chip">{kpis['store_page_views']} Mağaza</span>
                  <span class="kpi-micro-chip">{kpis['bridge_unique_clicks']} Köprü</span>
                </div>
              </div>
              <div class="card-desc" id="kpiDesc2">{ps_all.get('touchpoints_sub', '')}</div>
            </div>

            <!-- KÖPRÜ 2: TIK ➔ İNDİRME -->
            <div class="conv-connector">
              <span class="conv-conn-lbl">Tık ➔ İndirme</span>
              <span class="conv-conn-pill" style="color:var(--stage-3); border-color:rgba(var(--stage-3-rgb),0.30);" id="convBridge2">%{dl_of_vis_pct} ➔</span>
              <span class="sr-only" id="convBridge2Sub">{ps_all.get('cvr_breakdown_label', '')}</span>
            </div>

            <!-- ADIM 3: TOPLAM İNDİRME -->
            <div class="hero-stage-card stage-card-3">
              <div>
                <div class="card-label">
                  <span id="kpiTitle3">3. Kurulum</span>
                  <span class="delta-chip" id="kpiDelta3">+{s['kpi_deltas']['recent_3d_downloads']} (3G)</span>
                </div>
                <div class="kpi-hero-row">
                  <div class="big-num" style="color:var(--stage-3);" id="kpiDownloads">{f_dl}</div>
                  {spark_dl_svg}
                </div>
                <div class="kpi-micro-meta" id="kpiMeta3">
                  <span class="kpi-micro-chip">🍏 {kpis['ios_downloads']} iOS</span>
                  <span class="kpi-micro-chip">🤖 {kpis['android_downloads']} Android</span>
                </div>
              </div>
              <div class="card-desc" id="kpiDesc3">{ps_all.get('downloads_sub', '')}</div>
            </div>
          </div>

          <!-- KATMAN GEÇİŞ KÖPRÜSÜ: KURULUM ➔ BAŞLAYAN VIP -->
          <div class="conv-tier-bridge">
            <span class="conv-tier-lbl">⤵ Kurulum ➔ VIP<span class="sr-only"> Hunisi (İndirme ➔ VIP ➔ İptaller / Churn ➔ Net Abone)</span></span>
            <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
              <span style="font-size:11px; color:var(--text-muted);">➔ VIP:</span>
              <span class="conv-conn-pill" style="color:var(--stage-4); border-color:rgba(var(--stage-4-rgb),0.32);" id="convBridge3">%{ps_all.get('started_vip_of_dl_pct', 0)} ➔</span>
              <span style="font-size:11px; color:var(--text-muted);">➔ Net:</span>
              <span class="conv-conn-pill" style="color:var(--stage-6); border-color:rgba(var(--stage-6-rgb),0.30);" id="convBridge3Net">%{vip_of_dl_pct}</span>
            </div>
          </div>

          <!-- KATMAN 2: ABONELİK, CHURN & NET ABONE HUNİSİ (BAŞLAYAN VIP ➔ İPTALLER / CHURN ➔ NET ABONE) -->
          <div class="conv-bridge-grid">
            <!-- ADIM 4: BAŞLAYAN VIP (TOPLAM KAYIT) -->
            <div class="hero-stage-card stage-card-4">
              <div>
                <div class="card-label">
                  <span id="kpiTitle4">4. Başlayan VIP</span>
                  <span class="delta-chip" id="kpiDelta4" style="background:rgba(var(--stage-4-rgb),0.14); color:var(--stage-4);">%{ps_all.get('started_vip_of_dl_pct', 0)} Kurulumdan</span>
                </div>
                <div class="kpi-hero-row">
                  <div class="big-num" style="color:var(--stage-4);" id="kpiStartedVip">{ps_all.get('total_vip_count', f_vip)}</div>
                  {spark_vip_svg}
                </div>
                <div class="kpi-micro-meta" id="kpiMeta4">
                  <span class="kpi-micro-chip">🍏 {ps_ios.get('total_vip_count', 0)} iOS Başlangıç</span>
                  <span class="kpi-micro-chip">🤖 {ps_and.get('total_vip_count', 0)} Android Başlangıç</span>
                </div>
              </div>
              <div class="card-desc" id="kpiDesc4">{ps_all.get('started_vip_sub', '')}</div>
            </div>

            <!-- KÖPRÜ 4: BAŞLAYAN VIP ➔ İPTALLER (CHURN) -->
            <div class="conv-connector">
              <span class="conv-conn-lbl">VIP ➔ Churn</span>
              <span class="conv-conn-pill" style="color:var(--stage-5); border-color:rgba(var(--stage-5-rgb),0.30);" id="convBridge4">-%{ps_all.get('churn_rate_pct', 0)} ➔</span>
            </div>

            <!-- ADIM 5: İPTALLER & CHURN -->
            <div class="hero-stage-card stage-card-5">
              <div>
                <div class="card-label">
                  <span id="kpiTitle5">5. İptaller (Churn)</span>
                  <span class="delta-chip" id="kpiDelta5" style="background:rgba(var(--stage-5-rgb),0.14); color:var(--stage-5);">%{ps_all.get('churn_rate_pct', 0)} Churn</span>
                </div>
                <div class="kpi-hero-row">
                  <div class="big-num" style="color:var(--stage-5);" id="kpiCancelledVip">{ps_all.get('cancelled_vip_count', 0)}</div>
                </div>
                <div class="kpi-micro-meta" id="kpiMeta5">
                  <span class="kpi-micro-chip">🍏 {ps_ios.get('cancelled_vip_count', 0)} iOS İptal</span>
                  <span class="kpi-micro-chip">🤖 {ps_and.get('cancelled_vip_count', 0)} Android İptal</span>
                  <span class="kpi-micro-chip">✖ %{ps_all.get('churn_rate_pct', 0)} Churn</span>
                </div>
              </div>
              <div class="card-desc" id="kpiDesc5">{ps_all.get('cancelled_vip_sub', '')}</div>
            </div>

            <!-- KÖPRÜ 5: TUTUNDURMA (NET KORUNAN) -->
            <div class="conv-connector">
              <span class="conv-conn-lbl">Tutundurma</span>
              <span class="conv-conn-pill" style="color:var(--stage-6); border-color:rgba(var(--stage-6-rgb),0.30);" id="convBridge5">%{ps_all.get('retention_rate_pct', 0)} ➔</span>
            </div>

            <!-- ADIM 6: NET AKTİF ABONE & BEKLENEN NET MRR -->
            <div class="hero-stage-card stage-card-6" style="border-color:rgba(var(--stage-6-rgb),0.38) !important;">
              <div>
                <div class="card-label">
                  <span id="kpiTitle6">6. Net Abone</span>
                  <span class="delta-chip" id="kpiDelta6" style="background:rgba(var(--stage-6-rgb),0.14); color:var(--stage-6);">{fl['projected_total_mrr_net_try']:.2f} ₺/Ay</span>
                </div>
                <div class="kpi-hero-row">
                  <div class="big-num" style="color:var(--stage-6);" id="kpiVip">{f_vip}</div>
                  {spark_vip_svg}
                </div>
                <div class="kpi-micro-meta" id="kpiMeta6">
                  <span class="kpi-micro-chip">💳 {paid_conv} Ücretli</span>
                  <span class="kpi-micro-chip">⏳ {active_trials} Deneme</span>
                  <span class="kpi-micro-chip">🎟️ {offer_code_subs} Kod</span>
                </div>
              </div>
              <div class="card-desc" id="kpiDesc6">{ps_all.get('vip_sub', '')}</div>
            </div>
          </div>
        </div>

        <!-- İSTEĞE BAĞLI AÇILIR/KAPANIR PLATFORM KIYASLAMA ÇEKMECESİ -->
        <div class="bento-card" id="platformCompareDrawer" style="display:none;">
          <div class="section-head">
            <span>⚖️ iOS vs Android Kıyaslama</span>
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
                  <td style="font-weight:700; color:#059669;">{kpis.get('ios_impressions', f_imp):,} ({int(sb.get('apple_impressions_unique', 0) or 0):,} Cihaz)</td>
                  <td style="font-weight:700; color:#2563EB;">{kpis.get('android_impressions', 0):,} Gösterim (Google Play + Meta)</td>
                  <td><span class="badge" style="background:rgba(217,119,6,0.14); color:#D97706;">App Store & Google Play (%{imp_search_pct} Arama)</span></td>
                </tr>
                <tr>
                  <td><strong>2. İnceleme & Sosyal Tık</strong></td>
                  <td style="font-weight:800; color:#2563EB;">{f_vis:,} Etkileşim</td>
                  <td style="font-weight:700; color:#059669;">{ps_ios.get('touchpoints', 0)} ({kpis.get('ios_store_page_views', kpis['store_page_views'])} Mağaza + {ps_ios.get('touchpoints', 0) - kpis.get('ios_store_page_views', kpis['store_page_views'])} Profil)</td>
                  <td style="font-weight:700; color:#2563EB;">{ps_and.get('touchpoints', 0)} ({kpis.get('android_store_page_views', 0)} Mağaza + {ig['android_clicks']} Profil)</td>
                  <td><span class="badge badge-meta">Mağaza Sayfası + Instagram Profil Bağlantısı</span></td>
                </tr>
                <tr>
                  <td><strong>3. Gerçek Kurulum (İndirme)</strong></td>
                  <td style="font-weight:800; color:#059669; font-size:14px;">{f_dl} Kurulum</td>
                  <td style="font-weight:800; color:#059669;">{kpis['ios_downloads']} iOS (%{dl_ios_pct})</td>
                  <td style="font-weight:800; color:#2563EB;">{kpis['android_downloads']} Android (%{100 - dl_ios_pct})</td>
                  <td><span class="badge badge-gp">🍏 %{ps_ios.get('cvr_pct', 0)} Genel (Mağaza %{ps_ios.get('store_cvr_pct', 0)}) vs 🤖 %{ps_and.get('cvr_pct', 0)} Android CVR</span></td>
                </tr>
                <tr>
                  <td><strong>4. Canlı Abonelik Paketleri &amp; A/B Testi</strong></td>
                  <td style="font-weight:700;">4 Aktif Paket • %50/%50 A/B Testi</td>
                  <td><strong>2 Paket:</strong> <code>misil_annual</code> (599.99 ₺) &amp; <code>misil_monthly</code> (🔥 Grup A: İlk Ay 49.99 ₺ vs 🎁 Grup B: İlk Ay 0 ₺ ➔ 149.99 ₺)</td>
                  <td><strong>{len(gp_catalog)} Paket Aktif:</strong> <code>misil</code> (599.99 ₺) &amp; <code>misilaylik</code> (🔥 Grup A: İlk Ay 49.99 ₺ vs 🎁 Grup B: İlk Ay 0 ₺ ➔ 149.99 ₺)</td>
                  <td><span class="badge badge-gp">🧪 RevenueCat A/B: İlk Ay %67 İndirim vs 30G Ücretsiz</span></td>
                </tr>
                <tr>
                  <td><strong>5. Aktif VIP Abone & Net MRR</strong></td>
                  <td style="font-weight:800; color:#7C3AED;">{f_vip} Aktif VIP ({ps_all.get('total_vip_count', f_vip)} Kayıt • {fl.get('cancelled_subs_count', 0)} İptal / %{fl.get('churn_rate_pct', 0.0)} Churn) • {fl['projected_total_mrr_net_try']:.2f} ₺/Ay</td>
                  <td style="font-weight:800; color:#7C3AED;">{ps_ios.get('vip_count', f_vip)} Aktif VIP ({paid_conv} Ücretli + {active_trials} Deneme + {offer_code_subs} Kod • {ps_ios.get('cancelled_vip_count', 0)} İptal / %{ps_ios.get('churn_rate_pct', 0.0)} Churn)</td>
                  <td style="font-weight:700; color:{'#059669' if ps_and.get('vip_count', 0) > 0 else 'var(--text-muted)'};">{ps_and.get('vip_count', 0)} Aktif Abone ({ps_and.get('cancelled_vip_count', 0)} İptal / %{ps_and.get('churn_rate_pct', 0.0)} Churn • {ps_and.get('mrr_net_try', 0.0):.2f} ₺ MRR)</td>
                  <td><span class="badge" style="background:rgba(124,58,237,0.14); color:#7C3AED;">{'🤖 Android Gelir Köprüsü Aktif' if ps_and.get('vip_count', 0) > 0 else f"Android {kpis['android_downloads']} Kurulum ➔ Paywall Optimizasyon Fırsatı"}</span></td>
                </tr>
                <tr>
                  <td><strong>6. Resmi Mağaza Yorumları</strong></td>
                  <td style="font-weight:800; color:#D97706;">{reviews_total_cnt} Yorum ({avg_stars_label})</td>
                  <td><strong>{ps_ios.get('reviews_count', 0)} App Store Yorumu</strong> ({html.escape(str(ps_ios.get('avg_rating_str', 'Yorum Yok')))})</td>
                  <td><strong>{ps_and.get('reviews_count', 0)} Google Play Yorumu</strong> ({html.escape(str(ps_and.get('avg_rating_str', 'Yorum Yok')))})</td>
                  <td><span class="badge badge-gp">🍏 {html.escape(str(ps_ios.get('avg_rating_str', 'Yorum Yok')))} • 🤖 {html.escape(str(ps_and.get('avg_rating_str', 'Yorum Yok')))} (Canlı API)</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- SEKME 1: BÜYÜME, İNDİRME TRENDİ & EDİNME KANALLARI (2 SÜTUNLU BENTO MİMARİSİ) -->
        <div id="tabPane_tab1" class="tab-pane active">
          <div class="subcat-bar" id="tab1SubNav">
            <span class="subcat-label">📂 Görünüm:</span>
            <button type="button" class="subcat-pill active" id="subcatBtn_t1_all" onclick="filterTab1Category('all')">🌐 Tümü</button>
            <button type="button" class="subcat-pill" id="subcatBtn_t1_trend" onclick="filterTab1Category('trend')">📈 İndirme Trendi &amp; Sosyal</button>
            <button type="button" class="subcat-pill" id="subcatBtn_t1_donuts" onclick="filterTab1Category('donuts')">🍩 Dağılım Halkaları</button>
            <button type="button" class="subcat-pill" id="subcatBtn_t1_channels" onclick="filterTab1Category('channels')">🎯 Edinim &amp; Ülkeler ({len(countries_list)})</button>
          </div>

          <!-- SEKME 1 MÜKERRER OY DAĞILIMI KALDIRILDI (TEK KAYNAK: SEKME 4 #reviewsStarDistributionCard) -->
          <div class="sr-only" id="tab1StarDistributionCard">
            {tab1_star_dist_boxes_html}
          </div>

          <div class="bento-split-2col tab1-sec tab1-sec-trend">
            <div class="bento-card">
              <div class="section-head">
                <div>
                  <span>📈 İndirme Trendi ({f_dl})</span>
                  <div class="sr-only">
                    Yeşil kısım <strong>🍏 Apple iOS</strong>, mavi kısım <strong>🤖 Google Play Android</strong> kurulumlarını; kesikli sütunlar (<code>*</code>) Apple TSV 24s gecikmesini gösterir.
                  </div>
                </div>
                <div class="chart-toggle">
                  <button type="button" onclick="scrollTimelineBy(-260)" title="Eski Günlere Kaydır">◀</button>
                  <button type="button" onclick="scrollTimelineBy(260)" title="Yeni Günlere Kaydır">▶</button>
                  <button id="btnCumChart" class="active" onclick="switchChartMode('cum')">🌐 Tümü ({f_dl})</button>
                  <button id="btnIosChart" onclick="switchChartMode('ios')">🍏 iOS ({kpis['ios_downloads']})</button>
                  <button id="btnAndChart" onclick="switchChartMode('android')">🤖 Android ({kpis['android_downloads']})</button>
                  <button id="btnDailyChart" onclick="switchChartMode('daily')">📊 Günlük</button>
                </div>
              </div>

              <div class="timeline-scroll" id="timelineScrollWrap">
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

            <div class="bento-card">
              <div class="section-head">
                <span id="socialBridgeHeadSpan">📲 Sosyal & Reklam Kanalları ({ig['unique_clicks']} Profil Tıkı)</span>
                <span class="badge" style="background:rgba(16,185,129,0.14); color:#059669;">Canlı Ölçüm</span>
              </div>
              <div class="steps-grid">
                <div class="step-box">
                  <div class="step-num" style="color:#7C3AED;">1. INSTAGRAM PROFİL BAĞLANTISI</div>
                  <div class="step-val" id="igUniqueClicksVal">{ig['unique_clicks']} Kişi</div>
                  <div class="step-sub">Instagram profilimizdeki yönlendirme bağlantısından gelen gerçek tekil ziyaretçiler (<strong>{ig['ios_clicks']} iPhone</strong> + <strong>{ig['android_clicks']} Android</strong>).</div>
                  <span class="step-rate" id="igSplitRate">🍏 {ig['ios_clicks']} iOS • 🤖 {ig['android_clicks']} Android</span>
                </div>
                <div class="step-box">
                  <div class="step-num" style="color:#2563EB;">2. META UYGULAMA REKLAMLARI & MAĞAZA</div>
                  <div class="step-val" id="metaDirectSdkVal">🍏 iOS + 🤖 Android Reklamları Aktif</div>
                  <div class="step-sub">
                    <strong>🍏 iOS:</strong> <span id="iosAttSdkStatusText">{html.escape(str(s.get('meta_app_installs_sdk', {}).get('ios_sdk_status_badge', '🟢 iOS Reklamları Aktif')))}</span> •
                    <strong>🤖 Android:</strong> Google Play organik aramalar ve doğrudan Meta uygulama tanıtım reklamları aktif (<strong>{s.get('meta_app_installs_sdk', {}).get('android_direct_installs', kpis['android_downloads'])} kurulum</strong>).
                  </div>
                  <span class="step-rate" id="metaSplitRate">🍏 {s.get('meta_app_installs_sdk', {}).get('ios_direct_installs', kpis['ios_downloads'])} App Store/Meta • 🤖 {s.get('meta_app_installs_sdk', {}).get('android_direct_installs', kpis['android_downloads'])} Play/Meta Kurulum</span>
                  <span class="sr-only" id="metaUniqueClicksVal">{meta['unique_clicks']} Kişi</span>
                </div>
              </div>
            </div>
          </div>

          <div class="donuts-grid tab1-sec tab1-sec-donuts">
            <div class="bento-card">
              <div class="section-head"><span>🍩 1. Kaynak Dağılımı</span></div>
              {donut_install_sources}
            </div>

            <div class="bento-card">
              <div class="section-head"><span>🍩 2. Ülke Dağılımı</span></div>
              {donut_countries}
            </div>

            <div class="bento-card">
              <div class="section-head"><span>🍩 3. Saat Dağılımı (Zirve: {top_h1})</span></div>
              {donut_night_day}
            </div>
          </div>

          <div class="bento-split-2col tab1-sec tab1-sec-channels">
            <div class="bento-card">
              <div class="section-head">
                <span>🎯 Edinim Kanalları</span>
                <span class="badge badge-gp">🍏 {kpis['ios_downloads']} iOS • 🤖 {kpis['android_downloads']} Android</span>
              </div>
              <div class="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Kanal</th>
                      <th>Kaynak</th>
                      <th>Gösterim</th>
                      <th>Ziyaret / Tık</th>
                      <th>Kurulum</th>
                      <th>CVR</th>
                      <th>VIP</th>
                    </tr>
                  </thead>
                  <tbody>
                    {aso_rows_html}
                  </tbody>
                </table>
              </div>
            </div>

            <div class="bento-card">
              <div class="section-head">
                <span>🌍 Ülke Kurulumları ({len(countries_list)} Ülke)</span>
                <button type="button" class="collapse-btn" id="btnToggleTab1Countries" onclick="toggleDetailWrap('tab1CountriesTableWrap', 'btnToggleTab1Countries')">▼ Tüm Ülkeleri Göster</button>
              </div>
              <div class="table-wrap table-scroll-bounded" id="tab1CountriesTableWrap" style="display:none;">
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

        <!-- SEKME 2: GELİR, MAĞAZA MUTABAKATI & ÜLKE DAĞILIMI (2 SÜTUNLU BENTO MİMARİSİ) -->
        <div id="tabPane_tab2" class="tab-pane">
          <div class="subcat-bar" id="tab2SubNav">
            <span class="subcat-label">📂 Filtre:</span>
            <button type="button" class="subcat-pill active" id="subcatBtn_all" onclick="filterTab2Category('all')">🌐 Tümü</button>
            <button type="button" class="subcat-pill" id="subcatBtn_ab" onclick="filterTab2Category('ab')">🧪 A/B Testi (🔥A:{ab_a_act} vs 🎁B:{ab_b_act})</button>
            <button type="button" class="subcat-pill" id="subcatBtn_reconcile" onclick="filterTab2Category('reconcile')">⚖️ Mutabakat</button>
            <button type="button" class="subcat-pill" id="subcatBtn_country" onclick="filterTab2Category('country')">🌍 Ülke ({paid_countries_cnt})</button>
            <button type="button" class="subcat-pill" id="subcatBtn_calendar" onclick="filterTab2Category('calendar')">📅 Takvim</button>
            <button type="button" class="subcat-pill" id="subcatBtn_ledger" onclick="filterTab2Category('ledger')">📒 Defter ({len(sub_ledger)})</button>
          </div>

          <div class="kpi-grid">
            <div class="bento-card">
              <div class="card-label">💵 1. TAHSİL EDİLEN GELİR</div>
              <div class="big-num" style="color:#059669;">{card1_big_html}</div>
              <div class="kpi-micro-meta">
                <span class="kpi-micro-chip">Brüt: {fl['realized_gross_try']:.2f} ₺</span>
                <span class="kpi-micro-chip">Son 7 Gün: {sr_7d.get('net_try', 0.0):.2f} ₺ Net</span>
                <span class="kpi-micro-chip">🏷️ %15 Komisyon Aktif</span>
              </div>
              <div class="card-desc">
                {card1_desc_html}
              </div>
            </div>

            <div class="bento-card">
              <div class="card-label">🌍 2. ÜCRETLİ ÜLKE</div>
              <div class="big-num" style="color:#2563EB;">{paid_countries_cnt} Ülke</div>
              <div class="kpi-micro-meta">
                <span class="kpi-micro-chip">💳 {paid_conv} Ücretli</span>
                <span class="kpi-micro-chip">👑 {vip_countries_cnt} VIP Ülke</span>
                <span class="kpi-micro-chip">🌍 {dl_countries_cnt} Toplam</span>
              </div>
              <div class="card-desc">
                VIP başlatılan toplam <strong>{vip_countries_cnt} ülke</strong> • İndirme yapılan <strong>{dl_countries_cnt} ülke</strong> • Vadesi dolan deneme: <strong>+{fl['reconciling_7d_mrr_net_try']:.2f} ₺ Net</strong> ({fl['reconciling_7d_trials_count']} abone).
              </div>
            </div>

            <div class="bento-card">
              <div class="card-label">⏳ 3. AKTİF DENEME &amp; VADE HAVUZU (30G / 7G)<span class="sr-only">⏳ 3. AKTİF 7G DENEME &amp; MUTABAKAT</span></div>
              <div class="big-num" style="color:#D97706;">+{fl['pipeline_7d_mrr_net_try']:.2f} ₺</div>
              <div class="kpi-micro-meta">
                <span class="kpi-micro-chip">🎁 30G Ücretsiz: {fl.get('active_30d_trials_count', 0)} (+{fl.get('active_30d_mrr_net_try', 0.0):.2f} ₺)</span>
                <span class="kpi-micro-chip">⏳ 7G Tarihsel: {fl.get('active_legacy_7d_trials_count', 0)} (+{fl.get('active_legacy_7d_mrr_net_try', 0.0):.2f} ₺)</span>
                <span class="kpi-micro-chip">🔄 Mutabakat: {fl['reconciling_7d_trials_count']}</span>
              </div>
              <div class="card-desc">
                Toplam Deneme Havuzu: <strong>{fl['pipeline_7d_trials_count']} Abone (+{fl['pipeline_7d_mrr_net_try']:.2f} ₺ Net / {fl['pipeline_7d_mrr_gross_try']:.2f} ₺ Brüt)</strong> — 🎁 Grup B 30G Ücretsiz: <strong>{fl.get('active_30d_trials_count', 0)} abone (+{fl.get('active_30d_mrr_net_try', 0.0):.2f} ₺)</strong> • ⏳ Tarihsel 7G Deneme: <strong>{fl.get('active_legacy_7d_trials_count', 0)} abone (+{fl.get('active_legacy_7d_mrr_net_try', 0.0):.2f} ₺)</strong> • Vade mutabakatında: <strong>{fl['reconciling_7d_trials_count']} abone</strong>.
              </div>
            </div>

            <div class="bento-card">
              <div class="card-label">🚀 4. BEKLENEN NET MRR</div>
              <div class="big-num" style="color:#7C3AED;">{fl['projected_total_mrr_net_try']:.2f} ₺</div>
              <div class="kpi-micro-meta">
                <span class="kpi-micro-chip">🍏 {ps_ios.get('mrr_net_try', fl['projected_total_mrr_net_try']):.2f} ₺</span>
                <span class="kpi-micro-chip">🤖 {ps_and.get('mrr_net_try', 0.0):.2f} ₺</span>
                <span class="kpi-micro-chip">💳 {fl.get('auto_renewing_paid_subs_count', fl['paid_subs_count'])}/{fl['paid_subs_count']} Oto-Yenileme</span>
                <span class="kpi-micro-chip">🏷️ %15 Komisyon</span>
              </div>
              <div class="card-desc">
                🍏 Apple (%15 SBP): <strong>{ps_ios.get('mrr_net_try', fl['projected_total_mrr_net_try']):.2f} ₺ Net/Ay</strong> ({ps_ios.get('vip_count', f_vip)} Aktif / {ps_ios.get('total_vip_count', len(sub_ledger))} Kayıt • <strong>{fl.get('auto_renewing_paid_subs_count', fl['paid_subs_count'])} Oto-Yenileme Açık</strong>, <strong>{fl.get('non_renewing_paid_subs_count', 0)} Dönem Sonu Bitecek</strong>) • 🤖 Google Play (%15): <strong>{ps_and.get('mrr_net_try', 0.0):.2f} ₺ Net/Ay</strong> ({ps_and.get('vip_count', 0)} Abone).
              </div>
            </div>
          </div>

          {ab_experiment_html}

          <div class="bento-split-2col">
            {store_reconciliation_html}

            <div class="bento-card tab2-sec tab2-sec-calendar" id="appleRenewalCard">
              <div class="section-head">
                <span>📅 Deneme &amp; Yenileme Vade Takvimi (30G / 7G)<span class="sr-only">📅 7G Vade Takvimi</span></span>
                <span class="badge" style="background:rgba(16,185,129,0.14); color:#059669;">+{fl['pipeline_7d_mrr_net_try']:.2f} ₺ Net</span>
              </div>
              <div class="steps-grid">
                {renewal_calendar_html}
              </div>
            </div>
          </div>

          <div class="bento-split-2col">
            {country_revenue_html}

            <!-- GOOGLE PLAY STORE ABONELİK PAKETLERİ -->
            <div class="bento-card tab2-sec tab2-sec-ledger" id="googlePlayLedgerCard">
              <div class="section-head">
                <span>🤖 Google Play Paketleri</span>
                <div style="display:flex; align-items:center; gap:8px;">
                  <span class="badge badge-gp">{len(gp_catalog)} Paket • {ps_and.get('vip_count', 0)} Abone</span>
                  <button type="button" class="collapse-btn" id="btnToggleGpLedger" onclick="toggleDetailWrap('gpLedgerTableWrap', 'btnToggleGpLedger')">▼ Göster</button>
                </div>
              </div>
              <div class="sr-only">
                {gp_diag_html}
              </div>
              <div class="table-wrap" id="gpLedgerTableWrap" style="display:none;">
                <table>
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Google Play Ürün / Plan ID</th>
                      <th>Mağaza Paket Başlığı</th>
                      <th>Durum</th>
                      <th>Periyot</th>
                      <th>Başlangıç Teklifi</th>
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

          <div class="bento-card tab2-sec tab2-sec-ledger" id="appleLedgerCard">
            <div class="section-head">
              <span id="ledgerHeadSpan">📒 Abone Defteri ({f_vip} Aktif • {fl.get('cancelled_subs_count', 0)} İptal / %{fl.get('churn_rate_pct', 0.0)} Churn • Toplam {len(sub_ledger)} Kayıt)</span>
              <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                <input type="search" id="appleLedgerSearchInput" class="table-search-input" placeholder="🔍 Abone ID, ülke, paket ara..." oninput="filterTableByQuery(this, 'appleLedgerTbody')" />
                <button type="button" class="collapse-btn" id="btnToggleAppleLedger" onclick="toggleDetailWrap('appleLedgerTableWrap', 'btnToggleAppleLedger')">▲ Gizle</button>
              </div>
            </div>
            <div class="table-wrap table-scroll-bounded" id="appleLedgerTableWrap" style="display:block;">
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Abone ID</th>
                    <th>Paket</th>
                    <th>Durum &amp; A/B Vade İlerleme<span class="sr-only">Durum & 7G İlerleme</span></th>
                    <th>Başlangıç</th>
                    <th>Son İşlem</th>
                    <th>Yenilenme / Vade</th>
                    <th>Oto-Yenileme</th>
                    <th>Tahsil Edilen (Brüt / Net)</th>
                    <th>Sonraki Dönem</th>
                    <th>Ülke / Cihaz</th>
                  </tr>
                </thead>
                <tbody id="appleLedgerTbody">
                  {ledger_rows_html}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <!-- SEKME 3: 10 ADIMLI ONBOARDING (0➔9), ÜRÜN KULLANIMI, PAYWALL & KOHORT TUTUNDURMA -->
        <div id="tabPane_tab3" class="tab-pane">
          <div class="subcat-bar" id="tab3SubNav">
            <span class="subcat-label">📂 Görünüm:</span>
            <button type="button" class="subcat-pill active" id="subcatBtn_t3_all" onclick="filterTab3Category('all')">🌐 Tümü</button>
            <button type="button" class="subcat-pill" id="subcatBtn_t3_onboarding" onclick="filterTab3Category('onboarding')">🧭 10 Adım Onboarding ({onb_total_devs} Cihaz)</button>
            <button type="button" class="subcat-pill" id="subcatBtn_t3_paywall" onclick="filterTab3Category('paywall')">🔄 Paywall &amp; Modüller</button>
            <button type="button" class="subcat-pill" id="subcatBtn_t3_cohort" onclick="filterTab3Category('cohort')">📊 Kohort Matrisi ({len(pr['subscriber_cohorts'])})</button>
          </div>

          <div class="bento-card tab3-sec tab3-sec-onboarding" id="onboardingNineStepFunnelCard">
            <div class="section-head">
              <span>🧭 10 Adım Onboarding (Adım 0➔9 • Yeni Sıralama &amp; 7. Kart Öneri C)<span class="sr-only"> — 9 Adımlı Kullanıcı Onboarding &amp; Paywall İlerleme Analizi (Gerçek Cihaz Telemetrisi — Sıfır Statik Veri)</span></span>
              <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                <span class="badge" id="onbFunnelDevicesBadge" style="background:rgba(37,99,235,0.12); color:#2563EB;">📱 {onb_total_devs} Cihaz</span>
                <span class="badge" id="onbFunnelCompletionBadge" style="background:rgba(124,58,237,0.14); color:#7C3AED;">🏁 0➔9: {html.escape(onb_comp_str)}</span>
                <span class="badge" id="onbFunnelPurchasesBadge" style="background:rgba(16,185,129,0.16); color:#059669;">{html.escape(onb_purchases_badge_str)}</span>
                <span class="badge" id="onbFunnelDropoffBadge" style="background:rgba(217,119,6,0.14); color:#D97706;">{html.escape(onb_drop_badge_str)}</span>
              </div>
            </div>
            <div style="display:flex; align-items:center; justify-content:space-between; gap:8px; flex-wrap:wrap; margin-bottom:10px;">
              <div class="period-pills" id="onbAbCohortPills">
                <button type="button" class="period-pill active" id="onbCohortBtn_all" onclick="switchOnboardingAbCohort('all')">🌐 Kümülatif ({onb_total_devs} Cihaz)</button>
                <button type="button" class="period-pill" id="onbCohortBtn_group_a" onclick="switchOnboardingAbCohort('group_a')">🔥 A Grubu: İlk Ay ₺49,99 ({onb_ga_total_devs} Cihaz • 💳 {onb_purch_a})</button>
                <button type="button" class="period-pill" id="onbCohortBtn_group_b" onclick="switchOnboardingAbCohort('group_b')">🎁 B Grubu: 30G Ücretsiz ({onb_gb_total_devs} Cihaz • 💳 {onb_purch_b})</button>
              </div>
              <div class="kpi-micro-meta" id="onbFunnelContinuationMeta" style="margin:0;">
                <span class="kpi-micro-chip">🚀 Açılış: {int(onb_f.get('first_open_unique_devices', 0) or 0)}</span>
                <span class="kpi-micro-chip">⚡ 7. Kart Hızlı Çip: {int(onb_f.get('step7_quick_chip_unique_devices', 0) or 0)}</span>
                <span class="kpi-micro-chip">👁️ Paywall: {int(onb_f.get('paywall_viewed_unique_devices', 0) or 0)} (🔥A:{int(onb_f.get('ab_a_paywall_viewed_unique_devices', 0) or 0)} • 🎁B:{int(onb_f.get('ab_b_paywall_viewed_unique_devices', 0) or 0)})</span>
                <span class="kpi-micro-chip">👆 Tık: {int(onb_f.get('paywall_cta_unique_devices', 0) or 0)} (🔥A:{int(onb_f.get('ab_a_paywall_cta_unique_devices', 0) or 0)} • 🎁B:{int(onb_f.get('ab_b_paywall_cta_unique_devices', 0) or 0)})</span>
              </div>
            </div>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Adım</th>
                    <th>Cihaz</th>
                    <th>🍏 / 🤖</th>
                    <th>Geçiş</th>
                    <th>Kayıp</th>
                    <th>İlerleme</th>
                  </tr>
                </thead>
                <tbody id="onboardingNineStepTbody">
                  {onb_rows_html}
                </tbody>
              </table>
            </div>
          </div>

          <div class="kpi-grid tab3-sec tab3-sec-paywall">
            <div class="bento-card">
              <div class="card-label">📱 UYGULAMA OTURUMLARI</div>
              <div class="big-num" style="color:#2563EB;">{pr['total_tracked_sessions']}</div>
              <div class="kpi-micro-meta">
                <span class="kpi-micro-chip">⚡ {pr.get('live_telemetry_sessions', 0)} Canlı</span>
                <span class="kpi-micro-chip">🍏 {pr['apple_official_sessions']} Mağaza Onaylı</span>
                <span class="kpi-micro-chip">⏱️ {pr['avg_session_duration_sec']} sn</span>
              </div>
              <div class="card-desc">
                Canlı uygulama oturumu: <strong>{pr.get('live_telemetry_sessions', 0)} oturum</strong> • Resmi mağaza verisi: <strong>{pr['apple_official_sessions'] + pr.get('android_official_sessions', 0)} oturum</strong> ({pr['returning_sessions_total']} tekrar) • Ortalama süre: <strong>{pr['avg_session_duration_sec']} sn</strong>.
              </div>
            </div>

            <div class="bento-card">
              <div class="card-label">🔄 GERİ DÖNEN CİHAZLAR</div>
              <div class="big-num" style="color:#059669;">{pr['verified_returning_devices_floor']}–{pr['verified_returning_devices_ceiling']}</div>
              <div class="kpi-micro-meta">
                <span class="kpi-micro-chip">Geri Dönüş: %{pr['optin_ios_return_rate_pct']}</span>
                <span class="kpi-micro-chip">~{pr['estimated_total_returning_users']} Ebeveyn</span>
              </div>
              <div class="card-desc">
                Tekrar Giren iPhone: <strong>{pr['returning_optin_ios_devices']}/{pr['optin_ios_total_devices']} Cihaz (%{pr['optin_ios_return_rate_pct']})</strong> • 3+ Oturum Sadık: <strong>{pr['loyal_optin_ios_devices']}</strong> • Toplam Tahmini Sadık: <strong>~{pr['estimated_total_returning_users']} Ebeveyn</strong>.
              </div>
            </div>

            <div class="bento-card">
              <div class="card-label">🌙 GECE NÖBETİ &amp; PROFİL</div>
              <div class="big-num" style="color:#7C3AED;">%{nvd['night_pct']} • {pr['babies_count']} Bebek</div>
              <div class="kpi-micro-meta">
                <span class="kpi-micro-chip">🌙 {nvd['night_clicks']} Gece</span>
                <span class="kpi-micro-chip">☀️ {nvd['day_clicks']} Gündüz</span>
              </div>
              <div class="card-desc">
                <strong>{nvd['night_clicks']} Gece</strong> vs <strong>{nvd['day_clicks']} Gündüz</strong> etkileşimi • Kayıtlı bebek profili: <strong>{pr['babies_count']}</strong> ({top_h1} / {top_h2}).
              </div>
            </div>

            <div class="bento-card">
              <div class="card-label">🛡️ KOHORT TUTUNDURMA</div>
              <div class="big-num" style="color:#D97706;">{html.escape(pr['overall_retention_str'])}</div>
              <div class="kpi-micro-meta">
                <span class="kpi-micro-chip">{len(pr['subscriber_cohorts'])} Kohort</span>
                <span class="kpi-micro-chip">{fl['cancelled_subs_count']} İptal</span>
              </div>
              <div class="card-desc">
                Toplam <strong>{len(pr['subscriber_cohorts'])} ayrı günlük kohorttaki {len(sub_ledger)} abonenin</strong> aktif tutundurma oranı (<strong>{fl['cancelled_subs_count']} İptal</strong>).
              </div>
            </div>
          </div>

          <div class="bento-split-2col-equal tab3-sec tab3-sec-paywall">
            <div class="bento-card">
              <div class="section-head">
                <span>💳 Paywall Dönüşüm &amp; İptal Özeti<span class="sr-only">🔄 Geri Dönüş &amp; Paywall</span></span>
                <span class="badge" style="background:rgba(124,58,237,0.14); color:#7C3AED;">👁️ {pf['paywall_funnel']['paywall_viewed']} ➔ 👆 {pf['paywall_funnel']['paywall_cta_clicked']}</span>
              </div>
              <div class="steps-grid">
                <div class="step-box">
                  <div class="step-num" style="color:#7C3AED;">1. PAYWALL ➔ SATIN ALMA ADIMI</div>
                  <div class="step-val">{pf['paywall_funnel']['paywall_viewed']} ➔ {pf['paywall_funnel']['paywall_cta_clicked']}</div>
                  <div class="step-sub">İlk Açılış: <strong>{pf['first_open_signals']}</strong> • Bebek Profili: <strong>{pr['babies_count']}</strong> • Paywall Atlama: <strong>{pf['paywall_funnel']['paywall_skipped']}</strong> • 60sn Ses Önizleme Bitişi: <strong>{pf['paywall_funnel']['sound_preview_60s_ended']}</strong>.</div>
                  <span class="step-rate">🍏 {pf['paywall_funnel']['ios']['paywall_viewed']}➔{pf['paywall_funnel']['ios']['paywall_cta_clicked']} • 🤖 {pf['paywall_funnel']['android']['paywall_viewed']}➔{pf['paywall_funnel']['android']['paywall_cta_clicked']}</span>
                </div>
                <div class="step-box">
                  <div class="step-num" style="color:var(--stage-5);">2. ÖDEME İPTALİ &amp; KURTARMA</div>
                  <div class="step-val">{pf['paywall_funnel']['purchase_cancelled']} (%{pf['paywall_funnel']['cancel_rate_pct']})</div>
                  <div class="step-sub">🍏 iOS: <strong>{pf['paywall_funnel']['ios']['purchase_cancelled']}/{pf['paywall_funnel']['ios']['paywall_cta_clicked']}</strong> • 🤖 Android: <strong>{pf['paywall_funnel']['android']['purchase_cancelled']}/{pf['paywall_funnel']['android']['paywall_cta_clicked']}</strong> • Kurtarma Gösterimi: <strong>{pf['paywall_funnel']['paywall_cancel_recovery_shown']}</strong> (Kurtarma CTA: <strong>{pf['paywall_funnel'].get('paywall_cancel_recovery_cta_clicked', 0)}</strong>).</div>
                  <span class="step-rate">🍏 {pf['paywall_funnel']['ios']['purchase_cancelled']} İptal • 🤖 {pf['paywall_funnel']['android']['purchase_cancelled']} İptal</span>
                </div>
              </div>
            </div>

            <div class="bento-card">
              <div class="section-head">
                <span>🍼 Modül Aktivitesi</span>
              </div>
              <div class="steps-grid">
                <div class="step-box">
                  <div class="step-num" style="color:#059669;">UYKU & SES</div>
                  <div class="step-val">{pr['sleep_logs_count']} Kayıt</div>
                  <div class="step-sub">Bulut senkronizasyonlu uyku seansı ve ses oynatma takibi aktif.</div>
                  <span class="step-rate">Bulut Senkron Aktif</span>
                </div>
                <div class="step-box">
                  <div class="step-num" style="color:#2563EB;">AĞLAMA ANALİZİ</div>
                  <div class="step-val">{pr['cry_events_count']} Analiz</div>
                  <div class="step-sub">Yapay zeka destekli bebek ağlama analizi aktif.</div>
                  <span class="step-rate">AI Analiz Aktif</span>
                </div>
                <div class="step-box">
                  <div class="step-num" style="color:#D97706;">RUTİN & DADI AI</div>
                  <div class="step-val">{pr['routine_logs_count'] + pr['dadi_chats_count']} İşlem</div>
                  <div class="step-sub">{pr['routine_logs_count']} rutin kaydı + {pr['dadi_chats_count']} Bilge Dadı sohbet mesajı.</div>
                  <span class="step-rate">{pr['routine_logs_count']} Rutin • {pr['dadi_chats_count']} Sohbet</span>
                </div>
                <div class="step-box">
                  <div class="step-num" style="color:#7C3AED;">VIP AKTİVASYON</div>
                  <div class="step-val">{pf['vip_started_signals']} Aktivasyon</div>
                  <div class="step-sub">Uygulama içi VIP başlangıç ve ilk açılış ({pf['first_open_signals']}) takibi aktif.</div>
                  <span class="step-rate">{pf['first_open_signals']} İlk Açılış</span>
                </div>
              </div>
            </div>
          </div>

          <div class="bento-card tab3-sec tab3-sec-cohort">
            <div class="section-head">
              <span>📊 Kohort Matrisi</span>
              <span class="badge" style="background:rgba(16,185,129,0.14); color:#059669;">{len(pr['subscriber_cohorts'])} Kohort • {html.escape(pr['overall_retention_str'])}</span>
            </div>
            <div class="table-wrap table-scroll-bounded">
              <table>
                <thead>
                  <tr>
                    <th>Kohort Başlangıç Günü</th>
                    <th>Başlayan VIP</th>
                    <th>Ücretliye Geçen (🔥 Grup A / 👑 Yıllık)</th>
                    <th>Yıllık Kodlu</th>
                    <th>Denemesi Süren (🎁 30G / ⏳ 7G)<span class="sr-only">7G Denemesi Süren</span></th>
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
        </div>

        <!-- SEKME 4: MAĞAZA YORUMLARI & CANLI SOSYAL KÖPRÜ TRAFİĞİ (2 SÜTUN YAN YANA) -->
        <div id="tabPane_tab4" class="tab-pane">
          <!-- SEKME 4 EN ÜST TAM GENİŞLİKLİ 5★..1★ YILDIZ & OY DAĞILIMI KARTI -->
          <div class="bento-card" id="reviewsStarDistributionCard" style="margin-bottom:14px;">
            <div class="section-head">
              <span>⭐ Mağaza Oy &amp; Yıldız Dağılımı (🍏 iOS App Store &amp; 🤖 Android Google Play)</span>
              <span class="badge" id="reviewsTopAvgBadge" style="background:rgba(217,119,6,0.14); color:#D97706;">{avg_stars_label}</span>
            </div>
            <div class="bento-split-2col-equal" id="reviewsStarDistributionGrid" style="margin-bottom:0;">
              {star_dist_boxes_html}
            </div>
          </div>

            <div class="bento-card" id="inAppFeedbacksCard" style="margin-bottom:14px;">
              <div class="section-head">
                <span id="inAppFeedbacksHeadSpan">💌 Uygulama İçi Anne Mesajları &amp; Geri Bildirimler ({fb_total_cnt})</span>
                <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                  <span class="badge" id="inAppFeedbacksTotalBadge" style="background:rgba(16,185,129,0.14); color:#059669;">📨 Toplam: {fb_total_cnt}</span>
                  <span class="badge" id="inAppFeedbacks24hBadge" style="background:rgba(217,119,6,0.14); color:#D97706;">⚡ Son 24s: {fb_24h_cnt}</span>
                  <input type="search" id="inAppFeedbacksSearchInput" class="table-search-input" placeholder="🔍 Mesaj, iletişim, bebek ayı ara..." oninput="filterInAppFeedbacks(this)" />
                  <a href="/api/v1/feedback/export.csv" class="btn">📥 CSV</a>
                </div>
              </div>
              <div class="reviews-grid" id="inAppFeedbacksList" style="max-height:460px; overflow-y:auto; padding-right:4px;">
                {in_app_feedbacks_html}
              </div>
            </div>

          <div class="bento-split-2col-equal">
            <div class="bento-card">
              <div class="section-head">
                <span>💬 Yazılı Mağaza Yorumları ({reviews_total_cnt})</span>
              </div>

              <!-- DÜŞÜK YILDIZ KURTARMA: UYGULAMA İÇİ + YEREL BİLDİRİM MEMNUNİYET & ÇÖZÜM YOKLAMASI -->
              <div class="step-box" id="satisfactionPulseCard" style="margin-bottom:12px; border-left:4px solid #F4A261;">
                <div style="display:flex; align-items:center; justify-content:space-between; gap:8px; flex-wrap:wrap;">
                  <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
                    <span style="font-size:11.5px; font-weight:800; color:#F4A261;">🔔 Çözüm &amp; Memnuniyet Yoklaması</span>
                    <span class="badge" id="pulseStatusBadge" style="background:{pulse_status_bg}; color:{pulse_status_col}; font-size:10.5px; padding:2px 8px;">{pulse_status_badge}</span>
                  </div>
                  <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
                    <span class="kpi-micro-chip" title="Yoklamayı Gören Cihaz">👁️ <strong id="pulseShownCnt">{int(pulse_info.get('shown_count', 0) or 0)}</strong></span>
                    <span class="kpi-micro-chip" style="color:#059669;" title="Sorun Çözüldü / Memnun (Mağaza Puanına Yönlendirildi)">😍 <strong id="pulseSatisfiedCnt">{int(pulse_info.get('satisfied_count', 0) or 0)}</strong></span>
                    <span class="kpi-micro-chip" onclick="jumpToInAppFeedbacks()" style="color:#DC2626; cursor:pointer;" title="Sorun Devam Ediyor (Kokpite Geri Bildirim Düştü — Mesajlara Git)">💬 <strong id="pulseIssueCnt">{int(pulse_info.get('issue_persists_count', 0) or 0)}</strong></span>
                    <button type="button" class="collapse-btn" onclick="toggleDetailWrap('pulseConfigDrawer', 'btnTogglePulseDrawer')" id="btnTogglePulseDrawer" style="font-size:11px; padding:3px 9px;">⚙️ Ayarla</button>
                  </div>
                </div>
                <div id="pulseConfigDrawer" style="display:none; margin-top:10px; padding-top:8px; border-top:1px dashed var(--border-subtle);">
                  <div style="display:grid; grid-template-columns:110px 1fr; gap:6px; margin-bottom:6px;">
                    <select id="pulseTargetPlat" style="border-radius:8px; border:1px solid var(--border-subtle); background:var(--bg-card); color:var(--text-primary); padding:6px 8px; font-size:11.5px;">
                      <option value="ios" {'selected' if pulse_info.get('target_platform', 'ios') == 'ios' else ''}>🍏 iOS</option>
                      <option value="android" {'selected' if pulse_info.get('target_platform') == 'android' else ''}>🤖 Android</option>
                      <option value="all" {'selected' if pulse_info.get('target_platform') == 'all' else ''}>🌐 Tümü</option>
                    </select>
                    <input type="text" id="pulseTitleInput" value="{html.escape(str(pulse_info.get('title_tr') or 'Uyku ve uyanma saatleri kaydı iyileştirildi'))}" placeholder="Başlık (Örn: Uyku saatleri kaydı iyileştirildi)" style="border-radius:8px; border:1px solid var(--border-subtle); background:var(--bg-card); color:var(--text-primary); padding:6px 10px; font-size:11.5px;" />
                  </div>
                  <input type="text" id="pulseQuestionInput" value="{html.escape(str(pulse_info.get('question_tr') or 'Son güncellememizden sonra uyku kayıtlarınız sorunsuz çalışıyor mu?'))}" placeholder="Kullanıcıya sorulacak soru..." style="width:100%; border-radius:8px; border:1px solid var(--border-subtle); background:var(--bg-card); color:var(--text-primary); padding:6px 10px; font-size:11.5px; margin-bottom:8px;" />
                  <input type="hidden" id="pulseRefAuthor" value="{html.escape(str(pulse_info.get('reference_author') or 'Rabia Özcan Kahya'))}" />
                  <input type="hidden" id="pulseRefReviewId" value="{html.escape(str(pulse_info.get('reference_review_id') or ''))}" />
                  <div style="display:flex; justify-content:space-between; align-items:center; gap:6px; flex-wrap:wrap;">
                    <button type="button" class="btn" onclick="submitSatisfactionPulseConfig(false)" id="btnStopPulse" style="padding:5px 10px; font-size:11px;">⏹️ Durdur</button>
                    <button type="button" class="subcat-pill active" onclick="submitSatisfactionPulseConfig(true)" id="btnStartPulse" style="padding:5px 12px; font-size:11px;">🚀 Bildirim &amp; Yoklamayı Başlat</button>
                  </div>
                </div>
              </div>

              <div class="reviews-grid">
                {reviews_html}
              </div>
            </div>

            <div class="bento-card">
              <div class="section-head">
                <span id="liveClicksHeadSpan">⚡ Canlı Trafik ({s['active_human_count']} Tekil)</span>
                <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                  <input type="search" id="liveClicksSearchInput" class="table-search-input" placeholder="🔍 Cihaz, mağaza, ülke ara..." oninput="filterTableByQuery(this, 'liveClicksTbody')" />
                  <a href="/api/v1/analytics/export.csv" class="btn">📥 CSV</a>
                </div>
              </div>
              <div class="table-wrap table-scroll-bounded">
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
                  <tbody id="liveClicksTbody">
                    {rows_html}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>

        <!-- SEKME 5: REFERANSLAR & VERİ MİMARİSİ (2 SÜTUNLU BENTO MİMARİSİ) -->
        <div id="tabPane_tab5" class="tab-pane">
          <div class="bento-card" id="dataGovernanceMatrixCard">
            <div class="section-head">
              <div>
                <span>📋 Veri Sözlüğü (SSOT)<span class="sr-only">Hangi Veri, Hangi Yöntemle, Ne Frekansta Güncellenir?</span></span>
              </div>
              <span class="badge" style="background:rgba(16,185,129,0.14); color:#059669;">SSOT Aktif</span>
            </div>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Veri Kümesi & Kapsanan Metrikler</th>
                    <th>Tek Doğruluk Kaynağı (DB Tablosu)</th>
                    <th>Güncelleme Yöntemi (Nasıl Gelir?)</th>
                    <th>Güncellenme Frekansı</th>
                    <th>Gecikme Sınıfı</th>
                    <th>Son Veri & Durum</th>
                    <th>Tutarlılık & İzolasyon Kuralı</th>
                  </tr>
                </thead>
                <tbody>
                  {gov_rows_html}
                </tbody>
              </table>
            </div>
          </div>

          <div class="bento-split-2col-equal">
            <div class="bento-card" id="architecturePrinciplesCard">
              <div class="section-head">
                <span>🧭 Tutarlılık İlkeleri</span>
              </div>
              <div class="steps-grid">
                {arch_cards_html}
              </div>
            </div>

            <div class="bento-card" id="syncPipelinesStatusCard">
              <div class="section-head">
                <span>🔌 Aktif Veri Hatları</span>
                <span class="badge badge-meta">{html.escape(str(sb.get('last_synced_at', '-')))}</span>
              </div>
              <div class="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Veri Hattı (Pipeline)</th>
                      <th>Sistem Anahtarı</th>
                      <th>Güncel Durum & Son Veri</th>
                      <th>Kapsam & Detay</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sync_sources_rows_html}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
            </div>
          </main>
        </div>
        <!-- MOBİL SABİT ALT NAVİGASYON DOCK BARI (app.html MİMARİ PARİTESİ) -->
        <nav class="cockpit-mobile-bottom-dock hide-in-pres" id="cockpitMobileBottomDock" aria-label="Mobil Modül Navigasyonu">
          <button type="button" class="mobile-dock-btn active" id="mobDockBtn_tab1" onclick="switchTab('tab1')">
            <span class="dock-ico">📊</span>
            <span>Büyüme</span>
          </button>
          <button type="button" class="mobile-dock-btn" id="mobDockBtn_tab2" onclick="switchTab('tab2')">
            <span class="dock-ico">💰</span>
            <span>Gelir</span>
          </button>
          <button type="button" class="mobile-dock-btn" id="mobDockBtn_tab3" onclick="switchTab('tab3')">
            <span class="dock-ico">🧭</span>
            <span>Onboarding</span>
          </button>
          <button type="button" class="mobile-dock-btn" id="mobDockBtn_tab4" onclick="switchTab('tab4')">
            <span class="dock-ico">⭐</span>
            <span>Trafik</span>
          </button>
          <button type="button" class="mobile-dock-btn" id="mobDockBtn_tab5" onclick="switchTab('tab5')">
            <span class="dock-ico">🏛️</span>
            <span>Mimari</span>
          </button>
        </nav>
      </div>

      <script>
        var PLATFORM_SPLIT = {ps_json_str};
        var currentPlatform = 'all';
        var currentOnbAbCohort = 'all';

        function switchOnboardingAbCohort(cohortKey) {{
          if (cohortKey !== 'group_a' && cohortKey !== 'group_b') cohortKey = 'all';
          currentOnbAbCohort = cohortKey;
          var cBtns = ['all', 'group_a', 'group_b'];
          for (var i = 0; i < cBtns.length; i++) {{
            var b = document.getElementById('onbCohortBtn_' + cBtns[i]);
            if (b) {{
              if (cBtns[i] === cohortKey) b.classList.add('active');
              else b.classList.remove('active');
            }}
          }}
          switchPlatform(currentPlatform, true);
        }}

        document.addEventListener('click', function(ev) {{
          var t = ev.target && ev.target.closest ? ev.target.closest('.card-desc, .step-sub') : null;
          if (t) {{
            t.classList.toggle('desc-expanded');
          }}
        }});

        function toggleHeroFunnel() {{
          var card = document.getElementById('conversionBridgeCard');
          var btn = document.getElementById('btnToggleHeroFunnel');
          if (!card) return;
          card.classList.toggle('funnel-collapsed');
          var isCol = card.classList.contains('funnel-collapsed');
          if (btn) btn.textContent = isCol ? '🔽 Huniyi Genişlet' : '🔼 Huniyi Daralt';
          try {{ localStorage.setItem('mishil_dash_funnel_collapsed', isCol ? '1' : '0'); }} catch (_le) {{}}
        }}

        function toggleVerboseDescriptions() {{
          document.body.classList.toggle('show-verbose-desc');
          var isShown = document.body.classList.contains('show-verbose-desc');
          var btn = document.getElementById('btnToggleVerboseDesc');
          if (btn) btn.textContent = isShown ? '📖 Açıklamalar: Açık' : '📖 Açıklamalar';
          try {{ localStorage.setItem('mishil_dash_verbose_desc', isShown ? '1' : '0'); }} catch (_ve) {{}}
        }}
        if (localStorage.getItem('mishil_dash_verbose_desc') === '1') {{
          document.body.classList.add('show-verbose-desc');
        }}

        function jumpToOnboardingFunnel() {{
          switchTab('tab3');
          filterTab3Category('all');
          var el = document.getElementById('onboardingNineStepFunnelCard');
          if (el && el.scrollIntoView) {{
            setTimeout(function() {{
              try {{ el.scrollIntoView({{ behavior: 'smooth', block: 'start' }}); }} catch (_se) {{ el.scrollIntoView(); }}
            }}, 40);
          }}
        }}

        function jumpToAbExperiment() {{
          switchTab('tab2');
          filterTab2Category('all');
          var el = document.getElementById('abExperimentCommandCard');
          if (el && el.scrollIntoView) {{
            setTimeout(function() {{
              try {{ el.scrollIntoView({{ behavior: 'smooth', block: 'start' }}); }} catch (_se) {{ el.scrollIntoView(); }}
            }}, 40);
          }}
        }}

        function jumpToStarDistribution() {{
          switchTab('tab4');
          var el = document.getElementById('reviewsStarDistributionCard');
          if (el && el.scrollIntoView) {{
            setTimeout(function() {{
              try {{ el.scrollIntoView({{ behavior: 'smooth', block: 'start' }}); }} catch (_se) {{ el.scrollIntoView(); }}
            }}, 40);
          }}
        }}

        function jumpToInAppFeedbacks() {{
          switchTab('tab4');
          var el = document.getElementById('inAppFeedbacksCard');
          if (el && el.scrollIntoView) {{
            setTimeout(function() {{
              try {{ el.scrollIntoView({{ behavior: 'smooth', block: 'start' }}); }} catch (_se) {{ el.scrollIntoView(); }}
            }}, 40);
          }}
        }}

        function filterInAppFeedbacks(inputEl) {{
          var listEl = document.getElementById('inAppFeedbacksList');
          if (!listEl) return;
          var q = (inputEl && inputEl.value ? inputEl.value : '').toLocaleLowerCase('tr-TR').trim();
          var items = listEl.querySelectorAll('.in-app-feedback-item');
          for (var i = 0; i < items.length; i++) {{
            var itemPlat = items[i].getAttribute('data-platform') || 'all';
            var platOk = (currentPlatform === 'all' || itemPlat === 'all' || itemPlat === currentPlatform);
            var txt = (items[i].textContent || '').toLocaleLowerCase('tr-TR');
            var queryOk = (!q || txt.indexOf(q) > -1);
            items[i].style.display = (platOk && queryOk) ? '' : 'none';
          }}
        }}

        function filterTab1Category(cat) {{
          var pills = ['all', 'trend', 'donuts', 'channels'];
          for (var i = 0; i < pills.length; i++) {{
            var b = document.getElementById('subcatBtn_t1_' + pills[i]);
            if (b) {{
              if (pills[i] === cat) b.classList.add('active');
              else b.classList.remove('active');
            }}
          }}
          var secs = document.querySelectorAll('#tabPane_tab1 .tab1-sec');
          for (var j = 0; j < secs.length; j++) {{
            var el = secs[j];
            if (cat === 'all' || el.classList.contains('tab1-sec-' + cat)) {{
              el.style.display = '';
            }} else {{
              el.style.display = 'none';
            }}
          }}
        }}

        function filterTab3Category(cat) {{
          var pills = ['all', 'onboarding', 'paywall', 'cohort'];
          for (var i = 0; i < pills.length; i++) {{
            var b = document.getElementById('subcatBtn_t3_' + pills[i]);
            if (b) {{
              if (pills[i] === cat) b.classList.add('active');
              else b.classList.remove('active');
            }}
          }}
          var secs = document.querySelectorAll('#tabPane_tab3 .tab3-sec');
          for (var j = 0; j < secs.length; j++) {{
            var el = secs[j];
            if (cat === 'all' || el.classList.contains('tab3-sec-' + cat)) {{
              el.style.display = '';
            }} else {{
              el.style.display = 'none';
            }}
          }}
        }}

        function filterTableByQuery(inputEl, tbodyId) {{
          var tbody = document.getElementById(tbodyId);
          if (!tbody) return;
          var q = (inputEl && inputEl.value ? inputEl.value : '').toLocaleLowerCase('tr-TR').trim();
          var rows = tbody.querySelectorAll('tr');
          for (var i = 0; i < rows.length; i++) {{
            var rowPlat = rows[i].getAttribute('data-platform');
            var platOk = (!rowPlat || currentPlatform === 'all' || rowPlat === currentPlatform);
            var txt = (rows[i].textContent || '').toLocaleLowerCase('tr-TR');
            var queryOk = (!q || txt.indexOf(q) > -1);
            rows[i].style.display = (platOk && queryOk) ? '' : 'none';
          }}
        }}

        function reapplyAllTableFilters() {{
          filterTableByQuery(document.getElementById('countryRevenueSearchInput'), 'countryRevenueTableBody');
          filterTableByQuery(document.getElementById('appleLedgerSearchInput'), 'appleLedgerTbody');
          filterTableByQuery(document.getElementById('liveClicksSearchInput'), 'liveClicksTbody');
          filterInAppFeedbacks(document.getElementById('inAppFeedbacksSearchInput'));
        }}

        function toggleDetailWrap(wrapId, btnId) {{
          var wrap = document.getElementById(wrapId);
          var btn = document.getElementById(btnId);
          if (!wrap) return;
          var isHidden = (wrap.style.display === 'none' || wrap.style.display === '');
          wrap.style.display = isHidden ? 'block' : 'none';
          if (btn) {{
            var txt = btn.textContent || '';
            if (isHidden) {{
              btn.textContent = txt.replace('▼', '▲');
            }} else {{
              btn.textContent = txt.replace('▲', '▼');
            }}
          }}
        }}

        function toggleReviewReplyDrawer(domKey) {{
          var drawer = document.getElementById('replyDrawer_' + domKey);
          if (!drawer) return;
          var isHidden = (drawer.style.display === 'none' || drawer.style.display === '');
          drawer.style.display = isHidden ? 'block' : 'none';
        }}

        async function submitStoreReviewReply(reviewId, platform, domKey) {{
          var inputEl = document.getElementById('replyInput_' + domKey);
          var sendBtn = document.getElementById('btnSendReply_' + domKey);
          if (!inputEl || !reviewId) return;
          var bodyTxt = (inputEl.value || '').trim();
          if (bodyTxt.length < 3) {{
            alert('Lütfen en az 3 karakterlik bir geliştirici yanıtı girin.');
            return;
          }}
          var origTxt = sendBtn ? sendBtn.textContent : '🚀 Resmi API İle Gönder';
          if (sendBtn) {{
            sendBtn.disabled = true;
            sendBtn.textContent = '⏳ Gönderiliyor...';
          }}
          try {{
            var res = await fetch('/api/v1/analytics/review-reply', {{
              method: 'POST',
              headers: {{ 'Content-Type': 'application/json', 'Accept': 'application/json' }},
              credentials: 'same-origin',
              body: JSON.stringify({{
                review_id: reviewId,
                response_body: bodyTxt,
                platform: platform || 'ios'
              }})
            }});
            var data = await res.json();
            if (!res.ok) {{
              alert('Mağaza API hatası: ' + (data.detail || res.status));
              return;
            }}
            var boxEl = document.getElementById('devReplyBox_' + domKey);
            var txtEl = document.getElementById('devReplyText_' + domKey);
            var toggleBtn = document.getElementById('btnToggleReply_' + domKey);
            var drawerEl = document.getElementById('replyDrawer_' + domKey);
            if (txtEl) txtEl.textContent = data.response_body || bodyTxt;
            if (boxEl) boxEl.style.display = 'block';
            if (toggleBtn) toggleBtn.textContent = '✏️ Yanıtı Güncelle (API)';
            if (drawerEl) drawerEl.style.display = 'none';
          }} catch (err) {{
            alert('Bağlantı hatası: ' + err);
          }} finally {{
            if (sendBtn) {{
              sendBtn.disabled = false;
              sendBtn.textContent = origTxt;
            }}
          }}
        }}

        function prefillAndTriggerPulse(plat, authorName, revId, revTitle) {{
          var drawer = document.getElementById('pulseConfigDrawer');
          var platSel = document.getElementById('pulseTargetPlat');
          var titleIn = document.getElementById('pulseTitleInput');
          var qIn = document.getElementById('pulseQuestionInput');
          var authIn = document.getElementById('pulseRefAuthor');
          var revIn = document.getElementById('pulseRefReviewId');
          if (drawer) drawer.style.display = 'block';
          if (platSel) platSel.value = (plat === 'android' ? 'android' : 'ios');
          if (authIn) authIn.value = authorName || '';
          if (revIn) revIn.value = revId || '';
          if (titleIn) titleIn.value = 'Uyku ve uyanma saatleri kaydı iyileştirildi';
          if (qIn) qIn.value = 'Son güncellememizden sonra uyku kayıtlarınız sorunsuz çalışıyor mu?';
          var card = document.getElementById('satisfactionPulseCard');
          if (card && card.scrollIntoView) {{
            try {{ card.scrollIntoView({{ behavior: 'smooth', block: 'center' }}); }} catch (_se) {{ card.scrollIntoView(); }}
          }}
          submitSatisfactionPulseConfig(true);
        }}

        async function submitSatisfactionPulseConfig(isActive) {{
          var platSel = document.getElementById('pulseTargetPlat');
          var titleIn = document.getElementById('pulseTitleInput');
          var qIn = document.getElementById('pulseQuestionInput');
          var authIn = document.getElementById('pulseRefAuthor');
          var revIn = document.getElementById('pulseRefReviewId');
          var startBtn = document.getElementById('btnStartPulse');
          if (startBtn) startBtn.disabled = true;
          try {{
            var res = await fetch('/api/v1/analytics/satisfaction-pulse', {{
              method: 'POST',
              headers: {{ 'Content-Type': 'application/json', 'Accept': 'application/json' }},
              credentials: 'same-origin',
              body: JSON.stringify({{
                active: Boolean(isActive),
                target_platform: platSel ? platSel.value : 'ios',
                topic_key: 'sleep_save_fix',
                title_tr: titleIn ? titleIn.value : 'Uyku ve uyanma saatleri kaydı iyileştirildi',
                question_tr: qIn ? qIn.value : 'Son güncellememizden sonra uyku kayıtlarınız sorunsuz çalışıyor mu?',
                reference_author: authIn ? authIn.value : '',
                reference_review_id: revIn ? revIn.value : '',
                reset_counters: false
              }})
            }});
            var data = await res.json();
            if (res.ok && data.satisfaction_pulse) {{
              updateSatisfactionPulseDom(data.satisfaction_pulse);
            }}
          }} catch (_pe) {{
          }} finally {{
            if (startBtn) startBtn.disabled = false;
          }}
        }}

        function updateSatisfactionPulseDom(sp) {{
          if (!sp) return;
          var stBadge = document.getElementById('pulseStatusBadge');
          var shCnt = document.getElementById('pulseShownCnt');
          var satCnt = document.getElementById('pulseSatisfiedCnt');
          var issCnt = document.getElementById('pulseIssueCnt');
          var isAct = Boolean(sp.active);
          if (stBadge) {{
            stBadge.textContent = isAct ? ('🟢 Aktif (' + String(sp.target_platform || 'ios').toUpperCase() + ')') : '⚪ Pasif';
            stBadge.style.background = isAct ? 'rgba(16,185,129,0.16)' : 'rgba(148,163,184,0.15)';
            stBadge.style.color = isAct ? '#059669' : 'var(--text-muted)';
          }}
          if (shCnt) shCnt.textContent = String(Number(sp.shown_count || 0));
          if (satCnt) satCnt.textContent = String(Number(sp.satisfied_count || 0));
          if (issCnt) issCnt.textContent = String(Number(sp.issue_persists_count || 0));
        }}

        function updatePlatformStarDistDom(platKey, sd) {{
          if (!sd) return;
          var ovNodes = document.querySelectorAll('.js-star-overall-' + platKey);
          var wrNodes = document.querySelectorAll('.js-star-written-' + platKey);
          var silNodes = document.querySelectorAll('.js-star-silent-' + platKey);
          var ovTxt = 'Mağaza: ' + (sd.overall_avg_str || 'Yorum Yok') + ' (' + Number(sd.overall_count || 0) + ')';
          var wrTxt = 'Yazılı: ' + (sd.written_avg_str || 'Yorum Yok') + ' (' + Number(sd.written_count || 0) + ')';
          for (var i = 0; i < ovNodes.length; i++) ovNodes[i].textContent = ovTxt;
          for (var j = 0; j < wrNodes.length; j++) wrNodes[j].textContent = wrTxt;
          var silCnt = Number(sd.silent_ratings_count || 0);
          for (var k = 0; k < silNodes.length; k++) {{
            if (silCnt > 0) {{
              silNodes[k].textContent = '+' + silCnt + ' Yorumsuz Oy';
              silNodes[k].style.display = '';
            }} else {{
              silNodes[k].style.display = 'none';
            }}
          }}
          if (Array.isArray(sd.bars)) {{
            for (var bi = 0; bi < sd.bars.length; bi++) {{
              var b = sd.bars[bi];
              var sLvl = Number(b.star || 5);
              var totC = Number(b.count || 0);
              var wrC = Number(b.written_count !== undefined ? b.written_count : totC);
              var silC = Number(b.silent_count || 0);
              var cntLbl = (silC > 0) ? (totC + ' (' + wrC + '+' + silC + ')') : String(totC);
              var fillNodes = document.querySelectorAll('.js-star-fill-' + platKey + '-' + sLvl);
              var cntNodes = document.querySelectorAll('.js-star-cnt-' + platKey + '-' + sLvl);
              var pctNodes = document.querySelectorAll('.js-star-pct-' + platKey + '-' + sLvl);
              for (var fIdx = 0; fIdx < fillNodes.length; fIdx++) fillNodes[fIdx].style.width = Number(b.pct || 0) + '%';
              for (var cIdx = 0; cIdx < cntNodes.length; cIdx++) cntNodes[cIdx].textContent = cntLbl;
              for (var pIdx = 0; pIdx < pctNodes.length; pIdx++) pctNodes[pIdx].textContent = '%' + Number(b.pct || 0);
            }}
          }}
        }}

        function filterTab2Category(cat) {{
          var pills = ['all', 'ab', 'country', 'reconcile', 'calendar', 'ledger'];
          for (var i = 0; i < pills.length; i++) {{
            var b = document.getElementById('subcatBtn_' + pills[i]);
            if (b) {{
              if (pills[i] === cat) b.classList.add('active');
              else b.classList.remove('active');
            }}
          }}
          var secs = document.querySelectorAll('#tabPane_tab2 .tab2-sec');
          for (var j = 0; j < secs.length; j++) {{
            var el = secs[j];
            if (cat === 'all') {{
              el.style.display = 'block';
            }} else if (el.classList.contains('tab2-sec-' + cat)) {{
              el.style.display = 'block';
            }} else {{
              el.style.display = 'none';
            }}
          }}
          if (cat === 'ledger') {{
            var w1 = document.getElementById('appleLedgerTableWrap');
            var w2 = document.getElementById('gpLedgerTableWrap');
            if (w1) w1.style.display = 'block';
            if (w2) w2.style.display = 'block';
          }}
        }}

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
          var mobBtns = document.querySelectorAll('.mobile-dock-btn');
          for (var i = 0; i < panes.length; i++) {{
            panes[i].classList.remove('active');
          }}
          for (var j = 0; j < btns.length; j++) {{
            btns[j].classList.remove('active');
          }}
          for (var k = 0; k < mobBtns.length; k++) {{
            mobBtns[k].classList.remove('active');
          }}
          var targetPane = document.getElementById('tabPane_' + tabId);
          var targetBtn = document.getElementById('tabBtn_' + tabId);
          var targetMobBtn = document.getElementById('mobDockBtn_' + tabId);
          if (targetPane && targetBtn) {{
            targetPane.classList.add('active');
            targetBtn.classList.add('active');
            if (targetMobBtn) targetMobBtn.classList.add('active');
            localStorage.setItem('mishil_dash_active_tab', tabId);
          }}
          var heroCard = document.getElementById('conversionBridgeCard');
          var heroBtn = document.getElementById('btnToggleHeroFunnel');
          if (heroCard) {{
            var userForcedCol = (localStorage.getItem('mishil_dash_funnel_collapsed') === '1');
            var shouldCollapse = (tabId !== 'tab1') || userForcedCol;
            if (shouldCollapse) {{
              heroCard.classList.add('funnel-collapsed');
              if (heroBtn) heroBtn.textContent = '🔽 Huniyi Genişlet';
            }} else {{
              heroCard.classList.remove('funnel-collapsed');
              if (heroBtn) heroBtn.textContent = '🔼 Huniyi Daralt';
            }}
          }}
        }}

        function scrollTimelineToLatest() {{
          var ts = document.getElementById('timelineScrollWrap');
          if (!ts) return;
          setTimeout(function() {{
            ts.scrollLeft = ts.scrollWidth;
          }}, 20);
        }}

        function scrollTimelineBy(dx) {{
          var ts = document.getElementById('timelineScrollWrap');
          if (!ts) return;
          try {{
            ts.scrollBy({{ left: dx, behavior: 'smooth' }});
          }} catch (_se) {{
            ts.scrollLeft += dx;
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
          scrollTimelineToLatest();
        }}

        function escapeHtmlJs(str) {{
          return String(str || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
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
          var elStartedVip = document.getElementById('kpiStartedVip');
          var elCancelledVip = document.getElementById('kpiCancelledVip');
          var elVip = document.getElementById('kpiVip');
          if (elImp) elImp.textContent = p.impressions_display;
          if (elVis) elVis.textContent = p.touchpoints_display;
          if (elDl) elDl.textContent = p.downloads_display;
          var startedVipNum = (p.total_vip_count !== undefined) ? p.total_vip_count : 0;
          var cancelledVipNum = (p.cancelled_vip_count !== undefined) ? p.cancelled_vip_count : 0;
          var vipNum = (p.vip_count !== undefined) ? p.vip_count : ((p.vip !== undefined) ? p.vip : String(p.vip_display || '').replace(' Net Abone', '').replace(' Aktif VIP', '').replace(' VIP', ''));
          if (elStartedVip) elStartedVip.textContent = String(startedVipNum);
          if (elCancelledVip) elCancelledVip.textContent = String(cancelledVipNum);
          if (elVip) {{
            elVip.textContent = String(vipNum);
          }}

          var sDl = document.getElementById('sideKpiDl');
          var sVip = document.getElementById('sideKpiVip');
          var sMrr = document.getElementById('sideKpiMrr');
          var mobMrr = document.getElementById('mobileHeaderMrrBadge');
          if (sDl) sDl.textContent = p.downloads_display;
          if (sVip) sVip.textContent = String(vipNum);
          if (sMrr) sMrr.textContent = Number(p.mrr_net_try || 0).toFixed(2) + ' ₺';
          if (mobMrr) mobMrr.textContent = '👑 ' + String(vipNum) + ' VIP • ' + Number(p.mrr_net_try || 0).toFixed(0) + ' ₺';

          function renderMetaChips(containerId, chipsArr) {{
            var cEl = document.getElementById(containerId);
            if (!cEl || !Array.isArray(chipsArr)) return;
            var htmlStr = '';
            for (var ci = 0; ci < chipsArr.length; ci++) {{
              htmlStr += '<span class="kpi-micro-chip">' + escapeHtmlJs(chipsArr[ci]) + '</span>';
            }}
            cEl.innerHTML = htmlStr;
          }}
          renderMetaChips('kpiMeta1', p.meta_chips_1);
          renderMetaChips('kpiMeta2', p.meta_chips_2);
          renderMetaChips('kpiMeta3', p.meta_chips_3);
          renderMetaChips('kpiMeta4', p.meta_chips_4);
          renderMetaChips('kpiMeta5', p.meta_chips_5);
          renderMetaChips('kpiMeta6', p.meta_chips_6);

          var d1 = document.getElementById('kpiDesc1');
          var d2 = document.getElementById('kpiDesc2');
          var d3 = document.getElementById('kpiDesc3');
          var d4 = document.getElementById('kpiDesc4');
          var d5 = document.getElementById('kpiDesc5');
          var d6 = document.getElementById('kpiDesc6');
          var dl1 = document.getElementById('kpiDelta1');
          var dl2 = document.getElementById('kpiDelta2');
          var dl3 = document.getElementById('kpiDelta3');
          var dl4 = document.getElementById('kpiDelta4');
          var dl5 = document.getElementById('kpiDelta5');
          var dl6 = document.getElementById('kpiDelta6');
          var visOfImp = (p.vis_of_imp_pct !== undefined) ? p.vis_of_imp_pct : 0;
          var dlOfVis = (p.cvr_pct !== undefined) ? p.cvr_pct : 0;
          var dlOfImp = (p.dl_of_imp_pct !== undefined) ? p.dl_of_imp_pct : 0;
          var startedVipOfDl = (p.started_vip_of_dl_pct !== undefined) ? p.started_vip_of_dl_pct : 0;
          var vipOfDl = (p.vip_of_dl_pct !== undefined) ? p.vip_of_dl_pct : 0;
          var vipOfVis = (p.vip_of_vis_pct !== undefined) ? p.vip_of_vis_pct : 0;
          var vipOfImp = (p.vip_of_imp_pct !== undefined) ? p.vip_of_imp_pct : 0;
          var churnPct = (p.churn_rate_pct !== undefined) ? p.churn_rate_pct : 0;
          var retPct = (p.retention_rate_pct !== undefined) ? p.retention_rate_pct : 0;

          if (dl1 && p.delta_1) dl1.textContent = p.delta_1;
          if (dl2 && p.delta_2) dl2.textContent = p.delta_2;
          if (dl3) dl3.textContent = 'CVR %' + dlOfVis;
          if (dl4) dl4.textContent = '%' + startedVipOfDl + ' Kurulumdan';
          if (dl5) dl5.textContent = '%' + churnPct + ' Churn';
          if (dl6) dl6.textContent = Number(p.mrr_net_try || 0).toFixed(2) + ' ₺/Ay Net';

          if (d1) d1.textContent = p.impressions_sub;
          if (d2) d2.textContent = p.touchpoints_sub;
          if (d3) d3.textContent = p.downloads_sub;
          if (d4) d4.textContent = p.started_vip_sub || p.vip_sub;
          if (d5) d5.textContent = p.cancelled_vip_sub || '';
          var dynRatingStr = p.avg_rating_str || 'Yorum Yok';
          if (d6) d6.textContent = p.vip_sub + ' • ' + dynRatingStr + ' (' + p.reviews_count + ' Yorum)';

          var csVipImp = document.getElementById('convSumVipImp');
          if (csVipImp) csVipImp.textContent = '%' + vipOfImp;

          var cb1 = document.getElementById('convBridge1');
          var cb1Sub = document.getElementById('convBridge1Sub');
          var cb2 = document.getElementById('convBridge2');
          var cb2Sub = document.getElementById('convBridge2Sub');
          var cb3 = document.getElementById('convBridge3');
          var cb3Net = document.getElementById('convBridge3Net');
          var cb4 = document.getElementById('convBridge4');
          var cb5 = document.getElementById('convBridge5');
          var csStorePill = document.getElementById('convStoreCvrPill');
          var csStartedPill = document.getElementById('convStartedVipDlPill');
          var csChurnPill = document.getElementById('convChurnPill');
          var csRetPill = document.getElementById('convRetentionPill');
          if (cb1) cb1.textContent = '%' + visOfImp + ' ➔';
          if (cb1Sub && p.imp_breakdown_label) cb1Sub.textContent = p.imp_breakdown_label;
          if (cb2) cb2.textContent = '%' + dlOfVis + ' ➔';
          if (cb2Sub && p.cvr_breakdown_label) cb2Sub.textContent = p.cvr_breakdown_label;
          if (cb3) cb3.textContent = '%' + startedVipOfDl + ' ➔';
          if (cb3Net) cb3Net.textContent = '%' + vipOfDl;
          if (cb4) cb4.textContent = '-%' + churnPct + ' ➔';
          if (cb5) cb5.textContent = '%' + retPct + ' ➔';
          if (csStorePill && p.store_cvr_pct !== undefined) csStorePill.textContent = '%' + p.store_cvr_pct;
          if (csStartedPill) csStartedPill.textContent = '%' + startedVipOfDl;
          if (csChurnPill) csChurnPill.textContent = '%' + churnPct;
          if (csRetPill) csRetPill.textContent = '%' + retPct;

          var cc4 = document.getElementById('convCum4');
          if (cc4) cc4.textContent = '%' + vipOfVis;

          if (!skipChartSync) {{
            if (plat === 'ios') switchChartMode('ios');
            else if (plat === 'android') switchChartMode('android');
            else switchChartMode('cum');
          }}

          var appRen = document.getElementById('appleRenewalCard');
          var appLed = document.getElementById('appleLedgerCard');
          var gpLed = document.getElementById('googlePlayLedgerCard');
          var ledHead = document.getElementById('ledgerHeadSpan');
          if (appRen) appRen.style.display = 'block';
          if (appLed) appLed.style.display = 'block';
          if (gpLed) gpLed.style.display = (plat === 'ios') ? 'none' : 'block';
          if (ledHead && p) {{
            var cCnt = (p.cancelled_vip_count !== undefined) ? p.cancelled_vip_count : 0;
            var chPct = (p.churn_rate_pct !== undefined) ? p.churn_rate_pct : 0;
            ledHead.textContent = '📒 Abone Defteri (' + (p.vip_count !== undefined ? p.vip_count : 0) + ' Aktif • ' + cCnt + ' İptal / %' + chPct + ' Churn • Toplam ' + (p.total_vip_count !== undefined ? p.total_vip_count : 0) + ' Kayıt)';
          }}

          if (p && p.onboarding_step_funnel) {{
            var rootOfData = p.onboarding_step_funnel;
            var abCohortsMap = rootOfData.ab_cohorts || {{}};
            var ofData = (currentOnbAbCohort !== 'all' && abCohortsMap[currentOnbAbCohort]) ? abCohortsMap[currentOnbAbCohort] : rootOfData;
            var allCohortObj = abCohortsMap.all || rootOfData;
            var gaCohortObj = abCohortsMap.group_a || {{}};
            var gbCohortObj = abCohortsMap.group_b || {{}};
            var btnAllC = document.getElementById('onbCohortBtn_all');
            var btnGaC = document.getElementById('onbCohortBtn_group_a');
            var btnGbC = document.getElementById('onbCohortBtn_group_b');
            var rootPA = Number(allCohortObj.ab_a_purchases_count !== undefined ? allCohortObj.ab_a_purchases_count : (allCohortObj.ab_a_vip_started_unique_devices || 0));
            var rootPB = Number(allCohortObj.ab_b_purchases_count !== undefined ? allCohortObj.ab_b_purchases_count : (allCohortObj.ab_b_vip_started_unique_devices || 0));
            if (btnAllC) btnAllC.textContent = '🌐 Kümülatif (' + Number(allCohortObj.total_tracked_onboarding_devices || 0) + ' Cihaz)';
            if (btnGaC) btnGaC.textContent = '🔥 A Grubu: İlk Ay ₺49,99 (' + Number(gaCohortObj.total_tracked_onboarding_devices || 0) + ' Cihaz • 💳 ' + rootPA + ')';
            if (btnGbC) btnGbC.textContent = '🎁 B Grubu: 30G Ücretsiz (' + Number(gbCohortObj.total_tracked_onboarding_devices || 0) + ' Cihaz • 💳 ' + rootPB + ')';
            var devBadge = document.getElementById('onbFunnelDevicesBadge');
            var compBadge = document.getElementById('onbFunnelCompletionBadge');
            var purchBadge = document.getElementById('onbFunnelPurchasesBadge');
            var dropBadge = document.getElementById('onbFunnelDropoffBadge');
            var contMeta = document.getElementById('onbFunnelContinuationMeta');
            var onbTbody = document.getElementById('onboardingNineStepTbody');
            var sideOnb = document.getElementById('sideKpiOnb');
            var heroOnbPill = document.getElementById('convOnbCompPill');
            var totOnbDevs = Number(ofData.total_tracked_onboarding_devices || 0);
            var stBaseDevs = Number(ofData.start_base_devices || 0);
            var st9Devs = Number(ofData.step9_reached_devices || 0);
            var compStr = (ofData.step0_to_step9_completion_pct !== null && ofData.step0_to_step9_completion_pct !== undefined)
              ? ('%' + ofData.step0_to_step9_completion_pct)
              : 'Veri Yok';
            var pA = Number(ofData.ab_a_purchases_count !== undefined ? ofData.ab_a_purchases_count : (ofData.ab_a_vip_started_unique_devices || 0));
            var pB = Number(ofData.ab_b_purchases_count !== undefined ? ofData.ab_b_purchases_count : (ofData.ab_b_vip_started_unique_devices || 0));
            var pAnn = Number(ofData.annual_purchases_count || 0);
            var pLeg = Number(ofData.legacy_or_code_purchases_count || 0);
            var pTot = Number(ofData.total_purchases_count !== undefined ? ofData.total_purchases_count : (ofData.vip_started_unique_devices || 0));
            var pIos = Number(ofData.ios_purchases_count || 0);
            var pAnd = Number(ofData.android_purchases_count || 0);
            var pIosA = Number(ofData.ios_ab_a_purchases_count || 0);
            var pIosB = Number(ofData.ios_ab_b_purchases_count || 0);
            var pAndA = Number(ofData.android_ab_a_purchases_count || 0);
            var pAndB = Number(ofData.android_ab_b_purchases_count || 0);
            var pAnnSuffix = (pAnn > 0) ? (' • 👑Yıllık: ' + pAnn) : '';
            var cohortBadgePrefix = (currentOnbAbCohort === 'group_a') ? '🔥 A Grubu: ' : ((currentOnbAbCohort === 'group_b') ? '🎁 B Grubu: ' : '📱 ');
            if (devBadge) devBadge.textContent = cohortBadgePrefix + totOnbDevs + ' Cihaz';
            if (compBadge) compBadge.textContent = '🏁 0➔9: ' + compStr;
            if (purchBadge) {{
              if (currentOnbAbCohort === 'group_a') purchBadge.textContent = '💳 🔥 Grup A Satın Alma: ' + pA;
              else if (currentOnbAbCohort === 'group_b') purchBadge.textContent = '💳 🎁 Grup B Satın Alma: ' + pB;
              else purchBadge.textContent = '💳 Satın Alma: ' + pTot + ' (🔥A: ' + pA + ' • 🎁B: ' + pB + pAnnSuffix + ')';
            }}
            if (sideOnb) sideOnb.textContent = compStr + ' (' + st9Devs + '/' + stBaseDevs + ')';
            if (heroOnbPill) heroOnbPill.textContent = compStr + ' (' + st9Devs + '/' + stBaseDevs + ') ➔';
            if (dropBadge) {{
              var bd = ofData.biggest_dropoff_step;
              if (bd && Number(bd.dropoff_count || 0) > 0) {{
                dropBadge.textContent = '⚠️ ' + bd.title + ' (-' + bd.dropoff_count + ' / -%' + bd.dropoff_pct + ')';
              }} else {{
                dropBadge.textContent = totOnbDevs > 0 ? '🟢 Kayıp Yok' : '⏳ Bekleniyor';
              }}
            }}
            if (contMeta) {{
              if (currentOnbAbCohort === 'group_a') {{
                contMeta.innerHTML =
                  '<span class="kpi-micro-chip">🚀 Açılış: ' + Number(ofData.first_open_unique_devices || 0) + '</span>' +
                  '<span class="kpi-micro-chip">⚡ 7. Kart Hızlı Çip: ' + Number(ofData.step7_quick_chip_unique_devices || 0) + '</span>' +
                  '<span class="kpi-micro-chip">👁️ 🔥A Paywall: ' + Number(ofData.ab_a_paywall_viewed_unique_devices || ofData.paywall_viewed_unique_devices || 0) + '</span>' +
                  '<span class="kpi-micro-chip">👆 🔥A Tık: ' + Number(ofData.ab_a_paywall_cta_unique_devices || ofData.paywall_cta_unique_devices || 0) + '</span>';
              }} else if (currentOnbAbCohort === 'group_b') {{
                contMeta.innerHTML =
                  '<span class="kpi-micro-chip">🚀 Açılış: ' + Number(ofData.first_open_unique_devices || 0) + '</span>' +
                  '<span class="kpi-micro-chip">⚡ 7. Kart Hızlı Çip: ' + Number(ofData.step7_quick_chip_unique_devices || 0) + '</span>' +
                  '<span class="kpi-micro-chip">👁️ 🎁B Paywall: ' + Number(ofData.ab_b_paywall_viewed_unique_devices || ofData.paywall_viewed_unique_devices || 0) + '</span>' +
                  '<span class="kpi-micro-chip">👆 🎁B Tık: ' + Number(ofData.ab_b_paywall_cta_unique_devices || ofData.paywall_cta_unique_devices || 0) + '</span>';
              }} else {{
                contMeta.innerHTML =
                  '<span class="kpi-micro-chip">🚀 Açılış: ' + Number(ofData.first_open_unique_devices || 0) + '</span>' +
                  '<span class="kpi-micro-chip">⚡ 7. Kart Hızlı Çip: ' + Number(ofData.step7_quick_chip_unique_devices || 0) + '</span>' +
                  '<span class="kpi-micro-chip">👁️ Paywall: ' + Number(ofData.paywall_viewed_unique_devices || 0) + ' (🔥A:' + Number(ofData.ab_a_paywall_viewed_unique_devices || 0) + ' • 🎁B:' + Number(ofData.ab_b_paywall_viewed_unique_devices || 0) + ')</span>' +
                  '<span class="kpi-micro-chip">👆 Tık: ' + Number(ofData.paywall_cta_unique_devices || 0) + ' (🔥A:' + Number(ofData.ab_a_paywall_cta_unique_devices || 0) + ' • 🎁B:' + Number(ofData.ab_b_paywall_cta_unique_devices || 0) + ')</span>';
              }}
            }}
            if (onbTbody && Array.isArray(ofData.steps)) {{
              var rowsHtml = '';
              for (var si = 0; si < ofData.steps.length; si++) {{
                var st = ofData.steps[si];
                var sNum = Number(st.step_number || 0);
                var sUniq = Number(st.unique_devices || 0);
                var sRaw = Number(st.raw_events || 0);
                var sIos = Number(st.ios_unique_devices || 0);
                var sAnd = Number(st.android_unique_devices || 0);
                var sGa = Number(st.group_a_unique_devices || 0);
                var sGb = Number(st.group_b_unique_devices || 0);
                var sAbChip = (currentOnbAbCohort === 'all' && (sGa > 0 || sGb > 0))
                  ? ' <span style="font-size:11px; color:var(--text-muted); font-weight:700;">(🔥A:' + sGa + ' • 🎁B:' + sGb + ')</span>'
                  : '';
                var sRet = st.retention_from_prev_pct;
                var sDropCnt = Number(st.dropoff_from_prev_count || 0);
                var sDropPct = st.dropoff_from_prev_pct;
                var sCum = st.cumulative_from_start_pct;
                var retHtml = '';
                var dropHtml = '';
                if (sNum === 0) {{
                  retHtml = sUniq > 0
                    ? '<span class="badge" style="background:rgba(37,99,235,0.12); color:#2563EB;">🏁 %100</span>'
                    : '<span style="color:var(--text-muted); font-size:12px;">—</span>';
                  dropHtml = '<span style="color:var(--text-muted); font-size:12px;">—</span>';
                }} else {{
                  if (sRet !== null && sRet !== undefined) {{
                    var rCol = sRet >= 80 ? '#059669' : (sRet >= 50 ? '#D97706' : '#DC2626');
                    retHtml = '<strong style="color:' + rCol + ';">%' + sRet + '</strong>';
                  }} else {{
                    retHtml = '<span style="color:var(--text-muted); font-size:12px;">—</span>';
                  }}
                  if (sDropPct !== null && sDropPct !== undefined && sDropCnt > 0) {{
                    dropHtml = '<span style="color:#DC2626; font-weight:700;">-' + sDropCnt + ' (-%' + sDropPct + ')</span>';
                  }} else if (sDropPct !== null && sDropPct !== undefined) {{
                    dropHtml = '<span style="color:#059669; font-weight:700;">0</span>';
                  }} else {{
                    dropHtml = '<span style="color:var(--text-muted); font-size:12px;">—</span>';
                  }}
                }}
                var bW = Math.max(0, Math.min(100, Number(sCum || 0)));
                var cLbl = (sCum !== null && sCum !== undefined) ? ('%' + sCum) : '—';
                var bCol = (sNum === 9) ? '#7C3AED' : (bW >= 65 ? '#059669' : (bW >= 35 ? '#2563EB' : '#D97706'));
                rowsHtml += '<tr>' +
                  '<td style="font-weight:800; color:var(--text-primary); white-space:nowrap;">' + escapeHtmlJs(st.title) + '<span class="sr-only"> ' + escapeHtmlJs(st.subtitle) + '</span></td>' +
                  '<td style="font-weight:800; color:var(--text-primary); font-variant-numeric:tabular-nums; white-space:nowrap;">' + sUniq + sAbChip + '<span class="sr-only"> Cihaz (' + sRaw + ' sinyal)</span></td>' +
                  '<td style="font-size:12px; white-space:nowrap;">🍏 <strong>' + sIos + '</strong> • 🤖 <strong>' + sAnd + '</strong></td>' +
                  '<td style="font-variant-numeric:tabular-nums;">' + retHtml + '</td>' +
                  '<td style="font-variant-numeric:tabular-nums;">' + dropHtml + '</td>' +
                  '<td style="min-width:150px;"><div style="display:flex; align-items:center; gap:8px;"><div style="flex:1; height:8px; background:rgba(148,163,184,0.18); border-radius:999px; overflow:hidden;"><div style="width:' + bW + '%; height:100%; background:' + bCol + '; border-radius:999px;"></div></div><span style="font-size:12px; font-weight:700; color:var(--text-secondary); min-width:48px; text-align:right;">' + cLbl + '</span></div></td>' +
                  '</tr>';
              }}
              var pRetPct = ofData.step9_to_purchase_cvr_pct;
              var pDropCnt = Number(ofData.step9_to_purchase_dropoff_count || 0);
              var pDropPct = ofData.step9_to_purchase_dropoff_pct;
              var pCumPct = ofData.step0_to_purchase_cvr_pct;
              var pRetHtml = (pRetPct !== null && pRetPct !== undefined)
                ? '<strong style="color:#059669;">%' + pRetPct + '</strong>'
                : '<span style="color:var(--text-muted); font-size:12px;">—</span>';
              var pDropHtml = '<span style="color:var(--text-muted); font-size:12px;">—</span>';
              if (pDropPct !== null && pDropPct !== undefined && pDropCnt > 0) {{
                pDropHtml = '<span style="color:#DC2626; font-weight:700;">-' + pDropCnt + ' (-%' + pDropPct + ')</span>';
              }} else if (pDropPct !== null && pDropPct !== undefined) {{
                pDropHtml = '<span style="color:#059669; font-weight:700;">0</span>';
              }}
              var pBarW = Math.max(0, Math.min(100, Number(pCumPct || 0)));
              var pCumLbl = (pCumPct !== null && pCumPct !== undefined) ? ('%' + pCumPct) : '—';
              var pAnnChip = (pAnn > 0)
                ? ' <span class="badge" style="background:rgba(124,58,237,0.14); color:#7C3AED; font-size:10.5px; padding:2px 6px;">👑 Yıllık: ' + pAnn + '</span>'
                : '';
              var pLegChip = (pLeg > 0)
                ? ' <span class="badge badge-meta" style="font-size:10.5px; padding:2px 6px;">⏳/🎟️ Diğer: ' + pLeg + '</span>'
                : '';
              var pRowTitleHtml = '';
              var pRowCountHtml = '';
              var pRowPlatHtml = '';
              if (currentOnbAbCohort === 'group_a') {{
                pRowTitleHtml = '💳 🔥 A Grubu Satın Alma / VIP Başlatma <span class="badge" style="background:rgba(217,119,6,0.16); color:#D97706; font-size:10.5px; padding:2px 7px; margin-left:4px;">🔥 Grup A: ' + pA + '</span>';
                pRowCountHtml = pA + ' <span style="font-size:11.5px; color:#D97706; font-weight:700;">(🔥 İlk Ay ₺49,99)</span>';
                pRowPlatHtml = '🍏 <strong>' + pIosA + '</strong> • 🤖 <strong>' + pAndA + '</strong>';
              }} else if (currentOnbAbCohort === 'group_b') {{
                pRowTitleHtml = '💳 🎁 B Grubu Satın Alma / VIP Başlatma <span class="badge" style="background:rgba(16,185,129,0.16); color:#059669; font-size:10.5px; padding:2px 7px; margin-left:4px;">🎁 Grup B: ' + pB + '</span>';
                pRowCountHtml = pB + ' <span style="font-size:11.5px; color:#059669; font-weight:700;">(🎁 30G Ücretsiz)</span>';
                pRowPlatHtml = '🍏 <strong>' + pIosB + '</strong> • 🤖 <strong>' + pAndB + '</strong>';
              }} else {{
                pRowTitleHtml = '💳 Satın Alma / VIP Başlatma <span class="badge" style="background:rgba(217,119,6,0.16); color:#D97706; font-size:10.5px; padding:2px 7px; margin-left:4px;">🔥 Grup A: ' + pA + '</span> <span class="badge" style="background:rgba(16,185,129,0.16); color:#059669; font-size:10.5px; padding:2px 7px; margin-left:2px;">🎁 Grup B: ' + pB + '</span>' + pAnnChip + pLegChip;
                pRowCountHtml = pTot + ' <span style="font-size:11.5px; color:var(--text-secondary); font-weight:700;">(🔥A:' + pA + ' • 🎁B:' + pB + ')</span>';
                pRowPlatHtml = '🍏 <strong>' + pIos + '</strong> <span style="font-size:11px; color:var(--text-muted);">(A:' + pIosA + '/B:' + pIosB + ')</span> • 🤖 <strong>' + pAnd + '</strong> <span style="font-size:11px; color:var(--text-muted);">(A:' + pAndA + '/B:' + pAndB + ')</span>';
              }}
              rowsHtml += '<tr class="onb-purchase-summary-row" id="onbPurchaseSummaryRow" style="background:rgba(16,185,129,0.08); border-top:2px solid rgba(16,185,129,0.32);">' +
                '<td style="font-weight:800; color:#059669; white-space:nowrap;">' + pRowTitleHtml + '</td>' +
                '<td style="font-weight:800; color:#059669; font-variant-numeric:tabular-nums; white-space:nowrap;">' + pRowCountHtml + '</td>' +
                '<td style="font-size:12px; white-space:nowrap;">' + pRowPlatHtml + '</td>' +
                '<td style="font-variant-numeric:tabular-nums;">' + pRetHtml + '</td>' +
                '<td style="font-variant-numeric:tabular-nums;">' + pDropHtml + '</td>' +
                '<td style="min-width:150px;"><div style="display:flex; align-items:center; gap:8px;"><div style="flex:1; height:8px; background:rgba(148,163,184,0.18); border-radius:999px; overflow:hidden;"><div style="width:' + pBarW + '%; height:100%; background:#059669; border-radius:999px;"></div></div><span style="font-size:12px; font-weight:800; color:#059669; min-width:48px; text-align:right;">' + pCumLbl + '</span></div></td>' +
                '</tr>';
              onbTbody.innerHTML = rowsHtml;
            }}
          }}

          if (p && p.ab_experiment) {{
            var ab = p.ab_experiment;
            var gA = ab.group_a || {{}};
            var gB = ab.group_b || {{}};
            var gAnn = ab.annual_anchor || {{}};
            var gCode = ab.offer_code_vip || {{}};
            var gLeg = ab.legacy_7d_trial || {{}};
            var aAct = Number(gA.active_vip_count || 0);
            var bAct = Number(gB.active_vip_count || 0);
            var annAct = Number(gAnn.active_vip_count || 0);
            var sideAb = document.getElementById('sideKpiAbTest');
            var convAb = document.getElementById('convAbTestPill');
            var winB = document.getElementById('abWinnerBadge');
            var topSp = document.getElementById('abTopSplitBadge');
            var winDiag = document.getElementById('abWinnerDiagnosisText');
            var aVal = document.getElementById('abGroupAActiveVal');
            var bVal = document.getElementById('abGroupBActiveVal');
            var annVal = document.getElementById('abAnnualActiveVal');
            if (sideAb) sideAb.textContent = '🔥A:' + aAct + ' • 🎁B:' + bAct;
            if (convAb) convAb.textContent = '🔥A:' + aAct + ' vs 🎁B:' + bAct + ' (👑' + annAct + ') ➔';
            if (winB && ab.winner_badge) winB.textContent = ab.winner_badge;
            if (topSp) topSp.textContent = '🔥 Grup A: ' + aAct + ' • 🎁 Grup B: ' + bAct + ' • 👑 Yıllık: ' + annAct;
            if (winDiag && ab.winner_diagnosis_tr) winDiag.textContent = ab.winner_diagnosis_tr;
            if (aVal) aVal.innerHTML = aAct + ' Aktif VIP <span style="font-size:13px; color:var(--text-muted);">(' + Number(gA.started_vip_count || 0) + ' Başlayan)</span>';
            if (bVal) bVal.innerHTML = bAct + ' Aktif VIP <span style="font-size:13px; color:var(--text-muted);">(' + Number(gB.started_vip_count || 0) + ' Başlayan)</span>';
            if (annVal) annVal.innerHTML = annAct + ' Yıllık VIP <span style="font-size:13px; color:var(--text-muted);">(' + Number(gAnn.started_vip_count || 0) + ' Başlayan)</span>';
          }}

          if (p && p.star_distribution) {{
            var topAvg = document.getElementById('reviewsTopAvgBadge');
            var sideStars = document.getElementById('sideKpiStars');
            var convStars = document.getElementById('convStarsPill');
            var sdP = p.star_distribution;
            if (topAvg) {{
              topAvg.textContent = (sdP.overall_count > 0)
                ? (sdP.overall_avg_str + ' (' + sdP.overall_count + ' Oy • ' + sdP.written_count + ' Yorum)')
                : 'Yorum Yok';
            }}
            var shortStarTxt = (sdP.overall_count > 0)
              ? (sdP.overall_avg_str + ' (' + sdP.overall_count + ' Oy)')
              : 'Yorum Yok';
            if (sideStars) sideStars.textContent = shortStarTxt;
            if (convStars) convStars.textContent = shortStarTxt + ' ➔';
          }}
          if (PLATFORM_SPLIT && PLATFORM_SPLIT.ios && PLATFORM_SPLIT.ios.star_distribution) {{
            updatePlatformStarDistDom('ios', PLATFORM_SPLIT.ios.star_distribution);
          }}
          if (PLATFORM_SPLIT && PLATFORM_SPLIT.android && PLATFORM_SPLIT.android.star_distribution) {{
            updatePlatformStarDistDom('android', PLATFORM_SPLIT.android.star_distribution);
          }}

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

          reapplyAllTableFilters();
          try {{ localStorage.setItem('mishil_dash_platform', plat); }} catch (_pe) {{}}
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
          if (window.location.hash === '#inAppFeedbacksCard') {{
            jumpToInAppFeedbacks();
          }} else if (savedTab && document.getElementById('tabPane_' + savedTab)) {{
            switchTab(savedTab);
          }}

          if (localStorage.getItem('mishil_dash_funnel_collapsed') === '1') {{
            toggleHeroFunnel();
          }}

          var savedPlat = localStorage.getItem('mishil_dash_platform');
          if (savedPlat === 'ios' || savedPlat === 'android' || savedPlat === 'all') {{
            switchPlatform(savedPlat, true);
          }}

          var savedChartMode = localStorage.getItem('mishil_dash_chart_mode');
          if (savedChartMode === 'daily' || savedChartMode === 'cum' || savedChartMode === 'ios' || savedChartMode === 'android') {{
            switchChartMode(savedChartMode);
          }} else {{
            scrollTimelineToLatest();
          }}

          var tsWrap = document.getElementById('timelineScrollWrap');
          if (tsWrap) {{
            tsWrap.addEventListener('wheel', function(ev) {{
              if (Math.abs(ev.deltaY) > Math.abs(ev.deltaX) && tsWrap.scrollWidth > tsWrap.clientWidth) {{
                ev.preventDefault();
                tsWrap.scrollLeft += ev.deltaY;
              }}
            }}, {{ passive: false }});
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

          var isPolling = false;
          var pollErrorState = false;

          async function pollLiveTelemetry() {{
            if (isPolling || document.hidden) return;
            isPolling = true;
            var abortCtrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
            var timeoutId = abortCtrl ? setTimeout(function() {{ abortCtrl.abort(); }}, 8000) : null;
            try {{
              var res = await fetch('/api/v1/analytics/summary?period={clean_period}', {{
                headers: {{ 'Accept': 'application/json' }},
                credentials: 'same-origin',
                signal: abortCtrl ? abortCtrl.signal : undefined
              }});
              if (!res.ok) {{
                pollErrorState = true;
                if (countdownEl && dotEl && autoRefreshEnabled) {{
                  countdownEl.textContent = (res.status === 401) ? 'Oturum Yenile' : 'Canlı: Bekleniyor';
                  dotEl.style.background = '#F59E0B';
                  dotEl.style.boxShadow = '0 0 8px #F59E0B';
                }}
                return;
              }}
              var data = await res.json();
              if (pollErrorState) {{
                pollErrorState = false;
                updateUi();
              }}
              if (data.platform_split) {{
                PLATFORM_SPLIT = data.platform_split;
                switchPlatform(currentPlatform, true);
              }}
              if (data.satisfaction_pulse) {{
                updateSatisfactionPulseDom(data.satisfaction_pulse);
              }}
              if (data.in_app_feedbacks) {{
                var fbObj = data.in_app_feedbacks;
                var fbTot = Number(fbObj.total_count || 0);
                var fb24 = Number(fbObj.last_24h_count || 0);
                var sFb = document.getElementById('sideKpiFeedbacks');
                var cFb = document.getElementById('convFeedbacksPill');
                var hFb = document.getElementById('inAppFeedbacksHeadSpan');
                var bTotFb = document.getElementById('inAppFeedbacksTotalBadge');
                var b24Fb = document.getElementById('inAppFeedbacks24hBadge');
                if (sFb) sFb.textContent = fbTot + ' Mesaj';
                if (cFb) cFb.textContent = fbTot + ' Mesaj ➔';
                if (hFb) hFb.textContent = '💌 Uygulama İçi Anne Mesajları & Geri Bildirimler (' + fbTot + ')';
                if (bTotFb) bTotFb.textContent = '📨 Toplam: ' + fbTot;
                if (b24Fb) b24Fb.textContent = '⚡ Son 24s: ' + fb24;
                var fbListEl = document.getElementById('inAppFeedbacksList');
                if (fbListEl && Array.isArray(fbObj.items)) {{
                  if (fbObj.items.length === 0) {{
                    fbListEl.innerHTML = '<div class="bento-card" id="inAppFeedbacksEmptyState" style="grid-column: 1 / -1; text-align:center; color:var(--text-muted); padding:18px;">Henüz uygulama içinden gönderilmiş anne mesajı veya geri bildirim bulunmuyor. Uygulama içinden (veya memnuniyet yoklamasından) mesaj geldiğinde anında burada listelenir.</div>';
                  }} else {{
                    var fbHtmlOut = '';
                    for (var fi = 0; fi < fbObj.items.length; fi++) {{
                      var fIt = fbObj.items[fi];
                      var fPlat = fIt.platform || 'all';
                      var fPlatBadge = '<span class="badge" style="background:rgba(148,163,184,0.16); color:var(--text-secondary);">🌐 Web</span>';
                      if (fPlat === 'ios') fPlatBadge = '<span class="badge badge-meta">🍏 iOS</span>';
                      else if (fPlat === 'android') fPlatBadge = '<span class="badge badge-gp">🤖 Android</span>';
                      var fMsgStr = String(fIt.message || '');
                      var fSentStr = String(fIt.sentiment || 'suggestion').toLowerCase();
                      var fSentBadge = '<span class="badge" style="background:rgba(16,185,129,0.14); color:#059669;">💡 Öneri / Mesaj</span>';
                      if (fMsgStr.toLocaleLowerCase('tr-TR').indexOf('çözüm yoklaması') > -1) {{
                        fSentBadge = '<span class="badge" style="background:rgba(var(--stage-5-rgb),0.14); color:var(--stage-5);">🔔 Çözüm Yoklaması</span>';
                      }} else if (fSentStr === 'awake' || fSentStr === 'still_awake') {{
                        fSentBadge = '<span class="badge" style="background:rgba(var(--stage-5-rgb),0.14); color:var(--stage-5);">🥱 Uyuyamadı</span>';
                      }} else if (fSentStr === 'needs_improvement') {{
                        fSentBadge = '<span class="badge" style="background:rgba(217,119,6,0.15); color:#D97706;">🟡 Zorlandık</span>';
                      }}
                      var fAgeChip = (fIt.baby_age_months !== null && fIt.baby_age_months !== undefined)
                        ? '<span class="kpi-micro-chip">👶 ' + Number(fIt.baby_age_months) + ' Aylık</span>'
                        : '';
                      var fVerChip = fIt.app_version
                        ? '<span class="kpi-micro-chip">v' + escapeHtmlJs(fIt.app_version) + '</span>'
                        : '';
                      var fContactBlock = fIt.contact_info
                        ? '<div class="review-foot" style="margin-top:6px; color:#2563EB; font-weight:700;">📞 İletişim: ' + escapeHtmlJs(fIt.contact_info) + '</div>'
                        : '';
                      fbHtmlOut += '<div class="review-bubble in-app-feedback-item" data-platform="' + escapeHtmlJs(fPlat) + '">' +
                        '<div class="review-head">' +
                          '<div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">' +
                            fPlatBadge + fSentBadge + fAgeChip + fVerChip +
                          '</div>' +
                          '<span style="font-size:11.5px; color:var(--text-muted); font-weight:700; font-variant-numeric:tabular-nums;">🕒 ' + escapeHtmlJs(fIt.time_tr || '-') + '</span>' +
                        '</div>' +
                        '<p class="review-body" style="white-space:pre-wrap; margin:6px 0 2px;">' + escapeHtmlJs(fMsgStr) + '</p>' +
                        fContactBlock +
                      '</div>';
                    }}
                    fbListEl.innerHTML = fbHtmlOut;
                    filterInAppFeedbacks(document.getElementById('inAppFeedbacksSearchInput'));
                  }}
                }}
              }}
              if (data.zero_static_data_audit) {{
                var zBadge = document.getElementById('zeroStaticAuditBadge');
                if (zBadge) {{
                  var zOk = Boolean(data.zero_static_data_audit.all_passed);
                  var zPass = Number(data.zero_static_data_audit.contracts_passed || 0);
                  var zTot = Number(data.zero_static_data_audit.contracts_checked || 5);
                  zBadge.textContent = (zOk ? '🛡️ %100 Canlı Veri (' : '⚠️ Veri Denetimi (') + zPass + '/' + zTot + ')';
                  zBadge.title = data.zero_static_data_audit.status_badge || '';
                }}
              }}
              var elSub = document.getElementById('livePeriodSub');
              if (elSub) {{
                elSub.textContent = (data.period_label || '{html.escape(s["period_label"])}') + ' • ' + (data.active_human_count || 0) + ' Tekil Tık (Bugün: ' + (data.today_unique_clicks || 0) + ')';
              }}
              var dl2 = document.getElementById('kpiDelta2');
              if (dl2 && data.today_unique_clicks !== undefined) {{
                dl2.textContent = '+' + data.today_unique_clicks + ' Bugün';
              }}
              var headSpan = document.getElementById('liveClicksHeadSpan');
              if (headSpan) {{
                headSpan.textContent = '⚡ Canlı Trafik (' + (data.active_human_count || 0) + ' Tekil / ' + (data.total_raw || 0) + ' Ham)';
              }}
              var sbHead = document.getElementById('socialBridgeHeadSpan');
              if (sbHead && data.instagram_bio && data.instagram_bio.unique_clicks !== undefined) {{
                sbHead.textContent = '📲 Sosyal & Reklam Kanalları (' + data.instagram_bio.unique_clicks + ' Profil Tıkı)';
              }}
              if (data.meta_ads) {{
                var mVal = document.getElementById('metaUniqueClicksVal');
                if (mVal && data.meta_ads.unique_clicks !== undefined) mVal.textContent = data.meta_ads.unique_clicks + ' Kişi';
              }}
              if (data.meta_app_installs_sdk) {{
                var mRate = document.getElementById('metaSplitRate');
                var iosSdkTxt = document.getElementById('iosAttSdkStatusText');
                if (mRate) mRate.textContent = '🍏 ' + (data.meta_app_installs_sdk.ios_direct_installs || 0) + ' App Store/Meta • 🤖 ' + (data.meta_app_installs_sdk.android_direct_installs || 0) + ' Play/Meta Kurulum';
                if (iosSdkTxt && data.meta_app_installs_sdk.ios_sdk_status_badge) iosSdkTxt.textContent = data.meta_app_installs_sdk.ios_sdk_status_badge;
              }}
              if (data.instagram_bio) {{
                var igVal = document.getElementById('igUniqueClicksVal');
                var igRate = document.getElementById('igSplitRate');
                if (igVal && data.instagram_bio.unique_clicks !== undefined) igVal.textContent = data.instagram_bio.unique_clicks + ' Kişi';
                if (igRate) igRate.textContent = '🍏 ' + (data.instagram_bio.ios_clicks || 0) + ' iOS • 🤖 ' + (data.instagram_bio.android_clicks || 0) + ' Android';
              }}
              var tbody = document.getElementById('liveClicksTbody');
              if (tbody && Array.isArray(data.recent_clicks)) {{
                var rowsOut = '';
                var list = data.recent_clicks.slice(0, 60);
                for (var i = 0; i < list.length; i++) {{
                  var c = list[i];
                  if (c.is_bot || !c.is_unique) continue;
                  var dtStr = '';
                  if (c.time_tr && String(c.time_tr).length >= 16) {{
                    dtStr = String(c.time_tr).slice(0, 5) + ' ' + String(c.time_tr).slice(11, 16);
                  }} else {{
                    try {{
                      var dObj = new Date(c.created_at);
                      dtStr = dObj.toLocaleString('tr-TR', {{ timeZone: 'Europe/Istanbul', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }}).replace(',', '');
                    }} catch (_de) {{
                      dtStr = String(c.created_at || '').slice(5, 16);
                    }}
                  }}
                  var cPlat = (c.os_family === 'ios' || c.target_store === 'app_store') ? 'ios' : 'android';
                  var rowDisp = (currentPlatform === 'all' || currentPlatform === cPlat) ? '' : 'display:none;';
                  var storeStr = (c.target_store === 'app_store') ? '🍏 App Store (iPhone)' : '🤖 Google Play (Android)';
                  var devPrefix = (c.os_family === 'ios') ? '🍏 ' : '🤖 ';
                  var stColor = (cPlat === 'ios') ? '#059669' : '#2563EB';
                  rowsOut += '<tr data-platform="' + cPlat + '" style="' + rowDisp + '">' +
                    '<td style="color:var(--text-secondary); font-weight:600; font-variant-numeric:tabular-nums;">' + escapeHtmlJs(dtStr) + '</td>' +
                    '<td>' + devPrefix + escapeHtmlJs(c.device_detail || 'Telefon') + '</td>' +
                    '<td>' + escapeHtmlJs(c.app_webview || 'Tarayıcı') + '</td>' +
                    '<td style="color:' + stColor + '; font-weight:700;">' + storeStr + '</td>' +
                    '<td style="color:var(--text-muted);">' + escapeHtmlJs(c.country || 'TR') + '</td>' +
                    '</tr>';
                }}
                tbody.innerHTML = rowsOut;
                filterTableByQuery(document.getElementById('liveClicksSearchInput'), 'liveClicksTbody');
              }}
            }} catch (_err) {{
              pollErrorState = true;
              if (countdownEl && dotEl && autoRefreshEnabled) {{
                countdownEl.textContent = 'Canlı: Bağlanıyor...';
                dotEl.style.background = '#F59E0B';
                dotEl.style.boxShadow = '0 0 8px #F59E0B';
              }}
            }} finally {{
              if (timeoutId) clearTimeout(timeoutId);
              isPolling = false;
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
            if (!autoRefreshEnabled || document.hidden) return;
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
            secure=_is_request_https(request),
            max_age=_ADMIN_SESSION_TTL_SECONDS,
            path="/",
        )
    return dashboard_response
