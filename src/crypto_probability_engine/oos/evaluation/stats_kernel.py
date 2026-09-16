"""Dependency-free boundary statistics for the Section 5A evaluator."""

from __future__ import annotations

import math
import sys

_BETA_EPSILON = 3.0e-14
_BETA_MAX_ITERATIONS = 200
_BETA_FPMIN = sys.float_info.min / _BETA_EPSILON


def student_t_lower_tail_cdf(t: float, df: int) -> float:
    """Return ``P(T_df <= t)`` via the regularized incomplete beta function."""

    if df < 1:
        raise ValueError("df must be at least 1")
    if not math.isfinite(t):
        raise ValueError("t must be finite")
    if t == 0.0:
        return 0.5

    x = df / (df + t * t)
    beta = _regularized_incomplete_beta(x, df / 2.0, 0.5)
    lower_tail = 0.5 * beta
    return lower_tail if t < 0.0 else 1.0 - lower_tail


def sign_test_one_sided_p(n_neg: int, k: int) -> float:
    """Return the exact fair-binomial upper tail from ``n_neg`` through ``k``."""

    if not 0 <= n_neg <= k:
        raise ValueError("expected 0 <= n_neg <= k")
    numerator = sum(math.comb(k, i) for i in range(n_neg, k + 1))
    return numerator / (1 << k)


def _regularized_incomplete_beta(x: float, a: float, b: float) -> float:
    """Evaluate I_x(a, b) using a continued fraction."""

    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0

    log_front = (
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log1p(-x)
    )
    front = math.exp(log_front)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _beta_continued_fraction(a, b, x) / a
    return 1.0 - front * _beta_continued_fraction(b, a, 1.0 - x) / b


def _beta_continued_fraction(a: float, b: float, x: float) -> float:
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < _BETA_FPMIN:
        d = _BETA_FPMIN
    d = 1.0 / d
    result = d

    for iteration in range(1, _BETA_MAX_ITERATIONS + 1):
        doubled = 2 * iteration
        coefficient = iteration * (b - iteration) * x / (
            (qam + doubled) * (a + doubled)
        )
        d = 1.0 + coefficient * d
        if abs(d) < _BETA_FPMIN:
            d = _BETA_FPMIN
        c = 1.0 + coefficient / c
        if abs(c) < _BETA_FPMIN:
            c = _BETA_FPMIN
        d = 1.0 / d
        result *= d * c

        coefficient = -(a + iteration) * (qab + iteration) * x / (
            (a + doubled) * (qap + doubled)
        )
        d = 1.0 + coefficient * d
        if abs(d) < _BETA_FPMIN:
            d = _BETA_FPMIN
        c = 1.0 + coefficient / c
        if abs(c) < _BETA_FPMIN:
            c = _BETA_FPMIN
        d = 1.0 / d
        delta = d * c
        result *= delta
        if abs(delta - 1.0) <= _BETA_EPSILON:
            return result

    raise ArithmeticError("regularized incomplete beta did not converge")

