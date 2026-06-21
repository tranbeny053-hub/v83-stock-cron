from __future__ import annotations

import importlib
import inspect
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from math import inf

import crypto_probability_engine.quant_v2.contract as contract
from crypto_probability_engine.api.schemas import QuantV2Block
from crypto_probability_engine.config import env_flags
from crypto_probability_engine.quant.pipeline import run_quant_pipeline
from crypto_probability_engine.quant_v2.contract import build_quant_v2_shadow
from tests.fixtures.market_data import FIXED_NOW, make_snapshot

BLOCK_FIELDS = {
    "schema_version",
    "status",
    "influence_mode",
    "feature_methodology_version",
    "computed_at_utc",
    "symbol",
    "normalized_symbol",
    "timeframe",
    "reference_close_utc",
    "input_staleness_seconds",
    "no_lookahead_assertion",
    "feature_count",
    "degraded_count",
    "features",
    "plain_english",
    "not_trade_command",
    "not_financial_advice",
}
FEATURE_FIELDS = {
    "feature_name",
    "feature_id",
    "family",
    "timeframe",
    "symbol",
    "source_provider",
    "source_priority",
    "lookback",
    "candle_count",
    "computed_at",
    "input_start_time",
    "input_end_time",
    "input_staleness_seconds",
    "status",
    "reason_if_invalid",
    "raw_value",
    "normalized_value",
    "bucket",
    "direction_hint",
    "confidence_hint",
    "risk_hint",
    "explanation_short",
    "explanation_detail",
    "influence_mode",
    "methodology_version",
    "data_quality",
    "no_lookahead_assertion",
}


def _build(*, snapshot=None, quant_result=None, provider_state=None, enabled=True) -> dict:
    snapshot = snapshot or make_snapshot(provider="binance")
    provider_state = (
        {"status": "OK", "active_provider": snapshot.provider}
        if provider_state is None
        else provider_state
    )
    quant_result = quant_result or run_quant_pipeline(snapshot, provider_state)
    return build_quant_v2_shadow(
        quant_result=quant_result,
        snapshot=snapshot,
        provider_state=provider_state,
        symbol="BTC",
        normalized_symbol="BTC/USDT",
        timeframe=snapshot.timeframe,
        enabled=enabled,
    )


def test_active_contract_has_exact_four_strict_feature_groups() -> None:
    block = _build()

    assert set(block) == BLOCK_FIELDS
    assert block["status"] == "ACTIVE"
    assert block["influence_mode"] == "SHADOW_ONLY"
    assert block["schema_version"] == "quant_v2.0"
    assert block["feature_methodology_version"] == "quant-v2-shadow-v0"
    assert block["feature_count"] == 4
    assert block["degraded_count"] == 0
    assert block["no_lookahead_assertion"] is True
    assert [feature["family"] for feature in block["features"]] == [
        "VOLATILITY",
        "TREND",
        "VOLUME",
        "REGIME",
    ]
    for feature in block["features"]:
        assert set(feature) == FEATURE_FIELDS
        assert feature["status"] == "VALID"
        assert feature["reason_if_invalid"] is None
        assert feature["influence_mode"] == "SHADOW_ONLY"
        assert feature["normalized_value"] is None
        assert feature["bucket"] is None
        assert feature["confidence_hint"] is None
        assert feature["risk_hint"] is None
        assert feature["no_lookahead_assertion"] is True
    direction_hints = {
        feature["family"]: feature["direction_hint"] for feature in block["features"]
    }
    assert direction_hints["TREND"] in {"UP", "DOWN", "SIDEWAYS"}
    assert all(
        hint is None
        for family, hint in direction_hints.items()
        if family != "TREND"
    )
    QuantV2Block.model_validate(block)


def test_shadow_feature_flag_defaults_enabled(monkeypatch) -> None:
    monkeypatch.delenv("UCPE_QUANT_V2_SHADOW_ENABLED", raising=False)
    reloaded = importlib.reload(env_flags)

    assert reloaded.QUANT_V2_SHADOW_ENABLED is True


def test_disabled_contract_is_complete_and_schema_valid() -> None:
    block = _build(enabled=False)

    assert set(block) == BLOCK_FIELDS
    assert block["status"] == "DISABLED"
    assert block["influence_mode"] == "SHADOW_ONLY"
    assert block["features"] == []
    assert block["feature_count"] == 0
    assert block["degraded_count"] == 0
    assert block["not_trade_command"] is True
    assert block["not_financial_advice"] is True
    QuantV2Block.model_validate(block)


def test_insufficient_history_is_explicit_without_new_feature_math() -> None:
    snapshot = make_snapshot(provider="binance", count=10)
    block = _build(snapshot=snapshot)
    by_family = {feature["family"]: feature for feature in block["features"]}

    assert block["status"] == "DEGRADED"
    assert by_family["TREND"]["status"] == "INSUFFICIENT_HISTORY"
    assert by_family["VOLUME"]["status"] == "INSUFFICIENT_HISTORY"
    assert by_family["TREND"]["reason_if_invalid"]
    assert by_family["VOLUME"]["reason_if_invalid"]


def test_non_finite_and_malformed_upstream_values_degrade_per_feature() -> None:
    snapshot = make_snapshot(provider="binance")
    quant_result = run_quant_pipeline(snapshot, {"status": "OK"})
    quant_result = deepcopy(quant_result)
    quant_result["market_features"]["volatility"]["realized_vol"] = inf
    quant_result["market_features"]["trend_mtf"] = "malformed"

    block = _build(snapshot=snapshot, quant_result=quant_result)
    by_family = {feature["family"]: feature for feature in block["features"]}

    assert by_family["VOLATILITY"]["status"] == "COMPUTE_ERROR"
    assert by_family["VOLATILITY"]["raw_value"] is None
    assert by_family["TREND"]["status"] == "COMPUTE_ERROR"
    assert by_family["TREND"]["reason_if_invalid"]
    assert by_family["VOLUME"]["status"] == "VALID"


def test_upstream_degraded_status_remains_separate_from_shadow_governance() -> None:
    snapshot = make_snapshot(provider="binance")
    quant_result = deepcopy(run_quant_pipeline(snapshot, {"status": "OK"}))
    quant_result["market_features"]["volume_anomaly"]["status"] = "DEGRADED"

    block = _build(snapshot=snapshot, quant_result=quant_result)
    volume = next(feature for feature in block["features"] if feature["family"] == "VOLUME")

    assert volume["status"] == "DEGRADED"
    assert volume["influence_mode"] == "SHADOW_ONLY"
    assert volume["reason_if_invalid"]


def test_forced_feature_exception_becomes_compute_error(monkeypatch) -> None:
    original = contract._extract_raw_value

    def fail_volume(spec, upstream):
        if spec.family == "VOLUME":
            raise RuntimeError("forced test failure")
        return original(spec, upstream)

    monkeypatch.setattr(contract, "_extract_raw_value", fail_volume)
    block = _build()
    by_family = {feature["family"]: feature for feature in block["features"]}

    assert by_family["VOLUME"]["status"] == "COMPUTE_ERROR"
    assert by_family["VOLUME"]["reason_if_invalid"]
    assert by_family["VOLATILITY"]["status"] == "VALID"


def test_existing_freshness_rule_marks_stale_without_new_threshold() -> None:
    original = make_snapshot(provider="binance")
    stale_snapshot = replace(original, as_of_utc=FIXED_NOW + timedelta(hours=7))
    quant_result = run_quant_pipeline(original, {"status": "OK"})

    block = _build(snapshot=stale_snapshot, quant_result=quant_result)

    assert block["status"] == "DEGRADED"
    assert block["input_staleness_seconds"] == 7 * 60 * 60
    assert {feature["status"] for feature in block["features"]} == {"STALE_INPUT"}


def test_missing_provider_state_uses_snapshot_provenance_without_crashing() -> None:
    block = _build(provider_state={})

    assert block["status"] == "ACTIVE"
    assert all(feature["source_provider"] == "binance" for feature in block["features"])
    assert all(
        feature["data_quality"]["provider_state_status"] is None
        for feature in block["features"]
    )


def test_missing_snapshot_provider_is_provider_unavailable() -> None:
    snapshot = replace(make_snapshot(provider="binance"), provider="")
    quant_result = run_quant_pipeline(snapshot, {})
    block = _build(snapshot=snapshot, quant_result=quant_result, provider_state={})

    assert block["status"] == "DEGRADED"
    assert {feature["status"] for feature in block["features"]} == {
        "PROVIDER_UNAVAILABLE"
    }


def test_invalid_future_timestamp_cannot_earn_no_lookahead() -> None:
    original = make_snapshot(provider="binance")
    last = original.candles[-1]
    future_last = replace(last, close_time_utc=FIXED_NOW + timedelta(hours=1))
    invalid_snapshot = replace(original, candles=(*original.candles[:-1], future_last))
    quant_result = run_quant_pipeline(original, {"status": "OK"})

    block = _build(snapshot=invalid_snapshot, quant_result=quant_result)

    assert block["status"] == "DEGRADED"
    assert block["no_lookahead_assertion"] is False
    assert all(feature["no_lookahead_assertion"] is False for feature in block["features"])
    assert all(feature["reason_if_invalid"] for feature in block["features"])


def test_repeated_calls_are_identical_and_use_snapshot_timestamps() -> None:
    snapshot = make_snapshot(provider="binance")
    quant_result = run_quant_pipeline(snapshot, {"status": "OK"})

    first = _build(snapshot=snapshot, quant_result=quant_result)
    second = _build(snapshot=snapshot, quant_result=quant_result)

    assert first == second
    assert first["computed_at_utc"] == snapshot.as_of_utc.isoformat().replace("+00:00", "Z")
    assert first["reference_close_utc"] == snapshot.candles[-1].close_time_utc.isoformat().replace(
        "+00:00", "Z"
    )


def test_builder_has_no_network_clock_randomness_or_forbidden_layer_imports() -> None:
    source = inspect.getsource(contract)
    forbidden = (
        "datetime.now",
        "utcnow",
        "time.time",
        "random",
        "httpx",
        "requests",
        "public_market",
        "crypto_probability_engine.persistence",
        "crypto_probability_engine.calibration",
        "resolve_outcomes",
    )
    assert not any(marker in source for marker in forbidden)


def test_safety_copy_is_factual_and_non_actionable() -> None:
    block = _build()
    assert block["plain_english"] == (
        "Shadow diagnostics — evidence only, not used in the decision yet. "
        "Not a trade command. Not financial advice. Not profitability evidence. Not accuracy."
    )
    assert block["not_trade_command"] is True
    assert block["not_financial_advice"] is True
