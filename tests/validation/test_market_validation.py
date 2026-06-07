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
