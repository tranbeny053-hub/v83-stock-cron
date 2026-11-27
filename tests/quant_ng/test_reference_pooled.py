from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from crypto_probability_engine.adapters.types import MarketCandle
from crypto_probability_engine.quant_ng import reference_pooled as pooled
from crypto_probability_engine.quant_ng.windows import TIMEFRAME_SECONDS
from crypto_probability_engine.utils.invariants import validate_probability_triplet

ROOT = Path(__file__).resolve().parents[2]


def candles(
    timeframe: str,
    count: int,
    *,
    closes: list[float] | None = None,
    last_close_offset: int = 0,
) -> tuple[MarketCandle, ...]:
    bar = TIMEFRAME_SECONDS[timeframe]
    lattice = pooled.LATTICE_BARS * bar
    base = int(datetime(2025, 1, 1, tzinfo=UTC).timestamp())
    last_close = base + (last_close_offset * bar - base % lattice) % lattice
    first_close = last_close - (count - 1) * bar
    prices = closes if closes is not None else [100.0] * count
    result = []
    for index, close in enumerate(prices):
        close_time = datetime.fromtimestamp(first_close + index * bar, tz=UTC)
        open_time = close_time - timedelta(seconds=bar)
        result.append(
            MarketCandle(
                open_time_utc=open_time,
                close_time_utc=close_time,
                open=close,
                high=max(close, 100.0) + 1.0,
                low=min(close, 100.0) - 1.0,
                close=close,
                volume=1.0,
            )
        )
    return tuple(result)


def assert_reason(reason: pooled.RefusalReason, call) -> None:
    with pytest.raises(pooled.PooledReferenceUnavailable) as error:
        call()
    assert error.value.reason is reason
    assert str(error.value) == f"{reason.value}: {error.value.detail}"


def compute(items, timeframe: str, band: object = 0.0):
    return pooled.compute_pooled_reference(items, timeframe=timeframe, band_frac=band)


def test_window_and_k_constants() -> None:
    assert [pooled.bars_required(tf) for tf in ("15m", "1H", "4H")] == [678, 678, 174]
    assert [pooled.expected_k(tf) for tf in ("15m", "1H", "4H")] == [224, 224, 56]


@pytest.mark.parametrize("timeframe", ["15m", "1H", "4H"])
@pytest.mark.parametrize("offset", [0, 1, 2])
def test_lattice_alignment_keeps_expected_k(timeframe: str, offset: int) -> None:
    result = compute(
        candles(timeframe, pooled.bars_required(timeframe), last_close_offset=offset), timeframe
    )
    assert result.matured_outcome_count == pooled.expected_k(timeframe)
    validate_probability_triplet(result.p_up_frac, result.p_down_frac, result.p_timeout_frac)


@pytest.mark.parametrize("timeframe", ["15m", "1H", "4H"])
def test_constant_prices_are_all_inside_band(timeframe: str) -> None:
    result = compute(candles(timeframe, pooled.bars_required(timeframe)), timeframe)
    assert result.inside_band_count == result.matured_outcome_count
    assert result.p_timeout_frac == 1.0
    assert result.p_up_frac == result.p_down_frac == 0.0
    validate_probability_triplet(result.p_up_frac, result.p_down_frac, result.p_timeout_frac)


def test_hand_built_4h_series_has_fourteen_inside_outcomes() -> None:
    timeframe = "4H"
    items = candles(timeframe, pooled.bars_required(timeframe), last_close_offset=0)
    # The first 14 two-step log returns cancel; the remaining 42 are positive.
    anchor_phase = next(
        i
        for i, candle in enumerate(items)
        if int(candle.close_time_utc.timestamp()) % (3 * TIMEFRAME_SECONDS[timeframe]) == 0
    )
    node_count = 58
    increments = [0.01 if index % 2 == 0 else -0.01 for index in range(14)]
    increments.extend([0.01] * (node_count - 1 - len(increments)))
    nodes = [100.0]
    for change in increments:
        nodes.append(nodes[-1] * math.exp(change))
    prices = [100.0] * len(items)
    for node_index, price in enumerate(nodes):
        candle_index = anchor_phase + 3 * node_index
        if candle_index < len(prices):
            prices[candle_index] = price
    # Fill between lattice points without changing the lattice node closes.
    for index in range(len(prices)):
        if index and prices[index] == 100.0:
            prices[index] = prices[index - 1]
    adjusted = tuple(
        MarketCandle(
            c.open_time_utc, c.close_time_utc, price, price + 1, price - 1, price, c.volume
        )
        for c, price in zip(items, prices, strict=True)
    )
    result = compute(adjusted, timeframe, 0.005)
    assert result.inside_band_count == 14
    assert result.matured_outcome_count == 56
    assert result.p_timeout_frac == 0.25
    assert result.p_up_frac == result.p_down_frac == 0.375
    validate_probability_triplet(result.p_up_frac, result.p_down_frac, result.p_timeout_frac)


def test_both_band_edges_are_inside() -> None:
    timeframe = "15m"
    items = list(candles(timeframe, pooled.bars_required(timeframe)))
    lattice_seconds = pooled.LATTICE_BARS * TIMEFRAME_SECONDS[timeframe]
    anchor_index = next(
        i
        for i, candle in enumerate(items[: -pooled.HORIZON_BARS])
        if int(candle.close_time_utc.timestamp()) % lattice_seconds == 0
    )
    band = 101.0 / 100.0 - 1.0
    for anchor, end, end_price in (
        (anchor_index, anchor_index + 6, 101.0),
        (anchor_index + 3, anchor_index + 9, 99.0),
    ):
        items[anchor] = _with_close(items[anchor], 100.0)
        items[end] = _with_close(items[end], end_price)
    result = compute(tuple(items), timeframe, band)
    assert result.inside_band_count == 223
    assert result.p_timeout_frac == result.inside_band_count / result.matured_outcome_count
    validate_probability_triplet(result.p_up_frac, result.p_down_frac, result.p_timeout_frac)


def _with_close(candle: MarketCandle, close: float) -> MarketCandle:
    return MarketCandle(
        candle.open_time_utc,
        candle.close_time_utc,
        close,
        close + 1,
        close - 1,
        close,
        candle.volume,
    )


def test_refusals_have_exact_reasons() -> None:
    valid = candles("15m", 678)
    assert_reason(
        pooled.RefusalReason.TIMEFRAME_UNSUPPORTED,
        lambda: compute(valid, "1D", 0.1),
    )
    for band in (None, float("nan"), float("inf"), -0.001, True):
        assert_reason(
            pooled.RefusalReason.BAND_UNAVAILABLE, lambda band=band: compute(valid, "15m", band)
        )
    gap = list(valid)
    gap[10] = _shift_candle(gap[10], timedelta(seconds=900))
    assert_reason(pooled.RefusalReason.WINDOW_MALFORMED, lambda: compute(tuple(gap), "15m"))
    unaligned = _shift_candle(valid[0], timedelta(seconds=1))
    assert_reason(
        pooled.RefusalReason.WINDOW_MALFORMED,
        lambda: compute((unaligned, *valid[1:]), "15m"),
    )
    assert_reason(
        pooled.RefusalReason.WINDOW_SHORT,
        lambda: compute(candles("15m", 677), "15m"),
    )


def _shift_candle(candle: MarketCandle, amount: timedelta) -> MarketCandle:
    return MarketCandle(
        candle.open_time_utc + amount,
        candle.close_time_utc + amount,
        candle.open,
        candle.high,
        candle.low,
        candle.close,
        candle.volume,
    )


def test_extra_candles_are_ignored_and_only_last_window_is_returned() -> None:
    all_items = candles("15m", 1000)
    full = compute(all_items, "15m", 0.01)
    suffix = compute(all_items[-678:], "15m", 0.01)
    assert full == suffix
    assert full.window_first_close_utc == all_items[-678].close_time_utc
    validate_probability_triplet(full.p_up_frac, full.p_down_frac, full.p_timeout_frac)


def test_k_mismatch_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pooled, "expected_k", lambda timeframe: 225)
    assert_reason(
        pooled.RefusalReason.K_MISMATCH,
        lambda: compute(candles("15m", 678), "15m"),
    )


def test_module_is_pure_and_uses_strict_memory_boundary() -> None:
    source = (ROOT / "src/crypto_probability_engine/quant_ng/reference_pooled.py").read_text()
    for forbidden in ("open(", "requests", "httpx", "urllib", "socket", "datetime.now", "random"):
        assert forbidden not in source
    # The fixed window has no candidate ending exactly at ref-memory; retain this rule explicitly.
    assert "def selected_anchors(" in source
    assert "memory_start < end.close_time_utc <= ref" in source
    assert "selected_anchors(window, timeframe, band)" in source
