import logging

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from app.api.dependencies import (
    verify_api_key,
)
from app.models.schedule import (
    ScheduleSolveRequest,
    ScheduleSolveResponse,
)
from app.services.schedule_solver import (
    solve_schedule,
)


logger = logging.getLogger(
    __name__,
)


router = APIRouter(
    prefix="/schedules",
    tags=["Horarios"],
    dependencies=[
        Depends(verify_api_key),
    ],
)


@router.post(
    "/solve",
    response_model=ScheduleSolveResponse,
    status_code=status.HTTP_200_OK,
)
def solve_schedule_endpoint(
    request: ScheduleSolveRequest,
) -> ScheduleSolveResponse:
    try:
        return solve_schedule(
            request,
        )
    except HTTPException:
        raise
    except Exception as error:
        logger.exception(
            "Error inesperado resolviendo el horario.",
        )

        raise HTTPException(
            status_code=
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Ocurrió un error inesperado durante "
                "la generación del horario."
            ),
        ) from error