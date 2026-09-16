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

RLS_TABLES = {"predictions", "prediction_outcomes", "news_items"}


def rehearsal_snapshot() -> dict[str, list]:
    """What the catalog queries return on the rehearsal fixtures (scripts/audit_rehearsal/)."""

    tables = [
        ["public", name, "r", "postgres", name in RLS_TABLES, False, False]
        for name in audit.AUDITED_TABLES
    ]
    effective = []
    for name in audit.AUDITED_TABLES:
        for role in audit.API_ROLES:
            for privilege in ALL_PRIVILEGES:
                held = True
                if name == "watchlist":
                    held = False
                if name == "analysis_timeframe_results" and role == "anon":
                    held = False
                effective.append(["public", name, role, privilege, held])
    grants = [
        ["public", name, role, privilege, False]
        for name in audit.AUDITED_TABLES
        for role in audit.API_ROLES
        for privilege in ALL_PRIVILEGES
        if name != "watchlist" and not (name == "analysis_timeframe_results" and role == "anon")
    ] + [["public", "news_clusters", "PUBLIC", "SELECT", False]]
    return {
        "roles": [
            ["anon", False, False, False, False],
            ["authenticated", False, False, False, False],
            ["service_role", False, True, False, False],
        ],
        "role_memberships": [],
        "tables": tables,
        "table_grants": sorted(grants),
        "effective_privileges": effective,
        "column_grants": [["public", "analysis_timeframe_results", "run_id", "anon", "SELECT"]],
        "policies": [
            [
                "public", "news_items", "rehearsal_narrow", "RESTRICTIVE",
                "{anon}", "SELECT", "true", None,
            ],
            [
                "public", "prediction_outcomes", "rehearsal_read", "PERMISSIVE",
                "{anon}", "SELECT", "true", None,
            ],
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
    observed: dict[str, Any] = {"query_errors": {}, "transaction_read_only": "on"}
    observed.update(deepcopy(snapshot))
    observed.update(overrides)
    return observed


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
            ("SELECT ", "SET TRANSACTION READ ONLY", "SET LOCAL ", "SAVEPOINT audit_",
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
    database = FakeDatabase(healthy_results(snapshot))
    observed, _ = _read(database)
    assert observed["tables"][0][3] == "<non-standard role name withheld>"
    assert observed["schema_usage"][0][1] == "<non-standard role name withheld>"
    assert observed["role_memberships"] == [["anon", "<non-standard role name withheld>"]]
    assert "abcdefghijklmnop" not in json.dumps(observed)


# --------------------------------------------------------------------------- the assessment


def test_the_rehearsal_snapshot_satisfies_every_rehearsal_expectation() -> None:
    observed = observed_from(rehearsal_snapshot())
    assessment = audit.assess(observed)
    assert audit.rehearsal_failures(observed, assessment) == []
    assert assessment["verdict"] == "EXPOSED"
    assert assessment["api_schemas"] == ["graphql_public", "public"]
    assert assessment["public_grants"] == [["public", "news_clusters", "SELECT"]]
    assert any("SECURITY DEFINER" in item for item in assessment["not_audited"])
    prediction_outcomes = assessment["tables"]["public.prediction_outcomes"]["roles"]
    assert prediction_outcomes["authenticated"]["data_api"] == dict.fromkeys(
        audit.API_PRIVILEGES, "RLS_DENIES_ALL"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "predictions-without-rls",
        "restrictive-becomes-permissive",
        "watchlist-granted",
        "column-grant-gone",
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
        snapshot["column_grants"] = []
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


def test_a_fully_hardened_database_is_not_exposed() -> None:
    """The shape 0005, 0006 and 0009 have: RLS on, no API grant but service_role's."""

    snapshot = rehearsal_snapshot()
    for row in snapshot["tables"]:
        row[4] = True
    for row in snapshot["effective_privileges"]:
        row[4] = row[2] == "service_role" and row[3] in ("SELECT", "INSERT")
    snapshot["table_grants"] = []
    snapshot["column_grants"] = []
    snapshot["policies"] = []
    snapshot["dependent_views"] = []
    snapshot["dependent_view_privileges"] = []
    assessment = audit.assess(observed_from(snapshot))
    assert assessment["anon_or_authenticated_exposures"] == []
    assert assessment["verdict"] == "NOT_EXPOSED_THROUGH_TABLE_GRANTS"
    service = assessment["tables"]["public.predictions"]["roles"]["service_role"]
    assert service["data_api"] == {
        "SELECT": "OPEN", "INSERT": "OPEN", "UPDATE": "NO_PRIVILEGE", "DELETE": "NO_PRIVILEGE"
    }


def test_an_all_command_policy_for_public_decides_every_command() -> None:
    snapshot = rehearsal_snapshot()
    snapshot["policies"].append(
        ["public", "predictions", "open_all", "PERMISSIVE", "{public}", "ALL", "true", "true"]
    )
    assessment = audit.assess(observed_from(snapshot))
    anon = assessment["tables"]["public.predictions"]["roles"]["anon"]["data_api"]
    assert anon == dict.fromkeys(audit.API_PRIVILEGES, "POLICY_DECIDES: open_all")
    assert any(line.startswith("public.predictions: anon DELETE POLICY_DECIDES") for line in
               assessment["anon_or_authenticated_exposures"])


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
    for statement in (
        "ALTER TABLE public.predictions ENABLE ROW LEVEL SECURITY;",
        "CREATE POLICY rehearsal_read ON public.prediction_outcomes FOR SELECT TO anon",
        "AS RESTRICTIVE FOR SELECT TO anon USING (true);",
        "REVOKE ALL ON TABLE public.watchlist FROM anon, authenticated, service_role;",
        "GRANT SELECT (run_id) ON TABLE public.analysis_timeframe_results TO anon;",
        "CREATE VIEW public.rehearsal_runs_view AS SELECT run_id FROM public.analysis_runs;",
        "CREATE PUBLICATION supabase_realtime FOR TABLE public.app_events;",
        "GRANT SELECT ON TABLE public.news_clusters TO PUBLIC;",
    ):
        assert statement in variations, statement
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
