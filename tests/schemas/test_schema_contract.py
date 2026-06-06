from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, RefResolver
from pydantic import ValidationError

from crypto_probability_engine.api.schemas import AnalysisResponse, ErrorCode
from crypto_probability_engine.utils.invariants import validate_probability_triplet
from tests.fixtures.sample_payloads import sample_analysis_payload

SCHEMA_DIR = Path("schemas")


def load_schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text())


def validate_json_schema(payload: dict) -> None:
    store = {
        "quant.schema.json": load_schema("quant.schema.json"),
        "detail_view.schema.json": load_schema("detail_view.schema.json"),
    }
    schema = load_schema("response.schema.json")
    validator = Draft202012Validator(
        schema,
        resolver=RefResolver.from_schema(schema, store=store),
    )
    validator.validate(payload)


@pytest.mark.parametrize("analysis_mode", ["METRICS_ONLY", "NEWS_ADDON"])
def test_response_schema_and_model_accept_canonical_payload(analysis_mode: str) -> None:
    payload = sample_analysis_payload(analysis_mode)
    validate_json_schema(payload)
    model = AnalysisResponse.model_validate(payload)
    assert model.analysis_mode == analysis_mode


def test_probability_invariant_rejects_bad_sum() -> None:
    with pytest.raises(ValueError):
        validate_probability_triplet(0.9, 0.2, 0.1)


def test_model_rejects_probability_invariant_break() -> None:
    payload = sample_analysis_payload()
    payload["probability_state"]["horizons"]["H_primary"]["p_timeout_frac"] = 0.30
    with pytest.raises(ValidationError):
        AnalysisResponse.model_validate(payload)


def test_model_rejects_non_utc_datetime() -> None:
    payload = sample_analysis_payload()
    payload["as_of_utc"] = "2026-06-06T07:00:00+07:00"
    with pytest.raises(ValidationError):
        AnalysisResponse.model_validate(payload)


def test_model_rejects_fraction_out_of_bounds() -> None:
    payload = sample_analysis_payload()
    payload["frontend_display"]["prob_up_frac"] = 1.2
    with pytest.raises(ValidationError):
        AnalysisResponse.model_validate(payload)


def test_error_code_includes_unsupported_asset_class() -> None:
    assert ErrorCode.UNSUPPORTED_ASSET_CLASS == "UNSUPPORTED_ASSET_CLASS"

