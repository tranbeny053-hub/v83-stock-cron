"""R-1 (WB3): reconciling COMMIT_UNKNOWN by an idempotent READ, never a blind duplicate write.

Plan §8.1: an unknown commit is reconciled "by idempotent read/retry logic, not blind duplicate
writes". Since W-A (migration 0017), ONE function writes the run identity, its detail, the
prediction and its snapshots in ONE transaction, and on that path the run is written nowhere else.
So reading the core back decides the whole bundle. The run exists as sent (run_id and
analysis_hash, the columns the function itself compares), and every forecast prediction id exists,
if and only if that transaction committed.

WIRED (the owner authorized the pinned crossing, 2026-10-03). The design is
.work/roadmap/phase3/wb3_s8/WB3_S8_DESIGN.md. analysis_service._reconcile_unknown_commits feeds it
the REST repository's read_core_strict: the database's own answer, or None (Unreadable). Unlike
get_run, that read never falls back to the in-memory mirror, which could "confirm" a commit that
never happened. S8 is the owner's Option 1: a NOT_SAVED is never retried.

Nothing here keeps a payload, so nothing here pretends durability (§8.1). An unknown commit that the
process does not live to reconcile stays COMMIT_UNKNOWN, honestly.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

# Plan §8.1's receipt states, as analysis_service names them (a test pins them equal; importing
# them would make the wiring circular).
RECEIPT_SAVED = "SAVED"
RECEIPT_NOT_SAVED = "NOT_SAVED"
RECEIPT_COMMIT_UNKNOWN = "COMMIT_UNKNOWN"
# The decided reasons. CONFLICT and INCOMPLETE_BUNDLE are the receipts' own NOT_SAVED reasons.
RECONCILED_COMMITTED = "RECONCILED_COMMITTED"
RECONCILED_NOT_COMMITTED = "RECONCILED_NOT_COMMITTED"
CONFLICT = "CONFLICT"
INCOMPLETE_BUNDLE = "INCOMPLETE_BUNDLE"
RECONCILE_UNREADABLE = "RECONCILE_UNREADABLE"
RECONCILE_EXPIRED = "RECONCILE_EXPIRED"
# Section 5A OOS identities keep their own write path, outside the forecast RPC.
OOS_PREFIX = "oosb-"
CAPACITY = 64
TTL_SECONDS = 3600.0
MAX_ATTEMPTS = 5


@dataclass(frozen=True)
class UnknownCommit:
    """One unknown commit's identity. Never its payload."""

    run_id: str
    analysis_hash: str
    prediction_ids: tuple[str, ...]
    first_seen: float
    attempts: int = 0


@dataclass(frozen=True)
class StoredCore:
    """A STRICT read's answer: the stored run (None when absent) and which expected predictions
    exist. Never an in-memory mirror's."""

    run: Mapping[str, object] | None
    prediction_ids: frozenset[str]


class Unreadable:
    """The strict read could not reach the database: nothing is known."""


UNREADABLE = Unreadable()


@dataclass(frozen=True)
class Decision:
    receipt: str
    reason: str
    final: bool


def unknown_commit(
    run_summary: Mapping[str, object], prediction_rows: Sequence[Mapping[str, object]], now: float
) -> UnknownCommit | None:
    """The identity to reconcile, or None: without a run id, an analysis hash and a forecast
    prediction, a read cannot decide, and the receipt stays COMMIT_UNKNOWN."""

    run_id, analysis_hash = run_summary.get("run_id"), run_summary.get("analysis_hash")
    forecast = tuple(sorted(
        str(row["prediction_id"]) for row in prediction_rows
        if row.get("prediction_id") and not str(row["prediction_id"]).startswith(OOS_PREFIX)
    ))
    if not (isinstance(run_id, str) and run_id and isinstance(analysis_hash, str)
            and analysis_hash and forecast):
        return None
    return UnknownCommit(run_id, analysis_hash, forecast, first_seen=now)


def decide(
    pending: UnknownCommit,
    stored: StoredCore | Unreadable,
    *,
    now: float,
    max_attempts: int = MAX_ATTEMPTS,
    ttl_seconds: float = TTL_SECONDS,
) -> Decision:
    """The receipt that one strict read supports. SAVED only for the run as sent and every
    forecast prediction; NOT_SAVED when the read proves the transaction did not commit."""

    if isinstance(stored, Unreadable):
        expired = pending.attempts + 1 >= max_attempts or now - pending.first_seen >= ttl_seconds
        reason = RECONCILE_EXPIRED if expired else RECONCILE_UNREADABLE
        return Decision(RECEIPT_COMMIT_UNKNOWN, reason, final=expired)
    if stored.run is None:
        return Decision(RECEIPT_NOT_SAVED, RECONCILED_NOT_COMMITTED, final=True)
    if (stored.run.get("run_id"), stored.run.get("analysis_hash")) != (
        pending.run_id, pending.analysis_hash
    ):
        return Decision(RECEIPT_NOT_SAVED, CONFLICT, final=True)
    if not set(pending.prediction_ids) <= stored.prediction_ids:
        return Decision(RECEIPT_NOT_SAVED, INCOMPLETE_BUNDLE, final=True)
    return Decision(RECEIPT_SAVED, RECONCILED_COMMITTED, final=True)


class UnknownCommits:
    """A bounded, in-memory list of unknown commits awaiting a strict read. Identities only.

    It is opportunistic, never a durability guarantee (§8.1): what it holds is lost with the
    process, and those receipts simply stay COMMIT_UNKNOWN.
    """

    def __init__(self, capacity: int = CAPACITY) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self._capacity = capacity
        self._pending: OrderedDict[str, UnknownCommit] = OrderedDict()

    def __len__(self) -> int:
        return len(self._pending)

    def add(self, commit: UnknownCommit) -> UnknownCommit | None:
        """Keep one entry per run (the earliest). Returns the oldest entry evicted to stay within
        capacity, whose receipt the caller reports as RECONCILE_EXPIRED."""

        if commit.run_id in self._pending:
            return None
        self._pending[commit.run_id] = commit
        if len(self._pending) > self._capacity:
            return self._pending.popitem(last=False)[1]
        return None

    def due(self) -> tuple[UnknownCommit, ...]:
        """Every pending entry, oldest first."""

        return tuple(self._pending.values())

    def apply(self, commit: UnknownCommit, decision: Decision) -> None:
        """A final decision removes the entry; otherwise one more attempt is counted."""

        if commit.run_id not in self._pending:
            return
        if decision.final:
            del self._pending[commit.run_id]
        else:
            self._pending[commit.run_id] = replace(
                self._pending[commit.run_id], attempts=self._pending[commit.run_id].attempts + 1
            )
