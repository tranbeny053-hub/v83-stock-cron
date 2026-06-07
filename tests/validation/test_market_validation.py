from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from math import nan

import pytest

from crypto_probability_engine.api.schemas import ErrorCode
from crypto_probability_engine.config.defaults import TIMEFRAME_SECONDS, min_history_for
from crypto_probability_engine.validation.market_data import (
    DataValidationError,
    assert_snapshots_coherent,
    snapshot_coherence_report,
    validate_candles,
    validate_market_snapshot,
    validate_order_book,
)
from tests.fixtures.market_data import FIXED_NOW, make_candles, make_order_book, make_snapshot


def test_valid_snapshot_passes() -> None:
    validate_market_snapshot(make_snapshot(), min_bars=3)


def test_monthly_snapshot_uses_lower_per_timeframe_min_history() -> None:
    snapshot = make_snapshot(timeframe="1M", count=30)
    validate_market_snapshot(snapshot)
    assert min_history_for("1M") == 24
    assert snapshot.candles[-1].close_time_utc - snapshot.candles[-1].open_time_utc == timedelta(
        seconds=TIMEFRAME_SECONDS["1M"]
    )


def test_monthly_snapshot_below_min_history_fails_closed() -> None:
    with pytest.raises(DataValidationError) as excinfo:
        validate_market_snapshot(make_snapshot(timeframe="1M", count=23))
    assert excinfo.value.code == ErrorCode.INSUFFICIENT_DATA


def test_stale_candles_fail_closed() -> None:
    candles = make_candles(count=3)
    with pytest.raises(DataValidationError) as excinfo:
        validate_candles(candles, "4H", now_utc=FIXED_NOW + timedelta(days=2), min_bars=3)
    assert excinfo.value.code == ErrorCode.STALE_CANDLES


def test_gap_in_candles_fails_closed() -> None:
    candles = list(make_candles(count=3))
    candles[1] = replace(
        candles[1],
        open_time_utc=candles[1].open_time_utc + timedelta(hours=4),
        close_time_utc=candles[1].close_time_utc + timedelta(hours=4),
    )
    with pytest.raises(DataValidationError):
        validate_candles(tuple(candles), "4H", now_utc=FIXED_NOW, min_bars=3)


def test_duplicate_candles_fail_closed() -> None:
    candles = list(make_candles(count=3))
    candles[1] = replace(candles[1], open_time_utc=candles[0].open_time_utc)
    with pytest.raises(DataValidationError):
        validate_candles(tuple(candles), "4H", now_utc=FIXED_NOW, min_bars=3)


def test_nan_candle_fails_closed() -> None:
    candles = list(make_candles(count=3))
    candles[-1] = replace(candles[-1], close=nan)
    with pytest.raises(DataValidationError):
        validate_candles(tuple(candles), "4H", now_utc=FIXED_NOW, min_bars=3)


def test_crossed_book_is_data_conflict() -> None:
    with pytest.raises(DataValidationError) as excinfo:
        validate_order_book(make_order_book(bid=121.0, ask=120.0))
    assert excinfo.value.code == ErrorCode.DATA_CONFLICT


def test_provider_price_conflict() -> None:
    with pytest.raises(DataValidationError) as excinfo:
        assert_snapshots_coherent(
            make_snapshot(provider="a"),
            make_snapshot(provider="b", close_shift=10.0),
        )
    assert excinfo.value.code == ErrorCode.DATA_CONFLICT


@pytest.mark.parametrize("timeframe", ["1D", "1W"])
def test_daily_weekly_coherence_uses_equivalent_closed_bucket(timeframe: str) -> None:
    report = snapshot_coherence_report(
        make_snapshot(provider="binance", timeframe=timeframe),
        make_snapshot(provider="okx", timeframe=timeframe),
    )
    assert report["status"] == "OK"
    assert report["aligned_close_time_utc"]
    assert report["disagreement_bps"] == 0.0


def test_coherence_ignores_non_equivalent_open_candle() -> None:
    left = make_snapshot(provider="binance", timeframe="1D")
    right = make_snapshot(provider="okx", timeframe="1D")
    candles = list(right.candles)
    last = candles[-1]
    unclosed = replace(
        last,
        open_time_utc=last.close_time_utc,
        close_time_utc=last.close_time_utc + timedelta(days=1),
        open=last.close,
        high=last.close + 500.0,
        low=last.close - 1.0,
        close=last.close + 499.0,
    )
    right_with_open_candle = replace(right, candles=tuple(candles + [unclosed]))

    report = snapshot_coherence_report(left, right_with_open_candle)

    assert report["status"] == "OK"
    assert report["right_price"] == last.close
    assert report["aligned_close_time_utc"] == last.close_time_utc.isoformat().replace(
        "+00:00",
        "Z",
    )
