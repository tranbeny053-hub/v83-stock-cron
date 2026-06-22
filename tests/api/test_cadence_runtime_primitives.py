from __future__ import annotations

import hashlib
import inspect
import json
import re
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from uuid import UUID

import pytest
from fastapi import HTTPException

from crypto_probability_engine.adapters.provider_selection import ProviderSelectionResult
from crypto_probability_engine.api import analysis_service
from crypto_probability_engine.api.schemas import AnalysisRequest
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.derivatives_intel.block import build_derivatives_intelligence
from crypto_probability_engine.persistence.feature_snapshot import (
    FeatureSnapshotWriteStatus,
)
from crypto_probability_engine.persistence.repository import InMemoryPersistenceRepository
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from tests.fixtures.market_data import FIXED_NOW, make_candles, make_snapshot

EXPECTED_DEFAULT_ANALYSIS_HASH = (
    "sha256:3d65034da3b18e10b474d1a9908373537deddab2ad523a73914c63d2727f58f4"
)
EXPECTED_DEFAULT_RESPONSE_HASH = (
    "72cfb34d213a1b57f5010558a6b7e9a22fd794c2c82bb357d5cf4b5a63ac050c"
)
EXPECTED_CADENCE_RUN_ID = "cadence-265a4bf99c44ef001b40b1bdc514f9a3"


def _selection(snapshot=None):
    snapshot = snapshot or make_snapshot(provider="binance")

    def select(symbol, timeframe, *, settings):
        del settings
        selected = replace(
            snapshot,
            normalized_symbol=symbol.display,
            timeframe=timeframe,
        )
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


def _analyze(
    monkeypatch,
    *,
    symbol: str = "BTC",
    deterministic: bool = False,
    snapshot=None,
    derivatives: bool = False,
) -> dict:
    monkeypatch.setattr(analysis_service, "select_market_data", _selection(snapshot))
    return analysis_service.analyze_request(
        AnalysisRequest(symbol=symbol, timeframe="4H"),
        settings=Settings(data_mode="fixture", enable_derivatives_intel=derivatives),
        run_store=InMemoryRunStore(),
        prediction_origin="SCHEDULED_SHADOW_EVIDENCE"
        if deterministic
        else "USER_REQUESTED",
        deterministic_identity=deterministic,
    )


def _prediction_row(payload: dict) -> dict:
    predictions, _, failed, _, derivatives_failed = (
        analysis_service._peek_prediction_persistence(payload)  # noqa: SLF001
    )
    assert not failed
    assert not derivatives_failed
    assert len(predictions) == 1
    return predictions[0]


def _clear_pending(payload: dict) -> None:
    analysis_service._pop_prediction_persistence(payload)  # noqa: SLF001


def _unavailable_derivatives_block(**kwargs):
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
                    "semantic_class": semantic,
                    "left_provider": "BINANCE_USDM",
                    "right_provider": "OKX_SWAP",
                    "comparable": False,
                    "reason": "Fixture provider evidence is unavailable.",
                }
                for semantic in ("CURRENT_FUNDING", "CURRENT_OPEN_INTEREST")
            ],
            "warnings": ["Fixture derivatives evidence unavailable."],
        }
    )
    return block


def test_default_identity_path_is_byte_stable_under_frozen_inputs(monkeypatch) -> None:
    monkeypatch.setattr(analysis_service, "uuid4", lambda: UUID(int=73))

    payload = _analyze(monkeypatch)

    assert payload["run_id"] == "run_00000000000000000000000000000049"
    assert payload["analysis_hash"] == EXPECTED_DEFAULT_ANALYSIS_HASH
    canonical_response = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    assert hashlib.sha256(canonical_response.encode("utf-8")).hexdigest() == (
        EXPECTED_DEFAULT_RESPONSE_HASH
    )
    assert payload["decision_synthesis"]["action_permission"]["can_enter_now"] is False
    assert payload["decision_synthesis"]["trade_plan_skeleton"]["can_chase"] is False
    _clear_pending(payload)


def test_deterministic_identity_matches_exact_vector_and_aliases(monkeypatch) -> None:
    monkeypatch.setattr(
        analysis_service,
        "uuid4",
        lambda: pytest.fail("deterministic identity must not request a UUID"),
    )

    btc = _analyze(monkeypatch, symbol="BTC", deterministic=True)
    btc_prediction = _prediction_row(btc)
    _clear_pending(btc)
    alias = _analyze(monkeypatch, symbol="btcusdt", deterministic=True)
    alias_prediction = _prediction_row(alias)

    assert btc["run_id"] == alias["run_id"] == EXPECTED_CADENCE_RUN_ID
    assert re.fullmatch(r"cadence-[0-9a-f]{32}", btc["run_id"])
    assert btc_prediction["prediction_id"] == alias_prediction["prediction_id"]
    assert btc_prediction["prediction_id"] == f"{EXPECTED_CADENCE_RUN_ID}:4H"
    assert btc_prediction["prediction_origin"] == "SCHEDULED_SHADOW_EVIDENCE"
    _clear_pending(alias)


def test_cadence_identity_has_no_clock_workflow_or_retry_input() -> None:
    source = inspect.getsource(analysis_service._deterministic_cadence_run_id)  # noqa: SLF001
    for forbidden in (
        "uuid4",
        "datetime.now",
        "utcnow",
        "time.time",
        "workflow",
        "retry",
    ):
        assert forbidden not in source


def test_different_closed_candle_changes_cadence_identity(monkeypatch) -> None:
    first = _analyze(monkeypatch, deterministic=True)
    first_prediction = _prediction_row(first)
    _clear_pending(first)
    later_as_of = FIXED_NOW + timedelta(hours=4)
    later = replace(
        make_snapshot(provider="binance"),
        candles=make_candles(as_of_utc=later_as_of),
        as_of_utc=later_as_of,
    )
    second = _analyze(monkeypatch, deterministic=True, snapshot=later)
    second_prediction = _prediction_row(second)

    assert first["run_id"] != second["run_id"]
    assert first_prediction["prediction_id"] != second_prediction["prediction_id"]
    _clear_pending(second)


def test_deterministic_identity_changes_only_identifiers_and_hash(monkeypatch) -> None:
    monkeypatch.setattr(analysis_service, "uuid4", lambda: UUID(int=79))
    normal = _analyze(monkeypatch)
    normal_prediction = _prediction_row(normal)
    _clear_pending(normal)
    deterministic = _analyze(monkeypatch, deterministic=True)
    deterministic_prediction = _prediction_row(deterministic)

    assert normal["run_id"] != deterministic["run_id"]
    assert normal["analysis_hash"] != deterministic["analysis_hash"]
    assert normal_prediction["prediction_id"] != deterministic_prediction["prediction_id"]
    for key in (
        "probability_state",
        "score_stack",
        "gate_result",
        "decision_synthesis",
        "quant_v2",
        "derivatives_intelligence",
    ):
        assert normal[key] == deterministic[key]
    assert (
        normal["decision_synthesis"]["trade_plan_skeleton"]
        == deterministic["decision_synthesis"]["trade_plan_skeleton"]
    )
    _clear_pending(deterministic)


@pytest.mark.parametrize(
    "invalid_kind",
    ["no_candles", "open", "invalid_interval", "naive", "mismatch"],
)
def test_deterministic_identity_fails_closed_without_uuid_or_persistence(
    monkeypatch,
    invalid_kind: str,
) -> None:
    snapshot = make_snapshot(provider="binance")
    if invalid_kind == "no_candles":
        snapshot = replace(snapshot, candles=())
    elif invalid_kind == "open":
        last = snapshot.candles[-1]
        open_last = replace(last, close_time_utc=snapshot.as_of_utc + timedelta(seconds=1))
        snapshot = replace(snapshot, candles=(*snapshot.candles[:-1], open_last))
    elif invalid_kind == "invalid_interval":
        last = snapshot.candles[-1]
        invalid_last = replace(last, open_time_utc=last.close_time_utc)
        snapshot = replace(snapshot, candles=(*snapshot.candles[:-1], invalid_last))
    elif invalid_kind == "naive":
        last = snapshot.candles[-1]
        naive_last = replace(last, close_time_utc=last.close_time_utc.replace(tzinfo=None))
        snapshot = replace(snapshot, candles=(*snapshot.candles[:-1], naive_last))
    else:
        snapshot = replace(snapshot, normalized_symbol="ETH/USDT")
        monkeypatch.setattr(
            analysis_service,
            "select_market_data",
            lambda *args, **kwargs: ProviderSelectionResult(
                snapshot=snapshot,
                provider_state={"status": "OK"},
                data_quality={"is_live_data": True},
            ),
        )
    if invalid_kind != "mismatch":
        monkeypatch.setattr(analysis_service, "select_market_data", _selection(snapshot))
    monkeypatch.setattr(
        analysis_service,
        "uuid4",
        lambda: pytest.fail("fail-closed cadence path must not request a UUID"),
    )
    pending_before = set(analysis_service._PENDING_PREDICTION_ROWS)  # noqa: SLF001
    run_store = InMemoryRunStore()

    with pytest.raises(HTTPException) as exc_info:
        analysis_service.analyze_request(
            AnalysisRequest(symbol="BTC", timeframe="4H"),
            settings=Settings(data_mode="fixture"),
            run_store=run_store,
            deterministic_identity=True,
        )

    assert exc_info.value.status_code == 400
    assert run_store.runs == {}
    assert set(analysis_service._PENDING_PREDICTION_ROWS) == pending_before  # noqa: SLF001


def test_cadence_identity_helper_rejects_noncanonical_symbol_and_timeframe() -> None:
    snapshot = make_snapshot(provider="binance")
    for symbol, timeframe in (("BTCUSDT", "4H"), ("BTC/USDT", "2H")):
        with pytest.raises(HTTPException):
            analysis_service._deterministic_cadence_run_id(  # noqa: SLF001
                normalized_symbol=symbol,
                timeframe=timeframe,
                snapshot=snapshot,
            )


def test_sync_persist_is_immutable_ordered_and_idempotent(monkeypatch) -> None:
    monkeypatch.setattr(
        analysis_service,
        "build_derivatives_intelligence",
        _unavailable_derivatives_block,
    )
    payload = _analyze(monkeypatch, deterministic=True, derivatives=True)
    payload_before = deepcopy(payload)

    class RecordingRepository(InMemoryPersistenceRepository):
        def __init__(self) -> None:
            super().__init__()
            self.artifact_calls: list[str] = []

        def save_prediction(self, row):
            self.artifact_calls.append("prediction")
            return super().save_prediction(row)

        def save_feature_snapshot(self, row):
            self.artifact_calls.append("feature_snapshot")
            return super().save_feature_snapshot(row)

        def save_derivatives_snapshot(self, row):
            self.artifact_calls.append("derivatives_snapshot")
            return super().save_derivatives_snapshot(row)

    repository = RecordingRepository()
    first = analysis_service.persist_analysis_now(payload, repository)
    second = analysis_service.persist_analysis_now(payload, repository)

    assert payload == payload_before
    assert first == {
        "prediction": "STATELESS",
        "feature_snapshot": "INSERTED",
        "derivatives_snapshot": "INSERTED",
        "overall": "OK",
    }
    assert second == {
        "prediction": "STATELESS",
        "feature_snapshot": "IDENTICAL_DUPLICATE",
        "derivatives_snapshot": "IDENTICAL_DUPLICATE",
        "overall": "OK",
    }
    assert repository.artifact_calls == [
        "prediction",
        "feature_snapshot",
        "derivatives_snapshot",
        "prediction",
        "feature_snapshot",
        "derivatives_snapshot",
    ]
    prediction = _prediction_row(payload)
    assert repository._predictions[prediction["prediction_id"]]["prediction_origin"] == (  # noqa: SLF001
        "SCHEDULED_SHADOW_EVIDENCE"
    )
    assert set(first) == {
        "prediction",
        "feature_snapshot",
        "derivatives_snapshot",
        "overall",
    }
    json.dumps(first, allow_nan=False)
    _clear_pending(payload)


def test_sync_persist_contains_prediction_and_dependent_failures(monkeypatch) -> None:
    payload = _analyze(monkeypatch, deterministic=True)

    class PredictionUnavailable(InMemoryPersistenceRepository):
        def __init__(self) -> None:
            super().__init__()
            self.feature_attempted = False

        def save_prediction(self, row):
            return "UNAVAILABLE"

        def save_feature_snapshot(self, row):
            self.feature_attempted = True
            return FeatureSnapshotWriteStatus.INSERTED

    parent_failure = PredictionUnavailable()
    result = analysis_service.persist_analysis_now(payload, parent_failure)
    assert result == {
        "prediction": "UNAVAILABLE",
        "feature_snapshot": None,
        "derivatives_snapshot": None,
        "overall": "UNAVAILABLE",
    }
    assert parent_failure.feature_attempted is False

    class FeatureUnavailable(InMemoryPersistenceRepository):
        def save_feature_snapshot(self, row):
            return FeatureSnapshotWriteStatus.UNAVAILABLE

    partial = analysis_service.persist_analysis_now(payload, FeatureUnavailable())
    assert partial["prediction"] == "STATELESS"
    assert partial["feature_snapshot"] == "UNAVAILABLE"
    assert partial["derivatives_snapshot"] is None
    assert partial["overall"] == "PARTIAL"
    _clear_pending(payload)


def test_sync_persist_sanitizes_unexpected_exception(monkeypatch) -> None:
    monkeypatch.setattr(
        analysis_service,
        "build_derivatives_intelligence",
        _unavailable_derivatives_block,
    )
    payload = _analyze(monkeypatch, deterministic=True, derivatives=True)

    class ExplodingRepository(InMemoryPersistenceRepository):
        def save_derivatives_snapshot(self, row):
            raise RuntimeError("credential=forbidden raw database detail")

    result = analysis_service.persist_analysis_now(payload, ExplodingRepository())
    serialized = json.dumps(result)

    assert result["prediction"] == "STATELESS"
    assert result["feature_snapshot"] == "INSERTED"
    assert result["derivatives_snapshot"] is None
    assert result["overall"] == "UNAVAILABLE"
    assert "credential" not in serialized
    assert "database" not in serialized
    _clear_pending(payload)


def test_sync_persist_without_pending_work_is_unavailable_and_does_not_raise() -> None:
    result = analysis_service.persist_analysis_now(
        {"run_id": "unknown"},
        InMemoryPersistenceRepository(),
    )
    assert result == {
        "prediction": None,
        "feature_snapshot": None,
        "derivatives_snapshot": None,
        "overall": "UNAVAILABLE",
    }
