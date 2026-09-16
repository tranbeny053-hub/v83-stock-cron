from __future__ import annotations

import inspect
from copy import deepcopy
from dataclasses import replace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import TypeAdapter
from pydantic import ValidationError as PydanticError

import crypto_probability_engine.api.analysis_service as analysis_service
import crypto_probability_engine.derivatives_intel.block as block_module
from crypto_probability_engine.adapters.provider_selection import ProviderSelectionResult
from crypto_probability_engine.api.app import create_app
from crypto_probability_engine.api.auth import dev_limiter, hash_code, session_limiter
from crypto_probability_engine.api.schemas import (
    AnalysisRequest,
    DerivativesIntelligenceBlock,
    DerivativesIntelligenceBlockResponse,
    DerivativesIntelligenceBlockV1,
)
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.derivatives_intel.schemas import (
    METHODOLOGY_VERSION_V0,
    METHODOLOGY_VERSION_V1,
    PROVIDER_POLICY_VERSION_V1,
    SCHEMA_VERSION_V1,
)
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from tests.derivatives_intel.test_block import OBSERVED, raw_bundle, raw_okx_only_bundle
from tests.fixtures.market_data import make_snapshot


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


def _settings(*, derivatives: bool) -> Settings:
    return Settings(data_mode="fixture", enable_derivatives_intel=derivatives)


def _analyze(
    monkeypatch: pytest.MonkeyPatch,
    *,
    derivatives: bool,
    methodology_version: str | object = METHODOLOGY_VERSION_V0,
    deterministic: bool = True,
    symbol: str = "BTC",
) -> dict:
    payload, _prediction_row, _feature_snapshot = _analyze_with_work(
        monkeypatch,
        derivatives=derivatives,
        methodology_version=methodology_version,
        deterministic=deterministic,
        symbol=symbol,
    )
    return payload


def _analyze_with_work(
    monkeypatch: pytest.MonkeyPatch,
    *,
    derivatives: bool,
    methodology_version: str | object = METHODOLOGY_VERSION_V0,
    deterministic: bool = True,
    symbol: str = "BTC",
) -> tuple[dict, dict, dict]:
    monkeypatch.setattr(analysis_service, "select_market_data", _selection())
    kwargs = {}
    if methodology_version is not _OMIT:
        kwargs["derivatives_methodology_version"] = methodology_version
    payload = analysis_service.analyze_request(
        AnalysisRequest(symbol=symbol, timeframe="4H"),
        settings=_settings(derivatives=derivatives),
        run_store=InMemoryRunStore(),
        prediction_origin="SCHEDULED_SHADOW_EVIDENCE" if deterministic else "USER_REQUESTED",
        deterministic_identity=deterministic,
        **kwargs,
    )
    predictions, snapshots, failed, _derivatives_rows, derivatives_failed = (
        analysis_service._peek_prediction_persistence(payload)  # noqa: SLF001
    )
    assert not failed
    assert not derivatives_failed
    assert len(predictions) == 1
    assert len(snapshots) == 1
    analysis_service._pop_prediction_persistence(payload)  # noqa: SLF001
    return payload, predictions[0], snapshots[0]


def _enabled_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict, dict, dict, dict, dict, dict, list[tuple[str, ...]]]:
    calls: list[tuple[str, ...]] = []

    def fake_raw_bundle(*args, **kwargs):
        del args
        providers = tuple(kwargs["providers"])
        calls.append(providers)
        if providers == ("OKX_SWAP",):
            return raw_okx_only_bundle()
        return raw_bundle()

    monkeypatch.setattr(block_module, "get_raw_derivatives_bundle", fake_raw_bundle)
    monkeypatch.setattr(block_module, "utc_now", lambda: OBSERVED)
    v0, v0_prediction, v0_snapshot = _analyze_with_work(
        monkeypatch,
        derivatives=True,
        methodology_version=METHODOLOGY_VERSION_V0,
    )
    v1, v1_prediction, v1_snapshot = _analyze_with_work(
        monkeypatch,
        derivatives=True,
        methodology_version=METHODOLOGY_VERSION_V1,
    )
    return v0, v0_prediction, v0_snapshot, v1, v1_prediction, v1_snapshot, calls


def _core_projection(payload: dict) -> dict:
    projected = deepcopy(payload)
    projected.pop("derivatives_intelligence")
    return projected


_OMIT = object()


def test_analyze_request_signature_preserves_existing_contract() -> None:
    signature = inspect.signature(analysis_service.analyze_request)
    params = signature.parameters

    assert list(params) == [
        "request",
        "settings",
        "run_store",
        "persistence_status",
        "prediction_origin",
        "deterministic_identity",
        "derivatives_methodology_version",
        "methodology_version",
        "pair_context",
        "arm",
    ]
    assert params["request"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    for name in list(params)[1:]:
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["persistence_status"].default == "STATELESS"
    assert params["prediction_origin"].default == "USER_REQUESTED"
    assert params["deterministic_identity"].default is False
    assert params["derivatives_methodology_version"].default == METHODOLOGY_VERSION_V0
    assert params["methodology_version"].default == "heuristic-v1-wave4b0"
    assert params["pair_context"].default is None
    assert params["arm"].default is None


def test_omitted_selector_and_explicit_v0_are_deep_equal_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    omitted = _analyze(monkeypatch, derivatives=False, methodology_version=_OMIT)
    explicit = _analyze(
        monkeypatch,
        derivatives=False,
        methodology_version=METHODOLOGY_VERSION_V0,
    )

    assert omitted == explicit
    assert omitted["run_id"] == explicit["run_id"]
    assert omitted["analysis_hash"] == explicit["analysis_hash"]
    assert omitted["probability_state"] == explicit["probability_state"]
    assert omitted["score_stack"] == explicit["score_stack"]
    assert omitted["gate_result"] == explicit["gate_result"]
    assert omitted["decision_synthesis"] == explicit["decision_synthesis"]
    assert omitted["decision_brief"] == explicit["decision_brief"]
    assert omitted["quant_v2"] == explicit["quant_v2"]
    assert omitted["derivatives_intelligence"]["schema_version"] == "deriv-intel.v0"
    assert omitted["derivatives_intelligence"]["methodology_version"] == METHODOLOGY_VERSION_V0
    assert omitted["derivatives_intelligence"]["block_status"] == "DISABLED"


def test_explicit_v1_enabled_uses_okx_only_response_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _v0, _v0_prediction, _v0_snapshot, v1, _v1_prediction, _v1_snapshot, calls = (
        _enabled_payloads(monkeypatch)
    )

    block = v1["derivatives_intelligence"]
    DerivativesIntelligenceBlockV1.model_validate(block)
    assert block["schema_version"] == SCHEMA_VERSION_V1
    assert block["methodology_version"] == METHODOLOGY_VERSION_V1
    assert block["provider_policy_version"] == PROVIDER_POLICY_VERSION_V1
    assert block["influence_mode"] == "SHADOW_ONLY"
    assert block["decision_influence_frac"] == 0.0
    assert block["comparability"] == []
    assert block["disagreement"] == []
    assert [summary["provider"] for summary in block["provider_summary"]] == ["OKX_SWAP"]
    assert {metric["provider"] for metric in block["metrics"]} == {"OKX_SWAP"}
    assert {metric["methodology_version"] for metric in block["metrics"]} == {
        METHODOLOGY_VERSION_V1
    }
    assert calls == [("BINANCE_USDM", "OKX_SWAP"), ("OKX_SWAP",)]


def test_explicit_v1_changes_only_derivatives_block_vs_explicit_v0(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    v0, v0_prediction, v0_snapshot, v1, v1_prediction, v1_snapshot, _calls = (
        _enabled_payloads(monkeypatch)
    )

    assert _core_projection(v1) == _core_projection(v0)
    assert v1["run_id"] == v0["run_id"]
    assert v1_prediction["prediction_id"] == v0_prediction["prediction_id"]
    assert v1["analysis_hash"] == v0["analysis_hash"]
    assert v1["probability_state"] == v0["probability_state"]
    assert v1["score_stack"] == v0["score_stack"]
    assert v1["gate_result"] == v0["gate_result"]
    assert v1["decision_synthesis"] == v0["decision_synthesis"]
    assert v1["decision_brief"] == v0["decision_brief"]
    assert v1["quant_v2"] == v0["quant_v2"]
    assert v1_snapshot == v0_snapshot
    assert v1["derivatives_intelligence"] != v0["derivatives_intelligence"]


def test_discriminated_union_selects_exact_derivatives_schema_member(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = TypeAdapter(DerivativesIntelligenceBlockResponse)
    v0 = _analyze(monkeypatch, derivatives=False, methodology_version=METHODOLOGY_VERSION_V0)[
        "derivatives_intelligence"
    ]
    _v0, _v0_prediction, _v0_snapshot, v1_payload, _v1_prediction, _v1_snapshot, _calls = (
        _enabled_payloads(monkeypatch)
    )
    v1 = v1_payload["derivatives_intelligence"]

    assert isinstance(adapter.validate_python(v0), DerivativesIntelligenceBlock)
    assert isinstance(adapter.validate_python(v1), DerivativesIntelligenceBlockV1)
    with pytest.raises(PydanticError):
        DerivativesIntelligenceBlock.model_validate(v1)
    with pytest.raises(PydanticError):
        DerivativesIntelligenceBlockV1.model_validate(v0)
    unknown = deepcopy(v1)
    unknown["schema_version"] = "deriv-intel.v999"
    with pytest.raises(PydanticError):
        adapter.validate_python(unknown)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda block: block["metrics"].append(deepcopy(block["metrics"][0])),
        lambda block: block["metrics"][0].update({"provider": "BINANCE_USDM"}),
        lambda block: block["provider_summary"][0].update({"provider": "BINANCE_USDM"}),
        lambda block: block["provider_summary"][0].update({"valid_metric_count": 3}),
        lambda block: block["metrics"][0].update({"status": "STALE_INPUT"}),
        lambda block: block.update({"comparability": [{"comparable": False}]}),
        lambda block: block.update({"disagreement": [{"provider": "OKX_SWAP"}]}),
        lambda block: block.update({"decision_influence_frac": 0.01}),
        lambda block: block.update({"influence_mode": "ACTIVE"}),
    ],
)
def test_v1_response_model_rejects_mixed_provider_and_false_active_blocks(
    monkeypatch: pytest.MonkeyPatch,
    mutate,
) -> None:
    _v0, _v0_prediction, _v0_snapshot, v1_payload, _v1_prediction, _v1_snapshot, _calls = (
        _enabled_payloads(monkeypatch)
    )
    block = deepcopy(v1_payload["derivatives_intelligence"])
    mutate(block)

    with pytest.raises(PydanticError):
        DerivativesIntelligenceBlockV1.model_validate(block)


@pytest.mark.parametrize(
    "bad_value",
    [None, "", " ", "unknown", "deriv-intel-okx-shadow-v2", 0, False],
)
def test_invalid_selector_fails_before_market_or_provider_calls(
    monkeypatch: pytest.MonkeyPatch,
    bad_value,
) -> None:
    market_calls = 0

    def fail_market(*args, **kwargs):
        nonlocal market_calls
        market_calls += 1
        raise AssertionError("market data selection must not run")

    def fail_provider(*args, **kwargs):
        raise AssertionError("derivatives provider selection must not run")

    monkeypatch.setattr(analysis_service, "select_market_data", fail_market)
    monkeypatch.setattr(block_module, "get_raw_derivatives_bundle", fail_provider)

    with pytest.raises(HTTPException) as exc_info:
        analysis_service.analyze_request(
            AnalysisRequest(symbol="BTC", timeframe="4H"),
            settings=_settings(derivatives=True),
            run_store=InMemoryRunStore(),
            derivatives_methodology_version=bad_value,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error"]["code"] == "SCHEMA_VALIDATION_FAILED"
    assert exc_info.value.detail["error"]["message"] == (
        "Unsupported derivatives methodology version."
    )
    assert market_calls == 0


def test_explicit_v1_disabled_has_no_derivatives_provider_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        block_module,
        "get_raw_derivatives_bundle",
        lambda *args, **kwargs: pytest.fail("disabled v1 must not call providers"),
    )

    v0 = _analyze(monkeypatch, derivatives=False, methodology_version=METHODOLOGY_VERSION_V0)
    v1 = _analyze(monkeypatch, derivatives=False, methodology_version=METHODOLOGY_VERSION_V1)

    block = v1["derivatives_intelligence"]
    assert block["schema_version"] == SCHEMA_VERSION_V1
    assert block["methodology_version"] == METHODOLOGY_VERSION_V1
    assert block["provider_policy_version"] == PROVIDER_POLICY_VERSION_V1
    assert block["block_status"] == "DISABLED"
    assert block["observation_as_of_utc"] is None
    assert _core_projection(v1) == _core_projection(v0)


def test_analysis_request_and_http_contract_do_not_expose_selector() -> None:
    assert "derivatives_methodology_version" not in AnalysisRequest.model_fields
    request_schema = AnalysisRequest.model_json_schema()
    assert "derivatives_methodology_version" not in str(request_schema)

    app_source = (
        "src/crypto_probability_engine/api/app.py"
    )
    with open(app_source, encoding="utf-8") as handle:
        assert "derivatives_methodology_version" not in handle.read()


def test_http_extra_methodology_field_is_rejected_and_cannot_select_v1() -> None:
    session_limiter.reset()
    dev_limiter.reset()
    client = TestClient(
        create_app(
            Settings(
                access_code_hash=hash_code("operator-test-code"),
                session_signing_key="test-signing-key",
                session_cookie_secure=False,
                data_mode="fixture",
            )
        )
    )
    login = client.post("/v1/auth/login", json={"code": "operator-test-code"})
    assert login.status_code == 200

    response = client.post(
        "/v1/analyze",
        json={
            "symbol": "BTC",
            "timeframe": "4H",
            "derivatives_methodology_version": METHODOLOGY_VERSION_V1,
        },
    )

    assert response.status_code == 422
    assert "derivatives_intelligence" not in response.text


def test_invalid_selector_validation_uses_no_wall_clock_or_runtime_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(analysis_service, "uuid4", lambda: pytest.fail("must fail before UUID"))
    monkeypatch.setattr(
        analysis_service,
        "_deterministic_cadence_run_id",
        lambda *args, **kwargs: pytest.fail("must fail before deterministic identity"),
    )

    with pytest.raises(HTTPException):
        analysis_service.analyze_request(
            AnalysisRequest(symbol="BTC", timeframe="4H"),
            settings=_settings(derivatives=True),
            run_store=InMemoryRunStore(),
            deterministic_identity=True,
            derivatives_methodology_version=" ",
        )
