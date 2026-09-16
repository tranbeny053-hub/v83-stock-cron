from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, RefResolver

from crypto_probability_engine.adapters.provider_selection import ProviderSelectionResult
from crypto_probability_engine.api import analysis_service
from crypto_probability_engine.api.schemas import AnalysisRequest
from crypto_probability_engine.config.defaults import (
    DISTRIBUTIONAL_METHODOLOGY_VERSION,
    METHODOLOGY_VERSION,
)
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.detail.frontend_display import build_frontend_display
from crypto_probability_engine.oos.pair_context import OOSArm, build_oos_pair_context
from crypto_probability_engine.persistence.repository import InMemoryPersistenceRepository
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from tests.fixtures.market_data import make_snapshot

ROOT = Path(__file__).resolve().parents[2]
SKILL_EVIDENCE = {
    "verdict": "INSUFFICIENT_EVIDENCE",
    "n": 0,
    "observed_directional_rate": None,
}


def _selection(snapshot):
    def select(symbol, timeframe, *, settings):
        del settings
        assert snapshot.normalized_symbol == symbol.display
        assert snapshot.timeframe == timeframe
        return ProviderSelectionResult(
            snapshot=snapshot,
            provider_state={
                "status": "OK",
                "active_provider": "binance",
                "cross_provider_state": "UNAVAILABLE",
                "providers": {"binance": {"status": "OK"}},
            },
            data_quality={
                "status": "OK",
                "warnings": [],
                "freshness_budget": "DEFAULT_PHASE1A",
                "is_live_data": True,
                "data_source": "BINANCE_PUBLIC",
                "latest_candle_age_seconds": 0,
                "provider_failures": {},
                "cross_provider_state": "UNAVAILABLE",
            },
        )

    return select


def _pair(timeframe: str):
    snapshot = make_snapshot(provider="binance", timeframe=timeframe)
    selection = _selection(snapshot)(
        type("Symbol", (), {"display": snapshot.normalized_symbol})(),
        snapshot.timeframe,
        settings=Settings(data_mode="fixture"),
    )
    return build_oos_pair_context(
        market_snapshot=snapshot,
        provider_state=selection.provider_state,
        data_quality=selection.data_quality,
        resolved_skill_evidence=SKILL_EVIDENCE,
        information_cutoff=snapshot.as_of_utc,
        decision_band_frac=0.002,
    )


def _response_validator() -> Draft202012Validator:
    schema_dir = ROOT / "schemas"
    schema = json.loads((schema_dir / "response.schema.json").read_text())
    store = {
        "quant.schema.json": json.loads((schema_dir / "quant.schema.json").read_text()),
        "detail_view.schema.json": json.loads(
            (schema_dir / "detail_view.schema.json").read_text()
        ),
    }
    return Draft202012Validator(
        schema,
        resolver=RefResolver.from_schema(schema, store=store),
    )


@pytest.mark.parametrize("timeframe", ["15m", "1H", "4H"])
@pytest.mark.parametrize(
    ("arm", "methodology_version"),
    [
        (OOSArm.BASELINE, METHODOLOGY_VERSION),
        (OOSArm.CANDIDATE, DISTRIBUTIONAL_METHODOLOGY_VERSION),
    ],
)
def test_oos_frontend_display_omits_blocking_reasons(
    monkeypatch, timeframe: str, arm: OOSArm, methodology_version: str
) -> None:
    pair = _pair(timeframe)
    expected_key_sets = []
    real_builder = analysis_service.build_frontend_display

    def capturing_builder(*args, **kwargs):
        expected_kwargs = {**kwargs, "include_blocking_reasons": False}
        expected_key_sets.append(set(real_builder(*args, **expected_kwargs)))
        return real_builder(*args, **kwargs)

    monkeypatch.setattr(analysis_service, "build_frontend_display", capturing_builder)
    payload = analysis_service.analyze_request(
        AnalysisRequest(symbol="BTC", timeframe=timeframe),
        settings=Settings(data_mode="fixture"),
        run_store=InMemoryRunStore(),
        prediction_origin="SCHEDULED_SHADOW_EVIDENCE",
        methodology_version=methodology_version,
        pair_context=pair,
        arm=arm,
    )
    repository = InMemoryPersistenceRepository()
    try:
        analysis_service.persist_analysis_now(payload, repository)
    finally:
        analysis_service._pop_prediction_persistence(payload)  # noqa: SLF001

    assert "blocking_reasons" not in payload["frontend_display"]
    _response_validator().validate(payload)
    assert set(payload["frontend_display"]) == expected_key_sets[0]


def test_ordinary_frontend_display_keeps_blocking_reasons(monkeypatch) -> None:
    snapshot = make_snapshot(provider="binance", timeframe="4H")
    monkeypatch.setattr(analysis_service, "select_market_data", _selection(snapshot))
    monkeypatch.setattr(
        analysis_service,
        "get_cached_skill_evidence",
        lambda _timeframe: SKILL_EVIDENCE,
    )

    payload = analysis_service.analyze_request(
        AnalysisRequest(symbol="BTC", timeframe="4H"),
        settings=Settings(data_mode="fixture"),
        run_store=InMemoryRunStore(),
    )

    assert "blocking_reasons" in payload["frontend_display"]


def test_blocking_reasons_flag_only_removes_that_key() -> None:
    quant_result = {
        "probability_state": {
            "horizons": {
                "H_primary": {
                    "p_up_frac": 0.4,
                    "p_down_frac": 0.3,
                    "p_timeout_frac": 0.3,
                }
            }
        },
        "score_stack": {"total_score": 50.0, "disposition": "WATCH"},
        "gate_result": {
            "action": "BLOCKED",
            "hard_gate_passed": False,
            "hard_blocks": ["PROVIDER_DEGRADED"],
        },
        "execution_realism": {"warnings": []},
    }
    news_blocks = {"news_addon_state": {"warnings": []}}
    data_quality = {"warnings": []}
    horizon_context = {
        "timeframe_label": "One hour",
        "horizon_label": "Four bars",
        "horizon_bars": 4,
        "horizon_approx_label": "About four hours",
        "probability_explanation": "Test explanation.",
        "uncalibrated_banner": "Test banner.",
        "model_readiness_label": "Test readiness.",
    }
    included = build_frontend_display(
        quant_result,
        news_blocks,
        "METRICS_ONLY",
        data_quality,
        horizon_context,
    )
    omitted = build_frontend_display(
        quant_result,
        news_blocks,
        "METRICS_ONLY",
        data_quality,
        horizon_context,
        include_blocking_reasons=False,
    )

    assert set(omitted) == set(included) - {"blocking_reasons"}
