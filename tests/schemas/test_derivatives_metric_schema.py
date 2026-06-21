from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema import ValidationError as JsonSchemaError

from crypto_probability_engine.derivatives_intel.instruments import (
    resolve_binance_usdm_instrument,
    resolve_okx_swap_instrument,
)
from crypto_probability_engine.derivatives_intel.provenance import (
    build_binance_current_funding_metric,
    build_okx_current_funding_metric,
)

SCHEMA = json.loads(Path("schemas/derivatives_metric.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
AS_OF = datetime(2026, 6, 21, 12, tzinfo=UTC)


def _metric() -> dict:
    resolution = resolve_binance_usdm_instrument(
        "BTCUSDT",
        {
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "status": "TRADING",
                    "contractType": "PERPETUAL",
                    "quoteAsset": "USDT",
                    "marginAsset": "USDT",
                }
            ]
        },
    )
    return build_binance_current_funding_metric(
        {
            "lastFundingRate": "0.0001",
            "time": int((AS_OF - timedelta(seconds=10)).timestamp() * 1000),
        },
        resolution,
        fetched_at_utc=AS_OF - timedelta(seconds=1),
        prediction_as_of_utc=AS_OF,
    )


def test_generated_metric_validates_against_strict_schema() -> None:
    metric = _metric()
    VALIDATOR.validate(metric)
    assert set(metric) == set(SCHEMA["required"])


def test_contract_mismatch_metric_remains_schema_valid_and_non_interpreted() -> None:
    resolution = resolve_okx_swap_instrument(
        "BTCUSDT",
        [
            {
                "instId": "BTC-USDT-SWAP",
                "instType": "SWAP",
                "settleCcy": "BTC",
                "ctType": "inverse",
                "state": "live",
            }
        ],
    )
    metric = build_okx_current_funding_metric(
        [{"fundingRate": "0.1", "ts": str(int(AS_OF.timestamp() * 1000))}],
        resolution,
        fetched_at_utc=AS_OF,
        prediction_as_of_utc=AS_OF,
    )
    VALIDATOR.validate(metric)
    assert metric["status"] == "CONTRACT_MISMATCH"
    assert metric["raw_value"] is None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda metric: metric.update({"unexpected": True}),
        lambda metric: metric.update({"influence_mode": "ACTIVE"}),
        lambda metric: metric.update({"normalized_value": 1}),
        lambda metric: metric.update({"direction_hint": "UP"}),
        lambda metric: metric.update({"status": "UNKNOWN"}),
        lambda metric: metric.update({"family": "OTHER"}),
        lambda metric: metric.update({"unit": "OTHER"}),
        lambda metric: metric.update({"raw_value": float("inf")}),
        lambda metric: metric.pop("provider"),
    ],
)
def test_invalid_or_extra_metric_fields_fail_schema(mutate) -> None:
    metric = deepcopy(_metric())
    mutate(metric)
    with pytest.raises(JsonSchemaError):
        VALIDATOR.validate(metric)


def test_metric_serialization_rejects_nonfinite_json() -> None:
    metric = _metric()
    metric["raw_value"] = float("nan")
    with pytest.raises(ValueError):
        json.dumps(metric, allow_nan=False)
