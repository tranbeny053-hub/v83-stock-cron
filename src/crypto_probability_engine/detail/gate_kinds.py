"""The one authority for what the hard gates mean (owner rulings CLASS-B-4=A, AD1=A and G2,
2026-10-10; governing plan §14.1: missing evidence must never render as a negative market signal).

The gates are unchanged (gates/composite.py). They report three kinds of hard block:
- a risk gate: a measured finding about the market or its execution (a tail-risk breach, an
  execution cost that is too high, liquidity that was measured and is not viable);
- a system or data gate: the kill switch, shelter mode, a degraded provider, insufficient inputs,
  and the liquidity gate when it fired because the order book was missing or unusable. Missing data
  is not a proven market risk (owner ruling G2), so that block is never worded as a finding;
- the evidence gate: directional skill is not established for this model and timeframe. It says
  what is not yet known about the model, never anything about the market.

The evidence gate, and the liquidity gate on missing data, force the same action and the same score
token as a risk gate (NO_TRADE, ELEVATED_RISK_AVOID). Those tokens stay. `build_gate_view` turns a
gate result into the gate framing every surface shows: the kinds, each block, one summary and one
framing sentence. The frontend displays these sentences and words none of its own.

It is a pure function of facts the analysis already holds: the gate result, and the liquidity state
the liquidity gate judged. Every saved run stores both. So the framing of a reopened run is built
when it is read (`attach_gate_view`), never stored: an old run and a new one read the same, and a
wording change needs no stored text rewritten. No field here is named with "code", "key", "hash" or
"token", which utils/sanitize.py masks in a stored payload.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crypto_probability_engine.detail.frontend_display import (
    blocking_reason,
    liquidity_was_measured,
)

SCHEMA_VERSION = "gate_view.v1"
RISK_GATE_BLOCKS = frozenset(
    {"LIQUIDITY_NOT_VIABLE", "TAIL_RISK_BREACH", "EXECUTION_COST_TOO_HIGH"}
)
EVIDENCE_GATE_BLOCKS = frozenset({"SKILL_NOT_DEMONSTRATED"})
LIQUIDITY_BLOCK = "LIQUIDITY_NOT_VIABLE"
ELEVATED_RISK_TOKEN = "ELEVATED_RISK_AVOID"
EVIDENCE_GATE_COPY = "directional skill is not established for this model and timeframe"
EVIDENCE_GATE_HEADLINE = "Directional skill is not established"
NOT_FORCED_BY_A_RISK_GATE = "not forced by a risk gate"
UNNAMED_HARD_GATE = "One or more hard gates are active."
NO_HARD_GATE = "No hard gate is active."
# The risk framing names the gate it is about (review finding D1): beside another gate, a sentence
# that began "This is a finding" could be read as being about that other gate.
RISK_FRAMING_ONE = (
    "The risk gate ({names}) is a finding about market conditions or execution. It is analysis "
    "only, not an instruction."
)
RISK_FRAMING_SEVERAL = (
    "The risk gates ({names}) are findings about market conditions or execution. They are "
    "analysis only, not an instruction."
)
NOT_A_MARKET_CALL = (
    "The gates' disposition, not a market call: a gate outcome is not a forecast to act on."
)
# The framing under an accepted state (owner ruling 2026-10-06). The frontend used to word these
# two itself; it now displays them (review finding D3).
ACCEPTED_CLAIM_FRAMING = "The gates' disposition: hard gates outrank everything shown."
DIRECTIONAL_PERMISSION_FRAMING = (
    "The gates' disposition, with an accepted directional permission for this model and "
    "timeframe. Not financial advice: it never tells you to trade, and hard gates outrank "
    "everything shown."
)
_STATE_FRAMING = {
    "ACCEPTED_FORECAST_CLAIM": ACCEPTED_CLAIM_FRAMING,
    "DIRECTIONAL_PERMISSION": DIRECTIONAL_PERMISSION_FRAMING,
}


def hard_blocks(gate: Mapping[str, Any]) -> list[str]:
    return [str(block) for block in gate.get("hard_blocks") or []]


def _kind(block: str, liquidity: Any) -> str:
    if block in EVIDENCE_GATE_BLOCKS:
        return "EVIDENCE"
    if block == LIQUIDITY_BLOCK:
        return "RISK" if liquidity_was_measured(liquidity) else "SYSTEM_OR_DATA"
    return "RISK" if block in RISK_GATE_BLOCKS else "SYSTEM_OR_DATA"


def _headline(block: str, liquidity: Any) -> str:
    if block in EVIDENCE_GATE_BLOCKS:
        return EVIDENCE_GATE_HEADLINE
    return blocking_reason(block, liquidity)[0]


def _of_kind(gate: Mapping[str, Any], liquidity: Any, kind: str) -> list[str]:
    return [block for block in hard_blocks(gate) if _kind(block, liquidity) == kind]


def risk_gate_active(gate: Mapping[str, Any], liquidity: Any) -> bool:
    """Whether a named risk gate reports a measured finding. The gates' own `risk_guard_applied`
    flag is not enough: it is also set by the liquidity gate on a missing order book."""

    return bool(_of_kind(gate, liquidity, "RISK"))


def hard_gate_active(gate: Mapping[str, Any]) -> bool:
    return (
        bool(gate.get("hard_blocks"))
        or gate.get("hard_gate_passed") is False
        or str(gate.get("action") or "").startswith("ABORT")
    )


def elevated_risk_is_a_risk_finding(
    gate: Mapping[str, Any], score: Mapping[str, Any], liquidity: Any
) -> bool:
    """Whether the score's ELEVATED_RISK_AVOID is a risk reading.

    It is when a risk gate with a measured finding forced it, or when no gate forced it and the
    score produced it. It is not when the evidence gate forced it, or the liquidity gate on missing
    data: both overwrite the score's own disposition without a finding about the market.
    """

    if str(score.get("disposition") or "") != ELEVATED_RISK_TOKEN:
        return False
    forced = gate.get("skill_guard_applied") is True or gate.get("risk_guard_applied") is True
    return risk_gate_active(gate, liquidity) or not forced


def elevated_risk_not_forced_by_a_risk_gate(
    gate: Mapping[str, Any], score: Mapping[str, Any], liquidity: Any
) -> bool:
    return str(
        score.get("disposition") or ""
    ) == ELEVATED_RISK_TOKEN and not elevated_risk_is_a_risk_finding(gate, score, liquidity)


def _names(blocks: list[str], liquidity: Any) -> str:
    return "; ".join(_headline(block, liquidity) for block in blocks)


def hard_gate_summary(gate: Mapping[str, Any], liquidity: Any) -> str:
    """One or two sentences naming each kind of hard gate that is active."""

    risk = _of_kind(gate, liquidity, "RISK")
    other = _of_kind(gate, liquidity, "SYSTEM_OR_DATA")
    evidence = _of_kind(gate, liquidity, "EVIDENCE")
    parts = []
    if risk:
        parts.append(f"A risk gate is active: {_names(risk, liquidity)}.")
    if other:
        parts.append(f"A system or data gate is active: {_names(other, liquidity)}.")
    if evidence and parts:
        parts.append(f"The evidence gate is active too: {EVIDENCE_GATE_COPY}.")
    elif evidence:
        parts.append(f"Evidence gate: {EVIDENCE_GATE_COPY}. No risk gate is active.")
    if parts:
        return " ".join(parts)
    return UNNAMED_HARD_GATE if hard_gate_active(gate) else NO_HARD_GATE


def gate_framing(gate: Mapping[str, Any], liquidity: Any, state: str | None = None) -> str:
    """The one sentence that says how to read the gates. A risk gate's finding is named, whatever
    the state; otherwise an accepted state frames its gates, and anything else is no market call.
    `state` is the decision view's (a reopened run has none)."""

    risk = _of_kind(gate, liquidity, "RISK")
    if risk:
        template = RISK_FRAMING_ONE if len(risk) == 1 else RISK_FRAMING_SEVERAL
        return template.format(names=_names(risk, liquidity))
    return _STATE_FRAMING.get(state or "", NOT_A_MARKET_CALL)


def build_gate_view(
    gate: Mapping[str, Any], *, liquidity: Any = None, state: str | None = None
) -> dict[str, Any]:
    """The gate framing of one analysis: a pure function of its gate result, the liquidity state
    its liquidity gate judged, and the decision view's state where there is one."""

    blocks = hard_blocks(gate)
    return {
        "schema_version": SCHEMA_VERSION,
        "blocked": hard_gate_active(gate),
        "kinds": sorted({_kind(block, liquidity) for block in blocks}),
        "blocks": [
            {
                "block": block,
                "kind": _kind(block, liquidity),
                "headline": _headline(block, liquidity),
            }
            for block in blocks
        ],
        "risk_gate_active": risk_gate_active(gate, liquidity),
        "summary": hard_gate_summary(gate, liquidity),
        "framing": gate_framing(gate, liquidity, state),
    }


def _stored_liquidity(detail: Mapping[str, Any]) -> Any:
    """The liquidity state a saved run stores (detail/builder.py), or None."""

    stored = detail.get("liquidity_execution_detail")
    return stored.get("liquidity_state") if isinstance(stored, Mapping) else None


def attach_gate_view(detail: Any) -> Any:
    """A run's detail as it is read back, with its gate framing built now from the gate result
    (`invalidation_detail`) and the liquidity state it stores. The stored detail is not changed,
    and a detail without a gate result is returned as it is.

    It never raises: reading a saved run must not fail on what an old or damaged row holds (review
    finding D5). A gate result is framed when its `hard_blocks` is a list of block names, as the
    gates have always written it, or is absent or None, which reads as no blocks. Any other shape
    is returned as it is, without a framing: a framing built from it could contradict the record.
    """

    try:
        if not isinstance(detail, Mapping):
            return detail
        gate = detail.get("invalidation_detail")
        if not isinstance(gate, Mapping):
            return detail
        blocks = gate.get("hard_blocks")
        if blocks is not None and not (
            isinstance(blocks, list) and all(isinstance(block, str) for block in blocks)
        ):
            return detail
        view = build_gate_view(gate, liquidity=_stored_liquidity(detail))
        return {**detail, "gate_view": view}
    except Exception:
        return detail
