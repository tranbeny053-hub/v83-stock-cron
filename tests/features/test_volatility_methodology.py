from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import isclose

from crypto_probability_engine.adapters.types import MarketCandle
from crypto_probability_engine.features.volatility import compute_realized_volatility


def _candles_from_returns(returns: list[float]) -> tuple[MarketCandle, ...]:
    close = 100.0
    closes = [close]
    for value in returns:
        close *= 1.0 + value
        closes.append(close)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    candles: list[MarketCandle] = []
    for idx, close_price in enumerate(closes):
        open_time = start + timedelta(hours=idx)
        candles.append(
            MarketCandle(
                open_time_utc=open_time,
                close_time_utc=open_time + timedelta(hours=1),
                open=close_price,
                high=close_price * 1.01,
                low=close_price * 0.99,
                close=close_price,
                volume=1_000.0,
            )
        )
    return tuple(candles)


def test_realized_volatility_is_per_bar_not_sample_count_scaled() -> None:
    pattern = [0.012, -0.018, 0.009, -0.006]
    single = compute_realized_volatility(_candles_from_returns(pattern * 12))
    duplicated = compute_realized_volatility(_candles_from_returns(pattern * 24))

    assert single["method"] == "PER_BAR_LOG_RETURN_PSTDEV"
    assert duplicated["method"] == "PER_BAR_LOG_RETURN_PSTDEV"
    assert isclose(single["realized_vol"], duplicated["realized_vol"], rel_tol=1e-12)
