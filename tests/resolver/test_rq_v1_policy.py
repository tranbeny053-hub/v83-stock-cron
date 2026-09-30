"""Retry/quarantine policy rq-v1 (owner decision D4): every rule, boundary and backoff step, and
the outage guard. The policy is pure: these tests pass ``now`` and the existing status in."""

from __future__ import annotations

import dataclasses
import re
from datetime import UTC, datetime, timedelta

import pytest

from crypto_probability_engine.resolution import rq_v1
from crypto_probability_engine.resolution.rq_v1 import (
    QUARANTINED,
    RESOLVED,
    RETRYABLE,
    Attempt,
    ExistingStatus,
    StatusWrite,
)
from scripts import apply_migration_0012 as apply_0012
from scripts import resolve_outcomes

NOW = datetime(2026, 10, 1, 12, 17, tzinfo=UTC)
FIRST = datetime(2026, 9, 28, 12, 17, tzinfo=UTC)  # exactly 3 days before NOW
HORIZON = datetime(2026, 9, 24, 12, 17, tzinfo=UTC)  # exactly 7 days before NOW
VERSION = "resolver-v2b-tc-v1-rq-v1"
HOUR = timedelta(hours=1)
TICK = timedelta(microseconds=1)
UNRESOLVED_REASONS = sorted(set(resolve_outcomes.REASON_KEYS) - rq_v1.NO_WRITE_REASONS)


def _attempt(outcome, *, pid="p1", venue="BINANCE_PUBLIC", horizon=HORIZON):
    return Attempt(prediction_id=pid, outcome=outcome, venue=venue, horizon_end_utc=horizon)


def _retryable(count, *, first=FIRST, first_reason="skip_terminal_bar_missing"):
    return ExistingStatus(
        resolution_status=RETRYABLE,
        attempt_count=count,
        first_attempt_utc=first,
        last_attempt_utc=NOW - HOUR,
        first_reason=first_reason,
        last_reason="error_provider_unavailable",
        next_eligible_utc=NOW - TICK,
    )


def _decide(outcome, existing=None, *, now=NOW, horizon=HORIZON):
    return rq_v1.decide(
        _attempt(outcome, horizon=horizon), existing, now=now, resolver_version=VERSION
    )


def _plan(attempts, existing=None):
    return rq_v1.plan_status_writes(
        attempts, existing or {}, now=NOW, resolver_version=VERSION
    )


# --------------------------------------------------------------------------- the rule table


def test_every_reason_of_the_resolver_has_exactly_one_rule() -> None:
    rules = (
        rq_v1.NO_WRITE_REASONS,
        rq_v1.QUARANTINE_AT_ONCE_REASONS,
        rq_v1.AFTER_HORIZON_REASONS,
        rq_v1.AFTER_FIRST_ATTEMPT_REASONS,
        rq_v1.NEVER_QUARANTINED_REASONS,
        rq_v1.SAVE_ERROR_REASONS,
    )
    assert sum(len(rule) for rule in rules) == len(set().union(*rules))  # pairwise disjoint
    assert set().union(*rules) == set(resolve_outcomes.REASON_KEYS)
    assert rq_v1.MARKET_REASONS == {
        "skip_terminal_bar_missing",
        "error_provider_unavailable",
        "error_provider_rejected",
        "error_candle_invalid",
    }
    assert rq_v1.OUTCOME_RESOLVED == "resolved"
    assert rq_v1.OUTCOME_RESOLVED not in resolve_outcomes.REASON_KEYS


def test_the_labels_and_the_write_shape_are_migration_0012_s() -> None:
    (policy_pattern,) = apply_0012.EXPECTED_CONSTRAINTS["prs_policy_version_format"][2]
    assert rq_v1.POLICY_VERSION == "rq-v1"
    assert re.fullmatch(policy_pattern, rq_v1.POLICY_VERSION)
    assert {RETRYABLE, QUARANTINED, RESOLVED} == apply_0012.STATUSES
    assert tuple(field.name for field in dataclasses.fields(StatusWrite)) == tuple(
        name for name in apply_0012.EXPECTED_COLUMN_NAMES if name != "updated_at_utc"
    )


# --------------------------------------------------------------------------- nothing written


@pytest.mark.parametrize("existing", [None, _retryable(2)], ids=["new", "retryable"])
@pytest.mark.parametrize("outcome", ["skip_ineligible", "skip_not_due", "error_outcome_conflict"])
def test_these_outcomes_write_nothing(outcome, existing) -> None:
    assert _decide(outcome, existing) is None


def test_a_row_resolved_on_its_first_attempt_never_gets_a_status() -> None:
    assert _decide("resolved") is None
    assert _plan([_attempt("resolved", pid=f"p{i}") for i in range(3)]).writes == ()


@pytest.mark.parametrize("pid", [None, "", "   "])
def test_a_row_without_a_usable_prediction_id_gets_no_status(pid) -> None:
    attempt = _attempt("skip_invalid_target", pid=pid)
    assert rq_v1.decide(attempt, None, now=NOW, resolver_version=VERSION) is None
    assert _plan([attempt]).writes == ()


@pytest.mark.parametrize("status", [QUARANTINED, RESOLVED])
@pytest.mark.parametrize("outcome", ["resolved", "skip_invalid_target", "error_other"])
def test_a_quarantined_or_resolved_row_is_never_changed(status, outcome) -> None:
    existing = dataclasses.replace(_retryable(3), resolution_status=status, next_eligible_utc=None)
    assert _decide(outcome, existing) is None


def test_an_unknown_outcome_is_refused() -> None:
    with pytest.raises(ValueError, match="no rule"):
        _decide("error_something_new")
    with pytest.raises(ValueError, match="no rule"):
        _plan([_attempt("skip_unknown")])


# --------------------------------------------------------------------------- resolved


def test_a_retryable_row_that_resolves_becomes_resolved() -> None:
    existing = _retryable(3, first_reason="error_provider_rejected")

    write = _decide("resolved", existing)

    assert write == StatusWrite(
        prediction_id="p1",
        resolution_status=RESOLVED,
        attempt_count=4,
        first_attempt_utc=FIRST,
        last_attempt_utc=NOW,
        first_reason="error_provider_rejected",
        last_reason="error_provider_unavailable",  # kept: the last reason it stayed unresolved
        next_eligible_utc=None,
        quarantined_at_utc=None,
        resolved_at_utc=NOW,
        policy_version="rq-v1",
        resolver_version=VERSION,
    )


# --------------------------------------------------------------------------- unresolved


@pytest.mark.parametrize("reason", UNRESOLVED_REASONS)
def test_a_first_failure_starts_the_record_at_now(reason) -> None:
    write = _decide(reason)

    assert (write.attempt_count, write.first_attempt_utc, write.last_attempt_utc) == (1, NOW, NOW)
    assert (write.first_reason, write.last_reason) == (reason, reason)
    assert (write.policy_version, write.resolver_version) == ("rq-v1", VERSION)
    assert write.resolved_at_utc is None


@pytest.mark.parametrize("reason", UNRESOLVED_REASONS)
def test_a_repeat_failure_keeps_the_first_attempt_and_reason(reason) -> None:
    write = _decide(reason, _retryable(2))

    assert (write.attempt_count, write.first_attempt_utc, write.last_attempt_utc) == (3, FIRST, NOW)
    assert (write.first_reason, write.last_reason) == ("skip_terminal_bar_missing", reason)


@pytest.mark.parametrize("reason", ["skip_invalid_target", "error_row_unreadable"])
@pytest.mark.parametrize("existing", [None, _retryable(1)], ids=["new", "retryable"])
def test_an_invalid_target_or_unreadable_row_is_quarantined_at_once(reason, existing) -> None:
    write = _decide(reason, existing, horizon=None)

    assert write.resolution_status == QUARANTINED
    assert (write.quarantined_at_utc, write.next_eligible_utc) == (NOW, None)


@pytest.mark.parametrize("reason", ["skip_terminal_bar_missing", "error_candle_invalid"])
@pytest.mark.parametrize(
    ("previous", "now", "status", "next_eligible"),
    [
        (0, HORIZON + timedelta(days=30), RETRYABLE, HOUR),  # n = 1
        (3, HORIZON + timedelta(days=7), RETRYABLE, 8 * HOUR),  # n = 4: too few attempts
        (4, HORIZON + timedelta(days=7) - TICK, RETRYABLE, 16 * HOUR),  # n = 5: too early
        (4, HORIZON + timedelta(days=7), QUARANTINED, None),  # n = 5, exactly a week on
        (10, HORIZON + timedelta(days=30), QUARANTINED, None),
    ],
)
def test_a_missing_bar_or_invalid_candle_quarantines_after_5_attempts_and_a_week(
    reason, previous, now, status, next_eligible
) -> None:
    existing = _retryable(previous) if previous else None

    write = _decide(reason, existing, now=now)

    assert (write.attempt_count, write.resolution_status) == (previous + 1, status)
    if status == QUARANTINED:
        assert (write.quarantined_at_utc, write.next_eligible_utc) == (now, None)
    else:
        assert (write.quarantined_at_utc, write.next_eligible_utc) == (None, now + next_eligible)


@pytest.mark.parametrize("reason", ["skip_terminal_bar_missing", "error_candle_invalid"])
def test_a_row_with_no_readable_horizon_is_never_aged_into_quarantine(reason) -> None:
    write = _decide(reason, _retryable(9), now=HORIZON + timedelta(days=365), horizon=None)

    assert write.resolution_status == RETRYABLE


@pytest.mark.parametrize(
    ("previous", "now", "status"),
    [
        (0, FIRST + timedelta(days=30), RETRYABLE),  # n = 1: its first attempt is now
        (3, FIRST + timedelta(days=3), RETRYABLE),  # n = 4
        (4, FIRST + timedelta(days=3) - TICK, RETRYABLE),  # n = 5, a microsecond early
        (4, FIRST + timedelta(days=3), QUARANTINED),  # n = 5, exactly 3 days on
    ],
)
def test_a_rejected_symbol_quarantines_after_5_attempts_and_3_days(previous, now, status) -> None:
    existing = _retryable(previous) if previous else None

    write = _decide("error_provider_rejected", existing, now=now)

    assert (write.attempt_count, write.resolution_status) == (previous + 1, status)
    assert write.first_attempt_utc == (FIRST if previous else now)


@pytest.mark.parametrize("reason", ["error_provider_unavailable", "error_other"])
def test_an_outage_or_unknown_error_is_never_quarantined_automatically(reason) -> None:
    now = HORIZON + timedelta(days=365)

    write = _decide(reason, _retryable(999, first=HORIZON), now=now)

    assert (write.resolution_status, write.attempt_count) == (RETRYABLE, 1000)
    assert write.next_eligible_utc == now + timedelta(hours=24)


@pytest.mark.parametrize("reason", ["error_save_not_ok", "error_save_exception"])
@pytest.mark.parametrize("previous", [0, 1, 6])
def test_a_save_error_retries_on_the_next_run(reason, previous) -> None:
    write = _decide(reason, _retryable(previous) if previous else None)

    assert write.resolution_status == RETRYABLE
    assert write.next_eligible_utc == NOW


@pytest.mark.parametrize(
    ("attempt", "hours"), [(1, 1), (2, 2), (3, 4), (4, 8), (5, 16), (6, 24), (7, 24), (10**6, 24)]
)
def test_every_backoff_step(attempt, hours) -> None:
    assert rq_v1.backoff(attempt) == timedelta(hours=hours)
    write = _decide("error_other", _retryable(attempt - 1) if attempt > 1 else None)
    assert write.next_eligible_utc == NOW + timedelta(hours=hours)


@pytest.mark.parametrize("attempt", [0, -1, True, 1.0, None])
def test_the_backoff_refuses_what_is_not_an_attempt_number(attempt) -> None:
    with pytest.raises(ValueError):
        rq_v1.backoff(attempt)


# --------------------------------------------------------------------------- outage guard


def _venue(outcomes, venue="BINANCE_PUBLIC", prefix="b"):
    return [
        _attempt(outcome, pid=f"{prefix}{index}", venue=venue)
        for index, outcome in enumerate(outcomes)
    ]


@pytest.mark.parametrize(("attempted", "outage"), [(4, False), (5, True)])
def test_the_outage_guard_needs_5_attempted_rows_on_the_venue(attempted, outage) -> None:
    plan = _plan(_venue(["error_provider_unavailable"] * attempted))

    assert plan.outage_venues == ({"BINANCE_PUBLIC"} if outage else set())
    assert (len(plan.writes), plan.suppressed) == ((0, attempted) if outage else (attempted, 0))


@pytest.mark.parametrize(
    ("market", "resolved", "outage"),
    [
        (4, 1, True),  # 4 / 5 = 80%
        (20, 5, True),  # 20 / 25 = 80%
        (19, 5, False),  # 19 / 24 = 79.2%
        (3, 2, False),  # 60%
    ],
)
def test_the_outage_guard_needs_one_market_reason_on_80_percent(market, resolved, outage) -> None:
    attempts = _venue(["skip_terminal_bar_missing"] * market + ["resolved"] * resolved)

    plan = _plan(attempts)

    assert (plan.outage_venues == {"BINANCE_PUBLIC"}) is outage
    assert plan.suppressed == (market if outage else 0)
    assert len(plan.writes) == (0 if outage else market)


def test_two_market_reasons_that_share_the_rows_are_not_an_outage() -> None:
    attempts = _venue(["skip_terminal_bar_missing"] * 3 + ["error_provider_unavailable"] * 2)

    plan = _plan(attempts)

    assert plan.outage_venues == set()
    assert (len(plan.writes), plan.suppressed) == (5, 0)


def test_a_venue_outage_suppresses_every_unresolved_write_but_never_a_resolved_one() -> None:
    # 8 of the venue's 10 attempted rows failed the same way: 80%, an outage.
    down = _venue(["error_provider_unavailable"] * 8 + ["skip_invalid_target", "resolved"])
    other = _venue(["error_provider_unavailable"], venue="OKX_PUBLIC", prefix="o")
    existing = {"b9": _retryable(2)}  # the row that resolves this run was RETRYABLE

    plan = _plan(down + other, existing)

    assert plan.outage_venues == {"BINANCE_PUBLIC"}
    assert plan.suppressed == 9  # 8 retries and the quarantine of b8
    assert [(w.prediction_id, w.resolution_status) for w in plan.writes] == [
        ("b9", RESOLVED),
        ("o0", RETRYABLE),
    ]


def test_rows_with_no_venue_are_never_grouped() -> None:
    attempts = _venue(["error_provider_unavailable"] * 6, venue=None)

    plan = _plan(attempts)

    assert (plan.outage_venues, plan.suppressed, len(plan.writes)) == (frozenset(), 0, 6)


def test_the_plan_keeps_attempt_order() -> None:
    attempts = [
        _attempt("error_other", pid="z", venue="OKX_PUBLIC"),
        _attempt("skip_invalid_target", pid="a", venue=None),
        _attempt("error_save_exception", pid="m"),
    ]

    assert [write.prediction_id for write in _plan(attempts).writes] == ["z", "a", "m"]
