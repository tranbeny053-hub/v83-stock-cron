#!/usr/bin/env python
"""One-shot, fail-closed application of authored migration 0019 and the pilot capacity row."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = "migrations/authored/0019_lattice_evidence.sql"
CAPACITY = "scripts/migration_0019_capacity.sql"
WORKFLOW = "ops/ng4_pilot/workflows/apply-migration-0019.yml"
MIGRATION_SHA256 = "8ae3c32968bb250f9700047309456606f8f75ac9b2580712f999b087355c9dc6"
CAPACITY_SHA256 = "ef1fa7af0cf370604c2ad593f84833d23e5722083141b016ef7b3afff25f3b52"
CONFIRMATION = "APPLY-MIGRATION-0019-ONCE"
REPORT_SCHEMA = "migration-0019-apply-report.v1"
EXPECTED_REPOSITORY = "tranbeny053-hub/v83-stock-cron"
PINNED_PYTHON = ("CPython", "3.13.14")


class Refused(Exception):
    pass


def refuse_url(url: str) -> str | None:
    if "supabase" in url.lower():
        return "the URL names supabase"
    parsed = urlparse(url)
    if parsed.scheme not in ("postgresql", "postgres"):
        return "the URL is not a postgresql URL"
    if parsed.password:
        return "the URL contains a password"
    host = parsed.hostname or ""
    socket = parse_qs(parsed.query).get("host", [""])[0]
    local = host in ("localhost", "127.0.0.1") or (host == "" and socket.startswith("/"))
    return None if local else "the URL is not local"


def pinned_bytes() -> tuple[bytes, bytes]:
    migration, capacity = (ROOT / MIGRATION).read_bytes(), (ROOT / CAPACITY).read_bytes()
    if hashlib.sha256(migration).hexdigest() != MIGRATION_SHA256:
        raise Refused("migration digest mismatch")
    if hashlib.sha256(capacity).hexdigest() != CAPACITY_SHA256:
        raise Refused("capacity digest mismatch")
    return migration, capacity


CHECKS = {
    "server_16_plus": "SELECT current_setting('server_version_num')::int >= 160000",
    "schema_absent": "SELECT NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='ucpe_lattice')",
    "roles_absent": (
        "SELECT NOT EXISTS (SELECT 1 FROM pg_roles "
        "WHERE rolname IN ('ucpe_lattice_owner','ucpe_lattice_writer'))"
    ),
    "createrole": "SELECT rolcreaterole FROM pg_roles WHERE rolname=current_user",
    "not_superuser": "SELECT NOT rolsuper FROM pg_roles WHERE rolname=current_user",
    "createrole_self_grant_empty": "SELECT current_setting('createrole_self_grant') = ''",
    "no_bypassrls_data_role_member": (
        "SELECT NOT EXISTS (SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member "
        "JOIN pg_roles g ON g.oid=m.roleid WHERE g.rolname IN "
        "('pg_read_all_data','pg_write_all_data') AND r.rolbypassrls AND NOT r.rolsuper "
        "AND r.rolname<>current_user)"
    ),
    "no_all_tables_publication": (
        "SELECT NOT EXISTS (SELECT 1 FROM pg_publication WHERE puballtables)"
    ),
}
RECORDED_CHECKS = {
    "track_commit_timestamp_on": "SELECT current_setting('track_commit_timestamp') = 'on'",
    "roles_that_can_set_role_to_me": (
        "SELECT count(*) FROM pg_auth_members m "
        "WHERE m.roleid=(SELECT oid FROM pg_roles WHERE rolname=current_user) AND m.set_option"
    ),
    "event_triggers_ddl": (
        "SELECT count(*) FROM pg_event_trigger "
        "WHERE evtevent IN ('ddl_command_end','ddl_command_start')"
    ),
}

OUTSIDE_SNAPSHOT = """
SELECT jsonb_build_object(
 'roles',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY x::text),'[]') FROM (
   SELECT rolname, rolsuper, rolinherit, rolcreaterole, rolcreatedb, rolcanlogin,
          rolreplication, rolbypassrls FROM pg_roles
    WHERE rolname NOT IN ('ucpe_lattice_owner','ucpe_lattice_writer')) x),
 'memberships',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY x::text),'[]') FROM (
   SELECT pg_get_userbyid(m.roleid) AS role, pg_get_userbyid(m.member) AS member,
          pg_get_userbyid(m.grantor) AS grantor, m.admin_option, m.inherit_option, m.set_option
     FROM pg_auth_members m
    WHERE pg_get_userbyid(m.roleid) NOT IN ('ucpe_lattice_owner','ucpe_lattice_writer')
      AND pg_get_userbyid(m.member) NOT IN ('ucpe_lattice_owner','ucpe_lattice_writer')) x),
 'grants',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY x::text),'[]') FROM (
   SELECT n.nspname, c.relname, c.relkind, c.relacl::text AS acl FROM pg_class c
     JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname<>'ucpe_lattice') x),
 'schema_grants',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY x::text),'[]') FROM (
   SELECT nspname, nspacl::text AS acl FROM pg_namespace WHERE nspname<>'ucpe_lattice') x),
 'policies',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY x::text),'[]') FROM (
   SELECT schemaname, tablename, policyname, roles::text, cmd, qual, with_check
     FROM pg_policies WHERE schemaname<>'ucpe_lattice') x),
 'functions',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY x::text),'[]') FROM (
   SELECT n.nspname, p.proname, pg_get_function_identity_arguments(p.oid) AS args,
          pg_get_userbyid(p.proowner) AS owner, p.proacl::text AS acl, p.prosrc,
          p.prosecdef, p.proconfig::text AS config FROM pg_proc p
     JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname<>'ucpe_lattice') x),
 'publications',(SELECT coalesce(jsonb_agg(to_jsonb(p) ORDER BY pubname),'[]')
   FROM pg_publication p),
 'default_acls',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY x::text),'[]') FROM (
   SELECT pg_get_userbyid(defaclrole) AS role, defaclnamespace::regnamespace::text AS schema,
          defaclobjtype, defaclacl::text AS acl FROM pg_default_acl) x),
 'event_triggers',(SELECT coalesce(jsonb_agg(to_jsonb(e) ORDER BY evtname),'[]')
   FROM pg_event_trigger)
)::text
"""


def _scalar(cur, sql):
    cur.execute(sql)
    row = cur.fetchone()
    return row[0] if row else None


def _outside_fingerprint(cur):
    import hashlib

    return hashlib.sha256(str(_scalar(cur, OUTSIDE_SNAPSHOT)).encode("utf-8")).hexdigest()


def _checks(cur, records, prefix):
    result = {}
    for name, sql in CHECKS.items():
        result[name] = _scalar(cur, sql)
        records[f"{prefix}.{name}"] = result[name]
    return result


def _pre_failures(values):
    return [key for key, expected in CHECKS.items() if values.get(key) is not True]


def verify_dispatch(env, expected_sha):
    actual = env.get("GITHUB_SHA", "")
    ref = env.get("GITHUB_REF", "")
    workflow_ref = env.get("GITHUB_WORKFLOW_REF", "")
    failures = []
    if env.get("GITHUB_ACTIONS") != "true":
        failures.append("not GitHub Actions")
    if env.get("GITHUB_REPOSITORY") != EXPECTED_REPOSITORY:
        failures.append("repository mismatch")
    if env.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        failures.append("event mismatch")
    if ref != "refs/heads/main":
        failures.append("ref mismatch")
    if workflow_ref != f"{EXPECTED_REPOSITORY}/{WORKFLOW}@refs/heads/main":
        failures.append("workflow mismatch")
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha or "") or actual != expected_sha:
        failures.append("expected SHA mismatch")
    if (platform.python_implementation(), platform.python_version()) != PINNED_PYTHON:
        failures.append("Python runtime mismatch")
    if failures:
        raise Refused("dispatch refused: " + ", ".join(failures))


def apply_in_one_transaction(open_connection, migration: bytes, capacity: bytes, captured=None):
    records = {} if captured is None else captured
    with open_connection() as conn, conn.cursor() as cur:
        cur.execute("SET LOCAL lock_timeout = '10s'")
        cur.execute("SET LOCAL statement_timeout = '120s'")
        cur.execute("SELECT pg_advisory_xact_lock(5000019)")
        before = _checks(cur, records, "pre")
        for name, sql in RECORDED_CHECKS.items():
            records[name] = _scalar(cur, sql)
        failures = _pre_failures(before)
        if failures:
            raise Refused("pre-check refusal: " + ", ".join(failures))
        outside_before = _outside_fingerprint(cur)
        records["outside_before"] = outside_before
        cur.execute(migration.decode("utf-8"))
        records["migration_executed"] = True
        cur.execute(capacity.decode("utf-8"))
        records["capacity_executed"] = True
        after = _checks(cur, records, "post")
        outside_after = _outside_fingerprint(cur)
        records["outside_after"] = outside_after
        if before != after or outside_before != outside_after:
            raise Refused("post-check catalog mismatch")
        # PostgreSQL 16 CREATEROLE auto-grant must be ADMIN-only for the applier.
        cur.execute("""SELECT m.admin_option AND NOT m.inherit_option AND NOT m.set_option
            FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid
            JOIN pg_roles u ON u.oid=m.member
            WHERE r.rolname IN ('ucpe_lattice_owner','ucpe_lattice_writer')
              AND u.rolname=current_user ORDER BY r.rolname""")
        memberships = cur.fetchall()
        records["creator_memberships"] = len(memberships)
        if len(memberships) != 2 or any(not row[0] for row in memberships):
            raise Refused("post-check creator membership mismatch")
        cur.execute("""SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid
            WHERE r.rolname IN ('ucpe_lattice_owner','ucpe_lattice_writer')
              AND m.member<>(SELECT oid FROM pg_roles WHERE rolname=current_user)""")
        if cur.fetchone()[0] != 0:
            raise Refused("post-check unexpected lattice member")
        cur.execute("""SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member
            WHERE r.rolname='ucpe_lattice_writer'""")
        if cur.fetchone()[0] != 0:
            raise Refused("post-check writer membership")
        cur.execute("""SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='ucpe_lattice' AND c.relkind IN ('r','p')
              AND has_table_privilege('ucpe_lattice_writer',c.oid,
              'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')""")
        if cur.fetchone()[0] != 0:
            raise Refused("post-check writer table privilege")
        records["commit_attempted"] = True
        conn.commit()
        records["committed"] = True
    return records


def main(argv=None, *, environ=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("attest", "rehearse", "apply"), required=True)
    parser.add_argument("--report")
    parser.add_argument("--expected-sha")
    parser.add_argument("--confirm")
    parser.add_argument("--wheelhouse")
    args = parser.parse_args(argv)
    env = os.environ if environ is None else environ
    report = {
        "schema": REPORT_SCHEMA,
        "outcome": "FAILED",
        "committed": False,
        "refusals": [],
        "checks": {},
        "migration_sha256": MIGRATION_SHA256,
        "capacity_sha256": CAPACITY_SHA256,
    }
    try:
        migration, capacity = pinned_bytes()
        if args.mode == "attest":
            verify_dispatch(env, args.expected_sha)
            report["outcome"] = "APPLIED"
        else:
            if args.mode == "apply" and args.confirm != CONFIRMATION:
                raise Refused("confirmation mismatch")
            if args.mode == "apply":
                verify_dispatch(env, args.expected_sha)
            variable = (
                "MIGRATION_0019_REHEARSAL_URL" if args.mode == "rehearse" else "SUPABASE_DB_URL"
            )
            url = env.get(variable, "")
            reason = refuse_url(url) if args.mode == "rehearse" else None
            if reason or not url or (args.mode == "rehearse" and env.get("SUPABASE_DB_URL")):
                raise Refused("database URL refused")
            import psycopg

            checks = report["checks"]

            def opener():
                return psycopg.connect(url, connect_timeout=8)

            apply_in_one_transaction(opener, migration, capacity, checks)
            if args.mode == "rehearse":
                second = {}
                try:
                    apply_in_one_transaction(opener, migration, capacity, second)
                except Refused as exc:
                    checks["second_run_refused"] = True
                    checks["second_run_refusal"] = str(exc)
                else:
                    raise Refused("second rehearsal apply was not refused")
            report["outcome"] = "APPLIED"
            report["committed"] = True
        code = 0
    except Refused as exc:
        report["outcome"] = "REFUSED"
        report["refusals"] = [str(exc)]
        code = 2
    except Exception as exc:
        report["outcome"] = "FAILED"
        report["committed"] = (
            "UNKNOWN" if report.get("checks", {}).get("commit_attempted") else False
        )
        report["refusals"] = [type(exc).__name__]
        code = 1
    encoded = json.dumps(report, sort_keys=True)
    print(encoded, file=sys.stdout if code == 0 else sys.stderr)
    if args.report:
        Path(args.report).write_text(encoded + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
