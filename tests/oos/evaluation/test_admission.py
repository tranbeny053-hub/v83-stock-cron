"""Tier-1/Tier-2 admission and the half-open holdout bound."""

from __future__ import annotations

from datetime import timedelta

import pytest

from crypto_probability_engine.oos.evaluation import admission
from tests.oos.evaluation.conftest import T0, T_CLOSE, evidence_row


def test_holdout_is_half_open_on_reference_close() -> None:
    assert admission.within_holdout(T0, T0, T_CLOSE) is True
    assert admission.within_holdout(T_CLOSE - timedelta(seconds=1), T0, T_CLOSE) is True
    assert admission.within_holdout(T_CLOSE, T0, T_CLOSE) is False
    assert admission.within_holdout(T0 - timedelta(seconds=1), T0, T_CLOSE) is False


def test_rows_collected_after_t_close_are_excluded() -> None:
    """The collector kept running past T_close; those rows must not reach a statistic."""

    rows = [
        evidence_row(T0),
        evidence_row(T_CLOSE),
        evidence_row(T_CLOSE + timedelta(hours=2)),
    ]
    result = admission.admit(rows, t0=T0, t_close=T_CLOSE)
    assert result.tier1_in_holdout == 1
    assert result.tier1_outside_holdout == 2
    assert result.admitted_count == 1


@pytest.mark.parametrize(
    ("kwargs", "cause"),
    [
        ({"baseline_label": None}, admission.UNRESOLVED_BASELINE),
        ({"candidate_label": None}, admission.UNRESOLVED_CANDIDATE),
        ({"baseline_label": "UP", "candidate_label": "DOWN"}, admission.LABEL_DISAGREEMENT),
    ],
)
def test_tier2_rejections_are_counted_by_cause(kwargs: dict, cause: str) -> None:
    result = admission.admit([evidence_row(T0, **kwargs)], t0=T0, t_close=T_CLOSE)
    assert result.admitted_count == 0
    assert result.rejections[cause] == 1


def test_admission_works_without_probabilities() -> None:
    """Readiness admits on the same rule with no probabilities loaded."""

    rows = [evidence_row(T0, with_probabilities=False)]
    result = admission.admit(rows, t0=T0, t_close=T_CLOSE)
    assert result.admitted_count == 1
    assert not any(key.endswith("_p_up_frac") for key in result.admitted[0])


def test_resolution_after_close_is_counted_but_never_excludes() -> None:
    row = evidence_row(
        T_CLOSE - timedelta(hours=1), horizon_end_utc=T_CLOSE + timedelta(hours=23)
    )
    result = admission.admit([row], t0=T0, t_close=T_CLOSE)
    assert result.admitted_count == 1, "membership is fixed by reference_close_utc alone"
    assert result.resolved_after_close == 1
