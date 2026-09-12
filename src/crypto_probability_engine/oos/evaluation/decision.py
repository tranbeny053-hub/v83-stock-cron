"""The section 5A acceptance decision: A, B, C and the per-timeframe states.

Contract: ``V1_QUANT_CONTRACT.md`` §5A.7 and §5A.8.
Edge cases fixed in advance: ``docs/SECTION_5A_EVALUATION_PREREGISTRATION.md`` §5, §10.

Nothing here invents an acceptance rule.  Every case §5A leaves undefined is resolved
fail-closed, so no resolution can make PASS easier to reach than the contract allows.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from crypto_probability_engine.oos.evaluation.admission import (
    AdmissionResult,
    realized_label,
)
from crypto_probability_engine.oos.evaluation.lattice import (
    COARSENINGS,
    assign_window_index,
    window_count,
)
from crypto_probability_engine.oos.evaluation.scoring import ece, per_row_d, window_mean
from crypto_probability_engine.oos.evaluation.stats_kernel import (
    sign_test_one_sided_p,
    student_t_lower_tail_cdf,
)
from crypto_probability_engine.utils.invariants import validate_probability_triplet

# §5A.0: a CONVENTION, carrying no probabilistic claim and no error rate.
BOUNDARY_CONVENTION = 0.05

ORDERED_COARSENINGS = tuple(sorted(COARSENINGS))
TRANCHE_1_SYMBOLS = ("BTC/USDT", "ETH/USDT")

PASS = "PASS"
A_AND_B_HELD_FAIL_UNVERIFIED = "A_AND_B_HELD_FAIL_UNVERIFIED"
NOT_PASS = "NOT_PASS"
FAIL = "FAIL"

# OWNER RULING (2026-09-12), closing verification finding F1.
#
# §5A.7 defines PASS as "A and B hold with no FAIL". Three of the four FAIL predicates
# cannot be reconstructed from the ledger, so "no FAIL" is UNVERIFIED, not verified.
# Treating unknown as clean would make PASS easier to reach than the contract allows.
#
# The contract token PASS is therefore reserved for A and B holding AND every FAIL
# predicate being AFFIRMATIVELY established as clean. When any required predicate is
# unverified the terminal state is A_AND_B_HELD_FAIL_UNVERIFIED, which authorizes
# NOTHING. It is not a lesser PASS; it is a different, honest statement.

OBSERVABLE_PASS = "OBSERVABLE_PASS"
OBSERVABLE_BREACH = "OBSERVABLE_BREACH"
NOT_OBSERVABLE = "NOT_OBSERVABLE_FROM_PERSISTED_STATE"


@dataclass(frozen=True)
class FailCheck:
    name: str
    status: str
    detail: str = ""


@dataclass(frozen=True)
class CoarseningResult:
    coarsening: int
    k_pre_drop: int
    usable_windows: int
    dropped_windows: int
    a1_holds: bool
    a1_boundary_statistic: float | None
    a2_holds: bool
    a2_boundary_statistic: float | None
    a2_negative_windows: int

    @property
    def holds(self) -> bool:
        return self.a1_holds and self.a2_holds


@dataclass(frozen=True)
class SymbolResult:
    symbol: str
    covered: bool
    n_worse: int
    n_better: int

    @property
    def holds(self) -> bool:
        return self.covered and self.n_worse <= self.n_better


@dataclass(frozen=True)
class TimeframeResult:
    timeframe: str
    state: str
    reason: str
    admitted_pairs: int
    coarsenings: tuple[CoarseningResult, ...] = ()
    a_holds: bool = False
    b1_holds: bool = False
    b1_ece_baseline: float | None = None
    b1_ece_candidate: float | None = None
    b2_holds: bool = False
    b2_n_worse: int = 0
    b2_n_better: int = 0
    b_holds: bool = False
    per_symbol: Mapping[str, SymbolResult] = field(default_factory=dict)
    fail_checks: tuple[FailCheck, ...] = ()
    authorized_cells: tuple[str, ...] = ()


def evaluate_timeframe(
    timeframe: str,
    admission: AdmissionResult,
    *,
    t0: datetime,
    t_close: datetime,
) -> TimeframeResult:
    """Return the §5A decision for one timeframe."""

    rows = [row for row in admission.admitted if row.get("timeframe") == timeframe]
    fail_checks = _fail_checks(rows)
    breached = [check for check in fail_checks if check.status == OBSERVABLE_BREACH]
    if breached:
        return TimeframeResult(
            timeframe=timeframe,
            state=FAIL,
            reason="; ".join(f"{check.name}: {check.detail}" for check in breached),
            admitted_pairs=len(rows),
            fail_checks=fail_checks,
        )

    # Pre-registration §10: decided BEFORE A or B, so B can never affirm on no evidence.
    if not rows:
        return TimeframeResult(
            timeframe=timeframe,
            state=NOT_PASS,
            reason="no Tier-2 admitted pairs in this timeframe",
            admitted_pairs=0,
            fail_checks=fail_checks,
        )

    coarsenings = tuple(
        _evaluate_coarsening(timeframe, rows, c, t0=t0, t_close=t_close)
        for c in ORDERED_COARSENINGS
    )
    a_holds = all(result.holds for result in coarsenings)

    baseline_rows = [_calibration_row(row, "baseline") for row in rows]
    candidate_rows = [_calibration_row(row, "candidate") for row in rows]
    b1_baseline = ece(baseline_rows)
    b1_candidate = ece(candidate_rows)
    b1_holds = b1_candidate <= b1_baseline

    b2_worse, b2_better = _b2_tally(timeframe, rows, t0=t0, t_close=t_close)
    b2_holds = b2_worse <= b2_better
    b_holds = b1_holds and b2_holds

    per_symbol = {
        symbol: _symbol_result(symbol, timeframe, rows, t0=t0, t_close=t_close)
        for symbol in TRANCHE_1_SYMBOLS
    }

    unverified = [
        check.name for check in fail_checks if check.status == NOT_OBSERVABLE
    ]
    if not (a_holds and b_holds):
        state = NOT_PASS
        reason = _not_pass_reason(a_holds, b1_holds, b2_holds)
    elif unverified:
        state = A_AND_B_HELD_FAIL_UNVERIFIED
        reason = (
            "A and B hold and the probability invariant shows no detected breach, but "
            "§5A's no-FAIL condition is NOT established: "
            + ", ".join(unverified)
            + " cannot be reconstructed from the persisted ledger. This authorizes nothing."
        )
    else:
        state = PASS
        reason = "A and B hold and every FAIL predicate is affirmatively established clean"

    # AUTHORIZED requires the contract PASS, never the unverified state.
    authorized = (
        tuple(
            f"{symbol}|{timeframe}"
            for symbol in TRANCHE_1_SYMBOLS
            if per_symbol[symbol].holds
        )
        if state == PASS
        else ()
    )

    return TimeframeResult(
        timeframe=timeframe,
        state=state,
        reason=reason,
        admitted_pairs=len(rows),
        coarsenings=coarsenings,
        a_holds=a_holds,
        b1_holds=b1_holds,
        b1_ece_baseline=b1_baseline,
        b1_ece_candidate=b1_candidate,
        b2_holds=b2_holds,
        b2_n_worse=b2_worse,
        b2_n_better=b2_better,
        b_holds=b_holds,
        per_symbol=per_symbol,
        fail_checks=fail_checks,
        authorized_cells=authorized,
    )


def a1(window_means: Sequence[float]) -> tuple[bool, float | None]:
    """One-sided t-test that the mean of window means is below zero.

    Fails closed with fewer than two windows (no dispersion estimate) and with zero or
    non-finite dispersion (the statistic is undefined).  A strict guard may only err
    toward NOT PASS.
    """

    k = len(window_means)
    if k < 2:
        return False, None
    mean = math.fsum(window_means) / k
    variance = math.fsum((value - mean) ** 2 for value in window_means) / (k - 1)
    stdev = math.sqrt(variance)
    if stdev <= 0.0 or not math.isfinite(stdev):
        return False, None
    statistic = mean / (stdev / math.sqrt(k))
    boundary = student_t_lower_tail_cdf(statistic, k - 1)
    return boundary <= BOUNDARY_CONVENTION, boundary


def a2(window_means: Sequence[float]) -> tuple[bool, float | None, int]:
    """One-sided sign test.  Ties are non-negative and REMAIN in ``k``."""

    k = len(window_means)
    n_neg = sum(1 for value in window_means if value < 0.0)
    boundary = sign_test_one_sided_p(n_neg, k)
    return boundary <= BOUNDARY_CONVENTION, boundary, n_neg


def _evaluate_coarsening(
    timeframe: str,
    rows: Sequence[Mapping[str, Any]],
    c: int,
    *,
    t0: datetime,
    t_close: datetime,
) -> CoarseningResult:
    means = _window_means(timeframe, rows, c, t0=t0, t_close=t_close)
    k_pre_drop = window_count(timeframe, c, t0, t_close)
    a1_holds, a1_boundary = a1(means)
    a2_holds, a2_boundary, n_neg = a2(means)
    return CoarseningResult(
        coarsening=c,
        k_pre_drop=k_pre_drop,
        usable_windows=len(means),
        dropped_windows=max(0, k_pre_drop - len(means)),
        a1_holds=a1_holds,
        a1_boundary_statistic=a1_boundary,
        a2_holds=a2_holds,
        a2_boundary_statistic=a2_boundary,
        a2_negative_windows=n_neg,
    )


def _grouped_by_window(
    timeframe: str,
    rows: Sequence[Mapping[str, Any]],
    c: int,
    *,
    t0: datetime,
    t_close: datetime,
) -> dict[int, list[Mapping[str, Any]]]:
    grouped: dict[int, list[Mapping[str, Any]]] = {}
    for row in rows:
        index = assign_window_index(
            row["reference_close_utc"], timeframe, c, t0, t_close
        )
        if index is None:
            continue
        grouped.setdefault(index, []).append(row)
    return grouped


def _window_means(
    timeframe: str,
    rows: Sequence[Mapping[str, Any]],
    c: int,
    *,
    t0: datetime,
    t_close: datetime,
) -> list[float]:
    grouped = _grouped_by_window(timeframe, rows, c, t0=t0, t_close=t_close)
    return [
        window_mean([_row_d(row) for row in grouped[index]])
        for index in sorted(grouped)
    ]


def _b2_tally(
    timeframe: str,
    rows: Sequence[Mapping[str, Any]],
    *,
    t0: datetime,
    t_close: datetime,
) -> tuple[int, int]:
    grouped = _grouped_by_window(timeframe, rows, 1, t0=t0, t_close=t_close)
    worse = better = 0
    for index in sorted(grouped):
        window_rows = grouped[index]
        baseline = ece([_calibration_row(row, "baseline") for row in window_rows])
        candidate = ece([_calibration_row(row, "candidate") for row in window_rows])
        if candidate >= baseline:
            worse += 1
        else:
            better += 1
    return worse, better


def _symbol_result(
    symbol: str,
    timeframe: str,
    rows: Sequence[Mapping[str, Any]],
    *,
    t0: datetime,
    t_close: datetime,
) -> SymbolResult:
    symbol_rows = [row for row in rows if row.get("normalized_symbol") == symbol]
    grouped = _grouped_by_window(timeframe, symbol_rows, 1, t0=t0, t_close=t_close)
    if not grouped:
        return SymbolResult(symbol=symbol, covered=False, n_worse=0, n_better=0)
    worse = better = 0
    for index in sorted(grouped):
        mean = window_mean([_row_d(row) for row in grouped[index]])
        if mean >= 0.0:
            worse += 1
        else:
            better += 1
    return SymbolResult(symbol=symbol, covered=True, n_worse=worse, n_better=better)


def _row_d(row: Mapping[str, Any]) -> float:
    return per_row_d(
        _probabilities(row, "candidate"),
        _probabilities(row, "baseline"),
        realized_label(row),
    )


def _probabilities(row: Mapping[str, Any], arm: str) -> dict[str, float]:
    try:
        return {
            "UP": float(row[f"{arm}_p_up_frac"]),
            "DOWN": float(row[f"{arm}_p_down_frac"]),
            "TIMEOUT": float(row[f"{arm}_p_timeout_frac"]),
        }
    except KeyError as exc:  # pragma: no cover - guarded by the readiness boundary
        raise KeyError(
            "evidence row carries no probabilities; a readiness projection cannot be scored"
        ) from exc


def _calibration_row(row: Mapping[str, Any], arm: str) -> dict[str, Any]:
    probabilities = _probabilities(row, arm)
    return {
        "p_up_frac": probabilities["UP"],
        "p_down_frac": probabilities["DOWN"],
        "p_timeout_frac": probabilities["TIMEOUT"],
        "realized_label": realized_label(row),
    }


def _fail_checks(rows: Sequence[Mapping[str, Any]]) -> tuple[FailCheck, ...]:
    """Report FAIL by observability, never by assumption (pre-registration §6)."""

    breaches: list[str] = []
    for row in rows:
        for arm in ("baseline", "candidate"):
            probabilities = _probabilities(row, arm)
            try:
                validate_probability_triplet(
                    probabilities["UP"],
                    probabilities["DOWN"],
                    probabilities["TIMEOUT"],
                )
            except ValueError as exc:
                breaches.append(f"{row.get(f'{arm}_prediction_id')}: {exc}")

    invariant = (
        FailCheck(
            name="probability_triplet_sums_to_one",
            status=OBSERVABLE_BREACH,
            detail="; ".join(breaches[:5]),
        )
        if breaches
        else FailCheck(
            name="probability_triplet_sums_to_one",
            status=OBSERVABLE_PASS,
            detail=f"{len(rows)} admitted pairs, both arms, tolerance 1e-6",
        )
    )

    unobservable_detail = (
        "gates.composite.apply_composite_gates requires liquidity, tail-risk, execution, "
        "provider and score state plus shelter_mode and kill_switch, none of which is "
        "persisted on the prediction row, so the gate decision cannot be recomputed from "
        "the ledger. No predicate is invented in its place."
    )
    return (
        invariant,
        FailCheck("hard_gate_not_overridden_by_score_or_news", NOT_OBSERVABLE, unobservable_detail),
        FailCheck("gated_when_evidence_is_thin", NOT_OBSERVABLE, unobservable_detail),
        FailCheck("no_sentiment_only_action", NOT_OBSERVABLE, unobservable_detail),
    )


def _not_pass_reason(a_holds: bool, b1_holds: bool, b2_holds: bool) -> str:
    unmet = []
    if not a_holds:
        unmet.append("A")
    if not b1_holds:
        unmet.append("B1")
    if not b2_holds:
        unmet.append("B2")
    return "requirement(s) not met: " + ", ".join(unmet)
