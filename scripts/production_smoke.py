"""Opt-in, read-only smoke for a deployed UCPE base URL."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

PRODUCTION_SMOKE_ENV = "UCPE_PRODUCTION_SMOKE_ENABLED"
ACCESS_CODE_ENV = "UCPE_SMOKE_ACCESS_CODE"
STALE_FRONTEND_MARKERS = (
    "uncalibrated" + " — see Detail",
    "Open Detail for full probability" + " breakdown",
)
REQUIRED_FRONTEND_MARKERS = ("prob_up_pct", "prob_down_pct", "prob_timeout_pct")
SENSITIVE_SYSTEM_FIELD_PARTS = ("url", "host", "username", "password", "key")
DEFAULT_TIMEOUT = 10.0
DEFAULT_CALIBRATION_TIMEOUT = 120.0


class SmokeFailure(RuntimeError):
    """The first causal smoke failure."""


def _positive_timeout(value: str) -> float:
    try:
        timeout = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive number") from exc
    if not math.isfinite(timeout) or timeout <= 0:
        raise argparse.ArgumentTypeError("must be a positive number")
    return timeout


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--authenticated", action="store_true")
    parser.add_argument("--raw-capture-dir", default=".work/prod-smoke/")
    parser.add_argument("--timeout", type=_positive_timeout, default=DEFAULT_TIMEOUT)
    parser.add_argument(
        "--calibration-timeout",
        type=_positive_timeout,
        default=DEFAULT_CALIBRATION_TIMEOUT,
    )
    return parser


def _require_preconditions(args: argparse.Namespace, environ: dict[str, str]) -> str | None:
    if environ.get(PRODUCTION_SMOKE_ENV) != "true":
        raise SmokeFailure(f"{PRODUCTION_SMOKE_ENV} must be true")
    access_code = environ.get(ACCESS_CODE_ENV)
    if args.authenticated and not access_code:
        raise SmokeFailure(f"{ACCESS_CODE_ENV} is required with --authenticated")
    parsed = urlsplit(args.base_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise SmokeFailure("--base-url must be an https URL without credentials")
    return access_code


def _capture(response: httpx.Response, capture_dir: Path, name: str) -> None:
    capture_dir.mkdir(parents=True, exist_ok=True)
    (capture_dir / name).write_bytes(response.content)


def _request(
    client: httpx.Client,
    capture_dir: Path,
    name: str,
    path: str,
    timeout: float,
) -> httpx.Response:
    safe_path = urlsplit(path).path
    try:
        response = client.get(path, timeout=timeout)
    except httpx.TimeoutException as exc:
        raise SmokeFailure(f"GET {safe_path} timed out after {timeout:.1f}s") from exc
    except httpx.TransportError as exc:
        raise SmokeFailure(f"GET {safe_path} transport error after {timeout:.1f}s") from exc
    _capture(response, capture_dir, name)
    return response


def _login(
    client: httpx.Client,
    capture_dir: Path,
    access_code: str,
    timeout: float,
) -> httpx.Response:
    path = "/v1/auth/login"
    try:
        response = client.post("/v1/auth/login", json={"code": access_code}, timeout=timeout)
    except httpx.TimeoutException as exc:
        raise SmokeFailure(f"POST {path} timed out after {timeout:.1f}s") from exc
    except httpx.TransportError as exc:
        raise SmokeFailure(f"POST {path} transport error after {timeout:.1f}s") from exc
    _capture(response, capture_dir, "phase-b-login.body")
    return response


def _json(response: httpx.Response, context: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SmokeFailure(f"{context} returned malformed JSON") from exc
    if not isinstance(payload, dict):
        raise SmokeFailure(f"{context} returned a non-object JSON body")
    return payload


def _require_status(response: httpx.Response, expected: int, context: str) -> None:
    if response.status_code != expected:
        raise SmokeFailure(f"{context} returned HTTP {response.status_code}, expected {expected}")


def _assert_unauthorized(response: httpx.Response, context: str) -> None:
    _require_status(response, 401, context)
    payload = _json(response, context)
    try:
        error = payload["detail"]["error"]
    except (KeyError, TypeError) as exc:
        raise SmokeFailure(f"{context} returned a malformed unauthorized error body") from exc
    if not isinstance(error, dict) or error.get("code") != "UNAUTHORIZED":
        raise SmokeFailure(f"{context} did not return the UNAUTHORIZED error contract")


def _phase_a(client: httpx.Client, capture_dir: Path, timeout: float) -> str:
    health = _request(client, capture_dir, "phase-a-healthcheck.body", "/healthcheck", timeout)
    _require_status(health, 200, "GET /healthcheck")
    if _json(health, "GET /healthcheck").get("status") != "OK":
        raise SmokeFailure("GET /healthcheck did not report status OK")

    build = _request(client, capture_dir, "phase-a-build-info.body", "/v1/build-info", timeout)
    _require_status(build, 200, "GET /v1/build-info")
    fingerprint = _json(build, "GET /v1/build-info").get("fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint:
        raise SmokeFailure("GET /v1/build-info omitted the build fingerprint")
    print(f"build fingerprint: {fingerprint}")

    root = _request(client, capture_dir, "phase-a-root.body", "/", timeout)
    _require_status(root, 200, "GET /")
    match = re.search(r'<script[^>]+src="([^"]*app\.js[^"]*)"', root.text)
    if match is None:
        raise SmokeFailure("app.js script tag not found in served HTML")
    app_js_path = match.group(1)
    bundle = _request(client, capture_dir, "phase-a-app-js.body", app_js_path, timeout)
    _require_status(bundle, 200, f"GET {app_js_path}")
    for marker in REQUIRED_FRONTEND_MARKERS:
        if marker not in bundle.text:
            raise SmokeFailure(f"served app.js missing {marker}")
    for marker in STALE_FRONTEND_MARKERS:
        if marker in bundle.text:
            raise SmokeFailure(f"served app.js contains stale marker: {marker}")

    status = _request(
        client,
        capture_dir,
        "phase-a-system-status-unauthorized.body",
        "/v1/system_status",
        timeout,
    )
    _assert_unauthorized(status, "unauthenticated GET /v1/system_status")
    calibration = _request(
        client,
        capture_dir,
        "phase-a-calibration-unauthorized.body",
        "/v1/calibration",
        timeout,
    )
    _assert_unauthorized(calibration, "unauthenticated GET /v1/calibration")
    return app_js_path


def _assert_system_status_sanitized(payload: dict[str, Any]) -> tuple[str, str]:
    system = payload.get("system")
    if not isinstance(system, dict):
        raise SmokeFailure("GET /v1/system_status omitted the system object")
    for key in system:
        lowered = str(key).lower()
        if any(part in lowered for part in SENSITIVE_SYSTEM_FIELD_PARTS):
            raise SmokeFailure("GET /v1/system_status exposed a sensitive field")
    serialized = json.dumps(payload, sort_keys=True).lower()
    if "://" in serialized:
        raise SmokeFailure("GET /v1/system_status exposed a URL")
    persistence = system.get("persistence_status")
    repository = system.get("repository_type")
    if not isinstance(persistence, str) or not isinstance(repository, str):
        raise SmokeFailure("GET /v1/system_status omitted persistence diagnostics")
    return persistence, repository


def _phase_b(
    client: httpx.Client,
    capture_dir: Path,
    access_code: str,
    timeout: float,
    calibration_timeout: float,
) -> None:
    login = _login(client, capture_dir, access_code, timeout)
    _require_status(login, 200, "login")

    status = _request(
        client, capture_dir, "phase-b-system-status.body", "/v1/system_status", timeout
    )
    _require_status(status, 200, "authenticated GET /v1/system_status")
    persistence, repository = _assert_system_status_sanitized(
        _json(status, "authenticated GET /v1/system_status")
    )
    print(f"persistence_status={persistence} repository_type={repository}")

    response = _request(
        client,
        capture_dir,
        "phase-b-calibration.body",
        "/v1/calibration",
        calibration_timeout,
    )
    _require_status(response, 200, "authenticated GET /v1/calibration")
    payload = _json(response, "authenticated GET /v1/calibration")
    timeframes = payload.get("timeframes")
    if not isinstance(timeframes, list):
        raise SmokeFailure("GET /v1/calibration omitted the timeframes list")
    for item in timeframes:
        if not isinstance(item, dict):
            raise SmokeFailure("GET /v1/calibration returned a malformed timeframe")
        timeframe = item.get("timeframe")
        calibration_status = item.get("reliability_status")
        sample_count = item.get("sample_count")
        if (
            not isinstance(timeframe, str)
            or not isinstance(calibration_status, str)
            or not isinstance(sample_count, int)
            or isinstance(sample_count, bool)
            or sample_count < 0
        ):
            raise SmokeFailure("GET /v1/calibration returned incomplete timeframe diagnostics")
        print(
            f"timeframe={timeframe} calibration_status={calibration_status} "
            f"sample_count={sample_count}"
        )


def main(
    argv: Sequence[str] | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
    environ: dict[str, str] | None = None,
) -> int:
    args = _parser().parse_args(argv)
    env = dict(os.environ) if environ is None else environ
    phases: list[str] = []
    try:
        access_code = _require_preconditions(args, env)
        capture_dir = Path(args.raw_capture_dir)
        with httpx.Client(
            base_url=args.base_url.rstrip("/") + "/",
            transport=transport,
            follow_redirects=False,
        ) as client:
            phases.append("A")
            _phase_a(client, capture_dir, args.timeout)
            if args.authenticated:
                phases.append("B")
                _phase_b(
                    client,
                    capture_dir,
                    access_code or "",
                    args.timeout,
                    args.calibration_timeout,
                )
    except (SmokeFailure, httpx.HTTPError, OSError) as exc:
        ran = "+".join(phases) if phases else "none"
        print(f"FAIL: production smoke phases {ran}; {exc}")
        return 1
    ran = "+".join(phases)
    print(f"PASS: production smoke phases {ran}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
