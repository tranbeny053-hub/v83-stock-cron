"""The one-shot apply of migration 0008. No database is contacted.

Every database interaction runs against a fake driver that behaves like psycopg 3 where it matters
here: a connection used as a context manager commits on success and rolls back on an exception,
and a statement is recorded with the parameters it was given.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from crypto_probability_engine.runtime_isolation import REQUIRED_FLAGS_TEXT, ProvenanceRefused
from scripts import apply_migration_0008 as apply_0008

ROOT = Path(__file__).resolve().parents[2]
MIGRATION_BYTES = (ROOT / apply_0008.MIGRATION).read_bytes()
MIGRATION_SQL = MIGRATION_BYTES.decode("utf-8")
DATABASE_URL = "postgresql://owner:NEVER-SHOWN-SECRET@db.never-contacted.invalid:5432/postgres"
SHA = "d" * 40
REPOSITORY = "synthetic-owner/synthetic-repo"


# ------------------------------------------------------------------------ a psycopg-3-shaped fake


class FakeDatabase:
    def __init__(
        self, results: dict[str, list[tuple]], fail_on: dict[str, Exception] | None = None
    ):
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
        self.rows: list[tuple] = []

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

    def fetchone(self) -> tuple | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[tuple]:
        return list(self.rows)


HEALTHY_PRE = (0, 0, True, True, True, 3, True)


def healthy_results() -> dict[str, list[tuple]]:
    """What a first apply of the reviewed 0008 returns on Supabase Postgres."""

    return {
        apply_0008.PRECHECK_SQL: [HEALTHY_PRE],
        apply_0008.COLUMNS_SQL: [tuple(column) for column in apply_0008.EXPECTED_COLUMNS],
        apply_0008.CONSTRAINTS_SQL: [tuple(c) for c in apply_0008.EXPECTED_CONSTRAINTS],
        apply_0008.INDEXES_SQL: [
            (
                "analysis_run_details_pkey",
                "CREATE UNIQUE INDEX analysis_run_details_pkey ON public.analysis_run_details "
                "USING btree (run_id)",
            ),
            (
                "idx_analysis_run_details_created_at",
                "CREATE INDEX idx_analysis_run_details_created_at ON public.analysis_run_details "
                "USING btree (created_at DESC)",
            ),
        ],
        apply_0008.SECURITY_SQL: [apply_0008.EXPECTED_SECURITY],
        apply_0008.ROWS_SQL: [(0,)],
        apply_0008.SEAL_SQL: [(True,)],
    }


EXPECTED_ORDER = [
    *apply_0008.TIMEOUT_STATEMENTS,
    apply_0008.ADVISORY_LOCK_SQL,
    apply_0008.PRECHECK_SQL,
    MIGRATION_SQL,
    apply_0008.COLUMNS_SQL,
    apply_0008.CONSTRAINTS_SQL,
    apply_0008.INDEXES_SQL,
    apply_0008.SECURITY_SQL,
    apply_0008.ROWS_SQL,
    apply_0008.SEAL_SQL,
]


def _apply(database: FakeDatabase) -> tuple[dict[str, Any], dict[str, Any]]:
    captured: dict[str, Any] = {}
    outcome = apply_0008.apply_in_one_transaction(
        lambda: database.connect(DATABASE_URL), MIGRATION_SQL, captured
    )
    return outcome, captured


# --------------------------------------------------------------------------- the contract


def test_the_script_imports_only_the_standard_library_at_module_level() -> None:
    tree = ast.parse((ROOT / apply_0008.SCRIPT).read_text(encoding="utf-8"))
    imported = {
        (node.module if isinstance(node, ast.ImportFrom) else alias.name).split(".")[0]
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in (node.names if isinstance(node, ast.Import) else [None])
    }
    assert imported and all(
        name == "__future__" or name in sys.stdlib_module_names for name in imported
    ), imported


def test_it_names_itself_the_workflow_that_runs_it_and_the_reviewed_bytes() -> None:
    assert (ROOT / apply_0008.SCRIPT).resolve() == Path(apply_0008.__file__).resolve()
    assert (ROOT / apply_0008.WORKFLOW).is_file()
    assert hashlib.sha256(MIGRATION_BYTES).hexdigest() == apply_0008.MIGRATION_SHA256
    assert apply_0008.CONFIRMATION == "APPLY-MIGRATION-0008-ONCE"


def test_it_is_not_bound_to_the_section_5a_seal() -> None:
    assert apply_0008.ADVISORY_LOCK_SQL != "SELECT pg_advisory_xact_lock(5009005)"
    assert "0009" not in apply_0008.MIGRATION


def test_every_post_check_reads_the_public_table_and_no_query_takes_parameters() -> None:
    for query in (apply_0008.CONSTRAINTS_SQL, apply_0008.SECURITY_SQL, apply_0008.ROWS_SQL):
        assert "public.analysis_run_details" in query
    assert "table_schema = 'public'" in apply_0008.COLUMNS_SQL
    assert "schemaname = 'public'" in apply_0008.INDEXES_SQL
    checks = [statement for statement in EXPECTED_ORDER if statement is not MIGRATION_SQL]
    assert "%" not in "".join(checks)


def test_the_security_check_covers_every_role_and_every_privilege() -> None:
    every = "'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER'"
    for role in ("anon", "authenticated"):
        assert f"has_table_privilege('{role}', c.oid, {every})" in apply_0008.SECURITY_SQL
    for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
        assert (
            f"has_table_privilege('service_role', c.oid, '{privilege}')" in apply_0008.SECURITY_SQL
        )
    assert "acl.grantee = 0" in apply_0008.SECURITY_SQL, "PUBLIC is grantee 0"
    assert len(apply_0008.SECURITY_FIELDS) == len(apply_0008.EXPECTED_SECURITY) == 13
    expected = dict(zip(apply_0008.SECURITY_FIELDS, apply_0008.EXPECTED_SECURITY, strict=True))
    granted = [name for name, held in expected.items() if name.startswith("service_role") and held]
    assert granted == [
        "service_role_has_select",
        "service_role_has_insert",
        "service_role_has_update",
    ]


# --------------------------------------------------------------------------- the one transaction


def test_a_first_apply_runs_every_check_in_one_committed_transaction() -> None:
    database = FakeDatabase(healthy_results())
    outcome, captured = _apply(database)

    assert database.executed() == EXPECTED_ORDER
    assert all(params is None for _, params in database.statements), "no statement has parameters"
    assert database.commits == 1 and database.rollbacks == 0
    assert outcome["outcome"] == "APPLIED" and outcome["committed"] is True
    assert outcome["executed_migration_sha256"] == apply_0008.MIGRATION_SHA256
    assert captured["pre_checks"] == dict(zip(apply_0008.PRECHECK_FIELDS, HEALTHY_PRE, strict=True))
    assert captured["post_checks"]["security"]["service_role_has_delete"] is False
    assert captured["committed"] is True


def test_the_migration_statement_is_exactly_the_file() -> None:
    database = FakeDatabase(healthy_results())
    _apply(database)
    (executed,) = [s for s in database.executed() if "CREATE TABLE" in s]
    assert executed.encode("utf-8") == MIGRATION_BYTES


PRE_CHECK_DIFFERENCES = {
    "table-exists-somewhere": (1, 0, True, True, True, 3, True),
    "index-name-taken": (0, 1, True, True, True, 3, True),
    "already-applied": (2, 1, True, True, True, 3, True),
    "no-analysis-runs": (0, 0, False, True, True, 3, True),
    "no-predictions": (0, 0, True, False, True, 3, True),
    "no-prediction-origin": (0, 0, True, True, False, 3, True),
    "missing-api-role": (0, 0, True, True, True, 2, True),
    "seal-not-observed": (0, 0, True, True, True, 3, None),
}


@pytest.mark.parametrize("difference", sorted(PRE_CHECK_DIFFERENCES))
def test_a_database_not_ready_for_a_first_apply_refuses_before_the_migration(
    difference: str,
) -> None:
    database = FakeDatabase(
        {**healthy_results(), apply_0008.PRECHECK_SQL: [PRE_CHECK_DIFFERENCES[difference]]}
    )
    with pytest.raises(ProvenanceRefused, match="nothing is applied"):
        _apply(database)
    assert MIGRATION_SQL not in database.executed()
    assert database.executed()[-1] == apply_0008.PRECHECK_SQL
    assert database.commits == 0 and database.rollbacks == 1


def _security(**changes: bool) -> list[tuple]:
    values = dict(zip(apply_0008.SECURITY_FIELDS, apply_0008.EXPECTED_SECURITY, strict=True))
    values.update(changes)
    return [tuple(values[field] for field in apply_0008.SECURITY_FIELDS)]


_COLUMNS = [tuple(c) for c in apply_0008.EXPECTED_COLUMNS]
_INDEXES = healthy_results()[apply_0008.INDEXES_SQL]
POST_CHECK_DIFFERENCES = {
    "missing-column": (apply_0008.COLUMNS_SQL, _COLUMNS[:-1]),
    "extra-column": (apply_0008.COLUMNS_SQL, [*_COLUMNS, ("note", "text", "YES", None)]),
    "nullable-payload": (
        apply_0008.COLUMNS_SQL,
        [
            ("detail_payload", "jsonb", "YES", None) if c[0] == "detail_payload" else c
            for c in _COLUMNS
        ],
    ),
    "no-created-default": (
        apply_0008.COLUMNS_SQL,
        [c[:3] + (None,) if c[0] == "created_at" else c for c in _COLUMNS],
    ),
    "no-primary-key": (apply_0008.CONSTRAINTS_SQL, []),
    "a-foreign-key": (
        apply_0008.CONSTRAINTS_SQL,
        [
            *apply_0008.EXPECTED_CONSTRAINTS,
            ("analysis_run_details_run_id_fkey", "f", "FOREIGN KEY (run_id)"),
        ],
    ),
    "missing-created-index": (apply_0008.INDEXES_SQL, _INDEXES[:1]),
    "ascending-created-index": (
        apply_0008.INDEXES_SQL,
        [_INDEXES[0], (_INDEXES[1][0], _INDEXES[1][1].replace(" DESC", ""))],
    ),
    "rls-off": (apply_0008.SECURITY_SQL, _security(row_level_security=False)),
    "rls-forced": (apply_0008.SECURITY_SQL, _security(row_level_security_forced=True)),
    "not-owner": (apply_0008.SECURITY_SQL, _security(owned_by_applying_role=False)),
    "anon-privilege": (apply_0008.SECURITY_SQL, _security(anon_has_a_privilege=True)),
    "authenticated-privilege": (
        apply_0008.SECURITY_SQL,
        _security(authenticated_has_a_privilege=True),
    ),
    "public-privilege": (apply_0008.SECURITY_SQL, _security(public_has_a_privilege=True)),
    "service-role-cannot-read": (apply_0008.SECURITY_SQL, _security(service_role_has_select=False)),
    "service-role-cannot-upsert": (
        apply_0008.SECURITY_SQL,
        _security(service_role_has_update=False),
    ),
    "service-role-can-delete": (apply_0008.SECURITY_SQL, _security(service_role_has_delete=True)),
    "service-role-can-truncate": (
        apply_0008.SECURITY_SQL,
        _security(service_role_has_truncate=True),
    ),
    "a-row-exists": (apply_0008.ROWS_SQL, [(1,)]),
    "seal-changed": (apply_0008.SEAL_SQL, [(False,)]),
    "security-row-missing": (apply_0008.SECURITY_SQL, []),
}


@pytest.mark.parametrize("difference", sorted(POST_CHECK_DIFFERENCES))
def test_any_difference_from_the_reviewed_schema_rolls_the_apply_back(difference: str) -> None:
    query, rows = POST_CHECK_DIFFERENCES[difference]
    database = FakeDatabase({**healthy_results(), query: rows})
    captured: dict[str, Any] = {}
    with pytest.raises(ProvenanceRefused, match="nothing is applied"):
        apply_0008.apply_in_one_transaction(
            lambda: database.connect(DATABASE_URL), MIGRATION_SQL, captured
        )
    assert MIGRATION_SQL in database.executed(), "the difference is seen only after applying"
    assert database.commits == 0 and database.rollbacks == 1
    assert "committed" not in captured


def test_a_driver_error_mid_apply_rolls_back() -> None:
    database = FakeDatabase(healthy_results(), fail_on={MIGRATION_SQL: RuntimeError("boom")})
    with pytest.raises(RuntimeError):
        _apply(database)
    assert database.commits == 0 and database.rollbacks == 1


def test_the_checks_name_every_difference_not_only_the_first() -> None:
    assert len(apply_0008.pre_check_failures(dict.fromkeys(apply_0008.PRECHECK_FIELDS))) == 7
    healthy_pre = dict(zip(apply_0008.PRECHECK_FIELDS, HEALTHY_PRE, strict=True))
    assert apply_0008.pre_check_failures(healthy_pre) == []
    post = {
        "columns": [],
        "constraints": [],
        "indexes": [],
        "security": dict.fromkeys(apply_0008.SECURITY_FIELDS, None),
        "rows": 3,
        "section_5a_seal_present": False,
    }
    assert len(apply_0008.post_check_failures(healthy_pre, post)) == 3 + 13 + 2


# --------------------------------------------------------------------------- the dispatch


def _dispatch(**changes: str) -> dict[str, str]:
    values = {
        "github_actions": "true",
        "event_name": "workflow_dispatch",
        "repository": REPOSITORY,
        "workflow_ref": f"{REPOSITORY}/{apply_0008.WORKFLOW}@refs/heads/main",
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
    record = apply_0008.verify_dispatch(_dispatch(), _runtime(), expected_sha=SHA)
    assert record["dispatch_verified"] is True
    assert record["workflow"] == apply_0008.WORKFLOW
    assert record["expected_sha"] == record["sha"] == record["git_head"] == SHA


DISPATCH_REFUSALS = {
    "not-actions": (_dispatch(github_actions=""), _runtime(), SHA),
    "push-event": (_dispatch(event_name="push"), _runtime(), SHA),
    "other-branch": (_dispatch(ref="refs/heads/feature"), _runtime(), SHA),
    "the-seal-workflow": (
        _dispatch(
            workflow_ref=f"{REPOSITORY}/.github/workflows/section-5a-apply-seal-migration.yml"
            "@refs/heads/main"
        ),
        _runtime(),
        SHA,
    ),
    "workflow-from-a-branch": (
        _dispatch(workflow_ref=f"{REPOSITORY}/{apply_0008.WORKFLOW}@refs/heads/feature"),
        _runtime(),
        SHA,
    ),
    "other-repository-workflow": (
        _dispatch(workflow_ref=f"attacker/fork/{apply_0008.WORKFLOW}@refs/heads/main"),
        _runtime(),
        SHA,
    ),
    "short-sha": (_dispatch(sha=SHA[:7]), _runtime(git_head=SHA[:7]), SHA[:7]),
    "uppercase-sha": (_dispatch(sha=SHA.upper()), _runtime(git_head=SHA.upper()), SHA.upper()),
    "dispatched-other-commit": (_dispatch(sha="f" * 40), _runtime(), SHA),
    "checked-out-other-commit": (_dispatch(), _runtime(git_head="f" * 40), SHA),
    "dirty-tree": (_dispatch(), _runtime(tracked_tree_clean=False), SHA),
    "unknown-tree": (_dispatch(), _runtime(tracked_tree_clean=None), SHA),
    "other-python": (_dispatch(), _runtime(python_version="3.13.13"), SHA),
    "not-isolated": (_dispatch(), _runtime(interpreter_flags=""), SHA),
    "unverified-install": (_dispatch(), _runtime(installed_files_sha256=""), SHA),
    "bad-run-id": (_dispatch(run_id="x"), _runtime(), SHA),
    "bad-attempt": (_dispatch(run_attempt=""), _runtime(), SHA),
}


@pytest.mark.parametrize("case", sorted(DISPATCH_REFUSALS))
def test_every_dispatch_deviation_refuses(case: str) -> None:
    dispatch, runtime, expected = DISPATCH_REFUSALS[case]
    with pytest.raises(ProvenanceRefused, match="dispatch does not verify"):
        apply_0008.verify_dispatch(dispatch, runtime, expected_sha=expected)


def test_a_dispatch_refusal_names_every_failed_check() -> None:
    with pytest.raises(ProvenanceRefused) as refused:
        apply_0008.verify_dispatch(
            _dispatch(event_name="push", ref="refs/heads/x"),
            _runtime(tracked_tree_clean=False),
            expected_sha=SHA,
        )
    message = str(refused.value)
    assert "workflow_dispatch" in message and "refs/heads/main" in message
    assert "tracked files differ" in message


def test_different_migration_bytes_refuse_before_any_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(apply_0008, "MIGRATION_SHA256", "0" * 64)
    with pytest.raises(ProvenanceRefused, match="not the reviewed"):
        apply_0008.migration_bytes()


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
        return {"dispatch_verified": True, "workflow": apply_0008.WORKFLOW}

    monkeypatch.setattr(apply_0008, "enter_isolated_runtime", _enter)
    monkeypatch.setattr(apply_0008, "attest_dispatch", _attest)
    monkeypatch.setattr(
        apply_0008, "attest_loaded_modules", lambda isolation: events.append("modules")
    )
    return events


def _argv(mode: str, tmp_path: Path, **overrides: str) -> list[str]:
    options = {
        "mode": mode,
        "expected-sha": SHA,
        "confirm": apply_0008.CONFIRMATION,
        "wheelhouse": "/synthetic/runner-temp/section-5a-wheels",
        "report": str(tmp_path / "report.json"),
        **overrides,
    }
    return [f"--{name}={value}" for name, value in options.items()]


def _install_driver(monkeypatch: pytest.MonkeyPatch, database: FakeDatabase, events: list[str]):
    def _load():
        events.append("driver")
        return database

    monkeypatch.setattr(apply_0008, "load_driver", _load)


def test_apply_refuses_without_the_exact_token_before_anything_is_entered(
    calls: list[str], tmp_path: Path
) -> None:
    for token in (
        "",
        "apply",
        apply_0008.CONFIRMATION.lower(),
        apply_0008.CONFIRMATION + " ",
        "APPLY-SECTION-5A-SEAL-MIGRATION-ONCE",
    ):
        assert apply_0008.main(_argv("apply", tmp_path, confirm=token), environ={}) == 2
    assert calls == []
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["outcome"] == "REFUSED" and report["committed"] is False
    assert apply_0008.CONFIRMATION in report["detail"]


def test_attest_mode_touches_no_database(
    calls: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(healthy_results())
    _install_driver(monkeypatch, database, calls)
    code = apply_0008.main(
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
    assert set(report["driver_helpers"]) <= {"_cython_3_2_4", "cython_runtime"}
    assert report["migration_sha256"] == apply_0008.MIGRATION_SHA256


def test_apply_without_a_database_url_refuses_before_the_driver_loads(
    calls: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(healthy_results())
    _install_driver(monkeypatch, database, calls)
    assert apply_0008.main(_argv("apply", tmp_path), environ={}) == 2
    assert "driver" not in calls and database.connects == []


def test_a_full_apply_verifies_the_driver_before_connecting_and_reports_raw_results(
    calls: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = FakeDatabase(healthy_results())
    _install_driver(monkeypatch, database, calls)
    original_connect = database.connect

    def _connect(url: str, **options: Any):
        calls.append("connect")
        return original_connect(url, **options)

    database.connect = _connect  # type: ignore[method-assign]
    code = apply_0008.main(_argv("apply", tmp_path), environ={"SUPABASE_DB_URL": DATABASE_URL})
    assert code == 0
    assert calls == [
        "enter:/synthetic/runner-temp/section-5a-wheels",
        f"attest:{SHA}",
        "modules",
        "driver",
        "modules",
        "connect",
    ]
    assert database.connects == [(DATABASE_URL, {"connect_timeout": 8})]
    assert database.commits == 1
    report_text = (tmp_path / "report.json").read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert report["outcome"] == "APPLIED" and report["mode"] == "apply"
    assert report["executed_migration_sha256"] == report["migration_sha256"]
    streams = capsys.readouterr()
    for text in (report_text, streams.out, streams.err):
        assert "NEVER-SHOWN-SECRET" not in text and "never-contacted" not in text


def test_a_refused_apply_reports_what_it_saw_and_commits_nothing(
    calls: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(
        {**healthy_results(), apply_0008.PRECHECK_SQL: [(1, 0, True, True, True, 3, True)]}
    )
    _install_driver(monkeypatch, database, calls)
    code = apply_0008.main(_argv("apply", tmp_path), environ={"SUPABASE_DB_URL": DATABASE_URL})
    assert code == 2
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["outcome"] == "REFUSED" and report["committed"] is False
    assert report["captured"]["pre_checks"]["analysis_run_details_relations_in_any_schema"] == 1
    assert database.commits == 0


def test_an_unexpected_failure_withholds_its_message_because_it_can_name_the_host(
    calls: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    error = RuntimeError(f"connection to server at {DATABASE_URL} failed")
    database = FakeDatabase(healthy_results(), fail_on={apply_0008.PRECHECK_SQL: error})
    _install_driver(monkeypatch, database, calls)
    code = apply_0008.main(_argv("apply", tmp_path), environ={"SUPABASE_DB_URL": DATABASE_URL})
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
    apply_0008.attest_loaded_modules("isolation")
    assert seen["pinned"] == (*pinned_files(ROOT), apply_0008.SCRIPT)
    assert Path(seen["root"]).resolve() == ROOT


def _scrubbed_environment(extra: dict[str, str]) -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GITHUB_", "RUNNER_", "SUPABASE_", "PYTHON")) and key != "ImageOS"
    }
    environment.update(extra)
    return environment


def test_an_unisolated_process_refuses_before_any_database_access(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            apply_0008.SCRIPT,
            *_argv("apply", tmp_path, report=str(report)),
        ],
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
