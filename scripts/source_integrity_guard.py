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
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SPACE_HOST = "beny053-ultimate-crypto-probability-engine.hf.space"
SPACE_ORIGIN = f"https://{SPACE_HOST}"
HF_GIT_URL = "https://huggingface.co/spaces/beny053/ultimate-crypto-probability-engine"
EXPECTED_SCHEMA_VERSION = "build-info.v1"

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
    {"STALE_RUNTIME", "STALE_FRONTEND", "SOURCE_DIVERGENCE", "CONTRACT_MISSING"}
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
    }
)


class ProbeTransportError(RuntimeError):
    """Sanitized transport failure without provider response content."""


@dataclass(frozen=True)
class IntendedContract:
    release_id: str
    source_milestone: str
    fingerprint: str
    asset_tokens: dict[str, str]
    fingerprint_marker: bool


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
    """Read release and frontend identity without importing application modules."""

    build_info_path = checkout_root / "src/crypto_probability_engine/config/build_info.py"
    values = _read_constant_assignments(build_info_path)
    release_id = _required_text(values.get("RELEASE_ID"), "RELEASE_ID")
    source_milestone = _required_text(
        values.get("SOURCE_MILESTONE"), "SOURCE_MILESTONE"
    )
    fingerprint = _required_text(values.get("FINGERPRINT"), "FINGERPRINT")

    index_text = (checkout_root / "frontend/index.html").read_text(encoding="utf-8")
    styles_token = _extract_asset_token(index_text, "styles.css")
    app_token = _extract_asset_token(index_text, "app.js")
    return IntendedContract(
        release_id=release_id,
        source_milestone=source_milestone,
        fingerprint=fingerprint,
        asset_tokens={"styles_css": styles_token, "app_js": app_token},
        fingerprint_marker="data-build-fingerprint" in index_text,
    )


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
    checkout_root: Path,
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
                local_path = checkout_root / relative_path
                if not local_path.is_file():
                    missing.append(relative_path)
                    continue
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
                elif result.stdout != local_path.read_bytes():
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
    checkout_root: Path,
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
        and hashlib.sha256(app.body).digest()
        == hashlib.sha256((checkout_root / "frontend/app.js").read_bytes()).digest()
    )
    styles_match = (
        styles is not None
        and styles.status == 200
        and hashlib.sha256(styles.body).digest()
        == hashlib.sha256((checkout_root / "frontend/styles.css").read_bytes()).digest()
    )
    token_match = live_tokens == intended.asset_tokens
    frontend_asset_match = (
        root_reachable
        and root_marker
        and intended.fingerprint_marker
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
) -> dict[str, Any]:
    """Run three rounds and return one strictly allowlisted summary."""

    intended = load_intended_contract(checkout_root)
    now = utc_now or (lambda: datetime.now(UTC))
    rounds: list[RoundEvidence] = []
    for index in range(PROBE_ROUNDS):
        timestamp = _iso_utc(now())
        if round_probe is None:
            source = verify_hf_source(checkout_root)
            live = probe_live_runtime(checkout_root, intended)
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
    return summarize_rounds(intended, rounds)


def summarize_rounds(
    intended: IntendedContract,
    rounds: Sequence[RoundEvidence],
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
    }
    if set(summary) != ALLOWED_SUMMARY_FIELDS:
        raise ValueError("Integrity summary contains an undeclared field.")
    return summary


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
        or len(value) > 256
        or not value.isprintable()
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
    summary = run_guard(args.checkout_root.resolve())
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    write_step_summary(summary)
    return int(summary["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
