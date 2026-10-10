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

from crypto_probability_engine.detail import decision_view
from crypto_probability_engine.detail.decision_view import STATE_COPY
from scripts.ux_comprehension import card

STORAGE_KEPT = "Storage available"
NOT_KEPT = "will not appear in Recent Analysis history"


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
    assert "not being retained" in screens["D"]["rows"]["Storage"]
    # Every pair of analyses can be told apart from what the screen shows.
    for left, right in combinations(sorted(screens), 2):
        assert (screens[left]["headline"], screens[left]["rows"]) != (
            screens[right]["headline"],
            screens[right]["rows"],
        ), (left, right)


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
            yes_no(NOT_KEPT in screen["rows"]["Storage"]),
        )
        assert card.answers(scenario) == derived, scenario.letter


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
