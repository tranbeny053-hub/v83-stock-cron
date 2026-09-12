"""Section 5A.10 diagnostics: reported with EVERY outcome, gating nothing.

Contract: ``V1_QUANT_CONTRACT.md`` §5A.10.  Declared there so the list cannot be chosen
after seeing results.  Nothing in this module may influence a verdict.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from statistics import median
from typing import Any

from crypto_probability_engine.oos.evaluation.admission import (
    AdmissionResult,
    realized_label,
)
from crypto_probability_engine.oos.evaluation.lattice import (
    assign_window_index,
    window_count,
)

UNMEASURED = "UNMEASURED"
"""§5A.10 requires a missed-attempt count. It is NOT derivable from the persisted ledger:
the collector's attempt outcomes live in GitHub Actions run logs, not the database.
Reporting 0 would be a fabricated number, so the absence is reported as absence."""

ORDERED_COARSENINGS = (1, 2, 4)
OUTCOME_LABELS = ("UP", "DOWN", "TIMEOUT")


def numeric_summary(values: Sequence[Any]) -> dict[str, float | None]:
    """Median and IQR of the finite numeric values, or ``None`` when there are none."""

    numbers = sorted(
        float(value)
        for value in values
        if isinstance(value, (int, float)) and not isinstance(value, bool)
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


def build(
    admission: AdmissionResult,
    *,
    t0: datetime,
    t_close: datetime,
    t_freeze: datetime,
    timeframes: Sequence[str],
    feature_rows: Sequence[Mapping[str, Any]] = (),
    origin_anomalies: int = 0,
    missed_attempts: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Assemble the pre-declared diagnostic block."""

    features_by_prediction = {
        str(row.get("prediction_id")): row for row in feature_rows
    }
    per_timeframe = {
        timeframe: _timeframe_block(
            timeframe,
            [row for row in admission.admitted if row.get("timeframe") == timeframe],
            t0=t0,
            t_close=t_close,
            features_by_prediction=features_by_prediction,
            missed_attempts=(
                UNMEASURED
                if missed_attempts is None or timeframe not in missed_attempts
                else missed_attempts[timeframe]
            ),
        )
        for timeframe in timeframes
    }
    return {
        "t_freeze": t_freeze.isoformat(),
        "t0": t0.isoformat(),
        "t_close": t_close.isoformat(),
        "activation_gap_seconds": int((t0 - t_freeze).total_seconds()),
        "tier1_in_holdout": admission.tier1_in_holdout,
        "tier1_outside_holdout": admission.tier1_outside_holdout,
        "tier2_admitted": admission.admitted_count,
        "tier2_rejections": dict(admission.rejections),
        "admitted_resolved_after_t_close": admission.resolved_after_close,
        "origin_anomalies": origin_anomalies,
        "per_timeframe": per_timeframe,
        "gating": "NONE — diagnostics are reported with every outcome and gate nothing",
    }


def _timeframe_block(
    timeframe: str,
    rows: Sequence[Mapping[str, Any]],
    *,
    t0: datetime,
    t_close: datetime,
    features_by_prediction: Mapping[str, Mapping[str, Any]],
    missed_attempts: int | str,
) -> dict[str, Any]:
    closes = sorted(row["reference_close_utc"] for row in rows)
    feature_values: dict[str, list[Any]] = {
        "regime": [],
        "realized_vol": [],
        "trend_mtf": [],
        "volume_anomaly": [],
    }
    for row in rows:
        snapshot = features_by_prediction.get(str(row.get("candidate_prediction_id")))
        for name in feature_values:
            feature_values[name].append(
                snapshot.get(name) if isinstance(snapshot, Mapping) else None
            )

    return {
        "admitted_pairs": len(rows),
        "k_pre_drop": {
            str(c): window_count(timeframe, c, t0, t_close) for c in ORDERED_COARSENINGS
        },
        "usable_windows": _window_counts(timeframe, rows, t0=t0, t_close=t_close),
        "dropped_windows": _dropped_counts(timeframe, rows, t0=t0, t_close=t_close),
        "missed_attempts": missed_attempts,
        "missed_attempts_basis": (
            "not derivable from the persisted ledger; collector attempt outcomes live in "
            "workflow run logs. Reported as absent rather than as zero."
            if missed_attempts == UNMEASURED
            else "supplied by an attempt ledger"
        ),
        "realized_label_distribution": distribution(
            [realized_label(row) for row in rows]
        ),
        "regime_distribution": distribution(feature_values["regime"]),
        "trend_mtf_distribution": distribution(feature_values["trend_mtf"]),
        "realized_vol_summary": numeric_summary(feature_values["realized_vol"]),
        "volume_anomaly_summary": numeric_summary(feature_values["volume_anomaly"]),
        "first_reference_close_utc": closes[0].isoformat() if closes else None,
        "last_reference_close_utc": closes[-1].isoformat() if closes else None,
        "realised_span_seconds": (
            int((closes[-1] - closes[0]).total_seconds()) if len(closes) > 1 else 0
        ),
        "per_symbol": {
            symbol: _cell_block(timeframe, symbol, rows, t0=t0, t_close=t_close)
            for symbol in sorted({str(row.get("normalized_symbol")) for row in rows})
        },
    }


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


def _cell_block(timeframe, symbol, rows, *, t0, t_close) -> dict[str, Any]:
    """§5A.10 requires the diagnostics PER CELL, not only per timeframe."""

    cell_rows = [row for row in rows if row.get("normalized_symbol") == symbol]
    closes = sorted(row["reference_close_utc"] for row in cell_rows)
    return {
        "admitted_pairs": len(cell_rows),
        "usable_windows": _window_counts(timeframe, cell_rows, t0=t0, t_close=t_close),
        "dropped_windows": _dropped_counts(timeframe, cell_rows, t0=t0, t_close=t_close),
        "realized_label_distribution": distribution(
            [realized_label(row) for row in cell_rows]
        ),
        "first_reference_close_utc": closes[0].isoformat() if closes else None,
        "last_reference_close_utc": closes[-1].isoformat() if closes else None,
    }


def _percentile(sorted_values: Sequence[float], fraction: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = fraction * (len(sorted_values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight
