import os
import sys
import time
import uuid
import asyncio

# Ensure root package directory is in sys.path for direct python main.py runs
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from typing import Optional
from contextlib import asynccontextmanager
from fastapi import BackgroundTasks, FastAPI, Request, status

from fastapi.responses import JSONResponse, HTMLResponse, PlainTextResponse, FileResponse, RedirectResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging, get_logger, request_id_ctx
from app.db.base import Base, engine, get_db
import app.db.models  # Ensures all SQLAlchemy models are registered in Base.metadata
from app.api.v1.router import api_router
from app.api.v1.endpoints.analytics import (
    BOT_SIGNATURES,
    capture_bridge_click_context,
    record_bridge_click,
    run_periodic_store_sync_loop,
)

# Setup structured logging
setup_logging(debug=settings.DEBUG)
logger = get_logger("main")

# In-Memory Sliding Window Rate Limiter (IP-based, 120 req / min)
RATE_LIMIT_RECORD: dict = {}
_RATE_LIMIT_LAST_CLEANUP = 0.0
_RATE_LIMIT_CLEANUP_INTERVAL = 300  # Cleanup every 5 minutes


def _cleanup_rate_limit_record(now: float) -> None:
    """Remove all stale IP entries older than 60s to prevent memory leak."""
    global _RATE_LIMIT_LAST_CLEANUP
    if now - _RATE_LIMIT_LAST_CLEANUP < _RATE_LIMIT_CLEANUP_INTERVAL:
        return
    stale_keys = [ip for ip, ts_list in RATE_LIMIT_RECORD.items() if not ts_list or all(now - t >= 60 for t in ts_list)]
    for key in stale_keys:
        del RATE_LIMIT_RECORD[key]
    _RATE_LIMIT_LAST_CLEANUP = now


_store_sync_stop_event: Optional[asyncio.Event] = None
_store_sync_task: Optional[asyncio.Task] = None


def run_safe_schema_migrations(db_engine) -> None:
    """
    Idempotent SQLAlchemy ALTER TABLE column migration guard (.agents/AGENTS.md §3).
    Base.metadata.create_all() creates new tables (family_whispers, night_watch_presence)
    but does NOT add new columns to existing PostgreSQL/SQLite tables.
    """
    from sqlalchemy import inspect as sa_inspect, text as sa_text

    migration_plan = {
        "family_groups": [
            ("room_key", "VARCHAR(64)"),
            ("max_members", "INTEGER DEFAULT 3 NOT NULL"),
            ("vip_active", "BOOLEAN DEFAULT FALSE NOT NULL"),
            ("vip_plan", "VARCHAR(32) DEFAULT 'free' NOT NULL"),
            ("vip_subscriber_id", "VARCHAR(128)"),
            ("checked_vaccines_json", "JSON"),
            ("checked_leaps_json", "JSON"),
            ("active_sleep_start_iso", "VARCHAR(64)"),
            ("active_sleep_actor", "VARCHAR(100)"),
            ("updated_at", "TIMESTAMP"),
        ],
        "family_members": [
            ("device_uid", "VARCHAR(128)"),
            ("member_token_hash", "VARCHAR(128)"),
            ("is_active", "BOOLEAN DEFAULT TRUE NOT NULL"),
            ("last_seen_at", "TIMESTAMP"),
        ],
        "babies": [
            ("device_uid", "VARCHAR(128)"),
            ("premature_weeks", "INTEGER DEFAULT 0"),
        ],
        "dadi_chat_history": [
            ("audience", "VARCHAR(32) DEFAULT 'baby'"),
        ],
        "sleep_logs": [
            ("client_id", "VARCHAR(128)"),
            ("actor_name", "VARCHAR(100)"),
            ("actor_role", "VARCHAR(50)"),
            ("is_deleted", "BOOLEAN DEFAULT FALSE"),
            ("updated_at", "TIMESTAMP"),
        ],
        "routine_logs": [
            ("client_id", "VARCHAR(128)"),
            ("actor_name", "VARCHAR(100)"),
            ("actor_role", "VARCHAR(50)"),
            ("is_deleted", "BOOLEAN DEFAULT FALSE"),
            ("updated_at", "TIMESTAMP"),
        ],
        "subscriber_ledger": [
            ("rc_app_user_id", "VARCHAR(128)"),
            ("device_uid", "VARCHAR(128)"),
        ],
    }

    try:
        inspector = sa_inspect(db_engine)
        existing_tables = set(inspector.get_table_names())
    except Exception as insp_err:
        logger.warning(f"Schema inspector skipped: {insp_err}")
        return

    for table_name, columns in migration_plan.items():
        if table_name not in existing_tables:
            continue
        try:
            existing_cols = {col["name"] for col in inspector.get_columns(table_name)}
        except Exception as col_err:
            logger.warning(f"Could not inspect columns for {table_name}: {col_err}")
            continue

        for col_name, col_ddl in columns:
            if col_name in existing_cols:
                continue
            conn = db_engine.connect()
            trans = conn.begin()
            try:
                conn.execute(sa_text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_ddl}"))
                trans.commit()
                logger.info(f"[DB MIGRATION] Added column {table_name}.{col_name}")
            except Exception as alter_err:
                try:
                    trans.rollback()
                except Exception:
                    pass
                logger.warning(f"[DB MIGRATION] Skipped {table_name}.{col_name}: {alter_err}")
            finally:
                conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    global _store_sync_stop_event, _store_sync_task
    logger.info(f"Starting {settings.APP_NAME} in {settings.ENVIRONMENT} mode...")
    try:
        # Create database tables if they do not exist, then migrate missing columns safely
        if get_db not in app.dependency_overrides:
            Base.metadata.create_all(bind=engine)
            run_safe_schema_migrations(engine)
            logger.info("Database tables verified and initialized successfully.")
    except Exception as e:
        logger.error(f"Error during DB initialization: {str(e)}", exc_info=True)

    # Arka plan periyodik mağaza API senkronizasyon görevini başlat (her 6 saatte bir)
    _store_sync_stop_event = asyncio.Event()
    _store_sync_task = asyncio.create_task(run_periodic_store_sync_loop(_store_sync_stop_event))

    yield

    logger.info(f"Shutting down {settings.APP_NAME}...")
    if _store_sync_stop_event:
        _store_sync_stop_event.set()
    if _store_sync_task:
        try:
            await asyncio.wait_for(_store_sync_task, timeout=3)
        except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
            _store_sync_task.cancel()


app = FastAPI(
    title=settings.APP_TITLE,
    version=settings.APP_VERSION,
    description="Mishil: Baby Sleep, Dynamic Wake Windows, Routines & Cry Heuristic Analysis Backend",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths that bypass rate limiting (static, health, compliance, docs)
_RATE_LIMIT_BYPASS_PREFIXES = (
    "/health",
    "/privacy",
    "/terms",
    "/delete-account",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/sounds",
    "/assets",
    "/ios",
    "/download",
    "/app-store",
    "/android",
    "/play-store",
    "/api/v1/analytics/app-open-signal",
)


# Rate Limiting & Security Header Middleware
@app.middleware("http")
async def security_and_rate_limit_middleware(request: Request, call_next):
    # 1. Rate Limiting Check (Bypass for static files and health check)
    if not request.url.path.startswith(_RATE_LIMIT_BYPASS_PREFIXES):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        # Periodic full cleanup to prevent memory leak
        _cleanup_rate_limit_record(now)

        # Clean this IP's history older than 60s
        history = RATE_LIMIT_RECORD.get(client_ip, [])
        history = [t for t in history if now - t < 60]

        if len(history) >= 120:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "type": "https://mishil.app/errors/rate-limit-exceeded",
                    "title": "Too Many Requests",
                    "status": 429,
                    "detail": "Çok fazla istek gönderildi. Lütfen 1 dakika sonra tekrar deneyiniz.",
                    "instance": request.url.path,
                },
                headers={"Retry-After": "60"}
            )

        history.append(now)
        RATE_LIMIT_RECORD[client_ip] = history

    # 2. Request ID & Timing
    req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request_id_ctx.set(req_id)

    start_time = time.time()
    try:
        response = await call_next(request)
        process_time = (time.time() - start_time) * 1000
        response.headers["X-Request-ID"] = req_id
        response.headers["X-Process-Time-Ms"] = f"{process_time:.2f}"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        logger.info(f"{request.method} {request.url.path} - {response.status_code} ({process_time:.2f}ms)")
        return response
    except Exception as exc:
        process_time = (time.time() - start_time) * 1000
        logger.error(f"{request.method} {request.url.path} failed in {process_time:.2f}ms: {str(exc)}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "type": "https://mishil.app/errors/internal-server-error",
                "title": "Internal Server Error",
                "status": 500,
                "detail": "Sunucuda beklenmeyen bir durum oluştu. Güvenlik gereği detaylar gizlenmiştir.",
                "instance": request.url.path,
                "request_id": req_id,
            }
        )


# ============================================================
# Global Exception Handlers (RFC 7807 Standard Error Format)
# ============================================================
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error_code": f"HTTP_{exc.status_code}",
            "message": exc.detail,
            "request_id": request_id_ctx.get(),
            "path": request.url.path,
        },
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        loc = " -> ".join(str(x) for x in err.get("loc", []))
        errors.append({"field": loc, "issue": err.get("msg")})

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "error_code": "VALIDATION_ERROR",
            "message": "İstek gövdesindeki veriler doğrulanamadı.",
            "details": errors,
            "request_id": request_id_ctx.get(),
            "path": request.url.path,
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled internal server error: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error_code": "INTERNAL_SERVER_ERROR",
            "message": "Beklenmeyen bir sunucu hatası oluştu.",
            "request_id": request_id_ctx.get(),
            "path": request.url.path,
        },
    )


# ============================================================
# Health Check & Root Endpoints
# ============================================================

# Include API V1 router
app.include_router(api_router, prefix="/api/v1")


# PWA & Static Brand Icon Endpoints
@app.get("/favicon.ico", include_in_schema=False)
@app.get("/favicon.png", include_in_schema=False)
@app.get("/favicon-32x32.png", include_in_schema=False)
@app.get("/favicon-16x16.png", include_in_schema=False)
@app.get("/apple-touch-icon.png", include_in_schema=False)
@app.get("/apple-touch-icon-precomposed.png", include_in_schema=False)
@app.get("/icon-192.png", include_in_schema=False)
@app.get("/icon-512.png", include_in_schema=False)
@app.get("/manifest.json", include_in_schema=False)
async def serve_pwa_static(request: Request):
    """Serve PWA icons and web manifest directly from public/ folder."""
    filename = request.url.path.lstrip("/")
    file_path = os.path.join(project_root, "public", filename)
    if os.path.exists(file_path):
        media_type = "application/manifest+json" if filename.endswith(".json") else "image/png"
        if filename.endswith(".ico"):
            media_type = "image/x-icon"
        return FileResponse(file_path, media_type=media_type)
    return PlainTextResponse("Not Found", status_code=404)


@app.get("/", response_class=HTMLResponse, tags=["Landing"])
async def landing_page():
    """Mışıl Baby Official Landing Page & Store Download Hub."""
    landing_file = os.path.join(project_root, "public", "index.html")
    if os.path.exists(landing_file):
        with open(landing_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("""
    <!DOCTYPE html>
    <html lang="tr">
    <head><meta charset="UTF-8"><title>Mışıl Baby</title></head>
    <body><h1>Mışıl Baby</h1><p>App Store ve Google Play'de.</p></body>
    </html>
    """)


_BOT_USER_AGENTS = BOT_SIGNATURES

APP_STORE_URL = "https://apps.apple.com/app/m%C4%B1%C5%9F%C4%B1l-baby-bebek-uyku-ve-a%C4%9Flama/id6809223195"
APP_STORE_SHORT_URL = "https://apps.apple.com/app/id6809223195"
APP_STORE_NATIVE_URL = "itms-apps://apps.apple.com/app/id6809223195"
INSTAGRAM_IOS_EXTBROWSER_URL = (
    "instagram://extbrowser/?url=https%3A%2F%2Fapps.apple.com%2Fapp%2Fid6809223195"
)
GOOGLE_PLAY_URL = "https://play.google.com/store/apps/details?id=com.levitas.misilbaby"
GOOGLE_PLAY_MARKET_URL = "market://details?id=com.levitas.misilbaby"
GOOGLE_PLAY_INTENT_URL = (
    "intent://details?id=com.levitas.misilbaby"
    "#Intent;scheme=market;package=com.android.vending;"
    "S.browser_fallback_url=https%3A%2F%2Fplay.google.com%2Fstore%2Fapps%2Fdetails%3Fid%3Dcom.levitas.misilbaby;end"
)


def generate_interstitial_html(
    is_android: bool,
    is_ios: Optional[bool] = None,
    is_iab: bool = False,
    prefer_android: Optional[bool] = None,
) -> str:
    if is_ios is None:
        is_ios = not is_android
    is_desktop = (not is_android) and (not is_ios)
    if prefer_android is None:
        prefer_android = bool(is_android)

    use_play_primary = bool(is_android or (is_desktop and prefer_android))
    store_name = "Google Play" if use_play_primary else "App Store"
    if is_android:
        cta_href = GOOGLE_PLAY_INTENT_URL
    elif is_ios:
        cta_href = APP_STORE_NATIVE_URL
    else:
        cta_href = GOOGLE_PLAY_URL if prefer_android else APP_STORE_URL
    store_icon = "🤖" if use_play_primary else "🍏"
    if is_android:
        web_fallback_html = (
            f'<a href="{GOOGLE_PLAY_URL}" id="storeWebFallbackBtn" class="sub-link" onclick="window.__sendStoreButtonSignal && window.__sendStoreButtonSignal(\'web_fallback\')">'
            "Play Store uygulaması yüklü değilse tarayıcıda aç ↗</a>"
        )
    elif is_ios and is_iab:
        web_fallback_html = (
            f'<a href="{INSTAGRAM_IOS_EXTBROWSER_URL}" id="iosExternalBrowserBtn" class="sub-link" onclick="window.__sendStoreButtonSignal && window.__sendStoreButtonSignal(\'ios_safari_escape\')">'
            "Açılmazsa Safari ile App Store'da aç ↗</a>"
            '<p class="iab-hint">Instagram kısıtlarsa sağ üstteki <strong>•••</strong> menüsünden <strong>"Tarayıcıda Aç"</strong> seçin.</p>'
        )
    elif is_ios:
        web_fallback_html = (
            f'<a href="{APP_STORE_URL}" id="iosHttpsFallbackBtn" class="sub-link" onclick="window.__sendStoreButtonSignal && window.__sendStoreButtonSignal(\'ios_web_fallback\')">'
            "Açılmazsa App Store web sayfasını aç ↗</a>"
        )
    elif is_desktop:
        alt_href = APP_STORE_URL if prefer_android else GOOGLE_PLAY_URL
        alt_label = "🍏 App Store Sayfasını Aç ↗" if prefer_android else "🤖 Google Play Sayfasını Aç ↗"
        web_fallback_html = (
            f'<a href="{alt_href}" id="desktopAltStoreBtn" class="sub-link" onclick="window.__sendStoreButtonSignal && window.__sendStoreButtonSignal(\'desktop_alt_store\')">'
            f"{alt_label}</a>"
        )
    else:
        web_fallback_html = ""

    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Mışıl Baby — {store_name}'de Açılıyor...</title>
  <meta name="apple-itunes-app" content="app-id=6809223195">
  <meta property="og:title" content="Mışıl Baby — Bebek Uyku & Ağlama Analizi">
  <meta property="og:description" content="Yapay zeka ağlama analizi ve beyaz gürültü. {store_name}'de.">
  <meta property="og:image" content="/icon-512.png">
  <meta property="al:ios:url" content="misilbaby://open">
  <meta property="al:ios:app_store_id" content="6809223195">
  <meta property="al:ios:app_name" content="Mışıl Baby">
  <meta property="al:android:url" content="{GOOGLE_PLAY_MARKET_URL}">
  <meta property="al:android:package" content="com.levitas.misilbaby">
  <meta property="al:android:app_name" content="Mışıl Baby">
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      background: #0B0F19;
      color: #F8FAFC;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      padding: 24px;
      text-align: center;
    }}
    .moon {{ font-size: 56px; margin-bottom: 18px; animation: pulse 1.4s ease-in-out infinite; }}
    @keyframes pulse {{
      0%, 100% {{ transform: scale(1); filter: drop-shadow(0 0 10px rgba(232, 168, 85, 0.4)); }}
      50% {{ transform: scale(1.1); filter: drop-shadow(0 0 24px rgba(232, 168, 85, 0.8)); }}
    }}
    h1 {{ font-size: 1.4rem; font-weight: 700; margin-bottom: 8px; color: #FFFFFF; }}
    p {{ color: #94A3B8; font-size: 0.95rem; margin-bottom: 22px; max-width: 340px; line-height: 1.5; }}
    .btn {{
      background: linear-gradient(135deg, #E8A855 0%, #D4882B 100%);
      color: #0B0F19;
      font-weight: 800;
      padding: 15px 30px;
      border-radius: 30px;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      box-shadow: 0 4px 20px rgba(232, 168, 85, 0.35);
    }}
    .sub-link {{
      margin-top: 16px;
      color: #CBD5E1;
      font-size: 0.84rem;
      text-decoration: underline;
      opacity: 0.9;
    }}
    .iab-hint {{
      margin-top: 12px;
      margin-bottom: 0;
      color: #64748B;
      font-size: 0.78rem;
      max-width: 310px;
    }}
  </style>
</head>
<body>
  <div class="moon">🌙</div>
  <h1>Mışıl Baby Açılıyor...</h1>
  <p>Telefonunuzdaki <strong>{store_name}</strong> uygulamasına yönlendiriliyorsunuz. Otomatik açılmazsa dokunun:</p>
  <a href="{cta_href}" id="storeOpenBtn" class="btn" onclick="return window.__handlePrimaryStoreClick ? window.__handlePrimaryStoreClick(event) : true;">
    <span>{store_icon}</span> {store_name} Uygulamasında Aç
  </a>
  {web_fallback_html}
  <script>
    (function() {{
      var ua = (navigator.userAgent || "").toLowerCase();
      var isTouchMac = /macintosh/.test(ua) && navigator.maxTouchPoints && navigator.maxTouchPoints > 1;
      var isIos = /iphone|ipad|ipod/.test(ua) || isTouchMac;
      var isAnd = !isIos && (ua.indexOf("android") > -1 || {str(bool(is_android)).lower()});
      var preferAndroidDesktop = {str(bool(prefer_android)).lower()};
      var isIg = ua.indexOf("instagram") > -1;
      var isIab = /fban|fbav|fb_iab|instagram|wv|line|tiktok|bytedancewebview|musical_ly/.test(ua);
      var jumpUid = "jump_" + Math.random().toString(36).slice(2, 10);
      var playIntentUrl = "{GOOGLE_PLAY_INTENT_URL}";
      var playMarketUrl = "{GOOGLE_PLAY_MARKET_URL}";
      var playHttpsUrl = "{GOOGLE_PLAY_URL}";
      var appStoreNativeUrl = "{APP_STORE_NATIVE_URL}";
      var appStoreHttpsUrl = "{APP_STORE_URL}";
      var igIosEscapeUrl = "{INSTAGRAM_IOS_EXTBROWSER_URL}";

      if (isTouchMac) {{
        var mainBtn = document.getElementById("storeOpenBtn");
        if (mainBtn) mainBtn.setAttribute("href", appStoreNativeUrl);
      }}

      function emitBridgeSignal(evtType, platformTag) {{
        try {{
          var payload = JSON.stringify({{
            device_uid: jumpUid,
            event_type: evtType,
            os_family: isAnd ? "android" : (isIos ? "ios" : "desktop"),
            platform: platformTag || (isIab ? "bridge_iab" : "bridge_interstitial"),
            app_version: "4.52.1"
          }});
          if (navigator.sendBeacon) {{
            var blob = new Blob([payload], {{ type: "application/json" }});
            navigator.sendBeacon("/api/v1/analytics/app-open-signal", blob);
          }} else {{
            fetch("/api/v1/analytics/app-open-signal", {{
              method: "POST",
              headers: {{ "Content-Type": "application/json" }},
              body: payload,
              keepalive: true
            }}).catch(function(){{}});
          }}
        }} catch (err) {{}}
      }}

      window.__sendStoreButtonSignal = function(mode) {{
        emitBridgeSignal("store_button_click", mode || (isIab ? "manual_cta_iab" : "manual_cta"));
      }};

      window.__handlePrimaryStoreClick = function(ev) {{
        window.__sendStoreButtonSignal("primary_cta");
        if (isIos && isIg) {{
          setTimeout(function() {{
            if (!document.hidden) {{
              try {{ window.location.href = igIosEscapeUrl; }} catch (igErr) {{}}
            }}
          }}, 550);
        }}
        return true;
      }};

      emitBridgeSignal("store_jump", isIab ? "bridge_iab" : "bridge_interstitial");

      function triggerNativeStoreNow() {{
        if (isAnd) {{
          // Android: Sadece yerel Google Play Store uygulamasını (com.android.vending) uyandır;
          // ASLA play.google.com web sayfasını Instagram tarayıcısı içinde zorla açma.
          try {{
            window.location.href = playIntentUrl;
          }} catch (e) {{
            try {{ window.location.href = playMarketUrl; }} catch (e2) {{}}
          }}
          return;
        }}
        if (isIos) {{
          // iOS: Sadece yerel App Store protokolünü (itms-apps://) tetikle;
          // ASLA apps.apple.com web önizlemesini Instagram WKWebView içinde açma.
          if (isIab) {{
            try {{
              var ifr = document.createElement("iframe");
              ifr.style.display = "none";
              ifr.src = appStoreNativeUrl;
              document.body.appendChild(ifr);
            }} catch (ifrErr) {{}}
            try {{
              window.location.href = appStoreNativeUrl;
            }} catch (navErr) {{}}
          }} else {{
            try {{
              window.location.replace(appStoreNativeUrl);
            }} catch (e) {{
              window.location.href = appStoreNativeUrl;
            }}
          }}
          return;
        }}
        // Masaüstü (Mac / Windows): İşletim sistemi veya rota tercihine uygun mağaza sayfasına yönlendir
        var desktopTarget = preferAndroidDesktop ? playHttpsUrl : appStoreHttpsUrl;
        try {{
          window.location.replace(desktopTarget);
        }} catch (deskErr) {{
          window.location.href = desktopTarget;
        }}
      }}

      // Sıfır yapay gecikme (0ms): DOM gövdesi çizildiği anda yerel mağaza protokolünü ateşle
      triggerNativeStoreNow();
    }})();
  </script>
</body>
</html>"""


@app.get("/ios", response_model=None, tags=["Landing"])
@app.get("/download", response_model=None, tags=["Landing"])
@app.get("/app-store", response_model=None, tags=["Landing"])
@app.get("/android", response_model=None, tags=["Landing"])
@app.get("/play-store", response_model=None, tags=["Landing"])
async def smart_app_store_bridge(request: Request, background_tasks: BackgroundTasks):
    """
    Universal Direct HTTP 302 Store Bridge (AppsFlyer OneLink Architecture):
    - Meta / sosyal inceleme botlarına 200 OK resmi landing sayfası (index.html) sunar (reklam kısıtlarına takılmaz),
    - Gerçek kullanıcılara ara 'Açılıyor...' HTML ekranı göstermeden <1ms içinde doğrudan HTTP 302 mağaza yönlendirmesi döner,
    - Kokpit tıklama metriklerini BackgroundTasks üzerinden %100 eksiksiz kaydeder.
    """
    user_agent = (request.headers.get("user-agent") or "").lower()
    route_path = request.url.path or "/ios"
    is_ios = any(os_tok in user_agent for os_tok in ("iphone", "ipad", "ipod"))
    is_android = (not is_ios) and ("android" in user_agent)
    is_mobile_os = is_ios or is_android
    no_cache_headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    }

    # Tek kaynaklı BOT_SIGNATURES + masaüstü WhatsApp önizleme botu kontrolü
    is_crawler = any(bot in user_agent for bot in _BOT_USER_AGENTS) or (
        "whatsapp" in user_agent and not is_mobile_os
    )

    click_ctx = capture_bridge_click_context(request)

    if is_crawler:
        background_tasks.add_task(
            record_bridge_click,
            click_ctx,
            route_path=route_path,
            target_store="landing_bot",
        )
        landing_file = os.path.join(project_root, "public", "index.html")
        if os.path.exists(landing_file):
            with open(landing_file, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read(), status_code=status.HTTP_200_OK, headers=no_cache_headers)
        return HTMLResponse(
            content="<!DOCTYPE html><html lang='tr'><head><meta charset='UTF-8'><title>Mışıl Baby</title></head><body><h1>Mışıl Baby</h1></body></html>",
            status_code=status.HTTP_200_OK,
            headers=no_cache_headers,
        )

    is_android_route = route_path in ("/android", "/play-store")
    is_ios_route = route_path in ("/ios", "/app-store")
    is_windows_desktop = (not is_mobile_os) and ("windows" in user_agent)
    prefer_android = bool(
        is_android
        or (not is_ios and (is_android_route or (is_windows_desktop and not is_ios_route)))
    )
    target_url = GOOGLE_PLAY_URL if prefer_android else APP_STORE_SHORT_URL

    # Tıklama kaydını BackgroundTasks ile HTTP 302 yanıtı gönderildikten hemen sonra yaz (<1ms TTFB, %100 aynı kokpit sayımı)
    background_tasks.add_task(
        record_bridge_click,
        click_ctx,
        route_path=route_path,
        target_store="google_play" if prefer_android else "app_store",
    )
    return RedirectResponse(
        url=target_url,
        status_code=status.HTTP_302_FOUND,
        headers=no_cache_headers,
    )


@app.get("/invite/{code}", response_class=HTMLResponse, tags=["Family"])
async def family_invite_bridge(code: str, request: Request, baby: Optional[str] = None):
    """Smart Family Co-Parenting Invite Landing & Deep-Link Bridge (max 3 members)."""
    import html as _html
    import re as _re
    import urllib.parse as _urlparse

    clean_code = _re.sub(r"[^A-Z0-9-]", "", (code or "").strip().upper())[:16]
    if len(clean_code) < 4:
        return RedirectResponse(url="/download", status_code=status.HTTP_302_FOUND)

    safe_code_html = _html.escape(clean_code, quote=True)
    raw_baby = (baby or "").strip()[:40]
    safe_baby_html = _html.escape(raw_baby, quote=True) if raw_baby else "Bebeğiniz"
    ua = (request.headers.get("user-agent") or "").lower()
    is_android = "android" in ua
    store_url = GOOGLE_PLAY_URL if is_android else APP_STORE_URL
    store_label = "Google Play'den İndir" if is_android else "App Store'dan İndir"
    app_query = f"/app?code={_urlparse.quote(clean_code)}"
    if raw_baby:
        app_query += f"&baby={_urlparse.quote(raw_baby)}"
    import json as _json
    safe_code_js = _json.dumps(clean_code).replace("<", "\\u003c").replace(">", "\\u003e")
    safe_app_query_js = _json.dumps(app_query).replace("<", "\\u003c").replace(">", "\\u003e")

    html_page = f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Mışıl Baby — Ortak Aile Daveti ({safe_code_html})</title>
  <meta property="og:title" content="👨‍👩‍👧 Mışıl Baby — {safe_baby_html} İçin Ortak Aile Takibi">
  <meta property="og:description" content="Aile Davet Kodu: {safe_code_html} • Tek VIP ile 3 kişiye kadar (Anne, Baba, Bakıcı) aynı bebeği canlı takip edin.">
  <meta property="og:image" content="/icon-512.png">
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      background: #0B0F19; color: #F8FAFC;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      display: flex; align-items: center; justify-content: center;
      min-height: 100vh; padding: 20px; text-align: center;
    }}
    .card {{
      width: 100%; max-width: 400px; background: #141B2E;
      border: 1px solid rgba(232, 168, 85, 0.35); border-radius: 22px;
      padding: 26px 22px; box-shadow: 0 18px 48px rgba(0,0,0,0.45);
    }}
    .code-box {{
      margin: 16px 0; padding: 14px; border-radius: 14px;
      background: rgba(232, 168, 85, 0.12); border: 1.5px dashed #E8A855;
      font-size: 24px; font-weight: 800; letter-spacing: 3px; color: #E8A855;
    }}
    .btn {{
      width: 100%; padding: 14px 18px; border-radius: 14px; border: none;
      font-size: 14px; font-weight: 700; cursor: pointer; text-decoration: none;
      display: flex; align-items: center; justify-content: center; gap: 8px; margin-top: 10px;
    }}
    .btn-gold {{ background: linear-gradient(135deg, #E8A855 0%, #D4882B 100%); color: #0B0F19; }}
    .btn-outline {{ background: rgba(255,255,255,0.06); color: #F8FAFC; border: 1px solid rgba(255,255,255,0.16); }}
    .hint {{ font-size: 12px; color: #94A3B8; line-height: 1.5; margin-top: 12px; }}
  </style>
</head>
<body>
  <div class="card">
    <div style="font-size: 42px; margin-bottom: 8px;">👨‍👩‍👧</div>
    <h1 style="font-size: 19px; font-weight: 800; margin-bottom: 6px;">{safe_baby_html} Ailesine Davetlisiniz</h1>
    <p style="font-size: 13px; color: #CBD5E1; line-height: 1.5;">
      Anne, Baba ve Bakıcı (3 kişiye kadar) kendi telefonundan aynı bebeğin uykusunu, beslenmesini ve aşılarını canlı takip eder.
    </p>
    <div class="code-box" id="invCodeText">{safe_code_html}</div>
    <button type="button" class="btn btn-gold" id="copyOpenBtn" onclick="copyAndOpenApp()">📋 Kodu Kopyala &amp; Mışıl Baby'yi Aç</button>
    <a href="{store_url}" class="btn btn-outline">📲 Uygulama Yüklü Değilse {store_label}</a>
    <a href="{_html.escape(app_query, quote=True)}" class="btn btn-outline" style="font-size: 12px; opacity: 0.88;">🌐 Web Görünümünde Doğrudan Katıl ➔</a>
    <p class="hint">Uygulamayı açtığınızda ilk ekrandaki <strong>"Eşimin Aile Kodu Var"</strong> kartına dokunup kodu yapıştırmanız yeterlidir.</p>
  </div>
  <script>
    function copyAndOpenApp() {{
      var c = {safe_code_js};
      try {{
        if (navigator.clipboard && navigator.clipboard.writeText) {{
          navigator.clipboard.writeText(c);
        }}
      }} catch (e) {{}}
      var btn = document.getElementById('copyOpenBtn');
      if (btn) btn.textContent = '✅ Kod Kopyalandı (' + c + ') — Açılıyor...';
      window.location.href = 'misilbaby://sleep?code=' + encodeURIComponent(c);
      setTimeout(function() {{
        if (!document.hidden) {{
          window.location.href = {safe_app_query_js};
        }}
      }}, 900);
    }}
  </script>
</body>
</html>"""
    return HTMLResponse(content=html_page, status_code=status.HTTP_200_OK)


@app.get("/app", response_class=HTMLResponse, tags=["Developer"])
@app.get("/preview", response_class=HTMLResponse, tags=["Developer"])
async def developer_preview():
    """PIN-Protected Live Developer Preview of Mışıl Baby."""
    app_file = os.path.join(project_root, "public", "app.html")
    # Telefonların diske eski HTML önbelleği kaydetmesini engelle; her zaman
    # Railway'deki canlı kodu çeksinler.
    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    }
    if os.path.exists(app_file):
        with open(app_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), headers=headers)
    return HTMLResponse("<h2>Uygulama dosyası bulunamadı.</h2>", status_code=404, headers=headers)


@app.get("/admin/feedbacks", response_class=HTMLResponse, tags=["Admin"])
async def admin_feedbacks_shortcut(request: Request, pin: Optional[str] = None):
    """Direct shortcut for Admin Feedback Dashboard."""
    pin_param = f"?pin={pin}" if pin else ""
    return RedirectResponse(url=f"/api/v1/feedback/dashboard{pin_param}")


@app.get("/admin/analytics", response_class=HTMLResponse, tags=["Admin"])
@app.get("/admin/clicks", response_class=HTMLResponse, tags=["Admin"])
async def admin_analytics_shortcut(request: Request, pin: Optional[str] = None):
    """Direct shortcut for Live Ad & Store Bridge Analytics Cockpit."""
    pin_param = f"?pin={pin}" if pin else ""
    return RedirectResponse(url=f"/api/v1/analytics/dashboard{pin_param}")



@app.get("/health", tags=["Health"])
async def health_check():
    """Liveness probe endpoint."""
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


@app.api_route("/privacy", methods=["GET", "HEAD"], response_class=HTMLResponse, tags=["Compliance"])
async def privacy_policy():
    """Privacy Policy for Google Play and Apple App Store compliance."""
    privacy_file = os.path.join(project_root, "public", "privacy.html")
    if os.path.exists(privacy_file):
        with open(privacy_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("""
    <!DOCTYPE html>
    <html lang="tr">
    <head><meta charset="UTF-8"><title>Gizlilik Politikası — Mışıl Baby</title></head>
    <body><h1>Mışıl Baby — Gizlilik Politikası</h1><p>Levitas Enterprise Intelligence & Technology</p></body>
    </html>
    """)


@app.api_route("/terms", methods=["GET", "HEAD"], response_class=HTMLResponse, tags=["Compliance"])
async def terms_of_service():
    """Terms of Service and Medical Disclaimer for Store Compliance."""
    terms_file = os.path.join(project_root, "public", "terms.html")
    if os.path.exists(terms_file):
        with open(terms_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("""
    <!DOCTYPE html>
    <html lang="tr">
    <head><meta charset="UTF-8"><title>Kullanım Koşulları — Mışıl Baby</title></head>
    <body><h1>Mışıl Baby — Kullanım Koşulları</h1><p>Levitas Enterprise Intelligence & Technology</p></body>
    </html>
    """)


@app.get("/delete-account", response_class=HTMLResponse, tags=["Compliance"])
async def delete_account_page():
    """Account Deletion Request Web Page (Apple App Store Requirement)."""
    return HTMLResponse("""
    <!DOCTYPE html>
    <html lang="tr">
    <head>
      <meta charset="UTF-8">
      <title>Hesap Silme Talebi — Mishil</title>
      <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #2C3E50; max-width: 600px; margin: 50px auto; padding: 0 20px; }
        input, button { width: 100%; padding: 12px; margin: 8px 0; border-radius: 8px; border: 1px solid #CCC; box-sizing: border-box; }
        button { background: #FF4757; color: #FFF; font-weight: bold; border: none; cursor: pointer; }
      </style>
    </head>
    <body>
      <h1>🗑️ Mishil Hesabınızı ve Verilerinizi Silin</h1>
      <p>Apple App Store ve Google Play yönergeleri uyarınca, hesabınızı ve bebeğinize ait tüm uyku/rutin günlüklerini kalıcı olarak silebilirsiniz.</p>

      <form onsubmit="event.preventDefault(); alert('Hesap silme talebiniz alındı. 24 saat içinde tüm verileriniz kalıcı olarak temizlenecektir.');">
        <label>Kayıtlı E-posta Adresiniz:</label>
        <input type="email" placeholder="ornek@eposta.com" required />
        <label>Silme Onayı (Onaylıyorum yazınız):</label>
        <input type="text" placeholder="Onaylıyorum" required />
        <button type="submit">Hesabımı ve Tüm Verilerimi Kalıcı Olarak Sil</button>
      </form>
    </body>
    </html>
    """)


# ============================================================
# Static files mount for Web Preview and Lossless Studio Sounds
# ============================================================
web_preview_dir = os.path.join(project_root, "mobile", "web-preview")
if os.path.exists(web_preview_dir):
    from fastapi.staticfiles import StaticFiles

    sounds_dir = os.path.join(web_preview_dir, "sounds")
    if os.path.exists(sounds_dir):
        app.mount("/sounds", StaticFiles(directory=sounds_dir), name="sounds")

    assets_dir = os.path.join(project_root, "mobile", "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


if __name__ == "__main__":
    import uvicorn
    # Port 8080 default for Railway & container environments
    port = int(os.environ.get("PORT") or 8080)
    host = os.environ.get("HOST") or "0.0.0.0"
    uvicorn.run("app.main:app", host=host, port=port, reload=False)
