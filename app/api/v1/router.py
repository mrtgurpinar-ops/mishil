from fastapi import APIRouter
from app.api.v1.endpoints import (
    auth,
    wake_window,
    cry_analysis,
    sounds,
    routines,
    subscription,
    coach,
    family,
    baby,
    sleep,
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(wake_window.router)
api_router.include_router(cry_analysis.router)
api_router.include_router(sounds.router)
api_router.include_router(routines.router)
api_router.include_router(subscription.router)
api_router.include_router(coach.router, prefix="/coach", tags=["Mışıl Dadı AI"])
api_router.include_router(family.router, prefix="/family", tags=["Family & Nanny Sync"])
api_router.include_router(baby.router, prefix="/baby", tags=["Baby Profile Sync"])
api_router.include_router(sleep.router, prefix="/sleep", tags=["Live Sleep Logs"])

