"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, Cookie, Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from crypto_probability_engine.adapters.public_market import BinancePublicAdapter, OkxPublicAdapter
from crypto_probability_engine.adapters.symbol_universe import resolve_symbol_availability
from crypto_probability_engine.api.analysis_service import (
    analyze_request,
    current_persistence_status,
    schedule_best_effort_persist,
)
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
    WatchlistRequest,
)
from crypto_probability_engine.config.settings import Settings, get_settings
from crypto_probability_engine.normalizers.symbols import SymbolNormalizationError, normalize_symbol
from crypto_probability_engine.persistence.repository import build_persistence_repository
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from crypto_probability_engine.telemetry.events import TelemetrySink
from crypto_probability_engine.utils.sanitize import sanitize_for_export

WATCHLIST_LIMIT = 20


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    run_store = InMemoryRunStore(limit=app_settings.recent_run_limit)
    persistence_repository = build_persistence_repository(app_settings)
    telemetry = TelemetrySink()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            close = getattr(persistence_repository, "close", None)
            if callable(close):
                close()

    app = FastAPI(
        title=app_settings.app_name,
        version=app_settings.app_version,
        lifespan=lifespan,
    )
    app.state.run_store = run_store
    app.state.persistence_repository = persistence_repository
    app.state.telemetry = telemetry

    origins = list(app_settings.strict_cors_origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["http://localhost:7860", "http://127.0.0.1:7860"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
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
        return system_status(
            app_settings,
            persistence=_persistence_diagnostic(app.state.persistence_repository),
        )

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
        background_tasks: BackgroundTasks,
        _session: dict = Depends(require_app_session),  # noqa: B008
    ) -> dict:
        repository = app.state.persistence_repository
        result = analyze_request(
            body,
            settings=app_settings,
            run_store=run_store,
            persistence_status=current_persistence_status(repository),
        )
        schedule_best_effort_persist(background_tasks, repository, result)
        telemetry.record("analysis_completed", {"run_id": result["run_id"]})
        return result

    @app.post("/v1/analyze_batch")
    def analyze_batch(
        body: BatchAnalysisRequest,
        background_tasks: BackgroundTasks,
        _session: dict = Depends(require_app_session),  # noqa: B008
    ) -> dict:
        results: list[dict] = []
        errors: list[dict] = []
        repository = app.state.persistence_repository
        for index, item in enumerate(body.requests):
            try:
                result = analyze_request(
                    item,
                    settings=app_settings,
                    run_store=run_store,
                    persistence_status=current_persistence_status(repository),
                )
                schedule_best_effort_persist(background_tasks, repository, result)
                results.append(result)
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

    @app.get("/v1/watchlist")
    def list_watchlist(session: dict = Depends(require_app_session)) -> dict:  # noqa: B008
        repository = app.state.persistence_repository
        operator_id = session.get("sub", "operator")
        return {
            "symbols": repository.list_watchlist(operator_id=operator_id),
            "persistence_status": repository.persistence_status(),
        }

    @app.post("/v1/watchlist")
    def add_watchlist(
        body: WatchlistRequest,
        session: dict = Depends(require_app_session),  # noqa: B008
    ) -> dict:
        repository = app.state.persistence_repository
        operator_id = session.get("sub", "operator")
        symbol = _normalize_watchlist_symbol(body.symbol, app_settings)
        symbols = repository.list_watchlist(operator_id=operator_id)
        if symbol not in symbols and len(symbols) >= WATCHLIST_LIMIT:
            raise api_error(400, ErrorCode.BATCH_LIMIT_EXCEEDED, "Watchlist limit is 20 symbols.")
        repository.add_watchlist(symbol, operator_id=operator_id)
        return {
            "symbols": repository.list_watchlist(operator_id=operator_id),
            "persistence_status": repository.persistence_status(),
        }

    @app.delete("/v1/watchlist/{symbol:path}")
    def remove_watchlist(
        symbol: str,
        session: dict = Depends(require_app_session),  # noqa: B008
    ) -> dict:
        repository = app.state.persistence_repository
        operator_id = session.get("sub", "operator")
        normalized = _normalize_watchlist_symbol(symbol, app_settings, validate_live_support=False)
        repository.remove_watchlist(normalized, operator_id=operator_id)
        return {
            "symbols": repository.list_watchlist(operator_id=operator_id),
            "persistence_status": repository.persistence_status(),
        }

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


def _normalize_watchlist_symbol(
    raw_symbol: str,
    settings: Settings,
    *,
    validate_live_support: bool = True,
) -> str:
    try:
        symbol = normalize_symbol(raw_symbol)
    except SymbolNormalizationError as exc:
        raise api_error(400, ErrorCode.INVALID_SYMBOL, "Invalid or unsupported symbol.") from exc
    if validate_live_support and settings.data_mode == "live":
        providers = [
            provider
            for provider in (
                BinancePublicAdapter(settings=settings),
                OkxPublicAdapter(settings=settings),
            )
            if provider.name in settings.provider_priority
        ]
        resolution = resolve_symbol_availability(
            symbol,
            providers,
            ttl_seconds=settings.symbol_universe_cache_ttl_seconds,
        )
        if resolution.availability == "UNSUPPORTED":
            raise api_error(400, ErrorCode.INVALID_SYMBOL, "Unsupported spot USDT symbol.")
        if settings.cross_provider_required and resolution.availability in {
            "BINANCE_ONLY",
            "OKX_ONLY",
        }:
            message = (
                "Cross-provider confirmation required but symbol is available on only one provider."
            )
            raise api_error(
                400,
                ErrorCode.PROVIDER_DEGRADED,
                message,
            )
    return symbol.display


def _persistence_diagnostic(repository) -> dict:
    status = current_persistence_status(repository)
    repository_type = _safe_repository_field(repository, "repository_type", "IN_MEMORY")
    circuit_state = _safe_repository_field(repository, "circuit_state", "STATELESS")
    return {
        "persistence_status": status,
        "repository_type": repository_type,
        "circuit_state": circuit_state,
    }


def _safe_repository_field(repository, method_name: str, fallback: str) -> str:
    method = getattr(repository, method_name, None)
    if not callable(method):
        return fallback
    try:
        value = method()
    except Exception:
        return fallback
    return str(value)
