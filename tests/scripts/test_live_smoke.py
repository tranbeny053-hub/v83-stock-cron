from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from crypto_probability_engine.persistence.prediction_origin import PredictionOrigin
from scripts import live_smoke


@pytest.fixture(autouse=True)
def _clear_smoke_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UCPE_LIVE_SMOKE_ENABLED", raising=False)
    monkeypatch.delenv(live_smoke.WAVE4B0_SMOKE_ENV, raising=False)
    for name in live_smoke.DATABASE_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def _payload(*, live: bool = True, total: float = 1.0, sample: str = "SUFFICIENT") -> dict:
    return {
        "run_id": "run-mocked",
        "data_quality": {
            "is_live_data": live,
            "data_source": "BINANCE_PUBLIC",
        },
        "probability_state": {
            "horizons": {
                "H_primary": {
                    "p_up_frac": 0.5,
                    "p_down_frac": 0.3,
                    "p_timeout_frac": total - 0.8,
                },
                "H_extended": {
                    "p_up_frac": 0.4,
                    "p_down_frac": 0.3,
                    "p_timeout_frac": 0.3,
                },
            }
        },
        "calibration_state": {"profitability_claim": False},
        "score_stack": {"news_influence_frac": 0.0},
        "epistemic_sufficiency_state": {"sufficiency_level": sample},
    }


def _mock_wave_runtime(monkeypatch: pytest.MonkeyPatch, payload_factory=None) -> list:
    calls = []
    payload_factory = payload_factory or (
        lambda request: _payload(sample="LOW_SAMPLE" if request.timeframe == "1M" else "SUFFICIENT")
    )

    def fake_analyze(request, **kwargs):
        calls.append((request, kwargs))
        payload = payload_factory(request)
        payload["run_id"] = f"run-{request.symbol}-{request.timeframe}"
        return payload

    monkeypatch.setattr(live_smoke, "analyze_request", fake_analyze)
    monkeypatch.setattr(live_smoke, "validate_analysis_response", lambda payload: payload)
    monkeypatch.setattr(
        live_smoke,
        "_peek_prediction_persistence",
        lambda payload: (
            [{"prediction_origin": "CONTROLLED_SMOKE"}],
            [],
            False,
            [],
            False,
        ),
    )
    return calls


def test_wave4b0_passes_mocked_live_payload_and_explicit_origin_for_every_cell(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = _mock_wave_runtime(monkeypatch)
    monkeypatch.setattr(
        live_smoke,
        "TestClient",
        lambda *args, **kwargs: pytest.fail("Wave 4B0 must not construct TestClient"),
    )

    assert live_smoke.run_wave4b0_smoke() == 0
    assert len(calls) == 6
    assert {(call[0].symbol, call[0].timeframe) for call in calls} == {
        (symbol, timeframe)
        for symbol in live_smoke.WAVE4B0_SYMBOLS
        for timeframe in live_smoke.WAVE4B0_TIMEFRAMES
    }
    for request, kwargs in calls:
        assert request.analysis_mode.value == "METRICS_ONLY"
        assert kwargs["prediction_origin"] is PredictionOrigin.CONTROLLED_SMOKE
        assert kwargs["persistence_status"] == "STATELESS"
    output = capsys.readouterr().out
    assert "SUMMARY: BTC:1M:BINANCE_PUBLIC:UP=0.500000:LOW_SAMPLE" in output
    assert output.rstrip().endswith(
        "PASS: Wave 4B0 CONTROLLED_SMOKE long-timeframe live smoke."
    )


@pytest.mark.parametrize("database_var", live_smoke.DATABASE_ENV_VARS)
def test_wave4b0_refuses_database_environment_before_any_provider_call(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    database_var: str,
) -> None:
    monkeypatch.setenv(database_var, "configured-but-never-printed")
    monkeypatch.setattr(
        live_smoke,
        "analyze_request",
        lambda *args, **kwargs: pytest.fail("provider runtime must not be called"),
    )

    assert live_smoke.run_wave4b0_smoke() == 1
    output = capsys.readouterr().out
    assert database_var in output
    assert "configured-but-never-printed" not in output


def test_main_refuses_wave_database_before_sprint_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UCPE_LIVE_SMOKE_ENABLED", "true")
    monkeypatch.setenv(live_smoke.WAVE4B0_SMOKE_ENV, "true")
    monkeypatch.setenv("SUPABASE_DB_URL", "configured")
    monkeypatch.setattr(
        live_smoke,
        "run_sprint2_smoke",
        lambda: pytest.fail("Sprint provider calls must not start"),
    )
    assert live_smoke.main() == 1


def test_wave4b0_never_uses_http_or_persistence_write_calls() -> None:
    source = inspect.getsource(live_smoke.run_wave4b0_smoke)
    assert "TestClient" not in source
    assert "/v1/" not in source
    for write_call in (
        "save_prediction",
        "persist_analysis_sync",
        "schedule_analysis_persistence",
        "_persist_synchronously",
    ):
        assert write_call not in source


def test_wave4b0_probability_invariant_failure_stops_at_first_cell(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = _mock_wave_runtime(monkeypatch, lambda request: _payload(total=0.9))
    assert live_smoke.run_wave4b0_smoke() == 1
    assert len(calls) == 1
    output = capsys.readouterr().out
    assert output.count("FAIL:") == 1
    assert "probability sum was not 1.0" in output


def test_wave4b0_rejects_non_live_payload(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = _mock_wave_runtime(monkeypatch, lambda request: _payload(live=False))
    assert live_smoke.run_wave4b0_smoke() == 1
    assert len(calls) == 1
    assert "is_live_data=true" in capsys.readouterr().out


def test_wave4b0_monthly_requires_real_low_sample_flag(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def payload_for(request):
        return _payload(sample="SUFFICIENT")

    calls = _mock_wave_runtime(monkeypatch, payload_for)
    assert live_smoke.run_wave4b0_smoke() == 1
    assert len(calls) == 3
    assert "expected sample flag LOW_SAMPLE" in capsys.readouterr().out


def test_sprint2_smoke_regression_still_uses_http_both_modes(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    requests = []

    class FakeClient:
        def __init__(self, app):
            del app

        def post(self, path, json):
            requests.append((path, json))
            if path == "/v1/auth/login":
                return SimpleNamespace(status_code=200)
            mode = json["analysis_mode"]
            payload = {
                "data_quality": {
                    "data_source": "OKX_PUBLIC",
                    "is_live_data": True,
                },
                "news_addon_state": {
                    "status": "UNAVAILABLE" if mode == "NEWS_ADDON" else "DISABLED"
                },
            }
            return SimpleNamespace(status_code=200, json=lambda: payload, text="")

    monkeypatch.setattr(live_smoke, "TestClient", FakeClient)
    monkeypatch.setattr(live_smoke, "create_app", lambda settings: object())
    monkeypatch.setattr(live_smoke, "validate_analysis_response", lambda payload: payload)
    assert live_smoke.run_sprint2_smoke() == 0
    analyze_requests = [item for item in requests if item[0] == "/v1/analyze"]
    assert len(analyze_requests) == 4
    assert {item[1]["analysis_mode"] for item in analyze_requests} == {
        "METRICS_ONLY",
        "NEWS_ADDON",
    }
    assert "PASS: live public-provider smoke" in capsys.readouterr().out


def test_main_skips_by_default_without_constructing_any_client(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        live_smoke,
        "run_sprint2_smoke",
        lambda: pytest.fail("disabled smoke must not run"),
    )
    assert live_smoke.main() == 0
    assert "SKIP: UCPE_LIVE_SMOKE_ENABLED" in capsys.readouterr().out
