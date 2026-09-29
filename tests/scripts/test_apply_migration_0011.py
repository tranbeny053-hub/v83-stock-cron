"""The one-shot apply of migration 0011 (target contract v1's columns). No database is contacted.

Every database interaction runs against a fake driver that behaves like psycopg 3 where it matters:
a connection used as a context manager commits on success and rolls back on an exception, a
statement is recorded with its parameters, and a check read before and after the migration can
return different rows. The real PostgreSQL rehearsal runs inside the dispatch job
(.github/workflows/apply-migration-0011.yml), before the secret is handed to any step.
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
from scripts import audit_table_privileges as audit

ROOT = Path(__file__).resolve().parents[2]
MIGRATION_BYTES = (ROOT / apply_0011.MIGRATION).read_bytes()
MIGRATION_SQL = MIGRATION_BYTES.decode("utf-8")
DATABASE_URL = "postgresql://owner:NEVER-SHOWN-SECRET@db.never-contacted.invalid:5432/postgres"
REHEARSAL_URL = "postgresql:///migration_0011_rehearsal?host=/var/run/postgresql"
SHA = "c" * 40
REPOSITORY = apply_0011.EXPECTED_REPOSITORY
# Production is Supabase PostgreSQL 17.6. The CI rehearsal runs Ubuntu 24.04's PostgreSQL 16,
# which has no MAINTAIN.
PRODUCTION_SERVER = 170006
REHEARSAL_SERVER = 160010
ALL = list(apply_0011.table_privileges_for(PRODUCTION_SERVER))
REHEARSAL_ALL = list(apply_0011.table_privileges_for(REHEARSAL_SERVER))
PREDICTIONS_SQL = apply_0011.predictions_security_sql(PRODUCTION_SERVER)
OTHER_SQL = apply_0011.other_security_sql(PRODUCTION_SERVER)
COLUMNS_SQL = apply_0011.COLUMNS_SQL
CONSTRAINTS_SQL = apply_0011.CONSTRAINTS_SQL
INDEXES_SQL = apply_0011.INDEXES_SQL
TRIGGERS_SQL = apply_0011.TRIGGERS_SQL
COLUMN_FIELDS = apply_0011.COLUMN_FIELDS
CONSTRAINT_FIELDS = apply_0011.CONSTRAINT_FIELDS
NEW_COLUMN_NAMES = [name for name, _ in apply_0011.NEW_COLUMNS]
CHECK_NAMES = ("predictions", "columns", "constraints", "indexes", "triggers", "other")


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


# ------------------------------------------------------------------------ production after 0010


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
    return tuple(values[field] for field in apply_0011.SECURITY_FIELDS)


def other_rows(privileges: list[str] = ALL) -> list[tuple]:
    """The other tables: the legacy ones as 0010 left them, the later ones as they grant."""

    granted = {
        "analysis_run_details": ["INSERT", "SELECT", "UPDATE"],
        "prediction_derivatives_snapshots": ["INSERT", "SELECT"],
        "section_5a_evaluation_seal": [],
    }
    return [
        security_row(table, privileges=granted.get(table, privileges))
        for table in apply_0011.OTHER_TABLES
    ]


def column_row(name: str, type_name: str, **flags: bool) -> tuple:
    values = {
        "column": name,
        "type": type_name,
        **dict.fromkeys(apply_0011.NEW_COLUMN_FLAGS, False),
        **flags,
    }
    return tuple(values[field] for field in COLUMN_FIELDS)


TEXT = "text"
TIMESTAMPTZ = "timestamp with time zone"
# Predictions' columns after migrations 0003 and 0007, in their physical order.
EXISTING_COLUMNS = [
    column_row("prediction_id", TEXT, not_null=True),
    column_row("run_id", TEXT, not_null=True),
    column_row("operator_id", TEXT),
    column_row("symbol", TEXT, not_null=True),
    column_row("normalized_symbol", TEXT, not_null=True),
    column_row("timeframe", TEXT, not_null=True),
    column_row("horizon_bars", "integer", not_null=True),
    column_row("predicted_at_utc", TIMESTAMPTZ, not_null=True),
    column_row("reference_close_utc", TIMESTAMPTZ, not_null=True),
    column_row("reference_price", "numeric", not_null=True),
    column_row("horizon_end_utc", TIMESTAMPTZ, not_null=True),
    column_row("p_up_frac", "numeric", not_null=True),
    column_row("p_down_frac", "numeric", not_null=True),
    column_row("p_timeout_frac", "numeric", not_null=True),
    column_row("decision_band_frac", "numeric"),
    column_row("model_version", TEXT, not_null=True),
    column_row("methodology_version", TEXT, not_null=True),
    column_row("calibration_status", TEXT, not_null=True),
    column_row("reliability_status", TEXT, not_null=True),
    column_row("epistemic_sufficiency", TEXT),
    column_row("gate_action", TEXT),
    column_row("data_source", TEXT),
    column_row("is_live_data", "boolean", not_null=True, has_default=True),
    column_row("cross_provider_state", TEXT),
    column_row("created_at", TIMESTAMPTZ, not_null=True, has_default=True),
    column_row("prediction_origin", TEXT, not_null=True, has_default=True),
]
NEW_COLUMN_ROWS = [column_row(name, type_name) for name, type_name in apply_0011.NEW_COLUMNS]
APPLIED_COLUMNS = [*EXISTING_COLUMNS, *NEW_COLUMN_ROWS]


def constraint_row(
    name: str, kind: str, definition: str, columns: list[str], *, validated: bool = True
) -> tuple:
    return (name, kind, validated, definition, list(columns))


def by_name(rows: list[tuple]) -> list[tuple]:
    """In the order the check returns them: by name, bytewise."""

    return sorted(rows, key=lambda row: row[0])


EXISTING_CONSTRAINTS = [
    constraint_row("predictions_pkey", "p", "PRIMARY KEY (prediction_id)", ["prediction_id"]),
    constraint_row(
        "predictions_prediction_origin_chk",
        "c",
        "CHECK ((prediction_origin = ANY (ARRAY['USER_REQUESTED'::text, "
        "'CONTROLLED_SMOKE'::text, 'SCHEDULED_SHADOW_EVIDENCE'::text])))",
        ["prediction_origin"],
    ),
]
# How PostgreSQL 16 and 17 deparse 0011's three constraints.
NEW_CONSTRAINT_ROWS = {
    "predictions_target_version_chk": constraint_row(
        "predictions_target_version_chk",
        "c",
        "CHECK (((target_version IS NULL) OR (target_version = 'tc-v1'::text)))",
        ["target_version"],
    ),
    "predictions_reference_venue_chk": constraint_row(
        "predictions_reference_venue_chk",
        "c",
        "CHECK (((reference_venue IS NULL) OR (reference_venue = ANY "
        "(ARRAY['BINANCE_PUBLIC'::text, 'OKX_PUBLIC'::text]))))",
        ["reference_venue"],
    ),
    "predictions_target_stamp_chk": constraint_row(
        "predictions_target_stamp_chk",
        "c",
        "CHECK ((((target_version IS NULL) AND (reference_venue IS NULL) AND "
        "(core_computed_at_utc IS NULL) AND (issued_at_utc IS NULL)) OR "
        "((target_version IS NOT NULL) AND (reference_venue IS NOT NULL) AND "
        "(core_computed_at_utc IS NOT NULL) AND (issued_at_utc IS NOT NULL) AND "
        "(core_computed_at_utc <= issued_at_utc))))",
        ["core_computed_at_utc", "issued_at_utc", "reference_venue", "target_version"],
    ),
}
APPLIED_CONSTRAINTS = by_name([*EXISTING_CONSTRAINTS, *NEW_CONSTRAINT_ROWS.values()])
INDEXES = [
    (
        "idx_predictions_horizon_end",
        "CREATE INDEX idx_predictions_horizon_end ON public.predictions USING btree "
        "(horizon_end_utc)",
    ),
    (
        "idx_predictions_model_timeframe",
        "CREATE INDEX idx_predictions_model_timeframe ON public.predictions USING btree "
        "(model_version, timeframe)",
    ),
    (
        "idx_predictions_origin_methodology_tf",
        "CREATE INDEX idx_predictions_origin_methodology_tf ON public.predictions USING btree "
        "(prediction_origin, methodology_version, timeframe)",
    ),
    (
        "idx_predictions_symbol_timeframe_predicted",
        "CREATE INDEX idx_predictions_symbol_timeframe_predicted ON public.predictions USING "
        "btree (normalized_symbol, timeframe, predicted_at_utc DESC)",
    ),
    (
        "predictions_pkey",
        "CREATE UNIQUE INDEX predictions_pkey ON public.predictions USING btree (prediction_id)",
    ),
]
# The migrations create no trigger on predictions. One synthetic trigger shows a change is seen.
TRIGGERS = [("synthetic_trigger", "O")]


def healthy_results(version: int = PRODUCTION_SERVER, **overrides: Any) -> dict[str, Any]:
    """What a first apply returns on production as migrations 0001-0010 left it."""

    privileges = list(apply_0011.table_privileges_for(version))
    results: dict[str, Any] = {
        apply_0011.ROLES_SQL: [(3,)],
        apply_0011.SERVER_VERSION_SQL: [(version,)],
        apply_0011.predictions_security_sql(version): [
            security_row("predictions", privileges=privileges)
        ],
        COLUMNS_SQL: Each([EXISTING_COLUMNS, APPLIED_COLUMNS]),
        CONSTRAINTS_SQL: Each([EXISTING_CONSTRAINTS, APPLIED_CONSTRAINTS]),
        INDEXES_SQL: list(INDEXES),
        TRIGGERS_SQL: list(TRIGGERS),
        apply_0011.other_security_sql(version): other_rows(privileges),
    }
    results.update(overrides)
    return results


READS = [PREDICTIONS_SQL, COLUMNS_SQL, CONSTRAINTS_SQL, INDEXES_SQL, TRIGGERS_SQL, OTHER_SQL]
EXPECTED_ORDER = [
    *apply_0011.TIMEOUT_STATEMENTS,
    apply_0011.ADVISORY_LOCK_SQL,
    apply_0011.ROLES_SQL,
    apply_0011.SERVER_VERSION_SQL,
    *READS,
    MIGRATION_SQL,
    *READS,
]


def _apply(database: FakeDatabase) -> tuple[dict[str, Any], dict[str, Any]]:
    captured: dict[str, Any] = {}
    outcome = apply_0011.apply_in_one_transaction(
        lambda: database.connect(DATABASE_URL), MIGRATION_SQL, captured
    )
    return outcome, captured


def _dicts(fields: tuple[str, ...], rows: list[tuple]) -> list[dict[str, Any]]:
    return [dict(zip(fields, row, strict=True)) for row in rows]


# --------------------------------------------------------------------------- the contract


def test_the_script_imports_only_the_standard_library_at_module_level() -> None:
    tree = ast.parse((ROOT / apply_0011.SCRIPT).read_text(encoding="utf-8"))
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
    assert (ROOT / apply_0011.SCRIPT).resolve() == Path(apply_0011.__file__).resolve()
    assert (ROOT / apply_0011.WORKFLOW).is_file()
    assert not hasattr(apply_0011, "REHEARSAL_WORKFLOW"), "dispatch-only: no rehearsal workflow"
    assert hashlib.sha256(MIGRATION_BYTES).hexdigest() == apply_0011.MIGRATION_SHA256
    assert apply_0011.MIGRATION_SHA256 == (
        "de83e973a5ad607a8c57a8c5507f8e5b316337ea1a871174cc3b2d4dee52683e"
    )
    assert apply_0011.CONFIRMATION == "APPLY-MIGRATION-0011-ONCE"
    assert apply_0011.REPORT_SCHEMA == "migration-0011-apply-report.v1"
    assert apply_0011.DISPATCH_SCHEMA == "migration-0011-dispatch.v1"
    assert apply_0011.EXPECTED_REPOSITORY == "tranbeny053-hub/v83-stock-cron"


def test_its_lock_token_and_workflow_are_its_own() -> None:
    from scripts import apply_migration_0008

    assert apply_0011.ADVISORY_LOCK_SQL == "SELECT pg_advisory_xact_lock(5000011)"
    assert apply_0011.ADVISORY_LOCK_SQL not in {
        apply_migration_0008.ADVISORY_LOCK_SQL,
        "SELECT pg_advisory_xact_lock(5009005)",
        apply_0010.ADVISORY_LOCK_SQL,
    }
    assert apply_0011.CONFIRMATION not in {
        apply_migration_0008.CONFIRMATION,
        apply_0010.CONFIRMATION,
    }
    assert apply_0011.WORKFLOW not in {
        apply_migration_0008.WORKFLOW,
        apply_0010.WORKFLOW,
        apply_0010.REHEARSAL_WORKFLOW,
    }
    assert apply_0011.REHEARSAL_URL_VARIABLE == "MIGRATION_0011_REHEARSAL_URL"


@pytest.mark.parametrize("version", [150000, 160010, 170006])
def test_it_shares_0010_s_trust_boundary_and_security_check(version: int) -> None:
    """The copied security check produces exactly 0010's SQL; the boundary constants match."""

    privileges = apply_0010.table_privileges_for(version)
    assert apply_0011.table_privileges_for(version) == privileges
    assert apply_0011.SECURITY_FIELDS == apply_0010.SECURITY_FIELDS
    assert apply_0011.predictions_security_sql(version) == apply_0010._security_sql(
        ("predictions",), privileges
    )
    assert apply_0011.other_security_sql(version) == apply_0010._security_sql(
        apply_0011.OTHER_TABLES, privileges
    )
    assert apply_0011.ROLES_SQL == apply_0010.ROLES_SQL
    assert apply_0011.SERVER_VERSION_SQL == apply_0010.SERVER_VERSION_SQL
    assert apply_0011.TIMEOUT_STATEMENTS == apply_0010.TIMEOUT_STATEMENTS
    assert apply_0011.MINIMUM_SERVER_VERSION == apply_0010.MINIMUM_SERVER_VERSION
    for name in ("EXPECTED_REPOSITORY", "PINNED_PYTHON", "REQUIRED_EVENT", "REQUIRED_REF"):
        assert getattr(apply_0011, name) == getattr(apply_0010, name), name
    assert apply_0011._LOCAL_SOCKET_URL.pattern == apply_0010._LOCAL_SOCKET_URL.pattern


def test_its_new_columns_and_constraints_are_the_reviewed_ones() -> None:
    assert apply_0011.TABLE == "predictions"
    assert apply_0011.NEW_COLUMNS == (
        ("target_version", "text"),
        ("reference_venue", "text"),
        ("core_computed_at_utc", "timestamp with time zone"),
        ("issued_at_utc", "timestamp with time zone"),
    )
    assert dict(apply_0011.NEW_CONSTRAINTS) == {
        "predictions_target_version_chk": (("target_version",), frozenset({"tc-v1"})),
        "predictions_reference_venue_chk": (
            ("reference_venue",),
            frozenset({"BINANCE_PUBLIC", "OKX_PUBLIC"}),
        ),
        "predictions_target_stamp_chk": (
            ("core_computed_at_utc", "issued_at_utc", "reference_venue", "target_version"),
            frozenset(),
        ),
    }
    assert list(apply_0011.OTHER_TABLES) == sorted(apply_0011.OTHER_TABLES)
    assert "predictions" not in apply_0011.OTHER_TABLES and len(apply_0011.OTHER_TABLES) == 13


@pytest.mark.parametrize(
    ("definition", "literals"),
    [
        ("CHECK (((target_version IS NULL) OR (target_version = 'tc-v1'::text)))", {"tc-v1"}),
        (
            "CHECK ((reference_venue = ANY (ARRAY['BINANCE_PUBLIC'::text, 'OKX_PUBLIC'::text])))",
            {"BINANCE_PUBLIC", "OKX_PUBLIC"},
        ),
        ("CHECK ((core_computed_at_utc <= issued_at_utc))", set()),
        ("CHECK ((note <> 'it''s'::text))", {"it's"}),
        ("CHECK ((note <> ''::text))", {""}),
    ],
)
def test_constraint_literals_are_read_as_a_set_from_the_deparse(
    definition: str, literals: set[str]
) -> None:
    assert apply_0011.constraint_literals(definition) == literals


FORBIDDEN_WORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|TRUNCATE|ALTER|CREATE|DROP|GRANT|REVOKE|COPY|CALL|DO|VACUUM|"
    r"ANALYZE|LOCK|NOTIFY|LISTEN|REFRESH|CLUSTER|REINDEX|COMMENT|SECURITY|EXECUTE|PREPARE|"
    r"MERGE|RESET|DISCARD|IMPORT)\b"
)


def _without_literals(statement: str) -> str:
    return re.sub(r"'[^']*'", "''", statement)


CHECKS = [
    *(statement for statement in dict.fromkeys(EXPECTED_ORDER) if statement is not MIGRATION_SQL),
    apply_0011.predictions_security_sql(REHEARSAL_SERVER),
    apply_0011.other_security_sql(REHEARSAL_SERVER),
]


def test_every_check_is_a_read_only_catalog_query_without_parameters() -> None:
    assert len(CHECKS) == 5 + 6 + 2
    for statement in CHECKS:
        bare = _without_literals(statement)
        assert bare.startswith(("SELECT ", "SET LOCAL ")), statement
        assert not FORBIDDEN_WORDS.search(bare), statement
        assert ";" not in bare and "%" not in bare
        for target in re.findall(r"\b(?:FROM|JOIN)\s+(?:LATERAL\s+)?(\S+)", bare):
            assert target.startswith(("pg_catalog.", "(")), (statement, target)


def test_no_check_reads_an_application_row() -> None:
    for statement in CHECKS:
        bare = _without_literals(statement)
        assert "public." not in bare, "a relation is only ever named inside a literal"
        for table in (apply_0011.TABLE, *apply_0011.OTHER_TABLES):
            assert not re.search(rf"\b(?:FROM|JOIN)\s+(?:public\.)?{table}\b", bare), statement


def test_the_checks_cover_predictions_every_other_table_role_and_privilege() -> None:
    assert "FROM (VALUES ('predictions')) AS t(name)" in PREDICTIONS_SQL
    for table in apply_0011.OTHER_TABLES:
        assert f"('{table}')" in OTHER_SQL
    assert "('predictions')" not in OTHER_SQL
    for role in apply_0011.API_ROLES:
        assert f"has_table_privilege('{role}', c.oid, v.privilege)" in PREDICTIONS_SQL
    for privilege in ALL:
        assert f"('{privilege}')" in PREDICTIONS_SQL
    assert f"k.relkind = ANY ({audit._RELKINDS_SQL})" in PREDICTIONS_SQL
    assert "a.grantee = 0" in PREDICTIONS_SQL and "att.attacl" in PREDICTIONS_SQL
    relation = "pg_catalog.to_regclass('public.predictions')"
    for query in (COLUMNS_SQL, CONSTRAINTS_SQL, INDEXES_SQL, TRIGGERS_SQL):
        assert relation in query, query
    assert "a.attnum > 0 AND NOT a.attisdropped" in COLUMNS_SQL
    assert COLUMNS_SQL.endswith(" ORDER BY a.attnum"), "columns in their physical order"
    for fragment in (
        "pg_catalog.format_type(a.atttypid, a.atttypmod)",
        "a.attnotnull",
        "a.atthasdef",
        "a.attidentity <> ''",
        "a.attgenerated <> ''",
        "a.attacl IS NOT NULL",
    ):
        assert fragment in COLUMNS_SQL, fragment
    assert "pg_catalog.pg_get_constraintdef(c.oid)" in CONSTRAINTS_SQL
    assert "a.attnum = ANY (c.conkey)" in CONSTRAINTS_SQL
    assert CONSTRAINTS_SQL.endswith(' ORDER BY c.conname::text COLLATE "C"')
    assert "pg_catalog.pg_get_indexdef(x.indexrelid)" in INDEXES_SQL
    assert "NOT t.tgisinternal" in TRIGGERS_SQL and "t.tgenabled::text" in TRIGGERS_SQL
    assert len(apply_0011.SECURITY_FIELDS) == 12
    assert COLUMN_FIELDS == (
        "column", "type", "not_null", "has_default", "identity", "generated", "column_acl"
    )
    assert CONSTRAINT_FIELDS == ("constraint", "type", "validated", "definition", "columns")
    assert apply_0011.INDEX_FIELDS == ("index", "definition")
    assert apply_0011.TRIGGER_FIELDS == ("trigger", "enabled")


# --------------------------------------------------------------------------- the one transaction


def test_a_first_apply_runs_every_check_in_one_committed_transaction() -> None:
    database = FakeDatabase(healthy_results())
    outcome, captured = _apply(database)

    assert database.executed() == EXPECTED_ORDER
    assert all(params is None for _, params in database.statements)
    assert database.commits == 1 and database.rollbacks == 0
    assert outcome["outcome"] == "APPLIED" and outcome["committed"] is True
    assert outcome["executed_migration_sha256"] == apply_0011.MIGRATION_SHA256
    assert [row["column"] for row in outcome["post_columns"][-4:]] == NEW_COLUMN_NAMES
    assert len(outcome["post_columns"]) == len(outcome["pre_columns"]) + 4
    assert {row["constraint"] for row in outcome["post_constraints"]} == {
        *(row[0] for row in EXISTING_CONSTRAINTS),
        *apply_0011.NEW_CONSTRAINTS,
    }
    for name in CHECK_NAMES:
        assert outcome[f"pre_{name}"] == captured[f"pre_{name}"], name
        assert outcome[f"post_{name}"] == captured[f"post_{name}"], name
    for name in ("predictions", "indexes", "triggers", "other"):
        assert captured[f"post_{name}"] == captured[f"pre_{name}"], name
    assert captured["commit_attempted"] is True and captured["committed"] is True


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
    for query in (
        apply_0011.predictions_security_sql(version),
        apply_0011.other_security_sql(version),
    ):
        assert database.executed().count(query) == 2, "read before and after"
        assert ("('MAINTAIN')" in query) is has_maintain


@pytest.mark.parametrize(
    "reported",
    [[(140012,)], [(None,)], [("170006",)], [(True,)], [(170006.0,)], [], [(170006, 1)]],
    ids=["postgres-14", "null", "text", "boolean", "float", "no-row", "two-values"],
)
def test_an_unsupported_or_unreadable_server_version_refuses_before_any_read(
    reported: list[tuple],
) -> None:
    database = FakeDatabase(healthy_results(**{apply_0011.SERVER_VERSION_SQL: reported}))
    with pytest.raises(ProvenanceRefused, match="nothing is applied"):
        _apply(database)
    assert database.executed()[-1] == apply_0011.SERVER_VERSION_SQL
    assert database.commits == 0 and database.rollbacks == 1


def test_the_migration_statement_is_exactly_the_file() -> None:
    database = FakeDatabase(healthy_results())
    _apply(database)
    (executed,) = [s for s in database.executed() if s.startswith("-- Target contract v1")]
    assert executed.encode("utf-8") == MIGRATION_BYTES


# Predictions absent: the security check's LEFT JOIN finds no relation to describe.
ABSENT = security_row(
    "predictions",
    relations_named_so=0,
    relkind=None,
    owned_by_applying_role=None,
    row_level_security=None,
    row_level_security_forced=None,
    service_role=[],
)
PRE_CHECK_DIFFERENCES: dict[str, dict[str, list[tuple]]] = {
    "predictions-absent": {
        PREDICTIONS_SQL: [ABSENT],
        COLUMNS_SQL: [],
        CONSTRAINTS_SQL: [],
        INDEXES_SQL: [],
        TRIGGERS_SQL: [],
    },
    "predictions-named-twice": {
        PREDICTIONS_SQL: [security_row("predictions", relations_named_so=2)]
    },
    "predictions-a-view": {PREDICTIONS_SQL: [security_row("predictions", relkind="v")]},
    "predictions-partitioned": {PREDICTIONS_SQL: [security_row("predictions", relkind="p")]},
    "predictions-not-owned": {
        PREDICTIONS_SQL: [security_row("predictions", owned_by_applying_role=False)]
    },
    "predictions-read-empty": {PREDICTIONS_SQL: []},
    "predictions-read-twice": {
        PREDICTIONS_SQL: [security_row("predictions"), security_row("predictions")]
    },
    "other-table-missing": {OTHER_SQL: other_rows()[:-1]},
    "other-table-extra": {OTHER_SQL: [*other_rows(), security_row("zz_unexpected")]},
    "other-tables-in-another-order": {OTHER_SQL: list(reversed(other_rows()))},
    "predictions-among-the-other-tables": {
        OTHER_SQL: by_name([*other_rows(), security_row("predictions")])
    },
}


@pytest.mark.parametrize("difference", sorted(PRE_CHECK_DIFFERENCES))
def test_a_database_not_ready_for_a_first_apply_refuses_before_the_migration(
    difference: str,
) -> None:
    database = FakeDatabase(healthy_results(**PRE_CHECK_DIFFERENCES[difference]))
    captured: dict[str, Any] = {}
    with pytest.raises(ProvenanceRefused, match="not in the state a first apply of 0011 requires"):
        apply_0011.apply_in_one_transaction(
            lambda: database.connect(DATABASE_URL), MIGRATION_SQL, captured
        )
    assert MIGRATION_SQL not in database.executed()
    assert database.executed()[-1] == OTHER_SQL, "every pre-read is taken before the verdict"
    assert all(f"pre_{name}" in captured for name in CHECK_NAMES), "what was seen is reported"
    assert database.commits == 0 and database.rollbacks == 1


FIRST_APPLY_DIFFERENCES: dict[str, dict[str, list[tuple]]] = {
    **{
        f"column-{name}": {COLUMNS_SQL: [*EXISTING_COLUMNS, column_row(name, type_name)]}
        for name, type_name in apply_0011.NEW_COLUMNS
    },
    **{
        f"constraint-{name}": {
            CONSTRAINTS_SQL: by_name([*EXISTING_CONSTRAINTS, NEW_CONSTRAINT_ROWS[name]])
        }
        for name in apply_0011.NEW_CONSTRAINTS
    },
}


@pytest.mark.parametrize("difference", sorted(FIRST_APPLY_DIFFERENCES))
def test_any_new_column_or_constraint_already_present_is_not_a_first_apply(
    difference: str,
) -> None:
    database = FakeDatabase(healthy_results(**FIRST_APPLY_DIFFERENCES[difference]))
    with pytest.raises(ProvenanceRefused, match=apply_0011.NOT_A_FIRST_APPLY) as refused:
        _apply(database)
    assert difference.split("-", 1)[1] in str(refused.value), "the one present is named"
    assert MIGRATION_SQL not in database.executed()
    assert database.commits == 0 and database.rollbacks == 1


def test_a_second_apply_refuses_naming_every_failure_not_only_the_first() -> None:
    database = FakeDatabase(
        healthy_results(
            **{
                PREDICTIONS_SQL: [security_row("predictions", owned_by_applying_role=False)],
                COLUMNS_SQL: APPLIED_COLUMNS,
                CONSTRAINTS_SQL: APPLIED_CONSTRAINTS,
                OTHER_SQL: other_rows()[1:],
            }
        )
    )
    with pytest.raises(ProvenanceRefused) as refused:
        _apply(database)
    message = str(refused.value)
    assert message.count(apply_0011.NOT_A_FIRST_APPLY) == 4 + 3
    for name in (*NEW_COLUMN_NAMES, *apply_0011.NEW_CONSTRAINTS):
        assert name in message, name
    assert "not owned by the applying role" in message
    assert "the other tables read were" in message
    assert MIGRATION_SQL not in database.executed()


def test_the_rest_of_predictions_and_the_other_tables_are_recorded_not_required() -> None:
    """0011 only has to leave them as they are, whatever that is."""

    unusual_predictions = security_row(
        "predictions",
        row_level_security=False,
        policies=2,
        public_has_a_privilege=True,
        column_grant_to_public_anon_or_authenticated=True,
        anon=list(ALL),
        authenticated=["SELECT"],
        service_role=[],
    )
    unusual_other = [
        security_row("analysis_run_details", relations_named_so=0, relkind=None,
                     owned_by_applying_role=None, service_role=[]),
        security_row("analysis_runs", relkind="v", owned_by_applying_role=False),
        *other_rows()[2:],
    ]
    database = FakeDatabase(
        healthy_results(
            **{
                PREDICTIONS_SQL: [unusual_predictions],
                OTHER_SQL: unusual_other,
                INDEXES_SQL: [],
                TRIGGERS_SQL: [],
            }
        )
    )
    outcome, captured = _apply(database)
    assert outcome["outcome"] == "APPLIED" and database.commits == 1
    assert captured["pre_predictions"] == captured["post_predictions"]
    assert captured["pre_predictions"][0]["anon"] == ALL
    assert captured["pre_other"] == captured["post_other"]
    assert captured["pre_other"][0]["relations_named_so"] == 0


def test_missing_api_roles_refuse_before_anything_is_read() -> None:
    database = FakeDatabase(healthy_results(**{apply_0011.ROLES_SQL: [(2,)]}))
    with pytest.raises(ProvenanceRefused, match="Supabase API roles"):
        _apply(database)
    assert database.executed()[-1] == apply_0011.ROLES_SQL
    assert database.commits == 0 and database.rollbacks == 1


def _columns_with(name: str, **changes: Any) -> list[tuple]:
    """The applied columns with only ``name`` changed."""

    rows = []
    for row in APPLIED_COLUMNS:
        values = dict(zip(COLUMN_FIELDS, row, strict=True))
        if values["column"] == name:
            values.update(changes)
        rows.append(tuple(values[field] for field in COLUMN_FIELDS))
    return rows


def _constraints_with(name: str, **changes: Any) -> list[tuple]:
    """The applied constraints with only ``name`` changed."""

    rows = []
    for row in APPLIED_CONSTRAINTS:
        values = dict(zip(CONSTRAINT_FIELDS, row, strict=True))
        if values["constraint"] == name:
            values.update(changes)
        rows.append(tuple(values[field] for field in CONSTRAINT_FIELDS))
    return rows


WRONG_TYPE = {TEXT: "character varying", TIMESTAMPTZ: "timestamp without time zone"}


def _column_defects(name: str, type_name: str) -> dict[str, list[tuple]]:
    return {
        "missing": [row for row in APPLIED_COLUMNS if row[0] != name],
        "wrong-type": _columns_with(name, type=WRONG_TYPE[type_name]),
        "not-null": _columns_with(name, not_null=True),
        "with-a-default": _columns_with(name, has_default=True),
        "identity": _columns_with(name, identity=True),
        "generated": _columns_with(name, generated=True),
        "with-an-acl": _columns_with(name, column_acl=True),
    }


_STAMP = "predictions_target_stamp_chk"
WRONG_COLUMNS = {
    "predictions_target_version_chk": ["reference_venue", "target_version"],
    "predictions_reference_venue_chk": [],
    _STAMP: ["issued_at_utc", "reference_venue", "target_version"],
}
EXTRA_LITERAL = {
    "predictions_target_version_chk": "CHECK (((target_version IS NULL) OR (target_version = "
    "ANY (ARRAY['tc-v1'::text, 'tc-v2'::text]))))",
    "predictions_reference_venue_chk": "CHECK (((reference_venue IS NULL) OR (reference_venue = "
    "ANY (ARRAY['BINANCE_PUBLIC'::text, 'OKX_PUBLIC'::text, 'CROSS_PROVIDER'::text]))))",
    _STAMP: NEW_CONSTRAINT_ROWS[_STAMP][3].replace(
        "(target_version IS NOT NULL)", "(target_version <> ''::text)"
    ),
}
# The stamp constraint has no literal to lose.
MISSING_LITERAL = {
    "predictions_target_version_chk": "CHECK ((target_version IS NULL))",
    "predictions_reference_venue_chk": "CHECK (((reference_venue IS NULL) OR (reference_venue = "
    "'BINANCE_PUBLIC'::text)))",
}


def _constraint_defects(name: str) -> dict[str, list[tuple]]:
    defects = {
        "missing": [row for row in APPLIED_CONSTRAINTS if row[0] != name],
        "not-validated": _constraints_with(name, validated=False),
        "not-a-check": _constraints_with(name, type="u"),
        "wrong-columns": _constraints_with(name, columns=WRONG_COLUMNS[name]),
        "an-extra-literal": _constraints_with(name, definition=EXTRA_LITERAL[name]),
    }
    if name in MISSING_LITERAL:
        defects["a-missing-literal"] = _constraints_with(name, definition=MISSING_LITERAL[name])
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
_CHANGED_OTHER = list(other_rows())
_CHANGED_OTHER[0] = security_row(
    "analysis_run_details", anon=["SELECT"], service_role=["INSERT", "SELECT", "UPDATE"]
)
POST_CHECK_DIFFERENCES: dict[str, tuple[str, list[tuple]]] = {
    **{
        f"column-{name}-{defect}": (COLUMNS_SQL, rows)
        for name, type_name in apply_0011.NEW_COLUMNS
        for defect, rows in _column_defects(name, type_name).items()
    },
    "an-existing-column-changed": (COLUMNS_SQL, _columns_with("is_live_data", has_default=False)),
    "an-existing-column-gone": (
        COLUMNS_SQL,
        [row for row in APPLIED_COLUMNS if row[0] != "operator_id"],
    ),
    "an-extra-column": (COLUMNS_SQL, [*APPLIED_COLUMNS, column_row("unexpected", TEXT)]),
    "the-new-columns-reordered": (
        COLUMNS_SQL,
        [*EXISTING_COLUMNS, NEW_COLUMN_ROWS[1], NEW_COLUMN_ROWS[0], *NEW_COLUMN_ROWS[2:]],
    ),
    "the-existing-columns-reordered": (
        COLUMNS_SQL,
        [EXISTING_COLUMNS[1], EXISTING_COLUMNS[0], *EXISTING_COLUMNS[2:], *NEW_COLUMN_ROWS],
    ),
    "a-new-column-before-an-existing-one": (
        COLUMNS_SQL,
        [*EXISTING_COLUMNS[:-1], NEW_COLUMN_ROWS[0], EXISTING_COLUMNS[-1], *NEW_COLUMN_ROWS[1:]],
    ),
    **{
        f"constraint-{name}-{defect}": (CONSTRAINTS_SQL, rows)
        for name in apply_0011.NEW_CONSTRAINTS
        for defect, rows in _constraint_defects(name).items()
    },
    "an-existing-constraint-changed": (
        CONSTRAINTS_SQL,
        _constraints_with(
            "predictions_prediction_origin_chk",
            definition="CHECK ((prediction_origin = 'USER_REQUESTED'::text))",
        ),
    ),
    "an-existing-constraint-no-longer-validated": (
        CONSTRAINTS_SQL,
        _constraints_with("predictions_prediction_origin_chk", validated=False),
    ),
    "an-existing-constraint-gone": (
        CONSTRAINTS_SQL,
        [row for row in APPLIED_CONSTRAINTS if row[0] != "predictions_pkey"],
    ),
    "an-extra-constraint": (
        CONSTRAINTS_SQL,
        by_name(
            [
                *APPLIED_CONSTRAINTS,
                constraint_row(
                    "predictions_unexpected_chk", "c", "CHECK ((horizon_bars > 0))",
                    ["horizon_bars"],
                ),
            ]
        ),
    ),
    "an-index-changed": (
        INDEXES_SQL,
        [
            (
                INDEXES[0][0],
                "CREATE INDEX idx_predictions_horizon_end ON public.predictions USING hash "
                "(horizon_end_utc)",
            ),
            *INDEXES[1:],
        ],
    ),
    "an-index-appeared": (
        INDEXES_SQL,
        [
            *INDEXES,
            (
                "zz_predictions_target_version",
                "CREATE INDEX zz_predictions_target_version ON public.predictions USING btree "
                "(target_version)",
            ),
        ],
    ),
    "an-index-gone": (INDEXES_SQL, INDEXES[1:]),
    "a-trigger-disabled": (TRIGGERS_SQL, [("synthetic_trigger", "D")]),
    "a-trigger-appeared": (TRIGGERS_SQL, [*TRIGGERS, ("unexpected_trigger", "O")]),
    "a-trigger-gone": (TRIGGERS_SQL, []),
    **{
        f"predictions-{field}-changed": (
            PREDICTIONS_SQL,
            [security_row("predictions", **{field: value})],
        )
        for field, value in SECURITY_CHANGES.items()
    },
    "another-table-s-security-changed": (OTHER_SQL, _CHANGED_OTHER),
    "another-table-gone": (OTHER_SQL, other_rows()[1:]),
}
PRE_ROWS: dict[str, list[tuple]] = {
    PREDICTIONS_SQL: [security_row("predictions")],
    COLUMNS_SQL: EXISTING_COLUMNS,
    CONSTRAINTS_SQL: EXISTING_CONSTRAINTS,
    INDEXES_SQL: INDEXES,
    TRIGGERS_SQL: TRIGGERS,
    OTHER_SQL: other_rows(),
}


def _post(query: str, rows: list[tuple]) -> dict[str, Any]:
    return healthy_results(**{query: Each([PRE_ROWS[query], rows])})


def test_the_post_check_differences_cover_every_defect_the_spec_names() -> None:
    assert set(SECURITY_CHANGES) == set(apply_0011.SECURITY_FIELDS[1:])
    for name in NEW_COLUMN_NAMES:
        assert {key for key in POST_CHECK_DIFFERENCES if key.startswith(f"column-{name}-")} == {
            f"column-{name}-{defect}"
            for defect in (
                "missing", "wrong-type", "not-null", "with-a-default", "identity", "generated",
                "with-an-acl",
            )
        }
    for name in apply_0011.NEW_CONSTRAINTS:
        defects = {key for key in POST_CHECK_DIFFERENCES if key.startswith(f"constraint-{name}-")}
        assert len(defects) == (5 if name == _STAMP else 6), name


@pytest.mark.parametrize("difference", sorted(POST_CHECK_DIFFERENCES))
def test_any_difference_from_the_reviewed_result_rolls_the_apply_back(difference: str) -> None:
    query, rows = POST_CHECK_DIFFERENCES[difference]
    database = FakeDatabase(_post(query, rows))
    captured: dict[str, Any] = {}
    with pytest.raises(ProvenanceRefused, match="nothing is applied") as refused:
        apply_0011.apply_in_one_transaction(
            lambda: database.connect(DATABASE_URL), MIGRATION_SQL, captured
        )
    assert "so the transaction is rolled back" in str(refused.value)
    assert MIGRATION_SQL in database.executed(), "the difference is seen only after applying"
    assert database.commits == 0 and database.rollbacks == 1
    assert "committed" not in captured and "commit_attempted" not in captured
    assert all(f"post_{name}" in captured for name in CHECK_NAMES), "what was seen is reported"


UNIQUE_STATEMENTS = list(dict.fromkeys(EXPECTED_ORDER))


@pytest.mark.parametrize("position", range(len(UNIQUE_STATEMENTS)))
def test_a_driver_error_at_any_statement_rolls_back(position: int) -> None:
    statement = UNIQUE_STATEMENTS[position]
    database = FakeDatabase(healthy_results(), fail_on={statement: RuntimeError("boom")})
    captured: dict[str, Any] = {}
    with pytest.raises(RuntimeError):
        apply_0011.apply_in_one_transaction(
            lambda: database.connect(DATABASE_URL), MIGRATION_SQL, captured
        )
    assert database.commits == 0 and database.rollbacks == 1
    assert "committed" not in captured


@pytest.mark.parametrize(
    ("query", "rows", "width"),
    [
        (COLUMNS_SQL, [("prediction_id", "text")], 7),
        (PREDICTIONS_SQL, [("predictions", 1)], 12),
        (CONSTRAINTS_SQL, [("predictions_pkey", "p", True, "PRIMARY KEY (prediction_id)")], 5),
        (TRIGGERS_SQL, [("synthetic_trigger",)], 2),
    ],
)
def test_a_malformed_check_row_refuses(query: str, rows: list[tuple], width: int) -> None:
    database = FakeDatabase(healthy_results(**{query: Each([rows])}))
    with pytest.raises(ProvenanceRefused, match=f"not a row of {width} values"):
        _apply(database)
    assert MIGRATION_SQL not in database.executed()
    assert database.rollbacks == 1 and database.commits == 0


def _pre_dicts() -> dict[str, list[dict[str, Any]]]:
    return {
        "predictions": _dicts(apply_0011.SECURITY_FIELDS, [security_row("predictions")]),
        "columns": _dicts(COLUMN_FIELDS, EXISTING_COLUMNS),
        "constraints": _dicts(CONSTRAINT_FIELDS, EXISTING_CONSTRAINTS),
        "indexes": _dicts(apply_0011.INDEX_FIELDS, INDEXES),
        "triggers": _dicts(apply_0011.TRIGGER_FIELDS, TRIGGERS),
        "other": _dicts(apply_0011.SECURITY_FIELDS, other_rows()),
    }


def test_the_judges_name_every_difference_not_only_the_first() -> None:
    pre = _pre_dicts()
    post = {
        **pre,
        "columns": _dicts(COLUMN_FIELDS, APPLIED_COLUMNS),
        "constraints": _dicts(CONSTRAINT_FIELDS, APPLIED_CONSTRAINTS),
    }
    assert apply_0011.pre_check_failures(pre) == []
    assert apply_0011.post_check_failures(pre, post) == []

    absent = {**dict.fromkeys(apply_0011.SECURITY_FIELDS), "table": "predictions"}
    second = {**post, "predictions": [absent]}
    assert len(apply_0011.pre_check_failures(second)) == 3 + 4 + 3

    every_flag = dict.fromkeys(apply_0011.NEW_COLUMN_FLAGS, True)
    wrong_columns = [
        *pre["columns"],
        *({"column": name, "type": "bytea", **every_flag} for name in NEW_COLUMN_NAMES),
    ]
    assert len(apply_0011.column_post_check_failures(pre["columns"], wrong_columns)) == 4 * 6
    wrong_constraints = [
        *pre["constraints"],
        *(
            {
                "constraint": name,
                "type": "u",
                "validated": False,
                "definition": "CHECK (('x'::text <> ''::text))",
                "columns": [],
            }
            for name in apply_0011.NEW_CONSTRAINTS
        ),
    ]
    assert (
        len(apply_0011.constraint_post_check_failures(pre["constraints"], wrong_constraints))
        == 3 * 4
    )

    changed = {
        "predictions": [{**pre["predictions"][0], "anon": ["SELECT"], "policies": 1}],
        "columns": post["columns"],
        "constraints": post["constraints"],
        "indexes": pre["indexes"][1:],
        "triggers": [{"trigger": "synthetic_trigger", "enabled": "D"}],
        "other": [{**pre["other"][0], "service_role": []}, *pre["other"][1:]],
    }
    failures = apply_0011.post_check_failures(pre, changed)
    assert len(failures) == 4, failures
    assert "anon [] -> ['SELECT']" in failures[0] and "policies 0 -> 1" in failures[0]
    assert "idx_predictions_horizon_end" in failures[1]
    assert "enabled 'O' -> 'D'" in failures[2]
    assert "analysis_run_details" in failures[3]


# --------------------------------------------------------------------------- the dispatch


def _dispatch(**changes: str) -> dict[str, str]:
    values = {
        "github_actions": "true",
        "event_name": "workflow_dispatch",
        "repository": REPOSITORY,
        "workflow_ref": f"{REPOSITORY}/{apply_0011.WORKFLOW}@refs/heads/main",
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
    record = apply_0011.verify_dispatch(_dispatch(), _runtime(), expected_sha=SHA)
    assert record["dispatch_verified"] is True
    assert record["schema_version"] == apply_0011.DISPATCH_SCHEMA
    assert record["workflow"] == apply_0011.WORKFLOW
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
    "the-evaluation-workflow": (
        _dispatch(
            workflow_ref=f"{REPOSITORY}/.github/workflows/section-5a-evaluation.yml@refs/heads/main"
        ),
        _runtime(),
        SHA,
    ),
    "workflow-from-a-branch": (
        _dispatch(workflow_ref=f"{REPOSITORY}/{apply_0011.WORKFLOW}@refs/heads/feature"),
        _runtime(),
        SHA,
    ),
    "self-consistent-fork": (
        _dispatch(
            repository="attacker/fork",
            workflow_ref=f"attacker/fork/{apply_0011.WORKFLOW}@refs/heads/main",
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
        apply_0011.verify_dispatch(dispatch, runtime, expected_sha=expected)


def test_different_migration_bytes_refuse_before_any_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(apply_0011, "MIGRATION_SHA256", "0" * 64)
    with pytest.raises(ProvenanceRefused, match="not the reviewed"):
        apply_0011.migration_bytes()


def test_the_reviewed_bytes_are_read_from_this_commit() -> None:
    assert apply_0011.migration_bytes() == MIGRATION_BYTES


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
        return {"dispatch_verified": True, "workflow": apply_0011.WORKFLOW}

    monkeypatch.setattr(apply_0011, "enter_isolated_runtime", _enter)
    monkeypatch.setattr(apply_0011, "attest_dispatch", _attest)
    monkeypatch.setattr(
        apply_0011, "attest_loaded_modules", lambda isolation: events.append("modules")
    )
    return events


def _argv(mode: str, tmp_path: Path, **overrides: str) -> list[str]:
    options = {
        "mode": mode,
        "expected-sha": SHA,
        "confirm": apply_0011.CONFIRMATION,
        "wheelhouse": "/synthetic/runner-temp/section-5a-wheels",
        "report": str(tmp_path / "report.json"),
        **overrides,
    }
    return [f"--{name}={value}" for name, value in options.items() if value is not None]


def _install_driver(monkeypatch: pytest.MonkeyPatch, database: FakeDatabase, events: list[str]):
    def _load():
        events.append("driver")
        return database

    monkeypatch.setattr(apply_0011, "load_driver", _load)


def test_apply_refuses_without_the_exact_token_before_anything_is_entered(
    calls: list[str], tmp_path: Path
) -> None:
    for token in (
        "",
        "apply",
        apply_0011.CONFIRMATION.lower(),
        apply_0011.CONFIRMATION + " ",
        "APPLY-MIGRATION-0010-ONCE",
    ):
        assert apply_0011.main(_argv("apply", tmp_path, confirm=token), environ={}) == 2
    assert calls == []
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["outcome"] == "REFUSED" and report["committed"] is False
    assert apply_0011.CONFIRMATION in report["detail"]
    assert report["detail"].startswith("migration 0011 refused; nothing is applied: ")


def test_attest_mode_touches_no_database(
    calls: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(healthy_results())
    _install_driver(monkeypatch, database, calls)
    code = apply_0011.main(
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
    assert report["migration_sha256"] == apply_0011.MIGRATION_SHA256
    assert report["schema_version"] == apply_0011.REPORT_SCHEMA


def test_apply_without_a_database_url_refuses_before_the_driver_loads(
    calls: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(healthy_results())
    _install_driver(monkeypatch, database, calls)
    assert apply_0011.main(_argv("apply", tmp_path), environ={}) == 2
    assert "driver" not in calls and database.connects == []


def test_a_full_apply_reports_raw_results_without_the_url(
    calls: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = FakeDatabase(healthy_results())
    _install_driver(monkeypatch, database, calls)
    code = apply_0011.main(_argv("apply", tmp_path), environ={"SUPABASE_DB_URL": DATABASE_URL})
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
    assert report["post_columns"][-1]["column"] == "issued_at_utc"
    assert report["post_constraints"] == _dicts(CONSTRAINT_FIELDS, APPLIED_CONSTRAINTS)
    for name in CHECK_NAMES:
        assert f"pre_{name}" in report and f"post_{name}" in report, name
    streams = capsys.readouterr()
    for text in (report_text, streams.out, streams.err):
        assert "NEVER-SHOWN-SECRET" not in text and "never-contacted" not in text


def test_a_refused_apply_reports_what_it_saw_and_commits_nothing(
    calls: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(healthy_results(**PRE_CHECK_DIFFERENCES["predictions-not-owned"]))
    _install_driver(monkeypatch, database, calls)
    code = apply_0011.main(_argv("apply", tmp_path), environ={"SUPABASE_DB_URL": DATABASE_URL})
    assert code == 2
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["outcome"] == "REFUSED" and report["committed"] is False
    assert report["captured"]["pre_predictions"][0]["owned_by_applying_role"] is False
    assert report["captured"]["pre_columns"] == _dicts(COLUMN_FIELDS, EXISTING_COLUMNS)
    assert "executed_migration_sha256" not in report["captured"]
    assert database.commits == 0


def test_an_unexpected_failure_withholds_its_message_because_it_can_name_the_host(
    calls: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    error = RuntimeError(f"connection to server at {DATABASE_URL} failed")
    database = FakeDatabase(healthy_results(), fail_on={apply_0011.ROLES_SQL: error})
    _install_driver(monkeypatch, database, calls)
    code = apply_0011.main(_argv("apply", tmp_path), environ={"SUPABASE_DB_URL": DATABASE_URL})
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
    code = apply_0011.main(_argv("apply", tmp_path), environ={"SUPABASE_DB_URL": DATABASE_URL})
    assert code == 1
    report_text = (tmp_path / "report.json").read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert report["outcome"] == "FAILED" and report["error_type"] == "ConnectionError"
    assert report["committed"] == apply_0011.COMMIT_UNKNOWN == "UNKNOWN"
    assert report["captured"]["commit_attempted"] is True
    assert "committed" not in report["captured"]
    assert "post_columns" in report["captured"], "the post-checks had passed"
    assert "NEVER-SHOWN-SECRET" not in report_text and "never-contacted" not in report_text


@pytest.mark.parametrize(
    ("captured", "expected"),
    [
        ({}, False),
        ({"pre_columns": []}, False),
        ({"commit_attempted": True}, "UNKNOWN"),
        ({"commit_attempted": True, "committed": True}, True),
        ({"committed": "yes"}, False),
        ({"first_apply": {"commit_attempted": True, "committed": True}, "second_apply": {}}, True),
        ({"first_apply": {"commit_attempted": True}}, "UNKNOWN"),
        ({"first_apply": {"pre_columns": []}}, False),
    ],
)
def test_the_commit_state_is_never_claimed_without_a_returned_commit(
    captured: dict[str, Any], expected: object
) -> None:
    assert apply_0011._commit_state(captured) == expected


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
    apply_0011.attest_loaded_modules("isolation")
    assert seen["pinned"] == (*pinned_files(ROOT), apply_0011.SCRIPT)
    assert Path(seen["root"]).resolve() == ROOT


# --------------------------------------------------------------------------- the rehearsal mode


def _rehearsal_results() -> dict[str, Any]:
    """The scratch database: the first apply succeeds, the second finds nothing left to do."""

    return healthy_results(REHEARSAL_SERVER)


def test_a_rehearsal_applies_once_and_proves_a_second_apply_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(_rehearsal_results())
    _install_driver(monkeypatch, database, [])
    environ = {apply_0011.REHEARSAL_URL_VARIABLE: REHEARSAL_URL}
    code = apply_0011.main(_argv("rehearse", tmp_path, wheelhouse="", confirm=""), environ=environ)
    assert code == 0
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["outcome"] == "REHEARSED" and report["mode"] == "rehearse"
    assert report["first_apply"]["outcome"] == "APPLIED"
    assert report["first_apply"]["server_version_num"] == REHEARSAL_SERVER
    assert report["first_apply"]["table_privileges_asked"] == REHEARSAL_ALL
    assert apply_0011.NOT_A_FIRST_APPLY in report["second_apply_refusal"]
    assert report["second_apply_captured"]["pre_columns"][-1]["column"] == "issued_at_utc"
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
    results[COLUMNS_SQL] = Each([EXISTING_COLUMNS, APPLIED_COLUMNS] * 2)
    results[CONSTRAINTS_SQL] = Each([EXISTING_CONSTRAINTS, APPLIED_CONSTRAINTS] * 2)
    database = FakeDatabase(results)
    _install_driver(monkeypatch, database, [])
    environ = {apply_0011.REHEARSAL_URL_VARIABLE: REHEARSAL_URL}
    code = apply_0011.main(_argv("rehearse", tmp_path, wheelhouse="", confirm=""), environ=environ)
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
    environ = {apply_0011.REHEARSAL_URL_VARIABLE: REHEARSAL_URL}
    code = apply_0011.main(_argv("rehearse", tmp_path, wheelhouse="", confirm=""), environ=environ)
    assert code == 1
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["outcome"] == "FAILED" and report["committed"] == "UNKNOWN"
    assert report["captured"]["first_apply"]["commit_attempted"] is True


def test_a_rehearsal_whose_second_apply_fails_otherwise_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    results = _rehearsal_results()
    results[apply_0011.ROLES_SQL] = Each([[(3,)], [(2,)]])
    database = FakeDatabase(results)
    _install_driver(monkeypatch, database, [])
    environ = {apply_0011.REHEARSAL_URL_VARIABLE: REHEARSAL_URL}
    code = apply_0011.main(_argv("rehearse", tmp_path, wheelhouse="", confirm=""), environ=environ)
    assert code == 2
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert "Supabase API roles" in report["detail"]
    assert report["committed"] is True, "the first scratch apply committed"


@pytest.mark.parametrize(
    "url",
    [
        "",
        DATABASE_URL,
        "postgresql://localhost/migration_0011_rehearsal",
        "postgresql://user@/migration_0011_rehearsal?host=/var/run/postgresql",
        "postgresql:///migration_0011_rehearsal?host=/tmp",
        "postgresql:///migration_0011_rehearsal?host=/var/run/postgresql&sslmode=disable",
        "postgresql:///migration_0011_rehearsal?host=/var/run/postgresql\n",
        "POSTGRESQL:///migration_0011_rehearsal?host=/var/run/postgresql",
        "postgres:///migration_0011_rehearsal?host=/var/run/postgresql",
        "postgresql:///Rehearsal?host=/var/run/postgresql",
    ],
)
def test_the_rehearsal_only_ever_reaches_a_local_socket(
    url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(_rehearsal_results())
    events: list[str] = []
    _install_driver(monkeypatch, database, events)
    code = apply_0011.main(
        _argv("rehearse", tmp_path, wheelhouse="", confirm=""),
        environ={apply_0011.REHEARSAL_URL_VARIABLE: url},
    )
    assert code == 2 and database.connects == [] and events == []


def test_the_rehearsal_never_runs_beside_the_production_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(_rehearsal_results())
    _install_driver(monkeypatch, database, [])
    environ = {apply_0011.REHEARSAL_URL_VARIABLE: REHEARSAL_URL, "SUPABASE_DB_URL": DATABASE_URL}
    code = apply_0011.main(_argv("rehearse", tmp_path, wheelhouse="", confirm=""), environ=environ)
    assert code == 2 and database.connects == []
    report_text = (tmp_path / "report.json").read_text(encoding="utf-8")
    assert "production database secret" in json.loads(report_text)["detail"]
    assert "NEVER-SHOWN-SECRET" not in report_text and "never-contacted" not in report_text


def test_the_rehearsal_is_isolated_when_given_the_wheelhouse(
    calls: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(_rehearsal_results())
    _install_driver(monkeypatch, database, calls)
    environ = {apply_0011.REHEARSAL_URL_VARIABLE: REHEARSAL_URL}
    code = apply_0011.main(_argv("rehearse", tmp_path, confirm=""), environ=environ)
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
        [sys.executable, "-B", apply_0011.SCRIPT, *_argv("apply", tmp_path, report=str(report))],
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
