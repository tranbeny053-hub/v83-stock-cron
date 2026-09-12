"""Tier-1 and Tier-2 admission for the section 5A holdout.

Contract: ``V1_QUANT_CONTRACT.md`` §5A.4.
Holdout membership: ``docs/SECTION_5A_EVALUATION_PREREGISTRATION.md`` §9.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

UNRESOLVED_BASELINE = "UNRESOLVED_BASELINE"
UNRESOLVED_CANDIDATE = "UNRESOLVED_CANDIDATE"
LABEL_DISAGREEMENT = "LABEL_DISAGREEMENT"
REJECTION_CAUSES = (UNRESOLVED_BASELINE, UNRESOLVED_CANDIDATE, LABEL_DISAGREEMENT)


@dataclass(frozen=True)
class AdmissionResult:
    """What survived admission, and exactly what did not, and why."""

    admitted: tuple[dict[str, Any], ...] = ()
    tier1_in_holdout: int = 0
    tier1_outside_holdout: int = 0
    rejections: Mapping[str, int] = field(default_factory=dict)
    resolved_after_close: int = 0

    @property
    def admitted_count(self) -> int:
        return len(self.admitted)


def within_holdout(
    reference_close_utc: datetime, t0: datetime, t_close: datetime
) -> bool:
    """Return whether a close lies in the half-open holdout ``[T0, T_close)``.

    Half-open on ``reference_close_utc``, matching §5A.6's assignment rule.  This is
    load-bearing: the collector kept running past ``T_close``, and those rows must not
    enter B1, whose population is "the whole holdout" rather than the lattice.
    """

    return t0 <= reference_close_utc < t_close


def admit(
    evidence: Iterable[Mapping[str, Any]],
    *,
    t0: datetime,
    t_close: datetime,
) -> AdmissionResult:
    """Apply the holdout bound, then Tier-2 admission, counting every rejection."""

    admitted: list[dict[str, Any]] = []
    rejections = dict.fromkeys(REJECTION_CAUSES, 0)
    in_holdout = 0
    outside_holdout = 0
    resolved_after_close = 0

    for row in evidence:
        reference_close = row.get("reference_close_utc")
        if not isinstance(reference_close, datetime):
            raise ValueError("evidence row lacks a datetime reference_close_utc")
        if not within_holdout(reference_close, t0, t_close):
            outside_holdout += 1
            continue
        in_holdout += 1

        baseline_label = row.get("baseline_realized_label")
        candidate_label = row.get("candidate_realized_label")
        if baseline_label is None:
            rejections[UNRESOLVED_BASELINE] += 1
            continue
        if candidate_label is None:
            rejections[UNRESOLVED_CANDIDATE] += 1
            continue
        if baseline_label != candidate_label:
            rejections[LABEL_DISAGREEMENT] += 1
            continue

        admitted.append(dict(row))
        if _resolved_after_close(row, t_close):
            resolved_after_close += 1

    return AdmissionResult(
        admitted=tuple(admitted),
        tier1_in_holdout=in_holdout,
        tier1_outside_holdout=outside_holdout,
        rejections=rejections,
        resolved_after_close=resolved_after_close,
    )


def realized_label(row: Mapping[str, Any]) -> str:
    """Return the agreed label of an admitted pair."""

    return str(row["baseline_realized_label"])


def _resolved_after_close(row: Mapping[str, Any], t_close: datetime) -> bool:
    """Whether either arm's horizon ended after the declared close.

    Reported as a §5A.10-style diagnostic (pre-registration §9); it gates nothing.
    Membership is deliberately fixed by ``reference_close_utc`` alone, so that the
    analysed population cannot depend on when the resolver happened to run.
    """

    for arm in ("baseline", "candidate"):
        horizon_end = row.get(f"{arm}_horizon_end_utc")
        if isinstance(horizon_end, datetime) and horizon_end > t_close:
            return True
    return False
