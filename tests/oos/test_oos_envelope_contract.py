"""Freeze the response envelope used by the live OOS collector.

The live collector runs ``main`` and persists ``analysis_hash``. Any new response field
changes what is written into the running holdout, so these literals are a deliberate
contract. Changing them is not routine maintenance: a new field must first be gated OFF
the OOS path (see ``include_blocking_reasons`` in ``build_frontend_display`` for the
pattern), and only then may this contract be updated in its own reviewed commit.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from crypto_probability_engine.adapters.provider_selection import ProviderSelectionResult
from crypto_probability_engine.api import analysis_service
from crypto_probability_engine.api.schemas import AnalysisRequest
from crypto_probability_engine.config.defaults import (
    DISTRIBUTIONAL_METHODOLOGY_VERSION,
    METHODOLOGY_VERSION,
)
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.oos.pair_context import OOSArm, build_oos_pair_context
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from tests.fixtures.market_data import make_snapshot

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "tests" / "fixtures" / "oos_envelope_contract.json"
FROZEN_CONTRACT_DIGEST = (
    "b2e2d2daf879d3c0431d99fd0da8a93e2fbe37e5e7938fb8d23d36b39b344458"
)

FROZEN_OOS_RESPONSE_KEYS = frozenset(
    {
        "analysis_hash",
        "analysis_mode",
        "as_of_utc",
        "asset_class",
        "calibration_state",
        "catalyst_state",
        "data_quality",
        "debug",
        "decision_brief",
        "decision_synthesis",
        "derivatives_intelligence",
        "detail_view",
        "epistemic_sufficiency_state",
        "event_horizon_state",
        "execution_realism",
        "frontend_display",
        "gate_result",
        "horizon_timeout_state",
        "information_state",
        "liquidity_state",
        "macro_context",
        "market_features",
        "micro_news_context",
        "narrative_state",
        "news_addon_state",
        "news_evidence",
        "news_materiality_state",
        "normalized_symbol",
        "novelty_surprise_state",
        "probability_state",
        "provider_state",
        "quant_compute_state",
        "quant_v2",
        "risk_arbiter_state",
        "run_id",
        "schema_version",
        "score_stack",
        "skill_evidence",
        "source_confidence_state",
        "symbol",
        "tail_risk_state",
        "timeframes",
        "trend_summary",
    }
)
FROZEN_OOS_FRONTEND_DISPLAY_KEYS = frozenset(
    {
        "analysis_mode_badge",
        "data_quality_warnings",
        "data_source",
        "detail_available",
        "disposition",
        "execution_warnings",
        "heat_legend",
        "horizon_approx_label",
        "horizon_bars",
        "horizon_label",
        "invalidation_conditions",
        "is_live_data",
        "key_reasons",
        "model_readiness_label",
        "news_warnings",
        "prob_down_pct",
        "prob_timeout_pct",
        "prob_up_pct",
        "probability_explanation",
        "risk_level",
        "timeframe_label",
        "total_score",
        "uncalibrated_banner",
    }
)
FROZEN_OOS_RUN_SUMMARY_KEYS = frozenset(
    {
        "analysis_hash",
        "analysis_mode",
        "as_of_utc",
        "asset_class",
        "data_source",
        "disposition",
        "is_live_data",
        "normalized_symbol",
        "operator_id",
        "persistence_status",
        "primary_timeframe",
        "run_id",
        "symbol",
        "total_score",
    }
)
FROZEN_OOS_TIMEFRAME_RESULT_KEYS = frozenset(
    {
        "data_source",
        "disposition",
        "gate_action",
        "is_live_data",
        "prob_down_pct",
        "prob_timeout_pct",
        "prob_up_pct",
        "run_id",
        "timeframe",
        "total_score",
    }
)

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
                "warnings": [],
                "is_live_data": True,
                "data_source": "BINANCE_PUBLIC",
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


def _key_paths(value: object, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else key
            paths.add(path)
            paths.update(_key_paths(child, path))
    elif isinstance(value, list):
        for child in value:
            paths.update(_key_paths(child, f"{prefix}[]"))
    return paths


def test_oos_envelope_fixture_digest_is_frozen() -> None:
    actual_digest = hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest()

    assert actual_digest == FROZEN_CONTRACT_DIGEST


def _build_oos_payload(
    timeframe: str, arm: OOSArm, methodology_version: str
) -> dict:
    return analysis_service.analyze_request(
        AnalysisRequest(symbol="BTC", timeframe=timeframe),
        settings=Settings(data_mode="fixture"),
        run_store=InMemoryRunStore(),
        prediction_origin="SCHEDULED_SHADOW_EVIDENCE",
        methodology_version=methodology_version,
        pair_context=_pair(timeframe),
        arm=arm,
    )


@pytest.mark.parametrize("timeframe", ["15m", "1H", "4H"])
@pytest.mark.parametrize(
    ("arm", "methodology_version"),
    [
        (OOSArm.BASELINE, METHODOLOGY_VERSION),
        (OOSArm.CANDIDATE, DISTRIBUTIONAL_METHODOLOGY_VERSION),
    ],
)
def test_oos_frozen_key_sets(
    timeframe: str, arm: OOSArm, methodology_version: str
) -> None:
    # Kept separate so a Layer 1 failure cannot hide Layer 2 drift.
    payload = _build_oos_payload(timeframe, arm, methodology_version)
    try:
        work = analysis_service._persistence_work(  # noqa: SLF001
            payload,
            "STATELESS",
            consume_pending=False,
        )

        assert frozenset(payload) == FROZEN_OOS_RESPONSE_KEYS
        assert frozenset(payload["frontend_display"]) == FROZEN_OOS_FRONTEND_DISPLAY_KEYS
        assert frozenset(work.run_summary) == FROZEN_OOS_RUN_SUMMARY_KEYS
        assert frozenset(work.timeframe_result) == FROZEN_OOS_TIMEFRAME_RESULT_KEYS
    finally:
        analysis_service._pop_prediction_persistence(payload)  # noqa: SLF001


@pytest.mark.parametrize("timeframe", ["15m", "1H", "4H"])
@pytest.mark.parametrize(
    ("arm", "methodology_version"),
    [
        (OOSArm.BASELINE, METHODOLOGY_VERSION),
        (OOSArm.CANDIDATE, DISTRIBUTIONAL_METHODOLOGY_VERSION),
    ],
)
def test_oos_recursive_path_contract(
    timeframe: str, arm: OOSArm, methodology_version: str
) -> None:
    # Kept separate so a Layer 1 failure cannot hide Layer 2 drift.
    payload = _build_oos_payload(timeframe, arm, methodology_version)
    try:
        contract = json.loads(CONTRACT_PATH.read_text())
        expected_paths = set(contract[arm.value])
        actual_paths = _key_paths(payload)
        added_paths = sorted(actual_paths - expected_paths)
        removed_paths = sorted(expected_paths - actual_paths)
        assert actual_paths == expected_paths, (
            f"{arm.value} {timeframe} envelope drift; added paths: {added_paths}; "
            f"removed paths: {removed_paths}"
        )
    finally:
        analysis_service._pop_prediction_persistence(payload)  # noqa: SLF001
