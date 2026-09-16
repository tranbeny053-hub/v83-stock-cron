"""The one-shot apply of migration 0009 (owner rulings K1=A, K2=A). No database is contacted.

Every database interaction runs against a fake driver that behaves like psycopg 3 where it matters
here: a connection used as a context manager commits on success and rolls back on an exception,
and a statement is recorded with the parameters it was given.
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

from crypto_probability_engine.oos.evaluation import provenance
from crypto_probability_engine.runtime_isolation import ProvenanceRefused
from scripts import apply_section_5a_seal as seal

ROOT = Path(__file__).resolve().parents[2]
MIGRATION_BYTES = (ROOT / seal.MIGRATION).read_bytes()
MIGRATION_SQL = MIGRATION_BYTES.decode("utf-8")
DATABASE_URL = "postgresql://owner:NEVER-SHOWN-SECRET@db.never-contacted.invalid:5432/postgres"
SHA = "c" * 40


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


def healthy_results() -> dict[str, list[tuple]]:
    """What a first apply of the reviewed 0009 returns on Supabase Postgres."""

    return {
        seal.PRECHECK_SQL: [(0, 0, 0, False)],
        seal.COLUMNS_SQL: [tuple(column) for column in seal.EXPECTED_COLUMNS],
        seal.CONSTRAINTS_SQL: [
            ("section_5a_captured_is_complete", "c"),
            ("section_5a_claim_has_verified_provenance", "c"),
            ("section_5a_claimed_has_no_snapshot", "c"),
            ("section_5a_evaluation_seal_pkey", "p"),
            ("section_5a_evaluation_seal_seal_id_check", "c"),
            ("section_5a_evaluation_seal_state_check", "c"),
        ],
        seal.TRIGGERS_SQL: [("section_5a_seal_guard",), ("section_5a_seal_truncate_guard",)],
        seal.SECURITY_SQL: [seal.EXPECTED_SECURITY],
        seal.ROWS_SQL: [(0,)],
        seal.ANALYSIS_RUN_DETAILS_SQL: [(False,)],
    }


EXPECTED_ORDER = [
    *seal.TIMEOUT_STATEMENTS,
    seal.ADVISORY_LOCK_SQL,
    seal.PRECHECK_SQL,
    MIGRATION_SQL,
    seal.COLUMNS_SQL,
    seal.CONSTRAINTS_SQL,
    seal.TRIGGERS_SQL,
    seal.SECURITY_SQL,
    seal.ROWS_SQL,
    seal.ANALYSIS_RUN_DETAILS_SQL,
]


def _apply(database: FakeDatabase) -> tuple[dict[str, Any], dict[str, Any]]:
    captured: dict[str, Any] = {}
    outcome = seal.apply_in_one_transaction(
        lambda: database.connect(DATABASE_URL), MIGRATION_SQL, captured
    )
    return outcome, captured


# --------------------------------------------------------------------------- the contract


def test_the_script_imports_only_the_standard_library_at_module_level() -> None:
    tree = ast.parse((ROOT / seal.SCRIPT).read_text(encoding="utf-8"))
    imported = {
        (node.module if isinstance(node, ast.ImportFrom) else alias.name).split(".")[0]
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in (node.names if isinstance(node, ast.Import) else [None])
    }
    assert imported and all(
        name == "__future__" or name in sys.stdlib_module_names for name in imported
    ), imported


def test_it_names_itself_and_the_workflow_that_runs_it() -> None:
    assert (ROOT / seal.SCRIPT).resolve() == Path(seal.__file__).resolve()
    assert (ROOT / provenance.SEAL_MIGRATION_WORKFLOW).is_file()
    assert provenance.SEAL_MIGRATION_WORKFLOW in (ROOT / seal.SCRIPT).read_text(encoding="utf-8")


def test_the_expected_columns_are_exactly_the_migration_s() -> None:
    """The post-check cannot drift from the DDL: both are read from one place and compared."""

    opening = "CREATE TABLE IF NOT EXISTS public.section_5a_evaluation_seal ("
    body = MIGRATION_SQL.split(opening, 1)[1]
    body = body.split("CONSTRAINT", 1)[0]
    types = {"TEXT": "text", "TIMESTAMPTZ": "timestamp with time zone", "JSONB": "jsonb"}
    columns = []
    for line in body.splitlines():
        code = line.split("--", 1)[0].strip()
        match = re.match(r"^([a-z_0-9]+)\s+(TEXT|TIMESTAMPTZ|JSONB)\b(.*)$", code)
        if match:
            name, kind, rest = match.groups()
            required = "NOT NULL" in rest or "PRIMARY KEY" in rest
            columns.append((name, types[kind], "NO" if required else "YES"))
    assert columns == list(seal.EXPECTED_COLUMNS)


def test_the_required_constraints_and_triggers_are_the_migration_s() -> None:
    flat = " ".join(MIGRATION_SQL.split())
    for name in seal.REQUIRED_CHECK_CONSTRAINTS:
        assert f"CONSTRAINT {name} CHECK" in flat, name
    for name in seal.EXPECTED_TRIGGERS:
        assert f"CREATE TRIGGER {name}" in flat, name


def test_every_post_check_reads_the_public_table_and_no_query_takes_parameters() -> None:
    for query in (seal.CONSTRAINTS_SQL, seal.TRIGGERS_SQL, seal.SECURITY_SQL, seal.ROWS_SQL):
        assert "public.section_5a_evaluation_seal" in query
    assert "table_schema = 'public'" in seal.COLUMNS_SQL
    checks = [statement for statement in EXPECTED_ORDER if statement is not MIGRATION_SQL]
    assert len(checks) == len(EXPECTED_ORDER) - 1 and "%" not in "".join(checks)


def test_every_api_role_is_checked_for_every_privilege() -> None:
    for role in ("anon", "authenticated", "service_role"):
        assert (
            f"has_table_privilege('{role}', c.oid, "
            "'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')"
        ) in seal.SECURITY_SQL
    assert "acl.grantee = 0" in seal.SECURITY_SQL, "PUBLIC is grantee 0"
    assert len(seal.SECURITY_FIELDS) == len(seal.EXPECTED_SECURITY) == 7


# --------------------------------------------------------------------------- the one transaction


def test_a_first_apply_runs_every_check_in_one_committed_transaction() -> None:
    database = FakeDatabase(healthy_results())
    outcome, captured = _apply(database)

    assert database.executed() == EXPECTED_ORDER
    assert all(params is None for _, params in database.statements), "no statement has parameters"
    assert database.commits == 1 and database.rollbacks == 0
    assert database.connects == [(DATABASE_URL, {})]
    assert outcome["outcome"] == "APPLIED" and outcome["committed"] is True
    assert outcome["executed_migration_sha256"] == hashlib.sha256(MIGRATION_BYTES).hexdigest()
    assert captured["pre_checks"] == {
        "seal_tables_in_any_schema": 0,
        "guard_functions_in_any_schema": 0,
        "guard_triggers_in_any_schema": 0,
        "analysis_run_details_present": False,
    }
    assert captured["post_checks"]["security"]["row_level_security"] is True
    assert captured["committed"] is True


def test_the_migration_statement_is_exactly_the_file() -> None:
    database = FakeDatabase(healthy_results())
    _apply(database)
    (executed,) = [s for s in database.executed() if "CREATE TABLE" in s]
    assert executed.encode("utf-8") == MIGRATION_BYTES
    assert "0008" not in " ".join(s for s in database.executed() if s is not executed)
    assert not any("analysis_run_details (" in statement for statement in database.executed())


@pytest.mark.parametrize(
    "pre",
    [(1, 0, 0, False), (0, 1, 0, False), (0, 0, 1, False), (1, 2, 2, True)],
    ids=["stale-table", "guard-function", "guard-trigger", "already-applied"],
)
def test_existing_seal_objects_refuse_before_the_migration_runs(pre: tuple) -> None:
    """F-0009-C, and the one-shot property: a second apply stops here."""

    database = FakeDatabase({**healthy_results(), seal.PRECHECK_SQL: [pre]})
    with pytest.raises(ProvenanceRefused, match="F-0009-C"):
        _apply(database)
    assert MIGRATION_SQL not in database.executed()
    assert database.executed()[-1] == seal.PRECHECK_SQL
    assert database.commits == 0 and database.rollbacks == 1


def _mutate(results: dict[str, list[tuple]], query: str, rows: list[tuple]) -> None:
    results[query] = rows


POST_CHECK_DIFFERENCES = {
    "missing-column": (seal.COLUMNS_SQL, [tuple(c) for c in seal.EXPECTED_COLUMNS[:-1]]),
    "extra-column": (
        seal.COLUMNS_SQL,
        [*(tuple(c) for c in seal.EXPECTED_COLUMNS), ("note", "text", "YES")],
    ),
    "nullable-provenance": (
        seal.COLUMNS_SQL,
        [
            ("run_provenance", "jsonb", "YES") if c[0] == "run_provenance" else tuple(c)
            for c in seal.EXPECTED_COLUMNS
        ],
    ),
    "missing-provenance-check": (
        seal.CONSTRAINTS_SQL,
        [("section_5a_captured_is_complete", "c"), ("section_5a_evaluation_seal_pkey", "p")],
    ),
    "no-primary-key": (
        seal.CONSTRAINTS_SQL,
        [(name, "c") for name in seal.REQUIRED_CHECK_CONSTRAINTS],
    ),
    "missing-truncate-guard": (seal.TRIGGERS_SQL, [("section_5a_seal_guard",)]),
    "extra-trigger": (
        seal.TRIGGERS_SQL,
        [("section_5a_seal_guard",), ("section_5a_seal_truncate_guard",), ("x",)],
    ),
    "rls-off": (seal.SECURITY_SQL, [(False, False, True, False, False, False, False)]),
    "rls-forced": (seal.SECURITY_SQL, [(True, True, True, False, False, False, False)]),
    "not-owner": (seal.SECURITY_SQL, [(True, False, False, False, False, False, False)]),
    "anon-privilege": (seal.SECURITY_SQL, [(True, False, True, True, False, False, False)]),
    "authenticated-privilege": (
        seal.SECURITY_SQL,
        [(True, False, True, False, True, False, False)],
    ),
    "service-role-privilege": (
        seal.SECURITY_SQL,
        [(True, False, True, False, False, True, False)],
    ),
    "public-privilege": (seal.SECURITY_SQL, [(True, False, True, False, False, False, True)]),
    "a-row-exists": (seal.ROWS_SQL, [(1,)]),
    "0008-changed": (seal.ANALYSIS_RUN_DETAILS_SQL, [(True,)]),
    "security-row-missing": (seal.SECURITY_SQL, []),
}


@pytest.mark.parametrize("difference", sorted(POST_CHECK_DIFFERENCES))
def test_any_difference_from_the_reviewed_schema_rolls_the_apply_back(difference: str) -> None:
    query, rows = POST_CHECK_DIFFERENCES[difference]
    results = healthy_results()
    _mutate(results, query, rows)
    database = FakeDatabase(results)
    captured: dict[str, Any] = {}
    with pytest.raises(ProvenanceRefused, match="nothing is applied"):
        seal.apply_in_one_transaction(
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


def test_the_post_check_names_every_difference_not_only_the_first() -> None:
    pre = {"analysis_run_details_present": False}
    post = {
        "columns": [],
        "constraints": [],
        "triggers": [],
        "security": dict(zip(seal.SECURITY_FIELDS, (False,) * 7, strict=True)),
        "rows": 3,
        "analysis_run_details_present": True,
    }
    failures = seal.post_check_failures(pre, post)
    assert len(failures) >= 8, failures
    assert seal.post_check_failures(
        pre,
        {
            "columns": [list(c) for c in seal.EXPECTED_COLUMNS],
            "constraints": [[n, k] for n, k in healthy_results()[seal.CONSTRAINTS_SQL]],
            "triggers": list(seal.EXPECTED_TRIGGERS),
            "security": dict(zip(seal.SECURITY_FIELDS, seal.EXPECTED_SECURITY, strict=True)),
            "rows": 0,
            "analysis_run_details_present": False,
        },
    ) == []


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
        return {"dispatch_verified": True, "workflow_ref": "synthetic"}

    monkeypatch.setattr(seal, "enter_isolated_runtime", _enter)
    monkeypatch.setattr(seal, "attest_dispatch", _attest)
    monkeypatch.setattr(seal, "attest_loaded_modules", lambda isolation: events.append("modules"))
    return events


def _argv(mode: str, tmp_path: Path, **overrides: str) -> list[str]:
    options = {
        "mode": mode,
        "expected-sha": SHA,
        "confirm": seal.CONFIRMATION,
        "wheelhouse": "/synthetic/runner-temp/section-5a-wheels",
        "report": str(tmp_path / "report.json"),
        **overrides,
    }
    return [f"--{name}={value}" for name, value in options.items()]


def _install_driver(monkeypatch: pytest.MonkeyPatch, database: FakeDatabase, events: list[str]):
    def _load():
        events.append("driver")
        return database

    monkeypatch.setattr(seal, "load_driver", _load)


def test_apply_refuses_without_the_exact_token_before_anything_is_entered(
    calls: list[str], tmp_path: Path
) -> None:
    for token in ("", "apply", seal.CONFIRMATION.lower(), seal.CONFIRMATION + " "):
        code = seal.main(_argv("apply", tmp_path, confirm=token), environ={})
        assert code == 2
    assert calls == []
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["outcome"] == "REFUSED" and report["committed"] is False
    assert seal.CONFIRMATION in report["detail"]


def test_attest_mode_touches_no_database(
    calls: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(healthy_results())
    _install_driver(monkeypatch, database, calls)
    code = seal.main(
        _argv("attest", tmp_path, confirm=""), environ={"SUPABASE_DB_URL": DATABASE_URL}
    )
    assert code == 0
    # L1b: the secret-free attest step loads the driver WITHOUT connecting, then attests again.
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
    assert report["migration_sha256"] == hashlib.sha256(MIGRATION_BYTES).hexdigest()


def test_apply_without_a_database_url_refuses_before_the_driver_loads(
    calls: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(healthy_results())
    _install_driver(monkeypatch, database, calls)
    assert seal.main(_argv("apply", tmp_path), environ={}) == 2
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
    code = seal.main(_argv("apply", tmp_path), environ={"SUPABASE_DB_URL": DATABASE_URL})
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
    assert report["post_checks"]["triggers"] == list(seal.EXPECTED_TRIGGERS)
    streams = capsys.readouterr()
    for text in (report_text, streams.out, streams.err):
        assert "NEVER-SHOWN-SECRET" not in text and "never-contacted" not in text


def test_a_refused_apply_reports_what_it_saw_and_commits_nothing(
    calls: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase({**healthy_results(), seal.PRECHECK_SQL: [(1, 2, 2, False)]})
    _install_driver(monkeypatch, database, calls)
    assert seal.main(_argv("apply", tmp_path), environ={"SUPABASE_DB_URL": DATABASE_URL}) == 2
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["outcome"] == "REFUSED" and report["committed"] is False
    assert report["captured"]["pre_checks"]["seal_tables_in_any_schema"] == 1
    assert database.commits == 0


def test_an_unexpected_failure_withholds_its_message_because_it_can_name_the_host(
    calls: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    error = RuntimeError(f"connection to server at {DATABASE_URL} failed")
    database = FakeDatabase(healthy_results(), fail_on={seal.PRECHECK_SQL: error})
    _install_driver(monkeypatch, database, calls)
    assert seal.main(_argv("apply", tmp_path), environ={"SUPABASE_DB_URL": DATABASE_URL}) == 1
    report_text = (tmp_path / "report.json").read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert report["outcome"] == "FAILED" and report["error_type"] == "RuntimeError"
    streams = capsys.readouterr()
    for text in (report_text, streams.out, streams.err):
        assert "NEVER-SHOWN-SECRET" not in text and "never-contacted" not in text
    assert database.rollbacks == 1 and database.commits == 0


def test_the_run_is_attested_as_the_seal_migration_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def _attest(expected_sha, **kwargs):
        seen.update(kwargs, expected_sha=expected_sha)
        return {}

    monkeypatch.setattr(provenance, "attest", _attest)
    seal.attest_dispatch(SHA, {"GITHUB_ACTIONS": "true"}, "isolation")
    assert seen["workflow"] == provenance.SEAL_MIGRATION_WORKFLOW
    assert seen["expected_sha"] == SHA and seen["isolation"] == "isolation"


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
    seal.attest_loaded_modules("isolation")
    assert seen["pinned"] == (*pinned_files(ROOT), seal.SCRIPT)
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
            seal.SCRIPT,
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
