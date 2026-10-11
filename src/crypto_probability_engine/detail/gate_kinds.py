"""The one authority for what the hard gates mean (owner rulings CLASS-B-4=A and AD1=A, 2026-10-10;
governing plan §14.1: missing evidence must never render as a negative market signal).

The gates are unchanged (gates/composite.py). They report three kinds of hard block:
- a risk gate: a finding about the market or its execution (liquidity, tail risk, execution cost);
- a system or data gate: the kill switch, shelter mode, a degraded provider, insufficient inputs;
- the evidence gate: directional skill is not established for this model and timeframe. It says
  what is not yet known about the model, never anything about the market.

The evidence gate forces the same action and the same score token as a risk gate (NO_TRADE,
ELEVATED_RISK_AVOID). Those tokens stay. `build_gate_view` turns a gate result into the gate
framing every surface shows: the kinds, each block, one summary and one framing sentence.

It is a pure function of the gate result, and every saved run stores its gate result. So the
framing of a reopened run is built when it is read (`attach_gate_view`), never stored: an old run
and a new one read the same, and a wording change needs no stored text rewritten. No field here is
named with "code", "key", "hash" or "token", which utils/sanitize.py masks in a stored payload.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crypto_probability_engine.detail.frontend_display import blocking_headline

SCHEMA_VERSION = "gate_view.v1"
RISK_GATE_BLOCKS = frozenset(
    {"LIQUIDITY_NOT_VIABLE", "TAIL_RISK_BREACH", "EXECUTION_COST_TOO_HIGH"}
)
EVIDENCE_GATE_BLOCKS = frozenset({"SKILL_NOT_DEMONSTRATED"})
ELEVATED_RISK_TOKEN = "ELEVATED_RISK_AVOID"
EVIDENCE_GATE_COPY = "directional skill is not established for this model and timeframe"
EVIDENCE_GATE_HEADLINE = "Directional skill is not established"
NOT_FORCED_BY_A_RISK_GATE = "not forced by a risk gate"
UNNAMED_HARD_GATE = "One or more hard gates are active."
NO_HARD_GATE = "No hard gate is active."
RISK_FRAMING = (
    "This is a finding about market conditions or execution. It is analysis only, not an "
    "instruction."
)
NOT_A_MARKET_CALL = (
    "The gates' disposition, not a market call: a gate outcome is not a forecast to act on."
)


def hard_blocks(gate: Mapping[str, Any]) -> list[str]:
    return [str(block) for block in gate.get("hard_blocks") or []]


def risk_gate_active(gate: Mapping[str, Any]) -> bool:
    return gate.get("risk_guard_applied") is True or bool(RISK_GATE_BLOCKS & set(hard_blocks(gate)))


def hard_gate_active(gate: Mapping[str, Any]) -> bool:
    return (
        bool(gate.get("hard_blocks"))
        or gate.get("hard_gate_passed") is False
        or str(gate.get("action") or "").startswith("ABORT")
    )


def elevated_risk_is_a_risk_finding(gate: Mapping[str, Any], score: Mapping[str, Any]) -> bool:
    """Whether the score's ELEVATED_RISK_AVOID is a risk reading.

    It is when a risk gate forced it, or when no gate forced it and the score produced it. It is
    not when the evidence gate forced it: that gate overwrites the score's own disposition.
    """

    if str(score.get("disposition") or "") != ELEVATED_RISK_TOKEN:
        return False
    return risk_gate_active(gate) or gate.get("skill_guard_applied") is not True


def elevated_risk_forced_by_evidence(gate: Mapping[str, Any], score: Mapping[str, Any]) -> bool:
    return str(
        score.get("disposition") or ""
    ) == ELEVATED_RISK_TOKEN and not elevated_risk_is_a_risk_finding(gate, score)


def _kind(block: str) -> str:
    if block in RISK_GATE_BLOCKS:
        return "RISK"
    if block in EVIDENCE_GATE_BLOCKS:
        return "EVIDENCE"
    return "SYSTEM_OR_DATA"


def hard_gate_summary(gate: Mapping[str, Any]) -> str:
    """One or two sentences naming each kind of hard gate that is active."""

    blocks = hard_blocks(gate)
    risk = [block for block in blocks if _kind(block) == "RISK"]
    other = [block for block in blocks if _kind(block) == "SYSTEM_OR_DATA"]
    evidence = [block for block in blocks if _kind(block) == "EVIDENCE"]
    parts = []
    if risk:
        parts.append(f"A risk gate is active: {_names(risk)}.")
    if other:
        parts.append(f"A system or data gate is active: {_names(other)}.")
    if evidence and parts:
        parts.append(f"The evidence gate is active too: {EVIDENCE_GATE_COPY}.")
    elif evidence:
        parts.append(f"Evidence gate: {EVIDENCE_GATE_COPY}. No risk gate is active.")
    if parts:
        return " ".join(parts)
    return UNNAMED_HARD_GATE if hard_gate_active(gate) else NO_HARD_GATE


def build_gate_view(gate: Mapping[str, Any]) -> dict[str, Any]:
    """The gate framing of one analysis: a pure function of its gate result."""

    blocks = hard_blocks(gate)
    risk = risk_gate_active(gate)
    return {
        "schema_version": SCHEMA_VERSION,
        "blocked": hard_gate_active(gate),
        "kinds": sorted({_kind(block) for block in blocks}),
        "blocks": [
            {
                "block": block,
                "kind": _kind(block),
                "headline": EVIDENCE_GATE_HEADLINE
                if _kind(block) == "EVIDENCE"
                else blocking_headline(block),
            }
            for block in blocks
        ],
        "risk_gate_active": risk,
        "summary": hard_gate_summary(gate),
        "framing": RISK_FRAMING if risk else NOT_A_MARKET_CALL,
    }


def attach_gate_view(detail: Any) -> Any:
    """A run's detail as it is read back, with its gate framing built now from the gate result it
    stores (`invalidation_detail`). The stored detail is not changed, and a detail without a gate
    result is returned as it is."""

    if not isinstance(detail, Mapping):
        return detail
    gate = detail.get("invalidation_detail")
    if not isinstance(gate, Mapping):
        return detail
    return {**detail, "gate_view": build_gate_view(gate)}


def _names(blocks: list[str]) -> str:
    return "; ".join(blocking_headline(block) for block in blocks)
