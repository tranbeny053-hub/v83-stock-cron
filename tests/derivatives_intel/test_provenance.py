from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from crypto_probability_engine.derivatives_intel.instruments import (
    resolve_binance_usdm_instrument,
    resolve_okx_swap_instrument,
)
from crypto_probability_engine.derivatives_intel.provenance import (
    CURRENT_FUNDING_MAX_STALENESS_SECONDS,
    binance_funding_interval_from_info,
    build_binance_current_funding_metric,
    build_binance_current_open_interest_metric,
    build_binance_open_interest_history_metrics,
    build_binance_settled_funding_metric,
    build_okx_current_funding_metric,
    build_okx_current_open_interest_metrics,
    build_okx_settled_funding_metric,
)

AS_OF = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)
FETCHED = AS_OF - timedelta(seconds=5)


def _ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def _binance_resolution():
    return resolve_binance_usdm_instrument(
        "BTCUSDT",
        {
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "status": "TRADING",
                    "contractType": "PERPETUAL",
                    "quoteAsset": "USDT",
                    "marginAsset": "USDT",
                }
            ]
        },
    )


def _okx_resolution():
    return resolve_okx_swap_instrument(
        "BTCUSDT",
        [
            {
                "instId": "BTC-USDT-SWAP",
                "instType": "SWAP",
                "settleCcy": "USDT",
                "ctType": "linear",
                "state": "live",
            }
        ],
    )


def _assert_shadow(metric: dict) -> None:
    assert metric["influence_mode"] == "SHADOW_ONLY"
    assert metric["methodology_version"] == "deriv-intel-shadow-v0"
    for key in (
        "normalized_value",
        "bucket",
        "direction_hint",
        "confidence_hint",
        "risk_hint",
    ):
        assert metric[key] is None


def test_current_funding_is_point_in_time_and_has_no_direction() -> None:
    event = AS_OF - timedelta(minutes=2)
    binance = build_binance_current_funding_metric(
        {"lastFundingRate": "0.0001", "time": _ms(event)},
        _binance_resolution(),
        fetched_at_utc=FETCHED,
        prediction_as_of_utc=AS_OF,
    )
    okx = build_okx_current_funding_metric(
        [{"fundingRate": "-0.0002", "ts": str(_ms(event))}],
        _okx_resolution(),
        fetched_at_utc=FETCHED,
        prediction_as_of_utc=AS_OF,
    )
    assert binance["status"] == okx["status"] == "VALID"
    assert binance["raw_value"] == pytest.approx(0.0001)
    assert okx["raw_value"] == pytest.approx(-0.0002)
    assert binance["interval_start"] is None and binance["interval_end"] is None
    assert binance["interval_final"] is True
    _assert_shadow(binance)
    _assert_shadow(okx)


def test_settled_funding_rejects_future_event_without_staleness_rule() -> None:
    past = build_binance_settled_funding_metric(
        {"fundingRate": "0.0001", "fundingTime": _ms(AS_OF - timedelta(days=20))},
        _binance_resolution(),
        fetched_at_utc=FETCHED,
        prediction_as_of_utc=AS_OF,
    )
    future = build_okx_settled_funding_metric(
        {"fundingRate": "0.0002", "fundingTime": str(_ms(AS_OF + timedelta(hours=1)))},
        _okx_resolution(),
        fetched_at_utc=FETCHED,
        prediction_as_of_utc=AS_OF,
    )
    assert past["status"] == "VALID"
    assert past["input_staleness_seconds"] is None
    assert future["status"] == "DEGRADED"
    assert future["no_lookahead_assertion"] is False


def test_binance_funding_info_absence_is_honest_unknown_not_failure() -> None:
    assert binance_funding_interval_from_info([], "BTCUSDT") is None
    assert (
        binance_funding_interval_from_info(
            [{"symbol": "ETHUSDT", "fundingIntervalHours": 4}], "BTCUSDT"
        )
        is None
    )
    assert (
        binance_funding_interval_from_info(
            [{"symbol": "BTCUSDT", "fundingIntervalHours": 4}], "BTCUSDT"
        )
        == "4h"
    )


def test_open_interest_native_units_remain_separate() -> None:
    event = AS_OF - timedelta(seconds=30)
    current = build_binance_current_open_interest_metric(
        {"openInterest": "123.4", "time": _ms(event)},
        _binance_resolution(),
        fetched_at_utc=FETCHED,
        prediction_as_of_utc=AS_OF,
    )
    history = build_binance_open_interest_history_metrics(
        {
            "sumOpenInterest": "120.5",
            "sumOpenInterestValue": "8000000.5",
            "timestamp": _ms(event),
        },
        _binance_resolution(),
        period="5m",
        fetched_at_utc=FETCHED,
        prediction_as_of_utc=AS_OF,
    )
    okx = build_okx_current_open_interest_metrics(
        [{"oi": "10", "oiCcy": "0.1", "oiUsd": "6500", "ts": str(_ms(event))}],
        _okx_resolution(),
        fetched_at_utc=FETCHED,
        prediction_as_of_utc=AS_OF,
    )
    assert current["unit"] == "PROVIDER_NATIVE_CONTRACT_QUANTITY"
    assert [item["unit"] for item in history] == [
        "PROVIDER_NATIVE_CONTRACT_QUANTITY",
        "USDT_NOTIONAL",
    ]
    assert [item["unit"] for item in okx] == [
        "CONTRACTS",
        "BASE_ASSET_QUANTITY",
        "USD_NOTIONAL",
    ]
    assert all(item["interval_start"] is None for item in okx)
    assert all(item["status"] == "VALID" for item in okx)


def test_incomplete_historical_bucket_is_partial_but_current_oi_is_not() -> None:
    future_end = AS_OF + timedelta(minutes=1)
    history = build_binance_open_interest_history_metrics(
        {"sumOpenInterest": "10", "sumOpenInterestValue": "20", "timestamp": _ms(future_end)},
        _binance_resolution(),
        period="5m",
        fetched_at_utc=FETCHED,
        prediction_as_of_utc=AS_OF,
    )
    current = build_binance_current_open_interest_metric(
        {"openInterest": "10", "time": _ms(AS_OF - timedelta(seconds=1))},
        _binance_resolution(),
        fetched_at_utc=FETCHED,
        prediction_as_of_utc=AS_OF,
    )
    assert all(item["status"] == "PARTIAL_INTERVAL" for item in history)
    assert all(item["interval_final"] is False for item in history)
    assert current["status"] == "VALID"
    assert current["interval_final"] is True


@pytest.mark.parametrize("bad_value", [None, "nan", "inf", {}, []])
def test_malformed_or_nonfinite_values_become_compute_error(bad_value) -> None:
    metric = build_binance_current_funding_metric(
        {"lastFundingRate": bad_value, "time": _ms(AS_OF - timedelta(seconds=1))},
        _binance_resolution(),
        fetched_at_utc=FETCHED,
        prediction_as_of_utc=AS_OF,
    )
    assert metric["status"] == "COMPUTE_ERROR"
    assert metric["raw_value"] is None
    assert metric["reason_if_invalid"]


def test_timestamp_and_staleness_rules_are_deterministic() -> None:
    stale_event = AS_OF - timedelta(seconds=CURRENT_FUNDING_MAX_STALENESS_SECONDS + 1)
    args = (
        {"lastFundingRate": "0.1", "time": _ms(stale_event)},
        _binance_resolution(),
    )
    first = build_binance_current_funding_metric(
        *args, fetched_at_utc=FETCHED, prediction_as_of_utc=AS_OF
    )
    second = build_binance_current_funding_metric(
        *args, fetched_at_utc=FETCHED, prediction_as_of_utc=AS_OF
    )
    assert first == second
    assert first["status"] == "STALE_INPUT"

    with pytest.raises(ValueError, match="timezone-aware UTC"):
        build_binance_current_funding_metric(
            {"lastFundingRate": "0.1", "time": _ms(AS_OF - timedelta(seconds=1))},
            _binance_resolution(),
            fetched_at_utc=FETCHED.replace(tzinfo=None),
            prediction_as_of_utc=AS_OF,
        )
    future_fetch = build_binance_current_funding_metric(
        {"lastFundingRate": "0.1", "time": _ms(AS_OF - timedelta(seconds=1))},
        _binance_resolution(),
        fetched_at_utc=AS_OF + timedelta(seconds=1),
        prediction_as_of_utc=AS_OF,
    )
    assert future_fetch["status"] == "DEGRADED"
    assert not future_fetch["no_lookahead_assertion"]
