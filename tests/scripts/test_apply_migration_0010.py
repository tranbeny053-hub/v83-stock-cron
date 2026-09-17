"""The one-shot apply of migration 0010 (the legacy tables' security). No database is contacted.

Every database interaction runs against a fake driver that behaves like psycopg 3 where it matters:
a connection used as a context manager commits on success and rolls back on an exception, a
statement is recorded with its parameters, and a check read before and after the migration can
return different rows. The real PostgreSQL rehearsal runs in CI
(.github/workflows/apply-migration-0010-rehearsal.yml).
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

ROOT = Path(__file__).resolve().parents[2]
MIGRATION_BYTES = (ROOT / apply_0010.MIGRATION).read_bytes()
MIGRATION_SQL = MIGRATION_BYTES.decode("utf-8")
DATABASE_URL = "postgresql://owner:NEVER-SHOWN-SECRET@db.never-contacted.invalid:5432/postgres"
REHEARSAL_URL = "postgresql:///migration_0010_rehearsal?host=/var/run/postgresql"
SHA = "c" * 40
REPOSITORY = apply_0010.EXPECTED_REPOSITORY
ALL = list(apply_0010.TABLE_PRIVILEGES)
SEQUENCE_ALL = list(apply_0010.SEQUENCE_PRIVILEGES)


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


# ------------------------------------------------------------------------ the audited state


def legacy_row(table: str, **changes: Any) -> tuple:
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
        "anon": list(ALL),
        "authenticated": list(ALL),
        "service_role": list(ALL),
    }
    values.update(changes)
    return tuple(values[field] for field in apply_0010.SECURITY_FIELDS)


def audited_legacy(**changes: Any) -> list[tuple]:
    return [legacy_row(table, **changes) for table in apply_0010.LEGACY_TABLES]


def applied_legacy(**changes: Any) -> list[tuple]:
    return [
        legacy_row(table, **{"anon": [], "authenticated": [], **changes})
        for table in apply_0010.LEGACY_TABLES
    ]


def sequence_row(table: str, sequence: str, **changes: Any) -> tuple:
    values = {
        "table": table,
        "sequence": sequence,
        "public_has_a_privilege": False,
        "anon": list(SEQUENCE_ALL),
        "authenticated": list(SEQUENCE_ALL),
        "service_role": list(SEQUENCE_ALL),
    }
    values.update(changes)
    return tuple(values[field] for field in apply_0010.SEQUENCE_FIELDS)


def audited_sequences(**changes: Any) -> list[tuple]:
    return [
        sequence_row(table, sequence, **changes)
        for table, _, sequence in apply_0010.LEGACY_SEQUENCES
    ]


def applied_sequences(**changes: Any) -> list[tuple]:
    return audited_sequences(**{"anon": [], "authenticated": [], **changes})


OTHER_SERVICE_ROLE = {
    "analysis_run_details": ["INSERT", "SELECT", "UPDATE"],
    "prediction_derivatives_snapshots": ["INSERT", "SELECT"],
    "prediction_feature_snapshots": ["INSERT", "SELECT"],
    "section_5a_evaluation_seal": [],
}


def other_rows() -> list[tuple]:
    return [
        legacy_row(table, anon=[], authenticated=[], service_role=OTHER_SERVICE_ROLE[table])
        for table in sorted(apply_0010.OTHER_TABLES)
    ]


def healthy_results(**overrides: Any) -> dict[str, Any]:
    """What a first apply returns on the audited production database."""

    results: dict[str, Any] = {
        apply_0010.ROLES_SQL: [(3,)],
        apply_0010.LEGACY_SECURITY_SQL: Each([audited_legacy(), applied_legacy()]),
        apply_0010.SEQUENCE_SECURITY_SQL: Each([audited_sequences(), applied_sequences()]),
        apply_0010.OTHER_SECURITY_SQL: Each([other_rows(), other_rows()]),
    }
    results.update(overrides)
    return results


EXPECTED_ORDER = [
    *apply_0010.TIMEOUT_STATEMENTS,
    apply_0010.ADVISORY_LOCK_SQL,
    apply_0010.ROLES_SQL,
    apply_0010.LEGACY_SECURITY_SQL,
    apply_0010.SEQUENCE_SECURITY_SQL,
    apply_0010.OTHER_SECURITY_SQL,
    MIGRATION_SQL,
    apply_0010.LEGACY_SECURITY_SQL,
    apply_0010.SEQUENCE_SECURITY_SQL,
    apply_0010.OTHER_SECURITY_SQL,
]


def _apply(database: FakeDatabase) -> tuple[dict[str, Any], dict[str, Any]]:
    captured: dict[str, Any] = {}
    outcome = apply_0010.apply_in_one_transaction(
        lambda: database.connect(DATABASE_URL), MIGRATION_SQL, captured
    )
    return outcome, captured


# --------------------------------------------------------------------------- the contract


def test_the_script_imports_only_the_standard_library_at_module_level() -> None:
    tree = ast.parse((ROOT / apply_0010.SCRIPT).read_text(encoding="utf-8"))
    imported = {
        (node.module if isinstance(node, ast.ImportFrom) else alias.name).split(".")[0]
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in (node.names if isinstance(node, ast.Import) else [None])
    }
    assert imported and all(
        name == "__future__" or name in sys.stdlib_module_names for name in imported
    ), imported


def test_it_names_itself_its_workflows_and_the_reviewed_bytes() -> None:
    assert (ROOT / apply_0010.SCRIPT).resolve() == Path(apply_0010.__file__).resolve()
    assert (ROOT / apply_0010.WORKFLOW).is_file()
    assert (ROOT / apply_0010.REHEARSAL_WORKFLOW).is_file()
    assert hashlib.sha256(MIGRATION_BYTES).hexdigest() == apply_0010.MIGRATION_SHA256
    assert apply_0010.CONFIRMATION == "APPLY-MIGRATION-0010-ONCE"
    assert apply_0010.EXPECTED_REPOSITORY == "tranbeny053-hub/v83-stock-cron"


def test_its_lock_and_token_are_its_own() -> None:
    assert apply_0010.ADVISORY_LOCK_SQL not in {
        "SELECT pg_advisory_xact_lock(5000008)",
        "SELECT pg_advisory_xact_lock(5009005)",
    }
    from scripts import apply_migration_0008

    assert apply_0010.CONFIRMATION != apply_migration_0008.CONFIRMATION
    assert apply_0010.WORKFLOW != apply_migration_0008.WORKFLOW


FORBIDDEN_WORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|TRUNCATE|ALTER|CREATE|DROP|GRANT|REVOKE|COPY|CALL|DO|VACUUM|"
    r"ANALYZE|LOCK|NOTIFY|LISTEN|REFRESH|CLUSTER|REINDEX|COMMENT|SECURITY|EXECUTE|PREPARE)\b"
)


def _without_literals(statement: str) -> str:
    return re.sub(r"'[^']*'", "''", statement)


def test_every_check_is_a_read_only_catalog_query_without_parameters() -> None:
    checks = [statement for statement in EXPECTED_ORDER if statement is not MIGRATION_SQL]
    for statement in checks:
        bare = _without_literals(statement)
        assert bare.startswith(("SELECT ", "SET LOCAL ")), statement
        assert not FORBIDDEN_WORDS.search(bare), statement
        assert ";" not in bare and "%" not in bare
        for target in re.findall(r"\b(?:FROM|JOIN)\s+(?:LATERAL\s+)?(\S+)", bare):
            assert target.startswith(("pg_catalog.", "(")), (statement, target)


def test_no_check_reads_an_application_row() -> None:
    for statement in (
        apply_0010.LEGACY_SECURITY_SQL,
        apply_0010.SEQUENCE_SECURITY_SQL,
        apply_0010.OTHER_SECURITY_SQL,
        apply_0010.ROLES_SQL,
    ):
        for table in (*apply_0010.LEGACY_TABLES, *apply_0010.OTHER_TABLES):
            assert f"FROM public.{table}" not in statement
            assert f"JOIN public.{table}" not in statement


def test_the_checks_cover_every_table_role_privilege_and_sequence() -> None:
    legacy = apply_0010.LEGACY_SECURITY_SQL
    for table in apply_0010.LEGACY_TABLES:
        assert f"('{table}')" in legacy
    for table in apply_0010.OTHER_TABLES:
        assert f"('{table}')" in apply_0010.OTHER_SECURITY_SQL
    for role in apply_0010.API_ROLES:
        assert f"has_table_privilege('{role}', c.oid, v.privilege)" in legacy
        assert (
            f"has_sequence_privilege('{role}', q.oid, v.privilege)"
            in apply_0010.SEQUENCE_SECURITY_SQL
        )
    for privilege in apply_0010.TABLE_PRIVILEGES:
        assert f"('{privilege}')" in legacy
    assert "a.grantee = 0" in legacy, "PUBLIC is grantee 0"
    assert "att.attacl" in legacy, "column grants are checked"
    assert "pg_policy" in legacy and "relforcerowsecurity" in legacy
    assert 'COLLATE "C"' in legacy, "the order never depends on the database collation"
    assert len(apply_0010.SECURITY_FIELDS) == 12 and len(apply_0010.SEQUENCE_FIELDS) == 6


# --------------------------------------------------------------------------- the one transaction


def test_a_first_apply_runs_every_check_in_one_committed_transaction() -> None:
    database = FakeDatabase(healthy_results())
    outcome, captured = _apply(database)

    assert database.executed() == EXPECTED_ORDER
    assert all(params is None for _, params in database.statements)
    assert database.commits == 1 and database.rollbacks == 0
    assert outcome["outcome"] == "APPLIED" and outcome["committed"] is True
    assert outcome["executed_migration_sha256"] == apply_0010.MIGRATION_SHA256
    assert captured["pre_legacy"][0]["anon"] == ALL
    assert captured["post_legacy"][0]["anon"] == []
    assert captured["post_legacy"][0]["service_role"] == ALL
    assert captured["post_other"] == captured["pre_other"]
    assert captured["committed"] is True


def test_the_migration_statement_is_exactly_the_file() -> None:
    database = FakeDatabase(healthy_results())
    _apply(database)
    (executed,) = [s for s in database.executed() if s.startswith("-- The security posture")]
    assert executed.encode("utf-8") == MIGRATION_BYTES


def _one(rows: list[tuple], index: int, **changes: Any) -> list[tuple]:
    """``rows`` with only row ``index`` changed."""

    values = {**dict(zip(apply_0010.SECURITY_FIELDS, rows[index], strict=True)), **changes}
    changed = list(rows)
    changed[index] = tuple(values[field] for field in apply_0010.SECURITY_FIELDS)
    return changed


PRE_CHECK_DIFFERENCES = {
    "a-table-missing": {"LEGACY": audited_legacy()[:-1]},
    "a-table-twice": {"LEGACY": _one(audited_legacy(), 0, relations_named_so=2)},
    "a-table-absent": {"LEGACY": _one(audited_legacy(), 1, relations_named_so=0, relkind=None)},
    "a-view": {"LEGACY": _one(audited_legacy(), 2, relkind="v")},
    "another-owner": {"LEGACY": _one(audited_legacy(), 3, owned_by_applying_role=False)},
    "rls-off": {"LEGACY": _one(audited_legacy(), 4, row_level_security=False)},
    "rls-forced": {"LEGACY": _one(audited_legacy(), 5, row_level_security_forced=True)},
    "a-policy": {"LEGACY": _one(audited_legacy(), 6, policies=1)},
    "a-public-grant": {"LEGACY": _one(audited_legacy(), 7, public_has_a_privilege=True)},
    "a-column-grant": {
        "LEGACY": _one(audited_legacy(), 8, column_grant_to_public_anon_or_authenticated=True)
    },
    "service-role-lacks-delete": {
        "LEGACY": _one(audited_legacy(), 9, service_role=[p for p in ALL if p != "DELETE"])
    },
    "service-role-unreadable": {"LEGACY": _one(audited_legacy(), 0, service_role=None)},
    "already-applied": {"LEGACY": applied_legacy()},
    "wrong-order": {"LEGACY": list(reversed(audited_legacy()))},
    "sequence-renamed": {
        "SEQUENCE": [
            sequence_row("analysis_timeframe_results", "public.renamed_seq"),
            *audited_sequences()[1:],
        ]
    },
    "sequence-missing": {"SEQUENCE": audited_sequences()[:2]},
    "sequence-public-grant": {"SEQUENCE": audited_sequences(public_has_a_privilege=True)},
    "other-table-missing": {"OTHER": other_rows()[:3]},
    "other-table-absent": {
        "OTHER": [
            *other_rows()[:3],
            legacy_row("section_5a_evaluation_seal", relations_named_so=0, relkind=None),
        ]
    },
}


def _pre(difference: str) -> dict[str, Any]:
    keys = {
        "LEGACY": apply_0010.LEGACY_SECURITY_SQL,
        "SEQUENCE": apply_0010.SEQUENCE_SECURITY_SQL,
        "OTHER": apply_0010.OTHER_SECURITY_SQL,
    }
    changes = PRE_CHECK_DIFFERENCES[difference]
    overrides = {}
    for key, rows in changes.items():
        after = {
            "LEGACY": applied_legacy(),
            "SEQUENCE": applied_sequences(),
            "OTHER": other_rows(),
        }[key]
        overrides[keys[key]] = Each([rows, after])
    return healthy_results(**overrides)


@pytest.mark.parametrize("difference", sorted(PRE_CHECK_DIFFERENCES))
def test_a_database_not_in_the_audited_state_refuses_before_the_migration(difference: str) -> None:
    database = FakeDatabase(_pre(difference))
    with pytest.raises(ProvenanceRefused, match="nothing is applied"):
        _apply(database)
    assert MIGRATION_SQL not in database.executed()
    assert database.commits == 0 and database.rollbacks == 1


def test_a_second_apply_refuses_as_not_a_first_apply() -> None:
    database = FakeDatabase(
        healthy_results(
            **{apply_0010.LEGACY_SECURITY_SQL: Each([applied_legacy()])},
        )
    )
    with pytest.raises(ProvenanceRefused, match=apply_0010.NOT_A_FIRST_APPLY):
        _apply(database)
    assert database.executed()[-1] == apply_0010.LEGACY_SECURITY_SQL


def test_missing_api_roles_refuse_before_anything_is_read() -> None:
    database = FakeDatabase(healthy_results(**{apply_0010.ROLES_SQL: [(2,)]}))
    with pytest.raises(ProvenanceRefused, match="Supabase API roles"):
        _apply(database)
    assert database.executed()[-1] == apply_0010.ROLES_SQL


def _post(key: str, rows: list[tuple]) -> dict[str, Any]:
    before = {
        apply_0010.LEGACY_SECURITY_SQL: audited_legacy(),
        apply_0010.SEQUENCE_SECURITY_SQL: audited_sequences(),
        apply_0010.OTHER_SECURITY_SQL: other_rows(),
    }[key]
    return healthy_results(**{key: Each([before, rows])})


_CHANGED_OTHER = list(other_rows())
_CHANGED_OTHER[0] = legacy_row(
    "analysis_run_details", anon=["SELECT"], authenticated=[], service_role=["SELECT"]
)
POST_CHECK_DIFFERENCES = {
    "anon-keeps-a-privilege": (
        apply_0010.LEGACY_SECURITY_SQL,
        _one(applied_legacy(), 0, anon=["TRUNCATE"]),
    ),
    "authenticated-keeps-a-privilege": (
        apply_0010.LEGACY_SECURITY_SQL,
        _one(applied_legacy(), 9, authenticated=["SELECT"]),
    ),
    "rls-turned-off": (
        apply_0010.LEGACY_SECURITY_SQL,
        _one(applied_legacy(), 1, row_level_security=False),
    ),
    "rls-forced": (
        apply_0010.LEGACY_SECURITY_SQL,
        _one(applied_legacy(), 2, row_level_security_forced=True),
    ),
    "a-policy-appeared": (apply_0010.LEGACY_SECURITY_SQL, _one(applied_legacy(), 3, policies=1)),
    "owner-changed": (
        apply_0010.LEGACY_SECURITY_SQL,
        _one(applied_legacy(), 4, owned_by_applying_role=False),
    ),
    "public-granted": (
        apply_0010.LEGACY_SECURITY_SQL,
        _one(applied_legacy(), 5, public_has_a_privilege=True),
    ),
    "column-granted": (
        apply_0010.LEGACY_SECURITY_SQL,
        _one(applied_legacy(), 6, column_grant_to_public_anon_or_authenticated=True),
    ),
    "service-role-narrowed": (
        apply_0010.LEGACY_SECURITY_SQL,
        _one(applied_legacy(), 7, service_role=["SELECT"]),
    ),
    "a-table-vanished": (apply_0010.LEGACY_SECURITY_SQL, applied_legacy()[1:]),
    "sequence-anon-keeps-usage": (
        apply_0010.SEQUENCE_SECURITY_SQL,
        [sequence_row("analysis_timeframe_results", "public.analysis_timeframe_results_id_seq",
                      anon=["USAGE"], authenticated=[]), *applied_sequences()[1:]],
    ),
    "sequence-service-role-changed": (
        apply_0010.SEQUENCE_SECURITY_SQL,
        applied_sequences(service_role=["USAGE"]),
    ),
    "sequence-public-granted": (
        apply_0010.SEQUENCE_SECURITY_SQL,
        applied_sequences(public_has_a_privilege=True),
    ),
    "sequences-vanished": (apply_0010.SEQUENCE_SECURITY_SQL, []),
    "another-migration-s-table-changed": (apply_0010.OTHER_SECURITY_SQL, _CHANGED_OTHER),
}


@pytest.mark.parametrize("difference", sorted(POST_CHECK_DIFFERENCES))
def test_any_difference_from_the_reviewed_posture_rolls_the_apply_back(difference: str) -> None:
    key, rows = POST_CHECK_DIFFERENCES[difference]
    database = FakeDatabase(_post(key, rows))
    captured: dict[str, Any] = {}
    with pytest.raises(ProvenanceRefused, match="nothing is applied"):
        apply_0010.apply_in_one_transaction(
            lambda: database.connect(DATABASE_URL), MIGRATION_SQL, captured
        )
    assert MIGRATION_SQL in database.executed(), "the difference is seen only after applying"
    assert database.commits == 0 and database.rollbacks == 1
    assert "committed" not in captured
    assert "post_legacy" in captured, "what was seen is reported"


UNIQUE_STATEMENTS = list(dict.fromkeys(EXPECTED_ORDER))


@pytest.mark.parametrize("position", range(len(UNIQUE_STATEMENTS)))
def test_a_driver_error_at_any_statement_rolls_back(position: int) -> None:
    statement = UNIQUE_STATEMENTS[position]
    database = FakeDatabase(healthy_results(), fail_on={statement: RuntimeError("boom")})
    captured: dict[str, Any] = {}
    with pytest.raises(RuntimeError):
        apply_0010.apply_in_one_transaction(
            lambda: database.connect(DATABASE_URL), MIGRATION_SQL, captured
        )
    assert database.commits == 0 and database.rollbacks == 1
    assert "committed" not in captured


def test_a_malformed_check_row_refuses() -> None:
    database = FakeDatabase(
        healthy_results(**{apply_0010.LEGACY_SECURITY_SQL: Each([[("analysis_runs", 1)]])})
    )
    with pytest.raises(ProvenanceRefused, match="not a row of 12 values"):
        _apply(database)
    assert database.rollbacks == 1


def test_the_judges_name_every_difference_not_only_the_first() -> None:
    fields = apply_0010.SECURITY_FIELDS
    broken = [
        {**dict.fromkeys(fields), "table": table} for table in apply_0010.LEGACY_TABLES
    ]
    assert len(apply_0010.legacy_pre_check_failures(broken)) == 10 * 9
    healthy = [dict(zip(fields, row, strict=True)) for row in audited_legacy()]
    applied = [dict(zip(fields, row, strict=True)) for row in applied_legacy()]
    assert apply_0010.legacy_pre_check_failures(healthy) == []
    assert apply_0010.legacy_post_check_failures(healthy, applied) == []
    assert len(apply_0010.legacy_post_check_failures(healthy, healthy)) == 10 * 2


# --------------------------------------------------------------------------- the dispatch


def _dispatch(**changes: str) -> dict[str, str]:
    values = {
        "github_actions": "true",
        "event_name": "workflow_dispatch",
        "repository": REPOSITORY,
        "workflow_ref": f"{REPOSITORY}/{apply_0010.WORKFLOW}@refs/heads/main",
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
    record = apply_0010.verify_dispatch(_dispatch(), _runtime(), expected_sha=SHA)
    assert record["dispatch_verified"] is True
    assert record["workflow"] == apply_0010.WORKFLOW
    assert record["expected_sha"] == record["sha"] == record["git_head"] == SHA


DISPATCH_REFUSALS = {
    "not-actions": (_dispatch(github_actions=""), _runtime(), SHA),
    "push-event": (_dispatch(event_name="push"), _runtime(), SHA),
    "pull-request": (_dispatch(event_name="pull_request"), _runtime(), SHA),
    "other-branch": (_dispatch(ref="refs/heads/feature"), _runtime(), SHA),
    "the-0008-workflow": (
        _dispatch(
            workflow_ref=f"{REPOSITORY}/.github/workflows/apply-migration-0008.yml@refs/heads/main"
        ),
        _runtime(),
        SHA,
    ),
    "the-rehearsal-workflow": (
        _dispatch(workflow_ref=f"{REPOSITORY}/{apply_0010.REHEARSAL_WORKFLOW}@refs/heads/main"),
        _runtime(),
        SHA,
    ),
    "workflow-from-a-branch": (
        _dispatch(workflow_ref=f"{REPOSITORY}/{apply_0010.WORKFLOW}@refs/heads/feature"),
        _runtime(),
        SHA,
    ),
    "self-consistent-fork": (
        _dispatch(
            repository="attacker/fork",
            workflow_ref=f"attacker/fork/{apply_0010.WORKFLOW}@refs/heads/main",
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
        apply_0010.verify_dispatch(dispatch, runtime, expected_sha=expected)


def test_different_migration_bytes_refuse_before_any_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(apply_0010, "MIGRATION_SHA256", "0" * 64)
    with pytest.raises(ProvenanceRefused, match="not the reviewed"):
        apply_0010.migration_bytes()


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
        return {"dispatch_verified": True, "workflow": apply_0010.WORKFLOW}

    monkeypatch.setattr(apply_0010, "enter_isolated_runtime", _enter)
    monkeypatch.setattr(apply_0010, "attest_dispatch", _attest)
    monkeypatch.setattr(
        apply_0010, "attest_loaded_modules", lambda isolation: events.append("modules")
    )
    return events


def _argv(mode: str, tmp_path: Path, **overrides: str) -> list[str]:
    options = {
        "mode": mode,
        "expected-sha": SHA,
        "confirm": apply_0010.CONFIRMATION,
        "wheelhouse": "/synthetic/runner-temp/section-5a-wheels",
        "report": str(tmp_path / "report.json"),
        **overrides,
    }
    return [f"--{name}={value}" for name, value in options.items() if value is not None]


def _install_driver(monkeypatch: pytest.MonkeyPatch, database: FakeDatabase, events: list[str]):
    def _load():
        events.append("driver")
        return database

    monkeypatch.setattr(apply_0010, "load_driver", _load)


def test_apply_refuses_without_the_exact_token_before_anything_is_entered(
    calls: list[str], tmp_path: Path
) -> None:
    for token in (
        "",
        "apply",
        apply_0010.CONFIRMATION.lower(),
        apply_0010.CONFIRMATION + " ",
        "APPLY-MIGRATION-0008-ONCE",
    ):
        assert apply_0010.main(_argv("apply", tmp_path, confirm=token), environ={}) == 2
    assert calls == []
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["outcome"] == "REFUSED" and report["committed"] is False
    assert apply_0010.CONFIRMATION in report["detail"]


def test_attest_mode_touches_no_database(
    calls: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(healthy_results())
    _install_driver(monkeypatch, database, calls)
    code = apply_0010.main(
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
    assert report["migration_sha256"] == apply_0010.MIGRATION_SHA256


def test_apply_without_a_database_url_refuses_before_the_driver_loads(
    calls: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(healthy_results())
    _install_driver(monkeypatch, database, calls)
    assert apply_0010.main(_argv("apply", tmp_path), environ={}) == 2
    assert "driver" not in calls and database.connects == []


def test_a_full_apply_reports_raw_results_without_the_url(
    calls: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = FakeDatabase(healthy_results())
    _install_driver(monkeypatch, database, calls)
    code = apply_0010.main(_argv("apply", tmp_path), environ={"SUPABASE_DB_URL": DATABASE_URL})
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
    assert report["post_legacy"][0]["anon"] == []
    streams = capsys.readouterr()
    for text in (report_text, streams.out, streams.err):
        assert "NEVER-SHOWN-SECRET" not in text and "never-contacted" not in text


def test_a_refused_apply_reports_what_it_saw_and_commits_nothing(
    calls: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(_pre("rls-off"))
    _install_driver(monkeypatch, database, calls)
    code = apply_0010.main(_argv("apply", tmp_path), environ={"SUPABASE_DB_URL": DATABASE_URL})
    assert code == 2
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["outcome"] == "REFUSED" and report["committed"] is False
    assert report["captured"]["pre_legacy"][4]["row_level_security"] is False
    assert database.commits == 0


def test_an_unexpected_failure_withholds_its_message_because_it_can_name_the_host(
    calls: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    error = RuntimeError(f"connection to server at {DATABASE_URL} failed")
    database = FakeDatabase(healthy_results(), fail_on={apply_0010.ROLES_SQL: error})
    _install_driver(monkeypatch, database, calls)
    code = apply_0010.main(_argv("apply", tmp_path), environ={"SUPABASE_DB_URL": DATABASE_URL})
    assert code == 1
    report_text = (tmp_path / "report.json").read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert report["outcome"] == "FAILED" and report["error_type"] == "RuntimeError"
    streams = capsys.readouterr()
    for text in (report_text, streams.out, streams.err):
        assert "NEVER-SHOWN-SECRET" not in text and "never-contacted" not in text
    assert database.rollbacks == 1 and database.commits == 0


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
    apply_0010.attest_loaded_modules("isolation")
    assert seen["pinned"] == (*pinned_files(ROOT), apply_0010.SCRIPT)
    assert Path(seen["root"]).resolve() == ROOT


# --------------------------------------------------------------------------- the rehearsal mode


def _rehearsal_results() -> dict[str, Any]:
    """The scratch database: the first apply succeeds, the second finds nothing left to do."""

    return {
        apply_0010.ROLES_SQL: [(3,)],
        apply_0010.LEGACY_SECURITY_SQL: Each([audited_legacy(), applied_legacy()]),
        apply_0010.SEQUENCE_SECURITY_SQL: Each([audited_sequences(), applied_sequences()]),
        apply_0010.OTHER_SECURITY_SQL: Each([other_rows()]),
    }


def test_a_rehearsal_applies_once_and_proves_a_second_apply_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(_rehearsal_results())
    _install_driver(monkeypatch, database, [])
    environ = {apply_0010.REHEARSAL_URL_VARIABLE: REHEARSAL_URL}
    code = apply_0010.main(_argv("rehearse", tmp_path, wheelhouse="", confirm=""), environ=environ)
    assert code == 0
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["outcome"] == "REHEARSED"
    assert report["first_apply"]["outcome"] == "APPLIED"
    assert apply_0010.NOT_A_FIRST_APPLY in report["second_apply_refusal"]
    assert database.connects == [
        (REHEARSAL_URL, {"connect_timeout": 8}),
        (REHEARSAL_URL, {"connect_timeout": 8}),
    ]
    assert database.commits == 1 and database.rollbacks == 1


def test_a_rehearsal_whose_second_apply_succeeds_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(healthy_results())
    _install_driver(monkeypatch, database, [])
    database.results[apply_0010.LEGACY_SECURITY_SQL] = Each(
        [audited_legacy(), applied_legacy(), audited_legacy(), applied_legacy()]
    )
    database.results[apply_0010.SEQUENCE_SECURITY_SQL] = Each(
        [audited_sequences(), applied_sequences(), audited_sequences(), applied_sequences()]
    )
    environ = {apply_0010.REHEARSAL_URL_VARIABLE: REHEARSAL_URL}
    code = apply_0010.main(_argv("rehearse", tmp_path, wheelhouse="", confirm=""), environ=environ)
    assert code == 2
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert "one-shot property does not hold" in report["detail"]


def test_a_rehearsal_whose_second_apply_fails_otherwise_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    results = _rehearsal_results()
    results[apply_0010.ROLES_SQL] = Each([[(3,)], [(2,)]])
    database = FakeDatabase(results)
    _install_driver(monkeypatch, database, [])
    environ = {apply_0010.REHEARSAL_URL_VARIABLE: REHEARSAL_URL}
    code = apply_0010.main(_argv("rehearse", tmp_path, wheelhouse="", confirm=""), environ=environ)
    assert code == 2
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert "Supabase API roles" in report["detail"]


@pytest.mark.parametrize(
    "url",
    [
        "",
        DATABASE_URL,
        "postgresql://localhost/migration_0010_rehearsal",
        "postgresql://user@/migration_0010_rehearsal?host=/var/run/postgresql",
        "postgresql:///migration_0010_rehearsal?host=/tmp",
        "postgresql:///migration_0010_rehearsal?host=/var/run/postgresql&sslmode=disable",
        "postgresql:///migration_0010_rehearsal?host=/var/run/postgresql\n",
        "POSTGRESQL:///migration_0010_rehearsal?host=/var/run/postgresql",
        "postgres:///migration_0010_rehearsal?host=/var/run/postgresql",
        "postgresql:///Rehearsal?host=/var/run/postgresql",
    ],
)
def test_the_rehearsal_only_ever_reaches_a_local_socket(
    url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(_rehearsal_results())
    events: list[str] = []
    _install_driver(monkeypatch, database, events)
    code = apply_0010.main(
        _argv("rehearse", tmp_path, wheelhouse="", confirm=""),
        environ={apply_0010.REHEARSAL_URL_VARIABLE: url},
    )
    assert code == 2 and database.connects == [] and events == []


def test_the_rehearsal_never_runs_beside_the_production_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(_rehearsal_results())
    _install_driver(monkeypatch, database, [])
    environ = {apply_0010.REHEARSAL_URL_VARIABLE: REHEARSAL_URL, "SUPABASE_DB_URL": DATABASE_URL}
    code = apply_0010.main(_argv("rehearse", tmp_path, wheelhouse="", confirm=""), environ=environ)
    assert code == 2 and database.connects == []
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert "production database secret" in report["detail"]


def test_the_rehearsal_is_isolated_when_given_the_wheelhouse(
    calls: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(_rehearsal_results())
    _install_driver(monkeypatch, database, calls)
    environ = {apply_0010.REHEARSAL_URL_VARIABLE: REHEARSAL_URL}
    code = apply_0010.main(_argv("rehearse", tmp_path, confirm=""), environ=environ)
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
        [sys.executable, "-B", apply_0010.SCRIPT, *_argv("apply", tmp_path, report=str(report))],
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
