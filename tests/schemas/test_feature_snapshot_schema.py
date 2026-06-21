from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema import ValidationError as JsonSchemaError

from crypto_probability_engine.api.analysis_service import _prediction_row
from crypto_probability_engine.persistence.feature_snapshot import build_feature_snapshot
from crypto_probability_engine.quant.pipeline import run_quant_pipeline
from crypto_probability_engine.quant_v2.contract import build_quant_v2_shadow
from tests.fixtures.market_data import make_snapshot


def _row() -> dict:
    snapshot = make_snapshot(provider="binance")
    provider_state = {"status": "OK", "active_provider": "binance"}
    quant_result = run_quant_pipeline(snapshot, provider_state)
    prediction = _prediction_row(
        run_id="run_schema_snapshot",
        request_symbol="BTC",
        normalized_symbol="BTC/USDT",
        timeframe="4H",
        snapshot=snapshot,
        quant_result=quant_result,
        data_quality={"is_live_data": True, "data_source": "BINANCE_PUBLIC"},
        provider_state=provider_state,
    )
    assert prediction is not None
    block = build_quant_v2_shadow(
        quant_result=quant_result,
        snapshot=snapshot,
        provider_state=provider_state,
        symbol="BTC",
        normalized_symbol="BTC/USDT",
        timeframe="4H",
    )
    row = build_feature_snapshot(prediction, block)
    assert row is not None
    return row


SCHEMA = json.loads(Path("schemas/feature_snapshot.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


def test_valid_feature_snapshot_passes_strict_schema() -> None:
    VALIDATOR.validate(_row())


@pytest.mark.parametrize(
    "mutate",
    [
        lambda row: row.pop("prediction_id"),
        lambda row: row.update({"unexpected": True}),
        lambda row: row.update({"block_status": "UNKNOWN"}),
        lambda row: row.update({"influence_mode": "ACTIVE"}),
        lambda row: row.update({"prediction_as_of_utc": "not-a-timestamp"}),
        lambda row: row.update({"feature_count": 0}),
        lambda row: row["snapshot_payload"].update({"explanation_detail": "not approved"}),
        lambda row: row["snapshot_payload"]["features"][0].update(
            {"unexpected": True}
        ),
    ],
)
def test_invalid_feature_snapshot_contract_is_rejected(mutate) -> None:
    row = deepcopy(_row())
    mutate(row)
    with pytest.raises(JsonSchemaError):
        VALIDATOR.validate(row)


def test_strict_serialization_rejects_nonfinite_values() -> None:
    row = _row()
    row["snapshot_payload"]["features"][0]["raw_value"] = float("nan")
    with pytest.raises(ValueError):
        json.dumps(row, allow_nan=False)
