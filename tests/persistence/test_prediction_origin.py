from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from crypto_probability_engine.adapters.provider_selection import ProviderSelectionResult
from crypto_probability_engine.api import analysis_service
from crypto_probability_engine.api.analysis_service import _pop_prediction_persistence
from crypto_probability_engine.api.schemas import AnalysisRequest
from crypto_probability_engine.calibration.service import build_calibration_report
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.persistence.prediction_origin import (
    ALLOWED_PREDICTION_ORIGINS,
    DEFAULT_PREDICTION_ORIGIN,
    PredictionOrigin,
    validate_prediction_origin,
)
from crypto_probability_engine.persistence.repository import InMemoryPersistenceRepository
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from tests.fixtures.market_data import make_snapshot

ROOT = Path(__file__).resolve().parents[2]


def _live_selection(symbol, timeframe, *, settings) -> ProviderSelectionResult:
    del settings
    return ProviderSelectionResult(
        snapshot=make_snapshot(
            provider="binance",
            symbol=symbol.display,
            timeframe=timeframe,
        ),
        provider_state={
            "status": "OK",
            "active_provider": "binance",
            "cross_provider_state": "UNAVAILABLE",
            "providers": {"binance": {"status": "OK"}},
        },
        data_quality={
            "status": "OK",
            "warnings": [],
            "freshness_budget": "DEFAULT_PHASE1A",
            "is_live_data": True,
            "data_source": "BINANCE_PUBLIC",
            "latest_candle_age_seconds": 0,
            "provider_failures": {},
            "cross_provider_state": "UNAVAILABLE",
        },
    )


def _analyze(monkeypatch, *, origin: str | None = None) -> tuple[dict, dict, dict]:
    monkeypatch.setattr(analysis_service, "select_market_data", _live_selection)
    monkeypatch.setattr(analysis_service, "uuid4", lambda: UUID(int=41))
    kwargs = {}
    if origin is not None:
        kwargs["prediction_origin"] = origin
    payload = analysis_service.analyze_request(
        AnalysisRequest(symbol="BTC", timeframe="4H"),
        settings=Settings(data_mode="fixture"),
        run_store=InMemoryRunStore(),
        **kwargs,
    )
    predictions, feature_rows, failed, _, derivatives_failed = (
        _pop_prediction_persistence(payload)
    )
    assert not failed
    assert not derivatives_failed
    assert len(predictions) == len(feature_rows) == 1
    return payload, predictions[0], feature_rows[0]


def _prediction(identifier: str, origin: str | None) -> dict:
    row = {
        "prediction_id": identifier,
        "run_id": f"run-{identifier}",
        "symbol": "BTC",
        "normalized_symbol": "BTC/USDT",
        "timeframe": "4H",
        "predicted_at_utc": "2026-06-22T00:00:00Z",
        "horizon_end_utc": "2026-06-23T00:00:00Z",
        "model_version": "model-v1",
        "methodology_version": "method-v1",
        "is_live_data": True,
    }
    if origin is not None:
        row["prediction_origin"] = origin
    return row


def _outcome(identifier: str) -> dict:
    return {
        "prediction_id": identifier,
        "resolved_at_utc": "2026-06-23T00:00:01Z",
        "outcome_close_utc": "2026-06-23T00:00:00Z",
        "terminal_return_frac": 0.01,
        "realized_label": "UP",
        "resolver_version": "resolver-v1",
        "is_live_data": True,
    }


def test_prediction_origin_contract_is_exact_and_rejects_invalid_values() -> None:
    assert DEFAULT_PREDICTION_ORIGIN == "USER_REQUESTED"
    assert ALLOWED_PREDICTION_ORIGINS == {
        "USER_REQUESTED",
        "CONTROLLED_SMOKE",
        "SCHEDULED_SHADOW_EVIDENCE",
    }
    assert validate_prediction_origin(PredictionOrigin.CONTROLLED_SMOKE) == (
        "CONTROLLED_SMOKE"
    )
    for invalid in ("", "user_requested", " USER_REQUESTED", "UNKNOWN"):
        with pytest.raises(ValueError):
            validate_prediction_origin(invalid)


def test_analyze_request_defaults_accepts_explicit_origin_and_preserves_identity(
    monkeypatch,
) -> None:
    default_payload, default_row, default_snapshot = _analyze(monkeypatch)
    scheduled_payload, scheduled_row, scheduled_snapshot = _analyze(
        monkeypatch,
        origin="SCHEDULED_SHADOW_EVIDENCE",
    )

    assert default_row["prediction_origin"] == "USER_REQUESTED"
    assert scheduled_row["prediction_origin"] == "SCHEDULED_SHADOW_EVIDENCE"
    assert default_payload == scheduled_payload
    assert default_payload["analysis_hash"] == scheduled_payload["analysis_hash"]
    assert default_row["prediction_id"] == scheduled_row["prediction_id"]
    assert {
        key: value
        for key, value in default_row.items()
        if key != "prediction_origin"
    } == {
        key: value
        for key, value in scheduled_row.items()
        if key != "prediction_origin"
    }
    assert default_snapshot == scheduled_snapshot


def test_analyze_request_rejects_invalid_origin_before_market_selection(monkeypatch) -> None:
    monkeypatch.setattr(
        analysis_service,
        "select_market_data",
        lambda *args, **kwargs: pytest.fail("market selection must not run"),
    )
    with pytest.raises(ValueError):
        analysis_service.analyze_request(
            AnalysisRequest(symbol="BTC", timeframe="4H"),
            settings=Settings(data_mode="fixture"),
            run_store=InMemoryRunStore(),
            prediction_origin="INVALID",
        )


def test_in_memory_prediction_origin_is_defaulted_validated_and_first_write_wins() -> None:
    repository = InMemoryPersistenceRepository()
    missing = _prediction("missing", None)
    repository.save_prediction(missing)
    assert repository._predictions["missing"]["prediction_origin"] == "USER_REQUESTED"  # noqa: SLF001

    first = _prediction("immutable", "CONTROLLED_SMOKE")
    conflicting = _prediction("immutable", "USER_REQUESTED")
    repository.save_prediction(first)
    repository.save_prediction(conflicting)
    assert repository._predictions["immutable"]["prediction_origin"] == (  # noqa: SLF001
        "CONTROLLED_SMOKE"
    )

    with pytest.raises(ValueError):
        repository.save_prediction(_prediction("invalid", "UNKNOWN"))


def test_calibration_defaults_to_user_requested_and_supports_explicit_origin() -> None:
    repository = InMemoryPersistenceRepository()
    for identifier, origin in (
        ("legacy", None),
        ("user", "USER_REQUESTED"),
        ("smoke", "CONTROLLED_SMOKE"),
        ("scheduled", "SCHEDULED_SHADOW_EVIDENCE"),
    ):
        repository.save_prediction(_prediction(identifier, origin))
        repository.save_prediction_outcome(_outcome(identifier))
    repository._predictions["legacy"].pop("prediction_origin")  # noqa: SLF001

    default_report = build_calibration_report(repository)
    smoke_report = build_calibration_report(
        repository,
        prediction_origin="CONTROLLED_SMOKE",
    )

    assert default_report["sample_count"] == 2
    assert smoke_report["sample_count"] == 1
    assert repository.fetch_resolved_prediction_outcomes_for_calibration(
        prediction_origin="SCHEDULED_SHADOW_EVIDENCE"
    )[0]["prediction_id"] == "scheduled"


def test_resolver_due_selection_remains_origin_agnostic() -> None:
    repository = InMemoryPersistenceRepository()
    for identifier, origin in (
        ("user", "USER_REQUESTED"),
        ("smoke", "CONTROLLED_SMOKE"),
        ("scheduled", "SCHEDULED_SHADOW_EVIDENCE"),
    ):
        row = _prediction(identifier, origin)
        row["horizon_end_utc"] = "2026-06-21T00:00:00Z"
        repository.save_prediction(row)

    due = repository.fetch_due_unresolved_predictions(
        datetime(2026, 6, 22, tzinfo=UTC),
        limit=10,
    )
    assert {row["prediction_origin"] for row in due} == {
        "USER_REQUESTED",
        "CONTROLLED_SMOKE",
        "SCHEDULED_SHADOW_EVIDENCE",
    }


def test_prediction_origin_migration_is_additive_exact_and_idempotent() -> None:
    sql = (ROOT / "migrations" / "0007_prediction_origin.sql").read_text(
        encoding="utf-8"
    )
    upper = sql.upper()
    assert "ADD COLUMN IF NOT EXISTS PREDICTION_ORIGIN" in upper
    assert "NOT NULL" in upper
    assert "DEFAULT 'USER_REQUESTED'" in upper
    assert "PREDICTIONS_PREDICTION_ORIGIN_CHK" in upper
    assert "PG_CONSTRAINT" in upper
    assert "CONRELID = 'PUBLIC.PREDICTIONS'::REGCLASS" in upper
    assert "CREATE INDEX IF NOT EXISTS IDX_PREDICTIONS_ORIGIN_METHODOLOGY_TF" in upper
    assert "PREDICTION_ORIGIN,\n    METHODOLOGY_VERSION,\n    TIMEFRAME" in upper
    assert upper.count("'USER_REQUESTED'") == 2
    assert upper.count("'CONTROLLED_SMOKE'") == 1
    assert upper.count("'SCHEDULED_SHADOW_EVIDENCE'") == 1
    assert "UPDATE " not in upper
    assert "BACKFILL" not in upper
    assert "DROP " not in upper
    assert "DELETE " not in upper
    assert "INSERT " not in upper
    assert "PREDICTION_OUTCOMES" not in upper
    assert "PREDICTION_FEATURE_SNAPSHOTS" not in upper


def test_origin_change_does_not_mutate_input_rows() -> None:
    repository = InMemoryPersistenceRepository()
    source = _prediction("copy", None)
    before = deepcopy(source)
    repository.save_prediction(source)
    assert source == before
