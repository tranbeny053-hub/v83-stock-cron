"""Owner ruling CLASS-B-4=A (2026-10-10), on the screens a user reads.

The real app.js renders real analyses the backend built (the harness of
test_accepted_state_rendering.py): today's ordinary one, where only the evidence gate is active;
one with a real risk gate (a tail-risk breach); and one with the kill switch. On every surface:
- the evidence gate is never shown as elevated risk (plan §14.1: missing evidence must never render
  as a negative market signal), and a real risk gate is shown as one;
- the two cannot be confused on either card;
- both cards carry the view's own sentence under its headline;
- every gate token is what it was.
"""

from __future__ import annotations

import copy
import json
import re
import subprocess
from typing import Any

import pytest
import test_accepted_state_rendering as harness

from crypto_probability_engine.detail import decision_view
from crypto_probability_engine.detail.decision_view import STATE_COPY
from crypto_probability_engine.quant import pipeline

SURFACES = ("matrix", "overview", "detail")
EVIDENCE_SENTENCE = (
    "Evidence gate: directional skill is not established for this model and timeframe. No risk "
    "gate is active."
)
RISK_SENTENCE = (
    "A risk gate is active: Extreme-move risk is too high. The evidence gate is active too: "
    "directional skill is not established for this model and timeframe."
)
KILL_SENTENCE = (
    "A system or data gate is active: Safety shutdown is active. The evidence gate is active "
    "too: directional skill is not established for this model and timeframe."
)
ELEVATED_RISK_WORDS = re.compile(r"elevated[- ]risk", re.IGNORECASE)
NOT_A_RISK_FINDING = "not forced by a risk gate"


def _with_a_tail_risk_breach() -> dict:
    real = pipeline.compute_tail_cvar

    def breached(candles: Any, *, timeframe: str) -> dict:
        state = real(candles, timeframe=timeframe)
        return {**state, "cvar_loss": float(state["cvar_breach_threshold"]) * 2}

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(pipeline, "compute_tail_cvar", breached)
        return harness._analysis("1H")


def _with_the_kill_switch() -> dict:
    flags = {**pipeline.global_risk_state(), "kill_switch": True}
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(pipeline, "global_risk_state", lambda: dict(flags))
        return harness._analysis("1H")


def _not_assessed(payload: dict) -> dict:
    """SYNTHETIC: the view's invalid-data state, which no analysis reaches today (invalid data
    ends in an error). Only the view differs from the ordinary analysis."""

    synthetic = copy.deepcopy(payload)
    view = synthetic["decision_view"]
    headline, sentence = STATE_COPY["INVALID_OR_UNAVAILABLE_DATA"]
    view.update(state="INVALID_OR_UNAVAILABLE_DATA", headline=headline, detail=sentence)
    view["range"].update(
        assessed=False,
        in_band_frac=None,
        up_frac=None,
        down_frac=None,
        meaning=decision_view.NOT_ASSESSED,
    )
    return synthetic


@pytest.fixture(scope="module")
def cases() -> dict[str, dict]:
    evidence = harness._analysis("1H")
    return {
        "evidence": evidence,
        "risk": _with_a_tail_risk_breach(),
        "kill": _with_the_kill_switch(),
        "not_assessed": _not_assessed(evidence),
    }


@pytest.fixture(scope="module")
def rendered(cases: dict[str, dict]) -> dict[str, dict[str, list[str]]]:
    assert harness.NODE is not None, "node is required to run the real app.js"
    script = "\n".join(
        [
            harness._DOM_STAND_IN,
            (harness.ROOT / "frontend" / "app.js").read_text(encoding="utf-8"),
            f"const cases = {json.dumps(cases, default=str)};",
            f"const diagnostics = {json.dumps(harness._diagnostics())};",
            harness._RENDER,
        ]
    )
    done = subprocess.run(  # noqa: S603 - node on a script built here
        [harness.NODE, "-"],
        input=script,
        capture_output=True,
        encoding="utf-8",
        check=True,
        timeout=60,
    )
    return json.loads(done.stdout)["texts"]


def test_the_analyses_are_the_gates_they_claim_and_every_token_is_unchanged(
    cases: dict[str, dict],
) -> None:
    expected = {
        "evidence": ("NO_TRADE", ["SKILL_NOT_DEMONSTRATED"], False),
        "risk": ("NO_TRADE", ["TAIL_RISK_BREACH", "SKILL_NOT_DEMONSTRATED"], True),
        "kill": ("ABORT", ["KILL_SWITCH", "SKILL_NOT_DEMONSTRATED"], False),
    }
    for name, (action, blocks, risk_guard) in expected.items():
        payload = cases[name]
        gate = payload["gate_result"]
        assert gate["action"] == action, name
        assert gate["hard_blocks"] == blocks, name
        assert gate["risk_guard_applied"] is risk_guard, name
        assert gate["skill_guard_applied"] is True, name
        assert gate["forced_score_disposition"] == "ELEVATED_RISK_AVOID", name
        assert payload["score_stack"]["disposition"] == "ELEVATED_RISK_AVOID", name
        assert payload["decision_synthesis"]["decision_synthesis"]["label"] == "NO_TRADE", name
        assert payload["frontend_display"]["disposition"] == action, name
        assert payload["decision_view"]["state"] == "NO_ACCEPTED_CLAIM", name
    assert decision_view.ACCEPTED_FORECAST_CLAIMS == frozenset()
    assert decision_view.ACCEPTED_DIRECTIONAL_PERMISSIONS == frozenset()
    assert len(decision_view.ACCEPTANCE_BLOCKERS) == 4


def test_the_evidence_gate_is_never_shown_as_elevated_risk(rendered: dict) -> None:
    for surface in SURFACES:
        for text in rendered["evidence"][surface]:
            if ELEVATED_RISK_WORDS.search(text.replace("ELEVATED_RISK_AVOID", "")):
                raise AssertionError(f"{surface}: {text}")
            if "ELEVATED_RISK_AVOID" in text:
                assert NOT_A_RISK_FINDING in text, f"{surface}: the token without its reason"
    detail = rendered["evidence"]["detail"]
    assert harness._value(detail, "Why this is limited") == EVIDENCE_SENTENCE
    assert any(
        text.endswith("backend disposition is ELEVATED_RISK_AVOID (not forced by a risk gate).")
        for text in detail
    )


def test_a_real_risk_gate_is_shown_as_one(rendered: dict) -> None:
    detail = rendered["risk"]["detail"]
    assert harness._value(detail, "Why this is limited") == (
        "The elevated-risk disposition disables scenario planning."
    )
    assert any(text.endswith("backend disposition is ELEVATED_RISK_AVOID.") for text in detail)
    for surface in SURFACES:
        texts = rendered["risk"][surface]
        assert not any(NOT_A_RISK_FINDING in text for text in texts), surface
        assert not any("No risk gate is active" in text for text in texts), surface


@pytest.mark.parametrize(
    ("name", "sentence"),
    [("evidence", EVIDENCE_SENTENCE), ("risk", RISK_SENTENCE), ("kill", KILL_SENTENCE)],
)
def test_the_timeframe_card_says_which_kind_of_gate_blocks(
    rendered: dict, name: str, sentence: str
) -> None:
    card = rendered[name]["matrix"]
    assert card[:2] == ["BLOCK", sentence]
    assert sentence in rendered[name]["detail"]


def test_missing_evidence_and_a_real_block_cannot_be_confused_on_the_timeframe_card(
    rendered: dict,
) -> None:
    banners = {name: rendered[name]["matrix"][1] for name in ("evidence", "risk", "kill")}
    assert len(set(banners.values())) == 3
    assert "No risk gate is active." in banners["evidence"]
    assert banners["risk"].startswith("A risk gate is active")
    assert banners["kill"].startswith("A system or data gate is active")


@pytest.mark.parametrize("surface", ["matrix", "overview"])
def test_both_cards_carry_the_views_sentence_under_its_headline(
    rendered: dict, surface: str
) -> None:
    headline, sentence = STATE_COPY["NO_ACCEPTED_CLAIM"]
    assert "not a reason to act or to avoid acting" in sentence
    under_risk = decision_view.NO_ACCEPTED_CLAIM_UNDER_A_RISK_GATE
    assert "act or to avoid acting" not in under_risk
    for name in ("evidence", "risk", "kill"):
        expected = under_risk if name == "risk" else sentence
        texts = rendered[name][surface]
        assert texts[texts.index(headline) + 1] == expected, (name, surface)
        assert texts.count(expected) == 1, (name, surface)


def test_no_directional_reading_is_shown_where_the_view_assesses_nothing(rendered: dict) -> None:
    heat = "Signal heat (not risk)"
    for surface in ("matrix", "overview"):
        assert heat in rendered["evidence"][surface], surface
        assert heat not in rendered["not_assessed"][surface], surface
    interpretation = harness._between(
        rendered["evidence"]["detail"], "Probability interpretation", "Timeframe role"
    )
    assert (
        "UP_LEAN" in interpretation
        or "DOWN_LEAN" in interpretation
        or ("BALANCED" in interpretation)
    )
    withheld = harness._between(
        rendered["not_assessed"]["detail"], "Probability interpretation", "Timeframe role"
    )
    for reading in ("UP_LEAN", "DOWN_LEAN", "BALANCED"):
        assert reading not in withheld, reading
    assert not any("heuristic probability" in text for text in withheld)
