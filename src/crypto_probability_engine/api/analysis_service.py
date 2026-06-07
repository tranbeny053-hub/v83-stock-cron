"""End-to-end analysis service wiring for Sprint 1."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from uuid import uuid4

from fastapi import BackgroundTasks

from crypto_probability_engine.adapters.provider_selection import (
    ProviderSelectionError,
    select_market_data,
)
from crypto_probability_engine.api.errors import api_error
from crypto_probability_engine.api.schemas import (
    AnalysisRequest,
    AnalysisResponse,
    AssetClass,
    ErrorCode,
)
from crypto_probability_engine.config.defaults import DEFAULT_PHASE1A
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.detail.builder import build_detail_view
from crypto_probability_engine.detail.frontend_display import build_frontend_display
from crypto_probability_engine.news.contract import build_news_blocks
from crypto_probability_engine.normalizers.symbols import SymbolNormalizationError, normalize_symbol
from crypto_probability_engine.persistence.repository import PersistenceRepository
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from crypto_probability_engine.quant.pipeline import run_quant_pipeline, stable_hash

_PERSISTENCE_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ucpe-persist")


@dataclass(frozen=True)
class PersistenceWork:
    run_summary: dict
    timeframe_result: dict
    provider_observations: tuple[dict, ...]


def analyze_request(
    request: AnalysisRequest,
    *,
    settings: Settings,
    run_store: InMemoryRunStore,
    persistence_status: str = "STATELESS",
) -> dict:
    if request.asset_class == AssetClass.CRYPTO_PERP and not settings.enable_derivatives:
        raise api_error(
            400,
            ErrorCode.UNSUPPORTED_ASSET_CLASS,
            "CRYPTO_PERP requires explicit derivatives enablement.",
        )
    if request.asset_class != AssetClass.CRYPTO_SPOT:
        raise api_error(400, ErrorCode.UNSUPPORTED_ASSET_CLASS, "Unsupported asset class.")
    if request.timeframe not in DEFAULT_PHASE1A.timeframes:
        raise api_error(400, ErrorCode.SCHEMA_VALIDATION_FAILED, "Unsupported timeframe.")
    try:
        symbol = normalize_symbol(request.symbol)
    except SymbolNormalizationError as exc:
        raise api_error(400, ErrorCode.INVALID_SYMBOL, "Invalid or unsupported symbol.") from exc

    try:
        selection = select_market_data(symbol, request.timeframe, settings=settings)
    except ProviderSelectionError as exc:
        raise api_error(
            _status_for_selection_error(exc.code),
            exc.code,
            exc.message,
            provider_state_snapshot={
                "provider_state": exc.provider_state,
                "data_quality": exc.data_quality,
            },
        ) from exc

    snapshot = selection.snapshot
    provider_state = selection.provider_state
    data_quality = selection.data_quality
    quant_result = run_quant_pipeline(snapshot, provider_state)
    news_blocks = build_news_blocks(
        analysis_mode=request.analysis_mode,
        symbol=symbol.display,
    )
    run_id = f"run_{uuid4().hex}"
    frontend_display = build_frontend_display(
        quant_result,
        news_blocks,
        request.analysis_mode.value,
        data_quality,
    )
    detail_view = build_detail_view(
        symbol=symbol.display,
        run_id=run_id,
        analysis_mode=request.analysis_mode.value,
        quant_result=quant_result,
        news_blocks=news_blocks,
        provider_state=provider_state,
        data_quality=data_quality,
    )
    response = {
        "schema_version": settings.schema_version,
        "run_id": run_id,
        "symbol": request.symbol,
        "normalized_symbol": symbol.display,
        "asset_class": request.asset_class.value,
        "analysis_mode": request.analysis_mode.value,
        "timeframes": {
            "primary": request.timeframe,
            "trend": list(DEFAULT_PHASE1A.trend_timeframes),
            "H_primary_bars": DEFAULT_PHASE1A.h_primary_bars,
            "H_extended_bars": DEFAULT_PHASE1A.h_extended_bars,
        },
        "as_of_utc": snapshot.as_of_utc.isoformat().replace("+00:00", "Z"),
        "provider_state": provider_state,
        "data_quality": data_quality,
        "market_features": quant_result["market_features"],
        "liquidity_state": quant_result["liquidity_state"],
        "execution_realism": quant_result["execution_realism"],
        "quant_compute_state": quant_result["quant_compute_state"],
        "epistemic_sufficiency_state": quant_result["epistemic_sufficiency_state"],
        "probability_state": quant_result["probability_state"],
        "horizon_timeout_state": quant_result["horizon_timeout_state"],
        "risk_arbiter_state": quant_result["risk_arbiter_state"],
        "tail_risk_state": quant_result["tail_risk_state"],
        "calibration_state": quant_result["calibration_state"],
        "macro_context": news_blocks["macro_context"],
        "micro_news_context": news_blocks["micro_news_context"],
        "news_addon_state": news_blocks["news_addon_state"],
        "news_materiality_state": news_blocks["news_materiality_state"],
        "event_horizon_state": news_blocks["event_horizon_state"],
        "narrative_state": news_blocks["narrative_state"],
        "novelty_surprise_state": news_blocks["novelty_surprise_state"],
        "source_confidence_state": news_blocks["source_confidence_state"],
        "information_state": news_blocks["information_state"],
        "catalyst_state": news_blocks["catalyst_state"],
        "score_stack": quant_result["score_stack"],
        "trend_summary": quant_result["trend_summary"],
        "frontend_display": frontend_display,
        "detail_view": detail_view,
        "gate_result": quant_result["gate_result"],
        "debug": {
            "warnings": list(data_quality.get("warnings", [])),
            "news_influence": news_blocks["news_influence"],
            "analysis_hash_source": "backend_only",
            "persistence_status": persistence_status,
        },
        "analysis_hash": "",
    }
    response["analysis_hash"] = stable_hash(response)
    validated = AnalysisResponse.model_validate(response).model_dump(mode="json")
    validated["detail_view"]["debug_lite"]["persistence_status"] = persistence_status
    run_store.put(run_id, validated)
    return validated


def _status_for_selection_error(code: ErrorCode) -> int:
    if code == ErrorCode.DATA_CONFLICT:
        return 409
    if code == ErrorCode.INVALID_SYMBOL:
        return 400
    return 503


def current_persistence_status(repository: PersistenceRepository | None) -> str:
    if repository is None:
        return "STATELESS"
    try:
        return repository.persistence_status()
    except Exception:
        mark_unavailable = getattr(repository, "mark_unavailable", None)
        if callable(mark_unavailable):
            mark_unavailable()
        return "UNAVAILABLE"


def schedule_best_effort_persist(
    background_tasks: BackgroundTasks,
    repository: PersistenceRepository | None,
    payload: dict,
) -> str:
    status = current_persistence_status(repository)
    if repository is None:
        return status
    work = _persistence_work(payload, status)
    background_tasks.add_task(_submit_persistence_work, repository, work)
    return status


def _submit_persistence_work(repository: PersistenceRepository, work: PersistenceWork) -> None:
    try:
        _PERSISTENCE_EXECUTOR.submit(_best_effort_persist, work, repository)
    except Exception:
        mark_unavailable = getattr(repository, "mark_unavailable", None)
        if callable(mark_unavailable):
            mark_unavailable()


def _best_effort_persist(
    work: PersistenceWork,
    repository: PersistenceRepository | None,
) -> str:
    if repository is None:
        return "STATELESS"
    try:
        statuses = [
            repository.save_run(work.run_summary),
            repository.save_timeframe_result(work.timeframe_result),
        ]
        statuses.extend(
            repository.save_provider_observation(row) for row in work.provider_observations
        )
    except Exception:
        mark_unavailable = getattr(repository, "mark_unavailable", None)
        if callable(mark_unavailable):
            mark_unavailable()
        return "UNAVAILABLE"
    if any(status == "UNAVAILABLE" for status in statuses):
        return "UNAVAILABLE"
    return repository.persistence_status()


def _persistence_work(payload: dict, persistence_status: str) -> PersistenceWork:
    run_summary = _run_summary(payload)
    run_summary["persistence_status"] = persistence_status
    return PersistenceWork(
        run_summary=run_summary,
        timeframe_result=_timeframe_result(payload),
        provider_observations=tuple(_provider_observations(payload)),
    )


def _run_summary(payload: dict) -> dict:
    display = payload.get("frontend_display", {})
    data_quality = payload.get("data_quality", {})
    return {
        "run_id": payload.get("run_id"),
        "operator_id": "operator",
        "symbol": payload.get("symbol"),
        "normalized_symbol": payload.get("normalized_symbol"),
        "analysis_mode": payload.get("analysis_mode"),
        "asset_class": payload.get("asset_class"),
        "primary_timeframe": payload.get("timeframes", {}).get("primary"),
        "disposition": display.get("disposition"),
        "total_score": display.get("total_score"),
        "data_source": data_quality.get("data_source"),
        "is_live_data": bool(data_quality.get("is_live_data", False)),
        "persistence_status": payload.get("debug", {}).get("persistence_status", "STATELESS"),
        "analysis_hash": payload.get("analysis_hash"),
        "as_of_utc": payload.get("as_of_utc"),
    }


def _timeframe_result(payload: dict) -> dict:
    display = payload.get("frontend_display", {})
    return {
        "run_id": payload.get("run_id"),
        "timeframe": payload.get("timeframes", {}).get("primary"),
        "disposition": display.get("disposition"),
        "total_score": display.get("total_score"),
        "prob_up_pct": display.get("prob_up_pct"),
        "prob_down_pct": display.get("prob_down_pct"),
        "prob_timeout_pct": display.get("prob_timeout_pct"),
        "gate_action": payload.get("gate_result", {}).get("action"),
        "data_source": payload.get("data_quality", {}).get("data_source"),
        "is_live_data": bool(payload.get("data_quality", {}).get("is_live_data", False)),
    }


def _provider_observations(payload: dict) -> list[dict]:
    provider_state = payload.get("provider_state", {})
    data_quality = payload.get("data_quality", {})
    providers = provider_state.get("providers") or {}
    rows: list[dict] = []
    for provider, state in providers.items():
        warnings = state.get("warnings", []) if isinstance(state, dict) else []
        rows.append(
            {
                "run_id": payload.get("run_id"),
                "provider": provider,
                "provider_status": state.get("status") if isinstance(state, dict) else None,
                "active_provider": provider_state.get("active_provider"),
                "data_source": data_quality.get("data_source"),
                "is_live_data": bool(data_quality.get("is_live_data", False)),
                "warning_count": len(warnings),
            }
        )
    if not rows:
        rows.append(
            {
                "run_id": payload.get("run_id"),
                "provider": provider_state.get("active_provider") or "provider_selection",
                "provider_status": provider_state.get("status"),
                "active_provider": provider_state.get("active_provider"),
                "data_source": data_quality.get("data_source"),
                "is_live_data": bool(data_quality.get("is_live_data", False)),
                "warning_count": len(data_quality.get("warnings", [])),
            }
        )
    return rows
