"""FastAPI application factory and ASGI entry point."""

from pathlib import Path
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.web.routes import router

APP_DIR = Path(__file__).resolve().parent


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an independently testable Truth Hunter application."""

    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.app_log_level)
    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        docs_url="/docs" if resolved_settings.app_env != "production" else None,
        redoc_url=None,
    )
    app.state.settings = resolved_settings
    app.state.templates = Jinja2Templates(directory=APP_DIR / "templates")

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=resolved_settings.trusted_hosts)

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> HTMLResponse:
        if exc.status_code == 404:
            return cast(
                HTMLResponse,
                app.state.templates.TemplateResponse(
                    request=request,
                    name="errors/404.html",
                    context={"app_name": resolved_settings.app_name},
                    status_code=404,
                ),
            )
        return HTMLResponse("Request failed", status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        del request, exc
        return JSONResponse({"detail": "Invalid request"}, status_code=422)

    app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
    app.include_router(router)
    return app


app = create_app()
