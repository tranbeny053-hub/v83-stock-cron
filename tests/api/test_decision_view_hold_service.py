"""Review 3 of lane P, finding 1 (3rd occurrence of the test-adequacy class; owner-authorized
third repair): the H2 directional-evidence hold is exercised through the real analyze_request
service path, not only through build_decision_view directly. With a legacy SKILL_DEMONSTRATED
verdict cached, the recorded analysis's decision_view must withhold the verdict and the resolved
count and mark the hold active, while the raw skill_evidence still carries the legacy verdict — so
the view is proven to withhold it, not merely to lack it.
"""

from __future__ import annotations

from dataclasses import replace

from crypto_probability_engine.adapters.provider_selection import ProviderSelectionResult
from crypto_probability_engine.api import analysis_service
from crypto_probability_engine.api.schemas import AnalysisRequest
from crypto_probability_engine.calibration import skill as skill_module
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from tests.fixtures.market_data import make_snapshot

LEGACY_SKILL_DEMONSTRATED = {
    "verdict": "SKILL_DEMONSTRATED",
    "n": 50,
    "observed_directional_rate": 0.62,
}


def _selection(snapshot=None):
    snapshot = snapshot or make_snapshot(provider="binance")

    def select(symbol, timeframe, *, settings):
        del settings
        selected = replace(snapshot, normalized_symbol=symbol.display, timeframe=timeframe)
        return ProviderSelectionResult(
            snapshot=selected,
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


def _analyze_with_legacy_pass(monkeypatch) -> dict:
    monkeypatch.setattr(analysis_service, "select_market_data", _selection())
    monkeypatch.setattr(
        analysis_service,
        "get_cached_skill_evidence",
        lambda _timeframe: dict(LEGACY_SKILL_DEMONSTRATED),
    )
    return analysis_service.analyze_request(
        AnalysisRequest(symbol="BTC", timeframe="4H"),
        settings=Settings(data_mode="fixture"),
        run_store=InMemoryRunStore(),
        prediction_origin="USER_REQUESTED",
    )


def test_the_view_withholds_a_legacy_pass_under_the_hold(monkeypatch) -> None:
    assert skill_module.LEGACY_PASS_LIFTS_HARD_BLOCK is False, "the H2 hold must be in force"
    payload = _analyze_with_legacy_pass(monkeypatch)

    # The raw evidence still carries the legacy verdict: the view actively withholds it.
    assert payload["skill_evidence"]["verdict"] == "SKILL_DEMONSTRATED"
    assert payload["skill_evidence"]["n"] == 50

    view = payload["decision_view"]
    assert view["schema_version"] == "decision_view.v1"
    evidence = view["evidence"]
    assert evidence["directional_evidence_hold"] is True
    assert evidence["skill_verdict"] is None, "the view hides the legacy verdict under the hold"
    assert evidence["resolved_outcomes"] is None, "and the resolved count with it"
    assert any("directional hold is active" in note for note in evidence["limitations"])

    # Fail-closed: the legacy pass never becomes an accepted claim or a directional permission.
    assert view["accepted_claim"] is False
    assert view["directional_permission"] is False


def test_the_hold_is_carried_by_the_gate_the_service_built(monkeypatch) -> None:
    """The hold the view reads comes from the gate the service assembled, not a test fixture."""

    payload = _analyze_with_legacy_pass(monkeypatch)
    hold = payload["gate_result"]["directional_evidence_hold"]
    assert hold["active"] is True
    assert hold["legacy_verdict"] == "SKILL_DEMONSTRATED"
    # The gate evidence itself is downgraded (fail-closed), independent of the raw diagnostic.
    assert payload["skill_evidence"]["verdict"] == "SKILL_DEMONSTRATED"
