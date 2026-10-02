#!/usr/bin/env python
"""Apply migration 0015, the B9 forecast-bundle RPC (governing plan §8.1), ONCE.

    --mode attest     verify isolation, dispatch and runtime; touches no database
    --mode rehearse   the whole apply against a scratch local PostgreSQL: apply once, then prove
                      that a second apply refuses; never where the production secret is present,
                      never over the network
    --mode apply      THE ONE-SHOT APPLY; requires the confirmation token

Run only by ``.github/workflows/apply-migration-0015.yml``, as ``python -I -S -B``, inside the
closed trust boundary of the other database routes: exact CPython 3.13.14, CPython's bundled pip
and lock-authenticated wheels, with the dispatch verified HERE against THIS workflow in the owner
repository. The bulk scripts/apply_migrations.py applies every migration and is never used for it.

WHAT IT CHANGES, AND WHAT IT PROVES DOES NOT CHANGE. Migration 0015 adds ONE function,
``public.save_prediction_bundle(p_prediction jsonb, p_feature_snapshot jsonb,
p_derivatives_snapshot jsonb)``: the REST writer's atomic, idempotent forecast bundle, called
through PostgREST as one request (one transaction). It is SECURITY INVOKER with a fixed
search_path, and only service_role may execute it. No table, column, constraint, index, trigger,
policy or table privilege changes. This route refuses unless production is ready for exactly that:
- predictions, prediction_feature_snapshots and prediction_derivatives_snapshots each exist once, in
  ``public``, as ordinary tables on which service_role holds INSERT and SELECT (the function runs
  with its caller's privileges, so without them it could never write);
- the applying role may CREATE in schema ``public``;
- no function of that name exists yet (otherwise this is not a first apply, so a second dispatch
  refuses and the one-shot property is enforced by the database itself).

ONE TRANSACTION, FAIL CLOSED. Under bounded timeouts and an advisory lock:
  1. read-only PRE-CHECKS, as above. Recorded, not required: the three tables' security, columns,
     constraints, indexes and triggers; the security and the whole schema fingerprint (columns,
     constraints, indexes, triggers, policies) of every other table of migrations 0001-0014; the
     schema's privileges; the database's event triggers. The server's version decides which table
     privileges are asked about, so no check is blind to one the server can grant;
  2. exactly the pinned bytes of migration 0015, with no parameters;
  3. read-only catalog POST-CHECKS refuse unless:
     - the function exists once: plpgsql, returning jsonb, exactly its three jsonb arguments,
       VOLATILE, SECURITY INVOKER, a plain function owned by the applying role, search_path exactly
       pg_catalog, pg_temp, exactly the reviewed body, and EXECUTE for service_role and for none of
       PUBLIC, anon and authenticated;
     - every column, constraint, index and trigger of the three tables, their security, the
       schema's privileges, every other table's security and schema fingerprint, and the event
       triggers, are exactly as they were.
Any refusal or error rolls the transaction back, so nothing is applied; only then is it committed.
If the connection fails while the COMMIT is in flight, the report says ``committed`` is UNKNOWN.
Had it committed, a second dispatch would refuse as not a first apply.
No application row is ever read or written: every check reads only the catalog. The function's
behaviour (insert, identical replay, conflicting refusal, whole-bundle rollback, malformed refusal,
the API roles refused) is proven on the scratch rehearsals, against exactly these pinned bytes.

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
SCRIPT = "scripts/apply_migration_0015.py"
WORKFLOW = ".github/workflows/apply-migration-0015.yml"
MIGRATION = "migrations/0015_prediction_bundle_rpc.sql"
# The reviewed bytes. A different file on the dispatched commit refuses before any connection.
MIGRATION_SHA256 = "b3a9fa099e266d1a7b2840625f57365c6c819730162011be6a3ca30064276bca"
CONFIRMATION = "APPLY-MIGRATION-0015-ONCE"
REPORT_SCHEMA = "migration-0015-apply-report.v1"
DISPATCH_SCHEMA = "migration-0015-dispatch.v1"
MODE_ATTEST = "attest"
MODE_REHEARSE = "rehearse"
MODE_APPLY = "apply"
REQUIRED_EVENT = "workflow_dispatch"
REQUIRED_REF = "refs/heads/main"
# The owner repository, pinned: a fork's run carries a self-consistent identity of its own.
EXPECTED_REPOSITORY = "tranbeny053-hub/v83-stock-cron"
PINNED_PYTHON = ("CPython", "3.13.14")

# CREATE FUNCTION takes no table lock: the timeouts only bound a stuck catalog or connection.
TIMEOUT_STATEMENTS = (
    "SET LOCAL lock_timeout = '10s'",
    "SET LOCAL statement_timeout = '120s'",
)
# A fixed key, distinct from every other route's: two appliers of 0015 serialize.
ADVISORY_LOCK_SQL = "SELECT pg_advisory_xact_lock(5000015)"

API_ROLES = ("anon", "authenticated", "service_role")
# The three tables the function writes, sorted as the checks return them.
TARGET_TABLES = (
    "prediction_derivatives_snapshots",
    "prediction_feature_snapshots",
    "predictions",
)
# service_role's privileges the function needs on each, since it runs with its caller's.
REQUIRED_SERVICE_ROLE_PRIVILEGES = ("INSERT", "SELECT")
FUNCTION = "save_prediction_bundle"
FUNCTION_REFERENCE = f"public.{FUNCTION}"
FUNCTION_ARGUMENTS = "p_prediction jsonb, p_feature_snapshot jsonb, p_derivatives_snapshot jsonb"
FUNCTION_CONFIG = ("search_path=pg_catalog, pg_temp",)
_BODY_OPEN = "AS $function$"
_BODY_CLOSE = "$function$;"


def function_source(migration_sql: str) -> str:
    """Pure: the function body exactly as the migration writes it between its dollar quotes,
    which is what pg_proc.prosrc stores."""

    start = migration_sql.index(_BODY_OPEN) + len(_BODY_OPEN)
    return migration_sql[start:migration_sql.index(_BODY_CLOSE, start)]


# Every other table migrations 0001-0014 create. 0015 never touches them, so their security and
# schema must be exactly the same after the apply. A test re-derives this list from the migration
# files, so it cannot drift from them.
OTHER_TABLES = (
    "analysis_run_details",
    "analysis_runs",
    "analysis_timeframe_results",
    "app_events",
    "automation_credential",
    "automation_radar_ledger",
    "news_clusters",
    "news_evidence_links",
    "news_items",
    "prediction_outcomes",
    "prediction_resolution_status",
    "provider_observations",
    "section_5a_evaluation_seal",
    "watchlist",
)
# The table privileges of every supported server, sorted as the checks return them.
TABLE_PRIVILEGES = ("DELETE", "INSERT", "REFERENCES", "SELECT", "TRIGGER", "TRUNCATE", "UPDATE")
# PostgreSQL 17 added MAINTAIN, and production runs 17. On such a server every check also asks
# about MAINTAIN; on an older one, such as the CI rehearsal's 16, asking would fail.
MAINTAIN_SINCE_SERVER_VERSION = 170000
MINIMUM_SERVER_VERSION = 150000
TABLE_PRIVILEGES_WITH_MAINTAIN = tuple(sorted((*TABLE_PRIVILEGES, "MAINTAIN")))
SERVER_VERSION_SQL = "SELECT pg_catalog.current_setting('server_version_num')::integer"

_API_ROLES_SQL = ", ".join(f"'{role}'" for role in API_ROLES)


# table_privileges_for, _held and _security_sql are copied from scripts/apply_migration_0011.py,
# never imported: this route loads only the standard library, the evaluator pin and itself. A test
# requires both routes to produce the same SQL.
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


def targets_security_sql(server_version: int) -> str:
    return _security_sql(TARGET_TABLES, table_privileges_for(server_version))


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


def _tables_sql(names: Sequence[str]) -> str:
    """The listed tables, each resolved in ``public`` as the security check resolves it."""

    listed = ", ".join(f"('{name}')" for name in names)
    return (
        f"(SELECT t.name, pg_catalog.to_regclass('public.' || t.name) AS oid"
        f" FROM (VALUES {listed}) AS t(name)) AS t"
    )


_TARGETS = _tables_sql(TARGET_TABLES)
_OTHERS = _tables_sql(OTHER_TABLES)
# Every live column of the three tables, keyed "table.column", in table then physical order.
COLUMNS_SQL = (
    "SELECT t.name || '.' || a.attname::text,"
    " pg_catalog.format_type(a.atttypid, a.atttypmod),"
    " a.attnotnull, a.atthasdef, a.attidentity <> '', a.attgenerated <> '',"
    " a.attacl IS NOT NULL"
    f" FROM {_TARGETS}"
    " JOIN pg_catalog.pg_attribute AS a ON a.attrelid = t.oid"
    " WHERE a.attnum > 0 AND NOT a.attisdropped"
    ' ORDER BY t.name COLLATE "C", a.attnum'
)
COLUMN_FIELDS = ("item", "type", "not_null", "has_default", "identity", "generated", "column_acl")
# Their constraints, "table.constraint", with the server's own deparse and the columns each one
# references, sorted (none when conkey is NULL).
CONSTRAINTS_SQL = (
    "SELECT t.name || '.' || c.conname::text, c.contype::text, c.convalidated, c.condeferrable,"
    " pg_catalog.pg_get_constraintdef(c.oid),"
    " ARRAY(SELECT a.attname::text FROM pg_catalog.pg_attribute AS a"
    " WHERE a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)"
    ' ORDER BY a.attname::text COLLATE "C")'
    f" FROM {_TARGETS}"
    " JOIN pg_catalog.pg_constraint AS c ON c.conrelid = t.oid"
    ' ORDER BY t.name COLLATE "C", c.conname::text COLLATE "C"'
)
CONSTRAINT_FIELDS = ("item", "type", "validated", "deferrable", "definition", "columns")
INDEXES_SQL = (
    "SELECT t.name || '.' || i.relname::text, pg_catalog.pg_get_indexdef(x.indexrelid)"
    f" FROM {_TARGETS}"
    " JOIN pg_catalog.pg_index AS x ON x.indrelid = t.oid"
    " JOIN pg_catalog.pg_class AS i ON i.oid = x.indexrelid"
    ' ORDER BY t.name COLLATE "C", i.relname::text COLLATE "C"'
)
INDEX_FIELDS = ("item", "definition")
# Triggers the server creates for a constraint are internal: the constraints check covers those.
TRIGGERS_SQL = (
    "SELECT t.name || '.' || g.tgname::text, g.tgenabled::text, g.tgtype::integer,"
    " n.nspname::text || '.' || p.proname::text, g.tgnargs::integer,"
    " g.tgqual IS NOT NULL, g.tgconstraint <> 0"
    f" FROM {_TARGETS}"
    " JOIN pg_catalog.pg_trigger AS g ON g.tgrelid = t.oid"
    " JOIN pg_catalog.pg_proc AS p ON p.oid = g.tgfoid"
    " JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace"
    " WHERE NOT g.tgisinternal"
    ' ORDER BY t.name COLLATE "C", g.tgname::text COLLATE "C"'
)
TRIGGER_FIELDS = (
    "item", "enabled", "type", "function", "arguments", "has_when", "constraint_trigger",
)
# Every function of the new function's name in public, whatever its arguments.
FUNCTIONS_SQL = (
    "SELECT p.proname::text, pg_catalog.pg_get_function_identity_arguments(p.oid),"
    " pg_catalog.format_type(p.prorettype, NULL), l.lanname::text, p.prosecdef, p.prokind::text,"
    " p.provolatile::text, COALESCE(p.proconfig, ARRAY[]::text[]),"
    " pg_catalog.pg_get_userbyid(p.proowner) = current_user, p.prosrc,"
    " pg_catalog.has_function_privilege('public', p.oid, 'EXECUTE'),"
    " pg_catalog.has_function_privilege('anon', p.oid, 'EXECUTE'),"
    " pg_catalog.has_function_privilege('authenticated', p.oid, 'EXECUTE'),"
    " pg_catalog.has_function_privilege('service_role', p.oid, 'EXECUTE')"
    " FROM pg_catalog.pg_proc AS p"
    " JOIN pg_catalog.pg_language AS l ON l.oid = p.prolang"
    f" WHERE p.pronamespace = 'public'::regnamespace AND p.proname = '{FUNCTION}'"
    ' ORDER BY pg_catalog.pg_get_function_identity_arguments(p.oid) COLLATE "C"'
)
FUNCTION_FIELDS = (
    "function", "arguments", "returns", "language", "security_definer", "kind", "volatility",
    "config", "owned_by_applying_role", "source", "execute_public", "execute_anon",
    "execute_authenticated", "execute_service_role",
)
# The schema the function is created in: the applying role must be allowed to CREATE in it, and
# its owner and privileges must not change.
SCHEMA_SQL = (
    "SELECT n.nspname::text, pg_catalog.pg_get_userbyid(n.nspowner),"
    " COALESCE(n.nspacl::text, ''),"
    " pg_catalog.has_schema_privilege(current_user, n.oid, 'CREATE')"
    " FROM pg_catalog.pg_namespace AS n WHERE n.nspname = 'public'"
)
SCHEMA_FIELDS = ("schema", "owner", "acl", "applying_role_may_create")
# The whole schema fingerprint of every other table, one row per item: "table/kind/name" -> detail.
OTHER_SCHEMA_SQL = (
    "SELECT item, detail FROM ("
    "SELECT t.name || '/column/' || a.attname::text AS item,"
    " pg_catalog.format_type(a.atttypid, a.atttypmod) || ' notnull=' || a.attnotnull::text"
    " || ' default=' || COALESCE(pg_catalog.pg_get_expr(d.adbin, d.adrelid), '')"
    " || ' acl=' || COALESCE(a.attacl::text, '') AS detail"
    f" FROM {_OTHERS}"
    " JOIN pg_catalog.pg_attribute AS a ON a.attrelid = t.oid"
    " LEFT JOIN pg_catalog.pg_attrdef AS d ON d.adrelid = a.attrelid AND d.adnum = a.attnum"
    " WHERE a.attnum > 0 AND NOT a.attisdropped"
    " UNION ALL"
    " SELECT t.name || '/constraint/' || c.conname::text,"
    " c.contype::text || ' validated=' || c.convalidated::text || ' '"
    " || pg_catalog.pg_get_constraintdef(c.oid)"
    f" FROM {_OTHERS}"
    " JOIN pg_catalog.pg_constraint AS c ON c.conrelid = t.oid"
    " UNION ALL"
    " SELECT t.name || '/index/' || i.relname::text, pg_catalog.pg_get_indexdef(x.indexrelid)"
    f" FROM {_OTHERS}"
    " JOIN pg_catalog.pg_index AS x ON x.indrelid = t.oid"
    " JOIN pg_catalog.pg_class AS i ON i.oid = x.indexrelid"
    " UNION ALL"
    " SELECT t.name || '/trigger/' || g.tgname::text,"
    " g.tgenabled::text || ' ' || g.tgtype::text || ' ' || g.tgfoid::regproc::text"
    f" FROM {_OTHERS}"
    " JOIN pg_catalog.pg_trigger AS g ON g.tgrelid = t.oid"
    " WHERE NOT g.tgisinternal"
    " UNION ALL"
    " SELECT t.name || '/policy/' || p.polname::text,"
    " p.polcmd::text || ' ' || p.polpermissive::text || ' '"
    " || COALESCE(pg_catalog.pg_get_expr(p.polqual, p.polrelid), '') || ' '"
    " || COALESCE(pg_catalog.pg_get_expr(p.polwithcheck, p.polrelid), '')"
    f" FROM {_OTHERS}"
    " JOIN pg_catalog.pg_policy AS p ON p.polrelid = t.oid"
    ') AS fingerprint ORDER BY item COLLATE "C"'
)
OTHER_SCHEMA_FIELDS = ("item", "detail")
EVENT_TRIGGERS_SQL = (
    "SELECT e.evtname::text, e.evtevent::text, e.evtenabled::text, e.evtfoid::regproc::text,"
    " COALESCE(pg_catalog.array_to_string(e.evttags, ','), '')"
    " FROM pg_catalog.pg_event_trigger AS e"
    ' ORDER BY e.evtname::text COLLATE "C"'
)
EVENT_TRIGGER_FIELDS = ("event_trigger", "event", "enabled", "function", "tags")
NOT_A_FIRST_APPLY = "this is not a first apply"
COMMIT_UNKNOWN = "UNKNOWN"

# The rehearsal reaches only a local server through its unix socket: never a network host.
_LOCAL_SOCKET_URL = re.compile(r"postgresql:///[a-z_][a-z0-9_]*\?host=/var/run/postgresql")
REHEARSAL_URL_VARIABLE = "MIGRATION_0015_REHEARSAL_URL"
# The function body the post-check requires: read from the migration file itself, whose bytes
# migration_bytes() pins before anything runs.
FUNCTION_SOURCE = function_source((ROOT / MIGRATION).read_text(encoding="utf-8"))
_COMMIT_SHA = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_DIGITS = re.compile(r"[0-9]+")
def read_only_checks(server_version: int) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    """(name, query, fields) of every check, read in this order before and after the migration."""

    return (
        ("targets", targets_security_sql(server_version), SECURITY_FIELDS),
        ("columns", COLUMNS_SQL, COLUMN_FIELDS),
        ("constraints", CONSTRAINTS_SQL, CONSTRAINT_FIELDS),
        ("indexes", INDEXES_SQL, INDEX_FIELDS),
        ("triggers", TRIGGERS_SQL, TRIGGER_FIELDS),
        ("functions", FUNCTIONS_SQL, FUNCTION_FIELDS),
        ("schema", SCHEMA_SQL, SCHEMA_FIELDS),
        ("other", other_security_sql(server_version), SECURITY_FIELDS),
        ("other_schema", OTHER_SCHEMA_SQL, OTHER_SCHEMA_FIELDS),
        ("event_triggers", EVENT_TRIGGERS_SQL, EVENT_TRIGGER_FIELDS),
    )


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

    The scratch database is built from migrations 0001-0014 with Supabase-like roles and default
    privileges, as the role this process connects as, exactly as production's applying role holds
    them: the function must come out executable by service_role only.
    """

    url = environ.get(REHEARSAL_URL_VARIABLE, "")
    if not _LOCAL_SOCKET_URL.fullmatch(url):
        raise _refusal(
            f"{REHEARSAL_URL_VARIABLE} must be a local unix-socket URL, e.g. "
            "postgresql:///migration_0015_rehearsal?host=/var/run/postgresql"
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
            checks = read_only_checks(server_version)

            # Every pre-read first, each captured as it arrives; then one verdict naming them all.
            pre = _read_checks(cursor, checks, captured, "pre")
            failures = pre_check_failures(pre)
            if failures:
                raise _refusal(
                    "the database is not in the state a first apply of 0015 requires: "
                    + "; ".join(failures)
                )

            cursor.execute(migration_sql)
            captured["executed_migration_sha256"] = hashlib.sha256(
                migration_sql.encode("utf-8")
            ).hexdigest()

            post = _read_checks(cursor, checks, captured, "post")
            failures = post_check_failures(pre, post)
            if failures:
                raise _refusal(
                    "the applied result is not the reviewed one, so the transaction is rolled "
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
        **{f"pre_{name}": rows for name, rows in pre.items()},
        "executed_migration_sha256": captured["executed_migration_sha256"],
        **{f"post_{name}": rows for name, rows in post.items()},
        "committed": True,
    }


def pre_check_failures(pre: Mapping[str, Sequence[Mapping[str, Any]]]) -> list[str]:
    """Pure: every way the database differs from the state a first apply of 0015 requires."""

    return (
        targets_pre_check_failures(pre["targets"])
        + schema_pre_check_failures(pre["schema"])
        + function_pre_check_failures(pre["functions"])
        + other_pre_check_failures(pre["other"])
    )


def targets_pre_check_failures(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Their shape and service_role's INSERT and SELECT are required; the rest is recorded.

    The function writes them with its caller's privileges, so service_role must hold INSERT and
    SELECT on each. Their ownership, row-level security, policies and other privileges are earlier
    migrations': 0015 only has to leave them unchanged.
    """

    if [row.get("table") for row in rows] != list(TARGET_TABLES):
        return [f"the target tables read were {[row.get('table') for row in rows]}"]
    failures: list[str] = []
    for row in rows:
        table = row.get("table")
        if row.get("relations_named_so") != 1:
            failures.append(
                f"{table}: {row.get('relations_named_so')!r} relations have this name, not one"
            )
        if row.get("relkind") != "r":
            failures.append(f"{table}: is {row.get('relkind')!r}, not an ordinary table")
        held = row.get("service_role")
        missing = [
            privilege
            for privilege in REQUIRED_SERVICE_ROLE_PRIVILEGES
            if not isinstance(held, list) or privilege not in held
        ]
        if missing:
            failures.append(
                f"{table}: service_role lacks {', '.join(missing)}, which the SECURITY INVOKER "
                "function needs to write it"
            )
    return failures


def schema_pre_check_failures(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    if len(rows) != 1 or rows[0].get("schema") != "public":
        return [f"the schema public was read as {list(rows)!r}"]
    if rows[0].get("applying_role_may_create") is not True:
        return ["the applying role may not CREATE in schema public"]
    return []


def function_pre_check_failures(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    return [
        f"{NOT_A_FIRST_APPLY}: the function {FUNCTION_REFERENCE}({row.get('arguments')}) "
        "already exists"
        for row in rows
    ]


def other_pre_check_failures(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """The other tables are recorded, not required.

    0015 never touches them, and the post-check requires their security and schema to be identical
    after the apply, whatever they are. Only a malformed read refuses.
    """

    if [row.get("table") for row in rows] != sorted(OTHER_TABLES):
        return [f"the other tables read were {[row.get('table') for row in rows]}"]
    return []


def post_check_failures(
    pre: Mapping[str, Sequence[Mapping[str, Any]]],
    post: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[str]:
    """Pure: every way the applied database differs from the reviewed result."""

    return (
        _unchanged_failures("security of table", "table", pre["targets"], post["targets"])
        + _unchanged_failures("column", "item", pre["columns"], post["columns"])
        + _unchanged_failures("constraint", "item", pre["constraints"], post["constraints"])
        + _unchanged_failures("index", "item", pre["indexes"], post["indexes"])
        + _unchanged_failures("trigger", "item", pre["triggers"], post["triggers"])
        + function_post_check_failures(post["functions"])
        + _unchanged_failures("schema", "schema", pre["schema"], post["schema"])
        + _unchanged_failures("security of table", "table", pre["other"], post["other"])
        + _unchanged_failures("schema item", "item", pre["other_schema"], post["other_schema"])
        + _unchanged_failures(
            "event trigger", "event_trigger", pre["event_triggers"], post["event_triggers"]
        )
    )


def function_post_check_failures(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Pure: exactly one new function, as reviewed, executable by service_role only."""

    if len(rows) != 1:
        return [f"{FUNCTION_REFERENCE}: {_count_after(rows)}"]
    row = rows[0]
    expected = {
        "arguments": FUNCTION_ARGUMENTS,
        "returns": "jsonb",
        "language": "plpgsql",
        "security_definer": False,
        "kind": "f",
        "volatility": "v",
        "config": list(FUNCTION_CONFIG),
        "owned_by_applying_role": True,
        "source": FUNCTION_SOURCE,
        "execute_public": False,
        "execute_anon": False,
        "execute_authenticated": False,
        "execute_service_role": True,
    }
    return [
        f"{FUNCTION_REFERENCE}: {field} is {row.get(field)!r}, not {value!r}"
        for field, value in expected.items()
        if row.get(field) != value
    ]


def _count_after(found: Sequence[Mapping[str, Any]]) -> str:
    if not found:
        return "is missing after the apply"
    return f"appears {len(found)} times after the apply, not once"


def _unchanged_failures(
    what: str, key: str, pre: Sequence[Mapping[str, Any]], post: Sequence[Mapping[str, Any]]
) -> list[str]:
    """Pure: nothing when ``post`` is exactly ``pre``; otherwise every difference, by ``key``."""

    if list(post) == list(pre):
        return []
    before = {row.get(key): row for row in pre}
    after = {row.get(key): row for row in post}
    failures: list[str] = []
    for name in sorted({*before, *after}, key=repr):
        if name not in after:
            failures.append(f"the {what} {name!r} is gone after the apply")
        elif name not in before:
            failures.append(f"the {what} {name!r} appeared during the apply")
        elif after[name] != before[name]:
            fields = sorted({*before[name], *after[name]})
            changed = ", ".join(
                f"{field} {before[name].get(field)!r} -> {after[name].get(field)!r}"
                for field in fields
                if before[name].get(field) != after[name].get(field)
            )
            failures.append(f"the {what} {name!r} changed during the apply: {changed}")
    return failures or [f"the {what} rows changed in order or number during the apply"]


def _read_checks(
    cursor: Any,
    checks: Sequence[tuple[str, str, tuple[str, ...]]],
    captured: dict[str, Any],
    when: str,
) -> dict[str, list[dict[str, Any]]]:
    results: dict[str, list[dict[str, Any]]] = {}
    for name, query, fields in checks:
        results[name] = _rows(cursor, query, fields)
        captured[f"{when}_{name}"] = results[name]
    return results


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

    return ProvenanceRefused(f"migration 0015 refused; nothing is applied: {message}")


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
