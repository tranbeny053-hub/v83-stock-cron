"""Validate sample API payloads against JSON Schemas and Pydantic models."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

from jsonschema import Draft202012Validator, RefResolver

from crypto_probability_engine.api.schemas import validate_analysis_response

ROOT = Path(__file__).resolve().parents[1]


def sample_payload_module() -> ModuleType:
    path = ROOT / "tests" / "fixtures" / "sample_payloads.py"
    spec = importlib.util.spec_from_file_location("sample_payloads", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load sample payload fixtures.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_schema(name: str) -> dict:
    return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))


def main() -> int:
    response_schema = load_schema("response.schema.json")
    store = {
        "quant.schema.json": load_schema("quant.schema.json"),
        "news.schema.json": load_schema("news.schema.json"),
        "detail_view.schema.json": load_schema("detail_view.schema.json"),
    }
    resolver = RefResolver.from_schema(response_schema, store=store)
    validator = Draft202012Validator(response_schema, resolver=resolver)
    sample_analysis_payload = sample_payload_module().sample_analysis_payload
    for mode in ("METRICS_ONLY", "NEWS_ADDON"):
        payload = sample_analysis_payload(mode)
        validator.validate(payload)
        validate_analysis_response(payload)
    print("PASS: schemas and sample payloads validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
