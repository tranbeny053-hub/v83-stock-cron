import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from crypto_probability_engine.quant_ng import lattice

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "ng4_pilot_exp09_test", ROOT / "scripts/ng4_pilot_exp09.py"
)
exp09 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exp09)


def instant(day: int, hour: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, tzinfo=UTC)


def test_restated_constants_match_lattice():
    assert exp09.PILOT_START_UTC == lattice.PILOT_START_UTC
    assert exp09.PILOT_DURATION == lattice.PILOT_DURATION
    assert exp09.PILOT_END_UTC == lattice.pilot_end(lattice.PILOT_START_UTC)
    assert exp09.LATTICE_ANCHOR_UTC == lattice.LATTICE_ANCHOR_UTC
    assert exp09.PILOT_TIMEFRAMES == lattice.PILOT_TIMEFRAMES
    assert exp09.STEP_SECONDS == {
        tf: lattice._BAR_SECONDS[tf] * lattice.CADENCE_BARS for tf in lattice.PILOT_TIMEFRAMES
    }
    assert exp09.PILOT_CAPACITY_MAX == lattice.PILOT_CAPACITY_MAX
    assert exp09.PILOT_CAPACITY_WARN == lattice.PILOT_CAPACITY_WARN
    assert (
        exp09.PILOT_NORMALIZED_SYMBOL
        == lattice.build_missed_entry(lattice.PILOT_CELLS[0], exp09.PILOT_START_UTC, "NOT_ISSUED")[
            "normalized_symbol"
        ]
    )
    assert (
        exp09.PILOT_REFERENCE_VENUE
        == lattice.build_missed_entry(lattice.PILOT_CELLS[0], exp09.PILOT_START_UTC, "NOT_ISSUED")[
            "reference_venue"
        ]
    )


def test_lattice_grid_matches_for_full_window_and_day_seven():
    day_seven = datetime(2026, 11, 30, tzinfo=UTC)
    full_counts, day_counts = [], []
    for timeframe in exp09.PILOT_TIMEFRAMES:
        full = exp09.lattice_instants(timeframe, exp09.PILOT_START_UTC, exp09.PILOT_END_UTC)
        day = exp09.lattice_instants(timeframe, exp09.PILOT_START_UTC, day_seven)
        assert full == lattice.lattice_instants(
            timeframe, exp09.PILOT_START_UTC, exp09.PILOT_END_UTC
        )
        assert day == lattice.lattice_instants(timeframe, exp09.PILOT_START_UTC, day_seven)
        full_counts.append(len([value for value in full if value < exp09.PILOT_END_UTC]))
        day_counts.append(len([value for value in day if value < day_seven]))
    assert full_counts == [448, 112, 28, 5]
    assert sum(full_counts) == 593
    assert sum(full_counts) == sum(lattice.planned_slots(exp09.PILOT_START_UTC).values())
    assert day_counts == [224, 56, 14, 3]
    assert sum(day_counts) == 297
    assert sum(len(exp09.grid(tf, exp09.PILOT_END_UTC)) for tf in exp09.PILOT_TIMEFRAMES) == 593
    assert sum(len(exp09.grid(tf, day_seven)) for tf in exp09.PILOT_TIMEFRAMES) == 297


def test_reconstruct_gaps_matches_lattice():
    grid = [instant(23), instant(23, 1), instant(23, 2), instant(23, 3)]
    rows = [grid[0], grid[3]]
    missed = [grid[1]]
    assert exp09.reconstruct_gaps(grid, rows, missed) == lattice.reconstruct_gaps(
        grid, rows, missed
    )


@pytest.mark.parametrize(
    ("text", "now", "code"),
    [
        ("2026-11-23T00:00:00Z", instant(24), "AS_OF_NOT_AFTER_START"),
        ("2026-12-07T00:01:00Z", datetime(2026, 12, 8, tzinfo=UTC), "AS_OF_AFTER_END"),
        ("2026-11-24T00:00:00+00:00", instant(25), "AS_OF_FORMAT"),
        ("2026-11-24T00:00:30Z", instant(25), "AS_OF_FORMAT"),
        ("a" * 40, instant(25), "AS_OF_FORMAT"),
        ("2026-11-25T00:00:00Z", instant(24), "AS_OF_IN_FUTURE"),
        ("2026-12-07T00:00:00Z", datetime(2026, 12, 7, 0, 9, tzinfo=UTC), "END_NOT_SETTLED"),
    ],
)
def test_parse_as_of_refusal_codes_and_no_input_echo(text, now, code):
    with pytest.raises(exp09.Refused) as caught:
        exp09.parse_as_of(text, now)
    assert caught.value.code == code
    if len(text) == 40:
        assert text not in str(caught.value)


def test_parse_as_of_default_and_valid_value():
    settled = exp09.PILOT_END_UTC + exp09.END_SETTLE
    assert exp09.parse_as_of(None, settled) == exp09.PILOT_END_UTC
    expected = datetime(2026, 11, 25, 12, tzinfo=UTC)
    assert exp09.parse_as_of("2026-11-25T12:00:00Z", settled) == expected


def test_measure_cell_full_coverage_gap_runs_and_integrity_counts():
    as_of = datetime(2026, 11, 23, 4, tzinfo=UTC)
    values = exp09.grid("15m", as_of)
    complete = exp09.measure_cell("15m", as_of, values, [])
    assert complete["planned"] == 6
    assert complete["issued_on_grid"] == 6
    assert complete["unlogged"] == 0
    assert complete["issued_fraction"] == 1.0
    assert complete["accounted_fraction"] == 1.0
    gap = exp09.measure_cell("15m", as_of, values[:1] + values[4:], [])
    assert gap["unlogged"] == 3
    assert gap["unlogged_runs"] == [
        {
            "first": "2026-11-23T00:45:00Z",
            "last": "2026-11-23T02:15:00Z",
            "count": 3,
            "cause": "NOT_RECORDED_IN_DATABASE",
        }
    ]
    off_grid = as_of - timedelta(minutes=1)
    mixed = exp09.measure_cell("15m", as_of, [values[0], off_grid], [values[0]])
    assert mixed["off_grid_rows"] == 1
    assert mixed["row_and_missed_same_instant"] == 1
    assert mixed["issued_on_grid"] == 1
    assert mixed["missed_on_grid"] == 1
    assert mixed["accounted_fraction"] == round(1 / 6, 6)


def test_measure_cell_zero_planned():
    result = exp09.measure_cell("15m", exp09.PILOT_START_UTC, [], [])
    assert result["planned"] == 0
    assert result["issued_fraction"] is None
    assert result["accounted_fraction"] is None


@pytest.mark.parametrize(
    ("max_rows", "warn_rows", "rows", "missed", "expected"),
    [
        (None, 600, 0, 0, "CAPACITY_UNSET"),
        (1200, 600, 1200, 0, "CAPACITY_STOP"),
        (1200, 600, 599, 0, "WARN"),
        (1200, 600, 598, 0, "OK"),
    ],
)
def test_capacity_state_boundaries(max_rows, warn_rows, rows, missed, expected):
    assert exp09.capacity_state(max_rows, warn_rows, rows, missed) == expected


def test_report_is_deterministic_and_has_fixed_order_and_values():
    args = (datetime(2026, 11, 30, tzinfo=UTC), "a" * 40)
    first = exp09.assemble_report(*args)
    second = exp09.assemble_report(*args)
    assert exp09.dumps(first).encode() == exp09.dumps(second).encode()
    assert list(first) == [
        "schema",
        "evidence_use",
        "population",
        "claim",
        "look_spent",
        "verdict",
        "thresholds",
        "http_counts",
        "http_counts_note",
        "window",
        "as_of_utc",
        "provisional",
        "dispatched_sha",
    ]
    assert first["schema"] == exp09.REPORT_SCHEMA
    assert first["evidence_use"] == "TEST_ONLY"
    assert first["population"] == "E1_OPERATIONAL"
    assert first["claim"] == "NONE"
    assert first["look_spent"] == "NONE (counts, statuses and timestamps only)"
    assert first["verdict"] == "NOT_JUDGED_THRESHOLD_UNRULED"
    assert first["thresholds"] == "OD-NG-7 unruled; none applied or stored"
    assert first["http_counts"] == "NOT_IN_DATABASE"
    assert first["as_of_utc"] == "2026-11-30T00:00:00Z"
    assert first["provisional"] is True
    assert first["dispatched_sha"] == args[1]
    assert set(first) & {"threshold", "threshold_value", "completeness_threshold"} == set()
    assert "0.90" not in exp09.dumps(first)
