from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from jsonschema import ValidationError as JsonSchemaError
from pydantic import ValidationError as PydanticError

from crypto_probability_engine.api.app import create_app
from crypto_probability_engine.api.schemas import BuildInfoResponse
from crypto_probability_engine.config.build_info import build_info_payload
from crypto_probability_engine.config.settings import Settings

EXPECTED_FIELDS = {
    "schema_version",
    "release_id",
    "release_label",
    "environment",
    "source_milestone",
    "fingerprint",
}
SCHEMA = json.loads(Path("schemas/build_info.schema.json").read_text())
JSON_VALIDATOR = Draft202012Validator(SCHEMA)


def _client() -> TestClient:
    return TestClient(
        create_app(
            Settings(data_mode="fixture", session_cookie_secure=False)
        )
    )


def test_build_info_is_public_strict_and_no_store() -> None:
    response = _client().get("/v1/build-info")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert "no-store" in response.headers["cache-control"]
    assert response.headers["pragma"] == "no-cache"
    payload = response.json()
    assert set(payload) == EXPECTED_FIELDS
    assert payload["release_id"] == "UCPE-W4D3-OPS-COHORT-20260622-A"
    assert payload["fingerprint"] == "UCPE LIVE BUILD · W4D3-OPS-COHORT-20260622-A"
    assert payload["source_milestone"] == "wave-4d3-ops-prediction-origin"
    assert payload == build_info_payload()
    BuildInfoResponse.model_validate(payload)
    JSON_VALIDATOR.validate(payload)


def test_build_info_repeated_requests_are_byte_identical() -> None:
    client = _client()

    first = client.get("/v1/build-info")
    second = client.get("/v1/build-info")

    assert first.status_code == second.status_code == 200
    assert first.content == second.content
    assert first.json() == second.json()


@pytest.mark.parametrize(
    ("mutation", "value"),
    [
        ("missing", None),
        ("extra", True),
        ("schema_version", "build-info.v2"),
        ("release_id", "UCPE-invalid"),
        ("release_label", ""),
    ],
)
def test_pydantic_and_json_schema_reject_the_same_invalid_contracts(
    mutation: str,
    value: object,
) -> None:
    payload = deepcopy(build_info_payload())
    if mutation == "missing":
        payload.pop("release_label")
    elif mutation == "extra":
        payload["unexpected"] = value
    else:
        payload[mutation] = value

    with pytest.raises(PydanticError):
        BuildInfoResponse.model_validate(payload)
    with pytest.raises(JsonSchemaError):
        JSON_VALIDATOR.validate(payload)


def test_index_routes_are_no_store_without_disabling_asset_caching() -> None:
    client = _client()

    for path in ("/", "/index.html"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "Ultimate Crypto Probability Engine" in response.text
        assert "no-store" in response.headers["cache-control"]
        assert response.headers["pragma"] == "no-cache"

    for path in ("/app.js", "/styles.css"):
        response = client.get(path)
        assert response.status_code == 200
        assert "no-store" not in response.headers.get("cache-control", "")


def test_build_info_route_is_not_swallowed_by_static_mount() -> None:
    response = _client().get("/v1/build-info")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["schema_version"] == "build-info.v1"
