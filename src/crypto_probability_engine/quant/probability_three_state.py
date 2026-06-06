"""Three-state probability baseline with invariant enforcement."""

from __future__ import annotations

from math import tanh

from crypto_probability_engine.config.defaults import DEFAULT_PHASE1A
from crypto_probability_engine.utils.invariants import validate_probability_triplet


def _directional_split(net_signal: float, timeout_frac: float) -> tuple[float, float]:
    directional_mass = max(0.0, 1.0 - timeout_frac)
    tilt = tanh(net_signal * DEFAULT_PHASE1A.probability_signal_sensitivity)
    up = directional_mass * (
        DEFAULT_PHASE1A.probability_tilt_midpoint
        + DEFAULT_PHASE1A.probability_tilt_scale * tilt
    )
    down = directional_mass - up
    return up, down


def _user_norm(up: float, down: float) -> tuple[float, float]:
    total = up + down
    if total <= 0:
        return 0.5, 0.5
    return up / total, down / total


def compute_probability_state(
    *,
    net_signal: float,
    timeout_frac: float,
    epistemic_state: dict,
) -> dict:
    p_timeout = min(
        max(timeout_frac, DEFAULT_PHASE1A.timeout_min_frac),
        DEFAULT_PHASE1A.timeout_max_frac,
    )
    up, down = _directional_split(net_signal, p_timeout)
    if epistemic_state.get("sufficiency_level") != "SUFFICIENT":
        directional = 1.0 - p_timeout
        up = directional / 2.0
        down = directional / 2.0
    total = up + down + p_timeout
    up = up / total
    down = down / total
    p_timeout = p_timeout / total
    validate_probability_triplet(up, down, p_timeout)
    up_user, down_user = _user_norm(up, down)
    status = "OK" if epistemic_state.get("action") == "ALLOW" else "NULL"
    null_reason = None if status == "OK" else epistemic_state.get("reason", "EPISTEMIC_VOID")
    horizon = {
        "p_up_frac": up,
        "p_down_frac": down,
        "p_timeout_frac": p_timeout,
        "p_up_user_norm_frac": up_user,
        "p_down_user_norm_frac": down_user,
        "confidence_frac": 0.0 if status == "NULL" else 0.5,
        "news_confidence_adj_frac": 0.0,
        "status": status,
        "null_reason": null_reason,
    }
    return {
        "schema_version": "1.1-crypto-probability",
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
