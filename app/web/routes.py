"""Health and Phase 3 server-rendered investigation routes."""

from collections.abc import Callable
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.core.config import Settings, get_settings
from app.db.session import database_is_ready
from app.investigation.claim import InvalidClaimError, validate_claim
from app.investigation.pipeline import InvestigationPipelineError
from app.investigation.repository import InvestigationNotFoundError
from app.web.csrf import csrf_token, require_csrf
from app.web.i18n import CONFIDENCE_COPY, STATUS_COPY, VERDICT_COPY, copy_for
from app.web.service import InvestigationWebService

router = APIRouter()


def get_readiness_checker() -> Callable[[], bool]:
    return database_is_ready


def get_investigation_service(request: Request) -> InvestigationWebService:
    return cast(InvestigationWebService, request.app.state.investigation_service)


def language_from_request(request: Request) -> str:
    requested = request.query_params.get("lang")
    if requested in {"en", "hu"}:
        return requested
    return "hu" if request.headers.get("accept-language", "").lower().startswith("hu") else "en"


def render(
    request: Request,
    template: str,
    context: dict[str, object],
    *,
    status_code: int = 200,
) -> Response:
    base_context: dict[str, object] = {
        "app_name": request.app.state.settings.app_name,
        "app_version": request.app.state.settings.app_version,
    }
    base_context.update(context)
    return cast(
        Response,
        request.app.state.templates.TemplateResponse(
            request=request, name=template, context=base_context, status_code=status_code
        ),
    )


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def home(request: Request) -> Response:
    language = language_from_request(request)
    return render(
        request,
        "home.html",
        {
            "language": language,
            "t": copy_for(language),
            "csrf_token": csrf_token(request),
            "claim": "",
            "error": None,
        },
    )


@router.post("/investigations", response_class=HTMLResponse, include_in_schema=False)
async def submit_claim(
    request: Request,
    claim: Annotated[str, Form()],
    csrf: Annotated[str, Form()],
    service: Annotated[InvestigationWebService, Depends(get_investigation_service)],
) -> Response:
    require_csrf(request, csrf)
    language = language_from_request(request)
    try:
        validate_claim(claim)
        investigation_id, _ = await service.interpret(claim)
    except InvalidClaimError as exc:
        return render(
            request,
            "home.html",
            {
                "language": language,
                "t": copy_for(language),
                "csrf_token": csrf_token(request),
                "claim": claim,
                "error": str(exc),
            },
            status_code=400,
        )
    except (InvestigationPipelineError, ValueError):
        return render(
            request,
            "home.html",
            {
                "language": language,
                "t": copy_for(language),
                "csrf_token": csrf_token(request),
                "claim": claim,
                "error": "Investigation service is temporarily unavailable.",
            },
            status_code=503,
        )
    return RedirectResponse(f"/investigations/{investigation_id}/confirm", status_code=303)


@router.get(
    "/investigations/{investigation_id}/confirm",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def confirm_claim(
    request: Request,
    investigation_id: UUID,
    service: Annotated[InvestigationWebService, Depends(get_investigation_service)],
) -> Response:
    try:
        investigation = service.get(investigation_id)
    except InvestigationNotFoundError:
        return HTMLResponse("Not found", status_code=404)
    if investigation.status == "COMPLETED":
        return RedirectResponse(f"/investigations/{investigation_id}/result", status_code=303)
    if investigation.status not in {"AWAITING_CONFIRMATION", "INTERPRETING"}:
        return RedirectResponse(f"/investigations/{investigation_id}/progress", status_code=303)
    language = investigation.language or "en"
    return render(
        request,
        "claim_confirm.html",
        {
            "language": language,
            "t": copy_for(language),
            "investigation": investigation,
            "csrf_token": csrf_token(request),
            "error": None,
        },
    )


@router.post("/investigations/{investigation_id}/confirm", include_in_schema=False)
async def start_investigation(
    request: Request,
    investigation_id: UUID,
    background_tasks: BackgroundTasks,
    service: Annotated[InvestigationWebService, Depends(get_investigation_service)],
    action: Annotated[str, Form()],
    csrf: Annotated[str, Form()],
    corrected_claim: Annotated[str | None, Form()] = None,
) -> Response:
    require_csrf(request, csrf)
    try:
        investigation = service.get(investigation_id)
    except InvestigationNotFoundError:
        return HTMLResponse("Not found", status_code=404)
    if investigation.status != "AWAITING_CONFIRMATION":
        return RedirectResponse(f"/investigations/{investigation_id}/progress", status_code=303)
    corrected = action == "correct"
    claim = corrected_claim if corrected else investigation.interpreted_claim
    try:
        confirmed_claim = validate_claim(claim or "")
    except InvalidClaimError as exc:
        language = investigation.language or "en"
        return render(
            request,
            "claim_confirm.html",
            {
                "language": language,
                "t": copy_for(language),
                "investigation": investigation,
                "csrf_token": csrf_token(request),
                "error": str(exc),
            },
            status_code=400,
        )
    background_tasks.add_task(
        service.investigate, investigation_id, confirmed_claim, corrected=corrected
    )
    return RedirectResponse(f"/investigations/{investigation_id}/progress", status_code=303)


@router.get(
    "/investigations/{investigation_id}/progress",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def investigation_progress(
    request: Request,
    investigation_id: UUID,
    service: Annotated[InvestigationWebService, Depends(get_investigation_service)],
) -> Response:
    try:
        investigation = service.get(investigation_id)
    except InvestigationNotFoundError:
        return HTMLResponse("Not found", status_code=404)
    if investigation.status == "COMPLETED":
        return RedirectResponse(f"/investigations/{investigation_id}/result", status_code=303)
    language = investigation.language or "en"
    return render(
        request,
        "investigation.html",
        {
            "language": language,
            "t": copy_for(language),
            "investigation": investigation,
            "status_text": STATUS_COPY[language].get(investigation.status, investigation.status),
        },
    )


@router.get("/investigations/{investigation_id}/status", tags=["investigations"])
def investigation_status(
    investigation_id: UUID,
    service: Annotated[InvestigationWebService, Depends(get_investigation_service)],
) -> JSONResponse:
    try:
        investigation = service.get(investigation_id)
    except InvestigationNotFoundError:
        return JSONResponse({"detail": "Not found"}, status_code=404)
    language = investigation.language or "en"
    return JSONResponse(
        {
            "status": investigation.status,
            "label": STATUS_COPY[language].get(investigation.status, investigation.status),
            "result_url": (
                f"/investigations/{investigation_id}/result"
                if investigation.status == "COMPLETED"
                else None
            ),
        }
    )


@router.get(
    "/investigations/{investigation_id}/result",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def investigation_result(
    request: Request,
    investigation_id: UUID,
    service: Annotated[InvestigationWebService, Depends(get_investigation_service)],
) -> Response:
    try:
        investigation = service.get(investigation_id)
    except InvestigationNotFoundError:
        return HTMLResponse("Not found", status_code=404)
    if investigation.status != "COMPLETED":
        return RedirectResponse(f"/investigations/{investigation_id}/progress", status_code=303)
    language = investigation.language or "en"
    verdict = investigation.verdict or "INCONCLUSIVE"
    confidence = investigation.confidence or "LOW"
    return render(
        request,
        "result.html",
        {
            "language": language,
            "t": copy_for(language),
            "investigation": investigation,
            "verdict_label": VERDICT_COPY[language].get(verdict, verdict),
            "confidence_label": CONFIDENCE_COPY[language].get(confidence, confidence),
        },
    )


@router.get("/health/live", tags=["health"])
def liveness(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, str]:
    return {"status": "ok", "version": settings.app_version}


@router.get("/health/ready", tags=["health"])
def readiness(
    settings: Annotated[Settings, Depends(get_settings)],
    check_database: Annotated[Callable[[], bool], Depends(get_readiness_checker)],
) -> JSONResponse:
    ready = check_database()
    return JSONResponse(
        status_code=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "ready" if ready else "not_ready",
            "version": settings.app_version,
            "checks": {"database": "ok" if ready else "unavailable"},
        },
    )
