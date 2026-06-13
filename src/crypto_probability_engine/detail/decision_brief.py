"""Backend-built honesty labels and decision brief."""

from __future__ import annotations

from crypto_probability_engine.config.defaults import DEFAULT_PHASE1A

PROBABILITY_EXPLANATION = (
    "Up/Down/Timeout are uncalibrated heuristic estimates over the next ~6 bars "
    "of this timeframe. Timeout means no decisive directional resolution. Not a "
    "forecast, not expected return, and not a trade recommendation."
)
UNCALIBRATED_BANNER = (
    "⚠️ Uncalibrated heuristic — these percentages are momentum-based estimates "
    "over a multi-bar horizon, not validated forecasts. Not financial advice. "
    "No profitability claim."
)
MODEL_READINESS_COPY = "Model readiness: Heuristic (uncalibrated) — accuracy not yet measured."
PROBABILITY_TYPE = "UNCALIBRATED_HEURISTIC_6BAR_OUTCOME"
MODEL_READINESS = "HEURISTIC_UNCALIBRATED"
DISCLAIMER = (
    "Uncalibrated heuristic over a multi-bar horizon. Not a forecast, signal, "
    "or financial advice. No profitability claim."
)

_HORIZON_LABELS = {
    "15m": ("15m setup", "~90m horizon"),
    "1H": ("1H setup", "~6H horizon"),
    "4H": ("4H setup", "~24H horizon"),
    "1D": ("1D setup", "~6D horizon"),
    "1W": ("1W setup", "~6W horizon"),
    "1M": ("1M setup", "~6M horizon"),
}


def build_horizon_context(timeframe: str) -> dict:
    horizon_bars = DEFAULT_PHASE1A.h_primary_bars
    timeframe_label, horizon_label = _HORIZON_LABELS.get(
        timeframe,
        (f"{timeframe} setup", f"~{horizon_bars} bars horizon"),
    )
    return {
        "timeframe_label": timeframe_label,
        "horizon_bars": horizon_bars,
        "horizon_label": horizon_label,
        "horizon_approx_label": f"{timeframe_label} / {horizon_label}",
        "probability_explanation": PROBABILITY_EXPLANATION,
        "uncalibrated_banner": UNCALIBRATED_BANNER,
        "model_readiness_label": MODEL_READINESS_COPY,
    }


def build_decision_brief(
    *,
    symbol: str,
    normalized_symbol: str,
    timeframe: str,
    quant_result: dict,
    data_quality: dict,
) -> dict:
    horizon = build_horizon_context(timeframe)
    gate = quant_result.get("gate_result", {})
    score = quant_result.get("score_stack", {})
    calibration = quant_result.get("calibration_state", {})
    volatility = quant_result.get("market_features", {}).get("volatility", {})
    action = _decision_action(gate, score)
    hard_blockers = list(gate.get("hard_blocks") or [])
    reliability = calibration.get("reliability_status", DEFAULT_PHASE1A.reliability_status)
    calibration_status = calibration.get("calibration_status", DEFAULT_PHASE1A.calibration_status)
    key_reasons = _key_reasons(
        action=action,
        gate=gate,
        score=score,
        data_quality=data_quality,
        hard_blockers=hard_blockers,
    )
    return {
        "action": action,
        "symbol": symbol,
        "normalized_symbol": normalized_symbol,
        "timeframe_label": horizon["timeframe_label"],
        "horizon_label": horizon["horizon_label"],
        "horizon_bars": horizon["horizon_bars"],
        "probability_type": PROBABILITY_TYPE,
        "model_readiness": MODEL_READINESS if reliability != "MEASURED" else "MEASURED",
        "calibration_status": calibration_status,
        "reliability_status": reliability,
        "profitability_claim": False,
        "state_summary": _state_summary(
            action=action,
            normalized_symbol=normalized_symbol,
            horizon=horizon,
            gate=gate,
            score=score,
        ),
        "key_reasons": key_reasons,
        "hard_blockers": hard_blockers,
        "watchlist_triggers": _watchlist_triggers(action, data_quality),
        "invalidation_conditions": _invalidation_conditions(hard_blockers),
        "volatility_reference": {
            "status": volatility.get("status", "UNAVAILABLE"),
            "realized_vol": volatility.get("realized_vol")
            if volatility.get("status") == "OK"
            else None,
            "note": "Volatility reference only — not a stop/target recommendation.",
        },
        "risk_note": (
            "Hard gates, provider/data quality, liquidity, tail risk, and execution realism "
            "remain authoritative. This brief is display-only."
        ),
        "disclaimer": DISCLAIMER,
    }


def _decision_action(gate: dict, score: dict) -> str:
    gate_action = str(gate.get("action") or "")
    score_disposition = str(score.get("disposition") or "")
    hard_blocks = gate.get("hard_blocks") or []
    if (
        hard_blocks
        or gate.get("hard_gate_passed") is False
        or gate_action.startswith("ABORT")
        or gate_action == "NO_TRADE"
        or score_disposition == "ELEVATED_RISK_AVOID"
    ):
        return "NO_TRADE"
    if score_disposition == "WATCH" or gate_action == "WATCH":
        return "WATCHLIST"
    if score_disposition in {"CONSTRUCTIVE_CAUTIOUS", "CONSTRUCTIVE"}:
        return "SPOT_WATCH"
    return "WATCHLIST"


def _key_reasons(
    *,
    action: str,
    gate: dict,
    score: dict,
    data_quality: dict,
    hard_blockers: list[str],
) -> list[str]:
    reasons: list[str] = []
    if hard_blockers:
        reasons.append(f"Hard gate blockers present: {', '.join(hard_blockers[:3])}.")
    else:
        reasons.append(f"Gate action: {gate.get('action', 'UNKNOWN')}.")
    reasons.append(f"Backend disposition: {score.get('disposition', 'UNKNOWN')}.")
    if score.get("total_score") is not None:
        reasons.append(f"Heuristic signal heat score: {score.get('total_score')}.")
    data_source = data_quality.get("data_source")
    if data_source:
        reasons.append(f"Data source: {data_source}.")
    if action == "NO_TRADE":
        reasons.append("No trade instruction is produced by this analysis-only app.")
    return reasons[:5]


def _watchlist_triggers(action: str, data_quality: dict) -> list[str]:
    triggers = [
        "Re-check only with fresh backend data over the stated multi-bar horizon.",
        "Monitor whether backend hard gates remain clear.",
    ]
    if action == "NO_TRADE":
        triggers.insert(0, "Wait for hard blockers or degraded data conditions to clear.")
    if data_quality.get("warnings"):
        triggers.append("Review data-quality warnings before interpreting percentages.")
    return triggers


def _invalidation_conditions(hard_blockers: list[str]) -> list[str]:
    if hard_blockers:
        return [f"Hard blocker persists: {blocker}." for blocker in hard_blockers[:5]]
    return [
        "Provider/data quality degradation appears.",
        "Any hard gate fails.",
        "The run becomes stale relative to its timeframe horizon.",
    ]


def _state_summary(
    *,
    action: str,
    normalized_symbol: str,
    horizon: dict,
    gate: dict,
    score: dict,
) -> str:
    return (
        f"{normalized_symbol} is classified as {action} for {horizon['horizon_approx_label']} "
        f"using an uncalibrated heuristic. Gate action is {gate.get('action', 'UNKNOWN')} "
        f"and backend disposition is {score.get('disposition', 'UNKNOWN')}."
    )
