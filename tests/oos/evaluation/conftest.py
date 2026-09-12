"""Synthetic section 5A evidence. No live data, ever."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

T0 = datetime(2026, 8, 21, 4, 0, 0, tzinfo=UTC)
T_CLOSE = datetime(2026, 9, 12, 4, 0, 0, tzinfo=UTC)
T_FREEZE = datetime(2026, 8, 20, 11, 35, 56, tzinfo=UTC)

UNSET = object()
"""Sentinel: distinguishes "not overridden" from an explicit unresolved ``None``."""


def evidence_row(
    reference_close_utc: datetime,
    *,
    symbol: str = "BTC/USDT",
    timeframe: str = "4H",
    candidate_up: float = 0.60,
    baseline_up: float = 0.50,
    label: str | None = "UP",
    baseline_label: Any = UNSET,
    candidate_label: Any = UNSET,
    horizon_end_utc: datetime | None = None,
    with_probabilities: bool = True,
) -> dict[str, Any]:
    """One flat paired-evidence row, exactly as the repository projection emits it."""

    identifier = f"oosb-{abs(hash((reference_close_utc, symbol, timeframe))):032x}"[:37]
    horizon_end = horizon_end_utc or (reference_close_utc + timedelta(hours=24))
    row: dict[str, Any] = {
        "run_id": identifier,
        "normalized_symbol": symbol,
        "timeframe": timeframe,
        "reference_close_utc": reference_close_utc,
    }
    labels = {
        "baseline": label if baseline_label is UNSET else baseline_label,
        "candidate": label if candidate_label is UNSET else candidate_label,
    }
    tops = {"baseline": baseline_up, "candidate": candidate_up}
    for arm in ("baseline", "candidate"):
        row[f"{arm}_prediction_id"] = f"{identifier}:{timeframe}:{arm.upper()}"
        row[f"{arm}_predicted_at_utc"] = reference_close_utc
        row[f"{arm}_horizon_end_utc"] = horizon_end
        row[f"{arm}_prediction_origin"] = "SCHEDULED_SHADOW_EVIDENCE"
        row[f"{arm}_realized_label"] = labels[arm]
        if with_probabilities:
            top = tops[arm]
            remainder = 1.0 - top
            row[f"{arm}_p_up_frac"] = top
            row[f"{arm}_p_down_frac"] = remainder * 0.6
            row[f"{arm}_p_timeout_frac"] = remainder * 0.4
    return row


def daily_4h_evidence(
    *,
    candidate_ups: list[float] | None = None,
    symbol: str = "BTC/USDT",
    days: int = 22,
) -> list[dict[str, Any]]:
    """One pair per day at the T0 hour.

    This placement populates every window at all three coarsenings for 4H: c=1 takes
    the even days (11 windows), c=2 every third day (7), c=4 every fifth day (5) — the
    contract's own k_1/k_2/k_4.  Slight variation in candidate confidence is required
    because a zero-dispersion sample makes A1 fail closed by design.
    """

    # Length 7 is deliberate: coprime with the 2-, 3- and 5-day strides that the c=1,
    # c=2 and c=4 lattices sample, so no coarsening aliases onto a constant sample.
    # A 5-long cycle makes every c=4 window identical, s == 0, and A1 fail closed.
    ups = candidate_ups or [0.60, 0.61, 0.59, 0.62, 0.58, 0.63, 0.575]
    return [
        evidence_row(
            T0 + timedelta(days=day),
            symbol=symbol,
            candidate_up=ups[day % len(ups)],
        )
        for day in range(days)
    ]
