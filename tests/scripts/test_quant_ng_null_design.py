"""Known-answer tests for EXP-04 stage-1 identity and numeric primitives."""

import ast
from pathlib import Path

import numpy as np
import pytest

from scripts import quant_ng_null_design as q


@pytest.mark.parametrize(
    "df,expected",
    [(10, 2.228139), (25, 2.059539), (30, 2.042272), (60, 2.000298), (120, 1.979930)],
    ids=["df10", "df25", "df30", "df60", "df120"],
)
def test_kat_n1_student_t_quantile(df, expected):
    assert q.student_t_quantile(0.975, df) == pytest.approx(expected, abs=1e-6)


@pytest.mark.parametrize(
    "df,expected",
    [
        (25, [-1.7081408, -2.0595386, -2.3846102, -2.5659786]),
        (51, [-1.6752850, -2.0075838, -2.3095117, -2.4755143]),
        (103, [-1.6597823, -1.9832641, -2.2746407, -2.4337079]),
        (3, [-2.3533634, -3.1824463, -4.1765348, -4.8566573]),
        (4, [-2.1318468, -2.7764451, -3.4954059, -3.9607865]),
    ],
    ids=["df25", "df51", "df103", "df3", "df4"],
)
def test_kat_n2_student_t_lower_quantiles(df, expected):
    for level, value in zip(q.READING_LEVELS, expected, strict=True):
        assert q.student_t_quantile(q.LEVELS[level], df) == pytest.approx(value, abs=1e-6)


def test_kat_n3_normal_quantile():
    assert [q.normal_quantile(1 - q.LEVELS[x]) for x in q.READING_LEVELS] == pytest.approx(
        [1.6448536, 1.9599640, 2.2414027, 2.3939798], abs=1e-6
    )


@pytest.mark.parametrize(
    "p,expected",
    [
        (0.05, [0.0039321, 0.3518463, 2.1673499]),
        (0.2, [0.0641848, 1.0051740, 3.8223219]),
        (0.5, [0.4549364, 2.3659739, 6.3458112]),
    ],
    ids=["p05", "p20", "p50"],
)
def test_kat_n4_chi2_quantile(p, expected):
    assert [q.chi2_quantile(p, df) for df in (1, 3, 7)] == pytest.approx(expected, abs=1e-6)


@pytest.mark.parametrize(
    "ub,expected",
    [("UB80", [3.947154, 1.727587, 1.353273]), ("UB95", [15.947239, 2.920009, 1.797151])],
    ids=["ub80", "ub95"],
)
def test_kat_n5_upper_bound_factor(ub, expected):
    assert [q.ub_factor(k, ub) for k in (2, 4, 8)] == pytest.approx(expected, abs=1e-6)
    assert q.ub_factor(2, "NONE") == 1


@pytest.mark.parametrize(
    "x,n,expected",
    [
        (0, 10, (0, 0.308497108)),
        (10, 10, (0.691502892, 1)),
        (5, 10, (0.187086028, 0.812913972)),
        (1, 20, (0.001265089, 0.248732763)),
        (25, 1000, (0.016242536, 0.036684823)),
        (500, 20000, (0.022880525, 0.027259039)),
        (600, 20000, (0.027679350, 0.032458570)),
        (700, 20000, (0.032495778, 0.037640541)),
    ],
    ids=[
        "zero",
        "all",
        "five",
        "one_of_twenty",
        "25_of_1000",
        "500_of_20000",
        "600_of_20000",
        "700_of_20000",
    ],
)
def test_kat_n6_clopper_pearson(x, n, expected):
    assert q.clopper_pearson(x, n) == pytest.approx(expected, abs=1e-8)


@pytest.mark.parametrize(
    "d,expected",
    [
        (0.1, [0.111111111, 0.064327485]),
        (0.15, [0.176470588, 0.109697933]),
        (0.25, [0.333333333, 0.238095238]),
        (0.35, [0.538461538, 0.440559441]),
        (0.45, [0.818181818, 0.765395894]),
    ],
    ids=["d10", "d15", "d25", "d35", "d45"],
)
def test_kat_n7_arfima_acf(d, expected):
    assert q.arfima_acf(d, 3)[1:] == pytest.approx(expected, abs=1e-9)


@pytest.mark.parametrize(
    "d,expected", [(0.0, 0.300000), (0.15, 0.476354), (0.35, 0.757219)], ids=["d0", "d15", "d35"]
)
def test_kat_n7_ar_overlay(d, expected):
    assert q.arfima_acf(d, 2, 0.3)[1] == pytest.approx(expected, abs=1e-6)


@pytest.mark.parametrize(
    "d,L,expected",
    [
        (0.1, 104, 0.022794191),
        (0.15, 26, 0.093914858),
        (0.15, 52, 0.057751370),
        (0.35, 52, 0.279435082),
        (0.45, 104, 0.603611587),
    ],
    ids=["d10_l104", "d15_l26", "d15_l52", "d35_l52", "d45_l104"],
)
def test_kat_n8_window_mean_variance(d, L, expected):
    assert q.window_mean_variance(q.arfima_acf(d, L), L) == pytest.approx(expected, abs=1e-8)


@pytest.mark.parametrize(
    "d,expected",
    [
        (0.0, [1.3454, 1.3541, 1.3584]),
        (0.15, [1.9904, 2.2148, 2.4604]),
        (0.35, [3.4021, 4.3396, 5.5325]),
    ],
    ids=["d0", "d15", "d35"],
)
def test_kat_n8_window_variance_ar(d, expected):
    assert [
        np.sqrt(L * q.window_mean_variance(q.arfima_acf(d, L, 0.3), L)) for L in (26, 52, 104)
    ] == pytest.approx(expected, abs=1e-3)


def test_kat_n9_regime_constants():
    for speed, hi, lo in (("FAST", 0.875, 0.96875), ("SLOW", 25 / 26, 103 / 104)):
        dhi, dlo = (8, 32) if speed == "FAST" else (26, 104)
        phh, pll = 1 - 1 / dhi, 1 - 1 / dlo
        pi = (1 - pll) / ((1 - pll) + (1 - phh))
        assert (phh, pll, pi) == pytest.approx((hi, lo, 0.2))
    vlo = 1 / np.sqrt(0.8 + 0.2 * 9)
    assert (vlo, 3 * vlo) == pytest.approx((0.6201737, 1.8605210), abs=1e-6)


def test_kat_g1_grid_counts():
    val, dev = q.scenario_grid("VAL"), q.scenario_grid("DEV")
    assert len(val) == 975 and len(dev) == 101
    assert sum(s.kind == "SIZE" for s in val) == 588
    assert sum(s.kind == "POWER" for s in val) == 387
    assert len(q.design_grid()) == 103 and len(q.focus_designs()) == 34
    assert len(q.VARIANTS) == 12
    assert len(val) * 103 - 588 * 103 == 39861


def test_kat_g2_scenario_id_bijection_and_twins():
    for stage in ("DEV", "VAL"):
        for scenario in q.scenario_grid(stage):
            sid = q.scenario_id(scenario)
            assert q.parse_scenario_id(sid) == scenario
    ids = {q.scenario_id(s) for s in q.scenario_grid("VAL")}
    for scenario in q.scenario_grid("VAL"):
        twin = q.null_twin_id(scenario)
        if twin:
            assert twin in ids
    with pytest.raises(ValueError):
        q.parse_scenario_id("N-CORE/garbage")


def test_kat_d2_keys_disjoint_across_stages_streams_and_subjects():
    ids = [q.scenario_id(s) for s in q.scenario_grid("DEV")[:4]]
    args = (
        {"n_null": 10, "n_power": 4, "n_cal_sigma0": 4, "n_cal_thmc": 10},
        {"chunk_null": 3, "chunk_power": 2, "chunk_thmc": 4},
    )
    dev = q.all_seed_keys("DEV", ids, ["THMC/L=026/H=0.60"], *args)
    val = q.all_seed_keys("VAL", ids, ["THMC/L=026/H=0.60"], *args)
    assert len(dev) == len(set(dev)) and not (set(dev) & set(val))
    assert len({x.split("|")[2] for x in dev}) == 3
    digests = {__import__("hashlib").sha256(x.encode("ascii")).digest() for x in dev}
    assert len(digests) == len(dev)
    assert q.seed_key("DEV", "EVAL", "subject", "SERIES", 7).endswith("|000007")
    assert q.rng_for("key").integers(0, 2**31) == q.rng_for("key").integers(0, 2**31)


def test_kat_i1_imports_are_allowlisted():
    path = Path(q.__file__)
    tree = ast.parse(path.read_text())
    allow = {
        "__future__",
        "argparse",
        "collections",
        "dataclasses",
        "fractions",
        "functools",
        "hashlib",
        "json",
        "math",
        "os",
        "pathlib",
        "platform",
        "re",
        "statistics",
        "sys",
        "time",
        "typing",
        "numpy",
    }
    imported = {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    imported.update(
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert imported <= allow
