from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, RefResolver
from jsonschema import ValidationError as JsonSchemaError
from pydantic import ValidationError as PydanticError

import crypto_probability_engine.derivatives_intel.block as block_module
from crypto_probability_engine.api.schemas import AnalysisResponse
from crypto_probability_engine.derivatives_intel.block import build_derivatives_intelligence
from crypto_probability_engine.derivatives_intel.schemas import (
    METHODOLOGY_VERSION_V0,
    METHODOLOGY_VERSION_V1,
    PROVIDER_POLICY_VERSION_V1,
    SCHEMA_VERSION_V0,
    SCHEMA_VERSION_V1,
)
from tests.derivatives_intel.test_block import OBSERVED, raw_okx_only_bundle
from tests.fixtures.sample_payloads import sample_analysis_payload

SCHEMA_DIR = Path("schemas")


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text())


def _response_validator() -> Draft202012Validator:
    schema = _load_schema("response.schema.json")
    store = {
        "quant.schema.json": _load_schema("quant.schema.json"),
        "detail_view.schema.json": _load_schema("detail_view.schema.json"),
    }
    return Draft202012Validator(
        schema,
        resolver=RefResolver.from_schema(schema, store=store),
        format_checker=FormatChecker(),
    )


def _validate(payload: dict) -> None:
    _response_validator().validate(payload)


def _v1_block(monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setattr(
        block_module,
        "get_raw_derivatives_bundle",
        lambda *args, **kwargs: raw_okx_only_bundle(),
    )
    return build_derivatives_intelligence(
        normalized_symbol="BTC/USDT",
        core_prediction_as_of_utc=datetime(2026, 6, 6, tzinfo=UTC),
        enabled=True,
        now_utc=OBSERVED,
        methodology_version=METHODOLOGY_VERSION_V1,
    )


def _response_with_derivatives(block: dict) -> dict:
    payload = sample_analysis_payload()
    payload["derivatives_intelligence"] = deepcopy(block)
    return payload


def test_response_contract_accepts_v0_and_v1_derivatives_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    v0_payload = sample_analysis_payload()
    _validate(v0_payload)
    AnalysisResponse.model_validate(v0_payload)

    v1_payload = _response_with_derivatives(_v1_block(monkeypatch))
    _validate(v1_payload)
    model = AnalysisResponse.model_validate(v1_payload)
    assert model.derivatives_intelligence.schema_version == SCHEMA_VERSION_V1
    assert model.derivatives_intelligence.methodology_version == METHODOLOGY_VERSION_V1
    assert model.derivatives_intelligence.provider_policy_version == PROVIDER_POLICY_VERSION_V1


@pytest.mark.parametrize(
    "mutate",
    [
        lambda block: block.update({"schema_version": SCHEMA_VERSION_V0}),
        lambda block: block.update({"methodology_version": METHODOLOGY_VERSION_V0}),
        lambda block: block.pop("provider_policy_version"),
        lambda block: block.update({"provider_policy_version": "unreviewed-policy"}),
        lambda block: block["provider_summary"].append(
            {
                "provider": "BINANCE_USDM",
                "status": "PROVIDER_UNAVAILABLE",
                "valid_metric_count": 0,
                "total_metric_count": 2,
                "reason": "Binance is not part of v1 response evidence.",
            }
        ),
        lambda block: block["comparability"].append(
            {
                "semantic_class": "CURRENT_FUNDING",
                "left_provider": "BINANCE_USDM",
                "right_provider": "OKX_SWAP",
                "comparable": False,
                "reason": "Cross-provider comparison is not v1 evidence.",
            }
        ),
        lambda block: block["metrics"].pop(),
    ],
)
def test_response_contract_rejects_mixed_or_incomplete_v1_blocks(
    monkeypatch: pytest.MonkeyPatch,
    mutate,
) -> None:
    block = _v1_block(monkeypatch)
    mutate(block)
    payload = _response_with_derivatives(block)

    with pytest.raises(JsonSchemaError):
        _validate(payload)
    with pytest.raises(PydanticError):
        AnalysisResponse.model_validate(payload)


def test_response_contract_rejects_provider_policy_on_v0_block() -> None:
    payload = sample_analysis_payload()
    payload["derivatives_intelligence"]["provider_policy_version"] = (
        PROVIDER_POLICY_VERSION_V1
    )

    with pytest.raises(JsonSchemaError):
        _validate(payload)
    with pytest.raises(PydanticError):
        AnalysisResponse.model_validate(payload)


def test_response_contract_rejects_v1_with_unapproved_okx_metric_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    block = _v1_block(monkeypatch)
    block["metrics"][0]["metric_id"] = "okx.funding.settled"
    payload = _response_with_derivatives(block)

    with pytest.raises(JsonSchemaError):
        _validate(payload)
    with pytest.raises(PydanticError):
        AnalysisResponse.model_validate(payload)
