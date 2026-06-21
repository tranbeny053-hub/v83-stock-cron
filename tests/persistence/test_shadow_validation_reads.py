from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from crypto_probability_engine.persistence.repository import (
    InMemoryPersistenceRepository,
    SupabasePersistenceRepository,
    SupabaseRestRepository,
)
from tests.shadow_validation.conftest import make_validation_row


def _prediction(identifier: str, predicted: datetime) -> dict:
    return {
        "prediction_id": identifier,
        "run_id": f"run-{identifier}",
        "symbol": "BTC",
        "normalized_symbol": "BTC/USDT",
        "timeframe": "4H",
        "horizon_bars": 6,
        "predicted_at_utc": predicted.isoformat().replace("+00:00", "Z"),
        "reference_close_utc": predicted.isoformat().replace("+00:00", "Z"),
        "reference_price": 100.0,
        "horizon_end_utc": (predicted + timedelta(hours=24)).isoformat().replace(
            "+00:00", "Z"
        ),
        "p_up_frac": 0.4,
        "p_down_frac": 0.3,
        "p_timeout_frac": 0.3,
        "decision_band_frac": 0.01,
        "model_version": "model-v1",
        "methodology_version": "method-v1",
        "calibration_status": "DEFAULT",
        "reliability_status": "INSUFFICIENT_SAMPLE",
        "epistemic_sufficiency": "SUFFICIENT",
        "gate_action": "WATCH",
        "data_source": "BINANCE_PUBLIC",
        "is_live_data": True,
        "cross_provider_state": "UNAVAILABLE",
    }


def _outcome(identifier: str) -> dict:
    return {
        "prediction_id": identifier,
        "resolved_at_utc": "2026-02-01T00:00:00Z",
        "outcome_close_utc": "2026-02-01T00:00:00Z",
        "outcome_reference_price": 101.0,
        "terminal_return_frac": 0.01,
        "realized_label": "UP",
        "decision_band_frac": 0.01,
        "max_favorable_frac": 0.02,
        "max_adverse_frac": -0.01,
        "candles_observed": 6,
        "resolver_version": "resolver-v1",
        "data_source": "BINANCE_PUBLIC",
        "is_live_data": True,
    }


def _snapshot(identifier: str, predicted: datetime) -> dict:
    validation = make_validation_row(1, predicted_at=predicted)
    return {
        "prediction_id": identifier,
        "run_id": f"run-{identifier}",
        "symbol": "BTC",
        "normalized_symbol": "BTC/USDT",
        "timeframe": "4H",
        "prediction_as_of_utc": predicted.isoformat().replace("+00:00", "Z"),
        "reference_close_utc": predicted.isoformat().replace("+00:00", "Z"),
        "quant_v2_schema_version": "quant_v2.0",
        "feature_methodology_version": "quant-v2-shadow-v0",
        "influence_mode": "SHADOW_ONLY",
        "no_lookahead_assertion": True,
        "block_status": "ACTIVE",
        "feature_count": 4,
        "degraded_count": 0,
        "provider_signature": "BINANCE",
        "snapshot_payload": validation["snapshot_payload"],
        "snapshot_hash": identifier.ljust(64, "a")[:64],
    }


def test_in_memory_coverage_separates_all_time_from_first_snapshot_era() -> None:
    repository = InMemoryPersistenceRepository()
    historical = datetime(2025, 12, 1, tzinfo=UTC)
    first_snapshot = datetime(2026, 1, 1, tzinfo=UTC)
    second = datetime(2026, 1, 2, tzinfo=UTC)
    third = datetime(2026, 1, 3, tzinfo=UTC)
    for identifier, predicted in (
        ("historical", historical),
        ("joined", first_snapshot),
        ("missing-snapshot", second),
        ("missing-outcome", third),
    ):
        repository.save_prediction(_prediction(identifier, predicted))
    repository.save_prediction_outcome(_outcome("historical"))
    repository.save_prediction_outcome(_outcome("joined"))
    repository.save_prediction_outcome(_outcome("missing-snapshot"))
    repository.save_feature_snapshot(_snapshot("joined", first_snapshot))
    repository.save_feature_snapshot(_snapshot("missing-outcome", third))

    coverage = repository.fetch_feature_snapshot_validation_coverage(
        feature_methodology_version="quant-v2-shadow-v0",
        timeframe="4H",
        since=None,
        until=None,
    )

    assert coverage["live_predictions_all_time"] == 4
    assert coverage["live_predictions_eligible_era"] == 3
    assert coverage["snapshots_all_time"] == 2
    assert coverage["snapshots_eligible_era"] == 2
    assert coverage["resolved_outcomes_eligible_era"] == 2
    assert coverage["snapshot_outcome_joins_eligible_era"] == 1
    assert coverage["predictions_missing_snapshot_eligible_era"] == 1
    assert coverage["snapshots_missing_outcome_eligible_era"] == 1
    assert coverage["first_snapshot_as_of_utc"] == "2026-01-01T00:00:00Z"

    rows = repository.fetch_feature_snapshot_validation_rows(
        feature_methodology_version="quant-v2-shadow-v0",
        timeframe="4H",
        since=None,
        until=None,
        limit=50_000,
    )
    assert [row["prediction_id"] for row in rows] == ["joined"]
    assert set(rows[0]) == {
        "prediction_id",
        "run_id",
        "normalized_symbol",
        "symbol",
        "timeframe",
        "predicted_at_utc",
        "reference_close_utc",
        "horizon_end_utc",
        "horizon_bars",
        "p_up_frac",
        "p_down_frac",
        "p_timeout_frac",
        "model_version",
        "methodology_version",
        "prediction_is_live_data",
        "realized_label",
        "terminal_return_frac",
        "resolver_version",
        "outcome_is_live_data",
        "quant_v2_schema_version",
        "feature_methodology_version",
        "block_status",
        "no_lookahead_assertion",
        "provider_signature",
        "snapshot_payload",
    }

    bounded = repository.fetch_feature_snapshot_validation_coverage(
        feature_methodology_version="quant-v2-shadow-v0",
        timeframe="4H",
        since=second,
        until=third,
    )
    assert bounded["live_predictions_all_time"] == 4
    assert bounded["live_predictions_eligible_era"] == 2
    assert bounded["snapshots_eligible_era"] == 1
    assert bounded["resolved_outcomes_eligible_era"] == 1
    assert bounded["snapshot_outcome_joins_eligible_era"] == 0


def test_validation_row_limit_must_be_positive() -> None:
    repository = InMemoryPersistenceRepository()
    with pytest.raises(ValueError):
        repository.fetch_feature_snapshot_validation_rows(
            feature_methodology_version="quant-v2-shadow-v0",
            timeframe=None,
            since=None,
            until=None,
            limit=0,
        )


class _Cursor:
    def __init__(self, *, row=None, rows=None) -> None:
        self.row = row
        self.rows = rows or []
        self.statements = []
        self.params = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def execute(self, statement, params=None) -> None:
        self.statements.append(str(statement))
        self.params.append(params)

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self.cursor_value = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def cursor(self) -> _Cursor:
        return self.cursor_value


def test_postgres_validation_reads_are_select_only_bounded_and_explicit() -> None:
    coverage_row = {
        "live_predictions_all_time": 2,
        "live_predictions_eligible_era": 1,
        "snapshots_all_time": 1,
        "snapshots_eligible_era": 1,
        "resolved_outcomes_eligible_era": 1,
        "snapshot_outcome_joins_eligible_era": 1,
        "predictions_missing_snapshot_eligible_era": 0,
        "snapshots_missing_outcome_eligible_era": 0,
        "first_snapshot_as_of_utc": datetime(2026, 1, 1, tzinfo=UTC),
        "latest_snapshot_as_of_utc": datetime(2026, 1, 1, tzinfo=UTC),
    }
    joined_row = make_validation_row(1)
    coverage_cursor = _Cursor(row=coverage_row)
    row_cursor = _Cursor(rows=[joined_row])
    connections = iter((_Connection(coverage_cursor), _Connection(row_cursor)))
    repository = SupabasePersistenceRepository(
        "postgresql://example.invalid/db",
        direct_connection_factory=lambda: next(connections),
    )

    coverage = repository.fetch_feature_snapshot_validation_coverage(
        feature_methodology_version="quant-v2-shadow-v0",
        timeframe="4H",
        since=None,
        until=None,
    )
    rows = repository.fetch_feature_snapshot_validation_rows(
        feature_methodology_version="quant-v2-shadow-v0",
        timeframe="4H",
        since=None,
        until=None,
        limit=50_001,
    )

    assert coverage["snapshots_all_time"] == 1
    assert rows[0]["prediction_id"] == "prediction-00001"
    statements = "\n".join(coverage_cursor.statements + row_cursor.statements).upper()
    assert "FROM PUBLIC.PREDICTION_FEATURE_SNAPSHOTS S" in statements
    assert "JOIN PUBLIC.PREDICTIONS P ON P.PREDICTION_ID = S.PREDICTION_ID" in statements
    assert "JOIN PUBLIC.PREDICTION_OUTCOMES O ON O.PREDICTION_ID = S.PREDICTION_ID" in statements
    assert "ORDER BY P.PREDICTED_AT_UTC ASC, P.PREDICTION_ID ASC" in statements
    assert not any(term in statements for term in ("INSERT ", "UPDATE ", "DELETE ", "MERGE "))
    assert row_cursor.params[0]["limit"] == 50_000


def test_rest_validation_reads_are_explicitly_unsupported() -> None:
    repository = SupabaseRestRepository(
        "https://example.invalid",
        "test-key",
    )
    with pytest.raises(NotImplementedError):
        repository.fetch_feature_snapshot_validation_rows(
            feature_methodology_version="quant-v2-shadow-v0",
            timeframe=None,
            since=None,
            until=None,
            limit=100,
        )
    repository.close()
