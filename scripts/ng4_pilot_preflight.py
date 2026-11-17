#!/usr/bin/env python
"""Read-only catalog preflight for the dormant NG4 pilot route.

For the BYPASSRLS data-role check only, the report also names the roles and their data role
(catalog identifiers only, never values). Two owner-approved read-only roles are allowlisted;
their count is informational, while any write-role membership remains a hard failure. The report
also names DDL event triggers without exposing their definitions.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
# The path GitHub will report once the authored file is renamed into place (the enabling T3);
# today no such file exists, so no dispatch can match it (review R1-1).
WORKFLOW = ".github/workflows/ng4-pilot-preflight.yml"
REPORT_SCHEMA = "ng4-pilot-preflight-report.v1"
SUPABASE_EVENT_TRIGGERS: tuple[
    str, ...
] = ()  # No fixed platform names are referenced in this repository.
EXPECTED_REPOSITORY = "tranbeny053-hub/v83-stock-cron"
SOURCE = Path(__file__).resolve().parents[1] / "src"
SCRIPT = "scripts/ng4_pilot_preflight.py"
ALLOWED_BYPASSRLS_READERS = ("supabase_etl_admin", "supabase_read_only_user")
PREREQUISITES = (
    "server_16_plus", "schema_absent", "roles_absent", "lattice_space_absent",
    "createrole", "not_superuser", "createrole_self_grant_empty",
    "no_bypassrls_data_role_member", "no_all_tables_publication",
)
PREREQUISITE_SQL = {
    "server_16_plus": "SELECT current_setting('server_version_num')::int >= 160000",
    "schema_absent": "SELECT NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='ucpe_lattice')",
    "roles_absent": (
        "SELECT NOT EXISTS (SELECT 1 FROM pg_roles "
        "WHERE rolname IN ('ucpe_lattice_owner','ucpe_lattice_writer'))"
    ),
    "lattice_space_absent": (
        "SELECT NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ucpe_lattice_space')"
    ),
    "createrole": "SELECT rolcreaterole FROM pg_roles WHERE rolname=current_user",
    "not_superuser": "SELECT NOT rolsuper FROM pg_roles WHERE rolname=current_user",
    "createrole_self_grant_empty": "SELECT current_setting('createrole_self_grant') = ''",
    "no_bypassrls_data_role_member": (
        "SELECT NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles r CROSS JOIN "
        "(VALUES ('pg_read_all_data'),('pg_write_all_data')) g(rolname) "
        "WHERE pg_catalog.pg_has_role(r.oid, g.rolname::name, 'MEMBER') AND r.rolbypassrls "
        "AND NOT r.rolsuper "
        "AND r.rolname<>current_user AND NOT (g.rolname='pg_read_all_data' AND r.rolname IN "
        "('supabase_etl_admin','supabase_read_only_user')))"
    ),
    "no_all_tables_publication": (
        "SELECT NOT EXISTS (SELECT 1 FROM pg_publication WHERE puballtables)"
    ),
}
assert all(name in PREREQUISITE_SQL["no_bypassrls_data_role_member"]
           for name in ALLOWED_BYPASSRLS_READERS)
# The prerequisite's own FROM ... WHERE text, so the names are exactly the members it counts;
# DISTINCT is redundant since the predicate reads pg_roles x two names (no pg_auth_members); kept.
_BYPASSRLS_MEMBERS_FROM = (
    PREREQUISITE_SQL["no_bypassrls_data_role_member"].split(" FROM ", 1)[1][:-1]
)
BYPASSRLS_MEMBERS_SQL = (
    "SELECT coalesce(json_agg(json_build_array(x.rn, x.dn) ORDER BY x.rn, x.dn), '[]'::json)::text "
    "FROM (SELECT DISTINCT r.rolname AS rn, g.rolname AS dn FROM " + _BYPASSRLS_MEMBERS_FROM + ") x"
)
DDL_EVENT_TRIGGERS_SQL = (
    "SELECT coalesce(pg_catalog.json_agg(pg_catalog.json_build_array(e.evtname, e.evtevent, "
    "e.evtenabled::text) "
    "ORDER BY e.evtname, e.evtevent), '[]'::json)::text "
    "FROM pg_catalog.pg_event_trigger e WHERE e.evtevent IN "
    "('ddl_command_end','ddl_command_start')"
)
# A name that matches the identifier pattern can still look like a token (review R1-3): a run of 16+
# hexadecimal characters is replaced too.
_ROLE_NAME = re.compile(r"[a-z_][a-z0-9_$]{0,62}")
_TOKEN_LIKE = re.compile(r"[0-9a-f]{16,}")


def refuse_url(url: str) -> str | None:
    if "supabase" in url.lower():
        return "the URL names supabase"
    parsed = urlparse(url)
    if parsed.scheme not in ("postgresql", "postgres"):
        return "the URL is not a postgresql URL"
    host = parsed.hostname or ""
    socket = parse_qs(parsed.query).get("host", [""])[0]
    return (
        None
        if host in ("localhost", "127.0.0.1") or (host == "" and socket.startswith("/"))
        else "the URL is not local"
    )


def preflight(open_connection, captured: dict[str, Any] | None = None) -> dict[str, Any]:
    captured = {} if captured is None else captured
    with open_connection() as conn, conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute("SET LOCAL statement_timeout = '5000'")
        cur.execute("SET LOCAL lock_timeout = '2000'")
        queries = {
            **PREREQUISITE_SQL,
            "track_commit_timestamp_on": "SELECT current_setting('track_commit_timestamp') = 'on'",
            "createrole_self_grant_set": (
                "SELECT current_setting('createrole_self_grant') LIKE '%set%'"
            ),
            "createrole_self_grant_inherit": (
                "SELECT current_setting('createrole_self_grant') LIKE '%inherit%'"
            ),
            "roles_that_can_set_role_to_me": (
                "SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member "
                "WHERE m.roleid=(SELECT oid FROM pg_roles WHERE rolname=current_user) "
                "AND m.set_option"
            ),
            "event_triggers_ddl": (
                "SELECT count(*) FROM pg_event_trigger WHERE evtevent IN "
                "('ddl_command_end','ddl_command_start')"
            ),
            "event_triggers_ddl_not_allowlisted": (
                "SELECT count(*) FROM pg_event_trigger WHERE evtevent IN "
                "('ddl_command_end','ddl_command_start') AND evtname <> ALL(%s)"
            ),
            "session_replication_role_parameter_grants": (
                "SELECT count(*) FROM pg_parameter_acl a "
                "CROSS JOIN LATERAL aclexplode(a.paracl) x "
                "WHERE a.parname='session_replication_role'"
            ),
            "ucpe_space_db_exists": (
                "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ucpe_space_db')"
            ),
            "ucpe_space_db_inherit": (
                "SELECT COALESCE((SELECT rolinherit FROM pg_roles "
                "WHERE rolname='ucpe_space_db'), false)"
            ),
            "ucpe_space_db_memberships": (
                "SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member "
                "WHERE r.rolname='ucpe_space_db'"
            ),
            "ucpe_space_db_superuser_or_bypass": (
                "SELECT COALESCE((SELECT rolsuper OR rolbypassrls FROM pg_roles "
                "WHERE rolname='ucpe_space_db'), false)"
            ),
            "bypassrls_allowlisted_readers": (
                "SELECT count(*) FROM pg_catalog.pg_roles r WHERE r.rolname IN "
                "('supabase_etl_admin','supabase_read_only_user') AND r.rolbypassrls "
                "AND NOT r.rolsuper "
                "AND pg_catalog.pg_has_role(r.oid, 'pg_read_all_data', 'MEMBER') "
                "AND NOT pg_catalog.pg_has_role(r.oid, 'pg_write_all_data', 'MEMBER')"
            ),
            # Informational (review R1-2 and its delta notes): SET ROLE carries BYPASSRLS, so every
            # role that can SET ROLE to a named reader, or holds ADMIN on one (and can grant itself
            # SET), reads what the reader reads. The two named readers, superusers and the applier
            # are not counted. Never failing.
            "named_reader_set_role_paths": (
                "SELECT pg_catalog.count(DISTINCT u.oid) FROM pg_catalog.pg_roles u "
                "CROSS JOIN pg_catalog.pg_roles n "
                "WHERE n.rolname IN ('supabase_etl_admin','supabase_read_only_user') "
                "AND u.rolname NOT IN ('supabase_etl_admin','supabase_read_only_user') "
                "AND NOT u.rolsuper AND u.rolname<>current_user "
                "AND (pg_catalog.pg_has_role(u.oid, n.oid, 'SET') "
                "OR pg_catalog.pg_has_role(u.oid, n.oid, 'MEMBER WITH ADMIN OPTION'))"
            ),
            "ucpe_lattice_space_exists": (
                "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ucpe_lattice_space')"
            ),
            "applier_signal_backend": (
                "SELECT pg_has_role(current_user,'pg_signal_backend','USAGE')"
            ),
            "public_relation_privileges": """SELECT count(*) FROM pg_class c
                JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'
                AND c.relkind IN ('r','p','v','m','f','S')
                AND (has_table_privilege('public',c.oid,
                     'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
                OR has_any_column_privilege('public',c.oid,'SELECT,INSERT,UPDATE,REFERENCES')
                OR CASE WHEN c.relkind='S' THEN
                    has_sequence_privilege('public',c.oid,'USAGE,SELECT,UPDATE')
                ELSE false END)""",
            "public_executable_definers": """SELECT count(*) FROM pg_proc p
                JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.prosecdef
                AND has_schema_privilege('public',n.oid,'USAGE')
                AND has_function_privilege('public',p.oid,'EXECUTE')""",
            "public_schema_create": "SELECT has_schema_privilege('public','public','CREATE')",
            "public_database_create": """SELECT has_database_privilege(
                'public',current_database(),'CREATE')""",
            "public_database_temporary": """SELECT has_database_privilege(
                'public',current_database(),'TEMPORARY')""",
            "public_any_schema_create": """SELECT EXISTS (SELECT 1 FROM pg_namespace n
                WHERE has_schema_privilege('public',n.oid,'CREATE')
                AND n.oid <> pg_catalog.pg_my_temp_schema())""",
            "public_database_connect": """SELECT has_database_privilege(
                'public',current_database(),'CONNECT')""",
        }
        facts = {}
        for name, sql in queries.items():
            if name == "session_replication_role_parameter_grants":
                cur.execute("SELECT to_regclass('pg_catalog.pg_parameter_acl') IS NOT NULL")
                if not cur.fetchone()[0]:
                    facts[name] = 0
                    captured[name] = 0
                    continue
            cur.execute(
                sql,
                (list(SUPABASE_EVENT_TRIGGERS),)
                if name == "event_triggers_ddl_not_allowlisted"
                else None,  # no parameters: psycopg must not read the LIKE patterns' % as one
            )
            row = cur.fetchone()
            facts[name] = row[0] if row else 0
            captured[name] = facts[name]
        cur.execute(BYPASSRLS_MEMBERS_SQL)
        raw_members = json.loads(cur.fetchone()[0])
        if not isinstance(raw_members, list) or any(
            not isinstance(pair, list) or len(pair) != 2 for pair in raw_members
        ):
            raise RuntimeError("MALFORMED_MEMBERS")  # an error class, never REFUSED (review R1-2)
        members = []
        for pair in raw_members[:20]:
            role, data_role = pair
            members.append({
                "role": role if isinstance(role, str) and _ROLE_NAME.fullmatch(role)
                and not _TOKEN_LIKE.search(role) else "<non-identifier>",
                "data_role": data_role if data_role in (
                    "pg_read_all_data", "pg_write_all_data"
                ) else "<unexpected>",
            })
        # The fact and this list come from two statements (two snapshots under READ COMMITTED): they
        # must agree, or the run fails closed (review R1-6).
        if (not raw_members) != (facts["no_bypassrls_data_role_member"] is True):
            raise RuntimeError("INCONSISTENT_MEMBERS")
        captured["bypassrls_data_role_members"] = members
        if len(raw_members) > 20:
            captured["bypassrls_data_role_members_truncated"] = True
        cur.execute(DDL_EVENT_TRIGGERS_SQL)
        raw_triggers = json.loads(cur.fetchone()[0])
        if not isinstance(raw_triggers, list) or any(
            not isinstance(trigger, list) or len(trigger) != 3 for trigger in raw_triggers
        ):
            raise RuntimeError("MALFORMED_TRIGGERS")
        triggers = []
        enabled_states = {"O": "origin", "D": "disabled", "R": "replica", "A": "always"}
        for trigger in raw_triggers[:20]:
            name, event, enabled = trigger
            triggers.append({
                "name": name if isinstance(name, str) and _ROLE_NAME.fullmatch(name)
                and not _TOKEN_LIKE.search(name) else "<non-identifier>",
                "event": event if event in ("ddl_command_start", "ddl_command_end")
                else "<unexpected>",
                "enabled": enabled_states.get(enabled, "<unexpected>"),
            })
        # Compared always (the SQL returns the full list; review R1-8).
        if len(raw_triggers) != facts["event_triggers_ddl"]:
            raise RuntimeError("INCONSISTENT_TRIGGERS")
        captured["ddl_event_triggers"] = triggers
        if len(raw_triggers) > 20:
            captured["ddl_event_triggers_truncated"] = True
        cur.execute("ROLLBACK")
    failing = [key for key in PREREQUISITES if facts[key] is not True]
    for key in ("public_relation_privileges", "public_executable_definers"):
        if facts[key] != 0:
            failing.append(key)
    for key in ("public_schema_create", "public_database_create", "public_any_schema_create"):
        if facts[key] is True:
            failing.append(key)
    if facts["public_database_connect"] is not True:
        failing.append("public_database_connect")
    return {
        "schema": REPORT_SCHEMA,
        "verdict": "READY" if not failing else "NOT_READY",
        "facts": facts,
        "failing": failing,
        "bypassrls_data_role_members": members,
        **({"bypassrls_data_role_members_truncated": True} if len(raw_members) > 20 else {}),
        "ddl_event_triggers": triggers,
        **({"ddl_event_triggers_truncated": True} if len(raw_triggers) > 20 else {}),
    }


def verify_dispatch(env, expected_sha):
    failures = []
    if env.get("GITHUB_ACTIONS") != "true":
        failures.append("not GitHub Actions")
    if env.get("GITHUB_REPOSITORY") != EXPECTED_REPOSITORY:
        failures.append("repository mismatch")
    if env.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        failures.append("event mismatch")
    if env.get("GITHUB_REF") != "refs/heads/main":
        failures.append("ref mismatch")
    if env.get("GITHUB_WORKFLOW_REF") != f"{EXPECTED_REPOSITORY}/{WORKFLOW}@refs/heads/main":
        failures.append("workflow mismatch")
    if (
        not re.fullmatch(r"[0-9a-f]{40}", expected_sha or "")
        or env.get("GITHUB_SHA") != expected_sha
    ):
        failures.append("expected SHA mismatch")
    if platform.python_implementation() != "CPython" or platform.python_version() != "3.13.14":
        failures.append("Python runtime mismatch")
    if failures:
        raise ValueError("REFUSED")


def enter_isolated_runtime(wheelhouse):
    if not wheelhouse:
        raise ValueError("REFUSED")
    if str(SOURCE) not in sys.path:
        sys.path.append(str(SOURCE))
    from crypto_probability_engine import runtime_isolation
    return runtime_isolation.enter(SOURCE.parent, wheelhouse=Path(wheelhouse))


def attest_dispatch(env, expected_sha, isolation):
    from crypto_probability_engine import runtime_isolation
    root = SOURCE.parent
    status = subprocess.run(["git", "status", "--porcelain=v1", "--untracked-files=no"],
                            cwd=root, check=True, capture_output=True, text=True).stdout
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True,
                          capture_output=True, text=True).stdout.strip()
    python_runtime = (platform.python_implementation(), platform.python_version())
    if (status or head != expected_sha or env.get("GITHUB_SHA") != expected_sha
            or python_runtime != ("CPython", "3.13.14")
            or runtime_isolation.interpreter_flags() != runtime_isolation.REQUIRED_FLAGS_TEXT):
        raise ValueError("REFUSED")
    verify_dispatch(env, expected_sha)
    return {"workflow": WORKFLOW, "expected_sha": expected_sha, "git_head": head,
            "installed_files_sha256": isolation.installed_files_sha256}


def attest_loaded_modules(isolation):
    from crypto_probability_engine import runtime_isolation

    # As scripts/apply_migration_0018.py: the stdlib, the locked files, the evaluator pin's files
    # (runtime_isolation itself is one) and this script.
    from crypto_probability_engine.oos.evaluation.evaluator_pin import pinned_files

    root = SOURCE.parent
    return runtime_isolation.attest_loaded_modules(
        isolation, pinned=(*pinned_files(root), SCRIPT), root=root
    )


def load_driver():
    import psycopg
    return psycopg


def main(argv=None, *, environ=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("attest", "rehearse", "run"), required=True)
    parser.add_argument("--report")
    parser.add_argument("--expected-sha")
    parser.add_argument("--wheelhouse")
    args = parser.parse_args(argv)
    env = os.environ if environ is None else environ
    report = {"schema": REPORT_SCHEMA, "verdict": "NOT_READY", "facts": {}, "failing": []}
    try:
        if args.mode in ("attest", "run") and not args.wheelhouse:
            raise ValueError("REFUSED")
        if args.mode == "attest":
            isolation = enter_isolated_runtime(args.wheelhouse)
            report["dispatch"] = attest_dispatch(env, args.expected_sha, isolation)
            attest_loaded_modules(isolation)
            load_driver()
            attest_loaded_modules(isolation)
            report["verdict"] = "ATTESTED"
        else:
            url = (
                env.get("NG4_PILOT_PREFLIGHT_REHEARSAL_URL", "")
                if args.mode == "rehearse"
                else env.get("SUPABASE_DB_URL", "")
            )
            if args.mode == "rehearse" and env.get("SUPABASE_DB_URL"):
                raise ValueError("REFUSED")
            isolation = None
            if args.mode == "run":
                isolation = enter_isolated_runtime(args.wheelhouse)
                report["dispatch"] = attest_dispatch(env, args.expected_sha, isolation)
                attest_loaded_modules(isolation)
            elif args.wheelhouse:
                # As 0018: the dispatch workflow rehearses under `python -I -S -B`, where only the
                # authenticated wheelhouse provides the driver (W2 spec review R1-1).
                isolation = enter_isolated_runtime(args.wheelhouse)
            refusal = refuse_url(url) if args.mode == "rehearse" else None
            if refusal or not url:
                raise ValueError("REFUSED")
            driver = load_driver() if isolation is not None else __import__("psycopg")
            if isolation is not None:
                attest_loaded_modules(isolation)

            report = preflight(lambda: driver.connect(url, connect_timeout=8))
        code = 0
    except Exception as exc:
        code = 2 if type(exc).__name__ == "ValueError" else 1
        report["error"] = "REFUSED" if code == 2 else type(exc).__name__
    encoded = json.dumps(report, sort_keys=True)
    print(encoded)
    if args.report:
        Path(args.report).write_text(encoded + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
