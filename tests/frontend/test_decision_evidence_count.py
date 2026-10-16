"""The Decision view's "Evidence" row names one resolved outcome in the singular (F-7).

frontend/app.js decisionEvidenceText words the row from the view's evidence
(detail/decision_view.py): its skill verdict, its count of resolved outcomes and its reliability
status, joined by " · ". The count read "1 resolved outcomes" for a count of one. It now follows
the fold's rule (F-4, nestedValueBlock): the singular for one alone. "0 resolved outcomes" and
"N resolved outcomes" are unchanged, and so is the rest of the row: the hold's sentence (no
verdict and no count), no count part without a count (null or undefined), the order (verdict ·
count · reliability), and "Unavailable" when there is nothing to show.

The function is cut out of app.js, as the neighbouring tests do. Then one real analysis of the
human route, built as tests/detail/test_model_readiness_copy.py builds them (the fixture candles,
and the timeframe's evidence as the directional classifier gives it for one resolved outcome:
INSUFFICIENT_EVIDENCE, n 1), is rendered by the whole of app.js on the goldens' DOM stand-in
(fullscreen_goldens.render), live and read back as a saved run. Node reads each script on stdin
(conftest.py).

The committed whole-screen goldens and the UX comprehension card show the row for 0 and for 400
alone, in the plural, so none of their lines moves.
"""

from __future__ import annotations

import json
import re
from typing import Any

import fullscreen_goldens as goldens
import pytest
import test_model_quality_copy as quality_copy

from crypto_probability_engine.api import analysis_service
from crypto_probability_engine.api.schemas import AnalysisRequest
from crypto_probability_engine.calibration.skill import classify_directional_skill
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from tests.automation.conftest import fixture_selection

harness = goldens.harness

HOLD = "Directional evidence under review (the hold is active)"
UNAVAILABLE = "Unavailable"
ROW_FOR_ONE = "INSUFFICIENT_EVIDENCE · 1 resolved outcome · INSUFFICIENT_SAMPLE"
WRONG_NUMBER_FOR_ONE = "1 resolved outcomes"
# The row's count in a screen or card line: between the verdict and the reliability status.
ROW_COUNT = re.compile(r" · (\d+ resolved outcomes?) · ")
CARD = harness.ROOT / "docs" / "runbooks" / "UX_COMPREHENSION_CHECK.md"


def _evidence(verdict: str | None, count: int | None, *, hold: bool = False) -> dict[str, Any]:
    """The view's evidence as decision_view.py builds it (the fields the row reads), with the
    analysis's fixed reliability baseline."""

    return {
        "skill_verdict": verdict,
        "resolved_outcomes": count,
        "reliability_status": "INSUFFICIENT_SAMPLE",
        "directional_evidence_hold": hold,
    }


# A count -> its evidence and the row. One is singular; none, two and the larger counts (eleven
# and twenty-one end in one) are plural.
COUNTS: dict[int, tuple[dict[str, Any], str]] = {
    0: (
        _evidence("INSUFFICIENT_EVIDENCE", 0),
        "INSUFFICIENT_EVIDENCE · 0 resolved outcomes · INSUFFICIENT_SAMPLE",
    ),
    1: (_evidence("INSUFFICIENT_EVIDENCE", 1), ROW_FOR_ONE),
    2: (
        _evidence("INSUFFICIENT_EVIDENCE", 2),
        "INSUFFICIENT_EVIDENCE · 2 resolved outcomes · INSUFFICIENT_SAMPLE",
    ),
    11: (
        _evidence("INSUFFICIENT_EVIDENCE", 11),
        "INSUFFICIENT_EVIDENCE · 11 resolved outcomes · INSUFFICIENT_SAMPLE",
    ),
    21: (
        _evidence("INSUFFICIENT_EVIDENCE", 21),
        "INSUFFICIENT_EVIDENCE · 21 resolved outcomes · INSUFFICIENT_SAMPLE",
    ),
    400: (
        _evidence("NO_DEMONSTRATED_SKILL", 400),
        "NO_DEMONSTRATED_SKILL · 400 resolved outcomes · INSUFFICIENT_SAMPLE",
    ),
}
# Other evidence -> the row, as JSON carries it.
OTHERS: dict[str, tuple[dict[str, Any], str]] = {
    # A count alone: the singular and the plural without a verdict or a status around them.
    "one_alone": ({"resolved_outcomes": 1}, "1 resolved outcome"),
    "none_alone": ({"resolved_outcomes": 0}, "0 resolved outcomes"),
    # No count: the row has no count part.
    "null_count": (
        _evidence("INSUFFICIENT_EVIDENCE", None),
        "INSUFFICIENT_EVIDENCE · INSUFFICIENT_SAMPLE",
    ),
    "absent_count": (
        {"skill_verdict": "INSUFFICIENT_EVIDENCE", "reliability_status": "INSUFFICIENT_SAMPLE"},
        "INSUFFICIENT_EVIDENCE · INSUFFICIENT_SAMPLE",
    ),
    # The hold: as the view gives it (no verdict, no count), and with a count beside it.
    "held": (_evidence(None, None, hold=True), HOLD),
    "held_with_one": (_evidence("INSUFFICIENT_EVIDENCE", 1, hold=True), HOLD),
    "held_with_154": (_evidence("SKILL_DEMONSTRATED", 154, hold=True), HOLD),
    # Nothing to show.
    "empty": ({}, UNAVAILABLE),
    "nothing_known": ({**_evidence(None, None), "reliability_status": None}, UNAVAILABLE),
}
# What JSON cannot carry -> the row: a count that is undefined, and a view with no evidence.
UNDEFINED = {
    "undefined_count": "INSUFFICIENT_EVIDENCE · INSUFFICIENT_SAMPLE",
    "no_evidence": UNAVAILABLE,
}

_ROWS = r"""
const out = {};
for (const [name, evidence] of Object.entries(cases)) {
  out[name] = decisionEvidenceText(evidence);
}
out.undefined_count = decisionEvidenceText({ ...cases.null_count, resolved_outcomes: undefined });
out.no_evidence = decisionEvidenceText(undefined);
process.stdout.write(JSON.stringify(out), () => process.exit(0));
"""


@pytest.fixture(scope="module")
def rows() -> dict[str, str]:
    """The row for every case, as decisionEvidenceText cut out of app.js words it."""

    source = (harness.ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    cases = {
        **{f"count_{count}": evidence for count, (evidence, _row) in COUNTS.items()},
        **{name: evidence for name, (evidence, _row) in OTHERS.items()},
    }
    return quality_copy._node(
        "\n".join(
            [
                quality_copy._extract_function(source, "decisionEvidenceText"),
                f"const cases = {json.dumps(cases)};",
                _ROWS,
            ]
        )
    )


@pytest.mark.parametrize("count", list(COUNTS))
def test_the_count_is_singular_for_one_alone(rows: dict[str, str], count: int) -> None:
    """0, 1, 2, 11, 21 and 400: "1 resolved outcome", and "N resolved outcomes" for every other
    count, between the verdict and the reliability status."""

    _evidence_given, row = COUNTS[count]
    assert rows[f"count_{count}"] == row


def test_the_cases_hold_the_boundary() -> None:
    """The singular is for one alone: none, two and the larger counts are plural."""

    singular = {count for count, (_evidence_given, row) in COUNTS.items() if " outcome · " in row}
    assert singular == {1}
    assert {0, 2, 11, 21, 400} <= set(COUNTS)


@pytest.mark.parametrize("name", ["one_alone", "none_alone"])
def test_a_count_alone_is_in_the_same_words(rows: dict[str, str], name: str) -> None:
    assert rows[name] == OTHERS[name][1]


@pytest.mark.parametrize("name", ["null_count", "absent_count", "undefined_count"])
def test_without_a_count_the_row_has_no_count_part(rows: dict[str, str], name: str) -> None:
    """A count that is null, absent or undefined: the verdict and the status, nothing between."""

    expected = UNDEFINED.get(name) or OTHERS[name][1]
    assert rows[name] == expected
    assert "resolved" not in rows[name] and "null" not in rows[name]
    assert "undefined" not in rows[name]


@pytest.mark.parametrize("name", ["held", "held_with_one", "held_with_154"])
def test_the_hold_gives_its_sentence_and_no_count(rows: dict[str, str], name: str) -> None:
    """Under the hold the row is the hold's sentence alone: no verdict and no count, even when
    one is given."""

    assert rows[name] == HOLD
    assert "resolved" not in rows[name] and "·" not in rows[name]


@pytest.mark.parametrize("name", ["empty", "nothing_known", "no_evidence"])
def test_with_nothing_to_show_the_row_reads_unavailable(rows: dict[str, str], name: str) -> None:
    assert rows[name] == UNAVAILABLE


@pytest.fixture(scope="module")
def one_outcome() -> tuple[dict, dict[str, list[str]]]:
    """One analysis of the real service (human route) on the fixture candles, with the evidence
    the classifier gives for one resolved outcome, and its screens as the real app.js renders them:
    live (single, batch, detail) and read back as a saved run (history)."""

    evidence = classify_directional_skill(1, 1)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(analysis_service, "select_market_data", fixture_selection())
        patch.setattr(analysis_service, "get_cached_skill_evidence", lambda _tf: dict(evidence))
        payload = analysis_service.analyze_request(
            AnalysisRequest(symbol="BTC/USDT", timeframe="1H"),
            settings=Settings(data_mode="fixture"),
            run_store=InMemoryRunStore(limit=10),
        )
    analysis_service._pop_prediction_persistence(payload)  # noqa: SLF001 - clean up
    rendered = goldens.render({"one": payload}, {"one": goldens._reopened(payload)})
    return payload, rendered["screens"]["one"]


def test_the_analysis_has_one_resolved_outcome(one_outcome: tuple[dict, dict]) -> None:
    """The analysis is the one named: INSUFFICIENT_EVIDENCE on one resolved outcome, under the
    evidence gate, with no hold; its view carries the count."""

    payload, _screens = one_outcome
    assert payload["skill_evidence"]["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert payload["skill_evidence"]["n"] == 1
    assert "SKILL_NOT_DEMONSTRATED" in payload["gate_result"]["hard_blocks"]
    assert payload["gate_result"].get("directional_evidence_hold") is None
    evidence = payload["decision_view"]["evidence"]
    assert evidence["skill_verdict"] == "INSUFFICIENT_EVIDENCE"
    assert evidence["resolved_outcomes"] == 1
    assert evidence["reliability_status"] == "INSUFFICIENT_SAMPLE"
    assert evidence["directional_evidence_hold"] is False


@pytest.mark.parametrize("surface", ["single", "batch", "detail"])
def test_the_decision_views_evidence_row_reads_one_resolved_outcome(
    one_outcome: tuple[dict, dict], surface: str
) -> None:
    """The Decision view leads each live surface, and its "Evidence" row reads "1 resolved
    outcome"."""

    _payload, screens = one_outcome
    screen = screens[surface]
    assert screen.count("Evidence") == 1, screen
    assert screen[screen.index("Evidence") + 1] == ROW_FOR_ONE


def test_no_screen_line_reads_one_resolved_outcomes(one_outcome: tuple[dict, dict]) -> None:
    """No line of any surface, live or read back, says "1 resolved outcomes"."""

    _payload, screens = one_outcome
    assert set(screens) == {"single", "batch", "detail", "history"}
    for surface, screen in screens.items():
        assert screen, surface
        assert not [line for line in screen if WRONG_NUMBER_FOR_ONE in line], surface


def test_no_golden_and_no_card_line_holds_the_row_in_the_wrong_number() -> None:
    """The committed whole-screen goldens and the UX comprehension card show the row for 0 and
    for 400 alone, in the plural, which stays: none of their lines moves. None reads "1 resolved
    outcomes", or "N resolved outcome"."""

    golden_lines = [
        line for content in goldens.committed().values() for line in goldens.decode(content)
    ]
    card_lines = CARD.read_text(encoding="utf-8").splitlines()
    for lines in (golden_lines, card_lines):
        counts = [match.group(1) for line in lines for match in ROW_COUNT.finditer(line)]
        assert counts and set(counts) == {"0 resolved outcomes", "400 resolved outcomes"}
        assert not [line for line in lines if WRONG_NUMBER_FOR_ONE in line]
