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

from crypto_probability_engine.detail import decision_view, gate_kinds, saved_run_view
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
    "unusable_order_book_and_evidence": (f"{UNMEASURED} {EVIDENCE_TOO}", NOT_A_MARKET_CALL),
    "missing_order_book_and_evidence_SYNTHETIC": (
        f"{UNMEASURED} {EVIDENCE_TOO}",
        NOT_A_MARKET_CALL,
    ),
    "kill_switch_and_evidence_SYNTHETIC": (f"{SYSTEM} {EVIDENCE_TOO}", NOT_A_MARKET_CALL),
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
        read = reopened[name]["detail"]["saved_run_view"]
        assert read["schema_version"] == "saved_run_view.v1", name
        assert read["gates"]["schema_version"] == "gate_view.v1", name
        assert "decision_view" not in reopened[name]["row"], name
        assert "gate_view" not in reopened[name]["detail"], name


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
        "unusable_order_book_and_evidence": ("NO_TRADE", liquidity, "NO_TRADE"),
        "missing_order_book_and_evidence_SYNTHETIC": ("NO_TRADE", liquidity, "NO_TRADE"),
        "kill_switch_and_evidence_SYNTHETIC": (
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
    for name in ("wide_spread_and_evidence", "missing_order_book_and_evidence_SYNTHETIC"):
        assert cases[name]["gate_result"]["risk_guard_applied"] is True, name
    assert decision_view.ACCEPTED_FORECAST_CLAIMS == frozenset()
    assert decision_view.ACCEPTED_DIRECTIONAL_PERMISSIONS == frozenset()
    assert len(decision_view.ACCEPTANCE_BLOCKERS) == 4


@pytest.mark.parametrize("name", SCENARIOS)
def _evidence_reason(payload: dict) -> str | None:
    """The backend's own reason sentence for the evidence gate of a live analysis (the one the
    older key reasons showed), or None where that gate is not active."""

    reasons = payload["frontend_display"]["blocking_reasons"]
    found = [entry["detail"] for entry in reasons if entry["code"] == "SKILL_NOT_DEMONSTRATED"]
    return found[0] if found else None


def _as_saved(gates: dict) -> dict:
    """A live analysis's gate view as its reopened run reads it: the same, except that the
    evidence gate's entry says the verdict is not kept (the record does not store it)."""

    blocks = [
        {**entry, "detail": gate_kinds.SAVED_EVIDENCE_GATE_DETAIL}
        if entry["kind"] == "EVIDENCE"
        else entry
        for entry in gates["blocks"]
    ]
    return {**gates, "blocks": blocks}


# The evidence gate's reason on these scenarios' live screens: no resolved outcome yet.
LIVE_EVIDENCE_REASON = (
    "The model has not been evaluated on this timeframe because fewer than 100 resolved outcomes "
    "are available. Reported resolved outcomes: 0."
)


@pytest.mark.parametrize("name", SCENARIOS)
def test_the_view_is_the_one_gate_authority(cases: dict[str, dict], name: str) -> None:
    summary, framing = SCENARIOS[name]
    payload = cases[name]
    view = payload["decision_view"]
    gates = view["gates"]
    assert gates == gate_kinds.build_gate_view(
        payload["gate_result"],
        liquidity=payload["liquidity_state"],
        state=view["state"],
        evidence_detail=_evidence_reason(payload),
    )
    assert gates["summary"] == summary and gates["framing"] == framing
    risk = name in WITH_A_RISK_GATE
    assert gates["risk_gate_active"] is risk and gates["blocked"] is True
    assert [entry["block"] for entry in gates["blocks"]] == payload["gate_result"]["hard_blocks"]
    assert view["detail"] == (RISK_SENTENCE if risk else SENTENCE)
    # What a saved run stores is enough to build the same framing when it is read back.
    stored = sanitize_for_export(copy.deepcopy(payload["detail_view"]))
    assert "saved_run_view" not in stored, "the framing is never stored"
    # (The evidence gate's entry apart: the verdict behind it is not stored. Minor m4.)
    read = saved_run_view.attach_saved_run_view(stored)["saved_run_view"]["gates"]
    assert read == _as_saved(gates)


@pytest.mark.parametrize("name", SCENARIOS)
@pytest.mark.parametrize("surface", SURFACES)
def test_the_summary_and_its_framing_are_adjacent_and_in_that_order_on_every_surface(
    screens: dict, name: str, surface: str
) -> None:
    """Review finding D1, pinned: the framing is the line directly under the summary, wherever
    the authority is shown, and it is shown nowhere else. On the cards and on a reopened run
    the summary is shown once. The detail panel of a live analysis shows it once more, as the
    finding of the kept "Hard gates" check (#4 of the Actionability stack), which states the
    same fact as a check's result and words nothing of its own."""

    summary, framing = SCENARIOS[name]
    texts = screens[name][surface]
    assert texts[texts.index(summary) + 1] == framing, f"{name}/{surface}"
    assert texts.count(framing) == 1, f"{name}/{surface}: the framing away from its summary"
    if surface == "detail":
        check = texts.index("Hard gates")
        assert texts[check - 1 : check + 3] == ["BLOCK", "Hard gates", "#4", summary]
        assert texts.count(summary) == 2, f"{name}/{surface}"
    else:
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


@pytest.mark.parametrize("name", ["missing_order_book_and_evidence_SYNTHETIC", "saved"])
def test_a_gate_fired_by_missing_data_is_a_data_gate_on_every_surface(
    cases: dict, reopened: dict, screens: dict, name: str
) -> None:
    """Review finding D2 (owner ruling G2: missing data is not proven market risk). The venue
    gave no order book, so the liquidity gate fired on missing data: the same block and the same
    forced token as a measured finding, and no screen calls it one. A saved run reads the same."""

    scenario = "missing_order_book_and_evidence_SYNTHETIC"
    payload = cases[scenario]
    assert payload["liquidity_state"]["warning"] == "Order book unavailable."
    assert "LIQUIDITY_NOT_VIABLE" in payload["gate_result"]["hard_blocks"]
    surfaces = ("history",) if name == "saved" else ("single", "batch", "detail")
    if name == "saved":
        stored = reopened[scenario]["detail"]
        assert stored["saved_run_view"]["gates"] == _as_saved(payload["decision_view"]["gates"])
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
    # An order book that is missing and one that was served and is unusable are the same data
    # gate under the same headline. The two cards read alike for them; the detail panel's gate
    # list says which it is.
    twins = ("unusable_order_book_and_evidence", "missing_order_book_and_evidence_SYNTHETIC")
    alike = surface != "detail"
    assert (cells[twins[0]] == cells[twins[1]]) is alike, surface
    assert len(set(cells.values())) == len(cells) - (1 if alike else 0), surface


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
    assert screens["kill_switch_and_evidence_SYNTHETIC"]["single"][:2] == ["BLOCK", "Hard gates"]
    assert screens["first_check_blocks_SYNTHETIC"]["single"][:2] == ["BLOCK", "Data quality"]
    assert EVIDENCE in screens["first_check_blocks_SYNTHETIC"]["single"]


# --- raw gate tokens say what they are (owner ruling S3) ------------------------------------

DISPOSITION = "Gate disposition (not a market call)"
GATE_ACTION = "Gate action (internal gate token, not a market call)"
HARD_BLOCKS = "Hard blocks (internal gate tokens, not a market call)"
# Every token the gates or the score can put in a disposition, and every hard block code.
GATE_TOKENS = {
    *("NO_TRADE", "ABORT", "WATCH", "CONSTRUCTIVE", "CONSTRUCTIVE_CAUTIOUS", "ELEVATED_RISK_AVOID"),
    *("KILL_SWITCH", "SHELTER_MODE_BLOCK", "PROVIDER_DEGRADED", "EPISTEMIC_VOID"),
    *("LIQUIDITY_NOT_VIABLE", "TAIL_RISK_BREACH", "EXECUTION_COST_TOO_HIGH"),
    "SKILL_NOT_DEMONSTRATED",
}


def _is_raw_gate_token(text: str) -> bool:
    parts = [part.strip() for part in text.split(",")]
    return all(part in GATE_TOKENS for part in parts)


@pytest.mark.parametrize("name", [*goldens.SCENARIOS, SAVED_BEFORE])
def test_every_raw_gate_token_on_a_screen_stands_under_a_label_that_says_what_it_is(
    cases: dict, screens: dict, name: str
) -> None:
    """Owner ruling S3. Outside the decision view a raw gate token stood under a bare label
    ("Disposition", "Gate action", "Hard blocks"). Wherever one is shown, on every surface, the
    line above it now says it is the gates' own internal token and not a market call (or, under
    an accepted directional permission, not financial advice). Labels only: each value is what
    the backend gives, in the place it had."""

    payload = cases["evidence_only" if name == SAVED_BEFORE else name]
    permission = payload["decision_view"]["directional_permission"]
    says = "not financial advice" if permission else "not a market call"
    for surface, texts in screens[name].items():
        raw = [at for at, text in enumerate(texts) if _is_raw_gate_token(text)]
        assert raw, f"{name}/{surface}: the disposition is on every screen"
        for at in raw:
            assert says in texts[at - 1], f"{name}/{surface}: {texts[at - 1]!r} over {texts[at]!r}"
        for bare in ("Disposition", "Gate action", "Hard blocks", "Gate disposition"):
            assert bare not in texts, f"{name}/{surface}: the bare label {bare!r}"
        if surface in ("single", "batch"):
            continue
        # The values are the backend's own, unchanged, in Overview and in Gates.
        gate = payload["gate_result"]
        suffix = "; not financial advice)" if permission else ", not a market call)"
        overview = harness._between(texts, "Overview", "Gates")
        gates = harness._between(texts, "Gates", "Market Data Quality")
        label = [text for text in overview if text.startswith("Gate disposition (")]
        assert (
            len(label) == 1
            and harness._value(overview, label[0]) == (payload["frontend_display"]["disposition"])
        ), f"{name}/{surface}"
        assert harness._value(gates, f"Gate action (internal gate token{suffix}") == gate["action"]
        assert harness._value(gates, f"Hard blocks (internal gate tokens{suffix}") == (
            ", ".join(gate["hard_blocks"]) or "none"
        ), f"{name}/{surface}"
        assert gates[1:6:2] == [
            f"Gate action (internal gate token{suffix}",
            f"Hard blocks (internal gate tokens{suffix}",
            "Warnings",
        ], "the rows keep their order"


# Stored gate results that do not say whether the gates passed (the re-review's minor 1; the same
# shapes as tests/detail/test_saved_run_view.py UNDECIDED_GATES): no gate writes them.
UNDECIDED_GATES = {
    "gate_empty": {},
    "gate_blocks_empty_alone": {"hard_blocks": []},
    "gate_blocks_none_alone": {"hard_blocks": None},
    "gate_action_alone": {"action": "NO_TRADE"},
    "gate_forced_token_alone": {"forced_score_disposition": "ELEVATED_RISK_AVOID"},
    "gate_skill_guard_and_action": {"skill_guard_applied": True, "action": "NO_TRADE"},
    "gate_flag_none": {"hard_gate_passed": None, "hard_blocks": []},
}
GATES_NOT_READABLE = (
    "No gate result can be read from this saved analysis, so no gate framing is shown."
)


def test_a_gate_result_that_does_not_say_it_passed_never_reads_as_passed_on_the_screen(
    cases: dict, reopened: dict
) -> None:
    """The re-review's minor 1, on the screen. A reopened run whose stored gate result is empty,
    or carries no flag and no block, showed "No hard gate is active." over "Gate disposition (not
    a market call) / ELEVATED_RISK_AVOID", and with a stored action a second, different token in
    Gates. The screen now says that no gate result can be read: no claim that the gates passed,
    no forced token, no disposition row made up, and one answer in every place a token stood."""

    def stored(gate: dict) -> dict:
        detail = sanitize_for_export(copy.deepcopy(cases["evidence_only"]["detail_view"]))
        assert detail["score_detail"]["disposition"] == "ELEVATED_RISK_AVOID"
        detail["invalidation_detail"] = copy.deepcopy(gate)
        return {
            "row": reopened["evidence_only"]["row"],
            "detail": saved_run_view.attach_saved_run_view(detail),
        }

    rendered = goldens.render({}, {name: stored(gate) for name, gate in UNDECIDED_GATES.items()})
    whole = reopened["evidence_only"]["detail"]["saved_run_view"]
    for name, surfaces in rendered["screens"].items():
        texts = surfaces["history"]
        block = harness._between(texts, "Saved analysis", "Model Quality")
        assert "No hard gate is active." not in " ".join(texts), name
        assert not any("ELEVATED_RISK_AVOID" in text for text in texts), name
        assert not any(_is_raw_gate_token(text) for text in texts), f"{name}: a token is shown"
        # The block says what it cannot read, in the place the gate summary has.
        assert texts.count(GATES_NOT_READABLE) == 1 and GATES_NOT_READABLE in block[:3], name
        assert not any(text.startswith("Gate disposition") for text in block), name
        assert gate_kinds.NOT_A_MARKET_CALL not in texts, "no framing of a result that is not read"
        # Outside the block the three rows keep their labels, and none holds a value.
        overview = harness._between(texts, "Overview", "Gates")
        gates = harness._between(texts, "Gates", "Market Data Quality")
        assert harness._value(overview, "Gate disposition (not a market call)") == "n/a", name
        assert harness._value(gates, GATE_ACTION) == "n/a", name
        assert harness._value(gates, HARD_BLOCKS) == "n/a", name
        # Everything else the record holds is on the screen as on the whole record's.
        assert harness._value(block, "Up (above the band)") == "39.38%", name
        assert harness._value(block, "Asset · venue") == "BTC/USDT · okx", name
    assert whole["gates"]["summary"].startswith("Evidence gate: "), "the whole record is framed"


# The scenarios whose execution model could estimate no slippage: no order book, or a served
# book the liquidity measure refuses. Their round-trip cost is the two taker fees alone.
FEES_ONLY = {
    "unusable_order_book_and_evidence",
    "missing_order_book_and_evidence_SYNTHETIC",
    "missing_order_book_only_SYNTHETIC",
}


@pytest.mark.parametrize("name", list(goldens.SCENARIOS))
def test_a_fees_only_cost_says_so_under_the_cost_on_every_surface(
    cases: dict, reopened: dict, screens: dict, name: str
) -> None:
    """The re-review's minor 2. Where no slippage could be estimated, "Round-trip cost 0.20%" and
    "(band ±0.20%)" are the fees alone. Every surface now says so in the backend's sentence, on
    a row of its own directly under the cost; a reopened run reads it from its stored record.
    Where slippage was estimated no surface says it, and no number moved."""

    caveat = cases[name]["decision_view"]["cost"]["caveat"]
    assert (caveat is not None) is (name in FEES_ONLY)
    if name in reopened:
        assert reopened[name]["detail"]["saved_run_view"]["cost"]["caveat"] == caveat
    surfaces = screens[name]
    assert {"single", "batch", "detail"} <= set(surfaces)
    assert ("history" in surfaces) is (name in goldens.HISTORY)
    for surface, texts in surfaces.items():
        if caveat is None:
            assert COST_NOTE not in texts, f"{name}/{surface}"
            assert decision_view.COST_FEES_ONLY not in texts, f"{name}/{surface}"
            continue
        assert caveat == decision_view.COST_FEES_ONLY
        at = texts.index("Round-trip cost")
        assert texts[at : at + 4] == ["Round-trip cost", "0.20%", COST_NOTE, caveat], surface
        assert texts.count(COST_NOTE) == 1 and texts.count(caveat) == 1, f"{name}/{surface}"
        # The band the sentence speaks of is on the same screen, and is that cost.
        band = harness._value(texts, "In band (inside the decision band)")
        assert band.endswith("(band ±0.20%)"), f"{name}/{surface}: {band}"
    assert FEES_ONLY <= set(goldens.HISTORY), "each is also pinned as a reopened run"
    # The sentence is the backend's: the frontend holds a row label and words nothing.
    source = (harness.ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    assert "fees only" not in source.lower() and "slippage could not" not in source.lower()
    assert source.count('"Cost note"') == 1


def test_the_forced_token_keeps_its_note_on_the_screen_whatever_flags_the_record_lost(
    cases: dict, reopened: dict
) -> None:
    """The exact-final review's minor m1, through the real app.js: the three stored shapes that
    showed the forced token bare (the record lost its guard flags). Wherever the token stands on
    the reopened screen, its note stands with it."""

    def stored(gate: dict, liquidity: dict | None = None) -> dict:
        detail = sanitize_for_export(copy.deepcopy(cases["evidence_only"]["detail_view"]))
        detail["invalidation_detail"] = gate
        if liquidity is not None:
            detail["liquidity_execution_detail"]["liquidity_state"] = liquidity
        return {
            "row": reopened["evidence_only"]["row"],
            "detail": saved_run_view.attach_saved_run_view(detail),
        }

    token = "ELEVATED_RISK_AVOID"
    no_book = {"status": "DEGRADED", "spread_frac": None, "top_depth_quote": 0.0}
    shapes = {
        "evidence_block_action_is_the_token": stored(
            {"hard_gate_passed": False, "hard_blocks": ["SKILL_NOT_DEMONSTRATED"], "action": token}
        ),
        "passed_forced_token_still_stored": stored(
            {
                "hard_gate_passed": True,
                "hard_blocks": [],
                "action": "NO_TRADE",
                "forced_score_disposition": token,
            }
        ),
        "unmeasured_liquidity_block_action_is_the_token": stored(
            {"hard_gate_passed": False, "hard_blocks": ["LIQUIDITY_NOT_VIABLE"], "action": token},
            no_book,
        ),
    }
    rendered = goldens.render({}, shapes)["screens"]
    assert sorted(rendered) == sorted(shapes)
    for name, surfaces in rendered.items():
        texts = surfaces["history"]
        carrying = [text for text in texts if token in text]
        assert carrying, f"{name}: the token is on this screen"
        assert all(text == FORCED_NOTE for text in carrying), (name, carrying)


# Stored liquidity states that are absent or are not what the measure writes (minor m2), put
# where the wide-spread analysis's measured state was.
NOT_READABLE_LIQUIDITY = {
    "state_missing": lambda d: d["liquidity_execution_detail"].pop("liquidity_state"),
    "status_missing": lambda d: d["liquidity_execution_detail"]["liquidity_state"].pop("status"),
    "spread_is_text": lambda d: d["liquidity_execution_detail"]["liquidity_state"].update(
        spread_frac="0.095"
    ),
    "whole_detail_missing": lambda d: d.pop("liquidity_execution_detail"),
}


def test_a_record_without_a_readable_liquidity_state_asserts_no_cause_on_the_screen(
    cases: dict, reopened: dict, screens: dict
) -> None:
    """The exact-final review's minor m2, through the real app.js. The live analysis measured a
    spread that was too wide. Its reopened run, with the stored liquidity state lost or partial,
    said "missing data" or "the order book that was served has a spread outside the range": a
    cause the record does not show. It now names the liquidity gate and says only that the
    record holds no readable measurement."""

    name = "wide_spread_and_evidence"
    live = screens[name]["detail"]
    assert "Liquidity is not viable: Analysis is blocked because current liquidity does not" in (
        " ".join(live)
    )

    def stored(change) -> dict:
        detail = sanitize_for_export(copy.deepcopy(cases[name]["detail_view"]))
        change(detail)
        return {
            "row": reopened[name]["row"],
            "detail": saved_run_view.attach_saved_run_view(detail),
        }

    damaged = {key: stored(change) for key, change in NOT_READABLE_LIQUIDITY.items()}
    rendered = goldens.render({}, damaged)["screens"]
    summary = (
        "A risk gate is active: Execution cost is too high. The liquidity gate is active: this "
        "saved record does not hold a readable liquidity measurement. The evidence gate is active "
        "too: directional skill is not established for this model and timeframe."
    )
    entry = (
        "Liquidity gate: This saved record does not hold a readable liquidity measurement, so it "
        "cannot say whether liquidity was measured or what the gate found."
    )
    for key, surfaces in rendered.items():
        texts = surfaces["history"]
        block = harness._between(texts, "Saved analysis", "Model Quality")
        # The cost gate is a risk gate by its name alone, so it stays named as one even where
        # the whole liquidity and execution detail is lost.
        assert texts.count(summary) == 1 and block.count(entry) == 1, key
        written = " ".join(block)
        for claim in ("missing data", "are unavailable", "outside the range", "not viable"):
            assert claim not in written, (key, claim)
        assert "Liquidity could not be measured" not in written, key
        # The risk framing names the cost gate only: the liquidity gate is no finding here.
        framing = block[block.index(summary) + 1]
        assert framing == (
            "The risk gate (Execution cost is too high) is a finding about market conditions or "
            "execution. It is analysis only, not an instruction."
        ), key


def test_a_reopened_runs_data_sections_never_read_na_for_a_value_its_screen_shows(
    cases: dict, reopened: dict, screens: dict
) -> None:
    """The exact-final review's minor m3. A reopened run's Market Data Quality and Provider State
    sections read "n/a" for the data source, the live-data flag and the venue, which its own
    block and its Overview showed. They now show the same value; and where the record does not
    hold it, every one of those rows says "Not kept in saved history.", never "n/a" in one place
    and a sentence in another. A run with no saved view to read keeps its rows as they were."""

    def sections(texts: list[str]) -> tuple[list[str], list[str], list[str]]:
        return (
            harness._between(texts, "Overview", "Gates"),
            harness._between(texts, "Market Data Quality", "Provider State"),
            harness._between(texts, "Provider State", "Market Data v2 / Provider Observability"),
        )

    for name in (*goldens.HISTORY, SAVED_BEFORE):
        texts = screens[name]["history"]
        overview, quality, provider = sections(texts)
        assert harness._value(overview, "Data source") == "OKX_PUBLIC", name
        assert harness._value(quality, "Data source") == "OKX_PUBLIC", name
        assert harness._value(overview, "Live data") == "yes", name
        assert harness._value(quality, "Live data") == "yes", name
        assert harness._value(provider, "Active provider") == "okx", name
        assert harness._value(texts, "Asset · venue") == "BTC/USDT · okx", name

    def stored(change, *, version: str | None = None) -> dict:
        detail = sanitize_for_export(copy.deepcopy(cases["evidence_only"]["detail_view"]))
        change(detail)
        read = saved_run_view.attach_saved_run_view(detail)
        if version:
            read["saved_run_view"]["schema_version"] = version
        return {"row": reopened["evidence_only"]["row"], "detail": read}

    damaged = {
        "quality_lost": stored(lambda d: d.pop("data_quality_detail")),
        "another_version": stored(lambda d: None, version="saved_run_view.v2"),
    }
    # A row's own value stands where the screen has one: a response without a view that still
    # carries its data quality, read beside a saved view that names another source.
    own = {k: v for k, v in cases["evidence_only"].items() if k != "decision_view"}
    other = stored(lambda d: d["data_quality_detail"]["data_quality"].update(data_source="OTHER"))
    assert other["detail"]["saved_run_view"]["data"]["data_source"] == "OTHER"
    damaged["own_value"] = {"row": own, "detail": other["detail"]}
    rendered = goldens.render({}, damaged)["screens"]
    _, quality, provider = sections(rendered["own_value"]["history"])
    assert harness._value(quality, "Data source") == own["data_quality"]["data_source"]
    assert own["data_quality"]["data_source"] == "OKX_PUBLIC"
    assert harness._value(provider, "Active provider") == own["provider_state"]["active_provider"]
    overview, quality, provider = sections(rendered["quality_lost"]["history"])
    for rows, label in (
        (overview, "Data source"),
        (overview, "Live data"),
        (quality, "Data source"),
        (quality, "Live data"),
        (provider, "Active provider"),
    ):
        assert harness._value(rows, label) == NOT_KEPT, label
    assert harness._value(rendered["quality_lost"]["history"], "Venue") == NOT_KEPT
    # The exact-final review's minor m5, first gap: a saved-run view of a version this script
    # does not know is not drawn at all (no block, none of its sentences), and with no view to
    # read the rows keep their own value.
    other = rendered["another_version"]["history"]
    assert "Saved analysis" not in other
    kept = damaged["another_version"]["detail"]["saved_run_view"]
    assert kept["gates"]["summary"] not in other and kept["gates"]["framing"] not in other
    overview, quality, provider = sections(other)
    for rows, label in ((quality, "Data source"), (provider, "Active provider")):
        assert harness._value(rows, label) == "n/a", label
    assert "Saved analysis" in screens["evidence_only"]["history"], "the known version is drawn"


# The rows that repeat a value of the stored market-data block, and the key each reads.
MARKET_ROWS = {
    "Symbol availability": "symbol_availability",
    "Cross-provider state": "cross_provider_state",
    "Fallback to single provider": "fallback_to_single_provider",
    "Disagreement bps": "disagreement_bps",
}
PROVIDER_CROSS_LABELS = ("Cross-provider state", "Fallback to single provider", "Disagreement bps")


def test_a_reopened_runs_market_rows_show_what_its_stored_market_data_block_holds(
    cases: dict, reopened: dict, screens: dict
) -> None:
    """The release-prep review's minor M-1. A reopened run read "n/a" for the warnings, the
    symbol's availability and the cross-provider values, which the same screen's Market Data v2
    section shows a few lines below from the stored `market_data_v2_detail`. Each such row now
    shows the stored value (in Provider State the row is left out: the block holds those values,
    not the run's provider state). Live screens are as they were; a value the record does not
    hold still reads "n/a", as it did."""

    def sections(texts: list[str]) -> dict[str, list[str]]:
        return {
            "gates": harness._between(texts, "Gates", "Market Data Quality"),
            "quality": harness._between(texts, "Market Data Quality", "Provider State"),
            "provider": harness._between(
                texts, "Provider State", "Market Data v2 / Provider Observability"
            ),
            "v2": harness._between(
                texts, "Market Data v2 / Provider Observability", "Quant Signals"
            ),
        }

    def table(v2: list[str], key: str) -> str:
        return harness._value(v2, key.replace("_", " "))

    def stored(change) -> dict:
        detail = sanitize_for_export(copy.deepcopy(cases["evidence_only"]["detail_view"]))
        change(detail)
        return {
            "row": reopened["evidence_only"]["row"],
            "detail": saved_run_view.attach_saved_run_view(detail),
        }

    def distinct(detail: dict) -> None:
        detail["market_data_v2_detail"].update(
            symbol_availability="BOTH_PROVIDERS",
            cross_provider_state="COHERENT",
            fallback_to_single_provider=False,
            disagreement_bps=3.25,
            warnings=["first stored warning", "second stored warning"],
        )

    runs = {
        "distinct": stored(distinct),
        "block_lost": stored(lambda d: d.pop("market_data_v2_detail")),
    }
    # A row's own value stands where the screen has one: a response without a view that still
    # carries its data quality, read beside a stored block that holds other values.
    own = {k: v for k, v in cases["evidence_only"].items() if k != "decision_view"}
    runs["own_value"] = {"row": own, "detail": runs["distinct"]["detail"]}
    rendered = goldens.render({}, runs)["screens"]
    # Each row reads its own key: every value of the block is distinct from the others.
    mine = sections(rendered["distinct"]["history"])
    expected = {
        "Symbol availability": "BOTH_PROVIDERS",
        "Cross-provider state": "COHERENT",
        "Fallback to single provider": "no",
        "Disagreement bps": "3.2500",
    }
    for label, key in MARKET_ROWS.items():
        assert harness._value(mine["v2"], label) == expected[label] == table(mine["v2"], key)
    warnings = "first stored warning, second stored warning"
    assert harness._value(mine["gates"], "Warnings") == warnings
    assert harness._value(mine["quality"], "Warnings") == warnings
    for label in PROVIDER_CROSS_LABELS:
        assert label not in mine["provider"], label
    assert [harness._value(mine["provider"], label) for label in ("Status", "Reason")] == [
        "n/a",
        "n/a",
    ], "what the record's view does not carry reads as it did"
    # Every reopened golden: no such row reads "n/a" where the table below shows a value.
    for name in (*goldens.HISTORY, SAVED_BEFORE):
        parts = sections(screens[name]["history"])
        for label, key in MARKET_ROWS.items():
            assert harness._value(parts["v2"], label) == table(parts["v2"], key), (name, label)
        assert harness._value(parts["v2"], "Cross-provider state") == "UNAVAILABLE", name
        for part in ("gates", "quality"):
            assert harness._value(parts[part], "Warnings") == "none", (name, part)
        for label in PROVIDER_CROSS_LABELS:
            assert label not in parts["provider"], (name, label)
    theirs = sections(rendered["own_value"]["history"])
    assert own["data_quality"]["cross_provider_state"] == "UNAVAILABLE"
    assert harness._value(theirs["v2"], "Cross-provider state") == "UNAVAILABLE"
    assert harness._value(theirs["gates"], "Warnings") == "none"
    assert harness._value(theirs["provider"], "Cross-provider state") == "UNAVAILABLE"
    # A record without the block: the rows are as they were, "n/a" each.
    lost = sections(rendered["block_lost"]["history"])
    for label in MARKET_ROWS:
        assert harness._value(lost["v2"], label) == "n/a", label
    for label in PROVIDER_CROSS_LABELS:
        assert harness._value(lost["provider"], label) == "n/a", label
    assert harness._value(lost["gates"], "Warnings") == "n/a"
    # A live analysis's screen is untouched: its own rows, the Provider State ones included.
    for name in cases:
        parts = sections(screens[name]["detail"])
        payload = cases[name]
        for label in PROVIDER_CROSS_LABELS:
            assert label in parts["provider"], (name, label)
        assert harness._value(parts["provider"], "Cross-provider state") == (
            payload["provider_state"].get("cross_provider_state") or "n/a"
        ), name
        assert harness._value(parts["v2"], "Cross-provider state") == (
            payload["data_quality"].get("cross_provider_state") or "n/a"
        ), name


# The news rows that repeat a value of the stored news add-on state: label -> (section, key).
NEWS_ROWS = {"Warnings": ("news", "warnings"), "Influence mode": ("authority", "influence_mode")}


def test_a_reopened_runs_news_rows_show_what_its_stored_news_add_on_state_holds(
    cases: dict, reopened: dict, screens: dict
) -> None:
    """The release-prep review's minor MINOR-1. A reopened run read "n/a" for the news warnings
    and the influence mode, which the same screen's News Add-on section shows from the stored
    `news_detail.news_addon_state`: the analysis's own news add-on state (detail/builder.py),
    the object a live analysis's rows read. Each row now shows the stored value. "Provider
    status" still reads "n/a": the record's list is the sanitized one (a provider's
    `last_failure_error_code` is masked), not a copy of the list the row reads. Live screens are
    as they were."""

    def sections(texts: list[str]) -> dict[str, list[str]]:
        authority = "News Authority / Macro & Micro Context"
        return {
            "news": harness._between(texts, "News Add-on", authority),
            "authority": harness._between(texts, authority, "Debug / Raw JSON"),
        }

    def row(texts: list[str], label: str) -> str:
        part, _ = NEWS_ROWS.get(label, ("authority", None))
        return harness._value(sections(texts)[part], label)

    def stored(change, *, detail: dict | None = None) -> dict:
        kept = detail if detail is not None else cases["evidence_only"]["detail_view"]
        kept = sanitize_for_export(copy.deepcopy(kept))
        change(kept)
        return {
            "row": reopened["evidence_only"]["row"],
            "detail": saved_run_view.attach_saved_run_view(kept),
        }

    def distinct(detail: dict) -> None:
        news = detail["news_detail"]
        news["news_addon_state"].update(
            warnings=["first stored news warning", "second stored news warning"],
            influence_mode="STORED_INFLUENCE_MODE",
            provider_status=[{"provider": "stored_provider", "status": "OK"}],
        )
        # Every other block that holds a value of the same name holds another value.
        for key in ("micro_news_context", "macro_context"):
            news[key]["warnings"] = ["another block's warning"]
        detail["market_data_v2_detail"]["warnings"] = ["a market-data warning"]
        assert news["news_evidence"]["influence_mode"] == "ADVISORY_DISPLAY_ONLY"
        assert news["news_influence"]["influence_mode"] == "ADVISORY_DISPLAY_ONLY"

    runs = {
        "distinct": stored(distinct),
        "state_lost": stored(lambda d: d["news_detail"].pop("news_addon_state")),
        "news_lost": stored(lambda d: d.pop("news_detail")),
    }
    # A row's own value stands where the screen has one: a response without a view that still
    # carries its news add-on state, read beside a stored state that holds other values.
    own = {k: v for k, v in cases["evidence_only"].items() if k != "decision_view"}
    runs["own_value"] = {"row": own, "detail": runs["distinct"]["detail"]}
    # A live analysis's rows read its own response only: one that carries none of these values,
    # beside a detail whose news add-on state holds them, still reads "n/a".
    live = copy.deepcopy(cases["evidence_only"])
    assert live.get("decision_view"), "a live analysis has its view"
    live.pop("news_addon_state")
    live["frontend_display"].pop("news_warnings")
    live_detail = stored(distinct, detail=live["detail_view"])["detail"]
    runs["live_without_news"] = {"row": live, "detail": live_detail}
    rendered = goldens.render({}, runs)["screens"]

    mine = rendered["distinct"]["history"]
    assert row(mine, "Warnings") == "first stored news warning, second stored news warning"
    assert row(mine, "Influence mode") == "STORED_INFLUENCE_MODE"
    assert row(mine, "Provider status") == "n/a", "the stored list is not read"
    # Every reopened golden: each row shows the value its stored state holds.
    for name in (*goldens.HISTORY, SAVED_BEFORE):
        texts = screens[name]["history"]
        state = reopened[name]["detail"]["news_detail"]["news_addon_state"]
        assert (state["warnings"], state["influence_mode"]) == ([], "ADVISORY_DISPLAY_ONLY"), name
        assert row(texts, "Warnings") == "none", name
        assert row(texts, "Influence mode") == "ADVISORY_DISPLAY_ONLY", name
        assert row(texts, "Provider status") == "n/a", name
    # A record without the state, or without its news block: the rows are as they were.
    for name in ("state_lost", "news_lost"):
        for label in ("Warnings", "Influence mode", "Provider status"):
            assert row(rendered[name]["history"], label) == "n/a", (name, label)
    theirs = rendered["own_value"]["history"]
    assert own["frontend_display"]["news_warnings"] == []
    assert row(theirs, "Warnings") == "none"
    assert row(theirs, "Influence mode") == own["news_addon_state"]["influence_mode"]
    assert row(theirs, "Provider status") == "none"
    for label in ("Warnings", "Influence mode", "Provider status"):
        assert row(rendered["live_without_news"]["history"], label) == "n/a", label
    # A live analysis's screen is untouched: its own rows.
    for name in cases:
        texts = screens[name]["detail"]
        payload = cases[name]
        warnings = payload["frontend_display"]["news_warnings"]
        assert row(texts, "Warnings") == (", ".join(warnings) or "none"), name
        state = payload["news_addon_state"]
        assert row(texts, "Influence mode") == state["influence_mode"], name
        assert state["provider_status"] == [], name
        assert row(texts, "Provider status") == "none", name


def test_a_reopened_run_of_unusable_data_says_not_assessed_not_not_kept(
    cases: dict, reopened: dict
) -> None:
    """The exact-final review's minor m5, second gap. A reopened run whose record shows data that
    could support no assessment says of its three percentages what the live view said ("Not
    assessed"), not that they are "not kept": they were never shown. What the record truly does
    not hold still says "Not kept in saved history."."""

    def stored(status: str) -> dict:
        detail = sanitize_for_export(copy.deepcopy(cases["evidence_only"]["detail_view"]))
        detail["data_quality_detail"]["provider_state"]["status"] = status
        return {
            "row": reopened["evidence_only"]["row"],
            "detail": saved_run_view.attach_saved_run_view(detail),
        }

    runs = {"unavailable": stored("UNAVAILABLE"), "ok": stored("OK")}
    assert runs["unavailable"]["detail"]["saved_run_view"]["range"]["assessed"] is False
    rendered = goldens.render({}, runs)["screens"]
    texts = rendered["unavailable"]["history"]
    block = harness._between(texts, "Saved analysis", "Model Quality")
    assert harness._value(block, "In band (inside the decision band)") == (
        "Not assessed (the data cannot support an assessment)"
    )
    assert harness._value(block, "Up (above the band)") == "Not assessed"
    assert harness._value(block, "Down (below the band)") == "Not assessed"
    assert harness._value(block, "Reference close (UTC)") == NOT_KEPT
    assert decision_view.NOT_ASSESSED in block and decision_view.RANGE_MEANING not in block
    assert not any("%" in text for text in block[: block.index("Evidence level")])
    # The same record with usable data shows its percentages.
    usable = harness._between(rendered["ok"]["history"], "Saved analysis", "Model Quality")
    assert harness._value(usable, "Up (above the band)") == "39.38%"
    assert "Not assessed" not in " ".join(usable)


def test_a_card_without_a_view_labels_its_disposition_too(cases: dict) -> None:
    """Owner ruling S3, on the one screen no golden holds: a response without a decision view
    (an older one) still shows its disposition on the batch card, and under the same label."""

    payload = {key: kept for key, kept in cases["evidence_only"].items() if key != "decision_view"}
    texts = goldens.render({"no_view": payload}, {})["screens"]["no_view"]["batch"]
    shown = payload["frontend_display"]["disposition"]
    assert shown == "NO_TRADE" and texts.count(shown) == 1
    assert harness._value(texts, "Gate disposition (not a market call)") == shown
    assert "Disposition" not in texts


# --- the older decision sections are retired from the default screen -------------------------

# The headings, labels and fixed lines of the retired sections, in the parity review's order:
# the gate checks card (row 2); the Probability section (row 11); the advisor explanation, its
# conditions, the scenario plan, the future-quant block and every permission row (rows 5-6); the
# decision card (row 1); the gate brief and its four lists (rows 9-10).
RETIRED_LINES = (
    *("Gate checks", "Risk summary"),
    *("Probability", "Type", "Explanation"),
    *("Advisor explanation", "Why this decision", "Why immediate action is unavailable"),
    *("Why probability is muted", "Why timeframe matters", "Why reliability is insufficient"),
    *("What could change the decision", "Scenario plan", "Display only", "Plan status"),
    *("Direction context", "Chase move", "Why this is limited", "Wait for confirmation"),
    *("What would change the plan", "Safety notes", "Advanced context · Future Quant V2"),
    *("Influence mode: SHADOW_ONLY", "Decision influence"),
    *("Immediate action", "Plan", "Chase", "Observe only", "Plan only"),
    *("Primary reason", "Next action", "No trade", "Avoid", "LOW", "MODERATE", "HIGH"),
    *("Gate brief (not a market call)", "Gate brief summary", "Gate brief note", "Gate note"),
    *("State summary", "Volatility reference", "Disclaimer", "Profitability claim"),
    *("Key Reasons", "Hard Blockers", "Watchlist Triggers", "Invalidation Conditions"),
    "No decision synthesis for this run; the existing gate brief is shown.",
    "Scenario plan unavailable. Keep using the Decision summary and hard gates.",
    "Candidate labels are planning context only and do not grant entry permission.",
)


def _backend_sentences_no_longer_rendered(payload: dict) -> list[str]:
    """The backend's own sentences that only the retired sections showed. They stay in the
    payload (nothing is deleted from it in this pass) and are listed for the owner."""

    synthesis = payload["decision_synthesis"]
    plan = synthesis["trade_plan_skeleton"]
    brief = payload["decision_brief"]
    return [
        synthesis["decision_synthesis"]["plain_english"],
        synthesis["action_permission"]["plain_english"],
        *(item["plain_english"] for item in synthesis["what_would_change_decision"]),
        synthesis["advisor_explanations"]["why_not_enter_now"],
        synthesis["advisor_explanations"]["why_probability_is_muted"],
        synthesis["advisor_explanations"]["why_reliability_is_insufficient"],
        *plan["confirmation_required"],
        *plan["what_would_change_plan"],
        *plan["safety_copy"],
        synthesis["future_quant_v2_hooks"]["plain_english"],
        f"Decision synthesis label is {synthesis['decision_synthesis']['label']}.",
        brief["state_summary"],
        brief["risk_note"],
        brief["disclaimer"],
        brief["volatility_reference"]["note"],
        *brief["key_reasons"],
        *brief["watchlist_triggers"],
        *brief["invalidation_conditions"],
    ]


@pytest.mark.parametrize("name", [*goldens.SCENARIOS, SAVED_BEFORE])
def test_no_surface_renders_an_older_decision_section(
    cases: dict, screens: dict, name: str
) -> None:
    """Step 3 of the redesign, on every scenario and surface: no heading, label or fixed line of
    a retired section is on screen, and neither is a backend sentence only they showed."""

    payload = cases["evidence_only" if name == SAVED_BEFORE else name]
    sentences = _backend_sentences_no_longer_rendered(payload)
    assert len(sentences) > 20 and all(isinstance(text, str) and text for text in sentences)
    for surface, texts in screens[name].items():
        for line in RETIRED_LINES:
            assert line not in texts, f"{name}/{surface}: {line!r}"
        for sentence in sentences:
            assert sentence not in texts, f"{name}/{surface}: {sentence!r}"
        # The stack's copy of the retired decision card's label is not listed.
        assert "Final decision" not in texts and "#12" not in texts, f"{name}/{surface}"
    # The kept checks are listed, in order, on the detail panel of a live analysis.
    if name != SAVED_BEFORE:
        detail = screens[name]["detail"]
        stack = harness._between(detail, "Actionability stack", "Model Quality")
        numbers = [text for text in stack if text.startswith("#")]
        assert numbers == [f"#{number}" for number in range(1, 12)], name
        checks = payload["decision_synthesis"]["actionability_stack"]
        assert [check["key"] for check in checks][-1] == "final_decision"
        for check in checks[:-1]:
            assert check["label"] in stack and check["plain_english"] in stack, name


def test_the_sections_kept_on_the_detail_panel_and_their_order(screens: dict) -> None:
    """What the parity review keeps (rows 3, 4, 7, 8, 12, 13), under the decision view, in this
    order; a reopened run has its own block and no checks (it stores no decision synthesis)."""

    headings = (
        "Decision view",
        "Decision",
        "Probability interpretation",
        "Actionability stack",
        "Model Quality",
        "Overview",
        "Gates",
        "Market Data Quality",
        "Provider State",
        "Market Data v2 / Provider Observability",
        "Quant Signals",
        "News Add-on",
        "News Authority / Macro & Micro Context",
        "Debug / Raw JSON",
    )
    for name in SCENARIOS:
        detail = screens[name]["detail"]
        found = [detail.index(heading) for heading in headings]
        assert found == sorted(found) and found[0] == 0, name
        history = screens[name]["history"]
        kept = ("Saved analysis", *headings[4:])
        found = [history.index(heading) for heading in kept]
        assert found == sorted(found) and found[0] == 0, name
        for heading in headings[:4]:
            assert heading not in history, (name, heading)
    # No heading of a kept section is a risk heading, whatever gate is active.
    for name, surfaces in screens.items():
        for surface, texts in surfaces.items():
            for heading in RISK_HEADINGS:
                assert heading not in texts, (name, surface, heading)


def test_the_kill_switch_reads_one_disposition_on_every_surface(cases: dict, screens: dict) -> None:
    """The parity review's C5: under the kill switch one label read ABORT in the view and "No
    trade" or NO_TRADE in the older sections. They are retired, and every surface, a reopened
    run too, reads the gates' own disposition and no other."""

    name = "kill_switch_and_evidence_SYNTHETIC"
    assert cases[name]["gate_result"]["action"] == "ABORT"
    assert cases[name]["decision_brief"]["action"] == "NO_TRADE"
    for surface, texts in screens[name].items():
        label = "Gate disposition (not a market call)"
        said = [texts[at + 1] for at, text in enumerate(texts) if text == label]
        # Once in the view (or the run's own block); the panels repeat it in Overview.
        assert said == ["ABORT"] * (1 if surface in ("single", "batch") else 2), surface
        assert not any("NO_TRADE" in text or text == "No trade" for text in texts), surface


@pytest.mark.parametrize("name", ["accepted_claim_SYNTHETIC", "permission_SYNTHETIC"])
def test_the_accepted_states_keep_their_ruling_and_gain_the_gate_authority(
    cases: dict, screens: dict, name: str
) -> None:
    payload = cases[name]
    view = payload["decision_view"]
    gates = view["gates"]
    assert gates == gate_kinds.build_gate_view(
        payload["gate_result"],
        liquidity=payload["liquidity_state"],
        state=view["state"],
        evidence_detail=_evidence_reason(payload),
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


# --- what only the older sections said, now in the authoritative block -----------------------

NOT_KEPT = "Not kept in saved history."
EXPLANATION = (
    "Up/Down/In band are uncalibrated heuristic estimates for the terminal close ~6 bars ahead on "
    "this timeframe: Up ends above the decision band, Down below it, In band inside it (a "
    "terminal outcome, not a clock timeout). Not a forecast, not expected return, and not a trade "
    "recommendation."
)
# The rows of a reopened run's block, in order, under the labels a live analysis uses.
SAVED_ROWS = (
    "Asset · venue",
    "Reference close (Vietnam)",
    "Reference close (UTC)",
    "Horizon end (Vietnam)",
    "Horizon end (UTC)",
    "In band (inside the decision band)",
    "Up (above the band)",
    "Down (below the band)",
    "Evidence level",
    "Round-trip cost",
    "Evidence",
    "Calibration",
    "Reliability",
    "Gate disposition (not a market call)",
)
# The label of the row that holds the backend's caveat on a cost (frontend/app.js costCaveatRows).
COST_NOTE = "Cost note"
# The rows a saved run can fill from its record, which read as the live analysis's own rows did.
SAME_AS_LIVE = (
    "Asset · venue",
    "In band (inside the decision band)",
    "Up (above the band)",
    "Down (below the band)",
    "Evidence level",
    "Round-trip cost",
    "Gate disposition (not a market call)",
)


def _gate_lines(payload: dict, *, saved: bool = False) -> list[str]:
    gates = payload["decision_view"]["gates"]
    blocks = (_as_saved(gates) if saved else gates)["blocks"]
    return [f"{block['headline']}: {block['detail']}" for block in blocks]


@pytest.mark.parametrize("name", SCENARIOS)
def test_each_active_gate_is_listed_with_its_detail_under_the_authority(
    cases: dict, screens: dict, name: str
) -> None:
    """The parity review's item 1: only the older gate brief printed each gate's detail sentence.
    The detail panel and a reopened run now list them directly under the summary and its
    framing; the two cards stay as short as they were."""

    summary, framing = SCENARIOS[name]
    lines = _gate_lines(cases[name])
    kept = _gate_lines(cases[name], saved=True)
    assert lines and len(lines) == len(kept) == len(cases[name]["gate_result"]["hard_blocks"])
    for surface, listed in (("detail", lines), ("history", kept)):
        texts = screens[name][surface]
        at = texts.index(summary)
        assert texts[at : at + 2 + len(listed)] == [summary, framing, *listed], (name, surface)
    for surface in ("single", "batch"):
        for line in (*lines, *kept):
            assert line not in screens[name][surface], (name, surface, line)
    # The evidence gate's own line (the exact-final review's minor m4). On a live analysis it
    # is the backend's reason for the verdict at hand, which main showed as a key reason and
    # the redesign had dropped: the threshold and the count are on the screen again. A reopened
    # run does not store the verdict: it keeps the fixed sentence and says so. The two never
    # contradict each other, and neither says anything about the market.
    blocked = "SKILL_NOT_DEMONSTRATED" in cases[name]["gate_result"]["hard_blocks"]
    live = f"Evidence gate: {LIVE_EVIDENCE_REASON}"
    stored = (
        "Evidence gate: Directional skill is not established for this model and timeframe. Its "
        "verdict and counts are not kept in saved history."
    )
    assert (live in lines) is blocked and (stored in kept) is blocked
    assert live not in screens[name]["history"] and stored not in screens[name]["detail"]
    if blocked:
        assert _evidence_reason(cases[name]) == LIVE_EVIDENCE_REASON


def test_the_probability_sections_own_sentence_is_in_the_authoritative_block(
    cases: dict, screens: dict
) -> None:
    """The parity review's item 4: "~6 bars ahead ... not a clock timeout ... not expected
    return" was said by the older Probability section alone. The view carries the backend's
    sentence: under what the range means on the detail panel, and leading a reopened run's block
    (which has no view sentence of its own)."""

    for name in SCENARIOS:
        view = cases[name]["decision_view"]
        assert view["range"]["explanation"] == EXPLANATION, name
        detail = screens[name]["detail"]
        block = harness._between(detail, "Decision view", "Decision")
        at = block.index(view["range"]["meaning"])
        assert block[at + 1 : at + 3] == [EXPLANATION, view["cost"]["label"]], name
        assert screens[name]["history"][:2] == ["Saved analysis", EXPLANATION], name
        for surface in ("single", "batch"):
            assert EXPLANATION not in screens[name][surface], (name, surface)
    # An accepted state's own sentence says what its percentages carry: it has none (SYNTHETIC).
    for name in ("accepted_claim_SYNTHETIC", "permission_SYNTHETIC"):
        assert cases[name]["decision_view"]["range"]["explanation"] is None, name
        block = harness._between(screens[name]["detail"], "Decision view", "Decision")
        assert EXPLANATION not in block, name


@pytest.mark.parametrize("name", [*SCENARIOS, SAVED_BEFORE])
def test_a_reopened_run_has_a_block_of_its_own_and_says_what_it_does_not_store(
    cases: dict, reopened: dict, screens: dict, name: str
) -> None:
    """The parity review's item 2. The block holds the gate authority built when the run was
    read, the values the stored record holds, under the labels a live analysis uses, and for a
    value it does not hold the sentence that says so, never "n/a"."""

    live = cases["evidence_only" if name == SAVED_BEFORE else name]
    saved = reopened[name]["detail"]["saved_run_view"]
    texts = screens[name]["history"]
    block = harness._between(texts, "Saved analysis", "Model Quality")
    meaning, cost = saved["range"]["meaning"], saved["cost"]["label"]
    assert block[-2:] == [meaning, cost], name
    rows = block[2 + 2 + len(saved["gates"]["blocks"]) : -2]
    # The cost's caveat, when the record supports one, is a row of its own under the cost.
    caveat = saved["cost"]["caveat"]
    expected = list(SAVED_ROWS)
    if caveat is not None:
        expected.insert(expected.index("Round-trip cost") + 1, COST_NOTE)
    assert rows[0::2] == expected, name
    shown = dict(zip(rows[0::2], rows[1::2], strict=True))
    assert shown.get(COST_NOTE) == caveat, name
    assert "n/a" not in " ".join(block), f"{name}: a value that is not kept says so"
    # What the record holds reads exactly as the live analysis's own row read.
    scenario = "evidence_only" if name == SAVED_BEFORE else name
    live_rows = harness._between(screens[scenario]["detail"], "Asset · venue", meaning)
    live_shown = dict(zip(live_rows[0::2], live_rows[1::2], strict=True))
    for label in SAME_AS_LIVE:
        assert shown[label] == live_shown[label], (name, label)
    assert shown["Calibration"] == "DEFAULT_PHASE1A"
    assert shown["Reliability"] == "INSUFFICIENT_SAMPLE"
    # What it does not hold: the live analysis had these, and the saved run says they are not kept.
    for label in (
        "Reference close (Vietnam)",
        "Reference close (UTC)",
        "Horizon end (Vietnam)",
        "Horizon end (UTC)",
        "Evidence",
    ):
        assert shown[label] == NOT_KEPT and live_shown[label] != NOT_KEPT, (name, label)
    assert block.count(NOT_KEPT) == 5, name
    # The disposition is the gates' own (ABORT under the kill switch), not the brief's action.
    assert shown["Gate disposition (not a market call)"] == live["gate_result"]["action"]
    # The Overview and Gates rows of a reopened run show what its record holds, as the live
    # analysis's own rows read: no row reads "n/a" for a value another row of the screen shows.
    live_texts = screens[scenario]["detail"]
    for section, end, labels in (
        ("Overview", "Gates", ("Timeframe", "Horizon", DISPOSITION, "Data source")),
        ("Gates", "Market Data Quality", (GATE_ACTION, HARD_BLOCKS)),
    ):
        mine = harness._between(texts, section, end)
        theirs = harness._between(live_texts, section, end)
        for label in labels:
            assert harness._value(mine, label) == harness._value(theirs, label) != "n/a", (
                name,
                section,
                label,
            )
    overview = harness._between(texts, "Overview", "Gates")
    assert harness._value(overview, "Live data") == "yes"
    assert harness._value(overview, DISPOSITION) == shown[DISPOSITION]
    # No label of the run's own block is used again on the screen with another value.
    for label, value in shown.items():
        again = [texts[at + 1] for at, text in enumerate(texts) if text == label]
        assert set(again) == {value}, (name, label, again)


def test_a_run_reopened_in_the_same_session_reads_as_its_stored_copy_does(
    cases: dict, reopened: dict, screens: dict
) -> None:
    """Both read paths: the server's own copy of a run (not sanitized) and the stored copy show
    the same block, line for line."""

    held = {
        name: {
            "row": reopened[name]["row"],
            "detail": saved_run_view.attach_saved_run_view(cases[name]["detail_view"]),
        }
        for name in SCENARIOS
    }
    for name in SCENARIOS:
        assert held[name]["detail"]["decision_brief"] != reopened[name]["detail"]["decision_brief"]
    same_session = goldens.render({}, held)["screens"]
    for name in SCENARIOS:
        end = "Model Quality"
        assert harness._between(same_session[name]["history"], "Saved analysis", end) == (
            harness._between(screens[name]["history"], "Saved analysis", end)
        ), name


def test_a_reopened_run_whose_gate_result_cannot_be_read_says_so_and_frames_nothing(
    cases: dict, reopened: dict
) -> None:
    """Review finding D5, on the screen: a damaged stored gate result is never framed, so
    nothing shown can contradict the record. The block says that no gate result can be read,
    shows no disposition row, and still shows what else the record holds."""

    damaged = {}
    for name, gate in (("a_string", "NO_TRADE"), ("blocks_a_number", {"hard_blocks": 5})):
        stored = sanitize_for_export(copy.deepcopy(cases["risk_and_evidence"]["detail_view"]))
        stored["invalidation_detail"] = gate
        damaged[name] = {
            "row": reopened["risk_and_evidence"]["row"],
            "detail": saved_run_view.attach_saved_run_view(stored),
        }
    rendered = goldens.render({}, damaged)["screens"]
    note = "No gate result can be read from this saved analysis, so no gate framing is shown."
    for name in damaged:
        texts = rendered[name]["history"]
        assert texts[:4] == ["Saved analysis", EXPLANATION, note, "Asset · venue"], name
        block = harness._between(texts, "Saved analysis", "Model Quality")
        assert DISPOSITION not in block, name
        assert texts[texts.index("Up (above the band)") + 1].endswith("%"), name
        for text in texts:
            assert "gate is active" not in text and "risk gate" not in text.lower(), text


def test_a_damaged_saved_record_reads_honestly_on_the_screen(cases: dict, reopened: dict) -> None:
    """Review finding 4 and its family, on the screen. Stored records that lost or contradict a
    part: the forced token never stands alone; a value the record does not hold says "Not kept
    in saved history." on a row of its own, never inside another value; and percentages the
    record holds are shown, not called "not assessed"."""

    def stored(scenario: str, change) -> dict:
        detail = sanitize_for_export(copy.deepcopy(cases[scenario]["detail_view"]))
        change(detail)
        return {
            "row": reopened[scenario]["row"],
            "detail": saved_run_view.attach_saved_run_view(detail),
        }

    gate = "invalidation_detail"
    damaged = {
        "flag_passed": stored("evidence_only", lambda d: d[gate].update(hard_gate_passed=True)),
        "flag_passed_no_blocks": stored(
            "evidence_only", lambda d: d[gate].update(hard_gate_passed=True, hard_blocks=[])
        ),
        "liquidity_lost": stored(
            "wide_spread_and_evidence", lambda d: d.pop("liquidity_execution_detail")
        ),
        "data_quality_lost": stored("evidence_only", lambda d: d.pop("data_quality_detail")),
        "probability_lost": stored("evidence_only", lambda d: d.pop("probability_detail")),
        "brief_lost": stored("evidence_only", lambda d: d.pop("decision_brief")),
        "only_a_run_id": {
            "row": reopened["evidence_only"]["row"],
            "detail": saved_run_view.attach_saved_run_view({"run_id": "x"}),
        },
    }
    rendered = goldens.render({}, damaged)["screens"]
    label = "Gate disposition (not a market call)"
    for name, surfaces in rendered.items():
        texts = surfaces["history"]
        block = harness._between(texts, "Saved analysis", "Model Quality")
        for text in texts:
            assert NOT_KEPT not in text or text == NOT_KEPT, f"{name}: inside a value: {text!r}"
            if "ELEVATED_RISK_AVOID" in text:
                assert FORCED_NOTE in text, f"{name}: the forced token alone: {text!r}"
        assert "n/a" not in " ".join(block), name
    shown = {name: surfaces["history"] for name, surfaces in rendered.items()}
    assert harness._value(shown["flag_passed"], label) == "NO_TRADE"
    assert harness._value(shown["flag_passed_no_blocks"], label) == FORCED_NOTE
    # The liquidity state is lost: the percentage stands by itself, and the cost says it is lost.
    lost = shown["liquidity_lost"]
    assert harness._value(lost, "In band (inside the decision band)") == "40.04%"
    assert harness._value(lost, "Round-trip cost") == NOT_KEPT
    assert "Liquidity is not viable" not in " ".join(lost), "no finding without its measurement"
    # The provider state is lost: the stored percentages are shown, and the venue says it is lost.
    quality = shown["data_quality_lost"]
    assert harness._value(quality, "Up (above the band)") == "39.38%"
    assert not any("Not assessed" in text for text in quality)
    assert harness._value(quality, "Asset") == "BTC/USDT"
    assert harness._value(quality, "Venue") == NOT_KEPT and "Asset · venue" not in quality
    assert harness._value(shown["probability_lost"], "Up (above the band)") == NOT_KEPT
    assert harness._value(shown["brief_lost"], "Evidence level") == NOT_KEPT
    bare = shown["only_a_run_id"]
    assert bare[1] == (
        "No gate result can be read from this saved analysis, so no gate framing is shown."
    )
    assert label not in harness._between(bare, "Saved analysis", "Model Quality")


def test_a_gate_view_of_a_version_this_screen_does_not_know_is_not_rendered(cases: dict) -> None:
    """The screen renders the gate view it knows (gate_view.v1). One stamped with another version
    is not read as if it were known: no summary, framing or gate list is drawn from it, on any
    surface, and the rest of the view is unchanged."""

    other = copy.deepcopy(cases["risk_and_evidence"])
    gates = other["decision_view"]["gates"]
    gates["schema_version"] = "gate_view.v2"
    known = goldens.render({"case": cases["risk_and_evidence"]}, {})["screens"]["case"]
    unknown = goldens.render({"case": other}, {})["screens"]["case"]
    lines = [gates["summary"], gates["framing"], *_gate_lines(other)]
    for surface in ("single", "batch", "detail"):
        shown = [text for text in unknown[surface] if text in lines]
        # The kept "Hard gates" check still states its own finding (the stack's sentence).
        assert shown == ([gates["summary"]] if surface == "detail" else []), surface
        assert [text for text in known[surface] if text not in lines] == [
            text for text in unknown[surface] if text not in lines
        ], surface
        assert gates["framing"] in known[surface], surface


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
