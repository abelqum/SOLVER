import secrets
from typing import Annotated

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


async def verify_api_key(
    x_api_key: Annotated[str | None, Header()] = None,
) -> None:
    settings = get_settings()

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta el encabezado X-API-Key.",
        )

    if not secrets.compare_digest(
        x_api_key,
        settings.solver_api_key,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La clave de acceso no es válida.",
        )