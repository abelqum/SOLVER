import platform
import sys
from datetime import datetime, timezone

import fastapi
import ortools
import pydantic
from fastapi import APIRouter

from app.core.config import get_settings


router = APIRouter(
    prefix="/health",
    tags=["Diagnóstico"],
)


@router.get("")
async def health_check() -> dict:
    settings = get_settings()

    return {
        "success": True,
        "service": settings.app_name,
        "environment": settings.app_env,
        "message": "El servicio del solver funciona correctamente.",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "versions": {
            "python": sys.version.split()[0],
            "fastapi": fastapi.__version__,
            "pydantic": pydantic.__version__,
            "ortools": ortools.__version__,
        },
        "platform": platform.platform(),
    }