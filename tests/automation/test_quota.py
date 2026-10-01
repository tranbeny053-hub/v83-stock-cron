"""Rolling quota windows and nonblocking analysis slots."""

from datetime import timedelta
from unittest.mock import Mock

import pytest

from crypto_probability_engine.automation.ledger import Reservation, ReservationKind
from crypto_probability_engine.automation.quota import ConcurrencyGate, evaluate_quota
from tests.automation.conftest import utc

NOW = utc(2026, 9, 30)


@pytest.mark.parametrize(
    ("counts", "allowed"), [((5, 119), True), ((6, 6), False), ((0, 120), False)]
)
def test_both_windows(counts, allowed):
    result = evaluate_quota(
        Reservation(ReservationKind.NEW, None, *counts), per_5min=6, per_day=120, now=NOW
    )
    assert result.allowed is allowed
    assert (result.retry_after_seconds is None) is allowed


@pytest.mark.parametrize(
    ("window", "age", "expected"),
    [
        ("five", 10.2, 290),
        ("day", 10.2, 86390),
        ("five", 301, 1),
        ("day", 86401, 1),
        ("five", None, 300),
        ("day", None, 86400),
    ],
)
def test_retry_uses_oldest_counted_instant_and_rounds_up(window, age, expected):
    oldest = None if age is None else NOW - timedelta(seconds=age)
    reservation = Reservation(
        ReservationKind.NEW,
        None,
        counted_5min=6 if window == "five" else 0,
        counted_day=0 if window == "five" else 120,
        oldest_5min=oldest if window == "five" else None,
        oldest_day=oldest,
    )
    result = evaluate_quota(reservation, per_5min=6, per_day=120, now=NOW)
    assert not result.allowed and result.retry_after_seconds == expected
    assert result.retry_after_seconds >= 1


def test_retry_after_covers_every_exhausted_window():
    """Both windows full: the wait is the longer one, never just the 5-minute one (F2)."""

    reservation = Reservation(
        ReservationKind.NEW,
        None,
        counted_5min=1,
        counted_day=1,
        oldest_5min=NOW - timedelta(seconds=1),
        oldest_day=NOW - timedelta(seconds=1),
    )
    result = evaluate_quota(reservation, per_5min=1, per_day=1, now=NOW)
    assert not result.allowed and result.retry_after_seconds == 86399


def test_concurrency_gate_refuses_and_releases_slots():
    gate = ConcurrencyGate(1)
    assert gate.try_acquire()
    assert not gate.try_acquire()
    gate.release()
    assert gate.try_acquire()
    gate.release()


def test_concurrency_gate_explicitly_never_blocks(monkeypatch):
    gate = ConcurrencyGate(1)
    spy = Mock(return_value=False)
    monkeypatch.setattr(gate._semaphore, "acquire", spy)
    assert not gate.try_acquire()
    spy.assert_called_once_with(blocking=False)
