"""W26 (§2.6): the Postgres prediction INSERT names the tc-v1 stamp columns only for stamped rows.

A row whose four stamp values are all present and not None gets exactly four more columns and
placeholders, appended in STAMP_FIELDS order. Every other row, a partial stamp included, gets
today's statement byte for byte, so the OOS arm writer, the derivatives cadence and every
existing test see no change. Synthetic only: a fake cursor, never a database.
"""

from __future__ import annotations

import itertools
import re

import pytest

from crypto_probability_engine.persistence import repository
from crypto_probability_engine.persistence.repository import SupabasePersistenceRepository

# Hardcoded, as in repository.py, which never imports the target contract.
STAMP_COLUMNS = ("target_version", "reference_venue", "core_computed_at_utc", "issued_at_utc")
STAMP = {
    "target_version": "tc-v1",
    "reference_venue": "BINANCE_PUBLIC",
    "core_computed_at_utc": "2026-09-28T00:00:42.750000Z",
    "issued_at_utc": "2026-09-28T00:00:43.100000Z",
}
DO_NOTHING = "ON CONFLICT (prediction_id) DO NOTHING"
OOS_ARM_ID = "oosb-" + "0123456789abcdef" * 2 + ":4H:BASELINE"
TODAY_COLUMNS = (
    "prediction_id",
    "run_id",
    "operator_id",
    "symbol",
    "normalized_symbol",
    "timeframe",
    "horizon_bars",
    "predicted_at_utc",
    "reference_close_utc",
    "reference_price",
    "horizon_end_utc",
    "p_up_frac",
    "p_down_frac",
    "p_timeout_frac",
    "decision_band_frac",
    "model_version",
    "methodology_version",
    "calibration_status",
    "reliability_status",
    "epistemic_sufficiency",
    "gate_action",
    "data_source",
    "is_live_data",
    "cross_provider_state",
    "prediction_origin",
)
PARTIAL_STAMPS = [
    subset
    for size in range(1, len(STAMP_COLUMNS))
    for subset in itertools.combinations(STAMP_COLUMNS, size)
]


def _golden_sql(conflict_clause: str) -> str:
    """Today's statement, copied verbatim from main b11a8e53. Never derive it from the code."""

    return f"""
        INSERT INTO predictions (
          prediction_id, run_id, operator_id, symbol, normalized_symbol,
          timeframe, horizon_bars, predicted_at_utc, reference_close_utc,
          reference_price, horizon_end_utc, p_up_frac, p_down_frac,
          p_timeout_frac, decision_band_frac, model_version, methodology_version,
          calibration_status, reliability_status, epistemic_sufficiency,
          gate_action, data_source, is_live_data, cross_provider_state,
          prediction_origin
        )
        VALUES (
          %(prediction_id)s, %(run_id)s, %(operator_id)s, %(symbol)s,
          %(normalized_symbol)s, %(timeframe)s, %(horizon_bars)s,
          %(predicted_at_utc)s, %(reference_close_utc)s, %(reference_price)s,
          %(horizon_end_utc)s, %(p_up_frac)s, %(p_down_frac)s,
          %(p_timeout_frac)s, %(decision_band_frac)s, %(model_version)s,
          %(methodology_version)s, %(calibration_status)s,
          %(reliability_status)s, %(epistemic_sufficiency)s, %(gate_action)s,
          %(data_source)s, %(is_live_data)s, %(cross_provider_state)s,
          %(prediction_origin)s
        )
        {conflict_clause}
        """


COLUMN_FRAGMENT = "".join(f", {name}" for name in STAMP_COLUMNS)
VALUE_FRAGMENT = "".join(f", %({name})s" for name in STAMP_COLUMNS)


def _stamped_sql(conflict_clause: str) -> str:
    """The golden statement with the four columns and placeholders appended, and nothing else."""

    golden = _golden_sql(conflict_clause)
    column_line = "\n          prediction_origin\n"
    value_line = "\n          %(prediction_origin)s\n"
    assert golden.count(column_line) == 1
    assert golden.count(value_line) == 1
    return golden.replace(
        column_line, f"\n          prediction_origin{COLUMN_FRAGMENT}\n"
    ).replace(value_line, f"\n          %(prediction_origin)s{VALUE_FRAGMENT}\n")


class _Cursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def execute(self, statement, params=None) -> None:
        self.calls.append((str(statement), params))


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def cursor(self) -> _Cursor:
        return self._cursor


class _Pool:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def connection(self, timeout=None) -> _Connection:
        return _Connection(self._cursor)


def _row(**extra: object) -> dict:
    row = {
        "prediction_id": "run_w26:4H",
        "run_id": "run_w26",
        "operator_id": "operator",
        "symbol": "BTC",
        "normalized_symbol": "BTC/USDT",
        "timeframe": "4H",
        "horizon_bars": 6,
        "predicted_at_utc": "2026-09-28T00:00:41.250000Z",
        "reference_close_utc": "2026-09-28T00:00:00Z",
        "reference_price": 64_250.5,
        "horizon_end_utc": "2026-09-29T00:00:00Z",
        "p_up_frac": 0.40,
        "p_down_frac": 0.35,
        "p_timeout_frac": 0.25,
        "decision_band_frac": 0.003,
        "model_version": "phase1a-wave4b0",
        "methodology_version": "heuristic-v1-wave4b0",
        "calibration_status": "DEFAULT_PHASE1A",
        "reliability_status": "INSUFFICIENT_SAMPLE",
        "epistemic_sufficiency": "SUFFICIENT",
        "gate_action": "WATCH",
        "data_source": "BINANCE_PUBLIC",
        "is_live_data": True,
        "cross_provider_state": "UNAVAILABLE",
        "prediction_origin": "USER_REQUESTED",
    }
    row.update(extra)
    return row


def _insert(row: dict, *, reject_conflict: bool) -> tuple[str, object]:
    cursor = _Cursor()
    repository._insert_prediction(cursor, row, reject_conflict=reject_conflict)
    assert len(cursor.calls) == 1
    return cursor.calls[0]


def _named_lists(statement: str) -> tuple[list[str], list[str]]:
    """The column list and the VALUES list; each closes with ")" on its own line."""

    match = re.search(
        r"INSERT INTO predictions \((?P<columns>.*?)\n\s*\)\s*"
        r"VALUES \((?P<values>.*?)\n\s*\)\s*\n",
        statement,
        re.DOTALL,
    )
    assert match is not None
    columns = [name.strip() for name in match["columns"].split(",")]
    values = [value.strip() for value in match["values"].split(",")]
    return columns, values


@pytest.mark.parametrize("reject_conflict", [False, True])
def test_an_unstamped_row_gets_todays_statement_byte_for_byte(reject_conflict: bool) -> None:
    row = _row()
    statement, params = _insert(row, reject_conflict=reject_conflict)

    assert statement == _golden_sql("" if reject_conflict else DO_NOTHING)
    assert params == row


@pytest.mark.parametrize("reject_conflict", [False, True])
@pytest.mark.parametrize("present", PARTIAL_STAMPS, ids="+".join)
def test_a_partial_stamp_gets_todays_statement_byte_for_byte(
    present: tuple[str, ...], reject_conflict: bool
) -> None:
    row = _row(**{name: STAMP[name] for name in present})
    statement, params = _insert(row, reject_conflict=reject_conflict)

    assert statement == _golden_sql("" if reject_conflict else DO_NOTHING)
    # The keys still travel in params exactly as today; no placeholder names them.
    assert params == row


@pytest.mark.parametrize("reject_conflict", [False, True])
@pytest.mark.parametrize("nulls", PARTIAL_STAMPS + [STAMP_COLUMNS], ids="+".join)
def test_a_stamp_with_any_none_value_gets_todays_statement_byte_for_byte(
    nulls: tuple[str, ...], reject_conflict: bool
) -> None:
    row = _row(**{**STAMP, **dict.fromkeys(nulls)})
    statement, params = _insert(row, reject_conflict=reject_conflict)

    assert statement == _golden_sql("" if reject_conflict else DO_NOTHING)
    assert params == row


@pytest.mark.parametrize("reject_conflict", [False, True])
def test_a_stamped_row_gets_exactly_four_more_columns_and_values(reject_conflict: bool) -> None:
    row = _row(**STAMP)
    statement, params = _insert(row, reject_conflict=reject_conflict)
    clause = "" if reject_conflict else DO_NOTHING

    assert statement == _stamped_sql(clause)
    assert statement.replace(COLUMN_FRAGMENT, "").replace(VALUE_FRAGMENT, "") == _golden_sql(
        clause
    )
    columns, values = _named_lists(statement)
    assert columns == [*TODAY_COLUMNS, *STAMP_COLUMNS]
    assert values == [f"%({name})s" for name in columns]
    assert params == row
    assert [params[name] for name in STAMP_COLUMNS] == [STAMP[name] for name in STAMP_COLUMNS]


def test_the_golden_statement_names_todays_twenty_five_columns() -> None:
    columns, values = _named_lists(_golden_sql(DO_NOTHING))

    assert columns == list(TODAY_COLUMNS)
    assert values == [f"%({name})s" for name in TODAY_COLUMNS]


def test_the_postgres_writer_routes_live_and_oos_rows_through_the_same_rule() -> None:
    cursor = _Cursor()
    repo = SupabasePersistenceRepository(
        "postgresql://example.invalid/db",
        pool_factory=lambda: _Pool(cursor),
    )

    assert repo.save_prediction(_row()) == "OK"
    assert cursor.calls[-1] == (_golden_sql(DO_NOTHING), _row())

    stamped = _row(prediction_id="run_w26s:4H", run_id="run_w26s", **STAMP)
    assert repo.save_prediction(stamped) == "OK"
    assert cursor.calls[-1] == (_stamped_sql(DO_NOTHING), stamped)

    oos_arm = _row(
        prediction_id=OOS_ARM_ID,
        run_id=OOS_ARM_ID.split(":")[0],
        prediction_origin="SCHEDULED_SHADOW_EVIDENCE",
    )
    assert repo.save_prediction(oos_arm) == "OK"
    # The OOS arm path (reject_conflict=True): today's statement, no conflict clause.
    assert cursor.calls[-1] == (_golden_sql(""), oos_arm)
