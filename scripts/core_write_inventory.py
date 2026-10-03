"""D6: a deterministic inventory of every catalog route by which a role can write core evidence.

The owner's D6 ruling (2026-10-03): "scope=six core evidence tables + two bundle functions, keep
SELECT and revoke write/EXECUTE, with deterministic inventory proving no omitted core write surface
before freeze." This reads PostgreSQL's catalogs only, in one transaction made READ ONLY by its
first statement, and names no application row. For one role (service_role), each write surface
on the six core evidence tables is listed by kind:

- T: a table privilege, by has_table_privilege (direct, through PUBLIC, or inherited): INSERT,
  UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER, and MAINTAIN from PostgreSQL 17;
- C: a column privilege beyond the table's (INSERT, UPDATE or REFERENCES on some column);
- O: ownership, or membership in the owner (pg_has_role MEMBER);
- F: a SECURITY DEFINER function or procedure in an exposed schema that the role can EXECUTE and
  whose owner can write a core table;
- V: a view over a core table (pg_depend) that the role can write and that runs as its owner (no
  security_invoker);
- R: a rule on a relation the role can write whose action reaches a core table;
- G: a trigger on another table the role can write, whose function is SECURITY DEFINER and owned by
  a role that can write a core table;
- K: a foreign key from a core table to another table the role can delete from or update, with a
  cascading action (it would run as the owner).

D6's revoke set covers T and C on the six tables (a table REVOKE also revokes column privileges) and
F for the two bundle functions. Before freeze nothing else may appear; after D6 nothing may appear.
Informational, never a surface: BYPASSRLS, memberships, and default privileges for future tables.

THE ROUTE, .github/workflows/core-write-inventory.yml: owner-dispatched, inside the protected
Environment production-db-owner, as ``python -I -S -B`` within the closed trust boundary of the
other database routes (exact CPython, bundled pip, lock-authenticated wheels), with the dispatch
verified against THIS workflow in the owner repository, on main, at expected_sha.

    --mode attest      verify isolation, dispatch and runtime; touches no database
    --mode rehearse    the inventory against a scratch local PostgreSQL built from the migrations
                       with one planted surface per kind, as a role holding no privilege on any
                       core table; never where the production secret is present, never over the
                       network
    --mode inventory   THE READ-ONLY INVENTORY; requires --expect and the confirmation token

READ ONLY, CATALOGS ONLY, NEVER COMMITTED: one REPEATABLE READ snapshot made READ ONLY by its first
statement, refused unless the server says it is read only, and rolled back. The repository is
public, and so are its logs and artifacts: a role name is reported only if it is an API role,
PostgreSQL's own (pg_*) or UCPE's (ucpe_*), none of which can be the owner login. Every other name
is withheld; the connecting role and the database URL are never reported, and an unexpected failure
is reported by its type only.

THIS FILE IMPORTS ONLY THE STANDARD LIBRARY AT MODULE LEVEL, exactly like the other routes.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

CORE_TABLES = (
    "analysis_run_details",
    "analysis_runs",
    "prediction_derivatives_snapshots",
    "prediction_feature_snapshots",
    "prediction_outcomes",
    "predictions",
)
BUNDLE_FUNCTIONS = (
    "save_forecast_bundle(jsonb,jsonb,jsonb,jsonb,jsonb)",
    "save_prediction_bundle(jsonb,jsonb,jsonb)",
)
WRITE_PRIVILEGES = ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
COLUMN_PRIVILEGES = ("INSERT", "UPDATE", "REFERENCES")
EXPOSED_SCHEMAS = ("public", "graphql_public")
READ_ONLY_SQL = "SET TRANSACTION READ ONLY"
SURFACE_KINDS = ("T", "C", "O", "F", "V", "R", "G", "K")

_CORE = (
    "SELECT pg_catalog.to_regclass(pg_catalog.format('public.%%I', t)) AS oid, t"
    " FROM unnest(%(core)s::text[]) t"
)
_TABLE = "pg_catalog.format('public.%%I', t)"
# Whether a role (by oid) can write some core table: the test F and G apply to a function's owner.
_WRITES_CORE = (
    "EXISTS (SELECT 1 FROM unnest(%(core)s::text[]) t, unnest(%(privileges)s::text[]) w"
    f" WHERE pg_catalog.has_table_privilege({{owner}}, {_TABLE}, w))"
)
_CAN_WRITE = (
    "(pg_catalog.has_table_privilege(%(role)s, {relation}, 'INSERT')"
    " OR pg_catalog.has_table_privilege(%(role)s, {relation}, 'UPDATE')"
    " OR pg_catalog.has_table_privilege(%(role)s, {relation}, 'DELETE'))"
)
_REWRITE_DEPENDS = (
    " d.classid = 'pg_catalog.pg_rewrite'::pg_catalog.regclass"
    " AND d.refclassid = 'pg_catalog.pg_class'::pg_catalog.regclass"
)

QUERIES = {
    "T": (
        "SELECT t, p FROM unnest(%(core)s::text[]) t, unnest(%(privileges)s::text[]) p"
        f" WHERE pg_catalog.has_table_privilege(%(role)s, {_TABLE}, p) ORDER BY 1, 2"
    ),
    "C": (
        "SELECT t, p FROM unnest(%(core)s::text[]) t, unnest(%(columns)s::text[]) p"
        f" WHERE pg_catalog.has_any_column_privilege(%(role)s, {_TABLE}, p)"
        f" AND NOT pg_catalog.has_table_privilege(%(role)s, {_TABLE}, p) ORDER BY 1, 2"
    ),
    "O": (
        "SELECT c.relname, pg_catalog.pg_get_userbyid(c.relowner) FROM pg_catalog.pg_class c"
        f" JOIN ({_CORE}) core ON core.oid = c.oid"
        " WHERE pg_catalog.pg_has_role(%(role)s, c.relowner, 'MEMBER') ORDER BY 1"
    ),
    "F": (
        "SELECT n.nspname || '.' || p.proname"
        " || '(' || pg_catalog.oidvectortypes(p.proargtypes) || ')',"
        " pg_catalog.pg_get_userbyid(p.proowner) FROM pg_catalog.pg_proc p"
        " JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace"
        " WHERE n.nspname = ANY(%(exposed)s::text[]) AND p.prokind IN ('f', 'p') AND p.prosecdef"
        " AND pg_catalog.has_function_privilege(%(role)s, p.oid, 'EXECUTE')"
        f" AND {_WRITES_CORE.format(owner='p.proowner')} ORDER BY 1"
    ),
    "V": (
        "SELECT DISTINCT vn.nspname || '.' || v.relname, core.t FROM pg_catalog.pg_depend d"
        " JOIN pg_catalog.pg_rewrite r ON r.oid = d.objid"
        " JOIN pg_catalog.pg_class v ON v.oid = r.ev_class"
        " JOIN pg_catalog.pg_namespace vn ON vn.oid = v.relnamespace"
        f" JOIN ({_CORE}) core ON core.oid = d.refobjid"
        f" WHERE{_REWRITE_DEPENDS} AND v.relkind = 'v' AND v.oid <> core.oid"
        " AND NOT coalesce(v.reloptions && ARRAY['security_invoker=true',"
        " 'security_invoker=on'], false)"
        f" AND {_CAN_WRITE.format(relation='v.oid')} ORDER BY 1, 2"
    ),
    "R": (
        "SELECT DISTINCT cn.nspname || '.' || c.relname || '.' || r.rulename, core.t"
        " FROM pg_catalog.pg_rewrite r"
        " JOIN pg_catalog.pg_class c ON c.oid = r.ev_class"
        " JOIN pg_catalog.pg_namespace cn ON cn.oid = c.relnamespace"
        f" JOIN pg_catalog.pg_depend d ON d.objid = r.oid AND{_REWRITE_DEPENDS}"
        f" JOIN ({_CORE}) core ON core.oid = d.refobjid"
        " WHERE r.rulename <> '_RETURN' AND c.oid <> core.oid"
        f" AND {_CAN_WRITE.format(relation='c.oid')} ORDER BY 1, 2"
    ),
    "G": (
        "SELECT cn.nspname || '.' || c.relname || '.' || tg.tgname,"
        " pg_catalog.pg_get_userbyid(p.proowner) FROM pg_catalog.pg_trigger tg"
        " JOIN pg_catalog.pg_class c ON c.oid = tg.tgrelid"
        " JOIN pg_catalog.pg_namespace cn ON cn.oid = c.relnamespace"
        " JOIN pg_catalog.pg_proc p ON p.oid = tg.tgfoid"
        " WHERE NOT tg.tgisinternal AND p.prosecdef"
        f" AND c.oid NOT IN (SELECT oid FROM ({_CORE}) core)"
        f" AND ({_CAN_WRITE.format(relation='c.oid')}"
        " OR pg_catalog.has_table_privilege(%(role)s, c.oid, 'TRUNCATE'))"
        f" AND {_WRITES_CORE.format(owner='p.proowner')} ORDER BY 1"
    ),
    "K": (
        "SELECT con.conname, core.t || ' -> ' || rn.nspname || '.' || ref.relname"
        " FROM pg_catalog.pg_constraint con"
        f" JOIN ({_CORE}) core ON core.oid = con.conrelid"
        " JOIN pg_catalog.pg_class ref ON ref.oid = con.confrelid"
        " JOIN pg_catalog.pg_namespace rn ON rn.oid = ref.relnamespace"
        f" WHERE con.contype = 'f' AND ref.oid NOT IN (SELECT oid FROM ({_CORE}) others)"
        " AND (con.confdeltype IN ('c', 'n', 'd') OR con.confupdtype IN ('c', 'n', 'd'))"
        " AND (pg_catalog.has_table_privilege(%(role)s, ref.oid, 'DELETE')"
        " OR pg_catalog.has_table_privilege(%(role)s, ref.oid, 'UPDATE')) ORDER BY 1, 2"
    ),
}
INFORMATION = {
    "bypassrls": "SELECT rolbypassrls FROM pg_catalog.pg_roles WHERE rolname = %(role)s",
    "memberships": (
        "SELECT pg_catalog.pg_get_userbyid(m.roleid) FROM pg_catalog.pg_auth_members m"
        " JOIN pg_catalog.pg_roles r ON r.oid = m.member WHERE r.rolname = %(role)s ORDER BY 1"
    ),
    "default_privileges": (
        "SELECT pg_catalog.pg_get_userbyid(d.defaclrole), coalesce(n.nspname, ''),"
        " d.defaclobjtype, pg_catalog.array_to_string(d.defaclacl, ',')"
        " FROM pg_catalog.pg_default_acl d"
        " LEFT JOIN pg_catalog.pg_namespace n ON n.oid = d.defaclnamespace"
        " WHERE pg_catalog.array_to_string(d.defaclacl, ',') LIKE '%%' || %(role)s || '=%%'"
        " ORDER BY 1, 2, 3"
    ),
}


def parameters(role: str, server_version_num: int, exposed: Sequence[str]) -> dict[str, Any]:
    privileges = (*WRITE_PRIVILEGES, *(("MAINTAIN",) if server_version_num >= 170000 else ()))
    return {
        "role": role, "core": list(CORE_TABLES), "privileges": list(privileges),
        "columns": list(COLUMN_PRIVILEGES), "exposed": list(exposed),
    }


def collect(
    execute: Callable[[str, dict[str, Any]], list[tuple]],
    *,
    role: str,
    server_version_num: int,
    exposed: Sequence[str] = EXPOSED_SCHEMAS,
) -> dict[str, Any]:
    """The inventory, through ``execute`` (one statement, its rows), on the caller's transaction."""

    values = parameters(role, server_version_num, exposed)
    surfaces = {
        kind: sorted([str(cell) for cell in row] for row in execute(QUERIES[kind], values))
        for kind in SURFACE_KINDS
    }
    information = {name: [[str(cell) for cell in row] for row in execute(sql, values)]
                   for name, sql in INFORMATION.items()}
    return {
        "role": role, "server_version_num": server_version_num, "exposed_schemas": list(exposed),
        "core_tables": list(CORE_TABLES), "surfaces": surfaces, "information": information,
    }


def omitted(report: dict[str, Any]) -> list[list[str]]:
    """Every surface D6's revoke set does not cover: before freeze, this must be empty."""

    left: list[list[str]] = []
    for kind in SURFACE_KINDS:
        for row in report["surfaces"][kind]:
            covered = (
                (kind in ("T", "C") and row[0] in CORE_TABLES)
                or (kind == "F" and row[0].startswith("public.")
                    and row[0].removeprefix("public.").replace(", ", ",") in BUNDLE_FUNCTIONS)
            )
            if not covered:
                left.append([kind, *row])
    return left


def every_surface(report: dict[str, Any]) -> list[list[str]]:
    return [[kind, *row] for kind in SURFACE_KINDS for row in report["surfaces"][kind]]


def verdict(report: dict[str, Any], expect: str) -> list[str]:
    """before: nothing outside the revoke set (no omitted surface). after: nothing at all."""

    if expect == "before":
        return [" ".join(row) for row in omitted(report)]
    if expect == "after":
        return [" ".join(row) for row in every_surface(report)]
    raise ValueError(f"unknown expectation {expect!r}")


# --------------------------------------------------------------------------- the route

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
SCRIPT = "scripts/core_write_inventory.py"
WORKFLOW = ".github/workflows/core-write-inventory.yml"
CONFIRMATION = "READ-ONLY-CORE-WRITE-INVENTORY-ONCE"
REPORT_SCHEMA = "core-write-inventory.v1"
DISPATCH_SCHEMA = "core-write-inventory-dispatch.v1"
MODE_ATTEST = "attest"
MODE_REHEARSE = "rehearse"
MODE_INVENTORY = "inventory"
EXPECTATIONS = ("before", "after")
ROLE = "service_role"
REQUIRED_EVENT = "workflow_dispatch"
REQUIRED_REF = "refs/heads/main"
EXPECTED_REPOSITORY = "tranbeny053-hub/v83-stock-cron"
PINNED_PYTHON = ("CPython", "3.13.14")
GUARD_STATEMENTS = (
    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY",
    "SET LOCAL statement_timeout = '60s'",
    "SET LOCAL lock_timeout = '5s'",
)
TRANSACTION_READ_ONLY_SQL = "SELECT pg_catalog.current_setting('transaction_read_only')"
SERVER_VERSION_SQL = "SELECT pg_catalog.current_setting('server_version_num')"
# The rehearsal's own role must hold nothing on a core table: a query that read an application row
# would then fail, so success proves the inventory reads catalogs only.
REHEARSAL_HELD_SQL = (
    "SELECT t FROM unnest(%(core)s::text[]) t"
    f" WHERE pg_catalog.has_table_privilege(current_user, {_TABLE},"
    " 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')"
    f" OR pg_catalog.has_any_column_privilege(current_user, {_TABLE},"
    " 'SELECT,INSERT,UPDATE,REFERENCES') ORDER BY 1"
)
REHEARSAL_URL_VARIABLE = "INVENTORY_REHEARSAL_URL"
REHEARSAL_MARKER = "inventory_probe"
REHEARSAL_PLANTED_KINDS = ("F", "V", "R", "G", "K")
# Reportable role names: the API roles, PostgreSQL's own (pg_*) and UCPE's (ucpe_*). None of them
# can be the owner login. Every other name, in a surface's column or inside an ACL, is withheld.
REPORTED_ROLES = frozenset({"anon", "authenticated", "authenticator", "service_role"})
WITHHELD = "<role withheld>"
ROLE_COLUMNS = {"O": 1, "F": 1, "G": 1}
_REPORTED_ROLE = re.compile(r"(?:pg|ucpe)_[a-z0-9_]{1,58}")
_ACL_ITEM = re.compile(r"(?P<grantee>[^=/,]*)=(?P<privileges>[A-Za-z*]*)/(?P<grantor>[^=/,]+)")
# The rehearsal reaches only a local server through its unix socket: never a network host.
_LOCAL_SOCKET_URL = re.compile(r"^postgresql:///[a-z_][a-z0-9_]*\?host=/var/run/postgresql$")
_COMMIT_SHA = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_DIGITS = re.compile(r"[0-9]+")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="D6: the core-evidence write inventory, read-only."
    )
    parser.add_argument(
        "--mode", choices=[MODE_ATTEST, MODE_REHEARSE, MODE_INVENTORY], default=MODE_ATTEST
    )
    parser.add_argument(
        "--expect", default="", help="required for --mode inventory: exactly before or after"
    )
    parser.add_argument(
        "--confirm", default="", help="required for --mode inventory: the exact confirmation token"
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
    need(bool(_DIGITS.fullmatch(str(dispatch.get("run_id", "")))), "run_id is not a GitHub run id")
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


def main(argv: Sequence[str] | None = None, *, environ: Mapping[str, str] | None = None) -> int:
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
    return 1 if outcome.get("verdict") == "FAIL" else 0


def _run(
    args: argparse.Namespace, environ: Mapping[str, str], captured: dict[str, Any]
) -> dict[str, Any]:
    if args.mode == MODE_INVENTORY and args.confirm != CONFIRMATION:
        raise _refusal(f"--confirm must be exactly {CONFIRMATION}")
    if args.mode == MODE_INVENTORY and args.expect not in EXPECTATIONS:
        raise _refusal("--expect must be exactly before or after")
    if args.mode == MODE_REHEARSE:
        return rehearse(args, environ, captured)

    isolation = enter_isolated_runtime(args.wheelhouse)
    record = attest_dispatch(args.expected_sha, environ, isolation)
    attest_loaded_modules(isolation)
    base = {
        "schema_version": REPORT_SCHEMA,
        "role": ROLE,
        "core_tables": list(CORE_TABLES),
        "bundle_functions": list(BUNDLE_FUNCTIONS),
        "run_provenance": record,
    }
    if args.mode == MODE_ATTEST:
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
    report, _held = read_inventory(
        lambda: driver.connect(
            database_url, connect_timeout=8, autocommit=False, prepare_threshold=None
        ),
        captured,
    )
    published = redacted(report)
    failures = verdict(published, args.expect)
    return {
        **base,
        "mode": MODE_INVENTORY,
        "outcome": "INVENTORIED",
        "committed": False,
        "expect": args.expect,
        "verdict": "PASS" if not failures else "FAIL",
        "failures": failures,
        "inventory": published,
    }


def rehearse(
    args: argparse.Namespace, environ: Mapping[str, str], captured: dict[str, Any]
) -> dict[str, Any]:
    """The inventory, end to end, against the scratch database the rehearsal fixtures built.

    It connects as a role holding no privilege on any core table, so success proves the inventory
    reads catalogs only. It must then report exactly the planted surfaces as omitted.
    """

    url = environ.get(REHEARSAL_URL_VARIABLE, "")
    if not _LOCAL_SOCKET_URL.fullmatch(url):
        raise _refusal(
            f"{REHEARSAL_URL_VARIABLE} must be a local unix-socket URL, e.g. "
            "postgresql:///inventory_rehearsal?host=/var/run/postgresql"
        )
    if environ.get("SUPABASE_DB_URL"):
        raise _refusal("the rehearsal never runs where the production database secret is present")
    isolation = enter_isolated_runtime(args.wheelhouse) if args.wheelhouse else None
    driver = load_driver()
    if isolation is not None:
        attest_loaded_modules(isolation)
    report, held = read_inventory(
        lambda: driver.connect(url, connect_timeout=8, autocommit=False, prepare_threshold=None),
        captured,
        rehearsal=True,
    )
    published = redacted(report)
    failures = rehearsal_failures(published, held)
    if failures:
        captured["inventory"] = published
        raise _refusal("the rehearsal does not match its fixtures: " + "; ".join(failures))
    return {
        "schema_version": REPORT_SCHEMA,
        "mode": MODE_REHEARSE,
        "outcome": "REHEARSED",
        "committed": False,
        "omitted": [" ".join(row) for row in omitted(published)],
        "inventory": published,
    }


def read_inventory(
    open_connection: Callable[[], Any], captured: dict[str, Any], *, rehearsal: bool = False
) -> tuple[dict[str, Any], list[str]]:
    """The inventory of service_role in ONE read-only snapshot, always rolled back.

    With ``rehearsal``, also the core tables on which the connecting role itself holds anything.
    """

    held: list[str] = []
    with open_connection() as connection:
        try:
            with connection.cursor() as cursor:
                for statement in GUARD_STATEMENTS:
                    cursor.execute(statement)
                cursor.execute(TRANSACTION_READ_ONLY_SQL)
                read_only = _single(cursor.fetchone(), "read-only check")
                captured["transaction_read_only"] = read_only
                if read_only != "on":
                    raise _refusal(f"the server reports transaction_read_only={read_only!r}")
                cursor.execute(SERVER_VERSION_SQL)
                version = int(_single(cursor.fetchone(), "server version"))
                captured["maintain_inventoried"] = version >= 170000

                def execute(sql: str, values: dict[str, Any]) -> list[tuple]:
                    cursor.execute(sql, values)
                    return cursor.fetchall()

                report = collect(execute, role=ROLE, server_version_num=version)
                if rehearsal:
                    held = [
                        str(row[0])
                        for row in execute(REHEARSAL_HELD_SQL, {"core": list(CORE_TABLES)})
                    ]
        finally:
            connection.rollback()
    captured["rolled_back"] = True
    return report, held


def rehearsal_failures(report: Mapping[str, Any], held: Sequence[str]) -> list[str]:
    """Pure: what the rehearsal fixtures were built to show, and was not shown."""

    failures: list[str] = []
    if held:
        failures.append(
            f"the rehearsal role holds a privilege on {list(held)}: catalogs only is not proven"
        )
    left = omitted(report)
    strays = [" ".join(row) for row in left if REHEARSAL_MARKER not in " ".join(row)]
    if strays:
        failures.append(f"a surface outside the planted ones is omitted: {strays}")
    for kind in REHEARSAL_PLANTED_KINDS:
        if not any(row[0] == kind and REHEARSAL_MARKER in " ".join(row) for row in left):
            failures.append(f"the planted {kind} surface was not caught as omitted")
    for table in CORE_TABLES:
        if [table, "INSERT"] not in report["surfaces"]["T"]:
            failures.append(f"{ROLE} INSERT on {table} was not seen")
    return failures


def redacted(report: Mapping[str, Any]) -> dict[str, Any]:
    """The report as it may be published: every role name that is not reportable is withheld, and
    the server's version is reduced to whether MAINTAIN was inventoried (PostgreSQL 17 or later)."""

    clean = json.loads(json.dumps(report))
    version = clean.pop("server_version_num", 0)
    clean["maintain_inventoried"] = isinstance(version, int) and version >= 170000
    for kind, column in ROLE_COLUMNS.items():
        for row in clean["surfaces"][kind]:
            row[column] = reported_role(row[column])
    information = clean["information"]
    information["memberships"] = [[reported_role(row[0])] for row in information["memberships"]]
    information["default_privileges"] = [
        [reported_role(row[0]), row[1], row[2], reported_acl(row[3])]
        for row in information["default_privileges"]
    ]
    return clean


def reported_role(name: str) -> str:
    return name if name in REPORTED_ROLES or _REPORTED_ROLE.fullmatch(name) else WITHHELD


def reported_acl(acl: str) -> str:
    """An ACL's text, item by item: a name that is not reportable is withheld, and an item that
    does not parse (a quoted name, say) is withheld whole. PUBLIC's empty grantee stays empty."""

    items = []
    for item in acl.split(","):
        match = _ACL_ITEM.fullmatch(item)
        if match is None:
            items.append(WITHHELD)
            continue
        grantee = reported_role(match["grantee"]) if match["grantee"] else ""
        items.append(f"{grantee}={match['privileges']}/{reported_role(match['grantor'])}")
    return ",".join(items)


def _single(row: Any, what: str) -> Any:
    if row is None or len(row) != 1:
        raise _refusal(f"the {what} returned {row!r}, not one value")
    return row[0]


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

    return ProvenanceRefused(f"core-write inventory refused: {message}")


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
    text = json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())
