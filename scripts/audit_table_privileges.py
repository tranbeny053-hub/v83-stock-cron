#!/usr/bin/env python
"""Read-only privilege and exposure audit of the tables that migrations 0001-0004 and 0007 shape.

    --mode attest     verify isolation, dispatch and runtime; touches no database
    --mode rehearse   the same audit against a scratch local PostgreSQL built from the migrations;
                      never where the production secret is present, never over the network
    --mode audit      THE READ-ONLY AUDIT; requires the confirmation token

Owner ruling 2026-09-16: "strictly read-only metadata only for tables from migrations 0001-0004 and
0007: RLS, grants to PUBLIC/anon/authenticated/service_role, policies, ownership/schema exposure; no
application-row reads and no mutation."

WHY: 0005, 0006, 0008 and 0009 enable row-level security and REVOKE the Supabase API roles; the
older migrations do neither, so whether production exposes those tables through the Data API
depends on the project's live grants. This measures them instead of assuming.

Run only by ``.github/workflows/audit-table-privileges.yml``, as ``python -I -S -B``, inside the
closed trust boundary of the other database routes (exact CPython, bundled pip, lock-authenticated
wheels), with the dispatch verified against THIS workflow in the owner repository.

READ ONLY, CATALOGS ONLY, NEVER COMMITTED:
- the first statement makes the transaction READ ONLY, on one REPEATABLE READ snapshot; the audit
  refuses unless the server says it is read only;
- every query reads PostgreSQL catalogs (``pg_catalog``) only. No application table is ever named
  in a FROM clause, so no application row can be read;
- optional queries run inside savepoints, so one refused catalog read is recorded, not fatal;
- the transaction is ROLLED BACK; nothing is ever committed;
- only standard role names are reported; the connecting role's name is never reported, nor is the
  database URL. An unexpected failure is reported by its type only.

WHO MAY DO WHAT IS DECIDED BY THE SERVER, NEVER RE-IMPLEMENTED HERE. Role membership and its
INHERIT options, PUBLIC, table ownership (an owner bypasses row-level security unless it is forced),
the roles a policy applies to, and column privileges are all read through PostgreSQL's own
functions (``pg_has_role``, ``has_table_privilege``, ``has_column_privilege``), which apply exactly
the rules the server enforces. A fact the server did not return counts as a possible exposure and
makes the result INCOMPLETE; it never counts as safe.

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
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
SCRIPT = "scripts/audit_table_privileges.py"
WORKFLOW = ".github/workflows/audit-table-privileges.yml"
CONFIRMATION = "READ-ONLY-AUDIT-OLDER-TABLES-ONCE"
REPORT_SCHEMA = "older-table-privilege-audit.v1"
DISPATCH_SCHEMA = "older-table-privilege-audit-dispatch.v1"
MODE_ATTEST = "attest"
MODE_AUDIT = "audit"
MODE_REHEARSE = "rehearse"
REQUIRED_EVENT = "workflow_dispatch"
REQUIRED_REF = "refs/heads/main"
EXPECTED_REPOSITORY = "tranbeny053-hub/v83-stock-cron"
PINNED_PYTHON = ("CPython", "3.13.14")

# The tables migrations 0001-0004 create; 0007 only alters predictions. A test re-derives this from
# the migration files, so the list cannot drift from them.
AUDIT_MIGRATIONS = (
    "migrations/0001_init.sql",
    "migrations/0002_news.sql",
    "migrations/0003_prediction_ledger.sql",
    "migrations/0004_prediction_outcomes.sql",
    "migrations/0007_prediction_origin.sql",
)
AUDITED_TABLES = (
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
API_ROLES = ("anon", "authenticated", "service_role")
PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
# The Data API reaches a table only through these commands; TRUNCATE, REFERENCES and TRIGGER are
# reported but have no PostgREST endpoint.
API_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE")
# The API commands PostgreSQL can also grant on single columns; DELETE is table-level only.
COLUMN_PRIVILEGES = ("SELECT", "INSERT", "UPDATE")
WITHHELD = "<non-standard role name withheld>"

_IDENTIFIER = re.compile(r"[a-z_][a-z0-9_]*")
_TABLES_SQL = "ARRAY[" + ", ".join(f"'{name}'" for name in AUDITED_TABLES) + "]::text[]"
_ROLES_SQL = "ARRAY[" + ", ".join(f"'{name}'" for name in API_ROLES) + "]::text[]"
_PRIVILEGES_SQL = ", ".join(f"('{name}')" for name in PRIVILEGES)
_COLUMN_PRIVILEGES_SQL = ", ".join(f"('{name}')" for name in COLUMN_PRIVILEGES)
_RELKINDS_SQL = "ARRAY['r', 'p', 'v', 'm', 'f']::\"char\"[]"

GUARD_STATEMENTS = (
    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY",
    "SET LOCAL statement_timeout = '30s'",
    "SET LOCAL lock_timeout = '5s'",
)
READ_ONLY_SQL = "SELECT pg_catalog.current_setting('transaction_read_only')"

QUERIES: dict[str, str] = {
    "roles": (
        "SELECT r.rolname, r.rolsuper, r.rolbypassrls, r.rolinherit, r.rolcanlogin"
        " FROM pg_catalog.pg_roles AS r"
        f" WHERE r.rolname::text = ANY ({_ROLES_SQL}) ORDER BY r.rolname"
    ),
    "role_memberships": (
        "SELECT r.rolname, m.rolname"
        " FROM pg_catalog.pg_auth_members AS am"
        " JOIN pg_catalog.pg_roles AS r ON r.oid = am.member"
        " JOIN pg_catalog.pg_roles AS m ON m.oid = am.roleid"
        f" WHERE r.rolname::text = ANY ({_ROLES_SQL}) ORDER BY 1, 2"
    ),
    # Every role whose privileges an API role holds without SET ROLE, as the server resolves
    # membership chains and their INHERIT options (PostgreSQL 15: rolinherit; 16+: per grant).
    "role_inheritance": (
        "SELECT r.rolname, o.rolname"
        " FROM pg_catalog.pg_roles AS r"
        " CROSS JOIN pg_catalog.pg_roles AS o"
        f" WHERE r.rolname::text = ANY ({_ROLES_SQL}) AND o.oid <> r.oid"
        " AND pg_catalog.pg_has_role(r.oid, o.oid, 'USAGE')"
        " ORDER BY 1, 2"
    ),
    "tables": (
        "SELECT n.nspname, c.relname, c.relkind::text, pg_catalog.pg_get_userbyid(c.relowner),"
        " c.relrowsecurity, c.relforcerowsecurity,"
        " pg_catalog.pg_get_userbyid(c.relowner) = current_user"
        " FROM pg_catalog.pg_class AS c"
        " JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace"
        f" WHERE c.relname::text = ANY ({_TABLES_SQL}) AND c.relkind = ANY ({_RELKINDS_SQL})"
        " ORDER BY c.relname, n.nspname"
    ),
    # Whether an API role counts as the table's owner: the owner itself, or a role holding the
    # owner's privileges. Such a role bypasses row-level security unless the table forces it.
    "owner_equivalence": (
        "SELECT n.nspname, c.relname, r.rolname,"
        " pg_catalog.pg_has_role(r.oid, c.relowner, 'USAGE')"
        " FROM pg_catalog.pg_class AS c"
        " JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace"
        " CROSS JOIN pg_catalog.pg_roles AS r"
        f" WHERE c.relname::text = ANY ({_TABLES_SQL}) AND c.relkind = ANY ({_RELKINDS_SQL})"
        f" AND r.rolname::text = ANY ({_ROLES_SQL})"
        " ORDER BY 1, 2, 3"
    ),
    "table_grants": (
        "SELECT n.nspname, c.relname,"
        " CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_catalog.pg_get_userbyid(a.grantee) END,"
        " a.privilege_type, a.is_grantable"
        " FROM pg_catalog.pg_class AS c"
        " JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace"
        " CROSS JOIN LATERAL pg_catalog.aclexplode("
        "COALESCE(c.relacl, pg_catalog.acldefault('r', c.relowner))) AS a"
        f" WHERE c.relname::text = ANY ({_TABLES_SQL}) AND c.relkind = ANY ({_RELKINDS_SQL})"
        " AND (a.grantee = 0"
        f" OR pg_catalog.pg_get_userbyid(a.grantee)::text = ANY ({_ROLES_SQL}))"
        " ORDER BY 1, 2, 3, 4"
    ),
    "effective_privileges": (
        "SELECT n.nspname, c.relname, r.rolname, p.privilege,"
        " pg_catalog.has_table_privilege(r.oid, c.oid, p.privilege)"
        " FROM pg_catalog.pg_class AS c"
        " JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace"
        " CROSS JOIN pg_catalog.pg_roles AS r"
        f" CROSS JOIN (VALUES {_PRIVILEGES_SQL}) AS p(privilege)"
        f" WHERE c.relname::text = ANY ({_TABLES_SQL}) AND c.relkind = ANY ({_RELKINDS_SQL})"
        f" AND r.rolname::text = ANY ({_ROLES_SQL})"
        " ORDER BY 1, 2, 3, 4"
    ),
    "column_grants": (
        "SELECT n.nspname, c.relname, att.attname,"
        " CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_catalog.pg_get_userbyid(a.grantee) END,"
        " a.privilege_type"
        " FROM pg_catalog.pg_class AS c"
        " JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace"
        " JOIN pg_catalog.pg_attribute AS att ON att.attrelid = c.oid"
        " AND att.attnum > 0 AND NOT att.attisdropped AND att.attacl IS NOT NULL"
        " CROSS JOIN LATERAL pg_catalog.aclexplode(att.attacl) AS a"
        f" WHERE c.relname::text = ANY ({_TABLES_SQL}) AND c.relkind = ANY ({_RELKINDS_SQL})"
        " AND (a.grantee = 0"
        f" OR pg_catalog.pg_get_userbyid(a.grantee)::text = ANY ({_ROLES_SQL}))"
        " ORDER BY 1, 2, 3, 4, 5"
    ),
    # The columns an API role may use for a command it does NOT hold on the whole table, whether
    # granted to the role, to PUBLIC or to a role it inherits from.
    "column_privileges": (
        "SELECT n.nspname, c.relname, att.attname, r.rolname, p.privilege"
        " FROM pg_catalog.pg_class AS c"
        " JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace"
        " JOIN pg_catalog.pg_attribute AS att ON att.attrelid = c.oid"
        " AND att.attnum > 0 AND NOT att.attisdropped"
        " CROSS JOIN pg_catalog.pg_roles AS r"
        f" CROSS JOIN (VALUES {_COLUMN_PRIVILEGES_SQL}) AS p(privilege)"
        f" WHERE c.relname::text = ANY ({_TABLES_SQL}) AND c.relkind = ANY ({_RELKINDS_SQL})"
        f" AND r.rolname::text = ANY ({_ROLES_SQL})"
        " AND pg_catalog.has_column_privilege(r.oid, c.oid, att.attnum, p.privilege)"
        " AND NOT pg_catalog.has_table_privilege(r.oid, c.oid, p.privilege)"
        " ORDER BY 1, 2, 4, 5, att.attnum"
    ),
    "policies": (
        "SELECT p.schemaname::text, p.tablename::text, p.policyname::text, p.permissive,"
        " p.roles::text[], p.cmd, p.qual, p.with_check"
        " FROM pg_catalog.pg_policies AS p"
        f" WHERE p.tablename::text = ANY ({_TABLES_SQL})"
        " ORDER BY 1, 2, 3"
    ),
    # Whether each policy applies to each API role, as the server decides it: a policy for PUBLIC
    # applies to everyone, otherwise to any role holding the privileges of a role it names.
    "policy_applicability": (
        "SELECT n.nspname, c.relname, pol.polname, r.rolname,"
        " (0::pg_catalog.oid = ANY (pol.polroles) OR EXISTS ("
        "SELECT 1 FROM pg_catalog.unnest(pol.polroles) AS pr(roleid)"
        " WHERE pr.roleid <> 0 AND pg_catalog.pg_has_role(r.oid, pr.roleid, 'USAGE')))"
        " FROM pg_catalog.pg_policy AS pol"
        " JOIN pg_catalog.pg_class AS c ON c.oid = pol.polrelid"
        " JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace"
        " CROSS JOIN pg_catalog.pg_roles AS r"
        f" WHERE c.relname::text = ANY ({_TABLES_SQL}) AND c.relkind = ANY ({_RELKINDS_SQL})"
        f" AND r.rolname::text = ANY ({_ROLES_SQL})"
        " ORDER BY 1, 2, 3, 4"
    ),
    "schema_usage": (
        "SELECT n.nspname, pg_catalog.pg_get_userbyid(n.nspowner), r.rolname,"
        " pg_catalog.has_schema_privilege(r.oid, n.oid, 'USAGE')"
        " FROM pg_catalog.pg_namespace AS n"
        " CROSS JOIN pg_catalog.pg_roles AS r"
        f" WHERE r.rolname::text = ANY ({_ROLES_SQL}) AND n.oid IN ("
        " SELECT c.relnamespace FROM pg_catalog.pg_class AS c"
        f" WHERE c.relname::text = ANY ({_TABLES_SQL}) AND c.relkind = ANY ({_RELKINDS_SQL}))"
        " ORDER BY 1, 3"
    ),
    "default_privileges": (
        "SELECT pg_catalog.pg_get_userbyid(d.defaclrole),"
        " COALESCE(n.nspname, '*'),"
        " CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_catalog.pg_get_userbyid(a.grantee) END,"
        " a.privilege_type"
        " FROM pg_catalog.pg_default_acl AS d"
        " LEFT JOIN pg_catalog.pg_namespace AS n ON n.oid = d.defaclnamespace"
        " CROSS JOIN LATERAL pg_catalog.aclexplode(d.defaclacl) AS a"
        " WHERE d.defaclobjtype = 'r' AND (a.grantee = 0"
        f" OR pg_catalog.pg_get_userbyid(a.grantee)::text = ANY ({_ROLES_SQL}))"
        " ORDER BY 1, 2, 3, 4"
    ),
    "api_schemas_setting": (
        "SELECT COALESCE(db.datname, '*'), s.setting"
        " FROM pg_catalog.pg_db_role_setting AS rs"
        " JOIN pg_catalog.pg_roles AS r ON r.oid = rs.setrole"
        " LEFT JOIN pg_catalog.pg_database AS db ON db.oid = rs.setdatabase"
        " CROSS JOIN LATERAL pg_catalog.unnest(rs.setconfig) AS s(setting)"
        " WHERE r.rolname::text = 'authenticator' AND s.setting LIKE 'pgrst.db\\_schemas=%'"
        " ORDER BY 1"
    ),
    "dependent_views": (
        "SELECT DISTINCT vn.nspname, v.relname, v.relkind::text,"
        " pg_catalog.pg_get_userbyid(v.relowner), COALESCE(v.reloptions::text, ''),"
        " tn.nspname, t.relname"
        " FROM pg_catalog.pg_depend AS d"
        " JOIN pg_catalog.pg_rewrite AS rw ON rw.oid = d.objid"
        " JOIN pg_catalog.pg_class AS v ON v.oid = rw.ev_class"
        " JOIN pg_catalog.pg_namespace AS vn ON vn.oid = v.relnamespace"
        " JOIN pg_catalog.pg_class AS t ON t.oid = d.refobjid"
        " JOIN pg_catalog.pg_namespace AS tn ON tn.oid = t.relnamespace"
        " WHERE d.classid = 'pg_catalog.pg_rewrite'::regclass"
        " AND d.refclassid = 'pg_catalog.pg_class'::regclass"
        f" AND t.relname::text = ANY ({_TABLES_SQL}) AND v.oid <> t.oid"
        " ORDER BY 1, 2, 6, 7"
    ),
    "dependent_view_privileges": (
        "SELECT DISTINCT vn.nspname, v.relname, r.rolname, p.privilege,"
        " pg_catalog.has_table_privilege(r.oid, v.oid, p.privilege)"
        " FROM pg_catalog.pg_depend AS d"
        " JOIN pg_catalog.pg_rewrite AS rw ON rw.oid = d.objid"
        " JOIN pg_catalog.pg_class AS v ON v.oid = rw.ev_class"
        " JOIN pg_catalog.pg_namespace AS vn ON vn.oid = v.relnamespace"
        " JOIN pg_catalog.pg_class AS t ON t.oid = d.refobjid"
        " CROSS JOIN pg_catalog.pg_roles AS r"
        " CROSS JOIN (VALUES ('SELECT'), ('INSERT'), ('UPDATE'), ('DELETE')) AS p(privilege)"
        " WHERE d.classid = 'pg_catalog.pg_rewrite'::regclass"
        " AND d.refclassid = 'pg_catalog.pg_class'::regclass"
        f" AND t.relname::text = ANY ({_TABLES_SQL}) AND v.oid <> t.oid"
        f" AND r.rolname::text = ANY ({_ROLES_SQL})"
        " ORDER BY 1, 2, 3, 4"
    ),
    "realtime_publications": (
        "SELECT p.pubname::text, p.schemaname::text, p.tablename::text"
        " FROM pg_catalog.pg_publication_tables AS p"
        f" WHERE p.tablename::text = ANY ({_TABLES_SQL})"
        " ORDER BY 1, 2, 3"
    ),
}
# A refused read of one of these is recorded and the audit continues; the others are required.
OPTIONAL_QUERIES = frozenset(
    {"api_schemas_setting", "dependent_views", "dependent_view_privileges", "realtime_publications"}
)
# Columns holding any role name, or (policies) a list of them. Only standard identifiers are
# reported; every other name is withheld, element by element.
ROLE_NAME_COLUMNS = {
    "role_memberships": (0, 1),
    "role_inheritance": (0, 1),
    "tables": (3,),
    "policies": (4,),
    "schema_usage": (1,),
    "default_privileges": (0,),
    "dependent_views": (3,),
}
# The rehearsal reaches only a local server through its unix socket: never a network host.
_LOCAL_SOCKET_URL = re.compile(r"^postgresql:///[a-z_][a-z0-9_]*\?host=/var/run/postgresql$")
REHEARSAL_URL_VARIABLE = "AUDIT_REHEARSAL_URL"
# What scripts/audit_rehearsal/*.sql builds on top of the real migrations, and what the audit must
# therefore report. Each fixture exercises one branch of assess().
REHEARSAL_EXPECTED_ANON = {
    "public.analysis_runs": dict.fromkeys(API_PRIVILEGES, "OPEN"),
    "public.analysis_timeframe_results": {
        "SELECT": "OPEN ON COLUMNS run_id",
        "INSERT": "OPEN ON COLUMNS timeframe",
        "UPDATE": "OPEN ON COLUMNS disposition",
        "DELETE": "NO_PRIVILEGE",
    },
    "public.app_events": dict.fromkeys(API_PRIVILEGES, "OPEN"),
    "public.news_clusters": dict.fromkeys(API_PRIVILEGES, "OPEN"),
    "public.news_evidence_links": dict.fromkeys(API_PRIVILEGES, "OPEN"),
    "public.news_items": dict.fromkeys(API_PRIVILEGES, "RLS_DENIES_ALL"),
    "public.prediction_outcomes": {
        "SELECT": "POLICY_DECIDES: rehearsal_read",
        "INSERT": "POLICY_DECIDES: rehearsal_inherited_insert",
        "UPDATE": "RLS_DENIES_ALL",
        "DELETE": "RLS_DENIES_ALL",
    },
    "public.predictions": dict.fromkeys(API_PRIVILEGES, "RLS_DENIES_ALL"),
    "public.provider_observations": dict.fromkeys(API_PRIVILEGES, "RLS_DENIES_ALL"),
    "public.watchlist": dict.fromkeys(API_PRIVILEGES, "NO_PRIVILEGE"),
}
# (table, role): (acts as the table's owner, bypasses row-level security)
REHEARSAL_EXPECTED_OWNERSHIP = {
    ("public.news_evidence_links", "anon"): (True, True),
    ("public.news_evidence_links", "authenticated"): (False, False),
    ("public.provider_observations", "anon"): (True, False),
    ("public.predictions", "anon"): (False, False),
}
REHEARSAL_NON_STANDARD_ROLE = "rehearsal reader"
REHEARSAL_EXPECTED_ANON_INHERITS = {WITHHELD, "rehearsal_owner"}
REHEARSAL_EXPECTED_ANON_MEMBER_OF = {WITHHELD, "rehearsal_bystander", "rehearsal_owner"}
REHEARSAL_EXPECTED_EXPOSURE_MARKERS = (
    "public.analysis_runs: anon SELECT OPEN",
    "public.app_events: anon can receive change events through publication(s) supabase_realtime",
    "public.analysis_timeframe_results: anon SELECT OPEN ON COLUMNS run_id",
    "public.analysis_timeframe_results: anon INSERT OPEN ON COLUMNS timeframe",
    "public.analysis_timeframe_results: anon UPDATE OPEN ON COLUMNS disposition",
    "public.news_evidence_links: anon SELECT OPEN",
    "public.rehearsal_runs_view (a view over an audited table): anon SELECT REVIEW",
    "public.prediction_outcomes: anon SELECT POLICY_DECIDES: rehearsal_read",
    "public.prediction_outcomes: anon INSERT POLICY_DECIDES: rehearsal_inherited_insert",
)
# No exposure line may start with these: RLS with no applicable policy, forced RLS on an owner, a
# restrictive-only policy, and grants reachable only through a membership that does not inherit.
REHEARSAL_UNEXPOSED_PREFIXES = (
    "public.predictions:",
    "public.provider_observations:",
    "public.news_items:",
    "public.watchlist:",
    "public.news_evidence_links: authenticated",
)
_COMMIT_SHA = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_DIGITS = re.compile(r"[0-9]+")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=[MODE_ATTEST, MODE_REHEARSE, MODE_AUDIT], default=MODE_ATTEST
    )
    parser.add_argument(
        "--confirm", default="", help="required for --mode audit: the exact confirmation token"
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
    if args.mode == MODE_AUDIT and args.confirm != CONFIRMATION:
        raise _refusal(f"--confirm must be exactly {CONFIRMATION}")
    if args.mode == MODE_REHEARSE:
        return rehearse(args, environ, captured)

    isolation = enter_isolated_runtime(args.wheelhouse)
    record = attest_dispatch(args.expected_sha, environ, isolation)
    attest_loaded_modules(isolation)
    base = {
        "schema_version": REPORT_SCHEMA,
        "audited_tables": list(AUDITED_TABLES),
        "audited_migrations": list(AUDIT_MIGRATIONS),
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
    observed = read_catalogs(
        lambda: driver.connect(database_url, connect_timeout=8, autocommit=False), captured
    )
    return {
        **base,
        "mode": MODE_AUDIT,
        "outcome": "AUDITED",
        "committed": False,
        "observed": observed,
        "assessment": assess(observed),
    }


def rehearse(
    args: argparse.Namespace, environ: Mapping[str, str], captured: dict[str, Any]
) -> dict[str, Any]:
    """The audit, end to end, against the scratch database the rehearsal fixtures built.

    It connects as a role holding NO privilege on any audited table, so a query that read an
    application row would fail: success proves the audit reads catalogs only. It then checks the
    assessment against what the fixtures were built to show.
    """

    url = environ.get(REHEARSAL_URL_VARIABLE, "")
    if not _LOCAL_SOCKET_URL.fullmatch(url):
        raise _refusal(
            f"{REHEARSAL_URL_VARIABLE} must be a local unix-socket URL, e.g. "
            "postgresql:///audit_rehearsal?host=/var/run/postgresql"
        )
    if environ.get("SUPABASE_DB_URL"):
        raise _refusal("the rehearsal never runs where the production database secret is present")
    isolation = enter_isolated_runtime(args.wheelhouse) if args.wheelhouse else None
    driver = load_driver()
    if isolation is not None:
        attest_loaded_modules(isolation)
    observed = read_catalogs(
        lambda: driver.connect(url, connect_timeout=8, autocommit=False), captured
    )
    assessment = assess(observed)
    failures = rehearsal_failures(observed, assessment)
    if failures:
        raise _refusal("the rehearsal does not match its fixtures: " + "; ".join(failures))
    return {
        "schema_version": REPORT_SCHEMA,
        "mode": MODE_REHEARSE,
        "outcome": "REHEARSED",
        "committed": False,
        "observed": observed,
        "assessment": assessment,
    }


def rehearsal_failures(observed: Mapping[str, Any], assessment: Mapping[str, Any]) -> list[str]:
    """Pure: every way the rehearsal's audit differs from what its fixtures guarantee."""

    failures: list[str] = []
    unexpected_errors = {
        name: error
        for name, error in observed.get("query_errors", {}).items()
        if name != "api_schemas_setting"
    }
    if unexpected_errors:
        failures.append(f"catalog reads failed for a privilege-less role: {unexpected_errors}")
    if observed.get("transaction_read_only") != "on":
        failures.append("the transaction was not read-only")
    if "api_schemas_setting" in observed.get("query_errors", {}):
        if assessment["api_schemas"] != ["public"]:
            failures.append("an unreadable schema setting must fall back to public")
    elif assessment["api_schemas"] != ["graphql_public", "public"]:
        failures.append(f"api schemas are {assessment['api_schemas']}")
    if assessment["missing_tables"] or assessment["tables_in_more_than_one_schema"]:
        failures.append(
            f"tables missing {assessment['missing_tables']} or duplicated "
            f"{assessment['tables_in_more_than_one_schema']}"
        )
    if assessment["facts_incomplete"]:
        failures.append(f"the server did not return {assessment['facts_incomplete']}")
    tables = assessment["tables"]
    for key, expected in REHEARSAL_EXPECTED_ANON.items():
        got = tables.get(key, {}).get("roles", {}).get("anon", {}).get("data_api")
        if got != expected:
            failures.append(f"{key} anon is {got}, not {expected}")
    for (key, role), expected_facts in REHEARSAL_EXPECTED_OWNERSHIP.items():
        info = tables.get(key, {}).get("roles", {}).get(role, {})
        got_facts = (info.get("acts_as_table_owner"), info.get("bypasses_row_level_security"))
        if got_facts != expected_facts:
            failures.append(
                f"{key} {role} (acts as owner, bypasses RLS) is {got_facts}, not {expected_facts}"
            )
    inherits = set(assessment["role_inheritance"].get("anon", []))
    if inherits != REHEARSAL_EXPECTED_ANON_INHERITS:
        failures.append(f"anon inherits {sorted(inherits)}")
    member_of = {row[1] for row in observed["role_memberships"] if row[0] == "anon"}
    if member_of != REHEARSAL_EXPECTED_ANON_MEMBER_OF:
        failures.append(f"anon is directly a member of {sorted(member_of)}")
    if not all(isinstance(row[4], list) for row in observed["policies"]):
        failures.append("policy roles were not read as lists of names")
    if any(
        REHEARSAL_NON_STANDARD_ROLE in json.dumps(item, default=str)
        for item in (observed, assessment)
    ):
        failures.append("a non-standard role name was reported")
    service = tables.get("public.predictions", {}).get("roles", {}).get("service_role", {})
    if service.get("data_api") != dict.fromkeys(API_PRIVILEGES, "OPEN"):
        failures.append(f"service_role on predictions is {service.get('data_api')}, not OPEN")
    watchlist_service = tables.get("public.watchlist", {}).get("roles", {}).get("service_role", {})
    if watchlist_service.get("privileges") != []:
        failures.append("service_role must hold nothing on watchlist")
    exposures = assessment["anon_or_authenticated_exposures"]
    for marker in REHEARSAL_EXPECTED_EXPOSURE_MARKERS:
        if not any(line.startswith(marker) for line in exposures):
            failures.append(f"no exposure line starts with {marker!r}")
    for prefix in REHEARSAL_UNEXPOSED_PREFIXES:
        if any(line.startswith(prefix) for line in exposures):
            failures.append(f"an exposure line starts with {prefix!r}, which must stay closed")
    if not any(row[2] == "PUBLIC" for row in observed["table_grants"]):
        failures.append("the PUBLIC grant on news_clusters was not observed")
    if assessment["verdict"] != "EXPOSED":
        failures.append(f"the verdict is {assessment['verdict']}, not EXPOSED")
    return failures


def read_catalogs(open_connection: Callable[[], Any], captured: dict[str, Any]) -> dict[str, Any]:
    """Every catalog query in ONE read-only transaction, always rolled back. Rows kept raw."""

    observed: dict[str, Any] = {"query_errors": {}}
    captured["observed"] = observed
    with open_connection() as connection:
        try:
            with connection.cursor() as cursor:
                for statement in GUARD_STATEMENTS:
                    cursor.execute(statement)
                cursor.execute(READ_ONLY_SQL)
                read_only = _single(cursor.fetchone(), "read-only check")
                observed["transaction_read_only"] = read_only
                if read_only != "on":
                    raise _refusal(f"the server reports transaction_read_only={read_only!r}")
                for name, query in QUERIES.items():
                    if name in OPTIONAL_QUERIES:
                        cursor.execute(f"SAVEPOINT audit_{name}")
                        try:
                            cursor.execute(query)
                            rows = cursor.fetchall()
                        except Exception as exc:  # noqa: BLE001 - recorded by type; audit goes on
                            cursor.execute(f"ROLLBACK TO SAVEPOINT audit_{name}")
                            observed["query_errors"][name] = type(exc).__name__
                            continue
                        cursor.execute(f"RELEASE SAVEPOINT audit_{name}")
                    else:
                        cursor.execute(query)
                        rows = cursor.fetchall()
                    observed[name] = _redact_role_names(name, [list(row) for row in rows])
        finally:
            connection.rollback()
    captured["rolled_back"] = True
    return observed


def _single(row: Any, what: str) -> Any:
    if row is None or len(row) != 1:
        raise _refusal(f"the {what} returned {row!r}, not one value")
    return row[0]


def _redact_role_names(name: str, rows: list[list[Any]]) -> list[list[Any]]:
    for row in rows:
        for index in ROLE_NAME_COLUMNS.get(name, ()):
            row[index] = _redacted(row[index])
    return rows


def _redacted(value: Any) -> Any:
    """A standard role name as it is, a list of names element by element, anything else withheld."""

    if isinstance(value, (list, tuple)):
        return [_redacted(item) for item in value]
    if isinstance(value, str) and _IDENTIFIER.fullmatch(value):
        return value
    return WITHHELD


def assess(observed: Mapping[str, Any]) -> dict[str, Any]:
    """Pure: each audited table's exposure to anon and authenticated through the Data API.

    A role can use a command on a table when the server says it holds that privilege on the table
    or on some of its columns. Rows are then filtered unless row-level security is off or the role
    bypasses it: BYPASSRLS, superuser, or acting as the owner of a table that does not force it.
    Under row-level security only a PERMISSIVE policy that the server says applies to the role can
    admit rows; the policy expression then decides, and it is reported for review. The Data API
    reaches the table only if the role may use its schema and the schema is served; when the served
    schemas are not visible in the database, Supabase's default (``public``) is assumed and said.

    Each server fact is looked up for every API role that exists. A missing or unknown fact is
    listed in ``facts_incomplete`` and taken as the unsafe answer, so it can never hide an exposure.
    """

    roles = {
        row[0]: {"superuser": bool(row[1]), "bypassrls": bool(row[2])}
        for row in observed["roles"]
    }
    gaps: set[str] = set()

    def known(facts: Mapping[Any, Any], key: tuple[Any, ...], what: str) -> bool:
        value = facts.get(key)
        if value is None:
            gaps.add(what)
            return True
        return bool(value)

    usage = {(row[0], row[2]): row[3] for row in observed["schema_usage"]}
    held_facts = {tuple(row[:4]): row[4] for row in observed["effective_privileges"]}
    owner_facts = {tuple(row[:3]): row[3] for row in observed["owner_equivalence"]}
    policy_facts = {tuple(row[:4]): row[4] for row in observed["policy_applicability"]}
    column_only: dict[tuple[str, str, str, str], list[str]] = {}
    for schema, table, column, role, privilege in observed["column_privileges"]:
        column_only.setdefault((schema, table, role, privilege), []).append(column)
    policies: dict[tuple[str, str], list[list[Any]]] = {}
    for row in observed["policies"]:
        policies.setdefault((row[0], row[1]), []).append(row)
    inheritance: dict[str, list[str]] = {}
    for role, parent in observed["role_inheritance"]:
        inheritance.setdefault(role, []).append(parent)
    setting_rows = observed.get("api_schemas_setting")
    if setting_rows:
        served = set()
        for _, setting in setting_rows:
            listed = str(setting).split("=", 1)[1].split(",")
            served |= {part.strip() for part in listed if part.strip()}
        served_source = "pgrst.db_schemas on the authenticator role"
    else:
        served = {"public"}
        served_source = (
            "ASSUMED: Supabase's default API schema (the setting is not visible in the database)"
        )
    for name, what in (
        ("dependent_view_privileges", "views over the audited tables"),
        ("realtime_publications", "Realtime publications"),
    ):
        if name in observed.get("query_errors", {}):
            gaps.add(f"{what}: the catalog read was refused")
    public_grants = sorted(
        {(row[0], row[1], row[3]) for row in observed["table_grants"] if row[2] == "PUBLIC"}
    )
    tables: dict[str, Any] = {}
    exposures: list[str] = []
    found_tables = set()
    for schema, table, relkind, owner, rls, forced, owned_by_current in observed["tables"]:
        found_tables.add(table)
        key = f"{schema}.{table}"
        table_policies = policies.get((schema, table), [])
        entry: dict[str, Any] = {
            "relkind": relkind,
            "owner": owner,
            "owned_by_connecting_role": bool(owned_by_current),
            "row_level_security": bool(rls),
            "row_level_security_forced": bool(forced),
            "schema_served_by_api": schema in served,
            "policies": [row[2] for row in table_policies],
            "realtime_publications": [
                row[0]
                for row in observed.get("realtime_publications", [])
                if row[1] == schema and row[2] == table
            ],
            "roles": {},
        }
        for role in API_ROLES:
            if role in roles:
                held = {
                    privilege
                    for privilege in PRIVILEGES
                    if known(
                        held_facts,
                        (schema, table, role, privilege),
                        f"{key}: whether {role} holds {privilege}",
                    )
                }
                acts_as_owner = known(
                    owner_facts, (schema, table, role), f"{key}: whether {role} acts as its owner"
                )
                uses_schema = known(usage, (schema, role), f"{schema}: whether {role} has USAGE")
            else:
                held, acts_as_owner, uses_schema = set(), False, False
            attributes = roles.get(role, {})
            bypass = (
                attributes.get("bypassrls", False)
                or attributes.get("superuser", False)
                or (acts_as_owner and not forced)
            )
            reachable = schema in served and uses_schema
            commands: dict[str, str] = {}
            exposed: dict[str, bool] = {}
            columns_only: dict[str, list[str]] = {}
            for command in API_PRIVILEGES:
                columns = column_only.get((schema, table, role, command), [])
                if command not in held and not columns:
                    commands[command], exposed[command] = "NO_PRIVILEGE", False
                    continue
                if not rls or bypass:
                    verdict = "OPEN" if reachable else "OPEN_BUT_NOT_API_REACHABLE"
                    exposed[command] = reachable
                else:
                    # Only a PERMISSIVE policy can admit rows; RESTRICTIVE ones only narrow them.
                    applicable = sorted(
                        row[2]
                        for row in table_policies
                        if str(row[3]).upper() == "PERMISSIVE"
                        and row[5] in (command, "ALL")
                        and known(
                            policy_facts,
                            (schema, table, row[2], role),
                            f"{key}: whether policy {row[2]} applies to {role}",
                        )
                    )
                    if not applicable:
                        verdict = "RLS_DENIES_ALL"
                    elif reachable:
                        verdict = "POLICY_DECIDES: " + ", ".join(applicable)
                    else:
                        verdict = "POLICY_DECIDES_NOT_API_REACHABLE"
                    exposed[command] = bool(applicable) and reachable
                if command not in held:
                    columns_only[command] = columns
                    verdict += " ON COLUMNS " + ", ".join(columns)
                commands[command] = verdict
            entry["roles"][role] = {
                "privileges": sorted(held),
                "column_only_privileges": columns_only,
                "acts_as_table_owner": acts_as_owner,
                "bypasses_row_level_security": bypass,
                "schema_usage": uses_schema,
                "data_api": commands,
            }
            if role != "service_role":
                for command in API_PRIVILEGES:
                    if exposed[command]:
                        exposures.append(f"{key}: {role} {command} {commands[command]}")
                if exposed["SELECT"] and entry["realtime_publications"]:
                    exposures.append(
                        f"{key}: {role} can receive change events through publication(s) "
                        + ", ".join(entry["realtime_publications"])
                    )
        tables[key] = entry
    for view_schema, view, role, privilege, held in observed.get("dependent_view_privileges", []):
        if held is None:
            gaps.add(f"{view_schema}.{view}: whether {role} holds {privilege}")
        if (held or held is None) and role != "service_role" and view_schema in served:
            exposures.append(
                f"{view_schema}.{view} (a view over an audited table): {role} {privilege} "
                "REVIEW: the view's owner and security_invoker decide which rows are visible"
            )
    missing = sorted(set(AUDITED_TABLES) - found_tables)
    duplicated = sorted(
        name for name in found_tables
        if sum(1 for row in observed["tables"] if row[1] == name) > 1
    )
    if exposures:
        overall = "EXPOSED"
    elif gaps:
        overall = "INCOMPLETE"
    else:
        overall = "NOT_EXPOSED_THROUGH_TABLE_GRANTS"
    return {
        "api_schemas": sorted(served),
        "api_schemas_source": served_source,
        "role_inheritance": {
            role: sorted(parents) for role, parents in sorted(inheritance.items())
        },
        "tables": tables,
        "missing_tables": missing,
        "tables_in_more_than_one_schema": duplicated,
        "public_grants": [list(item) for item in public_grants],
        "column_grants": observed["column_grants"],
        "dependent_views": observed.get("dependent_views", []),
        "realtime_publications": observed.get("realtime_publications", []),
        "anon_or_authenticated_exposures": exposures,
        "facts_incomplete": sorted(gaps),
        "verdict": overall,
        "not_audited": [
            "SECURITY DEFINER functions and other RPC paths, which can read a table whatever the "
            "caller's grants: outside this audit's ruled scope (the tables themselves)",
            "row contents: never read, by design",
        ],
    }


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

    return ProvenanceRefused(f"privilege audit refused; nothing was read: {message}")


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
