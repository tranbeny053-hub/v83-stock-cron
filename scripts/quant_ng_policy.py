"""Validate the closed, digest-pinned OD-NG-5 corpus policy.

This module is the policy schema and does not interpret the policy or compute
provenance. ``CORPUS_POLICY_SCHEMA_v1.json`` is intentionally not created: a
separate schema file would create a second source of truth.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

_PARSER_SPEC = importlib.util.spec_from_file_location(
    "quant_ng_extract_policy", Path(__file__).with_name("quant_ng_extract.py")
)
if _PARSER_SPEC is None or _PARSER_SPEC.loader is None:
    raise RuntimeError("cannot load parser")
_EXTRACT = importlib.util.module_from_spec(_PARSER_SPEC)
_PREVIOUS_BYTECODE = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    _PARSER_SPEC.loader.exec_module(_EXTRACT)
finally:
    sys.dont_write_bytecode = _PREVIOUS_BYTECODE

Refusal = _EXTRACT._FIT.Refusal

# This allowlist changes only through a reviewed code change.
OWNER_RULED_POLICY_SHA256 = frozenset()

POLICY_ID = "ucpe.quant_ng.corpus_policy.v1"
RULINGS = {"SYNTHETIC_TEST_ONLY", "OWNER_RULED"}
PARAMETER_ORDER = (
    "D2_provenance",
    "D3_evidence",
    "D4_availability",
    "D5_revision",
    "D6_proxy",
    "D7_completeness",
    "D8_close_time",
    "operating_period_start",
)
PARAMETER_NAMES = set(PARAMETER_ORDER)
DECIMAL_RE = re.compile(r"^(?:0\.[0-9]+|1(?:\.0+)?)$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
UTC_INSTANT_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z$"
)
REQUIRED_EXCLUSIONS = {"F3", "BTCUSDT", "ETHUSDT", "BTC_ETH_PROXIES"}


def _closed(value: Any, keys: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == keys


def _ruling(value: Any) -> str:
    if not isinstance(value, str) or value not in RULINGS:
        raise Refusal("invalid policy")
    return value


def _decimal(value: Any) -> bool:
    if not isinstance(value, str) or not DECIMAL_RE.fullmatch(value):
        return False
    return float(value) > 0


def _sample(value: Any) -> None:
    if not _closed(value, {"size", "selection", "exclusions", "interval_days"}):
        raise Refusal("invalid policy")
    if type(value["size"]) is not int or value["size"] < 1:
        raise Refusal("invalid policy")
    selection = value["selection"]
    if not _closed(selection, {"method", "paths"}) or selection["method"] != "LISTED":
        raise Refusal("invalid policy")
    paths = selection["paths"]
    if (
        not isinstance(paths, list)
        or not paths
        or any(not isinstance(path, str) or not path for path in paths)
    ):
        raise Refusal("invalid policy")
    if value["size"] != len(paths):
        raise Refusal("invalid policy")
    exclusions = value["exclusions"]
    if not isinstance(exclusions, list) or any(not isinstance(item, str) for item in exclusions):
        raise Refusal("invalid policy")
    if not REQUIRED_EXCLUSIONS.issubset(exclusions):
        raise Refusal("policy detail unruled: sample exclusions")
    if type(value["interval_days"]) is not int or value["interval_days"] < 1:
        raise Refusal("invalid policy")


def _value(name: str, detail: Any) -> str | tuple[str, str]:
    if name == "D2_provenance":
        if not _closed(detail, {"value", "ruling"}):
            raise Refusal("invalid policy")
        value = detail["value"]
        if value == "FP-0":
            raise Refusal("policy option refused: FP-0")
        if value != "FP-1":
            raise Refusal("invalid policy")
    elif name == "D3_evidence":
        if not _closed(detail, {"value", "ruling", "non_market_sha256"}):
            raise Refusal("invalid policy")
        value = detail["value"]
        if not isinstance(value, str) or value not in {"E-1", "E-2", "E-3"}:
            raise Refusal("invalid policy")
        if not isinstance(detail["non_market_sha256"], str) or not SHA256_RE.fullmatch(
            detail["non_market_sha256"]
        ):
            raise Refusal("invalid policy")
    elif name == "D4_availability":
        if not _closed(detail, {"value", "ruling"}):
            raise Refusal("invalid policy")
        value = detail["value"]
        if not isinstance(value, str) or value not in {"P-1", "P-2"}:
            raise Refusal("invalid policy")
    elif name == "D5_revision":
        if not _closed(detail, {"value", "ruling", "sample"}):
            raise Refusal("invalid policy")
        value = detail["value"]
        if value == "RP-1′":
            raise Refusal("policy option refused: RP-1′ (it reads retained research data)")
        if not isinstance(value, str) or value not in {"RP-0", "RP-1", "RP-2", "RP-3", "RP-3+RP-1"}:
            raise Refusal("invalid policy")
        needs_sample = value in {"RP-1", "RP-2", "RP-3+RP-1"}
        if needs_sample and detail["sample"] is None:
            raise Refusal("policy detail unruled: sample")
        if not needs_sample and detail["sample"] is not None:
            raise Refusal("invalid policy")
        if needs_sample:
            _sample(detail["sample"])
    elif name == "D6_proxy":
        if not _closed(detail, {"value", "ruling"}):
            raise Refusal("invalid policy")
        value = detail["value"]
        if not isinstance(value, str) or value not in {"PX-1", "PX-2"}:
            raise Refusal("invalid policy")
    elif name == "D7_completeness":
        if not _closed(detail, {"value", "ruling"}):
            raise Refusal("invalid policy")
        value = detail["value"]
        if not isinstance(value, dict):
            raise Refusal("invalid policy")
        if value.get("shape") == "ONE":
            if not _closed(value, {"shape", "values"}) or not _closed(value["values"], {"all"}):
                raise Refusal("invalid policy")
            if not _decimal(value["values"]["all"]):
                raise Refusal("invalid policy")
        elif value.get("shape") == "PER_WINDOW":
            windows = {"1D", "15m", "1H", "4H"}
            if not _closed(value, {"shape", "values"}) or not _closed(value["values"], windows):
                raise Refusal("invalid policy")
            if any(not _decimal(value["values"][window]) for window in windows):
                raise Refusal("invalid policy")
        else:
            raise Refusal("invalid policy")
    elif name == "D8_close_time":
        if not _closed(detail, {"value", "ruling"}):
            raise Refusal("invalid policy")
        value = detail["value"]
        if not isinstance(value, str) or value not in {"CT-1", "CT-2", "CT-3", "CT-4"}:
            raise Refusal("invalid policy")
        if value == "CT-4":
            raise Refusal("policy detail unruled: close-time direction")
    else:
        if not _closed(detail, {"utc", "provenance"}):
            raise Refusal("invalid policy")
        for key in ("utc", "provenance"):
            item = detail[key]
            if not _closed(item, {"value", "ruling"}):
                raise Refusal("invalid policy")
            item_value = item["value"]
            if key == "utc":
                if item_value is not None:
                    if not isinstance(item_value, str) or not UTC_INSTANT_RE.fullmatch(item_value):
                        raise Refusal("invalid policy")
                    try:
                        datetime.fromisoformat(item_value[:-1] + "+00:00")
                    except ValueError as exc:
                        raise Refusal("invalid policy") from exc
            elif item_value is not None and (not isinstance(item_value, str) or not item_value):
                raise Refusal("invalid policy")
            _ruling(item["ruling"])
        return _ruling(detail["utc"]["ruling"]), _ruling(detail["provenance"]["ruling"])
    ruling = _ruling(detail["ruling"])
    if name == "D3_evidence" and value == "E-2" and ruling == "OWNER_RULED":
        raise Refusal("policy option refused: E-2 amends ruled R4")
    return ruling


def load(path: Path, expected_sha256: str) -> dict:
    """Read once, verify the pin, and return a closed validated policy object."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise Refusal("invalid policy") from exc
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256:
        raise Refusal("policy digest mismatch")
    try:
        policy = json.loads(raw, object_pairs_hook=_EXTRACT._FIT._no_duplicate_keys)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise Refusal("invalid policy") from exc
    if not _closed(policy, {"policy_id", "status", "parameters"}):
        raise Refusal("invalid policy")
    if (
        policy["policy_id"] != POLICY_ID
        or not isinstance(policy["status"], str)
        or policy["status"] not in {"MOCK", "OWNER_RULED"}
    ):
        raise Refusal("invalid policy")
    parameters = policy["parameters"]
    if not _closed(parameters, PARAMETER_NAMES):
        raise Refusal("invalid policy")
    rulings = []
    for name in PARAMETER_ORDER:
        result = _value(name, parameters[name])
        rulings.extend(result if isinstance(result, tuple) else (result,))
    expected_ruling = "SYNTHETIC_TEST_ONLY" if policy["status"] == "MOCK" else "OWNER_RULED"
    if any(ruling != expected_ruling for ruling in rulings):
        raise Refusal("invalid policy")
    if policy["status"] == "OWNER_RULED" and digest not in OWNER_RULED_POLICY_SHA256:
        raise Refusal("policy not owner-ruled")
    return policy
