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
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging, get_logger, request_id_ctx
from app.db.base import Base, engine
from app.api.v1.router import api_router

# Setup structured logging
setup_logging(debug=settings.DEBUG)
logger = get_logger("main")


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


# Request ID and Timing Middleware
@app.middleware("http")
async def request_middleware(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request_id_ctx.set(req_id)
    
    start_time = time.time()
    try:
        response = await call_next(request)
        process_time = (time.time() - start_time) * 1000
        response.headers["X-Request-ID"] = req_id
        response.headers["X-Process-Time-Ms"] = f"{process_time:.2f}"
        
        # Log request summary
        logger.info(
            f"{request.method} {request.url.path} completed {response.status_code} in {process_time:.2f}ms"
        )
        return response
    except Exception as exc:
        process_time = (time.time() - start_time) * 1000
        logger.error(
            f"{request.method} {request.url.path} failed in {process_time:.2f}ms: {str(exc)}",
            exc_info=True
        )
        raise exc


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
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/", response_class=HTMLResponse, tags=["Web App"])
async def root_app():
    """Serves the live interactive Mishil Mobile Web Application."""
    preview_path = os.path.join(project_root, "mobile", "web-preview", "index.html")
    if os.path.exists(preview_path):
        return FileResponse(preview_path)
    return HTMLResponse("<h2>Mishil API is running. Visit <a href='/docs'>/docs</a></h2>")


@app.get("/health", tags=["Health"])
async def health_check():
    """Liveness probe endpoint."""
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


if __name__ == "__main__":
    import uvicorn
    # Port 8080 default for Railway & container environments
    port = int(os.environ.get("PORT") or 8080)
    host = os.environ.get("HOST") or "0.0.0.0"
    uvicorn.run("app.main:app", host=host, port=port, reload=False)
