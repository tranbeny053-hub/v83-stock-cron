"""The proper-score skill classifier (R2 finding A6's recommended default), dormant.

It must demonstrate skill only when the model beats climatology on BOTH strictly proper scores,
refuse everything it cannot judge, and show why the directional classifier misleads for a model
with no location term.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from crypto_probability_engine.calibration import proper_score_skill as skill
from crypto_probability_engine.calibration.skill import classify_directional_skill
from crypto_probability_engine.config.defaults import (
    DEFAULT_METHODOLOGY_VERSION,
    DISTRIBUTIONAL_METHODOLOGY_VERSION,
    MIN_DIRECTIONAL_SAMPLES,
)
from crypto_probability_engine.oos.evaluation.decision import a1

ROOT = Path(__file__).resolve().parents[2]


def _row(label: str, up: float, down: float, timeout: float, **changes) -> dict:
    row = {
        "normalized_symbol": "BTC/USDT",
        "timeframe": "1H",
        "p_up_frac": up,
        "p_down_frac": down,
        "p_timeout_frac": timeout,
        "realized_label": label,
    }
    row.update(changes)
    return row


def _labels(up: int, down: int, timeout: int) -> list[str]:
    return ["UP"] * up + ["DOWN"] * down + ["TIMEOUT"] * timeout


def _informative(label: str, index: int, **changes) -> dict:
    """A model that puts 0.5, 0.6 or 0.7 on what happened: better than a coin, not constant."""

    hit = (0.5, 0.6, 0.7)[index % 3]
    miss = (1.0 - hit) / 2.0
    probabilities = {name: hit if name == label else miss for name in ("UP", "DOWN", "TIMEOUT")}
    return _row(label, probabilities["UP"], probabilities["DOWN"], probabilities["TIMEOUT"],
                **changes)


def test_an_informative_model_beats_climatology_on_both_scores() -> None:
    rows = [
        _informative(("UP", "DOWN", "TIMEOUT")[index % 4 % 3], index) for index in range(300)
    ]
    result = skill.assess_proper_score_skill(rows)
    assert result.verdict == "SKILL_DEMONSTRATED"
    assert result.n == 300 and result.groups == 1
    assert result.log_loss.holds and result.brier.holds
    assert result.log_loss.mean_difference < 0 and result.brier.mean_difference < 0
    assert skill.classify_proper_score_skill(rows) == {
        "verdict": "SKILL_DEMONSTRATED",
        "n": 300,
        "observed_directional_rate": None,
    }


def test_a_perfectly_constant_improvement_fails_closed_like_section_5a_a1() -> None:
    """Zero dispersion leaves the statistic undefined; a strict guard errs toward no skill."""

    rows = [_row(label, *{"UP": (0.6, 0.2, 0.2), "DOWN": (0.2, 0.6, 0.2),
                          "TIMEOUT": (0.2, 0.2, 0.6)}[label])
            for label in _labels(1, 1, 1) * 100]
    result = skill.assess_proper_score_skill(rows)
    assert result.brier.mean_difference < 0
    assert result.brier.boundary is None and result.verdict == "NO_DEMONSTRATED_SKILL"


def test_climatology_itself_can_never_demonstrate_skill() -> None:
    labels = _labels(45, 30, 25) * 4
    rows = [_row(label, 0.45, 0.30, 0.25) for label in labels]
    result = skill.assess_proper_score_skill(rows)
    assert result.verdict == "NO_DEMONSTRATED_SKILL"
    assert result.log_loss.boundary is None, "zero dispersion: the statistic is undefined"
    assert not result.log_loss.holds and not result.brier.holds


def test_a_static_skew_passes_the_directional_gate_but_not_the_proper_score_gate() -> None:
    """R2 finding A6, reproduced: a static UP skew on a market that drifted up."""

    labels = _labels(450, 300, 250)
    rows = [_row(label, 0.36, 0.30, 0.34) for label in labels]
    # The directional classifier sees the top label (UP) hit 450 of 750 non-timeouts: z = 5.5.
    directional = classify_directional_skill(750, 450)
    assert directional["verdict"] == "SKILL_DEMONSTRATED"
    # The static triplet cannot beat the base rate it is compared with.
    proper = skill.assess_proper_score_skill(rows)
    assert proper.verdict == "NO_DEMONSTRATED_SKILL"
    assert proper.log_loss.mean_difference > 0 and proper.brier.mean_difference > 0


def test_both_scores_must_clear() -> None:
    rows = []
    for index in range(400):
        label = "UP" if index % 2 else "DOWN"
        if index % 100 == 0:
            # A confident miss: Brier barely notices, log loss explodes.
            rows.append(_row(label, 1e-9 if label == "UP" else 0.999, 1e-9 if label == "DOWN" else
                             0.999, 0.001))
        else:
            rows.append(_row(label, 0.7 if label == "UP" else 0.29, 0.7 if label == "DOWN" else
                             0.29, 0.01))
    result = skill.assess_proper_score_skill(rows)
    assert result.brier.holds and not result.log_loss.holds
    assert result.verdict == "NO_DEMONSTRATED_SKILL"


def test_the_reference_is_climatology_per_symbol_and_timeframe() -> None:
    btc = [_row(label, 0.6, 0.2, 0.2) for label in _labels(60, 20, 20) * 2]
    eth = [
        _row(label, 0.2, 0.6, 0.2, normalized_symbol="ETH/USDT")
        for label in _labels(20, 60, 20) * 2
    ]
    result = skill.assess_proper_score_skill(btc + eth)
    assert result.groups == 2
    # Each group's model is exactly its own base rate, so it adds nothing over its climatology.
    assert result.verdict == "NO_DEMONSTRATED_SKILL"
    assert result.log_loss.mean_difference == pytest.approx(0.0, abs=1e-15)
    pooled = skill.assess_proper_score_skill(
        [dict(row, normalized_symbol="BTC/USDT") for row in btc + eth]
    )
    assert pooled.verdict == "SKILL_DEMONSTRATED", "pooled, the same rows would look skilful"


def test_the_floor_counts_every_resolved_outcome_including_timeouts() -> None:
    labels = (_labels(1, 1, 2) * 40)[:MIN_DIRECTIONAL_SAMPLES]
    rows = [_informative(label, index) for index, label in enumerate(labels)]
    assert sum(label == "TIMEOUT" for label in labels) == MIN_DIRECTIONAL_SAMPLES // 2
    below = rows[:-1]
    result = skill.assess_proper_score_skill(below)
    assert result.verdict == "INSUFFICIENT_EVIDENCE" and result.n == MIN_DIRECTIONAL_SAMPLES - 1
    assert skill.assess_proper_score_skill(rows).verdict == "SKILL_DEMONSTRATED"
    assert skill.classify_proper_score_skill([])["verdict"] == "INSUFFICIENT_EVIDENCE"


UNUSABLE = {
    "no-label": {"realized_label": None},
    "unknown-label": {"realized_label": "FLAT"},
    "no-symbol": {"normalized_symbol": ""},
    "symbol-not-text": {"normalized_symbol": 7},
    "no-timeframe": {"timeframe": None},
    "boolean-probability": {"p_up_frac": True},
    "negative-probability": {"p_down_frac": -0.1},
    "probability-above-one": {"p_timeout_frac": 1.5},
    "not-a-number": {"p_up_frac": float("nan")},
    "all-zero": {"p_up_frac": 0.0, "p_down_frac": 0.0, "p_timeout_frac": 0.0},
    "text-probability": {"p_up_frac": "0.5x"},
}


@pytest.mark.parametrize("case", sorted(UNUSABLE))
def test_one_unusable_row_fails_the_whole_evaluation_closed(case: str) -> None:
    rows = [_informative(label, index) for index, label in enumerate(_labels(100, 100, 100))]
    assert skill.assess_proper_score_skill(rows).verdict == "SKILL_DEMONSTRATED"
    rows[17] = {**rows[17], **UNUSABLE[case]}
    result = skill.assess_proper_score_skill(rows)
    assert result.verdict == "INSUFFICIENT_EVIDENCE"
    assert result.reason == "an evaluated row is unusable"
    missing = dict(rows[0])
    del missing["p_timeout_frac"]
    assert skill.assess_proper_score_skill([missing]).verdict == "INSUFFICIENT_EVIDENCE"


def test_the_statistic_is_the_section_5a_a1_test_on_the_per_row_differences() -> None:
    differences = [(-1) ** index * 0.1 - 0.02 for index in range(150)]
    model = [1.0 + value for value in differences]
    climatology = [1.0] * len(differences)
    ours = skill._score_test(model, climatology)
    holds, boundary = a1([m - c for m, c in zip(model, climatology, strict=True)])
    assert ours.holds is holds
    assert math.isclose(ours.boundary, boundary, rel_tol=0, abs_tol=0)
    assert skill.BOUNDARY_CONVENTION == 0.05


def test_each_methodology_has_its_classifier_and_unknown_ones_refuse() -> None:
    assert skill.skill_classifier_for(DEFAULT_METHODOLOGY_VERSION) == skill.DIRECTIONAL
    assert skill.skill_classifier_for(DISTRIBUTIONAL_METHODOLOGY_VERSION) == skill.PROPER_SCORE
    assert skill.skill_classifier_for("distributional-v2") == skill.PROPER_SCORE
    with pytest.raises(ValueError, match="no skill classifier"):
        skill.skill_classifier_for("heuristic-v2")


def test_nothing_selects_the_proper_score_classifier_yet() -> None:
    source = ROOT / "src" / "crypto_probability_engine"
    users = [
        path.relative_to(ROOT).as_posix()
        for path in source.rglob("*.py")
        if "proper_score_skill" in path.read_text(encoding="utf-8")
        and path.name != "proper_score_skill.py"
    ]
    assert users == []
