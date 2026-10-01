"""The per-credential rate bounds of the automation route.

Two windows, counted from the ledger (so a restart never resets them): a rolling 5 minutes and a
rolling day. Refusals before any analysis (``QUOTA_EXCEEDED``, ``CONCURRENCY_LIMIT``) do not
count. Beyond the quota, the ledger's row ceiling (the capacity contract) refuses a new request
without recording it: ``throttle_retry_after`` says when the oldest row of the day leaves the
window. At most ``MAX_CONCURRENT_ANALYSES`` automated analyses run at once in a process; the slot
is held until the analysis thread actually ends, even past a deadline, so an overrun can never
pile up work behind it.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta

from crypto_probability_engine.automation.ledger import WINDOW_5MIN, WINDOW_DAY, Reservation

CONCURRENCY_RETRY_AFTER_SECONDS = 10


@dataclass(frozen=True)
class QuotaDecision:
    allowed: bool
    retry_after_seconds: int | None = None


def evaluate_quota(
    reservation: Reservation, *, per_5min: int, per_day: int, now: datetime
) -> QuotaDecision:
    """Refuse when any window is full; Retry-After covers EVERY exhausted window."""

    waits = []
    if reservation.counted_5min >= per_5min:
        waits.append(_retry_after(reservation.oldest_5min, WINDOW_5MIN, now))
    if reservation.counted_day >= per_day:
        waits.append(_retry_after(reservation.oldest_day, WINDOW_DAY, now))
    if waits:
        return QuotaDecision(False, max(waits))
    return QuotaDecision(True)


def throttle_retry_after(reservation: Reservation, now: datetime) -> int:
    """Seconds until the credential's oldest row of the last day leaves the rolling day."""

    return _retry_after(reservation.oldest_row_day, WINDOW_DAY, now)


def _retry_after(oldest: datetime | None, window: timedelta, now: datetime) -> int:
    if oldest is None:
        return int(window.total_seconds())
    return max(1, math.ceil((oldest + window - now).total_seconds()))


class ConcurrencyGate:
    """A non-blocking slot counter: a busy gate refuses at once, it never queues a caller."""

    def __init__(self, limit: int) -> None:
        self._semaphore = threading.BoundedSemaphore(limit)

    def try_acquire(self) -> bool:
        return self._semaphore.acquire(blocking=False)

    def release(self) -> None:
        self._semaphore.release()
