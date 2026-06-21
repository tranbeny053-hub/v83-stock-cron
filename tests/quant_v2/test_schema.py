from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import (
    Draft202012Validator,
    RefResolver,
)
from jsonschema import (
    ValidationError as JsonSchemaError,
)
from pydantic import ValidationError as PydanticError

from crypto_probability_engine.api.schemas import AnalysisResponse, QuantV2Block
from crypto_probability_engine.quant.pipeline import run_quant_pipeline
from crypto_probability_engine.quant_v2.contract import build_quant_v2_shadow
from tests.fixtures.market_data import make_snapshot
from tests.fixtures.sample_payloads import sample_analysis_payload

SCHEMA_DIR = Path("schemas")


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text())


def _json_validator() -> Draft202012Validator:
    schema = _load_schema("response.schema.json")
    store = {
        "quant.schema.json": _load_schema("quant.schema.json"),
        "detail_view.schema.json": _load_schema("detail_view.schema.json"),
    }
    return Draft202012Validator(
        schema,
        resolver=RefResolver.from_schema(schema, store=store),
    )


def _block(*, count: int = 210, enabled: bool = True) -> dict:
    snapshot = make_snapshot(provider="binance", count=count)
    provider_state = {"status": "OK", "active_provider": "binance"}
    return build_quant_v2_shadow(
        quant_result=run_quant_pipeline(snapshot, provider_state),
        snapshot=snapshot,
        provider_state=provider_state,
        symbol="BTC",
        normalized_symbol="BTC/USDT",
        timeframe="4H",
        enabled=enabled,
    )


@pytest.mark.parametrize(
    "block",
    [
        pytest.param(_block(), id="active"),
        pytest.param(_block(count=10), id="degraded"),
        pytest.param(_block(enabled=False), id="disabled"),
    ],
)
def test_pydantic_and_json_schema_accept_all_block_states(block: dict) -> None:
    payload = sample_analysis_payload()
    payload["quant_v2"] = block

    AnalysisResponse.model_validate(payload)
    _json_validator().validate(payload)


@pytest.mark.parametrize("location", ["block", "feature"])
def test_undeclared_fields_fail_both_strict_schemas(location: str) -> None:
    payload = sample_analysis_payload()
    payload["quant_v2"] = _block()
    target = payload["quant_v2"] if location == "block" else payload["quant_v2"]["features"][0]
    target["unexpected"] = True

    with pytest.raises(PydanticError):
        AnalysisResponse.model_validate(payload)
    with pytest.raises(JsonSchemaError):
        _json_validator().validate(payload)


@pytest.mark.parametrize("location", ["block", "feature"])
def test_missing_required_fields_fail_both_strict_schemas(location: str) -> None:
    payload = sample_analysis_payload()
    payload["quant_v2"] = _block()
    target = payload["quant_v2"] if location == "block" else payload["quant_v2"]["features"][0]
    target.pop("influence_mode")

    with pytest.raises(PydanticError):
        AnalysisResponse.model_validate(payload)
    with pytest.raises(JsonSchemaError):
        _json_validator().validate(payload)


def test_missing_required_quant_v2_block_fails_both_schemas() -> None:
    payload = sample_analysis_payload()
    payload.pop("quant_v2")

    with pytest.raises(PydanticError):
        AnalysisResponse.model_validate(payload)
    with pytest.raises(JsonSchemaError):
        _json_validator().validate(payload)


def test_invalid_enums_fail_both_strict_schemas() -> None:
    payload = sample_analysis_payload()
    payload["quant_v2"] = _block()
    payload["quant_v2"]["features"][0]["family"] = "UNDECLARED"

    with pytest.raises(PydanticError):
        AnalysisResponse.model_validate(payload)
    with pytest.raises(JsonSchemaError):
        _json_validator().validate(payload)


def test_normalization_and_hint_fields_remain_null_except_direct_trend_mapping() -> None:
    block = _block()
    for feature in block["features"]:
        assert feature["normalized_value"] is None
        assert feature["bucket"] is None
        assert feature["confidence_hint"] is None
        assert feature["risk_hint"] is None
        if feature["family"] != "TREND":
            assert feature["direction_hint"] is None


def test_response_fixture_uses_full_disabled_contract_not_empty_default() -> None:
    payload = deepcopy(sample_analysis_payload())
    assert payload["quant_v2"]["status"] == "DISABLED"
    assert payload["quant_v2"]["features"] == []
    AnalysisResponse.model_validate(payload)
    _json_validator().validate(payload)


def test_pydantic_and_json_schema_required_sets_and_extra_policy_match() -> None:
    pydantic_schema = QuantV2Block.model_json_schema()
    json_schema = _load_schema("response.schema.json")
    pydantic_block = pydantic_schema
    pydantic_feature = pydantic_schema["$defs"]["QuantV2Feature"]
    json_block = json_schema["$defs"]["quantV2"]
    json_feature = json_schema["$defs"]["quantV2Feature"]

    assert set(pydantic_block["required"]) == set(json_block["required"])
    assert set(pydantic_feature["required"]) == set(json_feature["required"])
    assert pydantic_block["additionalProperties"] is False
    assert json_block["additionalProperties"] is False
    assert pydantic_feature["additionalProperties"] is False
    assert json_feature["additionalProperties"] is False
