"""The owner's UX comprehension check (plan §23 "UX"; scripts/ux_comprehension/card.py).

Plan §23: UX is PASS only when predefined owner-task scenarios distinguish invalid data, an
unvalidated model, an accepted forecast, a directional permission and saved/unsaved state. These
tests prove that the generated scenarios do so on the real gates, the real backend builders and
the real frontend; that each analysis on the card is what the real detail panel renders; that the
answer key is computed from each analysis's payload and receipt, never typed; that no question
can be answered by finding its words on the card; that the two tempting misreadings (the gates'
disposition as a market call; the badge or the request-time row as the save receipt) are wrong
on every analysis; that the acceptance registries are left empty; and that the committed card is
current and never marked run.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
import re
import subprocess

import fullscreen_goldens as goldens
import pytest

from crypto_probability_engine.adapters import provider_selection
from crypto_probability_engine.adapters.symbol_universe import ProviderSymbolUniverse
from crypto_probability_engine.api import analysis_service, save_receipt
from crypto_probability_engine.api.schemas import AnalysisRequest
from crypto_probability_engine.config.defaults import DEFAULT_PHASE1A, min_history_for
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.detail import decision_view
from crypto_probability_engine.detail.decision_view import STATE_COPY
from crypto_probability_engine.normalizers.symbols import normalize_symbol
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from crypto_probability_engine.quant.epistemic_sufficiency import assess_epistemic_sufficiency
from scripts.ux_comprehension import card
from tests.fixtures.market_data import make_snapshot

harness = goldens.harness
# The Storage row once the screen holds the analysis's save receipt (frontend/app.js
# SAVE_RECEIPT_TEXT): the state the backend gives, in the screen's own words.
RECEIPT_TEXT = {
    "SAVED": "Saved to Recent Analysis history",
    "FAILED": (
        "Save not confirmed: this analysis may be missing from Recent Analysis history after a "
        "restart"
    ),
    "NOT_RETAINED": "Not retained: no storage is configured",
}
# The page's own words for what storage said when it was asked (persistenceStatusText).
STATUS_TEXT = {
    "OK": "Storage available",
    "UNAVAILABLE": (
        "Storage unavailable when requested — this analysis may not be kept in Recent Analysis "
        "history"
    ),
    "STATELESS": "No storage configured — analyses are kept only until the server restarts",
    "UNKNOWN": "Storage status unknown",
}
LETTERS = list("ABCDEFGHI")


@pytest.fixture(scope="module")
def screens() -> dict[str, dict[str, object]]:
    shown = {}
    for screen in card.screens():
        (rows,) = [block["rows"] for block in screen["blocks"] if block["kind"] == "rows"]
        shown[screen["scenario"].letter] = {
            **screen,
            "rows": dict(rows),
            "headline": screen["view"]["headline"],
            "texts": card.shown_lines(screen),
            "key": card.answers(screen["payload"], screen["receipt"]),
        }
    return shown


def test_the_analyses_cover_what_the_check_must_tell_apart(
    screens: dict[str, dict[str, object]],
) -> None:
    """Owner ruling S5: the evidence gate alone; a real risk gate beside it; a data gate (an
    unusable order book, and a degraded provider); a system gate; the accepted states
    (SYNTHETIC); a save that is not confirmed; storage not configured."""

    assert sorted(screens) == LETTERS == [scenario.letter for scenario in card.SCENARIOS]
    blocks = {
        letter: [entry["block"] for entry in screen["view"]["gates"]["blocks"]]
        for letter, screen in screens.items()
    }
    evidence = ["SKILL_NOT_DEMONSTRATED"]
    assert blocks == {
        "A": evidence,
        "B": ["PROVIDER_DEGRADED", *evidence],
        "C": [],
        "D": evidence,
        "E": evidence,
        "F": ["TAIL_RISK_BREACH", *evidence],
        "G": ["LIQUIDITY_NOT_VIABLE", *evidence],
        "H": ["KILL_SWITCH", *evidence],
        "I": evidence,
    }
    states = {letter: screen["view"]["state"] for letter, screen in screens.items()}
    assert states == {
        **dict.fromkeys("ADFGHI", "NO_ACCEPTED_CLAIM"),
        "B": "INVALID_OR_UNAVAILABLE_DATA",
        "C": "DIRECTIONAL_PERMISSION",
        "E": "ACCEPTED_FORECAST_CLAIM",
    }
    for letter, screen in screens.items():
        assert screen["headline"] == STATE_COPY[states[letter]][0], letter
    kinds = {letter: screen["view"]["gates"]["kinds"] for letter, screen in screens.items()}
    assert kinds["F"] == ["EVIDENCE", "RISK"] and kinds["A"] == ["EVIDENCE"]
    assert kinds["B"] == kinds["G"] == kinds["H"] == ["EVIDENCE", "SYSTEM_OR_DATA"]
    # G's order book was served and is unusable: a data gate that claims no finding.
    liquidity_gate = screens["G"]["view"]["gates"]["blocks"][0]
    assert liquidity_gate["headline"] == "Liquidity could not be measured"
    assert "unusable data, not a finding about the market" in liquidity_gate["detail"]
    # The save receipt in each of its states on this card, and the accepted states are marked.
    receipts = {letter: screen["receipt"]["state"] for letter, screen in screens.items()}
    assert receipts == {
        **dict.fromkeys("ACEFH", "SAVED"),
        **dict.fromkeys("BDG", "FAILED"),
        "I": "NOT_RETAINED",
    }
    flags = {scenario.letter: scenario.synthetic for scenario in card.SCENARIOS}
    assert flags == {**dict.fromkeys("ADFGHI", False), **dict.fromkeys("BCE", True)}


def _expected_key(payload: dict, receipt: dict) -> tuple[str, ...]:
    """The key, derived here a second time from the payload's own fields."""

    view = payload["decision_view"]
    kinds = [entry["kind"] for entry in view["gates"]["blocks"]]
    state = view["state"]
    standing = "d" if not view["range"]["assessed"] else (
        "c" if view["directional_permission"] else "b" if view["accepted_claim"] else "a"
    )
    assert (state == "INVALID_OR_UNAVAILABLE_DATA") is (standing == "d")
    return (
        "yes" if "RISK" in kinds else "no",
        "yes" if "EVIDENCE" in kinds else "no",
        "yes" if "SYSTEM_OR_DATA" in kinds else "no",
        standing,
        "b" if payload["decision_synthesis"]["action_permission"]["can_enter_now"] else "c",
        {"SAVED": "a", "NOT_RETAINED": "b", "FAILED": "c", "PENDING": "c"}[receipt["state"]],
    )


def test_the_answer_key_is_computed_from_the_payload_and_the_receipt_never_typed(
    screens: dict[str, dict[str, object]],
) -> None:
    """Owner ruling S5: the key comes from the product's own facts. `answers` takes a payload and
    a receipt and nothing else; a scenario holds inputs and no answer; each answer is one of its
    question's fixed choices; and changing a fact of the payload changes the answer it decides."""

    assert list(inspect.signature(card.answers).parameters) == ["payload", "receipt"]
    fields = {field.name for field in dataclasses.fields(card.Scenario)}
    assert fields == {
        *("letter", "name", "synthetic", "accepted", "permission", "data_ok", "tail"),
        *("usable_book", "kill", "requested", "badge", "receipt"),
    }
    source = (card.ROOT / "scripts" / "ux_comprehension" / "card.py").read_text(encoding="utf-8")
    body = source[source.index("def answers(") : source.index("@contextmanager")]
    code = body.split('"""')[2]
    assert "scenario" not in code.lower(), "the key never reads a scenario"
    assert 'payload["decision_view"]' in code and 'receipt["state"]' in code
    text = card.card_markdown()
    assert len(card.QUESTIONS) == 6
    for letter, screen in screens.items():
        payload, receipt = screen["payload"], screen["receipt"]
        key = screen["key"]
        assert key == _expected_key(payload, receipt), letter
        for answer, (_, choices) in zip(key, card.QUESTIONS, strict=True):
            assert answer in [choice for choice, _ in choices], (letter, answer)
        assert f"| {letter} | {' | '.join(key)} |" in text, letter
        # The synthesis is the product's own, for the same gate result.
        synthesis = payload["decision_synthesis"]
        assert synthesis["action_permission"]["can_enter_now"] is False, letter
        assert synthesis["trade_plan_skeleton"]["not_trade_command"] is True, letter
    # Each fact decides its answer: change the fact, and only that answer moves.
    payload, receipt = screens["A"]["payload"], screens["A"]["receipt"]
    base = card.answers(payload, receipt)

    def changed(path: tuple[str, ...], value: object) -> tuple[str, ...]:
        copy = json.loads(json.dumps(payload))
        target = copy
        for name in path[:-1]:
            target = target[name]
        target[path[-1]] = value
        return card.answers(copy, receipt)

    gates = ("decision_view", "gates")
    assert changed((*gates, "risk_gate_active"), True) == ("yes", *base[1:])
    assert changed((*gates, "kinds"), ["SYSTEM_OR_DATA"]) == (base[0], "no", "yes", *base[3:])
    assert changed(("decision_view", "state"), "ACCEPTED_FORECAST_CLAIM")[3] == "b"
    assert changed(("decision_synthesis", "action_permission", "can_enter_now"), True)[4] == "b"
    for state, answer in (("NOT_RETAINED", "b"), ("FAILED", "c"), ("PENDING", "c")):
        assert card.answers(payload, {**receipt, "state": state}) == (*base[:5], answer)
    # Every choice of every question is the key of some analysis, except the two no screen of
    # this product can say: "stay out" and "proceed".
    for position, (_, choices) in enumerate(card.QUESTIONS):
        used = {screen["key"][position] for screen in screens.values()}
        unused = {choice for choice, _ in choices} - used
        assert unused == ({"a", "b"} if position == 4 else set()), (position, unused)


# The only words of four letters or more a question may share with a screen: function words,
# which carry no answer. Every other such word of a question or of a choice must be absent.
_COMMON = {
    *("this", "that", "what", "does", "would", "were", "there", "here", "them", "they"),
    *("about", "because", "from", "never", "with"),
}
_WORD = re.compile(r"[a-z]+")


def _stem(word: str) -> str:
    for ending in ("ing", "ed", "es", "s"):
        if word.endswith(ending) and len(word) - len(ending) >= 4:
            return word[: -len(ending)]
    return word


def _distinctive(text: str) -> set[str]:
    """The words of a question or a choice that could be looked up on a screen."""

    words = _WORD.findall(text.lower())
    return {_stem(word) for word in words if len(word) >= 4 and word not in _COMMON}


def test_no_question_can_be_answered_by_finding_its_words_on_the_card(
    screens: dict[str, dict[str, object]],
) -> None:
    """Owner ruling S5: the reviewer answered the card before this one 30 of 30 by matching a
    phrase of each question to a line on the card. No distinctive word of any question or of any
    of its choices is on any analysis now (compared without their endings), and no three words
    in a row are either: the questions ask what a screen means, in other words than its own."""

    asked: dict[str, str] = {}
    for number, (question, choices) in enumerate(card.QUESTIONS, start=1):
        asked[f"question {number}"] = question
        for choice, meaning in choices:
            asked[f"question {number}, answer {choice}"] = meaning
    assert sum(len(_distinctive(text)) for text in asked.values()) > 50, "the guard reads words"
    text = card.card_markdown()
    for letter, screen in screens.items():
        # Everything printed for this analysis: the product's lines and the card's own around
        # them. Every line the screen code drew is among them.
        printed = text.split(f"## Analysis {letter}\n")[1].split("\n## ")[0].lower()
        for line in screen["texts"]:
            assert line.lower() in printed, (letter, line)
        on_screen = {_stem(word) for word in _WORD.findall(printed)}
        joined = " ".join(_WORD.findall(printed))
        for where, sentence in asked.items():
            shared = _distinctive(sentence) & on_screen
            assert shared == set(), f"analysis {letter}, {where}: {sorted(shared)} is printed"
            words = _WORD.findall(sentence.lower())
            for at in range(len(words) - 2):
                run = " ".join(words[at : at + 3])
                assert run not in joined, f"analysis {letter}, {where}: {run!r} is printed"
    # The guard has teeth: the questions of the card before this one fail it.
    old = "Does the screen say this analysis is saved in Recent Analysis history?"
    saved_line = {_stem(word) for word in _WORD.findall(RECEIPT_TEXT["SAVED"].lower())}
    assert _distinctive(old) & saved_line >= {"saved", "recent", "history"}
    old_risk = "Does the screen report a risk gate: a finding about market conditions or execution?"
    f_words = {_stem(w) for line in screens["F"]["texts"] for w in _WORD.findall(line.lower())}
    assert len(_distinctive(old_risk) & f_words) >= 5


def _market_call_reader(screen: dict) -> tuple[str, ...]:
    """A reader who takes BLOCK and the Gate disposition for a call on the market: whatever holds
    an analysis up is about the market, and the disposition says what to do."""

    key = screen["key"]
    disposition = screen["payload"]["frontend_display"]["disposition"]
    blocked = screen["view"]["gates"]["blocked"]
    stay_out = disposition in {"NO_TRADE", "ABORT"}
    return ("yes" if blocked else "no", "no", "no", key[3], "a" if stay_out else "b", key[5])


def _storage_readers(screen: dict) -> list[str]:
    """What a reader answers to the storage question who takes the badge at the top, or the
    "Storage when requested" row, for the word on this one analysis."""

    by_status = {"OK": "a", "STATELESS": "b", "UNAVAILABLE": "c", "UNKNOWN": "c"}
    scenario = screen["scenario"]
    return [by_status[scenario.badge], by_status[scenario.requested]]


def test_the_two_tempting_misreadings_are_wrong_on_every_analysis(
    screens: dict[str, dict[str, object]],
) -> None:
    """Owner ruling S5. On every analysis at least one question is answered wrongly by a reader
    who takes BLOCK / NO_TRADE as a market call, and at least one by a reader who takes the
    storage badge or the request-time row for the save receipt."""

    for letter, screen in screens.items():
        key = screen["key"]
        read = zip(_market_call_reader(screen), key, strict=True)
        wrong = [number for number, (given, right) in enumerate(read, start=1) if given != right]
        assert wrong, f"{letter}: the market-call reader gets every answer right"
        assert 5 in wrong, letter
        badge, requested = _storage_readers(screen)
        assert key[5] != badge or key[5] != requested, f"{letter}: both storage readers are right"
        # The three storage lines are on the card as the page words them, and they differ.
        scenario = screen["scenario"]
        assert screen["badge"] == f"Storage, last checked: {STATUS_TEXT[scenario.badge]}", letter
        assert screen["requested"] == STATUS_TEXT[scenario.requested], letter
        assert screen["rows"]["Storage"] == RECEIPT_TEXT[scenario.receipt], letter
        assert screen["payload"]["debug"]["persistence_status"] == scenario.requested, letter
    # Beside the disposition, the first question catches the market-call reader on every
    # analysis that is held up without a risk gate.
    for letter in "ABDEGHI":
        assert _market_call_reader(screens[letter])[0] != screens[letter]["key"][0], letter
    # The badge reader is wrong on every analysis; the request-time reader on all but two, where
    # that row and the receipt cannot honestly disagree (C: both say kept; I: no storage at all).
    readers = {letter: _storage_readers(screen) for letter, screen in screens.items()}
    badge_wrong = [at for at, read in readers.items() if read[0] != screens[at]["key"][5]]
    requested_wrong = [at for at, read in readers.items() if read[1] != screens[at]["key"][5]]
    assert badge_wrong == ["A", "B", "C", "D", "F", "G", "I"], badge_wrong
    assert requested_wrong == ["A", "B", "D", "E", "F", "G", "H"], requested_wrong


def test_the_save_receipt_on_the_card_is_the_backends_in_the_screens_words(
    screens: dict[str, dict[str, object]],
) -> None:
    """Owner rulings R4 and S5: the save receipt is built and its UX acceptance is open. Each
    analysis's Storage row is the backend's own receipt for it, in app.js's own words, put in the
    row as the screen puts it; a receipt this screen cannot show leaves the row as it was."""

    source = card.APP_JS.read_text(encoding="utf-8")
    texts = card._extract(source, "SAVE_RECEIPT_TEXT")
    assert f'SAVED: "{RECEIPT_TEXT["SAVED"]}",' in texts
    assert f'NOT_RETAINED: "{RECEIPT_TEXT["NOT_RETAINED"]}",' in texts
    first, second = RECEIPT_TEXT["FAILED"][:86], RECEIPT_TEXT["FAILED"][86:]
    assert f'"{first}" +\n    "{second}",' in texts
    for screen in screens.values():
        given, payload = screen["receipt"], screen["payload"]
        assert given["schema_version"] == save_receipt.SCHEMA_VERSION == "save_receipt.v1"
        assert given["run_id"] == payload["run_id"], "each analysis is asked for its own receipt"
        assert given == card.receipt(screen["scenario"]), "the backend's own builder made it"
        assert sorted(given) == ["checked_at_utc", "run_id", "schema_version", "state"]
    payload, _ = card.build(card.SCENARIOS[0])
    for bad in (None, {}, {**card.receipt(card.SCENARIOS[0]), "run_id": "another-run"}):
        (drawn,) = card.render([(payload, bad, "OK")])
        (rows,) = [block["rows"] for block in drawn["blocks"] if block["kind"] == "rows"]
        assert dict(rows)["Storage"] == STATUS_TEXT["UNAVAILABLE"], bad
    text = card.card_markdown()
    note = " ".join(text[text.index("- The three storage lines.") :].split())
    assert "saved (A, C, E, F and H), not confirmed (B, D and G) and not retained (I)" in note
    assert "its UX acceptance is open until this check is run" in note


def test_each_analysis_is_what_the_real_detail_panel_renders(
    screens: dict[str, dict[str, object]],
) -> None:
    """The card cannot drift from the screen: the whole of app.js renders each analysis's detail
    panel on the DOM stand-in. Its Decision view section, its Overview storage row and the
    page's badge are the card's lines, line for line. Only the Decision view's Storage row
    differs: no backend answers the stand-in, so the panel keeps storage's status at request
    time, where the card shows the receipt."""

    jobs = {
        letter: {"payload": screen["payload"], "badge": screen["scenario"].badge}
        for letter, screen in screens.items()
    }
    script = "\n".join(
        [
            harness._DOM_STAND_IN,
            card.APP_JS.read_text(encoding="utf-8"),
            f"const jobs = {json.dumps(jobs)};",
            """
(async () => {
  const out = {};
  for (const [letter, job] of Object.entries(jobs)) {
    renderStructuredDetail(job.payload, {});
    for (let tick = 0; tick < 5; tick += 1) await new Promise((done) => setTimeout(done, 0));
    updatePersistenceStatus(job.badge);
    out[letter] = { panel: visibleTexts(detailPanel), badge: persistenceStatusBadge.textContent };
  }
  process.stdout.write(JSON.stringify(out), () => process.exit(0));
})();
""",
        ]
    )
    done = subprocess.run(  # noqa: S603 - node on a script built here, read on stdin
        [harness.NODE, "-"], input=script, capture_output=True, encoding="utf-8", timeout=60,
        check=True,
    )
    drawn = json.loads(done.stdout)
    assert sorted(drawn) == LETTERS
    committed = card.CARD.read_text(encoding="utf-8")
    for letter, screen in screens.items():
        panel = drawn[letter]["panel"]
        view = harness._between(panel, "Decision view", "Decision")
        overview = harness._between(panel, "Overview", "Gates")
        requested = harness._value(overview, card.REQUESTED_ROW_LABEL)
        on_card = list(screen["texts"])
        assert on_card[0] == drawn[letter]["badge"], letter
        assert on_card[-2:] == [card.REQUESTED_ROW_LABEL, requested], letter
        block = on_card[1:-2]
        at = block.index("Storage") + 1
        assert view[at] == requested and block[at] in RECEIPT_TEXT.values(), letter
        block[at] = view[at]
        assert block == view, letter
        # Every line of the analysis is on the committed card, in this order.
        printed = committed.split(f"## Analysis {letter}\n")[1].split("\n## ")[0]
        position = -1
        for line in [on_card[0], *on_card[2:]]:
            position = printed.index(line, position + 1)


def test_the_gates_on_the_card_are_the_real_gates_not_typed_by_hand(
    screens: dict[str, dict[str, object]],
) -> None:
    """CLAUDE_EXPERT_CHECK finding F9: the card's gate dispositions were typed by hand. Each
    analysis's gate result is what gates/composite.py returns for its inputs, and its
    disposition what the product derives from that."""

    expected = {
        **dict.fromkeys("ADEFGI", "NO_TRADE"),
        "B": "ABORT",
        "C": "CONSTRUCTIVE_CAUTIOUS",
        "H": "ABORT",
    }
    for letter, disposition in expected.items():
        screen = screens[letter]
        gates = screen["view"]["gates"]
        assert screen["payload"]["frontend_display"]["disposition"] == disposition, letter
        label = [name for name in screen["rows"] if name.startswith("Gate disposition")]
        assert [screen["rows"][name] for name in label] == [disposition], letter
        assert gates["blocked"] is bool(gates["blocks"]), letter
        for gate in gates["blocks"]:
            assert f"{gate['headline']}: {gate['detail']}" in screen["texts"], letter
        at = screen["texts"].index(gates["summary"])
        assert screen["texts"][at + 1] == gates["framing"], letter
    assert not hasattr(card.SCENARIOS[0], "disposition"), "no scenario carries one to type"
    permission = "Gate disposition (accepted directional permission; not financial advice)"
    assert permission in screens["C"]["rows"]
    assert not any("not a market call" in line for line in screens["C"]["texts"])
    for letter in ("C", "E"):
        assert screens[letter]["rows"]["Evidence level"] == screens[letter]["headline"], letter
    for letter in "ABDFGHI":
        assert screens[letter]["rows"]["Evidence level"] == card.MODEL_READINESS_COPY, letter
    assert screens["B"]["rows"]["Up (above the band)"] == "Not assessed"
    # Each SYNTHETIC accepted state reads as coherent evidence: an accepted forecast (E) shows
    # measured outcomes without demonstrated directional skill, a permission (C) shows the skill.
    evidence = {letter: screen["rows"]["Evidence"] for letter, screen in screens.items()}
    assert evidence["E"] == "NO_DEMONSTRATED_SKILL · 400 resolved outcomes · MEASURED"
    assert evidence["C"] == "SKILL_DEMONSTRATED · 400 resolved outcomes · MEASURED"
    for letter in "ABDFGHI":
        assert evidence[letter].startswith("INSUFFICIENT_EVIDENCE · 0 "), letter
    for letter in "ABDEFGHI":
        assert "Gate disposition (not a market call)" in screens[letter]["rows"], letter
    # A risk gate is named as a finding and nothing else is; without one the view says so.
    risk = screens["F"]["view"]["gates"]
    assert risk["summary"].startswith("A risk gate is active: Extreme-move risk is too high.")
    assert risk["framing"].startswith("The risk gate (Extreme-move risk is too high) is a finding")
    assert not any("reason to act or to avoid acting" in line for line in screens["F"]["texts"])
    for letter in "ADI":
        assert screens[letter]["view"]["gates"]["summary"].endswith("No risk gate is active.")
        assert "not a reason to act or to avoid acting" in screens[letter]["view"]["detail"]
        assert screens[letter]["view"]["detail"] in screens[letter]["texts"], letter
    for letter in "ABCDEGHI":
        lines = screens[letter]["texts"]
        assert not any("risk gate is active:" in line.lower() for line in lines), letter


def test_the_registries_stay_empty() -> None:
    card.card_markdown()
    assert decision_view.ACCEPTED_FORECAST_CLAIMS == frozenset()
    assert decision_view.ACCEPTED_DIRECTIONAL_PERMISSIONS == frozenset()


def test_the_committed_card_is_current_says_what_it_is_and_is_never_marked_run() -> None:
    text = card.card_markdown()
    assert card.CARD.read_text(encoding="utf-8") == text, (
        "run scripts/ux_comprehension/card.py --write"
    )
    assert text.count("**Status: PREPARED, NOT RUN.**") == 1
    for marked in ("Status: RUN", "Status: PASS", "Status: DONE", "RESULT"):
        assert marked not in text, marked
    assert "Analyses C, E are **SYNTHETIC**" in text
    assert "Analysis B is **SYNTHETIC** too, for a different reason." in text
    assert "the product shows an error message and no analysis" in text
    assert "Some analyses below are **SYNTHETIC**" in text
    assert text.index("**SYNTHETIC**") < text.index("## Analysis A"), "said before any analysis"
    assert text.index("## Answer key") > text.index("## Analysis I"), "the key comes last"
    # The plan's criterion is quoted, after the key.
    criterion = (
        'UX is "PASS only when predefined owner-task scenarios distinguish: invalid data;\n'
        '  unvalidated model; accepted forecast; directional permission; saved/unsaved state."'
    )
    assert criterion in text and text.index(criterion) > text.index("## Answer key")
    # Each question is printed with its fixed choices, before any analysis.
    for number, (question, choices) in enumerate(card.QUESTIONS, start=1):
        at = text.index(f"{number}. {question}\n")
        assert at < text.index("## Analysis A")
        for answer, meaning in choices:
            assert f"   - **{answer}** — {meaning}\n" in text


def _view_branch_and_the_rest(function_source: str) -> tuple[str, str]:
    """(horizonCard's `if (view) {…}` branch, horizonCard without that branch and its `else`)."""

    start = function_source.index("if (view) {")
    middle = function_source.index("} else {", start)
    depth = 0
    for position in range(function_source.index("{", middle), len(function_source)):
        depth += {"{": 1, "}": -1}.get(function_source[position], 0)
        if depth == 0:
            rest = function_source[:start] + function_source[position + 1 :]
            return function_source[start:middle], rest
    raise AssertionError("horizonCard's else branch does not close")


def test_the_card_names_what_the_screens_show_beside_it() -> None:
    """CLAUDE_EXPERT_CHECK 2026-10-10: the card says what the screens show beside what it
    prints. Each thing it names around the view is rendered by app.js's timeframe card when a
    view is present (in its view branch, or outside both branches), and each section it names
    under the view is one the detail panel renders, in that order."""

    text = card.card_markdown()
    assert "none of the following is on this card, so a PASS\n  here says nothing about it" in text
    assert "The gates are the product's own" in text
    source = card.APP_JS.read_text(encoding="utf-8")
    timeframe_card = card._extract(source, "horizonCard")
    view_branch, rest = _view_branch_and_the_rest(timeframe_card)
    assert "decisionViewRows(payload, view)" in view_branch
    assert len(card.OUTSIDE_THE_VIEW) == 5
    for name, literal, in_view_branch in card.OUTSIDE_THE_VIEW:
        assert f"    - {name}\n" in text, name
        where = view_branch if in_view_branch else rest
        assert literal in where, f"{name}: horizonCard no longer shows {literal} with a view"
    assert "renderPermissionRow" not in source and "Immediate action" not in text
    assert len(card.UNDER_THE_VIEW) == 5
    for name in card.UNDER_THE_VIEW:
        assert f"    - {name}\n" in text, name
    panel = card._extract(source, "renderStructuredDetail")
    order = [
        panel.index("...(checksSection ? [checksSection] : []),"),
        panel.index("renderModelQualitySection("),
        panel.index('section("Overview", ['),
        panel.index('section("Gates", ['),
        panel.index('section("Market Data Quality", ['),
        panel.index('section("Debug / Raw JSON", ['),
    ]
    assert order == sorted(order)
    assert f'"{card.REQUESTED_ROW_LABEL}",' in panel, "Overview's own label"
    assert "renderDecisionViewSection(payload, view)" in panel
    assert "view.detail" in view_branch and "view.detail" in card._extract(source, "overviewCard")
    index_html = (card.ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    for screen in ("Single Crypto Analysis", "Batch Crypto Analysis"):
        assert screen in text and f">{screen}</button>" in index_html, screen


class _Venue:
    """A venue that serves one prepared snapshot (no network)."""

    def __init__(self, name: str, timeframe: str, count: int) -> None:
        self.name = name
        self._snapshot = make_snapshot(provider=name, timeframe=timeframe, count=count)

    def fetch_market_snapshot(self, symbol: object, timeframe: str) -> object:
        return self._snapshot

    def fetch_symbol_universe(self) -> ProviderSymbolUniverse:
        return ProviderSymbolUniverse(provider=self.name, symbols=frozenset({"BTC/USDT"}))


def _select(timeframe: str, venues: list[_Venue]) -> object:
    settings = Settings(
        data_mode="live",
        provider_priority=tuple(venue.name for venue in venues),
        candle_cache_ttl_seconds=0,
    )
    try:
        provider_selection.clear_provider_cache()
        return provider_selection.select_market_data(
            normalize_symbol("BTC"), timeframe, settings=settings, providers=venues
        )
    finally:
        provider_selection.clear_provider_cache()


@pytest.mark.parametrize("timeframe", DEFAULT_PHASE1A.timeframes)
@pytest.mark.parametrize("venues", [("binance",), ("binance", "okx")])
def test_on_live_data_invalid_data_ends_in_an_error_and_never_in_the_view(
    timeframe: str, venues: tuple[str, ...]
) -> None:
    """Why the card calls B SYNTHETIC, on live data. The venue selection refuses a history shorter
    than the one the epistemic check needs, and what it serves is OK or DEGRADED, so neither block
    that makes the view say "Data cannot support an assessment" can reach it."""

    needed = min_history_for(timeframe)
    with pytest.raises(provider_selection.ProviderSelectionError):
        _select(timeframe, [_Venue(name, timeframe, needed - 1) for name in venues])
    served = _select(timeframe, [_Venue(name, timeframe, needed) for name in venues])
    assert served.provider_state["status"] in {"OK", "DEGRADED"}
    assert assess_epistemic_sufficiency(served.snapshot)["action"] == "ALLOW"


@pytest.mark.parametrize("timeframe", DEFAULT_PHASE1A.timeframes)
def test_on_demo_data_the_view_is_never_the_invalid_data_state(timeframe: str) -> None:
    """The same, for the built-in demo data: the real service's view is the demo state."""

    payload = analysis_service.analyze_request(
        AnalysisRequest(symbol="BTC", timeframe=timeframe),
        settings=Settings(data_mode="fixture"),
        run_store=InMemoryRunStore(),
        prediction_origin="USER_REQUESTED",
    )
    view = payload["decision_view"]
    assert view["state"] == "NO_ACCEPTED_CLAIM"
    assert view["data"]["state"] == "DEMO"
    assert view["range"]["assessed"] is True


def test_the_generator_reads_no_database_and_sends_nothing() -> None:
    source = (card.ROOT / "scripts" / "ux_comprehension" / "card.py").read_text(encoding="utf-8")
    imports = [line for line in source.splitlines() if line.startswith(("import ", "from "))]
    for forbidden in (
        "psycopg",
        "httpx",
        "requests",
        "urllib",
        "socket",
        ".persistence",
        ".adapters",
    ):
        assert not any(forbidden in line for line in imports), forbidden
    assert "SUPABASE" not in source and "DATABASE_URL" not in source
