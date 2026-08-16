from __future__ import annotations

from crypto_probability_engine.gates.composite import apply_composite_gates


def _apply(verdict: str, *, epistemic_action: str = "ALLOW") -> dict:
    return apply_composite_gates(
        epistemic_state={"action": epistemic_action},
        provider_state={"status": "OK"},
        score_state={"disposition": "CONSTRUCTIVE_CAUTIOUS", "total_score": 99},
        skill_state={
            "verdict": verdict,
            "n": 100,
            "observed_directional_rate": 0.5,
        },
    )


def test_skill_gate_is_hard_and_outranks_score_and_news() -> None:
    gate = _apply("NO_DEMONSTRATED_SKILL")

    assert gate["action"] == "NO_TRADE"
    assert gate["hard_gate_passed"] is False
    assert gate["hard_blocks"] == ["SKILL_NOT_DEMONSTRATED"]
    assert gate["score_ignored"] is True
    assert gate["news_ignored"] is True
    assert gate["forced_score_disposition"] == "ELEVATED_RISK_AVOID"


def test_demonstrated_skill_leaves_score_disposition_authoritative() -> None:
    gate = _apply("SKILL_DEMONSTRATED")

    assert gate["action"] == "CONSTRUCTIVE_CAUTIOUS"
    assert gate["hard_gate_passed"] is True
    assert gate["hard_blocks"] == []
    assert gate["score_ignored"] is False


def test_existing_hard_gate_action_keeps_seniority_over_skill_gate() -> None:
    gate = _apply("NO_DEMONSTRATED_SKILL", epistemic_action="ABORT")

    assert gate["action"] == "ABORT"
    assert gate["hard_blocks"] == ["EPISTEMIC_VOID", "SKILL_NOT_DEMONSTRATED"]
    assert gate["forced_score_disposition"] == "ELEVATED_RISK_AVOID"
