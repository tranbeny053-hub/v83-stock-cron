"""The wire contract of POST /v1/automation/radar-evidence: request, response, errors, hashes.

- **Request** (strict; unknown, missing or duplicate fields are refused):
  ``{"symbol", "primary_timeframe", "client_request_id", "deadline_ms"}``.
- **Response**: ``radar_evidence.v1`` (``schemas/radar_evidence.schema.json``), built only from
  UCPE's governed analysis, never recomputed. Every body is validated against the pinned schema
  before it leaves; a body that fails is never sent (503 ``CONTRACT_VIOLATION``).
- **Errors**: ``radar_evidence_error.v1`` with a fixed catalogue and fixed messages. No body ever
  echoes a credential, a request field or user data.
- **Hashes** (published so a consumer can re-verify offline):
  ``canonical_json(x) = json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
  allow_nan=False)``, encoded as ASCII; ``evidence_hash = "sha256:" + sha256(canonical_json(body
  without "evidence_hash"))``. ``analysis_hash`` is UCPE's own analysis identity, carried as read.
"""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from crypto_probability_engine.automation.config import (
    DEADLINE_MS_MAX,
    DEADLINE_MS_MIN,
    REQUEST_BODY_MAX_BYTES,
)
from crypto_probability_engine.automation.origin import AUTOMATED_RADAR
from crypto_probability_engine.normalizers.symbols import (
    SymbolNormalizationError,
    normalize_symbol,
)

RADAR_EVIDENCE_SCHEMA_VERSION = "radar_evidence.v1"
ERROR_SCHEMA_VERSION = "radar_evidence_error.v1"
SUPPORTED_TIMEFRAMES = ("15m", "1H", "4H", "1D")
HORIZON_KEYS = ("H_primary", "H_extended")
BUILD_INFO_KEYS = (
    "schema_version",
    "release_id",
    "release_label",
    "environment",
    "source_milestone",
    "fingerprint",
)
SAMPLE_COUNT_BASIS = "NONE_UNCALIBRATED_HEURISTIC"
DETERMINISM_BASIS = "CANONICAL_INPUTS_AND_RELEASE"
PROBABILITY_SUM_TOLERANCE = 1e-9
SCHEMA_DIR = Path(__file__).resolve().parents[3] / "schemas"
RADAR_EVIDENCE_SCHEMA_FILE = SCHEMA_DIR / "radar_evidence.schema.json"
ERROR_SCHEMA_FILE = SCHEMA_DIR / "radar_evidence_error.schema.json"
_REQUEST_KEYS = frozenset({"symbol", "primary_timeframe", "client_request_id", "deadline_ms"})
_PROBABILITY_KEYS = ("p_up_frac", "p_down_frac", "p_timeout_frac")


class ErrorCode(StrEnum):
    MALFORMED_REQUEST = "MALFORMED_REQUEST"
    CREDENTIAL_REQUIRED = "CREDENTIAL_REQUIRED"
    CREDENTIAL_INVALID = "CREDENTIAL_INVALID"
    HUMAN_SESSION_REFUSED = "HUMAN_SESSION_REFUSED"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    REQUEST_IN_PROGRESS = "REQUEST_IN_PROGRESS"
    UNSUPPORTED_SYMBOL = "UNSUPPORTED_SYMBOL"
    UNSUPPORTED_TIMEFRAME = "UNSUPPORTED_TIMEFRAME"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    CONCURRENCY_LIMIT = "CONCURRENCY_LIMIT"
    AUTOMATION_DISABLED = "AUTOMATION_DISABLED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    LEDGER_UNAVAILABLE = "LEDGER_UNAVAILABLE"
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    ANALYSIS_FAILED = "ANALYSIS_FAILED"
    CONTRACT_VIOLATION = "CONTRACT_VIOLATION"


# The whole error catalogue: HTTP status and a fixed message per code.
ERROR_CATALOGUE: dict[ErrorCode, tuple[int, str]] = {
    ErrorCode.MALFORMED_REQUEST: (400, "The request body is not a valid radar-evidence request."),
    ErrorCode.CREDENTIAL_REQUIRED: (401, "A machine credential is required."),
    ErrorCode.CREDENTIAL_INVALID: (401, "The machine credential was refused."),
    ErrorCode.HUMAN_SESSION_REFUSED: (403, "Human sessions are not accepted on this route."),
    ErrorCode.IDEMPOTENCY_CONFLICT: (
        409,
        "This client_request_id was already used for a different request.",
    ),
    ErrorCode.REQUEST_IN_PROGRESS: (409, "This client_request_id is still being processed."),
    ErrorCode.UNSUPPORTED_SYMBOL: (422, "The symbol is not supported."),
    ErrorCode.UNSUPPORTED_TIMEFRAME: (422, "The primary_timeframe is not supported."),
    ErrorCode.QUOTA_EXCEEDED: (429, "The credential's quota is exhausted."),
    ErrorCode.CONCURRENCY_LIMIT: (429, "An automated analysis is already running."),
    ErrorCode.AUTOMATION_DISABLED: (503, "The automation route is disabled."),
    ErrorCode.NOT_CONFIGURED: (503, "The automation route is not configured."),
    ErrorCode.LEDGER_UNAVAILABLE: (503, "The automation ledger is unavailable."),
    ErrorCode.DEADLINE_EXCEEDED: (503, "The deadline passed before evidence was ready."),
    ErrorCode.UPSTREAM_UNAVAILABLE: (503, "Market data is unavailable."),
    ErrorCode.ANALYSIS_FAILED: (503, "The analysis could not be completed."),
    ErrorCode.CONTRACT_VIOLATION: (503, "The evidence failed its contract and was withheld."),
}


class ContractError(Exception):
    """A refusal with a catalogued error code."""

    def __init__(self, code: ErrorCode, retry_after_seconds: int | None = None) -> None:
        super().__init__(code.value)
        self.code = code
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class RadarEvidenceRequest:
    symbol: str
    primary_timeframe: str
    client_request_id: str
    deadline_ms: int

    @property
    def fingerprint(self) -> str:
        """Identity of the request without its idempotency key: a repeat must match it exactly."""

        return content_hash(
            {
                "symbol": self.symbol,
                "primary_timeframe": self.primary_timeframe,
                "deadline_ms": self.deadline_ms,
            }
        )


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def content_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def evidence_hash(body: dict[str, Any]) -> str:
    """The published hash of a radar_evidence body: everything except ``evidence_hash`` itself."""

    return content_hash({key: value for key, value in body.items() if key != "evidence_hash"})


def error_body(code: ErrorCode, retry_after_seconds: int | None = None) -> dict[str, Any]:
    return {
        "schema_version": ERROR_SCHEMA_VERSION,
        "error": {
            "code": code.value,
            "message": ERROR_CATALOGUE[code][1],
            "retry_after_seconds": retry_after_seconds,
        },
    }


def error_status(code: ErrorCode) -> int:
    return ERROR_CATALOGUE[code][0]


def parse_request(body: bytes) -> RadarEvidenceRequest:
    """Parse one strict request. Raises ``ContractError``; never echoes the body."""

    if not isinstance(body, bytes | bytearray) or len(body) > REQUEST_BODY_MAX_BYTES:
        raise ContractError(ErrorCode.MALFORMED_REQUEST)
    try:
        text = bytes(body).decode("utf-8")
        payload = json.loads(
            text,
            object_pairs_hook=_refuse_duplicate_keys,
            parse_constant=_refuse_constant,
        )
    except (UnicodeDecodeError, ValueError, TypeError):
        raise ContractError(ErrorCode.MALFORMED_REQUEST) from None
    if not isinstance(payload, dict) or set(payload) != _REQUEST_KEYS:
        raise ContractError(ErrorCode.MALFORMED_REQUEST)
    symbol = payload["symbol"]
    timeframe = payload["primary_timeframe"]
    client_request_id = payload["client_request_id"]
    deadline_ms = payload["deadline_ms"]
    if not isinstance(symbol, str) or not 1 <= len(symbol) <= 32:
        raise ContractError(ErrorCode.MALFORMED_REQUEST)
    if not isinstance(timeframe, str) or not 1 <= len(timeframe) <= 8:
        raise ContractError(ErrorCode.MALFORMED_REQUEST)
    if not isinstance(client_request_id, str) or not _is_canonical_uuid(client_request_id):
        raise ContractError(ErrorCode.MALFORMED_REQUEST)
    if (
        not isinstance(deadline_ms, int)
        or isinstance(deadline_ms, bool)
        or not DEADLINE_MS_MIN <= deadline_ms <= DEADLINE_MS_MAX
    ):
        raise ContractError(ErrorCode.MALFORMED_REQUEST)
    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise ContractError(ErrorCode.UNSUPPORTED_TIMEFRAME)
    try:
        normalize_symbol(symbol)
    except (SymbolNormalizationError, ValueError, TypeError):
        raise ContractError(ErrorCode.UNSUPPORTED_SYMBOL) from None
    return RadarEvidenceRequest(symbol, timeframe, client_request_id, deadline_ms)


def build_radar_evidence(
    analysis: dict[str, Any],
    *,
    request: RadarEvidenceRequest,
    build_info: dict[str, Any],
    issued_at_utc: str,
) -> dict[str, Any]:
    """Map a validated UCPE analysis to radar_evidence.v1, reading values and never recomputing.

    Raises ``ContractError(CONTRACT_VIOLATION)`` when the analysis lacks a governed field, when a
    horizon's probabilities do not sum to 1, or when the body fails the pinned schema.
    """

    try:
        probability_state = analysis["probability_state"]
        calibration_state = analysis["calibration_state"]
        gate = analysis["gate_result"]
        brief = analysis["decision_brief"]
        display = analysis["frontend_display"]
        quality = analysis["data_quality"]
        timeframes = analysis["timeframes"]
        hold = gate.get("directional_evidence_hold")
        body: dict[str, Any] = {
            "schema_version": RADAR_EVIDENCE_SCHEMA_VERSION,
            "evidence_origin": AUTOMATED_RADAR,
            "client_request_id": request.client_request_id,
            "run_id": analysis["run_id"],
            "analysis_hash": analysis["analysis_hash"],
            "analysis_schema_version": analysis["schema_version"],
            "as_of_utc": analysis["as_of_utc"],
            "issued_at_utc": issued_at_utc,
            "symbol": request.symbol,
            "normalized_symbol": analysis["normalized_symbol"],
            "primary_timeframe": timeframes["primary"],
            "horizon": {"bars": timeframes["horizon_bars"], "label": timeframes["horizon_label"]},
            # Exactly the serving release's public build-info payload (GET /v1/build-info).
            "build_info": {key: build_info[key] for key in BUILD_INFO_KEYS},
            "probability_state": {
                "probability_type": brief["probability_type"],
                "calibration_status": probability_state["calibration_status"],
                "horizons": {
                    key: _horizon(probability_state["horizons"][key]) for key in HORIZON_KEYS
                },
            },
            "calibration_state": {
                "calibration_status": calibration_state["calibration_status"],
                "reliability_status": calibration_state["reliability_status"],
                "profitability_claim": calibration_state["profitability_claim"],
                "reason": calibration_state["reason"],
            },
            "gate_result": {
                "hard_gate_passed": gate["hard_gate_passed"],
                "hard_blocks": list(gate["hard_blocks"]),
                # The legacy verdict under correction is deliberately not carried.
                "directional_evidence_hold": (
                    None
                    if hold is None
                    else {"active": hold["active"], "hold_reason": hold["hold_reason"]}
                ),
            },
            "decision_brief": {
                "action": brief["action"],
                "hard_blockers": list(brief["hard_blockers"]),
                "model_readiness": brief["model_readiness"],
                "reliability_status": brief["reliability_status"],
                "profitability_claim": brief["profitability_claim"],
            },
            "frontend_display": {
                "is_live_data": display["is_live_data"],
                "disposition": display["disposition"],
            },
            "data_quality": {
                "status": quality["status"],
                "is_live_data": quality["is_live_data"],
                "data_source": quality.get("data_source"),
                "cross_provider_state": quality.get("cross_provider_state"),
            },
            "determinism": {"basis": DETERMINISM_BASIS, "live_repeat_reproducible": False},
        }
    except (KeyError, TypeError, AttributeError):
        raise ContractError(ErrorCode.CONTRACT_VIOLATION) from None
    body["evidence_hash"] = evidence_hash(body)
    if not radar_evidence_valid(body):
        raise ContractError(ErrorCode.CONTRACT_VIOLATION)
    return body


def radar_evidence_valid(body: Any) -> bool:
    return _validator(RADAR_EVIDENCE_SCHEMA_FILE).is_valid(body) and _probabilities_sum(body)


def error_body_valid(body: Any) -> bool:
    return _validator(ERROR_SCHEMA_FILE).is_valid(body)


def _horizon(horizon: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": horizon["status"],
        "null_reason": horizon.get("null_reason"),
        "p_up_frac": horizon["p_up_frac"],
        "p_down_frac": horizon["p_down_frac"],
        "p_timeout_frac": horizon["p_timeout_frac"],
        "confidence_frac": horizon["confidence_frac"],
        # UCPE's probabilities are uncalibrated heuristic estimates: no sample count stands
        # behind them, so none is ever reported (never fabricated).
        "sample_count": None,
        "sample_count_basis": SAMPLE_COUNT_BASIS,
    }


def _probabilities_sum(body: Any) -> bool:
    try:
        horizons = body["probability_state"]["horizons"]
        for key in HORIZON_KEYS:
            values = [horizons[key][name] for name in _PROBABILITY_KEYS]
            if all(value is None for value in values):
                continue
            if any(value is None or not math.isfinite(value) for value in values):
                return False
            if abs(sum(values) - 1.0) > PROBABILITY_SUM_TOLERANCE:
                return False
    except (KeyError, TypeError):
        return False
    return True


@lru_cache(maxsize=2)
def _validator(path: Path) -> Draft202012Validator:
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _is_canonical_uuid(value: str) -> bool:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return str(parsed) == value and parsed.variant == uuid.RFC_4122 and 1 <= parsed.version <= 8


def _refuse_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _refuse_constant(name: str) -> Any:
    raise ValueError(f"non-finite JSON constant {name}")
