from fastapi import APIRouter
from app.api.v1.endpoints import (
    auth,
    wake_window,
    cry_analysis,
    sounds,
    routines,
    subscription,
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(wake_window.router)
api_router.include_router(cry_analysis.router)
api_router.include_router(sounds.router)
api_router.include_router(routines.router)
api_router.include_router(subscription.router)
