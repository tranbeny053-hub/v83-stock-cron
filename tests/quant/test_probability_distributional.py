from __future__ import annotations

import ast
import hashlib
import inspect
import json
from dataclasses import replace

import pytest

import crypto_probability_engine.api.analysis_service as analysis_service
import crypto_probability_engine.quant.pipeline as pipeline_module
import crypto_probability_engine.quant.probability_distributional as distributional_module
from crypto_probability_engine.adapters.provider_selection import ProviderSelectionResult
from crypto_probability_engine.adapters.types import MarketCandle
from crypto_probability_engine.api.schemas import AnalysisRequest
from crypto_probability_engine.config.defaults import (
    DEFAULT_METHODOLOGY_VERSION,
    DEFAULT_PHASE1A,
    DISTRIBUTIONAL_METHODOLOGY_VERSION,
)
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from crypto_probability_engine.quant.horizon_timeout import (
    compute_timeout_probability,
    horizon_timeout_state,
)
from crypto_probability_engine.quant.pipeline import run_quant_pipeline
from crypto_probability_engine.quant.probability_distributional import (
    FROZEN_B3_PARAMETERS,
    SUPPORTED_TIMEFRAMES,
    build_distributional_probability_state,
    compute_distributional_probabilities,
)
from crypto_probability_engine.quant.probability_three_state import (
    compute_probability_state,
)
from tests.fixtures.market_data import make_candles, make_order_book, make_snapshot


def _candles_for_returns(returns: tuple[float, ...]) -> tuple[MarketCandle, ...]:
    template = make_candles(count=len(returns) + 1)
    closes = [100.0]
    for simple_return in returns:
        closes.append(closes[-1] * (1.0 + simple_return))
    return tuple(
        replace(
            candle,
            open=close,
            high=close,
            low=close,
            close=close,
        )
        for candle, close in zip(template, closes, strict=True)
    )


def test_default_methodology_is_pinned_to_prechange_pipeline_result() -> None:
    snapshot = make_snapshot()
    implicit = run_quant_pipeline(snapshot, {"status": "OK"})
    explicit = run_quant_pipeline(
        snapshot,
        {"status": "OK"},
        methodology_version=DEFAULT_METHODOLOGY_VERSION,
    )

    assert explicit == implicit
    assert explicit["analysis_hash"] == (
        "sha256:1192321026be5618e28bfe64f5782fd67f9c3ff8af4bf08957b75dbb9b8261ce"
    )


def test_selector_changes_probabilities_for_same_snapshot() -> None:
    snapshot = make_snapshot()
    baseline = run_quant_pipeline(snapshot, {"status": "OK"})
    candidate = run_quant_pipeline(
        snapshot,
        {"status": "OK"},
        methodology_version=DISTRIBUTIONAL_METHODOLOGY_VERSION,
    )

    assert candidate["probability_state"] != baseline["probability_state"]
    assert candidate["analysis_hash"] != baseline["analysis_hash"]


def test_unknown_and_unsupported_candidate_timeframes_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def legacy_fallback_was_called(*args, **kwargs):
        raise AssertionError("legacy timeout fallback was called")

    monkeypatch.setattr(
        pipeline_module,
        "compute_timeout_probability",
        legacy_fallback_was_called,
    )
    with pytest.raises(ValueError, match="Unsupported methodology version"):
        run_quant_pipeline(
            make_snapshot(),
            {"status": "OK"},
            methodology_version="unknown-v1",
        )
    with pytest.raises(ValueError, match="does not support timeframe: 1D"):
        run_quant_pipeline(
            make_snapshot(timeframe="1D"),
            {"status": "OK"},
            methodology_version=DISTRIBUTIONAL_METHODOLOGY_VERSION,
        )


def test_candidate_timeout_is_coherent_and_never_calls_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def legacy_timeout_was_called(*args, **kwargs):
        raise AssertionError("legacy timeout must not run for B3")

    monkeypatch.setattr(
        pipeline_module,
        "compute_timeout_probability",
        legacy_timeout_was_called,
    )
    result = run_quant_pipeline(
        make_snapshot(),
        {"status": "OK"},
        methodology_version=DISTRIBUTIONAL_METHODOLOGY_VERSION,
    )
    primary_timeout = result["probability_state"]["horizons"]["H_primary"][
        "p_timeout_frac"
    ]
    timeout_state = result["horizon_timeout_state"]

    assert primary_timeout is timeout_state["p_timeout_frac"]
    assert timeout_state["method"] == DISTRIBUTIONAL_METHODOLOGY_VERSION
    assert "vol_reference" not in timeout_state
    assert {"sigma_bar", "sigma_h", "band_frac"} <= timeout_state.keys()


def test_pipeline_wires_live_execution_band_only_to_candidate_probabilities() -> None:
    snapshot_a = make_snapshot(provider="binance")
    snapshot_b = replace(snapshot_a, order_book=make_order_book(ask=121.0))
    provider_state = {"status": "OK"}

    candidates = tuple(
        run_quant_pipeline(
            snapshot,
            provider_state,
            methodology_version=DISTRIBUTIONAL_METHODOLOGY_VERSION,
        )
        for snapshot in (snapshot_a, snapshot_b)
    )
    live_costs = tuple(
        result["execution_realism"]["round_trip_cost_frac"]
        for result in candidates
    )

    for result, live_cost in zip(candidates, live_costs, strict=True):
        assert result["horizon_timeout_state"]["band_frac"] == live_cost
    assert live_costs[0] != 0.002
    assert live_costs[0] != live_costs[1]

    primary_a, primary_b = (
        result["probability_state"]["horizons"]["H_primary"]
        for result in candidates
    )
    for key in ("p_up_frac", "p_down_frac", "p_timeout_frac"):
        assert primary_a[key] != primary_b[key]

    for snapshot in (snapshot_a, snapshot_b):
        baseline = run_quant_pipeline(
            snapshot,
            provider_state,
            methodology_version=DEFAULT_METHODOLOGY_VERSION,
        )
        volatility = baseline["market_features"]["volatility"]
        timeout_frac = compute_timeout_probability(
            volatility,
            baseline["liquidity_state"],
            timeframe=snapshot.timeframe,
        )
        expected_probability = compute_probability_state(
            net_signal=baseline["risk_arbiter_state"]["net_signal"],
            timeout_frac=timeout_frac,
            epistemic_state=baseline["epistemic_sufficiency_state"],
            volatility_state=volatility,
        )

        assert baseline["probability_state"] == expected_probability
        assert baseline["horizon_timeout_state"] == horizon_timeout_state(
            timeout_frac,
            timeframe=snapshot.timeframe,
        )


@pytest.mark.parametrize("timeframe", sorted(SUPPORTED_TIMEFRAMES))
@pytest.mark.parametrize(
    "band_frac",
    (0.0, 0.002, DEFAULT_PHASE1A.execution_cost_hard_gate_frac, 1.0),
)
@pytest.mark.parametrize("volatility", (0.0, 1e-9, 0.001, 0.02, 0.5))
def test_candidate_probability_invariant_sweep(
    timeframe: str,
    band_frac: float,
    volatility: float,
) -> None:
    returns = tuple(volatility if index % 2 else -volatility for index in range(209))
    result = compute_distributional_probabilities(
        _candles_for_returns(returns),
        timeframe=timeframe,
        band_frac=band_frac,
    )
    triplet = (result.p_up_frac, result.p_down_frac, result.p_timeout_frac)

    assert all(0.0 <= probability <= 1.0 for probability in triplet)
    assert sum(triplet) == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize(
    ("timeframe", "sample_size"),
    (("15m", 140100), ("1H", 70018), ("4H", 26220)),
)
def test_finite_sample_cdf_tails_are_pinned_and_derived(
    timeframe: str,
    sample_size: int,
) -> None:
    parameters = FROZEN_B3_PARAMETERS[timeframe]
    table = parameters["table"]

    assert parameters["n"] == sample_size
    assert distributional_module._empirical_cdf(  # noqa: SLF001
        -1e9, table, sample_size
    ) == 1.0 / (sample_size + 1)
    assert distributional_module._empirical_cdf(  # noqa: SLF001
        1e9, table, sample_size
    ) == sample_size / (sample_size + 1)


@pytest.mark.parametrize("timeframe", sorted(SUPPORTED_TIMEFRAMES))
@pytest.mark.parametrize("band_frac", (1e-12, 0.002, 1e9))
@pytest.mark.parametrize("volatility", (0.0, 0.02))
def test_extreme_sweep_never_emits_literal_probability_endpoints(
    timeframe: str,
    band_frac: float,
    volatility: float,
) -> None:
    returns = tuple(volatility if index % 2 else -volatility for index in range(209))
    result = compute_distributional_probabilities(
        _candles_for_returns(returns),
        timeframe=timeframe,
        band_frac=band_frac,
    )

    assert all(
        0.0 < probability < 1.0
        for probability in (
            result.p_up_frac,
            result.p_down_frac,
            result.p_timeout_frac,
        )
    )


@pytest.mark.parametrize(
    ("timeframe", "sample_size"),
    (("15m", 140100), ("1H", 70018), ("4H", 26220)),
)
def test_extreme_clamp_preserves_exact_declared_triplet(
    timeframe: str,
    sample_size: int,
) -> None:
    result = compute_distributional_probabilities(
        _candles_for_returns((0.0,) * 209),
        timeframe=timeframe,
        band_frac=1e9,
    )

    assert result.p_down_frac == 1.0 / (sample_size + 1)
    assert result.p_up_frac == 1.0 / (sample_size + 1)
    assert result.p_timeout_frac == (sample_size - 1) / (sample_size + 1)
    assert sum(
        (result.p_up_frac, result.p_down_frac, result.p_timeout_frac)
    ) == pytest.approx(1.0, abs=1e-12)


def test_frozen_parameters_and_all_quantile_knots_are_pinned() -> None:
    expected = {
        "15m": (
            0.90,
            0.60,
            140100,
            "b9a70ba3663027a18be4b01ad517a4fa89ddb6b3f90141a26b5a1aa30f701b86",
        ),
        "1H": (
            0.99,
            0.50,
            70018,
            "b27b19c60d68b7367f6cb78c58a9aad3171309a8c2e3d505928c3d05c2cdaadc",
        ),
        "4H": (
            0.99,
            0.50,
            26220,
            "ee3e8ad5c73edbd9a6c7e7ce9476c3efe3e4b5fe539790fe15a74c07f935ceff",
        ),
    }

    assert set(FROZEN_B3_PARAMETERS) == set(expected)
    for timeframe, (decay, alpha, sample_size, table_digest) in expected.items():
        parameters = FROZEN_B3_PARAMETERS[timeframe]
        table = parameters["table"]
        z_values = [knot[0] for knot in table]
        probabilities = [knot[1] for knot in table]
        serialized = json.dumps(table, separators=(",", ":")).encode()
        assert parameters["decay"] == decay
        assert parameters["alpha"] == alpha
        assert parameters["n"] == sample_size
        assert len(table) == 101
        assert z_values == sorted(z_values)
        assert probabilities == sorted(probabilities)
        assert probabilities[0] == 0.0
        assert probabilities[-1] == 1.0
        assert hashlib.sha256(serialized).hexdigest() == table_digest


def test_epistemic_null_neutralizes_real_distributional_asymmetry() -> None:
    probability = compute_distributional_probabilities(
        _candles_for_returns((0.02, -0.02) * 104 + (0.02,)),
        timeframe="4H",
        band_frac=0.002,
    )
    assert probability.p_up_frac != probability.p_down_frac

    state = build_distributional_probability_state(
        probability,
        epistemic_state={"action": "ABORT", "reason": "INSUFFICIENT_HISTORY"},
    )
    primary = state["horizons"]["H_primary"]
    neutral_direction = (1.0 - probability.p_timeout_frac) / 2.0

    assert primary["p_up_frac"] == neutral_direction
    assert primary["p_down_frac"] == neutral_direction
    assert primary["p_timeout_frac"] == probability.p_timeout_frac
    assert primary["status"] == "NULL"
    assert primary["null_reason"] == "INSUFFICIENT_HISTORY"
    assert primary["confidence_frac"] == 0.0


def test_epistemic_allow_preserves_existing_probability_and_confidence_path() -> None:
    probability = compute_distributional_probabilities(
        _candles_for_returns((0.02, -0.02) * 104 + (0.02,)),
        timeframe="4H",
        band_frac=0.002,
    )
    state = build_distributional_probability_state(
        probability,
        epistemic_state={"action": "ALLOW"},
    )
    primary = state["horizons"]["H_primary"]
    non_timeout_mass = probability.p_up_frac + probability.p_down_frac

    assert primary["p_up_frac"] == probability.p_up_frac
    assert primary["p_down_frac"] == probability.p_down_frac
    assert primary["p_timeout_frac"] == probability.p_timeout_frac
    assert primary["p_up_user_norm_frac"] == (
        probability.p_up_frac / non_timeout_mass
    )
    assert primary["p_down_user_norm_frac"] == (
        probability.p_down_frac / non_timeout_mass
    )
    assert primary["status"] == "OK"
    assert primary["null_reason"] is None
    assert primary["confidence_frac"] == 0.5


def test_zero_location_has_no_return_sign_response() -> None:
    # Binary-exact returns make this an exact sign-invariance check, not a tolerance check.
    returns = (0.5,)
    original = compute_distributional_probabilities(
        _candles_for_returns(returns),
        timeframe="4H",
        band_frac=0.002,
    )
    sign_flipped = compute_distributional_probabilities(
        _candles_for_returns(tuple(-value for value in returns)),
        timeframe="4H",
        band_frac=0.002,
    )

    assert original.sigma_bar == sign_flipped.sigma_bar
    assert original.sigma_h == sign_flipped.sigma_h
    assert original.p_up_frac == sign_flipped.p_up_frac
    assert original.p_down_frac == sign_flipped.p_down_frac
    assert original.p_timeout_frac == sign_flipped.p_timeout_frac


def test_distributional_module_has_no_location_term_or_runtime_io() -> None:
    source = inspect.getsource(distributional_module)
    tree = ast.parse(source)
    imported_roots = {
        alias.name.split(".", maxsplit=1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".", maxsplit=1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }

    assert imported_roots.isdisjoint(
        {"aiohttp", "fastapi", "httpx", "psycopg", "requests", "sqlalchemy", "urllib"}
    )
    assert "open(" not in source
    assert ".read(" not in source
    assert ".read_text(" not in source
    assert "drift" not in source.lower()
    assert "net_signal" not in source


def test_analyze_request_threads_core_methodology_to_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = make_snapshot(provider="binance")

    def select_market_data(symbol, timeframe, *, settings):
        del settings
        selected = replace(snapshot, normalized_symbol=symbol.display, timeframe=timeframe)
        return ProviderSelectionResult(
            snapshot=selected,
            provider_state={"status": "OK", "active_provider": "binance"},
            data_quality={
                "status": "OK",
                "warnings": [],
                "is_live_data": False,
                "data_source": "FIXTURE",
                "cross_provider_state": "UNAVAILABLE",
            },
        )

    calls: list[str] = []
    original_pipeline = pipeline_module.run_quant_pipeline

    def recording_pipeline(snapshot, provider_state, *, methodology_version):
        calls.append(methodology_version)
        return original_pipeline(
            snapshot,
            provider_state,
            methodology_version=methodology_version,
        )

    monkeypatch.setattr(analysis_service, "select_market_data", select_market_data)
    monkeypatch.setattr(analysis_service, "run_quant_pipeline", recording_pipeline)
    response = analysis_service.analyze_request(
        AnalysisRequest(symbol="BTC", timeframe="4H"),
        settings=Settings(data_mode="fixture"),
        run_store=InMemoryRunStore(),
        methodology_version=DISTRIBUTIONAL_METHODOLOGY_VERSION,
    )

    assert calls == [DISTRIBUTIONAL_METHODOLOGY_VERSION]
    assert response["horizon_timeout_state"]["method"] == (
        DISTRIBUTIONAL_METHODOLOGY_VERSION
    )
