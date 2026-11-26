"""Exact synthetic risk calculations; this module never estimates coefficients.

Manifest decisions: the preregistration is its own specification, so callers supply
equal preregistration and specification digests; neither is hard-coded. The closed
manifest schema is enforced. The builder accepts all values explicitly and has no
default grid. The only command is ``map``.
"""

import hashlib as _hashlib
import json as _json
import os as _os
import platform as _platform
import sys as _sys
from fractions import Fraction as _Fraction
from math import isqrt as _isqrt
from pathlib import Path as _Path
from time import perf_counter as _perf_counter


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


_MANIFEST_KEYS = {
    "schema",
    "prereg_sha256",
    "spec_sha256",
    "code_sha256",
    "environment",
    "fixed",
    "points",
    "strengths",
    "sc4_subset",
    "self_checks",
    "cap_seconds",
    "random_numbers",
    "provenance",
}
_POINT_KEYS = {"a", "m", "k", "c", "r_x", "omega"}
_ENV_KEYS = {"python", "system", "release", "machine"}
_FIXED_KEYS = {"p", "sigma2", "t"}
_SELF_CHECKS = [f"SC-{index}" for index in range(1, 9)]
_WRITE_FLAGS = _os.O_WRONLY | _os.O_RDWR | _os.O_APPEND | _os.O_CREAT | _os.O_TRUNC
_FS_EVENTS = {
    "os.mkdir",
    "os.rename",
    "os.remove",
    "os.rmdir",
    "os.chmod",
    "os.chown",
    "os.truncate",
    "os.link",
    "os.symlink",
    "os.utime",
}
_PROCESS_EVENTS = ("subprocess.", "os.system", "os.exec", "os.spawn", "os.posix_spawn", "os.fork")
_DISCLAIMERS = [
    "Synthetic parameters only. No market data was read. No random number was drawn.",
    "Exact risk in a declared linear model; not a score, not a floor, not a test.",
    "Every grid value is PROPOSED and none is adopted by this report.",
    "No look was taken and no claim is made or supported.",
    (
        "A computed risk gain does not establish that sharing helps any real symbol, and does not "
        "remove real-data survivorship bias."
    ),
    "Fixed-strength risk only. No strength is chosen, and no coefficient was estimated.",
]


def _canonical(value):
    return (
        _json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()


def _environment():
    return {
        "python": _sys.version,
        "system": _platform.system(),
        "release": _platform.release(),
        "machine": _platform.machine(),
    }


def _fraction_text(value):
    number = _fraction(value)
    return (
        str(number.numerator)
        if number.denominator == 1
        else f"{number.numerator}/{number.denominator}"
    )


def _parse_fraction(value):
    if not isinstance(value, str):
        raise Refusal("malformed fraction")
    pieces = value.split("/")
    try:
        if len(pieces) == 1:
            numerator, denominator = int(pieces[0]), 1
        elif len(pieces) == 2:
            numerator, denominator = int(pieces[0]), int(pieces[1])
        else:
            raise ValueError
        result = _Fraction(numerator, denominator)
    except (ValueError, ZeroDivisionError):
        raise Refusal("malformed fraction") from None
    if _fraction_text(result) != value or (len(pieces) == 2 and denominator <= 1):
        raise Refusal("fraction must be in lowest terms")
    return result


def build_manifest(
    schema,
    prereg_sha256,
    spec_sha256,
    code_sha256,
    environment,
    fixed,
    points,
    strengths,
    sc4_subset,
    self_checks,
    cap_seconds,
    random_numbers,
    provenance,
):
    """Return canonical manifest bytes from caller-supplied values."""
    item = {
        "schema": schema,
        "prereg_sha256": prereg_sha256,
        "spec_sha256": spec_sha256,
        "code_sha256": code_sha256,
        "environment": environment,
        "fixed": fixed,
        "points": points,
        "strengths": strengths,
        "sc4_subset": sc4_subset,
        "self_checks": self_checks,
        "cap_seconds": cap_seconds,
        "random_numbers": random_numbers,
        "provenance": provenance,
    }
    validate_manifest(item)
    return _canonical(item)


def validate_manifest(manifest):
    if not isinstance(manifest, dict) or set(manifest) != _MANIFEST_KEYS:
        raise Refusal("unknown or missing manifest key")
    if manifest["schema"] != "ucpe.exp05_stage0.manifest.v1":
        raise Refusal("malformed schema")
    digests = (manifest["prereg_sha256"], manifest["spec_sha256"], manifest["code_sha256"])
    if (
        any(not isinstance(value, str) for value in digests)
        or manifest["prereg_sha256"] != manifest["spec_sha256"]
        or any(
            len(value) != 64 or any(character not in "0123456789abcdef" for character in value)
            for value in digests
            if isinstance(value, str)
        )
    ):
        raise Refusal("malformed digest")
    if manifest["environment"] != _environment():
        raise Refusal("environment mismatch")
    if not isinstance(manifest["fixed"], dict) or set(manifest["fixed"]) != _FIXED_KEYS:
        raise Refusal("malformed fixed values")
    fixed = manifest["fixed"]
    if isinstance(fixed["p"], bool) or not isinstance(fixed["p"], int) or fixed["p"] < 2:
        raise Refusal("p must be an integer of at least two")
    if _parse_fraction(fixed["sigma2"]) <= 0 or _parse_fraction(fixed["t"]) <= 0:
        raise Refusal("sigma2 and t must be positive")
    if not isinstance(manifest["points"], list) or not manifest["points"]:
        raise Refusal("points must be a nonempty list")
    for point in manifest["points"]:
        if not isinstance(point, dict) or set(point) != _POINT_KEYS:
            raise Refusal("malformed point")
        for key in ("a", "c", "r_x"):
            _parse_fraction(point[key])
        if any(
            isinstance(point[key], bool) or not isinstance(point[key], int) or point[key] < 1
            for key in ("m", "k")
        ):
            raise Refusal("m and k must be positive integers")
        if point["omega"] not in ("GRAM", "IDENTITY"):
            raise Refusal("malformed omega")
        if _parse_fraction(point["a"]) < 0 or not 0 <= _parse_fraction(point["c"]) <= 1:
            raise Refusal("malformed point fraction")
        if not 0 <= _parse_fraction(point["r_x"]) < 1:
            raise Refusal("malformed r_x")
        _root(_Fraction(point["k"]))
    if not isinstance(manifest["strengths"], list) or not manifest["strengths"]:
        raise Refusal("strengths must be a nonempty list")
    strengths = manifest["strengths"]
    parsed = []
    infinite = False
    for strength in strengths:
        if strength == "INFINITE":
            if infinite:
                raise Refusal("duplicate strength")
            infinite = True
            parsed.append(None)
        else:
            value = _parse_fraction(strength)
            if value < 0 or infinite:
                raise Refusal("strengths must increase with INFINITE last")
            parsed.append(value)
    if parsed != sorted(parsed, key=lambda value: (value is None, value or 0)) or len(
        set(str(x) for x in strengths)
    ) != len(strengths):
        raise Refusal("strengths must increase")
    if not infinite:
        raise Refusal('strengths must include "INFINITE" last')
    subset = manifest["sc4_subset"]
    if (
        not isinstance(subset, dict)
        or set(subset) != {"m", "a", "c"}
        or not isinstance(subset["m"], int)
    ):
        raise Refusal("malformed sc4_subset")
    if any(not isinstance(subset[key], list) for key in ("a", "c")):
        raise Refusal("malformed sc4_subset")
    if isinstance(subset["m"], bool) or subset["m"] < 1:
        raise Refusal("malformed sc4_subset")
    for value in subset["a"] + subset["c"]:
        _parse_fraction(value)
    if manifest["self_checks"] != _SELF_CHECKS:
        raise Refusal("malformed self_checks")
    if (
        isinstance(manifest["cap_seconds"], bool)
        or not isinstance(manifest["cap_seconds"], int)
        or manifest["cap_seconds"] < 1
    ):
        raise Refusal("malformed cap_seconds")
    if manifest["random_numbers"] != "NONE":
        raise Refusal('random_numbers must be "NONE"')
    if manifest["provenance"] != "SYNTHETIC_PARAMETERS":
        raise Refusal('provenance must be "SYNTHETIC_PARAMETERS"')
    return True


def _number(value):
    value = _fraction(value)
    if value == 0:
        decimal = "0"
    else:
        sign = "-" if value < 0 else ""
        numerator, denominator = abs(value.numerator), value.denominator
        exponent = len(str(numerator)) - len(str(denominator))
        if (exponent >= 0 and numerator < denominator * 10**exponent) or (
            exponent < 0 and numerator * 10 ** (-exponent) < denominator
        ):
            exponent -= 1
        shift = 11 - exponent
        scaled_num, scaled_den = (
            (numerator * 10**shift, denominator)
            if shift >= 0
            else (numerator, denominator * 10 ** (-shift))
        )
        quotient, remainder = divmod(scaled_num, scaled_den)
        if 2 * remainder > scaled_den or (2 * remainder == scaled_den and quotient % 2):
            quotient += 1
        if quotient == 10**12:
            quotient //= 10
            exponent += 1
        digits = str(quotient).rjust(12, "0")
        decimal = f"{sign}{digits[0]}.{digits[1:]}e{exponent:+d}"
    return {"exact": _fraction_text(value), "decimal": decimal}


def _grid_matrices(manifest, point):
    p = manifest["fixed"]["p"]
    sigma2, t = (
        _parse_fraction(manifest["fixed"]["sigma2"]),
        _parse_fraction(manifest["fixed"]["t"]),
    )
    rx, a = _parse_fraction(point["r_x"]), _parse_fraction(point["a"])
    sigma = [
        [_Fraction(int(i == j)) if i == 0 else _Fraction(0) for j in range(p)] for i in range(p)
    ]
    sigma[0][0] = 1
    for i in range(1, p):
        for j in range(1, p):
            sigma[i][j] = 1 if i == j else rx
    inv = _inverse(sigma)
    v = sigma2 / t
    S = _scale(t, sigma)
    V = _scale(v, inv)
    Gamma = _scale(a * v, inv)
    omega = [[_Fraction(0) for _ in range(p)] for _ in range(p)]
    for i in range(1, p):
        for j in range(1, p):
            omega[i][j] = sigma[i][j] if point["omega"] == "GRAM" else _Fraction(int(i == j))
    m, k, c = point["m"], point["k"], _parse_fraction(point["c"])
    donor_ids = set(range(m + 2))
    donors = tuple(range(1, m + 1))
    W = _scale(k, S)
    cov = {}
    for i in donor_ids:
        for j in donor_ids:
            factor = (
                v
                if i == j and i in (0, m + 1)
                else v / k
                if i == j
                else c * v / _root(k)
                if (i in (0, m + 1)) != (j in (0, m + 1))
                else c * v / k
                if i != j
                else 0
            )
            cov[(i, j)] = _scale(factor, inv)
    Q = sigma
    return S, {j: W for j in donors}, omega, V, Gamma, cov, Q, donors, donor_ids, sigma, v


def _collapsed_target_risk(manifest, point, strength, matrices):
    S, weights, omega, V, Gamma, _, Q, _, _, sigma, v = matrices
    m, k = point["m"], point["k"]
    c = _parse_fraction(point["c"])
    gamma = _parse_fraction(point["a"]) * v
    donor_v = v / k
    z = (donor_v * (1 + (m - 1) * c) + gamma) / m + gamma
    cross = c * v / _root(k)
    inverse_sigma = _inverse(sigma)
    Z = _scale(z, inverse_sigma)
    K = _scale(cross, inverse_sigma)
    S, omega, strength = _validate_design(S, omega, strength)
    if strength == "INFINITE":
        B = pooling_projector(S, omega)
        H = _sub(_identity(len(S)), B)
    else:
        A = _inverse(_add(S, _scale(strength, omega)))
        B = _product(A, S)
        H = _scale(strength, _product(A, omega))
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


def _eval_point(manifest, point):
    matrices = _grid_matrices(manifest, point)
    S, weights, omega, V, Gamma, cov, Q, donors, donor_ids, sigma, v = matrices
    m, c = point["m"], _parse_fraction(point["c"])
    per_strength = []
    checks = {key: True for key in _SELF_CHECKS}
    for strength_text in manifest["strengths"]:
        strength = "INFINITE" if strength_text == "INFINITE" else _parse_fraction(strength_text)
        risk = _collapsed_target_risk(manifest, point, strength, matrices)
        other = _collapsed_target_risk(manifest, point, strength, matrices)
        cross = cross_covariance(
            S,
            omega,
            strength,
            S,
            omega,
            strength,
            cov[(0, m + 1)],
            {j: cov[(0, j)] for j in donors},
            {j: cov[(j, m + 1)] for j in donors},
            {(j, donor_l): cov[(j, donor_l)] for j in donors for donor_l in donors},
            Gamma,
            Q,
            donors,
            donors,
            weights,
            0,
            m + 1,
            donor_ids,
            risk,
            other,
        )
        inverse_sigma = _inverse(sigma)
        direction_scale = inverse_sigma[1][1]
        z = risk["Z"][1][1] / direction_scale
        cross_v = risk["K"][1][1] / direction_scale
        form = directional_totals(
            v,
            z,
            cross_v,
            _parse_fraction(point["a"]) * v,
            c,
            _parse_fraction(manifest["fixed"]["t"]),
            manifest["fixed"]["p"],
            point["omega"],
            strength,
            rx=_parse_fraction(point["r_x"]),
        )
        checks["SC-1"] &= strength != 0 or (
            risk["R_S"] == risk["R_U"] and cross["rS"] == cross["rU"]
        )
        checks["SC-2"] &= (
            risk["R_U"] == form["R_U"]
            and risk["R_S"] == form["R_S"]
            and risk["gain"] == form["gain"]
            and risk["relative_gain"] == form["relative_gain"]
            and cross["rS"] == form["rS"]
            and cross["rU"] == form["rU"]
        )
        checks["SC-3"] &= _symmetric(risk["MSE_S"]) and _positive_semidefinite(risk["MSE_S"])
        per_strength.append(
            {
                "strength": strength_text,
                "R_S": risk["R_S"],
                "gain": risk["gain"],
                "relative_gain": risk["relative_gain"],
                "rS": cross["rS"],
                "rU": cross["rU"],
            }
        )
    # The manifest strengths alone define the reported minimum; stable order favors weaker ties.
    best = min(enumerate(per_strength), key=lambda pair: (pair[1]["R_S"], pair[0]))[1]["strength"]
    result = {
        "parameters": point,
        "R_U": risk["R_U"],
        "strengths": per_strength,
        "best_strength": best,
        "status": "COMPUTED",
    }
    if point["omega"] == "GRAM":
        inverse_sigma = _inverse(sigma)
        direction_scale = inverse_sigma[1][1]
        z = risk["Z"][1][1] / direction_scale
        cross_v = risk["K"][1][1] / direction_scale
        form = closed_forms(v, z, cross_v, _parse_fraction(manifest["fixed"]["t"]))
        result["closed_form"] = {
            key: form[key]
            for key in ("w_star", "flag", "w_best", "best_strength", "R_best", "w_be")
        }
        for item in per_strength:
            checks["SC-7"] &= form["R_best"] <= item["R_S"]
        if form["flag"] == "OUT_OF_RANGE":
            endpoint = next(
                item["R_S"] for item in per_strength if item["strength"] == form["best_strength"]
            )
            checks["SC-7"] &= form["R_best"] == endpoint
    projector = pooling_projector(S, omega)
    complement = _sub(_identity(len(S)), projector)
    checks["SC-8"] = (
        _product(projector, projector) == projector
        and _product(omega, projector) == _zero(len(S), len(S))
        and _product(_product(_transpose(projector), S), complement) == _zero(len(S), len(S))
    )
    return result, checks


def _sc6_check(manifest):
    combinations_to_check = sorted(
        {(point["a"], point["m"], point["k"], point["c"]) for point in manifest["points"]}
    )
    for a_value, m, k, c_value in combinations_to_check:
        common = {"a": a_value, "m": m, "k": k, "c": c_value, "r_x": "0"}
        gram = _grid_matrices(manifest, {**common, "omega": "GRAM"})
        identity = _grid_matrices(manifest, {**common, "omega": "IDENTITY"})
        for strength_text in manifest["strengths"]:
            strength = "INFINITE" if strength_text == "INFINITE" else _parse_fraction(strength_text)
            gram_risk = target_risk(
                gram[0],
                gram[1],
                gram[2],
                strength,
                gram[3],
                gram[4],
                gram[5],
                gram[6],
                gram[7],
                0,
                gram[8],
            )
            identity_risk = target_risk(
                identity[0],
                identity[1],
                identity[2],
                strength,
                identity[3],
                identity[4],
                identity[5],
                identity[6],
                identity[7],
                0,
                identity[8],
            )
            if any(
                gram_risk[key] != identity_risk[key]
                for key in ("Z", "K", "MSE_S", "R_U", "R_S", "gain", "relative_gain")
            ):
                return False
    return True


def _sc4_check(manifest):
    subset = manifest["sc4_subset"]
    k_values = sorted({point["k"] for point in manifest["points"]})
    shapes = sorted({(point["r_x"], point["omega"]) for point in manifest["points"]})
    for rx, shape in shapes:
        for k_value in k_values:
            for a_value in subset["a"]:
                for c_value in subset["c"]:
                    point = {
                        "a": a_value,
                        "m": subset["m"],
                        "k": k_value,
                        "c": c_value,
                        "r_x": rx,
                        "omega": shape,
                    }
                    matrices = _grid_matrices(manifest, point)
                    S, weights, omega, V, Gamma, cov, Q, donors, ids, sigma, v = matrices
                    m = point["m"]
                    c = _parse_fraction(c_value)
                    gamma_scalar = _parse_fraction(a_value) * v
                    donor_v = v / k_value
                    z_scalar = (donor_v * (1 + (m - 1) * c) + gamma_scalar) / m + gamma_scalar
                    k_scalar = c * v / _root(k_value)
                    for strength_text in manifest["strengths"]:
                        strength = (
                            "INFINITE"
                            if strength_text == "INFINITE"
                            else _parse_fraction(strength_text)
                        )
                        risk = _collapsed_target_risk(manifest, point, strength, matrices)
                        symbolic_risk = target_risk(
                            S, weights, omega, strength, V, Gamma, cov, Q, donors, 0, ids
                        )
                        if any(
                            risk[key] != symbolic_risk[key]
                            for key in ("Z", "K", "MSE_S", "R_U", "R_S", "gain", "relative_gain")
                        ):
                            return False
                        sigma_inverse = _inverse(sigma)
                        if risk["Z"] != _add(
                            _scale(z_scalar, sigma_inverse), _zero(len(S), len(S))
                        ) or risk["K"] != _scale(k_scalar, sigma_inverse):
                            return False
                        direct_z = _zero(len(S), len(S))
                        for donor_j in donors:
                            for donor_l in donors:
                                direct_z = _add(
                                    direct_z,
                                    _product(
                                        _product(weights[donor_j], cov[(donor_j, donor_l)]),
                                        _transpose(weights[donor_l]),
                                    ),
                                )
                            direct_z = _add(
                                direct_z,
                                _product(
                                    _product(weights[donor_j], Gamma),
                                    _transpose(weights[donor_j]),
                                ),
                            )
                        P = _inverse(_sum_matrices([weights[j] for j in donors]))
                        direct_z = _add(_product(_product(P, direct_z), _transpose(P)), Gamma)
                        if direct_z != risk["Z"]:
                            return False
                        other = _collapsed_target_risk(manifest, point, strength, matrices)
                        cross = cross_covariance(
                            S,
                            omega,
                            strength,
                            S,
                            omega,
                            strength,
                            cov[(0, m + 1)],
                            {j: cov[(0, j)] for j in donors},
                            {j: cov[(j, m + 1)] for j in donors},
                            {(j, donor_l): cov[(j, donor_l)] for j in donors for donor_l in donors},
                            Gamma,
                            Q,
                            donors,
                            donors,
                            weights,
                            0,
                            m + 1,
                            ids,
                            risk,
                            other,
                        )
                        W = weights[donors[0]]
                        e_i_z_k = _scale(
                            m,
                            _product(_product(cov[(0, donors[0])], _transpose(W)), _transpose(P)),
                        )
                        z_i_e_k = _scale(m, _product(P, _product(W, cov[(donors[0], m + 1)])))
                        expected_cross = _add(
                            _add(
                                _product(
                                    _product(risk["B"], cov[(0, m + 1)]),
                                    _transpose(risk["B"]),
                                ),
                                _product(_product(risk["B"], e_i_z_k), _transpose(risk["H"])),
                            ),
                            _add(
                                _product(_product(risk["H"], z_i_e_k), _transpose(risk["B"])),
                                _product(
                                    _product(risk["H"], _sub(risk["Z"], Gamma)),
                                    _transpose(risk["H"]),
                                ),
                            ),
                        )
                        if cross["Cov_eS"] != expected_cross:
                            return False
    return True


def evaluate_map(manifest):
    """Evaluate a caller-supplied synthetic fixture; never constructs a grid."""
    rows, check_rows = [], []
    for point in manifest["points"]:
        row, checks = _eval_point(manifest, point)
        rows.append(row)
        check_rows.append(checks)
    table = [{"id": key, "passed": all(row[key] for row in check_rows)} for key in _SELF_CHECKS]
    table[3]["passed"] = _sc4_check(manifest)
    table[4]["passed"] = len(rows) == len(manifest["points"]) and sum(
        len(row["strengths"]) for row in rows
    ) == len(manifest["points"]) * len(manifest["strengths"])
    table[5]["passed"] = _sc6_check(manifest)
    return rows, table


def _guard_reason(event, args, allowed):
    if event.startswith("socket.") or event.startswith(_PROCESS_EVENTS):
        return f"forbidden event: {event}"
    if event.startswith("shutil.") or event in _FS_EVENTS:
        for arg in args:
            if isinstance(arg, (str, bytes, _os.PathLike)):
                try:
                    target = _Path(_os.fsdecode(arg)).resolve(strict=False)
                except (OSError, ValueError, TypeError):
                    continue
                if allowed not in (target, *target.parents):
                    return f"filesystem change outside the output folder: {event}"
        return None
    if event == "open":
        mode = args[1] if len(args) > 1 else None
        flags = args[2] if len(args) > 2 else None
        writing = (
            any(flag in mode for flag in "wax+")
            if isinstance(mode, str)
            else isinstance(flags, int) and bool(flags & _WRITE_FLAGS)
        )
        if not writing:
            return None
        try:
            target = _Path(_os.fsdecode(args[0])).resolve(strict=False)
            if allowed not in (target, *target.parents):
                return "write outside the output folder"
        except (OSError, ValueError, TypeError):
            return "write outside the output folder"
    return None


def _protected_component(path):
    return any(
        token in str(part)
        for part in _Path(path).parts
        for token in ("5a", "f3", "look_run", "holdout", "sealed", "f2_")
    )


def _install_guard(holder):
    def hook(event, args):
        reason = _guard_reason(event, args, holder[0])
        if reason:
            raise Refusal(reason)

    _sys.addaudithook(hook)


def run_map(manifest, manifest_bytes, out_folder, repo_root, expected_sha256):
    """Validate, evaluate and write one map. Tests call this directly, never through main."""
    validate_manifest(manifest)
    if _hashlib.sha256(manifest_bytes).hexdigest() != expected_sha256:
        raise Refusal("manifest digest mismatch")
    if manifest_bytes != _canonical(manifest):
        raise Refusal("manifest is not canonical")
    if _hashlib.sha256(_Path(__file__).read_bytes()).hexdigest() != manifest["code_sha256"]:
        raise Refusal("module digest mismatch")
    root = _Path(repo_root).resolve(strict=True)
    out = _Path(out_folder)
    if _protected_component(out):
        raise Refusal("protected output path")
    if out.is_symlink():
        raise Refusal("output folder is a symlink")
    resolved = out.resolve(strict=False)
    base = (root / ".work").resolve(strict=True)
    try:
        relative = resolved.relative_to(base)
    except ValueError:
        raise Refusal("output folder must be below .work/exp05_stage0_*") from None
    if len(relative.parts) < 2 or not relative.parts[0].startswith("exp05_stage0_"):
        raise Refusal("output folder must be below .work/exp05_stage0_*")
    protected = ("5a", "f3", "look_run", "holdout", "sealed", "f2_")
    if any(any(token in part for token in protected) for part in resolved.parts):
        raise Refusal("protected output path")
    if resolved.exists() and (not resolved.is_dir() or any(resolved.iterdir())):
        raise Refusal("output folder must be new or empty")
    if manifest["random_numbers"] != "NONE" or manifest["provenance"] != "SYNTHETIC_PARAMETERS":
        raise Refusal("manifest provenance refused")
    # Measure a single fixture evaluation and project conservatively before any write.
    start = _perf_counter()
    _eval_point(manifest, manifest["points"][0])
    sample = _perf_counter() - start
    sc6_count = len(
        {(point["a"], point["m"], point["k"], point["c"]) for point in manifest["points"]}
    )
    sc4_count = (
        len({point["k"] for point in manifest["points"]})
        * len({(point["r_x"], point["omega"]) for point in manifest["points"]})
        * len(manifest["sc4_subset"]["a"])
        * len(manifest["sc4_subset"]["c"])
    )
    projected = sample * (len(manifest["points"]) + sc6_count + sc4_count)
    if projected > manifest["cap_seconds"]:
        raise Refusal("projected runtime exceeds cap_seconds")
    rows, table = evaluate_map(manifest)
    status = "COMPUTED" if all(item["passed"] for item in table) else "STOP_KERNEL_DEFECT"
    for row in rows:
        raw_point = row["parameters"]
        row["parameters"] = {
            "fixed": {
                "p": _number(_Fraction(manifest["fixed"]["p"])),
                "sigma2": _number(_parse_fraction(manifest["fixed"]["sigma2"])),
                "t": _number(_parse_fraction(manifest["fixed"]["t"])),
            },
            "a": _number(_parse_fraction(raw_point["a"])),
            "m": _number(_Fraction(raw_point["m"])),
            "k": _number(_Fraction(raw_point["k"])),
            "c": _number(_parse_fraction(raw_point["c"])),
            "r_x": _number(_parse_fraction(raw_point["r_x"])),
            "omega": raw_point["omega"],
        }
        for item in row["strengths"]:
            if item["strength"] != "INFINITE":
                item["strength"] = _number(_parse_fraction(item["strength"]))
            for key in ("R_S", "gain", "relative_gain", "rS", "rU"):
                item[key] = _number(item[key])
        row["R_U"] = _number(row["R_U"])
        if row["best_strength"] != "INFINITE":
            row["best_strength"] = _number(_parse_fraction(row["best_strength"]))
        if "closed_form" in row:
            row["closed_form"] = {
                key: _number(value) if isinstance(value, _Fraction) else value
                for key, value in row["closed_form"].items()
            }
    map_bytes = b"".join(_canonical(row) for row in rows)
    report = {
        "status": status,
        "counts": {"points": len(rows), "evaluations": len(rows) * len(manifest["strengths"])},
        "self_checks": table,
        "non_computed_points": [row["parameters"] for row in rows if row["status"] != "COMPUTED"],
        "out_of_range_count": sum(
            row.get("closed_form", {}).get("flag") == "OUT_OF_RANGE" for row in rows
        ),
        "disclaimers": _DISCLAIMERS,
    }
    report_bytes = _canonical(report)
    manifest_copy = manifest_bytes
    sums = "".join(
        f"{_hashlib.sha256(data).hexdigest()}  {name}\n"
        for name, data in (
            ("MANIFEST.json", manifest_copy),
            ("MAP.jsonl", map_bytes),
            ("REPORT.json", report_bytes),
        )
    )
    out.mkdir(parents=True, exist_ok=True)
    for name, data in (
        ("MANIFEST.json", manifest_copy),
        ("MAP.jsonl", map_bytes),
        ("REPORT.json", report_bytes),
        ("SHA256SUMS.txt", sums.encode()),
    ):
        (out / name).write_bytes(data)
    return status


def main(argv):
    """The sole CLI command; its audit hook is installed only in this entry point."""
    if (
        len(argv) != 7
        or argv[0] != "map"
        or argv[1] != "--manifest"
        or argv[3] != "--expect-sha256"
        or argv[5] != "--out"
    ):
        raise Refusal("usage: map --manifest <file> --expect-sha256 <hex> --out <folder>")
    manifest_path, expected, output = _Path(argv[2]), argv[4], _Path(argv[6])
    if _protected_component(manifest_path):
        raise Refusal("protected manifest path")
    data = manifest_path.read_bytes()
    manifest = _json.loads(data)
    holder = [output.resolve(strict=False)]
    _install_guard(holder)
    return run_map(manifest, data, output, _Path.cwd(), expected)


CALLABLES = tuple(
    sorted(
        name
        for name, value in globals().copy().items()
        if callable(value) and not name.startswith("_")
    )
)


if __name__ == "__main__":
    try:
        main(_sys.argv[1:])
    except (Refusal, OSError, ValueError, _json.JSONDecodeError) as error:
        print(f"REFUSAL: {error}", file=_sys.stderr)
        raise SystemExit(2) from None
