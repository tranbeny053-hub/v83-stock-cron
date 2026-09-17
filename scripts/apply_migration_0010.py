#!/usr/bin/env python
"""Apply migration 0010, the legacy tables' security posture, ONCE.

    --mode attest     verify isolation, dispatch and runtime; touches no database
    --mode rehearse   the whole apply against a scratch local PostgreSQL: apply once, then prove
                      that a second apply refuses; never where the production secret is present,
                      never over the network
    --mode apply      THE ONE-SHOT APPLY; requires the confirmation token

Run only by ``.github/workflows/apply-migration-0010.yml``, as ``python -I -S -B``, inside the
closed trust boundary of the other database routes: exact CPython 3.13.14, CPython's bundled pip
and lock-authenticated wheels, with the dispatch verified HERE against THIS workflow in the owner
repository.

WHAT IT CHANGES, AND WHAT IT PROVES DOES NOT CHANGE. Migration 0010 codifies what the read-only
audit (run 35120616278) measured on the ten legacy tables. Row-level security stays on, PUBLIC,
anon and authenticated lose their latent privileges, and service_role keeps exactly what it holds.
Effective access is unchanged, and this route refuses unless production is still in the audited
state:
- every legacy table exists once, in ``public``, is owned by the applying role, has row-level
  security on and not forced, has no policy, and has no PUBLIC or column grant;
- service_role holds every table privilege the server has: seven, plus MAINTAIN on PostgreSQL 17
  and later (the audit saw production's API roles hold MAINTAIN, so production runs 17 or later);
- anon or authenticated still hold something (otherwise this is not a first apply, so a second
  dispatch refuses and the one-shot property is enforced by the database itself).

ONE TRANSACTION, FAIL CLOSED. Under bounded timeouts and an advisory lock:
  1. read-only PRE-CHECKS, as above, plus the three serial sequences. The security of the tables of
     0005, 0006, 0008 and 0009 is recorded, not required: 0010 never touches them. The server's
     version decides which table privileges are asked about, so no check is blind to one the server
     can grant;
  2. exactly the pinned bytes of migration 0010, with no parameters;
  3. read-only POST-CHECKS refuse unless:
     - every legacy table keeps row-level security, owner and zero policies;
     - PUBLIC, anon and authenticated hold nothing on the tables or the sequences;
     - service_role's table and sequence privileges are unchanged;
     - the other migrations' tables are exactly as they were.
Any refusal or error rolls the transaction back, so nothing is applied; only then is it committed.
If the connection fails while the COMMIT is in flight, the report says ``committed`` is UNKNOWN.
Had it committed, a second dispatch would refuse as not a first apply.
No application row is ever read.

Every query result is captured raw before it is judged, and written to ``--report`` on success
and on refusal alike. The database URL is never printed, logged or written. An unexpected failure
is reported by its type only, because driver messages can name the host.

THIS FILE IMPORTS ONLY THE STANDARD LIBRARY AT MODULE LEVEL, exactly like the other routes.
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
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
SCRIPT = "scripts/apply_migration_0010.py"
WORKFLOW = ".github/workflows/apply-migration-0010.yml"
REHEARSAL_WORKFLOW = ".github/workflows/apply-migration-0010-rehearsal.yml"
MIGRATION = "migrations/0010_legacy_table_security.sql"
# The reviewed bytes. A different file on the dispatched commit refuses before any connection.
MIGRATION_SHA256 = "bc2ec1dd501b1d5f0d49204a0d6b1619ef29f4359d3d98166101e99452cbcc1e"
CONFIRMATION = "APPLY-MIGRATION-0010-ONCE"
REPORT_SCHEMA = "migration-0010-apply-report.v1"
DISPATCH_SCHEMA = "migration-0010-dispatch.v1"
MODE_ATTEST = "attest"
MODE_REHEARSE = "rehearse"
MODE_APPLY = "apply"
REQUIRED_EVENT = "workflow_dispatch"
REQUIRED_REF = "refs/heads/main"
# The owner repository, pinned: a fork's run carries a self-consistent identity of its own.
EXPECTED_REPOSITORY = "tranbeny053-hub/v83-stock-cron"
PINNED_PYTHON = ("CPython", "3.13.14")

TIMEOUT_STATEMENTS = (
    "SET LOCAL lock_timeout = '10s'",
    "SET LOCAL statement_timeout = '120s'",
)
# A fixed key, distinct from 0008's and 0009's: two appliers of 0010 serialize.
ADVISORY_LOCK_SQL = "SELECT pg_advisory_xact_lock(5000010)"

API_ROLES = ("anon", "authenticated", "service_role")
# The tables migrations 0001-0004 create (0007 alters predictions). A test re-derives this list
# from the migration files, so it cannot drift from them.
LEGACY_MIGRATIONS = (
    "migrations/0001_init.sql",
    "migrations/0002_news.sql",
    "migrations/0003_prediction_ledger.sql",
    "migrations/0004_prediction_outcomes.sql",
    "migrations/0007_prediction_origin.sql",
)
LEGACY_TABLES = (
    "analysis_runs",
    "analysis_timeframe_results",
    "app_events",
    "news_clusters",
    "news_evidence_links",
    "news_items",
    "prediction_outcomes",
    "predictions",
    "provider_observations",
    "watchlist",
)
# (table, column, the sequence a BIGSERIAL column owns). A test re-derives these from 0001.
LEGACY_SEQUENCES = (
    ("analysis_timeframe_results", "id", "public.analysis_timeframe_results_id_seq"),
    ("app_events", "id", "public.app_events_id_seq"),
    ("provider_observations", "id", "public.provider_observations_id_seq"),
)
# The tables of the later migrations. Their security must be exactly the same after the apply.
OTHER_TABLES = (
    "analysis_run_details",
    "prediction_derivatives_snapshots",
    "prediction_feature_snapshots",
    "section_5a_evaluation_seal",
)
# The table privileges of every supported server, sorted as the checks return them.
TABLE_PRIVILEGES = ("DELETE", "INSERT", "REFERENCES", "SELECT", "TRIGGER", "TRUNCATE", "UPDATE")
# PostgreSQL 17 added MAINTAIN, and production runs 17 or later: the audit saw the API roles hold
# it. On such a server every check also asks about MAINTAIN; on an older one, asking would fail.
MAINTAIN_SINCE_SERVER_VERSION = 170000
MINIMUM_SERVER_VERSION = 150000
TABLE_PRIVILEGES_WITH_MAINTAIN = tuple(sorted((*TABLE_PRIVILEGES, "MAINTAIN")))
SEQUENCE_PRIVILEGES = ("SELECT", "UPDATE", "USAGE")
SERVER_VERSION_SQL = "SELECT pg_catalog.current_setting('server_version_num')::integer"

_API_ROLES_SQL = ", ".join(f"'{role}'" for role in API_ROLES)
_SEQUENCE_PRIVILEGES_SQL = ", ".join(f"('{name}')" for name in SEQUENCE_PRIVILEGES)


def table_privileges_for(server_version: int) -> tuple[str, ...]:
    """Every table privilege a server of ``server_version`` (server_version_num) can grant."""

    if server_version >= MAINTAIN_SINCE_SERVER_VERSION:
        return TABLE_PRIVILEGES_WITH_MAINTAIN
    return TABLE_PRIVILEGES


def _held(function: str, role: str, relation: str, values: str) -> str:
    """The privileges ``role`` holds on ``relation``, as a sorted text array."""

    return (
        f"ARRAY(SELECT v.privilege FROM (VALUES {values}) AS v(privilege)"
        f" WHERE pg_catalog.{function}('{role}', {relation}, v.privilege)"
        ' ORDER BY v.privilege COLLATE "C")'
    )


# The relation kinds of the audit's table facts (scripts/audit_table_privileges.py).
_TABLE_LIKE_RELKINDS_SQL = "ARRAY['r', 'p', 'v', 'm', 'f']::\"char\"[]"


def _security_sql(names: Sequence[str], privileges: Sequence[str]) -> str:
    listed = ", ".join(f"('{name}')" for name in names)
    asked = ", ".join(f"('{name}')" for name in privileges)
    return (
        "SELECT t.name,"
        # Relations of the kinds the audit measured, in any schema: a same-named index, sequence or
        # type is not a second table.
        " (SELECT count(*) FROM pg_catalog.pg_class AS k WHERE k.relname::text = t.name"
        f" AND k.relkind = ANY ({_TABLE_LIKE_RELKINDS_SQL})),"
        " c.relkind::text,"
        " pg_catalog.pg_get_userbyid(c.relowner) = current_user,"
        " c.relrowsecurity, c.relforcerowsecurity,"
        " (SELECT count(*) FROM pg_catalog.pg_policy AS p WHERE p.polrelid = c.oid),"
        " EXISTS (SELECT 1 FROM pg_catalog.aclexplode("
        "COALESCE(c.relacl, pg_catalog.acldefault('r', c.relowner))) AS a WHERE a.grantee = 0),"
        " EXISTS (SELECT 1 FROM pg_catalog.pg_attribute AS att"
        " CROSS JOIN LATERAL pg_catalog.aclexplode(att.attacl) AS a"
        " WHERE att.attrelid = c.oid AND att.attnum > 0 AND NOT att.attisdropped"
        " AND att.attacl IS NOT NULL AND (a.grantee = 0 OR a.grantee IN ("
        "SELECT r.oid FROM pg_catalog.pg_roles AS r"
        " WHERE r.rolname IN ('anon', 'authenticated')))),"
        f" {_held('has_table_privilege', 'anon', 'c.oid', asked)},"
        f" {_held('has_table_privilege', 'authenticated', 'c.oid', asked)},"
        f" {_held('has_table_privilege', 'service_role', 'c.oid', asked)}"
        f" FROM (VALUES {listed}) AS t(name)"
        " LEFT JOIN pg_catalog.pg_class AS c"
        " ON c.oid = pg_catalog.to_regclass('public.' || t.name)"
        ' ORDER BY t.name COLLATE "C"'
    )


ROLES_SQL = (
    "SELECT count(*) FROM pg_catalog.pg_roles"
    f" WHERE rolname IN ({_API_ROLES_SQL})"
)


def legacy_security_sql(server_version: int) -> str:
    return _security_sql(LEGACY_TABLES, table_privileges_for(server_version))


def other_security_sql(server_version: int) -> str:
    return _security_sql(OTHER_TABLES, table_privileges_for(server_version))


SECURITY_FIELDS = (
    "table",
    "relations_named_so",
    "relkind",
    "owned_by_applying_role",
    "row_level_security",
    "row_level_security_forced",
    "policies",
    "public_has_a_privilege",
    "column_grant_to_public_anon_or_authenticated",
    "anon",
    "authenticated",
    "service_role",
)
_SEQUENCES_LISTED = ", ".join(f"('{table}', '{column}')" for table, column, _ in LEGACY_SEQUENCES)
SEQUENCE_SECURITY_SQL = (
    "SELECT s.tbl, pg_catalog.pg_get_serial_sequence('public.' || s.tbl, s.col),"
    " EXISTS (SELECT 1 FROM pg_catalog.aclexplode("
    "COALESCE(q.relacl, pg_catalog.acldefault('s', q.relowner))) AS a WHERE a.grantee = 0),"
    f" {_held('has_sequence_privilege', 'anon', 'q.oid', _SEQUENCE_PRIVILEGES_SQL)},"
    f" {_held('has_sequence_privilege', 'authenticated', 'q.oid', _SEQUENCE_PRIVILEGES_SQL)},"
    f" {_held('has_sequence_privilege', 'service_role', 'q.oid', _SEQUENCE_PRIVILEGES_SQL)}"
    f" FROM (VALUES {_SEQUENCES_LISTED}) AS s(tbl, col)"
    " LEFT JOIN pg_catalog.pg_class AS q ON q.oid = pg_catalog.to_regclass("
    "pg_catalog.pg_get_serial_sequence('public.' || s.tbl, s.col))"
    ' ORDER BY s.tbl COLLATE "C"'
)
SEQUENCE_FIELDS = (
    "table",
    "sequence",
    "public_has_a_privilege",
    "anon",
    "authenticated",
    "service_role",
)
NOT_A_FIRST_APPLY = "this is not a first apply"
COMMIT_UNKNOWN = "UNKNOWN"

# The rehearsal reaches only a local server through its unix socket: never a network host.
_LOCAL_SOCKET_URL = re.compile(r"postgresql:///[a-z_][a-z0-9_]*\?host=/var/run/postgresql")
REHEARSAL_URL_VARIABLE = "MIGRATION_0010_REHEARSAL_URL"
_COMMIT_SHA = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_DIGITS = re.compile(r"[0-9]+")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=[MODE_ATTEST, MODE_REHEARSE, MODE_APPLY], default=MODE_ATTEST
    )
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
    """Pure: a manual dispatch of THIS workflow, in the owner repository, on main, at the SHA."""

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
        dispatch.get("workflow_ref") == f"{EXPECTED_REPOSITORY}/{WORKFLOW}@{REQUIRED_REF}",
        f"workflow is {dispatch.get('workflow_ref')!r}, not {WORKFLOW} on {REQUIRED_REF}",
    )
    sha_is_canonical = isinstance(expected_sha, str) and bool(_COMMIT_SHA.fullmatch(expected_sha))
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
        bool(_SHA256.fullmatch(str(runtime.get("installed_files_sha256", "")))),
        "the installed files were not verified against their records",
    )
    need(
        bool(_DIGITS.fullmatch(str(dispatch.get("run_id", "")))),
        "run_id is not a GitHub run id",
    )
    need(
        bool(_DIGITS.fullmatch(str(dispatch.get("run_attempt", "")))),
        "run_attempt is not a number",
    )
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


def migration_bytes() -> bytes:
    """The file on this commit, refused unless it is exactly the reviewed bytes."""

    data = (ROOT / MIGRATION).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != MIGRATION_SHA256:
        raise _refusal(f"{MIGRATION} is sha256 {digest}, not the reviewed {MIGRATION_SHA256}")
    return data


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
    print(json.dumps(outcome, indent=2, sort_keys=True))
    if args.report:
        _write_report(Path(args.report), outcome)
    return 0


def _run(
    args: argparse.Namespace, environ: Mapping[str, str], captured: dict[str, Any]
) -> dict[str, Any]:
    if args.mode == MODE_APPLY and args.confirm != CONFIRMATION:
        raise _refusal(f"--confirm must be exactly {CONFIRMATION}")
    if args.mode == MODE_REHEARSE:
        return rehearse(args, environ, captured)

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
        # Load the driver WITHOUT connecting, and attest again, before any step holds the secret.
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


def rehearse(
    args: argparse.Namespace, environ: Mapping[str, str], captured: dict[str, Any]
) -> dict[str, Any]:
    """The apply, end to end, on the scratch database the rehearsal built: once, then refused.

    The scratch database is built from migrations 0001-0009 plus the audited production state, as
    the role this process connects as, so that role owns the tables exactly as production's
    applying role does.
    """

    url = environ.get(REHEARSAL_URL_VARIABLE, "")
    if not _LOCAL_SOCKET_URL.fullmatch(url):
        raise _refusal(
            f"{REHEARSAL_URL_VARIABLE} must be a local unix-socket URL, e.g. "
            "postgresql:///migration_0010_rehearsal?host=/var/run/postgresql"
        )
    if environ.get("SUPABASE_DB_URL"):
        raise _refusal("the rehearsal never runs where the production database secret is present")
    isolation = enter_isolated_runtime(args.wheelhouse) if args.wheelhouse else None
    data = migration_bytes()
    driver = load_driver()
    if isolation is not None:
        attest_loaded_modules(isolation)

    def open_connection():
        return driver.connect(url, connect_timeout=8)

    first_captured: dict[str, Any] = {}
    captured["first_apply"] = first_captured
    first = apply_in_one_transaction(open_connection, data.decode("utf-8"), first_captured)
    second_captured: dict[str, Any] = {}
    captured["second_apply"] = second_captured
    try:
        apply_in_one_transaction(open_connection, data.decode("utf-8"), second_captured)
    except Exception as exc:  # noqa: BLE001 - only the one-shot refusal is the expected outcome
        if not (_is_refusal(exc) and NOT_A_FIRST_APPLY in str(exc)):
            raise
        second_refusal = str(exc)
    else:
        raise _refusal("a second apply was not refused, so the one-shot property does not hold")
    return {
        "schema_version": REPORT_SCHEMA,
        "mode": MODE_REHEARSE,
        "outcome": "REHEARSED",
        "migration": MIGRATION,
        "migration_sha256": hashlib.sha256(data).hexdigest(),
        "first_apply": first,
        "second_apply_refusal": second_refusal,
        "second_apply_captured": second_captured,
    }


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

            cursor.execute(ROLES_SQL)
            roles = _row(cursor.fetchone(), 1, "roles")[0]
            captured["api_roles_present"] = roles
            if roles != len(API_ROLES):
                raise _refusal(f"{roles!r} of the {len(API_ROLES)} Supabase API roles exist")

            cursor.execute(SERVER_VERSION_SQL)
            server_version = _row(cursor.fetchone(), 1, "server version")[0]
            captured["server_version_num"] = server_version
            if (
                not isinstance(server_version, int)
                or isinstance(server_version, bool)
                or server_version < MINIMUM_SERVER_VERSION
            ):
                raise _refusal(
                    f"the server version {server_version!r} is not PostgreSQL 15 or later"
                )
            privileges = table_privileges_for(server_version)
            captured["table_privileges_asked"] = list(privileges)
            legacy_sql = legacy_security_sql(server_version)
            other_sql = other_security_sql(server_version)

            pre_legacy = _rows(cursor, legacy_sql, SECURITY_FIELDS)
            captured["pre_legacy"] = pre_legacy
            failures = legacy_pre_check_failures(pre_legacy, privileges)
            if failures:
                raise _refusal(
                    "the database is not in the audited state a first apply of 0010 requires: "
                    + "; ".join(failures)
                )
            pre_sequences = _rows(cursor, SEQUENCE_SECURITY_SQL, SEQUENCE_FIELDS)
            captured["pre_sequences"] = pre_sequences
            pre_other = _rows(cursor, other_sql, SECURITY_FIELDS)
            captured["pre_other"] = pre_other
            failures = sequence_pre_check_failures(pre_sequences) + other_pre_check_failures(
                pre_other
            )
            if failures:
                raise _refusal(
                    "the database is not in the state a first apply of 0010 requires: "
                    + "; ".join(failures)
                )

            cursor.execute(migration_sql)
            captured["executed_migration_sha256"] = hashlib.sha256(
                migration_sql.encode("utf-8")
            ).hexdigest()

            post_legacy = _rows(cursor, legacy_sql, SECURITY_FIELDS)
            post_sequences = _rows(cursor, SEQUENCE_SECURITY_SQL, SEQUENCE_FIELDS)
            post_other = _rows(cursor, other_sql, SECURITY_FIELDS)
            captured["post_legacy"] = post_legacy
            captured["post_sequences"] = post_sequences
            captured["post_other"] = post_other
            failures = (
                legacy_post_check_failures(pre_legacy, post_legacy)
                + sequence_post_check_failures(pre_sequences, post_sequences)
                + (
                    []
                    if post_other == pre_other
                    else ["the tables of 0005, 0006, 0008 or 0009 changed during the apply"]
                )
            )
            if failures:
                raise _refusal(
                    "the applied posture is not the reviewed one, so the transaction is rolled "
                    "back: " + "; ".join(failures)
                )
        captured["commit_attempted"] = True
        connection.commit()
        captured["committed"] = True
    return {
        "outcome": "APPLIED",
        "api_roles_present": captured["api_roles_present"],
        "server_version_num": server_version,
        "table_privileges_asked": list(privileges),
        "pre_legacy": pre_legacy,
        "pre_sequences": pre_sequences,
        "pre_other": pre_other,
        "executed_migration_sha256": captured["executed_migration_sha256"],
        "post_legacy": post_legacy,
        "post_sequences": post_sequences,
        "post_other": post_other,
        "committed": True,
    }


def legacy_pre_check_failures(
    rows: Sequence[Mapping[str, Any]], privileges: Sequence[str] = TABLE_PRIVILEGES
) -> list[str]:
    """Pure: every way the legacy tables differ from the state the audit measured.

    ``privileges`` is every table privilege the server can grant (``table_privileges_for``).
    """

    failures: list[str] = []
    if [row.get("table") for row in rows] != list(LEGACY_TABLES):
        return [f"the legacy tables read were {[row.get('table') for row in rows]}"]
    for row in rows:
        failures += _table_shape_failures(row, "before")
        if row.get("row_level_security") is not True:
            failures.append(f"{row['table']}: row-level security is not on, as the audit measured")
        if row.get("policies") != 0:
            failures.append(f"{row['table']}: has {row.get('policies')!r} policies, not none")
        if row.get("service_role") != list(privileges):
            failures.append(
                f"{row['table']}: service_role holds {row.get('service_role')!r}, not every "
                "privilege, as the audit measured"
            )
        for role in ("anon", "authenticated"):
            if not set(row.get(role) or ()) <= set(privileges):
                failures.append(f"{row['table']}: {role} privileges are unreadable")
    if not failures and not any(row["anon"] or row["authenticated"] for row in rows):
        failures.append(
            f"{NOT_A_FIRST_APPLY}: anon and authenticated already hold nothing on any legacy table"
        )
    return failures


def sequence_pre_check_failures(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    failures: list[str] = []
    expected = [(table, sequence) for table, _, sequence in LEGACY_SEQUENCES]
    if [(row.get("table"), row.get("sequence")) for row in rows] != expected:
        failures.append(
            "the serial sequences are "
            f"{[(row.get('table'), row.get('sequence')) for row in rows]}, not {expected}"
        )
    for row in rows:
        if row.get("public_has_a_privilege") is not False:
            failures.append(f"{row.get('sequence')}: PUBLIC holds a privilege")
    return failures


def other_pre_check_failures(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """The later migrations' tables are recorded, not required.

    0010 never touches them, and the post-check requires their security to be identical after the
    apply, whatever it is. Only a malformed read refuses.
    """

    if [row.get("table") for row in rows] != sorted(OTHER_TABLES):
        return [f"the other tables read were {[row.get('table') for row in rows]}"]
    return []


def legacy_post_check_failures(
    pre: Sequence[Mapping[str, Any]], post: Sequence[Mapping[str, Any]]
) -> list[str]:
    """Pure: every way the applied legacy posture differs from the reviewed one."""

    if [row.get("table") for row in post] != list(LEGACY_TABLES) or len(pre) != len(post):
        return [f"the legacy tables read after were {[row.get('table') for row in post]}"]
    failures: list[str] = []
    for before, after in zip(pre, post, strict=True):
        failures += _table_shape_failures(after, "after")
        table = after["table"]
        if after.get("row_level_security") is not True:
            failures.append(f"{table}: row-level security is off after the apply")
        if after.get("policies") != before.get("policies"):
            failures.append(f"{table}: the policies changed")
        for role in ("anon", "authenticated"):
            if after.get(role) != []:
                failures.append(f"{table}: {role} still holds {after.get(role)!r}")
        if after.get("service_role") != before.get("service_role"):
            failures.append(
                f"{table}: service_role holds {after.get('service_role')!r}, "
                f"not the {before.get('service_role')!r} it held"
            )
    return failures


def sequence_post_check_failures(
    pre: Sequence[Mapping[str, Any]], post: Sequence[Mapping[str, Any]]
) -> list[str]:
    if [(row.get("table"), row.get("sequence")) for row in post] != [
        (row.get("table"), row.get("sequence")) for row in pre
    ]:
        return ["the serial sequences changed during the apply"]
    failures: list[str] = []
    for before, after in zip(pre, post, strict=True):
        sequence = after.get("sequence")
        if after.get("public_has_a_privilege") is not False:
            failures.append(f"{sequence}: PUBLIC holds a privilege after the apply")
        for role in ("anon", "authenticated"):
            if after.get(role) != []:
                failures.append(f"{sequence}: {role} still holds {after.get(role)!r}")
        if after.get("service_role") != before.get("service_role"):
            failures.append(f"{sequence}: service_role's privileges changed")
    return failures


def _table_shape_failures(row: Mapping[str, Any], when: str) -> list[str]:
    table = row.get("table")
    failures: list[str] = []
    if row.get("relations_named_so") != 1:
        failures.append(
            f"{table}: {row.get('relations_named_so')!r} relations have this name {when}, not one"
        )
    if row.get("relkind") != "r":
        failures.append(f"{table}: is {row.get('relkind')!r} {when}, not an ordinary table")
    if row.get("owned_by_applying_role") is not True:
        failures.append(f"{table}: is not owned by the applying role {when}")
    if row.get("row_level_security_forced") is not False:
        failures.append(f"{table}: row-level security is forced {when}")
    if row.get("public_has_a_privilege") is not False:
        failures.append(f"{table}: PUBLIC holds a privilege {when}")
    if row.get("column_grant_to_public_anon_or_authenticated") is not False:
        failures.append(f"{table}: carries a column grant to PUBLIC, anon or authenticated {when}")
    return failures


def _rows(cursor: Any, query: str, fields: Sequence[str]) -> list[dict[str, Any]]:
    cursor.execute(query)
    rows = []
    for row in cursor.fetchall():
        if row is None or len(row) != len(fields):
            raise _refusal(f"a check returned {row!r}, not a row of {len(fields)} values")
        rows.append({field: _plain(value) for field, value in zip(fields, row, strict=True)})
    return rows


def _plain(value: Any) -> Any:
    return list(value) if isinstance(value, (list, tuple)) else value


def _row(row: Any, width: int, what: str) -> tuple[Any, ...]:
    if row is None or len(row) != width:
        raise _refusal(f"the {what} query returned {row!r}, not one row of {width} values")
    return tuple(row)


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


def _refusal(message: str) -> Exception:
    ensure_source_path()
    from crypto_probability_engine.runtime_isolation import ProvenanceRefused  # stdlib-only

    return ProvenanceRefused(f"migration 0010 refused; nothing is applied: {message}")


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
        "committed": _commit_state(captured),
        "captured": dict(captured),
    }


def _commit_state(captured: Mapping[str, Any]) -> bool | str:
    """Whether anything was committed; UNKNOWN after a failure while a COMMIT was in flight.

    A rehearsal nests one record per apply (``first_apply``, ``second_apply``).
    """

    records = [captured, *(value for value in captured.values() if isinstance(value, Mapping))]
    if any(record.get("committed") is True for record in records):
        return True
    if any(record.get("commit_attempted") for record in records):
        return COMMIT_UNKNOWN
    return False


def _is_refusal(exc: BaseException) -> bool:
    ensure_source_path()
    from crypto_probability_engine.runtime_isolation import ProvenanceRefused  # stdlib-only

    return isinstance(exc, ProvenanceRefused)


def _write_report(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())
