"""The save receipt of one analysis (owner request, 2026-10-10).

The storage status an analysis carries is the repository's status read before the analysis ran and
before its background save, so it cannot say whether THIS analysis was saved. The receipt does:
`GET /v1/analyze/receipt/{run_id}` reads it. The analysis response itself is unchanged.

- SAVED: the durable store acknowledged the run's whole save (plan §8.1's SAVED receipt). When
  this process holds no record of the save (a restart, an evicted record), SAVED means the durable
  store returns the run's detail.
- PENDING: the save is scheduled and has not finished.
- FAILED: no save was acknowledged. It was sent and not confirmed (it may still have committed: an
  unconfirmed write is never read as SAVED), or it was not sent (storage unavailable, the save
  queue full), or the analysis has no forecast row (demo data), which History cannot find again.
- NOT_RETAINED: no durable store is configured.

The record is process memory: bounded, a run id and a state, never a payload. It is lost with the
process, and after that only the durable store can answer.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from datetime import UTC, datetime

SCHEMA_VERSION = "save_receipt.v1"
SAVED = "SAVED"
PENDING = "PENDING"
FAILED = "FAILED"
NOT_RETAINED = "NOT_RETAINED"
# Well above the in-memory run store's default (settings.recent_run_limit): a run this process
# still shows keeps its receipt.
LIMIT = 500


class SaveReceipts:
    """A bounded, thread-safe record of each run's save, oldest evicted first."""

    def __init__(self, limit: int = LIMIT) -> None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        self._limit = limit
        self._states: OrderedDict[str, str] = OrderedDict()
        self._lock = threading.Lock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._states)

    def open(self, run_id: str, state: str) -> None:
        """A save as it is scheduled: PENDING, or NOT_RETAINED when nothing durable can follow."""

        with self._lock:
            self._states[run_id] = state
            self._states.move_to_end(run_id)
            while len(self._states) > self._limit:
                self._states.popitem(last=False)

    def settle(self, run_id: str, state: str) -> None:
        """A save as it finishes. Only a PENDING record is settled: a run never opened here (another
        origin, an evicted record) stays unrecorded, and a settled state is final."""

        with self._lock:
            if self._states.get(run_id) == PENDING:
                self._states[run_id] = state

    def get(self, run_id: str) -> str | None:
        with self._lock:
            return self._states.get(run_id)


# One record for the process, like the persistence executor it reports on.
SAVE_RECEIPTS = SaveReceipts()


def unrecorded_state(*, stateless: bool, held: bool, stored: bool) -> str | None:
    """The receipt of a run whose save this process has no record of, or None for an unknown run.

    `held`: this process still holds the run. `stored`: the repository returns its detail.
    """

    if stateless:
        # A stateless repository answers from process memory: that is never a durable copy.
        return NOT_RETAINED if held or stored else None
    if stored:
        return SAVED
    # Held here, and the durable store does not return it: no durable copy is confirmed.
    return FAILED if held else None


def receipt_payload(run_id: str, state: str, checked_at: datetime) -> dict[str, str]:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "state": state,
        "checked_at_utc": checked_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
    }
