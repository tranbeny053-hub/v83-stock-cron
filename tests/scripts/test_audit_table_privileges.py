"""The read-only older-table privilege audit. No database is contacted.

A psycopg-3-shaped fake records every statement. The rehearsal on a real scratch PostgreSQL runs in
CI (.github/workflows/audit-table-privileges-rehearsal.yml); here a synthetic catalog snapshot that
mirrors those fixtures proves the assessment offline.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from crypto_probability_engine.runtime_isolation import REQUIRED_FLAGS_TEXT, ProvenanceRefused
from scripts import audit_table_privileges as audit

ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = "postgresql://owner:NEVER-SHOWN-SECRET@db.never-contacted.invalid:5432/postgres"
REHEARSAL_URL = "postgresql:///audit_rehearsal?host=/var/run/postgresql"
SHA = "e" * 40
REPOSITORY = audit.EXPECTED_REPOSITORY
ALL_PRIVILEGES = audit.PRIVILEGES


# ------------------------------------------------------------------------ a psycopg-3-shaped fake


class FakeDatabase:
    def __init__(self, results: dict[str, list], fail_on: dict[str, Exception] | None = None):
        self.results = results
        self.fail_on = fail_on or {}
        self.statements: list[tuple[str, Any]] = []
        self.connects: list[tuple[str, dict[str, Any]]] = []
        self.commits = 0
        self.rollbacks = 0
        self.in_transaction = False

    def connect(self, url: str, **options: Any) -> FakeConnection:
        self.connects.append((url, options))
        return FakeConnection(self)

    def executed(self) -> list[str]:
        return [statement for statement, _ in self.statements]


class FakeConnection:
    def __init__(self, database: FakeDatabase):
        self.database = database

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.database)

    def commit(self) -> None:
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
        self.rows: list = []

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def execute(self, query: str, params: Any = None) -> None:
        self.database.statements.append((query, params))
        self.database.in_transaction = True
        if query in self.database.fail_on:
            raise self.database.fail_on[query]
        self.rows = list(self.database.results.get(query, []))

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list:
        return list(self.rows)


# ------------------------------------------------------------------------ the rehearsal, synthetic

RLS_TABLES = {
    "predictions", "prediction_outcomes", "news_items", "news_evidence_links",
    "provider_observations",
}
FORCED_TABLES = {"provider_observations"}
OWNED_BY_REHEARSAL_OWNER = {"news_evidence_links", "provider_observations"}
NON_STANDARD = "rehearsal reader"
# (policy, role) pairs the server says apply; every other pair does not.
APPLYING = {
    ("rehearsal_narrow", "anon"),
    ("rehearsal_read", "anon"),
    ("rehearsal_inherited_insert", "anon"),
}


def _anon_without_table_grants(name: str) -> bool:
    return name == "analysis_timeframe_results"


def rehearsal_snapshot() -> dict[str, list]:
    """What the catalog queries return on the rehearsal fixtures (scripts/audit_rehearsal/).

    Raw, as the server returns it: role names are not yet withheld.
    """

    tables = [
        [
            "public", name, "r",
            "rehearsal_owner" if name in OWNED_BY_REHEARSAL_OWNER else "postgres",
            name in RLS_TABLES, name in FORCED_TABLES, False,
        ]
        for name in audit.AUDITED_TABLES
    ]
    effective = []
    for name in audit.AUDITED_TABLES:
        for role in audit.API_ROLES:
            for privilege in ALL_PRIVILEGES:
                held = True
                if name == "watchlist":
                    held = False
                if _anon_without_table_grants(name) and role == "anon":
                    held = False
                effective.append(["public", name, role, privilege, held])
    grants = [
        ["public", name, role, privilege, False]
        for name in audit.AUDITED_TABLES
        for role in audit.API_ROLES
        for privilege in ALL_PRIVILEGES
        if name != "watchlist"
        and not (role == "anon" and (
            _anon_without_table_grants(name) or name in OWNED_BY_REHEARSAL_OWNER
        ))
    ] + [["public", "news_clusters", "PUBLIC", "SELECT", False]]
    policies = [
        [
            "public", "news_items", "rehearsal_narrow", "RESTRICTIVE",
            ["anon"], "SELECT", "true", None,
        ],
        [
            "public", "prediction_outcomes", "rehearsal_inherited_insert", "PERMISSIVE",
            [NON_STANDARD], "INSERT", None, "false",
        ],
        [
            "public", "prediction_outcomes", "rehearsal_read", "PERMISSIVE",
            ["anon"], "SELECT", "true", None,
        ],
        [
            "public", "predictions", "rehearsal_not_inherited", "PERMISSIVE",
            ["rehearsal_bystander"], "SELECT", "true", None,
        ],
    ]
    return {
        "roles": [
            ["anon", False, False, False, False],
            ["authenticated", False, False, False, False],
            ["service_role", False, True, False, False],
        ],
        "role_memberships": [
            ["anon", NON_STANDARD],
            ["anon", "rehearsal_bystander"],
            ["anon", "rehearsal_owner"],
        ],
        "role_inheritance": [["anon", NON_STANDARD], ["anon", "rehearsal_owner"]],
        "tables": tables,
        "owner_equivalence": [
            ["public", name, role, role == "anon" and name in OWNED_BY_REHEARSAL_OWNER]
            for name in audit.AUDITED_TABLES
            for role in audit.API_ROLES
        ],
        "table_grants": sorted(grants),
        "effective_privileges": effective,
        "column_grants": [
            ["public", "analysis_timeframe_results", "run_id", "anon", "SELECT"],
            ["public", "analysis_timeframe_results", "timeframe", "PUBLIC", "INSERT"],
        ],
        "column_privileges": [
            ["public", "analysis_timeframe_results", "timeframe", "anon", "INSERT"],
            ["public", "analysis_timeframe_results", "run_id", "anon", "SELECT"],
            ["public", "analysis_timeframe_results", "disposition", "anon", "UPDATE"],
        ],
        "policies": policies,
        "policy_applicability": [
            [row[0], row[1], row[2], role, (row[2], role) in APPLYING]
            for row in policies
            for role in audit.API_ROLES
        ],
        "schema_usage": [["public", "pg_database_owner", role, True] for role in audit.API_ROLES],
        "default_privileges": [
            ["postgres", "public", role, privilege]
            for role in audit.API_ROLES
            for privilege in ALL_PRIVILEGES
        ],
        "api_schemas_setting": [["*", "pgrst.db_schemas=public, graphql_public"]],
        "dependent_views": [
            ["public", "rehearsal_runs_view", "v", "postgres", "", "public", "analysis_runs"]
        ],
        "dependent_view_privileges": [
            ["public", "rehearsal_runs_view", role, privilege, True]
            for role in audit.API_ROLES
            for privilege in ("DELETE", "INSERT", "SELECT", "UPDATE")
        ],
        "realtime_publications": [["supabase_realtime", "public", "app_events"]],
    }


def observed_from(snapshot: dict[str, list], **overrides: Any) -> dict[str, Any]:
    """The snapshot as read_catalogs records it: role names withheld, nothing else changed."""

    observed: dict[str, Any] = {"query_errors": {}, "transaction_read_only": "on"}
    for name, rows in deepcopy(snapshot).items():
        observed[name] = audit._redact_role_names(name, rows)
    observed.update(overrides)
    return observed


def set_fact(snapshot: dict[str, list], name: str, key: tuple, value: Any) -> None:
    """Set the last column of the one row of `name` whose leading columns are `key`."""

    rows = [row for row in snapshot[name] if tuple(row[: len(key)]) == key]
    assert len(rows) == 1, (name, key)
    rows[0][-1] = value


def healthy_results(snapshot: dict[str, list] | None = None) -> dict[str, list]:
    snapshot = rehearsal_snapshot() if snapshot is None else snapshot
    results: dict[str, list] = {audit.READ_ONLY_SQL: [("on",)]}
    for name, query in audit.QUERIES.items():
        results[query] = [tuple(row) for row in snapshot[name]]
    return results


def expected_order() -> list[str]:
    order = [*audit.GUARD_STATEMENTS, audit.READ_ONLY_SQL]
    for name, query in audit.QUERIES.items():
        if name in audit.OPTIONAL_QUERIES:
            order += [f"SAVEPOINT audit_{name}", query, f"RELEASE SAVEPOINT audit_{name}"]
        else:
            order.append(query)
    return order


def _read(database: FakeDatabase) -> tuple[dict[str, Any], dict[str, Any]]:
    captured: dict[str, Any] = {}
    observed = audit.read_catalogs(lambda: database.connect(DATABASE_URL), captured)
    return observed, captured


# --------------------------------------------------------------------------- the contract


def test_the_script_imports_only_the_standard_library_at_module_level() -> None:
    tree = ast.parse((ROOT / audit.SCRIPT).read_text(encoding="utf-8"))
    imported = {
        (node.module if isinstance(node, ast.ImportFrom) else alias.name).split(".")[0]
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in (node.names if isinstance(node, ast.Import) else [None])
    }
    assert imported and all(
        name == "__future__" or name in sys.stdlib_module_names for name in imported
    ), imported


def test_it_names_itself_and_its_workflows() -> None:
    assert (ROOT / audit.SCRIPT).resolve() == Path(audit.__file__).resolve()
    assert (ROOT / audit.WORKFLOW).is_file()
    assert audit.CONFIRMATION == "READ-ONLY-AUDIT-OLDER-TABLES-ONCE"
    assert audit.EXPECTED_REPOSITORY == "tranbeny053-hub/v83-stock-cron"


def test_the_audited_tables_are_exactly_what_the_migrations_create() -> None:
    created: set[str] = set()
    altered: set[str] = set()
    for relative in audit.AUDIT_MIGRATIONS:
        text = (ROOT / relative).read_text(encoding="utf-8")
        created |= set(re.findall(r"CREATE TABLE IF NOT EXISTS (?:public\.)?([a-z_]+)", text))
        altered |= set(re.findall(r"ALTER TABLE (?:public\.)?([a-z_]+)", text))
    assert set(audit.AUDITED_TABLES) == created
    assert altered <= created, "0007 only alters a table 0001-0004 created"
    assert audit.AUDIT_MIGRATIONS == (
        "migrations/0001_init.sql",
        "migrations/0002_news.sql",
        "migrations/0003_prediction_ledger.sql",
        "migrations/0004_prediction_outcomes.sql",
        "migrations/0007_prediction_origin.sql",
    )


FORBIDDEN_WORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|TRUNCATE|ALTER|CREATE|DROP|GRANT|REVOKE|COPY|CALL|DO|VACUUM|"
    r"ANALYZE|LOCK|NOTIFY|LISTEN|REFRESH|CLUSTER|REINDEX|COMMENT|SECURITY|EXECUTE|PREPARE)\b"
)


def _statements() -> list[str]:
    statements = [*audit.GUARD_STATEMENTS, audit.READ_ONLY_SQL, *audit.QUERIES.values()]
    for name in audit.OPTIONAL_QUERIES:
        statements += [
            f"SAVEPOINT audit_{name}",
            f"RELEASE SAVEPOINT audit_{name}",
            f"ROLLBACK TO SAVEPOINT audit_{name}",
        ]
    return statements


def _without_literals(statement: str) -> str:
    return re.sub(r"'[^']*'", "''", statement)


def test_every_statement_is_read_only_and_starts_as_expected() -> None:
    for statement in _statements():
        bare = _without_literals(statement)
        assert bare.startswith(
            ("SELECT ", "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY",
             "SET LOCAL ", "SAVEPOINT audit_",
             "RELEASE SAVEPOINT audit_", "ROLLBACK TO SAVEPOINT audit_")
        ), statement
        assert not FORBIDDEN_WORDS.search(bare.replace("privilege_type", "")), statement
        assert ";" not in bare, "one statement per execute"


def test_no_query_ever_reads_an_application_table() -> None:
    """Every FROM or JOIN target is a pg_catalog relation or function, VALUES, or a subquery."""

    for name, query in audit.QUERIES.items():
        targets = re.findall(r"\b(?:FROM|JOIN)\s+(?:LATERAL\s+)?(\S+)", _without_literals(query))
        assert targets, name
        for target in targets:
            assert target.startswith(("pg_catalog.", "(")), (name, target)
            assert not any(table == target.split(".")[-1] for table in audit.AUDITED_TABLES), target
    assert audit.READ_ONLY_SQL.startswith("SELECT pg_catalog.current_setting(")


def test_the_api_schema_setting_query_never_returns_other_settings() -> None:
    query = audit.QUERIES["api_schemas_setting"]
    assert "s.setting LIKE 'pgrst.db\\_schemas=%'" in query
    assert "rolname::text = 'authenticator'" in query


def test_every_role_and_privilege_is_checked() -> None:
    effective = audit.QUERIES["effective_privileges"]
    for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
        assert f"('{privilege}')" in effective
    for role in ("anon", "authenticated", "service_role"):
        assert f"'{role}'" in audit._ROLES_SQL
    assert "a.grantee = 0" in audit.QUERIES["table_grants"], "PUBLIC is grantee 0"
    assert "acldefault('r', c.relowner)" in audit.QUERIES["table_grants"]


def test_membership_ownership_policy_roles_and_columns_are_resolved_by_the_server() -> None:
    """No INHERIT, ownership or policy-role rule is re-implemented: the server decides."""

    assert audit.GUARD_STATEMENTS[0] == (
        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
    )
    inheritance = audit.QUERIES["role_inheritance"]
    assert "pg_catalog.pg_has_role(r.oid, o.oid, 'USAGE')" in inheritance
    assert "o.oid <> r.oid" in inheritance
    owner = audit.QUERIES["owner_equivalence"]
    assert "pg_catalog.pg_has_role(r.oid, c.relowner, 'USAGE')" in owner
    applicability = audit.QUERIES["policy_applicability"]
    assert "0::pg_catalog.oid = ANY (pol.polroles)" in applicability, "a PUBLIC policy"
    assert "pg_catalog.pg_has_role(r.oid, pr.roleid, 'USAGE')" in applicability
    assert "FROM pg_catalog.pg_policy AS pol" in applicability
    columns = audit.QUERIES["column_privileges"]
    assert "VALUES ('SELECT'), ('INSERT'), ('UPDATE')" in columns
    assert "pg_catalog.has_column_privilege(r.oid, c.oid, att.attnum, p.privilege)" in columns
    assert "NOT pg_catalog.has_table_privilege(r.oid, c.oid, p.privilege)" in columns
    assert "NOT att.attisdropped" in columns
    assert "p.roles::text[]" in audit.QUERIES["policies"], "policy roles arrive as a list"
    for name in ("role_inheritance", "owner_equivalence", "policy_applicability",
                 "column_privileges"):
        assert name not in audit.OPTIONAL_QUERIES, "a missing server fact is never optional"


# --------------------------------------------------------------------------- the transaction


def test_the_audit_reads_every_catalog_in_one_read_only_transaction_and_rolls_back() -> None:
    database = FakeDatabase(healthy_results())
    observed, captured = _read(database)

    assert database.executed() == expected_order()
    assert all(params is None for _, params in database.statements)
    assert database.commits == 0 and database.rollbacks == 1
    assert captured["rolled_back"] is True
    assert observed["transaction_read_only"] == "on"
    assert observed["query_errors"] == {}
    assert observed["tables"][0][:2] == ["public", "analysis_runs"]


@pytest.mark.parametrize("setting", ["off", None, ""])
def test_a_transaction_that_is_not_read_only_refuses_before_any_catalog_read(setting) -> None:
    results = healthy_results()
    results[audit.READ_ONLY_SQL] = [] if setting is None else [(setting,)]
    database = FakeDatabase(results)
    with pytest.raises(ProvenanceRefused, match="nothing was read"):
        _read(database)
    assert database.executed() == [*audit.GUARD_STATEMENTS, audit.READ_ONLY_SQL]
    assert database.commits == 0 and database.rollbacks == 1


@pytest.mark.parametrize("name", sorted(audit.OPTIONAL_QUERIES))
def test_a_refused_optional_catalog_read_is_recorded_and_the_audit_continues(name: str) -> None:
    query = audit.QUERIES[name]
    database = FakeDatabase(healthy_results(), fail_on={query: RuntimeError("permission denied")})
    observed, captured = _read(database)
    assert observed["query_errors"] == {name: "RuntimeError"}
    assert name not in observed
    assert f"ROLLBACK TO SAVEPOINT audit_{name}" in database.executed()
    assert f"RELEASE SAVEPOINT audit_{name}" not in database.executed()
    assert database.executed()[-1] == expected_order()[-1] or name == "realtime_publications"
    assert database.commits == 0 and database.rollbacks == 1
    audit.assess(observed)  # still assessable


@pytest.mark.parametrize(
    "name", sorted(set(audit.QUERIES) - set(audit.OPTIONAL_QUERIES))
)
def test_a_failed_required_catalog_read_rolls_back_and_raises(name: str) -> None:
    database = FakeDatabase(
        healthy_results(), fail_on={audit.QUERIES[name]: RuntimeError("boom")}
    )
    captured: dict[str, Any] = {}
    with pytest.raises(RuntimeError):
        audit.read_catalogs(lambda: database.connect(DATABASE_URL), captured)
    assert database.commits == 0 and database.rollbacks == 1
    assert "rolled_back" not in captured


def test_non_standard_role_names_are_withheld() -> None:
    snapshot = rehearsal_snapshot()
    snapshot["tables"][0][3] = "postgres.abcdefghijklmnop"
    snapshot["schema_usage"][0][1] = "Weird Owner"
    snapshot["role_memberships"] = [["anon", "role.with.dots"]]
    snapshot["role_inheritance"] = [["anon", "evil\n"], ["anon", "pg_read_all_data"]]
    snapshot["policies"][0][4] = ["public", "a,b", 'q"x', "anon\n", None, "authenticated"]
    snapshot["policies"][1][4] = '{"reader role"}'  # not a list: withheld whole
    database = FakeDatabase(healthy_results(snapshot))
    observed, _ = _read(database)
    withheld = audit.WITHHELD
    assert withheld == "<non-standard role name withheld>"
    assert observed["tables"][0][3] == withheld
    assert observed["schema_usage"][0][1] == withheld
    assert observed["role_memberships"] == [["anon", withheld]]
    assert observed["role_inheritance"] == [["anon", withheld], ["anon", "pg_read_all_data"]]
    assert observed["policies"][0][4] == [
        "public", withheld, withheld, withheld, withheld, "authenticated"
    ]
    assert observed["policies"][1][4] == withheld
    serialized = json.dumps(observed)
    for leaked in ("abcdefghijklmnop", "Weird", "dots", "evil", "a,b", 'q\\"x', "reader role",
                   NON_STANDARD):
        assert leaked not in serialized, leaked
    # The rehearsal's own non-standard role is withheld wherever the server returns it.
    rehearsal, _ = _read(FakeDatabase(healthy_results()))
    assert NON_STANDARD not in json.dumps(rehearsal)
    assert rehearsal["policies"][1][4] == [withheld]


# --------------------------------------------------------------------------- the assessment


def test_the_rehearsal_snapshot_satisfies_every_rehearsal_expectation() -> None:
    observed = observed_from(rehearsal_snapshot())
    assessment = audit.assess(observed)
    assert audit.rehearsal_failures(observed, assessment) == []
    assert assessment["verdict"] == "EXPOSED"
    assert assessment["api_schemas"] == ["graphql_public", "public"]
    assert assessment["public_grants"] == [["public", "news_clusters", "SELECT"]]
    assert any("SECURITY DEFINER" in item for item in assessment["not_audited"])
    assert assessment["facts_incomplete"] == []
    assert assessment["role_inheritance"] == {"anon": [audit.WITHHELD, "rehearsal_owner"]}
    prediction_outcomes = assessment["tables"]["public.prediction_outcomes"]["roles"]
    assert prediction_outcomes["authenticated"]["data_api"] == dict.fromkeys(
        audit.API_PRIVILEGES, "RLS_DENIES_ALL"
    )
    columns = assessment["tables"]["public.analysis_timeframe_results"]["roles"]["anon"]
    assert columns["privileges"] == []
    assert columns["column_only_privileges"] == {
        "SELECT": ["run_id"], "INSERT": ["timeframe"], "UPDATE": ["disposition"]
    }
    links = assessment["tables"]["public.news_evidence_links"]["roles"]
    assert links["anon"]["acts_as_table_owner"] and links["anon"]["bypasses_row_level_security"]
    assert links["authenticated"]["data_api"] == dict.fromkeys(
        audit.API_PRIVILEGES, "RLS_DENIES_ALL"
    )
    forced = assessment["tables"]["public.provider_observations"]
    assert forced["row_level_security_forced"] is True
    assert forced["roles"]["anon"]["acts_as_table_owner"] is True
    assert forced["roles"]["anon"]["bypasses_row_level_security"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        "predictions-without-rls",
        "restrictive-becomes-permissive",
        "watchlist-granted",
        "column-grant-gone",
        "public-column-grant-gone",
        "inherited-column-grant-gone",
        "inherited-policy-ignored",
        "non-inherited-policy-applies",
        "owner-bypass-ignored",
        "forced-rls-ignored",
        "owner-fact-missing",
        "policy-fact-unknown",
        "inheritance-differs",
        "membership-differs",
        "role-name-leaked",
        "policy-roles-not-a-list",
        "no-view",
        "no-publication",
        "no-public-grant",
        "anon-bypasses-rls",
        "query-error",
        "not-read-only",
        "table-missing",
        "table-duplicated",
    ],
)
def test_the_rehearsal_check_notices_every_departure(mutation: str) -> None:
    snapshot = rehearsal_snapshot()
    extra: dict[str, Any] = {}
    if mutation == "predictions-without-rls":
        for row in snapshot["tables"]:
            if row[1] == "predictions":
                row[4] = False
    elif mutation == "restrictive-becomes-permissive":
        snapshot["policies"][0][3] = "PERMISSIVE"
    elif mutation == "watchlist-granted":
        for row in snapshot["effective_privileges"]:
            if row[1] == "watchlist":
                row[4] = True
    elif mutation == "column-grant-gone":
        snapshot["column_privileges"] = [
            row for row in snapshot["column_privileges"] if row[4] != "SELECT"
        ]
    elif mutation == "public-column-grant-gone":
        snapshot["column_privileges"] = [
            row for row in snapshot["column_privileges"] if row[4] != "INSERT"
        ]
    elif mutation == "inherited-column-grant-gone":
        snapshot["column_privileges"] = [
            row for row in snapshot["column_privileges"] if row[4] != "UPDATE"
        ]
    elif mutation == "inherited-policy-ignored":
        key = ("public", "prediction_outcomes", "rehearsal_inherited_insert", "anon")
        set_fact(snapshot, "policy_applicability", key, False)
    elif mutation == "non-inherited-policy-applies":
        key = ("public", "predictions", "rehearsal_not_inherited", "anon")
        set_fact(snapshot, "policy_applicability", key, True)
    elif mutation == "owner-bypass-ignored":
        set_fact(snapshot, "owner_equivalence", ("public", "news_evidence_links", "anon"), False)
    elif mutation == "forced-rls-ignored":
        for row in snapshot["tables"]:
            if row[1] == "provider_observations":
                row[5] = False
    elif mutation == "owner-fact-missing":
        snapshot["owner_equivalence"] = [
            row for row in snapshot["owner_equivalence"]
            if row[:3] != ["public", "predictions", "anon"]
        ]
    elif mutation == "policy-fact-unknown":
        key = ("public", "predictions", "rehearsal_not_inherited", "authenticated")
        set_fact(snapshot, "policy_applicability", key, None)
    elif mutation == "inheritance-differs":
        snapshot["role_inheritance"].append(["anon", "rehearsal_bystander"])
    elif mutation == "membership-differs":
        snapshot["role_memberships"].pop()
    elif mutation == "role-name-leaked":
        extra["dependent_views"] = [
            ["public", "rehearsal_runs_view", "v", NON_STANDARD, "", "public", "analysis_runs"]
        ]
    elif mutation == "policy-roles-not-a-list":
        extra["policies"] = [
            [*row[:4], "{anon}", *row[5:]] for row in observed_from(snapshot)["policies"]
        ]
    elif mutation == "no-view":
        snapshot["dependent_view_privileges"] = []
    elif mutation == "no-publication":
        snapshot["realtime_publications"] = []
    elif mutation == "no-public-grant":
        snapshot["table_grants"] = [r for r in snapshot["table_grants"] if r[2] != "PUBLIC"]
    elif mutation == "anon-bypasses-rls":
        snapshot["roles"][0][2] = True
    elif mutation == "query-error":
        extra["query_errors"] = {"policies": "RuntimeError"}
    elif mutation == "not-read-only":
        extra["transaction_read_only"] = "off"
    elif mutation == "table-missing":
        snapshot["tables"] = snapshot["tables"][1:]
    elif mutation == "table-duplicated":
        snapshot["tables"].append(["extensions", "watchlist", "r", "postgres", False, False, False])
    observed = observed_from(snapshot, **extra)
    assert audit.rehearsal_failures(observed, audit.assess(observed)), mutation


def test_an_unreadable_schema_setting_falls_back_to_public_and_says_so() -> None:
    snapshot = rehearsal_snapshot()
    snapshot.pop("api_schemas_setting")
    errors = {"api_schemas_setting": "InsufficientPrivilege"}
    observed = observed_from(snapshot, query_errors=errors)
    assessment = audit.assess(observed)
    assert assessment["api_schemas"] == ["public"]
    assert assessment["api_schemas_source"].startswith("ASSUMED")
    assert audit.rehearsal_failures(observed, assessment) == []


def test_a_table_outside_the_served_schemas_or_without_usage_is_not_api_reachable() -> None:
    snapshot = rehearsal_snapshot()
    snapshot["api_schemas_setting"] = [["*", "pgrst.db_schemas=graphql_public"]]
    assessment = audit.assess(observed_from(snapshot))
    runs = assessment["tables"]["public.analysis_runs"]["roles"]["anon"]["data_api"]
    assert runs == dict.fromkeys(audit.API_PRIVILEGES, "OPEN_BUT_NOT_API_REACHABLE")
    assert assessment["verdict"] == "NOT_EXPOSED_THROUGH_TABLE_GRANTS"

    snapshot = rehearsal_snapshot()
    snapshot["schema_usage"] = [
        ["public", "pg_database_owner", role, role == "service_role"] for role in audit.API_ROLES
    ]
    assessment = audit.assess(observed_from(snapshot))
    runs = assessment["tables"]["public.analysis_runs"]["roles"]["anon"]["data_api"]
    assert runs == dict.fromkeys(audit.API_PRIVILEGES, "OPEN_BUT_NOT_API_REACHABLE")


def hardened_snapshot() -> dict[str, list]:
    """The shape 0005, 0006 and 0009 have: RLS on, no API grant but service_role's."""

    snapshot = rehearsal_snapshot()
    for row in snapshot["tables"]:
        row[4] = True
    for row in snapshot["effective_privileges"]:
        row[4] = row[2] == "service_role" and row[3] in ("SELECT", "INSERT")
    snapshot["table_grants"] = []
    snapshot["column_grants"] = []
    snapshot["column_privileges"] = []
    snapshot["policies"] = []
    snapshot["policy_applicability"] = []
    for row in snapshot["owner_equivalence"]:
        row[3] = False
    snapshot["dependent_views"] = []
    snapshot["dependent_view_privileges"] = []
    return snapshot


def test_a_fully_hardened_database_is_not_exposed() -> None:
    assessment = audit.assess(observed_from(hardened_snapshot()))
    assert assessment["anon_or_authenticated_exposures"] == []
    assert assessment["facts_incomplete"] == []
    assert assessment["verdict"] == "NOT_EXPOSED_THROUGH_TABLE_GRANTS"
    service = assessment["tables"]["public.predictions"]["roles"]["service_role"]
    assert service["data_api"] == {
        "SELECT": "OPEN", "INSERT": "OPEN", "UPDATE": "NO_PRIVILEGE", "DELETE": "NO_PRIVILEGE"
    }


def test_an_all_command_policy_for_public_decides_every_command() -> None:
    snapshot = rehearsal_snapshot()
    snapshot["policies"].append(
        ["public", "predictions", "open_all", "PERMISSIVE", ["public"], "ALL", "true", "true"]
    )
    snapshot["policy_applicability"] += [
        ["public", "predictions", "open_all", role, True] for role in audit.API_ROLES
    ]
    assessment = audit.assess(observed_from(snapshot))
    anon = assessment["tables"]["public.predictions"]["roles"]["anon"]["data_api"]
    assert anon == dict.fromkeys(audit.API_PRIVILEGES, "POLICY_DECIDES: open_all")
    assert any(line.startswith("public.predictions: anon DELETE POLICY_DECIDES") for line in
               assessment["anon_or_authenticated_exposures"])


def _anon(assessment: dict[str, Any], table: str) -> dict[str, Any]:
    return assessment["tables"][f"public.{table}"]["roles"]["anon"]


def test_a_policy_for_a_role_anon_inherits_decides_its_rows() -> None:
    """task-818 finding 1: the policy names a parent role; the server says it applies to anon."""

    snapshot = rehearsal_snapshot()
    snapshot["policies"] = [
        [
            "public", "predictions", "via_parent", "PERMISSIVE",
            ["reader role"], "SELECT", "true", None,
        ]
    ]
    snapshot["policy_applicability"] = [
        ["public", "predictions", "via_parent", role, role == "anon"] for role in audit.API_ROLES
    ]
    snapshot["role_memberships"] = [["anon", "reader role"]]
    snapshot["role_inheritance"] = [["anon", "reader role"]]
    snapshot["roles"][0][3] = True
    assessment = audit.assess(observed_from(snapshot))
    anon = _anon(assessment, "predictions")["data_api"]
    assert anon["SELECT"] == "POLICY_DECIDES: via_parent"
    assert anon["INSERT"] == anon["UPDATE"] == anon["DELETE"] == "RLS_DENIES_ALL"
    exposures = assessment["anon_or_authenticated_exposures"]
    assert "public.predictions: anon SELECT POLICY_DECIDES: via_parent" in exposures
    authenticated = assessment["tables"]["public.predictions"]["roles"]["authenticated"]
    assert authenticated["data_api"]["SELECT"] == "RLS_DENIES_ALL"
    assert assessment["role_inheritance"] == {"anon": [audit.WITHHELD]}
    assert "reader role" not in json.dumps(assessment)

    # The same membership without inheritance: the server says the policy does not apply.
    key = ("public", "predictions", "via_parent", "anon")
    set_fact(snapshot, "policy_applicability", key, False)
    assessment = audit.assess(observed_from(snapshot))
    assert _anon(assessment, "predictions")["data_api"]["SELECT"] == "RLS_DENIES_ALL"

    # An unknown answer is never taken as "does not apply".
    set_fact(snapshot, "policy_applicability", key, None)
    assessment = audit.assess(observed_from(snapshot))
    assert _anon(assessment, "predictions")["data_api"]["SELECT"] == "POLICY_DECIDES: via_parent"
    assert assessment["facts_incomplete"] == [
        "public.predictions: whether policy via_parent applies to anon"
    ]


def test_only_permissive_policies_the_server_applies_admit_rows() -> None:
    snapshot = rehearsal_snapshot()
    snapshot["policies"] = [
        ["public", "predictions", "allow_all", "PERMISSIVE", ["anon"], "ALL", "true", "true"],
        ["public", "predictions", "narrow", "RESTRICTIVE", ["anon"], "SELECT", "false", None],
        [
            "public", "predictions", "others", "PERMISSIVE",
            ["authenticated"], "SELECT", "true", None,
        ],
    ]
    applying = {"allow_all": {"anon"}, "narrow": {"anon"}, "others": {"authenticated"}}
    snapshot["policy_applicability"] = [
        ["public", "predictions", name, role, role in roles]
        for name, roles in applying.items()
        for role in audit.API_ROLES
    ]
    assessment = audit.assess(observed_from(snapshot))
    roles = assessment["tables"]["public.predictions"]["roles"]
    assert roles["anon"]["data_api"] == dict.fromkeys(
        audit.API_PRIVILEGES, "POLICY_DECIDES: allow_all"
    )
    assert roles["authenticated"]["data_api"] == {
        "SELECT": "POLICY_DECIDES: others",
        "INSERT": "RLS_DENIES_ALL",
        "UPDATE": "RLS_DENIES_ALL",
        "DELETE": "RLS_DENIES_ALL",
    }


def test_an_api_role_acting_as_the_owner_bypasses_unforced_row_level_security() -> None:
    """task-818 finding 2: ownership, direct or inherited, bypasses RLS unless it is forced."""

    snapshot = rehearsal_snapshot()
    predictions = next(row for row in snapshot["tables"] if row[1] == "predictions")
    predictions[3] = "anon"
    set_fact(snapshot, "owner_equivalence", ("public", "predictions", "anon"), True)
    assessment = audit.assess(observed_from(snapshot))
    anon = _anon(assessment, "predictions")
    assert anon["acts_as_table_owner"] and anon["bypasses_row_level_security"]
    assert anon["data_api"] == dict.fromkeys(audit.API_PRIVILEGES, "OPEN")
    assert "public.predictions: anon SELECT OPEN" in assessment["anon_or_authenticated_exposures"]
    authenticated = assessment["tables"]["public.predictions"]["roles"]["authenticated"]
    assert not authenticated["bypasses_row_level_security"]

    predictions[5] = True  # FORCE ROW LEVEL SECURITY
    assessment = audit.assess(observed_from(snapshot))
    anon = _anon(assessment, "predictions")
    assert anon["acts_as_table_owner"] and not anon["bypasses_row_level_security"]
    assert anon["data_api"] == dict.fromkeys(audit.API_PRIVILEGES, "RLS_DENIES_ALL")

    # An unknown ownership answer counts as ownership.
    predictions[5] = False
    set_fact(snapshot, "owner_equivalence", ("public", "predictions", "anon"), None)
    assessment = audit.assess(observed_from(snapshot))
    assert _anon(assessment, "predictions")["data_api"]["SELECT"] == "OPEN"
    assert assessment["facts_incomplete"] == [
        "public.predictions: whether anon acts as its owner"
    ]


def test_superuser_and_bypassrls_api_roles_bypass_row_level_security() -> None:
    snapshot = rehearsal_snapshot()
    snapshot["roles"][0][1] = True  # anon is a superuser
    snapshot["roles"][1][2] = True  # authenticated has BYPASSRLS
    assessment = audit.assess(observed_from(snapshot))
    for role in ("anon", "authenticated"):
        info = assessment["tables"]["public.predictions"]["roles"][role]
        assert info["bypasses_row_level_security"], role
        assert info["data_api"]["SELECT"] == "OPEN", role


def test_a_missing_api_role_holds_nothing_and_leaves_no_gap() -> None:
    snapshot = rehearsal_snapshot()
    for name, index in (
        ("roles", 0), ("role_memberships", 0), ("role_inheritance", 0),
        ("effective_privileges", 2), ("owner_equivalence", 2), ("policy_applicability", 3),
        ("column_privileges", 3), ("schema_usage", 2), ("dependent_view_privileges", 2),
    ):
        snapshot[name] = [row for row in snapshot[name] if row[index] != "anon"]
    assessment = audit.assess(observed_from(snapshot))
    assert assessment["facts_incomplete"] == []
    for entry in assessment["tables"].values():
        anon = entry["roles"]["anon"]
        assert anon["data_api"] == dict.fromkeys(audit.API_PRIVILEGES, "NO_PRIVILEGE")
        assert not anon["bypasses_row_level_security"] and not anon["acts_as_table_owner"]
    assert not any(" anon " in line for line in assessment["anon_or_authenticated_exposures"])


def test_column_privileges_from_public_or_an_inherited_role_are_exposures() -> None:
    """A sibling of finding 1: column privileges reach anon through PUBLIC and membership too."""

    assessment = audit.assess(observed_from(rehearsal_snapshot()))
    exposures = assessment["anon_or_authenticated_exposures"]
    for line in (
        "public.analysis_timeframe_results: anon SELECT OPEN ON COLUMNS run_id",
        "public.analysis_timeframe_results: anon INSERT OPEN ON COLUMNS timeframe",
        "public.analysis_timeframe_results: anon UPDATE OPEN ON COLUMNS disposition",
    ):
        assert line in exposures
    assert not any("DELETE" in line and "analysis_timeframe_results: anon" in line
                   for line in exposures)

    # Under row-level security with no applicable policy, column privileges admit no row.
    snapshot = rehearsal_snapshot()
    results = next(row for row in snapshot["tables"] if row[1] == "analysis_timeframe_results")
    results[4] = True
    assessment = audit.assess(observed_from(snapshot))
    assert _anon(assessment, "analysis_timeframe_results")["data_api"] == {
        "SELECT": "RLS_DENIES_ALL ON COLUMNS run_id",
        "INSERT": "RLS_DENIES_ALL ON COLUMNS timeframe",
        "UPDATE": "RLS_DENIES_ALL ON COLUMNS disposition",
        "DELETE": "NO_PRIVILEGE",
    }
    assert not any(line.startswith("public.analysis_timeframe_results: anon")
                   for line in assessment["anon_or_authenticated_exposures"])

    # With an applicable permissive policy, the policy decides those columns' rows.
    snapshot["policies"].append(
        ["public", "analysis_timeframe_results", "cols", "PERMISSIVE", ["anon"], "SELECT", "true",
         None]
    )
    snapshot["policy_applicability"] += [
        ["public", "analysis_timeframe_results", "cols", role, role == "anon"]
        for role in audit.API_ROLES
    ]
    assessment = audit.assess(observed_from(snapshot))
    verdict = "POLICY_DECIDES: cols ON COLUMNS run_id"
    assert _anon(assessment, "analysis_timeframe_results")["data_api"]["SELECT"] == verdict
    assert (
        f"public.analysis_timeframe_results: anon SELECT {verdict}"
        in assessment["anon_or_authenticated_exposures"]
    )


def test_realtime_follows_select_whether_the_table_or_a_policy_admits_it() -> None:
    snapshot = rehearsal_snapshot()
    snapshot["realtime_publications"] += [
        ["supabase_realtime", "public", "prediction_outcomes"],
        ["supabase_realtime", "public", "predictions"],
    ]
    exposures = audit.assess(observed_from(snapshot))["anon_or_authenticated_exposures"]
    assert (
        "public.prediction_outcomes: anon can receive change events through publication(s) "
        "supabase_realtime" in exposures
    )
    assert not any(line.startswith("public.predictions:") for line in exposures)


@pytest.mark.parametrize(
    "gap", ["privilege-row-missing", "owner-unknown", "usage-unknown", "realtime-refused",
            "views-refused"]
)
def test_a_missing_server_fact_makes_a_hardened_result_incomplete_never_safe(gap: str) -> None:
    snapshot = hardened_snapshot()
    errors: dict[str, str] = {}
    if gap == "privilege-row-missing":
        snapshot["effective_privileges"] = [
            row for row in snapshot["effective_privileges"]
            if row[:4] != ["public", "watchlist", "anon", "SELECT"]
        ]
    elif gap == "owner-unknown":
        set_fact(snapshot, "owner_equivalence", ("public", "watchlist", "anon"), None)
    elif gap == "usage-unknown":
        set_fact(snapshot, "schema_usage", ("public", "pg_database_owner", "anon"), None)
    elif gap == "realtime-refused":
        snapshot.pop("realtime_publications")
        errors["realtime_publications"] = "InsufficientPrivilege"
    elif gap == "views-refused":
        snapshot.pop("dependent_view_privileges")
        errors["dependent_view_privileges"] = "InsufficientPrivilege"
    assessment = audit.assess(observed_from(snapshot, query_errors=errors))
    assert assessment["anon_or_authenticated_exposures"] == []
    assert len(assessment["facts_incomplete"]) == 1, assessment["facts_incomplete"]
    assert assessment["verdict"] == "INCOMPLETE"


def test_an_unknown_view_privilege_is_reviewed_and_incomplete() -> None:
    snapshot = hardened_snapshot()
    snapshot["dependent_view_privileges"] = [
        ["public", "rehearsal_runs_view", "anon", "SELECT", None]
    ]
    assessment = audit.assess(observed_from(snapshot))
    assert assessment["anon_or_authenticated_exposures"][0].startswith(
        "public.rehearsal_runs_view (a view over an audited table): anon SELECT REVIEW"
    )
    assert assessment["facts_incomplete"] == [
        "public.rehearsal_runs_view: whether anon holds SELECT"
    ]
    assert assessment["verdict"] == "EXPOSED"


# --------------------------------------------------------------------------- the dispatch


def _dispatch(**changes: str) -> dict[str, str]:
    values = {
        "github_actions": "true",
        "event_name": "workflow_dispatch",
        "repository": REPOSITORY,
        "workflow_ref": f"{REPOSITORY}/{audit.WORKFLOW}@refs/heads/main",
        "ref": "refs/heads/main",
        "sha": SHA,
        "run_id": "987654321",
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
        "installed_files_sha256": "f" * 64,
    }
    values.update(changes)
    return values


def test_a_verified_dispatch_records_this_workflow() -> None:
    record = audit.verify_dispatch(_dispatch(), _runtime(), expected_sha=SHA)
    assert record["dispatch_verified"] is True and record["workflow"] == audit.WORKFLOW
    assert record["expected_sha"] == record["sha"] == record["git_head"] == SHA


DISPATCH_REFUSALS = {
    "not-actions": (_dispatch(github_actions=""), _runtime(), SHA),
    "push-event": (_dispatch(event_name="push"), _runtime(), SHA),
    "pull-request": (_dispatch(event_name="pull_request"), _runtime(), SHA),
    "other-branch": (_dispatch(ref="refs/heads/feature"), _runtime(), SHA),
    "the-0008-workflow": (
        _dispatch(workflow_ref=f"{REPOSITORY}/.github/workflows/apply-migration-0008.yml@refs/heads/main"),
        _runtime(),
        SHA,
    ),
    "the-rehearsal-workflow": (
        _dispatch(
            workflow_ref=(
                f"{REPOSITORY}/.github/workflows/audit-table-privileges-rehearsal.yml"
                "@refs/heads/main"
            )
        ),
        _runtime(),
        SHA,
    ),
    "self-consistent-fork": (
        _dispatch(
            repository="attacker/fork",
            workflow_ref=f"attacker/fork/{audit.WORKFLOW}@refs/heads/main",
        ),
        _runtime(),
        SHA,
    ),
    "short-sha": (_dispatch(sha=SHA[:7]), _runtime(git_head=SHA[:7]), SHA[:7]),
    "dispatched-other-commit": (_dispatch(sha="a" * 40), _runtime(), SHA),
    "checked-out-other-commit": (_dispatch(), _runtime(git_head="a" * 40), SHA),
    "dirty-tree": (_dispatch(), _runtime(tracked_tree_clean=False), SHA),
    "other-python": (_dispatch(), _runtime(python_version="3.12.9"), SHA),
    "not-isolated": (_dispatch(), _runtime(interpreter_flags=""), SHA),
    "unverified-install": (_dispatch(), _runtime(installed_files_sha256=""), SHA),
    "bad-run-id": (_dispatch(run_id="x"), _runtime(), SHA),
    "run-id-with-newline": (_dispatch(run_id="987654321\n"), _runtime(), SHA),
    "sha-with-newline": (_dispatch(sha=SHA + "\n"), _runtime(git_head=SHA + "\n"), SHA + "\n"),
    "install-digest-with-newline": (
        _dispatch(), _runtime(installed_files_sha256="f" * 64 + "\n"), SHA
    ),
}


@pytest.mark.parametrize("case", sorted(DISPATCH_REFUSALS))
def test_every_dispatch_deviation_refuses(case: str) -> None:
    dispatch, runtime, expected = DISPATCH_REFUSALS[case]
    with pytest.raises(ProvenanceRefused, match="dispatch does not verify"):
        audit.verify_dispatch(dispatch, runtime, expected_sha=expected)


# --------------------------------------------------------------------------- the entrypoint


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    events: list[str] = []

    def _enter(wheelhouse: str):
        events.append(f"enter:{wheelhouse}")
        return "isolation-report"

    def _attest(expected_sha, environ, isolation):
        events.append(f"attest:{expected_sha}")
        return {"dispatch_verified": True, "workflow": audit.WORKFLOW}

    monkeypatch.setattr(audit, "enter_isolated_runtime", _enter)
    monkeypatch.setattr(audit, "attest_dispatch", _attest)
    monkeypatch.setattr(audit, "attest_loaded_modules", lambda isolation: events.append("modules"))
    return events


def _argv(mode: str, tmp_path: Path, **overrides: str) -> list[str]:
    options = {
        "mode": mode,
        "expected-sha": SHA,
        "confirm": audit.CONFIRMATION,
        "wheelhouse": "/synthetic/runner-temp/section-5a-wheels",
        "report": str(tmp_path / "report.json"),
        **overrides,
    }
    return [f"--{name}={value}" for name, value in options.items() if value is not None]


def _install_driver(monkeypatch: pytest.MonkeyPatch, database: FakeDatabase, events: list[str]):
    def _load():
        events.append("driver")
        return database

    monkeypatch.setattr(audit, "load_driver", _load)


def test_audit_refuses_without_the_exact_token_before_anything_is_entered(
    calls: list[str], tmp_path: Path
) -> None:
    for token in ("", "audit", audit.CONFIRMATION.lower(), "APPLY-MIGRATION-0008-ONCE"):
        assert audit.main(_argv("audit", tmp_path, confirm=token), environ={}) == 2
    assert calls == []
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["outcome"] == "REFUSED" and report["committed"] is False


def test_attest_mode_touches_no_database(
    calls: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(healthy_results())
    _install_driver(monkeypatch, database, calls)
    code = audit.main(
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
    assert report["audited_tables"] == list(audit.AUDITED_TABLES)


def test_audit_without_a_database_url_refuses_before_the_driver_loads(
    calls: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(healthy_results())
    _install_driver(monkeypatch, database, calls)
    assert audit.main(_argv("audit", tmp_path), environ={}) == 2
    assert "driver" not in calls and database.connects == []


def test_a_full_audit_connects_read_only_and_reports_without_the_url(
    calls: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = FakeDatabase(healthy_results())
    _install_driver(monkeypatch, database, calls)
    code = audit.main(_argv("audit", tmp_path), environ={"SUPABASE_DB_URL": DATABASE_URL})
    assert code == 0
    assert calls == [
        "enter:/synthetic/runner-temp/section-5a-wheels",
        f"attest:{SHA}",
        "modules",
        "driver",
        "modules",
    ]
    assert database.connects == [(DATABASE_URL, {"connect_timeout": 8, "autocommit": False})]
    assert database.commits == 0 and database.rollbacks == 1
    report_text = (tmp_path / "report.json").read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert report["outcome"] == "AUDITED" and report["committed"] is False
    assert report["assessment"]["verdict"] == "EXPOSED"
    streams = capsys.readouterr()
    for text in (report_text, streams.out, streams.err):
        assert "NEVER-SHOWN-SECRET" not in text and "never-contacted" not in text


def test_an_unexpected_failure_withholds_its_message(
    calls: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    error = RuntimeError(f"connection to server at {DATABASE_URL} failed")
    database = FakeDatabase(healthy_results(), fail_on={audit.GUARD_STATEMENTS[0]: error})
    _install_driver(monkeypatch, database, calls)
    assert audit.main(_argv("audit", tmp_path), environ={"SUPABASE_DB_URL": DATABASE_URL}) == 1
    report_text = (tmp_path / "report.json").read_text(encoding="utf-8")
    assert json.loads(report_text)["outcome"] == "FAILED"
    streams = capsys.readouterr()
    for text in (report_text, streams.out, streams.err):
        assert "NEVER-SHOWN-SECRET" not in text and "never-contacted" not in text
    assert database.commits == 0


# --------------------------------------------------------------------------- the rehearsal mode


@pytest.mark.parametrize(
    "url",
    [
        "",
        DATABASE_URL,
        "postgresql://localhost/audit_rehearsal",
        "postgresql:///audit_rehearsal?host=/tmp",
        "postgresql:///audit_rehearsal?host=/var/run/postgresql&sslmode=disable",
        "postgresql:///audit_rehearsal?host=db.example.com",
        "postgres:///audit_rehearsal?host=/var/run/postgresql",
        "postgresql:///Audit?host=/var/run/postgresql",
    ],
)
def test_the_rehearsal_only_ever_reaches_a_local_socket(
    url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(healthy_results())
    events: list[str] = []
    _install_driver(monkeypatch, database, events)
    code = audit.main(
        _argv("rehearse", tmp_path, wheelhouse="", confirm=""),
        environ={audit.REHEARSAL_URL_VARIABLE: url},
    )
    assert code == 2 and database.connects == [] and events == []


def test_the_rehearsal_never_runs_beside_the_production_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(healthy_results())
    _install_driver(monkeypatch, database, [])
    environ = {audit.REHEARSAL_URL_VARIABLE: REHEARSAL_URL, "SUPABASE_DB_URL": DATABASE_URL}
    code = audit.main(_argv("rehearse", tmp_path, wheelhouse="", confirm=""), environ=environ)
    assert code == 2 and database.connects == []
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert "production database secret" in report["detail"]


def test_a_matching_rehearsal_passes_and_a_departing_one_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(healthy_results())
    _install_driver(monkeypatch, database, [])
    environ = {audit.REHEARSAL_URL_VARIABLE: REHEARSAL_URL}
    assert audit.main(_argv("rehearse", tmp_path, wheelhouse="", confirm=""), environ=environ) == 0
    assert database.connects == [(REHEARSAL_URL, {"connect_timeout": 8, "autocommit": False})]
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["outcome"] == "REHEARSED"

    snapshot = rehearsal_snapshot()
    snapshot["policies"] = []
    departing = FakeDatabase(healthy_results(snapshot))
    _install_driver(monkeypatch, departing, [])
    code = audit.main(_argv("rehearse", tmp_path, wheelhouse="", confirm=""), environ=environ)
    assert code == 2
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert "does not match its fixtures" in report["detail"]


def test_the_rehearsal_fixtures_build_what_the_expectations_describe() -> None:
    fixtures = ROOT / "scripts" / "audit_rehearsal"
    roles = (fixtures / "00_supabase_like_roles.sql").read_text(encoding="utf-8")
    variations = (fixtures / "90_variations.sql").read_text(encoding="utf-8")
    assert "CREATE ROLE service_role NOLOGIN NOINHERIT BYPASSRLS;" in roles
    assert "ALTER ROLE authenticator SET pgrst.db_schemas = 'public, graphql_public';" in roles
    assert "GRANT ALL ON TABLES TO anon, authenticated, service_role;" in roles
    assert "CREATE ROLE anon NOLOGIN NOINHERIT;" in roles
    assert audit.REHEARSAL_NON_STANDARD_ROLE == NON_STANDARD
    for statement in (
        f'CREATE ROLE "{NON_STANDARD}" NOLOGIN;',
        f'GRANT "{NON_STANDARD}" TO anon WITH INHERIT TRUE;',
        "GRANT rehearsal_owner TO anon WITH INHERIT TRUE;",
        "GRANT rehearsal_bystander TO anon WITH INHERIT FALSE;",
        "ALTER TABLE public.predictions ENABLE ROW LEVEL SECURITY;",
        "CREATE POLICY rehearsal_not_inherited ON public.predictions FOR SELECT TO "
        "rehearsal_bystander USING (true);",
        "CREATE POLICY rehearsal_read ON public.prediction_outcomes FOR SELECT TO anon",
        "CREATE POLICY rehearsal_inherited_insert ON public.prediction_outcomes FOR INSERT TO "
        f'"{NON_STANDARD}" WITH CHECK (false);',
        "AS RESTRICTIVE FOR SELECT TO anon USING (true);",
        "REVOKE ALL ON TABLE public.watchlist FROM anon, authenticated, service_role;",
        "GRANT SELECT ON TABLE public.watchlist TO rehearsal_bystander;",
        "GRANT SELECT (run_id) ON TABLE public.analysis_timeframe_results TO anon;",
        "GRANT INSERT (timeframe) ON TABLE public.analysis_timeframe_results TO PUBLIC;",
        "GRANT UPDATE (disposition) ON TABLE public.analysis_timeframe_results TO "
        f'"{NON_STANDARD}";',
        "ALTER TABLE public.news_evidence_links OWNER TO rehearsal_owner;",
        "ALTER TABLE public.news_evidence_links ENABLE ROW LEVEL SECURITY;",
        "REVOKE ALL ON TABLE public.news_evidence_links FROM anon;",
        "ALTER TABLE public.provider_observations OWNER TO rehearsal_owner;",
        "ALTER TABLE public.provider_observations FORCE ROW LEVEL SECURITY;",
        "REVOKE ALL ON TABLE public.provider_observations FROM anon;",
        "CREATE VIEW public.rehearsal_runs_view AS SELECT run_id FROM public.analysis_runs;",
        "CREATE PUBLICATION supabase_realtime FOR TABLE public.app_events;",
        "GRANT SELECT ON TABLE public.news_clusters TO PUBLIC;",
    ):
        assert statement in variations, statement
    # The synthetic snapshot mirrors exactly these fixtures.
    assert {row[1] for row in rehearsal_snapshot()["tables"] if row[3] == "rehearsal_owner"} == {
        "news_evidence_links", "provider_observations"
    }
    for text in (roles, variations):
        assert "PASSWORD" not in text.upper()


def _scrubbed_environment(extra: dict[str, str]) -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GITHUB_", "RUNNER_", "SUPABASE_", "PYTHON", "AUDIT_"))
        and key != "ImageOS"
    }
    environment.update(extra)
    return environment


def test_an_unisolated_process_refuses_before_any_database_access(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    completed = subprocess.run(
        [sys.executable, "-B", audit.SCRIPT, *_argv("audit", tmp_path, report=str(report))],
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
