"""Synthetic-only EXP-04 stage-1 null design identities and numerics."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import platform
import re
import statistics
import sys
import time
from dataclasses import dataclass
from fractions import Fraction
from functools import cache, lru_cache

import numpy as np

STAGES = ("DEV", "VAL", "KAT", "BENCH")
STREAMS = ("EVAL", "CAL_SIGMA0", "CAL_THMC")
SEED_COMPONENTS = ("REGIME", "NOISE_G1", "NOISE_G2", "NOISE_G3", "NOISE_G4", "MEMBERSHIP", "SERIES")
SCENARIO_FAMILIES = (
    "N-CORE",
    "N-VOL",
    "N-REGMEAN",
    "N-TWIN",
    "N-MEMSPLIT",
    "N-AR",
    "N-CHURN",
    "N-SEL",
    "N-TAIL",
    "P-CORE",
    "P-HET",
    "P-SCORE",
    "P-CTRL",
    "P-TWIN",
    "P-CHURN",
)
SCENARIO_KINDS = ("SIZE", "POWER")
FAMILY_CLASSES = ("PLAN_NAMED", "SENSITIVITY", "NOT_APPLICABLE")
ENVELOPES = ("E60", "E65", "E75", "E85", "E95")
CLASS_SETS = ("PLAN_NAMED", "SENSITIVITY", "ALL")
REGIME_SPEEDS = ("NONE", "FAST", "SLOW")
MEMORY_SPLITS = ("BOTH", "COMMON_ONLY", "IDIO_ONLY")
EFFECT_TYPES = ("NONE", "HOMOG", "HALF", "OPPOSED", "REGIME_ONLY")
SCORES = ("S", "LL", "BR")
ARMS = ("CAND", "CTRL")
LEVELS = {"A050": 0.05, "A025": 0.025, "A0125": 0.0125, "A0083": 0.025 / 3}
CORES = ("T", "TH", "TH_MC", "RA_EXT", "RA_WM", "SYM_REPL")
UPPER_BOUNDS = ("NONE", "UB80", "UB95")
VARIANTS = (
    "V_CORE",
    "V_J0",
    "V_Q_OFF",
    "V_Q_060",
    "V_Q_070",
    "V_Q_090",
    "V_Q_100",
    "V_CTRL_OFF",
    "V_MMIN_1",
    "V_FLOOR_005",
    "V_FLOOR_010",
    "V_FLOOR_020",
)
VARIANT_TABLE = {
    "V_CORE": {"q": None, "control": False, "m_min": None, "floor": 0.0},
    "V_J0": {"q": "4/5", "control": True, "m_min": "ceil(L/4)", "floor": 0.0},
    "V_Q_OFF": {"q": None, "control": True, "m_min": None, "floor": 0.0},
    "V_Q_060": {"q": "3/5", "control": True, "m_min": "ceil(L/4)", "floor": 0.0},
    "V_Q_070": {"q": "7/10", "control": True, "m_min": "ceil(L/4)", "floor": 0.0},
    "V_Q_090": {"q": "9/10", "control": True, "m_min": "ceil(L/4)", "floor": 0.0},
    "V_Q_100": {"q": "1", "control": True, "m_min": "ceil(L/4)", "floor": 0.0},
    "V_CTRL_OFF": {"q": "4/5", "control": False, "m_min": "ceil(L/4)", "floor": 0.0},
    "V_MMIN_1": {"q": "4/5", "control": True, "m_min": 1, "floor": 0.0},
    "V_FLOOR_005": {"q": "4/5", "control": True, "m_min": "ceil(L/4)", "floor": 0.05},
    "V_FLOOR_010": {"q": "4/5", "control": True, "m_min": "ceil(L/4)", "floor": 0.10},
    "V_FLOOR_020": {"q": "4/5", "control": True, "m_min": "ceil(L/4)", "floor": 0.20},
}
BOUNDS = ("STRICT", "TOL20", "CEIL2X")
POWER_TARGETS = ("P50", "P80", "P90")
CELL_STATUSES = ("ESTIMATED", "NOT_ESTIMABLE")
VERDICTS = ("VALID", "INVALID", "INCONCLUSIVE", "INSUFFICIENT_POWER", "NOT_ESTIMABLE")
SIZE_ROLLUP_STATUSES = ("VALID", "INVALID", "UNRESOLVED")
POWER_ROLLUP_STATUSES = ("MET", "INSUFFICIENT", "INCONCLUSIVE", "NOT_CREDITED")
DEPENDENCE_CONVENTIONS = ("CENTRAL", "WORST_E65", "WORST_E85")
SELF_CHECK_IDS = ("SC-1", "SC-2", "SC-3", "SC-4")
SELF_CHECK_STATUSES = ("PASS", "FAIL")
READING_LEVELS = ("A050", "A025", "A0125", "A0083")
READING_ENVELOPES = ("E65", "E85")
READINGS = tuple((level, envelope) for level in READING_LEVELS for envelope in READING_ENVELOPES)
READING_LABELS = tuple(
    f"OUTCOME@(α={a}, E={e}, TOL20)"
    for a, e in (
        ("0.05", "E65"),
        ("0.05", "E85"),
        ("0.025", "E65"),
        ("0.025", "E85"),
        ("0.0125", "E65"),
        ("0.0125", "E85"),
        ("0.025/3", "E65"),
        ("0.025/3", "E85"),
    )
)
OUTCOME_STATUSES = (
    "COMPUTED",
    "STOP_HARNESS_DEFECT",
    "DEV_ONLY_NOT_AN_OUTCOME",
    "KAT_ONLY_NOT_AN_OUTCOME",
)
OUTCOME_RESULTS = (
    "STAGE1_PASS_CONDITIONAL",
    "STOP_SIZE_UNCONTROLLED",
    "STOP_INSUFFICIENT_POWER",
    "STOP_INSUFFICIENT_POWER_VETO_KEYS",
    "STOP_INCONCLUSIVE",
    "STOP_HARNESS_DEFECT",
)
SELECTION_RULE_ID = "PREREG_4_4"
CONSUMED_MARKER_STATUSES = ("STARTED", "COMPLETE")
SCHEMA_IDS = (
    "ucpe.exp04_stage1.manifest.v1",
    "ucpe.exp04_stage1.report.v1",
    "ucpe.exp04_stage1.cells.v1",
    "ucpe.exp04_stage1.dev_decisions.v1",
    "ucpe.exp04_stage1.consumed.v1",
    "ucpe.exp04_stage1.timing.v1",
)
SEED_NAMESPACE = "UCPE-EXP04-STAGE1-v1"
DISCLAIMERS = (
    "Synthetic data only. No real market data was read.",
    "No look was taken and no claim is made or supported.",
    "Synthetic validity does not remove real-data survivorship bias.",
    "Every constant is PROPOSED and none is adopted by this report.",
    "Stage 2 needs the owner, real data and the licence; none is authorized.",
)
W_HIST_MAX = 208
QUARTER = 13


class Refusal(Exception):
    """Raised when an input violates the frozen harness contract."""


@cache
def normal_quantile(p: float) -> float:
    if not 0 < p < 1:
        raise ValueError("p must be between zero and one")
    return statistics.NormalDist().inv_cdf(p)


def _betacf(a: float, b: float, x: float) -> float:
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-300:
        d = 1e-300
    d = 1.0 / d
    h = d
    for m in range(1, 10001):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-300:
            d = 1e-300
        c = 1.0 + aa / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-300:
            d = 1e-300
        c = 1.0 + aa / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-14:
            return h
    raise ArithmeticError("beta continued fraction did not converge")


def _beta_reg(a: float, b: float, x: float) -> float:
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    front = math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    )
    if x < (a + 1) / (a + b + 2):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1 - x) / b


@cache
def student_t_cdf(t: float, df: int) -> float:
    if df <= 0:
        raise ValueError("df must be positive")
    x = df / (df + t * t)
    tail = 0.5 * _beta_reg(df / 2, 0.5, x)
    return 1.0 - tail if t >= 0 else tail


@cache
def student_t_quantile(p: float, df: int) -> float:
    if not 0 < p < 1 or df <= 0:
        raise ValueError("invalid probability or degrees of freedom")
    if p == 0.5:
        return 0.0
    if p < 0.5:
        return -student_t_quantile(1 - p, df)
    lo, hi = 0.0, 1.0
    while student_t_cdf(hi, df) < p:
        hi *= 2
    for _ in range(100):
        mid = (lo + hi) / 2
        if student_t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo < 2e-13:
            break
    return (lo + hi) / 2


def _gamma_p(a: float, x: float) -> float:
    if x <= 0:
        return 0.0
    gln = math.lgamma(a)
    if x < a + 1:
        ap, term, total = a, 1.0 / a, 1.0 / a
        for _ in range(10000):
            ap += 1
            term *= x / ap
            total += term
            if abs(term) < abs(total) * 3e-14:
                break
        return total * math.exp(-x + a * math.log(x) - gln)
    b = x + 1 - a
    c = 1e300
    d = 1 / b
    h = d
    for i in range(1, 10000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        if abs(d) < 1e-300:
            d = 1e-300
        c = b + an / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 3e-14:
            break
    return 1 - math.exp(-x + a * math.log(x) - gln) * h


@cache
def chi2_quantile(p: float, df: int) -> float:
    if not 0 < p < 1 or df <= 0:
        raise ValueError("invalid probability or degrees of freedom")
    lo, hi = 0.0, max(1.0, float(df))
    while _gamma_p(df / 2, hi / 2) < p:
        hi *= 2
    for _ in range(100):
        mid = (lo + hi) / 2
        if _gamma_p(df / 2, mid / 2) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo < 2e-13:
            break
    return (lo + hi) / 2


def _beta_quantile(p: float, a: float, b: float) -> float:
    if p <= 0:
        return 0.0
    if p >= 1:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if _beta_reg(a, b, mid) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo < 2e-14:
            break
    return (lo + hi) / 2


@cache
def clopper_pearson(x: int, n: int, conf: float = 0.95) -> tuple[float, float]:
    if n <= 0 or x < 0 or x > n or not 0 < conf < 1:
        raise ValueError("invalid binomial interval arguments")
    tail = (1 - conf) / 2
    return (
        0.0 if x == 0 else _beta_quantile(tail, x, n - x + 1),
        1.0 if x == n else _beta_quantile(1 - tail, x + 1, n - x),
    )


@cache
def cp_lower(x: int, n: int, tail: float) -> float:
    if n <= 0 or x < 0 or x > n or not 0 < tail < 1:
        raise ValueError("invalid binomial bound arguments")
    return 0.0 if x == 0 else _beta_quantile(tail, x, n - x + 1)


def ub_factor(K: int, ub: str) -> float:
    if ub == "NONE":
        return 1.0
    if ub not in ("UB80", "UB95") or K < 2:
        raise ValueError("invalid upper-bound setting")
    confidence = 0.80 if ub == "UB80" else 0.95
    return math.sqrt((K - 1) / chi2_quantile(1 - confidence, K - 1))


@lru_cache(maxsize=256)
def arfima_acf(d: float, n: int, ar_phi: float = 0.0) -> np.ndarray:
    if n < 1 or not 0 <= d < 0.5 or not 0 <= ar_phi < 1:
        raise ValueError("invalid ARFIMA parameters")
    r = np.empty(n, dtype=np.float64)
    r[0] = 1.0
    for k in range(1, n):
        r[k] = r[k - 1] * (k - 1 + d) / (k - d)
    if ar_phi:
        extended = np.empty(n + 400, dtype=np.float64)
        extended[:n] = r
        for k in range(n, n + 400):
            extended[k] = extended[k - 1] * (k - 1 + d) / (k - d)
        result = np.empty(n, dtype=np.float64)
        for k in range(n):
            result[k] = sum(ar_phi ** abs(j) * extended[abs(k - j)] for j in range(-400, 401))
        result /= result[0]
        return result
    r.setflags(write=False)
    return r


def window_mean_variance(acf: np.ndarray, L: int) -> float:
    if L < 1 or len(acf) < L:
        raise ValueError("acf must contain at least L entries")
    return (1 + 2 * sum((1 - k / L) * float(acf[k]) for k in range(1, L))) / L


@lru_cache(maxsize=128)
def cholesky_factor(d: float, n: int, ar_phi: float = 0.0) -> np.ndarray:
    acf = arfima_acf(d, n, ar_phi)
    matrix = acf[np.abs(np.arange(n)[:, None] - np.arange(n)[None, :])]
    result = np.linalg.cholesky(matrix)
    result.setflags(write=False)
    return result


# Orchestration and file boundary.  Kept here so the numerical layer remains usable
# directly by tests without installing a process-global audit hook.
_THREAD_KEYS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "MKL_NUM_THREADS",
)
_MANIFEST_KEYS = {
    "schema",
    "stage",
    "namespace",
    "prereg_sha256",
    "spec_sha256",
    "code_sha256",
    "environment",
    "replications",
    "chunking",
    "runtime_cap_seconds",
    "scenarios",
    "designs",
    "variants",
    "focus_designs",
    "levels",
    "seed_keys_sha256",
    "seed_key_count",
    "selections",
    "dev_report_sha256",
    "dev_manifest_sha256",
    "decisions_sha256",
    "amendments",
}
_REPORT_DISCLAIMERS = [
    "Synthetic data only. No real market data was read.",
    "No look was taken and no claim is made or supported.",
    "Synthetic validity does not remove real-data survivorship bias.",
    "Every constant is PROPOSED and none is adopted by this report.",
    "Stage 2 needs the owner, real data and the licence; none is authorized.",
]


def environment_record(environ):
    """Return the closed §12.1 runtime record using only approved platform calls."""
    return {
        "python": sys.version,
        "numpy": np.__version__,
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "threads": {key: environ.get(key) for key in _THREAD_KEYS},
    }


def thread_settings_ok(environ):
    return all(environ.get(key) == "1" for key in _THREAD_KEYS)


def _protected_path(value):
    text = os.fspath(value).lower()
    return any(
        token in part
        for part in pathlib.PurePath(text).parts
        for token in ("5a", "f3", "look_run", "holdout", "sealed", "f2_")
    )


def check_out_dir(path, repo_root):
    raw = pathlib.Path(path)
    if _protected_path(raw):
        raise Refusal("protected path component")
    root = pathlib.Path(repo_root).resolve()
    work = root / ".work"
    candidate = raw if raw.is_absolute() else pathlib.Path.cwd() / raw
    candidate = pathlib.Path(os.path.abspath(candidate))
    # Locate the repo root through the supplied spelling (macOS may spell the same
    # temp directory as /var or /private/var), then inspect each output component.
    prefix = pathlib.Path(candidate.anchor)
    suffix = None
    for index, part in enumerate(candidate.parts[1:], start=1):
        prefix = prefix / part
        if prefix.resolve(strict=False) == root:
            suffix = candidate.parts[index + 1 :]
            break
    if suffix is None:
        raise Refusal("output folder outside .work/exp04_stage1_*")
    current = root
    for part in suffix:
        current = current / part
        if current.is_symlink():
            raise Refusal("output folder is a symlink")
    candidate = current.resolve(strict=False)
    # Ancestors of repo_root may be platform aliases (for example /private); the
    # output path itself must contain no symlink from .work down.
    out = candidate
    try:
        rel = out.relative_to(work)
    except ValueError as exc:
        raise Refusal("output folder outside .work/exp04_stage1_*") from exc
    if (
        len(rel.parts) < 2
        or not rel.parts[0].startswith("exp04_stage1_")
        or out == (work / rel.parts[0]).resolve()
    ):
        raise Refusal("output folder outside .work/exp04_stage1_*")
    return out


def _write_bytes(path, data):
    path = pathlib.Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _code_sha256():
    return _sha(pathlib.Path(__file__).read_bytes())


def _check_hash(value):
    return (
        isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    )


def _validate_grid(stage, scenario_ids, designs, replications, chunking, selections=None):
    """Apply the immutable stage grid and minimum rules to a manifest or run."""
    minimums = VAL_MINIMUMS if stage == "VAL" else DEV_MINIMUMS
    refusal = (
        "validation grid is incomplete" if stage == "VAL" else "development grid is incomplete"
    )
    if stage in ("DEV", "VAL"):
        if any(replications.get(k, 0) < v for k, v in minimums.items()):
            raise Refusal(refusal)
        for key, nkey in (
            ("chunk_null", "n_null"),
            ("chunk_power", "n_power"),
            ("chunk_thmc", "n_cal_thmc"),
        ):
            if chunking.get(key, 0) < 1 or replications[nkey] % chunking[key]:
                raise Refusal(refusal)
    if stage in ("DEV", "VAL") and not set(design_grid()).issubset(designs):
        raise Refusal(refusal)
    try:
        scenarios = [parse_scenario_id(item) for item in scenario_ids]
    except (TypeError, ValueError) as exc:
        raise Refusal("invalid scenario id") from exc
    if len(scenario_ids) != len(set(scenario_ids)):
        raise Refusal("duplicate scenario")
    ids = set(scenario_ids)
    if any(s.kind == "POWER" and null_twin_id(s) not in ids for s in scenarios):
        raise Refusal("null twin missing")
    if stage in ("DEV", "VAL"):
        frozen = {scenario_id(s) for s in scenario_grid(stage)}
        if not frozen.issubset(ids) or any(
            s.kind != "SIZE" for s in scenarios if scenario_id(s) not in frozen
        ):
            raise Refusal(refusal)
    if stage == "VAL":
        if not isinstance(selections, list) or len(selections) != len(READINGS):
            raise Refusal("selection is incomplete")
        for selection, (level, envelope) in zip(selections, READINGS, strict=True):
            if not isinstance(selection, dict):
                raise Refusal("selection is incomplete")
            required = {"level", "envelope", "primary", "fallback", "dev_no_candidate"}
            if set(selection) - required:
                raise Refusal("unknown field")
            if set(selection) != required:
                raise Refusal("selection is incomplete")
            if selection.get("level") != level or selection.get("envelope") != envelope:
                raise Refusal("selection is incomplete")
            if selection.get("primary") not in candidates(level) or (
                selection.get("fallback") is not None
                and selection.get("fallback") not in candidates(level)
            ):
                raise Refusal("selected design is not a candidate")
    return scenarios


def build_manifest(
    stage,
    prereg_sha256,
    spec_sha256,
    *,
    environ=None,
    replications=None,
    chunking=None,
    scenarios=None,
    selections=None,
    dev_report_sha256=None,
    dev_manifest_sha256=None,
    decisions_sha256=None,
    amendments=None,
):
    """Build and validate the closed manifest record for a DEV, VAL, or KAT stage."""
    env = os.environ if environ is None else environ
    if stage not in ("DEV", "VAL", "KAT"):
        raise Refusal("unknown field")
    if not _check_hash(prereg_sha256) or not _check_hash(spec_sha256):
        raise Refusal("unknown field")
    mins = VAL_MINIMUMS if stage == "VAL" else DEV_MINIMUMS
    reps = dict(mins if replications is None else replications)
    if set(reps) != set(mins) or any(type(reps[k]) is not int or reps[k] < mins[k] for k in mins):
        raise Refusal(
            "validation grid is incomplete" if stage == "VAL" else "development grid is incomplete"
        )
    chunks = {"chunk_null": 1000, "chunk_power": 500, "chunk_thmc": 10000} | (chunking or {})
    if set(chunks) != {"chunk_null", "chunk_power", "chunk_thmc"} or any(
        type(v) is not int or v < 1 for v in chunks.values()
    ):
        raise Refusal("unknown field")
    if scenarios is None:
        grid = scenario_grid(stage)
    else:
        try:
            grid = tuple(sorted((parse_scenario_id(x) for x in scenarios), key=scenario_id))
        except (TypeError, ValueError) as exc:
            raise Refusal("invalid scenario id") from exc
    ids = [scenario_id(s) for s in grid]
    if len(ids) != len(set(ids)):
        raise Refusal("duplicate scenario")
    if any(s.kind != "SIZE" and null_twin_id(s) not in set(ids) for s in grid):
        raise Refusal("null twin missing")
    if stage in ("DEV", "VAL"):
        frozen = {scenario_id(s) for s in scenario_grid(stage)}
        if not frozen.issubset(set(ids)) or any(
            s.kind != "SIZE" for s in grid if scenario_id(s) not in frozen
        ):
            raise Refusal(
                "validation grid is incomplete"
                if stage == "VAL"
                else "development grid is incomplete"
            )
    des = list(design_grid())
    focus = list(focus_designs())
    _validate_grid(stage, ids, des, reps, chunks, selections)
    keys = all_seed_keys(
        stage,
        ids,
        [
            f"THMC/L={L:03d}/H={h:.2f}"
            for L in sorted({s.L for s in grid})
            for h in (0.60, 0.65, 0.75, 0.85, 0.95)
        ],
        reps,
        chunks,
    )
    if len(keys) != len(set(keys)) or len({_sha(key.encode("ascii")) for key in keys}) != len(keys):
        raise Refusal("seed streams are not disjoint")
    return {
        "schema": "ucpe.exp04_stage1.manifest.v1",
        "stage": stage,
        "namespace": "UCPE-EXP04-STAGE1-v1",
        "prereg_sha256": prereg_sha256,
        "spec_sha256": spec_sha256,
        "code_sha256": _code_sha256(),
        "environment": environment_record(env),
        "replications": reps,
        "chunking": chunks,
        "runtime_cap_seconds": 21600 if stage == "VAL" else 3600,
        "scenarios": ids,
        "designs": des,
        "variants": list(VARIANTS),
        "focus_designs": focus,
        "levels": dict(LEVELS),
        "seed_keys_sha256": _sha("\n".join(sorted(keys)).encode("ascii")),
        "seed_key_count": len(keys),
        "selections": selections,
        "dev_report_sha256": dev_report_sha256,
        "dev_manifest_sha256": dev_manifest_sha256,
        "decisions_sha256": decisions_sha256,
        "amendments": list(amendments or []),
    }


def load_manifest(path, expect_sha256):
    """Load only a canonical manifest, verify its byte digest, closed keys and code digest."""
    path = pathlib.Path(path)
    if _protected_path(path):
        raise Refusal("protected path component")
    raw = path.read_bytes()
    if _sha(raw) != expect_sha256:
        raise Refusal("manifest digest mismatch")
    try:
        obj = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise Refusal("unknown field") from exc
    if not isinstance(obj, dict) or set(obj) != _MANIFEST_KEYS:
        raise Refusal("unknown field")
    if obj.get("code_sha256") != _code_sha256():
        raise Refusal("harness digest mismatch")
    if obj.get("environment") != environment_record(os.environ):
        raise Refusal("environment mismatch")
    _validate_grid(
        obj.get("stage"),
        obj.get("scenarios", []),
        obj.get("designs", []),
        obj.get("replications", {}),
        obj.get("chunking", {}),
        obj.get("selections"),
    )
    return obj


def _runtime_shape(s, designs, focus, reps=2, chunk=2):
    th = {
        L: {h: {level: 0.0 for level in READING_LEVELS} for h in (0.60, 0.65, 0.75, 0.85, 0.95)}
        for L in (s.L,)
    }
    sig = {scenario_id(s): 1.0}
    if null_twin_id(s) is not None:
        sig[null_twin_id(s)] = 1.0
    start = time.perf_counter()
    count_scenario(
        s,
        stage="BENCH",
        n_reps=reps,
        chunk=chunk,
        designs=designs,
        focus=focus,
        sigma0=sig,
        thmc=th,
    )
    return time.perf_counter() - start


def project_runtime(manifest):
    """Measure count_scenario on three reference shapes and project the manifest workload."""
    shapes = (
        scenario_grid("DEV")[0],
        scenario_grid("DEV")[1],
        next(s for s in scenario_grid("DEV") if s.kind == "POWER"),
    )
    measured = [_runtime_shape(s, manifest["designs"], manifest["focus_designs"]) for s in shapes]
    scenarios = [parse_scenario_id(x) for x in manifest["scenarios"]]
    reps = manifest["replications"]
    eval_seconds = sum(measured[0] * reps["n_null"] / 2 for s in scenarios if s.kind == "SIZE")
    eval_seconds += sum(measured[2] * reps["n_power"] / 2 for s in scenarios if s.kind == "POWER")
    calib = sum(reps["n_cal_sigma0"] for s in scenarios if s.kind == "SIZE") * measured[1] / 2
    return float(eval_seconds + calib)


def guard_reason(event, args, allowed, extra_files=()):
    """Return an audit refusal reason, or None when an event is permitted."""
    if event.startswith("socket.") or event in {
        "subprocess.Popen",
        "os.system",
        "os.posix_spawn",
        "os.fork",
        "os.exec",
    }:
        return "network or process creation refused"
    if (
        event in {"open", "os.open", "os.rename", "os.remove", "os.mkdir", "os.rmdir", "os.chmod"}
        and args
    ):
        writing = event != "open"
        if event == "open":
            mode = args[1] if len(args) > 1 else "r"
            flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
            writing = any(flag in str(mode) for flag in ("w", "a", "x", "+")) or bool(
                flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            )
        if not writing:
            return None
        targets = args[:2] if event in {"os.rename", "os.replace"} else args[:1]
        roots = [pathlib.Path(allowed).resolve()]
        extras = {pathlib.Path(x).resolve() for x in extra_files}
        for target in targets:
            if not isinstance(target, (str, bytes, os.PathLike)):
                continue
            p = pathlib.Path(os.fsdecode(target)).resolve()
            if p in extras:
                continue
            if not any(p == root or root in p.parents for root in roots):
                return "write outside output folder refused"
    return None


def install_guard(holder):
    """Install the process audit hook; holder has allowed and extra_files entries."""

    def hook(event, args):
        reason = guard_reason(event, args, holder["allowed"], holder.get("extra_files", ()))
        if reason:
            raise Refusal(reason)

    sys.addaudithook(hook)


def _cell_for(s, stats, manifest, sigma, thmc, null_cells, m_sim):
    designs = manifest["designs"]
    entries = []
    counts = stats["counts"]
    bad = set(stats["not_estimable"])
    for design in designs:
        variants = (
            ("V_CORE",)
            if s.kind == "SIZE"
            else (VARIANTS if design in manifest["focus_designs"] else ("V_CORE", "V_J0"))
        )
        for variant in variants:
            key = f"{design}|{variant}"
            base = {
                "design_id": design,
                "variant_id": variant,
                "status": "NOT_ESTIMABLE" if key in bad else "ESTIMATED",
            }
            if key in bad:
                base.update({"rejections": None, "rate": None, "cp95": None})
            else:
                x = counts.get(f"{key}|rejections", 0)
                n = stats["n_reps"]
                ci = clopper_pearson(x, n)
                base.update({"rejections": x, "rate": x / n, "cp95": list(ci)})
            if s.kind == "SIZE":
                if key in bad:
                    base.update(
                        {
                            "cp_sim_lower": None,
                            "size_verdicts": {b: "NOT_ESTIMABLE" for b in BOUNDS},
                            "confirmed_invalid": {b: False for b in BOUNDS},
                            "rejections_core_and_sign": None,
                        }
                    )
                else:
                    x, n = base["rejections"], stats["n_reps"]
                    alpha = LEVELS[declared_level(design)]
                    cl = {b: classify_size(x, n, alpha, b, m_sim) for b in BOUNDS}
                    base.update(
                        {
                            "cp_sim_lower": cp_lower(x, n, 0.025 / (2 * m_sim)),
                            "size_verdicts": {b: cl[b]["verdict"] for b in BOUNDS},
                            "confirmed_invalid": {b: cl[b]["confirmed_invalid"] for b in BOUNDS},
                            "rejections_core_and_sign": counts.get(f"{design}|core_and_sign", 0),
                        }
                    )
            else:
                null = (
                    null_cells.get((design, "V_CORE"), {})
                    .get("size_verdicts", {})
                    .get("TOL20", "NOT_ESTIMABLE")
                )
                if key in bad:
                    base.update(
                        {
                            "null_twin_verdict": null,
                            "power_verdicts": {p: "NOT_ESTIMABLE" for p in POWER_TARGETS},
                            "core_rejections": None,
                            "sign_vetoes": None,
                            "control_vetoes": None,
                        }
                    )
                else:
                    x, n = base["rejections"], stats["n_reps"]
                    base.update(
                        {
                            "null_twin_verdict": null,
                            "power_verdicts": {
                                p: classify_power(x, n, p, null) for p in POWER_TARGETS
                            },
                            "core_rejections": counts.get(f"{key}|core_rejections", 0),
                            "sign_vetoes": counts.get(f"{key}|sign_vetoes", 0),
                            "control_vetoes": counts.get(f"{key}|control_vetoes", 0),
                        }
                    )
            entries.append(base)
    params = {k: getattr(s, k) for k in Scenario.__dataclass_fields__}
    return {
        "schema": "ucpe.exp04_stage1.cells.v1",
        "scenario_id": scenario_id(s),
        "kind": s.kind,
        "params": params,
        "family_class": family_class(s),
        "d_envelope": d_envelope(s),
        "null_twin_id": null_twin_id(s),
        "n_reps": stats["n_reps"],
        "diagnostics": {
            "mean_turnover": stats["mean_turnover"],
            "sign_not_evaluable": stats["sign_not_evaluable"],
        },
        "cells": entries,
    }


def run_stage(manifest, out_dir, *, resume=False, repo_root, environ):
    """Run one complete synthetic stage and write its canonical output bundle."""
    out = check_out_dir(out_dir, repo_root)
    if not thread_settings_ok(environ):
        raise Refusal("thread settings must be 1")
    if manifest.get("code_sha256") != _code_sha256():
        raise Refusal("harness digest mismatch")
    if manifest.get("environment") != environment_record(environ):
        raise Refusal("environment mismatch")
    if manifest.get("schema") != "ucpe.exp04_stage1.manifest.v1" or set(manifest) != _MANIFEST_KEYS:
        raise Refusal("unknown field")
    if manifest.get("stage") not in ("DEV", "VAL", "KAT"):
        raise Refusal("unknown field")
    _validate_grid(
        manifest["stage"],
        manifest.get("scenarios", []),
        manifest.get("designs", []),
        manifest.get("replications", {}),
        manifest.get("chunking", {}),
        manifest.get("selections"),
    )
    if manifest.get("stage") == "VAL" and (out / "REPORT.json").exists():
        raise Refusal("validation already consumed")
    if out.exists() and any(out.iterdir()) and not resume:
        raise Refusal("output folder is not empty")
    out.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    start_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    stage = manifest["stage"]
    marker = None
    if stage == "VAL":
        lane = out.relative_to(pathlib.Path(repo_root).resolve() / ".work").parts[0]
        marker = (
            pathlib.Path(repo_root)
            / ".work"
            / lane
            / f"VALIDATION_CONSUMED_{manifest['prereg_sha256'][:16]}.json"
        )
        if marker.exists():
            old = json.loads(marker.read_bytes())
            if old.get("manifest_sha256") != _sha(canonical_bytes(manifest)):
                raise Refusal("validation already consumed under this preregistration")
            if old.get("status") == "COMPLETE":
                raise Refusal("validation already consumed")
            if not resume:
                raise Refusal("validation interrupted: resume flag required")
            restarts = old.get("restarts", 0) + 1
        else:
            restarts = 0
        marker_obj = {
            "schema": "ucpe.exp04_stage1.consumed.v1",
            "prereg_sha256": manifest["prereg_sha256"],
            "manifest_sha256": _sha(canonical_bytes(manifest)),
            "status": "STARTED",
            "restarts": restarts,
        }
        marker.write_bytes(canonical_bytes(marker_obj))
    else:
        restarts = 0
    if stage in ("DEV", "VAL") and project_runtime(manifest) > manifest["runtime_cap_seconds"]:
        raise Refusal("projected runtime exceeds the cap")
    scenarios = [parse_scenario_id(x) for x in manifest["scenarios"]]
    size_scenarios = [s for s in scenarios if s.kind == "SIZE"]
    expected_cells = sum(len(manifest["designs"]) for s in size_scenarios) + sum(
        12 * len(manifest["focus_designs"])
        + 2 * (len(manifest["designs"]) - len(manifest["focus_designs"]))
        for s in scenarios
        if s.kind == "POWER"
    )
    thmc = {
        L: {
            h: thmc_table(
                L,
                h,
                stage=stage,
                n_series=manifest["replications"]["n_cal_thmc"],
                chunk=manifest["chunking"]["chunk_thmc"],
            )
            for h in (0.60, 0.65, 0.75, 0.85, 0.95)
        }
        for L in sorted({s.L for s in scenarios})
    }
    sigma = {
        scenario_id(s): sigma0_for(
            s,
            stage=stage,
            n_reps=manifest["replications"]["n_cal_sigma0"],
            chunk=manifest["chunking"]["chunk_null"],
        )
        for s in size_scenarios
    }
    rows, size_by_scenario = [], {}
    for s in scenarios:
        n = manifest["replications"]["n_null" if s.kind == "SIZE" else "n_power"]
        chunk = manifest["chunking"]["chunk_null" if s.kind == "SIZE" else "chunk_power"]
        twin_sigmas = {sid: val for sid, val in sigma.items()}
        stats = count_scenario(
            s,
            stage=stage,
            n_reps=n,
            chunk=chunk,
            designs=manifest["designs"],
            focus=manifest["focus_designs"],
            sigma0=twin_sigmas,
            thmc=thmc,
        )
        cellsrow = _cell_for(s, stats, manifest, sigma, thmc, {}, len(size_scenarios))
        if s.kind == "SIZE":
            size_by_scenario[scenario_id(s)] = {c["design_id"]: c for c in cellsrow["cells"]}
        rows.append(cellsrow)
    for row in rows:
        if row["kind"] == "POWER":
            twin = size_by_scenario.get(row["null_twin_id"], {})
            for c in row["cells"]:
                c["null_twin_verdict"] = (
                    twin.get(c["design_id"], {})
                    .get("size_verdicts", {})
                    .get("TOL20", "NOT_ESTIMABLE")
                )
                if c["status"] == "ESTIMATED":
                    c["power_verdicts"] = {
                        p: classify_power(c["rejections"], row["n_reps"], p, c["null_twin_verdict"])
                        for p in POWER_TARGETS
                    }
    cells_bytes = b"".join(canonical_bytes(row) for row in rows)
    checks = self_checks(rows, expected_scenarios=len(scenarios), expected_cells=expected_cells)
    size_roll = size_rollups(rows)
    power_roll = power_rollups(rows)
    mde = minimum_detectable_effects(rows)
    if stage == "DEV":
        sels = select_designs("DEV", rows)
        outcome_status, outcome_rows = "DEV_ONLY_NOT_AN_OUTCOME", []
    elif stage == "VAL":
        sels = [
            {
                "level": x["level"],
                "envelope": x["envelope"],
                "rule": SELECTION_RULE_ID,
                "candidates": [],
                "primary": x["primary"],
                "fallback": x["fallback"],
                "dev_no_candidate": x["dev_no_candidate"],
            }
            for x in manifest["selections"]
        ]
        outcome_rows = outcomes(manifest["selections"], size_roll, power_roll, rows, checks)
        outcome_status = (
            "STOP_HARNESS_DEFECT" if any(x["status"] != "PASS" for x in checks) else "COMPUTED"
        )
    else:
        sels, outcome_rows, outcome_status = [], [], "KAT_ONLY_NOT_AN_OUTCOME"
    cells_path = out / "CELLS.jsonl"
    _write_bytes(cells_path, cells_bytes)
    cell_digest = _sha(cells_bytes)
    size_count = sum(s.kind == "SIZE" for s in scenarios)
    power_count = len(scenarios) - size_count
    report = {
        "schema": "ucpe.exp04_stage1.report.v1",
        "stage": stage,
        "synthetic_only": True,
        "manifest_sha256": _sha(canonical_bytes(manifest)),
        "prereg_sha256": manifest["prereg_sha256"],
        "spec_sha256": manifest["spec_sha256"],
        "code_sha256": manifest["code_sha256"],
        "environment": manifest["environment"],
        "replications": manifest["replications"],
        "counts": {
            "scenarios_expected": len(scenarios),
            "scenarios_reported": len(rows),
            "size_scenarios": size_count,
            "power_scenarios": power_count,
            "designs": len(manifest["designs"]),
            "focus_designs": len(manifest["focus_designs"]),
            "size_cells": sum(len(r["cells"]) for r in rows if r["kind"] == "SIZE"),
            "power_cells": sum(len(r["cells"]) for r in rows if r["kind"] == "POWER"),
        },
        "cells_file": {"name": "CELLS.jsonl", "sha256": cell_digest, "lines": len(rows)},
        "calibration": {
            "thmc": [
                {"L": L, "h_c": h, "level": level, "critical_value": v}
                for L, hs in thmc.items()
                for h, levels in hs.items()
                for level, v in levels.items()
            ],
            "sigma0": [{"scenario_id": k, "sigma0": v} for k, v in sigma.items()],
        },
        "self_checks": checks,
        "size_rollups": size_roll,
        "power_rollups": power_roll,
        "minimum_detectable_effect": mde,
        "selections": sels,
        "outcome_status": outcome_status,
        "outcomes": outcome_rows,
        "omissions": [],
        "disclaimers": _REPORT_DISCLAIMERS,
    }
    _write_bytes(out / "REPORT.json", canonical_bytes(report))
    finished_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _write_bytes(
        out / "TIMING.json",
        canonical_bytes(
            {
                "schema": "ucpe.exp04_stage1.timing.v1",
                "started_utc": start_utc,
                "finished_utc": finished_utc,
                "seconds": time.perf_counter() - started,
                "restarts": restarts,
            }
        ),
    )
    if marker:
        marker_obj["status"] = "COMPLETE"
        marker.write_bytes(canonical_bytes(marker_obj))
    return report


def _load_dev_report(folder):
    folder = pathlib.Path(folder)
    report_raw = (folder / "REPORT.json").read_bytes()
    timing = json.loads((folder / "TIMING.json").read_bytes())
    with (folder / "CELLS.jsonl").open() as f:
        cells = [json.loads(line) for line in f]
    report = json.loads(report_raw)
    if report.get("stage") != "DEV":
        raise Refusal("not a development report")
    return {
        "dev_manifest_sha256": report["manifest_sha256"],
        "dev_report_sha256": _sha(report_raw),
        "code_sha256": report["code_sha256"],
        "started_utc": timing["started_utc"],
        "stage": "DEV",
        "cells": cells,
    }


def main(argv=None):
    """CLI entry point. Its audit hook is intentionally process-global."""
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "benchmark"):
        p = sub.add_parser(name)
        p.add_argument("--stage", choices=("DEV", "VAL"), required=True)
    p = sub.add_parser("manifest")
    p.add_argument("--stage", choices=("DEV", "VAL"), required=True)
    p.add_argument("--prereg-sha256", required=True)
    p.add_argument("--spec-sha256", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--dev-report", action="append")
    p.add_argument("--decisions")
    p.add_argument("--additions")
    p = sub.add_parser("run")
    p.add_argument("--manifest", required=True)
    p.add_argument("--expect-sha256", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--resume-interrupted", action="store_true")
    p = sub.add_parser("select")
    p.add_argument("--dev-report", action="append", required=True)
    p.add_argument("--additions")
    p.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    repo_root = pathlib.Path.cwd()
    try:
        path_args = [
            getattr(args, key, None) for key in ("manifest", "out", "additions", "decisions")
        ]
        path_args.extend(getattr(args, "dev_report", None) or [])
        if any(value is not None and _protected_path(value) for value in path_args):
            raise Refusal("protected path component")
        if args.command == "plan":
            scenarios = scenario_grid(args.stage)
            sizes = sum(s.kind == "SIZE" for s in scenarios)
            powers = len(scenarios) - sizes
            des, foc = len(design_grid()), len(focus_designs())
            size_cells = sizes * des
            power_cells = powers * (12 * foc + 2 * (des - foc))
            ids_digest = _sha("\n".join(sorted(scenario_id(s) for s in scenarios)).encode("ascii"))
            print(
                f"stage={args.stage} scenarios={len(scenarios)} size={sizes} "
                f"power={powers} designs={des} size_cells={size_cells} "
                f"power_cells={power_cells} scenario_ids_sha256={ids_digest}"
            )
            return 0
        holder = {"allowed": pathlib.Path(args.out).resolve(), "extra_files": ()}
        if args.command in ("run", "manifest", "select"):
            # Guard allows only output writes; consumed marker is the sole exact extra path.
            if args.command == "run":
                raw = pathlib.Path(args.manifest).read_bytes()
                manifest_obj = json.loads(raw)
                if manifest_obj.get("stage") == "VAL":
                    lane = (
                        pathlib.Path(args.out).resolve().relative_to(repo_root / ".work").parts[0]
                    )
                    holder["extra_files"] = (
                        repo_root
                        / ".work"
                        / lane
                        / f"VALIDATION_CONSUMED_{manifest_obj['prereg_sha256'][:16]}.json",
                    )
            install_guard(holder)
        if args.command == "benchmark":
            if not thread_settings_ok(os.environ):
                raise Refusal("thread settings must be 1")
            m = build_manifest(args.stage, "0" * 64, "0" * 64, environ=os.environ)
            print(f"projected_runtime_seconds={project_runtime(m):.6f}")
            return 0
        if args.command == "manifest":
            out = check_out_dir(args.out, repo_root)
            if out.exists() and any(out.iterdir()):
                raise Refusal("output folder is not empty")
            extra = {}
            if args.stage == "VAL":
                if not args.dev_report or not args.decisions:
                    raise Refusal("selection is incomplete")
                runs = [_load_dev_report(folder) for folder in args.dev_report]
                additions = (
                    json.loads(pathlib.Path(args.additions).read_bytes())
                    if args.additions
                    else None
                )
                expected_decisions = build_dev_decisions(runs, additions)
                decision_bytes = pathlib.Path(args.decisions).read_bytes()
                decisions = json.loads(decision_bytes)
                if decisions != expected_decisions:
                    raise Refusal("selection does not match the development report")
                ordered_runs = sorted(runs, key=lambda run: run["started_utc"])
                final_run = ordered_runs[-1]
                scenario_ids = [scenario_id(s) for s in scenario_grid("VAL")]
                scenario_ids.extend(x["scenario_id"] for x in expected_decisions["grid_additions"])
                replications = dict(VAL_MINIMUMS)
                replications.update(expected_decisions["replications"])
                extra = {
                    "scenarios": scenario_ids,
                    "selections": expected_decisions["selections"],
                    "dev_report_sha256": final_run["dev_report_sha256"],
                    "dev_manifest_sha256": final_run["dev_manifest_sha256"],
                    "decisions_sha256": _sha(decision_bytes),
                    "replications": replications,
                    "amendments": [expected_decisions["notes"]]
                    if expected_decisions["notes"]
                    else [],
                }
            m = build_manifest(
                args.stage, args.prereg_sha256, args.spec_sha256, environ=os.environ, **extra
            )
            out.mkdir(parents=True, exist_ok=True)
            _write_bytes(out / "MANIFEST.json", canonical_bytes(m))
            print(_sha(canonical_bytes(m)))
            return 0
        if args.command == "run":
            m = load_manifest(args.manifest, args.expect_sha256)
            report = run_stage(
                m, args.out, resume=args.resume_interrupted, repo_root=repo_root, environ=os.environ
            )
            print(report["outcome_status"])
            return 0
        if args.command == "select":
            out = check_out_dir(args.out, repo_root)
            if out.exists() and any(out.iterdir()):
                raise Refusal("output folder is not empty")
            additions = (
                json.loads(pathlib.Path(args.additions).read_bytes()) if args.additions else None
            )
            decisions = build_dev_decisions(
                [_load_dev_report(folder) for folder in args.dev_report], additions
            )
            out.mkdir(parents=True, exist_ok=True)
            _write_bytes(out / "DEV_DECISIONS.json", canonical_bytes(decisions))
            return 0
    except Refusal as exc:
        print(f"REFUSAL: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"run failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    return 1


@dataclass(frozen=True)
class Scenario:
    family: str
    kind: str
    d: float
    rho: float
    n: int
    L: int
    mem: str = "BOTH"
    ar_phi: float = 0.0
    tail_nu: int | None = None
    vol_ratio: float = 1.0
    regime_speed: str = "NONE"
    regime_mean_g: float = 0.0
    twin_fraction: float = 0.0
    twin_rho: float | None = None
    churn_a: float | None = None
    sel_psi: float = 0.0
    delta: float = 0.0
    effect: str = "NONE"
    score_rho: float | None = None
    brier_ratio: float = 1.0
    ctrl_omega: float | None = None


_ID_RE = re.compile(
    r"^(?P<family>[A-Z-]+)/d=(?P<d>\d+\.\d{2})/rho=(?P<rho>\d+\.\d{2})/n=(?P<n>\d{3})/L=(?P<L>\d{3})(?P<extra>(?:/[^/]+)*)$"
)


def scenario_id(s: Scenario) -> str:
    base = f"{s.family}/d={s.d:.2f}/rho={s.rho:.2f}/n={s.n:03d}/L={s.L:03d}"
    f = s.family
    if f not in SCENARIO_FAMILIES:
        raise ValueError("unknown scenario family")
    if f in ("N-CORE", "N-VOL"):
        extra = ""
    elif f == "N-REGMEAN":
        extra = f"/g={s.regime_mean_g:.2f}/speed={s.regime_speed}"
    elif f in ("N-TWIN", "P-TWIN"):
        extra = (
            f"/rtw={s.twin_rho:.2f}"
            if f == "N-TWIN"
            else f"/delta={s.delta:.2f}/rtw={s.twin_rho:.2f}"
        )
    elif f == "N-MEMSPLIT":
        extra = f"/mem={s.mem}"
    elif f == "N-AR":
        extra = f"/phi={s.ar_phi:.2f}"
    elif f in ("N-CHURN", "P-CHURN"):
        extra = (
            f"/a={s.churn_a:.2f}" if f == "N-CHURN" else f"/delta={s.delta:.2f}/a={s.churn_a:.2f}"
        )
    elif f == "N-SEL":
        extra = f"/a={s.churn_a:.2f}/psi={s.sel_psi:.2f}"
    elif f == "N-TAIL":
        extra = f"/nu={s.tail_nu:d}"
    elif f == "P-CORE":
        extra = f"/delta={s.delta:.2f}"
    elif f == "P-HET":
        extra = f"/delta={s.delta:.2f}/het={s.effect}"
    elif f == "P-SCORE":
        extra = f"/delta={s.delta:.2f}/rs={s.score_rho:.2f}/br={s.brier_ratio:.2f}"
    else:
        extra = f"/delta={s.delta:.2f}/omega={s.ctrl_omega:.2f}"
    return base + extra


def parse_scenario_id(text: str) -> Scenario:
    m = _ID_RE.fullmatch(text)
    if not m or m["family"] not in SCENARIO_FAMILIES:
        raise ValueError("invalid scenario id")
    family, d, rho, n, L = m["family"], float(m["d"]), float(m["rho"]), int(m["n"]), int(m["L"])
    if not (0 <= d <= 0.45 and 0 <= rho < 1 and n >= 5 and 26 <= L <= 104 and L % 13 == 0):
        raise ValueError("invalid scenario id")
    values: dict = {
        "family": family,
        "kind": "POWER" if family.startswith("P-") else "SIZE",
        "d": d,
        "rho": rho,
        "n": n,
        "L": L,
    }
    if family.startswith("P-"):
        values.update(effect="HOMOG", score_rho=0.8, ctrl_omega=0.5)
    extra = m["extra"]
    patterns = {
        "N-CORE": r"",
        "N-VOL": r"",
        "N-REGMEAN": r"/g=(\d+\.\d{2})/speed=(FAST|SLOW)",
        "N-TWIN": r"/rtw=(\d+\.\d{2})",
        "N-MEMSPLIT": r"/mem=(COMMON_ONLY|IDIO_ONLY)",
        "N-AR": r"/phi=(\d+\.\d{2})",
        "N-CHURN": r"/a=(\d+\.\d{2})",
        "N-SEL": r"/a=(\d+\.\d{2})/psi=(\d+\.\d{2})",
        "N-TAIL": r"/nu=(\d+)",
        "P-CORE": r"/delta=(\d+\.\d{2})",
        "P-HET": r"/delta=(\d+\.\d{2})/het=(HALF|OPPOSED|REGIME_ONLY)",
        "P-SCORE": r"/delta=(\d+\.\d{2})/rs=(\d+\.\d{2})/br=(\d+\.\d{2})",
        "P-CTRL": r"/delta=(\d+\.\d{2})/omega=(\d+\.\d{2})",
        "P-TWIN": r"/delta=(\d+\.\d{2})/rtw=(\d+\.\d{2})",
        "P-CHURN": r"/delta=(\d+\.\d{2})/a=(\d+\.\d{2})",
    }
    em = re.fullmatch(patterns[family], extra)
    if not em:
        raise ValueError("invalid scenario id")
    g = em.groups()
    if family == "N-REGMEAN":
        values.update(regime_mean_g=float(g[0]), regime_speed=g[1])
    elif family in ("N-TWIN", "P-TWIN"):
        values.update(
            twin_fraction=0.4,
            twin_rho=float(g[-1]),
            **({"delta": float(g[0])} if family == "P-TWIN" else {}),
        )
    elif family == "N-MEMSPLIT":
        values["mem"] = g[0]
    elif family == "N-AR":
        values["ar_phi"] = float(g[0])
    elif family in ("N-CHURN", "P-CHURN"):
        values.update(
            churn_a=float(g[-1]), **({"delta": float(g[0])} if family == "P-CHURN" else {})
        )
    elif family == "N-SEL":
        values.update(churn_a=float(g[0]), sel_psi=float(g[1]))
    elif family == "N-TAIL":
        values["tail_nu"] = int(g[0])
    elif family == "P-CORE":
        values["delta"] = float(g[0])
    elif family == "P-HET":
        values.update(delta=float(g[0]), effect=g[1])
    elif family == "P-SCORE":
        values.update(delta=float(g[0]), score_rho=float(g[1]), brier_ratio=float(g[2]))
    elif family == "P-CTRL":
        values.update(delta=float(g[0]), ctrl_omega=float(g[1]))
    if family == "N-VOL" or family == "P-HET" and values.get("effect") == "REGIME_ONLY":
        values.update(vol_ratio=3.0, regime_speed="FAST")
    if values["kind"] == "POWER" and values["delta"] <= 0:
        raise ValueError("invalid scenario id")
    if (
        values.get("tail_nu") is not None
        and values["tail_nu"] < 3
        or values.get("churn_a") is not None
        and not 0 < values["churn_a"] < 1
    ):
        raise ValueError("invalid scenario id")
    if not 0 <= values.get("ar_phi", 0.0) < 1 or not 0 <= values.get("sel_psi", 0.0) <= 1:
        raise ValueError("invalid scenario id")
    if values.get("twin_rho") is not None and not 0 < values["twin_rho"] <= 1:
        raise ValueError("invalid scenario id")
    if values["family"] == "P-HET" and (
        values["effect"] == "HALF" and n % 2 or values["effect"] == "OPPOSED" and n % 5
    ):
        raise ValueError("invalid scenario id")
    return Scenario(**values)


def _scenario(family: str, **kwargs) -> Scenario:
    kind = "POWER" if family.startswith("P-") else "SIZE"
    defaults = {"d": 0.0, "rho": 0.6, "n": 10, "L": 26}
    if kind == "POWER":
        defaults.update(effect="HOMOG", score_rho=0.8, ctrl_omega=0.5)
    if family == "N-VOL" or family == "P-HET" and kwargs.get("effect") == "REGIME_ONLY":
        defaults.update(vol_ratio=3.0, regime_speed="FAST")
    defaults.update(kwargs)
    return Scenario(family=family, kind=kind, **defaults)


def _anchors():
    return [_scenario("N-CORE", d=d, L=L) for d in (0.0, 0.15, 0.35) for L in (26, 52, 104)]


def scenario_grid(stage: str) -> tuple[Scenario, ...]:
    if stage not in ("DEV", "VAL"):
        raise ValueError("stage must be DEV or VAL")
    out: list[Scenario] = []
    anchors = _anchors()
    if stage == "VAL":
        for d in (0.0, 0.10, 0.15, 0.25, 0.35, 0.45):
            for rho in (0.0, 0.3, 0.6, 0.9, 0.99):
                for n in (5, 10, 20, 30, 60):
                    for L in (26, 52, 104):
                        out.append(_scenario("N-CORE", d=d, rho=rho, n=n, L=L))
        out += [_scenario("N-VOL", d=s.d, L=s.L) for s in anchors]
        for s in anchors:
            for g in (0.25, 0.5):
                for speed in ("FAST", "SLOW"):
                    out.append(
                        _scenario("N-REGMEAN", d=s.d, L=s.L, regime_mean_g=g, regime_speed=speed)
                    )
            for rt in (0.95, 1.0):
                out.append(_scenario("N-TWIN", d=s.d, L=s.L, twin_fraction=0.4, twin_rho=rt))
            if s.d > 0:
                for mem in ("COMMON_ONLY", "IDIO_ONLY"):
                    out.append(_scenario("N-MEMSPLIT", d=s.d, L=s.L, mem=mem))
            for phi in (0.3, 0.6):
                out.append(_scenario("N-AR", d=s.d, L=s.L, ar_phi=phi))
            for a in (0.9, 0.5):
                out.append(_scenario("N-CHURN", d=s.d, L=s.L, churn_a=a))
            out.append(_scenario("N-SEL", d=s.d, L=s.L, churn_a=0.9, sel_psi=0.5))
            for nu in (5, 3):
                out.append(_scenario("N-TAIL", d=s.d, L=s.L, tail_nu=nu))
        for delta in (0.1, 0.2, 0.4, 0.8, 1.6):
            for d in (0.0, 0.15, 0.35):
                for rho in (0.3, 0.6, 0.9):
                    for n in (10, 30):
                        for L in (26, 52, 104):
                            out.append(_scenario("P-CORE", delta=delta, d=d, rho=rho, n=n, L=L))
        for s in anchors:
            for delta in (0.4, 0.8):
                for effect in ("HALF", "OPPOSED", "REGIME_ONLY"):
                    out.append(_scenario("P-HET", d=s.d, L=s.L, delta=delta, effect=effect))
            for rs, br in ((0.5, 1.0), (1.0, 1.0), (0.8, 0.5)):
                out.append(
                    _scenario("P-SCORE", d=s.d, L=s.L, delta=0.4, score_rho=rs, brier_ratio=br)
                )
            for omega in (0.0, 0.9):
                out.append(_scenario("P-CTRL", d=s.d, L=s.L, delta=0.4, ctrl_omega=omega))
            out.append(
                _scenario("P-TWIN", d=s.d, L=s.L, delta=0.4, twin_fraction=0.4, twin_rho=1.0)
            )
            out.append(_scenario("P-CHURN", d=s.d, L=s.L, delta=0.4, churn_a=0.5))
    else:
        for d in (0.0, 0.15, 0.35):
            for rho in (0.3, 0.9):
                for n in (10, 30):
                    for L in (26, 52, 104):
                        out.append(_scenario("N-CORE", d=d, rho=rho, n=n, L=L))
        out.extend(anchors)
        for family in (
            "N-VOL",
            "N-REGMEAN",
            "N-TWIN",
            "N-MEMSPLIT",
            "N-AR",
            "N-CHURN",
            "N-SEL",
            "N-TAIL",
        ):
            group = [
                s
                for s in scenario_grid("VAL")
                if s.family == family
                and s.L == 52
                and s.rho == 0.6
                and s.n == 10
                and s.d in (0.15, 0.35)
            ]
            out.extend(group)
        for delta in (0.2, 0.4, 0.8, 1.6):
            for d in (0.15, 0.35):
                for L in (26, 52, 104):
                    out.append(_scenario("P-CORE", delta=delta, d=d, L=L))
    unique = {scenario_id(s): s for s in out}
    return tuple(unique[key] for key in sorted(unique))


def family_class(s: Scenario) -> str:
    if s.kind == "POWER":
        return "NOT_APPLICABLE"
    if s.rho > 0.90:
        return "SENSITIVITY"
    if s.family in ("N-CORE", "N-VOL", "N-TWIN", "N-MEMSPLIT", "N-CHURN"):
        return "PLAN_NAMED"
    if s.family == "N-REGMEAN" and s.regime_mean_g <= 0.25 and s.regime_speed == "FAST":
        return "PLAN_NAMED"
    return "SENSITIVITY"


def d_envelope(s: Scenario) -> str:
    for name, limit in zip(ENVELOPES, (0.10, 0.15, 0.25, 0.35, 0.45), strict=True):
        if s.d <= limit:
            return name
    raise ValueError("d outside the declared envelope")


def null_twin_id(s: Scenario) -> str | None:
    if s.kind != "POWER":
        return None
    base = {"d": s.d, "rho": s.rho, "n": s.n, "L": s.L}
    if (
        s.family in ("P-CORE", "P-SCORE", "P-CTRL")
        or s.family == "P-HET"
        and s.effect in ("HALF", "OPPOSED")
    ):
        twin = _scenario("N-CORE", **base)
    elif s.family == "P-HET":
        twin = _scenario("N-VOL", **base)
    elif s.family == "P-TWIN":
        twin = _scenario("N-TWIN", **base, twin_fraction=0.4, twin_rho=s.twin_rho)
    elif s.family == "P-CHURN":
        twin = _scenario("N-CHURN", **base, churn_a=s.churn_a)
    else:
        raise ValueError("unknown power family")
    return scenario_id(twin)


def design_grid() -> tuple[str, ...]:
    ids = []
    for level in READING_LEVELS:
        ids.append(f"T/{level}")
        ids.extend(f"TH/{level}/H{int(h * 100):03d}" for h in (0.60, 0.65, 0.75, 0.85, 0.95))
        ids.extend(f"TH_MC/{level}/H{int(h * 100):03d}" for h in (0.60, 0.65, 0.75, 0.85, 0.95))
        ids.extend(f"SYM_REPL/{level}" for _ in (0,))
    for a, ra in (
        ("A050", "A050"),
        ("A025", "A025"),
        ("A0125", "A0125"),
        ("A0083", "A0083"),
        ("A025", "A050"),
    ):
        ids.extend(f"RA_EXT/{a}/{ra}/K{v:03d}" for v in (50, 75, 100, 125, 150))
        for wh in (104, 208):
            ids.extend(
                f"RA_WM/{a}/{ra}/W{wh}/{'UB' + str(int(ub * 100)) if ub else 'NONE'}"
                for ub in (0, 0.8, 0.95)
            )
    return tuple(sorted(ids))


def focus_designs() -> tuple[str, ...]:
    ids = [
        d
        for d in design_grid()
        if d.startswith(
            ("T/A025", "TH/A025", "TH_MC/A025", "SYM_REPL/A025", "RA_EXT/A025/", "RA_WM/A025/A025/")
        )
    ]
    ids.extend(d for d in design_grid() if d.startswith(("RA_EXT/A025/A050/", "RA_WM/A025/A050/")))
    return tuple(sorted(set(ids)))


def declared_level(design_id: str) -> str:
    parts = design_id.split("/")
    if len(parts) < 2 or parts[1] not in LEVELS:
        raise ValueError("invalid design id")
    if parts[0] in ("RA_EXT", "RA_WM") and len(parts) >= 3:
        return parts[2]
    return parts[1]


def candidates(level: str) -> tuple[str, ...]:
    if level not in LEVELS:
        raise ValueError("invalid level")
    return tuple(
        d
        for d in design_grid()
        if declared_level(d) == level and d.split("/")[0] in ("RA_WM", "TH_MC", "TH", "T")
    )


def reading_label(level: str, envelope: str) -> str:
    if (level, envelope) not in READINGS:
        raise ValueError("invalid reading")
    return READING_LABELS[READINGS.index((level, envelope))]


def seed_key(stage: str, stream: str, subject_id: str, component: str, chunk: int) -> str:
    if (
        stage not in STAGES
        or stream not in STREAMS
        or component not in SEED_COMPONENTS
        or chunk < 0
    ):
        raise ValueError("invalid seed key component")
    return f"{SEED_NAMESPACE}|{stage}|{stream}|{subject_id}|{component}|{chunk:06d}"


def rng_for(key: str) -> np.random.Generator:
    digest = hashlib.sha256(key.encode("ascii")).digest()
    words = [int.from_bytes(digest[i : i + 4], "big") for i in range(0, 32, 4)]
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence(words)))


def all_seed_keys(stage: str, scenario_ids, table_ids, replications, chunking) -> tuple[str, ...]:
    if stage not in STAGES:
        raise ValueError("invalid stage")
    # Accept the manifest-shaped maps and keep the five arguments self-contained.
    n_null = replications.get("n_null", replications.get("null", 0))
    n_power = replications.get("n_power", replications.get("power", 0))
    n_sigma = replications.get("n_cal_sigma0", replications.get("cal_sigma0", 0))
    n_thmc = replications.get("n_cal_thmc", replications.get("cal_thmc", 0))
    c_null = chunking.get("chunk_null", chunking.get("null", 1))
    c_power = chunking.get("chunk_power", chunking.get("power", 1))
    c_thmc = chunking.get("chunk_thmc", chunking.get("thmc", 1))
    keys = []
    for sid in scenario_ids:
        s = parse_scenario_id(sid)
        reps, size = (n_power, c_power) if s.kind == "POWER" else (n_null, c_null)
        chunks = range((reps + size - 1) // size)
        components = (
            ["NOISE_G1"] if s.kind == "SIZE" else ["NOISE_G1", "NOISE_G2", "NOISE_G3", "NOISE_G4"]
        )
        if s.regime_speed != "NONE":
            components.append("REGIME")
        if s.churn_a is not None:
            components.append("MEMBERSHIP")
        for comp in components:
            keys.extend(seed_key(stage, "EVAL", sid, comp, c) for c in chunks)
        if s.kind == "SIZE":
            keys.extend(
                seed_key(stage, "CAL_SIGMA0", sid, "SERIES", c)
                for c in range((n_sigma + c_null - 1) // c_null)
            )
    for table in table_ids:
        for c in range((n_thmc + c_thmc - 1) // c_thmc):
            keys.append(seed_key(stage, "CAL_THMC", table, "SERIES", c))
    if len(keys) != len(set(keys)) or len(
        {hashlib.sha256(k.encode("ascii")).digest() for k in keys}
    ) != len(keys):
        raise Refusal("seed streams are not disjoint")
    return tuple(keys)


def canonical_bytes(obj) -> bytes:
    return (
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
        + "\n"
    ).encode("ascii")


@dataclass
class Panel:
    x: dict[tuple[str, str], np.ndarray]
    member: np.ndarray | None
    y: dict[tuple[str, str], np.ndarray]
    state: np.ndarray | None
    mean_turnover: float | None = None


def _regime_params(speed: str, vol_ratio: float) -> tuple[float, float, float, float, float]:
    """Return high/low persistence, stationary turbulent share, and variance-scaled vols."""
    if speed == "FAST":
        d_hi, d_lo = 8, 32
    elif speed == "SLOW":
        d_hi, d_lo = 26, 104
    else:
        raise ValueError("regime speed must be FAST or SLOW")
    p_hh, p_ll = 1 - 1 / d_hi, 1 - 1 / d_lo
    pi = (1 - p_ll) / ((1 - p_ll) + (1 - p_hh))
    v_lo = 1 / math.sqrt(1 - pi + pi * vol_ratio**2)
    return p_hh, p_ll, pi, v_lo, vol_ratio * v_lo


def pooled_block_means(x: np.ndarray, member: np.ndarray | None) -> np.ndarray:
    if member is None:
        return x.mean(axis=1)
    counts = member.sum(axis=1)
    if np.any(counts == 0):
        raise ValueError("every week must have at least one member")
    return np.where(member, x, 0.0).sum(axis=1) / counts


def _select_membership(
    scores: np.ndarray, eta: np.ndarray, a: float, psi: float, n: int, W: int
) -> tuple[np.ndarray, float | None]:
    reps, n_sup, Q = eta.shape
    latent = np.empty_like(eta)
    latent[..., 0] = eta[..., 0]
    for qtr in range(1, Q):
        latent[..., qtr] = a * latent[..., qtr - 1] + math.sqrt(1 - a**2) * eta[..., qtr]
    z = np.zeros((reps, n_sup, Q), dtype=np.float64)
    for qtr in range(1, Q):
        z[..., qtr] = math.sqrt(QUARTER) * scores[..., QUARTER * (qtr - 1) : QUARTER * qtr].mean(
            axis=2
        )
    u = math.sqrt(psi) * -z + math.sqrt(1 - psi) * latent
    selected = np.zeros((reps, n_sup, Q), dtype=bool)
    order = np.argsort(-u, axis=1, kind="stable")
    selected[np.arange(reps)[:, None, None], order[:, :n, :], np.arange(Q)[None, None, :]] = True
    member = np.repeat(selected, QUARTER, axis=2)[:, :, :W]
    turnover = None
    if Q > 1:
        turnover = float((1 - (selected[:, :, 1:] & selected[:, :, :-1]).sum(axis=1) / n).mean())
    return member, turnover


def simulate_chunk(s: Scenario, *, stage: str, stream: str, chunk: int, reps: int) -> Panel:
    if reps < 1:
        raise ValueError("reps must be positive")
    W = W_HIST_MAX + s.L
    n_sup = 2 * s.n if s.churn_a is not None else s.n
    state = None
    v = np.ones((reps, W), dtype=np.float64)
    m = np.zeros((reps, W), dtype=np.float64)
    if s.regime_speed != "NONE":
        p_hh, p_ll, pi, v_lo, v_hi = _regime_params(s.regime_speed, s.vol_ratio)
        u = rng_for(seed_key(stage, stream, scenario_id(s), "REGIME", chunk)).random((reps, W))
        state = np.empty((reps, W), dtype=bool)
        state[:, 0] = u[:, 0] < pi
        for b in range(1, W):
            prev = state[:, b - 1]
            state[:, b] = np.where(prev, u[:, b] < p_hh, u[:, b] >= p_ll)
        if s.vol_ratio != 1.0:
            v = np.where(state, v_hi, v_lo)
        if s.regime_mean_g != 0:
            m = np.where(state, -(1 - pi) * s.regime_mean_g, pi * s.regime_mean_g)

    dc, di = (s.d, s.d)
    if s.mem == "COMMON_ONLY":
        di = 0.0
    elif s.mem == "IDIO_ONLY":
        dc = 0.0
    Cc, Ci = cholesky_factor(dc, W, s.ar_phi), cholesky_factor(di, W, s.ar_phi)
    fields: dict[int, np.ndarray] = {}
    n_fields = 1 if s.kind == "SIZE" else 4
    for k in range(1, n_fields + 1):
        rg = rng_for(seed_key(stage, stream, scenario_id(s), f"NOISE_G{k}", chunk))
        shape = (reps, 1 + n_sup, W)
        if s.tail_nu is None:
            e = rg.standard_normal(shape)
        else:
            e = rg.standard_t(s.tail_nu, size=shape) / math.sqrt(s.tail_nu / (s.tail_nu - 2))
        common = e[:, 0, :] @ Cc.T
        idio = e[:, 1:, :] @ Ci.T
        if s.twin_fraction and s.twin_rho is not None:
            pairs = math.floor(s.twin_fraction * s.n / 2)
            if pairs:
                original = idio[:, : 2 * pairs : 2, :].copy()
                partner = idio[:, 1 : 2 * pairs : 2, :]
                idio[:, 1 : 2 * pairs : 2, :] = (
                    s.twin_rho * original + math.sqrt(1 - s.twin_rho**2) * partner
                )
        fields[k] = math.sqrt(s.rho) * common[:, None, :] + math.sqrt(1 - s.rho) * idio

    if s.kind == "SIZE":
        values = {("CAND", "S"): v[:, None, :] * fields[1] + m[:, None, :]}
    else:
        rs, omega = s.score_rho, s.ctrl_omega
        cand_ll = fields[1]
        cand_br = rs * fields[1] + math.sqrt(1 - rs**2) * fields[2]
        ctrl_ll = math.sqrt(omega) * fields[1] + math.sqrt(1 - omega) * fields[3]
        ctrl_br = math.sqrt(omega) * cand_br + math.sqrt(1 - omega) * (
            rs * fields[3] + math.sqrt(1 - rs**2) * fields[4]
        )
        effect = np.zeros((reps, n_sup, W), dtype=np.float64)
        if s.effect == "HOMOG":
            effect[:] = -s.delta
        elif s.effect == "HALF":
            effect[:, : n_sup // 2, :] = -2 * s.delta
        elif s.effect == "OPPOSED":
            effect[:, : int(0.8 * n_sup), :] = -1.5 * s.delta
            effect[:, int(0.8 * n_sup) :, :] = s.delta
        elif s.effect == "REGIME_ONLY":
            _, _, pi, _, _ = _regime_params(s.regime_speed, s.vol_ratio)
            effect = np.where(state[:, None, :], -s.delta / pi, 0.0)
        cand_br_effect = effect * s.brier_ratio
        values = {
            ("CAND", "LL"): effect + m[:, None, :] + v[:, None, :] * cand_ll,
            ("CAND", "BR"): cand_br_effect + m[:, None, :] + v[:, None, :] * cand_br,
            ("CTRL", "LL"): m[:, None, :] + v[:, None, :] * ctrl_ll,
            ("CTRL", "BR"): m[:, None, :] + v[:, None, :] * ctrl_br,
        }

    member = None
    turnover = None
    if s.churn_a is not None:
        Q = W // QUARTER
        rg = rng_for(seed_key(stage, stream, scenario_id(s), "MEMBERSHIP", chunk))
        eta = rg.standard_normal((reps, n_sup, Q))
        score = values[("CAND", "LL" if s.kind == "POWER" else "S")]
        member, turnover = _select_membership(score, eta, s.churn_a, s.sel_psi, s.n, W)

    y = {key: pooled_block_means(value, member) for key, value in values.items()}
    return Panel(values, member, y, state, turnover)


def block_t(y_look: np.ndarray, floor: float = 0.0) -> np.ndarray:
    means = y_look.mean(axis=1)
    sd = y_look.std(axis=1, ddof=1)
    return np.divide(
        (means + floor) * np.sqrt(y_look.shape[1]),
        sd,
        out=np.full_like(means, np.inf),
        where=sd > 0,
    )


def allowance_window_means(y_hist: np.ndarray, L: int, w_hist: int, ub: str) -> np.ndarray | None:
    K = w_hist // L
    if K < 2:
        return None
    recent = y_hist[:, -w_hist:]
    means = np.stack(
        [recent[:, w_hist - j * L : w_hist - (j - 1) * L].mean(axis=1) for j in range(1, K + 1)],
        axis=1,
    )
    return means.std(axis=1, ddof=1) * ub_factor(K, ub)


def core_rejects(
    design_id: str, y_by_score: dict[str, np.ndarray], *, L: int, floor: float, sigma0, thmc
) -> np.ndarray | None:
    parts = design_id.split("/")
    core = parts[0]
    if core == "SYM_REPL":
        return None
    if core in ("RA_WM", "RA_EXT"):
        level_k1, level_ra = parts[1], parts[2]
    else:
        level_k1 = parts[1]
        level_ra = None
    reject = None
    for _name, series in y_by_score.items():
        look = series[:, W_HIST_MAX : W_HIST_MAX + L]
        t = block_t(look, floor)
        if core in ("T", "RA_EXT", "RA_WM"):
            this = t <= student_t_quantile(LEVELS[level_k1], L - 1)
        elif core == "TH":
            h_c = int(parts[2][1:]) / 100
            this = (look.mean(axis=1) + floor) / (
                look.std(axis=1, ddof=1) * L ** (h_c - 1)
            ) <= student_t_quantile(LEVELS[level_k1], L - 1)
        elif core == "TH_MC":
            h_c = int(parts[2][1:]) / 100
            this = t <= thmc[L][h_c][level_k1]
        else:
            raise ValueError("unknown core")
        if core == "RA_EXT":
            kappa = int(parts[3][1:]) / 100
            this &= _allowance_rejects(look.mean(axis=1) + floor, level_ra, kappa * sigma0)
        elif core == "RA_WM":
            wh = int(parts[3][1:])
            ub = parts[4]
            allowance = allowance_window_means(series[:, :W_HIST_MAX], L, wh, ub)
            if allowance is None:
                return None
            this &= _allowance_rejects(look.mean(axis=1) + floor, level_ra, allowance)
        reject = this if reject is None else reject & this
    return reject


def _allowance_rejects(adjusted_mean: np.ndarray, level: str, allowance) -> np.ndarray:
    return adjusted_mean <= -normal_quantile(1 - LEVELS[level]) * allowance


def sign_key(
    x_cand_by_score: dict[str, np.ndarray], member: np.ndarray | None, *, L: int, q, m_min: int
):
    first = next(iter(x_cand_by_score.values()))
    if member is None:
        member = np.ones(first.shape, dtype=bool)
    look_member = member[:, :, W_HIST_MAX : W_HIST_MAX + L]
    eligible = look_member.sum(axis=2) >= m_min
    n_eligible = eligible.sum(axis=1)
    events = np.ones(first.shape[:2], dtype=bool)
    for values in x_cand_by_score.values():
        means = np.divide(
            (values[:, :, W_HIST_MAX : W_HIST_MAX + L] * look_member).sum(axis=2),
            look_member.sum(axis=2),
            out=np.zeros(first.shape[:2]),
            where=look_member.sum(axis=2) > 0,
        )
        events &= means < 0
    n_events = (events & eligible).sum(axis=1)
    frac = Fraction(q)
    evaluable = n_eligible > 0
    return (evaluable & (n_events * frac.denominator >= frac.numerator * n_eligible), evaluable)


def sym_repl_rejects(
    x_cand_by_score: dict[str, np.ndarray], member: np.ndarray | None, *, L: int, level: str
) -> np.ndarray:
    first = next(iter(x_cand_by_score.values()))
    if member is None:
        member = np.ones(first.shape, dtype=bool)
    look_member = member[:, :, W_HIST_MAX : W_HIST_MAX + L]
    eligible = look_member.sum(axis=2) > 0
    all_reject = None
    for values in x_cand_by_score.values():
        look = values[:, :, W_HIST_MAX : W_HIST_MAX + L]
        symbol_mean = np.divide(
            (look * look_member).sum(axis=2),
            look_member.sum(axis=2),
            out=np.zeros(first.shape[:2]),
            where=eligible,
        )
        count = eligible.sum(axis=1)
        mean = np.divide(
            (symbol_mean * eligible).sum(axis=1),
            count,
            out=np.zeros(first.shape[0]),
            where=count > 0,
        )
        sd = np.sqrt(
            np.divide(
                ((symbol_mean - mean[:, None]) ** 2 * eligible).sum(axis=1),
                count - 1,
                out=np.zeros(first.shape[0]),
                where=count > 1,
            )
        )
        stat = np.divide(
            mean * np.sqrt(count),
            sd,
            out=np.full(first.shape[0], np.inf),
            where=(count >= 2) & (sd > 0),
        )
        this = (count >= 2) & (
            stat <= student_t_quantile(LEVELS[level], max(first.shape[1] - 1, 1))
        )
        # The degrees of freedom are replication symbols, hence vary by replication.
        for n_e in np.unique(count[count >= 2]):
            mask = count == n_e
            this[mask] = stat[mask] <= student_t_quantile(LEVELS[level], int(n_e) - 1)
        all_reject = this if all_reject is None else all_reject & this
    return all_reject


def _arm(part: dict[tuple[str, str], np.ndarray], arm: str) -> dict[str, np.ndarray]:
    return {score: values for (name, score), values in part.items() if name == arm}


def _sigma_for(s: Scenario, sigma0) -> float:
    """The sigma0 an RA_EXT allowance uses: the null twin's, or a size scenario's own.

    Never a default: a missing value is refused.
    """
    if isinstance(sigma0, dict):
        key = null_twin_id(s) or scenario_id(s)
        if key not in sigma0:
            raise Refusal(f"sigma0 missing for {key}")
        return float(sigma0[key])
    if sigma0 is None:
        raise Refusal(f"sigma0 missing for {scenario_id(s)}")
    return float(sigma0)


class _ChunkEval:
    """Every decision on one chunk, each computed once.

    joint_rejects and count_scenario both use it, so the joint rule exists once.
    """

    def __init__(self, panel: Panel, *, L: int, sigma0, thmc) -> None:
        self.panel, self.L, self.sigma0, self.thmc = panel, L, sigma0, thmc
        self.x = {arm: _arm(panel.x, arm) for arm in ARMS}
        self.y = {arm: _arm(panel.y, arm) for arm in ARMS}
        self._sign: dict = {}
        self._decisions: dict = {}

    def sign(self, q: str, m_min: int) -> tuple[np.ndarray, np.ndarray]:
        key = (q, m_min)
        if key not in self._sign:
            self._sign[key] = sign_key(
                self.x["CAND"], self.panel.member, L=self.L, q=q, m_min=m_min
            )
        return self._sign[key]

    def decision(self, design_id: str, arm: str, floor: float) -> np.ndarray | None:
        """A core's decision on one arm.

        SYM_REPL takes no floor; the control arm is always evaluated with floor 0.
        """
        sym = design_id.split("/")[0] == "SYM_REPL"
        key = (design_id, arm, 0.0 if sym else float(floor))
        if key not in self._decisions:
            if sym:
                level = design_id.split("/")[1]
                value = sym_repl_rejects(self.x[arm], self.panel.member, L=self.L, level=level)
            else:
                value = core_rejects(
                    design_id,
                    self.y[arm],
                    L=self.L,
                    floor=key[2],
                    sigma0=self.sigma0,
                    thmc=self.thmc,
                )
            self._decisions[key] = value
        return self._decisions[key]

    def parts(self, design_id: str, variant_id: str):
        """(core, sign_fail, control_fail) for one cell, or None when the cell is NOT_ESTIMABLE."""
        if variant_id not in VARIANT_TABLE:
            raise ValueError("unknown variant")
        spec = VARIANT_TABLE[variant_id]
        core = self.decision(design_id, "CAND", spec["floor"])
        if core is None:
            return None
        sign_fail = np.zeros_like(core)
        if spec["q"] is not None:
            m_min = math.ceil(self.L / 4) if spec["m_min"] == "ceil(L/4)" else spec["m_min"]
            sign_fail = ~self.sign(spec["q"], m_min)[0]
        control_fail = np.zeros_like(core)
        if spec["control"]:
            control = self.decision(design_id, "CTRL", 0.0)
            if control is None:
                return None
            control_fail = control
        return core, sign_fail, control_fail


def joint_rejects(
    design_id: str, variant_id: str, panel: Panel, *, L: int, sigma0, thmc
) -> np.ndarray | None:
    parts = _ChunkEval(panel, L=L, sigma0=sigma0, thmc=thmc).parts(design_id, variant_id)
    if parts is None:
        return None
    core, sign_fail, control_fail = parts
    return core & ~sign_fail & ~control_fail


def thmc_table(L: int, h_c: float, *, stage: str, n_series: int, chunk: int) -> dict[str, float]:
    if n_series < 1 or chunk < 1:
        raise ValueError("series and chunk must be positive")
    C = cholesky_factor(h_c - 0.5, L)
    stats = []
    for idx, start in enumerate(range(0, n_series, chunk)):
        size = min(chunk, n_series - start)
        z = (
            rng_for(
                seed_key(stage, "CAL_THMC", f"THMC/L={L:03d}/H={h_c:.2f}", "SERIES", idx)
            ).standard_normal((size, L))
            @ C.T
        )
        sd = z.std(axis=1, ddof=1)
        stats.extend(
            np.divide(z.mean(axis=1), sd / math.sqrt(L), out=np.full(size, np.inf), where=sd > 0)
        )
    vals = np.asarray(stats)
    result = {}
    for level in READING_LEVELS:
        k = max(1, math.floor(LEVELS[level] * n_series)) - 1
        result[level] = float(np.partition(vals, k)[k])
    return result


def sigma0_for(s: Scenario, *, stage: str, n_reps: int, chunk: int) -> float:
    means = []
    for idx, start in enumerate(range(0, n_reps, chunk)):
        panel = simulate_chunk(
            s, stage=stage, stream="CAL_SIGMA0", chunk=idx, reps=min(chunk, n_reps - start)
        )
        means.extend(panel.y[("CAND", "S")][:, W_HIST_MAX : W_HIST_MAX + s.L].mean(axis=1))
    return float(np.std(means, ddof=1))


def count_scenario(
    s: Scenario,
    *,
    stage: str,
    n_reps: int,
    chunk: int,
    designs,
    focus,
    sigma0,
    thmc,
    chunk_indices=None,
) -> dict:
    """Integer counts for one scenario over its chunks (spec §10 step 5).

    Returns `scenario_id`, `n_reps` (replications counted), `counts` keyed
    `<design>|<variant>|<suffix>` with the suffixes `rejections`, `core_rejections`,
    `sign_vetoes` and `control_vetoes` (plus `<design>|core_and_sign` for a size
    scenario), `not_estimable` (sorted `<design>|<variant>`), `sign_not_evaluable` and
    `mean_turnover`. A missing sigma0 is refused, never defaulted.
    """
    if n_reps < 1 or chunk < 1:
        raise ValueError("n_reps and chunk must be positive")
    indices = (
        list(chunk_indices)
        if chunk_indices is not None
        else list(range((n_reps + chunk - 1) // chunk))
    )
    sid = scenario_id(s)
    sigma = _sigma_for(s, sigma0)
    m_min_default = math.ceil(s.L / 4)
    counts: dict[str, int] = {}
    not_estimable: set[str] = set()
    done, turnover_weighted, sign_not_evaluable = 0, 0.0, 0
    for idx in indices:
        panel = simulate_chunk(
            s, stage=stage, stream="EVAL", chunk=idx, reps=min(chunk, n_reps - idx * chunk)
        )
        reps_in_chunk = next(iter(panel.y.values())).shape[0]
        done += reps_in_chunk
        if panel.mean_turnover is not None:
            turnover_weighted += panel.mean_turnover * reps_in_chunk
        ev = _ChunkEval(panel, L=s.L, sigma0=sigma, thmc=thmc)
        sign_default, evaluable = ev.sign("4/5", m_min_default)
        sign_not_evaluable += int((~evaluable).sum())
        for design in designs:
            variants = (
                ("V_CORE",)
                if s.kind == "SIZE"
                else (VARIANTS if design in focus else ("V_CORE", "V_J0"))
            )
            for variant in variants:
                prefix = f"{design}|{variant}"
                parts = ev.parts(design, variant)
                if parts is None:
                    not_estimable.add(prefix)
                    continue
                core, sign_fail, control_fail = parts
                pre_control = core & ~sign_fail
                for suffix, values in (
                    ("rejections", pre_control & ~control_fail),
                    ("core_rejections", core),
                    ("sign_vetoes", core & sign_fail),
                    ("control_vetoes", pre_control & control_fail),
                ):
                    key = f"{prefix}|{suffix}"
                    counts[key] = counts.get(key, 0) + int(values.sum())
            if s.kind == "SIZE":
                core = ev.decision(design, "CAND", 0.0)
                if core is not None:
                    key = f"{design}|core_and_sign"
                    counts[key] = counts.get(key, 0) + int((core & sign_default).sum())
    return {
        "scenario_id": sid,
        "n_reps": done,
        "counts": counts,
        "not_estimable": sorted(not_estimable),
        "sign_not_evaluable": sign_not_evaluable,
        "mean_turnover": turnover_weighted / done if s.churn_a is not None and done else None,
    }


# Classification and decision layer.  Inputs are the in-memory equivalents of
# the public CELLS.jsonl rows; these helpers deliberately have no I/O or RNG.
def classify_size(x: int | None, n: int, alpha: float, bound: str, m_sim: int) -> dict:
    if bound not in BOUNDS or not 0 < alpha < 1 or m_sim < 1:
        raise ValueError("invalid size classification arguments")
    if x is None:
        return {
            "status": "NOT_ESTIMABLE",
            "rate": None,
            "cp95": None,
            "cp_sim_lower": None,
            "verdict": "NOT_ESTIMABLE",
            "confirmed_invalid": False,
        }
    if n <= 0 or not 0 <= x <= n:
        raise ValueError("invalid rejection count")
    rate = x / n
    lo, hi = clopper_pearson(x, n)
    limit = {"STRICT": alpha, "TOL20": 1.2 * alpha, "CEIL2X": 2 * alpha}[bound]
    verdict = "VALID" if hi <= limit else "INVALID" if lo > limit else "INCONCLUSIVE"
    simultaneous = cp_lower(x, n, 0.025 / (2 * m_sim))
    return {
        "status": "ESTIMATED",
        "rate": rate,
        "cp95": [lo, hi],
        "cp_sim_lower": simultaneous,
        "verdict": verdict,
        "confirmed_invalid": simultaneous > limit,
    }


def classify_power(x: int | None, n: int, target: str, null_twin_verdict: str) -> str:
    if target not in POWER_TARGETS or null_twin_verdict not in VERDICTS:
        raise ValueError("invalid power classification arguments")
    if null_twin_verdict != "VALID":
        return null_twin_verdict
    if x is None:
        return "NOT_ESTIMABLE"
    if n <= 0 or not 0 <= x <= n:
        raise ValueError("invalid rejection count")
    lo, hi = clopper_pearson(x, n)
    threshold = {"P50": 0.50, "P80": 0.80, "P90": 0.90}[target]
    return (
        "VALID" if lo >= threshold else "INSUFFICIENT_POWER" if hi < threshold else "INCONCLUSIVE"
    )


def _scenario_rows(cells):
    """Yield (scenario metadata, cell) from scenario records or flat rows."""
    for row in cells:
        if "cells" in row:
            for cell in row["cells"]:
                yield row, cell
        else:
            yield row, row


def _params(row):
    params = row.get("params", {})
    if params:
        return params
    try:
        s = parse_scenario_id(row["scenario_id"])
        return {**s.__dict__, "L": s.L}
    except (KeyError, ValueError):
        return {}


def _label(row):
    p = _params(row)
    return (
        row.get("family_class", family_class(Scenario(**p)) if "family" in p else "NOT_APPLICABLE"),
        row.get("d_envelope", d_envelope(Scenario(**p)) if "family" in p else "E95"),
        p,
    )


_ENVELOPE_LIMITS = dict(zip(ENVELOPES, (0.10, 0.15, 0.25, 0.35, 0.45), strict=True))
EFFECT_PAIRS = ((0.20, 0.10), (0.40, 0.20), (0.80, 0.40), (1.60, 0.80))
VAL_MINIMUMS = {
    "n_null": 100_000,
    "n_power": 4_000,
    "n_cal_sigma0": 20_000,
    "n_cal_thmc": 1_000_000,
}
DEV_MINIMUMS = {"n_null": 20_000, "n_power": 2_000, "n_cal_sigma0": 20_000, "n_cal_thmc": 1_000_000}
_ADDITIONS_KEYS = ("grid_additions", "replications", "defect_repairs", "notes")
_SELECTION_KEYS = ("level", "envelope", "primary", "fallback", "dev_no_candidate")


def _size_verdict(cell, bound: str) -> str:
    """A size cell's verdict at a bound; a cell without one is a defect, never skipped."""
    verdict = (cell.get("size_verdicts") or {}).get(bound)
    if verdict is None:
        if cell.get("status") == "NOT_ESTIMABLE":
            return "NOT_ESTIMABLE"
        raise ValueError(f"size cell without a {bound} verdict: {cell.get('design_id')}")
    if verdict not in VERDICTS:
        raise ValueError(f"unknown size verdict: {verdict}")
    return verdict


def _is_size(row) -> bool:
    return row.get("kind", _params(row).get("kind")) == "SIZE"


def size_rollups(cells, bounds=BOUNDS, envelopes=ENVELOPES, class_sets=CLASS_SETS):
    groups: dict = {}
    for row, cell in _scenario_rows(cells):
        if not _is_size(row):
            continue
        cls, _, p = _label(row)
        d, L = float(p.get("d", 0)), int(p.get("L", 0))
        did = cell.get("design_id")
        for bound in bounds:
            verdict = _size_verdict(cell, bound)
            for env in envelopes:
                if d > _ENVELOPE_LIMITS[env]:
                    continue
                for cset in class_sets:
                    if cset not in ("ALL", cls):
                        continue
                    for length in ("ALL", f"{L:03d}"):
                        groups.setdefault((did, bound, env, cset, length), []).append(
                            (row, cell, verdict)
                        )
    out = []
    for (did, bound, env, cset, length), vals in sorted(groups.items()):
        counts = {
            v: sum(x[2] == v for x in vals)
            for v in ("VALID", "INVALID", "INCONCLUSIVE", "NOT_ESTIMABLE")
        }
        status = (
            "VALID"
            if vals and counts["VALID"] == len(vals)
            else "INVALID"
            if counts["INVALID"]
            else "UNRESOLVED"
        )
        worst = max(vals, key=lambda x: x[1].get("rate") if x[1].get("rate") is not None else -1)
        out.append(
            {
                "design_id": did,
                "bound": bound,
                "envelope": env,
                "class_set": cset,
                "L": length,
                "status": status,
                "n_cells": len(vals),
                "n_valid": counts["VALID"],
                "n_invalid": counts["INVALID"],
                "n_inconclusive": counts["INCONCLUSIVE"],
                "n_not_estimable": counts["NOT_ESTIMABLE"],
                "confirmed_invalid": any(
                    (c.get("confirmed_invalid") or {}).get(bound, False) for _, c, _ in vals
                ),
                "worst": {
                    "scenario_id": worst[0].get("scenario_id"),
                    "rate": worst[1].get("rate"),
                    "cp95": worst[1].get("cp95"),
                },
                "invalid_cells": sorted(
                    r.get("scenario_id", "") for r, c, v in vals if v == "INVALID"
                )[:20],
            }
        )
    return out


def _dependence_match(p, dep):
    d, rho = float(p.get("d", 0)), float(p.get("rho", 0))
    return (
        (d == 0.15 and rho == 0.60)
        if dep == "CENTRAL"
        else (d <= 0.15 if dep == "WORST_E65" else True)
    )


def _p_core_cells(cells):
    for row, cell in _scenario_rows(cells):
        p = _params(row)
        if row.get("kind", p.get("kind")) == "POWER" and p.get("family") == "P-CORE":
            yield p, cell


def power_rollups(cells):
    """Spec §11 power roll-ups.

    An entry needs both required cells for every (d, rho) present; otherwise it is omitted.
    """
    groups: dict = {}
    for p, cell in _p_core_cells(cells):
        delta, L, n = float(p["delta"]), int(p["L"]), int(p["n"])
        dr = (float(p["d"]), float(p["rho"]))
        verdicts = cell.get("power_verdicts") or {}
        for pair in EFFECT_PAIRS:
            for target, value in (("P80", pair[0]), ("P50", pair[1])):
                if abs(delta - value) > 1e-9:
                    continue
                for dep in DEPENDENCE_CONVENTIONS:
                    if _dependence_match(p, dep):
                        key = (cell["design_id"], cell["variant_id"], pair, L, n, dep)
                        group = groups.setdefault(key, {"P80": {}, "P50": {}})
                        group[target][dr] = verdicts.get(target)
    out = []
    for (did, var, pair, L, n, dep), group in sorted(groups.items(), key=lambda x: str(x[0])):
        if not group["P80"] or set(group["P80"]) != set(group["P50"]):
            continue
        vals = list(group["P80"].values()) + list(group["P50"].values())
        status = (
            "NOT_CREDITED"
            if any(v in ("INVALID", "NOT_ESTIMABLE", None) for v in vals)
            else "INSUFFICIENT"
            if "INSUFFICIENT_POWER" in vals
            else "INCONCLUSIVE"
            if "INCONCLUSIVE" in vals
            else "MET"
        )
        out.append(
            {
                "design_id": did,
                "variant_id": var,
                "effect_pair": list(pair),
                "L": f"{L:03d}",
                "n": n,
                "dependence": dep,
                "status": status,
            }
        )
    return out


def minimum_detectable_effects(cells):
    """Smallest delta whose required cells are all VALID at P80 (and at P50); null if none."""
    index: dict = {}
    for p, cell in _p_core_cells(cells):
        verdicts = cell.get("power_verdicts") or {}
        for dep in DEPENDENCE_CONVENTIONS:
            if _dependence_match(p, dep):
                key = (cell["design_id"], cell["variant_id"], int(p["L"]), int(p["n"]), dep)
                index.setdefault(key, {}).setdefault(float(p["delta"]), []).append(verdicts)
    out = []
    for (did, var, L, n, dep), by_delta in sorted(index.items(), key=lambda x: str(x[0])):
        mde = {}
        for target in ("P80", "P50"):
            passing = [
                delta
                for delta, verdicts in by_delta.items()
                if verdicts and all(v.get(target) == "VALID" for v in verdicts)
            ]
            mde[target] = min(passing) if passing else None
        out.append(
            {
                "design_id": did,
                "variant_id": var,
                "L": f"{L:03d}",
                "n": n,
                "dependence": dep,
                "mde_p80": mde["P80"],
                "mde_p50": mde["P50"],
            }
        )
    return out


def self_checks(cells, *, expected_scenarios: int, expected_cells: int):
    """PREREG §5.3, exactly: SC-1 to SC-3 on the N-CORE cells present; SC-4 against the manifest."""
    rows = list(cells)
    found: dict = {"SC-1": [], "SC-2": [], "SC-3": []}
    for row, cell in _scenario_rows(rows):
        p = _params(row)
        if p.get("family") != "N-CORE" or not _is_size(row):
            continue
        d, rho = float(p.get("d", 0)), float(p.get("rho", 0))
        design = cell.get("design_id", "")
        verdict = (cell.get("size_verdicts") or {}).get("TOL20")
        sid = row.get("scenario_id", "")
        if design == "T/A025" and d == 0:
            found["SC-1"].append((sid, verdict == "VALID"))
        if design == "SYM_REPL/A025" and d == 0 and rho >= 0.6:
            found["SC-2"].append((sid, verdict == "INVALID"))
        if design == "SYM_REPL/A025" and d == 0 and rho == 0:
            found["SC-2"].append((sid, verdict is not None and verdict != "INVALID"))
        if d > 0 and design == f"TH_MC/A025/H{round((d + 0.5) * 100):03d}":
            found["SC-3"].append((sid, verdict == "VALID"))
    checks = []
    for check_id in ("SC-1", "SC-2", "SC-3"):
        failed = sorted(sid for sid, ok in found[check_id] if not ok)
        checks.append(
            {
                "id": check_id,
                "status": "FAIL" if failed else "PASS",
                "cells": len(found[check_id]),
                "failed_cells": failed,
            }
        )
    n_cells = sum(len(row["cells"]) if "cells" in row else 1 for row in rows)
    mismatch = []
    if len(rows) != expected_scenarios:
        mismatch.append(f"scenarios {len(rows)} != {expected_scenarios}")
    if n_cells != expected_cells:
        mismatch.append(f"cells {n_cells} != {expected_cells}")
    checks.append(
        {
            "id": "SC-4",
            "status": "FAIL" if mismatch else "PASS",
            "cells": n_cells,
            "failed_cells": mismatch,
        }
    )
    return checks


def select_designs(stage, cells):
    if stage != "DEV":
        raise Refusal("not a development report")
    flat = list(_scenario_rows(list(cells)))
    meta: dict = {}
    for row, _cell in flat:
        if id(row) not in meta:
            p = _params(row)
            kind = row.get("kind", p.get("kind"))
            cls = _label(row)[0] if kind == "SIZE" else None
            meta[id(row)] = (
                kind,
                cls,
                float(p.get("d", 0)),
                int(p.get("L", 0)),
                p.get("family"),
                row.get("scenario_id"),
            )
    size_cells: dict = {}  # (design, L) -> [(d, cell)] for PLAN_NAMED size rows
    power_cells: dict = {}  # P-CORE scenario id -> (L, d, {design: {variant: cell}})
    for row, cell in flat:
        kind, cls, d, L, family, sid = meta[id(row)]
        if kind == "SIZE" and cls == "PLAN_NAMED":
            size_cells.setdefault((cell.get("design_id"), L), []).append((d, cell))
        if family == "P-CORE":
            if sid not in power_cells:
                power_cells[sid] = (L, d, {})
            power_cells[sid] = (L, d, power_cells[sid][2])
            by_design = power_cells[sid][2].setdefault(cell.get("design_id"), {})
            by_design[cell.get("variant_id")] = cell
    results = []
    for level, envelope in READINGS:
        limit = _ENVELOPE_LIMITS[envelope]
        alpha = LEVELS[level]
        scored = []
        scenarios = [entry for entry in power_cells.values() if entry[1] <= limit]
        for design in candidates(level):
            pass_l = []
            for L in (26, 52, 104):
                at = [c for d, c in size_cells.get((design, L), []) if d <= limit]
                if at and all(
                    c.get("status") == "ESTIMATED"
                    and c.get("rate") is not None
                    and c["rate"] <= 1.2 * alpha
                    for c in at
                ):
                    pass_l.append(f"{L:03d}")
            passed = {int(x) for x in pass_l}
            score, core = [], []
            for L, _d, by_design in scenarios:
                if L not in passed:
                    score.append(0.0)
                    core.append(0.0)
                    continue
                by_variant = by_design.get(design, {})
                score.append(float(by_variant.get("V_J0", {}).get("rate") or 0.0))
                core.append(float(by_variant.get("V_CORE", {}).get("rate") or 0.0))
            scored.append(
                {
                    "design_id": design,
                    "screen_pass_L": pass_l,
                    "score": sum(score) / len(scenarios) if scenarios else 0.0,
                    "score_core": sum(core) / len(scenarios) if scenarios else 0.0,
                }
            )
        priority = {"RA_WM": 0, "TH_MC": 1, "TH": 2, "T": 3}

        def key(candidate, order=priority):
            return (
                -candidate["score"],
                order[candidate["design_id"].split("/")[0]],
                candidate["design_id"],
            )

        positive = sorted((x for x in scored if x["score"] > 0), key=key)
        if not positive:
            primary = f"RA_WM/{level}/{level}/W208/UB95"
            fallback = f"TH_MC/{level}/H095"
            no = True
        else:
            primary = positive[0]["design_id"]
            core_type = primary.split("/")[0]
            fallback = next(
                (x["design_id"] for x in positive[1:] if x["design_id"].split("/")[0] != core_type),
                None,
            )
            no = False
        results.append(
            {
                "level": level,
                "envelope": envelope,
                "rule": SELECTION_RULE_ID,
                "candidates": scored,
                "primary": primary,
                "fallback": fallback,
                "dev_no_candidate": no,
            }
        )
    return results


def _check_additions(additions) -> dict:
    """The additions file of §12.4: only its four keys; size scenarios only; larger N only."""
    additions = {} if additions is None else additions
    if not isinstance(additions, dict) or set(additions) - set(_ADDITIONS_KEYS):
        raise Refusal("unknown field")
    frozen = {scenario_id(s) for s in scenario_grid("VAL")}
    grid, seen = [], set()
    for item in additions.get("grid_additions", []):
        if not isinstance(item, dict) or set(item) != {"scenario_id", "reason"}:
            raise Refusal("unknown field")
        try:
            scenario = parse_scenario_id(item["scenario_id"])
        except (TypeError, ValueError) as exc:
            raise Refusal("invalid scenario id") from exc
        if scenario.kind != "SIZE":
            raise Refusal("only size scenarios may be added")
        sid = scenario_id(scenario)
        if sid in seen or sid in frozen:
            raise Refusal("duplicate scenario")
        seen.add(sid)
        grid.append({"scenario_id": sid, "reason": str(item["reason"])})
    replications = additions.get("replications", {})
    if not isinstance(replications, dict) or set(replications) - set(VAL_MINIMUMS):
        raise Refusal("unknown field")
    for key, value in replications.items():
        if type(value) is not int or value < VAL_MINIMUMS[key]:
            raise Refusal("validation grid is incomplete")
    repairs = additions.get("defect_repairs", [])
    if not isinstance(repairs, list) or any(
        not isinstance(r, dict) or set(r) != {"description", "test", "commit"} for r in repairs
    ):
        raise Refusal("unknown field")
    notes = additions.get("notes", "")
    if not isinstance(notes, str):
        raise Refusal("unknown field")
    return {
        "grid_additions": grid,
        "replications": dict(replications),
        "defect_repairs": [dict(r) for r in repairs],
        "notes": notes,
    }


def build_dev_decisions(dev_runs, additions=None):
    extra = _check_additions(additions)
    runs = list(dev_runs)
    if not runs or any(not isinstance(r, dict) or r.get("stage") != "DEV" for r in runs):
        raise Refusal("not a development report")
    ordered = sorted(runs, key=lambda r: r["started_utc"])
    recorded = [
        {
            k: run[k]
            for k in ("dev_manifest_sha256", "dev_report_sha256", "code_sha256", "started_utc")
        }
        | {"selections": select_designs("DEV", run["cells"])}
        for run in ordered
    ]
    return {
        "schema": "ucpe.exp04_stage1.dev_decisions.v1",
        "dev_runs": recorded,
        "selection_source": recorded[-1]["dev_report_sha256"],
        "selections": [{k: s[k] for k in _SELECTION_KEYS} for s in recorded[-1]["selections"]],
        **extra,
    }


def outcomes(selections, size_rollups, power_rollups, cells, checks):
    checks_failed = any(c.get("status") != "PASS" for c in checks)
    size = list(size_rollups)
    power = list(power_rollups)
    flat = list(_scenario_rows(cells))
    result = []
    for level, envelope in READINGS:
        sel = next(
            (s for s in selections if s.get("level") == level and s.get("envelope") == envelope),
            None,
        )
        if sel is None:
            raise Refusal("selection is incomplete")
        primary, fallback = sel["primary"], sel.get("fallback")
        consulted = [primary]
        used = primary

        def valid_l(design, reading_envelope=envelope):
            return sorted(
                {
                    r["L"]
                    for r in size
                    if r.get("design_id") == design
                    and r.get("bound") == "TOL20"
                    and r.get("envelope") == reading_envelope
                    and r.get("class_set") == "PLAN_NAMED"
                    and r.get("status") == "VALID"
                    and r.get("L") != "ALL"
                }
            )

        ls = valid_l(primary)
        if not ls and fallback is not None:
            consulted.append(fallback)
            used = fallback
            ls = valid_l(fallback)
        met = []
        met_core = []
        if checks_failed:
            outcome = "STOP_HARNESS_DEFECT"
        elif not ls:
            outcome = (
                "STOP_SIZE_UNCONTROLLED"
                if any(
                    r.get("design_id") in consulted
                    and r.get("bound") == "TOL20"
                    and r.get("envelope") == envelope
                    and r.get("class_set") == "PLAN_NAMED"
                    and r.get("status") == "INVALID"
                    and r.get("confirmed_invalid")
                    for r in size
                )
                else "STOP_INCONCLUSIVE"
            )
        else:
            dep = "WORST_E65" if envelope == "E65" else "WORST_E85"
            ps = [
                r
                for r in power
                if r.get("design_id") == used and r.get("dependence") == dep and r.get("L") in ls
            ]
            j = [r for r in ps if r.get("variant_id") == "V_J0"]
            c = [r for r in ps if r.get("variant_id") == "V_CORE"]
            met = [
                {"L": r["L"], "n": r["n"], "effect_pair": r["effect_pair"]}
                for r in j
                if r["status"] == "MET"
            ]
            met_core = [
                {"L": r["L"], "n": r["n"], "effect_pair": r["effect_pair"]}
                for r in c
                if r["status"] == "MET"
            ]
            if met:
                outcome = "STAGE1_PASS_CONDITIONAL"
            elif (
                j
                and all(r["status"] == "INSUFFICIENT" for r in j)
                and c
                and all(r["status"] == "INSUFFICIENT" for r in c)
            ):
                outcome = "STOP_INSUFFICIENT_POWER"
            elif j and all(r["status"] == "INSUFFICIENT" for r in j) and met_core:
                outcome = "STOP_INSUFFICIENT_POWER_VETO_KEYS"
            else:
                outcome = "STOP_INCONCLUSIVE"
        # PREREG §5.4 step 5: always attached, whatever the outcome, for the design in use.
        sensitivity = next(
            (
                r
                for r in size
                if r.get("design_id") == used
                and r.get("bound") == "TOL20"
                and r.get("envelope") == envelope
                and r.get("class_set") == "SENSITIVITY"
                and r.get("L") == "ALL"
            ),
            None,
        )
        limit = _ENVELOPE_LIMITS[envelope]
        sensitivity_invalid = sorted(
            row.get("scenario_id", "")
            for row, cell in flat
            if _is_size(row)
            and cell.get("design_id") == used
            and _label(row)[0] == "SENSITIVITY"
            and float(_params(row).get("d", 0)) <= limit
            and (cell.get("size_verdicts") or {}).get("TOL20") == "INVALID"
        )
        result.append(
            {
                "label": reading_label(level, envelope),
                "level": level,
                "envelope": envelope,
                "bound": "TOL20",
                "result": outcome,
                "consulted": consulted,
                "design_used": used if ls else None,
                "valid_L": ls,
                "met": met,
                "met_core": met_core,
                "reasons": [],
                "sensitivity_status": sensitivity["status"] if sensitivity else None,
                "sensitivity_invalid_cells": sensitivity_invalid,
            }
        )
    return result


if __name__ == "__main__":
    raise SystemExit(main())
