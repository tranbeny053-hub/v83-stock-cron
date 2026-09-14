from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from crypto_probability_engine.oos.evaluation.lattice import (
    assign_window_index,
    window_count,
)

T0 = datetime(2026, 8, 21, 4, tzinfo=UTC)
T_CLOSE = datetime(2026, 9, 12, 4, tzinfo=UTC)


def test_4h_window_counts_pin_contract_published_numbers() -> None:
    assert {c: window_count("4H", c, T0, T_CLOSE) for c in (1, 2, 4)} == {
        1: 11,
        2: 7,
        4: 5,
    }


@pytest.mark.parametrize(
    ("timeframe", "expected"),
    [
        ("1H", {1: 44, 2: 29, 4: 18}),
        ("15m", {1: 176, 2: 117, 4: 71}),
    ],
)
def test_window_counts_known_answers(timeframe: str, expected: dict[int, int]) -> None:
    assert {c: window_count(timeframe, c, T0, T_CLOSE) for c in (1, 2, 4)} == expected


@pytest.mark.parametrize(
    ("reference_close_utc", "expected"),
    [
        (T0, 0),
        (T0 + timedelta(hours=24) - timedelta(seconds=1), 0),
        (T0 + timedelta(hours=24), None),
        (T0 + timedelta(hours=47, minutes=59, seconds=59), None),
        (T0 + timedelta(hours=48), 1),
        (T0 - timedelta(seconds=1), None),
        (T0 + timedelta(hours=10 * 48 + 24), None),
        (T0 + timedelta(hours=11 * 48), None),
    ],
)
def test_4h_c1_assignment_uses_half_open_boundaries(
    reference_close_utc: datetime, expected: int | None
) -> None:
    assert assign_window_index(reference_close_utc, "4H", 1, T0, T_CLOSE) == expected


def test_lattice_returns_zero_when_no_window_can_resolve() -> None:
    assert window_count("4H", 1, T0, T0 + timedelta(hours=47)) == 0
    assert assign_window_index(T0, "4H", 1, T0, T0 + timedelta(hours=47)) is None


@pytest.mark.parametrize(("timeframe", "c"), [("1D", 1), ("4H", 3)])
def test_lattice_rejects_unsupported_parameters(timeframe: str, c: int) -> None:
    with pytest.raises(ValueError):
        window_count(timeframe, c, T0, T_CLOSE)


def test_lattice_rejects_subsecond_or_naive_instants() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        window_count("4H", 1, T0.replace(tzinfo=None), T_CLOSE)
    with pytest.raises(ValueError, match="whole seconds"):
        assign_window_index(T0.replace(microsecond=1), "4H", 1, T0, T_CLOSE)

