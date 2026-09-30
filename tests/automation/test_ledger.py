"""Idempotency, accounting, and transactional PostgreSQL behavior without a database."""

import json
import re
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path

import pytest

from crypto_probability_engine.automation import ledger as module
from crypto_probability_engine.automation.ledger import (
    InMemoryAutomationLedger,
    LedgerEntry,
    LedgerUnavailable,
    Outcome,
    PostgresAutomationLedger,
    ReservationKind,
)
from tests.automation.conftest import CREDENTIAL_ID, request_body, utc

NOW = utc(2026, 9, 30)
ARGS = {
    "credential_id": CREDENTIAL_ID,
    "client_request_id": request_body()["client_request_id"],
    "request_fingerprint": "sha256:" + "a" * 64,
    "release_id": "UCPE-SYNTHETIC",
    "deadline_ms": 5000,
    "now": NOW,
}
OUTCOME = Outcome("ANALYSIS_FAILED", 503, {"synthetic": "failure"})


def reserve(ledger, **overrides):
    return ledger.reserve(**(ARGS | overrides))


def complete(ledger, *, key=ARGS["client_request_id"], outcome=OUTCOME, now=NOW):
    ledger.complete(credential_id=CREDENTIAL_ID, client_request_id=key, outcome=outcome, now=now)


def test_new_completed_replay_and_conflict():
    ledger = InMemoryAutomationLedger()
    assert reserve(ledger).kind is ReservationKind.NEW
    complete(ledger)
    replay = reserve(ledger)
    assert replay.kind is ReservationKind.REPLAY
    assert replay.entry.response_body == OUTCOME.response_body
    assert replay.entry.state == "COMPLETED"
    assert replay.entry.outcome_code == OUTCOME.outcome_code
    assert reserve(ledger, request_fingerprint="sha256:" + "b" * 64).kind is (
        ReservationKind.CONFLICT
    )
    assert len(ledger.entries()) == 1


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, ReservationKind.IN_PROGRESS),
        (64.999, ReservationKind.IN_PROGRESS),
        (65, ReservationKind.ABANDONED),
        (66, ReservationKind.ABANDONED),
    ],
)
def test_deadline_plus_grace_classification(seconds, expected):
    ledger = InMemoryAutomationLedger()
    reserve(ledger)
    assert reserve(ledger, now=NOW + timedelta(seconds=seconds)).kind is expected


def test_conflict_outranks_in_progress_and_abandonment():
    ledger = InMemoryAutomationLedger()
    reserve(ledger)
    for when in (NOW, NOW + timedelta(days=1)):
        assert reserve(ledger, request_fingerprint="different", now=when).kind is (
            ReservationKind.CONFLICT
        )


def test_counts_exclude_refusals_other_credentials_and_window_boundaries():
    ledger = InMemoryAutomationLedger()
    # Insert chronologically so pruning cannot erase a younger completed sample.
    cases = [
        ("old", 86401, None),
        ("day-boundary", 86400, None),
        ("daily", 86399, "ANALYSIS_FAILED"),
        ("five-boundary", 300, None),
        ("five", 299, "ANALYSIS_FAILED"),
        ("quota", 100, "QUOTA_EXCEEDED"),
        ("busy", 50, "CONCURRENCY_LIMIT"),
        ("pending", 1, None),
    ]
    for key, age, code in cases:
        when = NOW - timedelta(seconds=age)
        reserve(ledger, client_request_id=key, now=when)
        if code:
            complete(ledger, key=key, outcome=Outcome(code, 503, {}), now=when)
    reserve(ledger, credential_id="other-radar", client_request_id="other")
    counted = reserve(ledger, client_request_id="new")
    assert (counted.counted_5min, counted.counted_day) == (2, 4)
    assert counted.oldest_5min == NOW - timedelta(seconds=299)
    assert counted.oldest_day == NOW - timedelta(seconds=86399)


def test_empty_counts_have_no_oldest_instant():
    result = reserve(InMemoryAutomationLedger())
    assert (result.counted_5min, result.counted_day) == (0, 0)
    assert result.oldest_5min is result.oldest_day is None


@pytest.mark.parametrize("known", [True, False])
def test_completion_requires_existing_in_progress_row(known):
    ledger = InMemoryAutomationLedger()
    if known:
        reserve(ledger)
        complete(ledger)
    with pytest.raises(LedgerUnavailable):
        complete(ledger)


def test_capacity_fails_closed_without_evicting_active_rows():
    ledger = InMemoryAutomationLedger(max_entries=1)
    reserve(ledger)
    with pytest.raises(LedgerUnavailable):
        reserve(ledger, client_request_id="new", now=NOW + timedelta(days=3))
    assert len(ledger.entries()) == 1
    assert ledger.entries()[0].state == "IN_PROGRESS"


def test_prune_only_drops_old_completed_rows():
    ledger = InMemoryAutomationLedger()
    old = NOW - timedelta(hours=27)
    for key in ("old-done", "old-pending"):
        reserve(ledger, client_request_id=key, now=old)
    complete(ledger, key="old-done", now=old)
    for key, age in (("grace-boundary", 26), ("within-day", 23)):
        when = NOW - timedelta(hours=age)
        reserve(ledger, client_request_id=key, now=when)
        complete(ledger, key=key, now=when)
    reserve(ledger, client_request_id="new")
    assert {e.client_request_id for e in ledger.entries()} == {
        "old-pending",
        "grace-boundary",
        "within-day",
        "new",
    }


class FakeDatabase:
    """Minimal context-managed connection/cursor; all effects are recorded in memory."""

    def __init__(self, rows=(), *, description=(), fail=None):
        self.rows = iter(rows)
        self.description = description
        self.fail = fail
        self.events = []
        self.statements = []
        self.connect_calls = []

    def connect(self, *args, **kwargs):
        self.connect_calls.append((args, kwargs))
        if self.fail == "connect":
            raise RuntimeError("synthetic connection failure")
        return self

    def __enter__(self):
        self.events.append("enter")
        return self

    def __exit__(self, *args):
        self.events.append("exit")

    def cursor(self):
        return self

    def execute(self, sql, params):
        self.statements.append((sql, dict(params)))
        self.events.append("execute")
        if self.fail == len(self.statements):
            raise RuntimeError("synthetic statement failure")

    def fetchone(self):
        if self.fail == "fetch":
            raise RuntimeError("synthetic fetch failure")
        return next(self.rows)

    def commit(self):
        self.events.append("commit")
        if self.fail == "commit":
            raise RuntimeError("synthetic commit failure")

    def ledger(self):
        # This sentinel is consumed only by the fake connect callable.
        return PostgresAutomationLedger("synthetic-offline-database", connect=self.connect)


def test_postgres_reserves_atomically_in_one_committed_transaction():
    oldest_five = NOW - timedelta(seconds=20)
    oldest_day = NOW - timedelta(hours=2)
    db = FakeDatabase([None, (2, 8, oldest_five, oldest_day)])
    result = reserve(db.ledger())
    assert result.kind is ReservationKind.NEW
    assert (result.counted_5min, result.counted_day) == (2, 8)
    assert (result.oldest_5min, result.oldest_day) == (oldest_five, oldest_day)
    assert len(db.connect_calls) == 1
    assert db.connect_calls[0][1] == {"connect_timeout": 5, "autocommit": False}
    assert db.events == ["enter", "enter", *["execute"] * 4, "commit", "exit", "exit"]
    sql = [" ".join(statement.split()) for statement, _ in db.statements]
    assert "pg_advisory_xact_lock" in sql[0]
    assert sql[1].startswith("SELECT credential_id,") and sql[1].endswith("FOR UPDATE")
    assert sql[2].startswith("SELECT count(*) FILTER")
    assert sql[3].startswith("INSERT INTO public.automation_radar_ledger")
    for _, params in db.statements:
        assert params["credential_id"] == CREDENTIAL_ID
        assert params["client_request_id"] == ARGS["client_request_id"]
        assert params["request_fingerprint"] == ARGS["request_fingerprint"]
        assert params["since_5min"] == NOW - timedelta(minutes=5)
        assert params["since_day"] == NOW - timedelta(days=1)
        assert set(params["non_counting"]) == {"QUOTA_EXCEEDED", "CONCURRENCY_LIMIT"}
        assert params["evidence_origin"] == "AUTOMATED_RADAR"
    assert "outcome_code <> ALL(%(non_counting)s)" in sql[2]


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({}, ReservationKind.IN_PROGRESS),
        ({"request_fingerprint": "different"}, ReservationKind.CONFLICT),
        ({"received_at_utc": NOW - timedelta(minutes=2)}, ReservationKind.ABANDONED),
        (
            {
                "state": "COMPLETED",
                "outcome_code": "ANALYSIS_FAILED",
                "http_status": 503,
                "response_body": '{"synthetic": "recorded"}',
            },
            ReservationKind.REPLAY,
        ),
    ],
)
def test_postgres_existing_row_classification(changes, expected):
    entry = LedgerEntry(**{k: v for k, v in ARGS.items() if k != "now"}, received_at_utc=NOW)
    values = asdict(entry) | changes
    db = FakeDatabase([tuple(values.values())], description=[(name,) for name in values])
    result = reserve(db.ledger())
    assert result.kind is expected
    assert len(db.statements) == 2 and db.events.count("commit") == 1
    if expected is ReservationKind.REPLAY:
        assert result.entry.response_body == {"synthetic": "recorded"}


@pytest.mark.parametrize("failure", ["connect", 1, 2, 3, 4, "fetch", "commit"])
def test_postgres_reserve_db_errors_fail_closed(failure):
    db = FakeDatabase([None, (0, 0, None, None)], fail=failure)
    with pytest.raises(LedgerUnavailable):
        reserve(db.ledger())


@pytest.mark.parametrize("operation", ["reserve", "complete"])
def test_postgres_missing_database_fails_closed(operation):
    def forbidden_connect(*args, **kwargs):
        pytest.fail("no connection should be attempted without configuration")

    ledger = PostgresAutomationLedger(None, connect=forbidden_connect)
    with pytest.raises(LedgerUnavailable):
        reserve(ledger) if operation == "reserve" else complete(ledger)


def test_postgres_complete_updates_in_progress_row_and_commits():
    db = FakeDatabase([(ARGS["client_request_id"],)])
    complete(db.ledger())
    [(sql, params)] = db.statements
    assert sql.lstrip().startswith("UPDATE public.automation_radar_ledger")
    assert "AND state = 'IN_PROGRESS'" in sql
    assert "RETURNING client_request_id" in sql
    assert json.loads(params["response_body"]) == OUTCOME.response_body
    assert params["http_status"] == 503 and params["outcome_code"] == "ANALYSIS_FAILED"
    assert params["completed_at_utc"] == NOW
    assert db.events.count("commit") == 1


def test_postgres_complete_requires_returned_row():
    db = FakeDatabase([None])
    with pytest.raises(LedgerUnavailable):
        complete(db.ledger())
    assert "commit" not in db.events


@pytest.mark.parametrize("failure", ["connect", 1, "fetch", "commit"])
def test_postgres_complete_db_errors_fail_closed(failure):
    db = FakeDatabase([("synthetic",)], fail=failure)
    with pytest.raises(LedgerUnavailable):
        complete(db.ledger())


def test_every_sql_column_exists_in_migration():
    path = Path(__file__).resolve().parents[2] / "migrations/0013_automation_radar_ledger.sql"
    create = path.read_text().split("CREATE TABLE IF NOT EXISTS", 1)[1].split("CONSTRAINT", 1)[0]
    columns = set(
        re.findall(r"^\s+(\w+)\s+(?:TEXT|UUID|INTEGER|JSONB|TIMESTAMPTZ)\b", create, re.M)
    )
    assert columns == set(LedgerEntry.__dataclass_fields__)
    statements = [module._SELECT_SQL, module._COUNT_SQL, module._INSERT_SQL, module._COMPLETE_SQL]
    keywords = set(
        """select from where and or is null not all for update insert into values set
        returning filter count min as text uuid jsonb public automation_radar_ledger""".split()
    )
    aliases = {"counted_5min", "counted_day", "oldest_5min", "oldest_day"}
    for sql in statements:
        stripped = re.sub(r"%\(\w+\)s|'[^']*'", "", sql.lower())
        identifiers = set(re.findall(r"\b[a-z_][a-z_0-9]*\b", stripped)) - keywords - aliases
        assert identifiers <= columns, identifiers - columns
