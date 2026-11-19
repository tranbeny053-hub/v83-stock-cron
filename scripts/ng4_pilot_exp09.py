"""Pure EXP-09 measurement helpers for the NG4 pilot.

EXP-09 measures operational completeness and unlogged grid instants. The route reads counts,
statuses and timestamps only; it never reads a probability, price or band value. It is authored
and disabled, and applies no threshold.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

PILOT_START_UTC = datetime(2026, 11, 23, tzinfo=UTC)
PILOT_DURATION = timedelta(days=14)
PILOT_END_UTC = PILOT_START_UTC + PILOT_DURATION
LATTICE_ANCHOR_UTC = datetime(2026, 9, 21, tzinfo=UTC)
PILOT_TIMEFRAMES = ("15m", "1H", "4H", "1D")
STEP_SECONDS = {"15m": 2700, "1H": 10800, "4H": 43200, "1D": 259200}
PILOT_NORMALIZED_SYMBOL = "SOL/USDT"
PILOT_REFERENCE_VENUE = "BINANCE_PUBLIC"
PILOT_CAPACITY_MAX = 1200
PILOT_CAPACITY_WARN = 600
REPORT_SCHEMA = "ng4-pilot-exp09-report.v1"
END_SETTLE = timedelta(minutes=10)


class Refused(Exception):
    """A safe refusal carrying only a stable code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def lattice_instants(timeframe: str, start: datetime, end: datetime) -> tuple[datetime, ...]:
    """Return lattice instants in the inclusive interval using the fixed lattice anchor."""
    if timeframe not in STEP_SECONDS:
        raise ValueError("Unsupported timeframe")
    if start.utcoffset() != timedelta(0) or end.utcoffset() != timedelta(0):
        raise ValueError("Bounds must be aware UTC datetimes")
    step = timedelta(seconds=STEP_SECONDS[timeframe])
    elapsed = (start - LATTICE_ANCHOR_UTC).total_seconds()
    first = LATTICE_ANCHOR_UTC + int(elapsed // step.total_seconds()) * step
    if first < start:
        first += step
    values = []
    while first <= end:
        values.append(first)
        first += step
    return tuple(values)


def reconstruct_gaps(
    grid: Iterable[datetime], row_instants: Iterable[datetime], missed_instants: Iterable[datetime]
) -> tuple[datetime, ...]:
    rows, missed = set(row_instants), set(missed_instants)
    return tuple(instant for instant in grid if instant not in rows and instant not in missed)


def parse_as_of(text: str | None, now: datetime) -> datetime:
    if text is None:
        value = PILOT_END_UTC
    else:
        try:
            if len(text) != 20 or text[-1] != "Z" or text[16:19] != ":00":
                raise ValueError
            value = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        except (TypeError, ValueError):
            raise Refused("AS_OF_FORMAT") from None
    if now.utcoffset() != timedelta(0):
        now = now.astimezone(UTC)
    if value <= PILOT_START_UTC:
        raise Refused("AS_OF_NOT_AFTER_START")
    if value > PILOT_END_UTC:
        raise Refused("AS_OF_AFTER_END")
    if value > now:
        raise Refused("AS_OF_IN_FUTURE")
    if value == PILOT_END_UTC and now < PILOT_END_UTC + END_SETTLE:
        raise Refused("END_NOT_SETTLED")
    return value


def window(as_of: datetime) -> tuple[datetime, datetime]:
    return PILOT_START_UTC, as_of


def grid(timeframe: str, as_of: datetime) -> list[datetime]:
    return [
        instant
        for instant in lattice_instants(timeframe, PILOT_START_UTC, as_of)
        if instant < as_of
    ]


def measure_cell(
    timeframe: str,
    as_of: datetime,
    row_instants: Iterable[datetime],
    missed_instants: Iterable[datetime],
) -> dict[str, object]:
    planned_grid = grid(timeframe, as_of)
    row_set, missed_set = set(row_instants), set(missed_instants)
    grid_set = set(planned_grid)
    issued = row_set & grid_set
    missed = missed_set & grid_set
    unlogged = set(reconstruct_gaps(planned_grid, row_set, missed_set))
    overlap = issued & missed
    planned = len(planned_grid)
    issued_fraction = round(len(issued) / planned, 6) if planned else None
    accounted_fraction = (
        round((len(issued) + len(missed) - len(overlap)) / planned, 6) if planned else None
    )
    runs: list[dict[str, object]] = []
    run_start: int | None = None
    for index, instant in enumerate(planned_grid):
        if instant in unlogged:
            if run_start is None:
                run_start = index
        elif run_start is not None:
            runs.append(_run(planned_grid, run_start, index - 1))
            run_start = None
    if run_start is not None:
        runs.append(_run(planned_grid, run_start, len(planned_grid) - 1))
    return {
        "planned": planned,
        "issued_on_grid": len(issued),
        "missed_on_grid": len(missed),
        "off_grid_rows": len(row_set - grid_set),
        "row_and_missed_same_instant": len(overlap),
        "unlogged": len(unlogged),
        "issued_fraction": issued_fraction,
        "accounted_fraction": accounted_fraction,
        "unlogged_runs": runs,
    }


def _run(grid_values: list[datetime], first_index: int, last_index: int) -> dict[str, object]:
    return {
        "first": _iso_z(grid_values[first_index]),
        "last": _iso_z(grid_values[last_index]),
        "count": last_index - first_index + 1,
        "cause": "NOT_RECORDED_IN_DATABASE",
    }


def capacity_state(max_rows: int | None, warn_rows: int | None, rows: int, missed: int) -> str:
    if max_rows is None:
        return "CAPACITY_UNSET"
    used = rows + missed
    if used >= max_rows:
        return "CAPACITY_STOP"
    if warn_rows is not None and used + 1 >= warn_rows:
        return "WARN"
    return "OK"


def assemble_report(
    as_of: datetime,
    dispatched_sha: str,
    sections: dict[str, object] | None = None,
    *,
    look_spent: str = "NONE (counts, statuses and timestamps only)",
) -> dict[str, object]:
    start, end = window(as_of)
    report: dict[str, object] = {
        "schema": REPORT_SCHEMA,
        "evidence_use": "TEST_ONLY",
        "population": "E1_OPERATIONAL",
        "claim": "NONE",
        "look_spent": look_spent,
        "verdict": "NOT_JUDGED_THRESHOLD_UNRULED",
        "thresholds": "OD-NG-7 unruled; none applied or stored",
        "http_counts": "NOT_IN_DATABASE",
        "http_counts_note": (
            "Provider exchanges appear only in the Space's own logs (owner-visible)."
        ),
        "window": {"start": _iso_z(start), "end": _iso_z(end)},
        "as_of_utc": _iso_z(as_of),
        "provisional": as_of < PILOT_END_UTC,
        "dispatched_sha": dispatched_sha,
    }
    if sections:
        report.update(sections)
    return report


def dumps(report: dict[str, object]) -> str:
    return json.dumps(report, indent=2, sort_keys=False, ensure_ascii=True) + "\n"
