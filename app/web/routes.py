"""Health and Phase 3 server-rendered investigation routes."""

from collections.abc import Callable
from typing import Annotated, cast
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.auth.session import current_user, guest_session_id
from app.core.config import Settings, get_settings
from app.db.models import Investigation
from app.db.session import database_is_ready, get_session
from app.feedback.service import FeedbackError, submit_feedback
from app.investigation.claim import InvalidClaimError, validate_claim
from app.investigation.pipeline import InvestigationPipelineError
from app.investigation.repository import InvestigationNotFoundError
from app.ocr import ImageTextError, extract_image_text
from app.sharing.service import SharingError, owns_investigation, set_public, submit_public_report
from app.web.confidence import confidence_explanation
from app.web.csrf import csrf_token, require_csrf
from app.web.i18n import (
    CONFIDENCE_COPY,
    STATUS_COPY,
    VERDICT_COPY,
    about_copy_for,
    account_copy_for,
    copy_for,
    language_from_request,
    language_switch_url,
)
from app.web.service import InvestigationWebService

PROGRESS_STATUS_INDEX = {
    "SEARCHING": 1,
    "COLLECTING_SOURCES": 2,
    "EVALUATING_EVIDENCE": 3,
    "CALCULATING_ASSESSMENT": 4,
    "GENERATING_RESULT": 5,
    "COMPLETED": 5,
}
PROGRESS_STAGE_TOTAL = 5

router = APIRouter()


def get_readiness_checker() -> Callable[[], bool]:
    return database_is_ready


def get_investigation_service(request: Request) -> InvestigationWebService:
    return cast(InvestigationWebService, request.app.state.investigation_service)


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
        "support_url": request.app.state.settings.support_url,
    }
    base_context["current_user"] = request.session.get("user_id")
    context_language = context.get("language")
    base_context["a"] = account_copy_for(
        context_language if isinstance(context_language, str) else "en"
    )
    base_context["language_urls"] = {
        "en": language_switch_url(request, "en"),
        "hu": language_switch_url(request, "hu"),
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


@router.get("/about", response_class=HTMLResponse, include_in_schema=False)
def about(request: Request) -> Response:
    language = language_from_request(request)
    settings = request.app.state.settings
    provider_settings = {
        "groq": (settings.groq_api_key, settings.groq_model, "Groq"),
        "gemini": (settings.gemini_api_key, settings.gemini_model, "Google Gemini"),
        "openrouter": (settings.openrouter_api_key, settings.openrouter_model, "OpenRouter"),
        "deepseek": (settings.deepseek_api_key, settings.deepseek_model, "DeepSeek"),
    }
    models = [
        {"provider": provider_settings[name][2], "model": provider_settings[name][1]}
        for name in settings.provider_order
        if name in provider_settings and provider_settings[name][0] is not None
    ]
    return render(
        request,
        "about.html",
        {
            "language": language,
            "t": copy_for(language),
            "about": about_copy_for(language),
            "models": models,
            "brave_enabled": settings.brave_search_api_key is not None,
        },
    )


@router.post("/investigations", response_class=HTMLResponse, include_in_schema=False)
async def submit_claim(
    request: Request,
    csrf: Annotated[str, Form()],
    service: Annotated[InvestigationWebService, Depends(get_investigation_service)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    claim: Annotated[str, Form()] = "",
    image: Annotated[UploadFile | None, File()] = None,
) -> Response:
    require_csrf(request, csrf)
    language = language_from_request(request)
    try:
        has_claim = bool(claim.strip())
        has_image = image is not None and bool(image.filename)
        if has_claim == has_image:
            raise InvalidClaimError("Enter a claim or upload one image, but not both.")
        submitted_claim = claim
        if image is not None and has_image:
            payload = await image.read(settings.image_upload_max_bytes + 1)
            submitted_claim = await run_in_threadpool(
                extract_image_text,
                payload,
                image.content_type,
                max_bytes=settings.image_upload_max_bytes,
                max_pixels=settings.image_upload_max_pixels,
                max_characters=500,
            )
        validate_claim(submitted_claim)
        user = current_user(request, session, settings)
        investigation_id, _ = await service.interpret(
            submitted_claim,
            user_id=user.id if user else None,
            session_id=None if user else guest_session_id(request),
        )
    except (InvalidClaimError, ImageTextError) as exc:
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
            "progress_stage_index": PROGRESS_STATUS_INDEX.get(investigation.status, 0),
            "progress_stage_total": PROGRESS_STAGE_TOTAL,
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
            "stage_index": PROGRESS_STATUS_INDEX.get(investigation.status, 0),
            "stage_total": PROGRESS_STAGE_TOTAL,
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
    raw_user_id = request.session.get("user_id")
    raw_session_id = request.session.get("guest_session_id")
    if not owns_investigation(
        investigation,
        user_id=raw_user_id if isinstance(raw_user_id, str) else None,
        session_id=raw_session_id if isinstance(raw_session_id, str) else None,
    ):
        return HTMLResponse("Not found", status_code=404)
    return _render_result(request, investigation, is_public_view=False)


def _render_result(
    request: Request, investigation: Investigation, *, is_public_view: bool
) -> Response:
    language = investigation.language or "en"
    verdict = investigation.verdict or "INCONCLUSIVE"
    confidence = investigation.confidence or "LOW"
    user_id = request.session.get("user_id")
    session_id = request.session.get("guest_session_id")
    selected_feedback = next(
        (
            item.value
            for item in investigation.feedback
            if (isinstance(user_id, str) and str(item.user_id) == user_id)
            or (isinstance(session_id, str) and item.session_id == session_id)
        ),
        None,
    )
    return render(
        request,
        "result.html",
        {
            "language": language,
            "t": copy_for(language),
            "investigation": investigation,
            "verdict_label": VERDICT_COPY[language].get(verdict, verdict),
            "confidence_label": CONFIDENCE_COPY[language].get(confidence, confidence),
            "confidence_explanation": confidence_explanation(
                confidence,
                investigation.evidence,
                conflict_detected=investigation.conflict_detected,
                language=language,
            ),
            "csrf_token": csrf_token(request),
            "selected_feedback": selected_feedback,
            "is_public_view": is_public_view,
            "share_url": (
                f"{str(request.app.state.settings.public_base_url).rstrip('/')}/investigation/"
                f"{investigation.public_slug}"
                if investigation.is_public and investigation.public_slug
                else None
            ),
        },
    )


@router.get("/investigation/{public_slug}", response_class=HTMLResponse, include_in_schema=False)
def public_investigation_result(
    request: Request,
    public_slug: str,
    service: Annotated[InvestigationWebService, Depends(get_investigation_service)],
) -> Response:
    try:
        investigation = service.get_public(public_slug)
    except InvestigationNotFoundError:
        return HTMLResponse("Not found", status_code=404)
    guest_session_id(request)
    return _render_result(request, investigation, is_public_view=True)


@router.post("/investigations/{investigation_id}/sharing", include_in_schema=False)
def investigation_sharing(
    request: Request,
    investigation_id: UUID,
    enabled: Annotated[str, Form()],
    csrf: Annotated[str, Form()],
    service: Annotated[InvestigationWebService, Depends(get_investigation_service)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    require_csrf(request, csrf)
    try:
        investigation = service.get(investigation_id)
        raw_user_id = request.session.get("user_id")
        raw_session_id = request.session.get("guest_session_id")
        set_public(
            session,
            investigation,
            enabled=enabled == "true",
            user_id=raw_user_id if isinstance(raw_user_id, str) else None,
            session_id=raw_session_id if isinstance(raw_session_id, str) else None,
        )
    except (InvestigationNotFoundError, SharingError):
        return HTMLResponse("Not found", status_code=404)
    state = "published" if enabled == "true" else "private"
    return RedirectResponse(
        f"/investigations/{investigation_id}/result?sharing={state}", status_code=303
    )


@router.post("/investigation/{public_slug}/report", include_in_schema=False)
def report_public_investigation(
    request: Request,
    public_slug: str,
    reason: Annotated[str, Form()],
    csrf: Annotated[str, Form()],
    service: Annotated[InvestigationWebService, Depends(get_investigation_service)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    require_csrf(request, csrf)
    try:
        investigation = service.get_public(public_slug)
        submit_public_report(
            session,
            investigation,
            reason=reason,
            reporter_session_id=guest_session_id(request),
        )
    except (InvestigationNotFoundError, SharingError):
        return HTMLResponse("Request failed", status_code=400)
    return RedirectResponse(f"/investigation/{public_slug}?report=received", status_code=303)


@router.post("/investigations/{investigation_id}/feedback", include_in_schema=False)
def investigation_feedback(
    request: Request,
    investigation_id: UUID,
    value: Annotated[str, Form()],
    csrf: Annotated[str, Form()],
    service: Annotated[InvestigationWebService, Depends(get_investigation_service)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    require_csrf(request, csrf)
    try:
        investigation = service.get(investigation_id)
    except InvestigationNotFoundError:
        return HTMLResponse("Not found", status_code=404)
    user = current_user(request, session, settings)
    guest_id = request.session.get("guest_session_id")
    try:
        submit_feedback(
            session,
            investigation,
            value,
            user_id=user.id if user else None,
            session_id=guest_id if isinstance(guest_id, str) else None,
        )
    except FeedbackError:
        return HTMLResponse("Request failed", status_code=403)
    return RedirectResponse(
        f"/investigations/{investigation_id}/result?feedback=received", status_code=303
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
