import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.api.routes.schedules import router as schedules_router
from app.core.config import get_settings


logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | %(levelname)s | "
        "%(name)s | %(message)s"
    ),
)


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(
    app: FastAPI,
) -> AsyncIterator[None]:
    settings = get_settings()

    logger.info(
        "Iniciando %s en modo %s.",
        settings.app_name,
        settings.app_env,
    )

    yield

    logger.info(
        "Deteniendo %s.",
        settings.app_name,
    )


settings = get_settings()


app = FastAPI(
    title=settings.app_name,
    description=(
        "Microservicio de optimización para generar "
        "horarios escolares mediante OR-Tools CP-SAT."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "X-API-Key",
    ],
)


@app.get(
    "/",
    tags=["Diagnóstico"],
)
async def root() -> dict:
    return {
        "service": settings.app_name,
        "version": "0.1.0",
        "documentation": "/docs",
        "health": "/api/v1/health",
    }


app.include_router(
    health_router,
    prefix="/api/v1",
)

app.include_router(
    schedules_router,
    prefix="/api/v1",
)