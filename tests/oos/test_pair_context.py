from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from crypto_probability_engine.adapters.provider_selection import ProviderSelectionResult
from crypto_probability_engine.api import analysis_service
from crypto_probability_engine.api.schemas import AnalysisRequest
from crypto_probability_engine.config.defaults import METHODOLOGY_VERSION
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.oos.pair_context import (
    OOSArm,
    PairInvalidError,
    build_oos_pair_context,
    is_derivatives_run_id,
    is_oos_run_id,
)
from crypto_probability_engine.persistence.repository import (
    InMemoryPersistenceRepository,
    OOSArmIdentityConflict,
    SupabasePersistenceRepository,
    SupabaseRestRepository,
)
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from tests.fixtures.market_data import make_snapshot

ROOT = Path(__file__).resolve().parents[2]
SKILL_EVIDENCE = {
    "verdict": "INSUFFICIENT_EVIDENCE",
    "n": 0,
    "observed_directional_rate": None,
}


def _pair(*, candidate_features=None):
    snapshot = make_snapshot(provider="binance")
    return build_oos_pair_context(
        market_snapshot=snapshot,
        resolved_skill_evidence=SKILL_EVIDENCE,
        information_cutoff=snapshot.as_of_utc,
        decision_band_frac=0.002,
        candidate_features=candidate_features,
    )


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


def _analyze_pair(monkeypatch, pair):
    seen_snapshots = []
    real_pipeline = analysis_service.run_quant_pipeline

    def capturing_pipeline(snapshot, provider_state):
        seen_snapshots.append(snapshot)
        return real_pipeline(snapshot, provider_state)

    monkeypatch.setattr(analysis_service, "select_market_data", _selection(pair.snapshot))
    monkeypatch.setattr(analysis_service, "run_quant_pipeline", capturing_pipeline)
    monkeypatch.setattr(
        analysis_service,
        "get_cached_skill_evidence",
        lambda _timeframe: pytest.fail("pair skill evidence must bypass the TTL cache"),
    )
    payloads = []
    for arm, methodology in (
        (OOSArm.BASELINE, METHODOLOGY_VERSION),
        (OOSArm.CANDIDATE, "candidate-version-label"),
    ):
        payloads.append(
            analysis_service.analyze_request(
                AnalysisRequest(symbol="BTC", timeframe="4H"),
                settings=Settings(data_mode="fixture"),
                run_store=InMemoryRunStore(),
                prediction_origin="SCHEDULED_SHADOW_EVIDENCE",
                methodology_version=methodology,
                pair_context=pair,
                arm=arm,
            )
        )
    return payloads, seen_snapshots


def test_t1_two_arms_on_one_input_persist_two_rows(monkeypatch) -> None:
    pair = _pair()
    payloads, _ = _analyze_pair(monkeypatch, pair)
    rows, snapshots, failed, _, derivatives_failed = (
        analysis_service._peek_prediction_persistence(payloads[0])  # noqa: SLF001
    )
    repository = InMemoryPersistenceRepository()
    try:
        result = analysis_service.persist_analysis_now(payloads[0], repository)
    finally:
        analysis_service._pop_prediction_persistence(payloads[0])  # noqa: SLF001

    assert not failed
    assert not derivatives_failed
    assert len(rows) == len(snapshots) == 2
    assert result["overall"] == "OK"
    assert set(repository._predictions) == {  # noqa: SLF001
        f"{pair.run_id}:4H:BASELINE",
        f"{pair.run_id}:4H:CANDIDATE",
    }


def test_t2_arm_identity_clash_surfaces_and_ordinary_idempotence_remains() -> None:
    repository = InMemoryPersistenceRepository()
    ordinary = {"prediction_id": "run_existing:4H"}
    arm = {
        "prediction_id": f"{'oosb-' + 'a' * 32}:4H:BASELINE",
        "prediction_origin": "SCHEDULED_SHADOW_EVIDENCE",
    }

    assert repository.save_prediction(ordinary) == "STATELESS"
    assert repository.save_prediction(ordinary) == "STATELESS"
    assert repository.save_prediction(arm) == "STATELESS"
    with pytest.raises(OOSArmIdentityConflict, match="already occupied"):
        repository.save_prediction(arm)


def test_t2_postgres_oos_write_has_no_ignore_conflict_path() -> None:
    class Cursor:
        def __init__(self):
            self.statements = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, statement, params=None):
            del params
            self.statements.append(str(statement))

    class Connection:
        def __init__(self, cursor):
            self._cursor = cursor

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return self._cursor

    class Pool:
        def __init__(self, cursor):
            self._cursor = cursor

        def connection(self, timeout=None):
            del timeout
            return Connection(self._cursor)

    cursor = Cursor()
    repository = SupabasePersistenceRepository(
        "postgresql://example.invalid/db",
        pool_factory=lambda: Pool(cursor),
    )
    row = {
        "prediction_id": f"oosb-{'b' * 32}:4H:CANDIDATE",
        "prediction_origin": "SCHEDULED_SHADOW_EVIDENCE",
    }

    assert repository.save_prediction(row) == "OK"
    insert = next(statement for statement in cursor.statements if "INSERT" in statement)
    assert "ON CONFLICT" not in insert
    with pytest.raises(OOSArmIdentityConflict):
        repository.save_prediction(row)


def test_t2_rest_oos_write_has_no_ignore_conflict_path() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json=[])

    repository = SupabaseRestRepository(
        "https://project.example.supabase.co",
        "test-service-role-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    row = {
        "prediction_id": f"oosb-{'c' * 32}:4H:BASELINE",
        "prediction_origin": "SCHEDULED_SHADOW_EVIDENCE",
    }

    assert repository.save_prediction(row) == "OK"
    assert "on_conflict" not in seen[0].url.params
    assert seen[0].headers["prefer"] == "return=minimal"
    with pytest.raises(OOSArmIdentityConflict):
        repository.save_prediction(row)
    assert len(seen) == 1


def test_t3_oos_and_derivatives_namespaces_are_disjoint_both_directions() -> None:
    oos = "oosb-" + "0" * 32
    cadence = "cadence-" + "f" * 32

    assert is_oos_run_id(oos)
    assert not is_derivatives_run_id(oos)
    assert is_derivatives_run_id(cadence)
    assert not is_oos_run_id(cadence)
    assert re.fullmatch(r"oosb-[0-9a-f]{32}", _pair().run_id)


def test_t4_target_is_derived_once_and_shared_by_both_arms() -> None:
    pair = _pair()
    baseline = pair.for_arm(OOSArm.BASELINE)
    candidate = pair.for_arm(OOSArm.CANDIDATE)

    assert baseline.target is candidate.target is pair.target
    assert (
        baseline.reference_close_utc,
        baseline.reference_price,
        baseline.horizon_end_utc,
        baseline.decision_band_frac,
    ) == (
        candidate.reference_close_utc,
        candidate.reference_price,
        candidate.horizon_end_utc,
        candidate.decision_band_frac,
    )


def test_t5_both_arms_receive_same_snapshot_object_and_skill_value(monkeypatch) -> None:
    pair = _pair()
    payloads, seen_snapshots = _analyze_pair(monkeypatch, pair)
    try:
        assert seen_snapshots[0] is seen_snapshots[1] is pair.snapshot
        assert pair.for_arm("BASELINE").resolved_skill_evidence is (
            pair.for_arm("CANDIDATE").resolved_skill_evidence
        )
        assert payloads[0]["skill_evidence"] == payloads[1]["skill_evidence"]
    finally:
        analysis_service._pop_prediction_persistence(payloads[0])  # noqa: SLF001


def test_t6_one_cutoff_bounds_every_admitted_candidate_feature() -> None:
    cutoff = make_snapshot(provider="binance").as_of_utc
    pair = _pair(
        candidate_features={
            "at_cutoff": {"value": 1, "point_in_time_utc": cutoff},
            "before": {
                "value": 2,
                "point_in_time_utc": cutoff - timedelta(seconds=1),
            },
        }
    )

    assert pair.for_arm("BASELINE").candidate_features == {}
    admitted = pair.for_arm("CANDIDATE").candidate_features.values()
    assert admitted
    assert all(feature.point_in_time_utc <= pair.information_cutoff for feature in admitted)


def test_t7_feature_after_cutoff_invalidates_whole_pair() -> None:
    snapshot = make_snapshot(provider="binance")
    with pytest.raises(PairInvalidError, match="after the information cutoff"):
        build_oos_pair_context(
            market_snapshot=snapshot,
            resolved_skill_evidence=SKILL_EVIDENCE,
            information_cutoff=snapshot.as_of_utc,
            decision_band_frac=0.002,
            candidate_features={
                "future": {
                    "value": 1,
                    "point_in_time_utc": snapshot.as_of_utc + timedelta(microseconds=1),
                }
            },
        )


def test_t8_missing_point_in_time_invalidates_whole_pair() -> None:
    with pytest.raises(PairInvalidError, match="timezone-aware"):
        _pair(candidate_features={"missing": {"value": 1}})


def test_t8_unparseable_point_in_time_invalidates_whole_pair() -> None:
    with pytest.raises(PairInvalidError, match="unparseable"):
        _pair(
            candidate_features={
                "bad": {"value": 1, "point_in_time_utc": "not-a-timestamp"}
            }
        )


def test_t8_timezone_naive_point_in_time_invalidates_whole_pair() -> None:
    with pytest.raises(PairInvalidError, match="timezone-aware"):
        _pair(
            candidate_features={
                "naive": {
                    "value": 1,
                    "point_in_time_utc": datetime(2026, 1, 1),
                }
            }
        )


def test_t9_derivatives_readiness_buckets_exclude_oos_rows() -> None:
    sql = (ROOT / "sql" / "phase_2d3b_readiness_proof.sql").read_text(
        encoding="utf-8"
    )
    exclusion = "pred.run_id !~ '^oosb-[0-9a-f]{32}$'"

    assert sql.count(exclusion) == 2
    assert re.search(
        rf"v1_methodology[\s\S]+scheduled_origin[\s\S]+{re.escape(exclusion)}",
        sql,
    )
    assert re.search(
        rf"v0_methodology[\s\S]+scheduled_origin[\s\S]+{re.escape(exclusion)}",
        sql,
    )


def test_t10_oos_shadow_row_cannot_enter_user_requested_cohort() -> None:
    pair = _pair()
    with pytest.raises(PairInvalidError, match="SCHEDULED_SHADOW_EVIDENCE"):
        analysis_service._oos_arm_context(  # noqa: SLF001
            pair_context=pair,
            arm="BASELINE",
            prediction_origin="USER_REQUESTED",
            deterministic_identity=False,
        )
    with pytest.raises(ValueError, match="shadow-evidence origin"):
        InMemoryPersistenceRepository().save_prediction(
            {
                "prediction_id": f"{pair.run_id}:4H:BASELINE",
                "prediction_origin": "USER_REQUESTED",
            }
        )


def test_t11_both_arms_have_zero_served_decision_influence(monkeypatch) -> None:
    pair = _pair(
        candidate_features={
            "shadow_only": {
                "value": 999,
                "point_in_time_utc": make_snapshot(provider="binance").as_of_utc,
            }
        }
    )
    payloads, _ = _analyze_pair(monkeypatch, pair)
    try:
        assert pair.decision_influence_frac == 0.0
        assert pair.for_arm("BASELINE").decision_influence_frac == 0.0
        assert pair.for_arm("CANDIDATE").decision_influence_frac == 0.0
        assert payloads[0]["decision_synthesis"] == payloads[1]["decision_synthesis"]
        assert payloads[0]["gate_result"] == payloads[1]["gate_result"]
    finally:
        analysis_service._pop_prediction_persistence(payloads[0])  # noqa: SLF001


def test_t12_ordinary_identity_and_response_payload_are_byte_identical(monkeypatch) -> None:
    snapshot = make_snapshot(provider="binance")
    monkeypatch.setattr(analysis_service, "select_market_data", _selection(snapshot))
    monkeypatch.setattr(analysis_service, "uuid4", lambda: UUID(int=73))
    monkeypatch.setattr(
        analysis_service,
        "get_cached_skill_evidence",
        lambda _timeframe: SKILL_EVIDENCE,
    )

    omitted = analysis_service.analyze_request(
        AnalysisRequest(symbol="BTC", timeframe="4H"),
        settings=Settings(data_mode="fixture"),
        run_store=InMemoryRunStore(),
    )
    omitted_rows = analysis_service._pop_prediction_persistence(omitted)[0]  # noqa: SLF001
    explicit = analysis_service.analyze_request(
        AnalysisRequest(symbol="BTC", timeframe="4H"),
        settings=Settings(data_mode="fixture"),
        run_store=InMemoryRunStore(),
        methodology_version="heuristic-v1-wave4b0",
        pair_context=None,
        arm=None,
    )
    explicit_rows = analysis_service._pop_prediction_persistence(explicit)[0]  # noqa: SLF001

    expected = "run_00000000000000000000000000000049:4H"
    assert omitted_rows[0]["prediction_id"] == expected
    assert explicit_rows[0]["prediction_id"] == expected
    assert omitted == explicit
    omitted_bytes = json.dumps(omitted, sort_keys=True, separators=(",", ":")).encode()
    explicit_bytes = json.dumps(explicit, sort_keys=True, separators=(",", ":")).encode()
    assert omitted_bytes == explicit_bytes
    assert hashlib.sha256(omitted_bytes).digest() == hashlib.sha256(explicit_bytes).digest()
