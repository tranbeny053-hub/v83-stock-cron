"""Route C's resolution-status stores (owner decisions D3 and D5): the Postgres store and its SQL,
and an in-memory twin with the same interface and semantics, for tests.

PgStatusStore uses its OWN psycopg connection for each operation, in ONE transaction that starts
with SET LOCAL statement_timeout. It never uses the pinned persistence/repository.py internals: its
due scan restates that module's pinned due query and row mapping, and tests pin both to it. The
database URL is never printed, logged or put in an error: a failure raises StatusStoreError, which
names the operation, the phase and the exception TYPE only, never the driver's message.

- preflight: Route C needs public.prediction_resolution_status (migration 0012) and the four stamp
  columns of public.predictions (migration 0011).
- fetch_due: the pinned due query with its source filter widened to stamped CROSS_PROVIDER tc-v1
  rows, and joined to the status table: a row is due with no status, or with a RETRYABLE status
  whose next_eligible_utc has passed. Ordered by horizon, then prediction_id.
- read_outcome: the stored outcome of one prediction, read back after it was saved.
- write_batch: one upsert per write, all in one transaction, each RETURNING its prediction_id. Its
  compare-and-set WHERE changes a row only while it is RETRYABLE with attempt_count one below the
  new one, so RESOLVED and QUARANTINED rows never change and a stale or concurrent writer cannot
  count an attempt twice. It returns only the writes the database applied: those that returned a
  row.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Protocol

from crypto_probability_engine.resolution.rq_v1 import (
    QUARANTINED,
    RESOLVED,
    RETRYABLE,
    ExistingStatus,
    StatusWrite,
)
from crypto_probability_engine.targets.contract_v1 import (
    CROSS_PROVIDER_SOURCE,
    STAMP_FIELDS,
    TARGET_VERSION_V1,
)

CONNECT_TIMEOUT_SECONDS = 8
SET_STATEMENT_TIMEOUT_SQL = "SET LOCAL statement_timeout = '30s'"
CONNECTED_ROLE_SQL = "SELECT current_user"

# The pinned due query's 24 columns, in its order (tests pin them to persistence/repository.py).
BASE_COLUMNS = (
    "prediction_id",
    "run_id",
    "operator_id",
    "symbol",
    "normalized_symbol",
    "timeframe",
    "horizon_bars",
    "predicted_at_utc",
    "reference_close_utc",
    "reference_price",
    "horizon_end_utc",
    "p_up_frac",
    "p_down_frac",
    "p_timeout_frac",
    "decision_band_frac",
    "model_version",
    "methodology_version",
    "calibration_status",
    "reliability_status",
    "epistemic_sufficiency",
    "gate_action",
    "data_source",
    "is_live_data",
    "cross_provider_state",
)
STAMP_COLUMNS = tuple(STAMP_FIELDS)
PREDICTION_COLUMNS = BASE_COLUMNS + STAMP_COLUMNS  # the keys of each due prediction dict
STATUS_COLUMNS = (
    "resolution_status",
    "attempt_count",
    "first_attempt_utc",
    "last_attempt_utc",
    "first_reason",
    "last_reason",
    "next_eligible_utc",
)
SCAN_COLUMNS = PREDICTION_COLUMNS + STATUS_COLUMNS
# Every column of the status table but updated_at_utc, in the table's order.
UPSERT_COLUMNS = (
    "prediction_id",
    "resolution_status",
    "attempt_count",
    "first_attempt_utc",
    "last_attempt_utc",
    "first_reason",
    "last_reason",
    "next_eligible_utc",
    "quarantined_at_utc",
    "resolved_at_utc",
    "policy_version",
    "resolver_version",
)

PREFLIGHT_SQL = """
SELECT to_regclass('public.prediction_resolution_status') IS NOT NULL AS has_status_table,
       (SELECT count(*)
          FROM pg_catalog.pg_attribute a
         WHERE a.attrelid = to_regclass('public.predictions')
           AND a.attname IN (
             'target_version', 'reference_venue', 'core_computed_at_utc', 'issued_at_utc'
           )
           AND a.attnum > 0
           AND NOT a.attisdropped) AS stamp_columns
"""

DUE_SCAN_SQL = """
SELECT p.prediction_id, p.run_id, p.operator_id, p.symbol, p.normalized_symbol,
       p.timeframe, p.horizon_bars, p.predicted_at_utc, p.reference_close_utc,
       p.reference_price, p.horizon_end_utc, p.p_up_frac, p.p_down_frac,
       p.p_timeout_frac, p.decision_band_frac, p.model_version,
       p.methodology_version, p.calibration_status, p.reliability_status,
       p.epistemic_sufficiency, p.gate_action, p.data_source, p.is_live_data,
       p.cross_provider_state,
       p.target_version, p.reference_venue, p.core_computed_at_utc, p.issued_at_utc,
       s.resolution_status, s.attempt_count, s.first_attempt_utc, s.last_attempt_utc,
       s.first_reason, s.last_reason, s.next_eligible_utc
FROM public.predictions p
LEFT JOIN public.prediction_outcomes o
  ON o.prediction_id = p.prediction_id
LEFT JOIN public.prediction_resolution_status s
  ON s.prediction_id = p.prediction_id
WHERE o.prediction_id IS NULL
  AND p.is_live_data = true
  AND p.horizon_end_utc < %(now_utc)s
  AND (p.data_source = ANY(%(venues)s)
       OR (p.data_source = 'CROSS_PROVIDER' AND p.target_version = 'tc-v1'))
  AND p.timeframe = ANY(%(timeframes)s)
  AND p.prediction_origin = ANY(%(prediction_origins)s)
  AND (s.prediction_id IS NULL
       OR (s.resolution_status = 'RETRYABLE' AND s.next_eligible_utc <= %(now_utc)s))
ORDER BY p.horizon_end_utc ASC, p.prediction_id ASC
LIMIT %(limit)s
"""

OUTCOME_READBACK_SQL = """
SELECT outcome_close_utc, realized_label, resolver_version
FROM public.prediction_outcomes
WHERE prediction_id = %(prediction_id)s
"""

STATUS_UPSERT_SQL = """
INSERT INTO public.prediction_resolution_status (
  prediction_id, resolution_status, attempt_count, first_attempt_utc, last_attempt_utc,
  first_reason, last_reason, next_eligible_utc, quarantined_at_utc, resolved_at_utc,
  policy_version, resolver_version
)
VALUES (
  %(prediction_id)s, %(resolution_status)s, %(attempt_count)s, %(first_attempt_utc)s,
  %(last_attempt_utc)s, %(first_reason)s, %(last_reason)s, %(next_eligible_utc)s,
  %(quarantined_at_utc)s, %(resolved_at_utc)s, %(policy_version)s, %(resolver_version)s
)
ON CONFLICT (prediction_id) DO UPDATE SET
  resolution_status = EXCLUDED.resolution_status,
  attempt_count = EXCLUDED.attempt_count,
  last_attempt_utc = EXCLUDED.last_attempt_utc,
  last_reason = EXCLUDED.last_reason,
  next_eligible_utc = EXCLUDED.next_eligible_utc,
  quarantined_at_utc = EXCLUDED.quarantined_at_utc,
  resolved_at_utc = EXCLUDED.resolved_at_utc,
  policy_version = EXCLUDED.policy_version,
  resolver_version = EXCLUDED.resolver_version,
  updated_at_utc = now()
WHERE prediction_resolution_status.resolution_status = 'RETRYABLE'
  AND prediction_resolution_status.attempt_count = EXCLUDED.attempt_count - 1
RETURNING prediction_id
"""

# Migration 0012's CHECK patterns, which the in-memory store enforces like PostgreSQL does.
_REASON_FORMAT = re.compile(r"(skip|error)_[a-z0-9_]{1,58}")
_POLICY_FORMAT = re.compile(r"rq-v[1-9][0-9]*")
_SQLSTATE = re.compile(r"[0-9A-Z]{5}")
_STATE_COLUMNS = {
    RETRYABLE: "next_eligible_utc",
    QUARANTINED: "quarantined_at_utc",
    RESOLVED: "resolved_at_utc",
}


@dataclass(frozen=True)
class DueScan:
    """The due predictions in query order and, separately, the status of those that have one."""

    rows: tuple[dict[str, Any], ...]
    statuses: Mapping[str, ExistingStatus]


@dataclass(frozen=True)
class StoredOutcome:
    """The three columns of a stored outcome that the outcome-conflict check compares."""

    outcome_close_utc: Any
    realized_label: Any
    resolver_version: Any


class StatusStoreError(RuntimeError):
    """A status-store operation failed. Its message never carries the driver's message, which
    can name the host, the user or the URL; only the operation, phase, type and SQLSTATE."""

    def __init__(self, operation: str, phase: str, exc: BaseException) -> None:
        sqlstate = getattr(exc, "sqlstate", None)
        known = isinstance(sqlstate, str) and _SQLSTATE.fullmatch(sqlstate) is not None
        detail = f" sqlstate={sqlstate}" if known else ""
        super().__init__(
            f"SUPABASE_POSTGRES {operation} failed: {type(exc).__name__} [{phase}]{detail}"
        )


class StatusStore(Protocol):
    def preflight(self) -> bool:
        """True when Route C's table and columns exist."""

    def fetch_due(
        self,
        now_utc: datetime,
        limit: int,
        *,
        venues: Sequence[str],
        timeframes: Sequence[str],
        prediction_origins: Sequence[str],
    ) -> DueScan:
        """The due rows, oldest horizon first, with the status of each that has one."""

    def read_outcome(self, prediction_id: str) -> StoredOutcome | None:
        """The stored outcome of ``prediction_id``, or None when there is none."""

    def write_batch(self, writes: Sequence[StatusWrite]) -> tuple[StatusWrite, ...]:
        """Upsert every write in one transaction and return those the database applied.

        A write the compare-and-set WHERE rejects (a RESOLVED or QUARANTINED row, or a stale
        attempt_count) changes nothing and is not returned. On any error, write nothing and raise.
        """


class PgStatusStore:
    """Route C's Postgres store. Each operation opens its own connection: one transaction."""

    def __init__(self, db_url: str, *, connect: Callable[..., Any] | None = None) -> None:
        self._db_url = db_url
        self._connect = connect

    def __repr__(self) -> str:
        return "PgStatusStore(<redacted>)"

    def connected_role(self) -> str:
        """The role this store's connections run as (current_user). G1's cutover evidence: the
        resolver's runs show ucpe_resolver once the owner's credential is in place."""

        with self._transaction("status identity") as cursor:
            cursor.execute(CONNECTED_ROLE_SQL)
            row = cursor.fetchone()
        return str(row[0]) if row else ""

    def preflight(self) -> bool:
        with self._transaction("status preflight") as cursor:
            cursor.execute(PREFLIGHT_SQL)
            row = cursor.fetchone()
        return row is not None and row[0] is True and row[1] == len(STAMP_COLUMNS)

    def fetch_due(
        self,
        now_utc: datetime,
        limit: int,
        *,
        venues: Sequence[str],
        timeframes: Sequence[str],
        prediction_origins: Sequence[str],
    ) -> DueScan:
        params = {
            "now_utc": now_utc,
            "venues": _text_list("venues", venues),
            "timeframes": _text_list("timeframes", timeframes),
            "prediction_origins": _text_list("prediction_origins", prediction_origins),
            "limit": max(0, int(limit)),
        }
        with self._transaction("status due scan") as cursor:
            cursor.execute(DUE_SCAN_SQL, params)
            return due_scan_from_db(cursor.fetchall())

    def read_outcome(self, prediction_id: str) -> StoredOutcome | None:
        with self._transaction("outcome readback") as cursor:
            cursor.execute(OUTCOME_READBACK_SQL, {"prediction_id": prediction_id})
            row = cursor.fetchone()
        if row is None:
            return None
        outcome_close_utc, realized_label, resolver_version = row
        return StoredOutcome(outcome_close_utc, realized_label, resolver_version)

    def write_batch(self, writes: Sequence[StatusWrite]) -> tuple[StatusWrite, ...]:
        if not writes:
            return ()
        applied: list[StatusWrite] = []
        with self._transaction("status write") as cursor:
            # One statement per row, all in this one transaction: RETURNING tells an applied upsert
            # from one the compare-and-set WHERE rejected, which executemany cannot.
            for write in writes:
                cursor.execute(STATUS_UPSERT_SQL, status_write_params(write))
                if cursor.fetchone() is not None:
                    applied.append(write)
        return tuple(applied)

    @contextmanager
    def _transaction(self, operation: str) -> Iterator[Any]:
        phase = "connect"
        connection = None
        try:
            connection = self._open()
            phase = "statement_timeout"
            with connection.cursor() as cursor:
                cursor.execute(SET_STATEMENT_TIMEOUT_SQL)
                phase = "query"
                yield cursor
            phase = "commit"
            connection.commit()
        except Exception as exc:
            if connection is not None:
                _quietly(connection.rollback)
            raise StatusStoreError(operation, phase, exc) from None
        finally:
            if connection is not None:
                _quietly(connection.close)

    def _open(self) -> Any:
        connect = self._connect
        if connect is None:
            import psycopg

            connect = psycopg.connect
        # No prepared statements, like the repository's direct connections: a transaction-mode
        # pooler can hand the next connection a backend that already holds one of the same name.
        return connect(
            self._db_url, connect_timeout=CONNECT_TIMEOUT_SECONDS, prepare_threshold=None
        )


class InMemoryStatusStore:
    """PgStatusStore's interface and semantics over in-memory rows. It never touches a database.

    ``outcomes`` maps prediction_id to an outcome row: share it with the repository whose
    save_prediction_outcome writes there. ``statuses`` maps prediction_id to the 12 upsert
    columns. write_batch applies the compare-and-set upsert and the table's CHECKs atomically.
    """

    def __init__(
        self,
        predictions: Iterable[Mapping[str, Any]] = (),
        *,
        outcomes: dict[str, Mapping[str, Any]] | None = None,
        statuses: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        self.predictions: dict[str, dict[str, Any]] = {}
        for row in predictions:
            self.add_prediction(row)
        self.outcomes = {} if outcomes is None else outcomes
        self.statuses = {str(key): dict(row) for key, row in (statuses or {}).items()}
        self.batches: list[tuple[StatusWrite, ...]] = []  # committed batches only

    def add_prediction(self, row: Mapping[str, Any]) -> None:
        self.predictions[str(row["prediction_id"])] = dict(row)

    def preflight(self) -> bool:
        return True

    def fetch_due(
        self,
        now_utc: datetime,
        limit: int,
        *,
        venues: Sequence[str],
        timeframes: Sequence[str],
        prediction_origins: Sequence[str],
    ) -> DueScan:
        now = _utc(now_utc)
        venue_set = set(_text_list("venues", venues))
        timeframe_set = set(_text_list("timeframes", timeframes))
        origin_set = set(_text_list("prediction_origins", prediction_origins))
        due = []
        for prediction_id, row in self.predictions.items():
            horizon = _utc_or_none(row.get("horizon_end_utc"))
            source = _text(row.get("data_source"))
            status = self.statuses.get(prediction_id)
            if (
                prediction_id in self.outcomes
                or row.get("is_live_data") is not True
                or horizon is None
                or not horizon < now
                or not (
                    source in venue_set
                    or (
                        source == CROSS_PROVIDER_SOURCE
                        and row.get("target_version") == TARGET_VERSION_V1
                    )
                )
                or _text(row.get("timeframe")) not in timeframe_set
                or _text(row.get("prediction_origin")) not in origin_set
                or not (
                    status is None
                    or (
                        status["resolution_status"] == RETRYABLE
                        and _utc(status["next_eligible_utc"]) <= now
                    )
                )
            ):
                continue
            due.append((horizon, prediction_id, row, status))
        due.sort(key=lambda item: (item[0], item[1]))
        selected = due[: max(0, int(limit))]
        return DueScan(
            rows=tuple(
                {key: _db_value(row.get(key)) for key in PREDICTION_COLUMNS}
                for _, _, row, _ in selected
            ),
            statuses=MappingProxyType(
                {
                    prediction_id: _existing_status(status)
                    for _, prediction_id, _, status in selected
                    if status is not None
                }
            ),
        )

    def read_outcome(self, prediction_id: str) -> StoredOutcome | None:
        row = self.outcomes.get(prediction_id)
        if row is None:
            return None
        return StoredOutcome(
            row.get("outcome_close_utc"), row.get("realized_label"), row.get("resolver_version")
        )

    def write_batch(self, writes: Sequence[StatusWrite]) -> tuple[StatusWrite, ...]:
        staged = {key: dict(row) for key, row in self.statuses.items()}
        applied: list[StatusWrite] = []
        for write in writes:
            row = status_write_params(write)
            current = staged.get(write.prediction_id)
            if current is not None:
                if (
                    current["resolution_status"] != RETRYABLE
                    or current["attempt_count"] != write.attempt_count - 1
                ):
                    continue  # the compare-and-set WHERE: the row is left as it is
                row["first_attempt_utc"] = current["first_attempt_utc"]  # never updated
                row["first_reason"] = current["first_reason"]
            _check_status_row(row)
            staged[write.prediction_id] = row
            applied.append(write)
        self.statuses.clear()
        self.statuses.update(staged)
        self.batches.append(tuple(writes))
        return tuple(applied)


def due_scan_from_db(rows: Iterable[Any]) -> DueScan:
    """Map due-scan rows like the repository maps due rows; carry the statuses separately."""

    predictions = []
    statuses: dict[str, ExistingStatus] = {}
    for row in rows:
        values = (
            {column: row[column] for column in SCAN_COLUMNS}
            if isinstance(row, Mapping)
            else dict(zip(SCAN_COLUMNS, row, strict=True))
        )
        predictions.append({key: _db_value(values[key]) for key in PREDICTION_COLUMNS})
        if values["resolution_status"] is not None:
            statuses[values["prediction_id"]] = _existing_status(values)
    return DueScan(rows=tuple(predictions), statuses=MappingProxyType(statuses))


def status_write_params(write: StatusWrite) -> dict[str, Any]:
    return {column: getattr(write, column) for column in UPSERT_COLUMNS}


def _existing_status(values: Mapping[str, Any]) -> ExistingStatus:
    return ExistingStatus(
        resolution_status=values["resolution_status"],
        attempt_count=values["attempt_count"],
        first_attempt_utc=_utc(values["first_attempt_utc"]),
        last_attempt_utc=_utc(values["last_attempt_utc"]),
        first_reason=values["first_reason"],
        last_reason=values["last_reason"],
        next_eligible_utc=_utc_or_none(values["next_eligible_utc"]),
    )


def _check_status_row(row: Mapping[str, Any]) -> None:
    """Migration 0012's CHECK constraints, for the in-memory store. Raises ValueError."""

    status = row["resolution_status"]
    checks = (
        ("prs_prediction_id_nonblank", bool((_text(row["prediction_id"]) or "").strip())),
        ("prs_status_valid", status in _STATE_COLUMNS),
        ("prs_attempt_count_positive", row["attempt_count"] >= 1),
        ("prs_attempt_chronology", row["last_attempt_utc"] >= row["first_attempt_utc"]),
        (
            "prs_reason_format",
            all(
                _REASON_FORMAT.fullmatch(_text(row[column]) or "") is not None
                for column in ("first_reason", "last_reason")
            ),
        ),
        (
            "prs_policy_version_format",
            _POLICY_FORMAT.fullmatch(_text(row["policy_version"]) or "") is not None,
        ),
        ("prs_resolver_version_nonblank", bool((_text(row["resolver_version"]) or "").strip())),
        (
            "prs_state_shape",
            status in _STATE_COLUMNS
            and all(
                (row[column] is not None) == (column == _STATE_COLUMNS[status])
                for column in _STATE_COLUMNS.values()
            ),
        ),
    )
    for name, passed in checks:
        if not passed:
            raise ValueError(f"status row violates {name}")


def _text_list(name: str, values: Sequence[str]) -> list[str]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{name} must be a collection of strings, not a single string")
    items = list(values)
    if not all(isinstance(item, str) for item in items):
        raise TypeError(f"{name} must be a collection of strings")
    return items


def _db_value(value: Any) -> Any:
    """The repository's due-row mapping: isoformat() for values that have it, else unchanged."""

    return value.isoformat() if hasattr(value, "isoformat") else value


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _utc(value: Any) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime):
        raise TypeError("not a timestamp")
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _utc_or_none(value: Any) -> datetime | None:
    try:
        return None if value is None else _utc(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _quietly(operation: Callable[[], Any]) -> None:
    try:
        operation()
    except Exception:
        pass
