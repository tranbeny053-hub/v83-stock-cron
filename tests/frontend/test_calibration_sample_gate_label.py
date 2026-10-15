"""The calibration card names its sample gate "Sample gate", not "Reliability status".

The Model Quality section's live calibration diagnostics (GET /v1/calibration) show one card per
timeframe (renderCalibrationTimeframe). One of its rows read "Reliability status" and showed the
item's reliability_status. The endpoint's mapper, the only constructor of a calibration item, sets
that to the timeframe's sample gate (api/calibration_endpoint.py _map_timeframe_item:
sample_gate=gate, reliability_status=gate). So the row showed the card's own sample gate, which
its badge already shows, under the label of the "Current status" card's "Reliability status" row,
which shows the analysis's fixed baseline: a different value. The card's row now reads "Sample
gate", and its value is unchanged. The "Current status" card keeps its "Reliability status" row.

For 0, 99, 100, 299, 300 and 500 valid outcomes (every gate, at its boundaries), each item is the
calibration service's own report, mapped by the endpoint's own mapper (test_model_quality_copy.py).
The card and the "Current status" card are cut out of app.js. The whole section runs from the
whole of app.js, with one such item per timeframe as the /v1/calibration answer, on the DOM
stand-in of test_accepted_state_rendering.py. Node reads each script on stdin (conftest.py).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
import test_accepted_state_rendering as harness
import test_model_quality_copy as quality_copy

from crypto_probability_engine.api import calibration_endpoint
from crypto_probability_engine.api.schemas import CalibrationResponse
from crypto_probability_engine.calibration.service import sample_gate_for

CARD_ROW = "Sample gate"
SUMMARY_ROW = "Reliability status"
# Valid outcomes -> the sample gate the calibration service gives them, and the badge's label.
GATES = {
    0: ("NO_SAMPLES", "No samples"),
    99: ("INSUFFICIENT_SAMPLE", "Insufficient sample"),
    100: ("WARMING_UP", "Warming up"),
    299: ("WARMING_UP", "Warming up"),
    300: ("PRELIMINARY_MEASURED", "Preliminary measured"),
    500: ("MEASURED", "Measured"),
}
# The whole section's /v1/calibration answer: one card per timeframe, one count each.
TIMEFRAMES = dict(zip(calibration_endpoint.SUPPORTED_TIMEFRAMES, GATES, strict=True))
# A reopened run's "Current status" card has no summary: F-3's fallback, kept by the owner.
REOPENED_STATUS = "Not measured yet"

# A card as a user reads it: its texts, its badge, and its rows (label, value) in order.
_READ = r"""
const cardTexts = (node) => visibleTexts(fakeElement("div", "", [node]));
const cardRows = (node) =>
  node.querySelectorAll("dl").flatMap((dl) => {
    const pairs = [];
    for (let at = 0; at < dl.children.length; at += 2) {
      pairs.push([dl.children[at].textContent, dl.children[at + 1].textContent]);
    }
    return pairs;
  });
const readCard = (node) => ({
  texts: cardTexts(node),
  badge: node.querySelector(".calibration-gate-badge")?.textContent ?? null,
  rows: cardRows(node),
});
"""

_CARDS = r"""
const out = { cards: {}, summaries: {} };
for (const [count, item] of Object.entries(items)) {
  out.cards[count] = readCard(renderCalibrationTimeframe(item));
}
for (const [name, [quality, probability, accepted]] of Object.entries(summaries)) {
  out.summaries[name] = readCard(renderModelQuality(quality, probability, accepted));
}
process.stdout.write(JSON.stringify(out), () => process.exit(0));
"""

_SECTION = r"""
(async () => {
  const out = {};
  for (const [name, [synthesis, accepted]] of Object.entries(sections)) {
    // As on a first visit: the diagnostics answer for this section alone.
    calibrationAnswer = calibration;
    calibrationDiagnosticsCache = null;
    calibrationDiagnosticsCachedAt = 0;
    const node = renderModelQualitySection(synthesis, accepted);
    for (let tick = 0; tick < 5; tick += 1) await new Promise((done) => setTimeout(done, 0));
    out[name] = {
      texts: cardTexts(node),
      summary: readCard(node.querySelector(".decision-model-quality")),
      cards: node.querySelectorAll(".calibration-timeframe-card").map(readCard),
    };
  }
  process.stdout.write(JSON.stringify(out), () => process.exit(0));
})();
"""


def _labels(card: dict[str, Any]) -> list[str]:
    return [label for label, _value in card["rows"]]


def _row(card: dict[str, Any], label: str) -> str:
    (value,) = [value for row_label, value in card["rows"] if row_label == label]
    return value


@pytest.fixture(scope="module")
def analysis() -> dict:
    """Today's live analysis: its "Current status" card states the analysis's fixed baseline."""

    return quality_copy._analysis("1H")


@pytest.fixture(scope="module")
def cut(analysis: dict) -> dict[str, Any]:
    """The calibration card for each count, and the "Current status" card of a live analysis and
    of a reopened run (no synthesis), as the functions cut out of app.js draw them."""

    source = (harness.ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    synthesis = analysis["decision_synthesis"]
    values = {
        "items": {str(count): quality_copy._item("1H", count) for count in GATES},
        "summaries": {
            "live": [
                synthesis["model_quality_summary"],
                synthesis["probability_interpretation"],
                None,
            ],
            "reopened": [{}, {}, None],
        },
    }
    return quality_copy._node(
        "\n".join(
            [
                harness._DOM_STAND_IN,
                *(quality_copy._extract_constant(source, name) for name in quality_copy.CONSTANTS),
                *(quality_copy._extract_function(source, name) for name in quality_copy.FUNCTIONS),
                *(f"const {name} = {json.dumps(value)};" for name, value in values.items()),
                _READ,
                _CARDS,
            ]
        )
    )


@pytest.fixture(scope="module")
def sections(analysis: dict) -> dict[str, Any]:
    """The whole Model Quality section, live and reopened, as the whole of app.js renders it with
    a /v1/calibration answer of one card per timeframe."""

    calibration = CalibrationResponse(
        status="OK",
        repository="FIXTURE",
        generated_at="2026-10-15T00:00:00Z",
        timeframes=[
            quality_copy._item(timeframe, count) for timeframe, count in TIMEFRAMES.items()
        ],
    ).model_dump(mode="json")
    inputs = {"live": [analysis["decision_synthesis"], None], "reopened": [{}, None]}
    return quality_copy._node(
        "\n".join(
            [
                harness._DOM_STAND_IN,
                (harness.ROOT / "frontend" / "app.js").read_text(encoding="utf-8"),
                f"const sections = {json.dumps(inputs)};",
                f"const calibration = {json.dumps(calibration)};",
                _READ,
                _SECTION,
            ]
        )
    )


@pytest.mark.parametrize("count", list(GATES))
def test_an_items_reliability_status_is_its_sample_gate(count: int) -> None:
    """The endpoint's item for `count` valid outcomes: its reliability_status is its sample gate,
    the gate the calibration service gives that count."""

    gate, _label = GATES[count]
    item = quality_copy._item("1H", count)
    assert sample_gate_for(count) == gate
    assert item["valid_count"] == count and item["sample_gate"] == gate
    assert item["reliability_status"] == item["sample_gate"]


@pytest.mark.parametrize("count", list(GATES))
def test_the_card_names_its_sample_gate(cut: dict[str, Any], count: int) -> None:
    """The card's "Sample gate" row shows its badge's label for the card's gate, where the
    "Reliability status" row was (after the sample count), and the card has no "Reliability
    status" row."""

    _gate, label = GATES[count]
    card = cut["cards"][str(count)]
    assert card["texts"][:2] == ["1H", label], card["texts"]
    assert card["badge"] == label
    assert _row(card, CARD_ROW) == card["badge"]
    assert _labels(card)[:2] == ["Resolved sample count", CARD_ROW], _labels(card)
    assert _row(card, "Resolved sample count") == str(count)
    assert SUMMARY_ROW not in _labels(card) and SUMMARY_ROW not in card["texts"]


@pytest.mark.parametrize("shape", ["live", "reopened"])
def test_the_current_status_card_keeps_its_reliability_status_row(
    cut: dict[str, Any], analysis: dict, shape: str
) -> None:
    """The "Current status" card's row is unchanged: "Reliability status", after "Calibration
    status", with the analysis's own status (or F-3's fallback on a reopened run)."""

    summary = cut["summaries"][shape]
    quality = analysis["decision_synthesis"]["model_quality_summary"]
    expected = quality["reliability_status"] if shape == "live" else REOPENED_STATUS
    assert summary["texts"][0] == "Current status"
    assert _labels(summary)[:2] == ["Calibration status", SUMMARY_ROW], _labels(summary)
    assert _row(summary, SUMMARY_ROW) == expected


@pytest.mark.parametrize("shape", ["live", "reopened"])
def test_the_whole_section_shows_one_reliability_status_and_a_sample_gate_per_card(
    sections: dict[str, Any], shape: str
) -> None:
    """The whole section, live and reopened: "Reliability status" is the "Current status" card's
    row alone, and each timeframe's card has one "Sample gate" row, its badge's label."""

    rendered = sections[shape]
    assert rendered["texts"][:2] == ["Model Quality", "Current status"], rendered["texts"]
    assert rendered["texts"].count(SUMMARY_ROW) == 1
    assert _labels(rendered["summary"]).count(SUMMARY_ROW) == 1
    assert rendered["texts"].count(CARD_ROW) == len(TIMEFRAMES)
    cards = rendered["cards"]
    assert [card["texts"][0] for card in cards] == list(TIMEFRAMES)
    for card, count in zip(cards, TIMEFRAMES.values(), strict=True):
        assert card["badge"] == GATES[count][1], card["texts"]
        assert _row(card, CARD_ROW) == card["badge"]
        assert SUMMARY_ROW not in _labels(card)
