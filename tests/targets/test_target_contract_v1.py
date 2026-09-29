"""Target contract v1 (tc-v1): stamping, validation and legacy classification. Synthetic only."""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterator, Mapping
from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pytest

from crypto_probability_engine.adapters.provider_selection import DATA_SOURCE_BY_PROVIDER
from crypto_probability_engine.api import analysis_service
from crypto_probability_engine.config.defaults import DEFAULT_PHASE1A, TIMEFRAME_SECONDS
from crypto_probability_engine.oos.evaluation import evaluator_pin
from crypto_probability_engine.targets import contract_v1 as tc
from scripts import resolve_outcomes

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "src" / "crypto_probability_engine"
TARGETS = PACKAGE / "targets"

# Monday 00:00 UTC: a closed bar boundary for every tc-v1 timeframe, 1W included.
REFERENCE_CLOSE = datetime(2026, 9, 28, tzinfo=UTC)
AS_OF = REFERENCE_CLOSE + timedelta(seconds=41, microseconds=250_000)
CORE_DONE = AS_OF + timedelta(seconds=1, microseconds=500_000)
ISSUED = CORE_DONE + timedelta(milliseconds=350)
TC_TIMEFRAMES = ("15m", "1H", "4H", "1D", "1W")
OOS_RUN = "oosb-" + "0123456789abcdef" * 2
TIMESTAMP_FIELDS = (
    "reference_close_utc",
    "predicted_at_utc",
    "core_computed_at_utc",
    "issued_at_utc",
    "horizon_end_utc",
)
NULL_STAMP = dict.fromkeys(tc.STAMP_FIELDS)
_iso = analysis_service._iso_utc  # the writer's own timestamp format


def _row(timeframe: str = "4H", **overrides: object) -> dict:
    """A live USER_REQUESTED row shaped like api/analysis_service.py::_prediction_row output."""

    horizon_end = REFERENCE_CLOSE + timedelta(seconds=6 * TIMEFRAME_SECONDS[timeframe])
    row = {
        "prediction_id": f"run_{'c' * 32}:{timeframe}",
        "run_id": f"run_{'c' * 32}",
        "operator_id": "operator",
        "symbol": "BTCUSDT",
        "normalized_symbol": "BTC/USDT",
        "timeframe": timeframe,
        "horizon_bars": 6,
        "predicted_at_utc": _iso(AS_OF),
        "reference_close_utc": _iso(REFERENCE_CLOSE),
        "reference_price": 64_250.5,
        "horizon_end_utc": _iso(horizon_end),
        "p_up_frac": 0.35,
        "p_down_frac": 0.25,
        "p_timeout_frac": 0.40,
        "decision_band_frac": 0.0023,
        "model_version": "phase1a-wave4b0",
        "methodology_version": "heuristic-v1-wave4b0",
        "calibration_status": "DEFAULT_PHASE1A",
        "reliability_status": "INSUFFICIENT_SAMPLE",
        "epistemic_sufficiency": "SUFFICIENT",
        "gate_action": "ALLOW",
        "data_source": "BINANCE_PUBLIC",
        "is_live_data": True,
        "cross_provider_state": "UNAVAILABLE",
        "prediction_origin": "USER_REQUESTED",
    }
    row.update(overrides)
    return row


def _stamp(
    row: object,
    provider: object = "binance",
    *,
    core: object = CORE_DONE,
    issued: object = ISSUED,
) -> dict:
    return tc.stamp_v1(row, snapshot_provider=provider, core_computed_at=core, issued_at=issued)


def _candidate(
    row: dict,
    venue: str = "BINANCE_PUBLIC",
    *,
    core: datetime = CORE_DONE,
    issued: datetime = ISSUED,
) -> dict:
    """What stamping would produce without its validity gate, to read the violations."""

    return {
        **row,
        "target_version": "tc-v1",
        "reference_venue": venue,
        "core_computed_at_utc": _iso(core),
        "issued_at_utc": _iso(issued),
    }


class _UnreadableRow(Mapping):
    def __getitem__(self, key: str) -> object:
        raise RuntimeError("unreadable row")

    def __iter__(self) -> Iterator[str]:
        return iter(("prediction_id",))

    def __len__(self) -> int:
        return 1


# --------------------------------------------------------------------------- valid stamping


@pytest.mark.parametrize("timeframe", TC_TIMEFRAMES)
def test_a_valid_row_is_stamped_for_every_tc_v1_timeframe(timeframe: str) -> None:
    row = _row(timeframe)
    stamped = _stamp(row)
    assert stamped == {
        **row,
        "target_version": "tc-v1",
        "reference_venue": "BINANCE_PUBLIC",
        "core_computed_at_utc": _iso(CORE_DONE),
        "issued_at_utc": _iso(ISSUED),
    }
    assert list(stamped) == [*row, *tc.STAMP_FIELDS]
    assert tc.validate_v1(stamped) == ()
    assert tc.classify_row(stamped) == "tc-v1"
    assert tc.resolution_venue(stamped) == "BINANCE_PUBLIC"


@pytest.mark.parametrize(
    ("provider", "data_source", "state", "venue"),
    [
        ("binance", "BINANCE_PUBLIC", "UNAVAILABLE", "BINANCE_PUBLIC"),
        ("okx", "OKX_PUBLIC", "UNAVAILABLE", "OKX_PUBLIC"),
        ("binance", "BINANCE_PUBLIC", "DATA_CONFLICT", "BINANCE_PUBLIC"),
        ("okx", "OKX_PUBLIC", "DATA_CONFLICT", "OKX_PUBLIC"),
        ("binance", "CROSS_PROVIDER", "COHERENT", "BINANCE_PUBLIC"),
        ("okx", "CROSS_PROVIDER", "COHERENT", "OKX_PUBLIC"),
    ],
    ids=[
        "binance-single",
        "okx-single",
        "binance-conflict-fallback",
        "okx-conflict-fallback",
        "cross-provider-binance",
        "cross-provider-okx",
    ],
)
def test_reference_venue_is_the_snapshot_provider(
    provider: str, data_source: str, state: str, venue: str
) -> None:
    stamped = _stamp(_row(data_source=data_source, cross_provider_state=state), provider)
    assert stamped["reference_venue"] == venue
    assert stamped["data_source"] == data_source
    assert tc.validate_v1(stamped) == ()
    assert tc.resolution_venue(stamped) == venue


@pytest.mark.parametrize("origin", ["CONTROLLED_SMOKE", "ABSENT"])
def test_other_non_oos_origins_are_stamped(origin: str) -> None:
    row = _row(prediction_origin=origin)
    if origin == "ABSENT":
        del row["prediction_origin"]  # the resolver's due query does not select it
    assert tc.validate_v1(_stamp(row)) == ()


def test_equal_instants_satisfy_the_chronology() -> None:
    row = _row(predicted_at_utc=_iso(REFERENCE_CLOSE))
    stamped = _stamp(row, core=REFERENCE_CLOSE, issued=REFERENCE_CLOSE)
    assert tc.validate_v1(stamped) == ()
    assert stamped["core_computed_at_utc"] == stamped["issued_at_utc"] == row["reference_close_utc"]


@pytest.mark.parametrize("created_at", ["2000-01-01T00:00:00Z", "2099-01-01T00:00:00Z"])
def test_the_database_commit_clock_is_never_checked(created_at: str) -> None:
    assert tc.validate_v1(_stamp(_row(created_at=created_at))) == ()


@pytest.mark.parametrize("bars", [1, 96])
def test_horizon_bar_bounds_are_inclusive(bars: int) -> None:
    horizon_end = REFERENCE_CLOSE + timedelta(minutes=15 * bars)
    row = _row("15m", horizon_bars=bars, horizon_end_utc=_iso(horizon_end))
    assert tc.validate_v1(_stamp(row)) == ()


def test_band_zero_and_probability_tolerance_are_accepted() -> None:
    assert tc.validate_v1(_stamp(_row(decision_band_frac=0.0))) == ()
    assert tc.validate_v1(_stamp(_row(p_timeout_frac=0.40 + 5e-10))) == ()


def test_stamp_times_use_the_writer_iso_format() -> None:
    naive = datetime(2026, 9, 28, 0, 0, 43)  # naive means UTC, as in the writer
    offset = datetime(2026, 9, 28, 7, 0, 43, 5, tzinfo=timezone(timedelta(hours=7)))
    stamped = _stamp(_row(), core=naive, issued=offset)
    assert stamped["core_computed_at_utc"] == _iso(naive) == "2026-09-28T00:00:43Z"
    assert stamped["issued_at_utc"] == _iso(offset) == "2026-09-28T00:00:43.000005Z"
    from_strings = _stamp(_row(), core="2026-09-28T07:00:43+07:00", issued="2026-09-28T00:00:44Z")
    assert from_strings["core_computed_at_utc"] == "2026-09-28T00:00:43Z"
    assert from_strings["issued_at_utc"] == "2026-09-28T00:00:44Z"


def test_database_shaped_rows_validate_like_writer_rows() -> None:
    stamped = _stamp(_row())
    database_row = {
        key: Decimal(repr(value)) if isinstance(value, float) else value
        for key, value in stamped.items()
    }
    for field in TIMESTAMP_FIELDS:
        database_row[field] = datetime.fromisoformat(
            stamped[field].replace("Z", "+00:00")
        ).isoformat()  # "+00:00", as persistence/repository.py returns due rows
    del database_row["prediction_origin"]
    assert tc.validate_v1(database_row) == ()
    assert tc.resolution_venue(database_row) == "BINANCE_PUBLIC"
    as_datetimes = {
        **database_row,
        **{field: datetime.fromisoformat(database_row[field]) for field in TIMESTAMP_FIELDS},
    }
    assert tc.validate_v1(as_datetimes) == ()


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        (
            {
                "p_up_frac": Decimal("1.00000000000000000001"),
                "p_down_frac": Decimal("0"),
                "p_timeout_frac": Decimal("0"),
            },
            tc.I5_PROBABILITY_INVALID,
        ),
        (
            {
                "p_up_frac": Decimal("-1E-400"),
                "p_down_frac": Decimal("0.5"),
                "p_timeout_frac": Decimal("0.5"),
            },
            tc.I5_PROBABILITY_INVALID,
        ),
        ({"p_up_frac": Decimal("NaN")}, tc.I5_PROBABILITY_INVALID),
        ({"decision_band_frac": Decimal("-1E-400")}, tc.BAND_INVALID),
        ({"reference_price": Decimal("0E-10")}, tc.REFERENCE_PRICE_INVALID),
        ({"reference_price": Decimal("NaN")}, tc.REFERENCE_PRICE_INVALID),
    ],
)
def test_decimal_bounds_are_checked_exactly(overrides: dict, code: str) -> None:
    # Postgres NUMERIC columns arrive as Decimal. Converting to float first would round these
    # out-of-bounds values onto a bound (1.0 or -0.0) and let them through.
    row = _row(**overrides)
    assert code in tc.validate_v1(_candidate(row))
    assert _stamp(row) == row


def test_contract_and_timestamps_are_built_from_a_valid_row() -> None:
    row = _row("1H", data_source="CROSS_PROVIDER", cross_provider_state="COHERENT")
    stamped = _stamp(row, "okx")
    horizon_end = REFERENCE_CLOSE + timedelta(hours=6)
    contract = tc.TargetContractV1.from_row(stamped)
    assert contract == tc.TargetContractV1(
        target_version="tc-v1",
        normalized_symbol="BTC/USDT",
        timeframe="1H",
        reference_venue="OKX_PUBLIC",
        reference_close_utc=REFERENCE_CLOSE,
        reference_price=64_250.5,
        horizon_bars=6,
        horizon_end_utc=horizon_end,
        band_frac=0.0023,
    )
    assert (contract.band_units, contract.label_rule, contract.resolution_rule) == (
        "FRACTION_OF_REFERENCE_PRICE",
        "TERMINAL_CLOSE_VS_BAND_3STATE",
        "EXACT_TERMINAL_BAR_SAME_VENUE",
    )
    with pytest.raises(FrozenInstanceError):
        contract.horizon_bars = 7  # type: ignore[misc]
    timestamps = tc.ForecastTimestampsV1.from_row(stamped)
    assert timestamps == tc.ForecastTimestampsV1(
        source_as_of_utc=AS_OF,
        candle_cutoff_utc=REFERENCE_CLOSE,
        overall_cutoff_utc=AS_OF,
        core_computed_at_utc=CORE_DONE,
        issued_at_utc=ISSUED,
        remaining_duration_at_issue=horizon_end - ISSUED,
    )
    # Close-anchored: the time left at issue is shorter than the nominal six bars.
    assert timedelta(0) < timestamps.remaining_duration_at_issue < timedelta(hours=6)
    assert tc.TargetContractV1.from_row(row) is None
    assert tc.ForecastTimestampsV1.from_row(row) is None
    assert tc.TargetContractV1.from_row(None) is None  # type: ignore[arg-type]


# --------------------------------------------------------------------------- fail closed


def test_monthly_rows_fail_closed() -> None:
    assert "1M" in DEFAULT_PHASE1A.timeframes and "1M" in TIMEFRAME_SECONDS
    row = _row("1M")  # horizon from the approximate 30-day bar
    assert _stamp(row) == row
    assert tc.validate_v1(_candidate(row)) == (tc.I9_TIMEFRAME_UNSUPPORTED,)


@pytest.mark.parametrize(
    "provider",
    ["bybit", "Binance", "OKX", "BINANCE_PUBLIC", "cross_provider", "fixture", "", None],
)
def test_an_unknown_provider_is_never_guessed(provider: object) -> None:
    # "cross_provider" is provider_state.active_provider for coherent rows, not snapshot.provider.
    row = _row(data_source="CROSS_PROVIDER", cross_provider_state="COHERENT")
    assert _stamp(row, provider) == row


@pytest.mark.parametrize(
    ("overrides", "codes"),
    [
        (
            {
                "prediction_id": f"{OOS_RUN}:4H:BASELINE",
                "run_id": OOS_RUN,
                "prediction_origin": "SCHEDULED_SHADOW_EVIDENCE",
            },
            (tc.OOS_ARM_ROW, tc.SHADOW_EVIDENCE_ROW),
        ),
        (
            {
                "prediction_id": f"{OOS_RUN}:4H:CANDIDATE",
                "run_id": OOS_RUN,
                "prediction_origin": "SCHEDULED_SHADOW_EVIDENCE",
            },
            (tc.OOS_ARM_ROW, tc.SHADOW_EVIDENCE_ROW),
        ),
        ({"prediction_id": f"{OOS_RUN}:4H:BASELINE"}, (tc.OOS_ARM_ROW,)),
        ({"run_id": OOS_RUN}, (tc.OOS_ARM_ROW,)),
        ({"prediction_origin": "SCHEDULED_SHADOW_EVIDENCE"}, (tc.SHADOW_EVIDENCE_ROW,)),
    ],
    ids=["baseline-arm", "candidate-arm", "arm-id-only", "oos-run-only", "shadow-origin-only"],
)
def test_the_oos_population_is_never_stamped(overrides: dict, codes: tuple[str, ...]) -> None:
    row = _row(**overrides)
    assert _stamp(row) == row
    assert tc.validate_v1(_candidate(row)) == codes


@pytest.mark.parametrize(
    "state", ["DATA_CONFLICT", "UNAVAILABLE", "NOT_REQUIRED", "coherent", None]
)
def test_cross_provider_rows_need_a_coherent_state(state: object) -> None:
    row = _row(data_source="CROSS_PROVIDER", cross_provider_state=state)
    assert _stamp(row) == row
    assert tc.validate_v1(_candidate(row)) == (tc.I8_CROSS_PROVIDER_NOT_COHERENT,)


@pytest.mark.parametrize(
    ("data_source", "provider"), [("OKX_PUBLIC", "binance"), ("BINANCE_PUBLIC", "okx")]
)
def test_a_venue_mismatch_is_never_stamped(data_source: str, provider: str) -> None:
    row = _row(data_source=data_source)
    assert _stamp(row, provider) == row
    candidate = _candidate(row, tc.VENUE_LABELS[provider])
    assert tc.validate_v1(candidate) == (tc.I8_DATA_SOURCE_VENUE_MISMATCH,)


def test_reference_venue_is_always_one_venue() -> None:
    coherent = _row(data_source="CROSS_PROVIDER", cross_provider_state="COHERENT")
    assert tc.validate_v1(_candidate(coherent, "CROSS_PROVIDER")) == (
        tc.I8_REFERENCE_VENUE_INVALID,
    )
    assert tc.validate_v1(_candidate(_row(), "BYBIT_PUBLIC")) == (
        tc.I8_REFERENCE_VENUE_INVALID,
        tc.I8_DATA_SOURCE_VENUE_MISMATCH,
    )


@pytest.mark.parametrize(
    ("overrides", "core", "issued", "code"),
    [
        (
            {"predicted_at_utc": _iso(REFERENCE_CLOSE - timedelta(microseconds=1))},
            CORE_DONE,
            ISSUED,
            tc.I1_REFERENCE_CLOSE_AFTER_PREDICTED_AT,
        ),
        ({}, AS_OF - timedelta(microseconds=1), ISSUED, tc.I1_PREDICTED_AT_AFTER_CORE_COMPUTED_AT),
        (
            {},
            CORE_DONE,
            CORE_DONE - timedelta(microseconds=1),
            tc.I1_CORE_COMPUTED_AT_AFTER_ISSUED_AT,
        ),
    ],
    ids=["reference-close-after-as-of", "as-of-after-core", "core-after-issued"],
)
def test_each_chronology_violation_is_refused(
    overrides: dict, core: datetime, issued: datetime, code: str
) -> None:
    row = _row(**overrides)
    assert _stamp(row, core=core, issued=issued) == row
    assert tc.validate_v1(_candidate(row, core=core, issued=issued)) == (code,)


@pytest.mark.parametrize(
    "overrides",
    [
        {"horizon_end_utc": _iso(REFERENCE_CLOSE + timedelta(hours=24, seconds=1))},
        {"horizon_end_utc": _iso(REFERENCE_CLOSE + timedelta(hours=24, seconds=-1))},
        {"horizon_bars": 5},
    ],
    ids=["one-second-late", "one-second-early", "bars-disagree"],
)
def test_horizon_arithmetic_must_be_exact(overrides: dict) -> None:
    row = _row("4H", **overrides)
    assert _stamp(row) == row
    assert tc.validate_v1(_candidate(row)) == (tc.I2_HORIZON_END_MISMATCH,)


@pytest.mark.parametrize("after", [timedelta(0), timedelta(seconds=1)], ids=["equal", "after"])
def test_a_forecast_issued_at_or_after_its_horizon_is_refused(after: timedelta) -> None:
    row = _row("4H")
    issued = REFERENCE_CLOSE + timedelta(hours=24) + after
    assert _stamp(row, issued=issued) == row
    assert tc.validate_v1(_candidate(row, issued=issued)) == (tc.I3_NO_REMAINING_DURATION,)


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"p_timeout_frac": 0.40 + 2e-9}, tc.I5_PROBABILITY_SUM),
        ({"p_up_frac": 0.30}, tc.I5_PROBABILITY_SUM),
        ({"p_up_frac": -0.05, "p_timeout_frac": 0.80}, tc.I5_PROBABILITY_INVALID),
        ({"p_up_frac": 1.2}, tc.I5_PROBABILITY_INVALID),
        ({"p_down_frac": float("nan")}, tc.I5_PROBABILITY_INVALID),
        ({"p_down_frac": None}, tc.I5_PROBABILITY_INVALID),
        ({"p_timeout_frac": True}, tc.I5_PROBABILITY_INVALID),
        ({"p_timeout_frac": "0.40"}, tc.I5_PROBABILITY_INVALID),
    ],
)
def test_the_probability_invariant_is_enforced(overrides: dict, code: str) -> None:
    row = _row(**overrides)
    assert _stamp(row) == row
    assert tc.validate_v1(_candidate(row)) == (code,)


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"reference_price": 0.0}, tc.REFERENCE_PRICE_INVALID),
        ({"reference_price": -1.0}, tc.REFERENCE_PRICE_INVALID),
        ({"reference_price": float("inf")}, tc.REFERENCE_PRICE_INVALID),
        ({"reference_price": float("nan")}, tc.REFERENCE_PRICE_INVALID),
        ({"reference_price": None}, tc.REFERENCE_PRICE_INVALID),
        ({"reference_price": "64250.5"}, tc.REFERENCE_PRICE_INVALID),
        ({"decision_band_frac": -0.001}, tc.BAND_INVALID),
        ({"decision_band_frac": float("nan")}, tc.BAND_INVALID),
        ({"decision_band_frac": None}, tc.BAND_INVALID),
        ({"is_live_data": False}, tc.NOT_LIVE_DATA),
        ({"is_live_data": "true"}, tc.NOT_LIVE_DATA),
        ({"is_live_data": 1}, tc.NOT_LIVE_DATA),
        ({"normalized_symbol": ""}, tc.NORMALIZED_SYMBOL_INVALID),
        ({"normalized_symbol": None}, tc.NORMALIZED_SYMBOL_INVALID),
        ({"timeframe": "1h"}, tc.I9_TIMEFRAME_UNSUPPORTED),
        ({"timeframe": "2H"}, tc.I9_TIMEFRAME_UNSUPPORTED),
        ({"timeframe": None}, tc.I9_TIMEFRAME_UNSUPPORTED),
        ({"horizon_bars": 0}, tc.I9_HORIZON_BARS_OUT_OF_RANGE),
        ({"horizon_bars": 97}, tc.I9_HORIZON_BARS_OUT_OF_RANGE),
        ({"horizon_bars": True}, tc.I9_HORIZON_BARS_OUT_OF_RANGE),
        ({"horizon_bars": 6.0}, tc.I9_HORIZON_BARS_OUT_OF_RANGE),
        ({"horizon_bars": "6"}, tc.I9_HORIZON_BARS_OUT_OF_RANGE),
        ({"predicted_at_utc": "yesterday"}, "PREDICTED_AT_UTC_INVALID"),
        ({"reference_close_utc": None}, "REFERENCE_CLOSE_UTC_INVALID"),
        ({"horizon_end_utc": 1_790_000_000}, "HORIZON_END_UTC_INVALID"),
        ({"data_source": "FIXTURE_DEMO"}, tc.I8_DATA_SOURCE_UNSUPPORTED),
        ({"data_source": "DEGRADED"}, tc.I8_DATA_SOURCE_UNSUPPORTED),
        ({"data_source": "binance_public"}, tc.I8_DATA_SOURCE_UNSUPPORTED),
        ({"data_source": None}, tc.I8_DATA_SOURCE_UNSUPPORTED),
    ],
)
def test_each_field_rule_refuses_the_stamp(overrides: dict, code: str) -> None:
    row = {**_row(), **overrides}
    assert _stamp(row) == row
    assert code in tc.validate_v1(_candidate(row))


# --------------------------------------------------------------------------- immutability


def test_stamping_never_changes_an_original_key_or_mutates_the_input() -> None:
    row = _row()
    original = deepcopy(row)
    stamped = _stamp(row)
    assert row == original
    assert stamped is not row
    assert {key: stamped[key] for key in original} == original
    assert stamped["predicted_at_utc"] == original["predicted_at_utc"] == _iso(AS_OF)
    assert set(stamped) - set(original) == set(tc.STAMP_FIELDS)
    refused = _stamp(row, "bybit")
    assert refused == original and refused is not row
    assert row == original


@pytest.mark.parametrize("value", [None, "tc-v0", "OKX_PUBLIC"])
@pytest.mark.parametrize("field", tc.STAMP_FIELDS)
def test_an_existing_stamp_key_is_never_overwritten(field: str, value: object) -> None:
    row = _row(**{field: value})
    assert _stamp(row) == row


def test_restamping_returns_the_first_stamp_unchanged() -> None:
    stamped = _stamp(_row())
    later = ISSUED + timedelta(seconds=5)
    assert _stamp(stamped, "okx", core=later, issued=later) == stamped


def test_a_read_only_mapping_is_copied_into_a_new_dict() -> None:
    row = _row()
    stamped = _stamp(MappingProxyType(row))
    assert type(stamped) is dict
    assert stamped == _stamp(row)


@pytest.mark.parametrize(
    "row",
    [None, 42, "row", b"row", [("prediction_id", "x")], object(), _UnreadableRow()],
    ids=["none", "int", "str", "bytes", "pairs", "object", "unreadable-mapping"],
)
def test_stamp_v1_returns_an_empty_dict_for_a_row_it_cannot_copy(row: object) -> None:
    assert _stamp(row) == {}
    assert tc.validate_v1(row) in {(tc.ROW_NOT_MAPPING,), (tc.ROW_UNREADABLE,)}
    assert tc.classify_row(row) == "tc-v1-invalid"
    assert tc.resolution_venue(row) is None


GARBAGE_ROWS = [
    {},
    {"timeframe": ["4H"], "horizon_bars": [6], "data_source": {"venue": 1}},
    {"reference_close_utc": 12_345, "p_up_frac": "x", "is_live_data": "yes"},
    {**_row(), "timeframe": ["4H"], "data_source": ["BINANCE_PUBLIC"], "prediction_id": 7},
]
GARBAGE_TIMES = [
    None,
    "",
    "not a time",
    1_700_000_000,
    float("nan"),
    datetime.max.replace(tzinfo=timezone(timedelta(hours=-1))),  # overflows in UTC
]


@pytest.mark.parametrize("row", GARBAGE_ROWS)
def test_stamp_v1_never_raises_on_garbage_values(row: dict) -> None:
    original = deepcopy(row)
    assert _stamp(row) == original
    assert row == original
    assert tc.validate_v1(row)
    assert tc.classify_row(row) in {"v0-legacy", "tc-v1-invalid"}


@pytest.mark.parametrize("garbage", GARBAGE_TIMES)
def test_stamp_v1_never_raises_on_garbage_times(garbage: object) -> None:
    row = _row()
    assert _stamp(row, core=garbage) == row
    assert _stamp(row, issued=garbage) == row


@pytest.mark.parametrize("provider", [[], {}, 1, b"binance", object()])
def test_stamp_v1_never_raises_on_a_garbage_provider(provider: object) -> None:
    row = _row()
    assert _stamp(row, provider) == row


# --------------------------------------------------------------------------- legacy mapping

STAMPED = _stamp(_row())
CLASSIFICATION_CASES = [
    ("stamped", STAMPED, "tc-v1", "BINANCE_PUBLIC"),
    (
        "stamped-cross-provider",
        _stamp(_row(data_source="CROSS_PROVIDER", cross_provider_state="COHERENT"), "okx"),
        "tc-v1",
        "OKX_PUBLIC",
    ),
    ("legacy-binance", _row(), "v0-legacy", "BINANCE_PUBLIC"),
    ("legacy-okx", _row(data_source="OKX_PUBLIC"), "v0-legacy", "OKX_PUBLIC"),
    (
        "legacy-null-stamp-columns",
        {**_row(data_source="OKX_PUBLIC"), **NULL_STAMP},
        "v0-legacy",
        "OKX_PUBLIC",
    ),
    (
        "legacy-cross-provider",
        _row(data_source="CROSS_PROVIDER", cross_provider_state="COHERENT"),
        "v0-legacy",
        None,
    ),
    ("legacy-inexact-source", _row(data_source=" OKX_PUBLIC"), "v0-legacy", None),
    ("legacy-no-source", _row(data_source=None), "v0-legacy", None),
    ("stamped-then-invalid", {**STAMPED, "p_up_frac": 0.9}, "tc-v1-invalid", None),
    ("other-version", {**STAMPED, "target_version": "tc-v2"}, "tc-v1-invalid", None),
    ("partial-stamp", {**_row(), "reference_venue": "BINANCE_PUBLIC"}, "tc-v1-invalid", None),
    ("stamp-without-version", {**STAMPED, "target_version": None}, "tc-v1-invalid", None),
]


@pytest.mark.parametrize(
    ("row", "kind", "venue"),
    [case[1:] for case in CLASSIFICATION_CASES],
    ids=[case[0] for case in CLASSIFICATION_CASES],
)
def test_classify_row_and_resolution_venue(row: dict, kind: str, venue: str | None) -> None:
    assert tc.classify_row(row) == kind
    assert tc.resolution_venue(row) == venue


# --------------------------------------------------------------------------- boundaries


def test_venue_labels_match_the_writer_and_the_resolver() -> None:
    assert isinstance(tc.VENUE_LABELS, MappingProxyType)
    assert dict(tc.VENUE_LABELS) == DATA_SOURCE_BY_PROVIDER
    inverse = {label: provider for provider, label in tc.VENUE_LABELS.items()}
    assert inverse == dict(resolve_outcomes.EXACT_SOURCE_PROVIDERS)
    assert tc.TC_V1_TIMEFRAMES == resolve_outcomes.EXACT_TIMEFRAMES
    assert tc.TC_V1_TIMEFRAMES < set(TIMEFRAME_SECONDS)
    assert tc.TC_V1_MAX_HORIZON_BARS == resolve_outcomes.MAX_WINDOW_BARS
    with pytest.raises(TypeError):
        tc.VENUE_LABELS["bybit"] = "BYBIT_PUBLIC"  # type: ignore[index]


def test_the_contract_imports_only_the_standard_library_and_config_defaults() -> None:
    tree = ast.parse((TARGETS / "contract_v1.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0 and node.module
            imported.add(node.module)
    first_party = {name for name in imported if name.split(".")[0] == "crypto_probability_engine"}
    assert first_party == {"crypto_probability_engine.config.defaults"}
    for name in imported - first_party:
        assert name.split(".")[0] in sys.stdlib_module_names, name
    init_tree = ast.parse((TARGETS / "__init__.py").read_text(encoding="utf-8"))
    assert not [
        node for node in ast.walk(init_tree) if isinstance(node, (ast.Import, ast.ImportFrom))
    ]


# The explicit allowlist: the resolver (Route C, RC1) and its status store, which reads the stamp
# columns. Nothing else under src/ or scripts/ may even name the contract.
CONTRACT_IMPORTERS = (
    "scripts/resolve_outcomes.py",
    "src/crypto_probability_engine/resolution/status_store.py",
)


def test_nothing_in_the_product_imports_the_target_contract() -> None:
    """Nothing but the allowlisted resolver files, and each of them really imports it."""

    importers = []
    for path in [*PACKAGE.rglob("*.py"), *(ROOT / "scripts").rglob("*.py")]:
        if path.parent == TARGETS:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "crypto_probability_engine.targets" in text or "contract_v1" in text:
            importers.append(path.relative_to(ROOT).as_posix())
    assert sorted(importers) == sorted(CONTRACT_IMPORTERS)
    for name in CONTRACT_IMPORTERS:
        tree = ast.parse((ROOT / name).read_text(encoding="utf-8"))
        assert [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module == "crypto_probability_engine.targets.contract_v1"
        ], name


def test_the_section_5a_evaluator_pin_still_verifies_without_the_contract() -> None:
    evaluator_pin.assert_evaluator_pin()
    assert not [
        path
        for path in evaluator_pin.pinned_files()
        if path.startswith("src/crypto_probability_engine/targets/")
    ]
