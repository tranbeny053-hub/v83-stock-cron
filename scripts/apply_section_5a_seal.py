#!/usr/bin/env python
"""Apply migration 0009, the section 5A one-look seal, ONCE (owner rulings K1=A, K2=A).

    --mode attest   verify isolation, pin, dispatch and runtime; touches no database
    --mode apply    THE ONE-SHOT APPLY; requires the confirmation token

Run only by ``.github/workflows/section-5a-apply-seal-migration.yml``, as ``python -I -S -B``,
under exactly the attestation the evaluator uses (pre-registration Addenda 5-8), bound to that
workflow. A record this run produces can never claim or recover the look.

ONE TRANSACTION, FAIL CLOSED. Under bounded timeouts and an advisory lock:
  1. read-only PRE-CHECKS refuse unless no seal table, guard function or guard trigger exists in
     ANY schema. ``CREATE TABLE IF NOT EXISTS`` would otherwise keep a stale table (F-0009-C);
  2. exactly the pinned bytes of migration 0009 are executed, with no parameters;
  3. read-only POST-CHECKS refuse unless the table has exactly the expected columns, the named
     constraints and exactly both guard triggers; row-level security is on and not forced; no
     privilege is held by PUBLIC, anon, authenticated or service_role; the applying role owns it;
     it holds zero rows; and 0008's table is exactly as it was.
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
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
SCRIPT = "scripts/apply_section_5a_seal.py"
MIGRATION = "migrations/0009_section_5a_evaluation_seal.sql"
CONFIRMATION = "APPLY-SECTION-5A-SEAL-MIGRATION-ONCE"
REPORT_SCHEMA = "section-5a-seal-migration-report.v1"
MODE_ATTEST = "attest"
MODE_APPLY = "apply"

TIMEOUT_STATEMENTS = (
    "SET LOCAL lock_timeout = '10s'",
    "SET LOCAL statement_timeout = '120s'",
)
# A fixed key: two appliers serialize even outside the workflow's concurrency group.
ADVISORY_LOCK_SQL = "SELECT pg_advisory_xact_lock(5009005)"

PRECHECK_SQL = (
    "SELECT"
    " (SELECT count(*) FROM pg_catalog.pg_class WHERE relname = 'section_5a_evaluation_seal'),"
    " (SELECT count(*) FROM pg_catalog.pg_proc"
    " WHERE proname IN ('section_5a_seal_guard', 'section_5a_seal_truncate_guard')),"
    " (SELECT count(*) FROM pg_catalog.pg_trigger"
    " WHERE tgname IN ('section_5a_seal_guard', 'section_5a_seal_truncate_guard',"
    " 'section_5a_seal_immutable')),"
    " to_regclass('public.analysis_run_details') IS NOT NULL"
)

COLUMNS_SQL = (
    "SELECT column_name, data_type, is_nullable FROM information_schema.columns"
    " WHERE table_schema = 'public' AND table_name = 'section_5a_evaluation_seal'"
    " ORDER BY ordinal_position"
)
EXPECTED_COLUMNS = (
    ("seal_id", "text", "NO"),
    ("sealed_at_utc", "timestamp with time zone", "NO"),
    ("evaluator_pin_digest", "text", "NO"),
    ("contract_instants", "jsonb", "NO"),
    ("run_provenance", "jsonb", "NO"),
    ("raw_evidence", "jsonb", "YES"),
    ("snapshot_payload", "jsonb", "YES"),
    ("evidence_snapshot_id", "text", "YES"),
    ("result_inputs_digest", "text", "YES"),
    ("state", "text", "NO"),
    ("state_detail", "text", "NO"),
    ("updated_at_utc", "timestamp with time zone", "NO"),
)

CONSTRAINTS_SQL = (
    "SELECT conname, contype FROM pg_catalog.pg_constraint"
    " WHERE conrelid = 'public.section_5a_evaluation_seal'::regclass ORDER BY conname"
)
REQUIRED_CHECK_CONSTRAINTS = (
    "section_5a_captured_is_complete",
    "section_5a_claim_has_verified_provenance",
    "section_5a_claimed_has_no_snapshot",
)

TRIGGERS_SQL = (
    "SELECT tgname FROM pg_catalog.pg_trigger"
    " WHERE tgrelid = 'public.section_5a_evaluation_seal'::regclass AND NOT tgisinternal"
    " ORDER BY tgname"
)
EXPECTED_TRIGGERS = ("section_5a_seal_guard", "section_5a_seal_truncate_guard")

API_ROLES = ("anon", "authenticated", "service_role")
_EVERY_TABLE_PRIVILEGE = "SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER"
SECURITY_SQL = (
    "SELECT c.relrowsecurity, c.relforcerowsecurity,"
    " pg_catalog.pg_get_userbyid(c.relowner) = current_user,"
    + "".join(
        f" has_table_privilege('{role}', c.oid, '{_EVERY_TABLE_PRIVILEGE}')," for role in API_ROLES
    )
    + " EXISTS (SELECT 1 FROM aclexplode(c.relacl) AS acl WHERE acl.grantee = 0)"
    " FROM pg_catalog.pg_class AS c"
    " WHERE c.oid = 'public.section_5a_evaluation_seal'::regclass"
)
SECURITY_FIELDS = (
    "row_level_security",
    "row_level_security_forced",
    "owned_by_applying_role",
    *(f"{role}_has_a_privilege" for role in API_ROLES),
    "public_has_a_privilege",
)
EXPECTED_SECURITY = (True, False, True, False, False, False, False)

ROWS_SQL = "SELECT count(*) FROM public.section_5a_evaluation_seal"
ANALYSIS_RUN_DETAILS_SQL = "SELECT to_regclass('public.analysis_run_details') IS NOT NULL"


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
    """G1=A, J1=B: the isolated process and its authenticated import surface, verified first."""

    ensure_source_path()
    from crypto_probability_engine import runtime_isolation

    if not wheelhouse:
        raise _refusal("--wheelhouse is required; installed code is authenticated against it")
    return runtime_isolation.enter(ROOT, wheelhouse=Path(wheelhouse))


def attest_dispatch(expected_sha: str, environ: Mapping[str, str], isolation) -> dict[str, Any]:
    """E2=A, E3=A, bound to THIS workflow. Its record verifies nowhere a look is claimed."""

    from crypto_probability_engine.oos.evaluation import provenance

    return provenance.attest(
        expected_sha,
        environ=environ,
        isolation=isolation,
        workflow=provenance.SEAL_MIGRATION_WORKFLOW,
    )


def attest_loaded_modules(isolation) -> int:
    """Every loaded module came from the stdlib, a locked file, the evaluator pin or this script.

    This script is bound by the reviewed commit (``expected_sha`` on a clean checkout), not by the
    evaluator pin, which stays exactly what the evaluation executes.
    """

    from crypto_probability_engine import runtime_isolation
    from crypto_probability_engine.oos.evaluation.evaluator_pin import pinned_files

    return runtime_isolation.attest_loaded_modules(
        isolation, pinned=(*pinned_files(ROOT), SCRIPT), root=ROOT
    )


def load_driver():
    """The locked driver, imported WITHOUT connecting. enter() authenticated its files first."""

    import psycopg
    import psycopg_pool  # noqa: F401 - loaded as the evaluator loads it, so the check sees both

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


def _run(
    args: argparse.Namespace, environ: Mapping[str, str], captured: dict[str, Any]
) -> dict[str, Any]:
    if args.mode == MODE_APPLY and args.confirm != CONFIRMATION:
        raise _refusal(f"--confirm must be exactly {CONFIRMATION}")

    isolation = enter_isolated_runtime(args.wheelhouse)
    record = attest_dispatch(args.expected_sha, environ, isolation)
    attest_loaded_modules(isolation)

    migration_bytes = (ROOT / MIGRATION).read_bytes()
    base = {
        "schema_version": REPORT_SCHEMA,
        "migration": MIGRATION,
        "migration_sha256": hashlib.sha256(migration_bytes).hexdigest(),
        "run_provenance": record,
    }
    if args.mode == MODE_ATTEST:
        # Owner ruling L1b: load the driver WITHOUT connecting, and attest again, in the step that
        # runs before any step holds the secret. The real runner proves the post-driver check first.
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
    migration_sql = migration_bytes.decode("utf-8")
    driver = load_driver()
    attest_loaded_modules(isolation)  # the driver's origin, verified before it reaches the network
    applied = apply_in_one_transaction(
        lambda: driver.connect(database_url, connect_timeout=8), migration_sql, captured
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
            pre = _row(cursor.fetchone(), 4, "pre-check")
            captured["pre_checks"] = {
                "seal_tables_in_any_schema": pre[0],
                "guard_functions_in_any_schema": pre[1],
                "guard_triggers_in_any_schema": pre[2],
                "analysis_run_details_present": pre[3],
            }
            stale = [
                f"{name} = {value}"
                for name, value in captured["pre_checks"].items()
                if name != "analysis_run_details_present" and value != 0
            ]
            if stale:
                raise _refusal(
                    "the database already holds seal objects, so this would not be a first apply "
                    "(F-0009-C): " + ", ".join(stale)
                )

            cursor.execute(migration_sql)
            captured["executed_migration_sha256"] = hashlib.sha256(
                migration_sql.encode("utf-8")
            ).hexdigest()

            cursor.execute(COLUMNS_SQL)
            columns = [list(row) for row in cursor.fetchall()]
            cursor.execute(CONSTRAINTS_SQL)
            constraints = [list(row) for row in cursor.fetchall()]
            cursor.execute(TRIGGERS_SQL)
            triggers = [row[0] for row in cursor.fetchall()]
            cursor.execute(SECURITY_SQL)
            security = _row(cursor.fetchone(), len(SECURITY_FIELDS), "security")
            cursor.execute(ROWS_SQL)
            rows = _row(cursor.fetchone(), 1, "row count")[0]
            cursor.execute(ANALYSIS_RUN_DETAILS_SQL)
            analysis_run_details = _row(cursor.fetchone(), 1, "0008 table")[0]
            captured["post_checks"] = {
                "columns": columns,
                "constraints": constraints,
                "triggers": triggers,
                "security": dict(zip(SECURITY_FIELDS, security, strict=True)),
                "rows": rows,
                "analysis_run_details_present": analysis_run_details,
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


def post_check_failures(pre: Mapping[str, Any], post: Mapping[str, Any]) -> list[str]:
    """Pure: every way the applied schema differs from the reviewed one."""

    failures: list[str] = []
    columns = [tuple(column) for column in post["columns"]]
    if columns != list(EXPECTED_COLUMNS):
        failures.append(f"columns are {columns}, not {list(EXPECTED_COLUMNS)}")
    names = {name for name, kind in post["constraints"] if kind == "c"}
    missing = sorted(set(REQUIRED_CHECK_CONSTRAINTS) - names)
    if missing:
        failures.append(f"check constraints missing: {missing}")
    if [kind for _, kind in post["constraints"]].count("p") != 1:
        failures.append("the table does not have exactly one primary key")
    if list(post["triggers"]) != list(EXPECTED_TRIGGERS):
        failures.append(f"triggers are {list(post['triggers'])}, not {list(EXPECTED_TRIGGERS)}")
    security = post["security"]
    for field, expected in zip(SECURITY_FIELDS, EXPECTED_SECURITY, strict=True):
        if security.get(field) is not expected:
            failures.append(f"{field} is {security.get(field)!r}, not {expected!r}")
    if post["rows"] != 0:
        failures.append(f"the new table holds {post['rows']!r} rows, not 0")
    if post["analysis_run_details_present"] is not pre["analysis_run_details_present"]:
        failures.append("0008's table changed during the apply")
    return failures


def _row(row: Any, width: int, what: str) -> tuple[Any, ...]:
    if row is None or len(row) != width:
        raise _refusal(f"the {what} query returned {row!r}, not one row of {width} values")
    return tuple(row)


def _refusal(message: str) -> Exception:
    ensure_source_path()
    from crypto_probability_engine.runtime_isolation import ProvenanceRefused  # stdlib-only

    return ProvenanceRefused(f"section 5A seal migration refused; nothing is applied: {message}")


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

    if isinstance(exc, ProvenanceRefused):
        return True
    pin = sys.modules.get("crypto_probability_engine.oos.evaluation.evaluator_pin")
    return pin is not None and isinstance(exc, pin.EvaluatorPinMismatch)


def _write_report(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())
