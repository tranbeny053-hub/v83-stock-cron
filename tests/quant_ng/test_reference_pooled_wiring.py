from __future__ import annotations

from datetime import timedelta

from crypto_probability_engine.quant_ng.reference import anchors_from_candles
from crypto_probability_engine.quant_ng.reference_pooled import (
    LATTICE_BARS,
    MEMORY_DAYS,
    bars_required,
    compute_pooled_reference,
)
from tests.fixtures.market_data import FIXED_NOW, make_candles
from tests.quant_ng.test_reference import SPEC


def test_a5_pooled_anchor_selection_matches_v1_reference_anchors():
    timeframe = "15m"
    candles = make_candles(
        count=bars_required(timeframe),
        timeframe_seconds=SPEC.bar_seconds[timeframe],
        as_of_utc=FIXED_NOW,
    )
    band = 0.01
    pooled = compute_pooled_reference(candles, timeframe=timeframe, band_frac=band)
    anchors = anchors_from_candles(
        candles,
        timeframe=timeframe,
        band_frac=band,
        spec=SPEC,
    )

    ref = candles[-1].close_time_utc
    memory_start = ref - timedelta(days=MEMORY_DAYS[timeframe])
    reference_selection = tuple(
        (anchor.reference_close_utc, anchor.horizon_end_utc)
        for anchor in anchors
        if memory_start < anchor.horizon_end_utc <= ref
    )
    needed = bars_required(timeframe)
    selected = candles[-needed:]
    lattice_seconds = LATTICE_BARS * SPEC.bar_seconds[timeframe]
    pooled_selection = tuple(
        (selected[index].close_time_utc, selected[index + 6].close_time_utc)
        for index in range(len(selected))
        if index + 6 < len(selected)
        and int(selected[index].close_time_utc.timestamp()) % lattice_seconds == 0
        and memory_start < selected[index + 6].close_time_utc <= ref
    )

    assert pooled_selection == reference_selection
    assert len(pooled_selection) == pooled.matured_outcome_count
