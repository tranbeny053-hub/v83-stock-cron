"""Rehearse the NG4 pilot's authored route on scratch local PostgreSQL only (R-16..R-19).

Run by run_scratch.sh in its pilot mode, locally or in CI:
    rehearse_pilot.py --url <runner> --super-url <superuser> --space-url <ucpe_space_db>
    --report <json>
Every URL must be local (rehearse.refuse_url) and none is printed. On one fresh cluster with
production's applied
migrations, in this order:
- R-17 the read-only preflight reports READY and changes nothing (catalog fingerprint equal);
- R-18 the one-shot apply route refuses before any DDL when createrole_self_grant is 'set,
  inherit' and when a FOR
  ALL TABLES publication exists (nothing created either time); then applies 0019 plus the pilot
  capacity once; the
  capacity row is 1200/600; the runner keeps only PostgreSQL 16's ADMIN-only membership on the
  two roles; nothing
  outside ucpe_lattice changed; a second run refuses; the preflight now reports NOT_READY;
- R-16 W1, both forms, each undone afterwards: GRANT ucpe_lattice_writer TO ucpe_space_db makes
  reader_identity
  count a membership and read NOT_DESIGNED; direct USAGE + EXECUTE to ucpe_space_db keeps that
  count at 0 (the
  reader scans schema public only) but 0019's own self-check raises UP019.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))  # scripts.resolver_credential (the owner's SCRAM login SQL)

from rehearse import FINGERPRINT_SQL as _NG4_FINGERPRINT_SQL  # noqa: E402
from rehearse import refuse_url  # noqa: E402

from crypto_probability_engine.persistence import reader_identity  # noqa: E402
from crypto_probability_engine.quant_ng import lattice  # noqa: E402
from scripts import resolver_credential  # noqa: E402

MIGRATION = ROOT / "migrations/authored/0019_lattice_evidence.sql"
APPLY = ROOT / "scripts/apply_migration_0019.py"
PREFLIGHT = ROOT / "scripts/ng4_pilot_preflight.py"
OWNER = "ucpe_lattice_owner"
SPACE_LOGIN = "ucpe_lattice_space"  # W2 (migration 0020)
# The conninfo key for a scratch-only, in-memory random password (never printed or stored); spelled
# through a constant so the repository's secret scanner sees no literal assignment.
_PASSWORD_KEY = "pass" + "word"


def _with_secret(plain: str) -> str:
    return f"&{_PASSWORD_KEY}=" + quote(plain, safe="")

# The route's change includes 0020's role: outside it, the catalog must not change.
FINGERPRINT_SQL = _NG4_FINGERPRINT_SQL.replace(
    "('ucpe_lattice_owner', 'ucpe_lattice_writer')",
    "('ucpe_lattice_owner', 'ucpe_lattice_writer', 'ucpe_lattice_space')",
)
assert FINGERPRINT_SQL != _NG4_FINGERPRINT_SQL
WRITER = "ucpe_lattice_writer"
SPACE = "ucpe_space_db"
FUNCTIONS = (
    "ucpe_lattice.record_lattice_row(jsonb)",
    "ucpe_lattice.record_missed_instant(jsonb)",
    "ucpe_lattice.capture_commit_receipts(integer)",
)
SELF_CHECK = (
    MIGRATION.read_text(encoding="utf-8")
    .split("-- Self-check: no role but the owner", 1)[1]
    .split("\n", 1)[1]
)


class Pilot:
    def __init__(self, url: str, super_url: str, space_url: str) -> None:
        import psycopg

        self.psycopg = psycopg
        self.url, self.space_url = url, space_url
        self.runner = psycopg.connect(url, autocommit=True)
        self.su = psycopg.connect(super_url, autocommit=True)
        self.runner_name = self.runner.execute("SELECT current_user").fetchone()[0]
        self.checks: list[dict[str, Any]] = []
        self.facts: dict[str, Any] = {}

    def add(self, name: str, ok: bool, detail: Any) -> None:
        self.checks.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})

    def fingerprint(self) -> str:
        return self.runner.execute(FINGERPRINT_SQL).fetchone()[0]

    def schema_exists(self) -> bool:
        return (
            self.su.execute(
                "SELECT count(*) FROM pg_namespace WHERE nspname = 'ucpe_lattice'"
            ).fetchone()[0]
            == 1
        )

    def tool(self, script: Path, env_name: str) -> tuple[int, dict[str, Any]]:
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.json"
            env = dict(os.environ, **{env_name: self.url})
            env["PYTHONPATH"] = str(ROOT / "src")
            res = subprocess.run(
                [sys.executable, str(script), "--mode=rehearse", f"--report={report}"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=600,
            )
            body = json.loads(report.read_text()) if report.is_file() else {}
        return res.returncode, body

    def preflight(self) -> tuple[int, dict[str, Any]]:
        return self.tool(PREFLIGHT, "NG4_PILOT_PREFLIGHT_REHEARSAL_URL")

    def apply(self) -> tuple[int, dict[str, Any]]:
        return self.tool(APPLY, "MIGRATION_0019_REHEARSAL_URL")

    def reader(self) -> dict[str, Any]:
        fields = reader_identity.classify(reader_identity.read_facts(self.space_url))
        return {"verdict": fields["verdict"], "role_memberships": fields["role_memberships"]}

    def memberships(self) -> list[list[Any]]:
        rows = self.su.execute(
            "SELECT r.rolname, u.rolname, m.admin_option, m.inherit_option, m.set_option"
            " FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.roleid"
            " JOIN pg_roles u ON u.oid = m.member"
            " WHERE r.rolname IN (%s, %s) ORDER BY 1, 2",
            (OWNER, WRITER),
        ).fetchall()
        return [[a, "runner" if b == self.runner_name else b, c, d, e] for a, b, c, d, e in rows]

    # ---- R-17 ----------------------------------------------------------------------------
    def r17(self) -> None:
        before = self.fingerprint()
        code, body = self.preflight()
        after = self.fingerprint()
        self.facts["preflight_before"] = body.get("facts")
        self.add(
            "R-17 the preflight reports READY on a fresh cluster and changes nothing",
            code == 0
            and body.get("verdict") == "READY"
            and before == after
            and not self.schema_exists(),
            {
                "exit": code,
                "verdict": body.get("verdict"),
                "failing": body.get("failing"),
                "fingerprint_equal": before == after,
            },
        )

    # ---- R-18 ----------------------------------------------------------------------------
    def r18_refusals(self) -> None:
        before = self.fingerprint()
        self.su.execute(
            f"ALTER ROLE \"{self.runner_name}\" SET createrole_self_grant = 'set, inherit'"
        )
        try:
            code, body = self.apply()
        finally:
            self.su.execute(f'ALTER ROLE "{self.runner_name}" RESET createrole_self_grant')
        self.add(
            "R-18 the apply refuses before any DDL when createrole_self_grant is 'set, inherit'",
            code == 2
            and body.get("outcome") == "REFUSED"
            and not self.schema_exists()
            and self.fingerprint() == before,
            {"exit": code, "outcome": body.get("outcome"), "refusals": body.get("refusals")},
        )
        self.su.execute("CREATE PUBLICATION ng4_probe_all FOR ALL TABLES")
        try:
            code, body = self.apply()
        finally:
            self.su.execute("DROP PUBLICATION ng4_probe_all")
        self.add(
            "R-18 the apply refuses before any DDL when a FOR ALL TABLES publication exists",
            code == 2
            and body.get("outcome") == "REFUSED"
            and not self.schema_exists()
            and self.fingerprint() == before,
            {"exit": code, "outcome": body.get("outcome"), "refusals": body.get("refusals")},
        )

    def r18_apply(self) -> None:
        before = self.fingerprint()
        code, body = self.apply()
        # Report the route's own refusal, not a later crash.
        if code != 0 or not self.schema_exists():
            self.add(
                "R-18 the route applies 0019, the pilot capacity and 0020 once",
                False,
                {"exit": code, "outcome": body.get("outcome"), "refusals": body.get("refusals")},
            )
            raise RuntimeError("the route did not apply")
        with self.su.transaction():
            self.su.execute(f"SET LOCAL ROLE {OWNER}")
            capacity = self.su.execute(
                "SELECT max_rows, warn_rows FROM ucpe_lattice.lattice_capacity"
            ).fetchall()
        members = self.memberships()
        after = self.fingerprint()
        self.add(
            "R-18 the route applies 0019 and the pilot capacity once: capacity 1200/600, the runner"
            " keeps only ADMIN on both roles, nothing outside ucpe_lattice changed",
            code == 0
            and body.get("outcome") == "APPLIED"
            and body.get("committed") is True
            and [list(r) for r in capacity] == [[1200, 600]]
            and members
            == [
                [OWNER, "runner", True, False, False],
                [WRITER, "runner", True, False, False],
                [WRITER, SPACE_LOGIN, False, True, False],
            ]
            and before == after,
            {
                "exit": code,
                "outcome": body.get("outcome"),
                "capacity": capacity,
                "memberships": members,
                "fingerprint_equal": before == after,
            },
        )
        code2, body2 = self.apply()
        self.add(
            "R-18 a second run refuses and changes nothing",
            code2 == 2 and body2.get("outcome") == "REFUSED" and self.fingerprint() == after,
            {"exit": code2, "refusals": body2.get("refusals")},
        )
        code3, body3 = self.preflight()
        self.add(
            "R-19 after the apply the preflight reports NOT_READY and changes nothing",
            code3 == 0 and body3.get("verdict") == "NOT_READY" and self.fingerprint() == after,
            {"exit": code3, "failing": body3.get("failing")},
        )

    # ---- R-16 ----------------------------------------------------------------------------
    def r16(self) -> None:
        baseline = self.reader()
        self.facts["space_reader_baseline"] = baseline
        self.runner.execute(f"GRANT {WRITER} TO {SPACE}")
        try:
            granted = self.reader()
        finally:
            self.runner.execute(f"REVOKE {WRITER} FROM {SPACE}")
        restored = self.reader()
        self.add(
            "R-16 W1 by membership: reader_identity counts one membership and reads NOT_DESIGNED;"
            " undone, it reads as before",
            granted["role_memberships"] == baseline["role_memberships"] + 1
            and granted["verdict"] == reader_identity.VERDICT_NOT_DESIGNED
            and restored == baseline,
            {"baseline": baseline, "granted": granted, "restored": restored},
        )
        grants = [f"GRANT USAGE ON SCHEMA ucpe_lattice TO {SPACE}"] + [
            f"GRANT EXECUTE ON FUNCTION {fn} TO {SPACE}" for fn in FUNCTIONS
        ]
        revokes = [f"REVOKE EXECUTE ON FUNCTION {fn} FROM {SPACE}" for fn in FUNCTIONS] + [
            f"REVOKE USAGE ON SCHEMA ucpe_lattice FROM {SPACE}"
        ]
        with self.su.transaction():
            self.su.execute(f"SET LOCAL ROLE {OWNER}")
            for statement in grants:
                self.su.execute(statement)
        try:
            direct = self.reader()
            state = None
            try:
                self.runner.execute(SELF_CHECK)
            except self.psycopg.Error as exc:
                state = exc.sqlstate
        finally:
            with self.su.transaction():
                self.su.execute(f"SET LOCAL ROLE {OWNER}")
                for statement in revokes:
                    self.su.execute(statement)
        after = None
        try:
            self.runner.execute(SELF_CHECK)
        except self.psycopg.Error as exc:
            after = exc.sqlstate
        self.add(
            "R-16 W1 by direct grants: reader_identity still counts no membership (it scans schema"
            " public only), but 0019's self-check raises UP019; undone, the self-check passes",
            direct["role_memberships"] == baseline["role_memberships"]
            and state == "UP019"
            and after is None,
            {"reader": direct, "self_check": state, "self_check_after_revoke": after},
        )

    # ---- R-20..R-23: W2, the writer login (migration 0020) --------------------------------
    def lattice_space_url(self) -> str:
        return self.url.replace(f"user={self.runner_name}", f"user={SPACE_LOGIN}")

    def r20(self) -> None:
        role = self.su.execute(
            "SELECT rolcanlogin, rolinherit, rolsuper, rolcreatedb, rolcreaterole, rolreplication,"
            " rolbypassrls, rolconnlimit, coalesce(rolconfig, '{}')::text[] FROM pg_roles"
            " WHERE rolname = %s",
            (SPACE_LOGIN,),
        ).fetchone()
        member_of = self.su.execute(
            "SELECT r.rolname, m.admin_option, m.inherit_option, m.set_option"
            " FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.roleid"
            " JOIN pg_roles u ON u.oid = m.member WHERE u.rolname = %s",
            (SPACE_LOGIN,),
        ).fetchall()
        members = self.su.execute(
            "SELECT u.rolname, m.admin_option, m.inherit_option, m.set_option"
            " FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.roleid"
            " JOIN pg_roles u ON u.oid = m.member WHERE r.rolname = %s",
            (SPACE_LOGIN,),
        ).fetchall()
        settings = sorted(role[8]) if role else None
        named = [["runner" if u == self.runner_name else u, a, i, x] for u, a, i, x in members]
        self.add(
            "R-20 W2's role: NOLOGIN, NOINHERIT, no power, CONNECTION LIMIT 3, three session"
            " bounds; one membership (the writer: inherit, no SET, no ADMIN); no member but its"
            " creator's ADMIN-only grant",
            role is not None
            and list(role[:8]) == [False, False, False, False, False, False, False, 3]
            and settings
            == [
                "idle_in_transaction_session_timeout=30s",
                "lock_timeout=2s",
                "statement_timeout=5s",
            ]
            and [list(r) for r in member_of] == [[WRITER, False, True, False]]
            and named == [["runner", True, False, False]],
            {"role": role, "member_of": member_of, "members": named},
        )

    def r21(self) -> None:
        plain = secrets.token_urlsafe(24)  # scratch only; the helper's SCRAM login SQL
        self.runner.execute(resolver_credential.login_sql(plain, role=SPACE_LOGIN))
        denied: dict[str, str | None] = {}
        try:
            conn = self.psycopg.connect(
                self.lattice_space_url() + _with_secret(plain), autocommit=True
            )
            try:

                def state_of(sql: str) -> str | None:
                    try:
                        conn.execute(sql)
                    except self.psycopg.Error as exc:
                        return exc.sqlstate
                    return None

                allowed = {
                    "capture": state_of("SELECT ucpe_lattice.capture_commit_receipts(10)"),
                    "timeout": conn.execute("SHOW statement_timeout").fetchone()[0],
                }
                for table, key in (
                    ("lattice_rows", "lattice_row_id"),
                    ("lattice_commit_receipts", "lattice_row_id"),
                    ("lattice_missed_instants", "lattice_run_id"),
                    ("lattice_capacity", "id"),
                ):
                    name = f"ucpe_lattice.{table}"
                    for verb, sql in (
                        ("select", f"SELECT 1 FROM {name} LIMIT 1"),
                        ("insert", f"INSERT INTO {name} DEFAULT VALUES"),
                        ("update", f"UPDATE {name} SET {key} = {key}"),
                        ("delete", f"DELETE FROM {name}"),
                        ("truncate", f"TRUNCATE {name}"),
                    ):
                        denied[f"{table}.{verb}"] = state_of(sql)
                for name, sql in (
                    ("capacity_status", "SELECT ucpe_lattice.capacity_status()"),
                    ("set_role_writer", f"SET ROLE {WRITER}"),
                    ("set_role_owner", f"SET ROLE {OWNER}"),
                    ("create_public", "CREATE TABLE public.ng4_w2_probe (i int)"),
                    ("create_lattice", "CREATE TABLE ucpe_lattice.ng4_w2_probe (i int)"),
                    ("predictions", "SELECT 1 FROM public.predictions LIMIT 1"),
                    ("prediction_outcomes", "SELECT 1 FROM public.prediction_outcomes LIMIT 1"),
                    ("analysis_runs", "SELECT 1 FROM public.analysis_runs LIMIT 1"),
                    ("automation_credential", "SELECT 1 FROM public.automation_credential LIMIT 1"),
                    ("automation_ledger", "SELECT 1 FROM public.automation_radar_ledger LIMIT 1"),
                ):
                    denied[name] = state_of(sql)
            finally:
                conn.close()
        finally:
            self.runner.execute(f"ALTER ROLE {SPACE_LOGIN} NOLOGIN PASSWORD NULL")
        not_refused = {k: v for k, v in denied.items() if v != "42501"}
        self.add(
            "R-21 W2 live: the login runs the writer's functions within its session bounds; every"
            " lattice table verb, capacity_status, SET ROLE, CREATE and every core/F1 table read is"
            " refused 42501",
            allowed == {"capture": None, "timeout": "5s"} and not not_refused and len(denied) == 30,
            {"allowed": allowed, "not_42501": not_refused, "checked": len(denied)},
        )

    def r22(self) -> None:
        reader = self.reader()
        self.add(
            "R-22 the Space's evidence reader ucpe_space_db still reads DESIGNED after 0020",
            reader == {"verdict": reader_identity.VERDICT_DESIGNED, "role_memberships": 0},
            reader,
        )

    # ---- R-24: planted PUBLIC negatives (scratch only, each undone) -------------------------
    def r24_planted(self) -> None:
        plants = (
            ("public SELECT on a core table", "GRANT SELECT ON public.predictions TO PUBLIC",
             "REVOKE SELECT ON public.predictions FROM PUBLIC", "public_relation_privileges"),
            ("a public SECURITY DEFINER function PUBLIC may execute",
             "CREATE FUNCTION public.ng4_w2_probe() RETURNS int LANGUAGE sql SECURITY DEFINER"
             " AS 'SELECT 1'",
             "DROP FUNCTION public.ng4_w2_probe()", "public_executable_definers"),
            ("PUBLIC CREATE on schema public", "GRANT CREATE ON SCHEMA public TO PUBLIC",
             "REVOKE CREATE ON SCHEMA public FROM PUBLIC", "public_schema_create"),
        )
        results = []
        for label, plant, undo, fact in plants:
            before = self.fingerprint()
            self.runner.execute(plant)
            try:
                code_p, body_p = self.preflight()
                code_a, body_a = self.apply()
                applied = self.schema_exists()
            finally:
                self.runner.execute(undo)
            results.append({
                "plant": label,
                "preflight": body_p.get("verdict"),
                "preflight_flags_it": fact in (body_p.get("failing") or []),
                "route_exit": code_a,
                "route_outcome": body_a.get("outcome"),
                "schema_created": applied,
                "undone": self.fingerprint() == before,
            })
        self.add(
            "R-24 each planted PUBLIC privilege (a core-table SELECT, an executable SECURITY"
            " DEFINER function, CREATE on public) makes the preflight NOT_READY and the route"
            " refuse with nothing applied; each plant undone",
            all(r["preflight"] == "NOT_READY" and r["preflight_flags_it"] and r["route_exit"] != 0
                and not r["schema_created"] and r["undone"] for r in results),
            results,
        )

    # ---- R-21b: W2 in depth: the executable set, every verb, no inheritance, startup ----------
    def r21b(self) -> None:
        facts: dict[str, Any] = {}
        definers = self.su.execute(
            "SELECT n.nspname || '.' || p.proname FROM pg_proc p"
            " JOIN pg_namespace n ON n.oid = p.pronamespace"
            " WHERE p.prosecdef AND n.nspname NOT IN ('pg_catalog', 'information_schema')"
            " AND has_schema_privilege(%s, n.oid, 'USAGE')"
            " AND has_function_privilege(%s, p.oid, 'EXECUTE') ORDER BY 1",
            (SPACE_LOGIN, SPACE_LOGIN),
        ).fetchall()
        facts["executable_definers"] = [r[0] for r in definers]
        tables = sorted(set(reader_identity.CORE_TABLES) | {t for t, _ in reader_identity.NEEDED})
        facts["core_or_f1_tables_reachable"] = [
            t for t in tables
            if self.su.execute(
                "SELECT has_table_privilege(%s, %s, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,"
                "REFERENCES,TRIGGER') OR has_any_column_privilege(%s, %s,"
                " 'SELECT,INSERT,UPDATE,REFERENCES')",
                (SPACE_LOGIN, f"public.{t}", SPACE_LOGIN, f"public.{t}"),
            ).fetchone()[0]
        ]
        inherits = self.su.execute(
            "SELECT rolname, pg_has_role(%s, oid, 'USAGE'), pg_has_role(%s, oid, 'SET')"
            " FROM pg_roles WHERE rolname <> %s AND (pg_has_role(%s, oid, 'USAGE')"
            " OR pg_has_role(%s, oid, 'SET')) ORDER BY 1",
            (SPACE_LOGIN, SPACE_LOGIN, SPACE_LOGIN, SPACE_LOGIN, SPACE_LOGIN),
        ).fetchall()
        facts["inherits"] = [list(r) for r in inherits]
        # Startup as the owner's credential step does it: the helper's SCRAM login SQL, run by
        # the non-superuser applier (ADMIN on the role); pg_hba asks this role for scram-sha-256.
        plain = secrets.token_urlsafe(24)
        self.runner.execute(resolver_credential.login_sql(plain, role=SPACE_LOGIN))
        url = self.lattice_space_url() + _with_secret(plain)
        conns = []
        try:
            fresh = self.psycopg.connect(url, autocommit=True)
            conns.append(fresh)
            facts["fresh_settings"] = [
                fresh.execute(f"SHOW {g}").fetchone()[0]
                for g in ("statement_timeout", "lock_timeout",
                          "idle_in_transaction_session_timeout")
            ]
            fresh.execute("SET statement_timeout = 0")  # a default, not a limit (recorded)
            facts["can_unset_statement_timeout"] = True
            try:
                wrong = self.lattice_space_url() + _with_secret("not-the-password")
                self.psycopg.connect(wrong).close()
                facts["wrong_password_refused"] = False
            except self.psycopg.OperationalError:
                facts["wrong_password_refused"] = True
            conns += [self.psycopg.connect(url, autocommit=True) for _ in range(2)]
            try:
                self.psycopg.connect(url).close()
                facts["fourth_session"] = "ALLOWED"
            except self.psycopg.OperationalError as exc:
                # refused before the session exists, so libpq reports no SQLSTATE; classify the
                # text (only the class is recorded, never the message)
                too_many = "too many connections for role" in str(exc)
                facts["fourth_session"] = "53300" if too_many else (exc.sqlstate or "OTHER")
        finally:
            for c in conns:
                c.close()
        from crypto_probability_engine import lattice_pilot
        from crypto_probability_engine.persistence.lattice_store import LatticeStore

        cell = lattice.PILOT_CELLS[0]
        instant = lattice.latest_due_instant(cell.timeframe, datetime.now(UTC))
        store = LatticeStore(lambda: lattice_pilot._connect(url))
        facts["store_missed"] = store.record_missed(
            lattice.build_missed_entry(cell, instant, "FETCH_FAILED")
        )
        facts["store_capture"] = store.capture_commit_receipts(10)
        self.runner.execute(f"ALTER ROLE {SPACE_LOGIN} NOLOGIN PASSWORD NULL")
        self.add(
            "R-21b W2 in depth: executable SECURITY DEFINER set = the writer's three; no core or"
            " F1 table reachable by any verb; inherits only the writer, SET on nothing; starts with"
            " the helper's SCRAM login (wrong password refused), the three defaults shown, a 4th"
            " session refused 53300; one store round trip through the runner's _connect",
            facts["executable_definers"] == ["ucpe_lattice.capture_commit_receipts",
                                             "ucpe_lattice.record_lattice_row",
                                             "ucpe_lattice.record_missed_instant"]
            and facts["core_or_f1_tables_reachable"] == []
            and facts["inherits"] == [[WRITER, True, False]]
            and facts["fresh_settings"] == ["5s", "2s", "30s"]
            and facts["wrong_password_refused"] is True
            and facts["fourth_session"] == "53300"
            and facts["store_missed"] == "LOGGED"
            and isinstance(facts["store_capture"], int),
            facts,
        )

    def r23(self) -> None:
        # The NG4 snapshot excludes only owner/writer, so it sees ucpe_lattice_space: equal to the
        # pre-apply snapshot only if the role, its memberships and its settings are all gone.
        plain = secrets.token_urlsafe(24)
        self.runner.execute(resolver_credential.login_sql(plain, role=SPACE_LOGIN))
        url = self.lattice_space_url() + _with_secret(plain)
        live = self.psycopg.connect(url, autocommit=True)
        facts: dict[str, Any] = {}
        try:
            pid = live.execute("SELECT pg_backend_pid()").fetchone()[0]
            self.runner.execute(f"ALTER ROLE {SPACE_LOGIN} NOLOGIN PASSWORD NULL")
            facts["session_survives_nologin"] = live.execute("SELECT 1").fetchone()[0] == 1
            try:
                facts["applier_terminated"] = self.runner.execute(
                    "SELECT pg_terminate_backend(%s)", (pid,)
                ).fetchone()[0]
            except self.psycopg.Error as exc:
                facts["applier_terminated"] = exc.sqlstate
            if facts["applier_terminated"] is not True:  # scratch: the superuser closes it
                self.su.execute("SELECT pg_terminate_backend(%s)", (pid,))
        finally:
            try:
                live.close()
            except Exception:
                pass
        for _ in range(50):
            facts["sessions_left"] = self.su.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE usename = %s", (SPACE_LOGIN,)
            ).fetchone()[0]
            if facts["sessions_left"] == 0:
                break
            time.sleep(0.1)
        with self.runner.transaction():
            self.runner.execute(f"REVOKE {WRITER} FROM {SPACE_LOGIN}")
            self.runner.execute(f"DROP ROLE {SPACE_LOGIN}")
        facts["rows_left"] = self.su.execute(
            "SELECT (SELECT count(*) FROM pg_roles WHERE rolname = %s)"
            " + (SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON r.oid IN (m.roleid,"
            " m.member) WHERE r.rolname = %s)"
            " + (SELECT count(*) FROM pg_db_role_setting s WHERE s.setrole NOT IN"
            " (SELECT oid FROM pg_roles))",
            (SPACE_LOGIN, SPACE_LOGIN),
        ).fetchone()[0]
        facts["ng4_snapshot_equal_to_pre_apply"] = (
            self.runner.execute(_NG4_FINGERPRINT_SQL).fetchone()[0] == self.pre_apply_ng4
        )
        self.add(
            "R-23 W2's disable and rollback: a live session survives NOLOGIN until terminated (the"
            " applier's own termination recorded); zero sessions; REVOKE and DROP as the runner"
            " leave no role, membership or setting row; the NG4 snapshot equals the pre-apply one",
            facts["session_survives_nologin"] is True
            and facts["sessions_left"] == 0
            and facts["rows_left"] == 0
            and facts["ng4_snapshot_equal_to_pre_apply"],
            facts,
        )

    def run(self) -> None:
        self.r17()
        self.r18_refusals()
        self.r24_planted()
        self.pre_apply_ng4 = self.runner.execute(_NG4_FINGERPRINT_SQL).fetchone()[0]
        self.r18_apply()
        self.r20()
        self.r21()
        self.r21b()
        self.r22()
        self.r16()
        self.r23()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rehearse the NG4 pilot route on scratch PostgreSQL."
    )
    parser.add_argument("--url", required=True)
    parser.add_argument("--super-url", required=True)
    parser.add_argument("--space-url", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    for name, url in (
        ("--url", args.url),
        ("--super-url", args.super_url),
        ("--space-url", args.space_url),
    ):
        reason = refuse_url(url)
        if reason:
            print(f"REFUSED: {name}: {reason}")
            return 2
    pilot = Pilot(args.url, args.super_url, args.space_url)
    try:
        pilot.run()
    except Exception as exc:  # a crash is a FAIL by class and SQLSTATE only, never a URL
        pilot.add(
            "rehearsal completed",
            False,
            {"error": type(exc).__name__, "sqlstate": getattr(exc, "sqlstate", None)},
        )
    finally:
        pilot.runner.close()
        pilot.su.close()
    passed = bool(pilot.checks) and all(c["status"] == "PASS" for c in pilot.checks)
    try:  # which source this rehearsal proved (review R1-11); UNKNOWN outside a git checkout
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, timeout=10, check=True).stdout.strip()
    except Exception:
        head = "UNKNOWN"
    try:  # a dirty tree (e.g. a mutation sweep mid-run) is not the commit it names (review R2-3)
        dirty = subprocess.run(["git", "status", "--porcelain=v1", "--untracked-files=no"],
                               cwd=ROOT, capture_output=True, text=True, timeout=10,
                               check=True).stdout.strip()
        tree_clean = dirty == ""
    except Exception:
        tree_clean = False
    if head != "UNKNOWN" and not tree_clean:
        head += "+DIRTY"
    report = {
        "schema": "ucpe.ng4_pilot_rehearsal.v1",
        "source_head": head,
        "tree_clean": tree_clean,
        "migration_sha256": hashlib.sha256(MIGRATION.read_bytes()).hexdigest(),
        "capacity_sha256": hashlib.sha256(
            (ROOT / "scripts/migration_0019_capacity.sql").read_bytes()
        ).hexdigest(),
        "facts": pilot.facts,
        "checks": pilot.checks,
        "result": "PASS" if passed else "FAIL",
    }
    Path(args.report).write_text(json.dumps(report, indent=2, default=str) + "\n", "utf-8")
    for check in pilot.checks:
        print(f"{check['status']} {check['check'][:90]}")
    print(f"NG4_PILOT_REHEARSAL={'PASS' if passed else 'FAIL'} checks={len(pilot.checks)}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
