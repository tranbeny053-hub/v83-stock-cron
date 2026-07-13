"""Public-read-only runtime source and serving integrity guard."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SPACE_HOST = "beny053-ultimate-crypto-probability-engine.hf.space"
SPACE_ORIGIN = f"https://{SPACE_HOST}"
HF_GIT_URL = "https://huggingface.co/spaces/beny053/ultimate-crypto-probability-engine"
EXPECTED_SCHEMA_VERSION = "build-info.v1"
PIN_SCHEMA_VERSION = "hf-runtime-baseline.v1"
PIN_SCHEMA_ID = (
    "https://ultimate-crypto-probability-engine.local/"
    "schemas/hf_runtime_baseline.schema.json"
)
PIN_MANIFEST_RELATIVE_PATH = Path("ops/hf_runtime_baseline.json")
PIN_SCHEMA_RELATIVE_PATH = Path("schemas/hf_runtime_baseline.schema.json")
PIN_MAX_FILE_BYTES = 256 * 1024
LOCAL_GIT_TIMEOUT_SECONDS = 5.0

PROBE_ROUNDS = 3
ROUND_SPACING_SECONDS = 20.0
HTTP_TIMEOUT_SECONDS = 15.0
HTTP_MAX_ATTEMPTS = 2
GIT_TIMEOUT_SECONDS = 30.0
MAX_BODY_BYTES = 5 * 1024 * 1024

CRITICAL_SOURCE_PATHS = (
    "src/crypto_probability_engine/config/build_info.py",
    "src/crypto_probability_engine/api/app.py",
    "src/crypto_probability_engine/api/analysis_service.py",
    "src/crypto_probability_engine/quant_v2/contract.py",
    "src/crypto_probability_engine/derivatives_intel/runtime.py",
    "schemas/build_info.schema.json",
    "schemas/response.schema.json",
    "frontend/index.html",
    "frontend/app.js",
    "frontend/styles.css",
    "Dockerfile",
)
SOURCE_CONTRACT_PATHS = frozenset(
    {
        "src/crypto_probability_engine/config/build_info.py",
        "schemas/build_info.schema.json",
    }
)
REQUIRED_BUILD_INFO_FIELDS = frozenset(
    {
        "schema_version",
        "release_id",
        "release_label",
        "environment",
        "source_milestone",
        "fingerprint",
    }
)
FORBIDDEN_ENDPOINTS = frozenset(
    {"/v1/analyze", "/v1/auth", "/v1/calibration", "/v1/watchlist"}
)
DIVERGENCE_CLASSIFICATIONS = frozenset(
    {
        "PIN_DRIFT",
        "STALE_RUNTIME",
        "STALE_FRONTEND",
        "SOURCE_DIVERGENCE",
        "CONTRACT_MISSING",
    }
)
ALL_CLASSIFICATIONS = frozenset(
    {
        "PIN_MISSING",
        "PIN_DRIFT",
        "CONTRACT_MISSING",
        "PROBE_UNAVAILABLE",
        "SOURCE_DIVERGENCE",
        "STALE_RUNTIME",
        "STALE_FRONTEND",
        "HEALTHY_WITH_METADATA_ANOMALY",
        "HEALTHY",
        "TRANSITIONING",
    }
)
ADVISORY_STATUSES = frozenset(
    {
        "NONE",
        "SCHEDULER_AHEAD_OF_PIN",
        "SCHEDULER_DIVERGENT_FROM_PIN",
        "NOT_EVALUATED",
    }
)
PIN_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "hf_main_sha",
        "release_id",
        "release_label",
        "environment",
        "source_milestone",
        "fingerprint",
        "frontend_asset_tokens",
        "critical_source_digests",
    }
)
ALLOWED_SUMMARY_FIELDS = frozenset(
    {
        "space_host",
        "intended_release_id",
        "live_release_id",
        "intended_source_milestone",
        "live_source_milestone",
        "schema_version",
        "intended_fingerprint",
        "live_fingerprint",
        "frontend_asset_tokens",
        "frontend_asset_match",
        "hf_main_sha",
        "critical_source_match",
        "mismatched_path_names",
        "runtime_stage",
        "http_statuses",
        "probe_timestamps",
        "per_round_classifications",
        "final_classification",
        "exit_code",
        "pinned_hf_main_sha",
        "pin_schema_version",
        "deployment_delta_present",
        "scheduler_head_sha",
        "scheduler_ahead_count",
        "deployment_delta_paths",
        "advisory_status",
    }
)


class ProbeTransportError(RuntimeError):
    """Sanitized transport failure without provider response content."""


class PinValidationError(RuntimeError):
    """Sanitized static pin failure raised before any runtime probe."""


@dataclass(frozen=True)
class IntendedContract:
    schema_version: str
    hf_main_sha: str
    release_id: str
    release_label: str
    environment: str
    source_milestone: str
    fingerprint: str
    asset_tokens: dict[str, str]
    critical_source_digests: dict[str, str]


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes


@dataclass(frozen=True)
class GitCommandResult:
    returncode: int
    stdout: bytes


@dataclass(frozen=True)
class SourceEvidence:
    available: bool
    hf_main_sha: str | None
    critical_source_match: bool
    missing_path_names: tuple[str, ...]
    mismatched_path_names: tuple[str, ...]
    contract_missing: bool


@dataclass(frozen=True)
class LiveEvidence:
    http_statuses: dict[str, int | None]
    root_reachable: bool
    transport_unavailable: bool
    contract_missing: bool
    schema_version: str | None
    release_id: str | None
    source_milestone: str | None
    fingerprint: str | None
    live_asset_tokens: dict[str, str | None]
    frontend_asset_match: bool
    runtime_stage: str | None


@dataclass(frozen=True)
class RoundEvidence:
    timestamp: str
    source: SourceEvidence
    live: LiveEvidence
    classification: str


HttpGet = Callable[[str, float], HttpResponse]
GitRunner = Callable[[Sequence[str], float], GitCommandResult]
Clock = Callable[[], float]
UtcNow = Callable[[], datetime]


def load_intended_contract(checkout_root: Path) -> IntendedContract:
    """Load and strictly validate the committed HF production baseline."""

    try:
        root = checkout_root.resolve()
        manifest_path = _resolved_pin_path(root, PIN_MANIFEST_RELATIVE_PATH)
        schema_path = _resolved_pin_path(root, PIN_SCHEMA_RELATIVE_PATH)
        manifest = _load_bounded_json(manifest_path)
        schema = _load_bounded_json(schema_path)
        if not isinstance(manifest, dict) or not isinstance(schema, dict):
            raise PinValidationError("Pinned baseline is invalid.")
        _validate_pin_schema(schema)
        _validate_pin_payload(manifest)
        return IntendedContract(
            schema_version=manifest["schema_version"],
            hf_main_sha=manifest["hf_main_sha"],
            release_id=manifest["release_id"],
            release_label=manifest["release_label"],
            environment=manifest["environment"],
            source_milestone=manifest["source_milestone"],
            fingerprint=manifest["fingerprint"],
            asset_tokens=dict(manifest["frontend_asset_tokens"]),
            critical_source_digests=dict(manifest["critical_source_digests"]),
        )
    except Exception:
        raise PinValidationError("Pinned baseline is unavailable.") from None


def _resolved_pin_path(checkout_root: Path, relative_path: Path) -> Path:
    path = (checkout_root / relative_path).resolve()
    if not path.is_relative_to(checkout_root):
        raise PinValidationError("Pinned baseline path is invalid.")
    return path


def _load_bounded_json(path: Path) -> Any:
    if not path.is_file() or path.stat().st_size > PIN_MAX_FILE_BYTES:
        raise PinValidationError("Pinned baseline file is unavailable.")
    return json.loads(path.read_bytes().decode("utf-8"))


def _validate_pin_payload(manifest: Mapping[str, Any]) -> None:
    if set(manifest) != PIN_MANIFEST_FIELDS:
        raise PinValidationError("Pinned baseline fields are invalid.")
    if manifest.get("schema_version") != PIN_SCHEMA_VERSION:
        raise PinValidationError("Pinned baseline version is unsupported.")
    hf_main_sha = manifest.get("hf_main_sha")
    if not isinstance(hf_main_sha, str) or not re.fullmatch(
        r"[0-9a-f]{40}", hf_main_sha
    ):
        raise PinValidationError("Pinned baseline SHA is invalid.")

    text_fields = (
        "release_id",
        "release_label",
        "environment",
        "source_milestone",
        "fingerprint",
    )
    if any(_strict_pin_text(manifest.get(field)) is None for field in text_fields):
        raise PinValidationError("Pinned baseline identity is invalid.")
    if manifest["environment"] != "HF_PRODUCTION":
        raise PinValidationError("Pinned baseline environment is invalid.")
    release_id = manifest["release_id"]
    if not re.fullmatch(r"UCPE-[A-Z0-9-]{3,}", release_id):
        raise PinValidationError("Pinned baseline release is invalid.")
    if manifest["fingerprint"] != (
        f"UCPE LIVE BUILD · {release_id.removeprefix('UCPE-')}"
    ):
        raise PinValidationError("Pinned baseline fingerprint is inconsistent.")

    asset_tokens = manifest.get("frontend_asset_tokens")
    if not isinstance(asset_tokens, dict) or set(asset_tokens) != {
        "app_js",
        "styles_css",
    }:
        raise PinValidationError("Pinned frontend tokens are invalid.")
    if any(
        not isinstance(token, str)
        or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", token)
        for token in asset_tokens.values()
    ):
        raise PinValidationError("Pinned frontend token is invalid.")

    digests = manifest.get("critical_source_digests")
    if not isinstance(digests, dict) or set(digests) != set(CRITICAL_SOURCE_PATHS):
        raise PinValidationError("Pinned critical source paths are invalid.")
    if any(
        not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
        for digest in digests.values()
    ):
        raise PinValidationError("Pinned critical source digest is invalid.")


def _validate_pin_schema(schema: Mapping[str, Any]) -> None:
    if set(schema) != {
        "$schema",
        "$id",
        "type",
        "additionalProperties",
        "required",
        "properties",
    }:
        raise PinValidationError("Pinned baseline schema fields are invalid.")
    if (
        schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema"
        or schema.get("$id") != PIN_SCHEMA_ID
        or schema.get("type") != "object"
        or schema.get("additionalProperties") is not False
        or not _exact_string_list(schema.get("required"), PIN_MANIFEST_FIELDS)
    ):
        raise PinValidationError("Pinned baseline schema root is invalid.")
    properties = schema.get("properties")
    if not isinstance(properties, dict) or set(properties) != PIN_MANIFEST_FIELDS:
        raise PinValidationError("Pinned baseline schema properties are invalid.")

    _require_schema_node(
        properties["schema_version"],
        {"type": "string", "minLength": 1, "const": PIN_SCHEMA_VERSION},
    )
    _require_schema_node(
        properties["hf_main_sha"],
        {"type": "string", "pattern": "^[0-9a-f]{40}$"},
    )
    for field in (
        "release_id",
        "release_label",
        "environment",
        "source_milestone",
        "fingerprint",
    ):
        _require_schema_node(
            properties[field], {"type": "string", "minLength": 1}
        )

    frontend = properties["frontend_asset_tokens"]
    frontend_fields = {"app_js", "styles_css"}
    if (
        not isinstance(frontend, dict)
        or set(frontend) != {
            "type",
            "additionalProperties",
            "required",
            "properties",
        }
        or frontend.get("type") != "object"
        or frontend.get("additionalProperties") is not False
        or not _exact_string_list(frontend.get("required"), frontend_fields)
        or not isinstance(frontend.get("properties"), dict)
        or set(frontend["properties"]) != frontend_fields
    ):
        raise PinValidationError("Pinned frontend token schema is invalid.")
    for field in frontend_fields:
        _require_schema_node(
            frontend["properties"][field], {"type": "string", "minLength": 1}
        )

    digests = properties["critical_source_digests"]
    governed_paths = set(CRITICAL_SOURCE_PATHS)
    if (
        not isinstance(digests, dict)
        or set(digests) != {
            "type",
            "additionalProperties",
            "required",
            "properties",
        }
        or digests.get("type") != "object"
        or digests.get("additionalProperties") is not False
        or not _exact_string_list(digests.get("required"), governed_paths)
        or not isinstance(digests.get("properties"), dict)
        or set(digests["properties"]) != governed_paths
    ):
        raise PinValidationError("Pinned critical digest schema is invalid.")
    for field in governed_paths:
        _require_schema_node(
            digests["properties"][field],
            {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        )


def _exact_string_list(value: Any, expected: set[str] | frozenset[str]) -> bool:
    return (
        isinstance(value, list)
        and all(isinstance(item, str) for item in value)
        and len(value) == len(expected)
        and set(value) == set(expected)
    )


def _require_schema_node(value: Any, expected: Mapping[str, Any]) -> None:
    if not isinstance(value, dict) or value != expected:
        raise PinValidationError("Pinned baseline schema node is invalid.")


def _strict_pin_text(value: Any) -> str | None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 256
        or not value.isprintable()
    ):
        return None
    return value


def _read_constant_assignments(path: Path) -> dict[str, Any]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values: dict[str, Any] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        try:
            values[target.id] = _safe_ast_value(node.value, values)
        except (KeyError, TypeError, ValueError):
            continue
    return values


def _safe_ast_value(node: ast.AST, values: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return values[node.id]
    if isinstance(node, ast.Call) and not node.keywords and len(node.args) == 1:
        if isinstance(node.func, ast.Attribute) and node.func.attr == "removeprefix":
            value = _safe_ast_value(node.func.value, values)
            prefix = _safe_ast_value(node.args[0], values)
            if isinstance(value, str) and isinstance(prefix, str):
                return value.removeprefix(prefix)
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                rendered = _safe_ast_value(value.value, values)
                if not isinstance(rendered, str):
                    raise TypeError("Formatted release value is not text.")
                parts.append(rendered)
            else:
                raise TypeError("Unsupported release expression.")
        return "".join(parts)
    raise TypeError("Unsupported release expression.")


def _extract_asset_token(index_text: str, asset_name: str) -> str:
    match = re.search(
        rf'["\']/({re.escape(asset_name)})\?v=([A-Za-z0-9._-]+)["\']', index_text
    )
    if match is None or not match.group(2).strip() or len(match.group(2)) > 128:
        raise ValueError(f"Missing version token for {asset_name}.")
    return match.group(2)


def verify_hf_source(
    intended: IntendedContract,
    *,
    git_runner: GitRunner | None = None,
    monotonic: Clock = time.monotonic,
) -> SourceEvidence:
    """Resolve and compare an exact HF main commit in an isolated temporary Git repo."""

    runner = git_runner or _run_git
    deadline = monotonic() + GIT_TIMEOUT_SECONDS

    def run_result(args: Sequence[str]) -> GitCommandResult:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise ProbeTransportError("Git probe deadline exceeded.")
        return runner(args, min(remaining, GIT_TIMEOUT_SECONDS))

    def run(args: Sequence[str]) -> GitCommandResult:
        result = run_result(args)
        if result.returncode != 0:
            raise ProbeTransportError("Public Git read failed.")
        return result

    try:
        remote = run(("git", "ls-remote", HF_GIT_URL, "refs/heads/main"))
        line = remote.stdout.decode("ascii", errors="ignore").strip().splitlines()
        sha = line[0].split()[0] if line else ""
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ProbeTransportError("HF main did not resolve to a commit.")
        if sha != intended.hf_main_sha:
            return SourceEvidence(
                available=True,
                hf_main_sha=sha,
                critical_source_match=False,
                missing_path_names=(),
                mismatched_path_names=(),
                contract_missing=False,
            )
        with tempfile.TemporaryDirectory(prefix="ucpe-source-integrity-") as temp_dir:
            run(("git", "-C", temp_dir, "init", "--quiet"))
            run(
                (
                    "git",
                    "-C",
                    temp_dir,
                    "fetch",
                    "--quiet",
                    "--depth=1",
                    HF_GIT_URL,
                    sha,
                )
            )
            missing: list[str] = []
            mismatched: list[str] = []
            for relative_path in CRITICAL_SOURCE_PATHS:
                result = run_result(
                    (
                        "git",
                        "-C",
                        temp_dir,
                        "show",
                        f"FETCH_HEAD:{relative_path}",
                    ),
                )
                if result.returncode != 0:
                    missing.append(relative_path)
                elif hashlib.sha256(result.stdout).hexdigest() != (
                    intended.critical_source_digests[relative_path]
                ):
                    mismatched.append(relative_path)
        missing_paths = tuple(sorted(set(missing)))
        mismatched_paths = tuple(sorted(set(mismatched)))
        return SourceEvidence(
            available=True,
            hf_main_sha=sha,
            critical_source_match=not missing_paths and not mismatched_paths,
            missing_path_names=missing_paths,
            mismatched_path_names=mismatched_paths,
            contract_missing=bool(SOURCE_CONTRACT_PATHS.intersection(missing_paths)),
        )
    except (OSError, ProbeTransportError, subprocess.SubprocessError):
        return SourceEvidence(
            available=False,
            hf_main_sha=None,
            critical_source_match=False,
            missing_path_names=(),
            mismatched_path_names=(),
            contract_missing=False,
        )


def validate_public_get(url: str, *, expected_asset_tokens: dict[str, str]) -> None:
    """Reject every method-independent URL outside the exact public-read allowlist."""

    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != SPACE_HOST
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError("URL is outside the public runtime allowlist.")
    if parsed.path in FORBIDDEN_ENDPOINTS:
        raise ValueError("Endpoint is explicitly forbidden.")
    if parsed.path in {"/", "/v1/build-info"}:
        if parsed.query:
            raise ValueError("Unexpected query on public runtime endpoint.")
        return
    asset_tokens = {
        "/app.js": expected_asset_tokens["app_js"],
        "/styles.css": expected_asset_tokens["styles_css"],
    }
    expected_token = asset_tokens.get(parsed.path)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    if expected_token is None or query != {"v": [expected_token]}:
        raise ValueError("URL is outside the public runtime allowlist.")


def public_get(
    method: str,
    url: str,
    *,
    expected_asset_tokens: dict[str, str],
    http_get: HttpGet | None = None,
) -> HttpResponse:
    """Perform one allowlisted public GET with at most two total attempts."""

    if method != "GET":
        raise ValueError("Only GET is allowed.")
    validate_public_get(url, expected_asset_tokens=expected_asset_tokens)
    transport = http_get or _urllib_get
    for attempt in range(HTTP_MAX_ATTEMPTS):
        try:
            return transport(url, HTTP_TIMEOUT_SECONDS)
        except (OSError, ProbeTransportError, TimeoutError):
            if attempt + 1 == HTTP_MAX_ATTEMPTS:
                raise ProbeTransportError("Public runtime probe unavailable.") from None
    raise ProbeTransportError("Public runtime probe unavailable.")


def _urllib_get(url: str, timeout: float) -> HttpResponse:
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": "UCPE-Source-Integrity-Guard/1.0"},
    )
    opener = urllib.request.build_opener(_NoRedirectHandler())
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read(MAX_BODY_BYTES + 1)
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        body = exc.read(MAX_BODY_BYTES + 1)
        status = int(exc.code)
    except urllib.error.URLError as exc:
        raise ProbeTransportError("Public runtime transport failed.") from exc
    if len(body) > MAX_BODY_BYTES:
        raise ProbeTransportError("Public runtime response exceeded the size limit.")
    return HttpResponse(status=status, body=body)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def probe_live_runtime(
    intended: IntendedContract,
    *,
    http_get: HttpGet | None = None,
    runtime_stage: str | None = None,
) -> LiveEvidence:
    """Probe root, build contract, and exact expected frontend assets."""

    urls = {
        "root": f"{SPACE_ORIGIN}/",
        "build_info": f"{SPACE_ORIGIN}/v1/build-info",
        "app_js": f"{SPACE_ORIGIN}/app.js?v={intended.asset_tokens['app_js']}",
        "styles_css": (
            f"{SPACE_ORIGIN}/styles.css?v={intended.asset_tokens['styles_css']}"
        ),
    }
    responses: dict[str, HttpResponse | None] = {}
    for name, url in urls.items():
        try:
            responses[name] = public_get(
                "GET",
                url,
                expected_asset_tokens=intended.asset_tokens,
                http_get=http_get,
            )
        except ProbeTransportError:
            responses[name] = None

    statuses = {
        name: response.status if response is not None else None
        for name, response in responses.items()
    }
    root = responses["root"]
    build = responses["build_info"]
    app = responses["app_js"]
    styles = responses["styles_css"]
    root_reachable = root is not None and root.status == 200
    transport_unavailable = any(response is None for response in responses.values())

    live_tokens: dict[str, str | None] = {"app_js": None, "styles_css": None}
    root_marker = False
    if root_reachable:
        root_text = root.body.decode("utf-8", errors="replace")
        live_tokens = {
            "app_js": _optional_asset_token(root_text, "app.js"),
            "styles_css": _optional_asset_token(root_text, "styles.css"),
        }
        root_marker = "data-build-fingerprint" in root_text

    schema_version = release_id = source_milestone = fingerprint = None
    malformed_contract = False
    if build is not None and build.status == 200:
        try:
            payload = json.loads(build.body)
            if not isinstance(payload, dict) or not REQUIRED_BUILD_INFO_FIELDS.issubset(
                payload
            ):
                malformed_contract = True
            else:
                if any(
                    _optional_text(payload.get(field)) is None
                    for field in REQUIRED_BUILD_INFO_FIELDS
                ):
                    malformed_contract = True
                schema_version = _optional_text(payload.get("schema_version"))
                release_id = _optional_text(payload.get("release_id"))
                source_milestone = _optional_text(payload.get("source_milestone"))
                fingerprint = _optional_text(payload.get("fingerprint"))
                if None in {
                    schema_version,
                    release_id,
                    source_milestone,
                    fingerprint,
                }:
                    malformed_contract = True
        except (TypeError, ValueError, json.JSONDecodeError):
            malformed_contract = True

    app_matches = (
        app is not None
        and app.status == 200
        and hashlib.sha256(app.body).hexdigest()
        == intended.critical_source_digests["frontend/app.js"]
    )
    styles_match = (
        styles is not None
        and styles.status == 200
        and hashlib.sha256(styles.body).hexdigest()
        == intended.critical_source_digests["frontend/styles.css"]
    )
    token_match = live_tokens == intended.asset_tokens
    frontend_asset_match = (
        root_reachable
        and root_marker
        and token_match
        and app_matches
        and styles_match
    )
    contract_missing = bool(
        root_reachable
        and (
            (build is not None and build.status == 404)
            or malformed_contract
            or schema_version not in {None, EXPECTED_SCHEMA_VERSION}
        )
    )
    return LiveEvidence(
        http_statuses=statuses,
        root_reachable=root_reachable,
        transport_unavailable=transport_unavailable,
        contract_missing=contract_missing,
        schema_version=schema_version,
        release_id=release_id,
        source_milestone=source_milestone,
        fingerprint=fingerprint,
        live_asset_tokens=live_tokens,
        frontend_asset_match=frontend_asset_match,
        runtime_stage=_optional_text(runtime_stage),
    )


def _optional_asset_token(index_text: str, asset_name: str) -> str | None:
    try:
        return _extract_asset_token(index_text, asset_name)
    except ValueError:
        return None


def classify_round(
    intended: IntendedContract,
    source: SourceEvidence,
    live: LiveEvidence,
) -> str:
    """Classify one independent observation round."""

    if source.available and source.hf_main_sha != intended.hf_main_sha:
        return "PIN_DRIFT"
    if live.contract_missing or source.contract_missing:
        return "CONTRACT_MISSING"
    if not source.available:
        return "PROBE_UNAVAILABLE"
    if not source.critical_source_match:
        return "SOURCE_DIVERGENCE"
    build_status = live.http_statuses.get("build_info")
    if not live.root_reachable or build_status != 200 or live.transport_unavailable:
        return "PROBE_UNAVAILABLE"
    if (
        live.release_id != intended.release_id
        or live.source_milestone != intended.source_milestone
        or live.fingerprint != intended.fingerprint
    ):
        return "STALE_RUNTIME"
    if not live.frontend_asset_match:
        return "STALE_FRONTEND"
    if live.runtime_stage not in {None, "RUNNING"}:
        return "HEALTHY_WITH_METADATA_ANOMALY"
    return "HEALTHY"


def run_guard(
    checkout_root: Path,
    *,
    sleep: Callable[[float], None] = time.sleep,
    utc_now: UtcNow | None = None,
    round_probe: Callable[[int, IntendedContract], tuple[SourceEvidence, LiveEvidence]]
    | None = None,
    local_git_runner: GitRunner | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Run three rounds and return one strictly allowlisted summary."""

    environment = os.environ if environ is None else environ
    try:
        intended = load_intended_contract(checkout_root)
    except PinValidationError:
        return _pin_missing_summary(environment)
    now = utc_now or (lambda: datetime.now(UTC))
    rounds: list[RoundEvidence] = []
    for index in range(PROBE_ROUNDS):
        timestamp = _iso_utc(now())
        if round_probe is None:
            source = verify_hf_source(intended)
            live = (
                _skipped_live_evidence()
                if source.available and source.hf_main_sha != intended.hf_main_sha
                else probe_live_runtime(intended)
            )
        else:
            source, live = round_probe(index, intended)
        classification = classify_round(intended, source, live)
        rounds.append(
            RoundEvidence(
                timestamp=timestamp,
                source=source,
                live=live,
                classification=classification,
            )
        )
        if index + 1 < PROBE_ROUNDS:
            sleep(ROUND_SPACING_SECONDS)
    return summarize_rounds(
        intended,
        rounds,
        checkout_root=checkout_root,
        local_git_runner=local_git_runner,
        environ=environment,
    )


def summarize_rounds(
    intended: IntendedContract,
    rounds: Sequence[RoundEvidence],
    *,
    checkout_root: Path | None = None,
    local_git_runner: GitRunner | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if len(rounds) != PROBE_ROUNDS:
        raise ValueError("Exactly three probe rounds are required.")
    classifications = [round.classification for round in rounds]
    evidence_signatures = {_round_signature(round) for round in rounds}
    final_classification = (
        classifications[0]
        if len(set(classifications)) == 1 and len(evidence_signatures) == 1
        else "TRANSITIONING"
    )
    exit_code = (
        1
        if final_classification in DIVERGENCE_CLASSIFICATIONS
        and classifications.count(final_classification) == PROBE_ROUNDS
        else 0
    )
    last = rounds[-1]
    mismatched_paths = sorted(
        {
            path
            for round in rounds
            for path in (
                *round.source.missing_path_names,
                *round.source.mismatched_path_names,
            )
        }
    )
    environment = os.environ if environ is None else environ
    advisory = (
        _safe_deployment_advisory(
            checkout_root,
            intended,
            local_git_runner=local_git_runner,
            environ=environment,
        )
        if final_classification == "HEALTHY" and checkout_root is not None
        else _not_evaluated_advisory(environment)
    )
    summary = {
        "space_host": SPACE_HOST,
        "intended_release_id": intended.release_id,
        "live_release_id": last.live.release_id,
        "intended_source_milestone": intended.source_milestone,
        "live_source_milestone": last.live.source_milestone,
        "schema_version": last.live.schema_version,
        "intended_fingerprint": intended.fingerprint,
        "live_fingerprint": last.live.fingerprint,
        "frontend_asset_tokens": {
            "intended": intended.asset_tokens,
            "live": last.live.live_asset_tokens,
        },
        "frontend_asset_match": all(
            round.live.frontend_asset_match for round in rounds
        ),
        "hf_main_sha": last.source.hf_main_sha,
        "critical_source_match": all(
            round.source.critical_source_match for round in rounds
        ),
        "mismatched_path_names": mismatched_paths,
        "runtime_stage": last.live.runtime_stage,
        "http_statuses": [round.live.http_statuses for round in rounds],
        "probe_timestamps": [round.timestamp for round in rounds],
        "per_round_classifications": classifications,
        "final_classification": final_classification,
        "exit_code": exit_code,
        "pinned_hf_main_sha": intended.hf_main_sha,
        "pin_schema_version": intended.schema_version,
        **advisory,
    }
    validate_summary(summary)
    return summary


def _safe_deployment_advisory(
    checkout_root: Path,
    intended: IntendedContract,
    *,
    local_git_runner: GitRunner | None,
    environ: Mapping[str, str],
) -> dict[str, Any]:
    try:
        return evaluate_deployment_delta(
            checkout_root,
            intended,
            local_git_runner=local_git_runner,
            environ=environ,
        )
    except Exception:
        return {
            "deployment_delta_present": True,
            "scheduler_head_sha": _normalized_sha(environ.get("GITHUB_SHA")),
            "scheduler_ahead_count": None,
            "deployment_delta_paths": [],
            "advisory_status": "SCHEDULER_DIVERGENT_FROM_PIN",
        }


def _pin_missing_summary(environ: Mapping[str, str]) -> dict[str, Any]:
    summary = {
        "space_host": SPACE_HOST,
        "intended_release_id": None,
        "live_release_id": None,
        "intended_source_milestone": None,
        "live_source_milestone": None,
        "schema_version": None,
        "intended_fingerprint": None,
        "live_fingerprint": None,
        "frontend_asset_tokens": {
            "intended": {},
            "live": {"app_js": None, "styles_css": None},
        },
        "frontend_asset_match": False,
        "hf_main_sha": None,
        "critical_source_match": False,
        "mismatched_path_names": [],
        "runtime_stage": None,
        "http_statuses": [],
        "probe_timestamps": [],
        "per_round_classifications": [],
        "final_classification": "PIN_MISSING",
        "exit_code": 1,
        "pinned_hf_main_sha": "",
        "pin_schema_version": "",
        **_not_evaluated_advisory(environ),
    }
    validate_summary(summary)
    return summary


def _skipped_live_evidence() -> LiveEvidence:
    return LiveEvidence(
        http_statuses={
            "root": None,
            "build_info": None,
            "app_js": None,
            "styles_css": None,
        },
        root_reachable=False,
        transport_unavailable=False,
        contract_missing=False,
        schema_version=None,
        release_id=None,
        source_milestone=None,
        fingerprint=None,
        live_asset_tokens={"app_js": None, "styles_css": None},
        frontend_asset_match=False,
        runtime_stage=None,
    )


def _not_evaluated_advisory(environ: Mapping[str, str]) -> dict[str, Any]:
    return {
        "deployment_delta_present": False,
        "scheduler_head_sha": _normalized_sha(environ.get("GITHUB_SHA")),
        "scheduler_ahead_count": None,
        "deployment_delta_paths": [],
        "advisory_status": "NOT_EVALUATED",
    }


def evaluate_deployment_delta(
    checkout_root: Path,
    intended: IntendedContract,
    *,
    local_git_runner: GitRunner | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Compare scheduler checkout bytes with the pin without remote access."""

    environment = os.environ if environ is None else environ
    root = checkout_root.resolve()
    delta_paths: list[str] = []
    for relative_path in CRITICAL_SOURCE_PATHS:
        path = (root / relative_path).resolve()
        try:
            if (
                not path.is_relative_to(root)
                or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest()
                != intended.critical_source_digests[relative_path]
            ):
                delta_paths.append(relative_path)
        except OSError:
            delta_paths.append(relative_path)
    delta_paths.sort()

    runner = local_git_runner or _run_git
    scheduler_sha = _normalized_sha(environment.get("GITHUB_SHA"))
    if scheduler_sha is None:
        scheduler_sha = _local_git_sha(
            runner,
            ("git", "-C", str(root), "rev-parse", "HEAD"),
        )
    deployment_delta_present = scheduler_sha != intended.hf_main_sha or bool(
        delta_paths
    )
    ancestor_proven = False
    scheduler_ahead_count: int | None = None
    if scheduler_sha is not None:
        pin_object = _safe_local_git(
            runner,
            (
                "git",
                "-C",
                str(root),
                "cat-file",
                "-e",
                f"{intended.hf_main_sha}^{{commit}}",
            ),
        )
        if pin_object is not None and pin_object.returncode == 0:
            ancestry = _safe_local_git(
                runner,
                (
                    "git",
                    "-C",
                    str(root),
                    "merge-base",
                    "--is-ancestor",
                    intended.hf_main_sha,
                    scheduler_sha,
                ),
            )
            ancestor_proven = ancestry is not None and ancestry.returncode == 0
            if ancestor_proven:
                count_result = _safe_local_git(
                    runner,
                    (
                        "git",
                        "-C",
                        str(root),
                        "rev-list",
                        "--count",
                        f"{intended.hf_main_sha}..{scheduler_sha}",
                    ),
                )
                if count_result is not None:
                    count_text = count_result.stdout.decode(
                        "ascii", errors="ignore"
                    ).strip()
                    if count_result.returncode == 0 and count_text.isdigit():
                        scheduler_ahead_count = int(count_text)

    if not deployment_delta_present:
        advisory_status = "NONE"
    elif ancestor_proven:
        advisory_status = "SCHEDULER_AHEAD_OF_PIN"
    else:
        advisory_status = "SCHEDULER_DIVERGENT_FROM_PIN"
    return {
        "deployment_delta_present": deployment_delta_present,
        "scheduler_head_sha": scheduler_sha,
        "scheduler_ahead_count": scheduler_ahead_count,
        "deployment_delta_paths": delta_paths,
        "advisory_status": advisory_status,
    }


def _safe_local_git(
    runner: GitRunner, args: Sequence[str]
) -> GitCommandResult | None:
    try:
        return runner(args, LOCAL_GIT_TIMEOUT_SECONDS)
    except (OSError, ProbeTransportError, subprocess.SubprocessError):
        return None


def _local_git_sha(runner: GitRunner, args: Sequence[str]) -> str | None:
    result = _safe_local_git(runner, args)
    if result is None or result.returncode != 0:
        return None
    return _normalized_sha(result.stdout.decode("ascii", errors="ignore").strip())


def _normalized_sha(value: str | None) -> str | None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", value):
        return None
    return value.lower()


def validate_summary(summary: Mapping[str, Any]) -> None:
    """Enforce the exact bounded output surface and advisory type contract."""

    if set(summary) != ALLOWED_SUMMARY_FIELDS:
        raise ValueError("Integrity summary contains an undeclared field.")
    if summary.get("final_classification") not in ALL_CLASSIFICATIONS:
        raise ValueError("Integrity summary classification is invalid.")
    if summary.get("exit_code") not in {0, 1}:
        raise ValueError("Integrity summary exit code is invalid.")
    if not isinstance(summary.get("pinned_hf_main_sha"), str) or not isinstance(
        summary.get("pin_schema_version"), str
    ):
        raise ValueError("Integrity summary pin identity is invalid.")
    if summary["final_classification"] != "PIN_MISSING" and (
        not re.fullmatch(r"[0-9a-f]{40}", summary["pinned_hf_main_sha"])
        or summary["pin_schema_version"] != PIN_SCHEMA_VERSION
    ):
        raise ValueError("Integrity summary pin identity is invalid.")
    if not isinstance(summary.get("deployment_delta_present"), bool):
        raise ValueError("Integrity summary deployment delta is invalid.")
    scheduler_sha = summary.get("scheduler_head_sha")
    if scheduler_sha is not None and (
        not isinstance(scheduler_sha, str)
        or re.fullmatch(r"[0-9a-f]{40}", scheduler_sha) is None
    ):
        raise ValueError("Integrity summary scheduler SHA is invalid.")
    ahead_count = summary.get("scheduler_ahead_count")
    if ahead_count is not None and (
        not isinstance(ahead_count, int)
        or isinstance(ahead_count, bool)
        or ahead_count < 0
    ):
        raise ValueError("Integrity summary scheduler count is invalid.")
    delta_paths = summary.get("deployment_delta_paths")
    if (
        not isinstance(delta_paths, list)
        or any(not isinstance(path, str) for path in delta_paths)
        or delta_paths != sorted(set(delta_paths))
        or not set(delta_paths).issubset(CRITICAL_SOURCE_PATHS)
    ):
        raise ValueError("Integrity summary deployment paths are invalid.")
    advisory_status = summary.get("advisory_status")
    if advisory_status not in ADVISORY_STATUSES:
        raise ValueError("Integrity summary advisory is invalid.")
    if summary["final_classification"] == "HEALTHY" and advisory_status == (
        "NOT_EVALUATED"
    ):
        raise ValueError("Integrity summary advisory was not evaluated.")
    if summary["final_classification"] != "HEALTHY" and (
        advisory_status != "NOT_EVALUATED"
        or summary["deployment_delta_present"]
        or delta_paths
        or ahead_count is not None
    ):
        raise ValueError("Integrity summary advisory affected Q1.")


def _round_signature(round_evidence: RoundEvidence) -> str:
    source = round_evidence.source
    live = round_evidence.live
    evidence = {
        "hf_main_sha": source.hf_main_sha,
        "source_available": source.available,
        "critical_source_match": source.critical_source_match,
        "missing_path_names": source.missing_path_names,
        "mismatched_path_names": source.mismatched_path_names,
        "contract_missing": source.contract_missing,
        "http_statuses": live.http_statuses,
        "root_reachable": live.root_reachable,
        "transport_unavailable": live.transport_unavailable,
        "live_contract_missing": live.contract_missing,
        "schema_version": live.schema_version,
        "release_id": live.release_id,
        "source_milestone": live.source_milestone,
        "fingerprint": live.fingerprint,
        "live_asset_tokens": live.live_asset_tokens,
        "frontend_asset_match": live.frontend_asset_match,
        "runtime_stage": live.runtime_stage,
    }
    return json.dumps(evidence, sort_keys=True, separators=(",", ":"))


def _run_git(args: Sequence[str], timeout: float) -> GitCommandResult:
    try:
        completed = subprocess.run(
            list(args),
            check=False,
            capture_output=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProbeTransportError("Public Git read failed.") from exc
    return GitCommandResult(returncode=completed.returncode, stdout=completed.stdout)


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Probe timestamp must be timezone-aware.")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing intended {name}.")
    return value


def _optional_text(value: Any) -> str | None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or len(value) > 256
        or not value.isprintable()
        or any(
            marker in value.casefold()
            for marker in (
                "authorization",
                "bearer ",
                "cookie",
                "credential",
                "password",
                "secret",
                "api-key",
                "api_key",
                "private key",
            )
        )
    ):
        return None
    return value


def write_step_summary(summary: dict[str, Any]) -> None:
    path = os.getenv("GITHUB_STEP_SUMMARY")
    if not path:
        return
    lines = [
        "## UCPE Runtime Source/Serving Integrity",
        "",
        f"- Final classification: `{summary['final_classification']}`",
        f"- Intended release: `{summary['intended_release_id']}`",
        f"- Live release: `{summary['live_release_id'] or 'unavailable'}`",
        f"- Critical source match: `{summary['critical_source_match']}`",
        f"- Frontend asset match: `{summary['frontend_asset_match']}`",
        f"- Per-round states: `{', '.join(summary['per_round_classifications'])}`",
        f"- Deployment advisory: `{summary['advisory_status']}`",
        f"- Deployment delta present: `{summary['deployment_delta_present']}`",
        f"- Deployment delta path count: `{len(summary['deployment_delta_paths'])}`",
    ]
    try:
        with Path(path).open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    except OSError:
        return


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check UCPE runtime source integrity.")
    parser.add_argument("--checkout-root", type=Path, default=Path.cwd())
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    summary = run_guard(args.checkout_root)
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    write_step_summary(summary)
    return int(summary["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
