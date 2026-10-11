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
# The liquidity gate's detail when no order book reached the measure, and when one was served
# and the measure refused it (review finding 2: the first sentence is false for the second).
NO_BOOK_DETAIL = (
    "Analysis is blocked because the order-book data needed to measure liquidity are "
    "unavailable. This is missing data, not a finding about the market."
)
UNUSABLE_BOOK_DETAIL = (
    "Analysis is blocked because the order book that was served has a spread outside the range "
    "the liquidity measure accepts, so liquidity was not measured from it: this is unusable data, "
    "not a finding about the market."
)
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
        "detail": "Analysis is blocked because current liquidity does not meet the required bar.",
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
        "detail": NO_BOOK_DETAIL if liquidity is NO_BOOK else UNUSABLE_BOOK_DETAIL,
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
    assert "not a finding about the market" in view["blocks"][0]["detail"]


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
    unmeasured = ("Liquidity could not be measured", NO_BOOK_DETAIL)
    unusable = ("Liquidity could not be measured", UNUSABLE_BOOK_DETAIL)
    for liquidity in MEASURED:
        assert frontend_display.blocking_reason("LIQUIDITY_NOT_VIABLE", liquidity) == measured
    for liquidity in (NO_BOOK, None, {}, "x", {"status": "DEGRADED"}):
        assert frontend_display.blocking_reason("LIQUIDITY_NOT_VIABLE", liquidity) == unmeasured
    assert frontend_display.blocking_reason("LIQUIDITY_NOT_VIABLE", CROSSED) == unusable
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


def test_a_served_order_book_that_cannot_be_used_is_not_called_missing() -> None:
    """Review finding 2. A book whose ask is more than three times its bid passes validation, and
    the liquidity measure refuses to compute a spread from it: the state then holds the book's
    best bid and ask and no spread. The screen must not say the data are missing (they were
    served), and must not claim a finding about the market either (owner ruling G2)."""

    from crypto_probability_engine.detail import frontend_display

    served = frontend_display.order_book_was_served
    assert (CROSSED["best_bid"], CROSSED["best_ask"]) == (10.0, 100.0)
    assert CROSSED["spread_frac"] is None and CROSSED["status"] == "DEGRADED"
    assert served(CROSSED) is True and served(LIQUID) is True and served(WIDE) is True
    for state in (NO_BOOK, None, {}, "x", 5, {"best_bid": 10.0}, {"best_ask": 100.0}):
        assert served(state) is False, state
    for state in ({"best_bid": "10", "best_ask": 100.0}, {"best_bid": True, "best_ask": False}):
        assert served(state) is False, state
    view = _view(CROSSED, skill_state=NO_SKILL)
    entry = view["blocks"][0]
    assert (entry["kind"], entry["headline"]) == (
        "SYSTEM_OR_DATA",
        "Liquidity could not be measured",
    )
    assert entry["detail"] == UNUSABLE_BOOK_DETAIL
    assert "missing" not in entry["detail"] and "unavailable" not in entry["detail"]
    assert "not a finding about the market" in entry["detail"]
    assert entry["detail"].count(".") == 1, "one sentence"
    assert view["risk_gate_active"] is False and view["framing"] == gate_kinds.NOT_A_MARKET_CALL
    # With no book the sentence says missing data, and does not say a book was served.
    missing = _view(NO_BOOK, skill_state=NO_SKILL)["blocks"][0]["detail"]
    assert missing == NO_BOOK_DETAIL and "was served" not in missing


def _check_6(gate: dict, liquidity: object, execution: object) -> dict:
    """The stack's "Liquidity and execution" check, from the real builder."""

    from crypto_probability_engine.detail import decision_synthesis

    stack = decision_synthesis._actionability_stack(
        label="NO_TRADE",
        gate=gate,
        data_quality={},
        provider_state={},
        epistemic={},
        probability={},
        quant_result={"liquidity_state": liquidity, "execution_realism": execution},
        reliability_status="INSUFFICIENT_SAMPLE",
    )
    (check,) = [item for item in stack if item["key"] == "liquidity_execution"]
    assert check["label"] == "Liquidity and execution" and check["priority"] == 6
    return check


@pytest.mark.parametrize(
    ("name", "liquidity", "blocks", "sentence"),
    [
        ("no book", NO_BOOK, ["LIQUIDITY_NOT_VIABLE"], "Liquidity could not be measured."),
        ("an unusable book", CROSSED, ["LIQUIDITY_NOT_VIABLE"], "Liquidity could not be measured."),
        ("too thin, measured", THIN, ["LIQUIDITY_NOT_VIABLE"], "Liquidity is not viable."),
        (
            "execution cost too high",
            LIQUID,
            ["EXECUTION_COST_TOO_HIGH"],
            "Execution cost is too high.",
        ),
        (
            "a too-wide measured spread: both",
            WIDE,
            ["EXECUTION_COST_TOO_HIGH", "LIQUIDITY_NOT_VIABLE"],
            "Execution cost is too high; Liquidity is not viable.",
        ),
    ],
)
def test_the_liquidity_check_says_what_the_gate_authority_says_when_it_blocks(
    name: str, liquidity: dict, blocks: list[str], sentence: str
) -> None:
    """Review finding 1 (the class-B line). Under BLOCK the check printed the two states' status
    words: "DEGRADED" for an order book that was never measured, and "OK" beside a measured spread
    that is too wide. When it blocks on the liquidity or the execution-cost gate, its sentence is
    now the gate authority's own headlines for those blocks, so it can never disagree with it."""

    execution = compute_execution_realism(liquidity)
    gate = {"hard_blocks": [*blocks, "SKILL_NOT_DEMONSTRATED"], "hard_gate_passed": False}
    if name != "execution cost too high":  # the one case the real gates cannot give alone
        real = _gate(liquidity, skill_state=NO_SKILL)
        assert real["hard_blocks"] == gate["hard_blocks"], name
    check = _check_6(gate, liquidity, execution)
    assert (check["status"], check["plain_english"]) == ("BLOCK", sentence), name
    # The same headlines, in the same order, as the authority's summary and gate list.
    view = gate_kinds.build_gate_view(gate, liquidity=liquidity)
    named = "; ".join(entry["headline"] for entry in view["blocks"] if entry["block"] in blocks)
    assert check["plain_english"] == f"{named}."
    assert f": {named}." in view["summary"]
    for word in ("DEGRADED", " is OK", "status"):
        assert word not in check["plain_english"], (name, word)


def test_the_liquidity_check_keeps_its_status_sentence_when_neither_gate_blocks() -> None:
    for gate in (
        _gate(LIQUID, skill_state=NO_SKILL),
        _gate(LIQUID, skill_state=SKILL),
        _gate(LIQUID, skill_state=NO_SKILL, tail_risk_state=TAIL_BREACH, kill_switch=True),
    ):
        check = _check_6(gate, LIQUID, compute_execution_realism(LIQUID))
        assert (check["status"], check["plain_english"]) == (
            "PASS",
            "Liquidity is OK; execution realism is OK.",
        )
    # A state that is not OK without the gate's block (no gate result names it): a warning, and
    # the status words stay: there is no headline of the authority to use.
    warned = _check_6({"hard_blocks": []}, NO_BOOK, compute_execution_realism(NO_BOOK))
    assert (warned["status"], warned["plain_english"]) == (
        "WARN",
        "Liquidity is DEGRADED; execution realism is DEGRADED.",
    )
    unknown = _check_6({"hard_blocks": []}, {}, {})
    assert (unknown["status"], unknown["plain_english"]) == (
        "UNKNOWN",
        "Liquidity is UNKNOWN; execution realism is UNKNOWN.",
    )


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
                "headline": "Evidence gate",
                "detail": "Directional skill is not established for this model and timeframe.",
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
        "detail": "Analysis is blocked because extreme-move risk exceeds the permitted level.",
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


def test_each_active_gate_carries_its_headline_and_its_detail_sentence() -> None:
    """The parity review's first item: the older gate brief alone printed each gate's detail
    sentence. The authority lists them now. A hard block other than the evidence gate reads as the
    backend's blocking-reason copy reads it; the evidence gate reads as its fixed sentence, never
    the skill verdict or its counts, so a saved run and a live one read the same."""

    from crypto_probability_engine.detail import frontend_display

    view = _view(WIDE, skill_state=NO_SKILL, tail_risk_state=TAIL_BREACH, kill_switch=True)
    assert [entry["block"] for entry in view["blocks"]] == [
        "KILL_SWITCH",
        "EXECUTION_COST_TOO_HIGH",
        "LIQUIDITY_NOT_VIABLE",
        "TAIL_RISK_BREACH",
        "SKILL_NOT_DEMONSTRATED",
    ]
    for entry in view["blocks"][:-1]:
        assert (entry["headline"], entry["detail"]) == frontend_display.blocking_reason(
            entry["block"], WIDE
        )
        assert entry["detail"].startswith("Analysis is blocked ")
    evidence = view["blocks"][-1]
    assert (evidence["headline"], evidence["detail"]) == (
        "Evidence gate",
        "Directional skill is not established for this model and timeframe.",
    )
    assert evidence["detail"] == f"D{gate_kinds.EVIDENCE_GATE_COPY[1:]}."
    # Whatever the skill evidence said, the evidence gate's entry is the same sentence.
    for verdict in ("INSUFFICIENT_EVIDENCE", "NO_DEMONSTRATED_SKILL", None):
        other = _view(skill_state={"verdict": verdict, "n": 250})
        assert other["blocks"] == [
            {
                "block": "SKILL_NOT_DEMONSTRATED",
                "kind": "EVIDENCE",
                **dict(headline="Evidence gate", detail=evidence["detail"]),
            }
        ]
        for entry in other["blocks"]:
            assert "250" not in entry["detail"] and str(verdict) not in entry["detail"]
    unknown = gate_kinds.build_gate_view({"hard_blocks": ["A_NEW_BLOCK"]})["blocks"][0]
    assert unknown["detail"] == "This is a hard gate, but its description is unavailable."


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

    payload, _ = card.build(card.SCENARIOS[0])
    built = payload["decision_view"]
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

    accepted = card.Scenario("X", "accepted", True, accepted=True, tail=True)
    payload, _ = card.build(accepted)
    view = payload["decision_view"]
    assert view["state"] == "ACCEPTED_FORECAST_CLAIM"
    assert view["gates"]["risk_gate_active"] is True
    assert view["detail"] == STATE_COPY["ACCEPTED_FORECAST_CLAIM"][1]
    assert view["gates"]["framing"] == TAIL_FRAMING
