from __future__ import annotations

import copy
import json
import re

import pytest
from fastapi.testclient import TestClient

from crypto_probability_engine.api import analysis_service
from crypto_probability_engine.api.app import create_app
from crypto_probability_engine.api.auth import hash_code, session_limiter
from crypto_probability_engine.api.schemas import AnalysisRequest, validate_analysis_response
from crypto_probability_engine.calibration.skill import (
    cache_skill_evidence,
    classify_directional_skill,
    clear_skill_evidence_cache,
    evidence_for_gate,
)
from crypto_probability_engine.config.defaults import (
    DISTRIBUTIONAL_METHODOLOGY_VERSION,
    METHODOLOGY_VERSION,
)
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.oos.pair_context import (
    OOS_PREDICTION_ORIGIN,
    OOSArm,
    build_oos_pair_context,
)
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from crypto_probability_engine.utils.sanitize import sanitize_for_export
from tests.fixtures.market_data import make_snapshot

_HOLD = {
    "active": True,
    "hold_reason": "EVIDENCE_UNIT_UNDER_CORRECTION",
    "legacy_verdict": "SKILL_DEMONSTRATED",
}
_HOLD_HEADLINE = "Directional candidates are paused"
_HOLD_DETAIL = (
    "The directional-accuracy evidence is being recounted so that repeated analyses of "
    "one candle and overlapping outcome windows are no longer counted as independent "
    "results. Until the corrected check is in place and validated, no directional "
    "candidate is issued on any timeframe. Any uncorrected result is still reported for "
    "diagnostics."
)


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


def _analyze(
    client: TestClient,
    timeframe: str = "4H",
    *,
    validate: bool = True,
) -> dict:
    response = client.post(
        "/v1/analyze",
        json={"symbol": "BTC", "analysis_mode": "METRICS_ONLY", "timeframe": timeframe},
    )
    assert response.status_code == 200
    payload = response.json()
    if validate:
        validate_analysis_response(payload)
    return payload


def _probability_bytes(payload: dict) -> bytes:
    return json.dumps(
        payload["probability_state"]["horizons"],
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _skill_reason(payload: dict) -> dict:
    return next(
        reason
        for reason in payload["frontend_display"]["blocking_reasons"]
        if reason["code"] == "SKILL_NOT_DEMONSTRATED"
    )


@pytest.mark.parametrize(
    ("evidence", "held"),
    [
        (
            {
                "verdict": "SKILL_DEMONSTRATED",
                "n": 151,
                "observed_directional_rate": 102 / 151,
            },
            True,
        ),
        (
            {
                "verdict": "NO_DEMONSTRATED_SKILL",
                "n": 151,
                "observed_directional_rate": 75 / 151,
            },
            False,
        ),
        (
            {
                "verdict": "INSUFFICIENT_EVIDENCE",
                "n": 12,
                "observed_directional_rate": 7 / 12,
            },
            False,
        ),
        (None, True),
        ("not-a-mapping", True),
    ],
)
@pytest.mark.parametrize("legacy_pass", [False, True])
def test_t1_evidence_for_gate_matrix(
    monkeypatch: pytest.MonkeyPatch,
    evidence: object,
    held: bool,
    legacy_pass: bool,
) -> None:
    monkeypatch.setattr(
        "crypto_probability_engine.calibration.skill.LEGACY_PASS_LIFTS_HARD_BLOCK",
        legacy_pass,
    )
    original = copy.deepcopy(evidence)

    gate_evidence, hold = evidence_for_gate(evidence)

    assert evidence == original
    if legacy_pass:
        assert gate_evidence is evidence
        assert hold is None
    elif held:
        expected_n = 151 if isinstance(evidence, dict) else 0
        expected_rate = (
            evidence.get("observed_directional_rate")
            if isinstance(evidence, dict)
            else None
        )
        expected_verdict = evidence.get("verdict") if isinstance(evidence, dict) else None
        assert gate_evidence == {
            "verdict": "INSUFFICIENT_EVIDENCE",
            "n": expected_n,
            "observed_directional_rate": expected_rate,
        }
        assert hold == {**_HOLD, "legacy_verdict": expected_verdict}
        assert gate_evidence is not evidence
        assert hold is not evidence
    else:
        assert gate_evidence is evidence
        assert hold is None


def test_t2_analyze_holds_cached_legacy_pass() -> None:
    cache_skill_evidence("4H", classify_directional_skill(151, 102))

    payload = _analyze(_client())

    gate = payload["gate_result"]
    assert "SKILL_NOT_DEMONSTRATED" in gate["hard_blocks"]
    assert gate["hard_gate_passed"] is False
    assert gate["directional_evidence_hold"] == _HOLD
    assert payload["frontend_display"]["disposition"] == "NO_TRADE"
    assert payload["score_stack"]["disposition"] == "ELEVATED_RISK_AVOID"
    assert payload["skill_evidence"]["verdict"] == "SKILL_DEMONSTRATED"
    synthesis = payload["decision_synthesis"]
    assert synthesis["decision_synthesis"]["label"] == "NO_TRADE"
    assert synthesis["trade_plan_skeleton"]["setup_direction"] == "NEUTRAL"
    validate_analysis_response(payload)


def test_t3_analyze_batch_holds_every_successful_result() -> None:
    cache_skill_evidence("4H", classify_directional_skill(151, 102))
    client = _client()

    response = client.post(
        "/v1/analyze_batch",
        json={
            "requests": [
                {"symbol": "BTC", "analysis_mode": "METRICS_ONLY", "timeframe": "4H"},
                {"symbol": "ETH", "analysis_mode": "METRICS_ONLY", "timeframe": "4H"},
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["results"]) == 2
    assert not payload["errors"]
    for result in payload["results"]:
        assert result["gate_result"]["hard_gate_passed"] is False
        assert "SKILL_NOT_DEMONSTRATED" in result["gate_result"]["hard_blocks"]
        assert result["gate_result"]["directional_evidence_hold"] == _HOLD
        assert result["skill_evidence"]["verdict"] == "SKILL_DEMONSTRATED"
        validate_analysis_response(result)


@pytest.mark.parametrize(
    ("hits", "expected_headline"),
    [
        (75, "Directional accuracy did not clear the evidence bar"),
        (1, "Directional skill has not been evaluated"),
    ],
)
def test_t4_existing_blocking_evidence_paths_are_unchanged(
    hits: int,
    expected_headline: str,
) -> None:
    n = 151 if hits == 75 else 1
    cache_skill_evidence("4H", classify_directional_skill(n, hits))

    payload = _analyze(_client())

    assert payload["gate_result"]["hard_gate_passed"] is False
    assert "SKILL_NOT_DEMONSTRATED" in payload["gate_result"]["hard_blocks"]
    assert "directional_evidence_hold" not in payload["gate_result"]
    assert _skill_reason(payload)["headline"] == expected_headline


def test_t5_missing_evidence_is_held_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(analysis_service, "_skill_evidence_for_analysis", lambda _timeframe: None)

    payload = _analyze(_client(), validate=False)

    assert payload["skill_evidence"] is None
    assert payload["gate_result"]["hard_gate_passed"] is False
    assert "SKILL_NOT_DEMONSTRATED" in payload["gate_result"]["hard_blocks"]
    assert payload["gate_result"]["directional_evidence_hold"] == {
        **_HOLD,
        "legacy_verdict": None,
    }
    assert _skill_reason(payload) == {
        "code": "SKILL_NOT_DEMONSTRATED",
        "headline": _HOLD_HEADLINE,
        "detail": _HOLD_DETAIL,
    }


def test_t6_probability_bytes_ignore_hold_and_gate_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client()
    cache_skill_evidence("4H", classify_directional_skill(151, 102))
    held = _analyze(client)

    cache_skill_evidence("4H", classify_directional_skill(151, 75))
    blocked = _analyze(client)

    monkeypatch.setattr(
        "crypto_probability_engine.calibration.skill.LEGACY_PASS_LIFTS_HARD_BLOCK",
        True,
    )
    cache_skill_evidence("4H", classify_directional_skill(151, 102))
    legacy_pass = _analyze(client)

    assert _probability_bytes(held) == _probability_bytes(blocked)
    assert _probability_bytes(held) == _probability_bytes(legacy_pass)
    assert held["gate_result"]["hard_gate_passed"] is False
    assert blocked["gate_result"]["hard_gate_passed"] is False
    assert legacy_pass["gate_result"]["hard_gate_passed"] is True


def test_t7_hold_preserves_preexisting_hard_gate_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_pipeline = analysis_service.run_quant_pipeline

    def pipeline_with_existing_block(*args, **kwargs):
        result = real_pipeline(*args, **kwargs)
        result["gate_result"] = {
            **result["gate_result"],
            "action": "ABORT",
            "hard_gate_passed": False,
            "hard_blocks": ["EPISTEMIC_VOID"],
            "score_ignored": True,
            "news_ignored": True,
        }
        return result

    monkeypatch.setattr(analysis_service, "run_quant_pipeline", pipeline_with_existing_block)
    cache_skill_evidence("4H", classify_directional_skill(151, 102))

    payload = _analyze(_client())

    assert payload["gate_result"]["action"] == "ABORT"
    assert payload["gate_result"]["hard_blocks"] == [
        "EPISTEMIC_VOID",
        "SKILL_NOT_DEMONSTRATED",
    ]
    assert payload["gate_result"]["directional_evidence_hold"] == _HOLD


def test_t8_oos_arms_hold_resolved_legacy_pass() -> None:
    snapshot = make_snapshot(provider="binance")
    pair = build_oos_pair_context(
        market_snapshot=snapshot,
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
        resolved_skill_evidence={
            "verdict": "SKILL_DEMONSTRATED",
            "n": 151,
            "observed_directional_rate": 102 / 151,
        },
        information_cutoff=snapshot.as_of_utc,
        decision_band_frac=0.002,
    )
    payloads = []
    try:
        for arm, methodology_version in (
            (OOSArm.BASELINE, METHODOLOGY_VERSION),
            (OOSArm.CANDIDATE, DISTRIBUTIONAL_METHODOLOGY_VERSION),
        ):
            payloads.append(
                analysis_service.analyze_request(
                    AnalysisRequest(symbol="BTC", timeframe="4H"),
                    settings=Settings(data_mode="fixture"),
                    run_store=InMemoryRunStore(),
                    prediction_origin=OOS_PREDICTION_ORIGIN,
                    methodology_version=methodology_version,
                    pair_context=pair,
                    arm=arm,
                )
            )

        for payload in payloads:
            assert payload["gate_result"]["hard_gate_passed"] is False
            assert "SKILL_NOT_DEMONSTRATED" in payload["gate_result"]["hard_blocks"]
            assert payload["gate_result"]["directional_evidence_hold"] == _HOLD
            assert "blocking_reasons" not in payload["frontend_display"]
    finally:
        if payloads:
            analysis_service._pop_prediction_persistence(payloads[0])  # noqa: SLF001


def test_t9_hold_copy_and_export_are_unmasked() -> None:
    cache_skill_evidence("4H", classify_directional_skill(151, 102))

    payload = _analyze(_client())
    reason = _skill_reason(payload)

    assert reason["headline"] == _HOLD_HEADLINE
    assert reason["detail"] == _HOLD_DETAIL
    assert re.search(r"\bskill\b", _HOLD_HEADLINE, re.IGNORECASE) is None
    assert re.search(r"\bskill\b", _HOLD_DETAIL, re.IGNORECASE) is None
    sanitized = sanitize_for_export(payload["detail_view"])
    assert sanitized["invalidation_detail"]["directional_evidence_hold"] == _HOLD


def test_t10_rollback_restores_legacy_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "crypto_probability_engine.calibration.skill.LEGACY_PASS_LIFTS_HARD_BLOCK",
        True,
    )
    cache_skill_evidence("4H", classify_directional_skill(151, 102))

    payload = _analyze(_client())

    assert payload["gate_result"]["hard_gate_passed"] is True
    assert "directional_evidence_hold" not in payload["gate_result"]
    serialized_display = json.dumps(payload["frontend_display"])
    assert _HOLD_HEADLINE not in serialized_display
    assert _HOLD_DETAIL not in serialized_display
