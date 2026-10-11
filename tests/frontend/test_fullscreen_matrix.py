"""The full-screen regression matrix (owner rulings AD1=A, AD2=read time, AD3: the provisional
regression contract of the class-B architecture package, section 6; not release acceptance).

The real backend builds each analysis and the real app.js renders it. Every line a user can read is
checked, on every surface, in every scenario:
- Single (the timeframe card), Batch (the batch card), Detail (the detail panel) and History (the
  detail panel of a saved run, read back with its gate framing built at read time);
- the evidence gate alone, a risk gate with it, a risk gate alone, the kill switch with it, a system
  gate alone, and the two accepted states. Scenarios marked SYNTHETIC cannot occur today.

The contract: one gate authority. The same summary and framing on every surface; missing evidence
never worded as risk; a real risk gate never worded as "no reason to act or to avoid acting"; the
forced token never shown alone; a saved run framed from its stored gate result, not from its stored
sentences. Every gate token stays what it was.

The analyses and the screens are the whole-screen goldens' own (fullscreen_goldens.py): one
builder, so the lines read here are the lines pinned there.

The saved/unsaved receipt (owner D4) exists, and by design it is not in the analyze response: it is
a separate endpoint, which the screen asks after showing the analysis. That is pinned here. The
stored "Key Reasons" defect is closed: a saved run says in one line that its reasons are not kept.
"""

from __future__ import annotations

import copy
import re

import fullscreen_goldens as goldens
import pytest

from crypto_probability_engine.detail import decision_view, gate_kinds
from crypto_probability_engine.detail.decision_view import STATE_COPY
from crypto_probability_engine.utils.sanitize import sanitize_for_export

harness = goldens.harness

EVIDENCE = (
    "Evidence gate: directional skill is not established for this model and timeframe. No risk "
    "gate is active."
)
EVIDENCE_TOO = (
    "The evidence gate is active too: directional skill is not established for this model and "
    "timeframe."
)
RISK = "A risk gate is active: Extreme-move risk is too high."
SYSTEM = "A system or data gate is active: Safety shutdown is active."
RISK_FRAMING = (
    "This is a finding about market conditions or execution. It is analysis only, not an "
    "instruction."
)
NOT_A_MARKET_CALL = (
    "The gates' disposition, not a market call: a gate outcome is not a forecast to act on."
)
HEADLINE, SENTENCE = STATE_COPY["NO_ACCEPTED_CLAIM"]
RISK_SENTENCE = (
    "No forecast-quality claim has been accepted for this model and timeframe. The percentages "
    "are uncalibrated reference context: not a forecast and not a market signal."
)
NO_REASON = "reason to act or to avoid acting"
FORCED_NOTE = "ELEVATED_RISK_AVOID (not forced by a risk gate)"
OLD_STORED_SUMMARY = goldens.OLD_STORED_SUMMARY
# What no screen may say over an analysis whose only hard block is the evidence gate.
RISK_WORDING = re.compile(r"elevated[- ]risk|risk gate is active|tail-risk state normalizes", re.I)
RISK_HEADINGS = {"Risk summary", "Risk / Gates", "Risk note", "Gate brief risk note"}
SURFACES = ("single", "batch", "detail", "history")

# scenario -> (the gate summary, whether a risk gate is active)
SCENARIOS: dict[str, tuple[str, bool]] = {
    "evidence_only": (EVIDENCE, False),
    "risk_and_evidence": (f"{RISK} {EVIDENCE_TOO}", True),
    "risk_only_SYNTHETIC": (RISK, True),
    "kill_switch_and_evidence": (f"{SYSTEM} {EVIDENCE_TOO}", False),
    "system_only_SYNTHETIC": (SYSTEM, False),
}
SAVED_BEFORE = goldens.SAVED_BEFORE


@pytest.fixture(scope="module")
def cases() -> dict[str, dict]:
    return goldens.build_cases()


@pytest.fixture(scope="module")
def reopened(cases: dict[str, dict]) -> dict[str, dict]:
    return goldens.build_reopened(cases)


@pytest.fixture(scope="module")
def screens(cases: dict[str, dict], reopened: dict[str, dict]) -> dict[str, dict[str, list[str]]]:
    """Every screen as the real app.js renders it: scenario -> surface -> the texts in order."""

    return goldens.render(cases, reopened)["screens"]


def test_the_matrix_reads_the_goldens_own_scenarios(reopened: dict) -> None:
    assert set(SCENARIOS) <= set(goldens.SCENARIOS)
    assert {*SCENARIOS, SAVED_BEFORE} <= set(reopened), "each is also pinned as a saved run"
    # A saved run read back carries the framing the read path built, and its stored summary.
    assert reopened[SAVED_BEFORE]["detail"]["decision_brief"]["state_summary"] == OLD_STORED_SUMMARY
    for name in (*SCENARIOS, SAVED_BEFORE):
        assert reopened[name]["detail"]["gate_view"]["schema_version"] == "gate_view.v1", name
        assert "decision_view" not in reopened[name]["row"], name


def test_every_gate_token_is_what_it_was(cases: dict[str, dict]) -> None:
    expected = {
        "evidence_only": ("NO_TRADE", ["SKILL_NOT_DEMONSTRATED"], "NO_TRADE"),
        "risk_and_evidence": (
            "NO_TRADE",
            ["TAIL_RISK_BREACH", "SKILL_NOT_DEMONSTRATED"],
            "NO_TRADE",
        ),
        "risk_only_SYNTHETIC": ("NO_TRADE", ["TAIL_RISK_BREACH"], "NO_TRADE"),
        "kill_switch_and_evidence": (
            "ABORT",
            ["KILL_SWITCH", "SKILL_NOT_DEMONSTRATED"],
            "NO_TRADE",
        ),
        "system_only_SYNTHETIC": ("ABORT", ["KILL_SWITCH"], "AVOID"),
    }
    for name, (action, blocks, label) in expected.items():
        payload = cases[name]
        assert payload["gate_result"]["action"] == action, name
        assert payload["gate_result"]["hard_blocks"] == blocks, name
        assert payload["decision_synthesis"]["decision_synthesis"]["label"] == label, name
        assert payload["frontend_display"]["disposition"] == action, name
        assert payload["decision_view"]["state"] == "NO_ACCEPTED_CLAIM", name
    for name in ("evidence_only", "risk_and_evidence", "kill_switch_and_evidence"):
        assert cases[name]["score_stack"]["disposition"] == "ELEVATED_RISK_AVOID", name
        assert cases[name]["gate_result"]["forced_score_disposition"] == "ELEVATED_RISK_AVOID", name
    assert decision_view.ACCEPTED_FORECAST_CLAIMS == frozenset()
    assert decision_view.ACCEPTED_DIRECTIONAL_PERMISSIONS == frozenset()
    assert len(decision_view.ACCEPTANCE_BLOCKERS) == 4


@pytest.mark.parametrize("name", SCENARIOS)
def test_the_view_is_the_one_gate_authority(cases: dict[str, dict], name: str) -> None:
    summary, risk = SCENARIOS[name]
    payload = cases[name]
    gates = payload["decision_view"]["gates"]
    assert gates == gate_kinds.build_gate_view(payload["gate_result"])
    assert gates["summary"] == summary
    assert gates["framing"] == (RISK_FRAMING if risk else NOT_A_MARKET_CALL)
    assert gates["risk_gate_active"] is risk and gates["blocked"] is True
    assert [entry["block"] for entry in gates["blocks"]] == payload["gate_result"]["hard_blocks"]
    assert payload["decision_view"]["detail"] == (RISK_SENTENCE if risk else SENTENCE)
    # What a saved run stores is enough to build the same framing when it is read back.
    stored = sanitize_for_export(copy.deepcopy(payload["detail_view"]))
    assert "gate_view" not in stored, "the framing is never stored"
    assert gate_kinds.attach_gate_view(stored)["gate_view"] == gates


@pytest.mark.parametrize("name", SCENARIOS)
@pytest.mark.parametrize("surface", SURFACES)
def test_every_surface_carries_the_same_gate_framing(
    screens: dict, name: str, surface: str
) -> None:
    summary, risk = SCENARIOS[name]
    texts = screens[name][surface]
    assert summary in texts, f"{name}/{surface}: the gate summary"
    assert (RISK_FRAMING if risk else NOT_A_MARKET_CALL) in texts, f"{name}/{surface}: the framing"
    if surface != "history":  # a reopened run has no view, only its gate framing
        assert texts[texts.index(HEADLINE) + 1] == (RISK_SENTENCE if risk else SENTENCE)
    assert "One or more hard gates are active." not in texts, f"{name}/{surface}"


@pytest.mark.parametrize(
    "name", ["evidence_only", "kill_switch_and_evidence", "system_only_SYNTHETIC"]
)
@pytest.mark.parametrize("surface", SURFACES)
def test_without_a_risk_gate_no_screen_words_risk(screens: dict, name: str, surface: str) -> None:
    for text in screens[name][surface]:
        cleaned = text.replace(FORCED_NOTE, "").replace("No risk gate is active.", "")
        assert not RISK_WORDING.search(cleaned), f"{name}/{surface}: {text}"
        assert text not in RISK_HEADINGS, f"{name}/{surface}: the heading {text!r}"
        if "ELEVATED_RISK_AVOID" in text:
            assert FORCED_NOTE in text, f"{name}/{surface}: the token alone in {text!r}"
        assert RISK_FRAMING != text, f"{name}/{surface}: risk framing without a risk gate"


@pytest.mark.parametrize("name", ["risk_and_evidence", "risk_only_SYNTHETIC"])
@pytest.mark.parametrize("surface", SURFACES)
def test_under_a_real_risk_gate_no_screen_says_no_reason_to_act(
    screens: dict, name: str, surface: str
) -> None:
    texts = screens[name][surface]
    for text in texts:
        assert NO_REASON not in text, f"{name}/{surface}: {text}"
    assert not any("No risk gate is active" in text for text in texts), f"{name}/{surface}"
    assert not any(FORCED_NOTE in text for text in texts), (
        f"{name}/{surface}: a risk gate forced it"
    )


@pytest.mark.parametrize("surface", ["single", "batch", "detail"])
def test_missing_evidence_and_a_real_block_cannot_be_confused(screens: dict, surface: str) -> None:
    cells = {name: tuple(screens[name][surface]) for name in SCENARIOS}
    assert len(set(cells.values())) == len(cells), surface


def test_a_run_saved_before_this_change_is_framed_from_its_stored_gate_result(
    screens: dict,
) -> None:
    texts = screens[SAVED_BEFORE]["history"]
    assert EVIDENCE in texts and NOT_A_MARKET_CALL in texts
    assert OLD_STORED_SUMMARY not in texts, "the stored summary shows the token alone"
    for text in texts:
        if "ELEVATED_RISK_AVOID" in text:
            assert FORCED_NOTE in text, text
        assert not RISK_WORDING.search(text.replace("No risk gate is active.", "")), text


def test_the_single_cards_banner_is_the_gate_summary_whatever_check_blocks_first(
    screens: dict,
) -> None:
    assert screens["first_check_blocks_SYNTHETIC"]["single"][:2] == ["BLOCK", EVIDENCE]
    assert screens["evidence_only"]["single"][:2] == ["BLOCK", EVIDENCE]


def test_only_currently_relevant_conditions_are_listed(cases: dict, screens: dict) -> None:
    for name in SCENARIOS:
        conditions = cases[name]["decision_synthesis"]["what_would_change_decision"]
        relevant = [item["plain_english"] for item in conditions if item["currently_relevant"]]
        hidden = [item["plain_english"] for item in conditions if not item["currently_relevant"]]
        assert relevant and hidden, name
        texts = screens[name]["detail"]
        for sentence in relevant:
            assert sentence in texts, f"{name}: {sentence}"
        listed = harness._between(texts, "What could change the decision", "Scenario plan")
        for sentence in hidden:
            assert sentence not in listed, f"{name}: not relevant now: {sentence}"


@pytest.mark.parametrize("name", ["accepted_claim_SYNTHETIC", "permission_SYNTHETIC"])
def test_the_accepted_states_keep_their_ruling_and_gain_the_gate_authority(
    cases: dict, screens: dict, name: str
) -> None:
    gates = cases[name]["decision_view"]["gates"]
    assert gates == gate_kinds.build_gate_view(cases[name]["gate_result"])
    for surface in ("single", "batch", "detail"):
        texts = screens[name][surface]
        assert cases[name]["decision_view"]["headline"] in texts, surface
        assert not any(
            RISK_WORDING.search(text.replace("No risk gate is active.", "")) for text in texts
        )
        if gates["blocked"]:
            assert gates["summary"] in texts, surface


def test_the_storage_row_is_storage_at_request_time(screens: dict) -> None:
    rows = {
        name: harness._value(screens[name]["single"], "Storage")
        for name in ("storage_OK", "storage_UNAVAILABLE", "storage_STATELESS")
    }
    assert rows["storage_OK"] == "Storage available"
    assert rows["storage_UNAVAILABLE"].startswith("Storage unavailable")
    assert rows["storage_STATELESS"].startswith("No storage configured")


def test_the_analyze_response_carries_no_save_receipt_by_design(
    cases: dict,
) -> None:
    """The save receipt (owner ruling D4) is a separate endpoint, GET /v1/analyze/receipt/{run_id}:
    so the analyze response, and its pinned hashes, stay what they were. The response carries
    storage's state at request time and no receipt; the screen asks for the receipt after it has
    shown the analysis (test_save_receipt_rendering.py)."""

    payload = cases["storage_OK"]
    assert "save_receipt" not in payload
    assert "saved" not in payload["decision_view"]
    assert payload["debug"]["persistence_status"] == "OK"


def test_a_stored_run_says_its_key_reasons_are_not_kept_and_a_live_analysis_lists_them(
    cases: dict, reopened: dict, screens: dict
) -> None:
    """utils/sanitize.py masks the stored `key_reasons` to one string (the name of its key reads
    as a credential's). The detail panel says so in one line: never the mask, and never its
    characters one a line, which was a release blocker. A live analysis lists its reasons as
    sentences, as before."""

    not_kept = "Not kept in saved history."
    for name in (*SCENARIOS, SAVED_BEFORE):
        mask = reopened[name]["detail"]["decision_brief"]["key_reasons"]
        assert isinstance(mask, str) and len(mask) > 3, f"{name}: the stored value is a mask"
        texts = screens[name]["history"]
        assert harness._between(texts, "Key Reasons", "Hard Blockers") == [
            "Key Reasons",
            not_kept,
        ], name
        assert texts.count(not_kept) == 1, f"{name}: the other lists are kept, and listed"
        assert not any(mask in text for text in texts), f"{name}: the mask itself"
        letters = list(mask.replace(" ", ""))
        windows = (texts[at : at + len(letters)] for at in range(len(texts)))
        assert letters not in windows, f"{name}: the mask, one character a line"
    for name in SCENARIOS:
        reasons = [
            f"{reason['headline']}: {reason['detail']}"
            for reason in cases[name]["frontend_display"]["blocking_reasons"]
        ]
        texts = screens[name]["detail"]
        assert reasons and all(len(reason) > 40 for reason in reasons), name
        assert harness._between(texts, "Key Reasons", "Hard Blockers") == [
            "Key Reasons",
            *reasons,
        ], name
        assert not_kept not in texts, name
    # Without a blocking reason the brief's own list is shown: sentences too.
    brief = cases["permission_SYNTHETIC"]["decision_brief"]
    assert len(brief["key_reasons"]) > 1 and brief["hard_blockers"] == []
    assert harness._between(
        screens["permission_SYNTHETIC"]["detail"], "Key Reasons", "Hard Blockers"
    ) == ["Key Reasons", *brief["key_reasons"]]
