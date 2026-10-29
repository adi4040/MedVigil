from fastapi import APIRouter
from app.core.config import settings

router = APIRouter()


@router.get("/health", summary="Service Health Check")
def get_health():
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


@router.get("/ready", summary="Service Readiness Check")
def get_ready():
    # Downstream dependencies (DB, Redis, etc.) can be checked here
    return {"status": "ready"}
