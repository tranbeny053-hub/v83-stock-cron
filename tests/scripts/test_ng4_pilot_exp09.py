import ast
import importlib.util
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from crypto_probability_engine.quant_ng import lattice

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "ng4_pilot_exp09_test", ROOT / "scripts/ng4_pilot_exp09.py"
)
exp09 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exp09)


def instant(day: int, hour: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, tzinfo=UTC)


def test_restated_constants_match_lattice():
    assert set(exp09.MISSED_REASONS) == lattice._MISSED
    assert exp09.PILOT_START_UTC == lattice.PILOT_START_UTC
    assert exp09.PILOT_DURATION == lattice.PILOT_DURATION
    assert exp09.PILOT_END_UTC == lattice.pilot_end(lattice.PILOT_START_UTC)
    assert exp09.LATTICE_ANCHOR_UTC == lattice.LATTICE_ANCHOR_UTC
    assert exp09.PILOT_TIMEFRAMES == lattice.PILOT_TIMEFRAMES
    assert exp09.STEP_SECONDS == {
        tf: lattice._BAR_SECONDS[tf] * lattice.CADENCE_BARS for tf in lattice.PILOT_TIMEFRAMES
    }
    assert exp09.PILOT_CAPACITY_MAX == lattice.PILOT_CAPACITY_MAX
    assert exp09.PILOT_CAPACITY_WARN == lattice.PILOT_CAPACITY_WARN
    assert (
        exp09.PILOT_NORMALIZED_SYMBOL
        == lattice.build_missed_entry(lattice.PILOT_CELLS[0], exp09.PILOT_START_UTC, "NOT_ISSUED")[
            "normalized_symbol"
        ]
    )
    assert (
        exp09.PILOT_REFERENCE_VENUE
        == lattice.build_missed_entry(lattice.PILOT_CELLS[0], exp09.PILOT_START_UTC, "NOT_ISSUED")[
            "reference_venue"
        ]
    )


def test_lattice_grid_matches_for_full_window_and_day_seven():
    day_seven = datetime(2026, 11, 30, tzinfo=UTC)
    full_counts, day_counts = [], []
    for timeframe in exp09.PILOT_TIMEFRAMES:
        full = exp09.lattice_instants(timeframe, exp09.PILOT_START_UTC, exp09.PILOT_END_UTC)
        day = exp09.lattice_instants(timeframe, exp09.PILOT_START_UTC, day_seven)
        assert full == lattice.lattice_instants(
            timeframe, exp09.PILOT_START_UTC, exp09.PILOT_END_UTC
        )
        assert day == lattice.lattice_instants(timeframe, exp09.PILOT_START_UTC, day_seven)
        full_counts.append(len([value for value in full if value < exp09.PILOT_END_UTC]))
        day_counts.append(len([value for value in day if value < day_seven]))
    assert full_counts == [448, 112, 28, 5]
    assert sum(full_counts) == 593
    assert sum(full_counts) == sum(lattice.planned_slots(exp09.PILOT_START_UTC).values())
    assert day_counts == [224, 56, 14, 3]
    assert sum(day_counts) == 297
    assert sum(len(exp09.grid(tf, exp09.PILOT_END_UTC)) for tf in exp09.PILOT_TIMEFRAMES) == 593
    assert sum(len(exp09.grid(tf, day_seven)) for tf in exp09.PILOT_TIMEFRAMES) == 297


def test_reconstruct_gaps_matches_lattice():
    grid = [instant(23), instant(23, 1), instant(23, 2), instant(23, 3)]
    rows = [grid[0], grid[3]]
    missed = [grid[1]]
    assert exp09.reconstruct_gaps(grid, rows, missed) == lattice.reconstruct_gaps(
        grid, rows, missed
    )


@pytest.mark.parametrize(
    ("text", "now", "code"),
    [
        ("2026-11-23T00:00:00Z", instant(24), "AS_OF_NOT_AFTER_START"),
        ("2026-12-07T00:01:00Z", datetime(2026, 12, 8, tzinfo=UTC), "AS_OF_AFTER_END"),
        ("2026-11-24T00:00:00+00:00", instant(25), "AS_OF_FORMAT"),
        ("2026-11-24T00:00:30Z", instant(25), "AS_OF_FORMAT"),
        ("a" * 40, instant(25), "AS_OF_FORMAT"),
        ("2026-11-25T00:00:00Z", instant(24), "AS_OF_IN_FUTURE"),
        ("2026-12-07T00:00:00Z", datetime(2026, 12, 7, 0, 9, tzinfo=UTC), "END_NOT_SETTLED"),
    ],
)
def test_parse_as_of_refusal_codes_and_no_input_echo(text, now, code):
    with pytest.raises(exp09.Refused) as caught:
        exp09.parse_as_of(text, now)
    assert caught.value.code == code
    if len(text) == 40:
        assert text not in str(caught.value)


def test_parse_as_of_default_and_valid_value():
    settled = exp09.PILOT_END_UTC + exp09.END_SETTLE
    assert exp09.parse_as_of(None, settled) == exp09.PILOT_END_UTC
    expected = datetime(2026, 11, 25, 12, tzinfo=UTC)
    assert exp09.parse_as_of("2026-11-25T12:00:00Z", settled) == expected


def test_measure_cell_full_coverage_gap_runs_and_integrity_counts():
    as_of = datetime(2026, 11, 23, 4, tzinfo=UTC)
    values = exp09.grid("15m", as_of)
    complete = exp09.measure_cell("15m", as_of, values, [])
    assert complete["planned"] == 6
    assert complete["issued_on_grid"] == 6
    assert complete["unlogged"] == 0
    assert complete["issued_fraction"] == 1.0
    assert complete["accounted_fraction"] == 1.0
    gap = exp09.measure_cell("15m", as_of, values[:1] + values[4:], [])
    assert gap["unlogged"] == 3
    assert gap["unlogged_runs"] == [
        {
            "first": "2026-11-23T00:45:00Z",
            "last": "2026-11-23T02:15:00Z",
            "count": 3,
            "cause": "NOT_RECORDED_IN_DATABASE",
        }
    ]
    off_grid = as_of - timedelta(minutes=1)
    mixed = exp09.measure_cell("15m", as_of, [values[0], off_grid], [values[0]])
    assert mixed["off_grid_rows"] == 1
    assert mixed["row_and_missed_same_instant"] == 1
    assert mixed["issued_on_grid"] == 1
    assert mixed["missed_on_grid"] == 1
    assert mixed["accounted_fraction"] == round(1 / 6, 6)


def test_measure_cell_zero_planned():
    result = exp09.measure_cell("15m", exp09.PILOT_START_UTC, [], [])
    assert result["planned"] == 0
    assert result["issued_fraction"] is None
    assert result["accounted_fraction"] is None


@pytest.mark.parametrize(
    ("max_rows", "warn_rows", "rows", "missed", "expected"),
    [
        (None, 600, 0, 0, "CAPACITY_UNSET"),
        (1200, 600, 1200, 0, "CAPACITY_STOP"),
        (1200, 600, 599, 0, "WARN"),
        (1200, 600, 598, 0, "OK"),
    ],
)
def test_capacity_state_boundaries(max_rows, warn_rows, rows, missed, expected):
    assert exp09.capacity_state(max_rows, warn_rows, rows, missed) == expected


def test_report_is_deterministic_and_has_fixed_order_and_values():
    args = (datetime(2026, 11, 30, tzinfo=UTC), "a" * 40)
    first = exp09.assemble_report(*args)
    second = exp09.assemble_report(*args)
    assert exp09.dumps(first).encode() == exp09.dumps(second).encode()
    assert list(first) == [
        "schema",
        "evidence_use",
        "population",
        "claim",
        "look_spent",
        "verdict",
        "thresholds",
        "http_counts",
        "http_counts_note",
        "window",
        "as_of_utc",
        "provisional",
        "dispatched_sha",
    ]
    assert first["schema"] == exp09.REPORT_SCHEMA
    assert first["evidence_use"] == "TEST_ONLY"
    assert first["population"] == "E1_OPERATIONAL"
    assert first["claim"] == "NONE"
    assert first["look_spent"] == "NONE (counts, statuses and timestamps only)"
    assert first["verdict"] == "NOT_JUDGED_THRESHOLD_UNRULED"
    assert first["thresholds"] == "OD-NG-7 unruled; none applied or stored"
    assert first["http_counts"] == "NOT_IN_DATABASE"
    assert first["as_of_utc"] == "2026-11-30T00:00:00Z"
    assert first["provisional"] is True
    assert first["dispatched_sha"] == args[1]
    assert exp09.assemble_report(args[0], "not-a-sha")["dispatched_sha"] is None
    assert set(first) & {"threshold", "threshold_value", "completeness_threshold"} == set()
    assert "0.90" not in exp09.dumps(first)


class FakeCursor:
    def __init__(self, responses, fail_on=None):
        self.responses = responses
        self.fail_on = fail_on
        self.executed = []
        self.current = None

    def execute(self, query):
        self.executed.append(query)
        self.current = next(key for key, value in exp09.SQL.items() if value == query)
        if self.current == self.fail_on:
            raise FakeOperationalError("db.example.supabase.co " + "a" * 40, "XX001")

    def fetchone(self):
        value = self.responses.get(self.current, [])
        if isinstance(value, list) and value and isinstance(value[0], tuple):
            return value[0]
        return value

    def fetchall(self):
        value = self.responses.get(self.current, [])
        return value


class FakeOperationalError(Exception):
    def __init__(self, message, sqlstate):
        self.sqlstate = sqlstate
        super().__init__(message)


class FakeConnection:
    def __init__(self, responses, fail_on=None):
        self.cur = FakeCursor(responses, fail_on)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.cur


def basic_responses(access=(True, False, True, True, True, True, True)):
    return {
        "access": [access],
        "read_at": [(datetime(2026, 11, 24, tzinfo=UTC),)],
        "capacity": [(1200, 600)],
        "rows": [],
        "missed": [],
        "sizes": [],
        "capacity_body": [("authored body",)],
    }


def test_measure_statement_order_and_rollback_on_success():
    conn = FakeConnection(basic_responses())
    exp09.measure(lambda: conn, datetime(2026, 11, 24, tzinfo=UTC), "a" * 40, "authored body")
    assert conn.cur.executed == [exp09.SQL[key] for key in (
        "begin", "timeout", "lock_timeout", "row_security", "timezone", "access",
        "read_at", "capacity", "rows", "missed", "sizes", "capacity_body", "rollback",
    )]
    assert all(not re.search(r"\bCOMMIT\b", sql, re.IGNORECASE)
               for sql in exp09.SQL.values())


@pytest.mark.parametrize("false_index", range(7))
def test_no_read_path_rolls_back_and_carries_only_access_booleans(false_index):
    access = [False, False, True, True, True, True, True]
    access[false_index] = False
    conn = FakeConnection(basic_responses(tuple(access)))
    with pytest.raises(exp09.Refused) as caught:
        exp09.measure(lambda: conn, datetime(2026, 11, 24, tzinfo=UTC), "a" * 40, "")
    assert caught.value.code == "NO_READ_PATH"
    assert caught.value.access == tuple(access)
    assert conn.cur.executed[-1] == exp09.SQL["rollback"]
    assert exp09.SQL["read_at"] not in conn.cur.executed


def test_mid_read_exception_rolls_back_and_cli_sanitizes_error(capsys):
    conn = FakeConnection(basic_responses(), fail_on="rows")
    with pytest.raises(FakeOperationalError):
        exp09.measure(lambda: conn, datetime(2026, 11, 24, tzinfo=UTC), "a" * 40, "")
    assert conn.cur.executed[-1] == exp09.SQL["rollback"]
    failure = FakeOperationalError("db.example.supabase.co " + "b" * 40, "XX001")
    with patch.object(exp09, "parse_as_of", return_value=datetime(2026, 11, 24, tzinfo=UTC)), \
            patch.object(exp09, "measure", side_effect=failure):
        code = exp09.main(
            ["--mode", "rehearse", "--as-of", "2026-11-24T00:00:00Z"],
            environ={"NG4_PILOT_EXP09_REHEARSAL_URL": "postgresql://localhost/test"},
        )
    output = capsys.readouterr().out
    assert code == 1
    assert "db.example.supabase.co" not in output and "b" * 40 not in output
    assert '"sqlstate": "XX001"' in output


def test_sql_ast_and_identifier_allowlist():
    tree = ast.parse((ROOT / "scripts/ng4_pilot_exp09.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "execute":
            arg = node.args[0]
            assert isinstance(arg, ast.Subscript)
            assert isinstance(arg.value, ast.Name) and arg.value.id == "SQL"
            assert isinstance(arg.slice, ast.Constant) and isinstance(arg.slice.value, str)
    allowed = set("""SELECT SET TRANSACTION ISOLATION LEVEL REPEATABLE READ ONLY LOCAL
        statement_timeout lock_timeout row_security off TimeZone UTC coalesce current_user
            FROM WHERE JOIN LEFT ON AND IN AS false true ROLLBACK ucpe_lattice pg_catalog
            pg_class pg_namespace pg_roles
        pg_proc oid relname relnamespace rolname rolsuper rolbypassrls proname pronamespace
        prosrc nspname id has_schema_privilege has_table_privilege statement_timestamp
        lattice_rows lattice_commit_receipts lattice_missed_instants lattice_capacity
        lattice_instant_utc issued_at_utc db_insert_clock_utc timeframe normalized_symbol
        reference_venue evidence_use evaluation_population lattice_row_id commit_state reason
        logged_at_db_clock max_rows warn_rows pg_total_relation_size pg_relation_size
        pg_indexes_size""".split())
    for query in exp09.SQL.values():
        no_literals = re.sub(r"'(?:''|[^'])*'", " ", query)
        identifiers = re.findall(r"[A-Za-z_][A-Za-z_0-9]*", no_literals)
        assert set(identifiers) <= allowed
        assert not re.search(
            r"\b(pg_stats|pg_statistic|pg_stats_ext|pg_statistic_ext_data|pg_stat_activity|"
            r"pg_stat_statements|get_raw_page|pgstattuple|pg_read_file|pg_read_binary_file|"
            r"lo_|dblink|COPY|TABLE|pg_column_size|octet_length|to_json|json_agg|jsonb_agg|"
            r"hstore|ROW\()\b", query, re.IGNORECASE,
        )
        assert not re.search(
            r"\b(?:FROM|JOIN)\s+(?:ucpe_lattice\.)?[a-z_][a-z0-9_]*\s+"
            r"(?!WHERE\b|JOIN\b|ON\b|LEFT\b|AND\b)[a-z_][a-z0-9_]*\b",
            query, re.IGNORECASE,
        )
        assert query.count("*") == query.upper().count("COUNT(*)")


def test_authored_body_is_exact_capacity_function_body():
    body = exp09.authored_capacity_body(ROOT)
    assert "v_used >= v_max" in body
    assert body.startswith("\nDECLARE")


def test_measure_sections_counts_timing_capacity_and_foreign_rows():
    base = basic_responses()
    start = exp09.PILOT_START_UTC
    as_of = start + timedelta(hours=3)
    def row(tf, symbol, venue, minute, issued_seconds, store_seconds, state):
        instant_value = start + timedelta(minutes=minute)
        issued = instant_value + timedelta(seconds=issued_seconds)
        inserted = issued + timedelta(seconds=store_seconds)
        return (tf, symbol, venue, instant_value, issued, inserted,
                "TEST_ONLY", "E1_OPERATIONAL", state)
    base["rows"] = [
        row("15m", exp09.PILOT_NORMALIZED_SYMBOL, exp09.PILOT_REFERENCE_VENUE,
            0, 0, 1, "COMMITTED"),
        row("15m", exp09.PILOT_NORMALIZED_SYMBOL, exp09.PILOT_REFERENCE_VENUE,
            45, 10, 2, "COMMIT_UNKNOWN"),
        row("15m", exp09.PILOT_NORMALIZED_SYMBOL, exp09.PILOT_REFERENCE_VENUE,
            135, 20, 3, None),
        row("15m", exp09.PILOT_NORMALIZED_SYMBOL, exp09.PILOT_REFERENCE_VENUE,
            195, 4, 1, None),
        row("15m", "ETH/USDT", exp09.PILOT_REFERENCE_VENUE, 0, 1, 1, None),
        row("2H", exp09.PILOT_NORMALIZED_SYMBOL, exp09.PILOT_REFERENCE_VENUE,
            0, 1, 1, None),
    ]
    base["missed"] = [
        ("15m", exp09.PILOT_NORMALIZED_SYMBOL, exp09.PILOT_REFERENCE_VENUE,
         start + timedelta(minutes=90), "NOT_ISSUED", start + timedelta(minutes=91)),
        ("15m", exp09.PILOT_NORMALIZED_SYMBOL, exp09.PILOT_REFERENCE_VENUE,
         start + timedelta(minutes=120), "NEW_REASON", start + timedelta(minutes=121)),
        ("15m", "ETH/USDT", exp09.PILOT_REFERENCE_VENUE,
         start, "NOT_ISSUED", start),
    ]
    base["sizes"] = [
        ("lattice_rows", 300, 200, 100),
        ("lattice_commit_receipts", 120, 80, 40),
        ("lattice_missed_instants", 50, 40, 10),
        ("lattice_capacity", 20, 16, 4),
    ]
    conn = FakeConnection(base)
    report = exp09.measure(lambda: conn, as_of, "a" * 40, "different body")
    assert report["rows"]["15m"] == {
        "in_window": 3, "after_as_of": 1, "outside_pilot_window": 0,
        "first": "2026-11-23T00:00:00Z", "last": "2026-11-23T02:15:00Z",
        "non_test_only": 0,
        "receipts": {"COMMITTED": 1, "COMMIT_UNKNOWN": 1, "NONE": 1},
    }
    assert report["foreign_cell_rows"] == 1
    assert report["unexpected_timeframe_rows"] == {"<unexpected>": 1}
    assert report["missed"]["15m"] == {"NOT_ISSUED": 1, "<unexpected>": 1}
    assert report["foreign_cell_missed"] == 1
    assert report["timing"]["15m"]["issued_after_lattice_seconds"] == {
        "n": 3, "min": 0, "p50": 10.0, "p95": 19.0, "max": 20,
    }
    assert report["timing"]["15m"]["store_latency_plus_clock_offset_seconds"] == {
        "n": 3, "min": 1, "p50": 2.0, "p95": 2.9, "max": 3,
    }
    assert report["completeness"]["15m"]["planned"] == 4
    assert report["completeness"]["15m"]["issued_on_grid"] == 3
    assert report["completeness"]["15m"]["missed_on_grid"] == 1
    assert report["late_writes"]["rows"] == 1
    assert report["occupancy"]["all_time_rows"] == 6
    assert report["occupancy"]["all_time_receipts"] == 2
    assert report["occupancy"]["bytes_per_row_estimate"] == 70
    assert report["capacity"]["capacity_function_body_matches_authored"] is False
    conn = FakeConnection({**base, "capacity_body": [("authored body",)]})
    report = exp09.measure(lambda: conn, as_of, "a" * 40, "authored body")
    assert report["capacity"]["capacity_function_body_matches_authored"] is True


def test_rehearse_url_refusals_and_dispatch_workflow_constant(capsys):
    assert exp09.WORKFLOW == ".github/workflows/ng4-pilot-exp09.yml"
    with patch.object(exp09, "parse_as_of", return_value=datetime(2026, 11, 24, tzinfo=UTC)):
        assert exp09.main(
            ["--mode", "rehearse", "--as-of", "2026-11-24T00:00:00Z"],
            environ={"SUPABASE_DB_URL": "set", "NG4_PILOT_EXP09_REHEARSAL_URL":
                     "postgresql://localhost/test"},
        ) == 2
        assert exp09.main(
            ["--mode", "rehearse", "--as-of", "2026-11-24T00:00:00Z"],
            environ={"NG4_PILOT_EXP09_REHEARSAL_URL": "postgresql://db.example/test"},
        ) == 2
    report = capsys.readouterr().out
    assert "URL_REFUSED" in report
    assert exp09.main(["--mode", "run", "--expected-sha", "a" * 40], environ={}) == 2


def test_rehearsal_clock_is_rehearse_only_and_validated(capsys):
    clock = "2026-12-07T00:30:00Z"
    with patch.object(exp09, "parse_as_of", wraps=exp09.parse_as_of) as parse:
        assert exp09.main(
            ["--mode", "rehearse", "--as-of", "2026-11-30T00:00:00Z"],
            environ={"NG4_PILOT_EXP09_REHEARSAL_URL": "postgresql://localhost/test",
                     "NG4_PILOT_EXP09_REHEARSAL_NOW": clock},
        ) == 1
        assert parse.call_args.args[1] == datetime(2026, 12, 7, 0, 30, tzinfo=UTC)
    for mode in ("attest", "run"):
        assert exp09.main(["--mode", mode], environ={
            "NG4_PILOT_EXP09_REHEARSAL_NOW": clock,
        }) == 2
    assert exp09.main(
        ["--mode", "rehearse", "--as-of", "2026-11-30T00:00:00Z"],
        environ={"NG4_PILOT_EXP09_REHEARSAL_URL": "postgresql://localhost/test",
                 "NG4_PILOT_EXP09_REHEARSAL_NOW": "2026-12-07T00:30:01Z"},
    ) == 2
    assert "REHEARSAL_NOW_REFUSED" in capsys.readouterr().out


def test_rehearse_cli_fake_driver_deterministic_except_read_timestamp(capsys):
    class Driver:
        calls = 0

        @classmethod
        def connect(cls, *_args, **_kwargs):
            cls.calls += 1
            responses = basic_responses()
            responses["read_at"] = [(datetime(2026, 11, 30, 0, cls.calls, tzinfo=UTC),)]
            return FakeConnection(responses)

    env = {"NG4_PILOT_EXP09_REHEARSAL_URL": "postgresql://localhost/test",
           "NG4_PILOT_EXP09_REHEARSAL_NOW": "2026-12-07T00:30:00Z"}
    with patch.object(exp09, "load_driver", return_value=Driver):
        outputs = []
        for _ in range(2):
            assert exp09.main(["--mode", "rehearse", "--as-of", "2026-11-30T00:00:00Z"],
                              environ=env) == 0
            outputs.append(capsys.readouterr().out)
    left, right = [__import__("json").loads(value) for value in outputs]
    left.pop("read_at_db_utc")
    right.pop("read_at_db_utc")
    assert __import__("json").dumps(left) == __import__("json").dumps(right)
