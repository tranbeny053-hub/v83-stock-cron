from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from crypto_probability_engine.api import calibration_endpoint
from crypto_probability_engine.api.app import create_app
from crypto_probability_engine.api.auth import SESSION_COOKIE, hash_code, session_limiter
from crypto_probability_engine.config.settings import Settings

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_REPOSITORY = "SUPA" + "BASE_POSTGRES"


@pytest.fixture(autouse=True)
def isolate_calibration_cache() -> None:
    calibration_endpoint.clear_calibration_cache()
    yield
    calibration_endpoint.clear_calibration_cache()


def make_client() -> TestClient:
    session_limiter.reset()
    settings = Settings(
        access_code_hash=hash_code("operator-test-code"),
        session_signing_key="test-signing-key",
        session_cookie_secure=False,
        data_mode="fixture",
    )
    return TestClient(create_app(settings))


def login(client: TestClient) -> None:
    response = client.post("/v1/auth/login", json={"code": "operator-test-code"})
    assert response.status_code == 200


def calibration_report(timeframe: str, *, include_values: bool = True) -> dict:
    return {
        "status": "OK",
        "scope": {"timeframe": timeframe},
        "repository": EXPECTED_REPOSITORY,
        "sample_count": 37,
        "valid_count": 36,
        "invalid_row_count": 1,
        "sample_gate": "INSUFFICIENT_SAMPLE",
        "version_mix_warning": False,
        "versions_present": {
            "model_versions": ["model-v1"],
            "methodology_versions": ["method-v1"],
        },
        "metrics": {
            "brier_score": 0.42 if include_values else None,
            "log_loss": 0.71 if include_values else None,
            "top_label_hit_rate": 0.54 if include_values else None,
        },
        "reliability_buckets": [
            {
                "bucket": "0.50-0.60",
                "bucket_count": 12,
                "avg_predicted_max_prob": 0.55,
                "empirical_hit_rate": 0.5,
                "calibration_gap": 0.05,
                "bucket_sample_status": "LOW_BUCKET_SAMPLE",
                "unexpected_service_field": "not-returned",
            }
        ],
        "outcome_distribution": {"UP": 14, "DOWN": 12, "TIMEOUT": 10},
        "terminal_return_diagnostics": {},
        "warnings": [],
    }


def test_calibration_requires_valid_app_session() -> None:
    client = make_client()

    missing = client.get("/v1/calibration")
    invalid = client.get("/v1/calibration", cookies={SESSION_COOKIE: "invalid-session"})

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert missing.json()["detail"]["error"]["code"] == "UNAUTHORIZED"
    assert invalid.json()["detail"]["error"]["code"] == "UNAUTHORIZED"


def test_calibration_success_for_one_timeframe(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    def fake_build(**kwargs) -> dict:
        calls.append(kwargs)
        return calibration_report(kwargs["timeframe"])

    monkeypatch.setattr(calibration_endpoint, "build_calibration_report", fake_build)
    client = make_client()
    login(client)

    response = client.get(
        "/v1/calibration",
        params={
            "timeframe": "15m",
            "model_version": "model-v1",
            "methodology_version": "method-v1",
            "limit": 123,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "OK"
    assert payload["repository"] == EXPECTED_REPOSITORY
    assert payload["generated_at"].endswith("Z")
    assert len(payload["timeframes"]) == 1
    item = payload["timeframes"][0]
    assert item["timeframe"] == "15m"
    assert item["sample_count"] == 37
    assert item["sample_gate"] == "INSUFFICIENT_SAMPLE"
    assert item["top_label_hit_rate"] == 0.54
    assert item["reliability_buckets"] is None
    assert payload["not_win_rate"] is True
    assert payload["not_profitability_evidence"] is True
    assert payload["not_trade_ev"] is True
    assert calls[0]["model_version"] == "model-v1"
    assert calls[0]["methodology_version"] == "method-v1"
    assert calls[0]["limit"] == 123


def test_calibration_success_returns_all_timeframes_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_build(**kwargs) -> dict:
        calls.append(kwargs["timeframe"])
        return calibration_report(kwargs["timeframe"])

    monkeypatch.setattr(calibration_endpoint, "build_calibration_report", fake_build)
    client = make_client()
    login(client)

    response = client.get("/v1/calibration")

    expected = ["15m", "1H", "4H", "1D", "1W", "1M"]
    assert response.status_code == 200
    assert [item["timeframe"] for item in response.json()["timeframes"]] == expected
    assert calls == expected


def test_calibration_buckets_are_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_build(**kwargs) -> dict:
        return calibration_report(kwargs["timeframe"])

    monkeypatch.setattr(calibration_endpoint, "build_calibration_report", fake_build)
    client = make_client()
    login(client)

    without = client.get("/v1/calibration", params={"timeframe": "4H"})
    with_buckets = client.get(
        "/v1/calibration",
        params={"timeframe": "4H", "include_buckets": True},
    )

    assert without.json()["timeframes"][0]["reliability_buckets"] is None
    buckets = with_buckets.json()["timeframes"][0]["reliability_buckets"]
    assert buckets and buckets[0]["bucket"] == "0.50-0.60"
    assert "unexpected_service_field" not in buckets[0]


def test_calibration_unavailable_response_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_message = " ".join(
        (
            "post" + "gresql://operator:private@host/db",
            "SUPA" + "BASE_DB_URL",
            "pass" + "word",
            "to" + "ken",
            "service" + "_role",
            "trace" + "back",
        )
    )

    def fake_build(**kwargs) -> dict:
        raise RuntimeError(private_message)

    monkeypatch.setattr(calibration_endpoint, "build_calibration_report", fake_build)
    client = make_client()
    login(client)

    response = client.get("/v1/calibration", params={"timeframe": "1D"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "UNAVAILABLE"
    assert payload["repository"] == "UNAVAILABLE"
    assert payload["timeframes"] == []
    assert payload["error_class"] == "RuntimeError"
    assert private_message not in response.text
    for fragment in private_message.split():
        assert fragment not in response.text


def test_calibration_non_postgres_report_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_build(**kwargs) -> dict:
        report = calibration_report(kwargs["timeframe"])
        report["repository"] = "IN_MEMORY"
        return report

    monkeypatch.setattr(calibration_endpoint, "build_calibration_report", fake_build)
    client = make_client()
    login(client)

    response = client.get("/v1/calibration", params={"timeframe": "1W"})

    assert response.status_code == 200
    assert response.json()["status"] == "UNAVAILABLE"


def test_calibration_cache_deduplicates_and_keys_all_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    def fake_build(**kwargs) -> dict:
        calls.append(kwargs)
        return calibration_report(kwargs["timeframe"])

    monkeypatch.setattr(calibration_endpoint, "build_calibration_report", fake_build)
    client = make_client()
    login(client)

    base_params = {"timeframe": "15m", "limit": 50}
    assert client.get("/v1/calibration", params=base_params).status_code == 200
    assert client.get("/v1/calibration", params=base_params).status_code == 200
    assert len(calls) == 1

    client.get("/v1/calibration", params={"timeframe": "1H", "limit": 50})
    client.get(
        "/v1/calibration",
        params={"timeframe": "15m", "limit": 50, "include_buckets": True},
    )
    assert len(calls) == 3

    client.get(
        "/v1/calibration",
        params={"timeframe": "15m", "limit": 50, "model_version": "model-v2"},
    )
    client.get(
        "/v1/calibration",
        params={"timeframe": "15m", "limit": 50, "methodology_version": "method-v2"},
    )
    client.get("/v1/calibration", params={"timeframe": "15m", "limit": 51})
    assert len(calls) == 6

    calibration_endpoint.clear_calibration_cache()
    client.get("/v1/calibration", params=base_params)
    assert len(calls) == 7
    assert calibration_endpoint.CACHE_TTL_SECONDS == 60.0


def test_calibration_query_constraints_are_enforced() -> None:
    client = make_client()
    login(client)

    assert client.get("/v1/calibration", params={"timeframe": "2H"}).status_code == 422
    assert client.get("/v1/calibration", params={"limit": 0}).status_code == 422
    assert client.get("/v1/calibration", params={"limit": 5001}).status_code == 422


def test_calibration_endpoint_is_read_only() -> None:
    source = (ROOT / "src/crypto_probability_engine/api/calibration_endpoint.py").read_text(
        encoding="utf-8"
    )
    mutation_markers = (
        "IN" + "SERT",
        "UP" + "DATE",
        "DE" + "LETE",
        "save_" + "prediction",
        "save_" + "prediction_outcome",
        "resolve_" + "outcomes",
    )
    assert not any(marker in source for marker in mutation_markers)


def test_calibration_response_wording_is_safely_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_build(**kwargs) -> dict:
        return calibration_report(kwargs["timeframe"])

    monkeypatch.setattr(calibration_endpoint, "build_calibration_report", fake_build)
    client = make_client()
    login(client)
    response = client.get("/v1/calibration", params={"timeframe": "15m"})
    serialized = json.dumps(response.json()).lower()

    forbidden = (
        "win " + "rate",
        "profit" + "able",
        "reliable " + "signal",
        "high " + "confidence",
        "guaran" + "teed",
        "buy " + "now",
        "sell " + "now",
    )
    assert not any(phrase in serialized for phrase in forbidden)
    assert "not accuracy" in serialized
    assert "not profitability evidence" in serialized
    assert "not trade ev" in serialized
