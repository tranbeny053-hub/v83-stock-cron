from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from uuid import UUID

import crypto_probability_engine.api.analysis_service as analysis_service
from crypto_probability_engine.adapters.provider_selection import ProviderSelectionResult
from crypto_probability_engine.api.analysis_service import _pop_prediction_persistence
from crypto_probability_engine.api.schemas import AnalysisRequest
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.derivatives_intel.block import build_derivatives_intelligence
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from tests.fixtures.market_data import make_snapshot


def _live_selection(symbol, timeframe, *, settings) -> ProviderSelectionResult:
    del settings
    return ProviderSelectionResult(
        snapshot=make_snapshot(
            provider="binance",
            symbol=symbol.display,
            timeframe=timeframe,
        ),
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


def _unavailable_block(**kwargs):
    core = kwargs["core_prediction_as_of_utc"]
    block = build_derivatives_intelligence(
        normalized_symbol=kwargs["normalized_symbol"],
        core_prediction_as_of_utc=core,
        enabled=False,
    )
    block.update(
        {
            "observation_as_of_utc": (core + timedelta(seconds=1)).isoformat(),
            "block_status": "UNAVAILABLE",
            "provider_summary": [
                {
                    "provider": provider,
                    "status": "PROVIDER_UNAVAILABLE",
                    "valid_metric_count": 0,
                    "total_metric_count": 0,
                    "reason": "Fixture provider evidence unavailable.",
                }
                for provider in ("BINANCE_USDM", "OKX_SWAP")
            ],
            "comparability": [
                {
                    "semantic_class": semantic_class,
                    "left_provider": "BINANCE_USDM",
                    "right_provider": "OKX_SWAP",
                    "comparable": False,
                    "reason": "Provider-native evidence is not comparable in this fixture.",
                }
                for semantic_class in ("CURRENT_FUNDING", "CURRENT_OPEN_INTEREST")
            ],
            "warnings": ["Fixture derivatives evidence unavailable."],
        }
    )
    return block


def _analyze(*, enabled: bool) -> dict:
    return analysis_service.analyze_request(
        AnalysisRequest(symbol="BTC", timeframe="4H"),
        settings=Settings(data_mode="fixture", enable_derivatives_intel=enabled),
        run_store=InMemoryRunStore(),
    )


def test_analysis_handoff_skips_disabled_and_remembers_eligible_snapshot(monkeypatch) -> None:
    monkeypatch.setattr(analysis_service, "select_market_data", _live_selection)
    monkeypatch.setattr(analysis_service, "uuid4", lambda: UUID(int=19))
    disabled = _analyze(enabled=False)
    disabled_work = _pop_prediction_persistence(disabled)
    assert disabled_work[0]
    assert disabled_work[3] == []
    assert disabled_work[4] is False

    monkeypatch.setattr(
        analysis_service, "build_derivatives_intelligence", _unavailable_block
    )
    enabled = _analyze(enabled=True)
    predictions, feature_rows, feature_failed, derivatives_rows, derivatives_failed = (
        _pop_prediction_persistence(enabled)
    )
    assert predictions and feature_rows
    assert feature_failed is False
    assert derivatives_failed is False
    assert len(derivatives_rows) == 1
    assert derivatives_rows[0]["prediction_id"] == predictions[0]["prediction_id"]
    assert derivatives_rows[0]["block_status"] == "UNAVAILABLE"


def test_snapshot_builder_failure_does_not_change_or_fail_analysis(monkeypatch) -> None:
    monkeypatch.setattr(analysis_service, "select_market_data", _live_selection)
    monkeypatch.setattr(analysis_service, "uuid4", lambda: UUID(int=23))
    monkeypatch.setattr(
        analysis_service, "build_derivatives_intelligence", _unavailable_block
    )
    baseline = _analyze(enabled=True)
    baseline_work = _pop_prediction_persistence(baseline)

    def fail_snapshot_builder(*args, **kwargs):
        raise RuntimeError("fixture snapshot projection failure")

    monkeypatch.setattr(analysis_service, "build_derivatives_snapshot", fail_snapshot_builder)
    actual = _analyze(enabled=True)
    actual_work = _pop_prediction_persistence(actual)
    _, _, _, derivatives_rows, derivatives_failed = actual_work

    assert derivatives_rows == []
    assert derivatives_failed is True
    assert actual == baseline
    assert actual_work[:3] == baseline_work[:3]


def test_snapshot_projection_does_not_mutate_response_block(monkeypatch) -> None:
    monkeypatch.setattr(analysis_service, "select_market_data", _live_selection)
    monkeypatch.setattr(analysis_service, "uuid4", lambda: UUID(int=29))
    monkeypatch.setattr(
        analysis_service, "build_derivatives_intelligence", _unavailable_block
    )
    payload = _analyze(enabled=True)
    block_before = deepcopy(payload["derivatives_intelligence"])

    _, _, _, rows, failed = _pop_prediction_persistence(payload)

    assert not failed
    assert rows
    assert payload["derivatives_intelligence"] == block_before
    assert "snapshot_hash" not in payload["derivatives_intelligence"]
