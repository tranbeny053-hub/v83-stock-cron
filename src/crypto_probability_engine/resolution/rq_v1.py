"""Retry/quarantine policy rq-v1 of the outcome resolver (owner decision D4). Pure: no I/O.

After a Route C run, the resolver passes every row it ATTEMPTED: its outcome ("resolved", or the
one reason it stayed unresolved), its existing status (None, or the RETRYABLE row the due scan
read), the run's ``now``, its ``horizon_end_utc`` and its resolution venue. This module answers
which row of public.prediction_resolution_status (migration 0012) each one gets, if any. It never
reads a clock, a database or the network.

Nothing is written for a row resolved on its first attempt, for skip_ineligible, skip_not_due and
error_outcome_conflict, or for a row the run deferred (it was never attempted). A RETRYABLE row
that resolves becomes RESOLVED. Otherwise, with n the attempt number:
- skip_invalid_target and error_row_unreadable are QUARANTINED at once;
- skip_terminal_bar_missing and error_candle_invalid are QUARANTINED once n >= 5 and
  now >= horizon_end_utc + 7 days;
- error_provider_rejected is QUARANTINED once n >= 5 and now >= the first attempt + 3 days;
- error_provider_unavailable and error_other are never quarantined automatically;
- error_save_not_ok and error_save_exception retry on the next run (next_eligible_utc = now);
- every other RETRYABLE row backs off: next_eligible_utc = now + min(24 h, 1 h * 2**(n-1)).

The outage guard: when one market reason accounts for >= 80% of a venue's attempted rows, and the
venue had >= 5 of them this run, the venue failed, not its rows. Every unresolved write for that
venue's rows is suppressed this run; RESOLVED transitions never are. Rows with no venue are not
grouped.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from fractions import Fraction

POLICY_VERSION = "rq-v1"

RETRYABLE = "RETRYABLE"
QUARANTINED = "QUARANTINED"
RESOLVED = "RESOLVED"
# An attempt's outcome: this when the row resolved, otherwise the resolver's reason key.
OUTCOME_RESOLVED = "resolved"

# Each of the resolver's reason keys is in exactly one of these six sets (a test checks it).
NO_WRITE_REASONS = frozenset({"skip_ineligible", "skip_not_due", "error_outcome_conflict"})
QUARANTINE_AT_ONCE_REASONS = frozenset({"skip_invalid_target", "error_row_unreadable"})
AFTER_HORIZON_REASONS = frozenset({"skip_terminal_bar_missing", "error_candle_invalid"})
AFTER_FIRST_ATTEMPT_REASONS = frozenset({"error_provider_rejected"})
NEVER_QUARANTINED_REASONS = frozenset({"error_provider_unavailable", "error_other"})
SAVE_ERROR_REASONS = frozenset({"error_save_not_ok", "error_save_exception"})
# The reasons a venue outage produces. They feed the outage guard.
MARKET_REASONS = frozenset(
    {
        "skip_terminal_bar_missing",
        "error_provider_unavailable",
        "error_provider_rejected",
        "error_candle_invalid",
    }
)

QUARANTINE_MIN_ATTEMPTS = 5
QUARANTINE_AFTER_HORIZON = timedelta(days=7)
QUARANTINE_AFTER_FIRST_ATTEMPT = timedelta(days=3)
BACKOFF_BASE = timedelta(hours=1)
BACKOFF_CAP = timedelta(hours=24)
_BACKOFF_CAP_EXPONENT = 5  # 1 h * 2**5 = 32 h already exceeds the cap: no huge powers
OUTAGE_MIN_ATTEMPTS = 5
OUTAGE_SHARE = Fraction(4, 5)  # exact: 4 of 5 is an outage, 19 of 24 is not


@dataclass(frozen=True)
class ExistingStatus:
    """A status row as the due scan read it. Only RETRYABLE rows are ever due."""

    resolution_status: str
    attempt_count: int
    first_attempt_utc: datetime
    last_attempt_utc: datetime
    first_reason: str
    last_reason: str
    next_eligible_utc: datetime | None


@dataclass(frozen=True)
class Attempt:
    """One row this run attempted. ``prediction_id`` is None when the row had no usable one."""

    prediction_id: str | None
    outcome: str
    venue: str | None
    horizon_end_utc: datetime | None


@dataclass(frozen=True)
class StatusWrite:
    """One upserted row: every column of the table but updated_at_utc, in the table's order."""

    prediction_id: str
    resolution_status: str
    attempt_count: int
    first_attempt_utc: datetime
    last_attempt_utc: datetime
    first_reason: str
    last_reason: str
    next_eligible_utc: datetime | None
    quarantined_at_utc: datetime | None
    resolved_at_utc: datetime | None
    policy_version: str
    resolver_version: str


@dataclass(frozen=True)
class StatusPlan:
    writes: tuple[StatusWrite, ...]  # in attempt order, after the outage guard
    suppressed: int  # unresolved writes the outage guard dropped
    outage_venues: frozenset[str]


def backoff(attempt_count: int) -> timedelta:
    """min(24 h, 1 h * 2**(n-1)) for attempt number n >= 1."""

    if isinstance(attempt_count, bool) or not isinstance(attempt_count, int) or attempt_count < 1:
        raise ValueError("attempt_count must be an int >= 1")
    return min(BACKOFF_CAP, BACKOFF_BASE * 2 ** min(attempt_count - 1, _BACKOFF_CAP_EXPONENT))


def decide(
    attempt: Attempt,
    existing: ExistingStatus | None,
    *,
    now: datetime,
    resolver_version: str,
) -> StatusWrite | None:
    """The status write one attempt earns, before the outage guard, or None for no write.

    Raises ValueError for an outcome that is neither "resolved" nor a known reason.
    """

    if not _usable_id(attempt.prediction_id):
        return None  # a status row needs a non-blank prediction_id
    if existing is not None and existing.resolution_status != RETRYABLE:
        return None  # RESOLVED and QUARANTINED rows are never changed
    reason = attempt.outcome
    if reason == OUTCOME_RESOLVED:
        if existing is None:
            return None  # resolved on its first attempt: it never gets a status
        return StatusWrite(
            prediction_id=attempt.prediction_id,
            resolution_status=RESOLVED,
            attempt_count=existing.attempt_count + 1,
            first_attempt_utc=existing.first_attempt_utc,
            last_attempt_utc=now,
            first_reason=existing.first_reason,
            last_reason=existing.last_reason,  # kept: the last reason it stayed unresolved
            next_eligible_utc=None,
            quarantined_at_utc=None,
            resolved_at_utc=now,
            policy_version=POLICY_VERSION,
            resolver_version=resolver_version,
        )
    if reason in NO_WRITE_REASONS:
        return None
    attempts = 1 if existing is None else existing.attempt_count + 1
    first_attempt = now if existing is None else existing.first_attempt_utc
    first_reason = reason if existing is None else existing.first_reason
    if reason in QUARANTINE_AT_ONCE_REASONS:
        quarantine = True
    elif reason in AFTER_HORIZON_REASONS:
        quarantine = (
            attempts >= QUARANTINE_MIN_ATTEMPTS
            and attempt.horizon_end_utc is not None
            and now >= attempt.horizon_end_utc + QUARANTINE_AFTER_HORIZON
        )
    elif reason in AFTER_FIRST_ATTEMPT_REASONS:
        quarantine = (
            attempts >= QUARANTINE_MIN_ATTEMPTS
            and now >= first_attempt + QUARANTINE_AFTER_FIRST_ATTEMPT
        )
    elif reason in NEVER_QUARANTINED_REASONS or reason in SAVE_ERROR_REASONS:
        quarantine = False
    else:
        raise ValueError(f"rq-v1 has no rule for outcome {reason!r}")
    if quarantine:
        next_eligible = None
    elif reason in SAVE_ERROR_REASONS:
        next_eligible = now  # the next run
    else:
        next_eligible = now + backoff(attempts)
    return StatusWrite(
        prediction_id=attempt.prediction_id,
        resolution_status=QUARANTINED if quarantine else RETRYABLE,
        attempt_count=attempts,
        first_attempt_utc=first_attempt,
        last_attempt_utc=now,
        first_reason=first_reason,
        last_reason=reason,
        next_eligible_utc=next_eligible,
        quarantined_at_utc=now if quarantine else None,
        resolved_at_utc=None,
        policy_version=POLICY_VERSION,
        resolver_version=resolver_version,
    )


def outage_venues(attempts: Iterable[Attempt]) -> frozenset[str]:
    """Venues with >= 5 attempted rows of which ONE market reason accounts for >= 80%."""

    totals: Counter[str] = Counter()
    market: dict[str, Counter[str]] = {}
    for attempt in attempts:
        if attempt.venue is None:
            continue  # rows with no venue are not grouped
        totals[attempt.venue] += 1
        if attempt.outcome in MARKET_REASONS:
            market.setdefault(attempt.venue, Counter())[attempt.outcome] += 1
    return frozenset(
        venue
        for venue, total in totals.items()
        if total >= OUTAGE_MIN_ATTEMPTS
        and venue in market
        and Fraction(max(market[venue].values()), total) >= OUTAGE_SHARE
    )


def plan_status_writes(
    attempts: Iterable[Attempt],
    existing: Mapping[str, ExistingStatus],
    *,
    now: datetime,
    resolver_version: str,
) -> StatusPlan:
    """Every status write of one run, in attempt order, with the outage guard applied."""

    attempted = tuple(attempts)
    down = outage_venues(attempted)
    writes: list[StatusWrite] = []
    suppressed = 0
    for attempt in attempted:
        current = existing.get(attempt.prediction_id) if _usable_id(attempt.prediction_id) else None
        write = decide(attempt, current, now=now, resolver_version=resolver_version)
        if write is None:
            continue
        if write.resolution_status != RESOLVED and attempt.venue in down:
            suppressed += 1
            continue
        writes.append(write)
    return StatusPlan(writes=tuple(writes), suppressed=suppressed, outage_venues=down)


def _usable_id(prediction_id: object) -> bool:
    return isinstance(prediction_id, str) and bool(prediction_id.strip())
