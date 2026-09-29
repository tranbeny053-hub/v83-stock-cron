"""The one-shot apply of migration 0012 (the resolution-status table). No database is contacted.

Every database interaction runs against a fake driver that behaves like psycopg 3 where it matters:
a connection used as a context manager commits on success and rolls back on an exception, a
statement is recorded with its parameters, and a check read before and after the migration can
return different rows. The real PostgreSQL rehearsal runs inside the dispatch job
(.github/workflows/apply-migration-0012.yml), before the secret is handed to any step.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from crypto_probability_engine.runtime_isolation import REQUIRED_FLAGS_TEXT, ProvenanceRefused
from scripts import apply_migration_0010 as apply_0010
from scripts import apply_migration_0011 as apply_0011
from scripts import apply_migration_0012 as apply_0012
from scripts import audit_table_privileges as audit

ROOT = Path(__file__).resolve().parents[2]
MIGRATION_BYTES = (ROOT / apply_0012.MIGRATION).read_bytes()
MIGRATION_SQL = MIGRATION_BYTES.decode("utf-8")
DATABASE_URL = "postgresql://owner:NEVER-SHOWN-SECRET@db.never-contacted.invalid:5432/postgres"
REHEARSAL_URL = "postgresql:///migration_0012_rehearsal?host=/var/run/postgresql"
SHA = "c" * 40
REPOSITORY = apply_0012.EXPECTED_REPOSITORY
# Production is Supabase PostgreSQL 17.6. The CI rehearsal runs Ubuntu 24.04's PostgreSQL 16,
# which has no MAINTAIN.
PRODUCTION_SERVER = 170006
REHEARSAL_SERVER = 160010
ALL = list(apply_0012.table_privileges_for(PRODUCTION_SERVER))
REHEARSAL_ALL = list(apply_0012.table_privileges_for(REHEARSAL_SERVER))
TABLE = apply_0012.TABLE
PKEY = "prediction_resolution_status_pkey"
RETRY_IDX = "prediction_resolution_status_retry_idx"
TABLE_SQL = apply_0012.table_security_sql(PRODUCTION_SERVER)
EXISTING_SQL = apply_0012.existing_security_sql(PRODUCTION_SERVER)
RELATIONS_SQL = apply_0012.RELATIONS_SQL
MIGRATION_0011_SQL = apply_0012.MIGRATION_0011_SQL
COLUMNS_SQL = apply_0012.COLUMNS_SQL
CONSTRAINTS_SQL = apply_0012.CONSTRAINTS_SQL
REFERENCING_SQL = apply_0012.REFERENCING_SQL
INDEXES_SQL = apply_0012.INDEXES_SQL
TRIGGERS_SQL = apply_0012.TRIGGERS_SQL
ROW_COUNT_SQL = apply_0012.ROW_COUNT_SQL
SECURITY_FIELDS = apply_0012.SECURITY_FIELDS
RELATION_FIELDS = apply_0012.RELATION_FIELDS
COLUMN_FIELDS = apply_0012.COLUMN_FIELDS
CONSTRAINT_FIELDS = apply_0012.CONSTRAINT_FIELDS
INDEX_FIELDS = apply_0012.INDEX_FIELDS
PRE_NAMES = ("relations", "existing", "migration_0011_columns_present")
POST_NAMES = (
    "relations",
    "table",
    "columns",
    "constraints",
    "referencing_constraints",
    "indexes",
    "triggers",
    "row_count",
    "existing",
    "migration_0011_columns_present",
)
# 0011's columns on predictions once 0011 is applied, as the check returns them: sorted.
WITH_0011 = ["core_computed_at_utc", "issued_at_utc", "reference_venue", "target_version"]


# ------------------------------------------------------------------------ a psycopg-3-shaped fake


class FakeDatabase:
    """``results[query]`` is either one list of rows, or ``Each([rows, rows, ...])`` per call."""

    def __init__(self, results: dict[str, Any], fail_on: dict[str, Exception] | None = None):
        self.results = results
        self.fail_on = fail_on or {}
        self.statements: list[tuple[str, Any]] = []
        self.connects: list[tuple[str, dict[str, Any]]] = []
        self.commits = 0
        self.rollbacks = 0
        self.in_transaction = False
        self.calls: dict[str, int] = {}
        self.fail_commit: Exception | None = None

    def connect(self, url: str, **options: Any) -> FakeConnection:
        self.connects.append((url, options))
        return FakeConnection(self)

    def executed(self) -> list[str]:
        return [statement for statement, _ in self.statements]


class Each(list):
    """Rows for the first call, the second call, and so on; the last repeats."""


class FakeConnection:
    def __init__(self, database: FakeDatabase):
        self.database = database

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.database)

    def commit(self) -> None:
        if self.database.in_transaction and self.database.fail_commit is not None:
            raise self.database.fail_commit
        if self.database.in_transaction:
            self.database.commits += 1
        self.database.in_transaction = False

    def rollback(self) -> None:
        if self.database.in_transaction:
            self.database.rollbacks += 1
        self.database.in_transaction = False

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        return False


class FakeCursor:
    def __init__(self, database: FakeDatabase):
        self.database = database
        self.rows: list[tuple] = []

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def execute(self, query: str, params: Any = None) -> None:
        database = self.database
        database.statements.append((query, params))
        database.in_transaction = True
        if query in database.fail_on:
            raise database.fail_on[query]
        result = database.results.get(query, [])
        if isinstance(result, Each):
            call = database.calls.get(query, 0)
            database.calls[query] = call + 1
            result = result[min(call, len(result) - 1)]
        self.rows = list(result)

    def fetchone(self) -> tuple | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[tuple]:
        return list(self.rows)


# ------------------------------------------------------------------------ production after 0011


def security_row(table: str, *, privileges: list[str] = ALL, **changes: Any) -> tuple:
    """A table as 0010 left it: row-level security on, no policy, only service_role holding."""

    values = {
        "table": table,
        "relations_named_so": 1,
        "relkind": "r",
        "owned_by_applying_role": True,
        "row_level_security": True,
        "row_level_security_forced": False,
        "policies": 0,
        "public_has_a_privilege": False,
        "column_grant_to_public_anon_or_authenticated": False,
        "anon": [],
        "authenticated": [],
        "service_role": list(privileges),
    }
    values.update(changes)
    return tuple(values[field] for field in SECURITY_FIELDS)


def existing_rows(privileges: list[str] = ALL) -> list[tuple]:
    """Every table of 0001-0009: the legacy ones as 0010 left them, the later ones as they grant."""

    granted = {
        "analysis_run_details": ["INSERT", "SELECT", "UPDATE"],
        "prediction_derivatives_snapshots": ["INSERT", "SELECT"],
        "section_5a_evaluation_seal": [],
    }
    return [
        security_row(table, privileges=granted.get(table, privileges))
        for table in apply_0012.EXISTING_TABLES
    ]


def new_table_row(**changes: Any) -> tuple:
    """The new table as 0012 must leave it: nobody but its owner holds anything on it."""

    return security_row(TABLE, privileges=[], **changes)


def relation_rows(count: int, **overrides: Any) -> list[tuple]:
    """How many relations of each name are in public: ``count``, unless ``overrides`` says not."""

    return [(name, overrides.get(name, count)) for name in apply_0012.RELATION_NAMES]


ABSENT = relation_rows(0)
CREATED = relation_rows(1)


def column_row(
    name: str, type_name: str, *, not_null: bool = False, default: str | None = None, **flags: Any
) -> tuple:
    values = {
        "column": name,
        "type": type_name,
        "not_null": not_null,
        "default": default,
        "identity": False,
        "generated": False,
        "column_acl": False,
        **flags,
    }
    return tuple(values[field] for field in COLUMN_FIELDS)


TEXT = "text"
TIMESTAMPTZ = "timestamp with time zone"
# The new table's columns as PostgreSQL 16 and 17 report them, in their physical order.
APPLIED_COLUMNS = [
    column_row("prediction_id", TEXT, not_null=True),
    column_row("resolution_status", TEXT, not_null=True),
    column_row("attempt_count", "integer", not_null=True),
    column_row("first_attempt_utc", TIMESTAMPTZ, not_null=True),
    column_row("last_attempt_utc", TIMESTAMPTZ, not_null=True),
    column_row("first_reason", TEXT, not_null=True),
    column_row("last_reason", TEXT, not_null=True),
    column_row("next_eligible_utc", TIMESTAMPTZ),
    column_row("quarantined_at_utc", TIMESTAMPTZ),
    column_row("resolved_at_utc", TIMESTAMPTZ),
    column_row("policy_version", TEXT, not_null=True),
    column_row("resolver_version", TEXT, not_null=True),
    column_row("updated_at_utc", TIMESTAMPTZ, not_null=True, default="now()"),
]


def constraint_row(
    name: str, kind: str, definition: str, columns: list[str], *, validated: bool = True
) -> tuple:
    return (name, kind, validated, definition, list(columns))


def by_name(rows: list[tuple]) -> list[tuple]:
    """In the order the check returns them: by name, bytewise."""

    return sorted(rows, key=lambda row: row[0])


REASON = "'^(skip|error)_[a-z0-9_]{1,58}$'::text"
# How PostgreSQL 16 and 17 deparse 0012's nine constraints (NOT NULL is not among them).
APPLIED_CONSTRAINTS = by_name(
    [
        constraint_row(PKEY, "p", "PRIMARY KEY (prediction_id)", ["prediction_id"]),
        constraint_row(
            "prs_prediction_id_nonblank",
            "c",
            "CHECK ((btrim(prediction_id) <> ''::text))",
            ["prediction_id"],
        ),
        constraint_row(
            "prs_status_valid",
            "c",
            "CHECK ((resolution_status = ANY (ARRAY['RETRYABLE'::text, 'QUARANTINED'::text, "
            "'RESOLVED'::text])))",
            ["resolution_status"],
        ),
        constraint_row(
            "prs_attempt_count_positive", "c", "CHECK ((attempt_count >= 1))", ["attempt_count"]
        ),
        constraint_row(
            "prs_attempt_chronology",
            "c",
            "CHECK ((last_attempt_utc >= first_attempt_utc))",
            ["first_attempt_utc", "last_attempt_utc"],
        ),
        constraint_row(
            "prs_reason_format",
            "c",
            f"CHECK (((first_reason ~ {REASON}) AND (last_reason ~ {REASON})))",
            ["first_reason", "last_reason"],
        ),
        constraint_row(
            "prs_policy_version_format",
            "c",
            "CHECK ((policy_version ~ '^rq-v[1-9][0-9]*$'::text))",
            ["policy_version"],
        ),
        constraint_row(
            "prs_resolver_version_nonblank",
            "c",
            "CHECK ((btrim(resolver_version) <> ''::text))",
            ["resolver_version"],
        ),
        constraint_row(
            "prs_state_shape",
            "c",
            "CHECK ((((resolution_status = 'RETRYABLE'::text) AND (next_eligible_utc IS NOT NULL) "
            "AND (quarantined_at_utc IS NULL) AND (resolved_at_utc IS NULL)) OR "
            "((resolution_status = 'QUARANTINED'::text) AND (next_eligible_utc IS NULL) AND "
            "(quarantined_at_utc IS NOT NULL) AND (resolved_at_utc IS NULL)) OR "
            "((resolution_status = 'RESOLVED'::text) AND (next_eligible_utc IS NULL) AND "
            "(quarantined_at_utc IS NULL) AND (resolved_at_utc IS NOT NULL))))",
            ["next_eligible_utc", "quarantined_at_utc", "resolution_status", "resolved_at_utc"],
        ),
    ]
)
RETRY_PREDICATE = "(resolution_status = 'RETRYABLE'::text)"
# How PostgreSQL 16 and 17 describe 0012's two indexes.
APPLIED_INDEXES = [
    (
        PKEY,
        True,
        ["prediction_id"],
        None,
        "CREATE UNIQUE INDEX prediction_resolution_status_pkey"
        " ON public.prediction_resolution_status USING btree (prediction_id)",
    ),
    (
        RETRY_IDX,
        False,
        ["next_eligible_utc", "prediction_id"],
        RETRY_PREDICATE,
        "CREATE INDEX prediction_resolution_status_retry_idx"
        " ON public.prediction_resolution_status"
        f" USING btree (next_eligible_utc, prediction_id) WHERE {RETRY_PREDICATE}",
    ),
]


def healthy_results(
    version: int = PRODUCTION_SERVER, *, with_0011: list[str] = WITH_0011, **overrides: Any
) -> dict[str, Any]:
    """What a first apply returns on production as migrations 0001-0011 left it."""

    privileges = list(apply_0012.table_privileges_for(version))
    results: dict[str, Any] = {
        apply_0012.ROLES_SQL: [(3,)],
        apply_0012.SERVER_VERSION_SQL: [(version,)],
        RELATIONS_SQL: Each([ABSENT, CREATED]),
        apply_0012.existing_security_sql(version): existing_rows(privileges),
        MIGRATION_0011_SQL: [(list(with_0011),)],
        apply_0012.table_security_sql(version): [new_table_row()],
        COLUMNS_SQL: list(APPLIED_COLUMNS),
        CONSTRAINTS_SQL: list(APPLIED_CONSTRAINTS),
        REFERENCING_SQL: [(0,)],
        INDEXES_SQL: list(APPLIED_INDEXES),
        TRIGGERS_SQL: [],
        ROW_COUNT_SQL: [(0,)],
    }
    results.update(overrides)
    return results


PRE_READS = [RELATIONS_SQL, EXISTING_SQL, MIGRATION_0011_SQL]
POST_READS = [
    RELATIONS_SQL,
    TABLE_SQL,
    COLUMNS_SQL,
    CONSTRAINTS_SQL,
    REFERENCING_SQL,
    INDEXES_SQL,
    TRIGGERS_SQL,
    ROW_COUNT_SQL,
    EXISTING_SQL,
    MIGRATION_0011_SQL,
]
EXPECTED_ORDER = [
    *apply_0012.TIMEOUT_STATEMENTS,
    apply_0012.ADVISORY_LOCK_SQL,
    apply_0012.ROLES_SQL,
    apply_0012.SERVER_VERSION_SQL,
    *PRE_READS,
    MIGRATION_SQL,
    *POST_READS,
]


def _apply(database: FakeDatabase) -> tuple[dict[str, Any], dict[str, Any]]:
    captured: dict[str, Any] = {}
    outcome = apply_0012.apply_in_one_transaction(
        lambda: database.connect(DATABASE_URL), MIGRATION_SQL, captured
    )
    return outcome, captured


def _dicts(fields: tuple[str, ...], rows: list[tuple]) -> list[dict[str, Any]]:
    return [dict(zip(fields, row, strict=True)) for row in rows]


# --------------------------------------------------------------------------- the contract


def test_the_script_imports_only_the_standard_library_at_module_level() -> None:
    tree = ast.parse((ROOT / apply_0012.SCRIPT).read_text(encoding="utf-8"))
    imported = {
        (node.module if isinstance(node, ast.ImportFrom) else alias.name).split(".")[0]
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in (node.names if isinstance(node, ast.Import) else [None])
    }
    assert imported and all(
        name == "__future__" or name in sys.stdlib_module_names for name in imported
    ), imported


def test_it_names_itself_its_workflow_and_the_reviewed_bytes() -> None:
    assert (ROOT / apply_0012.SCRIPT).resolve() == Path(apply_0012.__file__).resolve()
    assert (ROOT / apply_0012.WORKFLOW).is_file()
    assert not hasattr(apply_0012, "REHEARSAL_WORKFLOW"), "dispatch-only: no rehearsal workflow"
    assert apply_0012.MIGRATION == "migrations/0012_prediction_resolution_status.sql"
    assert hashlib.sha256(MIGRATION_BYTES).hexdigest() == apply_0012.MIGRATION_SHA256
    assert apply_0012.MIGRATION_SHA256 == (
        "e7f6cbdac59be303994d0b3dd52f1ac873f0d6313c2ecdae333fb4f8f9040322"
    )
    assert apply_0012.CONFIRMATION == "APPLY-MIGRATION-0012-ONCE"
    assert apply_0012.REPORT_SCHEMA == "migration-0012-apply-report.v1"
    assert apply_0012.DISPATCH_SCHEMA == "migration-0012-dispatch.v1"
    assert apply_0012.EXPECTED_REPOSITORY == "tranbeny053-hub/v83-stock-cron"


def test_its_lock_token_and_workflow_are_its_own() -> None:
    from scripts import apply_migration_0008

    assert apply_0012.ADVISORY_LOCK_SQL == "SELECT pg_advisory_xact_lock(5000012)"
    assert apply_0012.ADVISORY_LOCK_SQL not in {
        apply_migration_0008.ADVISORY_LOCK_SQL,
        "SELECT pg_advisory_xact_lock(5009005)",
        apply_0010.ADVISORY_LOCK_SQL,
        apply_0011.ADVISORY_LOCK_SQL,
    }
    assert apply_0012.CONFIRMATION not in {
        apply_migration_0008.CONFIRMATION,
        apply_0010.CONFIRMATION,
        apply_0011.CONFIRMATION,
    }
    assert apply_0012.WORKFLOW not in {
        apply_migration_0008.WORKFLOW,
        apply_0010.WORKFLOW,
        apply_0010.REHEARSAL_WORKFLOW,
        apply_0011.WORKFLOW,
    }
    assert apply_0012.REHEARSAL_URL_VARIABLE == "MIGRATION_0012_REHEARSAL_URL"
    assert apply_0012.REHEARSAL_URL_VARIABLE != apply_0011.REHEARSAL_URL_VARIABLE


@pytest.mark.parametrize("version", [150000, 160010, 170006])
def test_it_shares_0010_s_trust_boundary_and_security_check(version: int) -> None:
    """The copied security check produces exactly 0010's SQL; the boundary constants match."""

    privileges = apply_0010.table_privileges_for(version)
    assert apply_0012.table_privileges_for(version) == privileges
    assert apply_0012.SECURITY_FIELDS == apply_0010.SECURITY_FIELDS
    assert apply_0012.table_security_sql(version) == apply_0010._security_sql((TABLE,), privileges)
    assert apply_0012.existing_security_sql(version) == apply_0010._security_sql(
        apply_0012.EXISTING_TABLES, privileges
    )
    assert apply_0012.ROLES_SQL == apply_0010.ROLES_SQL
    assert apply_0012.SERVER_VERSION_SQL == apply_0010.SERVER_VERSION_SQL
    assert apply_0012.TIMEOUT_STATEMENTS == apply_0010.TIMEOUT_STATEMENTS == (
        apply_0011.TIMEOUT_STATEMENTS
    )
    assert apply_0012.MINIMUM_SERVER_VERSION == apply_0010.MINIMUM_SERVER_VERSION
    for name in ("EXPECTED_REPOSITORY", "PINNED_PYTHON", "REQUIRED_EVENT", "REQUIRED_REF"):
        assert getattr(apply_0012, name) == getattr(apply_0010, name), name
    assert apply_0012._LOCAL_SOCKET_URL.pattern == apply_0010._LOCAL_SOCKET_URL.pattern
    assert apply_0012._QUOTED_LITERAL.pattern == apply_0011._QUOTED_LITERAL.pattern


def test_its_table_columns_constraints_and_indexes_are_the_reviewed_ones() -> None:
    assert TABLE == "prediction_resolution_status"
    assert apply_0012.RELATION_NAMES == (TABLE, PKEY, RETRY_IDX)
    assert list(apply_0012.RELATION_NAMES) == sorted(apply_0012.RELATION_NAMES)
    assert apply_0012.EXPECTED_COLUMNS == (
        ("prediction_id", "text", True, None),
        ("resolution_status", "text", True, None),
        ("attempt_count", "integer", True, None),
        ("first_attempt_utc", TIMESTAMPTZ, True, None),
        ("last_attempt_utc", TIMESTAMPTZ, True, None),
        ("first_reason", "text", True, None),
        ("last_reason", "text", True, None),
        ("next_eligible_utc", TIMESTAMPTZ, False, None),
        ("quarantined_at_utc", TIMESTAMPTZ, False, None),
        ("resolved_at_utc", TIMESTAMPTZ, False, None),
        ("policy_version", "text", True, None),
        ("resolver_version", "text", True, None),
        ("updated_at_utc", TIMESTAMPTZ, True, "now()"),
    )
    statuses = frozenset({"RETRYABLE", "QUARANTINED", "RESOLVED"})
    assert dict(apply_0012.EXPECTED_CONSTRAINTS) == {
        PKEY: ("p", ("prediction_id",), frozenset()),
        "prs_prediction_id_nonblank": ("c", ("prediction_id",), frozenset({""})),
        "prs_status_valid": ("c", ("resolution_status",), statuses),
        "prs_attempt_count_positive": ("c", ("attempt_count",), frozenset()),
        "prs_attempt_chronology": ("c", ("first_attempt_utc", "last_attempt_utc"), frozenset()),
        "prs_reason_format": (
            "c",
            ("first_reason", "last_reason"),
            frozenset({"^(skip|error)_[a-z0-9_]{1,58}$"}),
        ),
        "prs_policy_version_format": ("c", ("policy_version",), frozenset({"^rq-v[1-9][0-9]*$"})),
        "prs_resolver_version_nonblank": ("c", ("resolver_version",), frozenset({""})),
        "prs_state_shape": (
            "c",
            ("next_eligible_utc", "quarantined_at_utc", "resolution_status", "resolved_at_utc"),
            statuses,
        ),
    }
    for _, columns, _ in apply_0012.EXPECTED_CONSTRAINTS.values():
        assert list(columns) == sorted(columns)
    assert dict(apply_0012.EXPECTED_INDEXES) == {
        PKEY: (True, ("prediction_id",), None),
        RETRY_IDX: (False, ("next_eligible_utc", "prediction_id"), frozenset({"RETRYABLE"})),
    }
    assert apply_0012.PREDICATE_COLUMN == "resolution_status"
    assert set(apply_0012.EXPECTED_SECURITY) == set(SECURITY_FIELDS[1:])
    assert apply_0012.COLUMN_FLAGS_OFF == ("identity", "generated", "column_acl")


def test_the_existing_tables_and_0011_s_columns_are_the_reviewed_ones() -> None:
    existing = apply_0012.EXISTING_TABLES
    assert list(existing) == sorted(existing) and len(existing) == 14
    assert "predictions" in existing and TABLE not in existing
    assert set(existing) == {apply_0011.TABLE, *apply_0011.OTHER_TABLES}
    assert apply_0012.MIGRATION_0011_COLUMNS == tuple(name for name, _ in apply_0011.NEW_COLUMNS)
    assert WITH_0011 == sorted(apply_0012.MIGRATION_0011_COLUMNS)


@pytest.mark.parametrize(
    ("definition", "literals"),
    [
        ("CHECK ((btrim(prediction_id) <> ''::text))", {""}),
        (
            "CHECK ((resolution_status = ANY (ARRAY['RETRYABLE'::text, 'QUARANTINED'::text, "
            "'RESOLVED'::text])))",
            {"RETRYABLE", "QUARANTINED", "RESOLVED"},
        ),
        (
            f"CHECK (((first_reason ~ {REASON}) AND (last_reason ~ {REASON})))",
            {"^(skip|error)_[a-z0-9_]{1,58}$"},
        ),
        ("CHECK ((attempt_count >= 1))", set()),
        (RETRY_PREDICATE, {"RETRYABLE"}),
        ("CHECK ((note <> 'it''s'::text))", {"it's"}),
    ],
)
def test_literals_are_read_as_a_set_from_the_deparse(definition: str, literals: set[str]) -> None:
    assert apply_0012.constraint_literals(definition) == literals


FORBIDDEN_WORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|TRUNCATE|ALTER|CREATE|DROP|GRANT|REVOKE|COPY|CALL|DO|VACUUM|"
    r"ANALYZE|LOCK|NOTIFY|LISTEN|REFRESH|CLUSTER|REINDEX|COMMENT|SECURITY|EXECUTE|PREPARE|"
    r"MERGE|RESET|DISCARD|IMPORT)\b"
)


def _without_literals(statement: str) -> str:
    return re.sub(r"'[^']*'", "''", statement)


CHECKS = [
    *(statement for statement in dict.fromkeys(EXPECTED_ORDER) if statement is not MIGRATION_SQL),
    apply_0012.table_security_sql(REHEARSAL_SERVER),
    apply_0012.existing_security_sql(REHEARSAL_SERVER),
]


def test_every_check_is_a_read_only_query_without_parameters() -> None:
    assert len(CHECKS) == 5 + 10 + 2
    for statement in CHECKS:
        bare = _without_literals(statement)
        assert bare.startswith(("SELECT ", "SET LOCAL ")), statement
        assert not FORBIDDEN_WORDS.search(bare), statement
        assert ";" not in bare and "%" not in bare
        targets = re.findall(r"\b(?:FROM|JOIN)\s+(?:LATERAL\s+)?(\S+)", bare)
        if statement == ROW_COUNT_SQL:
            assert targets == [f"public.{TABLE}"], "the one non-catalog read"
            continue
        for target in targets:
            assert target.startswith(("pg_catalog.", "(")), (statement, target)


def test_the_only_application_read_is_the_new_table_s_row_count_after_the_migration() -> None:
    assert ROW_COUNT_SQL == "SELECT count(*) FROM public.prediction_resolution_status"
    for statement in CHECKS:
        if statement == ROW_COUNT_SQL:
            continue
        bare = _without_literals(statement)
        assert "public." not in bare, "a relation is only ever named inside a literal"
        for table in (TABLE, *apply_0012.EXISTING_TABLES):
            assert not re.search(rf"\b(?:FROM|JOIN)\s+(?:public\.)?{table}\b", bare), statement
    assert EXPECTED_ORDER.count(ROW_COUNT_SQL) == 1
    assert EXPECTED_ORDER.index(ROW_COUNT_SQL) > EXPECTED_ORDER.index(MIGRATION_SQL)


def test_the_checks_cover_the_new_table_every_existing_table_role_and_privilege() -> None:
    assert f"FROM (VALUES ('{TABLE}')) AS t(name)" in TABLE_SQL
    for table in apply_0012.EXISTING_TABLES:
        assert f"('{table}')" in EXISTING_SQL
    assert f"('{TABLE}')" not in EXISTING_SQL
    for role in apply_0012.API_ROLES:
        assert f"has_table_privilege('{role}', c.oid, v.privilege)" in TABLE_SQL
    for privilege in ALL:
        assert f"('{privilege}')" in TABLE_SQL
    assert "('MAINTAIN')" in TABLE_SQL and "('MAINTAIN')" not in (
        apply_0012.table_security_sql(REHEARSAL_SERVER)
    )
    assert f"k.relkind = ANY ({audit._RELKINDS_SQL})" in TABLE_SQL
    assert "a.grantee = 0" in TABLE_SQL and "att.attacl" in TABLE_SQL
    # Every name, a relation of any kind, only in public.
    for name in apply_0012.RELATION_NAMES:
        assert f"('{name}')" in RELATIONS_SQL
    assert "relkind" not in RELATIONS_SQL, "a relation of ANY kind counts"
    assert "k.relnamespace = pg_catalog.to_regnamespace('public')" in RELATIONS_SQL
    assert RELATIONS_SQL.endswith(' ORDER BY t.name COLLATE "C"')
    # 0011's columns, as one sorted array.
    assert MIGRATION_0011_SQL.startswith("SELECT ARRAY(SELECT a.attname::text")
    assert "pg_catalog.to_regclass('public.predictions')" in MIGRATION_0011_SQL
    for name in apply_0012.MIGRATION_0011_COLUMNS:
        assert f"'{name}'" in MIGRATION_0011_SQL
    assert MIGRATION_0011_SQL.endswith(' ORDER BY a.attname::text COLLATE "C")')
    relation = f"pg_catalog.to_regclass('public.{TABLE}')"
    for query in (COLUMNS_SQL, CONSTRAINTS_SQL, REFERENCING_SQL, INDEXES_SQL, TRIGGERS_SQL):
        assert relation in query, query
    for fragment in (
        "pg_catalog.format_type(a.atttypid, a.atttypmod)",
        "a.attnotnull",
        "pg_catalog.pg_get_expr(d.adbin, d.adrelid)",
        "LEFT JOIN pg_catalog.pg_attrdef AS d ON d.adrelid = a.attrelid AND d.adnum = a.attnum",
        "a.attidentity <> ''",
        "a.attgenerated <> ''",
        "a.attacl IS NOT NULL",
        "a.attnum > 0 AND NOT a.attisdropped",
    ):
        assert fragment in COLUMNS_SQL, fragment
    assert COLUMNS_SQL.endswith(" ORDER BY a.attnum"), "columns in their physical order"
    assert "c.contype <> 'n'" in CONSTRAINTS_SQL, "NOT NULL is judged from pg_attribute"
    assert "pg_catalog.pg_get_constraintdef(c.oid)" in CONSTRAINTS_SQL
    assert "a.attnum = ANY (c.conkey)" in CONSTRAINTS_SQL
    assert CONSTRAINTS_SQL.endswith(' ORDER BY c.conname::text COLLATE "C"')
    assert REFERENCING_SQL.startswith("SELECT count(*) FROM pg_catalog.pg_constraint AS c")
    assert f"c.confrelid = {relation}" in REFERENCING_SQL
    for fragment in (
        "x.indisunique",
        "FROM pg_catalog.unnest(x.indkey) WITH ORDINALITY AS k(attnum, n)",
        "LEFT JOIN pg_catalog.pg_attribute AS a",
        "WHERE k.n <= x.indnkeyatts ORDER BY k.n",
        "pg_catalog.pg_get_expr(x.indpred, x.indrelid)",
        "pg_catalog.pg_get_indexdef(x.indexrelid)",
    ):
        assert fragment in INDEXES_SQL, fragment
    assert "NOT t.tgisinternal" in TRIGGERS_SQL and "t.tgenabled::text" in TRIGGERS_SQL
    assert len(SECURITY_FIELDS) == 12
    assert RELATION_FIELDS == ("relation", "relations_in_public")
    assert COLUMN_FIELDS == (
        "column", "type", "not_null", "default", "identity", "generated", "column_acl"
    )
    assert CONSTRAINT_FIELDS == ("constraint", "type", "validated", "definition", "columns")
    assert INDEX_FIELDS == ("index", "unique", "columns", "predicate", "definition")
    assert apply_0012.TRIGGER_FIELDS == ("trigger", "enabled")
    assert [name for name, _, _ in apply_0012.pre_checks(PRODUCTION_SERVER)] == list(PRE_NAMES)
    assert [name for name, _, _ in apply_0012.post_checks(PRODUCTION_SERVER)] == list(POST_NAMES)


# --------------------------------------------------------------------------- the one transaction


def test_a_first_apply_runs_every_check_in_one_committed_transaction() -> None:
    database = FakeDatabase(healthy_results())
    outcome, captured = _apply(database)

    assert database.executed() == EXPECTED_ORDER
    assert all(params is None for _, params in database.statements)
    assert database.commits == 1 and database.rollbacks == 0
    assert outcome["outcome"] == "APPLIED" and outcome["committed"] is True
    assert outcome["executed_migration_sha256"] == apply_0012.MIGRATION_SHA256
    assert outcome["pre_relations"] == _dicts(RELATION_FIELDS, ABSENT)
    assert outcome["post_relations"] == _dicts(RELATION_FIELDS, CREATED)
    assert [row["column"] for row in outcome["post_columns"]] == list(
        apply_0012.EXPECTED_COLUMN_NAMES
    )
    assert {row["constraint"] for row in outcome["post_constraints"]} == set(
        apply_0012.EXPECTED_CONSTRAINTS
    )
    assert outcome["post_referencing_constraints"] == 0 and outcome["post_row_count"] == 0
    assert outcome["post_triggers"] == []
    for name in PRE_NAMES:
        assert outcome[f"pre_{name}"] == captured[f"pre_{name}"], name
    for name in POST_NAMES:
        assert outcome[f"post_{name}"] == captured[f"post_{name}"], name
    assert captured["post_existing"] == captured["pre_existing"]
    assert captured["commit_attempted"] is True and captured["committed"] is True


@pytest.mark.parametrize(
    "present",
    [[], WITH_0011, ["issued_at_utc", "target_version"]],
    ids=["0011-not-applied", "0011-applied", "0011-partly-present"],
)
def test_0011_s_columns_are_recorded_before_and_after_and_never_required(
    present: list[str],
) -> None:
    database = FakeDatabase(healthy_results(with_0011=present))
    outcome, captured = _apply(database)
    assert outcome["outcome"] == "APPLIED" and database.commits == 1
    assert outcome["pre_migration_0011_columns_present"] == present
    assert outcome["post_migration_0011_columns_present"] == present
    assert captured["pre_migration_0011_columns_present"] == present


@pytest.mark.parametrize("version", [150000, 160010, 169999, 170000, 170006])
def test_every_server_is_asked_about_exactly_its_table_privileges(version: int) -> None:
    database = FakeDatabase(healthy_results(version))
    outcome, captured = _apply(database)
    assert outcome["outcome"] == "APPLIED" and database.commits == 1
    assert outcome["server_version_num"] == captured["server_version_num"] == version
    has_maintain = version >= 170000
    assert ("MAINTAIN" in outcome["table_privileges_asked"]) is has_maintain
    assert len(outcome["table_privileges_asked"]) == 7 + has_maintain
    assert outcome["table_privileges_asked"] == sorted(outcome["table_privileges_asked"])
    table_sql = apply_0012.table_security_sql(version)
    existing_sql = apply_0012.existing_security_sql(version)
    assert database.executed().count(table_sql) == 1, "the new table is read after only"
    assert database.executed().count(existing_sql) == 2, "the existing tables before and after"
    for query in (table_sql, existing_sql):
        assert ("('MAINTAIN')" in query) is has_maintain


@pytest.mark.parametrize(
    "reported",
    [[(140012,)], [(None,)], [("170006",)], [(True,)], [(170006.0,)], [], [(170006, 1)]],
    ids=["postgres-14", "null", "text", "boolean", "float", "no-row", "two-values"],
)
def test_an_unsupported_or_unreadable_server_version_refuses_before_any_read(
    reported: list[tuple],
) -> None:
    database = FakeDatabase(healthy_results(**{apply_0012.SERVER_VERSION_SQL: reported}))
    with pytest.raises(ProvenanceRefused, match="nothing is applied"):
        _apply(database)
    assert database.executed()[-1] == apply_0012.SERVER_VERSION_SQL
    assert database.commits == 0 and database.rollbacks == 1


def test_the_migration_statement_is_exactly_the_file() -> None:
    database = FakeDatabase(healthy_results())
    _apply(database)
    (executed,) = [s for s in database.executed() if s.startswith("-- The resolution-status")]
    assert executed.encode("utf-8") == MIGRATION_BYTES


def test_missing_api_roles_refuse_before_anything_is_read() -> None:
    database = FakeDatabase(healthy_results(**{apply_0012.ROLES_SQL: [(2,)]}))
    with pytest.raises(ProvenanceRefused, match="Supabase API roles"):
        _apply(database)
    assert database.executed()[-1] == apply_0012.ROLES_SQL
    assert database.commits == 0 and database.rollbacks == 1


NOT_A_FIRST_APPLY_CASES: dict[str, tuple[list[tuple], list[str]]] = {
    **{
        f"{name}-already-in-public": (relation_rows(0, **{name: 1}), [name])
        for name in (TABLE, PKEY, RETRY_IDX)
    },
    "the-table-named-twice-in-public": (relation_rows(0, **{TABLE: 2}), [TABLE]),
    "all-three-already-in-public": (CREATED, [TABLE, PKEY, RETRY_IDX]),
}


@pytest.mark.parametrize("case", sorted(NOT_A_FIRST_APPLY_CASES))
def test_any_relation_already_named_so_in_public_is_not_a_first_apply(case: str) -> None:
    rows, named = NOT_A_FIRST_APPLY_CASES[case]
    database = FakeDatabase(healthy_results(**{RELATIONS_SQL: Each([rows, CREATED])}))
    captured: dict[str, Any] = {}
    with pytest.raises(ProvenanceRefused, match=apply_0012.NOT_A_FIRST_APPLY) as refused:
        apply_0012.apply_in_one_transaction(
            lambda: database.connect(DATABASE_URL), MIGRATION_SQL, captured
        )
    message = str(refused.value)
    assert message.count(apply_0012.NOT_A_FIRST_APPLY) == len(named)
    for name in named:
        assert f"named {name} already exist" in message, name
    assert MIGRATION_SQL not in database.executed()
    assert database.executed()[-1] == MIGRATION_0011_SQL, "every pre-read is taken first"
    assert all(f"pre_{name}" in captured for name in PRE_NAMES), "what was seen is reported"
    assert database.commits == 0 and database.rollbacks == 1


MALFORMED_PRE_READS: dict[str, tuple[str, list[tuple]]] = {
    "relations-read-empty": (RELATIONS_SQL, []),
    "a-relation-missing-from-the-read": (RELATIONS_SQL, ABSENT[1:]),
    "the-relations-in-another-order": (RELATIONS_SQL, list(reversed(ABSENT))),
    "a-relation-count-unreadable": (RELATIONS_SQL, relation_rows(0, **{TABLE: None})),
    "a-relation-count-a-boolean": (RELATIONS_SQL, relation_rows(0, **{TABLE: False})),
    "an-existing-table-missing": (EXISTING_SQL, existing_rows()[:-1]),
    "an-existing-table-extra": (EXISTING_SQL, [*existing_rows(), security_row("zz_unexpected")]),
    "the-existing-tables-in-another-order": (EXISTING_SQL, list(reversed(existing_rows()))),
    "predictions-missing-from-the-existing-tables": (
        EXISTING_SQL,
        [row for row in existing_rows() if row[0] != "predictions"],
    ),
    "the-new-table-among-the-existing-tables": (
        EXISTING_SQL,
        by_name([*existing_rows(), security_row(TABLE)]),
    ),
}


@pytest.mark.parametrize("case", sorted(MALFORMED_PRE_READS))
def test_a_malformed_pre_read_refuses_before_the_migration(case: str) -> None:
    query, rows = MALFORMED_PRE_READS[case]
    database = FakeDatabase(healthy_results(**{query: Each([rows, rows])}))
    captured: dict[str, Any] = {}
    with pytest.raises(ProvenanceRefused, match="not in the state a first apply of 0012 requires"):
        apply_0012.apply_in_one_transaction(
            lambda: database.connect(DATABASE_URL), MIGRATION_SQL, captured
        )
    assert MIGRATION_SQL not in database.executed()
    assert database.executed()[-1] == MIGRATION_0011_SQL, "every pre-read is taken first"
    assert all(f"pre_{name}" in captured for name in PRE_NAMES), "what was seen is reported"
    assert database.commits == 0 and database.rollbacks == 1


def test_a_second_apply_refuses_naming_every_failure_not_only_the_first() -> None:
    database = FakeDatabase(
        healthy_results(**{RELATIONS_SQL: CREATED, EXISTING_SQL: existing_rows()[1:]})
    )
    with pytest.raises(ProvenanceRefused) as refused:
        _apply(database)
    message = str(refused.value)
    assert message.count(apply_0012.NOT_A_FIRST_APPLY) == 3
    for name in apply_0012.RELATION_NAMES:
        assert f"named {name} already exist" in message, name
    assert "the existing tables read were" in message
    assert MIGRATION_SQL not in database.executed()


def test_the_existing_tables_are_recorded_not_required() -> None:
    """0012 only has to leave them as they are, whatever that is."""

    unusual = [
        security_row(
            "analysis_run_details",
            relations_named_so=0,
            relkind=None,
            owned_by_applying_role=None,
            service_role=[],
        ),
        security_row("analysis_runs", relkind="v", owned_by_applying_role=False),
        *existing_rows()[2:10],
        security_row(
            "predictions",
            row_level_security=False,
            policies=2,
            public_has_a_privilege=True,
            column_grant_to_public_anon_or_authenticated=True,
            anon=list(ALL),
            authenticated=["SELECT"],
        ),
        *existing_rows()[11:],
    ]
    assert [row[0] for row in unusual] == list(apply_0012.EXISTING_TABLES)
    database = FakeDatabase(healthy_results(**{EXISTING_SQL: unusual}))
    outcome, captured = _apply(database)
    assert outcome["outcome"] == "APPLIED" and database.commits == 1
    assert captured["pre_existing"] == captured["post_existing"]
    assert captured["pre_existing"][0]["relations_named_so"] == 0
    assert captured["pre_existing"][10]["anon"] == ALL


def _rows_with(
    rows: list[tuple], fields: tuple[str, ...], key: str, name: str, **changes: Any
) -> list[tuple]:
    """``rows`` with only the one whose ``key`` is ``name`` changed."""

    changed = []
    for row in rows:
        values = dict(zip(fields, row, strict=True))
        if values[key] == name:
            values.update(changes)
        changed.append(tuple(values[field] for field in fields))
    return changed


def _columns_with(name: str, **changes: Any) -> list[tuple]:
    return _rows_with(APPLIED_COLUMNS, COLUMN_FIELDS, "column", name, **changes)


def _constraints_with(name: str, **changes: Any) -> list[tuple]:
    return _rows_with(APPLIED_CONSTRAINTS, CONSTRAINT_FIELDS, "constraint", name, **changes)


def _indexes_with(name: str, **changes: Any) -> list[tuple]:
    return _rows_with(APPLIED_INDEXES, INDEX_FIELDS, "index", name, **changes)


WRONG_TYPE = {
    TEXT: "character varying",
    "integer": "bigint",
    TIMESTAMPTZ: "timestamp without time zone",
}
COLUMN_DEFECTS = (
    "missing", "wrong-type", "nullability-flipped", "wrong-default", "identity", "generated",
    "with-an-acl",
)


def _column_defects(row: tuple) -> dict[str, list[tuple]]:
    values = dict(zip(COLUMN_FIELDS, row, strict=True))
    name = values["column"]
    return {
        "missing": [other for other in APPLIED_COLUMNS if other[0] != name],
        "wrong-type": _columns_with(name, type=WRONG_TYPE[values["type"]]),
        "nullability-flipped": _columns_with(name, not_null=not values["not_null"]),
        # A default appears where there is none, or the one default is lost.
        "wrong-default": _columns_with(name, default=None if values["default"] else "now()"),
        "identity": _columns_with(name, identity=True),
        "generated": _columns_with(name, generated=True),
        "with-an-acl": _columns_with(name, column_acl=True),
    }


_QUOTED = re.compile(r"'(?:[^']|'')*'")
CONSTRAINT_ROWS = {row[0]: row for row in APPLIED_CONSTRAINTS}


def _another_literal(definition: str) -> str:
    """The definition with one quoted literal more than the reviewed one."""

    if definition.startswith("PRIMARY KEY"):
        return f"{definition} WITH (fillfactor='70')"
    return f"{definition[:-1]} AND (last_reason <> 'unexpected'::text))"


def _constraint_defects(name: str) -> dict[str, list[tuple]]:
    kind, columns, literals = apply_0012.EXPECTED_CONSTRAINTS[name]
    definition = CONSTRAINT_ROWS[name][3]
    defects = {
        "missing": [row for row in APPLIED_CONSTRAINTS if row[0] != name],
        "not-validated": _constraints_with(name, validated=False),
        "wrong-type": _constraints_with(name, type="u"),
        "wrong-columns": _constraints_with(name, columns=sorted([*columns, "updated_at_utc"])),
        "another-literal": _constraints_with(name, definition=_another_literal(definition)),
    }
    if literals:
        defects["a-literal-changed"] = _constraints_with(
            name, definition=_QUOTED.sub("'changed'", definition, count=1)
        )
        defects["no-literals"] = _constraints_with(name, definition=_QUOTED.sub("NULL", definition))
    return defects


# One changed value for every field of the security row but its name.
SECURITY_CHANGES: dict[str, Any] = {
    "relations_named_so": 2,
    "relkind": "p",
    "owned_by_applying_role": False,
    "row_level_security": False,
    "row_level_security_forced": True,
    "policies": 1,
    "public_has_a_privilege": True,
    "column_grant_to_public_anon_or_authenticated": True,
    "anon": ["SELECT"],
    "authenticated": ["SELECT"],
    "service_role": ["SELECT"],
}
_CHANGED_EXISTING = list(existing_rows())
_CHANGED_EXISTING[0] = security_row(
    "analysis_run_details", anon=["SELECT"], service_role=["INSERT", "SELECT", "UPDATE"]
)
FOREIGN_KEY = constraint_row(
    "prs_prediction_fk",
    "f",
    "FOREIGN KEY (prediction_id) REFERENCES predictions(prediction_id)",
    ["prediction_id"],
)
POST_CHECK_DIFFERENCES: dict[str, tuple[str, Any]] = {
    # The relations of public, after.
    "the-table-named-twice-in-public": (RELATIONS_SQL, relation_rows(1, **{TABLE: 2})),
    "the-retry-index-not-in-public": (RELATIONS_SQL, relation_rows(1, **{RETRY_IDX: 0})),
    "the-primary-key-index-twice-in-public": (RELATIONS_SQL, relation_rows(1, **{PKEY: 2})),
    "a-relation-missing-from-the-read-after": (RELATIONS_SQL, CREATED[:-1]),
    # The new table's security.
    **{
        f"table-{field}-changed": (TABLE_SQL, [new_table_row(**{field: value})])
        for field, value in SECURITY_CHANGES.items()
    },
    **{
        f"table-{role}-holds-{privilege}": (TABLE_SQL, [new_table_row(**{role: [privilege]})])
        for role in apply_0012.API_ROLES
        for privilege in ALL
    },
    "table-a-count-read-as-a-boolean": (TABLE_SQL, [new_table_row(relations_named_so=True)]),
    "table-read-empty": (TABLE_SQL, []),
    "table-read-twice": (TABLE_SQL, [new_table_row(), new_table_row()]),
    # Its columns.
    **{
        f"column-{row[0]}-{defect}": (COLUMNS_SQL, rows)
        for row in APPLIED_COLUMNS
        for defect, rows in _column_defects(row).items()
    },
    "column-updated_at_utc-another-default": (
        COLUMNS_SQL,
        _columns_with("updated_at_utc", default="clock_timestamp()"),
    ),
    "an-extra-column": (COLUMNS_SQL, [*APPLIED_COLUMNS, column_row("unexpected", TEXT)]),
    "two-columns-swapped": (
        COLUMNS_SQL,
        [APPLIED_COLUMNS[1], APPLIED_COLUMNS[0], *APPLIED_COLUMNS[2:]],
    ),
    "the-last-column-first": (COLUMNS_SQL, [APPLIED_COLUMNS[-1], *APPLIED_COLUMNS[:-1]]),
    # Its constraints.
    **{
        f"constraint-{name}-{defect}": (CONSTRAINTS_SQL, rows)
        for name in apply_0012.EXPECTED_CONSTRAINTS
        for defect, rows in _constraint_defects(name).items()
    },
    "an-extra-constraint": (
        CONSTRAINTS_SQL,
        by_name(
            [
                *APPLIED_CONSTRAINTS,
                constraint_row(
                    "prs_unexpected", "c", "CHECK ((attempt_count < 100))", ["attempt_count"]
                ),
            ]
        ),
    ),
    "a-foreign-key-out": (CONSTRAINTS_SQL, by_name([*APPLIED_CONSTRAINTS, FOREIGN_KEY])),
    "a-check-read-as-a-foreign-key": (
        CONSTRAINTS_SQL,
        _constraints_with("prs_status_valid", type="f"),
    ),
    "a-constraint-read-twice": (
        CONSTRAINTS_SQL,
        [*APPLIED_CONSTRAINTS, CONSTRAINT_ROWS["prs_state_shape"]],
    ),
    # Constraints anywhere that reference it.
    "a-foreign-key-in": (REFERENCING_SQL, [(1,)]),
    "the-referencing-count-read-as-a-boolean": (REFERENCING_SQL, [(False,)]),
    # Its indexes.
    **{
        f"index-{name}-missing": (INDEXES_SQL, [row for row in APPLIED_INDEXES if row[0] != name])
        for name in (PKEY, RETRY_IDX)
    },
    **{
        f"index-{name}-unique-flipped": (INDEXES_SQL, _indexes_with(name, unique=name != PKEY))
        for name in (PKEY, RETRY_IDX)
    },
    "index-pkey-other-columns": (
        INDEXES_SQL,
        _indexes_with(PKEY, columns=["prediction_id", "updated_at_utc"]),
    ),
    "index-pkey-partial": (INDEXES_SQL, _indexes_with(PKEY, predicate=RETRY_PREDICATE)),
    "index-retry-columns-swapped": (
        INDEXES_SQL,
        _indexes_with(RETRY_IDX, columns=["prediction_id", "next_eligible_utc"]),
    ),
    "index-retry-an-expression-key": (
        INDEXES_SQL,
        _indexes_with(RETRY_IDX, columns=[None, "prediction_id"]),
    ),
    "index-retry-predicate-missing": (INDEXES_SQL, _indexes_with(RETRY_IDX, predicate=None)),
    "index-retry-predicate-another-literal": (
        INDEXES_SQL,
        _indexes_with(RETRY_IDX, predicate="(resolution_status = 'QUARANTINED'::text)"),
    ),
    "index-retry-predicate-an-extra-literal": (
        INDEXES_SQL,
        _indexes_with(
            RETRY_IDX,
            predicate="(resolution_status = ANY (ARRAY['RETRYABLE'::text, 'QUARANTINED'::text]))",
        ),
    ),
    "index-retry-predicate-reads-another-column": (
        INDEXES_SQL,
        _indexes_with(RETRY_IDX, predicate="(last_reason = 'RETRYABLE'::text)"),
    ),
    "an-extra-index": (
        INDEXES_SQL,
        [
            *APPLIED_INDEXES,
            (
                "zz_prediction_resolution_status_extra",
                False,
                ["updated_at_utc"],
                None,
                "CREATE INDEX zz_prediction_resolution_status_extra ON "
                "public.prediction_resolution_status USING btree (updated_at_utc)",
            ),
        ],
    ),
    # Its triggers and rows.
    "a-trigger": (TRIGGERS_SQL, [("synthetic_trigger", "O")]),
    "a-row": (ROW_COUNT_SQL, [(1,)]),
    "the-row-count-unreadable": (ROW_COUNT_SQL, [(None,)]),
    # The existing tables and 0011's columns, which must be exactly as they were.
    "an-existing-table-s-security-changed": (EXISTING_SQL, _CHANGED_EXISTING),
    "an-existing-table-gone": (EXISTING_SQL, existing_rows()[1:]),
    "0011-s-columns-vanished-during-the-apply": (MIGRATION_0011_SQL, [([],)]),
    "0011-s-columns-changed-during-the-apply": (MIGRATION_0011_SQL, [(WITH_0011[:2],)]),
}
# The reads taken before the migration too, as a first apply finds them.
PRE_ROWS: dict[str, list[tuple]] = {
    RELATIONS_SQL: ABSENT,
    EXISTING_SQL: existing_rows(),
    MIGRATION_0011_SQL: [(list(WITH_0011),)],
}


def _post(query: str, rows: Any) -> dict[str, Any]:
    """Healthy results in which ``query`` returns ``rows`` after the migration."""

    if query in PRE_ROWS:
        return healthy_results(**{query: Each([PRE_ROWS[query], rows])})
    return healthy_results(**{query: rows})


def test_the_post_check_differences_cover_every_defect_the_spec_names() -> None:
    assert set(SECURITY_CHANGES) == set(SECURITY_FIELDS[1:])
    for role in apply_0012.API_ROLES:
        held = {key for key in POST_CHECK_DIFFERENCES if key.startswith(f"table-{role}-holds-")}
        assert held == {f"table-{role}-holds-{privilege}" for privilege in ALL}, role
    assert "MAINTAIN" in ALL
    for name in apply_0012.EXPECTED_COLUMN_NAMES:
        assert {
            key.removeprefix(f"column-{name}-")
            for key in POST_CHECK_DIFFERENCES
            if key.startswith(f"column-{name}-")
        } >= set(COLUMN_DEFECTS), name
    for name, (_, _, literals) in apply_0012.EXPECTED_CONSTRAINTS.items():
        defects = {key for key in POST_CHECK_DIFFERENCES if key.startswith(f"constraint-{name}-")}
        assert len(defects) == (7 if literals else 5), name
    for name in (PKEY, RETRY_IDX):
        for defect in ("missing", "unique-flipped"):
            assert f"index-{name}-{defect}" in POST_CHECK_DIFFERENCES


@pytest.mark.parametrize("difference", sorted(POST_CHECK_DIFFERENCES))
def test_any_difference_from_the_reviewed_result_rolls_the_apply_back(difference: str) -> None:
    query, rows = POST_CHECK_DIFFERENCES[difference]
    database = FakeDatabase(_post(query, rows))
    captured: dict[str, Any] = {}
    with pytest.raises(ProvenanceRefused, match="nothing is applied") as refused:
        apply_0012.apply_in_one_transaction(
            lambda: database.connect(DATABASE_URL), MIGRATION_SQL, captured
        )
    assert "so the transaction is rolled back" in str(refused.value)
    assert MIGRATION_SQL in database.executed(), "the difference is seen only after applying"
    assert database.executed()[-1] == MIGRATION_0011_SQL, "every post-read is taken first"
    assert database.commits == 0 and database.rollbacks == 1
    assert "committed" not in captured and "commit_attempted" not in captured
    assert all(f"post_{name}" in captured for name in POST_NAMES), "what was seen is reported"


UNIQUE_STATEMENTS = list(dict.fromkeys(EXPECTED_ORDER))


@pytest.mark.parametrize("position", range(len(UNIQUE_STATEMENTS)))
def test_a_driver_error_at_any_statement_rolls_back(position: int) -> None:
    statement = UNIQUE_STATEMENTS[position]
    database = FakeDatabase(healthy_results(), fail_on={statement: RuntimeError("boom")})
    captured: dict[str, Any] = {}
    with pytest.raises(RuntimeError):
        apply_0012.apply_in_one_transaction(
            lambda: database.connect(DATABASE_URL), MIGRATION_SQL, captured
        )
    assert database.commits == 0 and database.rollbacks == 1
    assert "committed" not in captured


@pytest.mark.parametrize(
    ("query", "rows", "message", "before"),
    [
        (RELATIONS_SQL, [(TABLE,)], "not a row of 2 values", True),
        (EXISTING_SQL, [("analysis_run_details", 1)], "not a row of 12 values", True),
        (MIGRATION_0011_SQL, [], "not one row of 1 values", True),
        (TABLE_SQL, [(TABLE, 1)], "not a row of 12 values", False),
        (COLUMNS_SQL, [("prediction_id", "text")], "not a row of 7 values", False),
        (CONSTRAINTS_SQL, [(PKEY, "p", True, "PRIMARY KEY (prediction_id)")], "of 5 values", False),
        (REFERENCING_SQL, [(0, 1)], "not one row of 1 values", False),
        (INDEXES_SQL, [(PKEY, True)], "not a row of 5 values", False),
        (TRIGGERS_SQL, [("synthetic_trigger",)], "not a row of 2 values", False),
        (ROW_COUNT_SQL, [], "not one row of 1 values", False),
    ],
)
def test_a_malformed_check_row_refuses(
    query: str, rows: list[tuple], message: str, before: bool
) -> None:
    database = FakeDatabase(healthy_results(**{query: Each([rows])}))
    with pytest.raises(ProvenanceRefused, match=message):
        _apply(database)
    assert (MIGRATION_SQL in database.executed()) is not before
    assert database.rollbacks == 1 and database.commits == 0


def _pre_dicts() -> dict[str, Any]:
    return {
        "relations": _dicts(RELATION_FIELDS, ABSENT),
        "existing": _dicts(SECURITY_FIELDS, existing_rows()),
        "migration_0011_columns_present": list(WITH_0011),
    }


def _post_dicts() -> dict[str, Any]:
    return {
        "relations": _dicts(RELATION_FIELDS, CREATED),
        "table": _dicts(SECURITY_FIELDS, [new_table_row()]),
        "columns": _dicts(COLUMN_FIELDS, APPLIED_COLUMNS),
        "constraints": _dicts(CONSTRAINT_FIELDS, APPLIED_CONSTRAINTS),
        "referencing_constraints": 0,
        "indexes": _dicts(INDEX_FIELDS, APPLIED_INDEXES),
        "triggers": [],
        "row_count": 0,
        "existing": _dicts(SECURITY_FIELDS, existing_rows()),
        "migration_0011_columns_present": list(WITH_0011),
    }


def test_the_judges_name_every_difference_not_only_the_first() -> None:
    pre, post = _pre_dicts(), _post_dicts()
    assert apply_0012.pre_check_failures(pre) == []
    assert apply_0012.post_check_failures(pre, post) == []

    second = {**pre, "relations": _dicts(RELATION_FIELDS, CREATED)}
    assert len(apply_0012.pre_check_failures(second)) == 3

    every_security_field = {"table": TABLE, **SECURITY_CHANGES}
    assert len(apply_0012.table_post_check_failures([every_security_field])) == 11

    every_column_field = [
        {
            "column": name,
            "type": "bytea",
            "not_null": not not_null,
            "default": "'x'::text",
            **dict.fromkeys(apply_0012.COLUMN_FLAGS_OFF, True),
        }
        for name, _, not_null, _ in apply_0012.EXPECTED_COLUMNS
    ]
    assert len(apply_0012.column_post_check_failures(every_column_field)) == 13 * 6

    every_constraint_field = [
        {
            "constraint": name,
            "type": "u",
            "validated": False,
            "definition": "CHECK (('zz'::text <> 'yy'::text))",
            "columns": ["zz"],
        }
        for name in sorted(apply_0012.EXPECTED_CONSTRAINTS)
    ]
    assert len(apply_0012.constraint_post_check_failures(every_constraint_field)) == 9 * 4

    every_index_field = [
        {"index": PKEY, "unique": False, "columns": [], "predicate": RETRY_PREDICATE},
        {"index": RETRY_IDX, "unique": True, "columns": [], "predicate": None},
    ]
    assert len(apply_0012.index_post_check_failures(every_index_field)) == 2 * 3

    changed = {
        "relations": _dicts(RELATION_FIELDS, relation_rows(1, **{TABLE: 2})),
        "table": _dicts(SECURITY_FIELDS, [new_table_row(policies=1)]),
        "columns": _dicts(COLUMN_FIELDS, _columns_with("attempt_count", identity=True)),
        "constraints": _dicts(
            CONSTRAINT_FIELDS, _constraints_with("prs_state_shape", validated=False)
        ),
        "referencing_constraints": 1,
        "indexes": _dicts(INDEX_FIELDS, _indexes_with(RETRY_IDX, predicate=None)),
        "triggers": [{"trigger": "synthetic_trigger", "enabled": "O"}],
        "row_count": 2,
        "existing": [{**pre["existing"][0], "service_role": []}, *pre["existing"][1:]],
        "migration_0011_columns_present": [],
    }
    failures = apply_0012.post_check_failures(pre, changed)
    assert len(failures) == 10, failures
    assert "2 relations in public" in failures[0]
    assert "policies is 1, not 0" in failures[1]
    assert "attempt_count: identity is True" in failures[2]
    assert "prs_state_shape: is not validated" in failures[3]
    assert f"1 constraints reference {TABLE}" in failures[4]
    assert "prediction_resolution_status_retry_idx: its predicate None" in failures[5]
    assert "synthetic_trigger" in failures[6]
    assert f"2 rows are in {TABLE}" in failures[7]
    assert "analysis_run_details" in failures[8]
    assert "0011's columns on predictions" in failures[9]


# --------------------------------------------------------------------------- the dispatch


def _dispatch(**changes: str) -> dict[str, str]:
    values = {
        "github_actions": "true",
        "event_name": "workflow_dispatch",
        "repository": REPOSITORY,
        "workflow_ref": f"{REPOSITORY}/{apply_0012.WORKFLOW}@refs/heads/main",
        "ref": "refs/heads/main",
        "sha": SHA,
        "run_id": "123456789",
        "run_attempt": "1",
    }
    values.update(changes)
    return values


def _runtime(**changes: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "git_head": SHA,
        "tracked_tree_clean": True,
        "python_implementation": "CPython",
        "python_version": "3.13.14",
        "interpreter_flags": REQUIRED_FLAGS_TEXT,
        "installed_files_sha256": "e" * 64,
    }
    values.update(changes)
    return values


def test_a_verified_dispatch_records_this_workflow() -> None:
    record = apply_0012.verify_dispatch(_dispatch(), _runtime(), expected_sha=SHA)
    assert record["dispatch_verified"] is True
    assert record["schema_version"] == apply_0012.DISPATCH_SCHEMA
    assert record["workflow"] == apply_0012.WORKFLOW
    assert record["expected_sha"] == record["sha"] == record["git_head"] == SHA


DISPATCH_REFUSALS = {
    "not-actions": (_dispatch(github_actions=""), _runtime(), SHA),
    "push-event": (_dispatch(event_name="push"), _runtime(), SHA),
    "pull-request": (_dispatch(event_name="pull_request"), _runtime(), SHA),
    "schedule": (_dispatch(event_name="schedule"), _runtime(), SHA),
    "other-branch": (_dispatch(ref="refs/heads/feature"), _runtime(), SHA),
    "the-0010-workflow": (
        _dispatch(workflow_ref=f"{REPOSITORY}/{apply_0010.WORKFLOW}@refs/heads/main"),
        _runtime(),
        SHA,
    ),
    "the-0010-rehearsal-workflow": (
        _dispatch(workflow_ref=f"{REPOSITORY}/{apply_0010.REHEARSAL_WORKFLOW}@refs/heads/main"),
        _runtime(),
        SHA,
    ),
    "the-0011-workflow": (
        _dispatch(workflow_ref=f"{REPOSITORY}/{apply_0011.WORKFLOW}@refs/heads/main"),
        _runtime(),
        SHA,
    ),
    "the-evaluation-workflow": (
        _dispatch(
            workflow_ref=f"{REPOSITORY}/.github/workflows/section-5a-evaluation.yml@refs/heads/main"
        ),
        _runtime(),
        SHA,
    ),
    "workflow-from-a-branch": (
        _dispatch(workflow_ref=f"{REPOSITORY}/{apply_0012.WORKFLOW}@refs/heads/feature"),
        _runtime(),
        SHA,
    ),
    "self-consistent-fork": (
        _dispatch(
            repository="attacker/fork",
            workflow_ref=f"attacker/fork/{apply_0012.WORKFLOW}@refs/heads/main",
        ),
        _runtime(),
        SHA,
    ),
    "short-sha": (_dispatch(sha=SHA[:7]), _runtime(git_head=SHA[:7]), SHA[:7]),
    "uppercase-sha": (_dispatch(sha=SHA.upper()), _runtime(git_head=SHA.upper()), SHA.upper()),
    "sha-with-newline": (_dispatch(sha=SHA + "\n"), _runtime(git_head=SHA + "\n"), SHA + "\n"),
    "dispatched-other-commit": (_dispatch(sha="f" * 40), _runtime(), SHA),
    "checked-out-other-commit": (_dispatch(), _runtime(git_head="f" * 40), SHA),
    "dirty-tree": (_dispatch(), _runtime(tracked_tree_clean=False), SHA),
    "unknown-tree": (_dispatch(), _runtime(tracked_tree_clean=None), SHA),
    "other-python": (_dispatch(), _runtime(python_version="3.13.13"), SHA),
    "other-implementation": (_dispatch(), _runtime(python_implementation="PyPy"), SHA),
    "not-isolated": (_dispatch(), _runtime(interpreter_flags=""), SHA),
    "unverified-install": (_dispatch(), _runtime(installed_files_sha256=""), SHA),
    "install-digest-with-newline": (
        _dispatch(),
        _runtime(installed_files_sha256="e" * 64 + "\n"),
        SHA,
    ),
    "bad-run-id": (_dispatch(run_id="x"), _runtime(), SHA),
    "run-id-with-newline": (_dispatch(run_id="123\n"), _runtime(), SHA),
    "bad-attempt": (_dispatch(run_attempt=""), _runtime(), SHA),
}


@pytest.mark.parametrize("case", sorted(DISPATCH_REFUSALS))
def test_every_dispatch_deviation_refuses(case: str) -> None:
    dispatch, runtime, expected = DISPATCH_REFUSALS[case]
    with pytest.raises(ProvenanceRefused, match="dispatch does not verify"):
        apply_0012.verify_dispatch(dispatch, runtime, expected_sha=expected)


def test_different_migration_bytes_refuse_before_any_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(apply_0012, "MIGRATION_SHA256", "0" * 64)
    with pytest.raises(ProvenanceRefused, match="not the reviewed"):
        apply_0012.migration_bytes()


def test_the_reviewed_bytes_are_read_from_this_commit() -> None:
    assert apply_0012.migration_bytes() == MIGRATION_BYTES


# --------------------------------------------------------------------------- the entrypoint


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Isolation, attestation and the driver, replaced by recorders. Nothing real is entered."""

    events: list[str] = []

    def _enter(wheelhouse: str):
        events.append(f"enter:{wheelhouse}")
        return "isolation-report"

    def _attest(expected_sha, environ, isolation):
        events.append(f"attest:{expected_sha}")
        return {"dispatch_verified": True, "workflow": apply_0012.WORKFLOW}

    monkeypatch.setattr(apply_0012, "enter_isolated_runtime", _enter)
    monkeypatch.setattr(apply_0012, "attest_dispatch", _attest)
    monkeypatch.setattr(
        apply_0012, "attest_loaded_modules", lambda isolation: events.append("modules")
    )
    return events


def _argv(mode: str, tmp_path: Path, **overrides: str) -> list[str]:
    options = {
        "mode": mode,
        "expected-sha": SHA,
        "confirm": apply_0012.CONFIRMATION,
        "wheelhouse": "/synthetic/runner-temp/section-5a-wheels",
        "report": str(tmp_path / "report.json"),
        **overrides,
    }
    return [f"--{name}={value}" for name, value in options.items() if value is not None]


def _install_driver(monkeypatch: pytest.MonkeyPatch, database: FakeDatabase, events: list[str]):
    def _load():
        events.append("driver")
        return database

    monkeypatch.setattr(apply_0012, "load_driver", _load)


def test_apply_refuses_without_the_exact_token_before_anything_is_entered(
    calls: list[str], tmp_path: Path
) -> None:
    for token in (
        "",
        "apply",
        apply_0012.CONFIRMATION.lower(),
        apply_0012.CONFIRMATION + " ",
        "APPLY-MIGRATION-0011-ONCE",
    ):
        assert apply_0012.main(_argv("apply", tmp_path, confirm=token), environ={}) == 2
    assert calls == []
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["outcome"] == "REFUSED" and report["committed"] is False
    assert apply_0012.CONFIRMATION in report["detail"]
    assert report["detail"].startswith("migration 0012 refused; nothing is applied: ")


def test_attest_mode_touches_no_database(
    calls: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(healthy_results())
    _install_driver(monkeypatch, database, calls)
    code = apply_0012.main(
        _argv("attest", tmp_path, confirm=""), environ={"SUPABASE_DB_URL": DATABASE_URL}
    )
    assert code == 0
    assert calls == [
        "enter:/synthetic/runner-temp/section-5a-wheels",
        f"attest:{SHA}",
        "modules",
        "driver",
        "modules",
    ]
    assert database.connects == [] and database.statements == []
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["touches_database"] is False
    assert report["migration_sha256"] == apply_0012.MIGRATION_SHA256
    assert report["schema_version"] == apply_0012.REPORT_SCHEMA


def test_apply_without_a_database_url_refuses_before_the_driver_loads(
    calls: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(healthy_results())
    _install_driver(monkeypatch, database, calls)
    assert apply_0012.main(_argv("apply", tmp_path), environ={}) == 2
    assert "driver" not in calls and database.connects == []


def test_a_full_apply_reports_raw_results_without_the_url(
    calls: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = FakeDatabase(healthy_results())
    _install_driver(monkeypatch, database, calls)
    code = apply_0012.main(_argv("apply", tmp_path), environ={"SUPABASE_DB_URL": DATABASE_URL})
    assert code == 0
    assert calls == [
        "enter:/synthetic/runner-temp/section-5a-wheels",
        f"attest:{SHA}",
        "modules",
        "driver",
        "modules",
    ]
    assert database.connects == [(DATABASE_URL, {"connect_timeout": 8})]
    assert database.commits == 1
    report_text = (tmp_path / "report.json").read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert report["outcome"] == "APPLIED" and report["mode"] == "apply"
    assert report["executed_migration_sha256"] == report["migration_sha256"]
    assert report["post_columns"][-1]["column"] == "updated_at_utc"
    assert report["post_constraints"] == _dicts(CONSTRAINT_FIELDS, APPLIED_CONSTRAINTS)
    assert report["post_indexes"] == _dicts(INDEX_FIELDS, APPLIED_INDEXES)
    assert report["pre_migration_0011_columns_present"] == WITH_0011
    assert report["post_migration_0011_columns_present"] == WITH_0011
    for name in PRE_NAMES:
        assert f"pre_{name}" in report, name
    for name in POST_NAMES:
        assert f"post_{name}" in report, name
    streams = capsys.readouterr()
    for text in (report_text, streams.out, streams.err):
        assert "NEVER-SHOWN-SECRET" not in text and "never-contacted" not in text


def test_a_refused_apply_reports_what_it_saw_and_commits_nothing(
    calls: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(healthy_results(**{RELATIONS_SQL: CREATED}))
    _install_driver(monkeypatch, database, calls)
    code = apply_0012.main(_argv("apply", tmp_path), environ={"SUPABASE_DB_URL": DATABASE_URL})
    assert code == 2
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["outcome"] == "REFUSED" and report["committed"] is False
    assert apply_0012.NOT_A_FIRST_APPLY in report["detail"]
    assert report["captured"]["pre_relations"] == _dicts(RELATION_FIELDS, CREATED)
    assert report["captured"]["pre_migration_0011_columns_present"] == WITH_0011
    assert "executed_migration_sha256" not in report["captured"]
    assert database.commits == 0


def test_an_unexpected_failure_withholds_its_message_because_it_can_name_the_host(
    calls: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    error = RuntimeError(f"connection to server at {DATABASE_URL} failed")
    database = FakeDatabase(healthy_results(), fail_on={apply_0012.ROLES_SQL: error})
    _install_driver(monkeypatch, database, calls)
    code = apply_0012.main(_argv("apply", tmp_path), environ={"SUPABASE_DB_URL": DATABASE_URL})
    assert code == 1
    report_text = (tmp_path / "report.json").read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert report["outcome"] == "FAILED" and report["error_type"] == "RuntimeError"
    streams = capsys.readouterr()
    for text in (report_text, streams.out, streams.err):
        assert "NEVER-SHOWN-SECRET" not in text and "never-contacted" not in text
    assert database.rollbacks == 1 and database.commits == 0


def test_a_commit_that_fails_in_flight_is_reported_as_unknown(
    calls: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(healthy_results())
    database.fail_commit = ConnectionError(f"server closed the connection: {DATABASE_URL}")
    _install_driver(monkeypatch, database, calls)
    code = apply_0012.main(_argv("apply", tmp_path), environ={"SUPABASE_DB_URL": DATABASE_URL})
    assert code == 1
    report_text = (tmp_path / "report.json").read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert report["outcome"] == "FAILED" and report["error_type"] == "ConnectionError"
    assert report["committed"] == apply_0012.COMMIT_UNKNOWN == "UNKNOWN"
    assert report["captured"]["commit_attempted"] is True
    assert "committed" not in report["captured"]
    assert "post_row_count" in report["captured"], "the post-checks had passed"
    assert "NEVER-SHOWN-SECRET" not in report_text and "never-contacted" not in report_text


@pytest.mark.parametrize(
    ("captured", "expected"),
    [
        ({}, False),
        ({"pre_relations": []}, False),
        ({"commit_attempted": True}, "UNKNOWN"),
        ({"commit_attempted": True, "committed": True}, True),
        ({"committed": "yes"}, False),
        ({"first_apply": {"commit_attempted": True, "committed": True}, "second_apply": {}}, True),
        ({"first_apply": {"commit_attempted": True}}, "UNKNOWN"),
        ({"first_apply": {"pre_relations": []}}, False),
    ],
)
def test_the_commit_state_is_never_claimed_without_a_returned_commit(
    captured: dict[str, Any], expected: object
) -> None:
    assert apply_0012._commit_state(captured) == expected


def test_the_loaded_module_check_covers_the_pin_and_this_script(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from crypto_probability_engine import runtime_isolation
    from crypto_probability_engine.oos.evaluation.evaluator_pin import pinned_files

    seen: dict[str, Any] = {}

    def _attest(report, *, pinned, root):
        seen.update(pinned=tuple(pinned), root=root)
        return 1

    monkeypatch.setattr(runtime_isolation, "attest_loaded_modules", _attest)
    apply_0012.attest_loaded_modules("isolation")
    assert seen["pinned"] == (*pinned_files(ROOT), apply_0012.SCRIPT)
    assert Path(seen["root"]).resolve() == ROOT


# --------------------------------------------------------------------------- the rehearsal mode


def _rehearsal_results() -> dict[str, Any]:
    """The scratch database: the first apply succeeds, the second finds the table already there."""

    return healthy_results(REHEARSAL_SERVER)


def test_a_rehearsal_applies_once_and_proves_a_second_apply_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(_rehearsal_results())
    _install_driver(monkeypatch, database, [])
    environ = {apply_0012.REHEARSAL_URL_VARIABLE: REHEARSAL_URL}
    code = apply_0012.main(_argv("rehearse", tmp_path, wheelhouse="", confirm=""), environ=environ)
    assert code == 0
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["outcome"] == "REHEARSED" and report["mode"] == "rehearse"
    assert report["first_apply"]["outcome"] == "APPLIED"
    assert report["first_apply"]["server_version_num"] == REHEARSAL_SERVER
    assert report["first_apply"]["table_privileges_asked"] == REHEARSAL_ALL
    assert report["first_apply"]["pre_migration_0011_columns_present"] == WITH_0011
    assert apply_0012.NOT_A_FIRST_APPLY in report["second_apply_refusal"]
    assert report["second_apply_captured"]["pre_relations"] == _dicts(RELATION_FIELDS, CREATED)
    assert "executed_migration_sha256" not in report["second_apply_captured"]
    assert database.connects == [
        (REHEARSAL_URL, {"connect_timeout": 8}),
        (REHEARSAL_URL, {"connect_timeout": 8}),
    ]
    assert database.commits == 1 and database.rollbacks == 1


def test_a_rehearsal_whose_second_apply_succeeds_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    results = _rehearsal_results()
    results[RELATIONS_SQL] = Each([ABSENT, CREATED] * 2)
    database = FakeDatabase(results)
    _install_driver(monkeypatch, database, [])
    environ = {apply_0012.REHEARSAL_URL_VARIABLE: REHEARSAL_URL}
    code = apply_0012.main(_argv("rehearse", tmp_path, wheelhouse="", confirm=""), environ=environ)
    assert code == 2
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert "one-shot property does not hold" in report["detail"]
    assert report["committed"] is True, "both scratch applies committed"


def test_a_rehearsal_commit_that_fails_in_flight_is_reported_as_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(_rehearsal_results())
    database.fail_commit = ConnectionError("server closed the connection")
    _install_driver(monkeypatch, database, [])
    environ = {apply_0012.REHEARSAL_URL_VARIABLE: REHEARSAL_URL}
    code = apply_0012.main(_argv("rehearse", tmp_path, wheelhouse="", confirm=""), environ=environ)
    assert code == 1
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["outcome"] == "FAILED" and report["committed"] == "UNKNOWN"
    assert report["captured"]["first_apply"]["commit_attempted"] is True


def test_a_rehearsal_whose_second_apply_fails_otherwise_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    results = _rehearsal_results()
    results[apply_0012.ROLES_SQL] = Each([[(3,)], [(2,)]])
    database = FakeDatabase(results)
    _install_driver(monkeypatch, database, [])
    environ = {apply_0012.REHEARSAL_URL_VARIABLE: REHEARSAL_URL}
    code = apply_0012.main(_argv("rehearse", tmp_path, wheelhouse="", confirm=""), environ=environ)
    assert code == 2
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert "Supabase API roles" in report["detail"]
    assert report["committed"] is True, "the first scratch apply committed"


@pytest.mark.parametrize(
    "url",
    [
        "",
        DATABASE_URL,
        "postgresql://localhost/migration_0012_rehearsal",
        "postgresql://user@/migration_0012_rehearsal?host=/var/run/postgresql",
        "postgresql:///migration_0012_rehearsal?host=/tmp",
        "postgresql:///migration_0012_rehearsal?host=/var/run/postgresql&sslmode=disable",
        "postgresql:///migration_0012_rehearsal?host=/var/run/postgresql\n",
        "POSTGRESQL:///migration_0012_rehearsal?host=/var/run/postgresql",
        "postgres:///migration_0012_rehearsal?host=/var/run/postgresql",
        "postgresql:///Rehearsal?host=/var/run/postgresql",
    ],
)
def test_the_rehearsal_only_ever_reaches_a_local_socket(
    url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(_rehearsal_results())
    events: list[str] = []
    _install_driver(monkeypatch, database, events)
    code = apply_0012.main(
        _argv("rehearse", tmp_path, wheelhouse="", confirm=""),
        environ={apply_0012.REHEARSAL_URL_VARIABLE: url},
    )
    assert code == 2 and database.connects == [] and events == []


def test_the_rehearsal_never_runs_beside_the_production_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(_rehearsal_results())
    _install_driver(monkeypatch, database, [])
    environ = {apply_0012.REHEARSAL_URL_VARIABLE: REHEARSAL_URL, "SUPABASE_DB_URL": DATABASE_URL}
    code = apply_0012.main(_argv("rehearse", tmp_path, wheelhouse="", confirm=""), environ=environ)
    assert code == 2 and database.connects == []
    report_text = (tmp_path / "report.json").read_text(encoding="utf-8")
    assert "production database secret" in json.loads(report_text)["detail"]
    assert "NEVER-SHOWN-SECRET" not in report_text and "never-contacted" not in report_text


def test_the_rehearsal_is_isolated_when_given_the_wheelhouse(
    calls: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(_rehearsal_results())
    _install_driver(monkeypatch, database, calls)
    environ = {apply_0012.REHEARSAL_URL_VARIABLE: REHEARSAL_URL}
    code = apply_0012.main(_argv("rehearse", tmp_path, confirm=""), environ=environ)
    assert code == 0
    assert calls == ["enter:/synthetic/runner-temp/section-5a-wheels", "driver", "modules"]


# --------------------------------------------------------------------------- the process


def _scrubbed_environment(extra: dict[str, str]) -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GITHUB_", "RUNNER_", "SUPABASE_", "PYTHON", "MIGRATION_"))
        and key != "ImageOS"
    }
    environment.update(extra)
    return environment


def test_an_unisolated_process_refuses_before_any_database_access(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    completed = subprocess.run(
        [sys.executable, "-B", apply_0012.SCRIPT, *_argv("apply", tmp_path, report=str(report))],
        cwd=ROOT,
        env=_scrubbed_environment({"SUPABASE_DB_URL": DATABASE_URL}),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert completed.returncode == 2, completed.stderr
    assert "python -I -S -B" in completed.stderr
    recorded = report.read_text(encoding="utf-8")
    assert json.loads(recorded)["outcome"] == "REFUSED"
    for text in (recorded, completed.stdout, completed.stderr):
        assert "NEVER-SHOWN-SECRET" not in text and "never-contacted" not in text
