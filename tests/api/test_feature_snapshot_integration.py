from __future__ import annotations

from copy import deepcopy

from crypto_probability_engine.adapters.provider_selection import ProviderSelectionResult
from crypto_probability_engine.api import analysis_service
from crypto_probability_engine.api.schemas import AnalysisMode, AnalysisRequest
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from tests.fixtures.market_data import make_snapshot


class _FixedUuid:
    hex = "4c2snapshot"


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


def test_snapshot_attachment_does_not_change_response_identity_or_decisions(monkeypatch) -> None:
    monkeypatch.setattr(analysis_service, "select_market_data", _live_selection)
    monkeypatch.setattr(analysis_service, "uuid4", lambda: _FixedUuid())
    request = AnalysisRequest(
        symbol="BTC",
        timeframe="4H",
        analysis_mode=AnalysisMode.METRICS_ONLY,
    )
    settings = Settings(data_mode="fixture")
    captured: list[tuple[dict | None, dict]] = []
    real_builder = analysis_service.build_feature_snapshot

    def capture_snapshot(prediction_row, quant_v2):
        captured.append((deepcopy(prediction_row), deepcopy(quant_v2)))
        return real_builder(prediction_row, quant_v2)

    monkeypatch.setattr(analysis_service, "build_feature_snapshot", capture_snapshot)
    with_snapshot = analysis_service.analyze_request(
        request,
        settings=settings,
        run_store=InMemoryRunStore(),
    )

    def skip_snapshot(prediction_row, quant_v2):
        captured.append((deepcopy(prediction_row), deepcopy(quant_v2)))
        return None

    monkeypatch.setattr(analysis_service, "build_feature_snapshot", skip_snapshot)
    without_snapshot = analysis_service.analyze_request(
        request,
        settings=settings,
        run_store=InMemoryRunStore(),
    )

    assert with_snapshot == without_snapshot
    assert captured[0] == captured[1]
    assert captured[0][0] is not None
    assert captured[0][0]["prediction_id"] == "run_4c2snapshot:4H"
    assert with_snapshot["analysis_hash"] == without_snapshot["analysis_hash"]
    assert with_snapshot["probability_state"] == without_snapshot["probability_state"]
    assert with_snapshot["score_stack"] == without_snapshot["score_stack"]
    assert with_snapshot["gate_result"] == without_snapshot["gate_result"]
    assert with_snapshot["decision_synthesis"] == without_snapshot["decision_synthesis"]
    assert with_snapshot["quant_v2"] == without_snapshot["quant_v2"]
    assert "feature_snapshot" not in with_snapshot
    decision = with_snapshot["decision_synthesis"]
    assert decision["action_permission"]["can_enter_now"] is False
    assert decision["action_permission"]["can_chase"] is False
    assert decision["future_quant_v2_hooks"]["decision_influence_frac"] == 0.0

    with analysis_service._PENDING_PREDICTION_LOCK:  # noqa: SLF001
        analysis_service._PENDING_PREDICTION_ROWS.clear()  # noqa: SLF001
        analysis_service._PENDING_FEATURE_SNAPSHOT_ROWS.clear()  # noqa: SLF001
