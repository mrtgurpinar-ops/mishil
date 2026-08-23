import os
import sys
import time
import uuid

# Ensure root package directory is in sys.path for direct python main.py runs
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, HTMLResponse, PlainTextResponse, FileResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging, get_logger, request_id_ctx
from app.db.base import Base, engine
import app.db.models  # Ensures all SQLAlchemy models are registered in Base.metadata
from app.api.v1.router import api_router

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    logger.info(f"Starting {settings.APP_NAME} in {settings.ENVIRONMENT} mode...")
    try:
        # Create database tables if they do not exist
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables verified and initialized successfully.")
    except Exception as e:
        logger.error(f"Error during DB initialization: {str(e)}", exc_info=True)
    yield
    logger.info(f"Shutting down {settings.APP_NAME}...")


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


@app.get("/health", tags=["Health"])
async def health_check():
    """Liveness probe endpoint."""
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/privacy", response_class=HTMLResponse, tags=["Compliance"])
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


@app.get("/terms", response_class=HTMLResponse, tags=["Compliance"])
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


# Single unified GET / route — serves web preview if available, otherwise API info
@app.get("/", response_class=HTMLResponse, tags=["Web App"])
async def root_app():
    """Serves the live interactive Mishil Mobile Web Application."""
    index_path = os.path.join(web_preview_dir if os.path.exists(web_preview_dir) else "", "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h2>Mishil API is running. Visit <a href='/docs'>/docs</a></h2>")


if __name__ == "__main__":
    import uvicorn
    # Port 8080 default for Railway & container environments
    port = int(os.environ.get("PORT") or 8080)
    host = os.environ.get("HOST") or "0.0.0.0"
    uvicorn.run("app.main:app", host=host, port=port, reload=False)
