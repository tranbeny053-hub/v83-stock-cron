"""Section 5A.10 diagnostics: reported with EVERY outcome, gating nothing.

Contract: ``V1_QUANT_CONTRACT.md`` §5A.10.  Declared there so the list cannot be chosen
after seeing results.  Nothing in this module may influence a verdict.

Two rules govern every value emitted here:

- **Per timeframe AND per cell.** §5A.10 says both, so the timeframe block and each cell block
  carry the same complete set (finding G6.1).
- **Absence is reported as absence.** A quantity that was not measured is ``UNMEASURED`` or
  ``None``, never ``0``. A zero that nothing measured is a fabricated number (G6.2, G11).
- **Every tranche cell is materialized, even when empty** (V807-F6). An absent cell is
  indistinguishable from a forgotten one; a present cell with zero pairs is a measurement.

WHY A DECLARED SCHEMA. Completeness was defeated in three consecutive rounds (F7, G6, V807-F6)
because §5A.10 lived only in prose. ``REQUIRED_KEYS_PER_SCOPE`` is the machine-checked
declaration: every timeframe block and every cell block must carry exactly these keys, in both
modes, for populated and empty evidence.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from statistics import median
from typing import Any

from crypto_probability_engine.oos.evaluation.admission import (
    REJECTION_CAUSES,
    AdmissionResult,
    realized_label,
    resolved_after_close_row,
)
from crypto_probability_engine.oos.evaluation.lattice import (
    assign_window_index,
    window_count,
)
from crypto_probability_engine.oos.evaluation.scope import TRANCHE_1_SYMBOLS

UNMEASURED = "UNMEASURED"
"""Reported in place of a quantity that no ledger measured. ``missed_attempts`` is the
standing case: collector attempt outcomes live in workflow run logs, not the database."""

ORDERED_COARSENINGS = (1, 2, 4)
OUTCOME_LABELS = ("UP", "DOWN", "TIMEOUT")

# §5A.10, per timeframe AND per cell, plus the per-scope counts pre-registration §9 requires.
REQUIRED_KEYS_PER_SCOPE = frozenset(
    {
        "t_freeze",
        "t0",
        "activation_gap_seconds",
        "admitted_pairs",
        "k_pre_drop",
        "usable_windows",
        "dropped_windows",
        "missed_attempts",
        "missed_attempts_basis",
        "realized_label_distribution",
        "regime_distribution",
        "trend_mtf_distribution",
        "realized_vol_summary",
        "volume_anomaly_summary",
        "first_reference_close_utc",
        "last_reference_close_utc",
        "realised_span_seconds",
        "admitted_resolved_after_t_close",
        "tier1_in_holdout",
        "tier1_outside_holdout",
        "tier2_rejections",
    }
)

_MISSED_ATTEMPTS_ABSENT_BASIS = (
    "not derivable from the persisted ledger; collector attempt outcomes live in workflow run "
    "logs. Reported as absent rather than as zero."
)


def numeric_summary(values: Sequence[Any]) -> dict[str, float | int | None]:
    """Median and IQR of the finite numeric values, or ``None`` when there are none.

    ``Decimal`` counts as numeric: a snapshot read back from disk or from Postgres carries
    exact decimals, and the summary must be the same whether it was computed at consumption
    or at recomputation.
    """

    numbers = sorted(
        float(value)
        for value in values
        if isinstance(value, (int, float, Decimal))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )
    if not numbers:
        return {"median": None, "p25": None, "p75": None, "iqr": None, "count": 0}
    p25 = _percentile(numbers, 0.25)
    p75 = _percentile(numbers, 0.75)
    return {
        "median": median(numbers),
        "p25": p25,
        "p75": p75,
        "iqr": p75 - p25,
        "count": len(numbers),
    }


def distribution(values: Sequence[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = "UNKNOWN" if value is None else str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def label_distribution(labels: Sequence[str]) -> dict[str, int]:
    """Every declared outcome label, including those with a zero count.

    Dropping a zero-count label would hide that a label never occurred — which is exactly the
    TIMEOUT-heavy (or TIMEOUT-free) composition §5A.10 exists to expose.
    """

    counts = dict.fromkeys(OUTCOME_LABELS, 0)
    for label in labels:
        if label not in counts:
            raise ValueError(f"undeclared realized label in admitted evidence: {label!r}")
        counts[label] += 1
    return counts


def build(
    admission: AdmissionResult,
    *,
    t0: datetime,
    t_close: datetime,
    t_freeze: datetime,
    timeframes: Sequence[str],
    feature_rows: Sequence[Mapping[str, Any]] = (),
    origin_anomalies: int | Decimal | None = None,
    missed_attempts: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Assemble the pre-declared diagnostic block."""

    features_by_prediction = {str(row.get("prediction_id")): row for row in feature_rows}
    contract = _contract_fields(t0=t0, t_freeze=t_freeze)
    per_timeframe = {
        timeframe: _block(
            timeframe,
            None,
            admission,
            t0=t0,
            t_close=t_close,
            contract=contract,
            features_by_prediction=features_by_prediction,
            missed_attempts=(
                UNMEASURED
                if missed_attempts is None or timeframe not in missed_attempts
                else missed_attempts[timeframe]
            ),
            with_cells=True,
        )
        for timeframe in timeframes
    }
    return {
        **contract,
        "t_close": t_close.isoformat(),
        "tier1_in_holdout": admission.tier1_in_holdout,
        "tier1_outside_holdout": admission.tier1_outside_holdout,
        # Out-of-scope rows belong to no tranche cell, so they are reported globally with a
        # breakdown, never folded silently into zero (V807-F1).
        "tier1_out_of_scope": admission.tier1_out_of_scope,
        "out_of_scope_breakdown": _cell_counts(admission.out_of_scope_cells),
        "tier2_admitted": admission.admitted_count,
        "tier2_rejections": dict(admission.rejections),
        "admitted_resolved_after_t_close": admission.resolved_after_close,
        "origin_anomalies": UNMEASURED if origin_anomalies is None else int(origin_anomalies),
        "per_timeframe": per_timeframe,
        "gating": "NONE — diagnostics are reported with every outcome and gate nothing",
    }


def _contract_fields(*, t0: datetime, t_freeze: datetime) -> dict[str, Any]:
    return {
        "t_freeze": t_freeze.isoformat(),
        "t0": t0.isoformat(),
        "activation_gap_seconds": int((t0 - t_freeze).total_seconds()),
    }


def _block(
    timeframe: str,
    symbol: str | None,
    admission: AdmissionResult,
    *,
    t0: datetime,
    t_close: datetime,
    contract: Mapping[str, Any],
    features_by_prediction: Mapping[str, Mapping[str, Any]],
    missed_attempts: int | str,
    with_cells: bool,
) -> dict[str, Any]:
    """One diagnostic block. The timeframe and every cell use this same function, so the
    two scopes cannot drift apart in what they report. ``symbol=None`` is the timeframe scope."""

    def in_scope(tf: str, sym: str) -> bool:
        return tf == timeframe and (symbol is None or sym == symbol)

    rows = [
        row
        for row in admission.admitted
        if in_scope(str(row.get("timeframe")), str(row.get("normalized_symbol")))
    ]
    closes = sorted(row["reference_close_utc"] for row in rows)
    rejected_here = [cause for tf, sym, cause in admission.rejected_cells if in_scope(tf, sym)]
    features = _feature_values(rows, features_by_prediction)
    block: dict[str, Any] = {
        **contract,
        "admitted_pairs": len(rows),
        "k_pre_drop": {
            str(c): window_count(timeframe, c, t0, t_close) for c in ORDERED_COARSENINGS
        },
        "usable_windows": _window_counts(timeframe, rows, t0=t0, t_close=t_close),
        "dropped_windows": _dropped_counts(timeframe, rows, t0=t0, t_close=t_close),
        "missed_attempts": missed_attempts,
        "missed_attempts_basis": (
            _MISSED_ATTEMPTS_ABSENT_BASIS
            if missed_attempts == UNMEASURED
            else "supplied by an attempt ledger"
        ),
        "realized_label_distribution": label_distribution(
            [realized_label(row) for row in rows]
        ),
        "regime_distribution": distribution(features["regime"]),
        "trend_mtf_distribution": distribution(features["trend_mtf"]),
        "realized_vol_summary": numeric_summary(features["realized_vol"]),
        "volume_anomaly_summary": numeric_summary(features["volume_anomaly"]),
        "first_reference_close_utc": closes[0].isoformat() if closes else None,
        "last_reference_close_utc": closes[-1].isoformat() if closes else None,
        # No closes means no span was measured: None, not a fabricated zero (G6.2, G11).
        # A single close is a MEASURED zero-second span, and is reported as 0.
        "realised_span_seconds": (
            int((closes[-1] - closes[0]).total_seconds()) if closes else None
        ),
        "admitted_resolved_after_t_close": sum(
            1 for row in rows if resolved_after_close_row(row, t_close)
        ),
        "tier1_in_holdout": sum(1 for tf, sym in admission.in_holdout_cells if in_scope(tf, sym)),
        "tier1_outside_holdout": sum(
            1 for tf, sym in admission.outside_holdout_cells if in_scope(tf, sym)
        ),
        "tier2_rejections": {
            cause: rejected_here.count(cause) for cause in REJECTION_CAUSES
        },
    }
    if with_cells:
        # EVERY tranche cell, whether or not it holds evidence (V807-F6).
        block["per_symbol"] = {
            cell_symbol: _block(
                timeframe,
                cell_symbol,
                admission,
                t0=t0,
                t_close=t_close,
                contract=contract,
                features_by_prediction=features_by_prediction,
                # Attempts are not ledgered per cell either.
                missed_attempts=UNMEASURED,
                with_cells=False,
            )
            for cell_symbol in TRANCHE_1_SYMBOLS
        }
    return block


def _cell_counts(cells: Sequence[tuple[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for timeframe, symbol in cells:
        key = f"{timeframe}|{symbol}"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _feature_values(
    rows: Sequence[Mapping[str, Any]],
    features_by_prediction: Mapping[str, Mapping[str, Any]],
) -> dict[str, list[Any]]:
    values: dict[str, list[Any]] = {
        "regime": [],
        "realized_vol": [],
        "trend_mtf": [],
        "volume_anomaly": [],
    }
    for row in rows:
        snapshot = features_by_prediction.get(str(row.get("candidate_prediction_id")))
        for name in values:
            values[name].append(snapshot.get(name) if isinstance(snapshot, Mapping) else None)
    return values


def _usable(timeframe, rows, c, *, t0, t_close) -> int:
    indices = {
        assign_window_index(row["reference_close_utc"], timeframe, c, t0, t_close)
        for row in rows
    }
    indices.discard(None)
    return len(indices)


def _window_counts(timeframe, rows, *, t0, t_close) -> dict[str, int]:
    return {
        str(c): _usable(timeframe, rows, c, t0=t0, t_close=t_close)
        for c in ORDERED_COARSENINGS
    }


def _dropped_counts(timeframe, rows, *, t0, t_close) -> dict[str, int]:
    return {
        str(c): max(
            0,
            window_count(timeframe, c, t0, t_close)
            - _usable(timeframe, rows, c, t0=t0, t_close=t_close),
        )
        for c in ORDERED_COARSENINGS
    }


def _percentile(sorted_values: Sequence[float], fraction: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = fraction * (len(sorted_values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight
