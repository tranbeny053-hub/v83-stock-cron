"""Scratch-only end-to-end rehearsal of the EXP-09 read route."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from rehearse import FINGERPRINT_SQL  # noqa: E402

EXP09 = ROOT / "scripts/ng4_pilot_exp09.py"
APPLY = ROOT / "scripts/apply_migration_0019.py"
AS_OF = datetime(2026, 11, 30, tzinfo=UTC)
REHEARSAL_NOW = "2026-12-07T00:30:00Z"
PILOT_START = datetime(2026, 11, 23, tzinfo=UTC)
ANCHOR = datetime(2026, 9, 21, tzinfo=UTC)
TIMEFRAMES = ("15m", "1H", "4H", "1D")
STEP_SECONDS = {"15m": 2700, "1H": 10800, "4H": 43200, "1D": 259200}
REASONS = ("NOT_ISSUED", "FETCH_FAILED")
PILOT_CAPACITY, PILOT_WARN = 1200, 600
# A3: written by a second connection while the route reads (15m grid position 20, otherwise unused).
LATE_MISSED_INSTANT = datetime(2026, 11, 23, 15, 0, tzinfo=UTC)


def grid(timeframe: str) -> list[datetime]:
    step = timedelta(seconds=STEP_SECONDS[timeframe])
    offset = (PILOT_START - ANCHOR).total_seconds()
    first = ANCHOR + int(offset // step.total_seconds()) * step
    if first < PILOT_START:
        first += step
    result = []
    while first < AS_OF:
        result.append(first)
        first += step
    return result


def row_id(timeframe: str, instant: datetime) -> str:
    payload = ["E3_LATTICE_V1", "SOL/USDT", "binance", timeframe, instant.isoformat()]
    digest = hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()[:32]
    return f"e3l-{digest}:{timeframe}:REF"


LATE_MISSED = {
    "lattice_run_id": row_id("15m", LATE_MISSED_INSTANT).split(":")[0],
    "timeframe": "15m",
    "normalized_symbol": "SOL/USDT",
    "reference_venue": "BINANCE_PUBLIC",
    "lattice_instant_utc": LATE_MISSED_INSTANT.isoformat(),
    "reason": "FETCH_FAILED",
    "protocol_version": "E3_LATTICE_V1",
    "evidence_use": "TEST_ONLY",
}


class Rehearsal:
    def __init__(self, url: str, super_url: str, report: Path) -> None:
        import psycopg

        self.psycopg = psycopg
        self.url, self.super_url, self.report = url, super_url, report
        self.su = psycopg.connect(super_url, autocommit=True)
        self.checks: list[dict[str, Any]] = []
        self.facts: dict[str, Any] = {}
        self.owner = (
            psycopg.connect(url, autocommit=True).execute("SELECT current_user").fetchone()[0]
        )

    def check(self, name: str, ok: bool, detail: Any = None) -> None:
        self.checks.append({"check": name, "ok": bool(ok), "detail": detail})

    def tool(self, mode: str, reader_url: str | None = None) -> tuple[int, dict[str, Any]]:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.json"
            env = dict(os.environ)
            env.pop("SUPABASE_DB_URL", None)
            env["NG4_PILOT_EXP09_REHEARSAL_URL"] = reader_url or self.url
            env["NG4_PILOT_EXP09_REHEARSAL_NOW"] = REHEARSAL_NOW
            env["MIGRATION_0019_REHEARSAL_URL"] = self.url
            result = subprocess.run(
                [
                    sys.executable,
                    str(EXP09),
                    "--mode=rehearse",
                    "--as-of=2026-11-30T00:00:00Z",
                    f"--report={path}",
                ],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=180,
            )
            body = json.loads(path.read_text()) if path.exists() else {}
        return result.returncode, body

    def apply(self) -> tuple[int, dict[str, Any]]:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.json"
            env = dict(os.environ, MIGRATION_0019_REHEARSAL_URL=self.url)
            result = subprocess.run(
                [sys.executable, str(APPLY), "--mode=rehearse", f"--report={path}"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=180,
            )
            body = json.loads(path.read_text()) if path.exists() else {}
        return result.returncode, body

    def fingerprint(self) -> tuple[int, int, int, int]:
        return tuple(
            self.su.execute(
                "SELECT (SELECT count(*) FROM ucpe_lattice.lattice_rows), "
                "(SELECT count(*) FROM ucpe_lattice.lattice_commit_receipts), "
                "(SELECT count(*) FROM ucpe_lattice.lattice_missed_instants), "
                "(SELECT count(*) FROM ucpe_lattice.lattice_capacity)"
            ).fetchone()
        )

    def catalog_fingerprint(self) -> str:
        return self.su.execute(FINGERPRINT_SQL).fetchone()[0]

    def seed(self) -> dict[str, Any]:
        # Synthetic, fixed operational fields. The route never reads or reports these values.
        instants: dict[str, list[datetime]] = {}
        counts: dict[str, tuple[int, int]] = {}
        # The scratch superuser takes the writer role: the applier holds ADMIN on it without SET
        # (createrole_self_grant is empty), exactly as in production.
        writer = self.psycopg.connect(self.super_url, autocommit=True)
        with writer.cursor() as cur:
            for tf in TIMEFRAMES:
                instants_grid = grid(tf)
                # A few early issued rows, two missed entries, and one three-slot unlogged run.
                # 1D has only three slots before day 7, so the pattern adapts to the grid's length.
                chosen = [instants_grid[i] for i in (0, 4, 8, 12) if i < len(instants_grid)]
                missed = [instants_grid[i] for i in (2, 6) if i < len(instants_grid)]
                counts[tf] = (len(chosen), len(missed))
                instants[tf] = chosen
                for n, instant in enumerate(chosen):
                    identity = row_id(tf, instant)
                    values = {
                        "lattice_row_id": identity,
                        "lattice_run_id": identity.split(":")[0],
                        "lattice_instant_utc": instant.isoformat(),
                        "reference_close_utc": instant.isoformat(),
                        "horizon_end_utc": (instant + timedelta(days=1)).isoformat(),
                        "predicted_at_utc": instant.isoformat(),
                        "core_computed_at_utc": instant.isoformat(),
                        "issued_at_utc": (instant + timedelta(seconds=n + 1)).isoformat(),
                        "protocol_version": "E3_LATTICE_V1",
                        "evaluation_population": "E1_OPERATIONAL",
                        "timing_class": "NOT_APPLICABLE",
                        "evidence_use": "TEST_ONLY",
                        "arm": "REF",
                        "artifact_id": None,
                        "recipe_id": "reference-daytype-v1",
                        "methodology_version": "reference-daytype-v1",
                        "reference_prior_id": "TEST_ONLY_FIXTURE",
                        "normalized_symbol": "SOL/USDT",
                        "reference_venue": "BINANCE_PUBLIC",
                        "data_source": "BINANCE_PUBLIC",
                        "provider": "binance",
                        "timeframe": tf,
                        "horizon_bars": 1,
                        "target_version": "tc-v1",
                        "is_live_data": True,
                        "reference_price": 1.0,
                        "decision_band_frac": 0.01,
                        "p_up_frac": 0.34,
                        "p_down_frac": 0.33,
                        "p_timeout_frac": 0.33,
                    }
                    cur.execute("SET ROLE ucpe_lattice_writer")
                    cur.execute(
                        "SELECT ucpe_lattice.record_lattice_row(%s::jsonb)", (json.dumps(values),)
                    )
                    cur.execute("RESET ROLE")
                    self.capacity_after_write()
                for n, instant in enumerate(missed):
                    reason = REASONS[n]
                    identity = row_id(tf, instant)
                    entry = {
                        "lattice_run_id": identity.split(":")[0],
                        "timeframe": tf,
                        "normalized_symbol": "SOL/USDT",
                        "reference_venue": "BINANCE_PUBLIC",
                        "lattice_instant_utc": instant.isoformat(),
                        "reason": reason,
                        "protocol_version": "E3_LATTICE_V1",
                        "evidence_use": "TEST_ONLY",
                    }
                    cur.execute("SET ROLE ucpe_lattice_writer")
                    cur.execute(
                        "SELECT ucpe_lattice.record_missed_instant(%s::jsonb)", (json.dumps(entry),)
                    )
                    cur.execute("RESET ROLE")
                    self.capacity_after_write()
        writer.close()
        with self.psycopg.connect(self.super_url, autocommit=True) as conn:
            conn.execute("SET ROLE ucpe_lattice_writer")
            conn.execute("SELECT ucpe_lattice.capture_commit_receipts(1000)")
        return {"rows": instants, "counts": counts}

    def capacity_after_write(self) -> None:
        """A9: the route's reproduction equals capacity_status() after every synthetic write."""
        if not hasattr(self, "_route"):
            spec = importlib.util.spec_from_file_location("exp09_route_cap", EXP09)
            self._route = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self._route)
            self.capacity_mismatches = 0
            self.capacity_compared = 0
        rows, _, missed, _ = self.fingerprint()
        expected = self.su.execute("SELECT ucpe_lattice.capacity_status()").fetchone()[0]
        got = self._route.capacity_state(PILOT_CAPACITY, PILOT_WARN, rows, missed)
        self.capacity_compared += 1
        self.capacity_mismatches += expected != got

    def rls_backstop(self, url: str) -> str | None:
        """Behind the access check: the route's own statements, read by a role that row security
        would filter, raise instead of returning zero rows."""
        spec = importlib.util.spec_from_file_location("exp09_route_b", EXP09)
        route = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(route)
        with self.psycopg.connect(url) as conn, conn.cursor() as cur:
            for key in ("begin", "timeout", "lock_timeout", "row_security", "timezone"):
                cur.execute(route.SQL[key])
            try:
                cur.execute(route.SQL["rows"])
            except self.psycopg.Error as exc:
                return exc.sqlstate
            finally:
                conn.rollback()
        return None

    def snapshot_check(self, reader_url: str) -> None:
        """A3: a row inserted by another connection mid-read is invisible to the one snapshot."""
        spec = importlib.util.spec_from_file_location("exp09_route", EXP09)
        route = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(route)
        su_url, pg = self.super_url, self.psycopg

        class Cursor:
            def __init__(self, inner):
                self.inner = inner

            def execute(self, sql, *args):
                if sql == route.SQL["rows"]:
                    with pg.connect(su_url, autocommit=True) as other:
                        other.execute("SET ROLE ucpe_lattice_writer")
                        other.execute(
                            "SELECT ucpe_lattice.record_missed_instant(%s::jsonb)",
                            (json.dumps(LATE_MISSED),),
                        )
                return self.inner.execute(sql, *args)

            def __getattr__(self, name):
                return getattr(self.inner, name)

        class Connection:
            def __init__(self):
                self.inner = pg.connect(reader_url)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                self.inner.close()
                return False

            def cursor(self):
                return Cursor(self.inner.cursor())

        as_of = datetime(2026, 11, 30, tzinfo=UTC)
        report = route.measure(Connection, as_of, "0" * 40, route.CAPACITY_BODY_SHA256)
        occupancy, capacity = report["occupancy"], report["capacity"]
        in_window = sum(item["in_window"] for item in report["rows"].values())
        on_grid = sum(item["issued_on_grid"] for item in report["completeness"].values())
        missed_seen = occupancy["all_time_missed"]
        missed_now = self.fingerprint()[2]
        self.check(
            "snapshot_is_one_repeatable_read",
            in_window == on_grid and missed_now == missed_seen + 1
            and capacity["state"] == route.capacity_state(
                PILOT_CAPACITY, PILOT_WARN, occupancy["all_time_rows"], missed_seen
            ),
            {"in_window": in_window, "on_grid": on_grid, "missed_seen": missed_seen,
             "missed_now": missed_now},
        )

    def run(self) -> int:
        code, apply_report = self.apply()
        self.check("apply_0019_capacity_0020", code == 0, apply_report.get("outcome"))
        for role, extra in (("exp09_no_rls", ""), ("exp09_reader", "BYPASSRLS")):
            self.su.execute(f"CREATE ROLE {role} LOGIN {extra}")
            self.su.execute(f"GRANT pg_read_all_data TO {role}")
        # No explicit grant (review EX-C1 A9): production's only possible path is the implicit
        # pg_read_all_data plus BYPASSRLS, so the readers get exactly that.
        pattern = self.seed()
        before = self.fingerprint()
        catalog_before = self.catalog_fingerprint()
        a_code, a = self.tool("rehearse")
        self.check(
            "applier_refuses_without_read_path",
            a_code == 2 and a.get("refusal") == "NO_READ_PATH",
            {"exit": a_code, "refusal": a.get("refusal")},
        )
        no_rls_url = self.url.replace(f"user={self.owner}", "user=exp09_no_rls")
        b_code, b = self.tool("rehearse", no_rls_url)
        # Case (b) never reads: the route's access check refuses it (no superuser, no BYPASSRLS).
        self.check(
            "read_all_data_without_bypass_is_refused",
            b_code == 2 and b.get("refusal") == "NO_READ_PATH" and "rows" not in b,
            {"exit": b_code, "refusal": b.get("refusal")},
        )
        self.check("row_security_off_backstop_raises", self.rls_backstop(no_rls_url) == "42501")
        reader_url = self.url.replace(f"user={self.owner}", "user=exp09_reader")
        c_code, c = self.tool("rehearse", reader_url)
        self.check(
            "bypass_reader_reads",
            c_code == 0 and c.get("outcome") == "READ_OK",
            {"exit": c_code, "outcome": c.get("outcome")},
        )
        pattern_checks = True
        pattern_detail = {}
        expected_plan = {"15m": 224, "1H": 56, "4H": 14, "1D": 3}
        for timeframe in TIMEFRAMES:
            rows = c.get("rows", {}).get(timeframe, {})
            completeness = c.get("completeness", {}).get(timeframe, {})
            missed = c.get("missed", {}).get(timeframe, {})
            n_rows, n_missed = pattern["counts"][timeframe]
            plan = expected_plan[timeframe]
            expected_missed = {REASONS[i]: 1 for i in range(n_missed)}
            current = (
                rows.get("in_window") == n_rows
                and completeness.get("planned") == plan
                and completeness.get("issued_on_grid") == n_rows
                and completeness.get("missed_on_grid") == n_missed
                and completeness.get("unlogged") == plan - n_rows - n_missed
                and completeness.get("issued_fraction") == round(n_rows / plan, 6)
                and completeness.get("accounted_fraction") == round((n_rows + n_missed) / plan, 6)
                and missed == expected_missed
                and sum(item.get("count", 0) for item in completeness.get("unlogged_runs", []))
                == plan - n_rows - n_missed
            )
            pattern_checks = pattern_checks and current
            pattern_detail[timeframe] = current
        self.check(
            "read_counts_fractions_and_gap_runs_match_fixture", pattern_checks, pattern_detail
        )
        self.check(
            "capacity_matches_function",
            c.get("capacity", {}).get("state")
            == self.su.execute("SELECT ucpe_lattice.capacity_status()").fetchone()[0],
            c.get("capacity"),
        )
        self.check(
            "capacity_reproduction_equals_function_after_every_write",
            getattr(self, "capacity_compared", 0) > 0 and self.capacity_mismatches == 0,
            {"compared": getattr(self, "capacity_compared", 0),
             "mismatches": getattr(self, "capacity_mismatches", None)},
        )
        self.check(
            "capacity_body_matches",
            c.get("capacity", {}).get("capacity_function_body_matches_authored") is True,
        )
        after = self.fingerprint()
        self.check("read_cases_change_no_rows", before == after, {"before": before, "after": after})
        self.snapshot_check(reader_url)
        catalog_after = self.catalog_fingerprint()
        self.check("read_cases_change_no_catalog", catalog_before == catalog_after)
        self.facts["pattern"] = pattern
        self.facts["results"] = {"case_a": a, "case_b": b, "case_c": c}
        self.report.write_text(
            json.dumps({"checks": self.checks, "facts": self.facts}, indent=2, default=str) + "\n"
        )
        return 0 if all(item["ok"] for item in self.checks) else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--super-url", required=True)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    return Rehearsal(args.url, args.super_url, args.report).run()


if __name__ == "__main__":
    raise SystemExit(main())
