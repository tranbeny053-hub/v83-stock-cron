"""Pure EXP-09 measurement helpers for the NG4 pilot.

EXP-09 measures operational completeness and unlogged grid instants. The route reads counts,
statuses and timestamps only; it never reads a probability, price or band value. It is authored
and disabled, and applies no threshold.
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
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PILOT_START_UTC = datetime(2026, 11, 23, tzinfo=UTC)
PILOT_DURATION = timedelta(days=14)
PILOT_END_UTC = PILOT_START_UTC + PILOT_DURATION
LATTICE_ANCHOR_UTC = datetime(2026, 9, 21, tzinfo=UTC)
PILOT_TIMEFRAMES = ("15m", "1H", "4H", "1D")
STEP_SECONDS = {"15m": 2700, "1H": 10800, "4H": 43200, "1D": 259200}
PILOT_NORMALIZED_SYMBOL = "SOL/USDT"
PILOT_REFERENCE_VENUE = "BINANCE_PUBLIC"
PILOT_CAPACITY_MAX = 1200
PILOT_CAPACITY_WARN = 600
REPORT_SCHEMA = "ng4-pilot-exp09-report.v1"
END_SETTLE = timedelta(minutes=10)
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
WORKFLOW = ".github/workflows/ng4-pilot-exp09.yml"
SCRIPT = "scripts/ng4_pilot_exp09.py"
EXPECTED_REPOSITORY = "tranbeny053-hub/v83-stock-cron"
MISSED_REASONS = (
    "NOT_ISSUED", "CAPACITY_STOP", "FETCH_FAILED",
    "STALE_SNAPSHOT", "REFERENCE_UNAVAILABLE", "WINDOW_UNAVAILABLE",
)
ACCESS_KEYS = (
    "rolsuper", "rolbypassrls", "schema_usage", "rows_select", "receipts_select",
    "missed_select", "capacity_select",
)
SQL = {
    "begin": "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY",
    "timeout": "SET LOCAL statement_timeout = '15000'",
    "lock_timeout": "SET LOCAL lock_timeout = '2000'",
    "row_security": "SET LOCAL row_security = off",
    "timezone": "SET LOCAL TimeZone = 'UTC'",
    "access": """SELECT
        coalesce((SELECT pg_roles.rolsuper FROM pg_catalog.pg_roles
                  WHERE pg_roles.rolname = current_user), false),
        coalesce((SELECT pg_roles.rolbypassrls FROM pg_catalog.pg_roles
                  WHERE pg_roles.rolname = current_user), false),
        coalesce(has_schema_privilege(current_user,
            (SELECT pg_namespace.oid FROM pg_catalog.pg_namespace
             WHERE pg_namespace.nspname = 'ucpe_lattice'), 'USAGE'), false),
        coalesce(has_table_privilege(current_user,
            (SELECT pg_class.oid FROM pg_catalog.pg_class
             JOIN pg_catalog.pg_namespace ON pg_namespace.oid = pg_class.relnamespace
             WHERE pg_namespace.nspname = 'ucpe_lattice'
             AND pg_class.relname = 'lattice_rows'), 'SELECT'), false),
        coalesce(has_table_privilege(current_user,
            (SELECT pg_class.oid FROM pg_catalog.pg_class
             JOIN pg_catalog.pg_namespace ON pg_namespace.oid = pg_class.relnamespace
             WHERE pg_namespace.nspname = 'ucpe_lattice'
             AND pg_class.relname = 'lattice_commit_receipts'), 'SELECT'), false),
        coalesce(has_table_privilege(current_user,
            (SELECT pg_class.oid FROM pg_catalog.pg_class
             JOIN pg_catalog.pg_namespace ON pg_namespace.oid = pg_class.relnamespace
             WHERE pg_namespace.nspname = 'ucpe_lattice'
             AND pg_class.relname = 'lattice_missed_instants'), 'SELECT'), false),
        coalesce(has_table_privilege(current_user,
            (SELECT pg_class.oid FROM pg_catalog.pg_class
             JOIN pg_catalog.pg_namespace ON pg_namespace.oid = pg_class.relnamespace
             WHERE pg_namespace.nspname = 'ucpe_lattice'
             AND pg_class.relname = 'lattice_capacity'), 'SELECT'), false)""",
    "read_at": "SELECT statement_timestamp()",
    "capacity": "SELECT lattice_capacity.max_rows, lattice_capacity.warn_rows "
                "FROM ucpe_lattice.lattice_capacity WHERE lattice_capacity.id",
    "rows": """SELECT lattice_rows.timeframe, lattice_rows.normalized_symbol,
        lattice_rows.reference_venue, lattice_rows.lattice_instant_utc,
        lattice_rows.issued_at_utc, lattice_rows.db_insert_clock_utc,
        lattice_rows.evidence_use, lattice_rows.evaluation_population,
        lattice_commit_receipts.commit_state
        FROM ucpe_lattice.lattice_rows LEFT JOIN ucpe_lattice.lattice_commit_receipts
        ON lattice_commit_receipts.lattice_row_id = lattice_rows.lattice_row_id""",
    "missed": """SELECT lattice_missed_instants.timeframe,
        lattice_missed_instants.normalized_symbol, lattice_missed_instants.reference_venue,
        lattice_missed_instants.lattice_instant_utc, lattice_missed_instants.reason,
        lattice_missed_instants.logged_at_db_clock
        FROM ucpe_lattice.lattice_missed_instants""",
    "sizes": """SELECT pg_class.relname, pg_total_relation_size(pg_class.oid),
        pg_relation_size(pg_class.oid), pg_indexes_size(pg_class.oid)
        FROM pg_catalog.pg_class JOIN pg_catalog.pg_namespace
        ON pg_namespace.oid = pg_class.relnamespace
        WHERE pg_namespace.nspname = 'ucpe_lattice'
        AND pg_class.relname IN ('lattice_rows', 'lattice_commit_receipts',
        'lattice_missed_instants', 'lattice_capacity')""",
    "capacity_body": """SELECT pg_proc.prosrc FROM pg_catalog.pg_proc
        JOIN pg_catalog.pg_namespace ON pg_namespace.oid = pg_proc.pronamespace
        WHERE pg_namespace.nspname = 'ucpe_lattice'
        AND pg_proc.proname = 'capacity_status'""",
    "rollback": "ROLLBACK",
}


class Refused(Exception):
    """A safe refusal carrying only a stable code."""

    def __init__(self, code: str, access: tuple[bool, ...] | None = None) -> None:
        self.code = code
        self.access = access
        super().__init__(code)


def _iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def lattice_instants(timeframe: str, start: datetime, end: datetime) -> tuple[datetime, ...]:
    """Return lattice instants in the inclusive interval using the fixed lattice anchor."""
    if timeframe not in STEP_SECONDS:
        raise ValueError("Unsupported timeframe")
    if start.utcoffset() != timedelta(0) or end.utcoffset() != timedelta(0):
        raise ValueError("Bounds must be aware UTC datetimes")
    step = timedelta(seconds=STEP_SECONDS[timeframe])
    elapsed = (start - LATTICE_ANCHOR_UTC).total_seconds()
    first = LATTICE_ANCHOR_UTC + int(elapsed // step.total_seconds()) * step
    if first < start:
        first += step
    values = []
    while first <= end:
        values.append(first)
        first += step
    return tuple(values)


def reconstruct_gaps(
    grid: Iterable[datetime], row_instants: Iterable[datetime], missed_instants: Iterable[datetime]
) -> tuple[datetime, ...]:
    rows, missed = set(row_instants), set(missed_instants)
    return tuple(instant for instant in grid if instant not in rows and instant not in missed)


def parse_as_of(text: str | None, now: datetime) -> datetime:
    if text is None:
        value = PILOT_END_UTC
    else:
        try:
            if len(text) != 20 or text[-1] != "Z" or text[16:19] != ":00":
                raise ValueError
            value = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        except (TypeError, ValueError):
            raise Refused("AS_OF_FORMAT") from None
    if now.utcoffset() != timedelta(0):
        now = now.astimezone(UTC)
    if value <= PILOT_START_UTC:
        raise Refused("AS_OF_NOT_AFTER_START")
    if value > PILOT_END_UTC:
        raise Refused("AS_OF_AFTER_END")
    if value > now:
        raise Refused("AS_OF_IN_FUTURE")
    if value == PILOT_END_UTC and now < PILOT_END_UTC + END_SETTLE:
        raise Refused("END_NOT_SETTLED")
    return value


def window(as_of: datetime) -> tuple[datetime, datetime]:
    return PILOT_START_UTC, as_of


def grid(timeframe: str, as_of: datetime) -> list[datetime]:
    return [
        instant
        for instant in lattice_instants(timeframe, PILOT_START_UTC, as_of)
        if instant < as_of
    ]


def measure_cell(
    timeframe: str,
    as_of: datetime,
    row_instants: Iterable[datetime],
    missed_instants: Iterable[datetime],
) -> dict[str, object]:
    planned_grid = grid(timeframe, as_of)
    row_set, missed_set = set(row_instants), set(missed_instants)
    grid_set = set(planned_grid)
    issued = row_set & grid_set
    missed = missed_set & grid_set
    unlogged = set(reconstruct_gaps(planned_grid, row_set, missed_set))
    overlap = issued & missed
    planned = len(planned_grid)
    issued_fraction = round(len(issued) / planned, 6) if planned else None
    accounted_fraction = (
        round((len(issued) + len(missed) - len(overlap)) / planned, 6) if planned else None
    )
    runs: list[dict[str, object]] = []
    run_start: int | None = None
    for index, instant in enumerate(planned_grid):
        if instant in unlogged:
            if run_start is None:
                run_start = index
        elif run_start is not None:
            runs.append(_run(planned_grid, run_start, index - 1))
            run_start = None
    if run_start is not None:
        runs.append(_run(planned_grid, run_start, len(planned_grid) - 1))
    return {
        "planned": planned,
        "issued_on_grid": len(issued),
        "missed_on_grid": len(missed),
        "off_grid_rows": len(row_set - grid_set),
        "row_and_missed_same_instant": len(overlap),
        "unlogged": len(unlogged),
        "issued_fraction": issued_fraction,
        "accounted_fraction": accounted_fraction,
        "unlogged_runs": runs,
    }


def _run(grid_values: list[datetime], first_index: int, last_index: int) -> dict[str, object]:
    return {
        "first": _iso_z(grid_values[first_index]),
        "last": _iso_z(grid_values[last_index]),
        "count": last_index - first_index + 1,
        "cause": "NOT_RECORDED_IN_DATABASE",
    }


def capacity_state(max_rows: int | None, warn_rows: int | None, rows: int, missed: int) -> str:
    if max_rows is None:
        return "CAPACITY_UNSET"
    used = rows + missed
    if used >= max_rows:
        return "CAPACITY_STOP"
    if warn_rows is not None and used + 1 >= warn_rows:
        return "WARN"
    return "OK"


def assemble_report(
    as_of: datetime,
    dispatched_sha: str,
    sections: dict[str, object] | None = None,
) -> dict[str, object]:
    start, end = window(as_of)
    report: dict[str, object] = {
        "schema": REPORT_SCHEMA,
        "evidence_use": "TEST_ONLY",
        "population": "E1_OPERATIONAL",
        "claim": "NONE",
        "look_spent": "NONE (counts, statuses and timestamps only)",
        "verdict": "NOT_JUDGED_THRESHOLD_UNRULED",
        "thresholds": "OD-NG-7 unruled; none applied or stored",
        "http_counts": "NOT_IN_DATABASE",
        "http_counts_note": (
            "Provider exchanges appear only in the Space's own logs (owner-visible)."
        ),
        "window": {"start": _iso_z(start), "end": _iso_z(end)},
        "as_of_utc": _iso_z(as_of),
        "provisional": as_of < PILOT_END_UTC,
        "dispatched_sha": dispatched_sha if isinstance(dispatched_sha, str)
        and re.fullmatch(r"[0-9a-f]{40}", dispatched_sha) else None,
    }
    if sections:
        report.update(sections)
    return report


def dumps(report: dict[str, object]) -> str:
    return json.dumps(report, indent=2, sort_keys=False, ensure_ascii=True) + "\n"


def authored_capacity_body(root: Path) -> str:
    filename = "0019" + "_" + "lattice_evidence.sql"
    migration = (root / "migrations/authored" / filename).read_text(encoding="utf-8")
    marker = "CREATE FUNCTION ucpe_lattice.capacity_status()"
    start = migration.index("AS $$", migration.index(marker)) + len("AS $$")
    end = migration.index("$$;", start)
    return migration[start:end]


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    values.sort()
    position = (len(values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def _distribution(values: list[float]) -> dict[str, object]:
    if not values:
        return {key: None for key in ("n", "min", "p50", "p95", "max")} | {"n": 0}
    return {
        "n": len(values),
        "min": round(min(values), 3),
        "p50": round(_percentile(values, 0.5), 3),
        "p95": round(_percentile(values, 0.95), 3),
        "max": round(max(values), 3),
    }


def _time(value: datetime) -> datetime:
    return value.astimezone(UTC)


def measure(open_connection, as_of: datetime, dispatched_sha: str,
            authored_capacity_body: str) -> dict[str, object]:
    access: tuple[bool, ...] = ()
    read_at: datetime | None = None
    rows: list[tuple] = []
    missed: list[tuple] = []
    sizes: dict[str, dict[str, int]] = {}
    capacity: tuple = (None, None)
    capacity_body = ""
    with open_connection() as conn:
        cur = conn.cursor()
        try:
            cur.execute(SQL["begin"])
            cur.execute(SQL["timeout"])
            cur.execute(SQL["lock_timeout"])
            cur.execute(SQL["row_security"])
            cur.execute(SQL["timezone"])
            cur.execute(SQL["access"])
            access = tuple(bool(value) for value in cur.fetchone())
            if len(access) != len(ACCESS_KEYS):
                raise RuntimeError("MALFORMED_ACCESS")
            if not ((access[0] or access[1]) and all(access[2:])):
                raise Refused("NO_READ_PATH", access)
            cur.execute(SQL["read_at"])
            read_at = cur.fetchone()[0]
            cur.execute(SQL["capacity"])
            capacity = cur.fetchone() or (None, None)
            cur.execute(SQL["rows"])
            rows = list(cur.fetchall())
            cur.execute(SQL["missed"])
            missed = list(cur.fetchall())
            cur.execute(SQL["sizes"])
            sizes = {
                str(name): {"total_bytes": int(total), "table_bytes": int(table),
                            "index_bytes": int(index)}
                for name, total, table, index in cur.fetchall()
            }
            cur.execute(SQL["capacity_body"])
            body_row = cur.fetchone()
            capacity_body = body_row[0] if body_row else ""
        finally:
            cur.execute(SQL["rollback"])

    by_tf_rows = {tf: [] for tf in PILOT_TIMEFRAMES}
    by_tf_missed = {tf: [] for tf in PILOT_TIMEFRAMES}
    unexpected_rows = unexpected_missed = 0
    foreign_rows = foreign_missed = 0
    for row in rows:
        tf, symbol, venue, instant, issued, inserted, evidence, population, state = row
        if (symbol, venue) != (PILOT_NORMALIZED_SYMBOL, PILOT_REFERENCE_VENUE):
            foreign_rows += 1
            continue
        if tf in by_tf_rows:
            by_tf_rows[tf].append((instant, issued, inserted, evidence, population, state))
        else:
            unexpected_rows += 1
    for entry in missed:
        tf, symbol, venue, instant, reason, logged = entry
        if (symbol, venue) != (PILOT_NORMALIZED_SYMBOL, PILOT_REFERENCE_VENUE):
            foreign_missed += 1
            continue
        if tf in by_tf_missed:
            by_tf_missed[tf].append((instant, reason, logged))
        else:
            unexpected_missed += 1

    start = PILOT_START_UTC
    row_report: dict[str, object] = {}
    missed_report: dict[str, object] = {}
    completeness: dict[str, object] = {}
    timing: dict[str, object] = {}
    for timeframe in PILOT_TIMEFRAMES:
        pilot_rows = by_tf_rows[timeframe]
        pilot_missed = by_tf_missed[timeframe]
        in_rows = [row for row in pilot_rows if start <= _time(row[0]) < as_of]
        after_rows = [row for row in pilot_rows if as_of <= _time(row[0]) < PILOT_END_UTC]
        outside_rows = [row for row in pilot_rows if not start <= _time(row[0]) < PILOT_END_UTC]
        instants = sorted(_time(row[0]) for row in in_rows)
        receipt_counts = {"COMMITTED": 0, "COMMIT_UNKNOWN": 0, "NONE": 0}
        non_test = 0
        for row in in_rows:
            state = row[5]
            receipt_counts[state if state in ("COMMITTED", "COMMIT_UNKNOWN") else "NONE"] += 1
            if row[3] != "TEST_ONLY" or row[4] != "E1_OPERATIONAL":
                non_test += 1
        row_report[timeframe] = {
            "in_window": len(in_rows), "after_as_of": len(after_rows),
            "outside_pilot_window": len(outside_rows),
            "first": _iso_z(instants[0]) if instants else None,
            "last": _iso_z(instants[-1]) if instants else None,
            "non_test_only": non_test, "receipts": receipt_counts,
        }
        in_missed = [row for row in pilot_missed if start <= _time(row[0]) < as_of]
        reason_counts: dict[str, int] = {}
        for _, reason, _ in in_missed:
            key = reason if reason in MISSED_REASONS else "<unexpected>"
            reason_counts[key] = reason_counts.get(key, 0) + 1
        missed_report[timeframe] = reason_counts
        completeness[timeframe] = measure_cell(
            timeframe, as_of,
            [row[0] for row in in_rows], [row[0] for row in in_missed],
        )
        first_latency = [(row[1] - row[0]).total_seconds() for row in in_rows]
        second_latency = [(row[2] - row[1]).total_seconds() for row in in_rows]
        timing[timeframe] = {
            "issued_after_lattice_seconds": _distribution(first_latency),
            "store_latency_plus_clock_offset_seconds": _distribution(second_latency),
        }

    all_rows = len(rows)
    all_receipts = sum(1 for row in rows if row[8] is not None)
    all_missed = len(missed)
    total_rows = sizes.get("lattice_rows", {}).get("total_bytes", 0)
    total_receipts = sizes.get("lattice_commit_receipts", {}).get("total_bytes", 0)
    max_rows, warn_rows = capacity
    sections = {
        "access": dict(zip(ACCESS_KEYS, access, strict=True)),
        "rows": row_report,
        "foreign_cell_rows": foreign_rows,
        "unexpected_timeframe_rows": {"<unexpected>": unexpected_rows} if unexpected_rows else {},
        "missed": missed_report,
        "foreign_cell_missed": foreign_missed,
        "unexpected_timeframe_missed": {"<unexpected>": unexpected_missed}
        if unexpected_missed else {},
        "completeness": completeness,
        "timing": timing,
        "late_writes": {
            "rows": sum(1 for row in rows if _time(row[5]) >= as_of),
            "missed": sum(1 for row in missed if _time(row[5]) >= as_of),
        },
        "occupancy": {
            "tables": sizes, "all_time_rows": all_rows,
            "all_time_receipts": all_receipts, "all_time_missed": all_missed,
            "bytes_per_row_estimate": (total_rows + total_receipts) / all_rows
            if all_rows else None,
            "label": "ESTIMATE_INCLUDES_PAGE_AND_INDEX_OVERHEAD",
        },
        "capacity": {
            "state": capacity_state(max_rows, warn_rows, all_rows, all_missed),
            "capacity_row_is_pilot": (max_rows, warn_rows)
            == (PILOT_CAPACITY_MAX, PILOT_CAPACITY_WARN),
            "capacity_function_body_matches_authored": hashlib.sha256(
                capacity_body.encode()
            ).digest() == hashlib.sha256(authored_capacity_body.encode()).digest(),
        },
        "read_at_db_utc": _iso_z(read_at),
    }
    return assemble_report(as_of, dispatched_sha, sections)


def refuse_url(url: str) -> str | None:
    if "supabase" in url.lower():
        return "URL_REFUSED"
    parsed = urlparse(url)
    if parsed.scheme not in ("postgresql", "postgres"):
        return "URL_REFUSED"
    host = parsed.hostname or ""
    socket = parse_qs(parsed.query).get("host", [""])[0]
    return None if host in ("localhost", "127.0.0.1") or (
        host == "" and socket.startswith("/")
    ) else "URL_REFUSED"


def verify_dispatch(env, expected_sha):
    failures = (
        env.get("GITHUB_ACTIONS") != "true",
        env.get("GITHUB_REPOSITORY") != EXPECTED_REPOSITORY,
        env.get("GITHUB_EVENT_NAME") != "workflow_dispatch",
        env.get("GITHUB_REF") != "refs/heads/main",
        env.get("GITHUB_WORKFLOW_REF")
        != f"{EXPECTED_REPOSITORY}/{WORKFLOW}@refs/heads/main",
        not re.fullmatch(r"[0-9a-f]{40}", expected_sha or "")
        or env.get("GITHUB_SHA") != expected_sha,
        platform.python_implementation() != "CPython"
        or platform.python_version() != "3.13.14",
    )
    if any(failures):
        raise Refused("DISPATCH")


def enter_isolated_runtime(wheelhouse):
    if not wheelhouse:
        raise Refused("RUNTIME")
    if str(SOURCE) not in sys.path:
        sys.path.append(str(SOURCE))
    from crypto_probability_engine import runtime_isolation
    return runtime_isolation.enter(ROOT, wheelhouse=Path(wheelhouse))


def attest_dispatch(env, expected_sha, isolation):
    from crypto_probability_engine import runtime_isolation
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=no"], cwd=ROOT,
        check=True, capture_output=True, text=True,
    ).stdout
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    if (status or head != expected_sha or env.get("GITHUB_SHA") != expected_sha
            or (platform.python_implementation(), platform.python_version())
            != ("CPython", "3.13.14")
            or runtime_isolation.interpreter_flags()
            != runtime_isolation.REQUIRED_FLAGS_TEXT):
        raise Refused("DISPATCH")
    verify_dispatch(env, expected_sha)
    return {"workflow": WORKFLOW, "expected_sha": expected_sha, "git_head": head,
            "installed_files_sha256": isolation.installed_files_sha256}


def attest_loaded_modules(isolation):
    from crypto_probability_engine import runtime_isolation
    from crypto_probability_engine.oos.evaluation.evaluator_pin import pinned_files
    return runtime_isolation.attest_loaded_modules(
        isolation, pinned=(*pinned_files(ROOT), SCRIPT), root=ROOT
    )


def load_driver():
    import psycopg
    return psycopg


def _empty_report(as_of, dispatched_sha):
    return assemble_report(as_of, dispatched_sha) if as_of else {
        "schema": REPORT_SCHEMA, "evidence_use": "TEST_ONLY", "population": "E1_OPERATIONAL",
        "claim": "NONE", "look_spent": "NONE (counts, statuses and timestamps only)",
        "verdict": "NOT_JUDGED_THRESHOLD_UNRULED",
        "thresholds": "OD-NG-7 unruled; none applied or stored", "http_counts": "NOT_IN_DATABASE",
        "http_counts_note": (
            "Provider exchanges appear only in the Space's own logs (owner-visible)."
        ),
        "window": {"start": _iso_z(PILOT_START_UTC), "end": _iso_z(PILOT_END_UTC)},
        "as_of_utc": None, "provisional": True,
        "dispatched_sha": dispatched_sha if isinstance(dispatched_sha, str)
        and re.fullmatch(r"[0-9a-f]{40}", dispatched_sha) else None,
    }


def main(argv=None, *, environ=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("attest", "rehearse", "run"), required=True)
    parser.add_argument("--report")
    parser.add_argument("--expected-sha")
    parser.add_argument("--wheelhouse")
    parser.add_argument("--as-of")
    args = parser.parse_args(argv)
    env = os.environ if environ is None else environ
    report = _empty_report(None, args.expected_sha)
    code = 1
    try:
        rehearsal_clock = env.get("NG4_PILOT_EXP09_REHEARSAL_NOW")
        if args.mode == "rehearse":
            if rehearsal_clock is None:
                now = datetime.now(UTC)
            else:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00Z", rehearsal_clock):
                    raise Refused("REHEARSAL_NOW_FORMAT")
                try:
                    now = datetime.strptime(
                        rehearsal_clock, "%Y-%m-%dT%H:%M:%SZ"
                    ).replace(tzinfo=UTC)
                except ValueError:
                    raise Refused("REHEARSAL_NOW_FORMAT") from None
        else:
            if rehearsal_clock is not None:
                raise Refused("REHEARSAL_NOW_REFUSED")
            now = datetime.now(UTC)
        as_of_text = args.as_of or env.get("NG4_PILOT_EXP09_AS_OF")
        as_of = parse_as_of(as_of_text, now)
        report = _empty_report(as_of, args.expected_sha)
        if args.mode in ("attest", "run") and not args.wheelhouse:
            raise Refused("RUNTIME")
        isolation = None
        if args.mode in ("attest", "run"):
            isolation = enter_isolated_runtime(args.wheelhouse)
            dispatch = attest_dispatch(env, args.expected_sha, isolation)
            attest_loaded_modules(isolation)
            if args.mode == "attest":
                load_driver()
                attest_loaded_modules(isolation)
                report["dispatch"] = dispatch
                report["outcome"] = "READ_OK"
                code = 0
            else:
                url = env.get("SUPABASE_DB_URL", "")
                driver = load_driver()
                attest_loaded_modules(isolation)
                measured = measure(
                    lambda: driver.connect(url, connect_timeout=8), as_of,
                    args.expected_sha, authored_capacity_body(ROOT),
                )
                report = measured
                report["dispatch"] = dispatch
                report["outcome"] = "READ_OK"
                code = 0
        else:
            if env.get("SUPABASE_DB_URL"):
                raise Refused("URL_REFUSED")
            url = env.get("NG4_PILOT_EXP09_REHEARSAL_URL", "")
            if refuse_url(url) or not url:
                raise Refused("URL_REFUSED")
            if args.wheelhouse:
                isolation = enter_isolated_runtime(args.wheelhouse)
                driver = load_driver()
                attest_loaded_modules(isolation)
            else:
                driver = load_driver()
            report = measure(
                lambda: driver.connect(url, connect_timeout=8), as_of,
                args.expected_sha or "", authored_capacity_body(ROOT),
            )
            report["outcome"] = "READ_OK"
            code = 0
    except Exception as exc:
        report = _empty_report(None, args.expected_sha)
        report["outcome"] = "REFUSED" if isinstance(exc, Refused) else "ERROR"
        if isinstance(exc, Refused):
            report["refusal"] = exc.code
            if exc.access is not None:
                report["access"] = dict(zip(ACCESS_KEYS, exc.access, strict=True))
            code = 2
        else:
            report["error"] = type(exc).__name__
            sqlstate = getattr(exc, "sqlstate", None)
            if isinstance(sqlstate, str) and re.fullmatch(r"[0-9A-Z]{5}", sqlstate):
                report["sqlstate"] = sqlstate
            code = 1
    encoded = dumps(report)
    dispatched = report.get("dispatched_sha")
    if not isinstance(dispatched, str) or not re.fullmatch(r"[0-9a-f]{40}", dispatched):
        report["dispatched_sha"] = None
        encoded = dumps(report)
    print(encoded, end="")
    if args.report:
        Path(args.report).write_text(encoded, encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
