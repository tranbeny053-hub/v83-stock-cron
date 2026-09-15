#!/usr/bin/env python
"""Apply migration 0008, durable sanitized Detail, ONCE.

    --mode attest   verify isolation, dispatch and runtime; touches no database
    --mode apply    THE ONE-SHOT APPLY; requires the confirmation token

Run only by ``.github/workflows/apply-migration-0008.yml``, as ``python -I -S -B``, inside the same
closed trust boundary the section 5A routes use: exact CPython 3.13.14, CPython's bundled pip, and
lock-authenticated wheels (pre-registration Addenda 5-7). The dispatch is verified HERE, against
THIS workflow, because the evaluator's provenance module is pinned and attests only its own two
workflows. A record this run produces verifies nowhere a section 5A look is claimed.

ONE TRANSACTION, FAIL CLOSED. Under bounded timeouts and an advisory lock:
  1. read-only PRE-CHECKS refuse unless no relation or index of 0008's names exists in ANY schema
     (``CREATE ... IF NOT EXISTS`` would otherwise keep a stale object), the tables the application
     joins exist, and the three Supabase API roles exist;
  2. exactly the pinned bytes of migration 0008 are executed, with no parameters;
  3. read-only POST-CHECKS refuse unless the table has exactly the reviewed columns, one primary
     key and no other constraint, exactly its two indexes; row-level security is on and not forced;
     the applying role owns it; PUBLIC, anon and authenticated hold no privilege; service_role holds
     exactly SELECT, INSERT and UPDATE; it holds zero rows; and the section 5A seal is untouched.
Any refusal or error rolls the transaction back, so nothing is applied; only then is it committed.
A second dispatch refuses at step 1, so the one-shot property is enforced by the database itself.

Every query result is captured raw, before it is judged, and written to ``--report`` on success
and on refusal alike. The database URL is never printed, logged or written. An unexpected failure
is reported by its type only, because driver messages can name the host.

THIS FILE IMPORTS ONLY THE STANDARD LIBRARY AT MODULE LEVEL, exactly like the evaluator CLI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
SCRIPT = "scripts/apply_migration_0008.py"
WORKFLOW = ".github/workflows/apply-migration-0008.yml"
MIGRATION = "migrations/0008_analysis_run_details.sql"
# The reviewed bytes. A different file on the dispatched commit refuses before any connection.
MIGRATION_SHA256 = "a8f290b3514bf087bfc2581e59cb837136a33c360faf68560d01cb439c32333d"
CONFIRMATION = "APPLY-MIGRATION-0008-ONCE"
REPORT_SCHEMA = "migration-0008-apply-report.v1"
DISPATCH_SCHEMA = "migration-0008-dispatch.v1"
MODE_ATTEST = "attest"
MODE_APPLY = "apply"
REQUIRED_EVENT = "workflow_dispatch"
REQUIRED_REF = "refs/heads/main"
# The owner repository, pinned. A fork's run carries a self-consistent identity of its own, and it
# must refuse here, although a fork is never handed this repository's secret (task-817, F-817-1).
EXPECTED_REPOSITORY = "tranbeny053-hub/v83-stock-cron"
PINNED_PYTHON = ("CPython", "3.13.14")

TIMEOUT_STATEMENTS = (
    "SET LOCAL lock_timeout = '10s'",
    "SET LOCAL statement_timeout = '120s'",
)
# A fixed key, distinct from 0009's: two appliers of 0008 serialize even outside the workflow.
ADVISORY_LOCK_SQL = "SELECT pg_advisory_xact_lock(5000008)"

API_ROLES = ("anon", "authenticated", "service_role")
PRECHECK_SQL = (
    "SELECT"
    " (SELECT count(*) FROM pg_catalog.pg_class WHERE relname = 'analysis_run_details'),"
    " (SELECT count(*) FROM pg_catalog.pg_class"
    " WHERE relname = 'idx_analysis_run_details_created_at'),"
    " to_regclass('public.analysis_runs') IS NOT NULL,"
    " to_regclass('public.predictions') IS NOT NULL,"
    " EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'"
    " AND table_name = 'predictions' AND column_name = 'prediction_origin'),"
    " (SELECT count(*) FROM pg_catalog.pg_roles"
    " WHERE rolname IN ('anon', 'authenticated', 'service_role')),"
    " to_regclass('public.section_5a_evaluation_seal') IS NOT NULL"
)
PRECHECK_FIELDS = (
    "analysis_run_details_relations_in_any_schema",
    "created_at_index_relations_in_any_schema",
    "analysis_runs_present",
    "predictions_present",
    "predictions_prediction_origin_present",
    "api_roles_present",
    "section_5a_seal_present",
)

COLUMNS_SQL = (
    "SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns"
    " WHERE table_schema = 'public' AND table_name = 'analysis_run_details'"
    " ORDER BY ordinal_position"
)
EXPECTED_COLUMNS = (
    ("run_id", "text", "NO", None),
    ("analysis_hash", "text", "YES", None),
    ("detail_payload", "jsonb", "NO", None),
    ("created_at", "timestamp with time zone", "NO", "now()"),
)

CONSTRAINTS_SQL = (
    "SELECT conname, contype, pg_catalog.pg_get_constraintdef(oid) FROM pg_catalog.pg_constraint"
    " WHERE conrelid = 'public.analysis_run_details'::regclass ORDER BY conname"
)
EXPECTED_CONSTRAINTS = (("analysis_run_details_pkey", "p", "PRIMARY KEY (run_id)"),)

INDEXES_SQL = (
    "SELECT indexname, indexdef FROM pg_catalog.pg_indexes"
    " WHERE schemaname = 'public' AND tablename = 'analysis_run_details' ORDER BY indexname"
)
EXPECTED_INDEX_SUFFIXES = (
    ("analysis_run_details_pkey", "USING btree (run_id)"),
    ("idx_analysis_run_details_created_at", "USING btree (created_at DESC)"),
)

_EVERY_TABLE_PRIVILEGE = "SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER"
SERVICE_ROLE_PRIVILEGES = (
    "SELECT",
    "INSERT",
    "UPDATE",
    "DELETE",
    "TRUNCATE",
    "REFERENCES",
    "TRIGGER",
)
SECURITY_SQL = (
    "SELECT c.relrowsecurity, c.relforcerowsecurity,"
    " pg_catalog.pg_get_userbyid(c.relowner) = current_user,"
    + "".join(
        f" has_table_privilege('{role}', c.oid, '{_EVERY_TABLE_PRIVILEGE}'),"
        for role in ("anon", "authenticated")
    )
    + " EXISTS (SELECT 1 FROM aclexplode(c.relacl) AS acl WHERE acl.grantee = 0),"
    + ",".join(
        f" has_table_privilege('service_role', c.oid, '{privilege}')"
        for privilege in SERVICE_ROLE_PRIVILEGES
    )
    + " FROM pg_catalog.pg_class AS c"
    " WHERE c.oid = 'public.analysis_run_details'::regclass"
)
SECURITY_FIELDS = (
    "row_level_security",
    "row_level_security_forced",
    "owned_by_applying_role",
    "anon_has_a_privilege",
    "authenticated_has_a_privilege",
    "public_has_a_privilege",
    *(f"service_role_has_{privilege.lower()}" for privilege in SERVICE_ROLE_PRIVILEGES),
)
EXPECTED_SECURITY = (
    True,
    False,
    True,
    False,
    False,
    False,
    True,  # SELECT
    True,  # INSERT
    True,  # UPDATE
    False,  # DELETE
    False,  # TRUNCATE
    False,  # REFERENCES
    False,  # TRIGGER
)

ROWS_SQL = "SELECT count(*) FROM public.analysis_run_details"
SEAL_SQL = "SELECT to_regclass('public.section_5a_evaluation_seal') IS NOT NULL"

_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DIGITS = re.compile(r"^[0-9]+$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=[MODE_ATTEST, MODE_APPLY], default=MODE_ATTEST)
    parser.add_argument(
        "--confirm", default="", help="required for --mode apply: the exact confirmation token"
    )
    parser.add_argument(
        "--expected-sha",
        default="",
        help="required: the full commit SHA on main that the owner reviewed and dispatched",
    )
    parser.add_argument(
        "--wheelhouse",
        default="",
        help="required: the directory of lock-authenticated wheels that were installed",
    )
    parser.add_argument(
        "--report", default=None, help="write this run's outcome, success or refusal, as JSON"
    )
    return parser


def ensure_source_path() -> None:
    """Make the first-party source importable, AFTER the interpreter's own library."""

    if str(SOURCE) not in sys.path:
        sys.path.append(str(SOURCE))


def enter_isolated_runtime(wheelhouse: str):
    """The isolated process and its authenticated import surface, verified first (J1=B)."""

    ensure_source_path()
    from crypto_probability_engine import runtime_isolation

    if not wheelhouse:
        raise _refusal("--wheelhouse is required; installed code is authenticated against it")
    return runtime_isolation.enter(ROOT, wheelhouse=Path(wheelhouse))


def observe(environ: Mapping[str, str], isolation) -> tuple[dict[str, str], dict[str, Any]]:
    """The dispatch facts GitHub sets, and this process's and checkout's. Nothing is judged."""

    from crypto_probability_engine import runtime_isolation

    dispatch = {
        field: str(environ.get(variable, ""))
        for field, variable in (
            ("github_actions", "GITHUB_ACTIONS"),
            ("event_name", "GITHUB_EVENT_NAME"),
            ("repository", "GITHUB_REPOSITORY"),
            ("workflow_ref", "GITHUB_WORKFLOW_REF"),
            ("ref", "GITHUB_REF"),
            ("sha", "GITHUB_SHA"),
            ("run_id", "GITHUB_RUN_ID"),
            ("run_attempt", "GITHUB_RUN_ATTEMPT"),
        )
    }
    status = _git("status", "--porcelain=v1", "--untracked-files=no")
    runtime = {
        "git_head": _git("rev-parse", "HEAD") or "",
        "tracked_tree_clean": status == "" if status is not None else None,
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "interpreter_flags": runtime_isolation.interpreter_flags(),
        "installed_files_sha256": getattr(isolation, "installed_files_sha256", ""),
    }
    return dispatch, runtime


def verify_dispatch(
    dispatch: Mapping[str, str], runtime: Mapping[str, Any], *, expected_sha: str
) -> dict[str, Any]:
    """Pure: this run is a manual dispatch of THIS workflow, on main, at exactly expected_sha.

    Refuses naming EVERY failed check. Mirrors the evaluator's dispatch checks for this workflow.
    """

    from crypto_probability_engine.runtime_isolation import REQUIRED_FLAGS_TEXT

    failures: list[str] = []

    def need(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    repository = str(dispatch.get("repository", ""))
    need(dispatch.get("github_actions") == "true", "not running inside GitHub Actions")
    need(
        repository == EXPECTED_REPOSITORY,
        f"repository is {repository!r}, not the owner repository {EXPECTED_REPOSITORY}",
    )
    need(
        dispatch.get("event_name") == REQUIRED_EVENT,
        f"event is {dispatch.get('event_name')!r}, not a manual {REQUIRED_EVENT}",
    )
    need(dispatch.get("ref") == REQUIRED_REF, f"ref is {dispatch.get('ref')!r}, not {REQUIRED_REF}")
    need(
        bool(_REPOSITORY.match(repository))
        and dispatch.get("workflow_ref") == f"{repository}/{WORKFLOW}@{REQUIRED_REF}",
        f"workflow is {dispatch.get('workflow_ref')!r}, not {WORKFLOW} on {REQUIRED_REF}",
    )
    sha_is_canonical = isinstance(expected_sha, str) and bool(_COMMIT_SHA.match(expected_sha))
    need(
        sha_is_canonical,
        "expected_sha must be the full 40-character lowercase commit SHA of the reviewed commit",
    )
    need(
        sha_is_canonical and dispatch.get("sha") == expected_sha,
        f"the dispatched commit {dispatch.get('sha')!r} is not expected_sha",
    )
    need(
        sha_is_canonical and runtime.get("git_head") == expected_sha,
        f"the checked-out commit {runtime.get('git_head')!r} is not expected_sha",
    )
    need(
        runtime.get("tracked_tree_clean") is True,
        "tracked files differ from the checked-out commit",
    )
    interpreter = (runtime.get("python_implementation"), runtime.get("python_version"))
    need(
        interpreter == PINNED_PYTHON,
        f"interpreter is {runtime.get('python_implementation')} {runtime.get('python_version')}, "
        f"not {PINNED_PYTHON[0]} {PINNED_PYTHON[1]}",
    )
    need(
        runtime.get("interpreter_flags") == REQUIRED_FLAGS_TEXT,
        f"the process did not start isolated (flags [{runtime.get('interpreter_flags')}])",
    )
    need(
        bool(_SHA256.match(str(runtime.get("installed_files_sha256", "")))),
        "the installed files were not verified against their records",
    )
    need(bool(_DIGITS.match(str(dispatch.get("run_id", "")))), "run_id is not a GitHub run id")
    need(bool(_DIGITS.match(str(dispatch.get("run_attempt", "")))), "run_attempt is not a number")
    if failures:
        raise _refusal("the dispatch does not verify: " + "; ".join(failures))
    return {
        "schema_version": DISPATCH_SCHEMA,
        "dispatch_verified": True,
        "workflow": WORKFLOW,
        "event_name": str(dispatch["event_name"]),
        "repository": repository,
        "workflow_ref": str(dispatch["workflow_ref"]),
        "ref": str(dispatch["ref"]),
        "sha": str(dispatch["sha"]),
        "expected_sha": expected_sha,
        "git_head": str(runtime["git_head"]),
        "run_id": str(dispatch["run_id"]),
        "run_attempt": str(dispatch["run_attempt"]),
        "python_version": str(runtime["python_version"]),
        "interpreter_flags": str(runtime["interpreter_flags"]),
        "installed_files_sha256": str(runtime["installed_files_sha256"]),
    }


def attest_dispatch(expected_sha: str, environ: Mapping[str, str], isolation) -> dict[str, Any]:
    dispatch, runtime = observe(environ, isolation)
    return verify_dispatch(dispatch, runtime, expected_sha=expected_sha)


def attest_loaded_modules(isolation) -> int:
    """Every loaded module came from the stdlib, a locked file, the evaluator pin or this script."""

    from crypto_probability_engine import runtime_isolation
    from crypto_probability_engine.oos.evaluation.evaluator_pin import pinned_files

    return runtime_isolation.attest_loaded_modules(
        isolation, pinned=(*pinned_files(ROOT), SCRIPT), root=ROOT
    )


def load_driver():
    """The locked driver, imported WITHOUT connecting. enter() authenticated its files first."""

    import psycopg

    return psycopg


def main(argv: list[str] | None = None, *, environ: Mapping[str, str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    captured: dict[str, Any] = {}
    try:
        outcome = _run(args, os.environ if environ is None else environ, captured)
    except Exception as exc:  # noqa: BLE001 - every failure is reported, then fails the step
        record = _refusal_record(args.mode, exc, captured)
        if args.report:
            _write_report(Path(args.report), record)
        print(f"{record['outcome']}: {record['error_type']}: {record['detail']}", file=sys.stderr)
        return 2 if record["outcome"] == "REFUSED" else 1
    print(json.dumps(outcome, indent=2))
    if args.report:
        _write_report(Path(args.report), outcome)
    return 0


def migration_bytes() -> bytes:
    """The file on this commit, refused unless it is exactly the reviewed bytes."""

    data = (ROOT / MIGRATION).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != MIGRATION_SHA256:
        raise _refusal(f"{MIGRATION} is sha256 {digest}, not the reviewed {MIGRATION_SHA256}")
    return data


def _run(
    args: argparse.Namespace, environ: Mapping[str, str], captured: dict[str, Any]
) -> dict[str, Any]:
    if args.mode == MODE_APPLY and args.confirm != CONFIRMATION:
        raise _refusal(f"--confirm must be exactly {CONFIRMATION}")

    isolation = enter_isolated_runtime(args.wheelhouse)
    record = attest_dispatch(args.expected_sha, environ, isolation)
    attest_loaded_modules(isolation)

    data = migration_bytes()
    base = {
        "schema_version": REPORT_SCHEMA,
        "migration": MIGRATION,
        "migration_sha256": hashlib.sha256(data).hexdigest(),
        "run_provenance": record,
    }
    if args.mode == MODE_ATTEST:
        # Load the driver WITHOUT connecting, and attest again, in the step that runs before any
        # step holds the secret (owner ruling L1b, as for 0009).
        load_driver()
        attest_loaded_modules(isolation)
        from crypto_probability_engine import runtime_isolation

        return {
            **base,
            "mode": MODE_ATTEST,
            "touches_database": False,
            "driver_helpers": runtime_isolation.loaded_dynamic_helpers(),
        }

    database_url = environ.get("SUPABASE_DB_URL", "")
    if not database_url:
        raise _refusal("SUPABASE_DB_URL is not set")
    driver = load_driver()
    attest_loaded_modules(isolation)  # the driver's origin, verified before it reaches the network
    applied = apply_in_one_transaction(
        lambda: driver.connect(database_url, connect_timeout=8), data.decode("utf-8"), captured
    )
    return {**base, "mode": MODE_APPLY, **applied}


def apply_in_one_transaction(
    open_connection: Callable[[], Any],
    migration_sql: str,
    captured: dict[str, Any],
) -> dict[str, Any]:
    """Pre-checks, the migration and post-checks in ONE transaction, committed only if all pass.

    ``captured`` receives every raw result as it arrives, so a refusal still reports what was seen.
    """

    with open_connection() as connection:
        with connection.cursor() as cursor:
            for statement in TIMEOUT_STATEMENTS:
                cursor.execute(statement)
            cursor.execute(ADVISORY_LOCK_SQL)

            cursor.execute(PRECHECK_SQL)
            pre = _row(cursor.fetchone(), len(PRECHECK_FIELDS), "pre-check")
            captured["pre_checks"] = dict(zip(PRECHECK_FIELDS, pre, strict=True))
            failures = pre_check_failures(captured["pre_checks"])
            if failures:
                raise _refusal(
                    "the database is not in the state a first apply of 0008 requires: "
                    + "; ".join(failures)
                )

            cursor.execute(migration_sql)
            captured["executed_migration_sha256"] = hashlib.sha256(
                migration_sql.encode("utf-8")
            ).hexdigest()

            cursor.execute(COLUMNS_SQL)
            columns = [list(row) for row in cursor.fetchall()]
            cursor.execute(CONSTRAINTS_SQL)
            constraints = [list(row) for row in cursor.fetchall()]
            cursor.execute(INDEXES_SQL)
            indexes = [list(row) for row in cursor.fetchall()]
            cursor.execute(SECURITY_SQL)
            security = _row(cursor.fetchone(), len(SECURITY_FIELDS), "security")
            cursor.execute(ROWS_SQL)
            rows = _row(cursor.fetchone(), 1, "row count")[0]
            cursor.execute(SEAL_SQL)
            seal_present = _row(cursor.fetchone(), 1, "seal")[0]
            captured["post_checks"] = {
                "columns": columns,
                "constraints": constraints,
                "indexes": indexes,
                "security": dict(zip(SECURITY_FIELDS, security, strict=True)),
                "rows": rows,
                "section_5a_seal_present": seal_present,
            }
            failures = post_check_failures(captured["pre_checks"], captured["post_checks"])
            if failures:
                raise _refusal(
                    "the applied schema is not the reviewed one, so the transaction is rolled "
                    "back: " + "; ".join(failures)
                )
        connection.commit()
    captured["committed"] = True
    return {
        "outcome": "APPLIED",
        "pre_checks": captured["pre_checks"],
        "executed_migration_sha256": captured["executed_migration_sha256"],
        "post_checks": captured["post_checks"],
        "committed": True,
    }


def pre_check_failures(pre: Mapping[str, Any]) -> list[str]:
    """Pure: every way the database differs from the state a first apply requires."""

    failures: list[str] = []
    for name in (
        "analysis_run_details_relations_in_any_schema",
        "created_at_index_relations_in_any_schema",
    ):
        if pre.get(name) != 0:
            failures.append(f"{name} = {pre.get(name)!r}, so this would not be a first apply")
    for name in (
        "analysis_runs_present",
        "predictions_present",
        "predictions_prediction_origin_present",
    ):
        if pre.get(name) is not True:
            failures.append(f"{name} is {pre.get(name)!r}; the application's joins need it")
    if pre.get("api_roles_present") != len(API_ROLES):
        failures.append(
            f"api_roles_present = {pre.get('api_roles_present')!r}, not {len(API_ROLES)}; "
            "the privilege statements need anon, authenticated and service_role"
        )
    if not isinstance(pre.get("section_5a_seal_present"), bool):
        failures.append("section_5a_seal_present was not observed")
    return failures


def post_check_failures(pre: Mapping[str, Any], post: Mapping[str, Any]) -> list[str]:
    """Pure: every way the applied schema differs from the reviewed one."""

    failures: list[str] = []
    columns = [tuple(column) for column in post["columns"]]
    if columns != list(EXPECTED_COLUMNS):
        failures.append(f"columns are {columns}, not {list(EXPECTED_COLUMNS)}")
    constraints = [tuple(constraint) for constraint in post["constraints"]]
    if constraints != list(EXPECTED_CONSTRAINTS):
        failures.append(f"constraints are {constraints}, not {list(EXPECTED_CONSTRAINTS)}")
    indexes = [tuple(index) for index in post["indexes"]]
    if [name for name, _ in indexes] != [name for name, _ in EXPECTED_INDEX_SUFFIXES] or not all(
        str(definition).endswith(suffix)
        for (_, definition), (_, suffix) in zip(indexes, EXPECTED_INDEX_SUFFIXES, strict=False)
    ):
        failures.append(f"indexes are {indexes}, not {list(EXPECTED_INDEX_SUFFIXES)}")
    security = post["security"]
    for field, expected in zip(SECURITY_FIELDS, EXPECTED_SECURITY, strict=True):
        if security.get(field) is not expected:
            failures.append(f"{field} is {security.get(field)!r}, not {expected!r}")
    if post["rows"] != 0:
        failures.append(f"the new table holds {post['rows']!r} rows, not 0")
    if post["section_5a_seal_present"] is not pre.get("section_5a_seal_present"):
        failures.append("the section 5A seal changed during the apply")
    return failures


def _git(*arguments: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _row(row: Any, width: int, what: str) -> tuple[Any, ...]:
    if row is None or len(row) != width:
        raise _refusal(f"the {what} query returned {row!r}, not one row of {width} values")
    return tuple(row)


def _refusal(message: str) -> Exception:
    ensure_source_path()
    from crypto_probability_engine.runtime_isolation import ProvenanceRefused  # stdlib-only

    return ProvenanceRefused(f"migration 0008 refused; nothing is applied: {message}")


def _refusal_record(mode: str, exc: BaseException, captured: Mapping[str, Any]) -> dict[str, Any]:
    """Deliberate refusals name no secret; any other failure is reported by type only."""

    refused = _is_refusal(exc)
    return {
        "schema_version": REPORT_SCHEMA,
        "mode": mode,
        "outcome": "REFUSED" if refused else "FAILED",
        "error_type": type(exc).__name__,
        "detail": str(exc)
        if refused
        else "unexpected failure; the detail is withheld because driver messages can name the host",
        "committed": False,
        "captured": dict(captured),
    }


def _is_refusal(exc: BaseException) -> bool:
    ensure_source_path()
    from crypto_probability_engine.runtime_isolation import ProvenanceRefused  # stdlib-only

    return isinstance(exc, ProvenanceRefused)


def _write_report(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())
