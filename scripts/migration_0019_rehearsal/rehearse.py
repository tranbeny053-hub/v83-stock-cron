"""Rehearse migration 0019 (NG4 Route S, the lattice store) on scratch local PostgreSQL only.

Run by run_scratch.sh, locally or in CI:
    rehearse.py --url <runner> --super-url <superuser> --commit-ts on|off --report <json>
Both URLs must be local (a socket path or localhost); a URL naming supabase is refused, and
neither is printed. The runner is the cluster's CREATEROLE non-superuser owner (production's
shape); the superuser only installs probe fixtures and runs SET ROLE probes. Checks R-0..R-15
follow the NG4 contract spec, section 4.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations/authored/0019_lattice_evidence.sql"
CODE_ROW = ROOT / "tests/quant_ng/fixtures/lattice_row_v1.json"
OWNER = "ucpe_lattice_owner"
WRITER = "ucpe_lattice_writer"
TABLES = (
    "lattice_rows",
    "lattice_commit_receipts",
    "lattice_missed_instants",
    "lattice_capacity",
)
COLUMN = {
    "lattice_rows": "timeframe",
    "lattice_commit_receipts": "commit_state",
    "lattice_missed_instants": "reason",
    "lattice_capacity": "note",
}
WRITER_FUNCTIONS = (
    "ucpe_lattice.record_lattice_row(jsonb)",
    "ucpe_lattice.record_missed_instant(jsonb)",
    "ucpe_lattice.capture_commit_receipts(integer)",
)
OTHER_FUNCTIONS = ("ucpe_lattice.capacity_status()", "ucpe_lattice.reject_mutation()")
NAMED_ROLES = (
    "anon",
    "authenticated",
    "service_role",
    "authenticator",
    "ucpe_api_writer",
    "ucpe_bundle_owner",
    "ucpe_space_db",
    "ucpe_resolver",
    "probe_public_only",
)
DENIED = "42501"
TRIGGER = "P0001"
CAPACITY = (16, 15)
ANCHOR = datetime(2026, 9, 21, tzinfo=UTC)

_OUTSIDE = "NOT IN ('pg_catalog', 'information_schema', 'pg_toast', 'ucpe_lattice')"
_LATTICE_ROLES = "('ucpe_lattice_owner', 'ucpe_lattice_writer')"
FINGERPRINT_SQL = f"""
SELECT json_build_object(
  'classes', (SELECT coalesce(json_agg(x ORDER BY x::text), '[]') FROM (
      SELECT n.nspname, c.relname, c.relkind, pg_get_userbyid(c.relowner) AS owner,
             c.relacl::text AS acl, c.relrowsecurity, c.relforcerowsecurity
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
       WHERE n.nspname {_OUTSIDE} AND n.nspname !~ '^pg_(toast_)?temp') x),
  'functions', (SELECT coalesce(json_agg(x ORDER BY x::text), '[]') FROM (
      SELECT n.nspname, p.proname, pg_get_function_identity_arguments(p.oid) AS args,
             pg_get_userbyid(p.proowner) AS owner, p.proacl::text AS acl, p.prosecdef,
             p.proconfig::text AS config
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
       WHERE n.nspname {_OUTSIDE}) x),
  'policies', (SELECT coalesce(json_agg(x ORDER BY x::text), '[]') FROM (
      SELECT schemaname, tablename, policyname, roles::text, cmd, qual, with_check
        FROM pg_policies WHERE schemaname <> 'ucpe_lattice') x),
  'triggers', (SELECT coalesce(json_agg(x ORDER BY x::text), '[]') FROM (
      SELECT n.nspname, c.relname, t.tgname, t.tgenabled, t.tgfoid::regprocedure::text AS fn
        FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
       WHERE NOT t.tgisinternal AND n.nspname <> 'ucpe_lattice') x),
  'namespaces', (SELECT coalesce(json_agg(x ORDER BY x::text), '[]') FROM (
      SELECT nspname, pg_get_userbyid(nspowner) AS owner, nspacl::text AS acl
        FROM pg_namespace WHERE nspname <> 'ucpe_lattice') x),
  'roles', (SELECT coalesce(json_agg(x ORDER BY x::text), '[]') FROM (
      SELECT rolname, rolsuper, rolinherit, rolcreaterole, rolcreatedb, rolcanlogin,
             rolreplication, rolbypassrls
        FROM pg_roles WHERE rolname NOT IN {_LATTICE_ROLES}) x),
  'memberships', (SELECT coalesce(json_agg(x ORDER BY x::text), '[]') FROM (
      SELECT pg_get_userbyid(m.roleid) AS role, pg_get_userbyid(m.member) AS member,
             pg_get_userbyid(m.grantor) AS grantor, m.admin_option, m.inherit_option,
             m.set_option
        FROM pg_auth_members m
       WHERE pg_get_userbyid(m.roleid) NOT IN {_LATTICE_ROLES}) x),
  'default_acls', (SELECT coalesce(json_agg(x ORDER BY x::text), '[]') FROM (
      SELECT pg_get_userbyid(d.defaclrole) AS role, d.defaclnamespace::regnamespace::text,
             d.defaclobjtype, d.defaclacl::text AS acl
        FROM pg_default_acl d
       WHERE pg_get_userbyid(d.defaclrole) NOT IN {_LATTICE_ROLES}) x),
  'publications', (SELECT coalesce(json_agg(x ORDER BY x::text), '[]') FROM (
      SELECT pubname, puballtables FROM pg_publication) x)
)::text
"""


def refuse_url(url: str) -> str | None:
    """Return a reason to refuse a URL that is not an explicitly local scratch database."""

    if "supabase" in url.lower():
        return "the URL names supabase"
    parsed = urlparse(url)
    if parsed.scheme not in ("postgresql", "postgres"):
        return "the URL is not a postgresql URL"
    host = parsed.hostname or ""
    socket = parse_qs(parsed.query).get("host", [""])[0]
    if host in ("localhost", "127.0.0.1"):
        return None
    if host == "" and socket.startswith("/"):
        return None
    return "the URL is not a local socket or localhost"


class _Rollback(Exception):
    pass


class Rehearsal:
    def __init__(self, url: str, super_url: str, commit_ts: str) -> None:
        import psycopg

        self.psycopg = psycopg
        self.super_url = super_url
        self.commit_ts = commit_ts
        self.checks: list[dict[str, Any]] = []
        self.facts: dict[str, Any] = {}
        self.runner = psycopg.connect(url, autocommit=True)
        self.su = psycopg.connect(super_url, autocommit=True)
        self.serial = 0

    # ---- helpers ---------------------------------------------------------------------------
    def add(self, name: str, ok: bool, detail: Any) -> None:
        self.checks.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})

    def one(self, conn: Any, sql: str, params: tuple = ()) -> Any:
        return conn.execute(sql, params or None).fetchone()[0]

    def sqlstate_of(self, fn: Callable[[], Any]) -> str | None:
        try:
            fn()
        except self.psycopg.Error as exc:
            return exc.sqlstate or "UNKNOWN"
        return None

    def as_role(self, role: str, sql: str, params: tuple = ()) -> Any:
        """Run one statement as `role` (SET LOCAL ROLE in the superuser session)."""

        with self.su.transaction():
            self.su.execute(f'SET LOCAL ROLE "{role}"')
            cur = self.su.execute(sql, params or None)
            return cur.fetchone()[0] if cur.description else cur.rowcount

    def denied(self, role: str, sql: str, params: tuple = ()) -> str | None:
        return self.sqlstate_of(lambda: self.as_role(role, sql, params))

    def _run_id(self, kind: str) -> str:
        self.serial += 1
        return "e3l-" + hashlib.sha256(f"{kind}-{self.serial}".encode()).hexdigest()[:32]

    def row(self, timeframe: str = "4H", **overrides: Any) -> dict[str, Any]:
        run_id = self._run_id("row")
        instant = ANCHOR + timedelta(hours=12 * self.serial)
        close = instant.isoformat()
        base = {
            "lattice_row_id": f"{run_id}:{timeframe}:REF",
            "lattice_run_id": run_id,
            "lattice_instant_utc": close,
            "reference_close_utc": close,
            "horizon_end_utc": (instant + timedelta(hours=24)).isoformat(),
            "predicted_at_utc": (instant + timedelta(seconds=5)).isoformat(),
            "core_computed_at_utc": (instant + timedelta(seconds=6)).isoformat(),
            "issued_at_utc": (instant + timedelta(seconds=7)).isoformat(),
            "protocol_version": "E3_LATTICE_V1",
            "evaluation_population": "E1_OPERATIONAL",
            "timing_class": "NOT_APPLICABLE",
            "evidence_use": "TEST_ONLY",
            "arm": "REF",
            "artifact_id": None,
            "recipe_id": "reference-daytype-v1",
            "methodology_version": "reference-daytype-v1",
            "reference_prior_id": "rehearsal-prior",
            "normalized_symbol": "SOL/USDT",
            "reference_venue": "BINANCE_SPOT",
            "data_source": "BINANCE_SPOT",
            "provider": "binance",
            "timeframe": timeframe,
            "horizon_bars": 6,
            "target_version": "tc-v1",
            "is_live_data": True,
            "reference_price": 150.25,
            "decision_band_frac": 0.004,
            "p_up_frac": 0.25,
            "p_down_frac": 0.25,
            "p_timeout_frac": 0.5,
        }
        base.update(overrides)
        return base

    def missed(self, **overrides: Any) -> dict[str, Any]:
        run_id = self._run_id("missed")
        base = {
            "lattice_run_id": run_id,
            "timeframe": "4H",
            "normalized_symbol": "SOL/USDT",
            "reference_venue": "BINANCE_SPOT",
            "lattice_instant_utc": (ANCHOR + timedelta(hours=12 * self.serial)).isoformat(),
            "reason": "STALE_SNAPSHOT",
            "protocol_version": "E3_LATTICE_V1",
            "evidence_use": "TEST_ONLY",
        }
        base.update(overrides)
        return base

    def write_row(self, row: dict[str, Any]) -> str:
        sql = "SELECT ucpe_lattice.record_lattice_row(%s::jsonb)"
        return self.as_role(WRITER, sql, (json.dumps(row),))

    def write_missed(self, entry: dict[str, Any]) -> str:
        sql = "SELECT ucpe_lattice.record_missed_instant(%s::jsonb)"
        return self.as_role(WRITER, sql, (json.dumps(entry),))

    def capture(self, limit: int = 100) -> int:
        return self.as_role(WRITER, "SELECT ucpe_lattice.capture_commit_receipts(%s)", (limit,))

    def count(self, table: str) -> int:
        return self.one(self.su, f"SELECT count(*) FROM ucpe_lattice.{table}")

    def used(self) -> int:
        return self.count("lattice_rows") + self.count("lattice_missed_instants")

    def receipt(self, row_id: str) -> tuple:
        return self.su.execute(
            "SELECT c.commit_state, c.commit_ts_utc, c.captured_at_db_clock, r.db_insert_clock_utc"
            " FROM ucpe_lattice.lattice_commit_receipts c"
            " JOIN ucpe_lattice.lattice_rows r USING (lattice_row_id)"
            " WHERE lattice_row_id = %s",
            (row_id,),
        ).fetchone()

    def _apply(self, sql: str) -> None:
        with self.runner.transaction():
            self.runner.execute(sql)

    # ---- the rehearsal ---------------------------------------------------------------------
    def run(self) -> None:
        self.preconditions()
        self.refusal_fixtures()
        before = self.one(self.runner, FINGERPRINT_SQL)
        sql = MIGRATION.read_text(encoding="utf-8")
        state = self.sqlstate_of(lambda: self._apply(sql))
        name = "R-1 0019 applies once as the CREATEROLE non-superuser owner"
        self.add(name, state is None, state)
        if state is not None:
            return
        second = self.sqlstate_of(lambda: self._apply(sql))
        self.add("R-1 a second application is refused UP019", second == "UP019", second)
        after = self.one(self.runner, FINGERPRINT_SQL)
        old, new = json.loads(before), json.loads(after)
        self.add(
            "R-2 every object, ACL, policy, trigger, role, membership, default ACL and"
            " publication outside ucpe_lattice is unchanged",
            before == after,
            {
                "sha256_before": hashlib.sha256(before.encode()).hexdigest(),
                "sha256_after": hashlib.sha256(after.encode()).hexdigest(),
                "changed_sections": sorted(k for k in old if old[k] != new[k]),
            },
        )
        self.facts["capacity_unset"] = [
            self.write_row(self.row()),
            self.write_missed(self.missed()),
        ]
        self.isolation()
        self.writer_privileges()
        self.owner_and_bypass()
        self.rows_and_receipts()

    def preconditions(self) -> None:
        setting = self.one(self.su, "SHOW track_commit_timestamp")
        superuser = self.one(self.su, "SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        weak = self.one(
            self.runner,
            "SELECT rolsuper OR NOT rolcreaterole FROM pg_roles WHERE rolname = current_user",
        )
        built = self.one(
            self.su,
            "SELECT count(*) = 4 FROM pg_roles WHERE rolname IN"
            " ('ucpe_api_writer', 'ucpe_bundle_owner', 'ucpe_space_db', 'ucpe_resolver')",
        )
        version = self.one(self.su, "SHOW server_version")
        self.facts.update({"server_version": version, "track_commit_timestamp": setting})
        self.add(
            "R-0 the cluster: track_commit_timestamp as asked, a superuser probe session,"
            " a CREATEROLE non-superuser runner, migrations 0001-0018 applied",
            setting == self.commit_ts and superuser and not weak and built,
            {"track_commit_timestamp": setting, "server_version": version},
        )

    def refusal_fixtures(self) -> None:
        sql = MIGRATION.read_text(encoding="utf-8")
        self.su.execute("CREATE ROLE probe_bypass_reader NOLOGIN BYPASSRLS")
        self.su.execute("GRANT pg_read_all_data TO probe_bypass_reader")
        bypass = self.sqlstate_of(lambda: self._apply(sql))
        self.su.execute("DROP ROLE probe_bypass_reader")
        self.su.execute("CREATE PUBLICATION probe_all FOR ALL TABLES")
        alltables = self.sqlstate_of(lambda: self._apply(sql))
        self.su.execute("DROP PUBLICATION probe_all")
        self.add(
            "R-0 the first-apply checks refuse a BYPASSRLS reader of pg_read_all_data"
            " and a FOR ALL TABLES publication",
            bypass == "UP019" and alltables == "UP019",
            {"bypass_reader": bypass, "all_tables_publication": alltables},
        )
        # Hostile fixtures that stay: the runner's global default privileges grant everything to
        # the API roles (a platform default's worst case), a PUBLIC-only role, and a non-bypass
        # member of the predefined data roles.
        for kind in ("TABLES", "SEQUENCES", "FUNCTIONS"):
            self.runner.execute(
                f"ALTER DEFAULT PRIVILEGES GRANT ALL ON {kind} TO anon, authenticated, service_role"
            )
        self.su.execute("CREATE ROLE probe_public_only NOLOGIN")
        self.su.execute("CREATE ROLE probe_read_all NOLOGIN")
        self.su.execute("GRANT pg_read_all_data, pg_write_all_data TO probe_read_all")

    def isolation(self) -> None:
        roles = [
            r[0]
            for r in self.su.execute(
                "SELECT rolname FROM pg_roles WHERE NOT rolsuper AND rolname NOT IN (%s, %s)"
                " ORDER BY rolname",
                (OWNER, WRITER),
            ).fetchall()
        ]
        predefined = ("pg_read_all_data", "pg_write_all_data")
        leaks: list[Any] = []
        for role in roles:
            via = role in predefined or any(
                self.one(self.su, "SELECT pg_has_role(%s, %s, 'MEMBER')", (role, p))
                for p in predefined
            )
            schema = self.one(
                self.su, "SELECT has_schema_privilege(%s, 'ucpe_lattice', 'USAGE,CREATE')", (role,)
            )
            if schema and not via:
                leaks.append([role, "schema"])
            for table in TABLES:
                for priv in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES"):
                    if via and priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                        continue  # built into the predefined roles; forced RLS decides (below)
                    if self.one(
                        self.su,
                        "SELECT has_table_privilege(%s, %s, %s)",
                        (role, f"ucpe_lattice.{table}", priv),
                    ):
                        leaks.append([role, table, priv])
            for fn in WRITER_FUNCTIONS + OTHER_FUNCTIONS:
                sql = "SELECT has_function_privilege(%s, %s, 'EXECUTE')"
                if self.one(self.su, sql, (role, fn)):
                    leaks.append([role, fn])
        self.add(
            "R-3 no role in the cluster but the owner, the writer and superusers holds a privilege"
            " on the lattice schema, tables or functions (predefined data roles: below)",
            not leaks,
            {"roles_checked": len(roles), "leaks": leaks},
        )

        with self.su.transaction():
            self.su.execute(f'SET LOCAL ROLE "{OWNER}"')
            self.su.execute(
                "INSERT INTO ucpe_lattice.lattice_capacity (max_rows, warn_rows, note)"
                " VALUES (%s, %s, 'rehearsal capacity')",
                CAPACITY,
            )
        seed = self.write_row(self.row())  # a stored row, so a read leak would show
        live: list[Any] = []
        for role in NAMED_ROLES:
            for table in TABLES:
                column = COLUMN[table]
                for sql in (
                    f"SELECT count(*) FROM ucpe_lattice.{table}",
                    f"INSERT INTO ucpe_lattice.{table} DEFAULT VALUES",
                    f"UPDATE ucpe_lattice.{table} SET {column} = {column}",
                    f"DELETE FROM ucpe_lattice.{table}",
                    f"TRUNCATE ucpe_lattice.{table}",
                ):
                    state = self.denied(role, sql)
                    if state != DENIED:
                        live.append([role, sql, state])
            for sql in (
                "SELECT ucpe_lattice.record_lattice_row('{}'::jsonb)",
                "SELECT ucpe_lattice.record_missed_instant('{}'::jsonb)",
                "SELECT ucpe_lattice.capture_commit_receipts(1)",
                "SELECT ucpe_lattice.capacity_status()",
            ):
                state = self.denied(role, sql)
                if state != DENIED:
                    live.append([role, sql, state])
        self.add(
            "R-3 live: each named API, service and probe role is refused (42501) every read,"
            " write and function call on the lattice",
            seed == "INSERTED" and not live,
            {"seed_row": seed, "unexpected": live},
        )

        reader = {
            "select": self.as_role(
                "probe_read_all", "SELECT count(*) FROM ucpe_lattice.lattice_rows"
            ),
            "insert": self.denied(
                "probe_read_all",
                "INSERT INTO ucpe_lattice.lattice_capacity (max_rows, warn_rows, note)"
                " VALUES (2, 1, 'x')",
            ),
            "update": self.as_role(
                "probe_read_all", "UPDATE ucpe_lattice.lattice_rows SET timeframe = timeframe"
            ),
            "delete": self.as_role("probe_read_all", "DELETE FROM ucpe_lattice.lattice_rows"),
            "truncate": self.denied("probe_read_all", "TRUNCATE ucpe_lattice.lattice_rows"),
        }
        expected = {"select": 0, "insert": DENIED, "update": 0, "delete": 0, "truncate": DENIED}
        self.add(
            "R-3 a non-bypass member of pg_read_all_data and pg_write_all_data sees no row and"
            " changes none (forced RLS, no policy)",
            reader == expected and self.count("lattice_rows") == 1,
            reader,
        )

        bypass = [
            r[0]
            for r in self.su.execute(
                "SELECT rolname FROM pg_roles WHERE rolbypassrls AND NOT rolsuper ORDER BY 1"
            ).fetchall()
        ]
        members = [
            r[0]
            for r in self.su.execute(
                "SELECT rolname FROM pg_roles r WHERE NOT rolsuper AND rolname !~ '^pg_'"
                " AND (pg_has_role(r.oid, 'pg_read_all_data', 'MEMBER')"
                " OR pg_has_role(r.oid, 'pg_write_all_data', 'MEMBER')) ORDER BY 1"
            ).fetchall()
        ]
        publications = [
            list(p)
            for p in self.su.execute(
                "SELECT pubname, puballtables FROM pg_publication ORDER BY 1"
            ).fetchall()
        ]
        published = self.one(
            self.su,
            "SELECT count(*) FROM pg_publication_tables WHERE schemaname = 'ucpe_lattice'",
        )
        self.facts.update({"bypassrls_roles": bypass, "predefined_data_role_members": members})
        self.add(
            "R-3 no BYPASSRLS role holds a predefined data role, and no publication covers"
            " the lattice",
            not (set(bypass) & set(members))
            and published == 0
            and not any(p[1] for p in publications),
            {"bypassrls": bypass, "members": members, "publications": publications},
        )

    def writer_privileges(self) -> None:
        refusals = {}
        for table in TABLES:
            for sql in (
                f"SELECT count(*) FROM ucpe_lattice.{table}",
                f"INSERT INTO ucpe_lattice.{table} DEFAULT VALUES",
                f"DELETE FROM ucpe_lattice.{table}",
                f"TRUNCATE ucpe_lattice.{table}",
            ):
                refusals[sql] = self.denied(WRITER, sql)
        refusals["capacity_status()"] = self.denied(WRITER, "SELECT ucpe_lattice.capacity_status()")
        executes = all(
            self.one(self.su, "SELECT has_function_privilege(%s, %s, 'EXECUTE')", (WRITER, fn))
            for fn in WRITER_FUNCTIONS
        )
        returns = sorted(
            r[0]
            for r in self.su.execute(
                "SELECT format_type(prorettype, NULL) FROM pg_proc"
                " WHERE pronamespace = 'ucpe_lattice'::regnamespace AND proname IN"
                " ('record_lattice_row', 'record_missed_instant', 'capture_commit_receipts')"
            ).fetchall()
        )
        self.add(
            "R-4 the writer: every table read and write refused, capacity_status refused,"
            " the three functions executable",
            all(v == DENIED for v in refusals.values()) and executes,
            {"refusals": refusals, "executes_three": executes},
        )
        self.add(
            "R-14 the writer reads nothing back: no table privilege, and its functions return"
            " only a status or a count",
            returns == ["integer", "text", "text"]
            and refusals["SELECT count(*) FROM ucpe_lattice.lattice_rows"] == DENIED,
            {"return_types": returns},
        )

    def owner_and_bypass(self) -> None:
        before = self.count("lattice_rows")
        owner = {
            "update": self.as_role(OWNER, "UPDATE ucpe_lattice.lattice_rows SET arm = arm"),
            "delete": self.as_role(OWNER, "DELETE FROM ucpe_lattice.lattice_rows"),
            # CASCADE: a plain TRUNCATE is refused earlier (0A000), as receipts reference rows.
            "truncate": self.denied(OWNER, "TRUNCATE ucpe_lattice.lattice_rows CASCADE"),
        }
        superuser = {
            "update": self.sqlstate_of(
                lambda: self.su.execute("UPDATE ucpe_lattice.lattice_rows SET arm = arm")
            ),
            "delete": self.sqlstate_of(
                lambda: self.su.execute("DELETE FROM ucpe_lattice.lattice_rows")
            ),
            "truncate": self.sqlstate_of(
                lambda: self.su.execute("TRUNCATE ucpe_lattice.lattice_rows CASCADE")
            ),
        }
        can_disable: Any = None
        try:
            with self.su.transaction():
                self.su.execute(f'SET LOCAL ROLE "{OWNER}"')
                self.su.execute(
                    "ALTER TABLE ucpe_lattice.lattice_rows DISABLE TRIGGER lattice_rows_append_only"
                )
                can_disable = True
                raise _Rollback
        except _Rollback:
            pass
        except self.psycopg.Error as exc:
            can_disable = exc.sqlstate
        members = [
            list(r)
            for r in self.su.execute(
                "SELECT pg_get_userbyid(roleid), pg_get_userbyid(member), admin_option,"
                " inherit_option, set_option FROM pg_auth_members"
                " WHERE pg_get_userbyid(roleid) IN (%s, %s) ORDER BY 1, 2",
                (OWNER, WRITER),
            ).fetchall()
        ]
        runner = self.one(self.runner, "SELECT current_user")
        expected = [[OWNER, runner, True, False, False], [WRITER, runner, True, False, False]]
        can_set = [
            r[0]
            for r in self.su.execute(
                "SELECT rolname FROM pg_roles r WHERE NOT rolsuper AND rolname <> %s"
                " AND pg_has_role(r.oid, %s, 'SET')",
                (OWNER, OWNER),
            ).fetchall()
        ]
        writer = {
            "disable_trigger": self.denied(
                WRITER, "ALTER TABLE ucpe_lattice.lattice_rows DISABLE TRIGGER ALL"
            ),
            "replication_role": self.denied(WRITER, "SET LOCAL session_replication_role = replica"),
            "member_of_owner": self.one(
                self.su, "SELECT pg_has_role(%s, %s, 'MEMBER')", (WRITER, OWNER)
            ),
        }
        powers = self.one(
            self.su,
            "SELECT bool_or(rolbypassrls OR rolsuper OR rolcanlogin OR rolcreaterole)"
            " FROM pg_roles WHERE rolname IN (%s, %s)",
            (OWNER, WRITER),
        )
        self.facts["lattice_role_memberships"] = members
        ok = (
            owner == {"update": 0, "delete": 0, "truncate": TRIGGER}
            and all(v == TRIGGER for v in superuser.values())
            and self.count("lattice_rows") == before
            and can_disable is True
            and members == expected
            and not can_set
            and writer
            == {"disable_trigger": DENIED, "replication_role": DENIED, "member_of_owner": False}
            and powers is False
        )
        self.add(
            "R-5 owner/bypass: the owner changes no row (forced RLS) and cannot truncate; a"
            " superuser is stopped by the append-only triggers; the owner CAN disable a trigger"
            " (recorded); the only memberships are the runner's ADMIN grants (no SET, no"
            " INHERIT); no other role can SET to the owner; the writer cannot disable triggers,"
            " set session_replication_role or reach the owner; neither role can log in, create"
            " roles or bypass RLS",
            ok,
            {
                "owner": owner,
                "superuser": superuser,
                "owner_can_disable_trigger": can_disable,
                "memberships": members,
                "roles_that_can_set_owner": can_set,
                "writer": writer,
            },
        )

    def rows_and_receipts(self) -> None:
        first_row = self.row()
        first = self.write_row(first_row)
        lookup = (
            "SELECT row_to_json(r)::text FROM ucpe_lattice.lattice_rows r WHERE lattice_row_id = %s"
        )
        stored = self.one(self.su, lookup, (first_row["lattice_row_id"],))
        again = self.write_row(dict(first_row, p_up_frac=0.3, p_down_frac=0.2))
        kept = self.one(self.su, lookup, (first_row["lattice_row_id"],))
        self.add(
            "R-7 a duplicate row id returns DUPLICATE and the stored row is unchanged",
            first == "INSERTED" and again == "DUPLICATE" and stored == kept,
            {"first": first, "again": again},
        )
        self.contract_refusals()
        self.code_row()
        self.commit_time()
        self.fresh_transaction_guard()
        self.missed_instants()
        self.append_only_elsewhere()
        self.capacity()

    def contract_refusals(self) -> None:
        before = self.count("lattice_rows")
        bad: dict[str, dict[str, Any]] = {
            "an E3 population": self.row(evaluation_population="E3_SPACE_ISSUED"),
            "ON_TIME timing": self.row(timing_class="ON_TIME"),
            "a claim use": self.row(evidence_use="CLAIM"),
            "an artifact": self.row(artifact_id="artifact-1"),
            "a CAND arm": self.row(arm="CAND"),
            "a triplet off by 1e-6": self.row(p_timeout_frac=0.500001),
            "1M": self.row(timeframe="1M"),
            "an unknown key": dict(self.row(), extra="x"),
            "a caller DB clock": dict(self.row(), db_insert_clock_utc="2026-11-05T00:00:00Z"),
            "a missing key": {k: v for k, v in self.row().items() if k != "decision_band_frac"},
            "another protocol": self.row(protocol_version="E3_LATTICE_V2"),
            "another target": self.row(target_version="v0"),
            "not live data": self.row(is_live_data=False),
            "a negative band": self.row(decision_band_frac=-0.001),
            "two venues": self.row(data_source="OKX_SPOT"),
        }
        early = self.row()
        instant = datetime.fromisoformat(early["lattice_instant_utc"])
        bad["source before the instant"] = dict(
            early, predicted_at_utc=(instant - timedelta(seconds=1)).isoformat()
        )
        late = self.row()
        late_instant = datetime.fromisoformat(late["lattice_instant_utc"])
        bad["a close that is not the instant"] = dict(
            late, reference_close_utc=(late_instant - timedelta(hours=4)).isoformat()
        )
        mismatch = self.row()
        bad["a timeframe mismatch"] = dict(mismatch, timeframe="1H")
        prefix = self.row()
        bad["a run prefix mismatch"] = dict(prefix, lattice_run_id="e3l-" + "0" * 32)
        order = self.row()
        bad["computed after issue"] = dict(
            order,
            core_computed_at_utc=order["issued_at_utc"],
            issued_at_utc=order["core_computed_at_utc"],
        )
        outcome = {name: self.sqlstate_of(lambda r=r: self.write_row(r)) for name, r in bad.items()}
        self.add(
            "R-8 every off-contract row is refused (CHECK 23514, or 22023 for the key set) and"
            " nothing is stored",
            all(s in ("23514", "22023") for s in outcome.values())
            and self.count("lattice_rows") == before,
            outcome,
        )

    def code_row(self) -> None:
        """R-15: a row built by quant_ng.lattice.build_lattice_row (frozen fixture) is accepted."""

        if not CODE_ROW.is_file():
            self.add("R-15 the code's frozen row is accepted by the store", False, "no fixture")
            return
        row = json.loads(CODE_ROW.read_text(encoding="utf-8"))["store_row"]
        status = self.write_row(row)
        again = self.write_row(row)
        self.add(
            "R-15 the row quant_ng.lattice builds (its frozen fixture) is accepted by the store,"
            " then DUPLICATE",
            status == "INSERTED" and again == "DUPLICATE",
            {"status": status, "again": again, "keys": len(row)},
        )

    def commit_time(self) -> None:
        conn = self.psycopg.connect(self.super_url, autocommit=True)
        try:
            timed = self.row()
            with conn.transaction():
                conn.execute(f'SET LOCAL ROLE "{WRITER}"')
                tx_start = conn.execute("SELECT now()").fetchone()[0]
                status = conn.execute(
                    "SELECT ucpe_lattice.record_lattice_row(%s::jsonb)", (json.dumps(timed),)
                ).fetchone()[0]
                conn.execute("SELECT pg_sleep(1)")
            captured = self.capture()
            state, commit_ts, captured_at, inserted = self.receipt(timed["lattice_row_id"])
            states = sorted(
                {
                    r[0]
                    for r in self.su.execute(
                        "SELECT commit_state FROM ucpe_lattice.lattice_commit_receipts"
                    ).fetchall()
                }
            )
            frozen = self.row()
            self.write_row(frozen)
            self.su.execute("VACUUM (FREEZE) ucpe_lattice.lattice_rows")
            self.capture()
            f_state, f_ts, f_captured, f_inserted = self.receipt(frozen["lattice_row_id"])
            pair = [self.row(), self.row()]
            for item in pair:
                self.write_row(item)
            results: list[int] = []

            def capture_in_thread() -> None:
                with self.psycopg.connect(self.super_url, autocommit=True) as c:
                    with c.transaction():
                        c.execute(f'SET LOCAL ROLE "{WRITER}"')
                        sql = "SELECT ucpe_lattice.capture_commit_receipts(100)"
                        results.append(c.execute(sql).fetchone()[0])

            threads = [threading.Thread(target=capture_in_thread) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            per_row = [
                self.one(
                    self.su,
                    "SELECT count(*) FROM ucpe_lattice.lattice_commit_receipts"
                    " WHERE lattice_row_id = %s",
                    (item["lattice_row_id"],),
                )
                for item in pair
            ]
        finally:
            conn.close()
        if self.commit_ts == "on":
            ok = (
                status == "INSERTED"
                and captured >= 1
                and state == "COMMITTED"
                and commit_ts - inserted >= timedelta(seconds=1)
                and commit_ts - tx_start >= timedelta(seconds=1)
                and commit_ts <= captured_at
            )
            self.add(
                "R-9 track_commit_timestamp on: the receipt holds the true commit time, at least"
                " 1 s after both the insert clock and the transaction start (the transaction"
                " slept 1 s after the insert) and not after the capture",
                ok,
                {
                    "state": state,
                    "commit_minus_insert_s": (commit_ts - inserted).total_seconds()
                    if commit_ts
                    else None,
                    "commit_minus_tx_start_s": (commit_ts - tx_start).total_seconds()
                    if commit_ts
                    else None,
                },
            )
        else:
            self.add(
                "R-10 track_commit_timestamp off: every receipt is COMMIT_UNKNOWN with no time"
                " (never another clock)",
                status == "INSERTED"
                and state == "COMMIT_UNKNOWN"
                and commit_ts is None
                and states == ["COMMIT_UNKNOWN"],
                {"state": state, "all_states": states},
            )
        freeze_ok = (f_state == "COMMIT_UNKNOWN" and f_ts is None) or (
            f_state == "COMMITTED" and f_inserted <= f_ts <= f_captured
        )
        self.facts["after_vacuum_freeze"] = f_state
        self.add(
            "R-9/R-10 after VACUUM FREEZE the receipt is what PostgreSQL returns: COMMITTED with"
            " a time between the insert and the capture, or COMMIT_UNKNOWN; never another clock",
            freeze_ok and (self.commit_ts == "on" or f_state == "COMMIT_UNKNOWN"),
            {"state": f_state},
        )
        self.add(
            "R-9/R-10 two concurrent captures write exactly one receipt per row",
            per_row == [1, 1] and len(results) == 2 and sum(results) == 2,
            {"captured_by_each": results, "receipts_per_row": per_row},
        )

    def fresh_transaction_guard(self) -> None:
        guard = None
        before = self.count("lattice_rows")
        try:
            with self.su.transaction():
                self.su.execute(f'SET LOCAL ROLE "{WRITER}"')
                self.su.execute(
                    "SELECT ucpe_lattice.record_lattice_row(%s::jsonb)", (json.dumps(self.row()),)
                )
                self.su.execute("SELECT ucpe_lattice.capture_commit_receipts(10)")
        except self.psycopg.Error as exc:
            guard = exc.sqlstate
        self.add(
            "R-11 a capture in a transaction that already wrote is refused, and the write rolls"
            " back",
            guard == "25000" and self.count("lattice_rows") == before,
            guard,
        )

    def missed_instants(self) -> None:
        entry = self.missed()
        logged = self.write_missed(entry)
        duplicate = self.write_missed(entry)
        refusals = {
            "an unknown key": self.sqlstate_of(
                lambda: self.write_missed(dict(self.missed(), extra="x"))
            ),
            "a caller DB clock": self.sqlstate_of(
                lambda: self.write_missed(
                    dict(self.missed(), logged_at_db_clock="2026-11-05T00:00:00Z")
                )
            ),
            "another reason": self.sqlstate_of(
                lambda: self.write_missed(self.missed(reason="GUESSED"))
            ),
            "a claim use": self.sqlstate_of(
                lambda: self.write_missed(self.missed(evidence_use="CLAIM"))
            ),
        }
        self.add(
            "R-12 a missed instant is LOGGED, then DUPLICATE; off-contract entries are refused",
            logged == "LOGGED"
            and duplicate == "DUPLICATE"
            and all(s in ("23514", "22023") for s in refusals.values()),
            {"logged": logged, "duplicate": duplicate, "refusals": refusals},
        )

    def append_only_elsewhere(self) -> None:
        mutations = {}
        for table in ("lattice_commit_receipts", "lattice_missed_instants", "lattice_capacity"):
            column = COLUMN[table]
            update = f"UPDATE ucpe_lattice.{table} SET {column} = {column}"
            delete = f"DELETE FROM ucpe_lattice.{table}"
            mutations[table] = {
                "owner_update": self.as_role(OWNER, update),
                "owner_delete": self.as_role(OWNER, delete),
                "owner_truncate": self.denied(OWNER, f"TRUNCATE ucpe_lattice.{table}"),
                "super_update": self.sqlstate_of(lambda u=update: self.su.execute(u)),
                "super_delete": self.sqlstate_of(lambda d=delete: self.su.execute(d)),
            }
        expected = {
            "owner_update": 0,
            "owner_delete": 0,
            "owner_truncate": TRIGGER,
            "super_update": TRIGGER,
            "super_delete": TRIGGER,
        }
        self.add(
            "R-13 receipts, missed instants and capacity: the owner changes nothing and cannot"
            " truncate; a superuser's UPDATE and DELETE are stopped by the triggers",
            all(m == expected for m in mutations.values()),
            mutations,
        )

    def capacity(self) -> None:
        maximum, warn = CAPACITY
        sequence = []
        while self.used() < maximum and len(sequence) <= maximum:
            sequence.append([self.used(), self.write_row(self.row())])
        stop_row = self.write_row(self.row())
        stop_missed = self.write_missed(self.missed())
        plain = [s for u, s in sequence if u + 1 < warn]
        warned = [s for u, s in sequence if u + 1 >= warn]
        self.add(
            "R-6 capacity: UNSET before the capacity row; INSERTED below the warning line,"
            " INSERTED_WARN at it, CAPACITY_STOP at the maximum for rows and missed instants,"
            " nothing added",
            self.facts.get("capacity_unset") == ["CAPACITY_UNSET", "CAPACITY_UNSET"]
            and all(s == "INSERTED" for s in plain)
            and bool(warned)
            and all(s == "INSERTED_WARN" for s in warned)
            and stop_row == "CAPACITY_STOP"
            and stop_missed == "CAPACITY_STOP"
            and self.used() == maximum,
            {"sequence": sequence, "stop_row": stop_row, "stop_missed": stop_missed},
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rehearse migration 0019 on scratch PostgreSQL.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--super-url", required=True)
    parser.add_argument("--commit-ts", choices=("on", "off"), required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    for name, url in (("--url", args.url), ("--super-url", args.super_url)):
        reason = refuse_url(url)
        if reason:
            print(f"REFUSED: {name}: {reason}")
            return 2
    started = time.monotonic()
    rehearsal = Rehearsal(args.url, args.super_url, args.commit_ts)
    try:
        rehearsal.run()
    except Exception as exc:  # a crash is a FAIL with its class and SQLSTATE, never a URL
        message = str(exc).splitlines()[0][:300] if str(exc) else ""
        detail = {"error": type(exc).__name__, "sqlstate": getattr(exc, "sqlstate", None)}
        rehearsal.add("rehearsal completed", False, dict(detail, message=message))
    finally:
        rehearsal.runner.close()
        rehearsal.su.close()
    passed = bool(rehearsal.checks) and all(c["status"] == "PASS" for c in rehearsal.checks)
    report = {
        "schema": "ucpe.migration_0019_rehearsal.v1",
        "commit_ts": args.commit_ts,
        "migration_sha256": hashlib.sha256(MIGRATION.read_bytes()).hexdigest(),
        "code_row_sha256": hashlib.sha256(CODE_ROW.read_bytes()).hexdigest()
        if CODE_ROW.is_file()
        else None,
        "seconds": round(time.monotonic() - started, 1),
        "facts": rehearsal.facts,
        "checks": rehearsal.checks,
        "result": "PASS" if passed else "FAIL",
    }
    Path(args.report).write_text(json.dumps(report, indent=2, default=str) + "\n", "utf-8")
    for check in rehearsal.checks:
        print(f"{check['status']} {check['check'][:90]}")
    print(f"MIGRATION_0019_REHEARSAL={'PASS' if passed else 'FAIL'} checks={len(rehearsal.checks)}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
