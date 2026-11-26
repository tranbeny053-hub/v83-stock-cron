"""Exact synthetic coefficient-prior risk calculations; this module never estimates coefficients."""

from fractions import Fraction as _Fraction
from math import isqrt as _isqrt


class Refusal(ValueError):
    """Raised when a request violates this component's closed contract."""


_MECHANISMS = ("NONE", "COEF_PRIOR", "SHAPE", "CALENDAR")
_PARAMS = {"donors", "weights", "omega", "strength", "profile_source"}


def _fraction(value):
    if isinstance(value, bool) or not isinstance(value, (int, _Fraction)):
        raise Refusal("number must be a finite Fraction or int (booleans are refused)")
    return _Fraction(value)


def _matrix(matrix):
    if not isinstance(matrix, (list, tuple)) or not matrix:
        raise Refusal("dimension mismatch")
    result = [list(row) for row in matrix]
    if (
        any(not isinstance(row, (list, tuple)) for row in matrix)
        or not result[0]
        or any(len(row) != len(result[0]) for row in result)
    ):
        raise Refusal("dimension mismatch")
    return [[_fraction(value) for value in row] for row in result]


def _same_shape(left, right):
    if not left or not right or len(left[0]) != len(right):
        raise Refusal("dimension mismatch")


def _zero(rows, cols):
    return [[_Fraction(0) for _ in range(cols)] for _ in range(rows)]


def _add(left, right):
    _same_shape(left, right)
    if len(left) != len(right) or len(left[0]) != len(right[0]):
        raise Refusal("dimension mismatch")
    return [[a + b for a, b in zip(x, y, strict=True)] for x, y in zip(left, right, strict=True)]


def _scale(factor, matrix):
    factor = _fraction(factor)
    return [[factor * value for value in row] for row in matrix]


def _sub(left, right):
    return _add(left, _scale(-1, right))


def _transpose(matrix):
    return [list(row) for row in zip(*matrix, strict=True)]


def _product(left, right):
    _same_shape(left, right)
    return [
        [
            sum((a * b for a, b in zip(row, col, strict=True)), _Fraction(0))
            for col in _transpose(right)
        ]
        for row in left
    ]


def _identity(size):
    return [[_Fraction(int(i == j)) for j in range(size)] for i in range(size)]


def _trace(matrix):
    if len(matrix) != len(matrix[0]):
        raise Refusal("dimension mismatch")
    return sum((matrix[i][i] for i in range(len(matrix))), _Fraction(0))


def _inverse(matrix):
    size = len(matrix)
    if len(matrix[0]) != size:
        raise Refusal("dimension mismatch")
    augmented = [row[:] + ident for row, ident in zip(matrix, _identity(size), strict=True)]
    for col in range(size):
        pivot = next((row for row in range(col, size) if augmented[row][col]), None)
        if pivot is None:
            raise Refusal("singular matrix")
        augmented[col], augmented[pivot] = augmented[pivot], augmented[col]
        value = augmented[col][col]
        augmented[col] = [item / value for item in augmented[col]]
        for row in range(size):
            if row != col:
                factor = augmented[row][col]
                augmented[row] = [
                    a - factor * b for a, b in zip(augmented[row], augmented[col], strict=True)
                ]
    return [row[size:] for row in augmented]


def _symmetric(matrix):
    return matrix == _transpose(matrix)


def _leading_determinants(matrix):
    determinants = []
    for size in range(1, len(matrix) + 1):
        sub = [row[:size] for row in matrix[:size]]
        determinants.append(_determinant(sub))
    return determinants


def _determinant(matrix):
    work = [row[:] for row in matrix]
    determinant = _Fraction(1)
    for col in range(len(work)):
        pivot = next((row for row in range(col, len(work)) if work[row][col]), None)
        if pivot is None:
            return _Fraction(0)
        if pivot != col:
            work[col], work[pivot] = work[pivot], work[col]
            determinant = -determinant
        value = work[col][col]
        determinant *= value
        for row in range(col + 1, len(work)):
            factor = work[row][col] / value
            for item in range(col + 1, len(work)):
                work[row][item] -= factor * work[col][item]
    return determinant


def _positive_definite(matrix):
    if len(matrix) != len(matrix[0]) or not _symmetric(matrix):
        return False
    work = [row[:] for row in matrix]
    for pivot in range(len(work)):
        value = work[pivot][pivot]
        if value <= 0:
            return False
        for row in range(pivot + 1, len(work)):
            for col in range(row, len(work)):
                updated = work[row][col] - work[row][pivot] * work[pivot][col] / value
                work[row][col] = updated
                work[col][row] = updated
    return True


def _positive_semidefinite(matrix):
    if len(matrix) != len(matrix[0]) or not _symmetric(matrix):
        return False
    work = [row[:] for row in matrix]
    size = len(work)
    for pivot in range(size):
        largest = max(range(pivot, size), key=lambda index: work[index][index])
        if largest != pivot:
            work[pivot], work[largest] = work[largest], work[pivot]
            for row in work:
                row[pivot], row[largest] = row[largest], row[pivot]
        value = work[pivot][pivot]
        if value < 0:
            return False
        if value == 0:
            # The largest remaining diagonal is 0, so every remaining diagonal is <= 0. PSD then
            # needs the whole remaining block to be 0: a negative diagonal or a nonzero entry fails.
            return all(
                work[row][col] == 0 for row in range(pivot, size) for col in range(pivot, size)
            )
        for row in range(pivot + 1, size):
            for col in range(row, size):
                updated = work[row][col] - work[row][pivot] * work[pivot][col] / value
                work[row][col] = updated
                work[col][row] = updated
    return True


def _covariance_entry(mapping, key):
    try:
        return mapping[key]
    except (KeyError, TypeError):
        raise Refusal("covariance entry missing") from None


def _weight_entries(mapping, donors):
    if not isinstance(mapping, dict) or set(mapping) != set(donors):
        raise Refusal("weights must be supplied for every donor")
    try:
        return {index: _matrix(mapping[index]) for index in donors}
    except KeyError:
        raise Refusal("weights must be supplied for every donor") from None


def _root(value):
    value = _fraction(value)
    if value < 0:
        raise Refusal("square root requires a nonnegative perfect-square rational")
    numerator = _isqrt(value.numerator)
    denominator = _isqrt(value.denominator)
    if numerator * numerator != value.numerator or denominator * denominator != value.denominator:
        raise Refusal("square root requires a nonnegative perfect-square rational")
    return _Fraction(numerator, denominator)


def _validate_design(S, Omega, strength):
    S = _matrix(S)
    Omega = _matrix(Omega)
    if len(S) != len(Omega) or len(S[0]) != len(Omega[0]):
        raise Refusal("dimension mismatch")
    if not _positive_definite(S):
        raise Refusal("S must be symmetric positive definite")
    if not _positive_semidefinite(Omega):
        raise Refusal("Omega must be symmetric positive semidefinite")
    if strength != "INFINITE":
        strength = _fraction(strength)
        if strength < 0:
            raise Refusal("lambda must be nonnegative")
    return S, Omega, strength


def validate_arm(arm):
    if not isinstance(arm, dict) or set(arm) != {"arm_id", "mechanism", "params"}:
        raise Refusal("arm must contain exactly arm_id, mechanism, params")
    if not isinstance(arm["arm_id"], str) or not arm["arm_id"]:
        raise Refusal("arm_id must be a nonempty string")
    mechanism, params = arm["mechanism"], arm["params"]
    if isinstance(mechanism, (list, tuple)):
        raise Refusal("one mechanism per arm")
    if mechanism not in _MECHANISMS:
        raise Refusal("unknown mechanism")
    if mechanism in ("SHAPE", "CALENDAR"):
        raise Refusal("mechanism not implemented in this component")
    if not isinstance(params, dict):
        raise Refusal("params must be an object")
    if mechanism == "NONE":
        if params:
            raise Refusal("NONE takes no params")
    else:
        if params.get("profile_source") != "OWN_UNSHARED":
            raise Refusal('profile_source must be "OWN_UNSHARED"')
        if set(params) != _PARAMS:
            raise Refusal(
                "COEF_PRIOR params must contain exactly donors, weights, omega, strength, "
                "profile_source"
            )
        if not isinstance(params["donors"], (list, tuple)) or not params["donors"]:
            raise Refusal("donor set must be nonempty")
        if any(
            isinstance(index, bool) or not isinstance(index, int) or index < 0
            for index in params["donors"]
        ):
            raise Refusal("donor index out of range")
        if len(set(params["donors"])) != len(params["donors"]):
            raise Refusal("donor set must not contain duplicates")
        if not isinstance(params["weights"], dict) or set(params["weights"]) != set(
            params["donors"]
        ):
            raise Refusal("weights must be supplied for every donor")
        omega = _matrix(params["omega"])
        if not _positive_semidefinite(omega):
            raise Refusal("Omega must be symmetric positive semidefinite")
        weight_matrices = [_matrix(params["weights"][index]) for index in params["donors"]]
        if any(
            len(matrix) != len(omega) or len(matrix[0]) != len(omega) for matrix in weight_matrices
        ):
            raise Refusal("dimension mismatch")
        _inverse(_sum_matrices(weight_matrices))
        if params["strength"] != "INFINITE" and _fraction(params["strength"]) < 0:
            raise Refusal("lambda must be nonnegative")
    return True


def matrix_product(left, right):
    return _product(_matrix(left), _matrix(right))


def matrix_transpose(matrix):
    return _transpose(_matrix(matrix))


def matrix_sum(left, right):
    return _add(_matrix(left), _matrix(right))


def matrix_scale(factor, matrix):
    return _scale(factor, _matrix(matrix))


def matrix_identity(size):
    if isinstance(size, bool) or not isinstance(size, int) or size < 1:
        raise Refusal("dimension mismatch")
    return _identity(size)


def matrix_trace(matrix):
    return _trace(_matrix(matrix))


def matrix_inverse(matrix):
    return _inverse(_matrix(matrix))


def matrix_is_symmetric(matrix):
    return _symmetric(_matrix(matrix))


def matrix_is_positive_definite(matrix):
    return _positive_definite(_matrix(matrix))


def matrix_is_positive_semidefinite(matrix):
    return _positive_semidefinite(_matrix(matrix))


def pooling_projector(S, Omega):
    S = _matrix(S)
    Omega = _matrix(Omega)
    if len(S) != len(Omega) or not _positive_definite(S) or not _positive_semidefinite(Omega):
        raise Refusal("S must be SPD and Omega must be PSD with matching dimensions")
    reduced = [row[:] for row in Omega]
    pivots = []
    pivot_row = 0
    for col in range(len(Omega)):
        found = next((row for row in range(pivot_row, len(Omega)) if reduced[row][col]), None)
        if found is None:
            continue
        reduced[pivot_row], reduced[found] = reduced[found], reduced[pivot_row]
        pivot = reduced[pivot_row][col]
        reduced[pivot_row] = [value / pivot for value in reduced[pivot_row]]
        for row in range(len(Omega)):
            if row != pivot_row:
                factor = reduced[row][col]
                reduced[row] = [
                    a - factor * b for a, b in zip(reduced[row], reduced[pivot_row], strict=True)
                ]
        pivots.append(col)
        pivot_row += 1
    free = [col for col in range(len(Omega)) if col not in pivots]
    if not free:
        return _zero(len(S), len(S))
    basis = _zero(len(S), len(free))
    for target_col, source_col in enumerate(free):
        basis[source_col][target_col] = 1
        for row, pivot_col in enumerate(pivots):
            basis[pivot_col][target_col] = -reduced[row][source_col]
    projected = _product(
        _product(basis, _inverse(_product(_product(_transpose(basis), S), basis))),
        _product(_transpose(basis), S),
    )
    return projected


def exact_square_root(value):
    return _root(value)


def isotropic_moments(v, k, m, c, gamma):
    v, c, gamma = map(_fraction, (v, c, gamma))
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in (k, m)):
        raise Refusal("k and m must be positive integers")
    v_direction = v / k
    z = (v_direction * (1 + (m - 1) * c) + gamma) / m + gamma
    cross = c * v / _root(k)
    return {"Z": z, "K": cross}


def target_risk(S, weights, Omega, strength, V, Gamma, C, Q, donors, target, donor_ids):
    S, Omega, strength = _validate_design(S, Omega, strength)
    V, Gamma, Q = _matrix(V), _matrix(Gamma), _matrix(Q)
    size = len(S)
    if any(len(matrix) != size or len(matrix[0]) != size for matrix in (V, Gamma, Q)):
        raise Refusal("dimension mismatch")
    donors = tuple(donors)
    if not donors:
        raise Refusal("donor set must be nonempty")
    if target in donors:
        raise Refusal("target must not be in its donor set")
    if any(index not in donor_ids for index in donors) or target not in donor_ids:
        raise Refusal("donor index out of range")
    W = _weight_entries(weights, donors)
    if any(len(matrix) != size or len(matrix[0]) != size for matrix in W.values()):
        raise Refusal("dimension mismatch")
    total_w = _zero(size, size)
    for matrix in W.values():
        total_w = _add(total_w, matrix)
    P = _inverse(total_w)
    z_cov = _zero(size, size)
    for j in donors:
        for k in donors:
            z_cov = _add(
                z_cov,
                _product(_product(W[j], _matrix(_covariance_entry(C, (j, k)))), _transpose(W[k])),
            )
        z_cov = _add(z_cov, _product(_product(W[j], Gamma), _transpose(W[j])))
    Z = _add(_product(_product(P, z_cov), _transpose(P)), Gamma)
    K = _zero(size, size)
    for j in donors:
        K = _add(
            K,
            _product(
                _product(_matrix(_covariance_entry(C, (target, j))), _transpose(W[j])),
                _transpose(P),
            ),
        )
    if strength == "INFINITE":
        B = pooling_projector(S, Omega)
        H = _sub(_identity(size), B)
    else:
        A = _inverse(_add(S, _scale(strength, Omega)))
        B = _product(A, S)
        H = _scale(strength, _product(A, Omega))
    mse = _add(
        _add(_product(_product(B, V), _transpose(B)), _product(_product(H, Z), _transpose(H))),
        _add(
            _product(_product(B, K), _transpose(H)),
            _product(_product(H, _transpose(K)), _transpose(B)),
        ),
    )
    risk_u = _trace(_product(Q, V))
    risk_s = _trace(_product(Q, mse))
    return {
        "Z": Z,
        "K": K,
        "B": B,
        "H": H,
        "MSE_S": mse,
        "R_U": risk_u,
        "R_S": risk_s,
        "gain": risk_u - risk_s,
        "relative_gain": (risk_u - risk_s) / risk_u,
    }


def cross_covariance(
    S_i,
    Omega_i,
    strength_i,
    S_k,
    Omega_k,
    strength_k,
    C_ik,
    C_i_dk,
    C_di_k,
    C_didk,
    Gamma,
    Q,
    donors_i,
    donors_k,
    weights,
    target_i,
    target_k,
    donor_ids,
    risk_i,
    risk_k,
):
    S_i, Omega_i, strength_i = _validate_design(S_i, Omega_i, strength_i)
    S_k, Omega_k, strength_k = _validate_design(S_k, Omega_k, strength_k)
    Gamma = _matrix(Gamma)
    if target_i in donors_i or target_k in donors_k:
        raise Refusal("target must not be in its donor set")
    if not donors_i or not donors_k:
        raise Refusal("donor set must be nonempty")
    if any(index not in donor_ids for index in set(donors_i) | set(donors_k)):
        raise Refusal("donor index out of range")
    W = _weight_entries(weights, set(donors_i) | set(donors_k))
    P_i = _inverse(_sum_matrices([W[j] for j in donors_i]))
    P_k = _inverse(_sum_matrices([W[j] for j in donors_k]))
    e_i_z_k = _product(
        _sum_matrices(
            [_product(_matrix(_covariance_entry(C_i_dk, j)), _transpose(W[j])) for j in donors_k]
        ),
        _transpose(P_k),
    )
    z_i_e_k = _product(
        P_i,
        _sum_matrices([_product(W[j], _matrix(_covariance_entry(C_di_k, j))) for j in donors_i]),
    )
    z_i_z_k = _zero(len(S_i), len(S_k))
    for j in donors_i:
        for donor_l in donors_k:
            z_i_z_k = _add(
                z_i_z_k,
                _product(
                    _product(W[j], _matrix(_covariance_entry(C_didk, (j, donor_l)))),
                    _transpose(W[donor_l]),
                ),
            )
        if j in donors_k:
            z_i_z_k = _add(z_i_z_k, _product(_product(W[j], Gamma), _transpose(W[j])))
    z_i_z_k = _product(_product(P_i, z_i_z_k), _transpose(P_k))
    if target_k in donors_i:
        z_i_z_k = _sub(z_i_z_k, _product(_product(P_i, W[target_k]), Gamma))
    if target_i in donors_k:
        z_i_z_k = _sub(z_i_z_k, _product(_product(Gamma, _transpose(W[target_i])), _transpose(P_k)))
    bi, hi = risk_i["B"], risk_i["H"]
    bk, hk = risk_k["B"], risk_k["H"]
    result = _add(
        _add(
            _product(_product(bi, _matrix(C_ik)), _transpose(bk)),
            _product(_product(bi, e_i_z_k), _transpose(hk)),
        ),
        _add(
            _product(_product(hi, z_i_e_k), _transpose(bk)),
            _product(_product(hi, z_i_z_k), _transpose(hk)),
        ),
    )
    same_target = (
        S_i == S_k
        and Omega_i == Omega_k
        and strength_i == strength_k
        and tuple(donors_i) == tuple(donors_k)
        and all(risk_i[key] == risk_k[key] for key in ("Z", "K", "B", "H", "MSE_S", "R_S", "R_U"))
    )
    if not same_target:
        return {"Cov_eS": result}
    risk_s_i, risk_s_k = risk_i["R_S"], risk_k["R_S"]
    risk_u_i, risk_u_k = risk_i["R_U"], risk_k["R_U"]
    corr_s = _trace(_product(_matrix(Q), result)) / _root(risk_s_i * risk_s_k)
    corr_u = _trace(_product(_matrix(Q), _matrix(C_ik))) / _root(risk_u_i * risk_u_k)
    return {"Cov_eS": result, "rS": corr_s, "rU": corr_u}


def _sum_matrices(matrices):
    if not matrices:
        raise Refusal("donor set must be nonempty")
    result = _zero(len(matrices[0]), len(matrices[0][0]))
    for matrix in matrices:
        result = _add(result, matrix)
    return result


def _scalar_risk(v, z, k, weight):
    v, z, k, weight = map(_fraction, (v, z, k, weight))
    return weight**2 * v + (1 - weight) ** 2 * z + 2 * weight * (1 - weight) * k


def closed_forms(v, z, k, t):
    v, z, k, t = map(_fraction, (v, z, k, t))
    if min(v, z, t) < 0:
        raise Refusal("closed-form variances and t must be nonnegative")
    denominator = v + z - 2 * k
    if denominator == 0:
        raise Refusal("best weight undefined when v + Z - 2K = 0")
    unconstrained = (z - k) / denominator
    flag = "IN_RANGE" if 0 <= unconstrained <= 1 else "OUT_OF_RANGE"
    best = min(_Fraction(1), max(_Fraction(0), unconstrained))
    if best == 0:
        best_strength = "INFINITE"
    elif best == 1:
        best_strength = _Fraction(0)
    else:
        best_strength = t * (1 - best) / best
    result = {
        "Z": z,
        "K": k,
        "w_star": unconstrained,
        "flag": flag,
        "w_best": best,
        "best_strength": best_strength,
        "R_best": _scalar_risk(v, z, k, best),
        "R_complete": z,
        "R_U": v,
        "w_be": (z - v) / denominator if z > v else "NONE",
    }
    if flag == "IN_RANGE":
        result["R_unconstrained"] = (v * z - k**2) / denominator
    return result


def directional_totals(v, z, k, gamma, c, t, regressors, shape, strength, rx=0):
    v, z, k, gamma, c, t, rx = map(_fraction, (v, z, k, gamma, c, t, rx))
    if isinstance(regressors, bool) or not isinstance(regressors, int) or regressors < 2:
        raise Refusal("regressors must be an integer of at least two")
    if shape not in ("GRAM", "IDENTITY"):
        raise Refusal("shape must be GRAM or IDENTITY")
    if strength != "INFINITE":
        strength = _fraction(strength)
        if strength < 0:
            raise Refusal("lambda must be nonnegative")
    if shape == "GRAM":
        direction_weights = [_Fraction(0) if strength == "INFINITE" else t / (t + strength)] * (
            regressors - 1
        )
    else:
        if not 0 <= rx < 1:
            raise Refusal("rx must be between zero inclusive and one exclusive")
        eigen_a = 1 + (regressors - 2) * rx
        eigen_b = 1 - rx
        direction_weights = [
            _Fraction(0) if strength == "INFINITE" else eigen_a * t / (eigen_a * t + strength)
        ]
        direction_weights.extend(
            [_Fraction(0) if strength == "INFINITE" else eigen_b * t / (eigen_b * t + strength)]
            * (regressors - 2)
        )
    direction_risks = [_scalar_risk(v, z, k, weight) for weight in direction_weights]
    direction_numerators = [
        weight**2 * c * v + 2 * weight * (1 - weight) * k + (1 - weight) ** 2 * (z - gamma)
        for weight in direction_weights
    ]
    total_u = regressors * v
    total_s = v + sum(direction_risks, _Fraction(0))
    total_cross = c * v + sum(direction_numerators, _Fraction(0))
    return {
        "direction_weights": tuple(direction_weights),
        "direction_risks": tuple(direction_risks),
        "direction_numerators": tuple(direction_numerators),
        "R_U": total_u,
        "R_S": total_s,
        "gain": total_u - total_s,
        "relative_gain": (total_u - total_s) / total_u,
        "rS": total_cross / total_s,
        "rU": c,
    }


CALLABLES = tuple(
    sorted(
        name
        for name, value in globals().copy().items()
        if callable(value) and not name.startswith("_")
    )
)
