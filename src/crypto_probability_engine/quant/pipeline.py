"""DEFAULT_PHASE1A deterministic quant pipeline."""

from __future__ import annotations

import hashlib
import json

from crypto_probability_engine.adapters.types import MarketSnapshot
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
from crypto_probability_engine.quant.probability_three_state import compute_probability_state
from crypto_probability_engine.quant.risk_arbiter import compute_risk_arbiter
from crypto_probability_engine.quant.tail_cvar import compute_tail_cvar
from crypto_probability_engine.score_stack.score import compute_score_stack


def stable_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run_quant_pipeline(snapshot: MarketSnapshot, provider_state: dict) -> dict:
    epistemic = assess_epistemic_sufficiency(snapshot)
    trend = compute_trend_mtf(snapshot.candles)
    volatility = compute_realized_volatility(snapshot.candles)
    liquidity = compute_liquidity_depth(snapshot.order_book)
    volume = compute_volume_anomaly(snapshot.candles)
    execution = compute_execution_realism(liquidity)
    risk_arbiter = compute_risk_arbiter(trend, volatility, liquidity, execution)
    timeout_frac = compute_timeout_probability(volatility, liquidity, timeframe=snapshot.timeframe)
    probability = compute_probability_state(
        net_signal=risk_arbiter["net_signal"],
        timeout_frac=timeout_frac,
        epistemic_state=epistemic,
        volatility_state=volatility,
    )
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
            "probability_three_state",
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
        "horizon_timeout_state": horizon_timeout_state(timeout_frac, timeframe=snapshot.timeframe),
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
    return result
