"""The Model Quality copy states no measurement status the screen contradicts (S1, S2; PROVISIONAL
wording).

The detail panel's Model Quality section holds the "Current status" card (the analysis's model
quality summary), the live calibration diagnostics (GET /v1/calibration: one card per timeframe)
and the glossary. Each diagnostics card reports the resolved sample count, the Brier score, the log
loss and the top-label hit rate from the first valid outcome on (calibration/metrics.py computes
them on any valid row; the tests below build the cards from the calibration service's own report).
- S1. When the summary lists no calibration metric (a live analysis today: its summary lists
  metrics only under MEASURED reliability; and a reopened run, which has no summary), the card
  said "Resolved-sample metrics are not surfaced in this view yet." The same section shows those
  metrics in its diagnostics, so the line denied what the section shows. It now says only what
  this summary lists, in the glossary's terms ("Measured calibration: ... after the sample gate is
  met"), and it holds under any claim.
- S2. A card at INSUFFICIENT_SAMPLE (1 to 99 valid outcomes) read "Early diagnostic — not measured
  yet." above its own sample count, Brier score, log loss and top-label hit rate. Its note now says
  why the diagnostic is early, as its neighbours do, and states no measurement status.

Two lines that state a measurement status stay, and the tests name them where they meet them:
- F-3's fallbacks ("Model quality: not measured yet.", "Not measured yet"), on a reopened run's
  card without a claim: the owner kept them;
- the backend's own copy, which the card renders as the payload carries it: the probability
  interpretation's reliability warning ("Reliability is not measured from sufficient resolved
  samples; ..."). This change is frontend copy only, and the payload is unchanged.

The real app.js runs under Node on the DOM stand-in of test_accepted_state_rendering.py: the card
and the notes cut out of it, as the neighbouring tests do, and the whole section from the whole of
app.js, with a synthetic /v1/calibration answer. Node reads each script on stdin (conftest.py).
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any

import pytest
import test_accepted_state_rendering as harness

from crypto_probability_engine.api import analysis_service, calibration_endpoint
from crypto_probability_engine.api.schemas import CalibrationResponse
from crypto_probability_engine.calibration.service import build_calibration_report
from crypto_probability_engine.detail.decision_synthesis import _model_quality_summary

S1 = (
    "This summary lists no calibration metric: measured calibration begins once the sample gate "
    "is met."
)
S1_BEFORE = "Resolved-sample metrics are not surfaced in this view yet."
S2 = "Early diagnostic — too few resolved samples to establish reliability."
S2_BEFORE = "Early diagnostic — not measured yet."
# The glossary's own definition, whose terms S1 uses.
MEASURED_CALIBRATION = (
    "A comparison between forecast probabilities and resolved outcomes after the sample gate is "
    "met."
)
# A line that states a measurement status, whatever the screen holds.
MEASUREMENT_STATUS = re.compile(r"not surfaced|not measured|not yet", re.IGNORECASE)
# F-3's fallbacks, kept by the owner: a reopened run's card without a claim.
F3_KEPT = {"Model quality: not measured yet.", "Not measured yet"}
# Every sample gate's note (and an unknown gate's). Only INSUFFICIENT_SAMPLE's changed.
NOTES = {
    "NO_SAMPLES": "No resolved samples yet.",
    "INSUFFICIENT_SAMPLE": S2,
    "WARMING_UP": "Early diagnostic — reliability not established.",
    "PRELIMINARY_MEASURED": "Preliminary diagnostic — reliability remains limited.",
    "MEASURED": "Measured calibration diagnostic — not a guarantee.",
    "UNKNOWN": "Calibration status unavailable.",
}
# The gates whose cards carry metrics: every gate from one valid outcome on.
WITH_METRICS = ("INSUFFICIENT_SAMPLE", "WARMING_UP", "PRELIMINARY_MEASURED", "MEASURED")
# Valid outcomes -> the gate the calibration service gives them: each gate's boundaries.
COUNTS = {
    0: "NO_SAMPLES",
    1: "INSUFFICIENT_SAMPLE",
    99: "INSUFFICIENT_SAMPLE",
    100: "WARMING_UP",
    299: "WARMING_UP",
    300: "PRELIMINARY_MEASURED",
    500: "MEASURED",
}
METRIC_ROWS = ("Brier score", "Log loss", "Top-label hit rate (diagnostic)")

# What the card and the notes call, cut out of app.js.
CONSTANTS = ("NOT_REPORTED_TEXT",)
FUNCTIONS = (
    "formatNumber",
    "formatValue",
    "nestedValueBlock",
    "appendDefinitionRows",
    "keyValueTable",
    "backendText",
    "textBlock",
    "hasPayloadValue",
    "renderModelQuality",
    "calibrationGateLabel",
    "calibrationGateClass",
    "calibrationGateNote",
    "formatCalibrationMetric",
    "formatCalibrationPercent",
    "formatCalibrationCount",
    "formatOutcomeDistribution",
    "renderCalibrationVersions",
    "renderCalibrationTimeframe",
)

_CARDS = r"""
const shown = (node) => visibleTexts(fakeElement("div", "", [node]));
const out = { cards: {}, notes: {}, timeframes: {} };
for (const [name, [quality, probability, accepted]] of Object.entries(cards)) {
  out.cards[name] = shown(renderModelQuality(quality, probability, accepted));
}
for (const gate of gates) {
  out.notes[gate] = calibrationGateNote(gate);
}
for (const [count, item] of Object.entries(items)) {
  out.timeframes[count] = shown(renderCalibrationTimeframe(item));
}
process.stdout.write(JSON.stringify(out), () => process.exit(0));
"""

_SECTION = r"""
(async () => {
  const out = {};
  for (const [name, [synthesis, accepted]] of Object.entries(sections)) {
    for (const [answer, diagnostics] of [["answered", calibration], ["unavailable", null]]) {
      // As on a first visit: the diagnostics answer (or fail) for this section alone.
      calibrationAnswer = diagnostics;
      calibrationDiagnosticsCache = null;
      calibrationDiagnosticsCachedAt = 0;
      const node = renderModelQualitySection(synthesis, accepted);
      for (let tick = 0; tick < 5; tick += 1) await new Promise((done) => setTimeout(done, 0));
      const cards = node.querySelectorAll(".calibration-timeframe-card");
      out[`${name}.${answer}`] = {
        texts: visibleTexts(fakeElement("div", "", [node])),
        cards: cards.map((card) => visibleTexts(card)),
      };
    }
  }
  process.stdout.write(JSON.stringify(out), () => process.exit(0));
})();
"""


def _extract_function(source: str, name: str) -> str:
    """One whole function: past its parameter list (which may hold a default ``{}``), then its
    balanced body."""

    start = source.index(f"function {name}(")
    depth, index = 0, source.index("(", start)
    while True:
        depth += {"(": 1, ")": -1}.get(source[index], 0)
        index += 1
        if depth == 0:
            break
    index = source.index("{", index)
    depth = 0
    for end in range(index, len(source)):
        depth += {"{": 1, "}": -1}.get(source[end], 0)
        if depth == 0:
            return source[start : end + 1]
    raise AssertionError(f"Could not extract {name}")


def _extract_constant(source: str, name: str) -> str:
    match = re.search(rf"^const {name} = .*;$", source, re.MULTILINE)
    assert match, f"Could not extract {name}"
    return match.group(0)


def _node(script: str) -> Any:
    assert harness.NODE is not None, "node is required to run the real app.js"
    done = subprocess.run(  # noqa: S603 - node on a script built here, read on stdin
        [harness.NODE, "-"], input=script, capture_output=True, encoding="utf-8", timeout=60
    )
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout)


class _ResolvedRows:
    """A read-only stand-in for the calibration repository: `count` resolved rows, each valid."""

    def __init__(self, count: int) -> None:
        labels = ("UP", "DOWN", "TIMEOUT")
        self.rows = [
            {
                "realized_label": labels[index % 3],
                "p_up_frac": 0.5,
                "p_down_frac": 0.3,
                "p_timeout_frac": 0.2,
                "terminal_return_frac": None,
                "model_version": "v1",
                "methodology_version": harness.METHODOLOGY,
            }
            for index in range(count)
        ]

    def fetch_resolved_prediction_outcomes_for_calibration(self, **_filters: Any) -> list[dict]:
        return [dict(row) for row in self.rows]


def _item(timeframe: str, count: int) -> dict:
    """The diagnostics card's item for `count` valid outcomes: the calibration service's own report
    (its sample gate and its metrics), mapped by the endpoint's own mapper."""

    report = build_calibration_report(_ResolvedRows(count), timeframe=timeframe)
    item = calibration_endpoint._map_timeframe_item(timeframe, report, include_buckets=False)
    return item.model_dump(mode="json")


def _analysis(timeframe: str, **claims: bool) -> dict:
    payload = harness._analysis(timeframe, **claims)
    analysis_service._pop_prediction_persistence(payload)
    return payload


@pytest.fixture(scope="module")
def analyses() -> dict[str, dict]:
    """Today's live analysis, and the same under an accepted forecast claim and an accepted
    directional permission (the governed registries patched for the build only)."""

    return {
        "today": _analysis("1H"),
        "claim": _analysis("1H", claim=True),
        "permission": _analysis("1H", permission=True),
    }


def _card_inputs(analyses: dict[str, dict]) -> dict[str, list[Any]]:
    """The "Current status" card's inputs (summary, probability interpretation, accepted view): a
    live analysis's, and a reopened run's (no synthesis: both are empty), with and without a
    claim."""

    def live(name: str) -> list[Any]:
        payload = analyses[name]
        synthesis = payload["decision_synthesis"]
        accepted = payload["decision_view"] if name != "today" else None
        return [
            synthesis["model_quality_summary"],
            synthesis["probability_interpretation"],
            accepted,
        ]

    return {
        "live": live("today"),
        "live_claim": live("claim"),
        "live_permission": live("permission"),
        "reopened": [{}, {}, None],
        "reopened_claim": [{}, {}, analyses["claim"]["decision_view"]],
    }


def _measured(analyses: dict[str, dict]) -> dict[str, list[Any]]:
    """Summaries that list a metric: the backend's own under MEASURED reliability, and today's
    with each metric alone."""

    today = analyses["today"]["decision_synthesis"]
    calibration = {
        "calibration_status": "MEASURED",
        "sample_count": 640,
        "sample_gate": "MEASURED",
        "brier_score": 0.58,
        "log_loss": 0.97,
        "top_label_hit_rate": 0.46,
    }
    cards = {
        "measured": [
            _model_quality_summary(calibration, "MEASURED"),
            today["probability_interpretation"],
            None,
        ]
    }
    for field in ("sample_count", "sample_gate", "brier_score", "log_loss", "top_label_hit_rate"):
        summary = {**today["model_quality_summary"], field: calibration[field]}
        cards[f"only_{field}"] = [summary, today["probability_interpretation"], None]
    return cards


@pytest.fixture(scope="module")
def cut(analyses: dict[str, dict]) -> dict[str, Any]:
    """The card, the notes and the diagnostics cards, as the functions cut out of app.js draw
    them."""

    source = (harness.ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    values = {
        "cards": {**_card_inputs(analyses), **_measured(analyses)},
        "gates": list(NOTES),
        "items": {str(count): _item("1H", count) for count in COUNTS},
    }
    return _node(
        "\n".join(
            [
                harness._DOM_STAND_IN,
                *(_extract_constant(source, name) for name in CONSTANTS),
                *(_extract_function(source, name) for name in FUNCTIONS),
                *(f"const {name} = {json.dumps(value)};" for name, value in values.items()),
                _CARDS,
            ]
        )
    )


def _diagnostics() -> dict:
    """A synthetic /v1/calibration answer, one card per sample gate, each with its metrics."""

    timeframes = {"15m": 40, "1H": 172, "4H": 350, "1D": 600, "1M": 0}
    response = CalibrationResponse(
        status="OK",
        repository="FIXTURE",
        generated_at="2026-10-15T00:00:00Z",
        timeframes=[_item(timeframe, count) for timeframe, count in timeframes.items()],
    )
    return response.model_dump(mode="json")


@pytest.fixture(scope="module")
def sections(analyses: dict[str, dict]) -> dict[str, Any]:
    """The whole Model Quality section, as the whole of app.js renders it: live and reopened, with
    and without a claim, with the diagnostics answering and failing."""

    claim = analyses["claim"]
    inputs = {
        "live": [analyses["today"]["decision_synthesis"], None],
        "live_claim": [claim["decision_synthesis"], claim["decision_view"]],
        "reopened": [{}, None],
        "reopened_claim": [{}, claim["decision_view"]],
    }
    calibration = _diagnostics()
    rendered = _node(
        "\n".join(
            [
                harness._DOM_STAND_IN,
                (harness.ROOT / "frontend" / "app.js").read_text(encoding="utf-8"),
                f"const sections = {json.dumps(inputs)};",
                f"const calibration = {json.dumps(calibration)};",
                _SECTION,
            ]
        )
    )
    return {"inputs": inputs, "calibration": calibration, "rendered": rendered}


def _stated_status(lines: list[str], *backend: Any) -> set[str]:
    """The lines that state a measurement status, except the backend's own copy, which the screen
    renders as the payload carries it."""

    own = set().union(*(harness._strings(value) for value in backend if value))
    return {line for line in lines if MEASUREMENT_STATUS.search(line) and line not in own}


def test_the_new_lines_state_no_measurement_status_and_hold_under_any_claim() -> None:
    for line in (S1, S2):
        assert MEASUREMENT_STATUS.search(line) is None, line
    # S1 speaks of this summary alone, and of measured calibration in the glossary's terms.
    assert S1.startswith("This summary lists no calibration metric")
    assert S1.endswith("measured calibration begins once the sample gate is met.")
    assert MEASURED_CALIBRATION.endswith("after the sample gate is met.")
    # True under any claim: no heuristic reading, and a UI text that holds whatever the state.
    assert not harness._is_heuristic_reading(S1)
    assert S1 in harness.STATE_INDEPENDENT_UI_TEXTS
    assert S1_BEFORE not in harness.STATE_INDEPENDENT_UI_TEXTS
    source = (harness.ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    for before in (S1_BEFORE, S2_BEFORE):
        assert before not in source, before
    assert source.count(f'"{S1}"') == 1 and source.count(f'"{S2}"') == 1


def test_the_analyses_are_the_states_named(analyses: dict[str, dict]) -> None:
    """Today's summary lists no metric (its reliability is not MEASURED); the other two hold an
    accepted claim."""

    summary = analyses["today"]["decision_synthesis"]["model_quality_summary"]
    assert summary["reliability_status"] != "MEASURED"
    for field in ("sample_count", "sample_gate", "brier_score", "log_loss", "top_label_hit_rate"):
        assert summary[field] is None, field
    assert analyses["today"]["decision_view"]["accepted_claim"] is False
    for name in ("claim", "permission"):
        assert analyses[name]["decision_view"]["accepted_claim"] is True, name


@pytest.mark.parametrize(
    "shape", ["live", "live_claim", "live_permission", "reopened", "reopened_claim"]
)
def test_s1_a_card_without_a_metric_says_what_its_summary_lists(
    cut: dict[str, Any], analyses: dict[str, dict], shape: str
) -> None:
    """S1, on a live analysis's card and a reopened run's, with and without a claim: the card
    carries the new sentence once, and no line of it the frontend words says "not surfaced", "not
    measured" or "not yet", except F-3's kept fallbacks on a reopened run without a claim."""

    lines = cut["cards"][shape]
    quality, probability, accepted = _card_inputs(analyses)[shape]
    assert lines[0] == "Current status", lines
    assert lines.count(S1) == 1, lines
    assert S1_BEFORE not in lines
    assert not any("not surfaced" in line.lower() for line in lines), lines
    kept = F3_KEPT if shape == "reopened" else set()
    assert _stated_status(lines, quality, probability, accepted) <= kept, lines


def test_s1_a_card_that_lists_a_metric_does_not_say_it_lists_none(cut: dict[str, Any]) -> None:
    """The sentence is shown only when it is true: a summary that lists any calibration metric
    (the backend's own under MEASURED reliability, or one metric alone) does not carry it."""

    for shape in ("measured", *(name for name in cut["cards"] if name.startswith("only_"))):
        lines = cut["cards"][shape]
        assert S1 not in lines and S1_BEFORE not in lines, shape
    measured = cut["cards"]["measured"]
    for label in ("Resolved sample count", "Sample gate", "Brier score", "Log loss"):
        assert label in measured, label
    assert "Top-label hit rate" in measured


def test_s2_no_note_of_a_gate_that_shows_metrics_states_a_measurement_status(
    cut: dict[str, Any],
) -> None:
    """S2: INSUFFICIENT_SAMPLE's note is the new one, every other gate's is as it was, and no gate
    whose card carries metrics has a note that states a measurement status. NO_SAMPLES keeps "No
    resolved samples yet."."""

    assert cut["notes"] == NOTES
    for gate in WITH_METRICS:
        assert MEASUREMENT_STATUS.search(cut["notes"][gate]) is None, gate
    assert cut["notes"]["NO_SAMPLES"] == "No resolved samples yet."


@pytest.mark.parametrize("count", list(COUNTS))
def test_s2_a_card_shows_its_metrics_under_a_note_that_does_not_deny_them(
    cut: dict[str, Any], count: int
) -> None:
    """Each card as the calibration service and the endpoint give it: from the first valid outcome
    on, its sample count, Brier score, log loss and top-label hit rate are shown, and no line of the
    card says "not measured" (or "not yet", or "not surfaced") over them."""

    item = _item("1H", count)
    gate = COUNTS[count]
    assert item["sample_gate"] == gate and item["valid_count"] == count
    lines = cut["timeframes"][str(count)]
    # The timeframe, the gate's badge, then its note.
    assert lines[0] == "1H" and lines[2] == NOTES[gate], lines
    assert harness._value(lines, "Resolved sample count") == str(count)
    if gate == "NO_SAMPLES":
        assert item["metrics_available"] is False
        assert [harness._value(lines, row) for row in METRIC_ROWS] == ["—", "—", "—"]
        return
    assert gate in WITH_METRICS and item["metrics_available"] is True
    for row in METRIC_ROWS:
        assert re.fullmatch(r"\d+(\.\d+)?%?", harness._value(lines, row)), (row, lines)
    assert not any(MEASUREMENT_STATUS.search(line) for line in lines), lines


@pytest.mark.parametrize("answer", ["answered", "unavailable"])
@pytest.mark.parametrize("shape", ["live", "live_claim", "reopened", "reopened_claim"])
def test_the_whole_section_denies_none_of_the_metrics_it_shows(
    sections: dict[str, Any], shape: str, answer: str
) -> None:
    """The whole Model Quality section, with the diagnostics answering (one card per sample gate,
    each with its metrics) and failing: S1 is on it once and the glossary defines its terms; with
    the answer, S2 sits on the INSUFFICIENT_SAMPLE card over its metrics. No line the frontend
    words states a measurement status, except F-3's kept fallbacks on a reopened run without a
    claim."""

    rendered = sections["rendered"][f"{shape}.{answer}"]
    lines = rendered["texts"]
    synthesis, accepted = sections["inputs"][shape]
    assert lines[:2] == ["Model Quality", "Current status"], lines
    assert lines.count(S1) == 1 and MEASURED_CALIBRATION in lines
    assert not any("not surfaced" in line.lower() for line in lines), lines
    kept = F3_KEPT if shape == "reopened" else set()
    calibration = sections["calibration"] if answer == "answered" else None
    assert _stated_status(lines, synthesis, accepted, calibration) <= kept, lines
    cards = {card[0]: card for card in rendered["cards"]}
    if answer == "unavailable":
        assert cards == {}
        return
    assert list(cards) == ["15m", "1H", "4H", "1D", "1M"]
    assert lines.count(S2) == 1 and cards["15m"][2] == S2
    for timeframe in ("15m", "1H", "4H", "1D"):
        for row in METRIC_ROWS:
            assert harness._value(cards[timeframe], row) != "—", (timeframe, row)
    assert cards["1M"][2] == NOTES["NO_SAMPLES"]
