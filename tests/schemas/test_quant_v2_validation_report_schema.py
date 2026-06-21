from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema import ValidationError as JsonSchemaError

from crypto_probability_engine.shadow_validation.service import (
    build_shadow_validation_report,
)
from tests.shadow_validation.conftest import ReadOnlyRepository, make_validation_row

SCHEMA = json.loads(Path("schemas/quant_v2_validation_report.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA)


def _report() -> dict:
    return build_shadow_validation_report(
        ReadOnlyRepository([make_validation_row(1)]),
        generated_at_utc="2026-06-21T00:00:00Z",
    )


def test_report_validates_with_strict_framework_constants() -> None:
    report = _report()
    VALIDATOR.validate(report)
    assert report["read_only"] is True
    assert report["framework_mode"] == "FRAMEWORK_ONLY"
    assert report["temporal_validation_policy"]["holdout_status"] == "SEALED_NOT_EVALUATED"
    assert report["promotion_eligibility"]["promotion_eligible"] is False
    assert report["promotion_eligibility"]["any_eligible"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        lambda report: report.update({"unexpected": True}),
        lambda report: report.update({"read_only": False}),
        lambda report: report["promotion_eligibility"].update(
            {"promotion_eligible": True}
        ),
        lambda report: report["temporal_validation_policy"].update(
            {"holdout_status": "EVALUATED"}
        ),
        lambda report: report["feature_reports"][0].update({"unexpected": True}),
    ],
)
def test_strict_schema_rejects_contract_drift(mutation) -> None:
    report = deepcopy(_report())
    mutation(report)
    with pytest.raises(JsonSchemaError):
        VALIDATOR.validate(report)


def test_schema_and_report_do_not_define_source_payload_output() -> None:
    assert "snapshot_payload" not in json.dumps(SCHEMA)
    assert "snapshot_payload" not in json.dumps(_report())
