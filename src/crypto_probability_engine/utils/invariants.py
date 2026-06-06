"""Contract invariants shared by schemas and tests."""

from collections.abc import Mapping

PROBABILITY_TOLERANCE = 1e-6


def validate_probability_triplet(
    p_up_frac: float,
    p_down_frac: float,
    p_timeout_frac: float,
    *,
    tolerance: float = PROBABILITY_TOLERANCE,
) -> None:
    values = (p_up_frac, p_down_frac, p_timeout_frac)
    if any(value < 0.0 or value > 1.0 for value in values):
        raise ValueError("probability fractions must be bounded [0, 1]")
    if abs(sum(values) - 1.0) > tolerance:
        raise ValueError("p_up_frac + p_down_frac + p_timeout_frac must equal 1.0")


def validate_probability_state(probability_state: Mapping[str, object]) -> None:
    horizons = probability_state.get("horizons")
    if not isinstance(horizons, Mapping):
        raise ValueError("probability_state.horizons must be an object")
    for horizon_name, horizon in horizons.items():
        if not isinstance(horizon, Mapping):
            raise ValueError(f"{horizon_name} must be an object")
        validate_probability_triplet(
            float(horizon["p_up_frac"]),
            float(horizon["p_down_frac"]),
            float(horizon["p_timeout_frac"]),
        )
