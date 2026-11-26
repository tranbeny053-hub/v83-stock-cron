from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

import crypto_probability_engine.api.analysis_service as service
from crypto_probability_engine.adapters.candle_history import CandleHistory
from crypto_probability_engine.adapters.types import ProviderError
from crypto_probability_engine.api.schemas import AnalysisRequest
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.oos.pair_context import OOSArm, build_oos_pair_context
from crypto_probability_engine.persistence.repository import InMemoryPersistenceRepository
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from crypto_probability_engine.quant_ng.pipeline_ng import run_pipeline_reference
from crypto_probability_engine.quant_ng.reference_pooled import (
    METHODOLOGY_VERSION as REFERENCE_VERSION,
)
from crypto_probability_engine.quant_ng.reference_pooled import (
    PooledReferenceUnavailable,
    RefusalReason,
    bars_required,
)
from tests.fixtures.market_data import FIXED_NOW, make_candles, make_snapshot


class HistoryAdapter:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def fetch_candle_history(self, symbol, timeframe, *, bars):
        self.calls.append((symbol.display, timeframe, bars))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _setup(monkeypatch, *, timeframe="4H", provider="binance", symbol="BTC/USDT", count=210):
    snapshot = make_snapshot(provider=provider, symbol=symbol, timeframe=timeframe, count=count)
    monkeypatch.setattr(service, "LEAN_REFERENCE_ENABLED", True)
    monkeypatch.setattr(service, "NG_PIPELINE_ENABLED", False)
    monkeypatch.setattr(service, "_stamp_clock", lambda: FIXED_NOW)
    monkeypatch.setattr(service, "utc_now", lambda: FIXED_NOW)
    monkeypatch.setattr(service.time, "perf_counter", lambda: 42.0)
    monkeypatch.setattr(service, "uuid4", lambda: SimpleNamespace(hex="lean-reference-test"))

    def select(symbol_key, tf, *, settings):
        del settings
        selected = replace(snapshot, normalized_symbol=symbol_key.display, timeframe=tf)
        state = {
            "status": "OK",
            "active_provider": provider,
            "cross_provider_state": "UNAVAILABLE",
            "providers": {provider: {"status": "OK"}},
        }
        quality = {
            "status": "OK",
            "warnings": [],
            "freshness_budget": "DEFAULT_PHASE1A",
            "is_live_data": True,
            "data_source": "BINANCE_PUBLIC" if provider == "binance" else "OKX_PUBLIC",
            "latest_candle_age_seconds": 0,
            "provider_failures": {},
            "cross_provider_state": "UNAVAILABLE",
        }
        return SimpleNamespace(snapshot=selected, provider_state=state, data_quality=quality)

    monkeypatch.setattr(service, "select_market_data", select)
    return snapshot


def _analyze(
    timeframe="4H",
    *,
    symbol="BTC",
    methodology=None,
    origin="USER_REQUESTED",
    deterministic=False,
    isolated=False,
    pair_context=None,
    arm=None,
):
    settings = Settings(data_mode="fixture", provider_priority=("binance",))
    request = AnalysisRequest(symbol=symbol, timeframe=timeframe)
    if isolated:
        return service.analyze_request_isolated(request, settings=settings)
    kwargs = {}
    if methodology is not None:
        kwargs["methodology_version"] = methodology
    return service.analyze_request(
        request,
        settings=settings,
        run_store=InMemoryRunStore(),
        prediction_origin=origin,
        deterministic_identity=deterministic,
        pair_context=pair_context,
        arm=arm,
        **kwargs,
    )


def _historical_window(snapshot):
    bar = 900
    prefix = make_candles(
        count=bars_required("15m") - len(snapshot.candles),
        timeframe_seconds=bar,
        as_of_utc=snapshot.candles[0].open_time_utc,
    )
    all_candles = prefix + snapshot.candles
    return CandleHistory(
        provider="binance",
        normalized_symbol=snapshot.normalized_symbol,
        timeframe="15m",
        requested_bars=bars_required("15m"),
        candles=all_candles,
        as_of_utc=all_candles[-1].close_time_utc,
        requests=1,
    )


def test_served_4h_uses_snapshot_skips_ledger_and_snapshots(monkeypatch):
    snapshot = _setup(monkeypatch)
    adapter = HistoryAdapter(None)
    monkeypatch.setattr(service, "_reference_history_adapter", lambda _settings: adapter)
    feature_calls = []
    derivatives_calls = []
    hashed_payloads = []
    real_stable_hash = service.stable_hash
    monkeypatch.setattr(
        service,
        "stable_hash",
        lambda payload: hashed_payloads.append(dict(payload)) or real_stable_hash(payload),
    )
    monkeypatch.setattr(service, "build_feature_snapshot", lambda *args: feature_calls.append(args))
    monkeypatch.setattr(
        service, "build_derivatives_snapshot", lambda *args: derivatives_calls.append(args)
    )

    response = _analyze()
    reference = run_pipeline_reference(
        snapshot,
        response["provider_state"],
        window_candles=snapshot.candles,
        window_source="SNAPSHOT",
    )
    assert response["reference_state"] == {
        "schema": "lean-reference-state.v1",
        "status": "SERVED",
        "reason": None,
        "methodology_version": REFERENCE_VERSION,
        "served_methodology_version": REFERENCE_VERSION,
        "cell": {"symbol": "BTC/USDT", "timeframe": "4H", "venue": "binance"},
        "h_extended": {"status": "UNAVAILABLE", "reason": "NOT_MODELED"},
        "prediction_ledger": "NOT_RECORDED_BY_DESIGN",
    }
    assert response["probability_state"] == reference["probability_state"]
    assert set(response["probability_state"]["horizons"]) == {"H_primary"}
    assert response["analysis_hash"] == real_stable_hash(hashed_payloads[0])
    assert hashed_payloads[0]["reference_state"] == response["reference_state"]
    assert adapter.calls == []
    assert feature_calls == []
    assert derivatives_calls == []
    assert service._peek_prediction_persistence(response)[0] == []


def test_served_reference_persists_run_detail_and_saved_receipt(monkeypatch):
    _setup(monkeypatch)
    monkeypatch.setattr(
        service, "_reference_history_adapter", lambda _settings: HistoryAdapter(None)
    )
    response = _analyze()

    class HealthyMemoryRepository(InMemoryPersistenceRepository):
        def persistence_status(self):
            return "OK"

    repository = HealthyMemoryRepository()
    service._open_save_receipt(response, "OK")
    work = service._persistence_work(response, "OK")
    detail_row = {
        "run_id": response["run_id"],
        "analysis_hash": response["analysis_hash"],
        "detail_payload": response["detail_view"],
    }
    work = replace(work, run_detail_row=detail_row)
    service._best_effort_persist(work, repository)

    assert service._save_receipt.SAVE_RECEIPTS.get(response["run_id"]) == "SAVED"
    assert len(work.prediction_rows) == 0
    assert len(work.feature_snapshot_rows) == 0
    assert len(work.derivatives_snapshot_rows) == 0
    assert response["run_id"] in repository._runs
    assert response["run_id"] in repository._run_details
    assert (
        repository._run_details[response["run_id"]]["detail_payload"]["reference_state"]
        == response["reference_state"]
    )
    assert repository._predictions == {}
    assert repository._feature_snapshots == {}
    assert repository._derivatives_snapshots == {}


def test_served_15m_fetches_one_history_request_of_678(monkeypatch):
    snapshot = _setup(monkeypatch, timeframe="15m", count=205)
    adapter = HistoryAdapter(_historical_window(snapshot))
    monkeypatch.setattr(service, "_reference_history_adapter", lambda _settings: adapter)
    response = _analyze("15m")
    assert response["reference_state"]["status"] == "SERVED"
    assert adapter.calls == [("BTC/USDT", "15m", 678)]


@pytest.mark.parametrize(
    "reason,kind",
    [
        ("NOT_NAMED_CELL", "unnamed"),
        ("VENUE_NOT_BINANCE", "venue"),
        ("HISTORY_FAILED", "history_failed"),
        ("HISTORY_CONFLICT", "history_conflict"),
        ("SHORT_SNAPSHOT", "short_snapshot"),
        ("BAND_UNAVAILABLE", "band"),
    ],
)
def test_reference_fallbacks_are_explicit_and_keep_heuristic_row(monkeypatch, reason, kind):
    provider = "okx" if kind == "venue" else "binance"
    timeframe = (
        "1D"
        if kind == "unnamed"
        else "15m"
        if kind in {"history_failed", "history_conflict", "short_snapshot"}
        else "4H"
    )
    count = 10 if kind == "short_snapshot" else 205 if timeframe == "15m" else 210
    _setup(monkeypatch, timeframe=timeframe, provider=provider, count=count)
    adapter = HistoryAdapter(ProviderError("FAILED", "mock history failure", provider="binance"))
    monkeypatch.setattr(service, "_reference_history_adapter", lambda _settings: adapter)

    if kind == "short_snapshot":
        monkeypatch.setattr(service, "_reference_history_adapter", lambda _settings: None)
    elif kind == "history_conflict":
        snapshot = make_snapshot(provider="binance", timeframe="15m", count=count)
        history = _historical_window(snapshot)
        items = list(history.candles)
        overlap = len(items) - len(snapshot.candles)
        items[overlap] = replace(
            items[overlap], close=items[overlap].close + 0.1, high=items[overlap].high + 0.1
        )
        adapter = HistoryAdapter(replace(history, candles=tuple(items)))
        monkeypatch.setattr(service, "_reference_history_adapter", lambda _settings: adapter)
    if kind == "band":
        monkeypatch.setattr(
            service,
            "run_pipeline_reference",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                PooledReferenceUnavailable(RefusalReason.BAND_UNAVAILABLE, "mock")
            ),
        )

    # Baseline with the switch off; compare outputs without the reference annotation and hash.
    monkeypatch.setattr(service, "LEAN_REFERENCE_ENABLED", False)
    baseline = _analyze(timeframe)
    monkeypatch.setattr(service, "LEAN_REFERENCE_ENABLED", True)
    actual = _analyze(timeframe)
    assert actual["reference_state"]["status"] == "UNAVAILABLE"
    assert actual["reference_state"]["reason"] == reason
    assert service._peek_prediction_persistence(actual)[0]
    if kind == "venue":
        assert adapter.calls == []
    elif kind in {"history_failed", "history_conflict"}:
        assert len(adapter.calls) == 1
    elif kind == "short_snapshot":
        assert adapter.calls == []
    comparable = {
        key: value
        for key, value in actual.items()
        if key not in {"reference_state", "analysis_hash"}
    }
    baseline_comparable = {key: value for key, value in baseline.items() if key != "analysis_hash"}
    comparable["detail_view"] = {
        key: value for key, value in comparable["detail_view"].items() if key != "reference_state"
    }
    baseline_comparable["detail_view"] = {
        key: value
        for key, value in baseline_comparable["detail_view"].items()
        if key != "reference_state"
    }
    assert comparable == baseline_comparable


@pytest.mark.parametrize(
    "case", ["isolated", "distributional", "smoke", "scheduled", "deterministic"]
)
def test_reference_switch_does_not_change_nonattempted_paths(monkeypatch, case):
    _setup(monkeypatch)
    adapter = HistoryAdapter(None)
    monkeypatch.setattr(service, "_reference_history_adapter", lambda _settings: adapter)
    kwargs = {}
    if case == "isolated":
        monkeypatch.setattr(service, "LEAN_REFERENCE_ENABLED", False)
        off = _analyze(isolated=True)
        monkeypatch.setattr(service, "LEAN_REFERENCE_ENABLED", True)
        on = _analyze(isolated=True)
    else:
        monkeypatch.setattr(service, "LEAN_REFERENCE_ENABLED", False)
        if case == "distributional":
            kwargs["methodology"] = "distributional-v1"
        elif case == "smoke":
            kwargs["origin"] = "CONTROLLED_SMOKE"
        elif case == "scheduled":
            kwargs["origin"] = "SCHEDULED_SHADOW_EVIDENCE"
        elif case == "deterministic":
            kwargs["deterministic"] = True
        off = _analyze(**kwargs)
        monkeypatch.setattr(service, "LEAN_REFERENCE_ENABLED", True)
        on = _analyze(**kwargs)
    assert on == off
    assert "reference_state" not in on
    assert adapter.calls == []


def test_oos_pair_arm_path_is_identical_with_reference_switch(monkeypatch):
    snapshot = _setup(monkeypatch)
    state = {
        "status": "OK",
        "active_provider": "binance",
        "cross_provider_state": "UNAVAILABLE",
        "providers": {"binance": {"status": "OK"}},
    }
    quality = {
        "status": "OK",
        "warnings": [],
        "freshness_budget": "DEFAULT_PHASE1A",
        "is_live_data": True,
        "data_source": "BINANCE_PUBLIC",
        "latest_candle_age_seconds": 0,
        "provider_failures": {},
        "cross_provider_state": "UNAVAILABLE",
    }
    pair = build_oos_pair_context(
        market_snapshot=snapshot,
        provider_state=state,
        data_quality=quality,
        resolved_skill_evidence={
            "verdict": "INSUFFICIENT_EVIDENCE",
            "n": 0,
            "observed_directional_rate": None,
        },
        information_cutoff=snapshot.as_of_utc,
        decision_band_frac=0.002,
    )
    monkeypatch.setattr(service, "LEAN_REFERENCE_ENABLED", False)
    off = _analyze(origin="SCHEDULED_SHADOW_EVIDENCE", pair_context=pair, arm=OOSArm.BASELINE)
    service._pop_prediction_persistence(off)
    monkeypatch.setattr(service, "LEAN_REFERENCE_ENABLED", True)
    on = _analyze(origin="SCHEDULED_SHADOW_EVIDENCE", pair_context=pair, arm=OOSArm.BASELINE)
    service._pop_prediction_persistence(on)
    assert on == off
    assert "reference_state" not in on


def test_both_pipeline_switches_on_is_refused():
    with pytest.raises(RuntimeError, match="cannot both be enabled"):
        service._ensure_exclusive_pipeline_switches(True, True)


def test_switch_off_never_constructs_reference_history_adapter(monkeypatch):
    _setup(monkeypatch)
    factory_calls = []
    monkeypatch.setattr(
        service,
        "_reference_history_adapter",
        lambda settings: factory_calls.append(settings),
    )
    monkeypatch.setattr(service, "LEAN_REFERENCE_ENABLED", False)
    response = _analyze()
    assert "reference_state" not in response
    assert factory_calls == []
