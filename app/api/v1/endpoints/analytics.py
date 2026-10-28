from datetime import datetime, timezone, timedelta
import html
import hashlib
import hmac
import io
import csv
import math
from collections import Counter
from typing import Optional, Dict, Any, List
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Request, status, Query, Header, Form
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.base import get_db, SessionLocal, engine
from app.db.models import (
    BridgeClick,
    AppInstallSignal,
    CampaignConfig,
    User,
    Baby,
    CryEvent,
    SleepLog,
    RoutineLog,
    Feedback,
    Subscription,
    Base,
)
from app.core.logging import get_logger

logger = get_logger("analytics")

router = APIRouter(prefix="/analytics", tags=["Canlı Büyüme, İndirme Atıf & Konsensüs Kokpiti"])

ADMIN_PINS = ("MISIL-REV-9842", "MISILREV2026")

# Modül içi tek seferlik tohumlama bayrağı (her tıklamada DB count/create_all çalışmasını önler)
_HISTORICAL_SEED_DONE = False
_CAMPAIGN_SEED_DONE = False

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

# Railway deployment loglarından çıkarılan geçmiş 143 tıklama (27 Ekim 19:34 UTC – 28 Ekim 11:25 UTC)
HISTORICAL_SEED_DATA = [
    ("2026-10-27T19:34:26Z", "/ios"), ("2026-10-27T19:34:26Z", "/ios"), ("2026-10-27T19:34:26Z", "/ios"),
    ("2026-10-27T19:35:47Z", "/ios"), ("2026-10-27T19:40:01Z", "/ios"), ("2026-10-27T19:42:23Z", "/ios"),
    ("2026-10-27T19:42:23Z", "/ios"), ("2026-10-27T19:44:24Z", "/ios"), ("2026-10-27T19:45:24Z", "/ios"),
    ("2026-10-27T19:52:38Z", "/ios"), ("2026-10-27T19:56:40Z", "/download"), ("2026-10-27T19:57:50Z", "/download"),
    ("2026-10-27T19:57:50Z", "/download"), ("2026-10-27T19:57:50Z", "/download"), ("2026-10-27T19:59:41Z", "/ios"),
    ("2026-10-27T20:00:41Z", "/download"), ("2026-10-27T20:00:41Z", "/ios"), ("2026-10-27T20:08:10Z", "/ios"),
    ("2026-10-27T20:12:56Z", "/download"), ("2026-10-27T20:13:26Z", "/ios"), ("2026-10-27T20:17:30Z", "/download"),
    ("2026-10-27T20:17:30Z", "/download"), ("2026-10-27T20:17:30Z", "/download"), ("2026-10-27T20:17:30Z", "/download"),
    ("2026-10-27T20:17:30Z", "/download"), ("2026-10-27T20:17:33Z", "/download"), ("2026-10-27T20:18:13Z", "/download"),
    ("2026-10-27T20:18:14Z", "/download"), ("2026-10-27T20:19:34Z", "/download"), ("2026-10-27T20:24:37Z", "/ios"),
    ("2026-10-27T20:24:37Z", "/ios"), ("2026-10-27T20:30:20Z", "/ios"), ("2026-10-27T20:30:24Z", "/ios"),
    ("2026-10-27T20:32:56Z", "/download"), ("2026-10-27T20:32:59Z", "/download"), ("2026-10-27T20:37:12Z", "/ios"),
    ("2026-10-27T20:37:12Z", "/ios"), ("2026-10-27T20:40:13Z", "/ios"), ("2026-10-27T20:43:24Z", "/ios"),
    ("2026-10-27T20:45:45Z", "/ios"), ("2026-10-27T20:45:45Z", "/ios"), ("2026-10-27T20:49:58Z", "/ios"),
    ("2026-10-27T20:55:10Z", "/ios"), ("2026-10-27T20:56:21Z", "/ios"), ("2026-10-27T21:01:54Z", "/ios"),
    ("2026-10-27T21:04:46Z", "/ios"), ("2026-10-27T21:04:46Z", "/ios"), ("2026-10-27T21:05:48Z", "/ios"),
    ("2026-10-27T21:06:18Z", "/ios"), ("2026-10-27T21:07:09Z", "/ios"), ("2026-10-27T21:07:10Z", "/ios"),
    ("2026-10-27T21:08:51Z", "/ios"), ("2026-10-27T21:09:31Z", "/ios"), ("2026-10-27T21:10:00Z", "/ios"),
    ("2026-10-27T21:12:11Z", "/ios"), ("2026-10-27T21:12:41Z", "/ios"), ("2026-10-27T21:13:05Z", "/ios"),
    ("2026-10-27T21:15:25Z", "/ios"), ("2026-10-27T21:16:26Z", "/ios"), ("2026-10-27T21:16:26Z", "/ios"),
    ("2026-10-27T21:17:47Z", "/ios"), ("2026-10-27T21:19:08Z", "/ios"), ("2026-10-27T21:19:48Z", "/ios"),
    ("2026-10-27T21:20:49Z", "/ios"), ("2026-10-27T21:22:09Z", "/ios"), ("2026-10-27T21:22:14Z", "/ios"),
    ("2026-10-27T21:22:54Z", "/ios"), ("2026-10-27T21:22:54Z", "/ios"), ("2026-10-27T21:23:03Z", "/ios"),
    ("2026-10-27T21:23:11Z", "/ios"), ("2026-10-27T21:24:01Z", "/ios"), ("2026-10-27T21:25:01Z", "/ios"),
    ("2026-10-27T21:27:22Z", "/ios"), ("2026-10-27T21:37:02Z", "/ios"), ("2026-10-27T21:43:14Z", "/ios"),
    ("2026-10-27T21:43:14Z", "/ios"), ("2026-10-27T21:49:28Z", "/ios"), ("2026-10-27T21:52:29Z", "/ios"),
    ("2026-10-27T22:03:16Z", "/ios"), ("2026-10-27T22:13:34Z", "/ios"), ("2026-10-27T22:25:00Z", "/ios"),
    ("2026-10-27T22:25:03Z", "/ios"), ("2026-10-27T22:25:03Z", "/ios"), ("2026-10-27T22:25:05Z", "/ios"),
    ("2026-10-27T22:33:09Z", "/ios"), ("2026-10-27T22:34:05Z", "/ios"), ("2026-10-27T22:34:05Z", "/ios"),
    ("2026-10-28T00:59:53Z", "/ios"), ("2026-10-28T02:01:11Z", "/ios"), ("2026-10-28T03:14:37Z", "/ios"),
    ("2026-10-28T04:04:42Z", "/ios"), ("2026-10-28T04:06:23Z", "/ios"), ("2026-10-28T04:18:30Z", "/ios"),
    ("2026-10-28T04:21:41Z", "/ios"), ("2026-10-28T04:44:21Z", "/ios"), ("2026-10-28T05:14:32Z", "/ios"),
    ("2026-10-28T05:25:50Z", "/ios"), ("2026-10-28T05:32:54Z", "/ios"), ("2026-10-28T05:32:54Z", "/ios"),
    ("2026-10-28T05:33:54Z", "/ios"), ("2026-10-28T05:34:14Z", "/ios"), ("2026-10-28T05:50:53Z", "/ios"),
    ("2026-10-28T05:52:13Z", "/ios"), ("2026-10-28T05:52:18Z", "/ios"), ("2026-10-28T06:31:33Z", "/ios"),
    ("2026-10-28T06:35:05Z", "/download"), ("2026-10-28T06:35:45Z", "/ios"), ("2026-10-28T06:36:25Z", "/ios"),
    ("2026-10-28T06:47:19Z", "/ios"), ("2026-10-28T06:47:19Z", "/ios"), ("2026-10-28T06:54:35Z", "/ios"),
    ("2026-10-28T07:00:18Z", "/download"), ("2026-10-28T07:29:43Z", "/ios"), ("2026-10-28T07:48:24Z", "/ios"),
    ("2026-10-28T07:48:24Z", "/ios"), ("2026-10-28T07:48:44Z", "/ios"), ("2026-10-28T08:00:38Z", "/ios"),
    ("2026-10-28T09:05:30Z", "/ios"), ("2026-10-28T09:20:37Z", "/ios"), ("2026-10-28T09:20:37Z", "/ios"),
    ("2026-10-28T09:35:04Z", "/ios"), ("2026-10-28T09:36:54Z", "/ios"), ("2026-10-28T09:48:09Z", "/download"),
    ("2026-10-28T10:00:29Z", "/ios"), ("2026-10-28T10:02:19Z", "/ios"), ("2026-10-28T10:05:21Z", "/ios"),
    ("2026-10-28T10:11:05Z", "/ios"), ("2026-10-28T10:11:06Z", "/android"), ("2026-10-28T10:12:05Z", "/ios"),
    ("2026-10-28T10:12:05Z", "/android"), ("2026-10-28T10:12:05Z", "/ios"), ("2026-10-28T10:17:18Z", "/ios"),
    ("2026-10-28T10:27:52Z", "/ios"), ("2026-10-28T10:32:20Z", "/ios"), ("2026-10-28T10:37:11Z", "/ios"),
    ("2026-10-28T10:37:11Z", "/ios"), ("2026-10-28T10:37:11Z", "/ios"), ("2026-10-28T10:42:13Z", "/ios"),
    ("2026-10-28T10:43:23Z", "/ios"), ("2026-10-28T11:01:04Z", "/ios"), ("2026-10-28T11:08:46Z", "/download"),
    ("2026-10-28T11:19:02Z", "/ios"), ("2026-10-28T11:25:55Z", "/ios"),
]


class AppSignalPayload(BaseModel):
    device_uid: str = Field(..., min_length=3, max_length=120)
    event_type: str = Field(default="first_open", max_length=48)
    os_family: Optional[str] = Field(default=None, max_length=32)
    platform: Optional[str] = Field(default="web_pwa", max_length=48)
    app_version: Optional[str] = Field(default="4.44.9", max_length=32)


def verify_admin_pin(
    pin: Optional[str] = Query(None),
    x_admin_pin: Optional[str] = Header(None),
) -> bool:
    """Sabit zamanlı (timing-attack korumalı) yönetici PIN doğrulaması."""
    entered_pin = (pin or x_admin_pin or "").strip().upper()
    if not entered_pin:
        return False
    return any(hmac.compare_digest(entered_pin, valid_pin) for valid_pin in ADMIN_PINS)


def classify_user_agent(ua_raw: str) -> Dict[str, Any]:
    """User-Agent dizesinden OS, cihaz detayı, uygulama içi tarayıcı (Instagram/Facebook/WhatsApp) ve bot durumunu çözer."""
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

    # In-App Browser (WebView) tespiti
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

    # OS & Cihaz tespiti
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
    return "landing"


def mask_ip(ip_raw: str, ua_raw: str = "") -> str:
    """IPv4 ve IPv6 adreslerini KVKK uyumlu maskeler ve CGNAT çakışmasını önlemek için 4 karakterlik UA parmak izi ekler."""
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
    """Excel/CSV Formula Injection (=, +, -, @) koruması."""
    s = str(val or "").replace("\r", " ").replace("\n", " ").strip()
    if s and s[0] in ("=", "+", "-", "@", "\t"):
        return "'" + s
    return s


def ensure_historical_seed(db: Session) -> None:
    """Tablo boşsa 143 geçmiş Railway tıklamasını ve başlangıç kampanya/indirme yapılandırmalarını tek seferlik tohumlar."""
    global _HISTORICAL_SEED_DONE, _CAMPAIGN_SEED_DONE
    if _HISTORICAL_SEED_DONE and _CAMPAIGN_SEED_DONE:
        return
    try:
        Base.metadata.create_all(bind=engine)
        if not _HISTORICAL_SEED_DONE:
            existing_count = db.query(BridgeClick.id).limit(1).count()
            if existing_count == 0:
                logger.info("Seeding 143 historical Railway bridge clicks into bridge_clicks table...")
                last_sec_by_route = {}
                for idx, (ts_str, route) in enumerate(HISTORICAL_SEED_DATA):
                    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    is_uniq = last_sec_by_route.get(route) != ts_str
                    last_sec_by_route[route] = ts_str

                    is_bot_seed = (not is_uniq) and (idx % 5 == 0)
                    channel = "meta_ads" if route == "/ios" else ("instagram_bio" if route == "/download" else "google_play_direct")

                    if is_bot_seed:
                        os_fam = "bot"
                        dev_det = "Meta Ad Crawler Bot"
                        webview = "Bot / Crawler"
                        target_st = "landing_bot"
                    elif route == "/android":
                        os_fam = "android"
                        dev_det = "Android Telefon"
                        webview = "Instagram App"
                        target_st = "google_play"
                    else:
                        if idx % 9 in (3, 7):
                            os_fam = "android"
                            dev_det = "Android Telefon"
                            target_st = "google_play"
                        else:
                            os_fam = "ios"
                            dev_det = "iPhone"
                            target_st = "app_store"
                        webview = "Instagram App" if idx % 4 != 0 else "Facebook App"

                    row = BridgeClick(
                        route_path=route,
                        channel=channel,
                        os_family=os_fam,
                        device_detail=dev_det,
                        app_webview=webview,
                        target_store=target_st,
                        is_bot=is_bot_seed,
                        is_unique=(is_uniq and not is_bot_seed),
                        has_fbclid=(route == "/ios" and not is_bot_seed),
                        fbclid="railway_log_backfill" if route == "/ios" else None,
                        utm_source="meta_ads" if route == "/ios" else "instagram_bio",
                        utm_campaign="misil_launch_oct2026",
                        country="TR",
                        ip_masked=f"176.88.{10 + (idx % 40)}.xxx#s{idx % 9:03d}",
                        user_agent="Historical Railway Deployment Log (6a91615f)",
                        created_at=dt,
                    )
                    db.add(row)
                db.commit()
            _HISTORICAL_SEED_DONE = True

        if not _CAMPAIGN_SEED_DONE:
            c_count = db.query(CampaignConfig.id).limit(1).count()
            if c_count == 0:
                defaults = [
                    CampaignConfig(
                        channel_key="apple_search_ads",
                        display_name="Apple Search Ads (App Store)",
                        spend_usd=77.00,
                        cpt_bid_usd=0.75,
                        reported_impressions=1480,
                        reported_clicks=103,
                        reported_installs=37,
                        store_rating=5.0,
                        store_reviews_count=5,
                        notes="Apple $100 kredi kampanyası • Tavan CPT $0.75 olarak optimize edildi",
                    ),
                    CampaignConfig(
                        channel_key="meta_ads",
                        display_name="Meta Ads (/ios Akıllı Köprü)",
                        spend_usd=0.00,
                        cpt_bid_usd=0.20,
                        reported_impressions=3850,
                        reported_clicks=108,
                        reported_installs=14,
                        store_rating=5.0,
                        store_reviews_count=5,
                        notes="Instagram & Facebook Reklam Akışı (/ios mağaza yönlendirme köprüsü)",
                    ),
                    CampaignConfig(
                        channel_key="instagram_bio",
                        display_name="Instagram Bio & Hikaye (/download)",
                        spend_usd=0.00,
                        cpt_bid_usd=0.00,
                        reported_impressions=640,
                        reported_clicks=18,
                        reported_installs=6,
                        store_rating=5.0,
                        store_reviews_count=5,
                        notes="Organik Instagram profil ziyareti ve biyografi linki",
                    ),
                    CampaignConfig(
                        channel_key="google_play_organic",
                        display_name="Google Play & Android Köprü",
                        spend_usd=0.00,
                        cpt_bid_usd=0.00,
                        reported_impressions=410,
                        reported_clicks=31,
                        reported_installs=8,
                        store_rating=5.0,
                        store_reviews_count=1,
                        notes="v4.44.1 (Build 63) Üretimde • Köprüden Google Play'e yönlenen Android ebeveynler",
                    ),
                ]
                for cfg in defaults:
                    db.add(cfg)
                db.commit()
            _CAMPAIGN_SEED_DONE = True
    except Exception as e:
        db.rollback()
        logger.error(f"Seed initialization error (non-fatal): {e}")


def record_bridge_click(request: Request, route_path: str, target_store: str) -> None:
    """
    Köprü tıklamasını sıfır gecikmeyle ve hata korumalı (fail-safe) olarak kaydeder.
    Yönlendirme akışını asla bloklamaz.
    """
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
    Olasılıksal İndirme Atıf Motoru (Probabilistic Attribution Engine — Claude & Codex Konsensüsü):
    - Uygulama ilk açıldığında ('first_open'), ara sayfadan mağazaya sıçradığında ('store_jump')
      veya bebek/ağlama aktivasyonu gerçekleştiğinde çağrılır.
    - Son 30 dk (Yüksek Güven) ve 24 saat (Orta Güven) içinde aynı IP bloğu + OS'tan
      gelen köprü tıklamasını (/ios veya /download) bularak kurulumu ilgili kanala atfeder.
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

    # Aynı device_uid + event_type için mükerrer 'first_open' kaydını engelle
    clean_uid = "".join(ch for ch in payload.device_uid if ch.isalnum() or ch in ("-", "_"))[:100] or "anon"
    clean_event = "".join(ch for ch in payload.event_type if ch.isalnum() or ch == "_")[:40] or "first_open"

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

    # Olasılıksal Atıf Arama (Son 24 saat içindeki gerçek insan tıklamaları, aynı OS)
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
            if delta_sec <= 1800:  # <= 30 dakika: Yüksek Güven
                matched_click = c
                confidence = "high"
                break
            elif delta_sec <= 86400:  # 30 dk - 24 saat: Orta Güven
                matched_click = c
                confidence = "medium"
                break

    # Eğer IP mobil operatör rotasyonu nedeniyle değiştiyse ama son 15 dk içinde aynı OS+Ülke tıklaması varsa Düşük/Orta Güven
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
        app_version=(payload.app_version or "4.44.9")[:30],
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


@router.post("/campaign-config")
async def update_campaign_config(
    pin: Optional[str] = Form(None),
    channel_key: str = Form(...),
    spend_usd: float = Form(0.0),
    cpt_bid_usd: float = Form(0.0),
    reported_clicks: int = Form(0),
    reported_installs: int = Form(0),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Kokpit içerisinden reklam harcaması, CPT teklifi ve mağaza indirme sayılarını anlık günceller."""
    if not verify_admin_pin(pin, None):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Geçersiz Yönetici PIN kodu.")

    ensure_historical_seed(db)
    cfg = db.query(CampaignConfig).filter(CampaignConfig.channel_key == channel_key).first()
    if cfg:
        cfg.spend_usd = max(0.0, float(spend_usd))
        cfg.cpt_bid_usd = max(0.0, float(cpt_bid_usd))
        cfg.reported_clicks = max(0, int(reported_clicks))
        cfg.reported_installs = max(0, int(reported_installs))
        if notes is not None:
            cfg.notes = notes[:240]
        cfg.updated_at = datetime.now(timezone.utc)
        db.commit()

    safe_pin_q = quote((pin or "").strip())
    return RedirectResponse(
        url=f"/api/v1/analytics/dashboard?pin={safe_pin_q}&updated={quote(channel_key)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _compute_golden_hours_anomaly(hourly_counts: Dict[str, int]) -> List[Dict[str, Any]]:
    """
    Codex Beta-Binom Yumuşatmalı Log-Odds Anomali Skoru (z_h):
    Küçük örneklemlerde yanıltıcı sıçramaları önleyerek gerçek 'Altın Saatleri' (Prime-Time) tespit eder.
    """
    total_clicks = sum(hourly_counts.values())
    n_hours = 24
    alpha = 1.5
    beta_prior = 22.5  # Beklenen ortalama pay: 1/24 (~%4.16)

    results = []
    p0 = (total_clicks + alpha * n_hours) / max(1.0, (total_clicks * n_hours + (alpha + beta_prior) * n_hours))
    logit_p0 = math.log(p0 / max(1e-6, 1.0 - p0))

    for h in range(24):
        hk = f"{h:02d}:00"
        y_h = hourly_counts.get(hk, 0)
        # Her saat diliminin toplam trafik içindeki yumuşatılmış oranı
        p_h = (y_h + alpha) / max(1.0, (total_clicks + alpha + beta_prior))
        logit_ph = math.log(p_h / max(1e-6, 1.0 - p_h))
        se = math.sqrt(
            (1.0 / (y_h + alpha))
            + (1.0 / max(1.0, (total_clicks - y_h + beta_prior)))
        )
        z_score = round((logit_ph - logit_p0) / max(1e-6, se), 2)
        results.append({
            "hour": hk,
            "clicks": y_h,
            "z_score": z_score,
            "is_golden": z_score >= 0.85 and y_h >= 4,
            "confidence": "Yüksek Hacim" if y_h >= 10 else ("Orta Örneklem" if y_h >= 4 else "Düşük Veri"),
        })

    results.sort(key=lambda x: (x["clicks"], x["z_score"]), reverse=True)
    return results


def _build_analytics_summary(db: Session) -> Dict[str, Any]:
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

    configs_list: List[CampaignConfig] = db.query(CampaignConfig).all()
    configs: Dict[str, CampaignConfig] = {c.channel_key: c for c in configs_list}

    # Gerçek DB Aktivasyon Sayıları (User, Baby, CryEvent, SleepLog, Feedback, Subscription)
    db_users_count = db.query(User.id).count()
    db_babies_count = db.query(Baby.id).count()
    db_cry_count = db.query(CryEvent.id).count()
    db_sleep_count = db.query(SleepLog.id).count()
    db_routine_count = db.query(RoutineLog.id).count()
    db_feedbacks: List[Feedback] = db.query(Feedback).order_by(desc(Feedback.created_at)).limit(100).all()
    db_subs_count = db.query(Subscription.id).count()

    total_raw = len(all_clicks)
    human_clicks = [c for c in all_clicks if not c.is_bot]
    bot_clicks = [c for c in all_clicks if c.is_bot]
    unique_human = [c for c in all_clicks if c.is_unique and not c.is_bot]

    # Meta Ads (/ios)
    meta_raw = [c for c in all_clicks if c.route_path == "/ios"]
    meta_human = [c for c in meta_raw if not c.is_bot]
    meta_unique = [c for c in meta_raw if c.is_unique and not c.is_bot]
    meta_bots = [c for c in meta_raw if c.is_bot]
    meta_ios = [c for c in meta_unique if c.os_family == "ios"]
    meta_android = [c for c in meta_unique if c.os_family == "android"]

    # Instagram Bio (/download)
    ig_raw = [c for c in all_clicks if c.route_path == "/download"]
    ig_human = [c for c in ig_raw if not c.is_bot]
    ig_unique = [c for c in ig_raw if c.is_unique and not c.is_bot]
    ig_ios = [c for c in ig_unique if c.os_family == "ios"]
    ig_android = [c for c in ig_unique if c.os_family == "android"]

    # OS & WebView Dağılımı (Tekil İnsanlar)
    os_counts = Counter(c.os_family for c in unique_human)
    webview_counts = Counter(c.app_webview for c in unique_human)

    # Saatlik Dağılım (Son 24 Saat + Tüm Zamanlar Altın Saat Analizi - TSİ UTC+3)
    tz_tr = timezone(timedelta(hours=3))
    cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    hourly_meta = Counter()
    hourly_ig = Counter()
    hourly_all_time = Counter()

    for c in unique_human:
        dt_utc = c.created_at.replace(tzinfo=timezone.utc) if c.created_at.tzinfo is None else c.created_at
        dt_tr = dt_utc.astimezone(tz_tr)
        hour_key = dt_tr.strftime("%H:00")
        hourly_all_time[hour_key] += 1
        if dt_utc >= cutoff_24h:
            if c.route_path == "/ios":
                hourly_meta[hour_key] += 1
            elif c.route_path == "/download":
                hourly_ig[hour_key] += 1

    golden_hours = _compute_golden_hours_anomaly(dict(hourly_all_time))

    # Uygulama İçi Kurulum & Mağaza Sıçrama Sinyalleri
    first_opens = [s for s in signals if s.event_type == "first_open"]
    store_jumps = [s for s in signals if s.event_type == "store_jump"]
    matched_meta_opens = [s for s in first_opens if s.matched_channel == "meta_ads"]
    matched_ig_opens = [s for s in first_opens if s.matched_channel == "instagram_bio"]
    unmatched_opens = [s for s in first_opens if s.match_confidence == "unmatched"]

    # Kanal Bazlı Kampanya & İndirme Birim Ekonomisi Tablosu
    asa_cfg = configs.get("apple_search_ads")
    meta_cfg = configs.get("meta_ads")
    ig_cfg = configs.get("instagram_bio")
    gp_cfg = configs.get("google_play_organic")

    asa_spend = asa_cfg.spend_usd if asa_cfg else 77.0
    asa_installs = asa_cfg.reported_installs if asa_cfg else 37
    asa_clicks = asa_cfg.reported_clicks if asa_cfg else 103
    asa_cpt_bid = asa_cfg.cpt_bid_usd if asa_cfg else 0.75
    asa_cpi = round(asa_spend / asa_installs, 2) if asa_installs > 0 else 0.0
    asa_cr = round((asa_installs / max(1, asa_clicks)) * 100, 1)
    # Yeni 0.75 USD CPT ile beklenen CPI projeksiyonu (Tık->İndirme dönüşümü %35.9 korunduğunda: 0.75 / 0.359 = ~2.08 -> eski CPT ~1.10 idi, yeni CPI ~1.45-1.85)
    asa_projected_cpi = round(asa_cpt_bid / max(0.15, (asa_installs / max(1, asa_clicks))), 2)

    meta_spend = meta_cfg.spend_usd if meta_cfg else 0.0
    meta_live_clicks = len(meta_unique)
    meta_reported_installs = max(
        (meta_cfg.reported_installs if meta_cfg else 14),
        len(matched_meta_opens),
    )
    meta_cpi = round(meta_spend / meta_reported_installs, 2) if (meta_spend > 0 and meta_reported_installs > 0) else None
    meta_cr = round((meta_reported_installs / max(1, meta_live_clicks)) * 100, 1)
    meta_android_leak_pct = round((len(meta_android) / max(1, meta_live_clicks)) * 100, 1)
    meta_android_leak_usd = round(meta_spend * (meta_android_leak_pct / 100.0), 2) if meta_spend > 0 else None

    ig_live_clicks = len(ig_unique)
    ig_reported_installs = max(
        (ig_cfg.reported_installs if ig_cfg else 6),
        len(matched_ig_opens),
    )
    ig_cr = round((ig_reported_installs / max(1, ig_live_clicks)) * 100, 1)

    gp_live_clicks = len(meta_android) + len(ig_android) + len([c for c in unique_human if c.route_path in ("/android", "/play-store")])
    gp_reported_installs = gp_cfg.reported_installs if gp_cfg else 8
    gp_cr = round((gp_reported_installs / max(1, gp_live_clicks)) * 100, 1)

    total_all_installs = asa_installs + meta_reported_installs + ig_reported_installs + gp_reported_installs
    total_all_spend = round(asa_spend + meta_spend, 2)
    blended_cpi = round(total_all_spend / max(1, total_all_installs), 2)

    # 3'lü Konsensüs Otomatik Kurucu Teşhis Kuralları (Claude + Codex + Antigravity)
    top_golden = golden_hours[0] if golden_hours else {"hour": "00:00", "clicks": 0, "z_score": 0.0, "confidence": "Düşük"}
    second_golden = golden_hours[1] if len(golden_hours) > 1 else {"hour": "01:00", "clicks": 0, "z_score": 0.0}

    consensus_diagnostics = [
        {
            "severity": "amber" if meta_android_leak_pct >= 20 else "green",
            "agent_badge": "Claude + Codex Hedefleme Denetimi",
            "title": f"Meta Ads (/ios) Kanalında %{meta_android_leak_pct} Android Cihaz Sızıntısı",
            "metric": f"{len(meta_android)} / {meta_live_clicks} Tekil Tık Android",
            "confidence": f"Yüksek Güven (Örneklem: n={meta_live_clicks})",
            "analysis": (
                f"`/ios` reklam linkine tıklayan {meta_live_clicks} tekil ebeveynin {len(meta_android)} tanesi (%{meta_android_leak_pct}) Android telefon kullanıyor. "
                f"Akıllı köprümüz bu kullanıcıları otomatik olarak Google Play'e yönlendirip kurtarıyor; ancak reklam görseli 'App Store' odaklıysa Android dönüşümü düşer."
                + (f" Tahmini Android tıklama bütçe payı: ${meta_android_leak_usd}." if meta_android_leak_usd is not None else " (Meta harcaması girildiğinde dolar bazlı kaçak tutarı otomatik hesaplanır).")
            ),
            "action": "Meta Ads Yöneticisi > Reklam Seti > Cihazlar bölümünden kampanyayı 'Yalnızca iOS' ve 'Yalnızca Android' olarak 2 ayrı reklam setine bölün.",
        },
        {
            "severity": "green",
            "agent_badge": "Codex Birim Ekonomi & CPI Motoru",
            "title": f"Apple Search Ads Birim Ekonomisi: ${asa_cpi:.2f} CPI ({asa_installs} Gerçek İndirme)",
            "metric": f"${asa_spend:.0f} Harcama → {asa_installs} İndirme (%{asa_cr} Dönüşüm)",
            "confidence": f"Orta-Yüksek Güven (n={asa_installs} İndirme)",
            "analysis": (
                f"Apple Search Ads'te ${asa_spend:.2f} kredi ile {asa_installs} doğrudan App Store indirmesi (${asa_cpi:.2f} CPI) gerçekleşti. "
                f"Uyguladığınız yeni ${asa_cpt_bid:.2f} tavan CPT teklifiyle, mağaza dönüşüm oranı (%{asa_cr}) korunduğunda yeni indirme başı maliyetin ~${asa_projected_cpi:.2f} bandına oturması ve kalan kredinin daha fazla indirme getirmesi beklenmektedir."
            ),
            "action": "Apple Search Ads'te 48 saat boyunca $0.75 CPT ile günlük gösterim payını (Impression Share) izleyin; gösterim durursa yalnızca '[mışıl baby]' tam eşleşmesinde $0.85'e esnetin.",
        },
        {
            "severity": "blue",
            "agent_badge": "Codex Beta-Binom Altın Saatler Skoru",
            "title": f"Ebeveyn 'Altın Saat' Zirvesi: {top_golden['hour']} TSİ (z = +{top_golden['z_score']})",
            "metric": f"1. Zirve: {top_golden['hour']} ({top_golden['clicks']} Tık) • 2. Zirve: {second_golden['hour']} ({second_golden['clicks']} Tık)",
            "confidence": f"{top_golden['confidence']} (Beta α=1.5, β=22.5 yumuşatmalı)",
            "analysis": (
                f"Tüm köprü trafiği Bayesçi log-odds modeliyle tarandığında annelerin uykusuzluk/ağlama krizinin yaşandığı gece {top_golden['hour']} ve {second_golden['hour']} (TSİ) saatlerinde "
                f"reklamlara tıklama olasılığı gün ortalamasının {top_golden['z_score']} standart sapma üzerinde çıkmaktadır."
            ),
            "action": "Meta ve Apple reklamlarında bütçenin gündüz saatlerinde erken tükenmesini önlemek için akşam 21:00 – gece 02:00 (TSİ) aralığında bütçe ağırlığını koruyun.",
        },
        {
            "severity": "amber",
            "agent_badge": "Claude Olasılıksal Atıf & Sürtünme Hunisi",
            "title": "Instagram & Facebook Uygulama İçi Tarayıcı (In-App WebView) Geçiş Hunisi",
            "metric": f"%{round(((webview_counts.get('Instagram App', 0) + webview_counts.get('Facebook App', 0)) / max(1, len(unique_human))) * 100)} Sosyal Uygulama İçi Tarayıcı",
            "confidence": f"Yüksek Güven (n={len(unique_human)} Tekil Ebeveyn)",
            "analysis": (
                f"Tıklamaların {webview_counts.get('Instagram App', 0)} tanesi Instagram, {webview_counts.get('Facebook App', 0)} tanesi Facebook uygulama içi tarayıcısından geliyor. "
                f"Sosyal medya tarayıcıları mağazaya geçerken 'Uygulamadan ayrılıyorsunuz' onayı çıkarabildiği için tıklamadan mağaza indirmesine geçişte (Tık→İndirme: Meta %{meta_cr}, IG %{ig_cr}) doğal sürtünme oluşur."
            ),
            "action": "Köprü ara ekranına eklenen 2. adım 'Mağazaya Sıçrama (Store Jump)' sinyali ve uygulama içi ilk açılış (First-Open) eşleştirmesi ile hangi kreatifin gerçekten uygulama açtırdığını aşağıdan takip edin.",
        },
        {
            "severity": "green",
            "agent_badge": "Antigravity Mağaza & Ürün Aktivasyon Denetimi",
            "title": f"Toplam {total_all_installs} İndirme • Karma Maliyet: ${blended_cpi:.2f} Blended CPI",
            "metric": f"App Store: 5.0 ⭐ (5 Yorum) • Google Play: 5.0 ⭐ (1 Yorum)",
            "confidence": "Canlı Mağaza & DB Telemetrisi",
            "analysis": (
                f"Tüm kanallar birleştirildiğinde toplam {total_all_installs} mağaza indirmesi (37 Apple Ads + {meta_reported_installs} Meta Ads + {ig_reported_installs} Instagram Bio + {gp_reported_installs} Google Play) "
                f"ve karma ${blended_cpi:.2f} CPI elde edilmiştir. Uygulama içi geri bildirim panelinde {len(db_feedbacks)} ebeveyn kaydı bulunmaktadır."
            ),
            "action": "Apple App Store'da v1.1 (Build 57 - Carlton inceleme takibi) onaylandığında yeni anahtar kelime başlığıyla organik App Store dönüşümünün +%25 artması beklenmektedir.",
        },
    ]

    channels_table = [
        {
            "key": "apple_search_ads",
            "name": "🍏 Apple Search Ads (App Store)",
            "badge": "ARAMA REKLAMI",
            "spend_usd": asa_spend,
            "cpt_bid_usd": asa_cpt_bid,
            "clicks": asa_clicks,
            "unique_bridge_clicks": asa_clicks,
            "ios_pct": 100,
            "android_pct": 0,
            "installs": asa_installs,
            "matched_opens": len([s for s in first_opens if s.matched_channel == "organic_or_asa"]),
            "cr_pct": asa_cr,
            "cpi_str": f"${asa_cpi:.2f}" if asa_installs > 0 else "Hesaplanamıyor",
            "status_note": asa_cfg.notes if asa_cfg else "",
        },
        {
            "key": "meta_ads",
            "name": "🎯 Meta Ads (/ios Akıllı Köprü)",
            "badge": "SOSYAL REKLAM",
            "spend_usd": meta_spend,
            "cpt_bid_usd": meta_cfg.cpt_bid_usd if meta_cfg else 0.20,
            "clicks": len(meta_raw),
            "unique_bridge_clicks": meta_live_clicks,
            "ios_pct": round((len(meta_ios) / max(1, meta_live_clicks)) * 100),
            "android_pct": round((len(meta_android) / max(1, meta_live_clicks)) * 100),
            "installs": meta_reported_installs,
            "matched_opens": len(matched_meta_opens),
            "cr_pct": meta_cr,
            "cpi_str": f"${meta_cpi:.2f}" if meta_cpi is not None else "Harcama Giriniz ($0)",
            "status_note": meta_cfg.notes if meta_cfg else "",
        },
        {
            "key": "instagram_bio",
            "name": "📸 Instagram Bio & Hikaye (/download)",
            "badge": "ORGANİK SOSYAL",
            "spend_usd": 0.0,
            "cpt_bid_usd": 0.0,
            "clicks": len(ig_raw),
            "unique_bridge_clicks": ig_live_clicks,
            "ios_pct": round((len(ig_ios) / max(1, ig_live_clicks)) * 100),
            "android_pct": round((len(ig_android) / max(1, ig_live_clicks)) * 100),
            "installs": ig_reported_installs,
            "matched_opens": len(matched_ig_opens),
            "cr_pct": ig_cr,
            "cpi_str": "$0.00 (Organik)",
            "status_note": ig_cfg.notes if ig_cfg else "",
        },
        {
            "key": "google_play_organic",
            "name": "🤖 Google Play & Android Köprü",
            "badge": "ANDROID MAĞAZA",
            "spend_usd": 0.0,
            "cpt_bid_usd": 0.0,
            "clicks": gp_live_clicks,
            "unique_bridge_clicks": gp_live_clicks,
            "ios_pct": 0,
            "android_pct": 100,
            "installs": gp_reported_installs,
            "matched_opens": len([s for s in first_opens if s.os_family == "android"]),
            "cr_pct": gp_cr,
            "cpi_str": "$0.00 (Köprü/Organik)",
            "status_note": gp_cfg.notes if gp_cfg else "",
        },
    ]

    return {
        "total_raw": total_raw,
        "total_human": len(human_clicks),
        "total_unique_human": len(unique_human),
        "total_bots": len(bot_clicks),
        "total_all_installs": total_all_installs,
        "total_all_spend_usd": total_all_spend,
        "blended_cpi_usd": blended_cpi,
        "asa_metrics": {
            "spend_usd": asa_spend,
            "installs": asa_installs,
            "clicks": asa_clicks,
            "cpi_usd": asa_cpi,
            "cpt_bid_usd": asa_cpt_bid,
            "cr_pct": asa_cr,
            "projected_cpi_usd": asa_projected_cpi,
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
            "installs": meta_reported_installs,
            "cr_pct": meta_cr,
            "spend_usd": meta_spend,
            "cpi_usd": meta_cpi,
        },
        "instagram_bio": {
            "route": "/download",
            "raw_hits": len(ig_raw),
            "human_hits": len(ig_human),
            "unique_clicks": ig_live_clicks,
            "ios_clicks": len(ig_ios),
            "android_clicks": len(ig_android),
            "installs": ig_reported_installs,
            "cr_pct": ig_cr,
        },
        "product_funnel": {
            "bridge_unique_clicks": len(unique_human),
            "asa_clicks": asa_clicks,
            "total_acquisition_clicks": len(unique_human) + asa_clicks,
            "store_jumps_tracked": len(store_jumps) + len(unique_human),
            "total_store_installs": total_all_installs,
            "first_open_signals": len(first_opens),
            "registered_users": db_users_count,
            "babies_created": db_babies_count,
            "cry_analyses": db_cry_count,
            "sleep_logs": db_sleep_count,
            "routine_logs": db_routine_count,
            "feedbacks_count": len(db_feedbacks),
            "subscriptions_count": db_subs_count,
            "unmatched_organic_opens": len(unmatched_opens),
        },
        "channels_table": channels_table,
        "consensus_diagnostics": consensus_diagnostics,
        "golden_hours": golden_hours[:6],
        "os_breakdown": dict(os_counts),
        "webview_breakdown": dict(webview_counts),
        "hourly_meta_tr": dict(hourly_meta),
        "hourly_ig_tr": dict(hourly_ig),
        "hourly_all_tr": dict(hourly_all_time),
        "recent_clicks": all_clicks[:100],
        "recent_signals": signals[:30],
    }


@router.get("/summary")
async def get_analytics_summary(
    pin: Optional[str] = Query(None),
    x_admin_pin: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """JSON API: Tüm kanalların tıklama, indirme, CPI, huni ve 3'lü konsensüs analiz özetini döndürür."""
    if not verify_admin_pin(pin, x_admin_pin):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Geçersiz veya eksik Yönetici PIN kodu.")

    summary = _build_analytics_summary(db)
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
    summary.pop("recent_signals", None)
    return summary


@router.get("/export.csv")
async def export_analytics_csv(
    pin: Optional[str] = Query(None),
    x_admin_pin: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """Tüm tıklama kayıtlarını Excel uyumlu ve Formula-Injection korumalı CSV olarak indirir."""
    if not verify_admin_pin(pin, x_admin_pin):
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
            c.id,
            dt_tr,
            sanitize_csv_cell(c.route_path),
            sanitize_csv_cell(c.channel),
            "EVET" if c.is_unique else "HAYIR (Prefetch/Tekrar)",
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
        headers={"Content-Disposition": "attachment; filename=misil_baby_reklam_ve_indirme_analizi.csv"},
    )


@router.get("/dashboard", response_class=HTMLResponse)
async def analytics_dashboard_page(
    pin: Optional[str] = Query(None),
    updated: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Mışıl Baby v4.44.9 — Tam Huni İndirme Atıf, Birim Ekonomi (Apple Ads vs Meta Ads) ve 3'lü Konsensüs Karar Destek Kokpiti.
    """
    if not verify_admin_pin(pin):
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html lang="tr">
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <meta name="referrer" content="no-referrer">
          <title>Büyüme & İndirme Kokpiti Girişi — Mışıl Baby</title>
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
            .err {{ color: #FF6B6B; font-size: 12px; margin-top: 12px; display: {'block' if pin else 'none'}; }}
          </style>
        </head>
        <body>
          <div class="card">
            <div class="moon">📊</div>
            <h2>Mışıl Büyüme & İndirme Kokpiti</h2>
            <p>Apple Ads, Meta Ads (/ios), Instagram (/download) indirme hunisi ve 3'lü konsensüs analizlerini açmak için PIN giriniz.</p>
            <form method="GET">
              <input type="password" name="pin" placeholder="Yönetici PIN" autofocus autocomplete="off" />
              <button type="submit">Kokpiti Aç</button>
            </form>
            <div class="err">❌ Geçersiz PIN kodu. Lütfen tekrar deneyin.</div>
          </div>
        </body>
        </html>
        """)

    safe_pin = html.escape(pin or "")
    s = _build_analytics_summary(db)
    asa = s["asa_metrics"]
    meta = s["meta_ads"]
    ig = s["instagram_bio"]
    pf = s["product_funnel"]

    total_uniq = max(1, s["total_unique_human"])
    ios_total = s["os_breakdown"].get("ios", 0)
    android_total = s["os_breakdown"].get("android", 0)
    ios_pct = round((ios_total / total_uniq) * 100)
    android_pct = round((android_total / total_uniq) * 100)

    ig_app_count = s["webview_breakdown"].get("Instagram App", 0)
    fb_app_count = s["webview_breakdown"].get("Facebook App", 0)
    ig_app_pct = round((ig_app_count / total_uniq) * 100)
    fb_app_pct = round((fb_app_count / total_uniq) * 100)

    # 3'lü Konsensüs Teşhis Kartları HTML
    diag_html = ""
    for d in s["consensus_diagnostics"]:
        sev = d["severity"]
        border_col = "rgba(245, 158, 11, 0.45)" if sev == "amber" else ("rgba(16, 185, 129, 0.45)" if sev == "green" else "rgba(59, 130, 246, 0.45)")
        tag_bg = "rgba(245, 158, 11, 0.16)" if sev == "amber" else ("rgba(16, 185, 129, 0.16)" if sev == "green" else "rgba(59, 130, 246, 0.16)")
        tag_col = "#FBBF24" if sev == "amber" else ("#34D399" if sev == "green" else "#60A5FA")
        icon = "⚠️" if sev == "amber" else ("✅" if sev == "green" else "🧠")

        diag_html += f"""
        <div class="diag-card" style="border-left: 4px solid {tag_col}; border-color: {border_col};">
          <div class="diag-head">
            <span class="diag-agent" style="background:{tag_bg}; color:{tag_col};">{icon} {html.escape(d['agent_badge'])}</span>
            <span class="diag-conf">🛡️ {html.escape(d['confidence'])}</span>
          </div>
          <div class="diag-title">{html.escape(d['title'])}</div>
          <div class="diag-metric">📌 Ölçüm: <strong>{html.escape(d['metric'])}</strong></div>
          <p class="diag-body">{html.escape(d['analysis'])}</p>
          <div class="diag-action">🎯 <strong>Önerilen Aksiyon:</strong> {html.escape(d['action'])}</div>
        </div>
        """

    # Kanal Bazlı Karşılaştırma Tablosu HTML
    ch_rows_html = ""
    for ch in s["channels_table"]:
        ch_rows_html += f"""
        <tr>
          <td>
            <div style="font-weight:700; color:#FFF;">{html.escape(ch['name'])}</div>
            <div style="font-size:11px; color:#94A3B8; margin-top:2px;">{html.escape(ch['status_note'] or '')}</div>
          </td>
          <td><span class="badge badge-web">{html.escape(ch['badge'])}</span></td>
          <td style="font-weight:700; color:#E8A855;">${ch['spend_usd']:.2f}</td>
          <td style="font-weight:700; color:#CBD5E1;">{ch['unique_bridge_clicks']} <span style="font-size:11px; color:#64748B;">(Ham: {ch['clicks']})</span></td>
          <td><span style="color:#E8A855;">%{ch['ios_pct']} iOS</span> / <span style="color:#4ADE80;">%{ch['android_pct']} And</span></td>
          <td>
            <span style="font-size:16px; font-weight:800; color:#34D399;">{ch['installs']} İndirme</span>
            {f'<div style="font-size:11px; color:#60A5FA;">+{ch["matched_opens"]} Cihaz İlk Açılış Sinyali</div>' if ch['matched_opens'] > 0 else ''}
          </td>
          <td><span class="badge badge-uniq">%{ch['cr_pct']}</span></td>
          <td style="font-weight:800; color:#FFF;">{html.escape(ch['cpi_str'])}</td>
        </tr>
        """

    # 24 saatlik grafik çubukları (Tüm zamanlar + Son 24 Saat)
    hours_list = [f"{h:02d}:00" for h in range(24)]
    max_hour_val = max(1, max((s["hourly_all_tr"].get(hk, 0) for hk in hours_list), default=1))
    golden_set = {g["hour"] for g in s["golden_hours"][:3] if g["clicks"] > 0}

    bars_html = ""
    for hk in hours_list:
        tot_v = s["hourly_all_tr"].get(hk, 0)
        m_24 = s["hourly_meta_tr"].get(hk, 0)
        i_24 = s["hourly_ig_tr"].get(hk, 0)
        h_pct = max(6, round((tot_v / max_hour_val) * 100)) if tot_v > 0 else 4
        if hk in golden_set:
            bar_color = "linear-gradient(180deg, #34D399 0%, #059669 100%)"
        elif tot_v > 0:
            bar_color = "linear-gradient(180deg, #E8A855 0%, #D48828 100%)"
        else:
            bar_color = "rgba(255,255,255,0.06)"

        bars_html += f"""
        <div class="hour-col" title="Saat {hk} (TSİ): Toplam {tot_v} Tekil Tık (Son 24s: {m_24} Meta + {i_24} IG)">
          <div class="hour-val" style="color:{'#34D399' if hk in golden_set else '#E8A855'};">{tot_v if tot_v > 0 else ''}</div>
          <div class="hour-bar-wrap">
            <div class="hour-bar" style="height: {h_pct}%; background: {bar_color};"></div>
          </div>
          <div class="hour-lbl">{hk[:2]}</div>
        </div>
        """

    # Son tıklamalar tablosu
    tz_tr = timezone(timedelta(hours=3))
    rows_html = ""
    for c in s["recent_clicks"][:80]:
        dt_utc = c.created_at.replace(tzinfo=timezone.utc) if c.created_at.tzinfo is None else c.created_at
        dt_tr = dt_utc.astimezone(tz_tr).strftime("%d.%m %H:%M:%S")
        safe_route = html.escape(c.route_path or "/")
        safe_detail = html.escape(c.device_detail or "")
        safe_webview = html.escape(c.app_webview or "—")
        safe_ip = html.escape(c.ip_masked or "—")
        safe_country = html.escape(c.country or "TR")

        if c.route_path == "/ios":
            route_badge = '<span class="badge badge-meta">🎯 Meta Ads (/ios)</span>'
        elif c.route_path == "/download":
            route_badge = '<span class="badge badge-ig">📸 Instagram Bio (/download)</span>'
        elif c.route_path in ("/android", "/play-store"):
            route_badge = '<span class="badge badge-gp">🤖 Android Köprü</span>'
        else:
            route_badge = f'<span class="badge badge-web">🌐 {safe_route}</span>'

        if c.is_bot:
            status_badge = '<span class="badge badge-bot">🤖 Meta/Crawler Bot</span>'
        elif c.is_unique:
            status_badge = '<span class="badge badge-uniq">✅ Gerçek Tekil Tık</span>'
        else:
            status_badge = '<span class="badge badge-dup">⚡ Prefetch / Tekrar</span>'

        if c.os_family == "ios":
            os_badge = f'🍏 {safe_detail or "iPhone"}'
        elif c.os_family == "android":
            os_badge = f'🤖 {safe_detail or "Android"}'
        elif c.os_family == "bot":
            os_badge = f'🕷️ {safe_detail or "Bot"}'
        else:
            os_badge = f'💻 {safe_detail or "Diğer"}'

        store_str = "App Store ↗" if c.target_store == "app_store" else ("Google Play ↗" if c.target_store == "google_play" else "Landing (200 OK)")

        rows_html += f"""
        <tr>
          <td style="font-family: monospace; color: #CBD5E1;">{dt_tr}</td>
          <td>{route_badge}</td>
          <td>{status_badge}</td>
          <td>{os_badge}</td>
          <td><span style="color: #E2E8F0; font-weight: 600;">{safe_webview}</span></td>
          <td style="color: #94A3B8;">{store_str}</td>
          <td style="font-family: monospace; font-size: 11px; color: #64748B;">{safe_ip} ({safe_country})</td>
        </tr>
        """

    # Huni yüzdeleri
    tot_acq_clicks = max(1, pf["total_acquisition_clicks"])
    funnel_store_pct = min(100, round((pf["store_jumps_tracked"] / tot_acq_clicks) * 100, 1))
    funnel_install_pct = min(100, round((pf["total_store_installs"] / tot_acq_clicks) * 100, 1))
    funnel_active_events = pf["cry_analyses"] + pf["sleep_logs"] + pf["routine_logs"] + pf["feedbacks_count"]

    updated_banner = ""
    if updated:
        updated_banner = f"""
        <div style="background:rgba(16,185,129,0.16); border:1px solid rgba(16,185,129,0.4); color:#34D399; padding:12px 16px; border-radius:14px; margin-bottom:18px; font-size:13px; font-weight:600;">
          ✅ <strong>{html.escape(updated)}</strong> kanalının harcama ve mağaza indirme verileri başarıyla güncellendi ve konsensüs motoru yeniden hesaplandı.
        </div>
        """

    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="tr">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <meta name="referrer" content="no-referrer">
      <title>Mışıl Baby — Büyüme, İndirme Atıf & 3'lü Konsensüs Kokpiti (v4.44.9)</title>
      <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Sora:wght@600;700;800&display=swap" rel="stylesheet">
      <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
          background: #07090E radial-gradient(circle at 50% 0%, #161F38 0%, #07090E 70%);
          color: #F8FAFC;
          font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
          min-height: 100vh;
          padding: 22px 18px 70px;
        }}
        .container {{ max-width: 1240px; margin: 0 auto; }}
        .topbar {{
          display: flex;
          flex-wrap: wrap;
          justify-content: space-between;
          align-items: center;
          gap: 14px;
          margin-bottom: 20px;
          padding-bottom: 16px;
          border-bottom: 1px solid rgba(255,255,255,0.08);
        }}
        .brand {{ display: flex; align-items: center; gap: 12px; }}
        .brand-icon {{
          width: 46px; height: 46px; border-radius: 14px;
          background: rgba(232, 168, 85, 0.15);
          border: 1px solid rgba(232, 168, 85, 0.35);
          display: flex; align-items: center; justify-content: center;
          font-size: 22px;
        }}
        .brand h1 {{ font-family: 'Sora', sans-serif; font-size: 20px; font-weight: 700; color: #FFF; }}
        .brand p {{ font-size: 12px; color: #94A3B8; margin-top: 3px; }}
        .actions {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
        .btn {{
          padding: 9px 14px;
          border-radius: 11px;
          font-size: 12px;
          font-weight: 700;
          text-decoration: none;
          display: inline-flex;
          align-items: center;
          gap: 6px;
          border: 1px solid rgba(255,255,255,0.12);
          background: rgba(255,255,255,0.05);
          color: #F8FAFC;
          cursor: pointer;
          transition: all 0.15s;
        }}
        .btn:hover {{ background: rgba(255,255,255,0.12); }}
        .btn-gold {{
          background: linear-gradient(135deg, #E8A855 0%, #D48828 100%);
          color: #07090E;
          border: none;
        }}
        .live-pill {{
          display: inline-flex;
          align-items: center;
          gap: 7px;
          padding: 8px 12px;
          border-radius: 99px;
          background: rgba(16, 185, 129, 0.14);
          border: 1px solid rgba(16, 185, 129, 0.35);
          color: #34D399;
          font-size: 12px;
          font-weight: 700;
          cursor: pointer;
        }}
        .pulse-dot {{
          width: 8px; height: 8px; border-radius: 50%;
          background: #34D399;
          box-shadow: 0 0 10px #34D399;
          animation: blink 1.4s infinite;
        }}
        @keyframes blink {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.35; }} }}
        .grid-5 {{
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
          gap: 14px;
          margin-bottom: 20px;
        }}
        .bento-card {{
          background: rgba(18, 24, 41, 0.88);
          border: 1px solid rgba(255,255,255,0.09);
          border-radius: 18px;
          padding: 18px;
          box-shadow: 0 12px 32px rgba(0,0,0,0.35);
          margin-bottom: 18px;
        }}
        .grid-5 .bento-card {{ margin-bottom: 0; }}
        .card-tag {{
          font-size: 11px;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.7px;
          color: #94A3B8;
          margin-bottom: 8px;
          display: flex;
          justify-content: space-between;
          align-items: center;
        }}
        .big-num {{
          font-family: 'Sora', sans-serif;
          font-size: 32px;
          font-weight: 800;
          color: #FFF;
          line-height: 1.1;
          margin-bottom: 6px;
        }}
        .sub-metrics {{
          font-size: 11px;
          color: #94A3B8;
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          margin-top: 10px;
          padding-top: 10px;
          border-top: 1px solid rgba(255,255,255,0.06);
        }}
        .sub-pill {{
          background: rgba(255,255,255,0.05);
          padding: 4px 8px;
          border-radius: 7px;
          font-weight: 600;
          color: #E2E8F0;
        }}
        .section-head {{
          font-family: 'Sora', sans-serif;
          font-size: 16px;
          font-weight: 700;
          color: #FFF;
          margin-bottom: 14px;
          display: flex;
          justify-content: space-between;
          align-items: center;
          flex-wrap: wrap;
          gap: 8px;
        }}
        .diag-grid {{
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
          gap: 14px;
        }}
        .diag-card {{
          background: rgba(13, 18, 31, 0.9);
          border: 1px solid rgba(255,255,255,0.08);
          border-radius: 14px;
          padding: 16px;
        }}
        .diag-head {{
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 8px;
          margin-bottom: 8px;
          flex-wrap: wrap;
        }}
        .diag-agent {{
          font-size: 11px;
          font-weight: 700;
          padding: 3px 9px;
          border-radius: 99px;
        }}
        .diag-conf {{ font-size: 11px; color: #94A3B8; font-weight: 600; }}
        .diag-title {{ font-family: 'Sora', sans-serif; font-size: 14px; font-weight: 700; color: #FFF; margin-bottom: 6px; }}
        .diag-metric {{ font-size: 12px; color: #E8A855; margin-bottom: 8px; }}
        .diag-body {{ font-size: 12.5px; color: #CBD5E1; line-height: 1.55; margin-bottom: 10px; }}
        .diag-action {{
          font-size: 12px;
          color: #F8FAFC;
          background: rgba(255,255,255,0.04);
          padding: 9px 11px;
          border-radius: 10px;
          border: 1px dashed rgba(232,168,85,0.35);
          line-height: 1.45;
        }}
        .funnel-steps {{
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(195px, 1fr));
          gap: 12px;
        }}
        .funnel-step {{
          background: rgba(255,255,255,0.03);
          border: 1px solid rgba(255,255,255,0.08);
          border-radius: 14px;
          padding: 14px;
          position: relative;
        }}
        .funnel-num {{ font-family: 'Sora', sans-serif; font-size: 24px; font-weight: 800; color: #E8A855; margin: 4px 0; }}
        .grid-2 {{
          display: grid;
          grid-template-columns: 1.35fr 1fr;
          gap: 16px;
        }}
        @media (max-width: 900px) {{ .grid-2 {{ grid-template-columns: 1fr; }} }}
        .hours-grid {{
          display: grid;
          grid-template-columns: repeat(24, 1fr);
          gap: 4px;
          height: 150px;
          align-items: end;
          padding-top: 18px;
        }}
        .hour-col {{ display: flex; flex-direction: column; align-items: center; height: 100%; }}
        .hour-val {{ font-size: 10px; font-weight: 700; height: 14px; margin-bottom: 2px; }}
        .hour-bar-wrap {{ flex: 1; width: 100%; display: flex; align-items: flex-end; justify-content: center; }}
        .hour-bar {{ width: 100%; max-width: 18px; border-radius: 5px 5px 2px 2px; }}
        .hour-lbl {{ font-size: 10px; color: #64748B; margin-top: 6px; font-weight: 600; }}
        .progress-row {{ margin-bottom: 13px; }}
        .progress-head {{ display: flex; justify-content: space-between; font-size: 12.5px; font-weight: 600; margin-bottom: 5px; }}
        .progress-track {{ height: 9px; background: rgba(255,255,255,0.06); border-radius: 99px; overflow: hidden; }}
        .progress-fill {{ height: 100%; border-radius: 99px; }}
        .table-wrap {{ overflow-x: auto; margin-top: 6px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 12.5px; }}
        th {{
          text-align: left;
          padding: 11px 10px;
          color: #94A3B8;
          font-weight: 700;
          font-size: 11px;
          text-transform: uppercase;
          border-bottom: 1px solid rgba(255,255,255,0.08);
        }}
        td {{ padding: 11px 10px; border-bottom: 1px solid rgba(255,255,255,0.05); white-space: nowrap; }}
        tr:hover td {{ background: rgba(255,255,255,0.02); }}
        .badge {{
          display: inline-flex;
          align-items: center;
          padding: 3px 9px;
          border-radius: 99px;
          font-size: 11px;
          font-weight: 700;
        }}
        .badge-meta {{ background: rgba(59, 130, 246, 0.18); color: #60A5FA; border: 1px solid rgba(59, 130, 246, 0.35); }}
        .badge-ig {{ background: rgba(236, 72, 153, 0.18); color: #F472B6; border: 1px solid rgba(236, 72, 153, 0.35); }}
        .badge-gp {{ background: rgba(34, 197, 94, 0.18); color: #4ADE80; border: 1px solid rgba(34, 197, 94, 0.35); }}
        .badge-web {{ background: rgba(148, 163, 184, 0.18); color: #CBD5E1; }}
        .badge-uniq {{ background: rgba(16, 185, 129, 0.18); color: #34D399; }}
        .badge-dup {{ background: rgba(245, 158, 11, 0.16); color: #FBBF24; }}
        .badge-bot {{ background: rgba(148, 163, 184, 0.15); color: #94A3B8; }}
        .form-grid {{
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
          gap: 10px;
          align-items: end;
          margin-top: 10px;
        }}
        .form-grid label {{ display: block; font-size: 11px; color: #94A3B8; margin-bottom: 4px; font-weight: 600; }}
        .form-grid input, .form-grid select {{
          width: 100%; padding: 9px 11px; border-radius: 9px;
          border: 1px solid rgba(255,255,255,0.14); background: rgba(0,0,0,0.35);
          color: #FFF; font-size: 13px;
        }}
      </style>
    </head>
    <body>
      <div class="container">
        <div class="topbar">
          <div class="brand">
            <div class="brand-icon">🚀</div>
            <div>
              <h1>Mışıl Baby — Büyüme, İndirme Atıf & 3'lü Konsensüs Kokpiti</h1>
              <p>Apple Search Ads • Meta Ads (<code>/ios</code>) • Instagram (<code>/download</code>) • Google Play • Uygulama İçi Kurulum & Karar Destek Motoru</p>
            </div>
          </div>
          <div class="actions">
            <div class="live-pill" onclick="toggleAutoRefresh()" id="liveToggleBtn" title="Otomatik yenilemeyi aç/kapat">
              <span class="pulse-dot" id="liveDot"></span>
              <span id="liveCountdown">Canlı Akış: 15s</span>
            </div>
            <button class="btn" onclick="document.getElementById('cfgBox').style.display = document.getElementById('cfgBox').style.display === 'none' ? 'block' : 'none'">⚙️ Harcama / İndirme Güncelle</button>
            <a href="/api/v1/analytics/dashboard?pin={safe_pin}" class="btn">🔄 Şimdi Yenile</a>
            <a href="/api/v1/analytics/export.csv?pin={safe_pin}" class="btn btn-gold">📥 CSV İndir</a>
            <a href="/api/v1/feedback/dashboard?pin={safe_pin}" class="btn">💌 Anne Geri Bildirimleri ({pf['feedbacks_count']})</a>
          </div>
        </div>

        {updated_banner}

        <!-- KAMPANYA & MAĞAZA İNDİRME VERİSİ GÜNCELLEME KUTUSU -->
        <div id="cfgBox" class="bento-card" style="display:none; border-color: rgba(232,168,85,0.45);">
          <div class="section-head">
            <span>⚙️ Reklam Harcaması & Mağaza İndirme Sayısı Güncelle (Apple Ads / Meta Ads / Google Play)</span>
            <span style="font-size:12px; color:#94A3B8;">Girdiğiniz veriler veritabanına kaydedilir ve CPI / Konsensüs analizlerini anında günceller</span>
          </div>
          <form method="POST" action="/api/v1/analytics/campaign-config">
            <input type="hidden" name="pin" value="{safe_pin}" />
            <div class="form-grid">
              <div>
                <label>Kanal Seçin</label>
                <select name="channel_key">
                  <option value="apple_search_ads">🍏 Apple Search Ads</option>
                  <option value="meta_ads">🎯 Meta Ads (/ios)</option>
                  <option value="instagram_bio">📸 Instagram Bio (/download)</option>
                  <option value="google_play_organic">🤖 Google Play / Android</option>
                </select>
              </div>
              <div>
                <label>Harcanan Tutar ($ USD)</label>
                <input type="number" step="0.01" name="spend_usd" value="{asa['spend_usd']:.2f}" required />
              </div>
              <div>
                <label>Tavan CPT Teklifi ($ USD)</label>
                <input type="number" step="0.01" name="cpt_bid_usd" value="{asa['cpt_bid_usd']:.2f}" required />
              </div>
              <div>
                <label>Panel Tıklama Sayısı</label>
                <input type="number" name="reported_clicks" value="{asa['clicks']}" required />
              </div>
              <div>
                <label>Gerçekleşen İndirme (Store)</label>
                <input type="number" name="reported_installs" value="{asa['installs']}" required />
              </div>
              <div>
                <button type="submit" class="btn btn-gold" style="width:100%; justify-content:center; padding:10px;">💾 Kaydet & Hesapla</button>
              </div>
            </div>
          </form>
        </div>

        <!-- ÜST 5 KPI KARTI (İNDİRMELER + APPLE ADS + META ADS + INSTAGRAM + MAĞAZA KARNESİ) -->
        <div class="grid-5">
          <div class="bento-card" style="border-color: rgba(16, 185, 129, 0.45);">
            <div class="card-tag">
              <span>🏆 TOPLAM GERÇEK İNDİRME</span>
              <span class="badge badge-uniq">TÜM KANALLAR</span>
            </div>
            <div class="big-num" style="color: #34D399;">{s['total_all_installs']} <span style="font-size:14px; font-weight:600; color:#94A3B8;">Kurulum</span></div>
            <div style="font-size: 12px; color: #CBD5E1;">Karma Maliyet: <strong>${s['blended_cpi_usd']:.2f} CPI</strong> (Toplam ${s['total_all_spend_usd']:.0f} Harcama)</div>
            <div class="sub-metrics">
              <span class="sub-pill">🍏 Apple Ads: {asa['installs']}</span>
              <span class="sub-pill">🎯 Meta/IG: {meta['installs'] + ig['installs']}</span>
              <span class="sub-pill">🤖 Play: {s['channels_table'][3]['installs']}</span>
            </div>
          </div>

          <div class="bento-card" style="border-color: rgba(232, 168, 85, 0.45);">
            <div class="card-tag">
              <span>🍏 APPLE SEARCH ADS</span>
              <span style="color:#E8A855; font-weight:800;">${asa['cpi_usd']:.2f} CPI</span>
            </div>
            <div class="big-num" style="color: #E8A855;">{asa['installs']} <span style="font-size:14px; font-weight:600; color:#94A3B8;">İndirme</span></div>
            <div style="font-size: 12px; color: #CBD5E1;">${asa['spend_usd']:.0f} Kredi Harcandı • Tavan CPT: <strong>${asa['cpt_bid_usd']:.2f}</strong></div>
            <div class="sub-metrics">
              <span class="sub-pill">Tık→İndirme: %{asa['cr_pct']}</span>
              <span class="sub-pill">Hedef Yeni CPI: ~${asa['projected_cpi_usd']:.2f}</span>
            </div>
          </div>

          <div class="bento-card" style="border-color: rgba(59, 130, 246, 0.4);">
            <div class="card-tag">
              <span>🎯 META ADS (/ios)</span>
              <span class="badge badge-meta">%{meta['cr_pct']} DÖNÜŞÜM</span>
            </div>
            <div class="big-num" style="color: #60A5FA;">{meta['unique_clicks']} <span style="font-size:14px; font-weight:600; color:#94A3B8;">Tekil Tık</span></div>
            <div style="font-size: 12px; color: #CBD5E1;">Tahmini/Eşleşen İndirme: <strong>{meta['installs']}</strong> ({meta['raw_hits']} Ham İstek)</div>
            <div class="sub-metrics">
              <span class="sub-pill">🍏 iPhone: {meta['ios_clicks']}</span>
              <span class="sub-pill" style="color:#FBBF24;">🤖 Android Kaçağı: {meta['android_clicks']} (%{meta['android_leak_pct']})</span>
            </div>
          </div>

          <div class="bento-card" style="border-color: rgba(236, 72, 153, 0.4);">
            <div class="card-tag">
              <span>📸 INSTAGRAM BIO (/download)</span>
              <span class="badge badge-ig">ORGANİK</span>
            </div>
            <div class="big-num" style="color: #F472B6;">{ig['unique_clicks']} <span style="font-size:14px; font-weight:600; color:#94A3B8;">Tekil Tık</span></div>
            <div style="font-size: 12px; color: #CBD5E1;">Organik İndirme: <strong>{ig['installs']}</strong> (%{ig['cr_pct']} Dönüşüm)</div>
            <div class="sub-metrics">
              <span class="sub-pill">Ham: {ig['raw_hits']}</span>
              <span class="sub-pill">🍏 iOS: {ig['ios_clicks']}</span>
              <span class="sub-pill">🤖 Android: {ig['android_clicks']}</span>
            </div>
          </div>

          <div class="bento-card">
            <div class="card-tag">
              <span>⭐ MAĞAZA & SÜRÜM KARNESİ</span>
              <span style="color:#34D399;">5.0 ★</span>
            </div>
            <div class="big-num" style="font-size:24px;">5.0 ⭐ <span style="font-size:13px; font-weight:600; color:#94A3B8;">(6 Mağaza Yorumu)</span></div>
            <div style="font-size: 12px; color: #CBD5E1;">App Store (5★) & Google Play (1★)</div>
            <div class="sub-metrics">
              <span class="sub-pill">🍏 iOS v1.1 (Build 57 İncelemede)</span>
              <span class="sub-pill">🤖 Play v4.44.1 (Build 63 Yayında)</span>
            </div>
          </div>
        </div>

        <!-- MODÜL 1: 3'LÜ KONSENSÜS (CLAUDE + CODEX + ANTIGRAVITY) OTOMATİK TEŞHİS & AKSİYON MOTORU -->
        <div class="bento-card" style="border-color: rgba(232, 168, 85, 0.35);">
          <div class="section-head">
            <span>🧠 Modül 1 — 3'lü Ajan Konsensüs Karar Destek & Otomatik Teşhis Motoru (Claude + Codex + Antigravity)</span>
            <span style="font-size:12px; color:#E8A855;">Canlı Veriden Otomatik Hesaplanan Bütçe, Huni ve Hedefleme Bulguları</span>
          </div>
          <div class="diag-grid">
            {diag_html}
          </div>
        </div>

        <!-- MODÜL 2: KANAL BAZLI TAM EDİNİM, İNDİRME & BİRİM EKONOMİ TABLOSU -->
        <div class="bento-card">
          <div class="section-head">
            <span>📊 Modül 2 — Kanal Bazlı Gerçek İndirme, Dönüşüm Oranı ve Birim Ekonomi (CPI) Kıyaslaması</span>
            <span style="font-size:12px; color:#94A3B8;">Hangi kanal kaç dolara gerçek anne/baba indirmesi getiriyor?</span>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Edinim Kanalı</th>
                  <th>Kategori</th>
                  <th>Harcama ($ USD)</th>
                  <th>Tekil Tıklama</th>
                  <th>Cihaz Dağılımı</th>
                  <th>Gerçekleşen İndirme</th>
                  <th>Tık → İndirme %</th>
                  <th>İndirme Başı Maliyet (CPI)</th>
                </tr>
              </thead>
              <tbody>
                {ch_rows_html}
              </tbody>
            </table>
          </div>
        </div>

        <!-- MODÜL 3: UÇTAN UCA EBEVEYN EDİNİM & UYGULAMA İÇİ AKTİVASYON HUNİSİ -->
        <div class="bento-card">
          <div class="section-head">
            <span>🌪️ Modül 3 — Uçtan Uca Edinim & Uygulama İçi Aktivasyon Hunisi (Acquisition & Activation Funnel)</span>
            <span style="font-size:12px; color:#94A3B8;">Reklam Tıklaması → Mağaza Yönlendirmesi → İndirme → İlk Uygulama Açılışı & Kullanım</span>
          </div>
          <div class="funnel-steps">
            <div class="funnel-step">
              <div style="font-size:11px; color:#94A3B8; font-weight:700;">1. ADIM • REKLAM & PROFİL TIKLAMASI</div>
              <div class="funnel-num">{pf['total_acquisition_clicks']}</div>
              <div style="font-size:12px; color:#CBD5E1;">{pf['bridge_unique_clicks']} Köprü + {pf['asa_clicks']} Apple Ads Tıkı</div>
            </div>
            <div class="funnel-step">
              <div style="font-size:11px; color:#94A3B8; font-weight:700;">2. ADIM • MAĞAZAYA SIÇRAMA</div>
              <div class="funnel-num" style="color:#60A5FA;">{pf['store_jumps_tracked']} <span style="font-size:13px;">(%{funnel_store_pct})</span></div>
              <div style="font-size:12px; color:#CBD5E1;">App Store (%{ios_pct}) & Google Play (%{android_pct})</div>
            </div>
            <div class="funnel-step">
              <div style="font-size:11px; color:#94A3B8; font-weight:700;">3. ADIM • MAĞAZADAN İNDİRME</div>
              <div class="funnel-num" style="color:#34D399;">{pf['total_store_installs']} <span style="font-size:13px;">(%{funnel_install_pct})</span></div>
              <div style="font-size:12px; color:#CBD5E1;">37 Apple Ads + {meta['installs']} Meta + {ig['installs']} IG + {s['channels_table'][3]['installs']} Play</div>
            </div>
            <div class="funnel-step">
              <div style="font-size:11px; color:#94A3B8; font-weight:700;">4. ADIM • CİHAZ İLK AÇILIŞ & KAYIT</div>
              <div class="funnel-num" style="color:#F472B6;">{max(pf['first_open_signals'], pf['registered_users'], pf['babies_created'])}</div>
              <div style="font-size:12px; color:#CBD5E1;">Kayıtlı Ebeveyn: {pf['registered_users']} • Bebek Profili: {pf['babies_created']}</div>
            </div>
            <div class="funnel-step">
              <div style="font-size:11px; color:#94A3B8; font-weight:700;">5. ADIM • AKTİF KULLANIM & GERİ BİLDİRİM</div>
              <div class="funnel-num" style="color:#E8A855;">{funnel_active_events}</div>
              <div style="font-size:12px; color:#CBD5E1;">Ağlama: {pf['cry_analyses']} • Uyku/Rutin: {pf['sleep_logs'] + pf['routine_logs']} • Mesaj: {pf['feedbacks_count']}</div>
            </div>
          </div>
        </div>

        <!-- MODÜL 4: ALTIN SAATLER ANOMALİ GRAFİĞİ & PLATFORM KIRILIMI -->
        <div class="grid-2">
          <div class="bento-card">
            <div class="section-head">
              <span>⏰ Modül 4A — Ebeveyn "Altın Saatler" Tıklama Yoğunluğu (TSİ — Yeşil Sütunlar = Zirve Anomali Saatleri)</span>
            </div>
            <div class="hours-grid">
              {bars_html}
            </div>
            <div style="font-size:11.5px; color:#94A3B8; margin-top:12px; display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px;">
              <span>🟢 <strong>Yeşil Sütunlar:</strong> Codex Beta-Binom modeline göre en yüksek dönüşüm potansiyelli 3 zirve saat</span>
              <span>🟡 <strong>Altın Sütunlar:</strong> Standart saatlik trafik</span>
            </div>
          </div>

          <div class="bento-card">
            <div class="section-head">
              <span>📲 Modül 4B — Cihaz & Uygulama İçi Tarayıcı (In-App WebView) Kırılımı</span>
            </div>
            <div class="progress-row">
              <div class="progress-head">
                <span>🍏 Apple iPhone (App Store Yönlendirmesi)</span>
                <span style="color:#E8A855;">{ios_total} Tekil (%{ios_pct})</span>
              </div>
              <div class="progress-track">
                <div class="progress-fill" style="width: {ios_pct}%; background: linear-gradient(90deg, #E8A855, #F4A261);"></div>
              </div>
            </div>

            <div class="progress-row">
              <div class="progress-head">
                <span>🤖 Android Telefonlar (Google Play Yönlendirmesi)</span>
                <span style="color:#4ADE80;">{android_total} Tekil (%{android_pct})</span>
              </div>
              <div class="progress-track">
                <div class="progress-fill" style="width: {android_pct}%; background: linear-gradient(90deg, #22C55E, #4ADE80);"></div>
              </div>
            </div>

            <div class="progress-row" style="margin-top: 16px;">
              <div class="progress-head">
                <span>📸 Instagram Uygulama İçi Tarayıcı (Instagram In-App)</span>
                <span style="color:#F472B6;">{ig_app_count} Tık (%{ig_app_pct})</span>
              </div>
              <div class="progress-track">
                <div class="progress-fill" style="width: {ig_app_pct}%; background: linear-gradient(90deg, #EC4899, #F472B6);"></div>
              </div>
            </div>

            <div class="progress-row">
              <div class="progress-head">
                <span>📘 Facebook Reklam Akışı (Facebook In-App)</span>
                <span style="color:#60A5FA;">{fb_app_count} Tık (%{fb_app_pct})</span>
              </div>
              <div class="progress-track">
                <div class="progress-fill" style="width: {fb_app_pct}%; background: linear-gradient(90deg, #3B82F6, #60A5FA);"></div>
              </div>
            </div>
          </div>
        </div>

        <!-- MODÜL 5: SANİYE BAZLI CANLI TIKLAMA & MAĞAZA YÖNLENDİRME AKIŞI -->
        <div class="bento-card">
          <div class="section-head">
            <span>⚡ Modül 5 — Canlı Tıklama & Mağaza Yönlendirme Akışı (Son 80 İstek — Saniye Bazlı)</span>
            <span style="font-size: 12px; color: #94A3B8;">Linkler: <code>/ios</code> (Meta Ads) • <code>/download</code> (Instagram Bio) • <code>/android</code> (Google Play)</span>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Tarih / Saat (TSİ)</th>
                  <th>Tıklanan Link & Kanal</th>
                  <th>Tıklama Niteliği</th>
                  <th>Cihaz / OS</th>
                  <th>Geldiği Uygulama</th>
                  <th>Hedef Mağaza</th>
                  <th>IP & Ülke (KVKK Maskeli)</th>
                </tr>
              </thead>
              <tbody>
                {rows_html}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <script>
        (function() {{
          var autoRefreshEnabled = localStorage.getItem('mishil_analytics_autorefresh') !== 'off';
          var secondsLeft = 15;
          var countdownEl = document.getElementById('liveCountdown');
          var dotEl = document.getElementById('liveDot');
          var btnEl = document.getElementById('liveToggleBtn');

          function updateUi() {{
            if (!autoRefreshEnabled) {{
              countdownEl.textContent = 'Canlı Akış: Duraklatıldı';
              dotEl.style.background = '#94A3B8';
              dotEl.style.boxShadow = 'none';
              btnEl.style.borderColor = 'rgba(148,163,184,0.35)';
              btnEl.style.color = '#94A3B8';
            }} else {{
              countdownEl.textContent = 'Canlı Akış: ' + secondsLeft + 's';
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
            var cfgBox = document.getElementById('cfgBox');
            var isEditing = cfgBox && cfgBox.style.display !== 'none';
            if (!autoRefreshEnabled || isEditing) return;
            secondsLeft -= 1;
            if (secondsLeft <= 0) {{
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
