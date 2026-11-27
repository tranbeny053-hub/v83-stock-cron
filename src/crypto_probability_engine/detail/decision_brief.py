"""Backend-built honesty labels and decision brief."""

from __future__ import annotations

from crypto_probability_engine.config.defaults import DEFAULT_PHASE1A
from crypto_probability_engine.detail.gate_kinds import (
    NOT_FORCED_BY_A_RISK_GATE,
    elevated_risk_not_forced_by_a_risk_gate,
)

PROBABILITY_EXPLANATION = (
    "Up/Down/In band are uncalibrated heuristic estimates for the terminal close ~6 bars "
    "ahead on this timeframe: Up ends above the decision band, Down below it, In band "
    "inside it (a terminal outcome, not a clock timeout). Not a forecast, not expected "
    "return, and not a trade recommendation."
)
UNCALIBRATED_BANNER = (
    "⚠️ Uncalibrated heuristic — these percentages are momentum-based estimates "
    "over a multi-bar horizon, not validated forecasts. Not financial advice. "
    "No profitability claim."
)
# The sentence must be true in every state (F-6, PROVISIONAL wording). No forecast-quality claim
# is accepted, and whether an accuracy was observed depends on the timeframe's evidence, so it
# states no measurement status.
MODEL_READINESS_COPY = "Model readiness: Heuristic (uncalibrated) — not validated."
PROBABILITY_TYPE = "UNCALIBRATED_HEURISTIC_6BAR_OUTCOME"
MODEL_READINESS = "HEURISTIC_UNCALIBRATED"
DISCLAIMER = (
    "Uncalibrated heuristic over a multi-bar horizon. Not a forecast, signal, "
    "or financial advice. No profitability claim."
)
REFERENCE_PROBABILITY_TYPE = "DESCRIPTIVE_REFERENCE_6BAR_INSIDE_BAND_FREQUENCY"
REFERENCE_MODEL_READINESS = "DESCRIPTIVE_REFERENCE_UNVALIDATED"
REFERENCE_MODEL_READINESS_COPY = (
    "Historical-frequency reference — descriptive estimate, not validated."
)
REFERENCE_PROBABILITY_EXPLANATION = (
    "In band is the share of recent matured six-bar outcomes on this market whose close ended "
    "inside today's decision band; Up and Down split the rest equally. Symmetric by design — "
    "no directional signal. The outcomes overlap. A descriptive historical frequency: not a "
    "validated forecast, not a prediction interval, not expected return, and not a trade "
    "recommendation."
)
REFERENCE_BANNER = "Historical-frequency reference · Descriptive estimate — not validated."
REFERENCE_DISCLAIMER = (
    "Descriptive historical frequency over a six-bar horizon. Not a forecast, signal, or "
    "financial advice. No profitability claim."
)
REFERENCE_METHOD = "DESCRIPTIVE_REFERENCE"
HEURISTIC_METHOD = "HEURISTIC"

_HORIZON_LABELS = {
    "15m": ("15m setup", "~90m horizon"),
    "1H": ("1H setup", "~6H horizon"),
    "4H": ("4H setup", "~24H horizon"),
    "1D": ("1D setup", "~6D horizon"),
    "1W": ("1W setup", "~6W horizon"),
    "1M": ("1M setup", "~6M horizon"),
}


def build_horizon_context(timeframe: str, *, methodology: str = HEURISTIC_METHOD) -> dict:
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
        "probability_explanation": (
            REFERENCE_PROBABILITY_EXPLANATION
            if methodology == REFERENCE_METHOD
            else PROBABILITY_EXPLANATION
        ),
        "uncalibrated_banner": REFERENCE_BANNER
        if methodology == REFERENCE_METHOD
        else UNCALIBRATED_BANNER,
        "model_readiness_label": (
            REFERENCE_MODEL_READINESS_COPY
            if methodology == REFERENCE_METHOD
            else MODEL_READINESS_COPY
        ),
    }


def build_decision_brief(
    *,
    symbol: str,
    normalized_symbol: str,
    timeframe: str,
    quant_result: dict,
    data_quality: dict,
    methodology: str = HEURISTIC_METHOD,
) -> dict:
    is_reference = methodology == REFERENCE_METHOD
    horizon = build_horizon_context(timeframe, methodology=methodology)
    gate = quant_result.get("gate_result", {})
    score = quant_result.get("score_stack", {})
    calibration = quant_result.get("calibration_state", {})
    volatility = quant_result.get("market_features", {}).get("volatility", {})
    # The forced token keeps its note unless a risk gate with a measured finding forced it.
    not_forced = elevated_risk_not_forced_by_a_risk_gate(
        gate, score, quant_result.get("liquidity_state")
    )
    action = _decision_action(gate, score)
    hard_blockers = list(gate.get("hard_blocks") or [])
    reliability = calibration.get("reliability_status", DEFAULT_PHASE1A.reliability_status)
    calibration_status = None if is_reference else calibration.get(
        "calibration_status", DEFAULT_PHASE1A.calibration_status
    )
    if is_reference:
        reliability = None
    key_reasons = _key_reasons(
        action=action,
        gate=gate,
        score=score,
        data_quality=data_quality,
        hard_blockers=hard_blockers,
        not_forced_by_a_risk_gate=not_forced,
        methodology=methodology,
    )
    result = {
        "action": action,
        "symbol": symbol,
        "normalized_symbol": normalized_symbol,
        "timeframe_label": horizon["timeframe_label"],
        "horizon_label": horizon["horizon_label"],
        "horizon_bars": horizon["horizon_bars"],
        "probability_type": REFERENCE_PROBABILITY_TYPE if is_reference else PROBABILITY_TYPE,
        "model_readiness": (
            REFERENCE_MODEL_READINESS
            if is_reference
            else MODEL_READINESS
            if reliability != "MEASURED"
            else "MEASURED"
        ),
        "calibration_status": calibration_status,
        "reliability_status": reliability,
        **({
            "calibration_status_reason": "NO_SCORED_COHORT_BY_DESIGN",
            "reliability_status_reason": "NO_SCORED_COHORT_BY_DESIGN",
        } if is_reference else {}),
        "profitability_claim": False,
        "state_summary": _state_summary(
            action=action,
            normalized_symbol=normalized_symbol,
            horizon=horizon,
            gate=gate,
            score=score,
            not_forced_by_a_risk_gate=not_forced,
            methodology=methodology,
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
        "disclaimer": REFERENCE_DISCLAIMER if is_reference else DISCLAIMER,
    }
    if is_reference:
        result.update(
            probability_explanation=REFERENCE_PROBABILITY_EXPLANATION,
            uncalibrated_banner=REFERENCE_BANNER,
            model_readiness_label=REFERENCE_MODEL_READINESS_COPY,
        )
    return result


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
    not_forced_by_a_risk_gate: bool,
    methodology: str = HEURISTIC_METHOD,
) -> list[str]:
    reasons: list[str] = []
    if hard_blockers:
        reasons.append(f"Hard gate blockers present: {', '.join(hard_blockers[:3])}.")
    else:
        reasons.append(f"Gate action: {gate.get('action', 'UNKNOWN')}.")
    forced = f" ({NOT_FORCED_BY_A_RISK_GATE})" if not_forced_by_a_risk_gate else ""
    reasons.append(f"Backend disposition: {score.get('disposition', 'UNKNOWN')}{forced}.")
    if score.get("total_score") is not None:
        if methodology == REFERENCE_METHOD:
            reasons.append(
                "Backend score (risk pressure only; direction is symmetric by design): "
                f"{score.get('total_score')}."
            )
        else:
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
    not_forced_by_a_risk_gate: bool,
    methodology: str = HEURISTIC_METHOD,
) -> str:
    methodology_copy = (
        "using a descriptive historical frequency"
        if methodology == REFERENCE_METHOD
        else "using an uncalibrated heuristic"
    )
    summary = (
        f"{normalized_symbol} is classified as {action} for {horizon['horizon_approx_label']} "
        f"{methodology_copy}. Gate action is {gate.get('action', 'UNKNOWN')} "
        f"and backend disposition is {score.get('disposition', 'UNKNOWN')}"
    )
    if not_forced_by_a_risk_gate:
        # The token stays; the sentence says no risk gate produced it (detail/gate_kinds.py).
        return f"{summary} ({NOT_FORCED_BY_A_RISK_GATE})."
    return f"{summary}."


def reference_display(reference_state: dict, horizon_timeout_state: dict) -> dict:
    """Build the reference block from backend-owned state only."""
    status = reference_state.get("status")
    if status == "SERVED":
        count = horizon_timeout_state.get("inside_band_count")
        total = horizon_timeout_state.get("matured_outcome_count")
        days = horizon_timeout_state.get("memory_days")
        return {
            "title": "Descriptive reference",
            "count_line": (
                f"In band: {count} of {total} matured six-bar outcomes over the last {days} days "
                "ended inside today's decision band."
            ),
            "direction_line": "Symmetric by design — no directional signal.",
            "overlap_line": "Outcomes overlap: each shares half its horizon with the next.",
            "honesty_line": (
                "Not a validated forecast and not a prediction interval. "
                "Not recorded for scoring."
            ),
            "extended_line": "Extended horizon: not modelled.",
        }
    reason = reference_state.get("reason")
    if reason == "NOT_NAMED_CELL":
        line = "Available only for BTC/USDT, ETH/USDT and SOL/USDT on Binance at 15m, 1H and 4H."
    else:
        line = f"Unavailable for this run ({reason}); the percentages shown are the heuristic's."
    return {
        "title": "Descriptive reference",
        "count_line": line,
        "direction_line": "",
        "overlap_line": "",
        "honesty_line": "",
        "extended_line": "",
    }
