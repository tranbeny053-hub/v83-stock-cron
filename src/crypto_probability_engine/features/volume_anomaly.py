"""Volume anomaly feature."""

from __future__ import annotations

from crypto_probability_engine.adapters.types import MarketCandle


def compute_volume_anomaly(candles: tuple[MarketCandle, ...], *, lookback: int = 20) -> dict:
    if len(candles) < lookback + 1:
        return {"status": "DEGRADED", "volume_ratio": 1.0}
    recent = candles[-lookback - 1 : -1]
    baseline = sum(candle.volume for candle in recent) / len(recent)
    ratio = candles[-1].volume / baseline if baseline > 0 else 1.0
    return {"status": "OK", "volume_ratio": ratio}

