"""Synthetic-only EXP-04 stage-1 null design identities and numerics."""

from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
from dataclasses import dataclass
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
        for d in (0.0, 0.05, 0.10, 0.15, 0.25, 0.35):
            for rho in (0.3, 0.6, 0.9, 0.95, 0.99):
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
