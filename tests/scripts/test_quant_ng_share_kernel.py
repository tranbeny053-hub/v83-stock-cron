from __future__ import annotations

import ast
import inspect
from fractions import Fraction as F
from pathlib import Path

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


def test_fixture_rule_applies_to_all_known_answer_fixtures():
    for donors, regressors in [(10, 1), (10, 2), (10, 3), (5, 2)]:
        _assert_fixture(donors, regressors)


def test_public_callable_inventory_and_signature_barrier():
    public = tuple(
        sorted(
            name
            for name, value in vars(kernel).items()
            if callable(value) and not name.startswith("_")
        )
    )
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
    allowed = {"fractions", "math", "json", "hashlib", "re", "itertools", "functools"}
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
