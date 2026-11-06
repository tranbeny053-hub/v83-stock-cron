#!/usr/bin/env python
"""Read-only catalog preflight for the dormant NG4 pilot route."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = "ops/ng4_pilot/workflows/ng4-pilot-preflight.yml"
REPORT_SCHEMA = "ng4-pilot-preflight-report.v1"
SUPABASE_EVENT_TRIGGERS: tuple[
    str, ...
] = ()  # No fixed platform names are referenced in this repository.
EXPECTED_REPOSITORY = "tranbeny053-hub/v83-stock-cron"


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
        queries = {
            "server_16_plus": "SELECT current_setting('server_version_num')::int >= 160000",
            "track_commit_timestamp_on": "SELECT current_setting('track_commit_timestamp') = 'on'",
            "schema_absent": (
                "SELECT NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='ucpe_lattice')"
            ),
            "roles_absent": (
                "SELECT NOT EXISTS (SELECT 1 FROM pg_roles "
                "WHERE rolname IN ('ucpe_lattice_owner','ucpe_lattice_writer'))"
            ),
            "createrole": "SELECT rolcreaterole FROM pg_roles WHERE rolname=current_user",
            "not_superuser": "SELECT NOT rolsuper FROM pg_roles WHERE rolname=current_user",
            "createrole_self_grant_set": (
                "SELECT current_setting('createrole_self_grant') LIKE '%set%'"
            ),
            "createrole_self_grant_inherit": (
                "SELECT current_setting('createrole_self_grant') LIKE '%inherit%'"
            ),
            "no_bypassrls_data_role_member": (
                "SELECT NOT EXISTS (SELECT 1 FROM pg_auth_members m JOIN pg_roles r "
                "ON r.oid=m.member JOIN pg_roles g ON g.oid=m.roleid WHERE g.rolname IN "
                "('pg_read_all_data','pg_write_all_data') AND r.rolbypassrls "
                "AND NOT r.rolsuper AND r.rolname<>current_user)"
            ),
            "no_all_tables_publication": (
                "SELECT NOT EXISTS (SELECT 1 FROM pg_publication WHERE puballtables)"
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
            "ucpe_lattice_space_exists": (
                "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ucpe_lattice_space')"
            ),
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
        cur.execute("ROLLBACK")
    prerequisites = (
        "server_16_plus",
        "schema_absent",
        "roles_absent",
        "createrole",
        "not_superuser",
        "no_bypassrls_data_role_member",
        "no_all_tables_publication",
    )
    failing = [key for key in prerequisites if facts[key] is not True]
    if facts["createrole_self_grant_set"] or facts["createrole_self_grant_inherit"]:
        failing.append("createrole_self_grant_empty")
    return {
        "schema": REPORT_SCHEMA,
        "verdict": "READY" if not failing else "NOT_READY",
        "facts": facts,
        "failing": failing,
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
        if args.mode == "attest":
            verify_dispatch(env, args.expected_sha)
            report["verdict"] = "READY"
        else:
            url = (
                env.get("NG4_PILOT_PREFLIGHT_REHEARSAL_URL", "")
                if args.mode == "rehearse"
                else env.get("SUPABASE_DB_URL", "")
            )
            if args.mode == "rehearse" and env.get("SUPABASE_DB_URL"):
                raise ValueError("REFUSED")
            if args.mode == "run":
                verify_dispatch(env, args.expected_sha)
            refusal = refuse_url(url) if args.mode == "rehearse" else None
            if refusal or not url:
                raise ValueError("REFUSED")
            import psycopg

            report = preflight(lambda: psycopg.connect(url, connect_timeout=8))
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
