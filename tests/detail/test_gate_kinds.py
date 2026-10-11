"""The one gate authority (detail/gate_kinds.py; owner rulings CLASS-B-4=A, AD1=A, G2; governing
plan §14.1: missing evidence must never render as a negative market signal).

The backend's sentences say which kind of hard gate is active. The evidence gate is never described
as elevated risk, and neither is a gate that fired because data are missing. A risk gate's framing
names the gate it is about. The gates themselves are untouched: every action, block and score token
is what it was.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest

from crypto_probability_engine.adapters.types import OrderBookLevel, OrderBookSnapshot
from crypto_probability_engine.detail import decision_view, gate_kinds
from crypto_probability_engine.detail.decision_brief import _key_reasons, _state_summary
from crypto_probability_engine.detail.decision_synthesis import _plan_disabled_reason
from crypto_probability_engine.execution_realism.realism import compute_execution_realism
from crypto_probability_engine.features.liquidity_depth import compute_liquidity_depth
from crypto_probability_engine.gates import composite
from crypto_probability_engine.gates.composite import apply_composite_gates
from tests.api.test_analysis_endpoints import login, make_client
from tests.fixtures.market_data import FIXED_NOW, make_order_book

ROOT = Path(__file__).resolve().parents[2]
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
TAIL_FRAMING = (
    "The risk gate (Extreme-move risk is too high) is a finding about market conditions or "
    "execution. It is analysis only, not an instruction."
)
UNMEASURED = "A system or data gate is active: Liquidity could not be measured."
# Wording that calls something a finding about the market.
MARKET_FINDING = ("risk gate", "finding", "market conditions", "not viable")


def _book(bid: float, ask: float, size: float = 2.0) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        bids=(OrderBookLevel(price=bid, size=size),),
        asks=(OrderBookLevel(price=ask, size=size),),
        as_of_utc=FIXED_NOW,
    )


# The liquidity states the real feature returns (features/liquidity_depth.py): a book that is
# measured and fine, measured and too wide, measured and too thin, missing, and unusable.
LIQUID = compute_liquidity_depth(make_order_book())
WIDE = compute_liquidity_depth(_book(100.0, 110.0))
THIN = compute_liquidity_depth(_book(120.0, 120.5, size=0.1))
NO_BOOK = compute_liquidity_depth(None)
CROSSED = compute_liquidity_depth(_book(10.0, 100.0))
MEASURED = (WIDE, THIN)
UNMEASURED_STATES = (NO_BOOK, CROSSED)


def _gate(liquidity: dict | None = None, **states: object) -> dict:
    """A real gate result (gates/composite.py) for the liquidity state the pipeline would give it,
    with the execution state the pipeline derives from that liquidity."""

    if liquidity is not None:
        states = {
            "liquidity_state": liquidity,
            "execution_state": compute_execution_realism(liquidity),
            **states,
        }
    return apply_composite_gates(
        epistemic_state={"action": "ALLOW"},
        provider_state={"status": "OK"},
        score_state={"disposition": "WATCH"},
        **states,
    )


def _score(gate: dict, own: str = "WATCH") -> dict:
    return {"disposition": gate.get("forced_score_disposition") or own}


def _view(liquidity: dict | None = None, *, state: str | None = None, **states: object) -> dict:
    return gate_kinds.build_gate_view(_gate(liquidity, **states), liquidity=liquidity, state=state)


def test_the_liquidity_states_are_what_their_names_say() -> None:
    assert LIQUID["status"] == WIDE["status"] == THIN["status"] == "OK"
    assert WIDE["spread_frac"] > 0.01 > LIQUID["spread_frac"] == THIN["spread_frac"]
    assert THIN["top_depth_quote"] < 100.0 < LIQUID["top_depth_quote"]
    for state in UNMEASURED_STATES:
        assert state["status"] == "DEGRADED" and state["spread_frac"] is None
    assert NO_BOOK["warning"] == "Order book unavailable."
    assert CROSSED["warning"] == "Order-book spread is outside bounded fraction range."
    # Each of the four blocks the liquidity gate, and the fine book does not.
    for state in (*MEASURED, *UNMEASURED_STATES):
        assert "LIQUIDITY_NOT_VIABLE" in _gate(state, skill_state=SKILL)["hard_blocks"]
    assert _gate(LIQUID, skill_state=SKILL)["hard_blocks"] == []


def test_the_gates_tokens_are_what_they_were() -> None:
    evidence = _gate(skill_state=NO_SKILL)
    assert evidence["action"] == "NO_TRADE"
    assert evidence["hard_blocks"] == ["SKILL_NOT_DEMONSTRATED"]
    assert evidence["forced_score_disposition"] == "ELEVATED_RISK_AVOID"
    assert evidence["skill_guard_applied"] is True and evidence["risk_guard_applied"] is False
    risk = _gate(skill_state=NO_SKILL, tail_risk_state=TAIL_BREACH)
    assert risk["action"] == "NO_TRADE" and risk["risk_guard_applied"] is True
    assert risk["hard_blocks"] == ["TAIL_RISK_BREACH", "SKILL_NOT_DEMONSTRATED"]
    # A missing order book is the same block, action and forced token as a measured one.
    for liquidity in (NO_BOOK, THIN):
        gate = _gate(liquidity, skill_state=NO_SKILL)
        assert gate["hard_blocks"] == ["LIQUIDITY_NOT_VIABLE", "SKILL_NOT_DEMONSTRATED"]
        assert gate["action"] == "NO_TRADE" and gate["risk_guard_applied"] is True
        assert gate["forced_score_disposition"] == "ELEVATED_RISK_AVOID"


def test_the_risk_kind_is_exactly_what_the_risk_viability_check_can_return() -> None:
    every_risk_block = composite._risk_viability_blocks(
        {"status": "DEGRADED", "spread_frac": None, "top_depth_quote": 0.0},
        TAIL_BREACH,
        {"round_trip_cost_frac": 1.0},
    )
    assert set(every_risk_block) == gate_kinds.RISK_GATE_BLOCKS
    assert gate_kinds.LIQUIDITY_BLOCK in gate_kinds.RISK_GATE_BLOCKS
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
    assert gate_kinds.hard_gate_summary(_gate(**states), None) == sentence
    assert gate_kinds.hard_gate_summary(_gate(**states), LIQUID) == sentence


def test_only_the_evidence_gate_alone_says_no_risk_gate_is_active() -> None:
    for states in (
        {"skill_state": NO_SKILL, "tail_risk_state": TAIL_BREACH},
        {"skill_state": NO_SKILL, "kill_switch": True},
        {"skill_state": SKILL, "tail_risk_state": TAIL_BREACH},
    ):
        assert "No risk gate is active" not in gate_kinds.hard_gate_summary(_gate(**states), None)
    assert gate_kinds.hard_gate_summary({"hard_gate_passed": False}, None) == (
        "One or more hard gates are active."
    )
    assert gate_kinds.hard_gate_summary({"hard_blocks": ["A_NEW_BLOCK"]}, None) == (
        "A system or data gate is active: A_NEW_BLOCK."
    )
    assert gate_kinds.hard_gate_summary({"hard_gate_passed": True}, None) == (
        "No hard gate is active."
    )


# --- D2 (owner ruling G2): missing data is not a proven market risk --------------------------


@pytest.mark.parametrize("liquidity", MEASURED)
def test_a_measured_liquidity_block_is_a_risk_gate(liquidity: dict) -> None:
    assert gate_kinds.liquidity_was_measured(liquidity) is True
    view = _view(liquidity, skill_state=NO_SKILL)
    blocks = {entry["block"]: entry for entry in view["blocks"]}
    assert blocks["LIQUIDITY_NOT_VIABLE"] == {
        "block": "LIQUIDITY_NOT_VIABLE",
        "kind": "RISK",
        "headline": "Liquidity is not viable",
    }
    assert view["risk_gate_active"] is True and "RISK" in view["kinds"]
    assert (
        "Liquidity is not viable" in view["summary"]
        and "Liquidity is not viable" in (view["framing"])
    )
    assert view["summary"].startswith("A risk gate is active: ")


@pytest.mark.parametrize("liquidity", UNMEASURED_STATES)
def test_a_liquidity_block_on_missing_data_is_a_data_gate_and_claims_no_finding(
    liquidity: dict,
) -> None:
    assert gate_kinds.liquidity_was_measured(liquidity) is False
    view = _view(liquidity, skill_state=NO_SKILL)
    assert view["blocks"][0] == {
        "block": "LIQUIDITY_NOT_VIABLE",
        "kind": "SYSTEM_OR_DATA",
        "headline": "Liquidity could not be measured",
    }
    assert view["kinds"] == ["EVIDENCE", "SYSTEM_OR_DATA"]
    assert view["risk_gate_active"] is False
    assert view["summary"] == f"{UNMEASURED} {EVIDENCE_TOO}"
    assert view["framing"] == gate_kinds.NOT_A_MARKET_CALL
    # Alone (SYNTHETIC: the evidence gate lifted), it reads the same and still claims nothing.
    alone = _view(liquidity, skill_state=SKILL)
    assert alone["summary"] == UNMEASURED and alone["kinds"] == ["SYSTEM_OR_DATA"]
    for text in (view["summary"], view["framing"], alone["summary"], alone["framing"]):
        assert not any(word in text.lower() for word in MARKET_FINDING), text


def test_a_measured_risk_gate_beside_missing_liquidity_data_is_still_the_only_risk_gate() -> None:
    view = _view(NO_BOOK, skill_state=NO_SKILL, tail_risk_state=TAIL_BREACH)
    assert [(entry["block"], entry["kind"]) for entry in view["blocks"]] == [
        ("LIQUIDITY_NOT_VIABLE", "SYSTEM_OR_DATA"),
        ("TAIL_RISK_BREACH", "RISK"),
        ("SKILL_NOT_DEMONSTRATED", "EVIDENCE"),
    ]
    assert view["summary"] == (
        f"A risk gate is active: Extreme-move risk is too high. {UNMEASURED} {EVIDENCE_TOO}"
    )
    assert view["framing"] == TAIL_FRAMING, "the framing names the measured gate only"


@pytest.mark.parametrize(
    "liquidity",
    [
        None,
        {},
        "OK",
        {"status": "OK"},
        {"status": "OK", "spread_frac": None},
        {"status": "OK", "spread_frac": "0.004"},
        {"status": "OK", "spread_frac": True},
        {"status": "DEGRADED", "spread_frac": 0.004},
        {"spread_frac": 0.004},
    ],
)
def test_a_liquidity_state_that_proves_no_measurement_never_reads_as_a_finding(
    liquidity: object,
) -> None:
    """Absent, unreadable or half a state: the block is worded as missing data, never as risk."""

    assert gate_kinds.liquidity_was_measured(liquidity) is False
    gate = {"hard_blocks": ["LIQUIDITY_NOT_VIABLE"], "hard_gate_passed": False}
    view = gate_kinds.build_gate_view(gate, liquidity=liquidity)
    assert view["summary"] == UNMEASURED and view["risk_gate_active"] is False


def test_the_blocking_reason_copy_says_missing_data_and_claims_no_finding() -> None:
    """The backend's own blocking-reason copy (`frontend_display.blocking_reasons`) is worded at
    the same source: on a missing order book it says data are missing, never that liquidity does
    not meet the bar."""

    from crypto_probability_engine.detail import frontend_display

    measured = (
        "Liquidity is not viable",
        "Analysis is blocked because current liquidity does not meet the required bar.",
    )
    unmeasured = (
        "Liquidity could not be measured",
        "Analysis is blocked because the order-book data needed to measure liquidity are "
        "unavailable or unusable. This is missing data, not a finding about the market.",
    )
    for liquidity in MEASURED:
        assert frontend_display.blocking_reason("LIQUIDITY_NOT_VIABLE", liquidity) == measured
    for liquidity in (*UNMEASURED_STATES, None, {}):
        assert frontend_display.blocking_reason("LIQUIDITY_NOT_VIABLE", liquidity) == unmeasured
    for word in MARKET_FINDING:
        if word != "finding":  # it says, in so many words, that this is not a finding
            assert word not in " ".join(unmeasured).lower(), word
    assert "not a finding about the market" in unmeasured[1]
    # Every other block reads as it did, whatever the liquidity state; an unknown one as itself.
    for liquidity in (None, NO_BOOK, LIQUID):
        assert frontend_display.blocking_reason("TAIL_RISK_BREACH", liquidity) == (
            "Extreme-move risk is too high",
            "Analysis is blocked because extreme-move risk exceeds the permitted level.",
        )
        assert frontend_display.blocking_reason("A_NEW_BLOCK", liquidity) == (
            "A_NEW_BLOCK",
            "This is a hard gate, but its description is unavailable.",
        )
    # The payload's list carries it, beside the evidence gate's own reason.
    quant = {
        "probability_state": {
            "horizons": {"H_primary": {"p_up_frac": 0.4, "p_down_frac": 0.3, "p_timeout_frac": 0.3}}
        },
        "score_stack": {"total_score": 50, "disposition": "ELEVATED_RISK_AVOID"},
        "execution_realism": {},
    }
    news = {"news_addon_state": {}}
    horizon = dict.fromkeys(
        (
            "timeframe_label",
            "horizon_label",
            "horizon_bars",
            "horizon_approx_label",
            "probability_explanation",
            "uncalibrated_banner",
            "model_readiness_label",
        ),
        "x",
    )
    for liquidity, copy in ((NO_BOOK, unmeasured), (THIN, measured)):
        display = frontend_display.build_frontend_display(
            {
                **quant,
                "gate_result": _gate(liquidity, skill_state=NO_SKILL),
                "liquidity_state": liquidity,
            },
            news,
            "METRICS_ONLY",
            {},
            horizon,
            skill_evidence=NO_SKILL,
        )
        first, second = display["blocking_reasons"]
        assert first == {"code": "LIQUIDITY_NOT_VIABLE", "headline": copy[0], "detail": copy[1]}
        assert second["code"] == "SKILL_NOT_DEMONSTRATED"
        # The raw block codes beside it are the gates' own, unchanged.
        assert display["key_reasons"] == ["LIQUIDITY_NOT_VIABLE", "SKILL_NOT_DEMONSTRATED"]


def test_the_other_risk_gates_are_always_measured() -> None:
    """A tail-risk breach and an execution cost need a number above their threshold to block: no
    missing input fires them (gates/composite.py), so they never depend on the liquidity state."""

    for liquidity in (None, NO_BOOK, LIQUID):
        for block in ("TAIL_RISK_BREACH", "EXECUTION_COST_TOO_HIGH"):
            view = gate_kinds.build_gate_view({"hard_blocks": [block]}, liquidity=liquidity)
            assert view["kinds"] == ["RISK"] and view["risk_gate_active"] is True
    # Without an order book the execution state holds no cost above the gate's threshold.
    assert "EXECUTION_COST_TOO_HIGH" not in _gate(NO_BOOK, skill_state=SKILL)["hard_blocks"]
    assert _gate(tail_risk_state={}, skill_state=SKILL)["hard_blocks"] == []


def test_the_gates_own_risk_flag_is_not_a_risk_gate() -> None:
    """`risk_guard_applied` is also set by the liquidity gate on a missing order book, so the
    authority reads the named blocks, never the flag."""

    missing = _gate(NO_BOOK, skill_state=NO_SKILL)
    assert missing["risk_guard_applied"] is True
    assert gate_kinds.risk_gate_active(missing, NO_BOOK) is False
    assert gate_kinds.risk_gate_active({"risk_guard_applied": True, "hard_blocks": []}, None) is (
        False
    )
    assert gate_kinds.risk_gate_active({"hard_blocks": ["TAIL_RISK_BREACH"]}, None) is True
    assert gate_kinds.risk_gate_active({"hard_blocks": ["SKILL_NOT_DEMONSTRATED"]}, LIQUID) is (
        False
    )


# --- D1: the risk framing names the gate it is about -----------------------------------------


def test_the_risk_framing_names_its_gate_beside_any_other_gate() -> None:
    alone = _view(skill_state=SKILL, tail_risk_state=TAIL_BREACH)
    with_evidence = _view(skill_state=NO_SKILL, tail_risk_state=TAIL_BREACH)
    with_all = _view(skill_state=NO_SKILL, tail_risk_state=TAIL_BREACH, kill_switch=True)
    for view in (alone, with_evidence, with_all):
        assert view["framing"] == TAIL_FRAMING
        assert not view["framing"].startswith("This "), "a sentence without a subject"
    # Each risk gate that is active is named, in the gates' own order, and the grammar agrees.
    two = _view(WIDE, skill_state=NO_SKILL)
    assert [entry["block"] for entry in two["blocks"]] == [
        "EXECUTION_COST_TOO_HIGH",
        "LIQUIDITY_NOT_VIABLE",
        "SKILL_NOT_DEMONSTRATED",
    ]
    assert two["framing"] == (
        "The risk gates (Execution cost is too high; Liquidity is not viable) are findings about "
        "market conditions or execution. They are analysis only, not an instruction."
    )
    assert two["summary"] == (
        "A risk gate is active: Execution cost is too high; Liquidity is not viable. "
        f"{EVIDENCE_TOO}"
    )
    # The framing names exactly the gates the summary calls risk gates.
    for view in (alone, with_evidence, with_all, two):
        named = view["summary"].split("A risk gate is active: ")[1].split(".")[0]
        assert f"({named})" in view["framing"]
    assert "act or to avoid acting" not in TAIL_FRAMING


# --- D3: the framing of every state is the backend's own sentence ----------------------------


def test_the_framing_is_worded_here_for_every_state() -> None:
    blocked = _gate(skill_state=NO_SKILL)
    clear = _gate(skill_state=SKILL)
    framing = gate_kinds.gate_framing
    for state in (None, "NO_ACCEPTED_CLAIM", "INVALID_OR_UNAVAILABLE_DATA", "ANOTHER_STATE"):
        assert framing(blocked, None, state) == gate_kinds.NOT_A_MARKET_CALL
        assert framing(clear, None, state) == gate_kinds.NOT_A_MARKET_CALL
    assert framing(blocked, None, "ACCEPTED_FORECAST_CLAIM") == (
        "The gates' disposition: hard gates outrank everything shown."
    )
    assert framing(clear, None, "DIRECTIONAL_PERMISSION") == (
        "The gates' disposition, with an accepted directional permission for this model and "
        "timeframe. Not financial advice: it never tells you to trade, and hard gates outrank "
        "everything shown."
    )
    # A risk gate's finding is named whatever the state.
    risk = _gate(skill_state=NO_SKILL, tail_risk_state=TAIL_BREACH)
    for state in (None, "NO_ACCEPTED_CLAIM", "ACCEPTED_FORECAST_CLAIM"):
        assert framing(risk, None, state) == TAIL_FRAMING
    assert "not a market call" not in gate_kinds.ACCEPTED_CLAIM_FRAMING
    assert "not a market call" not in gate_kinds.DIRECTIONAL_PERMISSION_FRAMING
    assert "Not financial advice" in gate_kinds.DIRECTIONAL_PERMISSION_FRAMING


# --- the forced token --------------------------------------------------------------------------


def test_elevated_risk_is_a_risk_finding_only_from_a_risk_gate_or_the_score_itself() -> None:
    finding = gate_kinds.elevated_risk_is_a_risk_finding
    not_forced = gate_kinds.elevated_risk_not_forced_by_a_risk_gate
    evidence = _gate(skill_state=NO_SKILL)
    assert finding(evidence, _score(evidence), LIQUID) is False
    assert not_forced(evidence, _score(evidence), LIQUID) is True
    kill = _gate(skill_state=NO_SKILL, kill_switch=True)
    assert finding(kill, _score(kill), LIQUID) is False
    risk = _gate(skill_state=NO_SKILL, tail_risk_state=TAIL_BREACH)
    assert finding(risk, _score(risk), LIQUID) is True
    risk_alone = _gate(skill_state=SKILL, tail_risk_state=TAIL_BREACH)
    assert finding(risk_alone, _score(risk_alone), LIQUID) is True
    clear = _gate(skill_state=SKILL)
    assert finding(clear, _score(clear, own="ELEVATED_RISK_AVOID"), LIQUID) is True, (
        "the score's own"
    )
    assert finding(clear, _score(clear), LIQUID) is False
    for gate in (evidence, risk, clear):
        other = {"disposition": "WATCH"}
        assert not_forced(gate, other, LIQUID) is False
    # The liquidity gate on missing data forces the token too, and is no risk finding: with the
    # evidence gate, and alone (SYNTHETIC).
    for skill in (NO_SKILL, SKILL):
        missing = _gate(NO_BOOK, skill_state=skill)
        assert _score(missing) == {"disposition": "ELEVATED_RISK_AVOID"}
        assert finding(missing, _score(missing), NO_BOOK) is False
        assert not_forced(missing, _score(missing), NO_BOOK) is True
        measured = _gate(THIN, skill_state=skill)
        assert finding(measured, _score(measured), THIN) is True
        assert not_forced(measured, _score(measured), THIN) is False


def test_the_plan_is_not_called_elevated_risk_by_the_evidence_gate_or_by_missing_data() -> None:
    block = {"plain_english": EVIDENCE_SENTENCE}
    for gate, liquidity in (
        (_gate(skill_state=NO_SKILL), LIQUID),
        (_gate(NO_BOOK, skill_state=NO_SKILL), NO_BOOK),
    ):
        risk = gate_kinds.elevated_risk_is_a_risk_finding(gate, _score(gate), liquidity)
        reason = _plan_disabled_reason(
            plan_status="DISABLED",
            elevated_risk=risk,
            insufficient_history=False,
            dominant_block=block,
        )
        assert reason == EVIDENCE_SENTENCE
    risk = _gate(skill_state=NO_SKILL, tail_risk_state=TAIL_BREACH)
    reason = _plan_disabled_reason(
        plan_status="DISABLED",
        elevated_risk=gate_kinds.elevated_risk_is_a_risk_finding(risk, _score(risk), LIQUID),
        insufficient_history=False,
        dominant_block=block,
    )
    assert reason == "The elevated-risk disposition disables scenario planning."


def test_the_brief_keeps_the_token_and_says_when_no_risk_gate_forced_it() -> None:
    horizon = {"horizon_approx_label": "1H setup / ~6H horizon"}

    def brief(gate: dict, liquidity: dict) -> tuple[str, list[str]]:
        note = gate_kinds.elevated_risk_not_forced_by_a_risk_gate(gate, _score(gate), liquidity)
        summary = _state_summary(
            action="NO_TRADE",
            normalized_symbol="BTC/USDT",
            horizon=horizon,
            gate=gate,
            score=_score(gate),
            not_forced_by_a_risk_gate=note,
        )
        reasons = _key_reasons(
            action="NO_TRADE",
            gate=gate,
            score=_score(gate),
            data_quality={},
            hard_blockers=list(gate["hard_blocks"]),
            not_forced_by_a_risk_gate=note,
        )
        return summary, reasons

    summary, reasons = brief(_gate(skill_state=NO_SKILL), LIQUID)
    assert summary == (
        "BTC/USDT is classified as NO_TRADE for 1H setup / ~6H horizon using an uncalibrated "
        "heuristic. Gate action is NO_TRADE and backend disposition is ELEVATED_RISK_AVOID (not "
        "forced by a risk gate)."
    )
    assert "Hard gate blockers present: SKILL_NOT_DEMONSTRATED." in reasons
    assert "Backend disposition: ELEVATED_RISK_AVOID (not forced by a risk gate)." in reasons
    # Missing liquidity data forced it: no risk gate did.
    summary, reasons = brief(_gate(NO_BOOK, skill_state=NO_SKILL), NO_BOOK)
    assert summary.endswith("disposition is ELEVATED_RISK_AVOID (not forced by a risk gate).")
    assert "Backend disposition: ELEVATED_RISK_AVOID (not forced by a risk gate)." in reasons
    # A risk gate with a measured finding forced it: the token stands alone.
    for gate, liquidity in (
        (_gate(skill_state=NO_SKILL, tail_risk_state=TAIL_BREACH), LIQUID),
        (_gate(THIN, skill_state=NO_SKILL), THIN),
    ):
        summary, reasons = brief(gate, liquidity)
        assert summary.endswith("and backend disposition is ELEVATED_RISK_AVOID.")
        assert "Backend disposition: ELEVATED_RISK_AVOID." in reasons


# --- the gate view -----------------------------------------------------------------------------


def test_the_gate_view_is_a_pure_function_of_the_gate_result_and_its_liquidity_state() -> None:
    evidence = _view(skill_state=NO_SKILL)
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
    risk = _view(skill_state=NO_SKILL, tail_risk_state=TAIL_BREACH)
    assert risk["kinds"] == ["EVIDENCE", "RISK"] and risk["risk_gate_active"] is True
    assert risk["framing"] == TAIL_FRAMING
    assert risk["blocks"][0] == {
        "block": "TAIL_RISK_BREACH",
        "kind": "RISK",
        "headline": "Extreme-move risk is too high",
    }
    kill = _view(skill_state=SKILL, kill_switch=True)
    assert kill["kinds"] == ["SYSTEM_OR_DATA"] and kill["framing"] == gate_kinds.NOT_A_MARKET_CALL
    clear = _view(skill_state=SKILL)
    assert clear["blocked"] is False and clear["blocks"] == [] and clear["kinds"] == []
    assert clear["summary"] == "No hard gate is active."
    assert clear["framing"] == gate_kinds.NOT_A_MARKET_CALL
    # Nothing given is changed, and the same facts give the same view.
    gate, liquidity = _gate(NO_BOOK, skill_state=NO_SKILL), dict(NO_BOOK)
    before = (deepcopy(gate), deepcopy(liquidity))
    first = gate_kinds.build_gate_view(gate, liquidity=liquidity)
    assert (gate, liquidity) == before
    assert gate_kinds.build_gate_view(gate, liquidity=liquidity) == first


def test_no_gate_view_field_is_named_as_the_sanitizer_masks() -> None:
    from crypto_probability_engine.utils.sanitize import sanitize_for_export

    view = _view(skill_state=NO_SKILL, tail_risk_state=TAIL_BREACH)
    assert sanitize_for_export({"gate_view": view})["gate_view"] == view
    # The liquidity state a saved run stores survives the sanitizer whole, so the read path
    # classifies the liquidity gate as the live path did.
    for liquidity in (LIQUID, WIDE, THIN, NO_BOOK, CROSSED):
        stored = sanitize_for_export({"liquidity_execution_detail": {"liquidity_state": liquidity}})
        assert stored["liquidity_execution_detail"]["liquidity_state"] == liquidity


# --- D6: the schema, and its version ---------------------------------------------------------


def _schema() -> dict:
    return json.loads((ROOT / "schemas" / "response.schema.json").read_text(encoding="utf-8"))


def test_the_strict_schema_requires_the_gate_block_and_validates_a_built_one() -> None:
    view = _schema()["$defs"]["decisionView"]
    assert "gates" in view["required"]
    gates = view["properties"]["gates"]
    assert gates["additionalProperties"] is False
    built = _view(skill_state=NO_SKILL)
    assert set(gates["required"]) == set(gates["properties"]) == set(built)
    block = gates["properties"]["blocks"]["items"]
    assert block["additionalProperties"] is False
    assert set(block["required"]) == set(block["properties"]) == set(built["blocks"][0])
    assert gates["properties"]["schema_version"] == {"const": gate_kinds.SCHEMA_VERSION}
    for liquidity, states in (
        (None, {"skill_state": NO_SKILL}),
        (None, {"skill_state": SKILL, "kill_switch": True}),
        (NO_BOOK, {"skill_state": NO_SKILL}),
        (WIDE, {"skill_state": NO_SKILL, "tail_risk_state": TAIL_BREACH}),
        (None, {"skill_state": SKILL}),
    ):
        for state in (None, "ACCEPTED_FORECAST_CLAIM", "DIRECTIONAL_PERMISSION"):
            jsonschema.validate(_view(liquidity, state=state, **states), gates)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**built, "advice": "x"}, gates)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**built, "kinds": ["MARKET"]}, gates)


def test_a_view_with_the_gate_block_is_a_new_version_of_the_view() -> None:
    """The gate block is a required field of the view, so the view's version moved with it
    (review finding D6). The schema names one version, as it always has, and a view stamped with
    the version before is refused, with the block or without it."""

    assert decision_view.SCHEMA_VERSION == "decision_view.v2"
    view = _schema()["$defs"]["decisionView"]
    assert view["properties"]["schema_version"] == {"const": "decision_view.v2"}
    assert view["additionalProperties"] is False
    from scripts.ux_comprehension import card

    _, built = card.build(card.SCENARIOS[0])
    assert built["schema_version"] == "decision_view.v2" and "gates" in built
    validator = jsonschema.Draft202012Validator(view)
    assert not list(validator.iter_errors(built))
    before = {**built, "schema_version": "decision_view.v1"}
    assert list(validator.iter_errors(before)), "the old version with the new field"
    without = {key: value for key, value in before.items() if key != "gates"}
    assert list(validator.iter_errors(without)), "the old version as it was"
    missing = {key: value for key, value in built.items() if key != "gates"}
    assert list(validator.iter_errors(missing)), "the new version without its gate block"


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
    assert view["gates"]["framing"] == TAIL_FRAMING


# --- D5: reading a saved run back ------------------------------------------------------------


def _stored(gate: object, liquidity: object = LIQUID) -> dict:
    return {
        "run_id": "run-old",
        "invalidation_detail": gate,
        "liquidity_execution_detail": {"liquidity_state": liquidity},
        "decision_brief": {"state_summary": "old"},
    }


def test_a_reopened_run_gets_its_framing_from_the_facts_it_stores() -> None:
    gate = _gate(skill_state=NO_SKILL)
    stored = _stored(dict(gate))
    read = gate_kinds.attach_gate_view(stored)
    assert read["gate_view"] == gate_kinds.build_gate_view(gate, liquidity=LIQUID)
    assert "gate_view" not in stored, "the stored detail is not changed"
    assert read["decision_brief"] is stored["decision_brief"]
    for without in ({"decision_brief": {}}, {"invalidation_detail": None}, None, "text"):
        assert gate_kinds.attach_gate_view(without) is without


@pytest.mark.parametrize("liquidity", [LIQUID, WIDE, THIN, NO_BOOK, CROSSED])
@pytest.mark.parametrize("skill", [NO_SKILL, SKILL])
def test_a_saved_run_is_framed_as_the_live_analysis_was(liquidity: dict, skill: dict) -> None:
    """The stored liquidity state decides the liquidity gate's kind when a run is read back, as
    the live one did: a saved run and a live one read the same (no state: a saved run has none)."""

    gate = _gate(liquidity, skill_state=skill)
    read = gate_kinds.attach_gate_view(json.loads(json.dumps(_stored(gate, liquidity))))
    assert read["gate_view"] == gate_kinds.build_gate_view(gate, liquidity=liquidity)
    measured = liquidity in MEASURED
    assert read["gate_view"]["risk_gate_active"] is measured
    # A record that lost its liquidity state proves no measurement: never a finding.
    lost = _stored(gate, liquidity)
    del lost["liquidity_execution_detail"]
    if "LIQUIDITY_NOT_VIABLE" in gate["hard_blocks"]:
        view = gate_kinds.attach_gate_view(lost)["gate_view"]
        assert "Liquidity could not be measured" in view["summary"]
        assert "Liquidity is not viable" not in view["summary"] + view["framing"]


# What a stored `invalidation_detail` can hold that is not a gate result as the gates write it.
# Framed anyway, a number or a boolean for `hard_blocks` would raise (the detail route would answer
# 500), and a string would read as one block a character: a framing that contradicts the record.
# An absent or None `hard_blocks` is not among them: it reads as no blocks.
MALFORMED_GATE_RESULTS = [
    pytest.param(5, id="a-number"),
    pytest.param(True, id="a-boolean"),
    pytest.param("NO_TRADE", id="a-string"),
    pytest.param(["TAIL_RISK_BREACH"], id="a-list"),
    pytest.param({"hard_blocks": 5, "hard_gate_passed": False}, id="hard-blocks-a-number"),
    pytest.param({"hard_blocks": True}, id="hard-blocks-a-boolean"),
    pytest.param({"hard_blocks": "TAIL_RISK_BREACH"}, id="hard-blocks-a-string"),
    pytest.param({"hard_blocks": {"TAIL_RISK_BREACH": True}}, id="hard-blocks-a-mapping"),
    pytest.param({"hard_blocks": 0, "hard_gate_passed": False}, id="hard-blocks-zero"),
    pytest.param({"hard_blocks": False}, id="hard-blocks-false"),
    pytest.param({"hard_blocks": ""}, id="hard-blocks-an-empty-string"),
    pytest.param({"hard_blocks": {}}, id="hard-blocks-an-empty-mapping"),
    pytest.param({"hard_blocks": [None]}, id="a-none-entry"),
    pytest.param({"hard_blocks": ["TAIL_RISK_BREACH", 7]}, id="a-number-entry"),
    pytest.param({"hard_blocks": [["TAIL_RISK_BREACH"]]}, id="a-list-entry"),
    pytest.param({"hard_blocks": [{"block": "TAIL_RISK_BREACH"}]}, id="a-mapping-entry"),
    pytest.param(
        {"hard_blocks": 5, "action": None, "added_later": {"deep": [None, 1.5]}},
        id="none-values-and-extra-keys",
    ),
]
# A gate result with no `hard_blocks`, or with None there: no blocks.
NO_BLOCKS_GATE_RESULTS = [
    pytest.param({}, id="an-empty-gate-result"),
    pytest.param({"hard_blocks": None}, id="hard-blocks-none"),
    pytest.param({"hard_gate_passed": True, "action": "ALLOW"}, id="absent-and-passed"),
    pytest.param({"hard_gate_passed": False}, id="absent-and-not-passed"),
    pytest.param({"hard_blocks": None, "hard_gate_passed": False}, id="none-and-not-passed"),
    pytest.param({"action": "ABORT"}, id="absent-and-aborted"),
    pytest.param({"hard_blocks": None, "risk_guard_applied": True}, id="none-and-a-risk-guard"),
    pytest.param(
        {"action": None, "forced_score_disposition": None, "added_later": {"deep": [None, 1.5]}},
        id="absent-with-none-values-and-extra-keys",
    ),
]
# What a stored `liquidity_execution_detail` can hold that is not what the builder writes.
MALFORMED_LIQUIDITY = [None, 5, "x", [], {"liquidity_state": 5}, {"liquidity_state": ["OK"]}]


@pytest.mark.parametrize("gate", NO_BLOCKS_GATE_RESULTS)
def test_an_absent_or_none_hard_blocks_is_framed_as_no_blocks(gate: dict) -> None:
    stored = _stored(gate)
    before = deepcopy(stored)
    read = gate_kinds.attach_gate_view(stored)
    assert stored == before and read is not stored
    view = read["gate_view"]
    assert view == gate_kinds.build_gate_view(gate, liquidity=LIQUID)
    assert view["blocks"] == [] and view["kinds"] == [] and view["risk_gate_active"] is False
    # No block is named, so no risk gate is: the gates' flag alone words no finding.
    assert view["framing"] == gate_kinds.NOT_A_MARKET_CALL
    blocked = gate.get("hard_gate_passed") is False or gate.get("action") == "ABORT"
    assert view["blocked"] is blocked
    assert view["summary"] == (gate_kinds.UNNAMED_HARD_GATE if blocked else gate_kinds.NO_HARD_GATE)


@pytest.mark.parametrize("gate", MALFORMED_GATE_RESULTS)
def test_a_malformed_stored_gate_result_is_read_back_unchanged_and_unframed(
    gate: object,
) -> None:
    stored = _stored(gate)
    before = deepcopy(stored)
    read = gate_kinds.attach_gate_view(stored)
    assert read is stored and stored == before
    assert "gate_view" not in read


@pytest.mark.parametrize("liquidity", MALFORMED_LIQUIDITY)
def test_a_malformed_stored_liquidity_state_never_fails_and_never_words_a_finding(
    liquidity: object,
) -> None:
    gate = _gate(THIN, skill_state=NO_SKILL)
    stored = {"invalidation_detail": gate, "liquidity_execution_detail": liquidity}
    view = gate_kinds.attach_gate_view(stored)["gate_view"]
    assert view["summary"] == f"{UNMEASURED} {EVIDENCE_TOO}"
    assert view["risk_gate_active"] is False


def test_a_tuple_of_blocks_is_not_a_stored_list_of_blocks() -> None:
    stored = {"invalidation_detail": {"hard_blocks": ("TAIL_RISK_BREACH",)}}
    assert gate_kinds.attach_gate_view(stored) is stored
    empty = {"invalidation_detail": {"hard_blocks": ()}}
    assert gate_kinds.attach_gate_view(empty) is empty, "only absent and None read as no blocks"


@pytest.mark.parametrize("detail", [None, 5, 1.5, True, "text", b"bytes", [], [{}], object()])
def test_a_detail_that_is_not_a_mapping_is_returned_as_it_is(detail: object) -> None:
    assert gate_kinds.attach_gate_view(detail) is detail


def test_reading_never_raises_even_when_the_framing_itself_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Unreadable(dict):
        def get(self, *_args: object) -> object:
            raise RuntimeError("unreadable")

    unreadable = Unreadable(invalidation_detail=_gate(skill_state=NO_SKILL))
    assert gate_kinds.attach_gate_view(unreadable) is unreadable
    nested = {"invalidation_detail": Unreadable(hard_blocks=[])}
    assert gate_kinds.attach_gate_view(nested) is nested
    liquidity = {
        "invalidation_detail": _gate(skill_state=NO_SKILL),
        "liquidity_execution_detail": Unreadable(liquidity_state=LIQUID),
    }
    assert gate_kinds.attach_gate_view(liquidity) is liquidity

    def failing(*_args: object, **_facts: object) -> dict:
        raise RuntimeError("framing failed")

    monkeypatch.setattr(gate_kinds, "build_gate_view", failing)
    stored = _stored(_gate(skill_state=NO_SKILL))
    assert gate_kinds.attach_gate_view(stored) is stored


class _Durable:
    """A durable store holding one run, as a stored JSON row reads back."""

    def __init__(self, stored: dict) -> None:
        self.stored = stored

    def get_run_detail(self, run_id: str, *, prediction_origin: str) -> dict | None:
        del prediction_origin
        return json.loads(json.dumps(self.stored)) if run_id == "durable-run" else None


@pytest.mark.parametrize("gate", MALFORMED_GATE_RESULTS)
def test_the_detail_route_answers_a_malformed_stored_run_as_it_is_stored(gate: object) -> None:
    stored = {**_stored(gate), "run_id": "durable-run"}
    client = make_client()
    client.app.state.persistence_repository = _Durable(stored)
    login(client)
    response = client.get("/v1/analyze/detail/durable-run")
    assert response.status_code == 200
    assert response.json() == stored
    assert "gate_view" not in response.json()


@pytest.mark.parametrize("gate", NO_BLOCKS_GATE_RESULTS)
def test_the_detail_route_frames_a_stored_run_whose_gate_result_has_no_hard_blocks(
    gate: dict,
) -> None:
    stored = {**_stored(gate), "run_id": "durable-run"}
    client = make_client()
    client.app.state.persistence_repository = _Durable(stored)
    login(client)
    response = client.get("/v1/analyze/detail/durable-run")
    assert response.status_code == 200
    expected = gate_kinds.build_gate_view(gate, liquidity=LIQUID)
    assert response.json() == {**stored, "gate_view": expected}
