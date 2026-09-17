"""The proper-score skill classifier for zero-location methodologies. PREP ONLY: NOTHING SELECTS IT.

WHY. ``classify_directional_skill`` tests the directional hit rate against a coin. A methodology
with no location term (distributional-v1, the distributional-v2 candidate) makes no conditional
directional claim: its up/down split is a fixed skew of its empirical shape tables. So that test
measures market drift against a static skew, not model skill (R2 finding A6).

THE RECOMMENDED DEFAULT (docs/R2_ZERO_DRIFT_GATE_AND_DISPLAY.md §2), implemented exactly:
- skill is demonstrated when the model beats climatology on strictly proper scores, and log loss
  AND Brier must both clear;
- the reference is the empirical three-class base rate of the same evaluated rows, per
  ``(normalized_symbol, timeframe)``;
- the rule is a one-sided paired test that the mean per-row difference ``model - climatology`` is
  below zero, at the 0.05 convention. It uses the section 5A statistics kernel, so no new
  mathematics enters the product;
- the floor is the same 100 resolved outcomes, but it now counts every resolved outcome, TIMEOUT
  included;
- the verdicts are unchanged, so ``apply_skill_gate``, hard-gate seniority, the detail view and the
  frontend are untouched. ``observed_directional_rate`` is ``None``, because no directional rate is
  measured.
Fail-closed behaviour is kept: any unusable row, too few rows, or an undefined statistic can never
demonstrate skill.

ADOPTION IS THE OWNER'S DECISION (R2 §7.2 (a)). Nothing calls ``classify_proper_score_skill`` or
``skill_classifier_for``. Adoption would also need the repository to return per-row probabilities
(``persistence/repository.py``, pinned by the section 5A evaluator).
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from crypto_probability_engine.calibration.metrics import (
    EPS,
    brier_score,
    normalize_probabilities,
)
from crypto_probability_engine.calibration.schemas import OUTCOME_LABELS, SkillEvidence
from crypto_probability_engine.config.defaults import (
    DEFAULT_METHODOLOGY_VERSION,
    DISTRIBUTIONAL_METHODOLOGY_VERSION,
    MIN_DIRECTIONAL_SAMPLES,
)
from crypto_probability_engine.oos.evaluation.stats_kernel import student_t_lower_tail_cdf
from crypto_probability_engine.quant.probability_distributional_v2 import CANDIDATE_NAME

BOUNDARY_CONVENTION = 0.05
DIRECTIONAL = "directional"
PROPER_SCORE = "proper_score"
# The classifier each methodology is judged by. Unknown methodologies refuse (fail closed).
SKILL_CLASSIFIER_BY_METHODOLOGY = {
    DEFAULT_METHODOLOGY_VERSION: DIRECTIONAL,
    DISTRIBUTIONAL_METHODOLOGY_VERSION: PROPER_SCORE,
    CANDIDATE_NAME: PROPER_SCORE,
}


@dataclass(frozen=True)
class ScoreTest:
    """One strictly proper score: the model against climatology on the same rows."""

    model_mean: float
    climatology_mean: float
    mean_difference: float
    boundary: float | None
    holds: bool


@dataclass(frozen=True)
class ProperScoreSkill:
    verdict: str
    n: int
    groups: int
    log_loss: ScoreTest | None
    brier: ScoreTest | None
    reason: str | None

    def evidence(self) -> SkillEvidence:
        return {"verdict": self.verdict, "n": self.n, "observed_directional_rate": None}


def skill_classifier_for(methodology_version: str) -> str:
    """Which skill classifier judges ``methodology_version``."""

    try:
        return SKILL_CLASSIFIER_BY_METHODOLOGY[methodology_version]
    except KeyError as exc:
        raise ValueError(
            f"no skill classifier is defined for methodology {methodology_version!r}"
        ) from exc


def classify_proper_score_skill(
    rows: Sequence[Mapping[str, Any]],
    *,
    min_samples: int = MIN_DIRECTIONAL_SAMPLES,
) -> SkillEvidence:
    """The skill verdict, in the shape ``classify_directional_skill`` returns."""

    return assess_proper_score_skill(rows, min_samples=min_samples).evidence()


def assess_proper_score_skill(
    rows: Sequence[Mapping[str, Any]],
    *,
    min_samples: int = MIN_DIRECTIONAL_SAMPLES,
) -> ProperScoreSkill:
    """The verdict with both score tests, for a report."""

    parsed = []
    for row in rows:
        item = _parse(row)
        if item is None:
            return ProperScoreSkill(
                "INSUFFICIENT_EVIDENCE", 0, 0, None, None, "an evaluated row is unusable"
            )
        parsed.append(item)
    n = len(parsed)
    counts: dict[tuple[str, str], Counter[str]] = {}
    for group, _, label in parsed:
        counts.setdefault(group, Counter())[label] += 1
    if n < min_samples:
        return ProperScoreSkill(
            "INSUFFICIENT_EVIDENCE",
            n,
            len(counts),
            None,
            None,
            f"{n} resolved outcomes, fewer than {min_samples}",
        )

    climatology = {
        group: {label: tally[label] / sum(tally.values()) for label in OUTCOME_LABELS}
        for group, tally in counts.items()
    }
    log_model, log_climatology, brier_model, brier_climatology = [], [], [], []
    for group, probabilities, label in parsed:
        reference = climatology[group]
        log_model.append(-math.log(max(probabilities[label], EPS)))
        log_climatology.append(-math.log(max(reference[label], EPS)))
        brier_model.append(brier_score(probabilities, label))
        brier_climatology.append(brier_score(reference, label))
    log_loss = _score_test(log_model, log_climatology)
    brier = _score_test(brier_model, brier_climatology)
    verdict = (
        "SKILL_DEMONSTRATED" if log_loss.holds and brier.holds else "NO_DEMONSTRATED_SKILL"
    )
    return ProperScoreSkill(verdict, n, len(counts), log_loss, brier, None)


def _parse(row: Mapping[str, Any]) -> tuple[tuple[str, str], dict[str, float], str] | None:
    try:
        symbol = row["normalized_symbol"]
        timeframe = row["timeframe"]
        label = row["realized_label"]
        raw = {
            "UP": row["p_up_frac"],
            "DOWN": row["p_down_frac"],
            "TIMEOUT": row["p_timeout_frac"],
        }
    except (KeyError, TypeError):
        return None
    if not (isinstance(symbol, str) and symbol and isinstance(timeframe, str) and timeframe):
        return None
    if label not in OUTCOME_LABELS:
        return None
    if any(isinstance(value, bool) for value in raw.values()):
        return None
    probabilities = normalize_probabilities(raw)
    if probabilities is None:
        return None
    return (symbol, timeframe), probabilities, label


def _score_test(model: Sequence[float], climatology: Sequence[float]) -> ScoreTest:
    """One-sided paired t-test that the mean of ``model - climatology`` is below zero.

    Fails closed with fewer than two rows and with zero or non-finite dispersion, exactly as the
    section 5A A1 test does: a strict guard may only err toward no demonstrated skill.
    """

    differences = [m - c for m, c in zip(model, climatology, strict=True)]
    n = len(differences)
    model_mean = math.fsum(model) / n
    climatology_mean = math.fsum(climatology) / n
    mean = math.fsum(differences) / n
    boundary = None
    if n >= 2:
        variance = math.fsum((value - mean) ** 2 for value in differences) / (n - 1)
        stdev = math.sqrt(variance)
        if stdev > 0.0 and math.isfinite(stdev):
            boundary = student_t_lower_tail_cdf(mean / (stdev / math.sqrt(n)), n - 1)
    holds = boundary is not None and boundary <= BOUNDARY_CONVENTION
    return ScoreTest(model_mean, climatology_mean, mean, boundary, holds)
