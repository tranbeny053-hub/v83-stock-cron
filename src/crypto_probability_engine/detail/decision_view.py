"""DecisionView: one authoritative, backend-built view of an analysis (governing plan §14.1-§14.3;
owner rulings DP-A and DP-F, 2026-10-05, local only until the owner authorizes publication).

It recomputes no probability and changes no other field of the analysis. It reads the analysis's
own values and says what they may mean, in the plan's precedence:
1. invalid or unavailable data;
2. valid data and no accepted forecast claim;
3. an accepted forecast-quality claim;
4. directional permission, only when that is separately accepted.
Missing evidence is never rendered as a negative market signal: without an accepted claim the view
says so, and no disposition is presented as a market call.

No forecast-quality claim and no directional permission is accepted today (Phase 4 INFEASIBLE; the
H2 hold), so states 3 and 4 are reachable only through the explicit registries below, which are
empty and change only by a governed acceptance. An acceptance names the probability type, the
methodology version and the timeframe, so it never outlives the model it was made for; and a
directional permission yields to any hard block (hard gates outrank everything shown).

DP-F, the honest DEGRADED: when the configured primary venue was tried and failed, so that another
venue served the data, the view's data state is DEGRADED, not OK. A primary that does not list the
symbol has not failed. The analysis's own data_quality and provider_state are untouched, so
radar_evidence.v1 and the AUTOMATED_RADAR path keep every value.

The view is built for every recorded analysis (a user's, the cadence's, a controlled smoke's) and
never for the isolated automation analysis or an OOS arm, which carry no decision_view key at all.

Its times are the target contract's (tc-v1, docs/TARGET_CONTRACT_V1.md): the reference is the last
closed candle, the horizon is close-anchored, and "In band" means the terminal close ends within
+/- the decision band (the round-trip cost) of the reference close.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from crypto_probability_engine.config.defaults import DEFAULT_PHASE1A, TIMEFRAME_SECONDS

SCHEMA_VERSION = "decision_view.v1"
# Governed acceptance registries, keyed "<probability_type>:<methodology_version>:<timeframe>".
# Empty: nothing is accepted.
ACCEPTED_FORECAST_CLAIMS: frozenset[str] = frozenset()
ACCEPTED_DIRECTIONAL_PERMISSIONS: frozenset[str] = frozenset()
# Hard blocks that mean the data cannot support an assessment at all.
DATA_HARD_BLOCKS = frozenset({"PROVIDER_DEGRADED", "EPISTEMIC_VOID"})

STATE_COPY = {
    "INVALID_OR_UNAVAILABLE_DATA": (
        "Data cannot support an assessment",
        "The market data for this analysis are unavailable or insufficient, so nothing here is an "
        "assessment of the market.",
    ),
    "NO_ACCEPTED_CLAIM": (
        "No accepted forecast",
        "No forecast-quality claim has been accepted for this model and timeframe. The "
        "percentages are uncalibrated reference context: not a forecast, not a market signal, and "
        "not a reason to act or to avoid acting.",
    ),
    "ACCEPTED_FORECAST_CLAIM": (
        "Accepted forecast-quality claim",
        "The percentages carry an accepted forecast-quality claim for this model and timeframe. "
        "They carry no directional permission.",
    ),
    "DIRECTIONAL_PERMISSION": (
        "Accepted forecast with directional permission",
        "The percentages carry an accepted forecast-quality claim and a separately accepted "
        "directional permission for this model and timeframe.",
    ),
}
DATA_COPY = {
    "OK": "Live data from the configured venues.",
    "DEMO": "Demo data: not a live market view.",
    "DEGRADED": "Live data, degraded.",
    "UNAVAILABLE": "Data unavailable.",
}
RANGE_MEANING = (
    "In band: the close at the horizon ends within +/- the decision band of the reference close. "
    "Up: above it. Down: below it."
)
NOT_ASSESSED = (
    "Not assessed: the data cannot support an assessment, so no range or probability is shown."
)
COST_LABEL = (
    "Estimated round-trip cost (2 x taker fee + slippage) as a fraction of the notional traded; "
    "it is also the decision band around the reference close."
)
REASON_COPY = {
    "PRIMARY_VENUE_ABSENT": "The configured primary venue failed; another venue served this data.",
    "CROSS_PROVIDER_CONFLICT": "The venues disagree beyond tolerance; one venue served this data.",
    "PROVIDER_UNAVAILABLE": "No venue produced valid data for an assessment.",
    "EVIDENCE_VOID": "The inputs are not sufficient for an assessment.",
}


def build_decision_view(
    *,
    timeframe: str,
    methodology_version: str,
    snapshot: Any,
    data_quality: Mapping[str, Any],
    provider_state: Mapping[str, Any],
    quant_result: Mapping[str, Any],
    decision_brief: Mapping[str, Any],
    skill_evidence: Mapping[str, Any] | None,
    primary_venue: str | None,
) -> dict[str, Any]:
    """The view of one analysis: a pure function of values the analysis already has."""

    gate = quant_result.get("gate_result") or {}
    hard_blocks = [str(block) for block in gate.get("hard_blocks") or []]
    data = _data_state(data_quality, provider_state, hard_blocks, primary_venue)
    claim_key = f"{decision_brief.get('probability_type')}:{methodology_version}:{timeframe}"
    if data["state"] == "UNAVAILABLE":
        state = "INVALID_OR_UNAVAILABLE_DATA"
    elif claim_key not in ACCEPTED_FORECAST_CLAIMS:
        state = "NO_ACCEPTED_CLAIM"
    elif claim_key in ACCEPTED_DIRECTIONAL_PERMISSIONS and not hard_blocks:
        state = "DIRECTIONAL_PERMISSION"
    else:
        state = "ACCEPTED_FORECAST_CLAIM"
    headline, detail = STATE_COPY[state]
    horizon = (quant_result.get("probability_state") or {}).get("horizons", {}).get("H_primary", {})
    execution = quant_result.get("execution_realism") or {}
    hold = gate.get("directional_evidence_hold")
    evidence = skill_evidence if isinstance(skill_evidence, Mapping) else {}
    # Precedence 1: data that cannot support an assessment shows no range or probability at all.
    assessed = state != "INVALID_OR_UNAVAILABLE_DATA"
    return {
        "schema_version": SCHEMA_VERSION,
        "state": state,
        "headline": headline,
        "detail": detail,
        "accepted_claim": state in {"ACCEPTED_FORECAST_CLAIM", "DIRECTIONAL_PERMISSION"},
        "directional_permission": state == "DIRECTIONAL_PERMISSION",
        "data": data,
        "time": _time(snapshot, timeframe),
        "range": {
            "assessed": assessed,
            "decision_band_frac": _fraction(execution.get("round_trip_cost_frac")),
            "in_band_frac": _fraction(horizon.get("p_timeout_frac")) if assessed else None,
            "up_frac": _fraction(horizon.get("p_up_frac")) if assessed else None,
            "down_frac": _fraction(horizon.get("p_down_frac")) if assessed else None,
            "evidence_level": decision_brief.get("probability_type"),
            "meaning": RANGE_MEANING if assessed else NOT_ASSESSED,
        },
        "cost": {
            "round_trip_cost_frac": _fraction(execution.get("round_trip_cost_frac")),
            "taker_fee_frac": _fraction(execution.get("taker_fee_frac")),
            "slippage_frac": _fraction(execution.get("slippage_frac")),
            "label": COST_LABEL,
        },
        "evidence": {
            "model_readiness": decision_brief.get("model_readiness"),
            "calibration_status": decision_brief.get("calibration_status"),
            "reliability_status": decision_brief.get("reliability_status"),
            "skill_verdict": None if _hold_active(hold) else evidence.get("verdict"),
            "resolved_outcomes": None if _hold_active(hold) else evidence.get("n"),
            "directional_evidence_hold": _hold_active(hold),
            "profitability_claim": False,
            "limitations": _limitations(state, _hold_active(hold)),
        },
    }


def _data_state(
    data_quality: Mapping[str, Any],
    provider_state: Mapping[str, Any],
    hard_blocks: list[str],
    primary_venue: str | None,
) -> dict[str, Any]:
    is_live = data_quality.get("is_live_data") is True
    active = provider_state.get("active_provider")
    providers = provider_state.get("providers") or {}
    primary = providers.get(primary_venue) if primary_venue else None
    # Tried and failed; a primary that does not list the symbol has not failed.
    primary_failed = (
        isinstance(primary, Mapping)
        and primary.get("status") == "QUARANTINED"
        and not str(primary.get("quarantine_reason") or "").startswith("INVALID_SYMBOL")
    )
    cross_provider = data_quality.get("cross_provider_state") or provider_state.get(
        "cross_provider_state"
    )
    reason: str | None = None
    if "PROVIDER_DEGRADED" in hard_blocks or provider_state.get("status") not in {"OK", "DEGRADED"}:
        state, reason = "UNAVAILABLE", "PROVIDER_UNAVAILABLE"
    elif "EPISTEMIC_VOID" in hard_blocks:
        state, reason = "UNAVAILABLE", "EVIDENCE_VOID"
    elif not is_live:
        state = "DEMO"
    elif cross_provider == "DATA_CONFLICT":
        state, reason = "DEGRADED", "CROSS_PROVIDER_CONFLICT"
    elif primary_failed and active not in {None, primary_venue, "cross_provider"}:
        state, reason = "DEGRADED", "PRIMARY_VENUE_ABSENT"
    else:
        state = "OK"
    return {
        "state": state,
        "reason": reason,
        "summary": " ".join([DATA_COPY[state], *([REASON_COPY[reason]] if reason else [])]),
        "venue": active,
        "primary_venue": primary_venue,
        "data_source": data_quality.get("data_source"),
        "is_live_data": is_live,
        "latest_candle_age_seconds": data_quality.get("latest_candle_age_seconds"),
    }


def _time(snapshot: Any, timeframe: str) -> dict[str, Any]:
    """The target contract's times (tc-v1): the last closed candle, and the close-anchored end."""

    horizon_bars = int(DEFAULT_PHASE1A.h_primary_bars)
    candles = tuple(getattr(snapshot, "candles", ()) or ())
    reference_close = _utc(getattr(candles[-1], "close_time_utc", None)) if candles else None
    horizon_end = (
        reference_close + timedelta(seconds=horizon_bars * TIMEFRAME_SECONDS[timeframe])
        if isinstance(reference_close, datetime) and timeframe in TIMEFRAME_SECONDS
        else None
    )
    return {
        "as_of_utc": _iso(getattr(snapshot, "as_of_utc", None)),
        "reference_close_utc": _iso(reference_close),
        "horizon_end_utc": _iso(horizon_end),
        "timeframe": timeframe,
        "horizon_bars": horizon_bars,
        "close_anchored": True,
    }


def _limitations(state: str, hold: bool) -> list[str]:
    limitations = [
        "Uncalibrated heuristic: its accuracy has not been established on resolved outcomes.",
        "No profitability claim.",
    ]
    if state in {"INVALID_OR_UNAVAILABLE_DATA", "NO_ACCEPTED_CLAIM"}:
        limitations.insert(0, "No forecast-quality claim is accepted for this model and timeframe.")
    if hold:
        limitations.append("Directional evidence is under review (the directional hold is active).")
    return limitations


def _hold_active(hold: Any) -> bool:
    """As the blocking-reason copy reads the hold (detail/frontend_display.py), so the view and the
    card never disagree on whether it applies."""

    return isinstance(hold, Mapping) and bool(hold.get("active"))


def _fraction(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _utc(value: Any) -> datetime | None:
    """As the prediction row reads a time (api/analysis_service.py's _coerce_utc_datetime)."""

    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _iso(value: Any) -> str | None:
    utc = _utc(value)
    return None if utc is None else utc.isoformat().replace("+00:00", "Z")
