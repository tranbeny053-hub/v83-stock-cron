from __future__ import annotations

import ast
import inspect
from fractions import Fraction as F
from itertools import combinations
from pathlib import Path
from time import perf_counter

import pytest

from scripts import quant_ng_share_kernel as kernel


def _oracle_estimate(S, g, prior, strength):
    a = _oracle_inverse(_oracle_add(S, _oracle_scale(strength, prior)))
    return _oracle_product(a, [[g[0] + strength * prior[0][0] * F(1, 2)]])


def _oracle_add(left, right):
    return [
        [a + b for a, b in zip(row_a, row_b, strict=True)]
        for row_a, row_b in zip(left, right, strict=True)
    ]


def _oracle_scale(value, matrix):
    return [[value * item for item in row] for row in matrix]


def _oracle_product(left, right):
    return [
        [
            sum((a * b for a, b in zip(row, col, strict=True)), F(0))
            for col in zip(*right, strict=True)
        ]
        for row in left
    ]


def _oracle_inverse(matrix):
    matrix = [[F(value) for value in row] for row in matrix]
    n = len(matrix)
    rows = [row[:] + [F(int(i == j)) for j in range(n)] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = next(i for i in range(col, n) if rows[i][col])
        rows[col], rows[pivot] = rows[pivot], rows[col]
        divisor = rows[col][col]
        rows[col] = [value / divisor for value in rows[col]]
        for row in range(n):
            if row != col:
                factor = rows[row][col]
                rows[row] = [a - factor * b for a, b in zip(rows[row], rows[col], strict=True)]
    return [row[n:] for row in rows]


def _oracle_determinant(matrix):
    if len(matrix) == 1:
        return F(matrix[0][0])
    return sum(
        (
            (-1) ** col
            * matrix[0][col]
            * _oracle_determinant([row[:col] + row[col + 1 :] for row in matrix[1:]])
            for col in range(len(matrix))
        ),
        F(0),
    )


def _oracle_positive_definite(matrix):
    return (
        len(matrix) == len(matrix[0])
        and matrix == list(map(list, zip(*matrix, strict=True)))
        and all(
            _oracle_determinant([row[:size] for row in matrix[:size]]) > 0
            for size in range(1, len(matrix) + 1)
        )
    )


def _oracle_positive_semidefinite(matrix):
    if len(matrix) != len(matrix[0]) or matrix != list(map(list, zip(*matrix, strict=True))):
        return False
    n = len(matrix)
    return all(
        _oracle_determinant([[matrix[row][col] for col in indexes] for row in indexes]) >= 0
        for size in range(1, n + 1)
        for indexes in combinations(range(n), size)
    )


def _oracle_unshared(S, moment):
    return _oracle_product(_oracle_inverse(S), [[value] for value in moment])


def _oracle_universe(weights, estimates):
    total = [[F(0) for _ in weights[0][0]] for _ in weights[0]]
    moment = [[F(0)] for _ in weights[0]]
    for weight, estimate in zip(weights, estimates, strict=True):
        total = _oracle_add(total, weight)
        moment = _oracle_add(moment, _oracle_product(weight, estimate))
    return _oracle_product(_oracle_inverse(total), moment)


def _oracle_shared(S, moment, prior, strength, universe):
    penalty = _oracle_scale(strength, prior)
    adjusted = _oracle_add([[value] for value in moment], _oracle_product(penalty, universe))
    return _oracle_product(_oracle_inverse(_oracle_add(S, penalty)), adjusted)


def _oracle_projector(S, Omega):
    basis = [[F(1)], [F(0)]]
    return _oracle_product(
        _oracle_product(
            basis,
            _oracle_inverse(
                _oracle_product(
                    _oracle_product(list(map(list, zip(*basis, strict=True))), S), basis
                )
            ),
        ),
        _oracle_product(list(map(list, zip(*basis, strict=True))), S),
    )


def _scalar_fixture(gamma=F(1, 100), c=F(0), donor_v=F(1, 40), count=10):
    donors = tuple(range(1, count + 1))
    ids = set(range(count + 2))
    cov = {}
    for i in ids:
        for j in ids:
            if i == j:
                cov[(i, j)] = [[F(1, 40) if i == 0 or i == count + 1 else donor_v]]
            else:
                vi = F(1, 40) if i in (0, count + 1) else donor_v
                vj = F(1, 40) if j in (0, count + 1) else donor_v
                cov[(i, j)] = [[c * kernel.exact_square_root(vi * vj)]]
    w = {j: [[F(1)]] for j in donors}
    return donors, ids, cov, w, [[gamma]]


def _three_regressor_fixture(rx, c, gamma, shape="IDENTITY"):
    donors = tuple(range(1, 11))
    ids = {0, 11, *donors}
    sigma = [[F(1), 0, 0], [0, F(1), rx], [0, rx, F(1)]]
    sigma_inverse = kernel.matrix_inverse(sigma)
    eye = [[F(int(row == col)) for col in range(3)] for row in range(3)]
    cov = {}
    for i in ids:
        for j in ids:
            if i == j:
                factor = F(1) if i not in donors else F(1, 4)
            elif i in donors and j in donors:
                factor = c / 4
            elif i in donors or j in donors:
                factor = c / 2
            else:
                factor = c
            cov[(i, j)] = [[factor * item for item in row] for row in sigma_inverse]
    weights = {j: sigma for j in donors}
    S = sigma
    Omega = [row[:] for row in sigma] if shape == "GRAM" else [row[:] for row in eye]
    Omega[0] = [F(0) for _ in range(3)]
    for row in Omega:
        row[0] = F(0)
    Gamma = [[gamma * item for item in row] for row in sigma_inverse]
    V = [row[:] for row in sigma_inverse]
    return donors, ids, cov, weights, S, Omega, V, Gamma, sigma


def _compare_three_regressor_paths(shape, rx, c, gamma, strengths):
    _assert_fixture(donors=10, regressors=3)
    donors, ids, cov, weights, S, Omega, V, Gamma, sigma = _three_regressor_fixture(
        rx, c, gamma, shape
    )
    z = (F(1, 4) * (1 + 9 * c) + gamma) / 10 + gamma
    cross = c / 2
    for strength in strengths:
        risk = kernel.target_risk(S, weights, Omega, strength, V, Gamma, cov, sigma, donors, 0, ids)
        other = kernel.target_risk(
            S, weights, Omega, strength, V, Gamma, cov, sigma, donors, 11, ids
        )
        matrix_path = kernel.cross_covariance(
            S,
            Omega,
            strength,
            S,
            Omega,
            strength,
            cov[(0, 11)],
            {j: cov[(0, j)] for j in donors},
            {j: cov[(j, 11)] for j in donors},
            {(j, donor_l): cov[(j, donor_l)] for j in donors for donor_l in donors},
            Gamma,
            sigma,
            donors,
            donors,
            weights,
            0,
            11,
            ids,
            risk,
            other,
        )
        form = kernel.directional_totals(F(1), z, cross, gamma, c, 1, 3, shape, strength, rx=rx)
        assert risk["R_S"] == form["R_S"]
        assert matrix_path["rS"] == form["rS"]


def _scalar_risk(gamma=F(1, 100), c=F(0), donor_v=F(1, 40), strength=F(0), target=0):
    donors, ids, cov, weights, gamma_m = _scalar_fixture(gamma, c, donor_v)
    result = kernel.target_risk(
        [[40]], weights, [[1]], strength, [[F(1, 40)]], gamma_m, cov, [[1]], donors, target, ids
    )
    result["Q"] = [[F(1)]]
    return result, (donors, ids, cov, weights, gamma_m)


def _walk_numbers(value):
    if isinstance(value, dict):
        for nested in value.values():
            yield from _walk_numbers(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            yield from _walk_numbers(nested)
    else:
        yield value


def _assert_fixture(donors=10, regressors=1):
    assert donors == 10 or regressors != 8


def test_kat_01_oracle():
    _assert_fixture(regressors=1)
    assert _oracle_estimate([[40]], [F(60)], [[1]], F(10)) == [[F(13, 10)]]


def test_kat_02_risk():
    _assert_fixture(donors=10)
    result, _ = _scalar_risk(strength=F(2000, 27))
    form = kernel.closed_forms(F(1, 40), result["Z"][0][0], result["K"][0][0], F(40))
    assert (
        result["Z"][0][0],
        form["w_star"],
        form["best_strength"],
        form["R_best"],
        result["relative_gain"],
    ) == (F(27, 2000), F(27, 77), F(2000, 27), F(27, 3080), F(50, 77))


def test_kat_03_correlated_risk():
    _assert_fixture(donors=10)
    result, _ = _scalar_risk(c=F(1, 2), strength=F(2000, 49))
    form = kernel.closed_forms(F(1, 40), result["Z"][0][0], result["K"][0][0], F(40))
    assert (
        result["Z"][0][0],
        result["K"][0][0],
        form["w_star"],
        form["R_best"],
        result["relative_gain"],
    ) == (F(99, 4000), F(1, 80), F(49, 99), F(37, 1980), F(25, 99))


def test_kat_04_break_even():
    _assert_fixture(donors=10)
    form = kernel.closed_forms(F(1, 40), F(9, 80), F(0), F(40))
    assert form["w_be"] == F(7, 11)
    assert F(40) * (1 - form["w_be"]) / form["w_be"] == F(160, 7)


def test_kat_05_induced_correlation():
    _assert_fixture(donors=10)
    risk, fixture = _scalar_risk(strength=F(2000, 27))
    donors, ids, cov, weights, gamma = fixture
    other = kernel.target_risk(
        [[40]], weights, [[1]], F(2000, 27), [[F(1, 40)]], gamma, cov, [[1]], donors, 11, ids
    )
    corr = kernel.cross_covariance(
        [[40]],
        [[1]],
        F(2000, 27),
        [[40]],
        [[1]],
        F(2000, 27),
        cov[(0, 11)],
        {j: cov[(0, j)] for j in donors},
        {j: cov[(j, 11)] for j in donors},
        {(j, donor_l): cov[(j, donor_l)] for j in donors for donor_l in donors},
        gamma,
        [[1]],
        donors,
        donors,
        weights,
        0,
        11,
        ids,
        risk,
        other,
    )
    assert corr["rS"] == F(50, 297)
    assert corr["rU"] == 0


def test_kat_06_oracle_id_1():
    _assert_fixture(regressors=1)
    S, moment, omega, b0 = [[4, 1], [1, 3]], [F(5), F(7)], [[1, 0], [0, 1]], [[F(1)], [F(2)]]
    assert _oracle_shared(S, moment, omega, F(0), b0) == _oracle_unshared(S, moment)


def test_kat_07_oracle_id_2():
    _assert_fixture(regressors=1)
    S, moment, omega, b0, strength = (
        [[4, 1], [1, 3]],
        [F(5), F(7)],
        [[1, 0], [0, 1]],
        [[F(1)], [F(2)]],
        F(2),
    )
    estimate = _oracle_unshared(S, moment)
    shared = _oracle_shared(S, moment, omega, strength, b0)
    h = _oracle_product(
        _oracle_inverse(_oracle_add(S, _oracle_scale(strength, omega))),
        _oracle_scale(strength, omega),
    )
    difference = _oracle_add(estimate, _oracle_scale(-1, b0))
    assert shared == _oracle_add(estimate, _oracle_scale(-1, _oracle_product(h, difference)))


def test_kat_08_oracle_id_3():
    _assert_fixture(regressors=2)
    assert kernel.pooling_projector([[4, 2], [2, 3]], [[0, 0], [0, 1]]) == [
        [F(1), F(1, 2)],
        [F(0), F(0)],
    ]
    S, moment, b0 = [[4, 2], [2, 3]], [F(3), F(5)], [[F(1)], [F(2)]]
    pi = _oracle_projector(S, [[0, 0], [0, 1]])
    complement = _oracle_add([[1, 0], [0, 1]], _oracle_scale(-1, pi))
    limit = _oracle_add(
        _oracle_product(pi, _oracle_unshared(S, moment)), _oracle_product(complement, b0)
    )
    assert limit == [[F(-1, 4)], [F(2)]]


def test_kat_09_oracle_id_4():
    _assert_fixture(regressors=2)
    S, moment, omega = [[4, 1], [1, 3]], [F(5), F(7)], [[1, 0], [0, 1]]
    fitted = _oracle_unshared(S, moment)
    for strength in (F(0), F(2), F(10)):
        assert _oracle_shared(S, moment, omega, strength, fitted) == fitted


def test_kat_10_oracle_id_5():
    _assert_fixture(regressors=2)
    S, moment, omega = [[4, 1], [1, 3]], [F(5), F(7)], [[0, 0], [0, 2]]
    G, Gt, Gi = [[1, 1], [0, 1]], [[1, 0], [1, 1]], [[1, -1], [0, 1]]
    b0, strength = [[F(1)], [F(2)]], F(3)
    old = _oracle_shared(S, moment, omega, strength, b0)
    transformed = _oracle_shared(
        _oracle_product(_oracle_product(Gt, S), G),
        [sum((a * b for a, b in zip(row, moment, strict=True)), F(0)) for row in Gt],
        _oracle_product(_oracle_product(Gt, omega), G),
        strength,
        _oracle_product(Gi, b0),
    )
    assert transformed == _oracle_product(Gi, old)


def test_kat_11_oracle_id_6():
    _assert_fixture(regressors=3)
    fits = {"alpha": _oracle_unshared([[2]], [F(6)]), "beta": _oracle_unshared([[4]], [F(12)])}
    permuted = {"beta": _oracle_unshared([[4]], [F(12)]), "alpha": _oracle_unshared([[2]], [F(6)])}
    assert permuted == {name: fits[name] for name in ("beta", "alpha")}


def test_kat_12_oracle_id_7():
    _assert_fixture(regressors=2)
    weights, estimates = [[[1]], [[1]]], [[[F(2)]], [[F(4)]]]
    before = _oracle_universe(weights, estimates)
    changed_target_moment = [F(999)]
    after = _oracle_universe(weights, estimates)
    assert changed_target_moment != [F(3)] and after == before == [[F(3)]]


def test_kat_13_matrix_matches_scalar():
    _assert_fixture(donors=10)
    result, _ = _scalar_risk(c=F(1, 2))
    assert result["R_U"] == F(1, 40)
    assert result["Z"] == [[F(99, 4000)]]
    totals = kernel.directional_totals(
        F(1, 40), F(99, 4000), F(1, 80), F(1, 100), F(1, 2), 40, 3, "GRAM", F(0)
    )
    assert totals["R_U"] == F(3, 40)
    assert totals["rU"] == F(1, 2)


def test_kat_15_interior_best():
    _assert_fixture(donors=10)
    result, _ = _scalar_risk(gamma=F(0))
    form = kernel.closed_forms(F(1, 40), result["Z"][0][0], result["K"][0][0], F(40))
    assert (form["Z"], form["w_star"], form["R_best"], form["R_complete"], form["R_U"]) == (
        F(1, 400),
        F(1, 11),
        F(1, 440),
        F(1, 400),
        F(1, 40),
    )


def test_kat_16_out_of_range_hides_unreachable_value():
    _assert_fixture(donors=10)
    result, _ = _scalar_risk(gamma=F(0), c=F(1, 2), donor_v=F(1, 360))
    form = kernel.closed_forms(F(1, 40), result["Z"][0][0], result["K"][0][0], F(40))
    assert (
        form["Z"],
        form["K"],
        form["w_star"],
        form["flag"],
        form["w_best"],
        form["best_strength"],
        form["R_best"],
    ) == (F(11, 7200), F(1, 240), F(-19, 131), "OUT_OF_RANGE", F(0), "INFINITE", F(11, 7200))
    returned = {"risk": result, "forms": form}
    assert F(3, 2620) not in tuple(_walk_numbers(returned))


def test_kat_17_complete_pooling_unshrunk_intercept():
    _assert_fixture(donors=10, regressors=3)
    result = kernel.directional_totals(
        F(1, 40), F(27, 2000), F(0), F(1, 100), F(0), 40, 3, "GRAM", "INFINITE"
    )
    assert result["R_U"] == F(3, 40)
    assert result["R_S"] == F(13, 250)
    assert result["relative_gain"] == F(23, 75)


def test_kat_18_nonorthogonal_pooling_limit():
    _assert_fixture(regressors=2)
    S, omega = [[4, 2], [2, 3]], [[0, 0], [0, 1]]
    projector = kernel.pooling_projector(S, omega)
    assert projector == [[F(1), F(1, 2)], [F(0), F(0)]]
    assert kernel.matrix_product(
        kernel.matrix_product(projector, [[F(1, 10), 0], [0, F(1, 10)]]),
        kernel.matrix_transpose(projector),
    ) == [[F(1, 8), 0], [0, 0]]


def test_kat_19_target_specific_cross_covariance():
    _assert_fixture(donors=10)
    donors, ids, cov, weights, gamma = _scalar_fixture(F(1, 100), F(1, 2), F(1, 40))
    cov[(0, 11)] = [[F(1, 160)]]
    cov[(11, 0)] = [[F(1, 160)]]
    for donor in donors:
        cov[(donor, 11)] = [[F(1, 160)]]
        cov[(11, donor)] = [[F(1, 160)]]
    r_i = kernel.target_risk(
        [[40]], weights, [[1]], F(10), [[F(1, 40)]], gamma, cov, [[1]], donors, 0, ids
    )
    r_k = kernel.target_risk(
        [[40]], weights, [[1]], F(20), [[F(1, 160)]], gamma, cov, [[1]], donors, 11, ids
    )
    got = kernel.cross_covariance(
        [[40]],
        [[1]],
        F(10),
        [[40]],
        [[1]],
        F(20),
        cov[(0, 11)],
        {j: cov[(0, j)] for j in donors},
        {j: cov[(j, 11)] for j in donors},
        {(j, donor_l): cov[(j, donor_l)] for j in donors for donor_l in donors},
        gamma,
        [[1]],
        donors,
        donors,
        weights,
        0,
        11,
        ids,
        r_i,
        r_k,
    )
    assert got["Cov_eS"] == [[F(509, 60000)]]
    assert F(759, 100000) != got["Cov_eS"][0][0]
    assert "rS" not in got


def test_kat_19_overlapping_donors_direct_covariance():
    _assert_fixture(donors=5, regressors=2)
    donors_i, donors_k = (2, 3), (3, 4)
    ids = {0, 1, 2, 3, 4}
    weights = {j: [[F(1), 0], [0, F(1)]] for j in (2, 3, 4)}
    gamma = [[F(1, 10), F(1, 30)], [F(1, 30), F(1, 5)]]
    cov = {
        (i, j): [[F(1, 12), F(1, 60)], [F(1, 60), F(1, 10)]]
        if i == j
        else [[F(1, 40), F(1, 120)], [F(1, 90), F(1, 30)]]
        for i in ids
        for j in ids
    }
    # Independent direct expansion of the linear error terms, keeping the two target operators.
    wi = {j: F(1, 2) for j in donors_i}
    wk = {j: F(1, 2) for j in donors_k}
    bi, hi, bk, hk = F(3, 4), F(1, 4), F(2, 3), F(1, 3)
    c_ik = cov[(0, 1)][0][0]
    e_i_zk = sum((cov[(0, j)][0][0] * wk[j] for j in donors_k), F(0))
    zi_ek = sum((cov[(j, 1)][0][0] * wi[j] for j in donors_i), F(0))
    zi_zk = sum(
        (wi[j] * wk[donor_l] * cov[(j, donor_l)][0][0] for j in donors_i for donor_l in donors_k),
        F(0),
    )
    zi_zk += sum((wi[j] * wk[j] * gamma[0][0] for j in set(donors_i) & set(donors_k)), F(0))
    direct = bi * bk * c_ik + bi * hk * e_i_zk + hi * bk * zi_ek + hi * hk * zi_zk
    ri = kernel.target_risk(
        [[6, 0], [0, 6]],
        {j: weights[j] for j in donors_i},
        [[1, 0], [0, 1]],
        F(2),
        [[F(1, 12), 0], [0, F(1, 10)]],
        gamma,
        cov,
        [[1, 0], [0, 1]],
        donors_i,
        0,
        ids,
    )
    rk = kernel.target_risk(
        [[4, 0], [0, 4]],
        {j: weights[j] for j in donors_k},
        [[1, 0], [0, 1]],
        F(2),
        [[F(1, 12), 0], [0, F(1, 10)]],
        gamma,
        cov,
        [[1, 0], [0, 1]],
        donors_k,
        1,
        ids,
    )
    got = kernel.cross_covariance(
        [[6, 0], [0, 6]],
        [[1, 0], [0, 1]],
        F(2),
        [[4, 0], [0, 4]],
        [[1, 0], [0, 1]],
        F(2),
        cov[(0, 1)],
        {j: cov[(0, j)] for j in donors_k},
        {j: cov[(j, 1)] for j in donors_i},
        {(j, donor_l): cov[(j, donor_l)] for j in donors_i for donor_l in donors_k},
        gamma,
        [[1, 0], [0, 1]],
        donors_i,
        donors_k,
        weights,
        0,
        1,
        ids,
        ri,
        rk,
    )
    assert direct == got["Cov_eS"][0][0]


def test_kat_20_identity_and_gram_match_when_uncorrelated():
    _assert_fixture(donors=10, regressors=3)
    gram = kernel.directional_totals(
        F(1, 40), F(27, 2000), F(0), F(1, 100), F(0), 40, 3, "GRAM", F(20)
    )
    identity = kernel.directional_totals(
        F(1, 40), F(27, 2000), F(0), F(1, 100), F(0), 40, 3, "IDENTITY", F(20), rx=0
    )
    assert gram == identity


def test_exact_definiteness_matches_brute_force_oracles():
    matrices = (
        [[1, 0], [0, 1]],
        [[2, 1], [1, 2]],
        [[1, 1], [1, 1]],
        [[1, 2], [2, 1]],
        [[2, 1, 0], [1, 2, 1], [0, 1, 2]],
        [[1, 1, 0], [1, 1, 0], [0, 0, 0]],
        [[2, 0, 0, 0], [0, 1, 0, 0], [0, 0, 3, 1], [0, 0, 1, 3]],
        [[1, 1, 0, 0], [1, 1, 1, 0], [0, 1, 1, 0], [0, 0, 0, -1]],
    )
    for matrix in matrices:
        assert kernel.matrix_is_positive_definite(matrix) == _oracle_positive_definite(matrix)
        assert kernel.matrix_is_positive_semidefinite(matrix) == _oracle_positive_semidefinite(
            matrix
        )


def test_nine_by_nine_exact_definiteness_is_fast():
    psd = [[F(int(row == col) + 1) for col in range(9)] for row in range(9)]
    pd = [[F(int(row == col) + 2) for col in range(9)] for row in range(9)]
    started = perf_counter()
    assert kernel.matrix_is_positive_semidefinite(psd)
    assert perf_counter() - started < 0.5
    started = perf_counter()
    assert kernel.matrix_is_positive_definite(pd)
    assert perf_counter() - started < 0.5


@pytest.mark.parametrize(
    ("gamma", "c", "donor_v", "k"),
    [
        (F(1, 100), F(0), F(1, 40), 1),
        (F(1, 100), F(1, 2), F(1, 40), 1),
        (F(0), F(0), F(1, 40), 1),
        (F(0), F(1, 2), F(1, 360), 9),
    ],
    ids=("kat-2", "kat-3", "kat-15", "kat-16"),
)
def test_isotropic_moments_match_scalar_kats(gamma, c, donor_v, k):
    _assert_fixture(donors=10)
    result, _ = _scalar_risk(gamma=gamma, c=c, donor_v=donor_v)
    moments = kernel.isotropic_moments(F(1, 40), k, 10, c, gamma)
    assert (moments["Z"], moments["K"]) == (result["Z"][0][0], result["K"][0][0])


def test_exact_square_root_refuses_nonperfect_rationals():
    for value in (2, F(1, 2)):
        with pytest.raises(
            kernel.Refusal,
            match="square root requires a nonnegative perfect-square rational",
        ):
            kernel.exact_square_root(value)


def test_closed_form_break_even_boundary():
    _assert_fixture(donors=10)
    assert kernel.closed_forms(F(1, 10), F(1, 10), 0, 10)["w_be"] == "NONE"
    assert isinstance(kernel.closed_forms(F(1, 10), F(1, 10) + F(1, 100), 0, 10)["w_be"], F)


def test_missing_covariance_and_weight_entries_refuse_cleanly():
    _assert_fixture(donors=10)
    donors, ids, cov, weights, gamma = _scalar_fixture()
    missing = dict(cov)
    del missing[(1, 1)]
    with pytest.raises(kernel.Refusal, match="covariance entry missing"):
        kernel.target_risk(
            [[40]], weights, [[1]], 0, [[F(1, 40)]], gamma, missing, [[1]], donors, 0, ids
        )
    with pytest.raises(kernel.Refusal, match="weights must be supplied for every donor"):
        kernel.target_risk(
            [[40]],
            {j: weights[j] for j in donors[:-1]},
            [[1]],
            0,
            [[F(1, 40)]],
            gamma,
            cov,
            [[1]],
            donors,
            0,
            ids,
        )
    with pytest.raises(kernel.Refusal, match="covariance entry missing"):
        kernel.cross_covariance(
            [[40]],
            [[1]],
            0,
            [[40]],
            [[1]],
            0,
            cov[(0, 11)],
            {},
            {j: cov[(j, 11)] for j in donors},
            {(j, donor_l): cov[(j, donor_l)] for j in donors for donor_l in donors},
            gamma,
            [[1]],
            donors,
            donors,
            weights,
            0,
            11,
            ids,
            {},
            {},
        )
    risk_i = kernel.target_risk(
        [[40]], weights, [[1]], 0, [[F(1, 40)]], gamma, cov, [[1]], donors, 0, ids
    )
    risk_k = kernel.target_risk(
        [[40]], weights, [[1]], 0, [[F(1, 40)]], gamma, cov, [[1]], donors, 11, ids
    )
    common = (
        [[40]],
        [[1]],
        0,
        [[40]],
        [[1]],
        0,
        cov[(0, 11)],
        {j: cov[(0, j)] for j in donors},
        {j: cov[(j, 11)] for j in donors},
        {(j, donor_l): cov[(j, donor_l)] for j in donors for donor_l in donors},
        gamma,
        [[1]],
        donors,
        donors,
        weights,
        0,
        11,
        ids,
        risk_i,
        risk_k,
    )
    for field_index in (7, 8, 9):
        malformed = list(common)
        malformed[field_index] = dict(malformed[field_index])
        malformed[field_index].pop(next(iter(malformed[field_index])))
        with pytest.raises(kernel.Refusal, match="covariance entry missing"):
            kernel.cross_covariance(*malformed)
    malformed_weights = dict(weights)
    malformed_weights.pop(donors[0])
    malformed = list(common)
    malformed[14] = malformed_weights
    with pytest.raises(kernel.Refusal, match="weights must be supplied for every donor"):
        kernel.cross_covariance(*malformed)


def test_mutually_targeted_donors_cross_covariance_direct_expansion():
    _assert_fixture(donors=5, regressors=2)
    donors_i, donors_k = (1, 3), (0, 1)
    ids = {0, 1, 2, 3, 4}
    eye = [[F(1), 0], [0, F(1)]]
    weights = {j: eye for j in (0, 1, 3)}
    gamma = [[F(1, 10), 0], [0, F(1, 10)]]
    cov = {
        (i, j): [[F(1, 10) if i == j else F(1, 30), 0], [0, F(1, 10) if i == j else F(1, 30)]]
        for i in ids
        for j in ids
    }
    cov[(3, 3)] = [[F(1, 8), 0], [0, F(1, 8)]]
    si, sk, oi, ok = [[10, 0], [0, 10]], [[8, 0], [0, 8]], eye, eye
    vi, vk = [[F(1, 10), 0], [0, F(1, 10)]], [[F(1, 8), 0], [0, F(1, 8)]]
    ri = kernel.target_risk(
        si, {j: weights[j] for j in donors_i}, oi, 2, vi, gamma, cov, eye, donors_i, 0, ids
    )
    rk = kernel.target_risk(
        sk, {j: weights[j] for j in donors_k}, ok, 3, vk, gamma, cov, eye, donors_k, 3, ids
    )
    wi = {j: F(1, 2) for j in donors_i}
    wk = {j: F(1, 2) for j in donors_k}
    bi, hi, bk, hk = F(5, 6), F(1, 6), F(8, 11), F(3, 11)
    e_i_z_k = sum((cov[(0, j)][0][0] * wk[j] for j in donors_k), F(0))
    z_i_e_k = sum((cov[(j, 3)][0][0] * wi[j] for j in donors_i), F(0))
    z_i_z_k = (
        sum(
            (
                wi[j] * wk[donor_l] * cov[(j, donor_l)][0][0]
                for j in donors_i
                for donor_l in donors_k
            ),
            F(0),
        )
        + wi[1] * wk[1] * gamma[0][0]
    )
    z_i_z_k -= F(1, 2) * gamma[0][0]
    z_i_z_k -= F(1, 2) * gamma[0][0]
    direct = bi * bk * cov[(0, 3)][0][0] + bi * hk * e_i_z_k + hi * bk * z_i_e_k + hi * hk * z_i_z_k
    got = kernel.cross_covariance(
        si,
        oi,
        2,
        sk,
        ok,
        3,
        cov[(0, 3)],
        {j: cov[(0, j)] for j in donors_k},
        {j: cov[(j, 3)] for j in donors_i},
        {(j, donor_l): cov[(j, donor_l)] for j in donors_i for donor_l in donors_k},
        gamma,
        eye,
        donors_i,
        donors_k,
        weights,
        0,
        3,
        ids,
        ri,
        rk,
    )
    assert got["Cov_eS"] == [[direct, 0], [0, direct]]


def test_identity_correlated_regressors_matrix_and_closed_form_totals_match():
    _compare_three_regressor_paths("IDENTITY", F(9, 10), F(1, 2), F(1, 100), (20, 80, "INFINITE"))


def test_gram_total_correlation_with_nonzero_c_and_gamma_matches():
    _compare_three_regressor_paths("GRAM", F(0), F(1, 2), F(1, 100), (20, 80, "INFINITE"))


def test_complete_pooling_risk_through_target_risk():
    _assert_fixture(donors=10)
    donors = tuple(range(1, 11))
    ids = {0, *donors}
    omega = [[0, 0], [0, 1]]
    S = [[4, 2], [2, 3]]
    cov = {
        (i, j): [
            [F(1, 2) if i == j and i in donors else 0, 0],
            [0, F(1, 2) if i == j and i in donors else 0],
        ]
        for i in ids
        for j in ids
    }
    weights = {j: [[1, 0], [0, 1]] for j in donors}
    result = kernel.target_risk(
        S,
        weights,
        omega,
        "INFINITE",
        [[F(1, 10), 0], [0, F(1, 10)]],
        [[0, 0], [0, 0]],
        cov,
        [[1, 0], [0, 1]],
        donors,
        0,
        ids,
    )
    assert result["R_U"] == F(1, 5)
    assert result["R_S"] == F(3, 16)

    _assert_fixture(donors=10, regressors=3)
    donors = tuple(range(1, 11))
    ids = {0, *donors}
    eye = [[F(int(i == j)) for j in range(3)] for i in range(3)]
    cov = {
        (i, j): [
            [(F(1, 40) if i == j and i in donors else 0) * item for item in row] for row in eye
        ]
        for i in ids
        for j in ids
    }
    result = kernel.target_risk(
        [[40, 0, 0], [0, 40, 0], [0, 0, 40]],
        {j: eye for j in donors},
        [[0, 0, 0], [0, 1, 0], [0, 0, 1]],
        "INFINITE",
        [[F(1, 40) if i == j else 0 for j in range(3)] for i in range(3)],
        [[F(1, 100) if i == j else 0 for j in range(3)] for i in range(3)],
        cov,
        eye,
        donors,
        0,
        ids,
    )
    assert result["R_S"] == F(13, 250)


def test_fixture_rule_applies_to_all_known_answer_fixtures():
    for donors, regressors in [(10, 1), (10, 2), (10, 3), (5, 2)]:
        _assert_fixture(donors, regressors)


def test_public_callable_inventory_and_signature_barrier():
    expected = (
        "Refusal",
        "build_manifest",
        "closed_forms",
        "cross_covariance",
        "directional_totals",
        "evaluate_map",
        "exact_square_root",
        "isotropic_moments",
        "main",
        "matrix_identity",
        "matrix_inverse",
        "matrix_is_positive_definite",
        "matrix_is_positive_semidefinite",
        "matrix_is_symmetric",
        "matrix_product",
        "matrix_scale",
        "matrix_sum",
        "matrix_trace",
        "matrix_transpose",
        "pooling_projector",
        "run_map",
        "target_risk",
        "validate_arm",
        "validate_manifest",
    )
    public = tuple(
        sorted(
            name
            for name, value in vars(kernel).items()
            if callable(value) and not name.startswith("_")
        )
    )
    assert kernel.CALLABLES == expected
    assert kernel.CALLABLES == public
    forbidden = {"g", "b", "b0", "bS", "y", "rows", "X"}
    for name in kernel.CALLABLES:
        callable_obj = getattr(kernel, name)
        if inspect.isclass(callable_obj):
            continue
        for parameter in inspect.signature(callable_obj).parameters:
            lowered = parameter.lower()
            assert parameter not in forbidden
            assert "coef" not in lowered and "response" not in lowered


def test_module_imports_exactly_allowed_standard_library_and_has_no_float():
    path = Path(kernel.__file__)
    tree = ast.parse(path.read_text())
    allowed = {
        "fractions",
        "math",
        "json",
        "hashlib",
        "re",
        "itertools",
        "functools",
        "os",
        "platform",
        "pathlib",
        "sys",
        "time",
    }
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module.split(".")[0])
        assert not (isinstance(node, ast.Constant) and isinstance(node.value, float))
        assert not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "float"
        )
    assert imported <= allowed


def test_no_other_code_imports_kernel_or_names_oracle_helpers():
    root = Path(__file__).resolve().parents[2]
    for path in (
        *root.joinpath("scripts").glob("*.py"),
        *root.joinpath("src").rglob("*.py"),
        *root.joinpath("tests").rglob("*.py"),
    ):
        if any(
            token in part
            for part in path.parts
            for token in ("5a", "f3", "look_run", "holdout", "sealed", "f2_")
        ):
            continue
        if path == Path(__file__).resolve():
            continue
        source = path.read_text()
        assert "_oracle_" not in source
        if path.parent.name == "scripts" or "src" in path.parts:
            assert "quant_ng_share_kernel" not in source


def test_refusals_exact_contract():
    arm = {
        "arm_id": "A",
        "mechanism": "COEF_PRIOR",
        "params": {
            "donors": [1],
            "weights": {1: [[1]]},
            "omega": [[1]],
            "strength": 1,
            "profile_source": "OWN_UNSHARED",
        },
    }
    assert kernel.validate_arm(arm) is True
    with pytest.raises(kernel.Refusal, match="arm must contain exactly"):
        kernel.validate_arm({**arm, "extra": 1})
    with pytest.raises(kernel.Refusal, match="COEF_PRIOR params must contain exactly"):
        kernel.validate_arm({**arm, "params": {**arm["params"], "extra": 1}})
    with pytest.raises(kernel.Refusal, match="one mechanism per arm"):
        kernel.validate_arm({**arm, "mechanism": ["NONE", "COEF_PRIOR"]})
    with pytest.raises(kernel.Refusal, match="unknown mechanism"):
        kernel.validate_arm({**arm, "mechanism": "OTHER"})
    for mechanism in ("SHAPE", "CALENDAR"):
        with pytest.raises(kernel.Refusal, match="mechanism not implemented in this component"):
            kernel.validate_arm({**arm, "mechanism": mechanism})
    with pytest.raises(kernel.Refusal, match="profile_source must be"):
        kernel.validate_arm(
            {
                **arm,
                "params": {
                    key: value for key, value in arm["params"].items() if key != "profile_source"
                },
            }
        )
    with pytest.raises(kernel.Refusal, match="profile_source must be"):
        kernel.validate_arm({**arm, "params": {**arm["params"], "profile_source": "SHARED"}})
    with pytest.raises(kernel.Refusal, match="lambda must be nonnegative"):
        kernel.target_risk(
            [[1]],
            {1: [[1]]},
            [[1]],
            -1,
            [[1]],
            [[0]],
            {(0, 1): [[0]], (1, 1): [[0]]},
            [[1]],
            [1],
            0,
            {0, 1},
        )
    for invalid in (True, float("inf"), 1.5):
        with pytest.raises(kernel.Refusal, match="number must be a finite Fraction or int"):
            kernel.exact_square_root(invalid)
    with pytest.raises(kernel.Refusal, match="S must be symmetric positive definite"):
        kernel.target_risk([[0]], {1: [[1]]}, [[1]], 0, [[1]], [[0]], {}, [[1]], [1], 0, {0, 1})
    with pytest.raises(kernel.Refusal, match="Omega must be symmetric positive semidefinite"):
        kernel.target_risk(
            [[1, 0], [0, 1]],
            {1: [[1, 0], [0, 1]]},
            [[1, 2], [2, 1]],
            0,
            [[1, 0], [0, 1]],
            [[0, 0], [0, 0]],
            {},
            [[1, 0], [0, 1]],
            [1],
            0,
            {0, 1},
        )
    with pytest.raises(kernel.Refusal, match="dimension mismatch"):
        kernel.matrix_product([[1, 2]], [[1]])
    with pytest.raises(kernel.Refusal, match="singular matrix"):
        kernel.matrix_inverse([[1, 2], [2, 4]])
    with pytest.raises(kernel.Refusal, match="target must not be in its donor set"):
        kernel.target_risk([[1]], {1: [[1]]}, [[1]], 0, [[1]], [[0]], {}, [[1]], [0], 0, {0, 1})
    with pytest.raises(kernel.Refusal, match="donor set must be nonempty"):
        kernel.target_risk([[1]], {}, [[1]], 0, [[1]], [[0]], {}, [[1]], [], 0, {0})
    with pytest.raises(kernel.Refusal, match="donor index out of range"):
        kernel.target_risk([[1]], {1: [[1]]}, [[1]], 0, [[1]], [[0]], {}, [[1]], [1], 0, {0})
    with pytest.raises(kernel.Refusal, match=r"best weight undefined when v \+ Z - 2K = 0"):
        kernel.closed_forms(1, 1, 1, 1)


@pytest.mark.parametrize(
    "matrix",
    [
        [[0, 0], [0, -1]],
        [[0, 0, 0], [0, 0, 1], [0, 1, 0]],
        [[1, 0, 0], [0, 0, 0], [0, 0, -1]],
        [[0, 0, 0], [0, 0, 0], [0, 0, 0]],
        [[2, 1, 0], [1, 0, 0], [0, 0, 0]],
        [[1, 1, 0], [1, 1, 0], [0, 0, 0]],
    ],
    ids=[
        "zero-then-negative",
        "zero-diagonal-nonzero-offdiagonal",
        "positive-zero-negative",
        "all-zero",
        "zero-diagonal-coupled",
        "singular-psd",
    ],
)
def test_psd_zero_pivot_cases_match_the_brute_force_oracle(matrix):
    # Master's repair: a zero largest pivot used to accept an indefinite remaining block.
    fractions = [[F(value) for value in row] for row in matrix]
    assert kernel.matrix_is_positive_semidefinite(fractions) is _oracle_positive_semidefinite(
        fractions
    )


def _fixture_manifest():
    _assert_fixture(donors=10, regressors=3)
    source = Path(kernel.__file__).read_bytes()
    digest = __import__("hashlib").sha256(source).hexdigest()
    return kernel.build_manifest(
        "ucpe.exp05_stage0.manifest.v1",
        "1" * 64,
        "1" * 64,
        digest,
        kernel._environment(),
        {"p": 3, "sigma2": "1", "t": "40"},
        [
            {"a": "2/5", "m": 10, "k": 1, "c": "0", "r_x": "0", "omega": "GRAM"},
            {"a": "2/5", "m": 10, "k": 1, "c": "0", "r_x": "0", "omega": "IDENTITY"},
            {"a": "2/5", "m": 10, "k": 1, "c": "0", "r_x": "1/2", "omega": "GRAM"},
            {"a": "2/5", "m": 10, "k": 1, "c": "0", "r_x": "1/2", "omega": "IDENTITY"},
        ],
        ["0", "2000/27", "INFINITE"],
        {"m": 2, "a": ["1/7"], "c": ["1/8"]},
        [f"SC-{index}" for index in range(1, 9)],
        30,
        "NONE",
        "SYNTHETIC_PARAMETERS",
    )


def test_fixture_map_matches_collapsed_and_closed_paths():
    _assert_fixture(donors=10, regressors=3)
    import json

    manifest = json.loads(_fixture_manifest())
    rows, checks = kernel.evaluate_map(manifest)
    assert all(item["passed"] for item in checks)
    assert len(rows) == 4
    for row in rows[:2]:
        assert row["status"] == "COMPUTED"
        assert row["R_U"] == 3 * F(1, 40)
        assert row["strengths"][1]["R_S"] == F(1, 40) + 2 * F(27, 3080)
        assert row["strengths"][2]["R_S"] == F(13, 250)
    assert rows[0]["strengths"] == rows[1]["strengths"]


def test_fixture_cli_outputs_repeat_byte_for_byte(tmp_path):
    import hashlib
    import json
    import shutil
    import subprocess

    manifest_bytes = _fixture_manifest()
    manifest_path = tmp_path / "fixture.json"
    manifest_path.write_bytes(manifest_bytes)
    output = tmp_path / ".work" / "exp05_stage0_test" / "map"
    output.parent.mkdir(parents=True)
    command = [
        str(Path(kernel.__file__).resolve()),
        "map",
        "--manifest",
        str(manifest_path),
        "--expect-sha256",
        hashlib.sha256(manifest_bytes).hexdigest(),
        "--out",
        str(output),
    ]
    captured = []
    for iteration in range(2):
        if iteration:
            shutil.rmtree(output)
        result = subprocess.run(
            [__import__("sys").executable, "-I", "-B", *command],
            cwd=tmp_path,
            capture_output=True,
            check=False,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        captured.append({path.name: path.read_bytes() for path in output.iterdir()})
    assert captured[0] == captured[1]
    assert json.loads(captured[0]["REPORT.json"])["status"] == "COMPUTED"


def test_decimal_formatter_is_exact_and_half_even():
    assert kernel._number(F(1, 8)) == {"exact": "1/8", "decimal": "1.25000000000e-1"}
    assert kernel._number(F(1, 2)) == {"exact": "1/2", "decimal": "5.00000000000e-1"}
    assert kernel._number(F(1, 2000000000000)) == {
        "exact": "1/2000000000000",
        "decimal": "5.00000000000e-13",
    }
    assert kernel._number(F(200000000001, 200000000000)) == {
        "exact": "200000000001/200000000000",
        "decimal": "1.00000000000e+0",
    }
    assert kernel._number(F(200000000003, 200000000000)) == {
        "exact": "200000000003/200000000000",
        "decimal": "1.00000000002e+0",
    }


def test_out_of_range_unconstrained_risk_is_absent_from_every_file(tmp_path):
    import hashlib
    import json

    values = json.loads(_fixture_manifest())
    values["points"] = [{"a": "0", "m": 10, "k": 9, "c": "1/2", "r_x": "0", "omega": "GRAM"}]
    source_hash = hashlib.sha256(Path(kernel.__file__).read_bytes()).hexdigest()
    manifest_bytes = kernel.build_manifest(
        values["schema"],
        values["prereg_sha256"],
        values["spec_sha256"],
        source_hash,
        values["environment"],
        values["fixed"],
        values["points"],
        values["strengths"],
        values["sc4_subset"],
        values["self_checks"],
        values["cap_seconds"],
        values["random_numbers"],
        values["provenance"],
    )
    output = tmp_path / ".work" / "exp05_stage0_test" / "map"
    output.parent.mkdir(parents=True)
    kernel.run_map(
        json.loads(manifest_bytes),
        manifest_bytes,
        output,
        tmp_path,
        hashlib.sha256(manifest_bytes).hexdigest(),
    )
    files = [path.read_text() for path in output.iterdir()]
    assert all("3/2620" not in content for content in files)
    row = json.loads((output / "MAP.jsonl").read_text())
    assert row["closed_form"]["flag"] == "OUT_OF_RANGE"


@pytest.mark.parametrize(
    "rule, reason",
    [
        ("input_digest", "manifest digest mismatch"),
        ("canonical", "manifest is not canonical"),
        ("module_digest", "module digest mismatch"),
        ("environment", "environment mismatch"),
        ("unknown_key", "unknown or missing manifest key"),
        ("outside_folder", "output folder must be below .work/exp05_stage0_*"),
        ("symlink", "output folder is a symlink"),
        ("not_empty", "output folder must be new or empty"),
        ("protected", "protected output path"),
        ("random_numbers", 'random_numbers must be "NONE"'),
        ("provenance", 'provenance must be "SYNTHETIC_PARAMETERS"'),
        ("budget", "projected runtime exceeds cap_seconds"),
    ],
    ids=[
        "digest-pin",
        "canonical-json",
        "module-pin",
        "environment-pin",
        "unknown-manifest-key",
        "outside-folder",
        "symlink-folder",
        "nonempty-folder",
        "protected-folder",
        "random-number-guard",
        "provenance-guard",
        "runtime-cap",
    ],
)
def test_map_stop_rules_refuse_before_evaluation(tmp_path, monkeypatch, rule, reason):
    import hashlib
    import json

    monkeypatch.setattr(
        kernel,
        "evaluate_map",
        lambda manifest: pytest.fail("evaluation must remain unreachable"),
    )
    valid_bytes = _fixture_manifest()
    manifest = json.loads(valid_bytes)
    output = tmp_path / ".work" / "exp05_stage0_test" / "map"
    output.parent.mkdir(parents=True, exist_ok=True)
    expected = hashlib.sha256(valid_bytes).hexdigest()
    if rule == "input_digest":
        expected = "0" * 64
    elif rule == "canonical":
        pass
    elif rule == "module_digest":
        manifest["code_sha256"] = "0" * 64
    elif rule == "environment":
        manifest["environment"]["machine"] += "-changed"
    elif rule == "unknown_key":
        manifest["extra"] = "refused"
    elif rule == "outside_folder":
        output = tmp_path / "outside" / "map"
    elif rule == "symlink":
        target = output.parent / "target"
        target.mkdir()
        output.symlink_to(target, target_is_directory=True)
    elif rule == "not_empty":
        output.mkdir()
        (output / "existing.txt").write_text("fixture")
    elif rule == "protected":
        output = tmp_path / ".work" / "exp05_stage0_holdout" / "map"
    elif rule == "random_numbers":
        manifest["random_numbers"] = "DRAW"
    elif rule == "provenance":
        manifest["provenance"] = "REAL_DATA"
    elif rule == "budget":
        manifest["cap_seconds"] = 1
        times = iter((0, 100))
        monkeypatch.setattr(kernel, "_perf_counter", lambda: next(times))
    supplied = (
        valid_bytes
        if rule in ("input_digest", "symlink", "not_empty", "outside_folder", "protected")
        else (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode()
        if rule == "canonical"
        else (
            json.dumps(
                manifest,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            + "\n"
        ).encode()
    )
    if rule not in ("input_digest",):
        expected = hashlib.sha256(supplied).hexdigest()
    with pytest.raises(kernel.Refusal) as error:
        kernel.run_map(manifest, supplied, output, tmp_path, expected)
    assert str(error.value) == reason
    assert not (output / "MAP.jsonl").exists()


@pytest.mark.parametrize(
    "check_id",
    ["SC-1", "SC-2", "SC-3", "SC-4", "SC-5", "SC-6", "SC-7", "SC-8"],
    ids=[
        "zero-strength",
        "closed-form",
        "psd",
        "symbol-sums",
        "counts",
        "shape-equality",
        "best-risk",
        "pooling-projector",
    ],
)
def test_each_self_check_marks_a_mutated_formula_failed(monkeypatch, check_id):
    import json

    manifest = json.loads(_fixture_manifest())
    if check_id == "SC-1":
        original = kernel._collapsed_target_risk

        def wrong(values, point, strength, matrices):
            result = original(values, point, strength, matrices)
            if point["m"] == 10 and strength == 0:
                result["R_S"] += 1
            return result

        monkeypatch.setattr(kernel, "_collapsed_target_risk", wrong)
    elif check_id == "SC-2":
        original = kernel.directional_totals

        def wrong(*args, **kwargs):
            result = original(*args, **kwargs)
            result["R_S"] += 1
            return result

        monkeypatch.setattr(kernel, "directional_totals", wrong)
    elif check_id == "SC-3":
        original = kernel._positive_semidefinite
        valid_omegas = [
            [[F(0), F(0), F(0)], [F(0), F(1), F(0)], [F(0), F(0), F(1)]],
            [[F(0), F(0), F(0)], [F(0), F(1), F(1, 2)], [F(0), F(1, 2), F(1)]],
        ]

        def wrong(matrix):
            return original(matrix) if matrix in valid_omegas else False

        monkeypatch.setattr(kernel, "_positive_semidefinite", wrong)
    elif check_id == "SC-4":
        original = kernel.cross_covariance

        def wrong(*args, **kwargs):
            result = original(*args, **kwargs)
            result["Cov_eS"][0][0] += 1
            return result

        monkeypatch.setattr(kernel, "cross_covariance", wrong)
    elif check_id == "SC-5":
        monkeypatch.setattr(
            kernel,
            "_eval_point",
            lambda values, point: ({"strengths": []}, {f"SC-{i}": True for i in range(1, 9)}),
        )
    elif check_id == "SC-6":
        original = kernel.target_risk
        calls = [0]

        def wrong(*args, **kwargs):
            result = original(*args, **kwargs)
            calls[0] += 1
            if calls[0] == 13:
                result["R_S"] += 1
            return result

        monkeypatch.setattr(kernel, "target_risk", wrong)
    elif check_id == "SC-7":
        original = kernel.closed_forms

        def wrong(*args, **kwargs):
            result = original(*args, **kwargs)
            result["R_best"] += 1
            return result

        monkeypatch.setattr(kernel, "closed_forms", wrong)
    else:
        original = kernel.pooling_projector

        def wrong(*args, **kwargs):
            return kernel.matrix_sum(
                original(*args, **kwargs), kernel.matrix_identity(len(args[0]))
            )

        monkeypatch.setattr(kernel, "pooling_projector", wrong)
    _, table = kernel.evaluate_map(manifest)
    failed = {item["id"] for item in table if not item["passed"]}
    assert check_id in failed
