"""The owner's UX comprehension check (plan §23 "UX"; scripts/ux_comprehension/card.py).

Plan §23: UX is PASS only when predefined owner-task scenarios distinguish invalid data, an
unvalidated model, an accepted forecast, a directional permission and saved/unsaved state. These
tests prove that the generated scenarios do so on the real backend builder and the real
frontend, that the answer key follows from each built view (not from the scenario's own flags
alone), that the acceptance registries are left empty, and that the committed card is current.
"""

from __future__ import annotations

from itertools import combinations

import pytest

from crypto_probability_engine.adapters import provider_selection
from crypto_probability_engine.adapters.symbol_universe import ProviderSymbolUniverse
from crypto_probability_engine.api import analysis_service
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

STORAGE_KEPT = "Storage available"
# The Storage row's warning (frontend/app.js persistenceStatusText). It is storage's status when
# the analysis was requested, so it warns and never forecasts: a save receipt can say otherwise.
MAY_NOT_BE_KEPT = "may not be kept in Recent Analysis history"
QUESTION_4 = "Does the screen warn that this analysis may NOT be kept in Recent Analysis history?"


@pytest.fixture(scope="module")
def screens() -> dict[str, dict[str, object]]:
    built = [card.build(scenario) for scenario in card.SCENARIOS]
    rendered = card.render(built)
    return {
        scenario.letter: {"view": view, "rows": dict(rows), "headline": view["headline"]}
        for scenario, (_, view), rows in zip(card.SCENARIOS, built, rendered, strict=True)
    }


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
    assert screens["A"]["rows"]["Storage"] == STORAGE_KEPT
    assert screens["D"]["rows"]["Storage"] == (
        f"Storage unavailable when requested — this analysis {MAY_NOT_BE_KEPT}"
    )
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
            yes_no(MAY_NOT_BE_KEPT in screen["rows"]["Storage"]),
            yes_no(view["gates"]["risk_gate_active"]),
        )
        assert card.answers(scenario) == derived, scenario.letter


def test_question_4_asks_what_the_storage_row_can_truthfully_say(
    screens: dict[str, dict[str, object]],
) -> None:
    """The Storage row is storage's status when the analysis was requested. It cannot say that an
    analysis will not be kept: the save receipt can say "Saved…" afterwards. So question 4 asks
    whether the screen WARNS, in the row's own words, and the card's note says what the row is."""

    assert card.QUESTIONS[3] == QUESTION_4
    assert MAY_NOT_BE_KEPT in QUESTION_4.replace("may NOT", "may not")
    # Answer 4, read off each analysis's rendered Storage row and nothing else: only D warns.
    warned = {
        letter: MAY_NOT_BE_KEPT in screen["rows"]["Storage"] for letter, screen in screens.items()
    }
    assert warned == {"A": False, "B": False, "C": False, "D": True, "E": False, "F": False}
    text = card.card_markdown()
    assert f"4. {QUESTION_4}\n" in text
    for forecast in ("will NOT be kept", "will not be kept", "will not appear", "not being"):
        assert forecast not in text, forecast
    for letter, screen in screens.items():
        assert f"| Storage | {screen['rows']['Storage']} |" in text, letter
    note = " ".join(text[text.index("- Question 4 reads the Storage row.") :].split())
    assert (
        "On this card that row is storage's status when the analysis was requested: "
        '"Storage available", or a warning that the analysis may not be kept.'
    ) in note
    assert "It is read before the analysis is saved." in note
    assert "the screen asks the backend for that analysis's save receipt" in note


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
    """CLAUDE_EXPERT_CHECK 2026-10-10: the card is the decision view's headline, sentence and rows.
    Each thing it names around the view is rendered by app.js's timeframe card when a view is
    present (in its view branch, or outside both branches). The sentence is shown by both cards
    and the detail panel (owner ruling CLASS-B-4=A)."""

    text = card.card_markdown()
    assert "This card shows the decision view only" in text
    assert "none of the following is on this card, so a PASS\n  here says nothing about it" in text
    assert "The Gate disposition value is made up" in text
    source = card.APP_JS.read_text(encoding="utf-8")
    timeframe_card = card._extract(source, "horizonCard")
    view_branch, rest = _view_branch_and_the_rest(timeframe_card)
    assert "decisionViewRows(payload, view)" in view_branch
    assert len(card.OUTSIDE_THE_VIEW) == 6
    for name, literal, in_view_branch in card.OUTSIDE_THE_VIEW:
        assert f"    - {name}\n" in text, name
        where = view_branch if in_view_branch else rest
        assert literal in where, f"{name}: horizonCard no longer shows {literal} with a view"
    action_row = card._extract(source, "renderPermissionRow")
    for label in ("Immediate action", "Plan", "Chase"):
        assert f'["{label}",' in action_row, label
    # The sentence (view.detail) is rendered by both cards and by the detail panel.
    detail_panel = card._extract(source, "renderStructuredDetail")
    assert "view.detail" in detail_panel and detail_panel.count("section(") > 1
    assert "view.detail" in view_branch
    assert "view.detail" in card._extract(source, "overviewCard")
    assert "Batch Crypto Analysis screens and the detail\n  panel show them." in text
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
