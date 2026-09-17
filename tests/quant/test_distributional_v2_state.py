"""The distributional-v2 pipeline states are exactly v1's contract, and nothing wires them yet."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from crypto_probability_engine.quant.distributional_v2_state import (
    build_distributional_v2_probability_state,
    build_distributional_v2_timeout_state,
)
from crypto_probability_engine.quant.distributional_v2_tables import REQUIRED_CANDLES
from crypto_probability_engine.quant.probability_distributional import (
    DistributionalProbability,
    build_distributional_probability_state,
)
from crypto_probability_engine.quant.probability_distributional_v2 import (
    CANDIDATE_NAME,
    compute_distributional_v2_probabilities,
)
from tests.quant._distributional_v2_synthetic import (
    GOLDEN_BANDS,
    GOLDEN_WINDOWS,
    epoch_seconds,
    golden_seed,
    synthetic_candles,
)

ROOT = Path(__file__).resolve().parents[2]
PROBABILITY_SCHEMA = json.loads((ROOT / "schemas" / "quant.schema.json").read_text("utf-8"))[
    "properties"
]["probability_state"]
EPISTEMIC_STATES = (
    {"action": "ALLOW"},
    {"action": "ABORT", "reason": "INSUFFICIENT_HISTORY"},
    {"action": "ABORT"},
)


def _v2_cases():
    for symbol in ("BTC/USDT", "ETH/USDT"):
        for timeframe, windows in GOLDEN_WINDOWS.items():
            for index, iso in enumerate(windows):
                candles = synthetic_candles(
                    timeframe,
                    last_open_seconds=epoch_seconds(iso),
                    count=REQUIRED_CANDLES[timeframe],
                    seed=golden_seed(symbol, timeframe, index),
                )
                for band in GOLDEN_BANDS:
                    yield symbol, timeframe, compute_distributional_v2_probabilities(
                        candles, symbol=symbol, timeframe=timeframe, band_frac=band
                    )


CASES = list(_v2_cases())


@pytest.mark.parametrize("epistemic", EPISTEMIC_STATES, ids=lambda state: str(state))
def test_the_probability_state_is_v1_s_contract_field_for_field(epistemic: dict) -> None:
    for _, _, probability in CASES:
        as_v1 = DistributionalProbability(
            p_up_frac=probability.p_up_frac,
            p_down_frac=probability.p_down_frac,
            p_timeout_frac=probability.p_timeout_frac,
            sigma_bar=float("nan"),
            sigma_h=probability.sigma_h,
            band_frac=probability.band_frac,
        )
        ours = build_distributional_v2_probability_state(probability, epistemic_state=epistemic)
        theirs = build_distributional_probability_state(as_v1, epistemic_state=epistemic)
        assert ours == theirs
        Draft202012Validator(PROBABILITY_SCHEMA).validate(ours)


def test_every_horizon_keeps_the_probability_invariant() -> None:
    for _, _, probability in CASES:
        for epistemic in EPISTEMIC_STATES:
            state = build_distributional_v2_probability_state(
                probability, epistemic_state=epistemic
            )
            for horizon in state["horizons"].values():
                total = horizon["p_up_frac"] + horizon["p_down_frac"] + horizon["p_timeout_frac"]
                assert math.isclose(total, 1.0, abs_tol=1e-12)
                assert all(
                    0.0 <= horizon[key] <= 1.0
                    for key in ("p_up_frac", "p_down_frac", "p_timeout_frac")
                )


def test_the_directional_split_is_reported_as_computed_and_neutralized_on_abort() -> None:
    asymmetric = [p for _, _, p in CASES if p.p_up_frac != p.p_down_frac]
    assert len(asymmetric) == len(CASES), "a zero-location model with skewed tables is not 50/50"
    probability = asymmetric[0]
    allowed = build_distributional_v2_probability_state(
        probability, epistemic_state={"action": "ALLOW"}
    )["horizons"]["H_primary"]
    assert allowed["p_up_frac"] == probability.p_up_frac
    assert allowed["p_up_user_norm_frac"] != 0.5
    aborted = build_distributional_v2_probability_state(
        probability, epistemic_state={"action": "ABORT", "reason": "INSUFFICIENT_HISTORY"}
    )["horizons"]["H_primary"]
    assert aborted["p_up_frac"] == aborted["p_down_frac"]
    assert aborted["p_timeout_frac"] == probability.p_timeout_frac
    assert aborted["status"] == "NULL" and aborted["confidence_frac"] == 0.0
    assert aborted["null_reason"] == "INSUFFICIENT_HISTORY"


def test_the_timeout_state_names_the_candidate_and_its_own_scale_facts() -> None:
    sessions = set()
    for _, timeframe, probability in CASES:
        state = build_distributional_v2_timeout_state(probability, timeframe=timeframe)
        assert state == {
            "status": "OK",
            "method": CANDIDATE_NAME,
            "p_timeout_frac": probability.p_timeout_frac,
            "timeout_is_directional": False,
            "timeframe": timeframe,
            "sigma_h": probability.sigma_h,
            "band_frac": probability.band_frac,
            "profile_mean": probability.profile_mean,
            "session": probability.session,
            "candles_used": REQUIRED_CANDLES[timeframe],
        }
        assert "sigma_bar" not in state, "v2 has no single-bar EWMA scale"
        if timeframe == "1H":
            sessions.add(state["session"])
        else:
            assert state["session"] is None
    assert sessions == {0, 1, 2}


def test_nothing_wires_the_v2_states_yet() -> None:
    source = ROOT / "src" / "crypto_probability_engine"
    importers = [
        path.relative_to(ROOT).as_posix()
        for path in source.rglob("*.py")
        if "distributional_v2_state" in path.read_text(encoding="utf-8")
        and path.name != "distributional_v2_state.py"
    ]
    assert importers == []
