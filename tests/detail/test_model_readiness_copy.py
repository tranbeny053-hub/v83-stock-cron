"""The model-readiness sentence is true in every state (F-6; PROVISIONAL wording).

It is the "Evidence level" row of every screen that holds no accepted claim. It said that accuracy
was "not yet measured". A NO_DEMONSTRATED_SKILL screen contradicted that: its evidence gate gives
the accuracy observed on the timeframe's resolved outcomes. A held screen did too (its legacy
measurement exists and is withheld), and so did the raw response, which carries the measured
`skill_evidence`. Whether an accuracy was observed depends on the timeframe's evidence, so the
sentence now states no measurement status. These tests prove that:
- the sentence makes no measurement claim, and still says the model is an uncalibrated heuristic;
- the human route and the isolated automation route carry that one sentence, in
  `frontend_display` and in `timeframes`, in five states of the timeframe's evidence that cover
  every verdict a live analysis can hold today: no outcomes; too few, with a rate; no demonstrated
  skill, with and without a rate; a legacy pass under the H2 hold;
- on the NO_DEMONSTRATED_SKILL screen, as the real frontend/app.js renders it, the sentence stands
  beside the evidence gate's observed accuracy;
- a reopened saved run's evidence level is that sentence;
- beyond 1H (the review's MINOR-1): both routes carry the sentence on 15m, 1D and 1W with
  NO_DEMONSTRATED_SKILL evidence, with and without a rate, and on 4H under the H2 hold; the
  Decision view's "Evidence level" row is the sentence on held screens (1H, 4H) and on those
  no-skill screens, as the real app.js renders them.
"""

from __future__ import annotations

import json
from copy import deepcopy

import pytest

from crypto_probability_engine.api import analysis_service
from crypto_probability_engine.api.schemas import AnalysisRequest
from crypto_probability_engine.calibration import skill as skill_module
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.detail.decision_brief import MODEL_READINESS_COPY
from crypto_probability_engine.detail.saved_run_view import attach_saved_run_view
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from crypto_probability_engine.utils.sanitize import sanitize_for_export
from tests.automation.conftest import fixture_selection
from tests.frontend import fullscreen_goldens as goldens

# The timeframe's evidence in five states, which cover every verdict a live analysis can hold today.
STATES = {
    "no_outcomes": {"verdict": "INSUFFICIENT_EVIDENCE", "n": 0, "observed_directional_rate": None},
    "few_outcomes_with_a_rate": {
        "verdict": "INSUFFICIENT_EVIDENCE",
        "n": 40,
        "observed_directional_rate": 0.55,
    },
    "no_skill_with_a_rate": {
        "verdict": "NO_DEMONSTRATED_SKILL",
        "n": 400,
        "observed_directional_rate": 0.44,
    },
    "no_skill_without_a_rate": {
        "verdict": "NO_DEMONSTRATED_SKILL",
        "n": 400,
        "observed_directional_rate": None,
    },
    # A legacy pass: the H2 hold withholds it, and the evidence gate stays active.
    "legacy_pass_under_the_hold": {
        "verdict": "SKILL_DEMONSTRATED",
        "n": 154,
        "observed_directional_rate": 0.62,
    },
}
OBSERVED_ACCURACY = "The accuracy observed on these outcomes was 44.0%."
MEASUREMENT_WORDS = ("measured", "not yet", "accuracy")
HELD = "legacy_pass_under_the_hold"
NO_SKILL = ("no_skill_with_a_rate", "no_skill_without_a_rate")
# The review's MINOR-1 (F-6): the label and the screen's row were pinned on 1H alone, so a label
# that reverted on 1D only (or on 15m, 1D and 1W only), and a row that changed under the H2 hold
# only (or on 1D only), passed. The timeframes it named: 15m, 1D and 1W with NO_DEMONSTRATED_SKILL
# evidence, and 1H and 4H under the hold. 1H's held analysis is in the route/state test above.
OTHER_TIMEFRAMES = [
    *((timeframe, state) for timeframe in ("15m", "1D", "1W") for state in NO_SKILL),
    ("4H", HELD),
]
# The screens rendered for the row: held on 1H and 4H; no skill on 15m, 1D and 1W.
SCREENS = {
    "held_1H": ("1H", HELD),
    "held_4H": ("4H", HELD),
    "no_skill_15m": ("15m", "no_skill_without_a_rate"),
    "no_skill_1D": ("1D", "no_skill_with_a_rate"),
    "no_skill_1W": ("1W", "no_skill_with_a_rate"),
}


def _analysis(
    monkeypatch: pytest.MonkeyPatch, state: str, *, isolated: bool = False, timeframe: str = "1H"
) -> dict:
    """One analysis of the real service on the fixture candles (no network, no database), with the
    timeframe's evidence in `state`: the human route's, or the isolated automation route's."""

    evidence = STATES[state]
    monkeypatch.setattr(analysis_service, "select_market_data", fixture_selection())
    monkeypatch.setattr(analysis_service, "get_cached_skill_evidence", lambda _tf: dict(evidence))
    request = AnalysisRequest(symbol="BTC/USDT", timeframe=timeframe)
    settings = Settings(data_mode="fixture")
    if isolated:
        return analysis_service.analyze_request_isolated(request, settings=settings)
    payload = analysis_service.analyze_request(
        request, settings=settings, run_store=InMemoryRunStore(limit=10)
    )
    analysis_service._pop_prediction_persistence(payload)  # noqa: SLF001 - clean up
    return payload


def _states_no_measurement(sentence: str) -> bool:
    return not any(words in sentence.lower() for words in MEASUREMENT_WORDS)


def test_the_sentence_states_no_measurement_status() -> None:
    assert _states_no_measurement(MODEL_READINESS_COPY), MODEL_READINESS_COPY
    assert "heuristic" in MODEL_READINESS_COPY.lower()
    assert "uncalibrated" in MODEL_READINESS_COPY.lower()


@pytest.mark.parametrize("isolated", [False, True], ids=["human", "automation"])
@pytest.mark.parametrize("state", list(STATES))
def test_both_routes_carry_the_one_sentence_in_every_state(
    monkeypatch: pytest.MonkeyPatch, state: str, isolated: bool
) -> None:
    payload = _analysis(monkeypatch, state, isolated=isolated)
    # The analysis is the one named: its route, its evidence as found, and the gate's hold.
    assert ("decision_view" in payload) is not isolated
    assert payload["skill_evidence"]["verdict"] == STATES[state]["verdict"]
    assert payload["skill_evidence"]["n"] == STATES[state]["n"]
    assert "SKILL_NOT_DEMONSTRATED" in payload["gate_result"]["hard_blocks"]
    hold = payload["gate_result"].get("directional_evidence_hold")
    if state == "legacy_pass_under_the_hold":
        assert skill_module.LEGACY_PASS_LIFTS_HARD_BLOCK is False, "the H2 hold must be in force"
        assert hold["active"] is True and hold["legacy_verdict"] == "SKILL_DEMONSTRATED"
    else:
        assert hold is None
    assert payload["frontend_display"]["model_readiness_label"] == MODEL_READINESS_COPY
    assert payload["timeframes"]["model_readiness_label"] == MODEL_READINESS_COPY


@pytest.mark.parametrize("isolated", [False, True], ids=["human", "automation"])
@pytest.mark.parametrize(("timeframe", "state"), OTHER_TIMEFRAMES)
def test_both_routes_carry_the_one_sentence_beyond_1h(
    monkeypatch: pytest.MonkeyPatch, timeframe: str, state: str, isolated: bool
) -> None:
    payload = _analysis(monkeypatch, state, isolated=isolated, timeframe=timeframe)
    # The analysis is the one named: its timeframe, its route, its evidence and the gate's hold.
    assert payload["timeframes"]["primary"] == timeframe
    assert ("decision_view" in payload) is not isolated
    assert payload["skill_evidence"] == STATES[state]
    assert "SKILL_NOT_DEMONSTRATED" in payload["gate_result"]["hard_blocks"]
    hold = payload["gate_result"].get("directional_evidence_hold")
    if state == HELD:
        assert hold["active"] is True and hold["legacy_verdict"] == "SKILL_DEMONSTRATED"
    else:
        assert hold is None
    assert payload["frontend_display"]["model_readiness_label"] == MODEL_READINESS_COPY
    assert payload["timeframes"]["model_readiness_label"] == MODEL_READINESS_COPY


def test_on_the_no_skill_screen_the_sentence_stands_beside_the_observed_accuracy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _analysis(monkeypatch, "no_skill_with_a_rate")
    display = payload["frontend_display"]
    reasons = display["blocking_reasons"]
    (reason,) = [entry for entry in reasons if entry["code"] == "SKILL_NOT_DEMONSTRATED"]
    assert OBSERVED_ACCURACY in reason["detail"]
    blocks = payload["decision_view"]["gates"]["blocks"]
    (entry,) = [block for block in blocks if block["kind"] == "EVIDENCE"]
    assert OBSERVED_ACCURACY in entry["detail"], "the evidence gate's entry gives the accuracy"
    assert display["model_readiness_label"] == MODEL_READINESS_COPY
    # The screen as the real app.js renders it: the Decision view's evidence gate entry gives the
    # accuracy observed, and its "Evidence level" row is the sentence, which claims no measurement.
    screen = goldens.render({"no_skill": payload}, {})["screens"]["no_skill"]["detail"]
    assert any(OBSERVED_ACCURACY in text for text in screen)
    readiness = [text for text in screen if "Model readiness" in text]
    assert readiness == [MODEL_READINESS_COPY]
    assert screen[screen.index(MODEL_READINESS_COPY) - 1] == "Evidence level"
    assert _states_no_measurement(readiness[0])


def test_the_evidence_level_row_is_the_sentence_on_held_and_other_timeframe_screens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Decision view's "Evidence level" row on held screens (1H, 4H) and on no-skill screens
    (15m, 1D, 1W), as the real app.js renders them, in one render: it is the sentence, the only
    readiness line on each screen."""

    payloads = {
        name: _analysis(monkeypatch, state, timeframe=timeframe)
        for name, (timeframe, state) in SCREENS.items()
    }
    screens = goldens.render(payloads, {})["screens"]
    for name, (timeframe, state) in SCREENS.items():
        payload = payloads[name]
        assert payload["timeframes"]["primary"] == timeframe, name
        held = payload["decision_view"]["evidence"]["directional_evidence_hold"]
        assert held is (state == HELD), name
        screen = screens[name]["detail"]
        assert screen[screen.index("Evidence level") + 1] == MODEL_READINESS_COPY, name
        readiness = [text for text in screen if "Model readiness" in text]
        assert readiness == [MODEL_READINESS_COPY], name
        # With a rate, the evidence gate gives the accuracy observed beside it.
        observed = any(OBSERVED_ACCURACY in text for text in screen)
        assert observed is (state == "no_skill_with_a_rate"), name


@pytest.mark.parametrize("state", list(STATES))
def test_a_reopened_saved_run_reads_the_sentence(
    monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    payload = _analysis(monkeypatch, state)
    # What a run stores (its detail view through the export sanitizer, as JSON reads it back),
    # with the view the detail route builds from it when it reads it.
    stored = json.loads(json.dumps(sanitize_for_export(deepcopy(payload["detail_view"]))))
    saved = attach_saved_run_view(stored)["saved_run_view"]
    assert saved["evidence"]["level"] == MODEL_READINESS_COPY
