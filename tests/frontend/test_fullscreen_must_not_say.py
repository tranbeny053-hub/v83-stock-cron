"""The "must not say" list, tested on whole screens (governing plan §14.1: missing evidence must
never render as a negative market signal; the class-B architecture package, root cause RC8).

The earlier checks of this class tested sentences: each named the phrases a review had already
read, and the class came back on the next surface. This one reads screens. Every line of every
committed whole-screen golden (fullscreen_goldens.py pins them to what the real app.js renders over
real analyses) is read, for every scenario in which no risk gate reports a measured finding, and a
line is refused when it:
- uses risk as a finding, or heads a block with a risk title: any line that says "risk" at all;
- gives an instruction: act, avoid, wait, observe, re-evaluate, monitor (and re-check);
- shows the forced token ELEVATED_RISK_AVOID without "(not forced by a risk gate)".

A line that says one of those words and is right to say it is on a short list, exactly as it reads,
with the reason. The list is closed: a line that leaves the screen must leave the list, and a new
line that says one of the words fails until someone reads it and decides.

Raw data printed as JSON (a "View" block of the Gates, Provider State, Quant Signals and News
sections) is data, not a sentence: it is not read here. Its field names are the backend's
(`risk_pressure`, `risk_arbiter_version`), and showing raw tokens is the owner's deferred decision.
"""

from __future__ import annotations

import re

import fullscreen_goldens as goldens
import pytest

# Scenario -> why no screen of it may read as risk. In each, no risk gate reports a measured
# finding; the first five are the evidence gate alone, which is every analysis today.
WITHOUT_A_RISK_FINDING = {
    "evidence_only": "the evidence gate alone (today's every analysis)",
    "storage_OK": "the evidence gate alone",
    "storage_UNAVAILABLE": "the evidence gate alone",
    "storage_STATELESS": "the evidence gate alone",
    goldens.SAVED_BEFORE: "the evidence gate alone, saved before the gate framing existed",
    "first_check_blocks_SYNTHETIC": "the evidence gate alone, another check shown first",
    "accepted_claim_SYNTHETIC": "the evidence gate alone, under an accepted claim",
    "unusable_order_book_and_evidence": "a gate fired by unusable data, with the evidence gate",
    "missing_order_book_and_evidence_SYNTHETIC": "a gate fired by missing data, with it",
    "missing_order_book_only_SYNTHETIC": "a gate fired by missing data, alone",
    "kill_switch_and_evidence_SYNTHETIC": "a system gate, with the evidence gate",
    "system_only_SYNTHETIC": "a system gate, alone",
    "permission_SYNTHETIC": "no gate at all",
}
# The scenarios in which a risk gate reports a measured finding: risk wording is theirs to use.
WITH_A_RISK_FINDING = ("risk_and_evidence", "wide_spread_and_evidence", "risk_only_SYNTHETIC")

RISK = re.compile(r"risk", re.IGNORECASE)
INSTRUCTION = re.compile(
    r"\b(act|acts|acting|avoid|avoids|avoiding|wait|waits|waiting|observe|observes|observing"
    r"|re-?evaluate|re-?evaluates|re-?evaluating|re-?check|monitor|monitors|monitoring)\b",
    re.IGNORECASE,
)
FORCED_TOKEN = "ELEVATED_RISK_AVOID"
FORCED_TOKEN_NOTE = "ELEVATED_RISK_AVOID (not forced by a risk gate)"

# The lines that say "risk" and are right to. Exact lines; nothing else may say it.
ALLOWED_RISK_LINES = {
    "Evidence gate: directional skill is not established for this model and timeframe. No risk "
    "gate is active.": "the gate authority's own summary: it says that no risk gate is active",
    "Tail risk": "the name of check #5 of the kept Actionability stack: a measured check",
    "Tail-risk status is OK.": "the result of that check: measured, and it passed",
    "Evidence: tail_risk_state.status, tail_risk_state.cvar_loss": (
        "the fields that check read (a raw field path; showing those is the owner's deferred call)"
    ),
    "Signal heat (not risk)": (
        "the cards' heat row label, which says it is not risk (the heat row is the owner's "
        "deferred call)"
    ),
    "risk arbiter": (
        "the backend field name heading the raw risk-arbiter values in the kept Gates section"
    ),
    "tail risk": (
        "the backend field name heading the raw tail-risk values in the kept Gates section: the "
        "tail-risk size stays where it is"
    ),
}
# The lines that say one of the instruction words and are right to: each says that something is
# NOT a reason or a forecast to act on.
ALLOWED_INSTRUCTION_LINES = {
    "No forecast-quality claim has been accepted for this model and timeframe. The percentages "
    "are uncalibrated reference context: not a forecast, not a market signal, and not a reason "
    "to act or to avoid acting.": (
        "the decision view's own sentence: it says the percentages are no reason to act or to "
        "avoid acting"
    ),
    "The gates' disposition, not a market call: a gate outcome is not a forecast to act on.": (
        "the gate authority's framing: it says a gate outcome is no forecast to act on"
    ),
}


def _is_raw_data(text: str) -> bool:
    """A "View" block: the backend's values printed as JSON."""

    return text.startswith(("{", "["))


def _screens() -> dict[str, dict[str, list[str]]]:
    """Every committed golden, decoded: scenario -> surface -> the lines a user reads."""

    screens: dict[str, dict[str, list[str]]] = {}
    for name, content in goldens.committed().items():
        scenario, surface, _ = name.rsplit(".", 2)
        screens.setdefault(scenario, {})[surface] = goldens.decode(content)
    return screens


SCREENS = _screens()
CELLS = [
    (scenario, surface)
    for scenario in WITHOUT_A_RISK_FINDING
    for surface in sorted(SCREENS.get(scenario, {}))
]


def forbidden(text: str) -> list[str]:
    """Why a line may not be on a screen without a risk finding; empty when it may."""

    if _is_raw_data(text):
        return []
    found = []
    if RISK.search(text) and text not in ALLOWED_RISK_LINES:
        found.append("says risk")
    if INSTRUCTION.search(text) and text not in ALLOWED_INSTRUCTION_LINES:
        found.append("gives an instruction")
    if FORCED_TOKEN in text and FORCED_TOKEN_NOTE not in text:
        found.append("shows the forced token alone")
    return found


def test_every_scenario_is_read_as_one_kind_or_the_other() -> None:
    assert set(WITHOUT_A_RISK_FINDING) | set(WITH_A_RISK_FINDING) == set(SCREENS)
    assert not set(WITHOUT_A_RISK_FINDING) & set(WITH_A_RISK_FINDING)
    assert set(SCREENS) == {*goldens.SCENARIOS, goldens.SAVED_BEFORE}
    # Every surface of every such scenario is read: 13 scenarios, 44 screens.
    assert len(CELLS) == sum(len(SCREENS[name]) for name in WITHOUT_A_RISK_FINDING) == 44
    for name in WITHOUT_A_RISK_FINDING:
        assert set(SCREENS[name]) >= ({"history"} if name == goldens.SAVED_BEFORE else {"single"})


@pytest.mark.parametrize(("scenario", "surface"), CELLS)
def test_no_line_of_a_screen_without_a_risk_finding_says_what_it_must_not(
    scenario: str, surface: str
) -> None:
    texts = SCREENS[scenario][surface]
    assert len(texts) > 20, "a whole screen"
    found = {text: why for text in texts if (why := forbidden(text))}
    assert found == {}, (
        f"{scenario}.{surface} ({WITHOUT_A_RISK_FINDING[scenario]}) says what it must not:\n"
        + "\n".join(f"  {' and '.join(why)}: {text!r}" for text, why in found.items())
        + "\nIf a line is right to say it, add the exact line to the list here, with the reason."
    )


def test_the_allow_lists_are_short_exact_and_in_use() -> None:
    """Each allowed line is on a screen exactly as it is listed, says the word it is allowed for,
    and carries its reason; an entry no screen shows any more must be removed."""

    shown = {
        text
        for name in WITHOUT_A_RISK_FINDING
        for texts in SCREENS[name].values()
        for text in texts
    }
    assert len(ALLOWED_RISK_LINES) == 7 and len(ALLOWED_INSTRUCTION_LINES) == 2
    for lines, pattern in ((ALLOWED_RISK_LINES, RISK), (ALLOWED_INSTRUCTION_LINES, INSTRUCTION)):
        for line, reason in lines.items():
            assert line in shown, f"no screen shows this any more: {line!r}"
            assert pattern.search(line), line
            assert len(reason) > 30, f"say why it is allowed: {line!r}"
    # Each instruction line that is allowed denies a reason to act: it instructs nothing.
    for line in ALLOWED_INSTRUCTION_LINES:
        assert " not a reason to act" in line or " not a forecast to act on" in line


@pytest.mark.parametrize(
    ("line", "why"),
    [
        ("Risk summary", "says risk"),
        ("Risk / Gates", "says risk"),
        ("Risk note", "says risk"),
        ("The elevated-risk disposition disables scenario planning.", "says risk"),
        ("A risk gate is active: Liquidity is not viable.", "says risk"),
        ("Re-evaluate if the existing tail-risk state normalizes.", "says risk"),
        ("No risk gate is active.", "says risk"),
        ("tail risk ", "says risk"),
        ("Observe only", "gives an instruction"),
        ("Observe only; current entry, chase, and numeric planning are disabled.", "instruction"),
        ("Re-evaluate after every active hard gate clears.", "gives an instruction"),
        ("Wait for hard blockers or degraded data conditions to clear.", "gives an instruction"),
        ("Wait for confirmation", "gives an instruction"),
        ("Monitor whether backend hard gates remain clear.", "gives an instruction"),
        ("Re-check only with fresh backend data over the stated horizon.", "gives an instruction"),
        ("Avoid this setup while a hard gate remains active.", "gives an instruction"),
        ("It is no reason to act or to avoid acting.", "gives an instruction"),
        ("Backend disposition: ELEVATED_RISK_AVOID.", "shows the forced token alone"),
        ("ELEVATED_RISK_AVOID", "shows the forced token alone"),
    ],
)
def test_the_lines_of_the_four_occurrences_are_each_refused(line: str, why: str) -> None:
    """The lines the class's occurrences were made of (the parity review's C1, C3 and C6, and the
    expert check's F1), and near misses of the allowed lines: each is refused."""

    assert any(why in reason for reason in forbidden(line)), (line, forbidden(line))


@pytest.mark.parametrize(
    "line",
    [
        "The heuristic probability leans upward, but it is context rather than an action.",
        "Actionability stack",
        "Gate action",
        "Immediate reaction",
        "Liquidity is OK; execution realism is OK.",
        "Interaction between factors",
        "sentiment only action",
        "Awaiting backend analysis.",
        '{\n  "risk_pressure": 0.004,\n  "risk_arbiter_version": "risk_arbiter_v1"\n}',
    ],
)
def test_a_line_that_only_looks_like_one_is_not_refused(line: str) -> None:
    """Words that contain a forbidden word are not it ("action" is not "act"), and raw data is
    not read."""

    assert forbidden(line) == []


def test_a_planted_line_fails_the_screen_test_on_any_screen() -> None:
    """The check is of whole screens: one forbidden line anywhere on any of them is found."""

    planted = "Observe only; re-evaluate after every active hard gate clears."
    for scenario, surface in CELLS:
        texts = SCREENS[scenario][surface]
        for position in (0, len(texts) // 2, len(texts)):
            screen = [*texts[:position], planted, *texts[position:]]
            assert [text for text in screen if forbidden(text)] == [planted], (scenario, surface)


def test_a_screen_with_a_risk_finding_names_it_and_still_instructs_nothing() -> None:
    """Where a risk gate reports a measured finding, risk wording is right; no instruction is, and
    the forced token is not on screen there either."""

    for scenario in WITH_A_RISK_FINDING:
        for surface, texts in SCREENS[scenario].items():
            assert any(text.startswith("A risk gate is active: ") for text in texts), (
                scenario,
                surface,
            )
            for text in texts:
                if _is_raw_data(text):
                    continue
                assert not INSTRUCTION.search(text), (scenario, surface, text)
                assert FORCED_TOKEN not in text, (scenario, surface, text)
