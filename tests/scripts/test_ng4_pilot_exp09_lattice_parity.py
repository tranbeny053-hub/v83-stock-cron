"""EXP-09: the script's restated constants and grid equal the engine's (quant_ng.lattice).

Kept apart from tests/scripts/test_ng4_pilot_exp09.py on purpose: the dispatch workflow's route-test
step runs that file under the evaluator lock only (no httpx or pydantic), and importing lattice
needs them (review EX-C1 A2). This file runs under ./verify.sh and the main test job.
"""

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

from crypto_probability_engine.quant_ng import lattice

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "ng4_pilot_exp09_parity_test", ROOT / "scripts/ng4_pilot_exp09.py"
)
exp09 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exp09)


def instant(day: int, hour: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, tzinfo=UTC)


def test_restated_constants_match_lattice():
    assert set(exp09.MISSED_REASONS) == lattice._MISSED
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
