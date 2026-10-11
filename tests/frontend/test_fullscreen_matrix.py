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
WIDE = "A risk gate is active: Execution cost is too high; Liquidity is not viable."
SYSTEM = "A system or data gate is active: Safety shutdown is active."
UNMEASURED = "A system or data gate is active: Liquidity could not be measured."
RISK_FRAMING = (
    "The risk gate (Extreme-move risk is too high) is a finding about market conditions or "
    "execution. It is analysis only, not an instruction."
)
WIDE_FRAMING = (
    "The risk gates (Execution cost is too high; Liquidity is not viable) are findings about "
    "market conditions or execution. They are analysis only, not an instruction."
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
# What no screen may say over an analysis on which no risk gate reports a measured finding.
RISK_WORDING = re.compile(
    r"elevated[- ]risk|risk gates? (is|are) active|risk gates? \(|tail-risk state normalizes"
    r"|finding about market|is not viable",
    re.I,
)
RISK_HEADINGS = {"Risk summary", "Risk / Gates", "Risk note", "Gate brief risk note"}
SURFACES = ("single", "batch", "detail", "history")

# scenario -> (the gate summary, the framing directly under it)
SCENARIOS: dict[str, tuple[str, str]] = {
    "evidence_only": (EVIDENCE, NOT_A_MARKET_CALL),
    "risk_and_evidence": (f"{RISK} {EVIDENCE_TOO}", RISK_FRAMING),
    "wide_spread_and_evidence": (f"{WIDE} {EVIDENCE_TOO}", WIDE_FRAMING),
    "missing_order_book_and_evidence": (f"{UNMEASURED} {EVIDENCE_TOO}", NOT_A_MARKET_CALL),
    "kill_switch_and_evidence": (f"{SYSTEM} {EVIDENCE_TOO}", NOT_A_MARKET_CALL),
    "risk_only_SYNTHETIC": (RISK, RISK_FRAMING),
    "missing_order_book_only_SYNTHETIC": (UNMEASURED, NOT_A_MARKET_CALL),
    "system_only_SYNTHETIC": (SYSTEM, NOT_A_MARKET_CALL),
}
# The scenarios on which a risk gate reports a measured finding, and the others.
WITH_A_RISK_GATE = [name for name, (_, framing) in SCENARIOS.items() if "risk gate" in framing]
WITHOUT_A_RISK_GATE = [name for name in SCENARIOS if name not in WITH_A_RISK_GATE]
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
    liquidity = ["LIQUIDITY_NOT_VIABLE", "SKILL_NOT_DEMONSTRATED"]
    expected = {
        "evidence_only": ("NO_TRADE", ["SKILL_NOT_DEMONSTRATED"], "NO_TRADE"),
        "risk_and_evidence": (
            "NO_TRADE",
            ["TAIL_RISK_BREACH", "SKILL_NOT_DEMONSTRATED"],
            "NO_TRADE",
        ),
        "wide_spread_and_evidence": (
            "NO_TRADE",
            ["EXECUTION_COST_TOO_HIGH", *liquidity],
            "NO_TRADE",
        ),
        "missing_order_book_and_evidence": ("NO_TRADE", liquidity, "NO_TRADE"),
        "kill_switch_and_evidence": (
            "ABORT",
            ["KILL_SWITCH", "SKILL_NOT_DEMONSTRATED"],
            "NO_TRADE",
        ),
        "risk_only_SYNTHETIC": ("NO_TRADE", ["TAIL_RISK_BREACH"], "NO_TRADE"),
        "missing_order_book_only_SYNTHETIC": ("NO_TRADE", ["LIQUIDITY_NOT_VIABLE"], "NO_TRADE"),
        "system_only_SYNTHETIC": ("ABORT", ["KILL_SWITCH"], "AVOID"),
    }
    assert set(expected) == set(SCENARIOS)
    for name, (action, blocks, label) in expected.items():
        payload = cases[name]
        assert payload["gate_result"]["action"] == action, name
        assert payload["gate_result"]["hard_blocks"] == blocks, name
        assert payload["decision_synthesis"]["decision_synthesis"]["label"] == label, name
        assert payload["frontend_display"]["disposition"] == action, name
        assert payload["decision_view"]["state"] == "NO_ACCEPTED_CLAIM", name
    for name in SCENARIOS:
        forced = name != "system_only_SYNTHETIC"
        token = "ELEVATED_RISK_AVOID" if forced else None
        assert cases[name]["gate_result"]["forced_score_disposition"] == token, name
        assert (cases[name]["score_stack"]["disposition"] == "ELEVATED_RISK_AVOID") is forced
    # The gates' own flag does not tell a measured finding from a missing order book.
    for name in ("wide_spread_and_evidence", "missing_order_book_and_evidence"):
        assert cases[name]["gate_result"]["risk_guard_applied"] is True, name
    assert decision_view.ACCEPTED_FORECAST_CLAIMS == frozenset()
    assert decision_view.ACCEPTED_DIRECTIONAL_PERMISSIONS == frozenset()
    assert len(decision_view.ACCEPTANCE_BLOCKERS) == 4


@pytest.mark.parametrize("name", SCENARIOS)
def test_the_view_is_the_one_gate_authority(cases: dict[str, dict], name: str) -> None:
    summary, framing = SCENARIOS[name]
    payload = cases[name]
    view = payload["decision_view"]
    gates = view["gates"]
    assert gates == gate_kinds.build_gate_view(
        payload["gate_result"], liquidity=payload["liquidity_state"], state=view["state"]
    )
    assert gates["summary"] == summary and gates["framing"] == framing
    risk = name in WITH_A_RISK_GATE
    assert gates["risk_gate_active"] is risk and gates["blocked"] is True
    assert [entry["block"] for entry in gates["blocks"]] == payload["gate_result"]["hard_blocks"]
    assert view["detail"] == (RISK_SENTENCE if risk else SENTENCE)
    # What a saved run stores is enough to build the same framing when it is read back.
    stored = sanitize_for_export(copy.deepcopy(payload["detail_view"]))
    assert "gate_view" not in stored, "the framing is never stored"
    assert gate_kinds.attach_gate_view(stored)["gate_view"] == gates


@pytest.mark.parametrize("name", SCENARIOS)
@pytest.mark.parametrize("surface", SURFACES)
def test_the_summary_and_its_framing_are_adjacent_and_in_that_order_on_every_surface(
    screens: dict, name: str, surface: str
) -> None:
    """Review finding D1, pinned: the framing is the line directly under the summary, wherever
    the authority is shown, and it is shown nowhere else. On the cards and on a reopened run
    the summary is shown once. On the detail panel of a live analysis the older sections still
    repeat the summary alone (they are retired in a later step); the first one leads."""

    summary, framing = SCENARIOS[name]
    texts = screens[name][surface]
    assert texts[texts.index(summary) + 1] == framing, f"{name}/{surface}"
    assert texts.count(framing) == 1, f"{name}/{surface}: the framing away from its summary"
    if surface != "detail":
        assert texts.count(summary) == 1, f"{name}/{surface}"
    if surface != "history":  # a reopened run has no view, only its gate framing
        risk = name in WITH_A_RISK_GATE
        at = texts.index(HEADLINE)
        assert texts[at + 1 : at + 4] == [RISK_SENTENCE if risk else SENTENCE, summary, framing]
    assert "One or more hard gates are active." not in texts, f"{name}/{surface}"


@pytest.mark.parametrize("name", WITH_A_RISK_GATE)
def test_the_risk_framing_names_the_gate_it_is_about(cases: dict, name: str) -> None:
    gates = cases[name]["decision_view"]["gates"]
    named = [entry["headline"] for entry in gates["blocks"] if entry["kind"] == "RISK"]
    assert named and gates["framing"].startswith(("The risk gate (", "The risk gates ("))
    assert f"({'; '.join(named)})" in gates["framing"]
    assert "This is a finding" not in gates["framing"], "a framing without a subject"
    for entry in gates["blocks"]:
        if entry["kind"] != "RISK":
            assert entry["headline"] not in gates["framing"], "only the risk gates are named"


@pytest.mark.parametrize("name", WITHOUT_A_RISK_GATE)
@pytest.mark.parametrize("surface", SURFACES)
def test_without_a_risk_gate_no_screen_words_risk(screens: dict, name: str, surface: str) -> None:
    for text in screens[name][surface]:
        cleaned = text.replace(FORCED_NOTE, "").replace("No risk gate is active.", "")
        assert not RISK_WORDING.search(cleaned), f"{name}/{surface}: {text}"
        assert text not in RISK_HEADINGS, f"{name}/{surface}: the heading {text!r}"
        if "ELEVATED_RISK_AVOID" in text:
            assert FORCED_NOTE in text, f"{name}/{surface}: the token alone in {text!r}"


@pytest.mark.parametrize("name", ["missing_order_book_and_evidence", "saved"])
def test_a_gate_fired_by_missing_data_is_a_data_gate_on_every_surface(
    cases: dict, reopened: dict, screens: dict, name: str
) -> None:
    """Review finding D2 (owner ruling G2: missing data is not proven market risk). The venue
    gave no order book, so the liquidity gate fired on missing data: the same block and the same
    forced token as a measured finding, and no screen calls it one. A saved run reads the same."""

    scenario = "missing_order_book_and_evidence"
    payload = cases[scenario]
    assert payload["liquidity_state"]["warning"] == "Order book unavailable."
    assert "LIQUIDITY_NOT_VIABLE" in payload["gate_result"]["hard_blocks"]
    surfaces = ("history",) if name == "saved" else ("single", "batch", "detail")
    if name == "saved":
        stored = reopened[scenario]["detail"]
        assert stored["gate_view"] == payload["decision_view"]["gates"]
        assert stored["liquidity_execution_detail"]["liquidity_state"] == payload["liquidity_state"]
    for surface in surfaces:
        texts = screens[scenario][surface]
        assert f"{UNMEASURED} {EVIDENCE_TOO}" in texts, surface
        for text in texts:
            assert "A risk gate is active" not in text, f"{surface}: {text}"
            assert "finding about market conditions" not in text, f"{surface}: {text}"
    # The measured counterpart is a risk gate, on the same block.
    wide = cases["wide_spread_and_evidence"]
    assert "LIQUIDITY_NOT_VIABLE" in wide["gate_result"]["hard_blocks"]
    assert wide["decision_view"]["gates"]["risk_gate_active"] is True


@pytest.mark.parametrize("name", WITH_A_RISK_GATE)
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
    assert texts[texts.index(EVIDENCE) + 1] == NOT_A_MARKET_CALL
    assert OLD_STORED_SUMMARY not in texts, "the stored summary shows the token alone"
    for text in texts:
        if "ELEVATED_RISK_AVOID" in text:
            assert FORCED_NOTE in text, text
        assert not RISK_WORDING.search(text.replace("No risk gate is active.", "")), text
    # An older run and a new one of the same analysis read the same, line for line.
    assert texts == screens["evidence_only"]["history"]


def test_the_single_cards_banner_names_the_check_that_blocks(screens: dict) -> None:
    """The gate summary is in the view, with its framing: the banner does not repeat it."""

    assert screens["evidence_only"]["single"][:2] == ["BLOCK", "Hard gates"]
    assert screens["kill_switch_and_evidence"]["single"][:2] == ["BLOCK", "Hard gates"]
    assert screens["first_check_blocks_SYNTHETIC"]["single"][:2] == ["BLOCK", "Data quality"]
    assert EVIDENCE in screens["first_check_blocks_SYNTHETIC"]["single"]


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
    payload = cases[name]
    view = payload["decision_view"]
    gates = view["gates"]
    assert gates == gate_kinds.build_gate_view(
        payload["gate_result"], liquidity=payload["liquidity_state"], state=view["state"]
    )
    framing = {
        "accepted_claim_SYNTHETIC": gate_kinds.ACCEPTED_CLAIM_FRAMING,
        "permission_SYNTHETIC": gate_kinds.DIRECTIONAL_PERMISSION_FRAMING,
    }[name]
    assert gates["framing"] == framing
    assert gates["blocked"] is (name == "accepted_claim_SYNTHETIC")
    for surface in ("single", "batch", "detail"):
        texts = screens[name][surface]
        assert view["headline"] in texts, surface
        assert not any(
            RISK_WORDING.search(text.replace("No risk gate is active.", "")) for text in texts
        )
        # The gate authority is shown whether a gate blocks or not, with the state's framing.
        assert texts[texts.index(gates["summary"]) + 1] == framing, surface
        assert texts.count(framing) == 1, surface
    assert screens["permission_SYNTHETIC"]["single"][0] != "BLOCK"
    assert cases["permission_SYNTHETIC"]["decision_view"]["gates"]["summary"] == (
        "No hard gate is active."
    )


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
