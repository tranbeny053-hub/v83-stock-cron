"""Read-only Binance USD-M registry diagnostic.

This script performs three public GET probes and emits a sanitized JSON
classification. It does not call UCPE analysis, persistence, collectors, or any
private provider resource.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import httpx

from crypto_probability_engine.adapters.derivatives_endpoints import (
    BINANCE_EXCHANGE_INFO_PATH,
    BINANCE_USDM_BASE_URL,
    OKX_INSTRUMENTS_PATH,
    OKX_PUBLIC_BASE_URL,
    DerivativesPublicHttpClient,
)
from crypto_probability_engine.adapters.types import ProviderError

DIAGNOSTIC_VERSION = "binance-registry-diagnostic-v1"
RATE_LIMIT_PER_MINUTE = 20
SUMMARY_ENV_NAME = "GITHUB_STEP_SUMMARY"

ERROR_CATEGORIES = frozenset(
    {
        "OK",
        "TIMEOUT",
        "NETWORK_OR_TLS",
        "RATE_LIMITED",
        "AUTH_FORBIDDEN",
        "LEGAL_BLOCK_451",
        "SERVER_5XX",
        "CLIENT_4XX",
        "MALFORMED_JSON",
        "UNKNOWN",
    }
)
FINAL_CLASSIFICATIONS = frozenset(
    {
        "BINANCE_OK",
        "BINANCE_TIMEOUT_AT_3S_BUT_OK_AT_10S",
        "BINANCE_ACCESS_RESTRICTED",
        "BINANCE_RATE_LIMITED",
        "BINANCE_SERVER_FAILURE",
        "BINANCE_NETWORK_OR_TLS_FAILURE",
        "BINANCE_MALFORMED_RESPONSE",
        "BINANCE_UNKNOWN_FAILURE",
    }
)
TOP_LEVEL_KEYS = frozenset(
    {
        "diagnostic_version",
        "probe_count",
        "probes",
        "final_classification",
    }
)
PROBE_KEYS = frozenset(
    {
        "provider",
        "endpoint_path",
        "timeout_seconds",
        "outcome",
        "http_status",
        "error_category",
        "attempt_count",
        "elapsed_ms",
        "symbols_count",
        "data_count",
    }
)


@dataclass(frozen=True)
class ProbeSpec:
    provider: str
    base_url: str
    endpoint_path: str
    params: Mapping[str, object]
    timeout_seconds: float
    expected_shape: str


PROBES = (
    ProbeSpec(
        provider="BINANCE_USDM",
        base_url=BINANCE_USDM_BASE_URL,
        endpoint_path=BINANCE_EXCHANGE_INFO_PATH,
        params={},
        timeout_seconds=3.0,
        expected_shape="binance_exchange_info",
    ),
    ProbeSpec(
        provider="BINANCE_USDM",
        base_url=BINANCE_USDM_BASE_URL,
        endpoint_path=BINANCE_EXCHANGE_INFO_PATH,
        params={},
        timeout_seconds=10.0,
        expected_shape="binance_exchange_info",
    ),
    ProbeSpec(
        provider="OKX_SWAP",
        base_url=OKX_PUBLIC_BASE_URL,
        endpoint_path=OKX_INSTRUMENTS_PATH,
        params={"instType": "SWAP"},
        timeout_seconds=10.0,
        expected_shape="okx_instruments",
    ),
)


def run_diagnostic(
    *,
    client_factory: Callable[[float], object] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, object]:
    """Run exactly three public probes and return sanitized diagnostic evidence."""

    probes = [
        _run_probe(spec, client_factory=client_factory, monotonic=monotonic)
        for spec in PROBES
    ]
    output = {
        "diagnostic_version": DIAGNOSTIC_VERSION,
        "probe_count": len(probes),
        "probes": probes,
        "final_classification": _final_classification(probes[:2]),
    }
    _validate_output(output)
    return output


def _run_probe(
    spec: ProbeSpec,
    *,
    client_factory: Callable[[float], object] | None,
    monotonic: Callable[[], float],
) -> dict[str, object]:
    start = monotonic()
    result = _base_probe_result(spec, elapsed_ms=0)
    try:
        client = (
            client_factory(spec.timeout_seconds)
            if client_factory is not None
            else DerivativesPublicHttpClient(
                timeout_seconds=spec.timeout_seconds,
                max_retries=0,
                rate_limit_per_min=RATE_LIMIT_PER_MINUTE,
            )
        )
        payload = client.get_json(
            base_url=spec.base_url,
            path=spec.endpoint_path,
            params=spec.params,
            provider=spec.provider,
        )
        result.update(_validate_success_payload(payload, spec))
    except Exception as exc:
        result.update(
            {
                "outcome": "FAILED",
                "http_status": _safe_http_status(exc),
                "error_category": _classify_exception(exc),
            }
        )
    result["elapsed_ms"] = _elapsed_ms(start, monotonic)
    _validate_probe_result(result)
    return result


def _base_probe_result(spec: ProbeSpec, *, elapsed_ms: int) -> dict[str, object]:
    return {
        "provider": spec.provider,
        "endpoint_path": spec.endpoint_path,
        "timeout_seconds": spec.timeout_seconds,
        "outcome": "FAILED",
        "http_status": None,
        "error_category": "UNKNOWN",
        "attempt_count": 1,
        "elapsed_ms": elapsed_ms,
        "symbols_count": None,
        "data_count": None,
    }


def _validate_success_payload(payload: object, spec: ProbeSpec) -> dict[str, object]:
    if spec.expected_shape == "binance_exchange_info":
        if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list):
            return {"outcome": "FAILED", "error_category": "MALFORMED_JSON"}
        symbols = payload["symbols"]
        _ = any(isinstance(row, dict) and row.get("symbol") == "BTCUSDT" for row in symbols)
        return {
            "outcome": "OK",
            "error_category": "OK",
            "http_status": 200,
            "symbols_count": len(symbols),
            "data_count": None,
        }
    if spec.expected_shape == "okx_instruments":
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            return {"outcome": "FAILED", "error_category": "MALFORMED_JSON"}
        return {
            "outcome": "OK",
            "error_category": "OK",
            "http_status": 200,
            "symbols_count": None,
            "data_count": len(payload["data"]),
        }
    return {"outcome": "FAILED", "error_category": "UNKNOWN"}


def _classify_exception(exc: BaseException) -> str:
    status = _safe_http_status(exc)
    if status in {401, 403}:
        return "AUTH_FORBIDDEN"
    if status in {418, 429}:
        return "RATE_LIMITED"
    if status == 451:
        return "LEGAL_BLOCK_451"
    if status is not None and 500 <= status <= 599:
        return "SERVER_5XX"
    if status is not None and 400 <= status <= 499:
        return "CLIENT_4XX"
    if isinstance(exc, ProviderError):
        if exc.error_type == "SCHEMA" or exc.error_code == "MALFORMED_JSON":
            return "MALFORMED_JSON"
        if "timed out" in exc.message.lower():
            return "TIMEOUT"
        return "NETWORK_OR_TLS"
    if isinstance(exc, httpx.TimeoutException):
        return "TIMEOUT"
    if isinstance(exc, httpx.TransportError):
        return "NETWORK_OR_TLS"
    return "UNKNOWN"


def _safe_http_status(exc: BaseException) -> int | None:
    if isinstance(exc, ProviderError):
        return exc.http_status
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def _final_classification(binance_probes: list[dict[str, object]]) -> str:
    categories = [str(probe.get("error_category")) for probe in binance_probes]
    if categories == ["OK", "OK"]:
        return "BINANCE_OK"
    if categories == ["TIMEOUT", "OK"]:
        return "BINANCE_TIMEOUT_AT_3S_BUT_OK_AT_10S"
    if any(category in {"LEGAL_BLOCK_451", "AUTH_FORBIDDEN"} for category in categories):
        return "BINANCE_ACCESS_RESTRICTED"
    if "RATE_LIMITED" in categories:
        return "BINANCE_RATE_LIMITED"
    if "SERVER_5XX" in categories:
        return "BINANCE_SERVER_FAILURE"
    if categories == ["NETWORK_OR_TLS", "NETWORK_OR_TLS"]:
        return "BINANCE_NETWORK_OR_TLS_FAILURE"
    if "MALFORMED_JSON" in categories:
        return "BINANCE_MALFORMED_RESPONSE"
    return "BINANCE_UNKNOWN_FAILURE"


def _elapsed_ms(start: float, monotonic: Callable[[], float]) -> int:
    return int(round(max(0.0, monotonic() - start) * 1000))


def append_step_summary(path: str | None, output: Mapping[str, object]) -> None:
    if not path:
        return
    probes = output.get("probes")
    if not isinstance(probes, list):
        return
    lines = [
        "## UCPE Derivatives Registry Diagnostic",
        "",
        (
            "| provider | endpoint path | timeout | outcome | HTTP status | "
            "error category | elapsed ms |"
        ),
        "|---|---|---:|---|---:|---|---:|",
    ]
    for probe in probes:
        if not isinstance(probe, Mapping):
            continue
        lines.append(
            "| {provider} | {endpoint_path} | {timeout_seconds} | {outcome} | "
            "{http_status} | {error_category} | {elapsed_ms} |".format(
                provider=probe.get("provider"),
                endpoint_path=probe.get("endpoint_path"),
                timeout_seconds=probe.get("timeout_seconds"),
                outcome=probe.get("outcome"),
                http_status="" if probe.get("http_status") is None else probe.get("http_status"),
                error_category=probe.get("error_category"),
                elapsed_ms=probe.get("elapsed_ms"),
            )
        )
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
        handle.write("\n")


def _validate_output(output: Mapping[str, object]) -> None:
    if set(output) != TOP_LEVEL_KEYS:
        raise RuntimeError("Diagnostic output contract mismatch.")
    if output.get("diagnostic_version") != DIAGNOSTIC_VERSION:
        raise RuntimeError("Diagnostic version mismatch.")
    probes = output.get("probes")
    if output.get("probe_count") != 3 or not isinstance(probes, list) or len(probes) != 3:
        raise RuntimeError("Probe count mismatch.")
    if output.get("final_classification") not in FINAL_CLASSIFICATIONS:
        raise RuntimeError("Final classification mismatch.")
    for probe in probes:
        if not isinstance(probe, Mapping):
            raise RuntimeError("Probe output is invalid.")
        _validate_probe_result(probe)


def _validate_probe_result(probe: Mapping[str, object]) -> None:
    if set(probe) != PROBE_KEYS:
        raise RuntimeError("Probe output contract mismatch.")
    if probe.get("outcome") not in {"OK", "FAILED"}:
        raise RuntimeError("Probe outcome mismatch.")
    if probe.get("error_category") not in ERROR_CATEGORIES:
        raise RuntimeError("Probe category mismatch.")


def main(
    argv: list[str] | None = None,
    *,
    client_factory: Callable[[float], object] | None = None,
    environ: Mapping[str, str] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> int:
    _ = argv
    output = run_diagnostic(client_factory=client_factory, monotonic=monotonic)
    text = json.dumps(output, sort_keys=True, separators=(",", ":"))
    print(text)
    summary_path = (environ or os.environ).get(SUMMARY_ENV_NAME)
    append_step_summary(summary_path, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
