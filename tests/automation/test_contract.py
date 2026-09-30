"""Strict wire parsing and independent verification of the published evidence contract."""

import hashlib
import json
from copy import deepcopy
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator

from crypto_probability_engine.api.analysis_service import analyze_request_isolated
from crypto_probability_engine.api.schemas import AnalysisRequest
from crypto_probability_engine.automation.contract import (
    ERROR_CATALOGUE,
    ERROR_SCHEMA_FILE,
    RADAR_EVIDENCE_SCHEMA_FILE,
    ContractError,
    ErrorCode,
    build_radar_evidence,
    error_body,
    evidence_hash,
    parse_request,
)
from crypto_probability_engine.config.build_info import build_info_payload
from crypto_probability_engine.config.settings import Settings
from tests.automation.conftest import request_body, token


def encode(**overrides):
    return json.dumps(request_body(**overrides)).encode()


MALFORMED = [
    b" " * 1025,
    b"\xff",
    b"not json",
    b"[]",
    b"null",
    b"{}",
    json.dumps({k: v for k, v in request_body().items() if k != "symbol"}).encode(),
    encode(extra="unexpected"),
    encode().replace(b'"symbol": "BTC"', b'"symbol": "BTC", "symbol": "ETH"'),
    encode(deadline_ms=float("nan")),
    encode(deadline_ms=float("inf")),
    encode(deadline_ms=float("-inf")),
    encode(deadline_ms=True),
    encode(deadline_ms=5000.0),
    encode(deadline_ms=4999),
    encode(deadline_ms=60001),
    encode(client_request_id=request_body()["client_request_id"].upper()),
    encode(client_request_id="{" + request_body()["client_request_id"] + "}"),
    encode(client_request_id=request_body()["client_request_id"].replace("-", "")),
    encode(symbol=42),
    encode(symbol=None),
    encode(symbol=""),
    encode(symbol="A" * 33),
]


@pytest.mark.parametrize("raw", MALFORMED)
def test_malformed_request_is_refused(raw):
    with pytest.raises(ContractError) as caught:
        parse_request(raw)
    assert caught.value.code is ErrorCode.MALFORMED_REQUEST
    assert str(caught.value) == "MALFORMED_REQUEST"


@pytest.mark.parametrize("timeframe", ["1W", "1M", "5m"])
def test_unsupported_timeframe(timeframe):
    with pytest.raises(ContractError) as caught:
        parse_request(encode(primary_timeframe=timeframe))
    assert caught.value.code is ErrorCode.UNSUPPORTED_TIMEFRAME


def test_unnormalizable_symbol():
    with pytest.raises(ContractError) as caught:
        parse_request(encode(symbol="???"))
    assert caught.value.code is ErrorCode.UNSUPPORTED_SYMBOL


@pytest.mark.parametrize("deadline", [5000, 60000])
@pytest.mark.parametrize("timeframe", ["15m", "1H", "4H", "1D"])
def test_request_accepts_published_boundaries(deadline, timeframe):
    parsed = parse_request(encode(deadline_ms=deadline, primary_timeframe=timeframe))
    assert parsed.deadline_ms == deadline and parsed.primary_timeframe == timeframe


def test_fingerprint_ignores_request_id():
    assert (
        parse_request(encode()).fingerprint
        == parse_request(encode(client_request_id=str(uuid4()))).fingerprint
    )


@pytest.mark.parametrize(
    "change",
    [
        {"symbol": "ETH"},
        {"primary_timeframe": "1H"},
        {"deadline_ms": 5000},
    ],
)
def test_fingerprint_covers_request_semantics(change):
    assert parse_request(encode()).fingerprint != parse_request(encode(**change)).fingerprint


def test_catalogue_exactly_matches_error_schema():
    schema = json.loads(ERROR_SCHEMA_FILE.read_text())
    codes = schema["properties"]["error"]["properties"]["code"]["enum"]
    assert set(codes) == {code.value for code in ErrorCode} == set(ERROR_CATALOGUE)


@pytest.mark.parametrize("code", list(ErrorCode))
@pytest.mark.parametrize("retry", [None, 1, 86400])
def test_every_error_body_validates_and_messages_are_fixed(code, retry):
    body = error_body(code, retry)
    Draft202012Validator(json.loads(ERROR_SCHEMA_FILE.read_text())).validate(body)
    assert body["error"]["code"] == code.value
    assert body["error"]["message"] == ERROR_CATALOGUE[code][1]
    assert body["error"]["retry_after_seconds"] == retry
    for private_value in [token(), request_body()["client_request_id"], "BTC", "30000"]:
        assert private_value not in body["error"]["message"]


@pytest.fixture
def real_analysis(fixture_market):
    return analyze_request_isolated(
        AnalysisRequest(symbol="BTC", timeframe="4H"), settings=Settings(data_mode="fixture")
    )


def build(analysis):
    return build_radar_evidence(
        analysis,
        request=parse_request(encode()),
        build_info=build_info_payload(),
        issued_at_utc="2026-09-30T00:00:00Z",
    )


def independent_hash(body):
    unsigned = {key: value for key, value in body.items() if key != "evidence_hash"}
    serialized = json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")
    return "sha256:" + hashlib.sha256(serialized).hexdigest()


def test_real_isolated_analysis_builds_schema_valid_evidence(real_analysis):
    body = build(real_analysis)
    Draft202012Validator(json.loads(RADAR_EVIDENCE_SCHEMA_FILE.read_text())).validate(body)
    assert body["evidence_hash"] == independent_hash(body) == evidence_hash(body)
    assert body["analysis_hash"] == real_analysis["analysis_hash"]
    for key, horizon in body["probability_state"]["horizons"].items():
        assert horizon["sample_count"] is None
        assert horizon["sample_count_basis"] == "NONE_UNCALIBRATED_HEURISTIC"
        for field in ("p_up_frac", "p_down_frac", "p_timeout_frac", "confidence_frac"):
            assert horizon[field] == real_analysis["probability_state"]["horizons"][key][field]


def leaf_paths(value, prefix=()):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from leaf_paths(child, (*prefix, key))
    elif isinstance(value, list) and value:
        for index, child in enumerate(value):
            yield from leaf_paths(child, (*prefix, index))
    else:
        yield prefix


def test_tampering_every_field_breaks_independent_hash(real_analysis):
    body = build(real_analysis)
    for path in leaf_paths(body):
        changed = deepcopy(body)
        parent = changed
        for part in path[:-1]:
            parent = parent[part]
        parent[path[-1]] = "synthetic-tampering"
        assert independent_hash(changed) != changed["evidence_hash"], path
        if path != ("evidence_hash",):
            assert evidence_hash(changed) != body["evidence_hash"], path


@pytest.mark.parametrize("horizon", ["H_primary", "H_extended"])
def test_probabilities_must_sum_to_one(real_analysis, horizon):
    real_analysis["probability_state"]["horizons"][horizon].update(
        p_up_frac=0.2, p_down_frac=0.2, p_timeout_frac=0.2
    )
    with pytest.raises(ContractError) as caught:
        build(real_analysis)
    assert caught.value.code is ErrorCode.CONTRACT_VIOLATION


@pytest.mark.parametrize(
    "field",
    [
        "probability_state",
        "calibration_state",
        "gate_result",
        "decision_brief",
        "frontend_display",
    ],
)
def test_missing_governed_field_is_withheld(real_analysis, field):
    del real_analysis[field]
    with pytest.raises(ContractError) as caught:
        build(real_analysis)
    assert caught.value.code is ErrorCode.CONTRACT_VIOLATION


@pytest.mark.parametrize("field", ["calibration_state", "decision_brief"])
def test_profitability_claim_is_refused(real_analysis, field):
    real_analysis[field]["profitability_claim"] = True
    with pytest.raises(ContractError) as caught:
        build(real_analysis)
    assert caught.value.code is ErrorCode.CONTRACT_VIOLATION


def test_hold_is_projected_without_legacy_verdict(real_analysis):
    real_analysis["gate_result"]["directional_evidence_hold"] = {
        "active": True,
        "hold_reason": "INSUFFICIENT_EVIDENCE",
        "legacy_verdict": "synthetic",
    }
    body = build(real_analysis)
    assert body["gate_result"]["directional_evidence_hold"] == {
        "active": True,
        "hold_reason": "INSUFFICIENT_EVIDENCE",
    }
    # Cohort/withheld-field isolation is already covered by test_cohort_isolation.py.
    assert "skill_evidence" not in json.dumps(body)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (
            RADAR_EVIDENCE_SCHEMA_FILE,
            "37c2d12488b71c2409ca48188d67aa981ad47e4d2b398a9668bbcfdc0c687b8f",
        ),
        (ERROR_SCHEMA_FILE, "1d3b402ee5c014ad2129dd87e3fd12de15cd69d9b07042d3f1c8bbac62d9b15f"),
    ],
)
def test_published_schema_bytes_are_pinned(path, expected):
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, (
        "Published contract changed: bump the schema version before updating this pin"
    )
