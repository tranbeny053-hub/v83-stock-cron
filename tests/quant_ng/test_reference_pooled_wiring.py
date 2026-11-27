from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from crypto_probability_engine.quant_ng.reference import Label, anchors_from_candles
from crypto_probability_engine.quant_ng.reference_pooled import (
    MEMORY_DAYS,
    bars_required,
    compute_pooled_reference,
    selected_anchors,
)
from crypto_probability_engine.quant_ng.windows import TIMEFRAME_SECONDS
from tests.fixtures.market_data import FIXED_NOW, make_candles
from tests.quant_ng.test_reference import SPEC


@pytest.mark.parametrize("timeframe", ["15m", "1H", "4H"])
@pytest.mark.parametrize("phase", [0, 1, 2])
def test_a5_anchor_selection_matches_reference_for_each_lattice_phase(timeframe, phase):
    seconds = TIMEFRAME_SECONDS[timeframe]
    candles = make_candles(
        count=bars_required(timeframe), timeframe_seconds=seconds, as_of_utc=FIXED_NOW
    )
    shift = timedelta(seconds=phase * seconds)
    alternating = []
    for index, candle in enumerate(candles):
        opened = candle.open_time_utc + shift
        closed = candle.close_time_utc + shift
        # A deterministic non-monotone series gives matured UP, DOWN and TIMEOUT labels.
        close = 100.0 + ((index * 7) % 13) * 0.08
        high = max(candle.open, close) + 0.01
        low = min(candle.open, close) - 0.01
        alternating.append(
            replace(
                candle,
                open_time_utc=opened,
                close_time_utc=closed,
                close=close,
                high=high,
                low=low,
            )
        )
    candles = tuple(alternating)
    band = 0.003
    pooled = compute_pooled_reference(candles, timeframe=timeframe, band_frac=band)
    anchors = anchors_from_candles(candles, timeframe=timeframe, band_frac=band, spec=SPEC)

    ref = candles[-1].close_time_utc
    memory_start = ref - timedelta(days=MEMORY_DAYS[timeframe])
    reference_selection = tuple(
        (anchor.reference_close_utc, anchor.horizon_end_utc, anchor.label)
        for anchor in anchors
        if memory_start < anchor.horizon_end_utc <= ref
    )
    pooled_selection = selected_anchors(candles, timeframe, band)

    assert pooled_selection == reference_selection
    assert pooled.matured_outcome_count == len(reference_selection)
    assert pooled.inside_band_count == sum(
        label is Label.TIMEOUT for _, _, label in reference_selection
    )
    assert 0 < pooled.inside_band_count < pooled.matured_outcome_count
    lattice = 3 * seconds
    assert int(candles[-1].close_time_utc.timestamp()) % lattice == phase * seconds
