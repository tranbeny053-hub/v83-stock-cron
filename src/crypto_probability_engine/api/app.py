"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import Cookie, Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from crypto_probability_engine.api.analysis_service import analyze_request
from crypto_probability_engine.api.auth import (
    DEV_SESSION_COOKIE,
    SESSION_COOKIE,
    LoginRequest,
    authenticate_dev,
    authenticate_login,
    set_session_cookie,
    verify_session_token,
)
from crypto_probability_engine.api.errors import api_error
from crypto_probability_engine.api.health import runtime_health, system_status
from crypto_probability_engine.api.schemas import (
    AnalysisRequest,
    BatchAnalysisRequest,
    ErrorCode,
)
from crypto_probability_engine.config.settings import Settings, get_settings
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from crypto_probability_engine.telemetry.events import TelemetrySink
from crypto_probability_engine.utils.sanitize import sanitize_for_export


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    app = FastAPI(title=app_settings.app_name, version=app_settings.app_version)
    run_store = InMemoryRunStore(limit=app_settings.recent_run_limit)
    telemetry = TelemetrySink()
    app.state.run_store = run_store
    app.state.telemetry = telemetry

    origins = list(app_settings.strict_cors_origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["http://localhost:7860", "http://127.0.0.1:7860"],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        if hasattr(exc, "status_code") and hasattr(exc, "detail"):
            raise exc
        return JSONResponse(
            status_code=500,
            content=api_error(
                500,
                ErrorCode.BACKEND_TIMEOUT,
                "Unexpected backend failure.",
            ).detail,
        )

    @app.get("/healthcheck")
    def healthcheck() -> dict:
        return runtime_health(app_settings)

    def require_app_session(
        session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),  # noqa: B008
    ) -> dict:
        return verify_session_token(session_token, app_settings)

    def require_app_dev_session(
        session_token: str | None = Cookie(default=None, alias=DEV_SESSION_COOKIE),  # noqa: B008
    ) -> dict:
        return verify_session_token(session_token, app_settings, require_dev=True)

    @app.get("/v1/system_status")
    def get_system_status(_session: dict = Depends(require_app_session)) -> dict:  # noqa: B008
        return system_status(app_settings)

    @app.post("/v1/auth/login")
    def login(body: LoginRequest, request: Request, response: Response) -> dict:
        token = authenticate_login(request, body, app_settings)
        set_session_cookie(response, token, app_settings)
        return {"ok": True}

    @app.post("/v1/auth/dev")
    def dev_login(body: LoginRequest, request: Request, response: Response) -> dict:
        token = authenticate_dev(request, body, app_settings)
        set_session_cookie(response, token, app_settings, dev=True)
        return {"ok": True}

    @app.get("/v1/auth/dev")
    def dev_status(_session: dict = Depends(require_app_dev_session)) -> dict:  # noqa: B008
        return {"ok": True}

    @app.post("/v1/analyze")
    def analyze(
        body: AnalysisRequest,
        _session: dict = Depends(require_app_session),  # noqa: B008
    ) -> dict:
        result = analyze_request(body, settings=app_settings, run_store=run_store)
        telemetry.record("analysis_completed", {"run_id": result["run_id"]})
        return result

    @app.post("/v1/analyze_batch")
    def analyze_batch(
        body: BatchAnalysisRequest,
        _session: dict = Depends(require_app_session),  # noqa: B008
    ) -> dict:
        results: list[dict] = []
        errors: list[dict] = []
        for index, item in enumerate(body.requests):
            try:
                results.append(analyze_request(item, settings=app_settings, run_store=run_store))
            except Exception as exc:
                if hasattr(exc, "detail"):
                    errors.append({"index": index, "detail": exc.detail})
                else:
                    errors.append(
                        {
                            "index": index,
                            "detail": api_error(
                                500,
                                ErrorCode.BACKEND_TIMEOUT,
                                "Batch item failed.",
                            ).detail,
                        }
                    )
        return {"results": results, "errors": errors}

    @app.get("/v1/analyze/detail/{run_id}")
    def analyze_detail(
        run_id: str,
        _session: dict = Depends(require_app_session),  # noqa: B008
    ) -> dict:
        payload = run_store.get(run_id)
        if not payload:
            raise api_error(404, ErrorCode.RUN_NOT_FOUND, "Run not found.")
        return payload["detail_view"]

    @app.get("/v1/debug/runs")
    def debug_runs(_session: dict = Depends(require_app_dev_session)) -> dict:  # noqa: B008
        return {"runs": run_store.list_runs()}

    @app.get("/v1/debug/runs/{run_id}")
    def debug_run(
        run_id: str,
        _session: dict = Depends(require_app_dev_session),  # noqa: B008
    ) -> dict:
        payload = run_store.get(run_id)
        if not payload:
            raise api_error(404, ErrorCode.RUN_NOT_FOUND, "Run not found.")
        return sanitize_for_export(payload)

    @app.get("/v1/debug/export/{run_id}")
    def debug_export(
        run_id: str,
        _session: dict = Depends(require_app_dev_session),  # noqa: B008
    ) -> dict:
        payload = run_store.get(run_id)
        if not payload:
            raise api_error(404, ErrorCode.RUN_NOT_FOUND, "Run not found.")
        sanitized = sanitize_for_export(payload)
        return {
            "debug_pack_version": "sprint1",
            "run": sanitized,
            "detail_view": sanitized["detail_view"],
            "news_addon_pack": {
                "news_addon_state": sanitized["news_addon_state"],
                "micro_news_context": sanitized["micro_news_context"],
                "macro_context": sanitized["macro_context"],
            },
        }

    frontend_dir = Path("frontend")
    if frontend_dir.exists():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

    return app


app = create_app()
