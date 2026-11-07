#!/usr/bin/env python
"""One-shot, fail-closed application of authored migrations 0019/0020 and capacity."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = "migrations/authored/0019_lattice_evidence.sql"
CAPACITY = "scripts/migration_0019_capacity.sql"
MIGRATION_0020 = "migrations/authored/0020_lattice_space_login.sql"
# The path GitHub will report once the authored file is renamed into place (the enabling T3);
# today no such file exists, so no dispatch can match it (review R1-1).
WORKFLOW = ".github/workflows/apply-migration-0019.yml"
MIGRATION_SHA256 = "8ae3c32968bb250f9700047309456606f8f75ac9b2580712f999b087355c9dc6"
CAPACITY_SHA256 = "ef1fa7af0cf370604c2ad593f84833d23e5722083141b016ef7b3afff25f3b52"
MIGRATION_0020_SHA256 = "b5d74139e3c16e5db9bf42b4fd7e201a6d626202c91cd2ad283dc17d3dda669d"
CONFIRMATION = "APPLY-MIGRATIONS-0019-0020-ONCE"
REPORT_SCHEMA = "migration-0019-apply-report.v2"
EXPECTED_REPOSITORY = "tranbeny053-hub/v83-stock-cron"
PINNED_PYTHON = ("CPython", "3.13.14")
SOURCE = ROOT / "src"
SCRIPT = "scripts/apply_migration_0019.py"


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


def pinned_bytes() -> tuple[bytes, bytes, bytes]:
    migration, capacity, migration_0020 = (
        (ROOT / path).read_bytes() for path in (MIGRATION, CAPACITY, MIGRATION_0020)
    )
    if hashlib.sha256(migration).hexdigest() != MIGRATION_SHA256:
        raise Refused("migration digest mismatch")
    if hashlib.sha256(capacity).hexdigest() != CAPACITY_SHA256:
        raise Refused("capacity digest mismatch")
    if hashlib.sha256(migration_0020).hexdigest() != MIGRATION_0020_SHA256:
        raise Refused("migration 0020 digest mismatch")
    return migration, capacity, migration_0020


CHECKS = {
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
    WHERE rolname NOT IN ('ucpe_lattice_owner','ucpe_lattice_writer','ucpe_lattice_space')) x),
 'memberships',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY x::text),'[]') FROM (
   SELECT pg_get_userbyid(m.roleid) AS role, pg_get_userbyid(m.member) AS member,
          pg_get_userbyid(m.grantor) AS grantor, m.admin_option, m.inherit_option, m.set_option
     FROM pg_auth_members m
    WHERE pg_get_userbyid(m.roleid) NOT IN
          ('ucpe_lattice_owner','ucpe_lattice_writer','ucpe_lattice_space')
      AND pg_get_userbyid(m.member) NOT IN
          ('ucpe_lattice_owner','ucpe_lattice_writer','ucpe_lattice_space')) x),
 'grants',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY x::text),'[]') FROM (
   SELECT n.nspname, c.relname, c.relkind, c.relacl::text AS acl FROM pg_class c
     JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname NOT IN ('pg_catalog','information_schema','pg_toast','ucpe_lattice')) x),
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
   FROM pg_event_trigger e)
)::text
"""

POST_MEMBERSHIP_SQL = """SELECT pg_get_userbyid(r.oid), pg_get_userbyid(m.member),
 pg_get_userbyid(m.grantor), m.admin_option, m.inherit_option, m.set_option
 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid
 WHERE r.rolname IN ('ucpe_lattice_owner','ucpe_lattice_writer')
   AND m.member<>(SELECT oid FROM pg_roles WHERE rolname=current_user) ORDER BY 1"""
CURRENT_USER_SQL = "SELECT current_user"
POST_CREATOR_MEMBERSHIPS_SQL = """SELECT pg_get_userbyid(r.oid), pg_get_userbyid(m.grantor),
 m.admin_option, m.inherit_option, m.set_option
 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid
 WHERE r.rolname IN ('ucpe_lattice_owner','ucpe_lattice_writer','ucpe_lattice_space')
   AND m.member=(SELECT oid FROM pg_roles WHERE rolname=current_user) ORDER BY 1"""
POST_SPACE_ATTRIBUTES_SQL = """SELECT rolcanlogin, rolinherit, rolsuper, rolcreatedb, rolcreaterole,
 rolreplication, rolbypassrls, rolconnlimit, rolvaliduntil FROM pg_roles
 WHERE rolname='ucpe_lattice_space'"""
POST_SPACE_SETTINGS_SQL = """SELECT setdatabase, setconfig FROM pg_db_role_setting
 WHERE setrole=(SELECT oid FROM pg_roles WHERE rolname='ucpe_lattice_space') ORDER BY setdatabase"""
POST_RELATION_PRIVILEGES_SQL = """
SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname IN ('public','ucpe_lattice') AND c.relkind IN ('r','p','v','m','f','S')
 AND (has_table_privilege('ucpe_lattice_space',c.oid,
      'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
 OR has_any_column_privilege('ucpe_lattice_space',c.oid,
      'SELECT,INSERT,UPDATE,REFERENCES')
 OR CASE WHEN c.relkind='S' THEN has_sequence_privilege('ucpe_lattice_space',c.oid,
 'USAGE,SELECT,UPDATE') ELSE false END)"""
POST_DEFINER_PRIVILEGES_SQL = """
SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname IN ('public','ucpe_lattice') AND p.prosecdef
 AND has_schema_privilege('ucpe_lattice_space',n.oid,'USAGE')
 AND has_function_privilege('ucpe_lattice_space',p.oid,'EXECUTE')
 AND (n.nspname,p.proname,pg_get_function_identity_arguments(p.oid)) NOT IN (
 ('ucpe_lattice','record_lattice_row','p_row jsonb'),
 ('ucpe_lattice','record_missed_instant','p_entry jsonb'),
 ('ucpe_lattice','capture_commit_receipts','p_limit integer'))"""
POST_CREATE_PRIVILEGES_SQL = """SELECT
 EXISTS (SELECT 1 FROM pg_namespace n
         WHERE has_schema_privilege('ucpe_lattice_space',n.oid,'CREATE'))
 OR has_database_privilege('ucpe_lattice_space',current_database(),'CREATE')"""
POST_SHDEPEND_SQL = """
SELECT count(*) FROM pg_shdepend d
 WHERE d.refclassid='pg_catalog.pg_authid'::regclass
 AND d.refobjid=(SELECT oid FROM pg_roles WHERE rolname='ucpe_lattice_space')"""
POST_OUTSIDE_RELATION_COUNT_SQL = """
SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname NOT IN ('pg_catalog','information_schema','pg_toast','public','ucpe_lattice')
 AND n.nspname NOT LIKE 'pg_temp_%' AND n.nspname NOT LIKE 'pg_toast_temp_%'
 AND c.relkind IN ('r','p','v','m','f','S') AND
 (has_table_privilege('ucpe_lattice_space',c.oid,
 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
 OR has_any_column_privilege('ucpe_lattice_space',c.oid,'SELECT,INSERT,UPDATE,REFERENCES')
 OR CASE WHEN c.relkind='S' THEN has_sequence_privilege('ucpe_lattice_space',c.oid,
 'USAGE,SELECT,UPDATE') ELSE false END)"""
POST_OUTSIDE_DEFINER_COUNT_SQL = """
SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname NOT IN ('pg_catalog','information_schema','pg_toast','public','ucpe_lattice')
 AND n.nspname NOT LIKE 'pg_temp_%' AND n.nspname NOT LIKE 'pg_toast_temp_%' AND p.prosecdef
 AND has_schema_privilege('ucpe_lattice_space',n.oid,'USAGE')
 AND has_function_privilege('ucpe_lattice_space',p.oid,'EXECUTE')"""
POST_TEMPORARY_SQL = """SELECT has_database_privilege(
 'ucpe_lattice_space',current_database(),'TEMPORARY')"""
POST_PUBLIC_PARAMETER_GRANTS_SQL = """
SELECT CASE WHEN to_regclass('pg_catalog.pg_parameter_acl') IS NULL THEN 0
 ELSE (SELECT count(*) FROM pg_parameter_acl a CROSS JOIN LATERAL aclexplode(a.paracl) x
       WHERE x.grantee=0) END"""
POST_WRITER_TABLE_SQL = """
SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='ucpe_lattice' AND c.relkind IN ('r','p')
 AND has_table_privilege('ucpe_lattice_writer',c.oid,
 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')"""


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


def enter_isolated_runtime(wheelhouse):
    if not wheelhouse:
        raise Refused("--wheelhouse is required")
    if str(SOURCE) not in sys.path:
        sys.path.append(str(SOURCE))
    from crypto_probability_engine import runtime_isolation
    return runtime_isolation.enter(ROOT, wheelhouse=Path(wheelhouse))


def attest_dispatch(env, expected_sha, isolation):
    from crypto_probability_engine import runtime_isolation
    status = subprocess.run(["git", "status", "--porcelain=v1", "--untracked-files=no"],
                            cwd=ROOT, check=True, capture_output=True, text=True).stdout
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                          capture_output=True, text=True).stdout.strip()
    if (env.get("GITHUB_ACTIONS") != "true" or env.get("GITHUB_REPOSITORY") != EXPECTED_REPOSITORY
            or env.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
            or env.get("GITHUB_REF") != "refs/heads/main"
            or env.get("GITHUB_WORKFLOW_REF") != f"{EXPECTED_REPOSITORY}/{WORKFLOW}@refs/heads/main"
            or not re.fullmatch(r"[0-9a-f]{40}", expected_sha or "")
            or env.get("GITHUB_SHA") != expected_sha or head != expected_sha or status
            or (platform.python_implementation(), platform.python_version()) != PINNED_PYTHON
            or runtime_isolation.interpreter_flags() != runtime_isolation.REQUIRED_FLAGS_TEXT):
        raise Refused("dispatch or isolated runtime refused")
    return {"workflow": WORKFLOW, "expected_sha": expected_sha, "git_head": head,
            "installed_files_sha256": isolation.installed_files_sha256}


def attest_loaded_modules(isolation):
    from crypto_probability_engine import runtime_isolation

    # As scripts/apply_migration_0018.py: the stdlib, the locked files, the evaluator pin's files
    # (runtime_isolation itself is one) and this script.
    from crypto_probability_engine.oos.evaluation.evaluator_pin import pinned_files

    return runtime_isolation.attest_loaded_modules(
        isolation, pinned=(*pinned_files(ROOT), SCRIPT), root=ROOT
    )


def load_driver():
    import psycopg
    return psycopg


def apply_in_one_transaction(
    open_connection, migration: bytes, capacity: bytes, migration_0020: bytes, captured=None
):
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
        cur.execute(migration_0020.decode("utf-8"))
        records["migration_0020_executed"] = True
        after = _checks(cur, records, "post")
        outside_after = _outside_fingerprint(cur)
        records["outside_after"] = outside_after
        # The schema and the two roles now exist; every other pre-check must still hold.
        if (after["schema_absent"] is not False or after["roles_absent"] is not False
                or after["lattice_space_absent"] is not False):
            raise Refused("post-check: the schema or roles are missing")
        unchanged = [k for k in CHECKS if k not in
                     ("schema_absent", "roles_absent", "lattice_space_absent")]
        if any(after[k] != before[k] for k in unchanged) or outside_before != outside_after:
            raise Refused("post-check catalog mismatch")
        # PostgreSQL 16 CREATEROLE auto-grant must be ADMIN-only for the applier.
        cur.execute(POST_MEMBERSHIP_SQL)
        lattice_members = cur.fetchall()
        records["lattice_non_creator_memberships"] = len(lattice_members)
        applier = _scalar(cur, CURRENT_USER_SQL)
        if not (len(lattice_members) == 1 and lattice_members[0][:2] ==
                ("ucpe_lattice_writer", "ucpe_lattice_space") and
                lattice_members[0][2] == applier
                and lattice_members[0][3:] == (False, True, False)):
            raise Refused("post-check unexpected lattice member")
        cur.execute(POST_CREATOR_MEMBERSHIPS_SQL)
        memberships = cur.fetchall()
        records["creator_memberships"] = len(memberships)
        if (len(memberships) != 3 or [row[0] for row in memberships] !=
                ["ucpe_lattice_owner", "ucpe_lattice_space", "ucpe_lattice_writer"]
                or any(row[1] != applier or row[2:] != (True, False, False)
                       for row in memberships)):
            raise Refused("post-check creator membership mismatch")
        cur.execute(POST_SPACE_ATTRIBUTES_SQL)
        attributes = cur.fetchone()
        records["lattice_space_attributes"] = list(attributes) if attributes else None
        if attributes != (False, False, False, False, False, False, False, 3, None):
            raise Refused("post-check lattice space attributes")
        cur.execute(POST_SPACE_SETTINGS_SQL)
        settings = cur.fetchall()
        records["lattice_space_settings"] = len(settings)
        expected_settings = {"statement_timeout=5s", "lock_timeout=2s",
                             "idle_in_transaction_session_timeout=30s"}
        if (len(settings) != 1 or settings[0][0] != 0
                or set(settings[0][1] or ()) != expected_settings):
            raise Refused("post-check lattice space settings")
        for name, sql in (("relation_privileges", POST_RELATION_PRIVILEGES_SQL),
                          ("definer_privileges", POST_DEFINER_PRIVILEGES_SQL),
                          ("create_privileges", POST_CREATE_PRIVILEGES_SQL),
                          ("shdepend", POST_SHDEPEND_SQL)):
            value = _scalar(cur, sql)
            records[f"post_{name}"] = value
            if value is not False and value != 0:
                raise Refused(f"post-check {name}")
        for name, sql in (("outside_relation_privileges", POST_OUTSIDE_RELATION_COUNT_SQL),
                          ("outside_definer_privileges", POST_OUTSIDE_DEFINER_COUNT_SQL),
                          ("temporary_privilege", POST_TEMPORARY_SQL),
                          ("public_parameter_grants", POST_PUBLIC_PARAMETER_GRANTS_SQL)):
            records[name] = _scalar(cur, sql)
        cur.execute(POST_WRITER_TABLE_SQL)
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
        "migration_0020_sha256": MIGRATION_0020_SHA256,
    }
    try:
        migration, capacity, migration_0020 = pinned_bytes()
        if args.mode in ("attest", "apply") and not args.wheelhouse:
            raise Refused("--wheelhouse is required")
        if args.mode == "attest":
            isolation = enter_isolated_runtime(args.wheelhouse)
            report["dispatch"] = attest_dispatch(env, args.expected_sha, isolation)
            attest_loaded_modules(isolation)
            load_driver()
            attest_loaded_modules(isolation)
            report["outcome"] = "ATTESTED"
        else:
            if args.mode == "apply" and args.confirm != CONFIRMATION:
                raise Refused("confirmation mismatch")
            isolation = None
            if args.mode == "apply":
                isolation = enter_isolated_runtime(args.wheelhouse)
                report["dispatch"] = attest_dispatch(env, args.expected_sha, isolation)
                attest_loaded_modules(isolation)
            variable = (
                "MIGRATION_0019_REHEARSAL_URL" if args.mode == "rehearse" else "SUPABASE_DB_URL"
            )
            url = env.get(variable, "")
            reason = refuse_url(url) if args.mode == "rehearse" else None
            if reason or not url or (args.mode == "rehearse" and env.get("SUPABASE_DB_URL")):
                raise Refused("database URL refused")
            driver = load_driver() if isolation is not None else __import__("psycopg")
            if isolation is not None:
                attest_loaded_modules(isolation)

            checks = report["checks"]

            def opener():
                return driver.connect(url, connect_timeout=8)

            apply_in_one_transaction(opener, migration, capacity, migration_0020, checks)
            if args.mode == "rehearse":
                second = {}
                try:
                    apply_in_one_transaction(opener, migration, capacity, migration_0020, second)
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
