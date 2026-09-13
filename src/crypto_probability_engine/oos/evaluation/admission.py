"""Scope, holdout, Tier-1 and Tier-2 admission for the section 5A evaluation.

Contract: ``V1_QUANT_CONTRACT.md`` §5A.1 (scope), §5A.4 (tiers).
Holdout membership: ``docs/SECTION_5A_EVALUATION_PREREGISTRATION.md`` §9.

Order is fixed and is itself a rule: SCOPE, then HOLDOUT, then TIER-2. A row outside the
tranche-1 scope never reaches a statistic, an attainability verdict, a diagnostic or an identity
(finding V807-F1). Every exclusion is counted, per timeframe and per symbol, so nothing is
silently dropped.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from crypto_probability_engine.oos.evaluation.scope import in_tranche_scope

UNRESOLVED_BASELINE = "UNRESOLVED_BASELINE"
UNRESOLVED_CANDIDATE = "UNRESOLVED_CANDIDATE"
LABEL_DISAGREEMENT = "LABEL_DISAGREEMENT"
REJECTION_CAUSES = (UNRESOLVED_BASELINE, UNRESOLVED_CANDIDATE, LABEL_DISAGREEMENT)

# (timeframe, normalized_symbol) — the key every per-scope count is attributed to.
Cell = tuple[str, str]


@dataclass(frozen=True)
class AdmissionResult:
    """What survived admission, and exactly what did not, and why — globally and per cell."""

    admitted: tuple[dict[str, Any], ...] = ()
    tier1_in_holdout: int = 0
    tier1_outside_holdout: int = 0
    tier1_out_of_scope: int = 0
    rejections: Mapping[str, int] = field(default_factory=dict)
    resolved_after_close: int = 0
    # Per-cell attribution, so §5A.10-style counts are reportable per timeframe AND per cell.
    in_holdout_cells: tuple[Cell, ...] = ()
    outside_holdout_cells: tuple[Cell, ...] = ()
    out_of_scope_cells: tuple[Cell, ...] = ()
    rejected_cells: tuple[tuple[str, str, str], ...] = ()  # (timeframe, symbol, cause)

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
    """Apply scope, then the holdout bound, then Tier-2 admission, counting every exclusion."""

    admitted: list[dict[str, Any]] = []
    rejections = dict.fromkeys(REJECTION_CAUSES, 0)
    in_holdout: list[Cell] = []
    outside: list[Cell] = []
    out_of_scope: list[Cell] = []
    rejected: list[tuple[str, str, str]] = []
    resolved_after_close = 0

    for row in evidence:
        cell = (str(row.get("timeframe")), str(row.get("normalized_symbol")))

        # SCOPE FIRST (V807-F1): an out-of-tranche row can never influence anything.
        if not in_tranche_scope(row.get("normalized_symbol"), row.get("timeframe")):
            out_of_scope.append(cell)
            continue

        reference_close = row.get("reference_close_utc")
        if not isinstance(reference_close, datetime):
            raise ValueError("evidence row lacks a datetime reference_close_utc")
        if not within_holdout(reference_close, t0, t_close):
            outside.append(cell)
            continue
        in_holdout.append(cell)

        baseline_label = row.get("baseline_realized_label")
        candidate_label = row.get("candidate_realized_label")
        cause = None
        if baseline_label is None:
            cause = UNRESOLVED_BASELINE
        elif candidate_label is None:
            cause = UNRESOLVED_CANDIDATE
        elif baseline_label != candidate_label:
            cause = LABEL_DISAGREEMENT
        if cause is not None:
            rejections[cause] += 1
            rejected.append((cell[0], cell[1], cause))
            continue

        admitted.append(dict(row))
        if resolved_after_close_row(row, t_close):
            resolved_after_close += 1

    return AdmissionResult(
        admitted=tuple(admitted),
        tier1_in_holdout=len(in_holdout),
        tier1_outside_holdout=len(outside),
        tier1_out_of_scope=len(out_of_scope),
        rejections=rejections,
        resolved_after_close=resolved_after_close,
        in_holdout_cells=tuple(in_holdout),
        outside_holdout_cells=tuple(outside),
        out_of_scope_cells=tuple(out_of_scope),
        rejected_cells=tuple(rejected),
    )


def realized_label(row: Mapping[str, Any]) -> str:
    """Return the agreed label of an admitted pair."""

    return str(row["baseline_realized_label"])


def resolved_after_close_row(row: Mapping[str, Any], t_close: datetime) -> bool:
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
