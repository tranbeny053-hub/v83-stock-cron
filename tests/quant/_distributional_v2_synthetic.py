"""Deterministic synthetic candles for the distributional-v2 golden test.

Shared by the committed test and by the offline oracle that computed the expected values with R2's
research model. Only IEEE-754 +, -, *, /, abs, min and max are used, so every platform generates
bit-identical candles; no transcendental function touches the inputs.
"""

from __future__ import annotations

from datetime import UTC, datetime

from crypto_probability_engine.adapters.types import MarketCandle

BAR_SECONDS = {"15m": 900, "1H": 3_600, "4H": 14_400}
_MASK = (1 << 64) - 1

# (last closed bar's open time, as an ISO UTC string), chosen to cover weekday and weekend calendar
# cells and, on 1H, all three sessions: Asia 00-07, Europe 08-15, US 16-23.
GOLDEN_WINDOWS = {
    "15m": ("2025-03-12T13:45:00Z", "2025-06-14T21:30:00Z", "2025-01-06T03:00:00Z"),
    "1H": ("2025-03-12T13:00:00Z", "2025-06-14T21:00:00Z", "2025-01-06T03:00:00Z"),
    "4H": ("2025-03-12T12:00:00Z", "2025-06-14T20:00:00Z", "2025-01-06T00:00:00Z"),
}
GOLDEN_BANDS = (0.002, 0.0045, 0.001)


def epoch_seconds(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def synthetic_candles(
    timeframe: str, *, last_open_seconds: int, count: int, seed: int
) -> tuple[MarketCandle, ...]:
    """``count`` adjacent closed candles whose last one opens at ``last_open_seconds``."""

    bar = BAR_SECONDS[timeframe]
    state = seed & _MASK

    def uniform() -> float:
        nonlocal state
        state = (state * 6364136223846793005 + 1442695040888963407) & _MASK
        return ((state >> 11) + 0.5) / 9007199254740992.0

    price = 100.0 + float(seed % 97)
    level = 0.004
    candles = []
    first_open = last_open_seconds - (count - 1) * bar
    for step in range(count):
        opened = first_open + step * bar
        hour = (opened % 86_400) // 3_600
        season = 0.7 + 0.6 * (abs(hour - 12) / 12.0)
        shock = (uniform() + uniform() + uniform() - 1.5) * 2.0
        level = 0.94 * level + 0.06 * (0.0015 + abs(shock) * 0.003)
        ret = shock * level * season
        close = price * (1.0 + ret)
        high = max(price, close) * (1.0 + uniform() * level * season)
        low = min(price, close) * (1.0 - uniform() * level * season)
        candles.append(
            MarketCandle(
                open_time_utc=datetime.fromtimestamp(opened, tz=UTC),
                close_time_utc=datetime.fromtimestamp(opened + bar, tz=UTC),
                open=price,
                high=high,
                low=low,
                close=close,
                volume=1000.0 + step,
            )
        )
        price = close
    return tuple(candles)


def golden_seed(symbol: str, timeframe: str, window: int) -> int:
    return (sum(ord(character) for character in f"{symbol}|{timeframe}") << 8) + window
