#!/usr/bin/env python
"""Apply migration 0016, Phase 3's least-privilege roles (governing plan §8.2), ONCE.

    --mode attest     verify isolation, dispatch and runtime; touches no database
    --mode rehearse   the whole apply against a scratch local PostgreSQL: apply once, then prove
                      that a second apply refuses; never where the production secret is present,
                      never over the network
    --mode apply      THE ONE-SHOT APPLY; requires the confirmation token

Run only by ``.github/workflows/apply-migration-0016.yml``, as ``python -I -S -B``, inside the
closed trust boundary of the other database routes:
- exact CPython 3.13.14;
- CPython's bundled pip and lock-authenticated wheels;
- the dispatch verified HERE against THIS workflow, in the owner repository.
The bulk scripts/apply_migrations.py applies every migration and is never used for it.

WHAT IT CHANGES. Migration 0016 (owner ruling E1 = YES, W2) creates four NOLOGIN, NOINHERIT roles
without powers: ucpe_api_writer, ucpe_bundle_owner, ucpe_space_db and ucpe_resolver.
- It grants each of them exactly its list, with a matching permissive policy per grant (40 in all).
- PostgREST's authenticator may switch to the writer.
- The bundle RPC public.save_prediction_bundle becomes SECURITY DEFINER, owned by ucpe_bundle_owner.
  Its body, its fixed search_path and service_role's EXECUTE are unchanged; the writer gains
  EXECUTE.
- ucpe_space_db keeps exactly what the live F1/UOR registry and ledger need (Correction 01).
- Nothing existing is revoked.

WHAT IT REFUSES. The route refuses unless production is ready for exactly that:
- PostgreSQL 16 or later, for the membership options;
- PostgREST's authenticator exists;
- the applying role holds CREATEROLE (or SUPERUSER), owns schema public's privileges, and owns every
  table it grants on;
- the bundle RPC is exactly migration 0015's: SECURITY INVOKER, owned by the applying role, its body
  and search_path, and EXECUTE for service_role only;
- none of the four roles, and no policy of theirs, exists yet. Otherwise this is not a first apply,
  so a second dispatch refuses before running anything.

ONE TRANSACTION, FAIL CLOSED. Under bounded timeouts and an advisory lock:
  1. read-only PRE-CHECKS, as above. Recorded, not required: every table's security, schema
     fingerprint and privileges; the schema; the memberships; every other function; the event
     triggers;
  2. exactly the pinned bytes of migration 0016, with no parameters;
  3. read-only catalog POST-CHECKS refuse unless:
     - the four roles exist, with no attribute, no LOGIN and no INHERIT;
     - the memberships are exactly the writer's in authenticator (SET without INHERIT), plus at most
       the CREATEROLE creator's ADMIN grants that PostgreSQL 16 makes;
     - each role's table, sequence and schema privileges are exactly its list;
     - the policies are exactly the 40;
     - the bundle RPC is SECURITY DEFINER, owned by ucpe_bundle_owner, with its body and search_path
       unchanged and EXECUTE exactly for service_role and the writer;
     - everything else is unchanged: the API roles' privileges, row-level security, every table's
       columns, constraints, indexes and triggers, every other function, the schema's owner and the
       API roles' rights on it, and the event triggers.
Any refusal or error rolls the transaction back, so nothing is applied; only then is it committed.
If the connection fails while the COMMIT is in flight, the report says ``committed`` is UNKNOWN.
Had it committed, a second dispatch would refuse as not a first apply.

No application row is ever read or written: every check reads only the catalog. The roles'
behaviour is proven on scratch rehearsals, against exactly these pinned bytes (P3-PRIV-R, criteria
P1-P8, behind a real PostgREST). It shows each role does exactly its list through production's own
code, the live writer is unchanged, a second application is refused, and the rollback is exact.

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
SCRIPT = "scripts/apply_migration_0016.py"
WORKFLOW = ".github/workflows/apply-migration-0016.yml"
MIGRATION = "migrations/0016_least_privilege_roles.sql"
# The reviewed bytes. A different file on the dispatched commit refuses before any connection.
MIGRATION_SHA256 = "5d89f5bdd333ee6c9ec460cd30db732870e154706021d9180cc010be37ad7c40"
CONFIRMATION = "APPLY-MIGRATION-0016-ONCE"
REPORT_SCHEMA = "migration-0016-apply-report.v1"
DISPATCH_SCHEMA = "migration-0016-dispatch.v1"
MODE_ATTEST = "attest"
MODE_REHEARSE = "rehearse"
MODE_APPLY = "apply"
REQUIRED_EVENT = "workflow_dispatch"
REQUIRED_REF = "refs/heads/main"
# The owner repository, pinned: a fork's run carries a self-consistent identity of its own.
EXPECTED_REPOSITORY = "tranbeny053-hub/v83-stock-cron"
PINNED_PYTHON = ("CPython", "3.13.14")

# CREATE POLICY takes a brief ACCESS EXCLUSIVE lock on its table: the lock timeout bounds the wait
# behind live traffic, and a timeout refuses the whole apply with nothing changed.
TIMEOUT_STATEMENTS = (
    "SET LOCAL lock_timeout = '10s'",
    "SET LOCAL statement_timeout = '120s'",
)
# A fixed key, distinct from every other route's: two appliers of 0016 serialize.
ADVISORY_LOCK_SQL = "SELECT pg_advisory_xact_lock(5000016)"

API_ROLES = ("anon", "authenticated", "service_role")
AUTHENTICATOR = "authenticator"
# The four roles 0016 creates, sorted as the checks return them.
NEW_ROLES = ("ucpe_api_writer", "ucpe_bundle_owner", "ucpe_resolver", "ucpe_space_db")
WRITER = "ucpe_api_writer"
BUNDLE_OWNER = "ucpe_bundle_owner"
# Every table of migrations 0001-0015, sorted. A test re-derives it from the migration files.
TABLES = (
    "analysis_run_details",
    "analysis_runs",
    "analysis_timeframe_results",
    "app_events",
    "automation_credential",
    "automation_radar_ledger",
    "news_clusters",
    "news_evidence_links",
    "news_items",
    "prediction_derivatives_snapshots",
    "prediction_feature_snapshots",
    "prediction_outcomes",
    "prediction_resolution_status",
    "predictions",
    "provider_observations",
    "section_5a_evaluation_seal",
    "watchlist",
)
SEQUENCES = (
    "analysis_timeframe_results_id_seq",
    "app_events_id_seq",
    "provider_observations_id_seq",
)
SEQUENCE_PRIVILEGES = ("SELECT", "UPDATE", "USAGE")
_UPSERTED = ("INSERT", "SELECT", "UPDATE")
# Each role's exact list (migration 0016's GRANTs; the privileges sorted as the checks return them).
# A test requires it to equal both the migration's statements and the rehearsal's expectation.
EXPECTED_GRANTS: dict[str, dict[str, tuple[str, ...]]] = {
    "ucpe_api_writer": {
        "analysis_run_details": _UPSERTED,
        "analysis_runs": _UPSERTED,
        "analysis_timeframe_results": ("INSERT",),
        "news_clusters": _UPSERTED,
        "news_evidence_links": _UPSERTED,
        "news_items": _UPSERTED,
        "predictions": ("SELECT",),
        "provider_observations": ("INSERT",),
        "watchlist": ("DELETE", "INSERT", "SELECT", "UPDATE"),
    },
    "ucpe_bundle_owner": {
        "prediction_derivatives_snapshots": ("INSERT", "SELECT"),
        "prediction_feature_snapshots": ("INSERT", "SELECT"),
        "predictions": ("INSERT", "SELECT"),
    },
    "ucpe_resolver": {
        "prediction_outcomes": ("INSERT", "SELECT"),
        "prediction_resolution_status": _UPSERTED,
        "predictions": ("SELECT",),
    },
    "ucpe_space_db": {
        # Correction 01: the live F1/UOR registry and ledger, plus calibration's read.
        "automation_credential": ("SELECT",),
        "automation_radar_ledger": _UPSERTED,
        "prediction_outcomes": ("SELECT",),
        "predictions": ("SELECT",),
    },
}
EXPECTED_SEQUENCE_GRANTS: dict[str, dict[str, tuple[str, ...]]] = {
    "ucpe_api_writer": {
        "analysis_timeframe_results_id_seq": ("USAGE",),
        "provider_observations_id_seq": ("USAGE",),
    },
}
# pg_policy.polcmd per command a grant can carry a policy for.
POLICY_COMMANDS = {"SELECT": "r", "INSERT": "a", "UPDATE": "w", "DELETE": "d"}


def expected_policies() -> dict[str, tuple[str, bool, list[str], str, str]]:
    """Pure: "table/policy" -> (command, permissive, roles, USING, WITH CHECK) of 0016's policies.

    One permissive policy per (table, role, command) the grants carry, named role_command. USING is
    true where the command reads existing rows, and WITH CHECK where it writes new ones.
    """

    policies = {}
    for role, tables in EXPECTED_GRANTS.items():
        for table, privileges in tables.items():
            for command, code in POLICY_COMMANDS.items():
                if command in privileges:
                    using = "true" if code in ("r", "w", "d") else ""
                    check = "true" if code in ("a", "w") else ""
                    item = f"{table}/{role}_{command.lower()}"
                    policies[item] = (code, True, [role], using, check)
    return policies


FUNCTION = "save_prediction_bundle"
FUNCTION_REFERENCE = f"public.{FUNCTION}"
FUNCTION_ARGUMENTS = "p_prediction jsonb, p_feature_snapshot jsonb, p_derivatives_snapshot jsonb"
FUNCTION_CONFIG = ("search_path=pg_catalog, pg_temp",)
# 0016 changes the function's owner, security and EXECUTE list, never its body (migration 0015's).
FUNCTION_MIGRATION = "migrations/0015_prediction_bundle_rpc.sql"
_BODY_OPEN = "AS $function$"
_BODY_CLOSE = "$function$;"


def function_source(migration_sql: str) -> str:
    """Pure: the function body exactly as the migration writes it between its dollar quotes,
    which is what pg_proc.prosrc stores."""

    start = migration_sql.index(_BODY_OPEN) + len(_BODY_OPEN)
    return migration_sql[start:migration_sql.index(_BODY_CLOSE, start)]


# The table privileges of every supported server, sorted as the checks return them.
TABLE_PRIVILEGES = ("DELETE", "INSERT", "REFERENCES", "SELECT", "TRIGGER", "TRUNCATE", "UPDATE")
# PostgreSQL 17 added MAINTAIN, and production runs 17. On such a server every check also asks
# about MAINTAIN; on an older one, such as the CI rehearsal's 16, asking would fail.
MAINTAIN_SINCE_SERVER_VERSION = 170000
MINIMUM_SERVER_VERSION = 150000
# GRANT ... WITH INHERIT/SET and pg_auth_members' option columns arrived in PostgreSQL 16.
MEMBERSHIP_OPTIONS_SINCE_SERVER_VERSION = 160000
TABLE_PRIVILEGES_WITH_MAINTAIN = tuple(sorted((*TABLE_PRIVILEGES, "MAINTAIN")))
SERVER_VERSION_SQL = "SELECT pg_catalog.current_setting('server_version_num')::integer"

_API_ROLES_SQL = ", ".join(f"'{role}'" for role in API_ROLES)
_NEW_ROLES_SQL = ", ".join(f"'{role}'" for role in NEW_ROLES)


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


def security_sql(server_version: int) -> str:
    """Every table's security and the API roles' privileges, the other routes' own check."""

    return _security_sql(TABLES, table_privileges_for(server_version))


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
SERVER_SQL = (
    "SELECT pg_catalog.current_setting('server_version_num')::integer AS server_version_num"
)
SERVER_FIELDS = ("server_version_num",)
# The four roles, authenticator and the applying role, with every attribute 0016 must not grant.
ROLES_STATE_SQL = (
    "SELECT r.rolname::text, r.rolsuper, r.rolinherit, r.rolcreaterole, r.rolcreatedb,"
    " r.rolcanlogin, r.rolreplication, r.rolbypassrls, r.rolname = current_user"
    " FROM pg_catalog.pg_roles AS r"
    f" WHERE r.rolname IN ('{AUTHENTICATOR}', {_NEW_ROLES_SQL}) OR r.rolname = current_user"
    ' ORDER BY r.rolname::text COLLATE "C"'
)
ROLE_FIELDS = (
    "role", "superuser", "inherit", "createrole", "createdb", "login", "replication", "bypassrls",
    "is_applying_role",
)


def memberships_sql(server_version: int) -> str:
    """Every membership in or of the four roles, and authenticator's; the options from 16 on."""

    if server_version >= MEMBERSHIP_OPTIONS_SINCE_SERVER_VERSION:
        options = "a.inherit_option, a.set_option"
    else:
        options = "NULL::boolean, NULL::boolean"
    return (
        "SELECT r.rolname::text, m.rolname::text, g.rolname = current_user, a.admin_option,"
        f" {options}"
        " FROM pg_catalog.pg_auth_members AS a"
        " JOIN pg_catalog.pg_roles AS r ON r.oid = a.roleid"
        " JOIN pg_catalog.pg_roles AS m ON m.oid = a.member"
        " JOIN pg_catalog.pg_roles AS g ON g.oid = a.grantor"
        f" WHERE r.rolname IN ({_NEW_ROLES_SQL}) OR m.rolname IN ({_NEW_ROLES_SQL})"
        f" OR m.rolname = '{AUTHENTICATOR}'"
        ' ORDER BY r.rolname::text COLLATE "C", m.rolname::text COLLATE "C",'
        ' g.rolname::text COLLATE "C"'
    )


MEMBERSHIP_FIELDS = ("role", "member", "granted_by_applying_role", "admin", "inherit", "set")


def _held_by(function: str, role_oid: str, relation: str, values: str) -> str:
    """The privileges the role with oid ``role_oid`` holds on ``relation``, as a sorted text array.

    By oid, not name, so asking about a role that does not exist yet is never an error.
    """

    return (
        f"ARRAY(SELECT v.privilege FROM (VALUES {values}) AS v(privilege)"
        f" WHERE pg_catalog.{function}({role_oid}, {relation}, v.privilege)"
        ' ORDER BY v.privilege COLLATE "C")'
    )


def grants_sql(server_version: int) -> str:
    """Each of the four roles' privileges on every table (no row before they exist)."""

    listed = ", ".join(f"('{name}')" for name in TABLES)
    asked = ", ".join(f"('{name}')" for name in table_privileges_for(server_version))
    return (
        "SELECT r.rolname::text, t.name,"
        f" {_held_by('has_table_privilege', 'r.oid', 'c.oid', asked)}"
        " FROM pg_catalog.pg_roles AS r"
        f" CROSS JOIN (VALUES {listed}) AS t(name)"
        " LEFT JOIN pg_catalog.pg_class AS c"
        " ON c.oid = pg_catalog.to_regclass('public.' || t.name)"
        f" WHERE r.rolname IN ({_NEW_ROLES_SQL})"
        ' ORDER BY r.rolname::text COLLATE "C", t.name COLLATE "C"'
    )


GRANT_FIELDS = ("role", "table", "privileges")
_SEQUENCES_LISTED = ", ".join(f"('{name}')" for name in SEQUENCES)
_SEQUENCE_PRIVILEGES_ASKED = ", ".join(f"('{name}')" for name in SEQUENCE_PRIVILEGES)
SEQUENCE_GRANTS_SQL = (
    "SELECT r.rolname::text, s.name,"
    f" {_held_by('has_sequence_privilege', 'r.oid', 'c.oid', _SEQUENCE_PRIVILEGES_ASKED)}"
    " FROM pg_catalog.pg_roles AS r"
    f" CROSS JOIN (VALUES {_SEQUENCES_LISTED}) AS s(name)"
    " LEFT JOIN pg_catalog.pg_class AS c"
    " ON c.oid = pg_catalog.to_regclass('public.' || s.name)"
    f" WHERE r.rolname IN ({_NEW_ROLES_SQL})"
    ' ORDER BY r.rolname::text COLLATE "C", s.name COLLATE "C"'
)
SEQUENCE_GRANT_FIELDS = ("role", "sequence", "privileges")
# The schema public: its owner, whether the applying role may create in it and holds its owner's
# privileges (GRANT ON SCHEMA needs them), and the API roles' rights on it, which must not change.
SCHEMA_SQL = (
    "SELECT n.nspname::text, pg_catalog.pg_get_userbyid(n.nspowner),"
    " pg_catalog.has_schema_privilege(current_user, n.oid, 'CREATE'),"
    " pg_catalog.pg_has_role(current_user, n.nspowner, 'USAGE'),"
    " pg_catalog.has_schema_privilege('public', n.oid, 'USAGE'),"
    " pg_catalog.has_schema_privilege('public', n.oid, 'CREATE'),"
    " pg_catalog.has_schema_privilege('anon', n.oid, 'USAGE'),"
    " pg_catalog.has_schema_privilege('anon', n.oid, 'CREATE'),"
    " pg_catalog.has_schema_privilege('authenticated', n.oid, 'USAGE'),"
    " pg_catalog.has_schema_privilege('authenticated', n.oid, 'CREATE'),"
    " pg_catalog.has_schema_privilege('service_role', n.oid, 'USAGE'),"
    " pg_catalog.has_schema_privilege('service_role', n.oid, 'CREATE')"
    " FROM pg_catalog.pg_namespace AS n WHERE n.nspname = 'public'"
)
SCHEMA_FIELDS = (
    "schema", "owner", "applying_role_may_create", "applying_role_holds_owner_privileges",
    "public_usage", "public_create", "anon_usage", "anon_create", "authenticated_usage",
    "authenticated_create", "service_role_usage", "service_role_create",
)
SCHEMA_GRANTS_SQL = (
    "SELECT r.rolname::text, pg_catalog.has_schema_privilege(r.oid, n.oid, 'USAGE'),"
    " pg_catalog.has_schema_privilege(r.oid, n.oid, 'CREATE')"
    " FROM pg_catalog.pg_roles AS r CROSS JOIN pg_catalog.pg_namespace AS n"
    f" WHERE n.nspname = 'public' AND r.rolname IN ({_NEW_ROLES_SQL})"
    ' ORDER BY r.rolname::text COLLATE "C"'
)
SCHEMA_GRANT_FIELDS = ("role", "usage", "create")
# Every policy in schema public, keyed "table/policy".
POLICIES_SQL = (
    "SELECT c.relname::text || '/' || p.polname::text, p.polcmd::text, p.polpermissive,"
    " ARRAY(SELECT pg_catalog.pg_get_userbyid(x.role)"
    " FROM pg_catalog.unnest(p.polroles) AS x(role)"
    ' ORDER BY pg_catalog.pg_get_userbyid(x.role) COLLATE "C"),'
    " COALESCE(pg_catalog.pg_get_expr(p.polqual, p.polrelid), ''),"
    " COALESCE(pg_catalog.pg_get_expr(p.polwithcheck, p.polrelid), '')"
    " FROM pg_catalog.pg_policy AS p"
    " JOIN pg_catalog.pg_class AS c ON c.oid = p.polrelid"
    " JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace"
    " WHERE n.nspname = 'public'"
    ' ORDER BY c.relname::text COLLATE "C", p.polname::text COLLATE "C"'
)
POLICY_FIELDS = ("item", "command", "permissive", "roles", "using", "with_check")
# The bundle RPC, every overload of its name in public, with its owner and its whole EXECUTE list.
FUNCTION_SQL = (
    "SELECT pg_catalog.pg_get_function_identity_arguments(p.oid),"
    " pg_catalog.format_type(p.prorettype, NULL), l.lanname::text, p.prosecdef, p.prokind::text,"
    " p.provolatile::text, COALESCE(p.proconfig, ARRAY[]::text[]),"
    " pg_catalog.pg_get_userbyid(p.proowner),"
    " pg_catalog.pg_get_userbyid(p.proowner) = current_user,"
    " p.prosrc,"
    " ARRAY(SELECT e.entry FROM (SELECT CASE WHEN a.grantee = 0 THEN 'PUBLIC'"
    " ELSE pg_catalog.pg_get_userbyid(a.grantee) END || '=' || a.privilege_type AS entry"
    " FROM pg_catalog.aclexplode(COALESCE(p.proacl, pg_catalog.acldefault('f', p.proowner))) AS a)"
    ' AS e ORDER BY e.entry COLLATE "C")'
    " FROM pg_catalog.pg_proc AS p"
    " JOIN pg_catalog.pg_language AS l ON l.oid = p.prolang"
    f" WHERE p.pronamespace = 'public'::regnamespace AND p.proname = '{FUNCTION}'"
    ' ORDER BY pg_catalog.pg_get_function_identity_arguments(p.oid) COLLATE "C"'
)
FUNCTION_FIELDS = (
    "arguments", "returns", "language", "security_definer", "kind", "volatility", "config",
    "owner", "owned_by_applying_role", "source", "acl",
)
# Every other function in public: 0016 must leave each exactly as it was.
OTHER_FUNCTIONS_SQL = (
    "SELECT p.proname::text || '(' || pg_catalog.pg_get_function_identity_arguments(p.oid) || ')',"
    " pg_catalog.pg_get_userbyid(p.proowner), p.prosecdef, COALESCE(p.proconfig, ARRAY[]::text[]),"
    " pg_catalog.md5(p.prosrc), COALESCE(p.proacl::text, '')"
    " FROM pg_catalog.pg_proc AS p"
    f" WHERE p.pronamespace = 'public'::regnamespace AND p.proname <> '{FUNCTION}'"
    ' ORDER BY p.proname::text COLLATE "C",'
    ' pg_catalog.pg_get_function_identity_arguments(p.oid) COLLATE "C"'
)
OTHER_FUNCTION_FIELDS = ("function", "owner", "security_definer", "config", "source_md5", "acl")


def _tables_sql(names: Sequence[str]) -> str:
    """The listed tables, each resolved in ``public`` as the security check resolves it."""

    listed = ", ".join(f"('{name}')" for name in names)
    return (
        f"(SELECT t.name, pg_catalog.to_regclass('public.' || t.name) AS oid"
        f" FROM (VALUES {listed}) AS t(name)) AS t"
    )


_TABLES = _tables_sql(TABLES)
# The whole schema fingerprint of every table but its policies, which the policies check reads:
# one row per item, "table/kind/name" -> detail. 0016 changes none of it.
SCHEMA_FINGERPRINT_SQL = (
    "SELECT item, detail FROM ("
    "SELECT t.name || '/column/' || a.attname::text AS item,"
    " pg_catalog.format_type(a.atttypid, a.atttypmod) || ' notnull=' || a.attnotnull::text"
    " || ' default=' || COALESCE(pg_catalog.pg_get_expr(d.adbin, d.adrelid), '')"
    " || ' acl=' || COALESCE(a.attacl::text, '') AS detail"
    f" FROM {_TABLES}"
    " JOIN pg_catalog.pg_attribute AS a ON a.attrelid = t.oid"
    " LEFT JOIN pg_catalog.pg_attrdef AS d ON d.adrelid = a.attrelid AND d.adnum = a.attnum"
    " WHERE a.attnum > 0 AND NOT a.attisdropped"
    " UNION ALL"
    " SELECT t.name || '/constraint/' || c.conname::text,"
    " c.contype::text || ' validated=' || c.convalidated::text || ' '"
    " || pg_catalog.pg_get_constraintdef(c.oid)"
    f" FROM {_TABLES}"
    " JOIN pg_catalog.pg_constraint AS c ON c.conrelid = t.oid"
    " UNION ALL"
    " SELECT t.name || '/index/' || i.relname::text, pg_catalog.pg_get_indexdef(x.indexrelid)"
    f" FROM {_TABLES}"
    " JOIN pg_catalog.pg_index AS x ON x.indrelid = t.oid"
    " JOIN pg_catalog.pg_class AS i ON i.oid = x.indexrelid"
    " UNION ALL"
    " SELECT t.name || '/trigger/' || g.tgname::text,"
    " g.tgenabled::text || ' ' || g.tgtype::text || ' ' || g.tgfoid::regproc::text"
    f" FROM {_TABLES}"
    " JOIN pg_catalog.pg_trigger AS g ON g.tgrelid = t.oid"
    " WHERE NOT g.tgisinternal"
    ') AS fingerprint ORDER BY item COLLATE "C"'
)
SCHEMA_FINGERPRINT_FIELDS = ("item", "detail")
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
REHEARSAL_URL_VARIABLE = "MIGRATION_0016_REHEARSAL_URL"
# The function body the checks require before and after: migration 0015's, read from its file.
FUNCTION_SOURCE = function_source((ROOT / FUNCTION_MIGRATION).read_text(encoding="utf-8"))
_COMMIT_SHA = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_DIGITS = re.compile(r"[0-9]+")


def read_only_checks(server_version: int) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    """(name, query, fields) of every check, read in this order before and after the migration."""

    return (
        ("server", SERVER_SQL, SERVER_FIELDS),
        ("roles", ROLES_STATE_SQL, ROLE_FIELDS),
        ("memberships", memberships_sql(server_version), MEMBERSHIP_FIELDS),
        ("grants", grants_sql(server_version), GRANT_FIELDS),
        ("sequence_grants", SEQUENCE_GRANTS_SQL, SEQUENCE_GRANT_FIELDS),
        ("schema", SCHEMA_SQL, SCHEMA_FIELDS),
        ("schema_grants", SCHEMA_GRANTS_SQL, SCHEMA_GRANT_FIELDS),
        ("policies", POLICIES_SQL, POLICY_FIELDS),
        ("function", FUNCTION_SQL, FUNCTION_FIELDS),
        ("other_functions", OTHER_FUNCTIONS_SQL, OTHER_FUNCTION_FIELDS),
        ("security", security_sql(server_version), SECURITY_FIELDS),
        ("schema_fingerprint", SCHEMA_FINGERPRINT_SQL, SCHEMA_FINGERPRINT_FIELDS),
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

    The scratch database is built from migrations 0001-0015 with Supabase-like roles, default
    privileges and PostgREST's authenticator. It runs as the role this process connects as, which
    holds CREATEROLE without SUPERUSER, exactly as production's applying role does. The four roles,
    their grants and policies, and the bundle RPC's new owner must come out exactly as reviewed.
    """

    url = environ.get(REHEARSAL_URL_VARIABLE, "")
    if not _LOCAL_SOCKET_URL.fullmatch(url):
        raise _refusal(
            f"{REHEARSAL_URL_VARIABLE} must be a local unix-socket URL, e.g. "
            "postgresql:///migration_0016_rehearsal?host=/var/run/postgresql"
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
                    "the database is not in the state a first apply of 0016 requires: "
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
    """Pure: every way the database differs from the state a first apply of 0016 requires."""

    return (
        server_pre_check_failures(pre["server"])
        + roles_pre_check_failures(pre["roles"])
        + policies_pre_check_failures(pre["policies"])
        + function_pre_check_failures(pre["function"])
        + schema_pre_check_failures(pre["schema"])
        + security_pre_check_failures(pre["security"])
    )


def server_pre_check_failures(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    version = rows[0].get("server_version_num") if len(rows) == 1 else None
    if not isinstance(version, int) or isinstance(version, bool):
        return [f"the server version was read as {list(rows)!r}"]
    if version < MEMBERSHIP_OPTIONS_SINCE_SERVER_VERSION:
        return [f"the server version {version} is not PostgreSQL 16 or later"]
    return []


def roles_pre_check_failures(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """authenticator exists, the applying role holds CREATEROLE, and no new role exists yet."""

    by_name = {row.get("role"): row for row in rows}
    failures: list[str] = []
    present = [role for role in NEW_ROLES if role in by_name]
    if present:
        failures.append(f"{NOT_A_FIRST_APPLY}: the role(s) {', '.join(present)} already exist")
    if AUTHENTICATOR not in by_name:
        failures.append("PostgREST's authenticator role does not exist")
    applying = [row for row in rows if row.get("is_applying_role") is True]
    if len(applying) != 1:
        failures.append(f"the applying role was read {len(applying)} times, not once")
    elif not (applying[0].get("createrole") is True or applying[0].get("superuser") is True):
        failures.append("the applying role holds neither CREATEROLE nor SUPERUSER")
    return failures


def policies_pre_check_failures(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    ours = sorted(name for name in expected_policies() if name in {row.get("item") for row in rows})
    if ours:
        return [f"{NOT_A_FIRST_APPLY}: the policies {', '.join(ours)} already exist"]
    return []


def function_pre_check_failures(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Exactly migration 0015's bundle RPC: SECURITY INVOKER, the applying role's, and executable
    by service_role and none of PUBLIC, anon and authenticated (any other grantee is recorded)."""

    if len(rows) != 1:
        return [f"{FUNCTION_REFERENCE} exists {len(rows)} times, not once"]
    row = rows[0]
    if row.get("security_definer") is True and row.get("owner") == BUNDLE_OWNER:
        return [
            f"{NOT_A_FIRST_APPLY}: {FUNCTION_REFERENCE} is already SECURITY DEFINER of"
            f" {BUNDLE_OWNER}"
        ]
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
    }
    failures = [
        f"{FUNCTION_REFERENCE}: {field} is {row.get(field)!r}, not migration 0015's {value!r}"
        for field, value in expected.items()
        if row.get(field) != value
    ]
    acl = row.get("acl") if isinstance(row.get("acl"), list) else []
    if "service_role=EXECUTE" not in acl:
        failures.append(f"{FUNCTION_REFERENCE}: service_role may not execute it")
    exposed = [
        entry for entry in acl if entry.split("=", 1)[0] in ("PUBLIC", "anon", "authenticated")
    ]
    if exposed:
        failures.append(f"{FUNCTION_REFERENCE}: {', '.join(exposed)} may execute it")
    return failures


def schema_pre_check_failures(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    if len(rows) != 1 or rows[0].get("schema") != "public":
        return [f"the schema public was read as {list(rows)!r}"]
    failures = []
    if rows[0].get("applying_role_may_create") is not True:
        failures.append("the applying role may not CREATE in schema public")
    if rows[0].get("applying_role_holds_owner_privileges") is not True:
        failures.append("the applying role does not hold schema public's owner privileges")
    return failures


def security_pre_check_failures(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Each table once, an ordinary table, owned by the applying role, which grants on it."""

    if [row.get("table") for row in rows] != list(TABLES):
        return [f"the tables read were {[row.get('table') for row in rows]}"]
    failures: list[str] = []
    for row in rows:
        table = row.get("table")
        if row.get("relations_named_so") != 1:
            failures.append(
                f"{table}: {row.get('relations_named_so')!r} relations have this name, not one"
            )
        if row.get("relkind") != "r":
            failures.append(f"{table}: is {row.get('relkind')!r}, not an ordinary table")
        if row.get("owned_by_applying_role") is not True:
            failures.append(f"{table}: is not owned by the applying role, which grants on it")
    return failures


def post_check_failures(
    pre: Mapping[str, Sequence[Mapping[str, Any]]],
    post: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[str]:
    """Pure: every way the applied database differs from the reviewed result."""

    applying = [row.get("role") for row in pre["roles"] if row.get("is_applying_role") is True]
    applying_role = applying[0] if len(applying) == 1 else None
    applying_superuser = any(
        row.get("is_applying_role") is True and row.get("superuser") is True for row in pre["roles"]
    )
    return (
        _unchanged_failures("server", "server_version_num", pre["server"], post["server"])
        + roles_post_check_failures(pre["roles"], post["roles"])
        + memberships_post_check_failures(
            pre["memberships"], post["memberships"], applying_role, applying_superuser
        )
        + grants_post_check_failures(post["grants"], post["sequence_grants"])
        + schema_post_check_failures(pre["schema"], post["schema"], post["schema_grants"])
        + policies_post_check_failures(pre["policies"], post["policies"])
        + function_post_check_failures(pre["function"], post["function"])
        + _unchanged_failures(
            "function", "function", pre["other_functions"], post["other_functions"]
        )
        + security_post_check_failures(pre["security"], post["security"])
        + _unchanged_failures(
            "schema item", "item", pre["schema_fingerprint"], post["schema_fingerprint"]
        )
        + _unchanged_failures(
            "event trigger", "event_trigger", pre["event_triggers"], post["event_triggers"]
        )
    )


def roles_post_check_failures(
    pre: Sequence[Mapping[str, Any]], post: Sequence[Mapping[str, Any]]
) -> list[str]:
    """The four roles exist with no attribute at all; authenticator and the applier unchanged."""

    failures = _unchanged_failures(
        "role",
        "role",
        [row for row in pre if row.get("role") not in NEW_ROLES],
        [row for row in post if row.get("role") not in NEW_ROLES],
    )
    by_name = {row.get("role"): row for row in post}
    attributes = ("superuser", "inherit", "createrole", "createdb", "login", "replication",
                  "bypassrls", "is_applying_role")
    for role in NEW_ROLES:
        row = by_name.get(role)
        if row is None:
            failures.append(f"the role {role} is missing after the apply")
            continue
        held = [attribute for attribute in attributes if row.get(attribute) is not False]
        if held:
            failures.append(f"the role {role} holds {', '.join(held)}")
    return failures


def memberships_post_check_failures(
    pre: Sequence[Mapping[str, Any]],
    post: Sequence[Mapping[str, Any]],
    applying_role: str | None,
    applying_superuser: bool,
) -> list[str]:
    """Only the writer's membership in authenticator (SET, no INHERIT, no ADMIN) is new, beside at
    most the ADMIN grants PostgreSQL 16 gives a CREATEROLE creator (no SET, no INHERIT)."""

    def key(row: Mapping[str, Any]) -> tuple:
        return tuple(row.get(field) for field in MEMBERSHIP_FIELDS)

    before = {key(row) for row in pre}
    after = {key(row) for row in post}
    failures = [
        f"the membership {row!r} is gone after the apply"
        for row in sorted(before - after, key=repr)
    ]
    # A SUPERUSER's grants are recorded as the bootstrap superuser's, so only then may the writer's
    # membership name another grantor.
    writer = {(WRITER, AUTHENTICATOR, granted, False, False, True)
              for granted in ((True, False) if applying_superuser else (True,))}
    creator = {(role, applying_role, False, True, False, False) for role in NEW_ROLES}
    new = after - before
    if len(new & writer) != 1:
        failures.append("authenticator cannot switch to the writer (SET without INHERIT)")
    unexpected = new - writer - creator
    failures += [
        f"the membership {row!r} appeared during the apply"
        for row in sorted(unexpected, key=repr)
    ]
    granted_to_creator = new & creator
    if applying_superuser and granted_to_creator:
        failures.append("a SUPERUSER applier was granted the new roles")
    if not applying_superuser and granted_to_creator != creator:
        failures.append("the CREATEROLE creator's ADMIN grants are not exactly the four roles'")
    return failures


def grants_post_check_failures(
    grants: Sequence[Mapping[str, Any]], sequence_grants: Sequence[Mapping[str, Any]]
) -> list[str]:
    """Each new role holds exactly its list on every table and sequence: nothing more or less."""

    failures: list[str] = []
    for rows, objects, expected, what in (
        (grants, TABLES, EXPECTED_GRANTS, "table"),
        (sequence_grants, SEQUENCES, EXPECTED_SEQUENCE_GRANTS, "sequence"),
    ):
        field = "table" if what == "table" else "sequence"
        found = {(row.get("role"), row.get(field)): row.get("privileges") for row in rows}
        if len(found) != len(rows) or set(found) != {(r, o) for r in NEW_ROLES for o in objects}:
            failures.append(f"the {what} privileges were read for {sorted(found)!r}")
            continue
        for role in NEW_ROLES:
            for name in objects:
                wanted = list(expected.get(role, {}).get(name, ()))
                if found[(role, name)] != wanted:
                    failures.append(
                        f"{role} holds {found[(role, name)]!r} on the {what} {name}, not {wanted!r}"
                    )
    return failures


def schema_post_check_failures(
    pre: Sequence[Mapping[str, Any]],
    post: Sequence[Mapping[str, Any]],
    schema_grants: Sequence[Mapping[str, Any]],
) -> list[str]:
    """The schema's owner and every older role's rights unchanged; each new role USAGE only."""

    failures = _unchanged_failures("schema", "schema", pre, post)
    rights = {row.get("role"): (row.get("usage"), row.get("create")) for row in schema_grants}
    for role in NEW_ROLES:
        if rights.get(role) != (True, False):
            failures.append(f"{role} holds {rights.get(role)!r} (USAGE, CREATE) on schema public")
    if set(rights) != set(NEW_ROLES):
        failures.append(f"the schema rights were read for {sorted(rights)!r}")
    return failures


def policies_post_check_failures(
    pre: Sequence[Mapping[str, Any]], post: Sequence[Mapping[str, Any]]
) -> list[str]:
    """Every older policy unchanged, plus exactly the 40 of 0016."""

    expected = expected_policies()
    failures = _unchanged_failures(
        "policy", "item", pre, [row for row in post if row.get("item") not in expected]
    )
    found = {row.get("item"): row for row in post if row.get("item") in expected}
    for item, (command, permissive, roles, using, check) in sorted(expected.items()):
        row = found.get(item)
        if row is None:
            failures.append(f"the policy {item} is missing after the apply")
            continue
        observed = (row.get("command"), row.get("permissive"), row.get("roles"), row.get("using"),
                    row.get("with_check"))
        if observed != (command, permissive, roles, using, check):
            wanted = (command, permissive, roles, using, check)
            failures.append(f"the policy {item} is {observed!r}, not {wanted!r}")
    return failures


def function_post_check_failures(
    pre: Sequence[Mapping[str, Any]], rows: Sequence[Mapping[str, Any]]
) -> list[str]:
    """Pure: the bundle RPC as reviewed: SECURITY DEFINER of its narrow owner, body unchanged, and
    EXECUTE exactly as before but for the owner's entry, which moves to the new owner, and the
    writer's, which is added."""

    if len(rows) != 1:
        return [f"{FUNCTION_REFERENCE}: {_count_after(rows)}"]
    row = rows[0]
    before = pre[0] if len(pre) == 1 else {}
    old_acl = before.get("acl") if isinstance(before.get("acl"), list) else []
    acl = sorted(
        {entry for entry in old_acl if entry != f"{before.get('owner')}=EXECUTE"}
        | {f"{BUNDLE_OWNER}=EXECUTE", f"{WRITER}=EXECUTE"}
    )
    expected = {
        "arguments": FUNCTION_ARGUMENTS,
        "returns": "jsonb",
        "language": "plpgsql",
        "security_definer": True,
        "kind": "f",
        "volatility": "v",
        "config": list(FUNCTION_CONFIG),
        "owner": BUNDLE_OWNER,
        "owned_by_applying_role": False,
        "source": FUNCTION_SOURCE,
        "acl": acl,
    }
    return [
        f"{FUNCTION_REFERENCE}: {field} is {row.get(field)!r}, not {value!r}"
        for field, value in expected.items()
        if row.get(field) != value
    ]


def security_post_check_failures(
    pre: Sequence[Mapping[str, Any]], post: Sequence[Mapping[str, Any]]
) -> list[str]:
    """Every table's security unchanged but its policy count, which grows by exactly 0016's."""

    added: dict[str, int] = {}
    for item in expected_policies():
        table = item.split("/", 1)[0]
        added[table] = added.get(table, 0) + 1

    def without_policies(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        return [{k: v for k, v in row.items() if k != "policies"} for row in rows]

    failures = _unchanged_failures(
        "security of table", "table", without_policies(pre), without_policies(post)
    )
    before = {row.get("table"): row.get("policies") for row in pre}
    for row in post:
        table = row.get("table")
        wanted = (before.get(table) or 0) + added.get(table, 0)
        if row.get("policies") != wanted:
            failures.append(f"{table} has {row.get('policies')!r} policies, not {wanted}")
    return failures


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

    return ProvenanceRefused(f"migration 0016 refused; nothing is applied: {message}")


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
