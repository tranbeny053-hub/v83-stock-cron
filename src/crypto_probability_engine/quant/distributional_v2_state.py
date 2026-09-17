"""distributional-v2 pipeline states. PREP ONLY: NOT WIRED, NOT FROZEN, NOT A METHODOLOGY VERSION.

These are the two pieces a future selector branch in ``quant/pipeline.py`` would call after
``compute_distributional_v2_probabilities``. They are exactly the ``probability_state`` and
``horizon_timeout_state`` shapes the distributional-v1 branch emits, so wiring changes nothing
downstream: the score stack, the gates, the response schema and the frontend see the same contract.
A test compares the probability state with v1's builder, field for field.

Nothing imports this module. The selector and the version constants live in files pinned by the
section 5A evaluator (``quant/pipeline.py``, ``config/defaults.py``), so wiring is the owner's
decision (docs/DISTRIBUTIONAL_V2_PREP.md).

THE DIRECTIONAL SPLIT IS NOT 50/50. Like v1, v2 has no location term, but its empirical shape tables
are skewed, so ``p_up`` and ``p_down`` differ by a fixed, table-driven amount at each band-to-scale
ratio. This builder reports them exactly as computed, as v1's does. Under an epistemic abort it
neutralizes them, as v1's does. Whether and how to display a split that no current market state
drives is an owner decision (docs/R2_ZERO_DRIFT_GATE_AND_DISPLAY.md §7).
"""

from __future__ import annotations

from crypto_probability_engine.config.defaults import DEFAULT_PHASE1A
from crypto_probability_engine.quant.probability_distributional_v2 import (
    CANDIDATE_NAME,
    DistributionalV2Probability,
)

PROBABILITY_SCHEMA_VERSION = "1.1-crypto-probability"


def build_distributional_v2_probability_state(
    probability: DistributionalV2Probability,
    *,
    epistemic_state: dict,
) -> dict:
    """The ``probability_state`` v1's builder emits, for a v2 triplet."""

    status = "OK" if epistemic_state.get("action") == "ALLOW" else "NULL"
    null_reason = None if status == "OK" else epistemic_state.get("reason", "EPISTEMIC_VOID")
    if status == "NULL":
        p_timeout = probability.p_timeout_frac
        p_up = p_down = (1.0 - p_timeout) / 2.0
        up_user = down_user = 0.5
    else:
        p_up = probability.p_up_frac
        p_down = probability.p_down_frac
        p_timeout = probability.p_timeout_frac
        non_timeout_mass = p_up + p_down
        if non_timeout_mass <= 0.0:
            up_user = down_user = 0.5
        else:
            up_user = p_up / non_timeout_mass
            down_user = p_down / non_timeout_mass
    horizon = {
        "p_up_frac": p_up,
        "p_down_frac": p_down,
        "p_timeout_frac": p_timeout,
        "p_up_user_norm_frac": up_user,
        "p_down_user_norm_frac": down_user,
        "confidence_frac": 0.0 if status == "NULL" else 0.5,
        "news_confidence_adj_frac": 0.0,
        "status": status,
        "null_reason": null_reason,
    }
    return {
        "schema_version": PROBABILITY_SCHEMA_VERSION,
        "horizons": {
            "H_primary": horizon,
            "H_extended": {
                **horizon,
                "confidence_frac": horizon["confidence_frac"]
                * DEFAULT_PHASE1A.probability_extended_confidence_multiplier,
            },
        },
        "calibration_status": DEFAULT_PHASE1A.calibration_status,
        "null_reason": null_reason,
    }


def build_distributional_v2_timeout_state(
    probability: DistributionalV2Probability,
    *,
    timeframe: str,
) -> dict:
    """The ``horizon_timeout_state`` of v1's branch, with v2's own scale facts.

    v2 has no single-bar EWMA scale, so ``sigma_bar`` is absent. It exposes instead what defines its
    six-bar scale: the calendar-profile mean over the horizon and, on 1H, the UTC session whose
    shape table was used.
    """

    return {
        "status": "OK",
        "method": CANDIDATE_NAME,
        "p_timeout_frac": probability.p_timeout_frac,
        "timeout_is_directional": False,
        "timeframe": timeframe,
        "sigma_h": probability.sigma_h,
        "band_frac": probability.band_frac,
        "profile_mean": probability.profile_mean,
        "session": probability.session,
        "candles_used": probability.candles_used,
    }
