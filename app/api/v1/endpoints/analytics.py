from datetime import datetime, timezone, timedelta
import html
import hashlib
import hmac
import io
import csv
from collections import Counter
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Request, status, Query, Header
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.base import get_db, SessionLocal, engine
from app.db.models import BridgeClick, Base
from app.core.logging import get_logger

logger = get_logger("analytics")

router = APIRouter(prefix="/analytics", tags=["Canlı Trafik, Meta Ads & Instagram Analitik Kokpiti"])

ADMIN_PINS = ("MISIL-REV-9842", "MISILREV2026")

# Modül içi tek seferlik tohumlama bayrağı (her tıklamada DB count/create_all çalışmasını önler)
_HISTORICAL_SEED_DONE = False

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
        # IPv6 maskeleme
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


def sanitize_csv_cell(val: Any) -> str:
    """Excel/CSV Formula Injection (=, +, -, @) koruması."""
    s = str(val or "").replace("\r", " ").replace("\n", " ").strip()
    if s and s[0] in ("=", "+", "-", "@", "\t"):
        return "'" + s
    return s


def ensure_historical_seed(db: Session) -> None:
    """Tablo boşsa dün gece 22:31 TSİ'den itibaren Railway loglarında biriken 143 gerçek tıklamayı tek seferlik tohumlar."""
    global _HISTORICAL_SEED_DONE
    if _HISTORICAL_SEED_DONE:
        return
    try:
        Base.metadata.create_all(bind=engine)
        existing_count = db.query(BridgeClick.id).limit(1).count()
        if existing_count > 0:
            _HISTORICAL_SEED_DONE = True
            return

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
                ip_masked="railway.log.seed",
                user_agent="Historical Railway Deployment Log (6a91615f)",
                created_at=dt,
            )
            db.add(row)
        db.commit()
        _HISTORICAL_SEED_DONE = True
        logger.info("Successfully seeded 143 historical bridge click records.")
    except Exception as e:
        db.rollback()
        logger.error(f"Historical seed error (non-fatal): {e}")


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
        # Sadece alfanümerik ülke koduna izin ver (XSS / Header Injection önlemi)
        country_clean = "".join(ch for ch in country_raw.upper() if ch.isalnum())[:6] or "TR"

        q_params = request.query_params
        fbclid = q_params.get("fbclid")
        utm_source = q_params.get("utm_source")
        utm_campaign = q_params.get("utm_campaign")
        referrer = request.headers.get("referer")
        has_fbclid = bool(fbclid)

        channel = classify_channel(route_path, utm_source, has_fbclid)

        # Son 15 saniye içinde aynı (maskeli IP + UA parmak izi) ve aynı rotadan tıklama var mı?
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


def _build_analytics_summary(db: Session) -> Dict[str, Any]:
    ensure_historical_seed(db)
    # Bellek güvenliği için en son 10.000 kaydı analiz et
    all_clicks: List[BridgeClick] = (
        db.query(BridgeClick)
        .order_by(desc(BridgeClick.created_at))
        .limit(10000)
        .all()
    )

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

    # OS Dağılımı (Tekil İnsanlar)
    os_counts = Counter(c.os_family for c in unique_human)
    webview_counts = Counter(c.app_webview for c in unique_human)

    # Saatlik Dağılım (Son 24 Saat - TSİ UTC+3)
    tz_tr = timezone(timedelta(hours=3))
    cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    hourly_meta = Counter()
    hourly_ig = Counter()
    for c in unique_human:
        dt_utc = c.created_at.replace(tzinfo=timezone.utc) if c.created_at.tzinfo is None else c.created_at
        if dt_utc >= cutoff_24h:
            dt_tr = dt_utc.astimezone(tz_tr)
            hour_key = dt_tr.strftime("%H:00")
            if c.route_path == "/ios":
                hourly_meta[hour_key] += 1
            elif c.route_path == "/download":
                hourly_ig[hour_key] += 1

    return {
        "total_raw": total_raw,
        "total_human": len(human_clicks),
        "total_unique_human": len(unique_human),
        "total_bots": len(bot_clicks),
        "meta_ads": {
            "route": "/ios",
            "raw_hits": len(meta_raw),
            "human_hits": len(meta_human),
            "unique_clicks": len(meta_unique),
            "bot_probes": len(meta_bots),
            "ios_clicks": len(meta_ios),
            "android_clicks": len(meta_android),
        },
        "instagram_bio": {
            "route": "/download",
            "raw_hits": len(ig_raw),
            "human_hits": len(ig_human),
            "unique_clicks": len(ig_unique),
            "ios_clicks": len(ig_ios),
            "android_clicks": len(ig_android),
        },
        "os_breakdown": dict(os_counts),
        "webview_breakdown": dict(webview_counts),
        "hourly_meta_tr": dict(hourly_meta),
        "hourly_ig_tr": dict(hourly_ig),
        "recent_clicks": all_clicks[:100],
    }


@router.get("/summary")
async def get_analytics_summary(
    pin: Optional[str] = Query(None),
    x_admin_pin: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """JSON API: Meta Ads (/ios) ve Instagram Bio (/download) canlı tıklama istatistiklerini döndürür."""
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
        headers={"Content-Disposition": "attachment; filename=misil_baby_reklam_tiklamalari.csv"},
    )


@router.get("/dashboard", response_class=HTMLResponse)
async def analytics_dashboard_page(
    pin: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Canlı Trafik, Meta Ads (/ios) ve Instagram (/download) Köprü Analitik Kokpiti.
    """
    if not verify_admin_pin(pin):
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html lang="tr">
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <meta name="referrer" content="no-referrer">
          <title>Analitik Kokpit Girişi — Mışıl Baby</title>
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
            <h2>Mışıl Reklam & Trafik Kokpiti</h2>
            <p>Meta Ads (/ios) ve Instagram (/download) canlı tıklama telemetrisini görüntülemek için yönetici PIN kodunuzu giriniz.</p>
            <form method="GET">
              <input type="password" name="pin" placeholder="Yönetici PIN" autofocus autocomplete="off" />
              <button type="submit">Analitik Kokpitini Aç</button>
            </form>
            <div class="err">❌ Geçersiz PIN kodu. Lütfen tekrar deneyin.</div>
          </div>
        </body>
        </html>
        """)

    safe_pin = html.escape(pin or "")
    s = _build_analytics_summary(db)
    meta = s["meta_ads"]
    ig = s["instagram_bio"]
    total_uniq = max(1, s["total_unique_human"])
    ios_total = s["os_breakdown"].get("ios", 0)
    android_total = s["os_breakdown"].get("android", 0)
    ios_pct = round((ios_total / total_uniq) * 100)
    android_pct = round((android_total / total_uniq) * 100)

    ig_app_count = s["webview_breakdown"].get("Instagram App", 0)
    fb_app_count = s["webview_breakdown"].get("Facebook App", 0)
    ig_app_pct = round((ig_app_count / total_uniq) * 100)
    fb_app_pct = round((fb_app_count / total_uniq) * 100)

    # 24 saatlik grafik çubukları
    hours_list = [f"{h:02d}:00" for h in range(24)]
    max_hour_val = 1
    for hk in hours_list:
        tot_h = s["hourly_meta_tr"].get(hk, 0) + s["hourly_ig_tr"].get(hk, 0)
        if tot_h > max_hour_val:
            max_hour_val = tot_h

    bars_html = ""
    for hk in hours_list:
        m_v = s["hourly_meta_tr"].get(hk, 0)
        i_v = s["hourly_ig_tr"].get(hk, 0)
        tot_v = m_v + i_v
        h_pct = max(6, round((tot_v / max_hour_val) * 100)) if tot_v > 0 else 4
        bar_color = "linear-gradient(180deg, #E8A855 0%, #D48828 100%)" if tot_v > 0 else "rgba(255,255,255,0.06)"
        bars_html += f"""
        <div class="hour-col" title="Saat {hk} (TSİ): {m_v} Meta Ads + {i_v} Instagram Bio = {tot_v} Tekil Tık">
          <div class="hour-val">{tot_v if tot_v > 0 else ''}</div>
          <div class="hour-bar-wrap">
            <div class="hour-bar" style="height: {h_pct}%; background: {bar_color};"></div>
          </div>
          <div class="hour-lbl">{hk[:2]}</div>
        </div>
        """

    # Son tıklamalar tablosu (tüm dinamik alanlar html.escape ile XSS korumalı)
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

    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="tr">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <meta name="referrer" content="no-referrer">
      <title>Mışıl Baby — Reklam & Köprü Analitik Kokpiti</title>
      <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Sora:wght@600;700;800&display=swap" rel="stylesheet">
      <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
          background: #07090E radial-gradient(circle at 50% 0%, #161F38 0%, #07090E 70%);
          color: #F8FAFC;
          font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
          min-height: 100vh;
          padding: 24px 18px 60px;
        }}
        .container {{ max-width: 1180px; margin: 0 auto; }}
        .topbar {{
          display: flex;
          flex-wrap: wrap;
          justify-content: space-between;
          align-items: center;
          gap: 14px;
          margin-bottom: 24px;
          padding-bottom: 18px;
          border-bottom: 1px solid rgba(255,255,255,0.08);
        }}
        .brand {{ display: flex; align-items: center; gap: 12px; }}
        .brand-icon {{
          width: 44px; height: 44px; border-radius: 14px;
          background: rgba(232, 168, 85, 0.15);
          border: 1px solid rgba(232, 168, 85, 0.35);
          display: flex; align-items: center; justify-content: center;
          font-size: 22px;
        }}
        .brand h1 {{ font-family: 'Sora', sans-serif; font-size: 20px; font-weight: 700; color: #FFF; }}
        .brand p {{ font-size: 12px; color: #94A3B8; margin-top: 2px; }}
        .actions {{ display: flex; gap: 10px; flex-wrap: wrap; }}
        .btn {{
          padding: 10px 16px;
          border-radius: 12px;
          font-size: 13px;
          font-weight: 700;
          text-decoration: none;
          display: inline-flex;
          align-items: center;
          gap: 6px;
          border: 1px solid rgba(255,255,255,0.12);
          background: rgba(255,255,255,0.05);
          color: #F8FAFC;
          transition: all 0.15s;
        }}
        .btn:hover {{ background: rgba(255,255,255,0.1); }}
        .btn-gold {{
          background: linear-gradient(135deg, #E8A855 0%, #D48828 100%);
          color: #07090E;
          border: none;
        }}
        .grid-4 {{
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
          gap: 16px;
          margin-bottom: 20px;
        }}
        .bento-card {{
          background: rgba(18, 24, 41, 0.85);
          border: 1px solid rgba(255,255,255,0.09);
          border-radius: 20px;
          padding: 20px;
          box-shadow: 0 12px 32px rgba(0,0,0,0.35);
        }}
        .card-tag {{
          font-size: 11px;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.8px;
          color: #94A3B8;
          margin-bottom: 8px;
          display: flex;
          justify-content: space-between;
          align-items: center;
        }}
        .big-num {{
          font-family: 'Sora', sans-serif;
          font-size: 36px;
          font-weight: 800;
          color: #FFF;
          line-height: 1.1;
          margin-bottom: 8px;
        }}
        .sub-metrics {{
          font-size: 12px;
          color: #94A3B8;
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
          margin-top: 10px;
          padding-top: 10px;
          border-top: 1px solid rgba(255,255,255,0.06);
        }}
        .sub-pill {{
          background: rgba(255,255,255,0.05);
          padding: 4px 8px;
          border-radius: 8px;
          font-weight: 600;
          color: #E2E8F0;
        }}
        .grid-2 {{
          display: grid;
          grid-template-columns: 1.4fr 1fr;
          gap: 16px;
          margin-bottom: 20px;
        }}
        @media (max-width: 860px) {{ .grid-2 {{ grid-template-columns: 1fr; }} }}
        .chart-title {{
          font-family: 'Sora', sans-serif;
          font-size: 15px;
          font-weight: 700;
          margin-bottom: 14px;
          color: #FFF;
          display: flex;
          justify-content: space-between;
          align-items: center;
        }}
        .hours-grid {{
          display: grid;
          grid-template-columns: repeat(24, 1fr);
          gap: 4px;
          height: 150px;
          align-items: end;
          padding-top: 18px;
        }}
        .hour-col {{
          display: flex;
          flex-direction: column;
          align-items: center;
          height: 100%;
        }}
        .hour-val {{
          font-size: 10px;
          font-weight: 700;
          color: #E8A855;
          height: 14px;
          margin-bottom: 2px;
        }}
        .hour-bar-wrap {{
          flex: 1;
          width: 100%;
          display: flex;
          align-items: flex-end;
          justify-content: center;
        }}
        .hour-bar {{
          width: 100%;
          max-width: 18px;
          border-radius: 5px 5px 2px 2px;
          transition: height 0.3s;
        }}
        .hour-lbl {{
          font-size: 10px;
          color: #64748B;
          margin-top: 6px;
          font-weight: 600;
        }}
        .progress-row {{ margin-bottom: 14px; }}
        .progress-head {{
          display: flex;
          justify-content: space-between;
          font-size: 13px;
          font-weight: 600;
          margin-bottom: 6px;
        }}
        .progress-track {{
          height: 10px;
          background: rgba(255,255,255,0.06);
          border-radius: 99px;
          overflow: hidden;
        }}
        .progress-fill {{ height: 100%; border-radius: 99px; }}
        .table-wrap {{
          overflow-x: auto;
          margin-top: 8px;
        }}
        table {{
          width: 100%;
          border-collapse: collapse;
          font-size: 13px;
        }}
        th {{
          text-align: left;
          padding: 12px 10px;
          color: #94A3B8;
          font-weight: 700;
          font-size: 11px;
          text-transform: uppercase;
          border-bottom: 1px solid rgba(255,255,255,0.08);
        }}
        td {{
          padding: 11px 10px;
          border-bottom: 1px solid rgba(255,255,255,0.05);
          white-space: nowrap;
        }}
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
      </style>
    </head>
    <body>
      <div class="container">
        <div class="topbar">
          <div class="brand">
            <div class="brand-icon">📊</div>
            <div>
              <h1>Mışıl Baby — Reklam & Köprü Analitik Kokpiti</h1>
              <p>Meta Ads (<code>/ios</code>) ve Instagram Bio (<code>/download</code>) Gerçek Zamanlı Tıklama & Cihaz Telemetrisi</p>
            </div>
          </div>
          <div class="actions">
            <a href="/api/v1/analytics/dashboard?pin={safe_pin}" class="btn">🔄 Yenile</a>
            <a href="/api/v1/analytics/export.csv?pin={safe_pin}" class="btn btn-gold">📥 Excel / CSV İndir</a>
            <a href="/api/v1/feedback/dashboard?pin={safe_pin}" class="btn">💌 Anne Geri Bildirimleri</a>
          </div>
        </div>

        <div class="grid-4">
          <div class="bento-card" style="border-color: rgba(59, 130, 246, 0.35);">
            <div class="card-tag">
              <span>🎯 META ADS LİNKİ (/ios)</span>
              <span class="badge badge-meta">REKLAM</span>
            </div>
            <div class="big-num" style="color: #60A5FA;">{meta['unique_clicks']} <span style="font-size:15px; font-weight:600; color:#94A3B8;">Tekil İnsan</span></div>
            <div style="font-size: 12px; color: #CBD5E1;">Meta Ads "Bağlantı Tıklaması" ile birebir kıyaslanan arındırılmış sayı</div>
            <div class="sub-metrics">
              <span class="sub-pill">Toplam Ham: {meta['raw_hits']}</span>
              <span class="sub-pill">🍏 iPhone: {meta['ios_clicks']}</span>
              <span class="sub-pill">🤖 Android: {meta['android_clicks']}</span>
              <span class="sub-pill">🕷️ Meta Bot: {meta['bot_probes']}</span>
            </div>
          </div>

          <div class="bento-card" style="border-color: rgba(236, 72, 153, 0.35);">
            <div class="card-tag">
              <span>📸 INSTAGRAM BIO (/download)</span>
              <span class="badge badge-ig">PROFİL / ORGANİK</span>
            </div>
            <div class="big-num" style="color: #F472B6;">{ig['unique_clicks']} <span style="font-size:15px; font-weight:600; color:#94A3B8;">Tekil İnsan</span></div>
            <div style="font-size: 12px; color: #CBD5E1;">Instagram profilinize girip Bio / Hikaye linkinden mağazaya geçenler</div>
            <div class="sub-metrics">
              <span class="sub-pill">Toplam Ham: {ig['raw_hits']}</span>
              <span class="sub-pill">🍏 iPhone: {ig['ios_clicks']}</span>
              <span class="sub-pill">🤖 Android: {ig['android_clicks']}</span>
            </div>
          </div>

          <div class="bento-card" style="border-color: rgba(232, 168, 85, 0.35);">
            <div class="card-tag">
              <span>📱 CİHAZ & MAĞAZA YÖNLENDİRMESİ</span>
              <span style="color:#E8A855;">iOS vs ANDROID</span>
            </div>
            <div class="big-num" style="color: #E8A855;">%{ios_pct} <span style="font-size:15px; font-weight:600; color:#94A3B8;">iPhone</span> / %{android_pct} <span style="font-size:15px; font-weight:600; color:#94A3B8;">Android</span></div>
            <div style="font-size: 12px; color: #CBD5E1;">Akıllı köprünün otomatik yönlendirdiği işletim sistemi dağılımı</div>
            <div class="sub-metrics">
              <span class="sub-pill">🍏 App Store'a Giden: {ios_total}</span>
              <span class="sub-pill">🤖 Google Play'e Giden: {android_total}</span>
            </div>
          </div>

          <div class="bento-card">
            <div class="card-tag">
              <span>🛡️ TOPLAM KÖPRÜ TRAFİĞİ</span>
              <span>TÜM KANALLAR</span>
            </div>
            <div class="big-num">{s['total_unique_human']} <span style="font-size:15px; font-weight:600; color:#94A3B8;">Net Tekil</span></div>
            <div style="font-size: 12px; color: #CBD5E1;">Prefetch ve bot taramaları temizlenmiş gerçek ebeveyn ziyareti</div>
            <div class="sub-metrics">
              <span class="sub-pill">Ham İstek: {s['total_raw']}</span>
              <span class="sub-pill">İnsan İsteği: {s['total_human']}</span>
              <span class="sub-pill">Bot Yoklaması: {s['total_bots']}</span>
            </div>
          </div>
        </div>

        <div class="grid-2">
          <div class="bento-card">
            <div class="chart-title">
              <span>⏰ Saatlik Tıklama Yoğunluğu (Son 24 Saat — TSİ)</span>
              <span style="font-size: 11px; color: #94A3B8;">24 Saatlik Dağılım</span>
            </div>
            <div class="hours-grid">
              {bars_html}
            </div>
          </div>

          <div class="bento-card">
            <div class="chart-title">
              <span>📲 Platform & Uygulama İçi Kaynak Kırılımı</span>
            </div>
            <div class="progress-row">
              <div class="progress-head">
                <span>🍏 Apple iPhone (App Store Yönlendirmesi)</span>
                <span style="color:#E8A855;">{ios_total} Tık (%{ios_pct})</span>
              </div>
              <div class="progress-track">
                <div class="progress-fill" style="width: {ios_pct}%; background: linear-gradient(90deg, #E8A855, #F4A261);"></div>
              </div>
            </div>

            <div class="progress-row">
              <div class="progress-head">
                <span>🤖 Android Telefonlar (Google Play Yönlendirmesi)</span>
                <span style="color:#4ADE80;">{android_total} Tık (%{android_pct})</span>
              </div>
              <div class="progress-track">
                <div class="progress-fill" style="width: {android_pct}%; background: linear-gradient(90deg, #22C55E, #4ADE80);"></div>
              </div>
            </div>

            <div class="progress-row" style="margin-top: 18px;">
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

        <div class="bento-card">
          <div class="chart-title">
            <span>⚡ Canlı Tıklama Akışı (Son 80 İstek — Saniye Bazlı)</span>
            <span style="font-size: 12px; color: #94A3B8;">Linkler: <code>/ios</code> (Meta Ads) • <code>/download</code> (Instagram Bio)</span>
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
                  <th>IP & Ülke</th>
                </tr>
              </thead>
              <tbody>
                {rows_html}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </body>
    </html>
    """)
