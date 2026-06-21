from __future__ import annotations

from datetime import UTC, datetime, timedelta


def make_feature(
    family: str,
    timeframe: str = "4H",
    *,
    status: str = "VALID",
    raw_value=None,
    direction_hint=None,
    provider: str = "BINANCE",
    no_lookahead: bool = True,
) -> dict:
    identifiers = {
        "VOLATILITY": "quant_v2.realized_volatility",
        "TREND": "quant_v2.trend_mtf",
        "VOLUME": "quant_v2.volume_anomaly",
        "REGIME": "quant_v2.regime_2state",
    }
    return {
        "feature_id": f"{identifiers[family]}:{timeframe}",
        "family": family,
        "status": status,
        "raw_value": raw_value,
        "direction_hint": direction_hint,
        "lookback": 20,
        "candle_count": 210,
        "source_provider": provider,
        "no_lookahead_assertion": no_lookahead,
        "data_quality": {
            "upstream_status": "OK" if status == "VALID" else "DEGRADED",
            "provider_state_status": "OK",
            "snapshot_source_status": "OK",
            "timestamp_evidence_complete": no_lookahead,
        },
        "explanation_short": "must be removed",
        "future_field": {"must": "be removed"},
    }


def make_validation_row(
    index: int,
    *,
    predicted_at: datetime | None = None,
    reference_close: datetime | None = None,
    horizon_hours: int = 24,
    timeframe: str = "4H",
    symbol: str = "BTC/USDT",
    model_version: str = "model-v1",
    methodology_version: str = "method-v1",
    resolver_version: str = "resolver-v1",
    quant_schema: str = "quant_v2.0",
    feature_methodology: str = "quant-v2-shadow-v0",
    provider_signature: str = "BINANCE",
    block_status: str = "ACTIVE",
    no_lookahead: bool = True,
    realized_label: str | None = None,
    features: list[dict] | None = None,
) -> dict:
    predicted = predicted_at or datetime(2026, 1, 1, tzinfo=UTC) + timedelta(
        hours=index * 24
    )
    reference = reference_close or predicted
    label = realized_label or ("UP", "DOWN", "TIMEOUT")[index % 3]
    if features is None:
        features = [
            make_feature("VOLATILITY", timeframe, raw_value=0.01 + index * 0.0001),
            make_feature("TREND", timeframe, raw_value="UP", direction_hint="UP"),
            make_feature("VOLUME", timeframe, raw_value=1.0 + index * 0.01),
            make_feature("REGIME", timeframe, raw_value="LOW_VOL"),
        ]
    return {
        "prediction_id": f"prediction-{index:05d}",
        "run_id": f"run-{index:05d}",
        "normalized_symbol": symbol,
        "symbol": symbol.split("/")[0],
        "timeframe": timeframe,
        "predicted_at_utc": predicted.isoformat().replace("+00:00", "Z"),
        "reference_close_utc": reference.isoformat().replace("+00:00", "Z"),
        "horizon_end_utc": (predicted + timedelta(hours=horizon_hours)).isoformat().replace(
            "+00:00", "Z"
        ),
        "horizon_bars": 6,
        "p_up_frac": 0.4,
        "p_down_frac": 0.3,
        "p_timeout_frac": 0.3,
        "model_version": model_version,
        "methodology_version": methodology_version,
        "prediction_is_live_data": True,
        "realized_label": label,
        "terminal_return_frac": 0.01 if label == "UP" else -0.01,
        "resolver_version": resolver_version,
        "outcome_is_live_data": True,
        "quant_v2_schema_version": quant_schema,
        "feature_methodology_version": feature_methodology,
        "block_status": block_status,
        "no_lookahead_assertion": no_lookahead,
        "provider_signature": provider_signature,
        "snapshot_payload": {
            "features": features,
            "plain_english": "must be removed",
            "unknown_future": ["must be removed"],
        },
    }


def make_coverage(count: int) -> dict:
    return {
        "live_predictions_all_time": count,
        "live_predictions_eligible_era": count,
        "snapshots_all_time": count,
        "snapshots_eligible_era": count,
        "resolved_outcomes_eligible_era": count,
        "snapshot_outcome_joins_eligible_era": count,
        "predictions_missing_snapshot_eligible_era": 0,
        "snapshots_missing_outcome_eligible_era": 0,
        "first_snapshot_as_of_utc": "2026-01-01T00:00:00Z" if count else None,
        "latest_snapshot_as_of_utc": "2026-06-01T00:00:00Z" if count else None,
    }


class ReadOnlyRepository:
    def __init__(self, rows: list[dict], coverage: dict | None = None) -> None:
        self.rows = rows
        self.coverage = coverage or make_coverage(len(rows))
        self.calls = []
        self.closed = False

    def repository_type(self) -> str:
        return "TEST_READ_ONLY"

    def fetch_feature_snapshot_validation_coverage(self, **kwargs):
        self.calls.append(("coverage", kwargs))
        return dict(self.coverage)

    def fetch_feature_snapshot_validation_rows(self, **kwargs):
        self.calls.append(("rows", kwargs))
        return list(self.rows[: kwargs["limit"]])

    def close(self) -> None:
        self.closed = True

    def __getattr__(self, name):
        if name.startswith("save_") or name == "mark_unavailable":
            raise AssertionError(f"write path accessed: {name}")
        raise AttributeError(name)
