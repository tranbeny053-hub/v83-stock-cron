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
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))

from rehearse import FINGERPRINT_SQL, refuse_url  # noqa: E402

from crypto_probability_engine.persistence import reader_identity  # noqa: E402

MIGRATION = ROOT / "migrations/authored/0019_lattice_evidence.sql"
APPLY = ROOT / "scripts/apply_migration_0019.py"
PREFLIGHT = ROOT / "scripts/ng4_pilot_preflight.py"
OWNER = "ucpe_lattice_owner"
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
            == [[OWNER, "runner", True, False, False], [WRITER, "runner", True, False, False]]
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

    def run(self) -> None:
        self.r17()
        self.r18_refusals()
        self.r18_apply()
        self.r16()


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
    report = {
        "schema": "ucpe.ng4_pilot_rehearsal.v1",
        "source_head": head,
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
