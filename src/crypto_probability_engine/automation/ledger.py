"""The automation ledger: idempotency and audit, isolated from every cohort table.

One row per authenticated, well-formed call, keyed by ``(credential_id, client_request_id)``:
- a NEW key is reserved IN_PROGRESS before any analysis starts, so a repeat can never start a
  second run;
- a repeat with the same request fingerprint REPLAYS the stored outcome (the same run, or the
  same refusal); with a different fingerprint it is a CONFLICT; while the first is still running
  it is IN_PROGRESS; an IN_PROGRESS row past its deadline plus a grace period is ABANDONED and
  closed as DEADLINE_EXCEEDED, never re-run;
- quota counts come from the same rows, computed atomically with the reservation;
- a success is recorded only while its deadline has not passed (checked inside the recording
  transaction); a late success is recorded as DEADLINE_EXCEEDED instead, so the ledger always
  says what the caller was told;
- every database operation is bounded by a transaction-scoped statement and lock timeout.

The ledger records the credential id, never its value. It is the ONLY place an automated run is
stored: nothing here reads or writes ``predictions`` or any other cohort table, and no
calibration or control reader reads this ledger (table ``automation_radar_ledger``, migration
0013). Retention: ``LEDGER_RETENTION_DAYS`` (stated; a purge is a separate owner-authorized step).
"""

from __future__ import annotations

import json
import math
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol

from crypto_probability_engine.automation.origin import AUTOMATED_RADAR

WINDOW_5MIN = timedelta(minutes=5)
WINDOW_DAY = timedelta(days=1)
ABANDON_GRACE = timedelta(seconds=60)
# Outcomes refused before any analysis started: they never count against the quota.
NON_COUNTING_OUTCOMES = frozenset({"QUOTA_EXCEEDED", "CONCURRENCY_LIMIT"})
MAX_MEMORY_ENTRIES = 10_000
RESERVE_TIMEOUT_SECONDS = 3.0
REFUSAL_RECORD_TIMEOUT_SECONDS = 3.0
MIN_TIMEOUT_SECONDS = 0.1


class LedgerUnavailable(Exception):
    """The ledger cannot be read or written; the call fails closed with 503."""


class ReservationKind(StrEnum):
    NEW = "NEW"
    REPLAY = "REPLAY"
    CONFLICT = "CONFLICT"
    IN_PROGRESS = "IN_PROGRESS"
    ABANDONED = "ABANDONED"


@dataclass(frozen=True)
class LedgerEntry:
    credential_id: str
    client_request_id: str
    request_fingerprint: str
    release_id: str
    deadline_ms: int
    received_at_utc: datetime
    state: str = "IN_PROGRESS"
    outcome_code: str | None = None
    http_status: int | None = None
    response_body: dict[str, Any] | None = None
    run_id: str | None = None
    analysis_hash: str | None = None
    evidence_hash: str | None = None
    completed_at_utc: datetime | None = None
    evidence_origin: str = AUTOMATED_RADAR


@dataclass(frozen=True)
class Reservation:
    kind: ReservationKind
    entry: LedgerEntry | None
    counted_5min: int = 0
    counted_day: int = 0
    oldest_5min: datetime | None = None
    oldest_day: datetime | None = None


@dataclass(frozen=True)
class Outcome:
    outcome_code: str
    http_status: int
    response_body: dict[str, Any]
    run_id: str | None = None
    analysis_hash: str | None = None
    evidence_hash: str | None = None


class AutomationLedger(Protocol):
    def reserve(
        self,
        *,
        credential_id: str,
        client_request_id: str,
        request_fingerprint: str,
        release_id: str,
        deadline_ms: int,
        now: datetime,
    ) -> Reservation: ...

    def complete(
        self,
        *,
        credential_id: str,
        client_request_id: str,
        outcome: Outcome,
        now: datetime,
    ) -> None: ...

    def complete_success(
        self,
        *,
        credential_id: str,
        client_request_id: str,
        outcome: Outcome,
        late_outcome: Outcome,
        deadline_at_utc: datetime,
        now: datetime,
        timeout_seconds: float,
    ) -> bool: ...


def classify_existing(
    entry: LedgerEntry, request_fingerprint: str, now: datetime
) -> ReservationKind:
    """What a repeat of an existing key means. Shared by every ledger implementation."""

    if entry.request_fingerprint != request_fingerprint:
        return ReservationKind.CONFLICT
    if entry.state == "COMPLETED":
        return ReservationKind.REPLAY
    abandon_at = entry.received_at_utc + timedelta(milliseconds=entry.deadline_ms) + ABANDON_GRACE
    return ReservationKind.ABANDONED if now >= abandon_at else ReservationKind.IN_PROGRESS


class InMemoryAutomationLedger:
    """A bounded, thread-safe ledger for tests and local runs. It is never wired in production."""

    def __init__(self, *, max_entries: int = MAX_MEMORY_ENTRIES) -> None:
        self._entries: dict[tuple[str, str], LedgerEntry] = {}
        self._lock = threading.Lock()
        self._max_entries = max_entries

    def reserve(
        self,
        *,
        credential_id: str,
        client_request_id: str,
        request_fingerprint: str,
        release_id: str,
        deadline_ms: int,
        now: datetime,
    ) -> Reservation:
        key = (credential_id, client_request_id)
        with self._lock:
            existing = self._entries.get(key)
            if existing is not None:
                return Reservation(classify_existing(existing, request_fingerprint, now), existing)
            self._prune(now)
            if len(self._entries) >= self._max_entries:
                raise LedgerUnavailable("the in-memory ledger is full")
            counted = [
                entry
                for entry in self._entries.values()
                if entry.credential_id == credential_id
                and entry.outcome_code not in NON_COUNTING_OUTCOMES
            ]
            in_5min = [e.received_at_utc for e in counted if e.received_at_utc > now - WINDOW_5MIN]
            in_day = [e.received_at_utc for e in counted if e.received_at_utc > now - WINDOW_DAY]
            entry = LedgerEntry(
                credential_id=credential_id,
                client_request_id=client_request_id,
                request_fingerprint=request_fingerprint,
                release_id=release_id,
                deadline_ms=deadline_ms,
                received_at_utc=now,
            )
            self._entries[key] = entry
            return Reservation(
                ReservationKind.NEW,
                entry,
                counted_5min=len(in_5min),
                counted_day=len(in_day),
                oldest_5min=min(in_5min, default=None),
                oldest_day=min(in_day, default=None),
            )

    def complete(
        self,
        *,
        credential_id: str,
        client_request_id: str,
        outcome: Outcome,
        now: datetime,
    ) -> None:
        key = (credential_id, client_request_id)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or entry.state != "IN_PROGRESS":
                raise LedgerUnavailable("no in-progress ledger entry to complete")
            self._entries[key] = _completed(entry, outcome, now)

    def complete_success(
        self,
        *,
        credential_id: str,
        client_request_id: str,
        outcome: Outcome,
        late_outcome: Outcome,
        deadline_at_utc: datetime,
        now: datetime,
        timeout_seconds: float,
    ) -> bool:
        del timeout_seconds  # in memory, the write itself cannot block
        key = (credential_id, client_request_id)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or entry.state != "IN_PROGRESS":
                raise LedgerUnavailable("no in-progress ledger entry to complete")
            on_time = now <= deadline_at_utc
            self._entries[key] = _completed(entry, outcome if on_time else late_outcome, now)
            return on_time

    def entries(self) -> list[LedgerEntry]:
        with self._lock:
            return list(self._entries.values())

    def _prune(self, now: datetime) -> None:
        horizon = now - WINDOW_DAY - timedelta(hours=2)
        stale = [
            key
            for key, entry in self._entries.items()
            if entry.state == "COMPLETED" and entry.received_at_utc < horizon
        ]
        for key in stale:
            del self._entries[key]


def _completed(entry: LedgerEntry, outcome: Outcome, now: datetime) -> LedgerEntry:
    return replace(
        entry,
        state="COMPLETED",
        outcome_code=outcome.outcome_code,
        http_status=outcome.http_status,
        response_body=json.loads(json.dumps(outcome.response_body)),
        run_id=outcome.run_id,
        analysis_hash=outcome.analysis_hash,
        evidence_hash=outcome.evidence_hash,
        # Never before reception, even if the wall clock stepped back.
        completed_at_utc=max(now, entry.received_at_utc),
    )


_TIMEOUT_SQL = (
    "SELECT set_config('statement_timeout', %(timeout)s, true), "
    "set_config('lock_timeout', %(timeout)s, true)"
)
_LOCK_SQL = "SELECT pg_advisory_xact_lock(hashtextextended(%(lock_key)s, 0))"
_SELECT_SQL = """
SELECT credential_id, client_request_id::text AS client_request_id, request_fingerprint,
       release_id, deadline_ms, received_at_utc, state, outcome_code, http_status,
       response_body, run_id, analysis_hash, evidence_hash, completed_at_utc, evidence_origin
  FROM public.automation_radar_ledger
 WHERE credential_id = %(credential_id)s AND client_request_id = %(client_request_id)s::uuid
   FOR UPDATE
"""
_COUNT_SQL = """
SELECT count(*) FILTER (WHERE received_at_utc > %(since_5min)s) AS counted_5min,
       count(*) AS counted_day,
       min(received_at_utc) FILTER (WHERE received_at_utc > %(since_5min)s) AS oldest_5min,
       min(received_at_utc) AS oldest_day
  FROM public.automation_radar_ledger
 WHERE credential_id = %(credential_id)s
   AND received_at_utc > %(since_day)s
   AND (outcome_code IS NULL OR outcome_code <> ALL(%(non_counting)s))
"""
_INSERT_SQL = """
INSERT INTO public.automation_radar_ledger
       (credential_id, client_request_id, request_fingerprint, evidence_origin, state,
        release_id, deadline_ms, received_at_utc)
VALUES (%(credential_id)s, %(client_request_id)s::uuid, %(request_fingerprint)s,
        %(evidence_origin)s, 'IN_PROGRESS', %(release_id)s, %(deadline_ms)s, %(received_at_utc)s)
"""
_COMPLETE_SQL = """
UPDATE public.automation_radar_ledger
   SET state = 'COMPLETED', outcome_code = %(outcome_code)s, http_status = %(http_status)s,
       response_body = %(response_body)s::jsonb, run_id = %(run_id)s,
       analysis_hash = %(analysis_hash)s, evidence_hash = %(evidence_hash)s,
       completed_at_utc = GREATEST(%(completed_at_utc)s, received_at_utc)
 WHERE credential_id = %(credential_id)s AND client_request_id = %(client_request_id)s::uuid
   AND state = 'IN_PROGRESS'
RETURNING client_request_id
"""
# The same UPDATE, applied only while the database clock is still within the deadline.
_COMPLETE_ON_TIME_SQL = _COMPLETE_SQL.replace(
    "   AND state = 'IN_PROGRESS'\n",
    "   AND state = 'IN_PROGRESS' AND clock_timestamp() <= %(deadline_at_utc)s\n",
)


class PostgresAutomationLedger:
    """The production ledger: its own short-lived psycopg connection per operation.

    Each reservation is ONE transaction holding a per-credential advisory lock, so the quota
    count and the insert are atomic even across processes. Any database failure raises
    ``LedgerUnavailable`` and the call fails closed. It needs migration 0013 applied.
    """

    def __init__(self, database_url: str | None, *, connect: Callable[..., Any] | None = None):
        self._database_url = database_url
        self._connect = connect

    def _connection(self, timeout_seconds: float):
        if not self._database_url:
            raise LedgerUnavailable("no database is configured")
        connect = self._connect
        if connect is None:
            import psycopg

            connect = psycopg.connect
        return connect(
            self._database_url,
            connect_timeout=max(1, math.ceil(timeout_seconds)),
            autocommit=False,
        )

    def reserve(
        self,
        *,
        credential_id: str,
        client_request_id: str,
        request_fingerprint: str,
        release_id: str,
        deadline_ms: int,
        now: datetime,
    ) -> Reservation:
        params = {
            "lock_key": f"ucpe.automation.ledger:{credential_id}",
            "credential_id": credential_id,
            "client_request_id": client_request_id,
            "request_fingerprint": request_fingerprint,
            "evidence_origin": AUTOMATED_RADAR,
            "release_id": release_id,
            "deadline_ms": deadline_ms,
            "received_at_utc": now,
            "since_5min": now - WINDOW_5MIN,
            "since_day": now - WINDOW_DAY,
            "non_counting": sorted(NON_COUNTING_OUTCOMES),
        }
        params["timeout"] = _timeout_text(RESERVE_TIMEOUT_SECONDS)
        try:
            with self._connection(RESERVE_TIMEOUT_SECONDS) as conn, conn.cursor() as cur:
                cur.execute(_TIMEOUT_SQL, params)
                cur.execute(_LOCK_SQL, params)
                cur.execute(_SELECT_SQL, params)
                row = cur.fetchone()
                if row is not None:
                    existing = _entry_from_row(row, cur.description)
                    conn.commit()
                    kind = classify_existing(existing, request_fingerprint, now)
                    return Reservation(kind, existing)
                cur.execute(_COUNT_SQL, params)
                counted_5min, counted_day, oldest_5min, oldest_day = cur.fetchone()
                cur.execute(_INSERT_SQL, params)
                conn.commit()
        except LedgerUnavailable:
            raise
        except Exception as exc:
            raise LedgerUnavailable("the automation ledger could not reserve") from exc
        entry = LedgerEntry(
            credential_id=credential_id,
            client_request_id=client_request_id,
            request_fingerprint=request_fingerprint,
            release_id=release_id,
            deadline_ms=deadline_ms,
            received_at_utc=now,
        )
        return Reservation(
            ReservationKind.NEW,
            entry,
            counted_5min=int(counted_5min or 0),
            counted_day=int(counted_day or 0),
            oldest_5min=oldest_5min,
            oldest_day=oldest_day,
        )

    def complete(
        self,
        *,
        credential_id: str,
        client_request_id: str,
        outcome: Outcome,
        now: datetime,
    ) -> None:
        params = {
            "credential_id": credential_id,
            "client_request_id": client_request_id,
            "outcome_code": outcome.outcome_code,
            "http_status": outcome.http_status,
            "response_body": json.dumps(outcome.response_body, sort_keys=True),
            "run_id": outcome.run_id,
            "analysis_hash": outcome.analysis_hash,
            "evidence_hash": outcome.evidence_hash,
            "completed_at_utc": now,
            "timeout": _timeout_text(REFUSAL_RECORD_TIMEOUT_SECONDS),
        }
        try:
            with self._connection(REFUSAL_RECORD_TIMEOUT_SECONDS) as conn, conn.cursor() as cur:
                cur.execute(_TIMEOUT_SQL, params)
                cur.execute(_COMPLETE_SQL, params)
                if cur.fetchone() is None:
                    raise LedgerUnavailable("no in-progress ledger entry to complete")
                conn.commit()
        except LedgerUnavailable:
            raise
        except Exception as exc:
            raise LedgerUnavailable("the automation ledger could not complete") from exc

    def complete_success(
        self,
        *,
        credential_id: str,
        client_request_id: str,
        outcome: Outcome,
        late_outcome: Outcome,
        deadline_at_utc: datetime,
        now: datetime,
        timeout_seconds: float,
    ) -> bool:
        """Record the success if the deadline holds, else DEADLINE_EXCEEDED; ONE transaction."""

        timeout = max(MIN_TIMEOUT_SECONDS, timeout_seconds)
        base = {
            "credential_id": credential_id,
            "client_request_id": client_request_id,
            "completed_at_utc": now,
            "deadline_at_utc": deadline_at_utc,
            "timeout": _timeout_text(timeout),
        }
        try:
            with self._connection(timeout) as conn, conn.cursor() as cur:
                cur.execute(_TIMEOUT_SQL, base)
                cur.execute(_COMPLETE_ON_TIME_SQL, {**base, **_outcome_params(outcome)})
                if cur.fetchone() is not None:
                    conn.commit()
                    return True
                cur.execute(_COMPLETE_SQL, {**base, **_outcome_params(late_outcome)})
                if cur.fetchone() is None:
                    raise LedgerUnavailable("no in-progress ledger entry to complete")
                conn.commit()
                return False
        except LedgerUnavailable:
            raise
        except Exception as exc:
            raise LedgerUnavailable("the automation ledger could not complete") from exc


def _outcome_params(outcome: Outcome) -> dict[str, Any]:
    return {
        "outcome_code": outcome.outcome_code,
        "http_status": outcome.http_status,
        "response_body": json.dumps(outcome.response_body, sort_keys=True),
        "run_id": outcome.run_id,
        "analysis_hash": outcome.analysis_hash,
        "evidence_hash": outcome.evidence_hash,
    }


def _timeout_text(seconds: float) -> str:
    return f"{max(1, int(seconds * 1000))}ms"


def _entry_from_row(row: Any, description: Any) -> LedgerEntry:
    names = [column.name if hasattr(column, "name") else column[0] for column in description]
    values = dict(zip(names, row, strict=True))
    body = values.get("response_body")
    if isinstance(body, str):
        body = json.loads(body)
    return LedgerEntry(
        credential_id=values["credential_id"],
        client_request_id=str(values["client_request_id"]),
        request_fingerprint=values["request_fingerprint"],
        release_id=values["release_id"],
        deadline_ms=int(values["deadline_ms"]),
        received_at_utc=values["received_at_utc"],
        state=values["state"],
        outcome_code=values["outcome_code"],
        http_status=values["http_status"],
        response_body=body,
        run_id=values["run_id"],
        analysis_hash=values["analysis_hash"],
        evidence_hash=values["evidence_hash"],
        completed_at_utc=values["completed_at_utc"],
        evidence_origin=values["evidence_origin"],
    )
