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
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence
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
STATEMENT_TIMEOUT_SQL = "SET LOCAL statement_timeout = '60s'"
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="D6: the core-evidence write inventory, read-only."
    )
    parser.add_argument("--role", default="service_role")
    parser.add_argument("--url-env", default="SUPABASE_DB_URL",
                        help="the environment variable holding the database URL (never printed)")
    parser.add_argument("--exposed", default=",".join(EXPOSED_SCHEMAS),
                        help="the schemas PostgREST exposes, comma-separated")
    parser.add_argument("--expect", choices=("before", "after"), required=True)
    arguments = parser.parse_args(argv)
    url = os.environ.get(arguments.url_env)
    if not url:
        print(f"REFUSED: {arguments.url_env} is not set", file=sys.stderr)
        return 2
    import psycopg

    with psycopg.connect(url, autocommit=False, prepare_threshold=None) as connection:
        with connection.cursor() as cursor:
            cursor.execute(READ_ONLY_SQL)
            cursor.execute(STATEMENT_TIMEOUT_SQL)
            cursor.execute("SHOW server_version_num")
            version = int(cursor.fetchone()[0])

            def execute(sql: str, values: dict[str, Any]) -> list[tuple]:
                cursor.execute(sql, values)
                return cursor.fetchall()

            report = collect(execute, role=arguments.role, server_version_num=version,
                             exposed=[name for name in arguments.exposed.split(",") if name])
        connection.rollback()
    failures = verdict(report, arguments.expect)
    report["expect"], report["failures"] = arguments.expect, failures
    report["verdict"] = "PASS" if not failures else "FAIL"
    print(json.dumps(report, indent=1, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
