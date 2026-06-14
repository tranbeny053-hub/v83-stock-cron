from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from crypto_probability_engine.adapters.types import MarketCandle
from crypto_probability_engine.config.defaults import RESOLVER_VERSION
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.persistence.repository import (
    InMemoryPersistenceRepository,
    SupabasePersistenceRepository,
    SupabaseRestRepository,
)
from scripts import resolve_outcomes

ROOT = Path(__file__).resolve().parents[2]


def test_resolver_repository_prefers_db_url_over_rest_when_both_configured() -> None:
    repo = resolve_outcomes.build_resolver_repository(
        Settings(
            **{
                "supabase_db_url": "postgresql://operator-db.example.invalid/db",
                "supabase_url": "https://project.example.invalid",
                "supabase_service_role_key": "test-service-role-key",
            }
        )
    )

    try:
        assert isinstance(repo, SupabasePersistenceRepository)
        assert repo.repository_type() == "SUPABASE_POSTGRES"
    finally:
        close = getattr(repo, "close", None)
        if callable(close):
            close()


def test_resolver_repository_falls_back_to_rest_when_db_url_absent() -> None:
    repo = resolve_outcomes.build_resolver_repository(
        Settings(
            **{
                "supabase_url": "https://project.example.invalid",
                "supabase_service_role_key": "test-service-role-key",
            }
        )
    )

    try:
        assert isinstance(repo, SupabaseRestRepository)
        assert repo.repository_type() == "SUPABASE_REST"
    finally:
        close = getattr(repo, "close", None)
        if callable(close):
            close()


def test_resolver_repository_uses_memory_without_external_store() -> None:
    repo = resolve_outcomes.build_resolver_repository(Settings())

    assert isinstance(repo, InMemoryPersistenceRepository)
    assert repo.repository_type() == "IN_MEMORY"


def test_main_output_includes_safe_repository_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_resolve_due_predictions(repository, **kwargs):
        assert repository.repository_type() == "SUPABASE_POSTGRES"
        assert kwargs["limit"] == 7
        return {"due": 4, "resolved": 1, "skipped": 2, "failed": 1}

    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://operator-db.example.invalid/db")
    monkeypatch.setenv("SUPABASE_URL", "https://project.example.invalid")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
    monkeypatch.setattr(resolve_outcomes, "resolve_due_predictions", fake_resolve_due_predictions)

    result = resolve_outcomes.main(["--limit", "7"])
    output = capsys.readouterr().out

    assert result == 0
    assert "resolved_outcomes repository=SUPABASE_POSTGRES limit=7" in output
    assert "due=4 resolved=1 skipped=2 failed=1" in output
    assert "operator-db.example.invalid" not in output
    assert "project.example.invalid" not in output
    assert "test-service-role-key" not in output


def test_no_lookahead_candles_at_or_before_reference_do_not_influence_outcome() -> None:
    prediction = _prediction()
    reference = _dt("2026-06-07T00:00:00Z")
    horizon = _dt("2026-06-08T00:00:00Z")
    candles = (
        _candle(reference - timedelta(hours=4), close=10_000.0, high=20_000.0, low=1.0),
        _candle(reference, close=10_000.0, high=50_000.0, low=1.0),
        _candle(reference + timedelta(hours=4), close=100.0, high=100.5, low=99.7),
        _candle(horizon, close=101.0, high=101.5, low=99.8),
    )

    row = resolve_outcomes.build_outcome_row(
        prediction,
        now_utc=_dt("2026-06-08T00:05:00Z"),
        settings=Settings(),
        fetch_candles=lambda _prediction, _settings: (candles, "BINANCE_PUBLIC"),
    )

    assert row is not None
    assert row["realized_label"] == "UP"
    assert row["terminal_return_frac"] == 0.01
    assert row["max_favorable_frac"] == 0.015
    assert row["max_adverse_frac"] == pytest.approx(-0.003)
    assert row["candles_observed"] == 2


def test_unfinished_horizon_writes_no_outcome() -> None:
    prediction = _prediction()
    candles = (
        _candle(_dt("2026-06-07T04:00:00Z"), close=100.5),
        _candle(_dt("2026-06-07T20:00:00Z"), close=101.0),
    )

    row = resolve_outcomes.build_outcome_row(
        prediction,
        now_utc=_dt("2026-06-08T00:05:00Z"),
        settings=Settings(),
        fetch_candles=lambda _prediction, _settings: (candles, "BINANCE_PUBLIC"),
    )

    assert row is None


def test_stale_window_overshoot_skips_outcome_and_writes_nothing() -> None:
    repo = InMemoryPersistenceRepository()
    prediction = _prediction()
    repo.save_prediction(prediction)
    stale_candles = (
        _candle(_dt("2026-06-09T00:00:01Z"), close=110.0),
        _candle(_dt("2026-06-09T04:00:01Z"), close=111.0),
    )

    stats = resolve_outcomes.resolve_due_predictions(
        repo,
        settings=Settings(),
        now_utc=_dt("2026-06-10T00:00:00Z"),
        fetch_candles=lambda _prediction, _settings: (stale_candles, "BINANCE_PUBLIC"),
    )

    assert stats == {"due": 1, "resolved": 0, "skipped": 1, "failed": 0}
    assert repo._prediction_outcomes == {}  # noqa: SLF001


def test_fresh_horizon_within_one_timeframe_buffer_still_resolves() -> None:
    row = resolve_outcomes.build_outcome_row(
        _prediction(),
        now_utc=_dt("2026-06-08T04:05:00Z"),
        settings=Settings(),
        fetch_candles=lambda _prediction, _settings: (
            (_candle(_dt("2026-06-08T04:00:00Z"), close=101.0),),
            "BINANCE_PUBLIC",
        ),
    )

    assert row is not None
    assert row["outcome_close_utc"] == "2026-06-08T04:00:00Z"
    assert row["realized_label"] == "UP"


def test_up_down_timeout_label_fixtures() -> None:
    assert _label_for_close(101.0) == "UP"
    assert _label_for_close(99.0) == "DOWN"
    assert _label_for_close(100.2) == "TIMEOUT"


def test_resolver_uses_fallback_band_when_prediction_band_missing() -> None:
    prediction = {**_prediction(), "decision_band_frac": None}
    row = resolve_outcomes.build_outcome_row(
        prediction,
        now_utc=_dt("2026-06-08T00:05:00Z"),
        settings=Settings(),
        fetch_candles=lambda _prediction, _settings: (
            (_candle(_dt("2026-06-08T00:00:00Z"), close=100.15),),
            "BINANCE_PUBLIC",
        ),
    )

    assert row is not None
    assert row["decision_band_frac"] == 0.002
    assert row["realized_label"] == "TIMEOUT"


def test_resolve_due_predictions_isolates_bad_prediction_failure() -> None:
    repo = InMemoryPersistenceRepository()
    bad = _prediction(prediction_id="bad:4H")
    good = _prediction(prediction_id="good:4H")
    repo.save_prediction(bad)
    repo.save_prediction(good)

    def fetch(prediction, settings):
        if prediction["prediction_id"] == "bad:4H":
            raise RuntimeError("mocked provider failure")
        return ((_candle(_dt("2026-06-08T00:00:00Z"), close=101.0),), "BINANCE_PUBLIC")

    stats = resolve_outcomes.resolve_due_predictions(
        repo,
        settings=Settings(),
        now_utc=_dt("2026-06-08T00:05:00Z"),
        fetch_candles=fetch,
    )

    assert stats == {"due": 2, "resolved": 1, "skipped": 0, "failed": 1}
    assert list(repo._prediction_outcomes.keys()) == ["good:4H"]  # noqa: SLF001


def test_prediction_row_is_not_mutated_by_resolution() -> None:
    prediction = _prediction()
    original = deepcopy(prediction)

    resolve_outcomes.build_outcome_row(
        prediction,
        now_utc=_dt("2026-06-08T00:05:00Z"),
        settings=Settings(),
        fetch_candles=lambda _prediction, _settings: (
            (_candle(_dt("2026-06-08T00:00:00Z"), close=101.0),),
            "BINANCE_PUBLIC",
        ),
    )

    assert prediction == original


def test_outcome_row_contains_resolver_version_and_no_prediction_update_fields() -> None:
    row = resolve_outcomes.build_outcome_row(
        _prediction(),
        now_utc=_dt("2026-06-08T00:05:00Z"),
        settings=Settings(),
        fetch_candles=lambda _prediction, _settings: (
            (_candle(_dt("2026-06-08T00:00:00Z"), close=101.0),),
            "BINANCE_PUBLIC",
        ),
    )

    assert row is not None
    assert row["resolver_version"] == RESOLVER_VERSION
    assert "calibration_status" not in row
    assert "reliability_status" not in row
    assert "profitability_claim" not in row


def test_resolve_outcomes_script_is_not_imported_by_api_package() -> None:
    api_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "src" / "crypto_probability_engine" / "api").glob("*.py")
    )

    assert "resolve_outcomes" not in api_text


def _label_for_close(close: float) -> str:
    row = resolve_outcomes.build_outcome_row(
        _prediction(),
        now_utc=_dt("2026-06-08T00:05:00Z"),
        settings=Settings(),
        fetch_candles=lambda _prediction, _settings: (
            (_candle(_dt("2026-06-08T00:00:00Z"), close=close),),
            "BINANCE_PUBLIC",
        ),
    )
    assert row is not None
    return str(row["realized_label"])


def _prediction(prediction_id: str = "run_1:4H") -> dict:
    return {
        "prediction_id": prediction_id,
        "run_id": "run_1",
        "operator_id": "operator",
        "symbol": "BTC",
        "normalized_symbol": "BTC/USDT",
        "timeframe": "4H",
        "horizon_bars": 6,
        "predicted_at_utc": "2026-06-07T00:00:00Z",
        "reference_close_utc": "2026-06-07T00:00:00Z",
        "reference_price": 100.0,
        "horizon_end_utc": "2026-06-08T00:00:00Z",
        "p_up_frac": 0.40,
        "p_down_frac": 0.35,
        "p_timeout_frac": 0.25,
        "decision_band_frac": 0.003,
        "model_version": "phase1a-wave4b0",
        "methodology_version": "heuristic-v1-wave4b0",
        "calibration_status": "DEFAULT_PHASE1A",
        "reliability_status": "INSUFFICIENT_SAMPLE",
        "epistemic_sufficiency": "SUFFICIENT",
        "gate_action": "WATCH",
        "data_source": "BINANCE_PUBLIC",
        "is_live_data": True,
        "cross_provider_state": "UNAVAILABLE",
    }


def _candle(
    close_time: datetime,
    *,
    close: float,
    high: float | None = None,
    low: float | None = None,
) -> MarketCandle:
    high = close if high is None else high
    low = close if low is None else low
    return MarketCandle(
        open_time_utc=close_time - timedelta(hours=4),
        close_time_utc=close_time,
        open=close,
        high=high,
        low=low,
        close=close,
        volume=1_000.0,
    )


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
