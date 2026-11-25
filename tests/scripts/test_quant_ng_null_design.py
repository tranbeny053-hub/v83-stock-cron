"""Known-answer tests for EXP-04 stage-1 identity and numeric primitives."""

import ast
import math
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


@pytest.mark.parametrize("L", [26, 52, 104], ids=["l026", "l052", "l104"])
def test_kat_n8_independent_window_variance(L):
    assert q.window_mean_variance(q.arfima_acf(0.0, L), L) == pytest.approx(1 / L, abs=1e-8)


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
    for speed, expected in (
        ("FAST", (0.875, 0.96875, 0.2, 0.6201737, 1.8605210)),
        ("SLOW", (25 / 26, 103 / 104, 0.2, 0.6201737, 1.8605210)),
    ):
        assert q._regime_params(speed, 3.0) == pytest.approx(expected, abs=1e-6)


def test_kat_g1_grid_counts():
    val, dev = q.scenario_grid("VAL"), q.scenario_grid("DEV")
    assert len(val) == 975 and len(dev) == 101
    assert sum(s.kind == "SIZE" for s in val) == 588
    assert sum(s.kind == "POWER" for s in val) == 387
    assert len(q.design_grid()) == 103 and len(q.focus_designs()) == 34
    assert len(q.VARIANTS) == 12
    family_counts = {family: sum(s.family == family for s in val) for family in q.SCENARIO_FAMILIES}
    assert family_counts == {
        "N-CORE": 450,
        "N-VOL": 9,
        "N-REGMEAN": 36,
        "N-TWIN": 18,
        "N-MEMSPLIT": 12,
        "N-AR": 18,
        "N-CHURN": 18,
        "N-SEL": 9,
        "N-TAIL": 18,
        "P-CORE": 270,
        "P-HET": 54,
        "P-SCORE": 27,
        "P-CTRL": 18,
        "P-TWIN": 9,
        "P-CHURN": 9,
    }
    sizes = [s for s in val if s.kind == "SIZE"]
    assert sum(q.family_class(s) == "PLAN_NAMED" for s in sizes) == 426
    assert sum(q.family_class(s) == "SENSITIVITY" for s in sizes) == 162
    plan_by_d = [
        sum(q.family_class(s) == "PLAN_NAMED" and s.d <= d for s in sizes)
        for d in (0.10, 0.15, 0.25, 0.35, 0.45)
    ]
    assert plan_by_d == [138, 222, 282, 366, 426]
    assert (588 * 103, 387 * (12 * 34 + 2 * (103 - 34))) == (60564, 211302)
    assert (77 * 103, 24 * (12 * 34 + 2 * (103 - 34))) == (7931, 13104)
    assert 387 * (12 * 35 + 2 * (103 - 35)) == 215172


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


def test_kat_i1_imports_no_source_or_other_script_imports_module():
    forbidden_parts = ("5a", "f3", "look_run", "holdout", "sealed", "f2_")
    root = Path(q.__file__).parents[1]
    matches = []
    for base_name in ("src", "scripts"):
        base = root / base_name
        for path in base.rglob("*.py"):
            if any(
                any(token in part.lower() for token in forbidden_parts)
                for part in path.relative_to(root).parts
            ):
                continue
            if path == Path(q.__file__).resolve():
                continue
            tree = ast.parse(path.read_text())
            imports = [
                node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
            ] + [
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            ]
            if any("quant_ng_null_design" in module for module in imports):
                matches.append(str(path.relative_to(root)))
    assert matches == []


def test_kat_s1_block_t_and_core_boundaries():
    look = np.array([[-0.3, -0.1, -0.2, -0.4]])
    full = np.zeros((1, 208 + 4))
    full[:, 208:] = look
    assert look.mean() == pytest.approx(-0.25)
    assert look.std(ddof=1) == pytest.approx(0.1290994, abs=1e-7)
    assert q.block_t(look)[0] == pytest.approx(-3.8729833, abs=1e-7)
    assert q.block_t(look, 0.10)[0] == pytest.approx(-2.3237900, abs=1e-7)
    for level, expected in (("A050", True), ("A025", True), ("A0125", False)):
        assert (
            bool(q.core_rejects(f"T/{level}", {"S": full}, L=4, floor=0, sigma0=1, thmc={})[0])
            == expected
        )
    assert not q.core_rejects("T/A025", {"S": full}, L=4, floor=0.1, sigma0=1, thmc={})[0]


def test_kat_s2_certified_h_statistic():
    look = np.array([[-0.3, -0.1, -0.2, -0.4]])
    full = np.zeros((1, 208 + 4))
    full[:, 208:] = look
    stat = (look.mean(axis=1)) / (look.std(axis=1, ddof=1) * 4 ** (0.75 - 1))
    assert stat[0] == pytest.approx(-2.7386128, abs=1e-7)
    assert not q.core_rejects("TH/A025/H075", {"S": full}, L=4, floor=0, sigma0=1, thmc={})[0]


def test_kat_s3_allowance_windows():
    hist = np.array([[0.1, -0.1, 0.2, 0.0, -0.2, 0.0, 0.1, -0.1]])
    allowance = q.allowance_window_means(hist, 4, 8, "NONE")
    assert allowance[0] == pytest.approx(0.0707107, abs=1e-7)
    adjusted = np.array([-0.25])
    assert q._allowance_rejects(adjusted, "A050", q.allowance_window_means(hist, 4, 8, "NONE"))[0]
    assert not q._allowance_rejects(adjusted, "A050", q.allowance_window_means(hist, 4, 8, "UB80"))[
        0
    ]
    assert q.allowance_window_means(hist[:, :4], 4, 4, "NONE") is None


def test_kat_s4_sign_key_uses_both_scores_and_strict_negative():
    W = 208 + 4
    ll = np.zeros((1, 5, W))
    br = np.zeros_like(ll)
    ll[0, :, 208:] = np.array([-0.1, -0.2, 0.05, -0.3, -0.01])[:, None]
    br[0, :, 208:] = np.array([-0.1, 0.02, -0.05, -0.3, -0.01])[:, None]
    member = np.ones_like(ll, dtype=bool)
    assert q.sign_key({"LL": ll, "BR": br}, member, L=4, q="3/5", m_min=1)[0][0]
    for fraction in ("7/10", "4/5"):
        assert not q.sign_key({"LL": ll, "BR": br}, member, L=4, q=fraction, m_min=1)[0][0]
    member[:] = False
    passed, evaluable = q.sign_key({"LL": ll, "BR": br}, member, L=4, q="1", m_min=1)
    assert not passed[0] and not evaluable[0]
    ll[:, :, 208:] = 0
    assert not q.sign_key({"LL": ll}, np.ones_like(ll, bool), L=4, q="1", m_min=1)[0][0]


def test_kat_s5_symbol_replication_core():
    W = 208 + 4
    x = np.zeros((1, 5, W))
    x[0, :, 208:] = np.array([-0.1, -0.2, -0.3, -0.2, -0.2])[:, None]
    member = np.ones_like(x, dtype=bool)
    assert q.sym_repl_rejects({"S": x}, member, L=4, level="A025")[0]


def test_kat_s6_weekly_pooling_is_permutation_invariant():
    x = np.array([[[1.0, 2.0], [3.0, 4.0], [100.0, 8.0]]])
    member = np.array([[[1, 1], [1, 1], [0, 1]]], dtype=bool)
    y = q.pooled_block_means(x, member)
    assert y.tolist() == [[2.0, 14 / 3]]
    assert np.array_equal(y, q.pooled_block_means(x[:, [2, 0, 1], :], member[:, [2, 0, 1], :]))
    permuted = x.copy()
    permuted[0, 0, :] = permuted[0, 0, ::-1]
    assert not np.array_equal(y, q.pooled_block_means(permuted, member))


def test_kat_s7_twin_idiosyncratic_series_are_equal():
    # At rho zero, each generated field is exactly its idiosyncratic component and twins match.
    s0 = q.Scenario("N-TWIN", "SIZE", 0, 0.0, 10, 26, twin_fraction=0.4, twin_rho=1.0)
    p0 = q.simulate_chunk(s0, stage="KAT", stream="EVAL", chunk=0, reps=3)
    assert np.array_equal(p0.x[("CAND", "S")][:, 0], p0.x[("CAND", "S")][:, 1])


def test_kat_s8_floor_invariance():
    y = np.array([[-0.25, -0.125, -0.375, -0.5], [0.0, 0.125, -0.125, -0.25]])
    assert np.array_equal(
        q.block_t(y - 0.125, 0.125) <= q.student_t_quantile(0.025, 3),
        q.block_t(y) <= q.student_t_quantile(0.025, 3),
    )


def test_kat_s9_control_veto_and_control_off_variant():
    W, L = 208 + 4, 4
    cand_y = np.zeros((1, W))
    ctrl_y = np.zeros((1, W))
    cand_y[:, 208:] = [-0.3, -0.1, -0.2, -0.4]
    ctrl_y[:, 208:] = [-0.3, -0.1, -0.2, -0.4]
    cand_x = np.repeat(cand_y[:, None, :], 5, axis=1)
    ctrl_x = np.repeat(ctrl_y[:, None, :], 5, axis=1)
    panel = q.Panel(
        {("CAND", "S"): cand_x, ("CTRL", "S"): ctrl_x},
        None,
        {("CAND", "S"): cand_y, ("CTRL", "S"): ctrl_y},
        None,
    )
    assert not q.joint_rejects("T/A050", "V_J0", panel, L=L, sigma0=1, thmc={})[0]
    assert q.joint_rejects("T/A050", "V_CTRL_OFF", panel, L=L, sigma0=1, thmc={})[0]


def _kat_chunks(scenario, reps, *, stage="KAT", stream="EVAL", chunk_size=1000):
    for chunk, start in enumerate(range(0, reps, chunk_size)):
        yield q.simulate_chunk(
            scenario, stage=stage, stream=stream, chunk=chunk, reps=min(chunk_size, reps - start)
        )


def test_kat_m1_independent_week_size():
    s = q.Scenario("N-CORE", "SIZE", 0, 0.6, 5, 26)
    rejects = 0
    for panel in _kat_chunks(s, 20_000):
        rejects += int(
            q.core_rejects(
                "T/A050", {"S": panel.y[("CAND", "S")]}, L=26, floor=0, sigma0=1, thmc={}
            ).sum()
        )
    # 6.2 standard deviations for Binomial(20,000, .05).
    assert abs(rejects - 1000) <= 6.2 * np.sqrt(20_000 * 0.05 * 0.95)


def test_kat_m2_symbol_replication_fails_under_dependence():
    def rate(rho):
        s = q.Scenario("N-CORE", "SIZE", 0, rho, 5, 26)
        total = 0
        for panel in _kat_chunks(s, 20_000):
            total += int(
                q.sym_repl_rejects({"S": panel.x[("CAND", "S")]}, None, L=26, level="A050").sum()
            )
        return total / 20_000

    assert rate(0.6) > 0.10
    independent = rate(0.0)
    assert abs(independent - 0.05) <= 6.2 * np.sqrt(0.05 * 0.95 / 20_000)


def test_kat_m3_calibrated_long_memory_t_and_mc():
    calibrated = q.thmc_table(26, 0.85, stage="KAT", n_series=200_000, chunk=1000)
    assert calibrated["A050"] < 0
    s = q.Scenario("N-CORE", "SIZE", 0.35, 0.6, 5, 26)
    t_rejects = mc_rejects = 0
    for panel in _kat_chunks(s, 20_000):
        y = {"S": panel.y[("CAND", "S")]}
        t_rejects += int(q.core_rejects("T/A050", y, L=26, floor=0, sigma0=1, thmc={}).sum())
        mc_rejects += int(
            q.core_rejects(
                "TH_MC/A050/H085", y, L=26, floor=0, sigma0=1, thmc={26: {0.85: calibrated}}
            ).sum()
        )
    assert 0.040 <= mc_rejects / 20_000 <= 0.060
    assert t_rejects / 20_000 > 0.15


def test_kat_m4_arima_look_mean_variance():
    L, reps, d = 52, 40_000, 0.35
    C = q.cholesky_factor(d, L)
    means = []
    for chunk, start in enumerate(range(0, reps, 1000)):
        size = min(1000, reps - start)
        z = (
            q.rng_for(q.seed_key("KAT", "CAL_THMC", "KAT-M4", "SERIES", chunk)).standard_normal(
                (size, L)
            )
            @ C.T
        )
        means.extend(z.mean(axis=1))
    expected = q.window_mean_variance(q.arfima_acf(d, L), L)
    assert np.var(means, ddof=1) == pytest.approx(expected, rel=0.05)


def test_kat_m5_sigma0_matches_dependence_variance():
    s = q.Scenario("N-CORE", "SIZE", 0.15, 0.60, 10, 52)
    observed = q.sigma0_for(s, stage="KAT", n_reps=20_000, chunk=1000)
    expected = np.sqrt((0.60 + 0.40 / 10) * q.window_mean_variance(q.arfima_acf(0.15, 52), 52))
    assert observed == pytest.approx(expected, rel=0.04)


def test_kat_m6_allowance_key2_gaussian_rate():
    reps, sigma0, z = 40_000, 0.2, q.normal_quantile(0.95)
    for delta, kappa in ((0.0, 1.0), (0.1, 0.75)):
        values = []
        for chunk, start in enumerate(range(0, reps, 1000)):
            size = min(1000, reps - start)
            values.extend(
                q.rng_for(q.seed_key("KAT", "EVAL", f"M6/{delta}/{kappa}", "SERIES", chunk)).normal(
                    -delta, sigma0, size
                )
            )
        rejects = q._allowance_rejects(np.asarray(values), "A050", kappa * sigma0).mean()
        expected = 0.5 * (1 + math.erf((delta - z * kappa * sigma0) / (sigma0 * np.sqrt(2))))
        assert abs(rejects - expected) <= 6.2 * np.sqrt(expected * (1 - expected) / reps)


def test_kat_m7_regime_stationarity_and_variance():
    # Spec §14 KAT-M7, through simulate_chunk (the path a run uses): 20,000 x 234 weeks.
    vol = q._scenario("N-VOL", d=0.0, L=26)
    states, values = [], []
    for panel in _kat_chunks(vol, 20_000):
        states.append(panel.state)
        values.append(panel.x[("CAND", "S")])
    assert abs(np.concatenate(states).mean() - 0.2) <= 0.01
    assert np.var(np.concatenate(values), ddof=1) == pytest.approx(1.0, rel=0.03)
    shifted = q._scenario("N-REGMEAN", d=0.0, L=26, regime_mean_g=0.5, regime_speed="FAST")
    means = [panel.x[("CAND", "S")].mean() for panel in _kat_chunks(shifted, 20_000)]
    assert abs(float(np.mean(means))) <= 0.01


def test_kat_m8_churn_is_asof_and_has_exact_panel_size():
    reps, n, W, Q = 4, 5, 208 + 26, (208 + 26) // 13
    eta = q.rng_for("membership-test").standard_normal((reps, 2 * n, Q))
    scores = q.rng_for("values-test").standard_normal((reps, 2 * n, W))
    member, _ = q._select_membership(scores, eta, 0.5, 0.5, n, W)
    assert np.all(member.sum(axis=1) == n)
    changed = scores.copy()
    changed[..., 13:26] += 1000
    member_changed, _ = q._select_membership(changed, eta, 0.5, 0.5, n, W)
    assert np.array_equal(member[:, :, 13:26], member_changed[:, :, 13:26])
    psi_zero, _ = q._select_membership(scores, eta, 0.5, 0.0, n, W)
    changed[:] = -scores
    psi_zero_changed, _ = q._select_membership(changed, eta, 0.5, 0.0, n, W)
    assert np.array_equal(psi_zero, psi_zero_changed)
    many = 64
    eta = q.rng_for("membership-test-asof").standard_normal((many, 2 * n, Q))
    scores = q.rng_for("values-test-asof").standard_normal((many, 2 * n, W))
    base, _ = q._select_membership(scores, eta, 0.5, 0.5, n, W)
    for quarter in range(1, Q):
        for shift in (1000.0, -1000.0):
            changed = scores.copy()
            changed[:, 0, 13 * quarter :] += shift
            after, _ = q._select_membership(changed, eta, 0.5, 0.5, n, W)
            weeks = slice(13 * quarter, 13 * (quarter + 1))
            assert np.array_equal(base[:, :, weeks], after[:, :, weeks]), (quarter, shift)


def _look_panel(look, history=None, L=4):
    full = np.zeros((1, 208 + L))
    if history is not None:
        full[:, 208 - len(history) : 208] = history
    full[:, 208:] = look
    return full


def test_kat_s1_boundary_is_inclusive(monkeypatch):
    # Spec §9: reject when t <= the critical value, so equality rejects (M4).
    full = _look_panel([-0.3, -0.1, -0.2, -0.4])
    t_exact = float(q.block_t(full[:, 208:])[0])
    monkeypatch.setattr(q, "student_t_quantile", lambda p, df: t_exact)
    assert q.core_rejects("T/A025", {"S": full}, L=4, floor=0, sigma0=1, thmc={})[0]
    monkeypatch.undo()
    table = {4: {0.75: {"A025": t_exact}}}
    assert q.core_rejects("TH_MC/A025/H075", {"S": full}, L=4, floor=0, sigma0=1, thmc=table)[0]


def test_kat_s3_core_reads_history_weeks_only():
    # KAT-S3's history in weeks 200-207 and a strongly negative look: windows 0.05 and -0.05,
    # s_K = 0.0707107, so K2 at A050 rejects. Windows that reached into the look weeks would
    # give s_K = 0.7071068 and no rejection (M8).
    hist = [0.1, -0.1, 0.2, 0.0, -0.2, 0.0, 0.1, -0.1]
    full = _look_panel([-1.0, -1.2, -0.9, -1.1], hist)
    assert q.core_rejects(
        "RA_WM/A050/A050/W008/NONE", {"S": full}, L=4, floor=0, sigma0=1, thmc={}
    )[0]


def test_kat_s8_floor_invariance_across_cores():
    # Spec §14 KAT-S8 for every core type: decisions on (y - phi, floor = phi) equal (y, floor = 0).
    rng = q.rng_for("kat-s8-dyadic")
    y = rng.integers(-64, 64, size=(64, 208 + 4)) / 64.0
    phi = 0.125
    table = {4: {0.75: {"A025": -2.5}}}
    for design in (
        "T/A025",
        "TH/A025/H075",
        "TH_MC/A025/H075",
        "RA_EXT/A025/A050/K100",
        "RA_WM/A025/A050/W008/UB80",
        "RA_WM/A025/A025/W208/NONE",
    ):
        shifted = q.core_rejects(design, {"S": y - phi}, L=4, floor=phi, sigma0=0.25, thmc=table)
        plain = q.core_rejects(design, {"S": y}, L=4, floor=0.0, sigma0=0.25, thmc=table)
        assert np.array_equal(shifted, plain), design


def _floor_panel():
    # Five symbols over the look: means -1, -1, -1, -0.1, +0.5 plus a common weekly wiggle.
    L, W = 4, 208 + 4
    base = np.array([-1.0, -1.0, -1.0, -0.1, 0.5])
    wiggle = np.array([0.05, -0.05, 0.03, -0.03])
    cand_x = np.zeros((1, 5, W))
    cand_x[0, :, 208:] = base[:, None] + wiggle[None, :]
    ctrl_x = np.zeros_like(cand_x)
    y = {("CAND", "S"): cand_x.mean(axis=1), ("CTRL", "S"): ctrl_x.mean(axis=1)}
    return q.Panel({("CAND", "S"): cand_x, ("CTRL", "S"): ctrl_x}, None, y, None), L


def test_kat_s8_floor_never_reaches_sign_key():
    # Four events of five pass q = 4/5. A floor of 0.20 added to the sign key's input would
    # turn the -0.1 symbol into a non-event and veto (M25); the floor belongs to the core only.
    panel, L = _floor_panel()
    assert q.joint_rejects("T/A050", "V_J0", panel, L=L, sigma0=1, thmc={})[0]
    assert q.joint_rejects("T/A050", "V_FLOOR_020", panel, L=L, sigma0=1, thmc={})[0]


def test_kat_s9_count_scenario_matches_joint_rejects():
    # count_scenario must count exactly the joint rule of joint_rejects (spec §9) on every cell,
    # with the null twin's sigma0, and list the cells that are not estimable.
    s = q._scenario("P-CHURN", d=0.15, L=26, delta=0.4, churn_a=0.5)
    designs, focus = q.design_grid(), set(q.focus_designs())
    thmc = {
        26: {
            h: q.thmc_table(26, h, stage="KAT", n_series=2000, chunk=1000)
            for h in (0.60, 0.65, 0.75, 0.85, 0.95)
        }
    }
    sigma0 = {q.null_twin_id(s): 0.3}
    out = q.count_scenario(
        s,
        stage="KAT",
        n_reps=200,
        chunk=100,
        designs=designs,
        focus=focus,
        sigma0=sigma0,
        thmc=thmc,
    )
    expected, not_estimable = {}, set()
    for idx in range(2):
        panel = q.simulate_chunk(s, stage="KAT", stream="EVAL", chunk=idx, reps=100)
        for design in designs:
            for variant in q.VARIANTS if design in focus else ("V_CORE", "V_J0"):
                r = q.joint_rejects(design, variant, panel, L=26, sigma0=0.3, thmc=thmc)
                if r is None:
                    not_estimable.add(f"{design}|{variant}")
                    continue
                key = f"{design}|{variant}|rejections"
                expected[key] = expected.get(key, 0) + int(r.sum())
        # An independent reference from the primitives for three V_J0 cells.
        cand_y = {k[1]: v for k, v in panel.y.items() if k[0] == "CAND"}
        ctrl_y = {k[1]: v for k, v in panel.y.items() if k[0] == "CTRL"}
        cand_x = {k[1]: v for k, v in panel.x.items() if k[0] == "CAND"}
        sign, _ = q.sign_key(cand_x, panel.member, L=26, q="4/5", m_min=7)
        for design in ("T/A025", "RA_EXT/A025/A050/K100", "RA_WM/A025/A050/W208/UB95"):
            core = q.core_rejects(design, cand_y, L=26, floor=0.0, sigma0=0.3, thmc=thmc)
            ctrl = q.core_rejects(design, ctrl_y, L=26, floor=0.0, sigma0=0.3, thmc=thmc)
            direct = core & sign & ~ctrl
            joint = q.joint_rejects(design, "V_J0", panel, L=26, sigma0=0.3, thmc=thmc)
            assert np.array_equal(direct, joint), design
    assert {k: v for k, v in out["counts"].items() if k.endswith("|rejections")} == expected
    assert out["not_estimable"] == sorted(not_estimable)
    assert out["n_reps"] == 200
    with pytest.raises(q.Refusal):
        q.count_scenario(
            s,
            stage="KAT",
            n_reps=100,
            chunk=100,
            designs=designs,
            focus=focus,
            sigma0={},
            thmc=thmc,
        )


def test_kat_s9_not_estimable_cells_are_listed():
    # At L = 104 the W104 allowance has K = 1 window: those 15 cells are NOT_ESTIMABLE (spec §9).
    s = q._scenario("N-CORE", d=0.15, L=104)
    out = q.count_scenario(
        s,
        stage="KAT",
        n_reps=20,
        chunk=20,
        designs=q.design_grid(),
        focus=set(q.focus_designs()),
        sigma0=0.3,
        thmc={104: {h: {lvl: -3.0 for lvl in q.LEVELS} for h in (0.60, 0.65, 0.75, 0.85, 0.95)}},
    )
    expected = sorted(
        f"{d}|V_CORE" for d in q.design_grid() if d.startswith("RA_WM/") and "/W104/" in d
    )
    assert out["not_estimable"] == expected and len(expected) == 15
    assert not any(
        k.startswith(tuple(e.split("|")[0] + "|" for e in expected)) for k in out["counts"]
    )


def test_kat_s4_sign_key_cache_keys_on_q_and_m_min():
    # Symbol 0 is a member in one look week only: eligible at m_min = 1, not at m_min = 2.
    L, W = 8, 208 + 8
    x = np.zeros((1, 5, W))
    x[0, :, 208:] = np.array([-0.2, -0.2, -0.2, -0.2, 0.3])[:, None]
    member = np.ones((1, 5, W), dtype=bool)
    member[0, 0, 209:] = False
    panel = q.Panel({("CAND", "S"): x}, member, {("CAND", "S"): x.mean(axis=1)}, None)
    ev = q._ChunkEval(panel, L=L, sigma0=1.0, thmc={})
    assert not ev.sign("4/5", 2)[0][0]
    assert ev.sign("4/5", 1)[0][0]
    assert np.array_equal(
        ev.sign("4/5", 1)[0], q.sign_key({"S": x}, member, L=L, q="4/5", m_min=1)[0]
    )
