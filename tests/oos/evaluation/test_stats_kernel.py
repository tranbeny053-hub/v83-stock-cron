from __future__ import annotations

import math
from itertools import pairwise

import pytest

from crypto_probability_engine.oos.evaluation.stats_kernel import (
    sign_test_one_sided_p,
    student_t_lower_tail_cdf,
)


@pytest.mark.parametrize(
    ("k", "n_neg", "expected"),
    [
        (5, 5, 0.03125),
        (4, 4, 0.0625),
        (5, 4, 0.1875),
        (6, 6, 0.015625),
        (10, 9, 0.010742187500),
        (1, 1, 0.5),
        (0, 0, 1.0),
        (3, 0, 1.0),
    ],
)
def test_sign_test_known_exact_binomial_tails(k: int, n_neg: int, expected: float) -> None:
    assert sign_test_one_sided_p(n_neg, k) == pytest.approx(expected, abs=1e-15)


def test_sign_test_pins_five_window_attainability_boundary() -> None:
    assert sign_test_one_sided_p(5, 5) <= 0.05
    assert sign_test_one_sided_p(4, 4) > 0.05


@pytest.mark.parametrize(("n_neg", "k"), [(-1, 1), (2, 1), (0, -1)])
def test_sign_test_rejects_invalid_counts(n_neg: int, k: int) -> None:
    with pytest.raises(ValueError):
        sign_test_one_sided_p(n_neg, k)


@pytest.mark.parametrize("df", [1, 2, 3, 5, 10, 30])
def test_student_t_zero_is_half(df: int) -> None:
    assert student_t_lower_tail_cdf(0.0, df) == 0.5


@pytest.mark.parametrize(
    ("t", "df", "expected"),
    [
        (1.0, 1, 0.75),
        (-1.0, 1, 0.25),
        (1.0, 2, 0.5 + 1.0 / (2.0 * math.sqrt(3.0))),
        (-1.0, 2, 0.21132486540518713),
        (2.0, 2, 0.5 + 1.0 / math.sqrt(6.0)),
    ],
)
def test_student_t_closed_form_known_answers(t: float, df: int, expected: float) -> None:
    assert student_t_lower_tail_cdf(t, df) == pytest.approx(expected, abs=1e-12)


@pytest.mark.parametrize(
    ("df", "critical_value"),
    [(1, -6.313752), (4, -2.131847), (9, -1.833113), (29, -1.699127)],
)
def test_student_t_published_one_sided_five_percent_critical_values(
    df: int, critical_value: float
) -> None:
    assert student_t_lower_tail_cdf(critical_value, df) == pytest.approx(0.05, abs=1e-6)


@pytest.mark.parametrize("df", [1, 2, 3, 5, 10, 30])
@pytest.mark.parametrize("t", [0.125, 0.5, 1.0, 2.5, 8.0])
def test_student_t_cdf_is_symmetric(t: float, df: int) -> None:
    total = student_t_lower_tail_cdf(t, df) + student_t_lower_tail_cdf(-t, df)
    assert total == pytest.approx(1.0, abs=1e-12)


@pytest.mark.parametrize("df", [1, 2, 4, 9, 29])
def test_student_t_cdf_is_monotonic_in_t(df: int) -> None:
    values = [
        student_t_lower_tail_cdf(t, df) for t in (-10.0, -2.0, -0.5, 0.0, 0.5, 2.0, 10.0)
    ]
    assert values == sorted(values)
    assert all(left < right for left, right in pairwise(values))


@pytest.mark.parametrize(("t", "df"), [(0.0, 0), (math.inf, 1), (-math.inf, 2), (math.nan, 3)])
def test_student_t_rejects_invalid_inputs(t: float, df: int) -> None:
    with pytest.raises(ValueError):
        student_t_lower_tail_cdf(t, df)
