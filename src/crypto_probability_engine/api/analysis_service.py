"""End-to-end analysis service wiring for Sprint 1."""

from __future__ import annotations

import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
from crypto_probability_engine.calibration.skill import (
    get_cached_skill_evidence,
    insufficient_skill_evidence,
)
from crypto_probability_engine.config.defaults import (
    DEFAULT_PHASE1A,
    METHODOLOGY_VERSION,
    MODEL_VERSION,
    TIMEFRAME_SECONDS,
    min_history_for,
)
from crypto_probability_engine.config.env_flags import QUANT_V2_SHADOW_ENABLED
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.derivatives_intel.block import build_derivatives_intelligence
from crypto_probability_engine.derivatives_intel.schemas import (
    METHODOLOGY_VERSION_V0,
    METHODOLOGY_VERSION_V1,
)
from crypto_probability_engine.detail.builder import build_detail_view
from crypto_probability_engine.detail.decision_brief import (
    build_decision_brief,
    build_horizon_context,
)
from crypto_probability_engine.detail.decision_synthesis import build_decision_synthesis
from crypto_probability_engine.detail.frontend_display import build_frontend_display
from crypto_probability_engine.gates.composite import apply_skill_gate
from crypto_probability_engine.news.contract import build_news_blocks
from crypto_probability_engine.normalizers.symbols import SymbolNormalizationError, normalize_symbol
from crypto_probability_engine.oos.pair_context import (
    OOS_PREDICTION_ORIGIN,
    OOSArm,
    OOSPairContext,
    PairInvalidError,
    PairTarget,
    is_oos_run_id,
)
from crypto_probability_engine.persistence.derivatives_snapshot import (
    build_derivatives_snapshot,
)
from crypto_probability_engine.persistence.feature_snapshot import build_feature_snapshot
from crypto_probability_engine.persistence.prediction_origin import (
    DEFAULT_PREDICTION_ORIGIN,
    validate_prediction_origin,
)
from crypto_probability_engine.persistence.repository import (
    OOSArmIdentityConflict,
    PersistenceRepository,
)
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from crypto_probability_engine.quant.pipeline import run_quant_pipeline, stable_hash
from crypto_probability_engine.quant_v2.contract import build_quant_v2_shadow
from crypto_probability_engine.validation.market_data import (
    DataValidationError,
    validate_market_snapshot,
)

_PERSISTENCE_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ucpe-persist")
_PENDING_PREDICTION_ROWS: dict[str, dict] = {}
_PENDING_FEATURE_SNAPSHOT_ROWS: dict[str, dict | None] = {}
_PENDING_DERIVATIVES_SNAPSHOT_ROWS: dict[str, dict | None] = {}
_PENDING_DERIVATIVES_SNAPSHOT_REQUIRED: dict[str, bool] = {}
_PENDING_PREDICTION_LOCK = threading.Lock()
_ALLOWED_DERIVATIVES_METHODOLOGY_VERSIONS = frozenset(
    {
        METHODOLOGY_VERSION_V0,
        METHODOLOGY_VERSION_V1,
    }
)


@dataclass(frozen=True)
class PersistenceWork:
    run_summary: dict
    timeframe_result: dict
    provider_observations: tuple[dict, ...]
    news_items: tuple[dict, ...] = ()
    news_clusters: tuple[dict, ...] = ()
    news_evidence_links: tuple[dict, ...] = ()
    prediction_rows: tuple[dict, ...] = ()
    feature_snapshot_rows: tuple[dict, ...] = ()
    feature_snapshot_build_failed: bool = False
    derivatives_snapshot_rows: tuple[dict, ...] = ()
    derivatives_snapshot_build_failed: bool = False


@dataclass(frozen=True)
class _PersistenceConfirmation:
    prediction: str | None
    feature_snapshot: str | None
    derivatives_snapshot: str | None
    overall: str
    background_status: str

    def public_result(self) -> dict[str, object]:
        return {
            "prediction": self.prediction,
            "feature_snapshot": self.feature_snapshot,
            "derivatives_snapshot": self.derivatives_snapshot,
            "overall": self.overall,
        }


def analyze_request(
    request: AnalysisRequest,
    *,
    settings: Settings,
    run_store: InMemoryRunStore,
    persistence_status: str = "STATELESS",
    prediction_origin: str = DEFAULT_PREDICTION_ORIGIN,
    deterministic_identity: bool = False,
    derivatives_methodology_version: str = METHODOLOGY_VERSION_V0,
    methodology_version: str = METHODOLOGY_VERSION,
    pair_context: OOSPairContext | None = None,
    arm: OOSArm | str | None = None,
) -> dict:
    prediction_origin = validate_prediction_origin(prediction_origin)
    if not isinstance(methodology_version, str) or not methodology_version:
        raise api_error(
            400,
            ErrorCode.SCHEMA_VALIDATION_FAILED,
            "Methodology version must be a non-empty string.",
        )
    try:
        arm_context = _oos_arm_context(
            pair_context=pair_context,
            arm=arm,
            prediction_origin=prediction_origin,
            deterministic_identity=deterministic_identity,
        )
    except PairInvalidError as exc:
        raise api_error(
            400,
            ErrorCode.SCHEMA_VALIDATION_FAILED,
            str(exc),
        ) from exc
    if (
        not isinstance(derivatives_methodology_version, str)
        or derivatives_methodology_version
        not in _ALLOWED_DERIVATIVES_METHODOLOGY_VERSIONS
    ):
        raise api_error(
            400,
            ErrorCode.SCHEMA_VALIDATION_FAILED,
            "Unsupported derivatives methodology version.",
        )
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
    if arm_context is not None:
        if (
            arm_context.market_snapshot.normalized_symbol != symbol.display
            or arm_context.market_snapshot.timeframe != request.timeframe
        ):
            raise api_error(
                400,
                ErrorCode.SCHEMA_VALIDATION_FAILED,
                "OOS pair snapshot does not match the requested market and timeframe.",
            )
        snapshot = arm_context.market_snapshot
    deterministic_run_id = (
        _deterministic_cadence_run_id(
            normalized_symbol=symbol.display,
            timeframe=request.timeframe,
            snapshot=snapshot,
        )
        if deterministic_identity
        else None
    )
    quant_result = run_quant_pipeline(snapshot, provider_state)
    skill_evidence = (
        arm_context.resolved_skill_evidence
        if arm_context is not None
        else _skill_evidence_for_analysis(request.timeframe)
    )
    quant_result = _apply_skill_evidence_gate(quant_result, skill_evidence)
    news_blocks = build_news_blocks(
        analysis_mode=request.analysis_mode,
        symbol=symbol.display,
        settings=settings,
    )
    if arm_context is not None:
        run_id = arm_context.run_id
    elif deterministic_identity:
        if deterministic_run_id is None:
            raise _cadence_identity_error()
        run_id = deterministic_run_id
    else:
        run_id = f"run_{uuid4().hex}"
    horizon_context = build_horizon_context(request.timeframe)
    frontend_display = build_frontend_display(
        quant_result,
        news_blocks,
        request.analysis_mode.value,
        data_quality,
        horizon_context,
    )
    decision_brief = build_decision_brief(
        symbol=request.symbol,
        normalized_symbol=symbol.display,
        timeframe=request.timeframe,
        quant_result=quant_result,
        data_quality=data_quality,
    )
    decision_synthesis = build_decision_synthesis(
        timeframe=request.timeframe,
        quant_result=quant_result,
        data_quality=data_quality,
        provider_state=provider_state,
        decision_brief=decision_brief,
    )
    detail_view = build_detail_view(
        symbol=symbol.display,
        run_id=run_id,
        analysis_mode=request.analysis_mode.value,
        quant_result=quant_result,
        news_blocks=news_blocks,
        provider_state=provider_state,
        data_quality=data_quality,
        decision_brief=decision_brief,
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
            **horizon_context,
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
        "news_evidence": news_blocks["news_evidence"],
        "news_materiality_state": news_blocks["news_materiality_state"],
        "event_horizon_state": news_blocks["event_horizon_state"],
        "narrative_state": news_blocks["narrative_state"],
        "novelty_surprise_state": news_blocks["novelty_surprise_state"],
        "source_confidence_state": news_blocks["source_confidence_state"],
        "information_state": news_blocks["information_state"],
        "catalyst_state": news_blocks["catalyst_state"],
        "score_stack": quant_result["score_stack"],
        "trend_summary": quant_result["trend_summary"],
        "decision_brief": decision_brief,
        "decision_synthesis": decision_synthesis,
        "frontend_display": frontend_display,
        "detail_view": detail_view,
        "gate_result": quant_result["gate_result"],
        "skill_evidence": skill_evidence,
        "debug": {
            "warnings": list(data_quality.get("warnings", [])),
            "news_influence": news_blocks["news_influence"],
            "analysis_hash_source": "backend_only",
            "persistence_status": persistence_status,
        },
        "analysis_hash": "",
    }
    response["analysis_hash"] = stable_hash(response)
    prediction_row = _prediction_row(
        run_id=run_id,
        request_symbol=request.symbol,
        normalized_symbol=symbol.display,
        timeframe=request.timeframe,
        snapshot=snapshot,
        quant_result=quant_result,
        data_quality=data_quality,
        provider_state=provider_state,
        prediction_origin=prediction_origin,
        arm=arm_context.arm if arm_context is not None else None,
        target=arm_context.target if arm_context is not None else None,
        methodology_version=methodology_version,
    )
    response["quant_v2"] = build_quant_v2_shadow(
        quant_result=quant_result,
        snapshot=snapshot,
        provider_state=provider_state,
        symbol=request.symbol,
        normalized_symbol=symbol.display,
        timeframe=request.timeframe,
        enabled=QUANT_V2_SHADOW_ENABLED,
    )
    response["derivatives_intelligence"] = build_derivatives_intelligence(
        normalized_symbol=symbol.display,
        core_prediction_as_of_utc=snapshot.as_of_utc,
        enabled=settings.enable_derivatives_intel,
        rate_limit_per_min=settings.provider_rate_limit_per_min,
        methodology_version=derivatives_methodology_version,
    )
    feature_snapshot_row = build_feature_snapshot(prediction_row, response["quant_v2"])
    validated = AnalysisResponse.model_validate(response).model_dump(mode="json")
    derivatives_block = validated["derivatives_intelligence"]
    derivatives_snapshot_required = derivatives_block["block_status"] in {
        "ACTIVE",
        "DEGRADED",
        "UNAVAILABLE",
    }
    try:
        derivatives_snapshot_row = build_derivatives_snapshot(
            prediction_row,
            derivatives_block,
        )
    except Exception:
        derivatives_snapshot_row = None
    if prediction_row is not None:
        _remember_prediction_persistence(
            run_id,
            prediction_row,
            feature_snapshot_row,
            derivatives_snapshot_row,
            derivatives_snapshot_required=derivatives_snapshot_required,
        )
    validated["detail_view"]["debug_lite"]["persistence_status"] = persistence_status
    run_store.put(run_id, validated)
    return validated


def _skill_evidence_for_analysis(timeframe: str) -> dict:
    try:
        return get_cached_skill_evidence(timeframe)
    except Exception:
        return insufficient_skill_evidence()


def _oos_arm_context(
    *,
    pair_context: OOSPairContext | None,
    arm: OOSArm | str | None,
    prediction_origin: str,
    deterministic_identity: bool,
):
    if pair_context is None and arm is None:
        return None
    if pair_context is None or arm is None:
        raise PairInvalidError("OOS pair context and arm must be supplied together.")
    if deterministic_identity:
        raise PairInvalidError("OOS identity cannot use the derivatives cadence identity.")
    if prediction_origin != pair_context.prediction_origin:
        raise PairInvalidError(
            "OOS pairs require SCHEDULED_SHADOW_EVIDENCE origin."
        )
    return pair_context.for_arm(arm)


def _apply_skill_evidence_gate(quant_result: dict, skill_evidence: dict) -> dict:
    gate = apply_skill_gate(
        quant_result.get("gate_result") or {},
        skill_state=skill_evidence,
    )
    score = dict(quant_result.get("score_stack") or {})
    forced_disposition = gate.get("forced_score_disposition")
    if forced_disposition:
        score["disposition"] = forced_disposition
    return {
        **quant_result,
        "score_stack": score,
        "gate_result": gate,
    }


def _status_for_selection_error(code: ErrorCode) -> int:
    if code == ErrorCode.DATA_CONFLICT:
        return 409
    if code == ErrorCode.INVALID_SYMBOL:
        return 400
    return 503


def _deterministic_cadence_run_id(
    *,
    normalized_symbol: str,
    timeframe: str,
    snapshot,
) -> str:
    try:
        canonical_symbol = normalize_symbol(normalized_symbol).display
    except (SymbolNormalizationError, TypeError, ValueError) as exc:
        raise _cadence_identity_error() from exc
    if (
        not normalized_symbol
        or canonical_symbol != normalized_symbol
        or timeframe not in TIMEFRAME_SECONDS
    ):
        raise _cadence_identity_error()
    try:
        validate_market_snapshot(snapshot, min_bars=min_history_for(timeframe))
        candles = tuple(getattr(snapshot, "candles", ()) or ())
        reference_candle = candles[-1]
        reference_close = reference_candle.close_time_utc
        snapshot_as_of = snapshot.as_of_utc
        snapshot_symbol = str(snapshot.normalized_symbol)
        snapshot_timeframe = str(snapshot.timeframe)
    except (AttributeError, DataValidationError, IndexError, TypeError, ValueError) as exc:
        raise _cadence_identity_error() from exc
    if (
        snapshot_symbol != normalized_symbol
        or snapshot_timeframe != timeframe
        or not _is_utc_datetime(reference_close)
        or not _is_utc_datetime(snapshot_as_of)
        or reference_close > snapshot_as_of
    ):
        raise _cadence_identity_error()
    try:
        reference_close_utc = _iso_utc(reference_close)
    except (AttributeError, TypeError, ValueError) as exc:
        raise _cadence_identity_error() from exc
    material = "|".join(
        (
            "derivatives-evidence-cadence-v1",
            MODEL_VERSION,
            METHODOLOGY_VERSION,
            normalized_symbol,
            timeframe,
            reference_close_utc,
        )
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"cadence-{digest[:32]}"


def _cadence_identity_error():
    return api_error(
        400,
        ErrorCode.SCHEMA_VALIDATION_FAILED,
        "Deterministic cadence identity requires a validated fully closed candle.",
    )


def _is_utc_datetime(value: object) -> bool:
    return bool(
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
        and value.utcoffset() == timedelta(0)
    )


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
    return _persist_work_confirmed(work, repository).background_status


def persist_analysis_now(
    payload: dict,
    repository,
) -> dict[str, object]:
    """Synchronously persist approved analysis artifacts and confirm their statuses."""

    unavailable = {
        "prediction": None,
        "feature_snapshot": None,
        "derivatives_snapshot": None,
        "overall": "UNAVAILABLE",
    }
    if repository is None:
        return unavailable
    try:
        payload_copy = deepcopy(payload)
        work = _persistence_work(
            payload_copy,
            current_persistence_status(repository),
            consume_pending=False,
        )
        return _persist_work_confirmed(work, repository).public_result()
    except OOSArmIdentityConflict:
        raise
    except Exception:
        _mark_repository_unavailable(repository)
        return unavailable


def _persist_work_confirmed(
    work: PersistenceWork,
    repository: PersistenceRepository | None,
) -> _PersistenceConfirmation:
    if repository is None:
        return _PersistenceConfirmation(None, None, None, "UNAVAILABLE", "STATELESS")
    prediction_confirmation: str | None = None
    feature_confirmation: str | None = None
    derivatives_confirmation: str | None = None
    auxiliary_unavailable = False
    unexpected_failure = False
    terminal_repository_unavailable = False
    try:
        statuses = [
            _status_text(repository.save_run(work.run_summary)),
            _status_text(repository.save_timeframe_result(work.timeframe_result)),
        ]
        statuses.extend(
            _status_text(repository.save_provider_observation(row))
            for row in work.provider_observations
        )
        statuses.extend(_status_text(repository.save_news_item(row)) for row in work.news_items)
        statuses.extend(
            _status_text(repository.save_news_cluster(row)) for row in work.news_clusters
        )
        statuses.extend(
            _status_text(repository.save_news_evidence_link(row))
            for row in work.news_evidence_links
        )
        snapshot_rows = {
            str(row.get("prediction_id", "")): row for row in work.feature_snapshot_rows
        }
        derivatives_snapshot_rows = {
            str(row.get("prediction_id", "")): row
            for row in work.derivatives_snapshot_rows
        }
        snapshot_issue = work.feature_snapshot_build_failed
        derivatives_snapshot_issue = work.derivatives_snapshot_build_failed
        for prediction_row in work.prediction_rows:
            prediction_status = _status_text(repository.save_prediction(prediction_row))
            prediction_confirmation = _merge_artifact_status(
                prediction_confirmation,
                prediction_status,
            )
            statuses.append(prediction_status)
            if prediction_status not in {"OK", "STATELESS"}:
                continue
            prediction_id = str(prediction_row.get("prediction_id", ""))
            snapshot_row = snapshot_rows.pop(prediction_id, None)
            save_snapshot = getattr(repository, "save_feature_snapshot", None)
            if snapshot_row is None or not callable(save_snapshot):
                snapshot_issue = True
            else:
                snapshot_status = _status_text(save_snapshot(snapshot_row))
                feature_confirmation = _merge_artifact_status(
                    feature_confirmation,
                    snapshot_status,
                )
                if snapshot_status not in {"INSERTED", "IDENTICAL_DUPLICATE"}:
                    snapshot_issue = True
            derivatives_snapshot_row = derivatives_snapshot_rows.pop(
                prediction_id, None
            )
            if derivatives_snapshot_row is not None:
                save_derivatives_snapshot = getattr(
                    repository, "save_derivatives_snapshot", None
                )
                if not callable(save_derivatives_snapshot):
                    derivatives_snapshot_issue = True
                else:
                    derivatives_snapshot_status = _status_text(
                        save_derivatives_snapshot(derivatives_snapshot_row)
                    )
                    derivatives_confirmation = _merge_artifact_status(
                        derivatives_confirmation,
                        derivatives_snapshot_status,
                    )
                    if derivatives_snapshot_status not in {
                        "INSERTED",
                        "IDENTICAL_DUPLICATE",
                    }:
                        derivatives_snapshot_issue = True
        if snapshot_rows:
            snapshot_issue = True
        if derivatives_snapshot_rows:
            derivatives_snapshot_issue = True
    except OOSArmIdentityConflict:
        raise
    except Exception:
        unexpected_failure = True
        snapshot_issue = True
        derivatives_snapshot_issue = True
        statuses = []
    auxiliary_unavailable = any(status == "UNAVAILABLE" for status in statuses)
    persistence_unavailable = (
        unexpected_failure
        or auxiliary_unavailable
        or snapshot_issue
        or derivatives_snapshot_issue
    )
    if persistence_unavailable:
        if unexpected_failure or (
            not auxiliary_unavailable
            and (snapshot_issue or derivatives_snapshot_issue)
        ):
            _mark_repository_unavailable(repository)
        background_status = "UNAVAILABLE"
    else:
        try:
            background_status = _status_text(repository.persistence_status()) or "UNAVAILABLE"
            terminal_repository_unavailable = background_status == "UNAVAILABLE"
        except Exception:
            _mark_repository_unavailable(repository)
            background_status = "UNAVAILABLE"
            unexpected_failure = True

    prediction_succeeded = prediction_confirmation in {"OK", "STATELESS"}
    if (
        unexpected_failure
        or auxiliary_unavailable
        or terminal_repository_unavailable
        or not prediction_succeeded
    ):
        overall = "UNAVAILABLE"
    elif snapshot_issue or derivatives_snapshot_issue:
        overall = "PARTIAL"
    else:
        overall = "OK"
    return _PersistenceConfirmation(
        prediction_confirmation,
        feature_confirmation,
        derivatives_confirmation,
        overall,
        background_status,
    )


def _status_text(status: object) -> str | None:
    if status is None:
        return None
    value = getattr(status, "value", status)
    return value if isinstance(value, str) else str(value)


def _merge_artifact_status(current: str | None, new: str | None) -> str | None:
    if current is None:
        return new
    return current if current == new else "UNAVAILABLE"


def _mark_repository_unavailable(repository) -> None:
    mark_unavailable = getattr(repository, "mark_unavailable", None)
    if callable(mark_unavailable):
        try:
            mark_unavailable()
        except Exception:
            pass


def _remember_prediction_persistence(
    run_id: str,
    prediction_row: dict,
    feature_snapshot_row: dict | None,
    derivatives_snapshot_row: dict | None,
    *,
    derivatives_snapshot_required: bool,
) -> None:
    with _PENDING_PREDICTION_LOCK:
        prediction_value = dict(prediction_row)
        feature_value = (
            dict(feature_snapshot_row) if feature_snapshot_row is not None else None
        )
        derivatives_value = (
            dict(derivatives_snapshot_row)
            if derivatives_snapshot_row is not None
            else None
        )
        if str(prediction_row.get("prediction_id", "")).startswith("oosb-"):
            _append_pending(_PENDING_PREDICTION_ROWS, run_id, prediction_value)
            _append_pending(_PENDING_FEATURE_SNAPSHOT_ROWS, run_id, feature_value)
            _append_pending(
                _PENDING_DERIVATIVES_SNAPSHOT_ROWS, run_id, derivatives_value
            )
            _append_pending(
                _PENDING_DERIVATIVES_SNAPSHOT_REQUIRED,
                run_id,
                bool(derivatives_snapshot_required),
            )
        else:
            _PENDING_PREDICTION_ROWS[run_id] = prediction_value
            _PENDING_FEATURE_SNAPSHOT_ROWS[run_id] = feature_value
            _PENDING_DERIVATIVES_SNAPSHOT_ROWS[run_id] = derivatives_value
            _PENDING_DERIVATIVES_SNAPSHOT_REQUIRED[run_id] = bool(
                derivatives_snapshot_required
            )


def _append_pending(values: dict, run_id: str, value: object) -> None:
    existing = values.get(run_id)
    if isinstance(existing, list):
        existing.append(value)
    elif existing is None and run_id not in values:
        values[run_id] = [value]
    else:
        values[run_id] = [existing, value]


def _pop_prediction_persistence(
    payload: dict,
) -> tuple[list[dict], list[dict], bool, list[dict], bool]:
    return _prediction_persistence(payload, consume=True)


def _peek_prediction_persistence(
    payload: dict,
) -> tuple[list[dict], list[dict], bool, list[dict], bool]:
    return _prediction_persistence(payload, consume=False)


def _prediction_persistence(
    payload: dict,
    *,
    consume: bool,
) -> tuple[list[dict], list[dict], bool, list[dict], bool]:
    run_id = str(payload.get("run_id") or "")
    if not run_id:
        return [], [], False, [], False
    with _PENDING_PREDICTION_LOCK:
        prediction_value = _pending_value(
            _PENDING_PREDICTION_ROWS,
            run_id,
            consume=consume,
        )
        had_snapshot_marker = run_id in _PENDING_FEATURE_SNAPSHOT_ROWS
        feature_snapshot_value = _pending_value(
            _PENDING_FEATURE_SNAPSHOT_ROWS,
            run_id,
            consume=consume,
        )
        had_derivatives_marker = run_id in _PENDING_DERIVATIVES_SNAPSHOT_ROWS
        derivatives_snapshot_value = _pending_value(
            _PENDING_DERIVATIVES_SNAPSHOT_ROWS,
            run_id,
            consume=consume,
        )
        derivatives_required_value = _pending_value(
            _PENDING_DERIVATIVES_SNAPSHOT_REQUIRED,
            run_id,
            consume=consume,
            default=False,
        )
    prediction_rows = _pending_rows(prediction_value)
    feature_values = _pending_values(feature_snapshot_value)
    feature_snapshot_rows = [row for row in feature_values if row is not None]
    build_failed = bool(prediction_rows) and (
        not had_snapshot_marker
        or len(feature_values) != len(prediction_rows)
        or any(row is None for row in feature_values)
    )
    derivatives_values = _pending_values(derivatives_snapshot_value)
    derivatives_snapshot_rows = [row for row in derivatives_values if row is not None]
    derivatives_required = [bool(value) for value in _pending_values(derivatives_required_value)]
    derivatives_build_failed = bool(prediction_rows) and (
        not had_derivatives_marker
        or len(derivatives_values) != len(prediction_rows)
        or len(derivatives_required) != len(prediction_rows)
        or any(
            required and row is None
            for required, row in zip(
                derivatives_required, derivatives_values, strict=False
            )
        )
    )
    return (
        prediction_rows,
        feature_snapshot_rows,
        build_failed,
        derivatives_snapshot_rows,
        derivatives_build_failed,
    )


def _pending_value(
    values: dict,
    run_id: str,
    *,
    consume: bool,
    default=None,
):
    value = values.pop(run_id, default) if consume else values.get(run_id, default)
    return deepcopy(value)


def _pending_values(value: object) -> list:
    return value if isinstance(value, list) else [value]


def _pending_rows(value: object) -> list[dict]:
    return [row for row in _pending_values(value) if isinstance(row, dict)]


def _prediction_row(
    *,
    run_id: str,
    request_symbol: str,
    normalized_symbol: str,
    timeframe: str,
    snapshot,
    quant_result: dict,
    data_quality: dict,
    provider_state: dict,
    prediction_origin: str = DEFAULT_PREDICTION_ORIGIN,
    arm: OOSArm | str | None = None,
    target: PairTarget | None = None,
    methodology_version: str = METHODOLOGY_VERSION,
) -> dict | None:
    prediction_origin = validate_prediction_origin(prediction_origin)
    if arm is not None and prediction_origin != OOS_PREDICTION_ORIGIN:
        raise PairInvalidError("OOS arm rows require shadow-evidence origin.")
    if not data_quality.get("is_live_data"):
        return None
    if timeframe not in TIMEFRAME_SECONDS:
        return None
    candles = tuple(getattr(snapshot, "candles", ()) or ())
    if not candles:
        return None
    predicted_at_utc = _coerce_utc_datetime(snapshot.as_of_utc)
    reference_candle = candles[-1]
    if target is None:
        reference_close_utc = _coerce_utc_datetime(reference_candle.close_time_utc)
        reference_price = float(reference_candle.close)
        horizon_bars = int(DEFAULT_PHASE1A.h_primary_bars)
        horizon_end_utc = reference_close_utc + timedelta(
            seconds=horizon_bars * TIMEFRAME_SECONDS[timeframe]
        )
        decision_band_frac = quant_result.get("execution_realism", {}).get(
            "round_trip_cost_frac"
        )
    else:
        reference_close_utc = target.reference_close_utc
        reference_price = target.reference_price
        horizon_bars = int(DEFAULT_PHASE1A.h_primary_bars)
        horizon_end_utc = target.horizon_end_utc
        decision_band_frac = target.decision_band_frac
    if reference_price <= 0.0 or reference_close_utc > predicted_at_utc:
        return None
    prediction_id = _prediction_id(run_id, timeframe, arm)
    horizon = quant_result.get("probability_state", {}).get("horizons", {}).get("H_primary", {})
    try:
        p_up_frac = float(horizon["p_up_frac"])
        p_down_frac = float(horizon["p_down_frac"])
        p_timeout_frac = float(horizon["p_timeout_frac"])
    except (KeyError, TypeError, ValueError):
        return None
    calibration = quant_result.get("calibration_state", {})
    epistemic = quant_result.get("epistemic_sufficiency_state", {})
    return {
        "prediction_id": prediction_id,
        "run_id": run_id,
        "operator_id": "operator",
        "symbol": request_symbol,
        "normalized_symbol": normalized_symbol,
        "timeframe": timeframe,
        "horizon_bars": horizon_bars,
        "predicted_at_utc": _iso_utc(predicted_at_utc),
        "reference_close_utc": _iso_utc(reference_close_utc),
        "reference_price": reference_price,
        "horizon_end_utc": _iso_utc(horizon_end_utc),
        "p_up_frac": p_up_frac,
        "p_down_frac": p_down_frac,
        "p_timeout_frac": p_timeout_frac,
        "decision_band_frac": decision_band_frac,
        "model_version": MODEL_VERSION,
        "methodology_version": methodology_version,
        "calibration_status": calibration.get(
            "calibration_status",
            DEFAULT_PHASE1A.calibration_status,
        ),
        "reliability_status": calibration.get(
            "reliability_status",
            DEFAULT_PHASE1A.reliability_status,
        ),
        "epistemic_sufficiency": epistemic.get("sufficiency_level"),
        "gate_action": quant_result.get("gate_result", {}).get("action"),
        "data_source": data_quality.get("data_source"),
        "is_live_data": True,
        "cross_provider_state": data_quality.get("cross_provider_state")
        or provider_state.get("cross_provider_state"),
        "prediction_origin": prediction_origin,
    }


def _prediction_id(run_id: str, timeframe: str, arm: OOSArm | str | None) -> str:
    if arm is None:
        return f"{run_id}:{timeframe}"
    try:
        resolved_arm = OOSArm(arm)
    except (TypeError, ValueError) as exc:
        raise PairInvalidError("OOS arm must be BASELINE or CANDIDATE.") from exc
    if not is_oos_run_id(run_id):
        raise PairInvalidError("Arm-suffixed prediction identity requires an OOS run.")
    return f"{run_id}:{timeframe}:{resolved_arm.value}"


def _coerce_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso_utc(value: datetime) -> str:
    return _coerce_utc_datetime(value).isoformat().replace("+00:00", "Z")


def _persistence_work(
    payload: dict,
    persistence_status: str,
    *,
    consume_pending: bool = True,
) -> PersistenceWork:
    run_summary = _run_summary(payload)
    run_summary["persistence_status"] = persistence_status
    (
        prediction_rows,
        feature_snapshot_rows,
        snapshot_build_failed,
        derivatives_snapshot_rows,
        derivatives_snapshot_build_failed,
    ) = (
        _pop_prediction_persistence(payload)
        if consume_pending
        else _peek_prediction_persistence(payload)
    )
    return PersistenceWork(
        run_summary=run_summary,
        timeframe_result=_timeframe_result(payload),
        provider_observations=tuple(_provider_observations(payload)),
        news_items=tuple(_news_item_rows(payload)),
        news_clusters=tuple(_news_cluster_rows(payload)),
        news_evidence_links=tuple(_news_evidence_link_rows(payload)),
        prediction_rows=tuple(prediction_rows),
        feature_snapshot_rows=tuple(feature_snapshot_rows),
        feature_snapshot_build_failed=snapshot_build_failed,
        derivatives_snapshot_rows=tuple(derivatives_snapshot_rows),
        derivatives_snapshot_build_failed=derivatives_snapshot_build_failed,
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


def _news_item_rows(payload: dict) -> list[dict]:
    run_id = payload.get("run_id")
    normalized_symbol = payload.get("normalized_symbol")
    contexts = (
        payload.get("macro_context", {}).get("items", []),
        payload.get("micro_news_context", {}).get("items", []),
    )
    rows: list[dict] = []
    for items in contexts:
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "item_id": item.get("url_hash") or item.get("title_hash"),
                    "run_id": run_id,
                    "normalized_symbol": normalized_symbol,
                    "provider": item.get("provider"),
                    "source_name": item.get("source_name"),
                    "domain": item.get("domain"),
                    "title": item.get("title"),
                    "snippet": item.get("snippet"),
                    "url": item.get("url"),
                    "url_hash": item.get("url_hash"),
                    "title_hash": item.get("title_hash"),
                    "published_at": item.get("published_at"),
                    "fetched_at": item.get("fetched_at"),
                    "language": item.get("language"),
                    "macro_or_micro": item.get("macro_or_micro"),
                    "event_class": item.get("event_class"),
                    "relevance_score": item.get("relevance_score"),
                    "freshness_score": item.get("freshness_score"),
                    "source_authority_score": item.get("source_authority_score"),
                    "confidence_score": item.get("confidence_score"),
                    "cluster_id": item.get("cluster_id"),
                }
            )
    return [row for row in rows if row.get("item_id") and row.get("title") and row.get("url")]


def _news_cluster_rows(payload: dict) -> list[dict]:
    run_id = payload.get("run_id")
    normalized_symbol = payload.get("normalized_symbol")
    clusters = payload.get("news_evidence", {}).get("clusters", [])
    rows: list[dict] = []
    if not isinstance(clusters, list):
        return rows
    for cluster in clusters:
        if not isinstance(cluster, dict):
            continue
        rows.append(
            {
                "cluster_id": cluster.get("cluster_id"),
                "run_id": run_id,
                "normalized_symbol": normalized_symbol,
                "representative_title": cluster.get("representative_title"),
                "macro_or_micro": cluster.get("macro_or_micro"),
                "event_class": cluster.get("event_class"),
                "source_count": cluster.get("source_count"),
                "item_count": cluster.get("item_count"),
                "dropped_count": cluster.get("dropped_count"),
                "max_relevance_score": cluster.get("max_relevance_score"),
            }
        )
    return [row for row in rows if row.get("cluster_id") and row.get("representative_title")]


def _news_evidence_link_rows(payload: dict) -> list[dict]:
    run_id = payload.get("run_id")
    links = payload.get("news_evidence", {}).get("links", [])
    rows: list[dict] = []
    if not isinstance(links, list):
        return rows
    for link in links:
        if not isinstance(link, dict):
            continue
        rows.append(
            {
                "run_id": run_id,
                "cluster_id": link.get("cluster_id"),
                "item_id": link.get("url_hash") or link.get("title_hash"),
                "evidence_type": "ADVISORY_NEWS_METADATA",
                "relevance_score": link.get("relevance_score"),
            }
        )
    return [
        row for row in rows if row.get("run_id") and row.get("cluster_id") and row.get("item_id")
    ]
