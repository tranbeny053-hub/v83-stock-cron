"""Dormant KEEP_HOLD wrapper that preserves the legacy result byte-for-byte."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from crypto_probability_engine.adapters.types import MarketSnapshot
from crypto_probability_engine.config.defaults import (
    DEFAULT_METHODOLOGY_VERSION,
    DISTRIBUTIONAL_METHODOLOGY_VERSION,
)
from crypto_probability_engine.execution_realism.realism import compute_execution_realism
from crypto_probability_engine.features.btc_eth_context import btc_eth_context_state
from crypto_probability_engine.features.correlation_beta import correlation_beta_state
from crypto_probability_engine.features.liquidity_depth import compute_liquidity_depth
from crypto_probability_engine.features.memory_features import memory_feature_state
from crypto_probability_engine.features.regime_2state import classify_regime
from crypto_probability_engine.features.trend_mtf import compute_trend_mtf
from crypto_probability_engine.features.volatility import compute_realized_volatility
from crypto_probability_engine.features.volume_anomaly import compute_volume_anomaly
from crypto_probability_engine.gates.composite import apply_composite_gates
from crypto_probability_engine.global_risk.state import global_risk_state
from crypto_probability_engine.quant.calibration_metrics import calibration_state
from crypto_probability_engine.quant.epistemic_sufficiency import assess_epistemic_sufficiency
from crypto_probability_engine.quant.horizon_timeout import (
    compute_timeout_probability,
    horizon_timeout_state,
)
from crypto_probability_engine.quant.pipeline import stable_hash
from crypto_probability_engine.quant.probability_distributional import (
    build_distributional_probability_state,
    compute_distributional_probabilities,
)
from crypto_probability_engine.quant.probability_three_state import compute_probability_state
from crypto_probability_engine.quant.risk_arbiter import compute_risk_arbiter
from crypto_probability_engine.quant.tail_cvar import compute_tail_cvar
from crypto_probability_engine.quant_ng.registry import (
    SLOT_POLICY,
    Refusal,
    serving_state,
)
from crypto_probability_engine.score_stack.score import compute_score_stack


def run_pipeline_ng(
    snapshot: MarketSnapshot,
    provider_state: dict,
    *,
    registry: Mapping,
    cell: Mapping,
    now: datetime,
    methodology_version: str = DEFAULT_METHODOLOGY_VERSION,
) -> dict:
    """Recompose the legacy pipeline and append a hidden-reference serving block."""
    if methodology_version not in {DEFAULT_METHODOLOGY_VERSION, DISTRIBUTIONAL_METHODOLOGY_VERSION}:
        raise ValueError(f"Unsupported methodology version: {methodology_version}")
    state = serving_state(registry, cell, now)
    if cell["symbol"] != snapshot.normalized_symbol:
        raise Refusal("cell symbol does not match snapshot")
    if cell["timeframe"] != snapshot.timeframe:
        raise Refusal("cell timeframe does not match snapshot")
    if cell["methodology_version"] != methodology_version:
        raise Refusal("cell methodology_version does not match argument")

    epistemic = assess_epistemic_sufficiency(snapshot)
    trend = compute_trend_mtf(snapshot.candles)
    volatility = compute_realized_volatility(snapshot.candles)
    liquidity = compute_liquidity_depth(snapshot.order_book)
    volume = compute_volume_anomaly(snapshot.candles)
    execution = compute_execution_realism(liquidity)
    risk_arbiter = compute_risk_arbiter(trend, volatility, liquidity, execution)
    if methodology_version == DEFAULT_METHODOLOGY_VERSION:
        timeout_frac = compute_timeout_probability(
            volatility, liquidity, timeframe=snapshot.timeframe
        )
        probability = compute_probability_state(
            net_signal=risk_arbiter["net_signal"],
            timeout_frac=timeout_frac,
            epistemic_state=epistemic,
            volatility_state=volatility,
        )
        timeout_state = horizon_timeout_state(timeout_frac, timeframe=snapshot.timeframe)
        probability_model = "probability_three_state"
    else:
        distributional = compute_distributional_probabilities(
            snapshot.candles,
            timeframe=snapshot.timeframe,
            band_frac=execution["round_trip_cost_frac"],
        )
        probability = build_distributional_probability_state(
            distributional, epistemic_state=epistemic
        )
        timeout_state = {
            "status": "OK",
            "method": DISTRIBUTIONAL_METHODOLOGY_VERSION,
            "p_timeout_frac": distributional.p_timeout_frac,
            "timeout_is_directional": False,
            "timeframe": snapshot.timeframe,
            "sigma_bar": distributional.sigma_bar,
            "sigma_h": distributional.sigma_h,
            "band_frac": distributional.band_frac,
        }
        probability_model = "probability_distributional"
    score = compute_score_stack(probability, risk_arbiter)
    tail_risk = compute_tail_cvar(snapshot.candles, timeframe=snapshot.timeframe)
    risk_flags = global_risk_state()
    gate = apply_composite_gates(
        epistemic_state=epistemic,
        provider_state=provider_state,
        score_state=score,
        liquidity_state=liquidity,
        tail_risk_state=tail_risk,
        execution_state=execution,
        shelter_mode=risk_flags["shelter_mode"],
        kill_switch=risk_flags["kill_switch"],
    )
    if gate.get("forced_score_disposition"):
        score = {
            **score,
            "disposition": gate["forced_score_disposition"],
            "risk_guard_applied": True,
        }
    features = {
        "trend_mtf": trend,
        "volatility": volatility,
        "liquidity_depth": liquidity,
        "volume_anomaly": volume,
        "btc_eth_context": btc_eth_context_state(),
        "correlation_beta": correlation_beta_state(),
        "memory_features": memory_feature_state(),
        "regime_2state": classify_regime(volatility),
    }
    quant_state = {
        "status": "OK" if epistemic["action"] == "ALLOW" else "ABORTED",
        "models_run": [
            "trend_mtf",
            "volatility",
            "liquidity_depth",
            "volume_anomaly",
            probability_model,
            "risk_arbiter",
            "tail_cvar",
        ],
        "models_skipped": ["evt", "backend_llm"],
    }
    result = {
        "market_features": features,
        "liquidity_state": liquidity,
        "execution_realism": execution,
        "quant_compute_state": quant_state,
        "epistemic_sufficiency_state": epistemic,
        "probability_state": probability,
        "horizon_timeout_state": timeout_state,
        "risk_arbiter_state": risk_arbiter,
        "tail_risk_state": tail_risk,
        "calibration_state": calibration_state(),
        "score_stack": score,
        "trend_summary": {
            "label": trend["label"],
            "magnitude_pct": trend["primary_return"] * 100.0,
        },
        "gate_result": gate,
        "global_risk_state": risk_flags,
    }
    result["analysis_hash"] = stable_hash(result)
    return {
        "result": result,
        "ng": {
            "schema": "quant-ng-serving.v1",
            "serving_state": {
                "tier": state.tier,
                "reference": state.reference,
                "status": state.status,
                "slot_policy": state.slot_policy,
                "reason": state.reason,
            },
            "reference_state": "HIDDEN",
            "evidence_status": "NONE",
            "slot_policy": SLOT_POLICY,
            "policy_id": None,
        },
    }
