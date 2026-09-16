"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, Cookie, Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
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
    clear_session_cookies,
    session_prediction_origin,
    set_session_cookie,
    verify_session_token,
)
from crypto_probability_engine.api.calibration_endpoint import (
    register_calibration_endpoint,
    schedule_skill_evidence_refresh,
)
from crypto_probability_engine.api.errors import api_error
from crypto_probability_engine.api.health import runtime_health, system_status
from crypto_probability_engine.api.schemas import (
    AnalysisRequest,
    BatchAnalysisRequest,
    BuildInfoResponse,
    ErrorCode,
    WatchlistRequest,
)
from crypto_probability_engine.config.build_info import build_info_payload
from crypto_probability_engine.config.settings import Settings, get_settings
from crypto_probability_engine.normalizers.symbols import SymbolNormalizationError, normalize_symbol
from crypto_probability_engine.persistence.prediction_origin import PredictionOrigin
from crypto_probability_engine.persistence.repository import (
    build_operator_repository,
    build_persistence_repository,
)
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from crypto_probability_engine.telemetry.events import TelemetrySink
from crypto_probability_engine.utils.sanitize import sanitize_for_export

WATCHLIST_LIMIT = 20
FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    run_store = InMemoryRunStore(limit=app_settings.recent_run_limit)
    persistence_repository = build_persistence_repository(app_settings)
    try:
        skill_evidence_repository = build_operator_repository(app_settings)
    except Exception:
        skill_evidence_repository = None
    telemetry = TelemetrySink()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            repositories = (persistence_repository, skill_evidence_repository)
            for repository in repositories:
                close = getattr(repository, "close", None)
                if callable(close):
                    close()

    app = FastAPI(
        title=app_settings.app_name,
        version=app_settings.app_version,
        lifespan=lifespan,
    )
    app.state.run_store = run_store
    app.state.persistence_repository = persistence_repository
    app.state.skill_evidence_repository = skill_evidence_repository
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

    @app.get("/v1/build-info", response_model=BuildInfoResponse)
    def get_build_info() -> JSONResponse:
        payload = BuildInfoResponse.model_validate(build_info_payload()).model_dump(mode="json")
        return JSONResponse(
            content=payload,
            headers={
                "Cache-Control": "no-store",
                "Pragma": "no-cache",
            },
        )

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

    @app.post("/v1/auth/logout")
    def logout(
        response: Response,
        _session: dict = Depends(require_app_session),  # noqa: B008
    ) -> dict:
        clear_session_cookies(response, app_settings)
        return {"ok": True}

    @app.post("/v1/auth/dev")
    def dev_login(body: LoginRequest, request: Request, response: Response) -> dict:
        token = authenticate_dev(request, body, app_settings)
        set_session_cookie(response, token, app_settings, dev=True)
        return {"ok": True}

    @app.get("/v1/auth/dev")
    def dev_status(_session: dict = Depends(require_app_dev_session)) -> dict:  # noqa: B008
        return {"ok": True}

    register_calibration_endpoint(
        app,
        require_app_session=require_app_session,
        settings=app_settings,
    )

    @app.post("/v1/analyze")
    def analyze(
        body: AnalysisRequest,
        background_tasks: BackgroundTasks,
        session: dict = Depends(require_app_session),  # noqa: B008
    ) -> dict:
        repository = app.state.persistence_repository
        prediction_origin = session_prediction_origin(session)
        result = analyze_request(
            body,
            settings=app_settings,
            run_store=run_store,
            persistence_status=current_persistence_status(repository),
            prediction_origin=prediction_origin,
        )
        schedule_best_effort_persist(
            background_tasks,
            repository,
            result,
            prediction_origin=prediction_origin,
        )
        schedule_skill_evidence_refresh(
            background_tasks,
            app.state.skill_evidence_repository,
        )
        telemetry.record("analysis_completed", {"run_id": result["run_id"]})
        return result

    @app.post("/v1/analyze_batch")
    def analyze_batch(
        body: BatchAnalysisRequest,
        background_tasks: BackgroundTasks,
        session: dict = Depends(require_app_session),  # noqa: B008
    ) -> dict:
        results: list[dict] = []
        errors: list[dict] = []
        items: list[dict] = []
        repository = app.state.persistence_repository
        prediction_origin = session_prediction_origin(session)
        for index, item in enumerate(body.requests):
            try:
                result = analyze_request(
                    item,
                    settings=app_settings,
                    run_store=run_store,
                    persistence_status=current_persistence_status(repository),
                    prediction_origin=prediction_origin,
                )
                schedule_best_effort_persist(
                    background_tasks,
                    repository,
                    result,
                    prediction_origin=prediction_origin,
                )
                results.append(result)
                items.append(
                    {
                        "index": index,
                        "symbol": item.symbol,
                        "status": "OK",
                        "run_id": result["run_id"],
                    }
                )
            except Exception as exc:
                if hasattr(exc, "detail"):
                    detail = exc.detail
                else:
                    detail = api_error(
                        500,
                        ErrorCode.BACKEND_TIMEOUT,
                        "Batch item failed.",
                    ).detail
                errors.append({"index": index, "detail": detail, "symbol": item.symbol})
                items.append(
                    {
                        "index": index,
                        "symbol": item.symbol,
                        "status": "ERROR",
                        "detail": detail,
                    }
                )
        schedule_skill_evidence_refresh(
            background_tasks,
            app.state.skill_evidence_repository,
        )
        return {"results": results, "errors": errors, "items": items}

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
        if payload and not any(
            row.get("run_id") == run_id
            and row.get("prediction_origin") == PredictionOrigin.USER_REQUESTED.value
            for row in run_store.list_runs()
        ):
            raise api_error(404, ErrorCode.RUN_NOT_FOUND, "Run not found.")
        if not payload:
            durable = app.state.persistence_repository.get_run_detail(
                run_id,
                prediction_origin=PredictionOrigin.USER_REQUESTED.value,
            )
            if not durable:
                raise api_error(404, ErrorCode.RUN_NOT_FOUND, "Run not found.")
            return durable
        return payload["detail_view"]

    @app.get("/v1/runs")
    def recent_runs(_session: dict = Depends(require_app_session)) -> dict:  # noqa: B008
        origin = PredictionOrigin.USER_REQUESTED.value
        repository = app.state.persistence_repository
        source = "durable"
        try:
            rows = repository.recent_runs_for_origin(
                app_settings.recent_run_limit,
                prediction_origin=origin,
            )
            if repository.persistence_status() != "OK":
                raise RuntimeError("durable persistence is unavailable")
        except Exception:
            source = "in_process"
            rows = [
                row
                for row in run_store.list_runs()
                if row.get("prediction_origin") == origin
            ]

        durable_only_ids = [
            str(row.get("run_id"))
            for row in rows
            if run_store.get(str(row.get("run_id"))) is None
        ]
        try:
            durable_detail_ids = repository.run_ids_with_detail(
                durable_only_ids,
                prediction_origin=origin,
            )
        except Exception:
            durable_detail_ids = set()

        normalized = []
        for row in rows:
            run_id = str(row.get("run_id"))
            in_process_detail = run_store.get(run_id) is not None
            normalized.append(
                {
                    "run_id": row.get("run_id"),
                    "symbol": row.get("symbol"),
                    "normalized_symbol": row.get("normalized_symbol"),
                    "analysis_mode": row.get("analysis_mode"),
                    "as_of_utc": row.get("as_of_utc"),
                    "analysis_hash": row.get("analysis_hash"),
                    "prediction_origin": origin,
                    "detail_available": in_process_detail
                    or run_id in durable_detail_ids,
                    "primary_timeframe": row.get("primary_timeframe"),
                    "data_source": row.get("data_source"),
                    "is_live_data": row.get("is_live_data"),
                }
            )
        return {"source": source, "runs": normalized}

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
                "news_evidence": sanitized["news_evidence"],
                "micro_news_context": sanitized["micro_news_context"],
                "macro_context": sanitized["macro_context"],
            },
        }

    @app.get("/", include_in_schema=False)
    @app.get("/index.html", include_in_schema=False)
    def frontend_index() -> FileResponse:
        return FileResponse(
            FRONTEND_DIR / "index.html",
            media_type="text/html",
            headers={
                "Cache-Control": "no-store",
                "Pragma": "no-cache",
            },
        )

    if FRONTEND_DIR.exists():
        app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

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
