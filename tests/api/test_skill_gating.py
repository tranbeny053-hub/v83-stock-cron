from __future__ import annotations

import json
import time
from threading import Event

import pytest
from fastapi.testclient import TestClient

from crypto_probability_engine.api.app import create_app
from crypto_probability_engine.api.auth import hash_code, session_limiter
from crypto_probability_engine.api.schemas import validate_analysis_response
from crypto_probability_engine.calibration.service import refresh_skill_evidence_cache
from crypto_probability_engine.calibration.skill import (
    cache_skill_evidence,
    classify_directional_skill,
    clear_skill_evidence_cache,
)
from crypto_probability_engine.config.settings import Settings


@pytest.fixture(autouse=True)
def isolate_skill_cache() -> None:
    clear_skill_evidence_cache()
    yield
    clear_skill_evidence_cache()


def _client() -> TestClient:
    session_limiter.reset()
    settings = Settings(
        access_code_hash=hash_code("operator-test-code"),
        session_signing_key="test-signing-key",
        session_cookie_secure=False,
        data_mode="fixture",
    )
    client = TestClient(create_app(settings))
    response = client.post("/v1/auth/login", json={"code": "operator-test-code"})
    assert response.status_code == 200
    return client


def _analyze(client: TestClient, timeframe: str = "4H") -> dict:
    response = client.post(
        "/v1/analyze",
        json={"symbol": "BTC", "analysis_mode": "METRICS_ONLY", "timeframe": timeframe},
    )
    assert response.status_code == 200
    payload = response.json()
    validate_analysis_response(payload)
    return payload


def _probability_bytes(payload: dict) -> bytes:
    return json.dumps(
        payload["probability_state"]["horizons"],
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def test_probability_triplets_are_byte_identical_with_gate_active_and_inactive() -> None:
    client = _client()
    cache_skill_evidence("4H", classify_directional_skill(151, 102))
    inactive = _analyze(client)

    cache_skill_evidence("4H", classify_directional_skill(151, 75))
    active = _analyze(client)

    assert _probability_bytes(active) == _probability_bytes(inactive)
    assert inactive["gate_result"]["hard_gate_passed"] is True
    assert active["gate_result"]["hard_gate_passed"] is False
    assert active["frontend_display"]["disposition"] == "NO_TRADE"
    assert active["score_stack"]["disposition"] == "ELEVATED_RISK_AVOID"
    assert active["skill_evidence"] == {
        "verdict": "NO_DEMONSTRATED_SKILL",
        "n": 151,
        "observed_directional_rate": 75 / 151,
    }


def test_probability_sum_invariant_holds_under_skill_gating() -> None:
    cache_skill_evidence("4H", classify_directional_skill(151, 75))
    payload = _analyze(_client())

    for horizon in payload["probability_state"]["horizons"].values():
        assert (
            horizon["p_up_frac"]
            + horizon["p_down_frac"]
            + horizon["p_timeout_frac"]
            == 1.0
        )
    assert payload["decision_brief"]["action"] == "NO_TRADE"
    assert payload["decision_synthesis"]["decision_synthesis"]["label"] == "NO_TRADE"


def test_no_database_cache_miss_returns_200_with_insufficient_evidence() -> None:
    payload = _analyze(_client(), timeframe="1M")

    assert payload["skill_evidence"] == {
        "verdict": "INSUFFICIENT_EVIDENCE",
        "n": 0,
        "observed_directional_rate": None,
    }
    assert payload["frontend_display"]["disposition"] == "NO_TRADE"
    assert payload["probability_state"]["horizons"]["H_primary"]


def test_persistence_exception_cannot_escape_analysis_path() -> None:
    class BrokenCalibrationRepository:
        def fetch_resolved_prediction_outcomes_for_calibration(self, **kwargs) -> list[dict]:
            raise ConnectionError("database unavailable")

    refresh_skill_evidence_cache(BrokenCalibrationRepository())  # type: ignore[arg-type]
    payload = _analyze(_client())

    assert payload["skill_evidence"]["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert payload["gate_result"]["hard_gate_passed"] is False
    assert payload["probability_state"]["horizons"]["H_primary"]


def test_slow_skill_repository_never_adds_request_latency() -> None:
    entered = Event()
    release = Event()

    class SlowCalibrationRepository:
        def repository_type(self) -> str:
            return "SUPABASE_POSTGRES"

        def fetch_resolved_prediction_outcomes_for_calibration(self, **kwargs) -> list[dict]:
            entered.set()
            release.wait(timeout=1.0)
            raise TimeoutError("slow calibration read")

    client = _client()
    client.app.state.skill_evidence_repository = SlowCalibrationRepository()
    started = time.perf_counter()
    try:
        payload = _analyze(client)
        elapsed = time.perf_counter() - started
    finally:
        release.set()

    assert elapsed < 0.5
    assert payload["skill_evidence"]["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert entered.wait(timeout=1.0)
