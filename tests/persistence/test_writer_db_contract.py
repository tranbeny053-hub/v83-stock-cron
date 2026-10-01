"""§8.2 groundwork (DBI-1): every prediction row the writer can emit meets the candidate invariants.

The constraints a later migration may add to `predictions` (NOT VALID, so they bind new rows only)
are restated here as predicates and checked against rows the real pipeline produces across market
shapes and every timeframe. A writer change that would breach them fails here first, before any
database could reject a production write. The probability tolerance is the pipeline's own
(utils/invariants.PROBABILITY_TOLERANCE), never a stricter one. The writer's refusals, which keep
invalid rows from ever being built, are pinned too.
"""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from crypto_probability_engine.api.analysis_service import _prediction_row
from crypto_probability_engine.config.defaults import TIMEFRAME_SECONDS
from crypto_probability_engine.quant.pipeline import run_quant_pipeline
from crypto_probability_engine.utils.invariants import PROBABILITY_TOLERANCE
from tests.fixtures.market_data import (
    make_downtrend_snapshot,
    make_high_volatility_snapshot,
    make_snapshot,
)

LIVE = {
    "is_live_data": True,
    "data_source": "BINANCE_PUBLIC",
    "cross_provider_state": "UNAVAILABLE",
}
PROVIDER = {"status": "OK", "active_provider": "binance"}
SHAPES = {
    "uptrend": make_snapshot,
    "downtrend": make_downtrend_snapshot,
    "volatile": make_high_volatility_snapshot,
}


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def candidate_violations(row: dict) -> list[str]:
    """The candidate CHECKs on `predictions` (see .work/roadmap/dbi1/), as Python predicates."""

    violations = []
    probabilities = [row["p_up_frac"], row["p_down_frac"], row["p_timeout_frac"]]
    if not all(isinstance(p, float) and math.isfinite(p) and 0.0 <= p <= 1.0
               for p in probabilities):
        violations.append("probability range")
    elif abs(sum(probabilities) - 1.0) > PROBABILITY_TOLERANCE:
        violations.append("probability sum")
    price = row["reference_price"]
    if not (isinstance(price, float) and math.isfinite(price) and price > 0.0):
        violations.append("reference price")
    if not (isinstance(row["horizon_bars"], int) and row["horizon_bars"] > 0):
        violations.append("horizon bars")
    reference = _utc(row["reference_close_utc"])
    if reference > _utc(row["predicted_at_utc"]):
        violations.append("reference after prediction")
    if _utc(row["horizon_end_utc"]) <= reference:
        violations.append("horizon end not after reference")
    return violations


def _row(snapshot, timeframe: str, **overrides) -> dict | None:
    quant = overrides.pop("quant_result", None) or run_quant_pipeline(snapshot, PROVIDER)
    return _prediction_row(run_id="run_dbi1", request_symbol="BTC", normalized_symbol="BTC/USDT",
                           timeframe=timeframe, snapshot=snapshot, quant_result=quant,
                           data_quality=overrides.pop("data_quality", LIVE),
                           provider_state=PROVIDER)


@pytest.mark.parametrize("shape", sorted(SHAPES))
@pytest.mark.parametrize("timeframe", sorted(TIMEFRAME_SECONDS))
def test_every_row_the_writer_emits_meets_the_candidate_invariants(
    shape: str, timeframe: str
) -> None:
    row = _row(SHAPES[shape](provider="binance", timeframe=timeframe), timeframe)
    assert row is not None, "a live row is expected for every shape and timeframe"
    assert candidate_violations(row) == []


@pytest.mark.parametrize("close_shift", [-50.0, -5.0, 0.0, 5.0, 50.0])
def test_moving_the_last_close_keeps_every_row_inside_the_invariants(close_shift: float) -> None:
    row = _row(make_snapshot(provider="binance", timeframe="1H", close_shift=close_shift), "1H")
    assert row is not None
    assert candidate_violations(row) == []


def _with_last_close(snapshot, close: float):
    last = replace(snapshot.candles[-1], close=close)
    return replace(snapshot, candles=(*snapshot.candles[:-1], last))


def test_the_writer_refuses_rows_that_would_break_the_invariants() -> None:
    snapshot = make_snapshot(provider="binance", timeframe="4H")
    quant = run_quant_pipeline(snapshot, PROVIDER)
    assert _row(snapshot, "4H", quant_result=quant) is not None
    # A non-positive reference price never becomes a row.
    for close in (0.0, -1.0):
        assert _row(_with_last_close(snapshot, close), "4H", quant_result=quant) is None
    # A reference close after the prediction time never becomes a row.
    early = replace(snapshot, as_of_utc=snapshot.candles[-1].close_time_utc - timedelta(seconds=1))
    assert _row(early, "4H", quant_result=quant) is None
    # Fixture (non-live) data and missing probabilities never become rows.
    assert _row(snapshot, "4H", quant_result=quant, data_quality={"is_live_data": False}) is None
    broken = {**quant, "probability_state": {"horizons": {}}}
    assert _row(snapshot, "4H", quant_result=broken) is None


def test_the_predicates_are_not_vacuous() -> None:
    row = _row(make_snapshot(provider="binance", timeframe="4H"), "4H")
    assert row is not None and candidate_violations(row) == []
    cases = {
        "probability range": {"p_up_frac": 1.2},
        "probability sum": {"p_up_frac": row["p_up_frac"] + 2 * PROBABILITY_TOLERANCE},
        "reference price": {"reference_price": float("nan")},
        "horizon bars": {"horizon_bars": 0},
        "reference after prediction": {"reference_close_utc": "2999-01-01T00:00:00Z"},
        "horizon end not after reference": {"horizon_end_utc": row["reference_close_utc"]},
    }
    for expected, change in cases.items():
        assert expected in candidate_violations({**row, **change}), expected
