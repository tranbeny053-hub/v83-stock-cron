"""The owner's UX comprehension check (plan §23 "UX"; scripts/ux_comprehension/card.py).

Plan §23: UX is PASS only when predefined owner-task scenarios distinguish invalid data, an
unvalidated model, an accepted forecast, a directional permission and saved/unsaved state. These
tests prove that the generated scenarios do so on the real gates, the real backend builder and
the real frontend, that each analysis on the card is the Decision view the real detail panel
renders, that the answer key follows from each screen (not from the scenario's own flags alone),
that the acceptance registries are left empty, and that the committed card is current.
"""

from __future__ import annotations

import json
import subprocess
from itertools import combinations

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
SAVED = "Saved to Recent Analysis history"
NOT_CONFIRMED = (
    "Save not confirmed: this analysis may be missing from Recent Analysis history after a restart"
)
# The same row before a receipt answers: storage's status when the analysis was requested.
AT_REQUEST_TIME = "Storage available"
QUESTION_4 = "Does the screen say this analysis is saved in Recent Analysis history?"


def _texts(blocks: list[dict]) -> list[str]:
    """A drawn section as the lines a user reads, in order: what a screen's text is."""

    lines: list[str] = []
    for block in blocks:
        if block["kind"] == "rows":
            lines += [text for row in block["rows"] for text in row]
        elif block["kind"] == "list":
            lines += block["items"]
        elif block["text"].strip():
            lines.append(block["text"])
    return lines


@pytest.fixture(scope="module")
def screens() -> dict[str, dict[str, object]]:
    shown = {}
    for screen in card.screens():
        (rows,) = [block["rows"] for block in screen["blocks"] if block["kind"] == "rows"]
        shown[screen["scenario"].letter] = {
            **screen,
            "rows": dict(rows),
            "headline": screen["view"]["headline"],
            "texts": [screen["title"], *_texts(screen["blocks"])],
        }
    return shown


def test_each_scenario_shows_its_own_state(screens: dict[str, dict[str, object]]) -> None:
    expected = {
        "A": "NO_ACCEPTED_CLAIM",
        "B": "INVALID_OR_UNAVAILABLE_DATA",
        "C": "DIRECTIONAL_PERMISSION",
        "D": "NO_ACCEPTED_CLAIM",
        "E": "ACCEPTED_FORECAST_CLAIM",
        "F": "NO_ACCEPTED_CLAIM",
    }
    for letter, state in expected.items():
        view = screens[letter]["view"]
        assert view["state"] == state, letter
        assert screens[letter]["headline"] == STATE_COPY[state][0], letter


def test_the_scenarios_distinguish_every_section_23_dimension(
    screens: dict[str, dict[str, object]],
) -> None:
    # Invalid data: the only scenario whose range is not assessed.
    not_assessed = {
        letter
        for letter, screen in screens.items()
        if screen["rows"]["Up (above the band)"] == "Not assessed"
    }
    assert not_assessed == {"B"}
    # Unvalidated model, accepted forecast, directional permission: three different headlines.
    headlines = {screens[letter]["headline"] for letter in ("A", "E", "C")}
    assert len(headlines) == 3
    # Saved/unsaved: A and D differ in the Storage row alone.
    differing = {
        label
        for label in screens["A"]["rows"]
        if screens["A"]["rows"][label] != screens["D"]["rows"][label]
    }
    assert differing == {"Storage"}
    assert screens["A"]["rows"]["Storage"] == SAVED
    assert screens["D"]["rows"]["Storage"] == NOT_CONFIRMED
    assert screens["A"]["texts"][1:] != screens["D"]["texts"][1:]
    # Every pair of analyses can be told apart from what the screen shows.
    for left, right in combinations(sorted(screens), 2):

        def shown(letter: str) -> tuple[object, ...]:
            view = screens[letter]["view"]
            gate_summary = view["gates"]["summary"]
            return (view["headline"], view["detail"], gate_summary, screens[letter]["rows"])

        assert shown(left) != shown(right), (left, right)


def test_the_answer_key_follows_from_each_built_view(
    screens: dict[str, dict[str, object]],
) -> None:
    def yes_no(value: bool) -> str:
        return "yes" if value else "no"

    for scenario in card.SCENARIOS:
        screen = screens[scenario.letter]
        view = screen["view"]
        derived = (
            yes_no(view["range"]["assessed"]),
            yes_no(view["accepted_claim"]),
            yes_no(view["directional_permission"]),
            yes_no(screen["rows"]["Storage"] == SAVED),
            yes_no(view["gates"]["risk_gate_active"]),
        )
        assert card.answers(scenario) == derived, scenario.letter


def test_question_4_tests_the_saved_or_unsaved_state_from_what_the_screen_shows(
    screens: dict[str, dict[str, object]],
) -> None:
    """Owner ruling R4: the save receipt is built and its UX acceptance is open, so question 4
    tests the plan's saved/unsaved state again, yes or no, from what the screen shows. The
    Storage row on the card is the receipt's: the backend's own receipt for the analysis, in the
    frontend's own words, put in the row as the screen puts it."""

    assert card.QUESTIONS[3] == QUESTION_4
    said = {letter: screen["rows"]["Storage"] for letter, screen in screens.items()}
    assert said == {"A": SAVED, "B": SAVED, "C": SAVED, "D": NOT_CONFIRMED, "E": SAVED, "F": SAVED}
    for letter, screen in screens.items():
        given, payload = screen["receipt"], screen["payload"]
        assert given["schema_version"] == save_receipt.SCHEMA_VERSION == "save_receipt.v1"
        assert given["run_id"] == payload["run_id"], "each analysis is asked for its own receipt"
        state = save_receipt.FAILED if letter == "D" else save_receipt.SAVED
        assert given["state"] == state, letter
        assert sorted(given) == ["checked_at_utc", "run_id", "schema_version", "state"]
        assert given == card.receipt(screen["scenario"]), "the backend's own builder made it"
        # Storage answered when each analysis was requested: the receipt, not that, is shown.
        assert payload["debug"]["persistence_status"] == "OK", letter
        assert AT_REQUEST_TIME not in screen["texts"], letter
    # The words are app.js's own for the state, and the answer follows from them alone.
    source = card.APP_JS.read_text(encoding="utf-8")
    texts = card._extract(source, "SAVE_RECEIPT_TEXT")
    assert f'SAVED: "{SAVED}",' in texts
    first, second = NOT_CONFIRMED[:86], NOT_CONFIRMED[86:]
    assert f'"{first}" +\n    "{second}",' in texts
    assert "saved" in SAVED.lower() and "not confirmed" in NOT_CONFIRMED.lower()
    text = card.card_markdown()
    assert f"4. {QUESTION_4}\n" in text
    for forecast in ("will NOT be kept", "will not be kept", "will not appear", "not being"):
        assert forecast not in text, forecast
    note = " ".join(text[text.index("- Question 4 reads the Storage row.") :].split())
    assert "On this card that row is the save receipt of the analysis" in note
    assert "Analyses A, B, C, E and F show a save the backend acknowledged" in note
    assert "Analysis D shows a save the backend could not confirm" in note
    assert "its UX acceptance is open until this check is run" in note
    # A receipt this screen cannot show leaves the row as it was at request time.
    payload, _ = card.build(card.SCENARIOS[0])
    for bad in (None, {}, {**card.receipt(card.SCENARIOS[0]), "run_id": "another-run"}):
        (drawn,) = card.render([(payload, bad)])
        (rows,) = [block["rows"] for block in drawn["blocks"] if block["kind"] == "rows"]
        assert dict(rows)["Storage"] == AT_REQUEST_TIME, bad


def test_each_analysis_is_the_decision_view_the_real_detail_panel_renders(
    screens: dict[str, dict[str, object]],
) -> None:
    """The card cannot drift from the screen: the whole of app.js renders each analysis's detail
    panel on the DOM stand-in, and the Decision view section it shows is the card's block, line
    for line. Only the Storage row differs: no backend answers the stand-in, so the panel keeps
    storage's status at request time, where the card shows the receipt."""

    payloads = {letter: screen["payload"] for letter, screen in screens.items()}
    script = "\n".join(
        [
            harness._DOM_STAND_IN,
            card.APP_JS.read_text(encoding="utf-8"),
            f"const payloads = {json.dumps(payloads)};",
            """
(async () => {
  const out = {};
  for (const [letter, payload] of Object.entries(payloads)) {
    renderStructuredDetail(payload, {});
    for (let tick = 0; tick < 5; tick += 1) await new Promise((done) => setTimeout(done, 0));
    out[letter] = visibleTexts(detailPanel);
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
    panels = json.loads(done.stdout)
    assert sorted(panels) == sorted(screens) == list("ABCDEF")
    for letter, screen in screens.items():
        panel = harness._between(panels[letter], "Decision view", "Model Quality")
        on_card = list(screen["texts"])
        at = on_card.index("Storage") + 1
        assert panel[at] == AT_REQUEST_TIME and on_card[at] in (SAVED, NOT_CONFIRMED), letter
        on_card[at] = panel[at]
        assert on_card == panel, letter
        # Every line of the block is on the committed card, in this order.
        text = card.CARD.read_text(encoding="utf-8")
        block = text.split(f"## Analysis {letter}\n")[1].split("\n## ")[0]
        position = -1
        for line in screen["texts"][1:]:
            position = block.index(line, position + 1)


def test_the_gates_on_the_card_are_the_real_gates_not_typed_by_hand(
    screens: dict[str, dict[str, object]],
) -> None:
    """CLAUDE_EXPERT_CHECK finding F9: the card's gate dispositions were typed by hand. Each
    analysis's gate result is now what gates/composite.py returns for its inputs, and its
    disposition what the product derives from that."""

    expected = {
        "A": ("NO_TRADE", ["SKILL_NOT_DEMONSTRATED"]),
        "B": ("ABORT", ["PROVIDER_DEGRADED", "SKILL_NOT_DEMONSTRATED"]),
        "C": ("CONSTRUCTIVE_CAUTIOUS", []),
        "D": ("NO_TRADE", ["SKILL_NOT_DEMONSTRATED"]),
        "E": ("NO_TRADE", ["SKILL_NOT_DEMONSTRATED"]),
        "F": ("NO_TRADE", ["TAIL_RISK_BREACH", "SKILL_NOT_DEMONSTRATED"]),
    }
    for letter, (disposition, blocks) in expected.items():
        screen = screens[letter]
        gates = screen["view"]["gates"]
        assert [entry["block"] for entry in gates["blocks"]] == blocks, letter
        assert screen["payload"]["frontend_display"]["disposition"] == disposition, letter
        label = [name for name in screen["rows"] if name.startswith("Gate disposition")]
        assert [screen["rows"][name] for name in label] == [disposition], letter
        assert gates["blocked"] is bool(blocks), letter
    assert not hasattr(card.SCENARIOS[0], "disposition"), "no scenario carries one to type"


def test_the_registries_stay_empty() -> None:
    card.card_markdown()
    assert decision_view.ACCEPTED_FORECAST_CLAIMS == frozenset()
    assert decision_view.ACCEPTED_DIRECTIONAL_PERMISSIONS == frozenset()


def test_the_committed_card_is_current_and_says_what_it_is() -> None:
    text = card.card_markdown()
    assert card.CARD.read_text(encoding="utf-8") == text, (
        "run scripts/ux_comprehension/card.py --write"
    )
    assert "**Status: PREPARED, NOT RUN.**" in text
    assert "Analyses C, E are **SYNTHETIC**" in text
    assert "Some analyses below are **SYNTHETIC**" in text
    assert text.index("**SYNTHETIC**") < text.index("## Analysis A"), "said before any analysis"
    assert text.index("## Answer key") > text.index("## Analysis E"), "the key comes last"
    # The plan's list maps one-to-one onto A to E, so it is quoted only after the key.
    assert text.index("owner-task scenarios distinguish") > text.index("## Answer key")


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


def test_the_card_says_it_is_the_view_alone_and_names_what_the_screen_adds() -> None:
    """CLAUDE_EXPERT_CHECK 2026-10-10: the card is the decision view, and says what the screens
    show beside it. Each thing it names around the view is rendered by app.js's timeframe card
    when a view is present (in its view branch, or outside both branches), and each section it
    names under the view is one the detail panel renders, in that order. The sentence is shown by
    both cards and the detail panel (owner ruling CLASS-B-4=A)."""

    text = card.card_markdown()
    assert "Each analysis is the Decision view as the detail panel shows it, line for line" in text
    assert "none of the following is on this card, so\n  a PASS here says nothing about it" in text
    assert "The gates are the product's own" in text and "made up too" not in text
    source = card.APP_JS.read_text(encoding="utf-8")
    timeframe_card = card._extract(source, "horizonCard")
    view_branch, rest = _view_branch_and_the_rest(timeframe_card)
    assert "decisionViewRows(payload, view)" in view_branch
    assert len(card.OUTSIDE_THE_VIEW) == 5
    for name, literal, in_view_branch in card.OUTSIDE_THE_VIEW:
        assert f"    - {name}\n" in text, name
        where = view_branch if in_view_branch else rest
        assert literal in where, f"{name}: horizonCard no longer shows {literal} with a view"
    # The action row (Immediate action, Plan, Chase) is retired from the screen, so not named.
    assert "renderPermissionRow" not in source and "Immediate action" not in text
    # The sections under the view: the detail panel's own, in the panel's own order.
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
    checks = card._extract(source, "renderDecisionSynthesis")
    assert 'section("Decision", [' in checks and "renderActionabilityStack(" in checks
    # The sentence (view.detail) is rendered by both cards and by the detail panel.
    detail_panel = card._extract(source, "renderDecisionViewSection")
    assert "view.detail" in detail_panel and 'section("Decision view", [' in detail_panel
    assert "renderDecisionViewSection(payload, view)" in panel
    assert "view.detail" in view_branch
    assert "view.detail" in card._extract(source, "overviewCard")
    assert "screens show the same headline, sentence, gate summary, framing\n  and rows" in text
    # The two screens the card names are the product's own tab names.
    index_html = (card.ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    for screen in ("Single Crypto Analysis", "Batch Crypto Analysis"):
        assert screen in text and f">{screen}</button>" in index_html, screen


def test_analysis_b_is_marked_synthetic() -> None:
    text = card.card_markdown()
    assert "Analysis B is **SYNTHETIC** too, for a different reason." in text
    assert "the product shows an error message and no analysis" in text
    flags = {scenario.letter: scenario.synthetic for scenario in card.SCENARIOS}
    assert flags == {"A": False, "B": True, "C": True, "D": False, "E": True, "F": False}


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


def test_the_card_shows_the_owners_ruling_on_accepted_states(
    screens: dict[str, dict[str, object]],
) -> None:
    """Owner ruling 2026-10-06, as the owner will read it: accepted evidence shows its accepted
    state, and the accepted directional permission (C) is shown without "not a market call"
    while staying explicitly non-advisory; the other analyses read as before."""

    permission = "Gate disposition (accepted directional permission; not financial advice)"
    assert permission in screens["C"]["rows"]
    assert not any("not a market call" in label for label in screens["C"]["rows"])
    for letter in ("A", "B", "D", "E"):
        assert "Gate disposition (not a market call)" in screens[letter]["rows"], letter
    for letter in ("C", "E"):
        assert screens[letter]["rows"]["Evidence level"] == screens[letter]["headline"], letter
    for letter in ("A", "B", "D"):
        assert screens[letter]["rows"]["Evidence level"] == card.MODEL_READINESS_COPY, letter


def test_each_synthetic_analysis_reads_as_coherent_evidence(
    screens: dict[str, dict[str, object]],
) -> None:
    """Review 1 of the ruling: an accepted forecast (E) shows measured outcomes without
    demonstrated directional skill; a directional permission (C) shows demonstrated skill."""

    assert screens["E"]["rows"]["Evidence"] == (
        "NO_DEMONSTRATED_SKILL · 400 resolved outcomes · MEASURED"
    )
    assert screens["C"]["rows"]["Evidence"] == (
        "SKILL_DEMONSTRATED · 400 resolved outcomes · MEASURED"
    )
    for letter in ("A", "B", "D"):
        assert screens[letter]["rows"]["Evidence"].startswith("INSUFFICIENT_EVIDENCE · 0 "), letter


def test_the_card_shows_the_views_gate_lines_and_asks_about_risk(
    screens: dict[str, dict[str, object]],
) -> None:
    """Owner rulings AD1=A and D3: the view is the one gate authority, so the card prints its gate
    lines as app.js shows them, and a fifth question asks whether a risk gate is reported."""

    text = card.card_markdown()
    assert len(card.QUESTIONS) == 5 and "risk gate" in card.QUESTIONS[4]
    answers = {scenario.letter: card.answers(scenario)[4] for scenario in card.SCENARIOS}
    assert answers == {"A": "no", "B": "no", "C": "no", "D": "no", "E": "no", "F": "yes"}
    blocks = {
        letter: text.split(f"## Analysis {letter}\n")[1].split("| Row |")[0] for letter in "ABCDEF"
    }
    # Each active gate is listed under the framing, with its detail sentence.
    for letter in "ABCDEF":
        for gate in screens[letter]["view"]["gates"]["blocks"]:
            assert f"\n- {gate['headline']}: {gate['detail']}\n" in blocks[letter], letter
    for letter in "ABCDEF":
        gates = screens[letter]["view"]["gates"]
        # The summary, and directly under it the framing: both the backend's, in every state.
        assert f"\n{gates['summary']}\n\n{gates['framing']}\n" in blocks[letter], letter
    assert "A risk gate is active: Extreme-move risk is too high." in blocks["F"]
    assert "The risk gate (Extreme-move risk is too high) is a finding" in blocks["F"]
    assert "reason to act or to avoid acting" not in blocks["F"]
    for letter in "AD":
        assert "No risk gate is active." in blocks[letter]
        assert "not a reason to act or to avoid acting" in blocks[letter]
    assert "risk gate is active" not in blocks["C"]
