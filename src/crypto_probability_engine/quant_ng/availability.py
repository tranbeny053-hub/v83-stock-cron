"""PROPOSAL, UNWIRED; the owner's OD-NG-6 (2026-10-22), and plan §F.3 reasons."""

from enum import StrEnum


class UnavailableTarget(StrEnum):
    TARGET_NOT_RESOLVABLE_1M = "TARGET_NOT_RESOLVABLE_1M"
    NOT_MODELED = "NOT_MODELED"


def target_unavailable_reason(timeframe: str, horizon: str) -> UnavailableTarget | None:
    """Return a stable unavailable reason for targets that are not modeled."""

    if horizon not in {"H_primary", "H_extended"}:
        raise ValueError(f"Unsupported horizon {horizon!r}")
    if timeframe == "1M":
        return UnavailableTarget.TARGET_NOT_RESOLVABLE_1M
    if horizon == "H_extended":
        return UnavailableTarget.NOT_MODELED
    return None


# OD-NG-6 ruling: “24-bar deferred not canceled.”
H24_LABEL_STATUS = "DEFERRED_NOT_CANCELLED"
