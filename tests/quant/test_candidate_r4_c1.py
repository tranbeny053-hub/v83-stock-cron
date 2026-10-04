"""R4-C1 (``r4-c1-symmetric-cb``): the Phase 4 candidate identity of R4's exact C1 recipe (P4-1).

Synthetic candles and synthetic constants only: no real constants exist until a D4-authorized DEV
refit (OP-1). The tests pin the identity (its name, recipe digest, timeframes and HAR terms), its
fail-closed behaviour, the validator that refuses anything but this recipe, and the probabilities'
construction (R2's _triplets on a symmetric table).
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest

from crypto_probability_engine.quant import candidate_r4_c1 as c1
from crypto_probability_engine.quant import probability_distributional_v2 as v2
from crypto_probability_engine.quant.distributional_v2_tables import CELLS as V2_CELLS
from tests.quant._distributional_v2_synthetic import epoch_seconds, synthetic_candles

ROOT = Path(__file__).resolve().parents[2]
LAST_OPEN = {"1H": epoch_seconds("2025-03-12T13:00:00Z"),
             "15m": epoch_seconds("2025-03-12T13:45:00Z")}


def symmetric_knots(scale: float = 1.0) -> list[float]:
    upper = [scale * math.tan(math.pi * (p - 0.5) * 0.9) for p in np.linspace(0.5, 1.0, 51)[1:]]
    return [-value for value in reversed(upper)] + [0.0] + upper


def cell(timeframe: str, **changes) -> dict:
    payload = {
        "coefficients": [-1.0] + [0.15] * (len(c1.HAR_FEATURES[timeframe]) + 1),
        "profile": [0.6 + 0.02 * index for index in range(c1.PROFILE_CELLS)],
        "knots": symmetric_knots(),
        "sample_size": 25_000,
    }
    payload.update(changes)
    return payload


def payload(**cells) -> dict:
    return {"candidate": c1.CANDIDATE_NAME, "recipe_sha256": c1.RECIPE_SHA256,
            "cells": cells or {"BTC/USDT": {"1H": cell("1H"), "15m": cell("15m")}}}


def constants():
    return c1.validate_constants(payload())


def window(timeframe: str, seed: int = 7):
    return synthetic_candles(timeframe, last_open_seconds=LAST_OPEN[timeframe],
                             count=c1.REQUIRED_CANDLES[timeframe] + 5, seed=seed)


def compute(timeframe="1H", band=0.0045, **kwargs):
    frozen = kwargs.get("frozen", constants())
    return c1.compute_r4_c1_probabilities(window(timeframe), symbol="BTC/USDT",
                                          timeframe=timeframe, band_frac=band, constants=frozen)


# ------------------------------------------------------------------ the identity


def test_the_identity_is_its_own_and_never_distributional_v2() -> None:
    assert c1.CANDIDATE_NAME == "r4-c1-symmetric-cb" != v2.CANDIDATE_NAME
    source = (ROOT / "src/crypto_probability_engine/quant/candidate_r4_c1.py").read_text()
    imports = [line for line in source.splitlines() if line.startswith(("import ", "from "))]
    assert not [line for line in imports if "distributional" in line], "no code shared with v2"


def test_the_recipe_digest_is_pinned_and_recomputable() -> None:
    canonical = json.dumps(dict(c1.RECIPE), sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(canonical.encode()).hexdigest() == c1.RECIPE_SHA256
    assert c1.RECIPE_SHA256 == "2f4742c69a74045bc18064d19dbef8f5f5f3f626c39e9f2ba51316ed3b5212f9"
    assert c1.RECIPE["shape"]["symmetric"] is True and c1.RECIPE["shape"]["tables"] == 1


def test_r4_carried_15m_and_1h_only_and_1h_drops_rv_day() -> None:
    assert c1.SUPPORTED_TIMEFRAMES == ("15m", "1H") == c1.R4_PROVENANCE["carried"]
    assert "4H" not in c1.REQUIRED_CANDLES
    assert "rv_day" not in c1.HAR_FEATURES["1H"] and "rv_day" in c1.HAR_FEATURES["15m"]
    assert c1.HAR_FEATURES["15m"] == v2.HAR_FEATURES
    assert c1.REQUIRED_CANDLES == {"15m": 673, "1H": 169}
    assert c1.R4_PROVENANCE["stage_b_commitment_sha256"].startswith("154a75c4")
    assert c1.R4_PROVENANCE["stage_b_commitment_sha256"].endswith("2211")


def test_the_grid_is_numpy_s_linspace_value_for_value() -> None:
    assert list(c1.PROBABILITY_GRID) == [float(x) for x in np.linspace(0.0, 1.0, 101)]


def test_the_calendar_key_is_r2_s_hour_by_weekend_cell() -> None:
    for timeframe in ("15m", "1H"):
        start = LAST_OPEN[timeframe]
        for step in range(400):
            moment = start + step * 3_600
            assert c1.calendar_key(moment) == v2.calendar_key(moment, timeframe)


# ------------------------------------------------------------------ fail closed


def test_without_frozen_constants_every_call_fails_closed() -> None:
    with pytest.raises(c1.CandidateNotFrozenError, match="OP-1"):
        compute(frozen=None)
    with pytest.raises(c1.CandidateNotFrozenError, match="ETH/USDT"):
        c1.compute_r4_c1_probabilities(window("1H"), symbol="ETH/USDT", timeframe="1H",
                                       band_frac=0.0045, constants=constants())


@pytest.mark.parametrize(("symbol", "timeframe"), [("BTC/USDT", "4H"), ("SOL/USDT", "1H")])
def test_an_unserved_symbol_or_timeframe_is_refused(symbol: str, timeframe: str) -> None:
    with pytest.raises(ValueError, match="does not serve"):
        c1.compute_r4_c1_probabilities(window("1H"), symbol=symbol, timeframe=timeframe,
                                       band_frac=0.0045, constants=constants())


@pytest.mark.parametrize("band", [True, -0.001, float("nan"), "0.004"])
def test_a_bad_band_is_refused(band) -> None:
    with pytest.raises(ValueError, match="band"):
        compute(band=band)


def test_a_bad_window_is_refused() -> None:
    candles = list(window("1H"))
    with pytest.raises(ValueError, match="closed candles"):
        c1.compute_r4_c1_probabilities(candles[:100], symbol="BTC/USDT", timeframe="1H",
                                       band_frac=0.0045, constants=constants())
    gap = candles[:-2] + candles[-1:]
    with pytest.raises(ValueError, match="adjacent"):
        c1.compute_r4_c1_probabilities(gap, symbol="BTC/USDT", timeframe="1H", band_frac=0.0045,
                                       constants=constants())
    with pytest.raises(ValueError, match="one bar"):
        c1.compute_r4_c1_probabilities(window("15m"), symbol="BTC/USDT", timeframe="1H",
                                       band_frac=0.0045, constants=constants())


# ------------------------------------------------------------------ the validator


def test_a_correct_payload_validates_into_cells() -> None:
    cells = constants()
    assert set(cells) == {("BTC/USDT", "1H"), ("BTC/USDT", "15m")}
    assert len(cells[("BTC/USDT", "1H")].coefficients) == 8
    assert len(cells[("BTC/USDT", "15m")].coefficients) == 9


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"candidate": "distributional-v2"}, "another candidate"),
        ({"recipe_sha256": "0" * 64}, "another recipe"),
        ({"cells": {}}, "no cells"),
        ({"cells": {"SOL/USDT": {"1H": cell("1H")}}}, "does not serve"),
        ({"cells": {"BTC/USDT": {"4H": cell("1H")}}}, "does not serve"),
        ({"cells": {"BTC/USDT": {"1H": cell("15m")}}}, "8 coefficients"),
        ({"cells": {"BTC/USDT": {"15m": cell("1H")}}}, "9 coefficients"),
        ({"cells": {"BTC/USDT": {"1H": cell("1H", coefficients=[True] * 8)}}}, "finite numbers"),
        ({"cells": {"BTC/USDT": {"1H": cell("1H", profile=[1.0] * 47)}}}, "48 positive"),
        ({"cells": {"BTC/USDT": {"1H": cell("1H", profile=[0.0] + [1.0] * 47)}}}, "48 positive"),
        ({"cells": {"BTC/USDT": {"1H": cell("1H", knots=symmetric_knots()[:100])}}},
         "101 strictly"),
        ({"cells": {"BTC/USDT": {"1H": cell("1H", knots=sorted(symmetric_knots() * 1)[::-1])}}},
         "101 strictly"),
        ({"cells": {"BTC/USDT": {"1H": cell("1H", knots=[k + 0.01 for k in symmetric_knots()])}}},
         "symmetric"),
        ({"cells": {"BTC/USDT": {"1H": cell("1H", sample_size=True)}}}, "sample size"),
        ({"cells": {"BTC/USDT": {"1H": cell("1H", sample_size=0)}}}, "sample size"),
    ],
)
def test_anything_but_this_recipe_is_refused(change: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        c1.validate_constants({**payload(), **change})


def test_distributional_v2_s_own_tables_are_refused_as_asymmetric() -> None:
    knots, _, n = V2_CELLS["BTC/USDT"]["15m"]["tables"][0]
    with pytest.raises(ValueError, match="symmetric"):
        c1.validate_constants(payload(**{"BTC/USDT": {"15m": cell("15m", knots=list(knots),
                                                                     sample_size=n)}}))


# ------------------------------------------------------------------ the probabilities


def test_the_triplet_is_symmetric_and_sums_to_one() -> None:
    for timeframe in ("1H", "15m"):
        result = compute(timeframe)
        assert abs(result.p_up_frac - result.p_down_frac) <= 1e-12
        assert abs(result.p_up_frac + result.p_down_frac + result.p_timeout_frac - 1.0) <= 1e-12
        assert 0.0 < result.p_timeout_frac < 1.0 and result.sigma_h > 0.0


def test_the_timeout_grows_with_the_band_and_a_zero_band_has_none() -> None:
    timeouts = [compute(band=band).p_timeout_frac for band in (0.0, 0.001, 0.0045, 0.01)]
    assert timeouts == sorted(timeouts) and timeouts[0] == 0.0
    zero = compute(band=0.0)
    assert zero.p_up_frac == zero.p_down_frac == 0.5


def test_a_band_past_the_table_clamps_both_tails_equally() -> None:
    result = compute(band=50.0)
    n = constants()[("BTC/USDT", "1H")].sample_size
    assert result.p_up_frac == result.p_down_frac == 1.0 / (n + 1)
    assert math.isclose(result.p_timeout_frac, (n - 1) / (n + 1), rel_tol=0, abs_tol=1e-15)


def test_sigma_and_the_central_range_follow_the_recipe() -> None:
    frozen = constants()[("BTC/USDT", "1H")]
    candles = window("1H")[-c1.REQUIRED_CANDLES["1H"]:]
    closes = [candle.close for candle in candles]
    squared = [(closes[i] / closes[i - 1] - 1.0) ** 2 for i in range(1, len(closes))]
    parkinson = [math.log(x.high / x.low) ** 2 / (4 * math.log(2)) for x in candles]
    features = [squared[-1], sum(squared[-6:]) / 6, sum(squared[-24:]) / 24,
                sum(squared[-168:]) / 168, sum(parkinson[-6:]) / 6, sum(parkinson[-24:]) / 24]
    last_open = int(candles[-1].open_time_utc.timestamp())
    m = sum(frozen.profile[c1.calendar_key(last_open + k * 3_600)] for k in range(1, 7)) / 6
    design = [1.0] + [math.log(f + c1.EPS) for f in features] + [math.log(m + c1.EPS)]
    log_variance = sum(b * x for b, x in zip(frozen.coefficients, design, strict=True))
    sigma = math.sqrt(math.exp(log_variance))
    result = compute()
    assert math.isclose(result.sigma_h, sigma, rel_tol=1e-12)
    assert math.isclose(result.profile_mean, m, rel_tol=1e-12)
    half_width = result.central_range_half_width_frac
    assert math.isclose(half_width, frozen.knots[90] * sigma, rel_tol=1e-12)
    assert result.candles_used == 169


def test_the_log_variance_is_clipped_and_the_scale_floored() -> None:
    high = payload(**{"BTC/USDT": {"1H": cell("1H", coefficients=[500.0] + [0.0] * 7)}})
    low = payload(**{"BTC/USDT": {"1H": cell("1H", coefficients=[-500.0] + [0.0] * 7)}})
    assert compute(frozen=c1.validate_constants(high)).sigma_h == math.sqrt(math.exp(20.0))
    assert compute(frozen=c1.validate_constants(low)).sigma_h == 1e-9  # exp(-60) is below the floor


def test_the_cdf_is_r2_s_interpolation_with_its_tail_clamps() -> None:
    knots = symmetric_knots()
    n = 1_000
    grid = np.linspace(0.0, 1.0, 101)
    for value in np.linspace(-20, 20, 401):
        expected = float(np.clip(np.interp(value, knots, grid), 1 / (n + 1), n / (n + 1)))
        if value < knots[0]:
            expected = 1 / (n + 1)
        if value >= knots[-1]:
            expected = n / (n + 1)
        assert math.isclose(c1._cdf(float(value), knots, n), expected, rel_tol=0, abs_tol=1e-15)
