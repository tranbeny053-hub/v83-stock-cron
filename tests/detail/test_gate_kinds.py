"""Owner ruling CLASS-B-4=A (2026-10-10): the backend's sentences say which kind of hard gate is
active, so the evidence gate is never described as elevated risk (governing plan §14.1). The gates
themselves are untouched: every action, block and score token is what it was.
"""

from __future__ import annotations

import pytest

from crypto_probability_engine.detail import gate_kinds
from crypto_probability_engine.detail.decision_brief import _key_reasons, _state_summary
from crypto_probability_engine.detail.decision_synthesis import _plan_disabled_reason
from crypto_probability_engine.gates import composite
from crypto_probability_engine.gates.composite import apply_composite_gates

NO_SKILL = {"verdict": "INSUFFICIENT_EVIDENCE", "n": 0}
SKILL = {"verdict": "SKILL_DEMONSTRATED", "n": 400}
TAIL_BREACH = {"cvar_loss": 0.9, "cvar_breach_threshold": 0.1}
EVIDENCE_SENTENCE = (
    "Evidence gate: directional skill is not established for this model and timeframe. No risk "
    "gate is active."
)
EVIDENCE_TOO = (
    "The evidence gate is active too: directional skill is not established for this model and "
    "timeframe."
)


def _gate(**states: object) -> dict:
    """A real gate result (gates/composite.py), with the score the pipeline and the service leave
    beside it: the gate's forced disposition, or the score's own."""

    return apply_composite_gates(
        epistemic_state={"action": "ALLOW"},
        provider_state={"status": "OK"},
        score_state={"disposition": "WATCH"},
        **states,
    )


def _score(gate: dict, own: str = "WATCH") -> dict:
    return {"disposition": gate.get("forced_score_disposition") or own}


def test_the_gates_tokens_are_what_they_were() -> None:
    evidence = _gate(skill_state=NO_SKILL)
    assert evidence["action"] == "NO_TRADE"
    assert evidence["hard_blocks"] == ["SKILL_NOT_DEMONSTRATED"]
    assert evidence["forced_score_disposition"] == "ELEVATED_RISK_AVOID"
    assert evidence["skill_guard_applied"] is True and evidence["risk_guard_applied"] is False
    risk = _gate(skill_state=NO_SKILL, tail_risk_state=TAIL_BREACH)
    assert risk["action"] == "NO_TRADE" and risk["risk_guard_applied"] is True
    assert risk["hard_blocks"] == ["TAIL_RISK_BREACH", "SKILL_NOT_DEMONSTRATED"]


def test_the_risk_kind_is_exactly_what_the_risk_viability_check_can_return() -> None:
    every_risk_block = composite._risk_viability_blocks(
        {"status": "DEGRADED", "spread_frac": None, "top_depth_quote": 0.0},
        TAIL_BREACH,
        {"round_trip_cost_frac": 1.0},
    )
    assert set(every_risk_block) == gate_kinds.RISK_GATE_BLOCKS
    assert gate_kinds.EVIDENCE_GATE_BLOCKS == {"SKILL_NOT_DEMONSTRATED"}
    assert not gate_kinds.RISK_GATE_BLOCKS & gate_kinds.EVIDENCE_GATE_BLOCKS


@pytest.mark.parametrize(
    ("states", "sentence"),
    [
        ({"skill_state": NO_SKILL}, EVIDENCE_SENTENCE),
        (
            {"skill_state": NO_SKILL, "tail_risk_state": TAIL_BREACH},
            f"A risk gate is active: Extreme-move risk is too high. {EVIDENCE_TOO}",
        ),
        (
            {"skill_state": SKILL, "tail_risk_state": TAIL_BREACH},
            "A risk gate is active: Extreme-move risk is too high.",
        ),
        (
            {"skill_state": NO_SKILL, "kill_switch": True},
            f"A system or data gate is active: Safety shutdown is active. {EVIDENCE_TOO}",
        ),
        (
            {"skill_state": SKILL, "kill_switch": True, "shelter_mode": True},
            "A system or data gate is active: Safety shutdown is active; Protective mode is "
            "active.",
        ),
        (
            {
                "skill_state": NO_SKILL,
                "tail_risk_state": TAIL_BREACH,
                "kill_switch": True,
            },
            "A risk gate is active: Extreme-move risk is too high. A system or data gate is "
            f"active: Safety shutdown is active. {EVIDENCE_TOO}",
        ),
    ],
)
def test_the_summary_names_each_kind_of_gate(states: dict, sentence: str) -> None:
    assert gate_kinds.hard_gate_summary(_gate(**states)) == sentence


def test_only_the_evidence_gate_alone_says_no_risk_gate_is_active() -> None:
    for states in (
        {"skill_state": NO_SKILL, "tail_risk_state": TAIL_BREACH},
        {"skill_state": NO_SKILL, "kill_switch": True},
        {"skill_state": SKILL, "tail_risk_state": TAIL_BREACH},
    ):
        assert "No risk gate is active" not in gate_kinds.hard_gate_summary(_gate(**states))
    assert gate_kinds.hard_gate_summary({"hard_gate_passed": False}) == (
        "One or more hard gates are active."
    )
    assert gate_kinds.hard_gate_summary({"hard_blocks": ["A_NEW_BLOCK"]}) == (
        "A system or data gate is active: A_NEW_BLOCK."
    )
    assert gate_kinds.hard_gate_summary({"hard_gate_passed": True}) == "No hard gate is active."


def test_a_risk_gate_is_recognised_by_its_flag_or_by_its_block() -> None:
    assert gate_kinds.risk_gate_active({"risk_guard_applied": True, "hard_blocks": []}) is True
    assert gate_kinds.risk_gate_active({"hard_blocks": ["TAIL_RISK_BREACH"]}) is True
    assert gate_kinds.risk_gate_active({"hard_blocks": ["SKILL_NOT_DEMONSTRATED"]}) is False
    assert gate_kinds.risk_gate_active({"risk_guard_applied": "yes", "hard_blocks": []}) is False


def test_elevated_risk_is_a_risk_finding_only_from_a_risk_gate_or_the_score_itself() -> None:
    finding = gate_kinds.elevated_risk_is_a_risk_finding
    evidence = _gate(skill_state=NO_SKILL)
    assert finding(evidence, _score(evidence)) is False
    assert gate_kinds.elevated_risk_forced_by_evidence(evidence, _score(evidence)) is True
    kill = _gate(skill_state=NO_SKILL, kill_switch=True)
    assert finding(kill, _score(kill)) is False
    risk = _gate(skill_state=NO_SKILL, tail_risk_state=TAIL_BREACH)
    assert finding(risk, _score(risk)) is True
    risk_alone = _gate(skill_state=SKILL, tail_risk_state=TAIL_BREACH)
    assert finding(risk_alone, _score(risk_alone)) is True
    clear = _gate(skill_state=SKILL)
    assert finding(clear, _score(clear, own="ELEVATED_RISK_AVOID")) is True, "the score's own"
    assert finding(clear, _score(clear)) is False
    for gate in (evidence, risk, clear):
        other = {"disposition": "WATCH"}
        assert gate_kinds.elevated_risk_forced_by_evidence(gate, other) is False


def test_the_plan_is_not_called_elevated_risk_by_the_evidence_gate() -> None:
    block = {"plain_english": EVIDENCE_SENTENCE}
    evidence = _gate(skill_state=NO_SKILL)
    reason = _plan_disabled_reason(
        plan_status="DISABLED",
        elevated_risk=gate_kinds.elevated_risk_is_a_risk_finding(evidence, _score(evidence)),
        insufficient_history=False,
        dominant_block=block,
    )
    assert reason == EVIDENCE_SENTENCE
    risk = _gate(skill_state=NO_SKILL, tail_risk_state=TAIL_BREACH)
    reason = _plan_disabled_reason(
        plan_status="DISABLED",
        elevated_risk=gate_kinds.elevated_risk_is_a_risk_finding(risk, _score(risk)),
        insufficient_history=False,
        dominant_block=block,
    )
    assert reason == "The elevated-risk disposition disables scenario planning."


def test_the_brief_keeps_the_token_and_says_which_gate_forced_it() -> None:
    horizon = {"horizon_approx_label": "1H setup / ~6H horizon"}
    evidence = _gate(skill_state=NO_SKILL)
    summary = _state_summary(
        action="NO_TRADE",
        normalized_symbol="BTC/USDT",
        horizon=horizon,
        gate=evidence,
        score=_score(evidence),
    )
    assert summary == (
        "BTC/USDT is classified as NO_TRADE for 1H setup / ~6H horizon using an uncalibrated "
        "heuristic. Gate action is NO_TRADE and backend disposition is ELEVATED_RISK_AVOID (not "
        "forced by a risk gate)."
    )
    reasons = _key_reasons(
        action="NO_TRADE",
        gate=evidence,
        score=_score(evidence),
        data_quality={},
        hard_blockers=list(evidence["hard_blocks"]),
    )
    assert "Hard gate blockers present: SKILL_NOT_DEMONSTRATED." in reasons
    assert "Backend disposition: ELEVATED_RISK_AVOID (not forced by a risk gate)." in reasons

    risk = _gate(skill_state=NO_SKILL, tail_risk_state=TAIL_BREACH)
    summary = _state_summary(
        action="NO_TRADE",
        normalized_symbol="BTC/USDT",
        horizon=horizon,
        gate=risk,
        score=_score(risk),
    )
    assert summary.endswith("and backend disposition is ELEVATED_RISK_AVOID.")
    reasons = _key_reasons(
        action="NO_TRADE",
        gate=risk,
        score=_score(risk),
        data_quality={},
        hard_blockers=list(risk["hard_blocks"]),
    )
    assert "Backend disposition: ELEVATED_RISK_AVOID." in reasons


def test_the_gate_view_is_a_pure_function_of_the_gate_result() -> None:
    evidence = gate_kinds.build_gate_view(_gate(skill_state=NO_SKILL))
    assert evidence == {
        "schema_version": "gate_view.v1",
        "blocked": True,
        "kinds": ["EVIDENCE"],
        "blocks": [
            {
                "block": "SKILL_NOT_DEMONSTRATED",
                "kind": "EVIDENCE",
                "headline": "Directional skill is not established",
            }
        ],
        "risk_gate_active": False,
        "summary": EVIDENCE_SENTENCE,
        "framing": gate_kinds.NOT_A_MARKET_CALL,
    }
    risk = gate_kinds.build_gate_view(_gate(skill_state=NO_SKILL, tail_risk_state=TAIL_BREACH))
    assert risk["kinds"] == ["EVIDENCE", "RISK"] and risk["risk_gate_active"] is True
    assert risk["framing"] == gate_kinds.RISK_FRAMING
    assert "act or to avoid acting" not in risk["framing"]
    assert risk["blocks"][0] == {
        "block": "TAIL_RISK_BREACH",
        "kind": "RISK",
        "headline": "Extreme-move risk is too high",
    }
    kill = gate_kinds.build_gate_view(_gate(skill_state=SKILL, kill_switch=True))
    assert kill["kinds"] == ["SYSTEM_OR_DATA"] and kill["framing"] == gate_kinds.NOT_A_MARKET_CALL
    clear = gate_kinds.build_gate_view(_gate(skill_state=SKILL))
    assert clear["blocked"] is False and clear["blocks"] == [] and clear["kinds"] == []
    assert clear["summary"] == "No hard gate is active."


def test_no_gate_view_field_is_named_as_the_sanitizer_masks() -> None:
    from crypto_probability_engine.utils.sanitize import sanitize_for_export

    view = gate_kinds.build_gate_view(_gate(skill_state=NO_SKILL, tail_risk_state=TAIL_BREACH))
    assert sanitize_for_export({"gate_view": view})["gate_view"] == view


def test_a_reopened_run_gets_its_framing_from_the_gate_result_it_stores() -> None:
    gate = _gate(skill_state=NO_SKILL)
    stored = {"invalidation_detail": dict(gate), "decision_brief": {"state_summary": "old"}}
    read = gate_kinds.attach_gate_view(stored)
    assert read["gate_view"] == gate_kinds.build_gate_view(gate)
    assert "gate_view" not in stored, "the stored detail is not changed"
    assert read["decision_brief"] is stored["decision_brief"]
    for without in ({"decision_brief": {}}, {"invalidation_detail": None}, None, "text"):
        assert gate_kinds.attach_gate_view(without) is without


def test_the_strict_schema_requires_the_gate_block_and_validates_a_built_one() -> None:
    import json
    from pathlib import Path

    import jsonschema

    root = Path(__file__).resolve().parents[2]
    schema = json.loads((root / "schemas" / "response.schema.json").read_text(encoding="utf-8"))
    view = schema["$defs"]["decisionView"]
    assert "gates" in view["required"]
    gates = view["properties"]["gates"]
    assert gates["additionalProperties"] is False
    assert (
        set(gates["required"])
        == set(gates["properties"])
        == set(gate_kinds.build_gate_view(_gate(skill_state=NO_SKILL)))
    )
    for states in ({"skill_state": NO_SKILL}, {"skill_state": SKILL, "kill_switch": True}):
        jsonschema.validate(gate_kinds.build_gate_view(_gate(**states)), gates)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**gate_kinds.build_gate_view(_gate()), "advice": "x"}, gates)


def test_an_accepted_claim_keeps_its_own_sentence_under_a_risk_gate() -> None:
    """SYNTHETIC (both registries are empty): the sentence that drops "no reason to act or to
    avoid acting" under a risk gate is the no-accepted-claim one only."""

    from crypto_probability_engine.detail.decision_view import STATE_COPY
    from scripts.ux_comprehension import card

    accepted = card.Scenario("X", "accepted", True, True, True, False, True, "NO_TRADE", risk=True)
    _, view = card.build(accepted)
    assert view["state"] == "ACCEPTED_FORECAST_CLAIM"
    assert view["gates"]["risk_gate_active"] is True
    assert view["detail"] == STATE_COPY["ACCEPTED_FORECAST_CLAIM"][1]
