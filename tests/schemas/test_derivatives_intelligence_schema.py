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
from crypto_probability_engine.api.schemas import DerivativesIntelligenceBlock
from crypto_probability_engine.derivatives_intel.block import (
    ProviderSummaryStatus,
    build_derivatives_intelligence,
)
from tests.derivatives_intel.test_block import OBSERVED, raw_bundle

SCHEMA = json.loads(Path("schemas/derivatives_intelligence.schema.json").read_text())
METRIC_SCHEMA = json.loads(Path("schemas/derivatives_metric.schema.json").read_text())
VALIDATOR = Draft202012Validator(
    SCHEMA,
    resolver=RefResolver.from_schema(
        SCHEMA,
        store={
            "derivatives_metric.schema.json": METRIC_SCHEMA,
            METRIC_SCHEMA["$id"]: METRIC_SCHEMA,
        },
    ),
    format_checker=FormatChecker(),
)


def off_block() -> dict:
    return build_derivatives_intelligence(
        normalized_symbol="BTC/USDT",
        core_prediction_as_of_utc=datetime(2026, 6, 22, tzinfo=UTC),
        enabled=False,
    )


def test_disabled_block_passes_python_and_json_contracts() -> None:
    payload = off_block()
    DerivativesIntelligenceBlock.model_validate(payload)
    VALIDATOR.validate(payload)


@pytest.mark.parametrize(
    ("okx_status", "expected"), [("OK", "ACTIVE"), ("PROVIDER_UNAVAILABLE", "DEGRADED")]
)
def test_enabled_blocks_pass_python_and_json_contracts(
    monkeypatch: pytest.MonkeyPatch, okx_status: str, expected: str
) -> None:
    bundle = raw_bundle(okx_status=okx_status)
    monkeypatch.setattr(block_module, "get_raw_derivatives_bundle", lambda *a, **k: bundle)
    payload = build_derivatives_intelligence(
        normalized_symbol="BTC/USDT",
        core_prediction_as_of_utc=datetime(2026, 6, 22, tzinfo=UTC),
        enabled=True,
        now_utc=OBSERVED,
    )
    assert payload["block_status"] == expected
    DerivativesIntelligenceBlock.model_validate(payload)
    VALIDATOR.validate(payload)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update({"unexpected": True}),
        lambda payload: payload.update({"influence_mode": "ACTIVE"}),
        lambda payload: payload.update({"decision_influence_frac": 0.1}),
        lambda payload: payload.pop("core_prediction_as_of_utc"),
        lambda payload: payload.update({"observation_as_of_utc": "2026-06-22T00:00:00Z"}),
        lambda payload: payload["disagreement"].append({"value": 1}),
    ],
)
def test_invalid_blocks_fail_python_and_json_contracts(mutate) -> None:
    payload = deepcopy(off_block())
    mutate(payload)
    with pytest.raises(PydanticError):
        DerivativesIntelligenceBlock.model_validate(payload)
    with pytest.raises(JsonSchemaError):
        VALIDATOR.validate(payload)


def test_provider_status_enums_are_identical() -> None:
    schema_values = set(SCHEMA["$defs"]["providerSummary"]["properties"]["status"]["enum"])
    from crypto_probability_engine.api.schemas import DerivativesProviderSummaryStatus

    assert schema_values == {item.value for item in DerivativesProviderSummaryStatus}
    assert schema_values == {item.value for item in ProviderSummaryStatus}
