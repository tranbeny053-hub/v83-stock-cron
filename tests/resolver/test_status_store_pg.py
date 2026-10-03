"""Route C's Postgres store, through a psycopg-shaped fake: its SQL and named parameters, the
row mapping pinned to the repository's, the preflight routing, one transaction per operation
(the status batch rolled back on error), and a database URL that never reaches any output."""

from __future__ import annotations

import ast
import inspect
import re
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest

from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.persistence import repository as repository_module
from crypto_probability_engine.persistence.repository import (
    InMemoryPersistenceRepository,
    SupabasePersistenceRepository,
    SupabaseRestRepository,
)
from crypto_probability_engine.resolution import rq_v1
from crypto_probability_engine.resolution import status_store as store_module
from crypto_probability_engine.resolution.rq_v1 import ExistingStatus, StatusWrite
from crypto_probability_engine.resolution.status_store import (
    BASE_COLUMNS,
    CONNECTED_ROLE_SQL,
    DUE_SCAN_SQL,
    OUTCOME_READBACK_SQL,
    PREDICTION_COLUMNS,
    PREFLIGHT_SQL,
    SET_STATEMENT_TIMEOUT_SQL,
    STATUS_COLUMNS,
    STATUS_UPSERT_SQL,
    UPSERT_COLUMNS,
    InMemoryStatusStore,
    PgStatusStore,
    StatusStoreError,
    StoredOutcome,
    due_scan_from_db,
    status_write_params,
)
from crypto_probability_engine.targets import contract_v1
from scripts import apply_migration_0012 as apply_0012
from scripts import resolve_outcomes
from tests.resolver._route_c_rows import (
    FILTERS,
    NOW,
    Clock,
    Fetch,
    db_row,
    missing,
    tc_row,
    v0_row,
)

ROOT = Path(__file__).resolve().parents[2]
URL = "postgresql://route-c-user:not-a-real-credential@db.route-c.example.invalid:6543/postgres"
URL_PARTS = ("route-c-user", "not-a-real-credential", "db.route-c.example.invalid", "postgresql://")
KWARGS = {"connect_timeout": 8, "prepare_threshold": None}
SQL = {
    "preflight": PREFLIGHT_SQL,
    "due_scan": DUE_SCAN_SQL,
    "readback": OUTCOME_READBACK_SQL,
    "upsert": STATUS_UPSERT_SQL,
}


# --------------------------------------------------------------------------- the fake driver


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.connection.log.append("cursor.close")
        return False

    def execute(self, sql, params=None):
        self.connection.log.append(("execute", sql, params))
        self.connection.maybe_fail(sql)

    def executemany(self, sql, params_seq):
        self.connection.log.append(("executemany", sql, list(params_seq)))
        self.connection.maybe_fail(sql)

    def fetchone(self):
        return self.connection.results.pop(0)

    def fetchall(self):
        return self.connection.results.pop(0)


class FakeConnection:
    """One psycopg connection: it logs every call, returns scripted results, can fail on SQL."""

    def __init__(self, *results, fail_on=None, error=None):
        self.results = list(results)
        self.fail_on = fail_on
        self.error = error
        self.log = []

    def cursor(self):
        return FakeCursor(self)

    def maybe_fail(self, sql):
        if self.fail_on is not None and self.fail_on in sql:
            raise self.error

    def commit(self):
        self.log.append("commit")

    def rollback(self):
        self.log.append("rollback")

    def close(self):
        self.log.append("close")

    @property
    def statements(self):
        return [entry for entry in self.log if isinstance(entry, tuple)]


class FakeConnect:
    """psycopg.connect: hands out the scripted connections in order, and records each call."""

    def __init__(self, *connections, error=None):
        self.connections = list(connections)
        self.error = error
        self.calls = []

    def __call__(self, conninfo, **kwargs):
        self.calls.append((conninfo, kwargs))
        if self.error is not None:
            raise self.error
        return self.connections.pop(0)


class FakeSupabase(SupabasePersistenceRepository):
    """The direct-Postgres repository TYPE, with its two resolver calls replaced: no database."""

    def __init__(self, *, status="OK"):
        super().__init__("postgresql://repository-unused.example.invalid/db")
        self.status = status
        self.saved = []

    def fetch_due_unresolved_predictions(self, *args, **kwargs):
        raise AssertionError("Route C never runs the pinned due query")

    def save_prediction_outcome(self, row):
        self.saved.append(dict(row))
        return self.status


def _flat(sql):
    return " ".join(sql.split())


def _write(pid="p1", **changes):
    write = StatusWrite(
        prediction_id=pid,
        resolution_status="RETRYABLE",
        attempt_count=2,
        first_attempt_utc=NOW - timedelta(hours=3),
        last_attempt_utc=NOW,
        first_reason="skip_terminal_bar_missing",
        last_reason="error_provider_unavailable",
        next_eligible_utc=NOW + timedelta(hours=2),
        quarantined_at_utc=None,
        resolved_at_utc=None,
        policy_version="rq-v1",
        resolver_version=resolve_outcomes.RESOLVER_VERSION,
    )
    return StatusWrite(**{**status_write_params(write), **changes})


def _store(*connections, error=None):
    connect = FakeConnect(*connections, error=error)
    return PgStatusStore(URL, connect=connect), connect


# --------------------------------------------------------------------------- the SQL


def test_the_due_scan_is_the_pinned_query_widened_joined_and_tie_broken() -> None:
    """Built from the pinned query itself: the same 24 columns and the same WHERE, with only
    the stamp and status columns, the status join, the widened source, the status condition and
    the prediction_id tie-break added."""

    class RecordingCursor:
        def execute(self, sql, params=None):
            self.sql = sql

    cursor = RecordingCursor()
    repository_module._execute_due_prediction_query(
        cursor, NOW, 50, data_sources=("BINANCE_PUBLIC",), timeframes=("4H",),
        prediction_origins=("USER_REQUESTED",),
    )
    pinned = _flat(cursor.sql)
    stamp = ", ".join(f"p.{column}" for column in contract_v1.STAMP_FIELDS)
    status = ", ".join(f"s.{column}" for column in STATUS_COLUMNS)
    replacements = (
        ("p.cross_provider_state FROM", f"p.cross_provider_state, {stamp}, {status} FROM"),
        (
            "ON o.prediction_id = p.prediction_id WHERE",
            "ON o.prediction_id = p.prediction_id LEFT JOIN public.prediction_resolution_status s"
            " ON s.prediction_id = p.prediction_id WHERE",
        ),
        (
            "AND p.data_source = ANY(%(data_sources)s)",
            "AND (p.data_source = ANY(%(venues)s) OR (p.data_source = 'CROSS_PROVIDER'"
            " AND p.target_version = 'tc-v1'))",
        ),
        (
            "AND p.prediction_origin = ANY(%(prediction_origins)s)",
            "AND p.prediction_origin = ANY(%(prediction_origins)s) AND (s.prediction_id IS NULL"
            " OR (s.resolution_status = 'RETRYABLE' AND s.next_eligible_utc <= %(now_utc)s))",
        ),
        ("ORDER BY p.horizon_end_utc ASC", "ORDER BY p.horizon_end_utc ASC, p.prediction_id ASC"),
    )
    expected = pinned
    for old, new in replacements:
        assert expected.count(old) == 1, old
        expected = expected.replace(old, new)
    assert _flat(DUE_SCAN_SQL) == expected
    assert "'CROSS_PROVIDER'" == f"'{contract_v1.CROSS_PROVIDER_SOURCE}'"
    assert "'tc-v1'" == f"'{contract_v1.TARGET_VERSION_V1}'"


def test_the_due_scan_has_the_adjudicated_fragments() -> None:
    flat = _flat(DUE_SCAN_SQL)
    for fragment in (
        "(p.data_source = ANY(%(venues)s) OR (p.data_source = 'CROSS_PROVIDER' AND "
        "p.target_version = 'tc-v1'))",
        "LEFT JOIN public.prediction_outcomes o ON o.prediction_id = p.prediction_id",
        "WHERE o.prediction_id IS NULL AND p.is_live_data = true AND p.horizon_end_utc < "
        "%(now_utc)s",
        "p.timeframe = ANY(%(timeframes)s)",
        "p.prediction_origin = ANY(%(prediction_origins)s)",
        "LEFT JOIN public.prediction_resolution_status s ON s.prediction_id = p.prediction_id",
        "(s.prediction_id IS NULL OR (s.resolution_status = 'RETRYABLE' AND "
        "s.next_eligible_utc <= %(now_utc)s))",
        "ORDER BY p.horizon_end_utc ASC, p.prediction_id ASC LIMIT %(limit)s",
    ):
        assert flat.count(fragment) == 1, fragment
    selected = flat[len("SELECT ") : flat.index(" FROM ")].split(", ")
    assert selected == [
        *(f"p.{column}" for column in PREDICTION_COLUMNS),
        *(f"s.{column}" for column in STATUS_COLUMNS),
    ]


def test_the_upsert_is_a_compare_and_set_that_never_touches_the_first_attempt() -> None:
    flat = _flat(STATUS_UPSERT_SQL)
    assert UPSERT_COLUMNS == tuple(
        name for name in apply_0012.EXPECTED_COLUMN_NAMES if name != "updated_at_utc"
    )
    assert flat.startswith(
        f"INSERT INTO public.prediction_resolution_status ( {', '.join(UPSERT_COLUMNS)} ) "
        f"VALUES ( {', '.join(f'%({column})s' for column in UPSERT_COLUMNS)} )"
    )
    updated = (
        "resolution_status", "attempt_count", "last_attempt_utc", "last_reason",
        "next_eligible_utc", "quarantined_at_utc", "resolved_at_utc", "policy_version",
        "resolver_version",
    )
    set_clause = ", ".join(f"{column} = EXCLUDED.{column}" for column in updated)
    assert flat.endswith(
        f"ON CONFLICT (prediction_id) DO UPDATE SET {set_clause}, updated_at_utc = now() "
        "WHERE prediction_resolution_status.resolution_status = 'RETRYABLE' "
        "AND prediction_resolution_status.attempt_count = EXCLUDED.attempt_count - 1 "
        "RETURNING prediction_id"
    )
    do_update = flat[flat.index("DO UPDATE") :]
    assert "first_attempt_utc" not in do_update and "first_reason" not in do_update


def test_the_preflight_asks_for_the_status_table_and_every_stamp_column() -> None:
    flat = _flat(PREFLIGHT_SQL)
    assert "to_regclass('public.prediction_resolution_status') IS NOT NULL" in flat
    assert "a.attrelid = to_regclass('public.predictions')" in flat
    assert "AND a.attnum > 0 AND NOT a.attisdropped" in flat
    named = re.findall(r"'(\w+)'", flat[flat.index("a.attname IN") :])
    migration_0011 = (ROOT / "migrations/0011_prediction_target_provenance.sql").read_text()
    added = re.findall(r"ADD COLUMN IF NOT EXISTS (\w+)", migration_0011)
    assert tuple(named) == tuple(added) == contract_v1.STAMP_FIELDS


def test_the_readback_reads_the_three_compared_columns() -> None:
    assert _flat(OUTCOME_READBACK_SQL) == (
        "SELECT outcome_close_utc, realized_label, resolver_version "
        "FROM public.prediction_outcomes WHERE prediction_id = %(prediction_id)s"
    )


@pytest.mark.parametrize("name", sorted(SQL))
def test_every_statement_uses_named_parameters_only(name) -> None:
    sql = SQL[name]
    assert "%" not in re.sub(r"%\(\w+\)s", "", sql), name
    assert "%s" not in sql
    assert "%" not in SET_STATEMENT_TIMEOUT_SQL


# --------------------------------------------------------------------------- the row mapping


def test_the_24_base_keys_are_the_repository_s_due_row_keys_in_order() -> None:
    mapped = repository_module._prediction_row_from_db(tuple(range(24)))
    assert tuple(mapped) == BASE_COLUMNS
    assert PREDICTION_COLUMNS == BASE_COLUMNS + contract_v1.STAMP_FIELDS


def test_a_due_row_maps_exactly_like_the_repository_and_carries_its_status_apart() -> None:
    row = tc_row("tc-1")
    status = {
        "resolution_status": "RETRYABLE",
        "attempt_count": 2,
        "first_attempt_utc": datetime(2026, 10, 1, 9, 17, tzinfo=timezone(timedelta(hours=7))),
        "last_attempt_utc": NOW - timedelta(hours=1),
        "first_reason": "error_provider_unavailable",
        "last_reason": "skip_terminal_bar_missing",
        "next_eligible_utc": NOW - timedelta(minutes=1),
    }
    values = db_row(row, status)
    assert isinstance(values[BASE_COLUMNS.index("reference_price")], Decimal)
    store, _ = _store(FakeConnection([values]))

    scan = store.fetch_due(NOW, 1000, **FILTERS)

    (mapped,) = scan.rows
    expected = repository_module._prediction_row_from_db(values[:24])
    for column, value in zip(contract_v1.STAMP_FIELDS, values[24:28], strict=True):
        expected[column] = value.isoformat() if hasattr(value, "isoformat") else value
    assert mapped == expected
    assert tuple(mapped) == PREDICTION_COLUMNS
    assert not set(STATUS_COLUMNS) & set(mapped)  # the status never rides in the prediction
    assert dict(scan.statuses) == {
        "tc-1": ExistingStatus(
            resolution_status="RETRYABLE",
            attempt_count=2,
            first_attempt_utc=datetime(2026, 10, 1, 2, 17, tzinfo=UTC),
            last_attempt_utc=NOW - timedelta(hours=1),
            first_reason="error_provider_unavailable",
            last_reason="skip_terminal_bar_missing",
            next_eligible_utc=NOW - timedelta(minutes=1),
        )
    }
    assert contract_v1.classify_row(mapped) == contract_v1.CLASS_TC_V1  # DB shape still tc-v1


def test_a_due_row_without_a_status_has_no_status_entry() -> None:
    scan = due_scan_from_db([db_row(v0_row("v0-1"))])

    assert [row["prediction_id"] for row in scan.rows] == ["v0-1"]
    assert dict(scan.statuses) == {}
    assert contract_v1.classify_row(scan.rows[0]) == contract_v1.CLASS_V0_LEGACY


def test_a_row_of_the_wrong_width_is_refused() -> None:
    with pytest.raises(ValueError):
        due_scan_from_db([db_row(v0_row("v0-1"))[:-1]])


# --------------------------------------------------------------------------- transactions


def test_each_operation_is_its_own_connection_and_transaction() -> None:
    preflight = FakeConnection((True, 4))
    scan = FakeConnection([])
    readback = FakeConnection(None)
    store, connect = _store(preflight, scan, readback)

    assert store.preflight() is True
    assert store.fetch_due(NOW, 7, **FILTERS).rows == ()
    assert store.read_outcome("p1") is None

    assert connect.calls == [(URL, KWARGS)] * 3
    scan_params = {"now_utc": NOW, "limit": 7, **{key: list(v) for key, v in FILTERS.items()}}
    for connection, sql, params in (
        (preflight, PREFLIGHT_SQL, None),
        (scan, DUE_SCAN_SQL, scan_params),
        (readback, OUTCOME_READBACK_SQL, {"prediction_id": "p1"}),
    ):
        assert connection.log == [
            ("execute", SET_STATEMENT_TIMEOUT_SQL, None),
            ("execute", sql, params),
            "cursor.close",
            "commit",
            "close",
        ]
    assert SET_STATEMENT_TIMEOUT_SQL == "SET LOCAL statement_timeout = '30s'"


@pytest.mark.parametrize(
    ("row", "ready"),
    [((True, 4), True), ((False, 4), False), ((True, 3), False), ((True, 0), False), (None, False)],
)
def test_the_preflight_needs_the_table_and_all_four_columns(row, ready) -> None:
    store, _ = _store(FakeConnection(row))

    assert store.preflight() is ready


def test_the_readback_returns_the_stored_columns() -> None:
    close = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    store, _ = _store(FakeConnection((close, "UP", "resolver-v1-wave4b2")))

    assert store.read_outcome("p1") == StoredOutcome(close, "UP", "resolver-v1-wave4b2")


def test_the_status_batch_is_one_transaction_and_returns_only_the_applied_writes() -> None:
    # RETURNING yields a row for each applied upsert and none for one the compare-and-set WHERE
    # rejects: here "b" is rejected, so only "a" and "c" count as written.
    connection = FakeConnection(("a",), None, ("c",))
    store, connect = _store(connection)
    writes = [
        _write("a"),
        _write(
            "b", resolution_status="QUARANTINED", next_eligible_utc=None, quarantined_at_utc=NOW
        ),
        _write("c", resolution_status="RESOLVED", next_eligible_utc=None, resolved_at_utc=NOW),
    ]

    applied = store.write_batch(writes)

    assert applied == (writes[0], writes[2])
    assert connect.calls == [(URL, KWARGS)]
    params = [status_write_params(write) for write in writes]
    assert connection.log == [
        ("execute", SET_STATEMENT_TIMEOUT_SQL, None),
        *(("execute", STATUS_UPSERT_SQL, param) for param in params),
        "cursor.close",
        "commit",
        "close",
    ]
    assert all(tuple(param) == UPSERT_COLUMNS for param in params)
    assert not any(entry[0] == "executemany" for entry in connection.statements)


def test_a_failing_batch_is_rolled_back_and_its_error_names_no_url() -> None:
    error = psycopg.errors.CheckViolation(f"new row violates check; conninfo {URL}")
    connection = FakeConnection(fail_on="INSERT INTO", error=error)
    store, _ = _store(connection)

    with pytest.raises(StatusStoreError) as raised:
        store.write_batch([_write("a"), _write("b")])

    assert "commit" not in connection.log
    assert connection.log[-2:] == ["rollback", "close"]
    message = str(raised.value)
    assert message == (
        "SUPABASE_POSTGRES status write failed: CheckViolation [query] sqlstate=23514"
    )
    assert raised.value.__cause__ is None and raised.value.__suppress_context__
    assert not any(part in message for part in URL_PARTS)


def test_an_empty_batch_opens_no_connection() -> None:
    store, connect = _store()

    assert store.write_batch([]) == ()

    assert connect.calls == []


@pytest.mark.parametrize(
    ("connections", "error", "phase"),
    [
        ((), psycopg.OperationalError(f"connection to {URL} failed"), "connect"),
        (
            (FakeConnection(fail_on="SET LOCAL", error=RuntimeError(URL)),),
            None,
            "statement_timeout",
        ),
        ((FakeConnection(fail_on="to_regclass", error=RuntimeError(URL)),), None, "query"),
    ],
)
def test_a_store_error_names_the_phase_and_never_the_url(connections, error, phase) -> None:
    store, _ = _store(*connections, error=error)

    with pytest.raises(StatusStoreError) as raised:
        store.preflight()

    assert f"[{phase}]" in str(raised.value)
    assert not any(part in str(raised.value) for part in URL_PARTS)
    assert not any(part in repr(store) for part in URL_PARTS)
    for connection in connections:
        assert connection.log[-2:] == ["rollback", "close"]


# --------------------------------------------------------------------------- preflight routing


def _settings(db_url=URL):
    return Settings(**{"supabase_db_url": db_url})


@pytest.mark.parametrize(
    ("script", "connect_error", "route"),
    [
        ((FakeConnection((True, 4)),), None, "active"),
        ((FakeConnection((False, 4)),), None, "absent"),
        ((FakeConnection((True, 3)),), None, "absent"),
        ((), psycopg.OperationalError(f"could not connect: {URL}"), "error"),
        (
            (FakeConnection(fail_on="SET LOCAL", error=psycopg.errors.QueryCanceled()),),
            None,
            "error",
        ),
    ],
)
def test_route_c_only_when_direct_postgres_passes_the_preflight(script, connect_error, route):
    connect = FakeConnect(*script, error=connect_error)

    store, state = resolve_outcomes.build_status_store(
        _settings(), FakeSupabase(), connect=connect
    )

    assert state == route
    assert isinstance(store, PgStatusStore) if route == "active" else store is None
    assert connect.calls == [(URL, KWARGS)]


@pytest.mark.parametrize("kind", ["memory", "rest", "postgres-without-url"])
def test_rest_and_in_memory_repositories_are_always_legacy_without_a_connection(kind) -> None:
    connect = FakeConnect(FakeConnection((True, 4)))
    repository = {
        "memory": InMemoryPersistenceRepository,
        "rest": lambda: SupabaseRestRepository("https://rest.example.invalid", "synthetic-key"),
        "postgres-without-url": FakeSupabase,
    }[kind]()
    settings = _settings(None if kind == "postgres-without-url" else URL)

    try:
        routed = resolve_outcomes.build_status_store(settings, repository, connect=connect)
    finally:
        close = getattr(repository, "close", None)
        if callable(close):
            close()

    assert routed == (None, "absent")
    assert connect.calls == []


# --------------------------------------------------------------------------- main(), end to end


def _run_main(monkeypatch, capsys, connect, repository, *, fetch=None, argv=("--limit", "50")):
    real = resolve_outcomes.resolve_due_predictions

    def with_fakes(repo, **kwargs):
        return real(repo, now_utc=NOW, fetch_candles=fetch or Fetch(), monotonic=Clock(), **kwargs)

    monkeypatch.setenv("SUPABASE_DB_URL", URL)
    monkeypatch.setattr(psycopg, "connect", connect)
    monkeypatch.setattr(resolve_outcomes, "build_resolver_repository", lambda settings: repository)
    monkeypatch.setattr(resolve_outcomes, "resolve_due_predictions", with_fakes)
    code = resolve_outcomes.main(list(argv))
    output = capsys.readouterr()
    return code, output.out.splitlines(), output.out + output.err


def _outcome_readback(repository, pid):
    saved = next(row for row in repository.saved if row["prediction_id"] == pid)
    close = datetime.fromisoformat(saved["outcome_close_utc"].replace("Z", "+00:00"))
    return (close, saved["realized_label"], saved["resolver_version"])


def test_a_route_c_run_through_the_postgres_store(monkeypatch, capsys) -> None:
    tc = tc_row("tc-okx")
    stuck = v0_row("v0-binance")
    status = {
        "resolution_status": "RETRYABLE",
        "attempt_count": 1,
        "first_attempt_utc": NOW - timedelta(hours=2),
        "last_attempt_utc": NOW - timedelta(hours=2),
        "first_reason": "skip_terminal_bar_missing",
        "last_reason": "skip_terminal_bar_missing",
        "next_eligible_utc": NOW - timedelta(hours=1),
    }
    repository = FakeSupabase()
    readback = FakeConnection()
    batch = FakeConnection(("v0-binance",))  # RETURNING: the one upsert was applied
    connect = FakeConnect(
        FakeConnection((True, 4)),
        FakeConnection(("ucpe_resolver",)),  # G1: the run's role, by name
        FakeConnection([db_row(stuck, status), db_row(tc)]),
        readback,
        batch,
    )
    fetch = Fetch(by_symbol={"v0-binance": missing})
    original_execute = FakeCursor.execute

    def execute(self, sql, params=None):  # the readback returns what the repository saved
        original_execute(self, sql, params)
        if self.connection is readback and sql == OUTCOME_READBACK_SQL:
            readback.results.append(_outcome_readback(repository, params["prediction_id"]))

    monkeypatch.setattr(FakeCursor, "execute", execute)

    code, lines, everything = _run_main(monkeypatch, capsys, connect, repository, fetch=fetch)

    assert code == 0
    assert lines[0] == (
        "resolved_outcomes repository=SUPABASE_POSTGRES limit=50 "
        "due=2 resolved=1 skipped=1 failed=0"
    )
    assert lines[1].endswith(
        " route=c status_store=active status_written=1 status_quarantined=0 "
        "status_resolved=0 status_outage_suppressed=0 status_error=0"
    )
    assert [(w.provider, w.data_source) for w in fetch.windows] == [
        ("binance", "BINANCE_PUBLIC"),
        ("okx", "OKX_PUBLIC"),
    ]
    assert [row["data_source"] for row in repository.saved] == ["OKX_PUBLIC"]
    assert connect.calls == [(URL, KWARGS)] * 5
    assert "resolver_identity role=ucpe_resolver" in everything
    upserts = [entry for entry in batch.statements if entry[1] == STATUS_UPSERT_SQL]
    assert [entry[0] for entry in upserts] == ["execute"]
    assert [entry[2] for entry in upserts] == [
        status_write_params(
            StatusWrite(
                prediction_id="v0-binance",
                resolution_status="RETRYABLE",
                attempt_count=2,
                first_attempt_utc=NOW - timedelta(hours=2),
                last_attempt_utc=NOW,
                first_reason="skip_terminal_bar_missing",
                last_reason="skip_terminal_bar_missing",
                next_eligible_utc=NOW + timedelta(hours=2),
                quarantined_at_utc=None,
                resolved_at_utc=None,
                policy_version=rq_v1.POLICY_VERSION,
                resolver_version=resolve_outcomes.RESOLVER_VERSION,
            )
        )
    ]
    assert batch.log[-2:] == ["commit", "close"]
    assert not any(part in everything for part in URL_PARTS)


def test_a_failed_status_batch_exits_1_with_failed_0_and_writes_nothing(monkeypatch, capsys):
    batch = FakeConnection(fail_on="INSERT INTO", error=psycopg.errors.SerializationFailure(URL))
    connect = FakeConnect(
        FakeConnection((True, 4)),
        FakeConnection(("ucpe_resolver",)),
        FakeConnection([db_row(v0_row("v0-binance"))]),
        batch,
    )
    fetch = Fetch(default=missing)

    code, lines, everything = _run_main(monkeypatch, capsys, connect, FakeSupabase(), fetch=fetch)

    assert code == 1
    assert lines[0].endswith("due=1 resolved=0 skipped=1 failed=0")
    assert "failed=" not in lines[1]
    assert lines[1].endswith(
        " route=c status_store=active status_written=0 status_quarantined=0 "
        "status_resolved=0 status_outage_suppressed=0 status_error=1"
    )
    assert "commit" not in batch.log and batch.log[-2:] == ["rollback", "close"]
    assert not any(part in everything for part in URL_PARTS)


def test_a_due_scan_failure_prints_one_line_without_the_url(monkeypatch, capsys) -> None:
    failing = FakeConnection(
        fail_on="FROM public.predictions p",
        error=psycopg.OperationalError(f"server closed the connection: {URL}"),
    )
    connect = FakeConnect(FakeConnection((True, 4)), FakeConnection(("postgres",)), failing)

    code, lines, everything = _run_main(monkeypatch, capsys, connect, FakeSupabase())

    assert code == 1
    assert lines == [
        "resolved_outcomes repository=SUPABASE_POSTGRES limit=50 due=0 resolved=0 skipped=0 "
        "failed=1 error=StatusStoreError: SUPABASE_POSTGRES status due scan failed: "
        "OperationalError [query]"
    ]
    assert "resolver_identity role=postgres" in everything, "before the cutover: the owner"
    assert not any(part in everything for part in URL_PARTS)


def test_a_preflight_error_is_not_fatal_and_takes_the_legacy_path(monkeypatch, capsys) -> None:
    class LegacyPostgres(FakeSupabase):
        def fetch_due_unresolved_predictions(self, now_utc, limit, **filters):
            self.due = (limit, filters)
            return []

    repository = LegacyPostgres()
    connect = FakeConnect(error=psycopg.OperationalError(f"could not translate host {URL}"))

    code, lines, everything = _run_main(monkeypatch, capsys, connect, repository)

    assert code == 0
    assert lines[1].endswith(
        " route=legacy status_store=error status_written=0 status_quarantined=0 "
        "status_resolved=0 status_outage_suppressed=0 status_error=0"
    )
    assert repository.due == (
        1000,
        {
            "data_sources": ("BINANCE_PUBLIC", "OKX_PUBLIC"),
            "timeframes": ("15m", "1D", "1H", "1W", "4H"),
            "prediction_origins": ("USER_REQUESTED",),
        },
    )
    assert not any(part in everything for part in URL_PARTS)


def test_the_in_memory_twin_has_the_same_interface_and_the_table_s_checks() -> None:
    for name in ("preflight", "fetch_due", "read_outcome", "write_batch"):
        assert inspect.signature(getattr(InMemoryStatusStore, name)) == inspect.signature(
            getattr(PgStatusStore, name)
        ), name
    (reason,) = apply_0012.EXPECTED_CONSTRAINTS["prs_reason_format"][2]
    (policy,) = apply_0012.EXPECTED_CONSTRAINTS["prs_policy_version_format"][2]
    assert f"^{store_module._REASON_FORMAT.pattern}$" == reason
    assert f"^{store_module._POLICY_FORMAT.pattern}$" == policy
    assert set(store_module._STATE_COLUMNS) == apply_0012.STATUSES


def test_the_store_modules_never_import_the_pinned_repository() -> None:
    for module in (store_module, rq_v1):
        source = Path(module.__file__).read_text(encoding="utf-8")
        imported = {
            node.module if isinstance(node, ast.ImportFrom) else alias.name
            for node in ast.walk(ast.parse(source))
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        assert not [name for name in imported if name and ".persistence" in name], module
        assert "_prediction_row_from_db" not in source
        assert "_execute_due_prediction_query" not in source


# --------------------------------------------------------------------------- G1: the run's role


def test_the_store_reads_its_role_by_name_in_one_bounded_transaction() -> None:
    connection = FakeConnection(("ucpe_resolver",))
    connect = FakeConnect(connection)

    assert PgStatusStore(URL, connect=connect).connected_role() == "ucpe_resolver"
    assert CONNECTED_ROLE_SQL == "SELECT current_user"
    assert [entry[1] for entry in connection.statements] == [
        SET_STATEMENT_TIMEOUT_SQL, CONNECTED_ROLE_SQL,
    ]
    assert connection.log[-2:] == ["commit", "close"]
    assert connect.calls == [(URL, KWARGS)]


def test_a_role_read_that_fails_names_no_url() -> None:
    connect = FakeConnect(error=psycopg.OperationalError(f"could not connect: {URL}"))

    with pytest.raises(StatusStoreError) as raised:
        PgStatusStore(URL, connect=connect).connected_role()
    assert not any(part in str(raised.value) for part in URL_PARTS)


@pytest.mark.parametrize(
    ("store", "printed"),
    [
        (None, "n/a"),
        (object(), "n/a"),
        (type("Store", (), {"connected_role": lambda self: "ucpe_resolver"})(), "ucpe_resolver"),
        (type("Store", (), {"connected_role": lambda self: "postgres"})(), "postgres"),
        (type("Store", (), {"connected_role": lambda self: 1 / 0})(), "error"),
        (type("Store", (), {"connected_role": lambda self: "x; select 1"})(), "error"),
        (type("Store", (), {"connected_role": lambda self: URL})(), "error"),
        (type("Store", (), {"connected_role": lambda self: None})(), "error"),
    ],
    ids=["no-store", "legacy-store", "resolver", "owner", "raises", "not-a-name", "a-url",
         "none"],
)
def test_the_resolver_prints_only_a_plain_role_name(store, printed) -> None:
    assert resolve_outcomes.connected_role(store) == printed
