"""Phase 1 routes."""

from collections.abc import Callable
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse

from app.core.config import Settings, get_settings
from app.db.session import database_is_ready

router = APIRouter()


def get_readiness_checker() -> Callable[[], bool]:
    """Dependency seam used by readiness tests and future infrastructure checks."""

    return database_is_ready


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def home(request: Request) -> Response:
    settings = get_settings()
    return cast(
        Response,
        request.app.state.templates.TemplateResponse(
            request=request,
            name="home.html",
            context={"app_name": settings.app_name, "app_version": settings.app_version},
        ),
    )


@router.get("/health/live", tags=["health"])
def liveness(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, str]:
    """Report process liveness without querying PostgreSQL."""

    return {"status": "ok", "version": settings.app_version}


@router.get("/health/ready", tags=["health"])
def readiness(
    settings: Annotated[Settings, Depends(get_settings)],
    check_database: Annotated[Callable[[], bool], Depends(get_readiness_checker)],
) -> JSONResponse:
    """Report whether required Phase 1 infrastructure is available."""

    ready = check_database()
    return JSONResponse(
        status_code=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "ready" if ready else "not_ready",
            "version": settings.app_version,
            "checks": {"database": "ok" if ready else "unavailable"},
        },
    )
