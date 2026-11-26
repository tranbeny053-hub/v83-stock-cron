from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import get_args

import pytest
from pydantic import ValidationError

import crypto_probability_engine.api.analysis_service as service
from crypto_probability_engine.adapters.candle_history import CandleHistory
from crypto_probability_engine.adapters.types import ProviderError
from crypto_probability_engine.api.schemas import (
    AnalysisRequest,
    DecisionBrief,
    LeanReferenceReason,
    LeanReferenceState,
)
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.detail.saved_run_view import build_saved_run_view
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
from crypto_probability_engine.quant_ng.windows import UnavailableReason
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


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


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
    assert {
        key: value for key, value in response["reference_state"].items() if key != "display"
    } == {
        "schema": "lean-reference-state.v1",
        "status": "SERVED",
        "reason": None,
        "methodology_version": REFERENCE_VERSION,
        "served_methodology_version": REFERENCE_VERSION,
        "cell": {"symbol": "BTC/USDT", "timeframe": "4H", "venue": "binance"},
        "h_extended": {"status": "UNAVAILABLE", "reason": "NOT_MODELED"},
        "prediction_ledger": "NOT_RECORDED_BY_DESIGN",
    }
    timeout = response["horizon_timeout_state"]
    assert response["reference_state"]["display"] == {
        "title": "Descriptive reference",
        "count_line": (
            f"In band: {timeout['inside_band_count']} of {timeout['matured_outcome_count']} "
            f"matured six-bar outcomes over the last {timeout['memory_days']} days ended inside "
            "today's decision band."
        ),
        "direction_line": "Up and Down are split equally: no direction.",
        "overlap_line": "Outcomes overlap: each shares half its horizon with the next.",
        "honesty_line": (
            "Not a validated forecast and not a prediction interval. Not recorded for scoring."
        ),
        "extended_line": "Extended horizon: not modelled.",
    }
    assert response["decision_brief"]["probability_type"] == (
        "DESCRIPTIVE_REFERENCE_6BAR_INSIDE_BAND_FREQUENCY"
    )
    assert response["decision_brief"]["model_readiness"] == "DESCRIPTIVE_REFERENCE_UNVALIDATED"
    assert response["decision_brief"]["calibration_status"] is None
    assert response["decision_brief"]["reliability_status"] is None
    assert response["decision_brief"]["calibration_status_reason"] == "NO_SCORED_COHORT_BY_DESIGN"
    assert response["decision_brief"]["reliability_status_reason"] == "NO_SCORED_COHORT_BY_DESIGN"
    assert any(
        reason.startswith(
            "Backend score (risk pressure only; the reference has no directional edge): "
        )
        for reason in response["decision_brief"]["key_reasons"]
    )
    assert response["decision_synthesis"]["model_quality_summary"]["reliability_status"] is None
    assert response["decision_synthesis"]["model_quality_summary"]["reliability_status_reason"] == (
        "NO_SCORED_COHORT_BY_DESIGN"
    )
    assert response["decision_brief"]["probability_explanation"].startswith(
        "In band is the share of recent matured six-bar outcomes"
    )
    assert response["decision_brief"]["uncalibrated_banner"].startswith(
        "⚠️ Descriptive historical frequency"
    )
    assert response["decision_brief"]["model_readiness_label"].startswith(
        "Model readiness: Descriptive reference"
    )
    assert response["decision_view"]["state"] == "NO_ACCEPTED_CLAIM"
    assert response["decision_view"]["evidence"]["skill_verdict"] is None
    assert response["decision_view"]["evidence"]["resolved_outcomes"] is None
    assert response["decision_view"]["evidence"]["skill_note"] == "NO_SCORED_COHORT_BY_DESIGN"
    reference_strings = " ".join(
        str(item)
        for section in (
            response["decision_brief"],
            response["decision_synthesis"],
            response["decision_view"],
            response["reference_state"]["display"],
            response["frontend_display"],
        )
        for item in _strings(section)
    ).lower()
    assert "heuristic" not in reference_strings and "momentum" not in reference_strings
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

        def save_run(self, row):
            assert set(row) <= set(service._run_summary({}))
            return super().save_run(row)

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
    saved_view = build_saved_run_view(response["detail_view"])
    assert (
        saved_view["range"]["explanation"] == response["decision_brief"]["probability_explanation"]
    )
    assert saved_view["evidence"]["level"] == (
        "Model readiness: Descriptive reference (pooled matured frequency) — not validated."
    )
    assert saved_view["reference"] == response["reference_state"]["display"]
    assert repository._predictions == {}
    assert repository._feature_snapshots == {}
    assert repository._derivatives_snapshots == {}
    assert set(work.run_summary) == set(service._run_summary({}))


@pytest.mark.parametrize("status", ["SERVED", "FALLBACK", "UNNAMED"])
def test_reference_run_summary_keeps_only_analysis_run_columns(monkeypatch, status):
    if status == "UNNAMED":
        _setup(monkeypatch, timeframe="1D")
        response = _analyze("1D")
    else:
        _setup(monkeypatch, timeframe="4H")
        if status == "SERVED":
            monkeypatch.setattr(
                service, "_reference_history_adapter", lambda _settings: HistoryAdapter(None)
            )
        else:
            _setup(monkeypatch, timeframe="15m", count=205)
            monkeypatch.setattr(
                service,
                "_reference_history_adapter",
                lambda _settings: HistoryAdapter(
                    ProviderError("FAILED", "mock history failure", provider="binance")
                ),
            )
            response = _analyze("15m")
        if status == "SERVED":
            response = _analyze("4H")
    work = service._persistence_work(response, "OK")
    assert set(work.run_summary) == set(service._run_summary({}))
    assert work.reference_served is (status == "SERVED")


def test_reference_reason_enum_matches_schema_and_quant_enums():
    reason_values = {
        "NOT_NAMED_CELL",
        "VENUE_NOT_BINANCE",
        *(reason.value for reason in RefusalReason),
        *(reason.value for reason in UnavailableReason),
    }
    assert set(get_args(LeanReferenceReason)) == reason_values
    root = Path(__file__).resolve().parents[2]
    schema = json.loads((root / "schemas/response.schema.json").read_text())
    reason_enum = schema["properties"]["reference_state"]["oneOf"][1]["properties"]["reason"][
        "enum"
    ]
    assert set(reason_enum) - {None} == set(get_args(LeanReferenceReason)) == reason_values
    served_versions = schema["properties"]["reference_state"]["oneOf"][1]["properties"][
        "served_methodology_version"
    ]["enum"]
    assert set(served_versions) == {"reference-pooled-tk-v1", "heuristic-v1-wave4b0"}


def test_probability_type_controls_status_nullability_in_both_validators(monkeypatch):
    from jsonschema import Draft202012Validator

    _setup(monkeypatch)
    monkeypatch.setattr(
        service, "_reference_history_adapter", lambda _settings: HistoryAdapter(None)
    )
    response = _analyze()
    reference_brief = response["decision_brief"]
    heuristic_brief = dict(reference_brief)
    heuristic_brief["probability_type"] = "UNCALIBRATED_HEURISTIC_6BAR_OUTCOME"
    with pytest.raises(ValidationError):
        DecisionBrief.model_validate(heuristic_brief)

    root = Path(__file__).resolve().parents[2]
    schema = json.loads((root / "schemas/response.schema.json").read_text())
    validator = Draft202012Validator(schema["properties"]["decision_brief"])
    heuristic_response = json.loads(json.dumps(response))
    heuristic_brief = heuristic_response["decision_brief"]
    heuristic_brief["probability_type"] = "UNCALIBRATED_HEURISTIC_6BAR_OUTCOME"
    assert list(validator.iter_errors(heuristic_brief))

    served_string = dict(reference_brief)
    served_string["calibration_status"] = "MEASURED"
    with pytest.raises(ValidationError):
        DecisionBrief.model_validate(served_string)
    bad_response = json.loads(json.dumps(response))
    bad_brief = bad_response["decision_brief"]
    bad_brief["reliability_status"] = "MEASURED"
    assert list(validator.iter_errors(bad_brief))


def test_reference_state_bad_values_are_rejected_by_both_schemas():
    from jsonschema import Draft202012Validator

    root = Path(__file__).resolve().parents[2]
    schema = json.loads((root / "schemas/response.schema.json").read_text())
    reference_schema = schema["properties"]["reference_state"]["oneOf"][1]
    json_validator = Draft202012Validator(reference_schema)
    valid = {
        "schema": "lean-reference-state.v1",
        "status": "SERVED",
        "reason": None,
        "methodology_version": "reference-pooled-tk-v1",
        "served_methodology_version": "reference-pooled-tk-v1",
        "cell": {"symbol": "BTC/USDT", "timeframe": "4H", "venue": "binance"},
        "h_extended": {"status": "UNAVAILABLE", "reason": "NOT_MODELED"},
        "prediction_ledger": "NOT_RECORDED_BY_DESIGN",
        "display": {
            key: "text"
            for key in (
                "title",
                "count_line",
                "direction_line",
                "overlap_line",
                "honesty_line",
                "extended_line",
            )
        },
    }
    for mutate in (
        lambda item: item.update(reason="HISTORY_FAILED"),
        lambda item: item.update(reason="MADE_UP"),
        lambda item: item.update(methodology_version="other"),
        lambda item: item.update(prediction_ledger="RECORDED_AS_x"),
        lambda item: item["display"].pop("honesty_line"),
    ):
        malformed = json.loads(json.dumps(valid))
        mutate(malformed)
        with pytest.raises(ValidationError):
            LeanReferenceState.model_validate(malformed)
        assert list(json_validator.iter_errors(malformed))


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
    display = actual["reference_state"]["display"]
    assert display["title"] == "Descriptive reference"
    if reason == "NOT_NAMED_CELL":
        assert display["count_line"] == (
            "Available only for BTC/USDT, ETH/USDT and SOL/USDT on Binance at 15m, 1H and 4H."
        )
    else:
        assert display["count_line"] == (
            f"Unavailable for this run ({reason}); the percentages shown are the heuristic's."
        )
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
