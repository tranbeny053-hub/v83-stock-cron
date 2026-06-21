from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

import crypto_probability_engine.derivatives_intel.block as block_module
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.derivatives_intel.block import build_derivatives_intelligence
from crypto_probability_engine.derivatives_intel.instruments import (
    resolve_binance_usdm_instrument,
    resolve_okx_swap_instrument,
)
from crypto_probability_engine.derivatives_intel.runtime import (
    CachedInstrumentResolution,
    RawDerivativesBundle,
    RawProviderBundle,
)

CORE = datetime(2026, 6, 22, 0, tzinfo=UTC)
EVENT = CORE + timedelta(minutes=1)
FETCHED = EVENT + timedelta(seconds=1)
OBSERVED = FETCHED + timedelta(seconds=1)


def raw_bundle(*, okx_status: str = "OK") -> RawDerivativesBundle:
    binance_resolution = resolve_binance_usdm_instrument(
        "BTC/USDT",
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
    okx_resolution = resolve_okx_swap_instrument(
        "BTC/USDT",
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
    event_ms = int(EVENT.timestamp() * 1000)
    binance = RawProviderBundle(
        provider="BINANCE_USDM",
        normalized_symbol="BTC/USDT",
        instrument=CachedInstrumentResolution.from_resolution(binance_resolution),
        funding_payload=(("symbol", "BTCUSDT"), ("lastFundingRate", "-0.0001"), ("time", event_ms)),
        open_interest_payload=(("symbol", "BTCUSDT"), ("openInterest", "100"), ("time", event_ms)),
        funding_event_time=EVENT,
        open_interest_event_time=EVENT,
        funding_fetched_at_utc=FETCHED,
        open_interest_fetched_at_utc=FETCHED,
        fetch_status="OK",
        reason=None,
    )
    okx = RawProviderBundle(
        provider="OKX_SWAP",
        normalized_symbol="BTC/USDT",
        instrument=CachedInstrumentResolution.from_resolution(okx_resolution),
        funding_payload=(
            ("instId", "BTC-USDT-SWAP"),
            ("fundingRate", "0.0002"),
            ("ts", str(event_ms)),
        )
        if okx_status == "OK"
        else None,
        open_interest_payload=(
            ("instId", "BTC-USDT-SWAP"),
            ("instType", "SWAP"),
            ("oi", "20"),
            ("oiCcy", "0.2"),
            ("oiUsd", "13000"),
            ("ts", str(event_ms)),
        )
        if okx_status == "OK"
        else None,
        funding_event_time=EVENT if okx_status == "OK" else None,
        open_interest_event_time=EVENT if okx_status == "OK" else None,
        funding_fetched_at_utc=FETCHED if okx_status == "OK" else None,
        open_interest_fetched_at_utc=FETCHED if okx_status == "OK" else None,
        fetch_status=okx_status,
        reason=None if okx_status == "OK" else "Fixture provider unavailable.",
    )
    return RawDerivativesBundle(normalized_symbol="BTC/USDT", providers=(binance, okx))


def test_flag_off_returns_before_runtime_and_has_no_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        block_module,
        "get_raw_derivatives_bundle",
        lambda *args, **kwargs: pytest.fail("OFF path accessed runtime"),
    )
    result = build_derivatives_intelligence(
        normalized_symbol="BTC/USDT",
        core_prediction_as_of_utc=CORE,
        enabled=False,
    )
    assert result["block_status"] == "DISABLED"
    assert result["core_prediction_as_of_utc"] == "2026-06-22T00:00:00Z"
    assert result["observation_as_of_utc"] is None
    assert result["metrics"] == result["provider_summary"] == []


def test_runtime_feature_flag_defaults_off_and_parses_explicit_enable(monkeypatch) -> None:
    monkeypatch.delenv("UCPE_ENABLE_DERIVATIVES_INTEL", raising=False)
    assert Settings.from_env().enable_derivatives_intel is False
    monkeypatch.setenv("UCPE_ENABLE_DERIVATIVES_INTEL", "true")
    assert Settings.from_env().enable_derivatives_intel is True


def test_active_block_preserves_dual_times_and_provider_native_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(block_module, "get_raw_derivatives_bundle", lambda *a, **k: raw_bundle())
    result = build_derivatives_intelligence(
        normalized_symbol="BTC/USDT",
        core_prediction_as_of_utc=CORE,
        enabled=True,
        now_utc=OBSERVED,
    )
    assert result["block_status"] == "ACTIVE"
    assert result["core_prediction_as_of_utc"] != result["observation_as_of_utc"]
    assert {
        datetime.fromisoformat(metric["prediction_as_of_utc"].replace("Z", "+00:00"))
        for metric in result["metrics"]
    } == {datetime.fromisoformat(result["observation_as_of_utc"].replace("Z", "+00:00"))}
    assert {
        datetime.fromisoformat(metric["fetched_at_utc"].replace("Z", "+00:00"))
        for metric in result["metrics"]
    } == {FETCHED}
    assert result["disagreement"] == []
    assert all(not item["comparable"] for item in result["comparability"])
    assert result["decision_influence_frac"] == 0.0


def test_cache_reuse_retains_fetch_time_but_rebuilds_staleness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = raw_bundle()
    monkeypatch.setattr(block_module, "get_raw_derivatives_bundle", lambda *a, **k: bundle)
    first = build_derivatives_intelligence(
        normalized_symbol="BTC/USDT",
        core_prediction_as_of_utc=CORE,
        enabled=True,
        now_utc=OBSERVED,
    )
    second = build_derivatives_intelligence(
        normalized_symbol="BTC/USDT",
        core_prediction_as_of_utc=CORE,
        enabled=True,
        now_utc=OBSERVED + timedelta(seconds=20),
    )
    assert first["metrics"][0]["fetched_at_utc"] == second["metrics"][0]["fetched_at_utc"]
    assert first["metrics"][0]["raw_value"] == second["metrics"][0]["raw_value"]
    assert (
        second["metrics"][0]["input_staleness_seconds"]
        > first["metrics"][0]["input_staleness_seconds"]
    )


def test_future_fetch_relative_to_observation_is_never_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(block_module, "get_raw_derivatives_bundle", lambda *a, **k: raw_bundle())
    result = build_derivatives_intelligence(
        normalized_symbol="BTC/USDT",
        core_prediction_as_of_utc=CORE,
        enabled=True,
        now_utc=FETCHED - timedelta(milliseconds=1),
    )
    assert all(metric["status"] != "VALID" for metric in result["metrics"])
    assert all(not metric["no_lookahead_assertion"] for metric in result["metrics"])


def test_one_provider_unavailable_is_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        block_module,
        "get_raw_derivatives_bundle",
        lambda *a, **k: raw_bundle(okx_status="PROVIDER_UNAVAILABLE"),
    )
    result = build_derivatives_intelligence(
        normalized_symbol="BTC/USDT",
        core_prediction_as_of_utc=CORE,
        enabled=True,
        now_utc=OBSERVED,
    )
    assert result["block_status"] == "DEGRADED"
    assert result["provider_summary"][1]["status"] == "PROVIDER_UNAVAILABLE"
