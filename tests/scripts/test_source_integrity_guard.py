from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from jsonschema import Draft202012Validator

from scripts import source_integrity_guard as guard

ROOT = Path(__file__).resolve().parents[2]
PIN_SHA = "e9d549c59f159222e763182cf0aa02564c1ed67c"
SCHEDULER_SHA = "c" * 40
DRIFT_SHA = "d" * 40
# Guarded source files that currently differ between the deployed pin and this tree.
# Empty while GitHub and the deployed Space agree. It goes non-empty whenever a guarded
# change is merged but not yet deployed, and is emptied again once the deploy lands and
# ops/hf_runtime_baseline.json is re-pinned. The frontend entries are the pending
# login-failure UI awaiting a deploy; analysis_service.py stays, because main carries
# section-5A code that the deployed candidate deliberately does not.
CURRENT_DELTA_PATHS = [
    "frontend/app.js",
    "frontend/index.html",
    "frontend/styles.css",
    "src/crypto_probability_engine/api/analysis_service.py",
]

# The deployed frontend comes from the pinned HF commit, not this working tree, so the
# fake Space must not read frontend/ from the checkout.
_DEPLOYED_APP_JS = b"// deployed app.js stand-in\n"
_DEPLOYED_STYLES_CSS = b"/* deployed styles.css stand-in */\n"


def _manifest() -> dict:
    return json.loads((ROOT / guard.PIN_MANIFEST_RELATIVE_PATH).read_text())


def _intended() -> guard.IntendedContract:
    return guard.load_intended_contract(ROOT)


def _deployed_intended(
    intended: guard.IntendedContract | None = None,
) -> guard.IntendedContract:
    intended = intended or _intended()
    digests = dict(intended.critical_source_digests)
    digests.update(
        {
            "frontend/app.js": hashlib.sha256(_DEPLOYED_APP_JS).hexdigest(),
            "frontend/styles.css": hashlib.sha256(_DEPLOYED_STYLES_CSS).hexdigest(),
        }
    )
    return replace(intended, critical_source_digests=digests)


def _healthy_source(
    intended: guard.IntendedContract | None = None,
    **overrides,
) -> guard.SourceEvidence:
    intended = intended or _intended()
    values = {
        "available": True,
        "hf_main_sha": intended.hf_main_sha,
        "critical_source_match": True,
        "missing_path_names": (),
        "mismatched_path_names": (),
        "contract_missing": False,
    }
    values.update(overrides)
    return guard.SourceEvidence(**values)


def _healthy_live(
    intended: guard.IntendedContract | None = None,
    **overrides,
) -> guard.LiveEvidence:
    intended = intended or _intended()
    values = {
        "http_statuses": {
            "root": 200,
            "build_info": 200,
            "app_js": 200,
            "styles_css": 200,
        },
        "root_reachable": True,
        "transport_unavailable": False,
        "contract_missing": False,
        "schema_version": guard.EXPECTED_SCHEMA_VERSION,
        "release_id": intended.release_id,
        "source_milestone": intended.source_milestone,
        "fingerprint": intended.fingerprint,
        "live_asset_tokens": intended.asset_tokens,
        "frontend_asset_match": True,
        "runtime_stage": "RUNNING",
    }
    values.update(overrides)
    return guard.LiveEvidence(**values)


def _round(
    classification: str,
    *,
    intended: guard.IntendedContract | None = None,
    source: guard.SourceEvidence | None = None,
    live: guard.LiveEvidence | None = None,
) -> guard.RoundEvidence:
    intended = intended or _intended()
    return guard.RoundEvidence(
        timestamp="2026-06-22T00:00:00Z",
        source=source or _healthy_source(intended),
        live=live or _healthy_live(intended),
        classification=classification,
    )


def _build_info_body(intended: guard.IntendedContract, **overrides) -> bytes:
    payload = {
        "schema_version": guard.EXPECTED_SCHEMA_VERSION,
        "release_id": intended.release_id,
        "release_label": intended.release_label,
        "environment": intended.environment,
        "source_milestone": intended.source_milestone,
        "fingerprint": intended.fingerprint,
    }
    payload.update(overrides)
    return json.dumps(payload).encode()


def _root_body(
    intended: guard.IntendedContract,
    *,
    app_token: str | None = None,
    styles_token: str | None = None,
) -> bytes:
    app_token = app_token or intended.asset_tokens["app_js"]
    styles_token = styles_token or intended.asset_tokens["styles_css"]
    return (
        '<link rel="stylesheet" href="/styles.css?v='
        f'{styles_token}"><span data-build-fingerprint></span>'
        f'<script src="/app.js?v={app_token}"></script>'
    ).encode()


def _healthy_http_get(
    intended: guard.IntendedContract,
    *,
    build_body: bytes | None = None,
    root_body: bytes | None = None,
    app_body: bytes | None = None,
    styles_body: bytes | None = None,
    build_status: int = 200,
):
    bodies = {
        "/": root_body or _root_body(intended),
        "/v1/build-info": build_body or _build_info_body(intended),
        "/app.js": app_body or _DEPLOYED_APP_JS,
        "/styles.css": styles_body or _DEPLOYED_STYLES_CSS,
    }

    def get(url: str, timeout: float) -> guard.HttpResponse:
        assert timeout == guard.HTTP_TIMEOUT_SECONDS
        path = urlsplit(url).path
        status = build_status if path == "/v1/build-info" else 200
        return guard.HttpResponse(status=status, body=bodies[path])

    return get


def _fixture_checkout(tmp_path: Path) -> tuple[Path, guard.IntendedContract]:
    digests: dict[str, str] = {}
    for relative_path in guard.CRITICAL_SOURCE_PATHS:
        body = f"pinned fixture: {relative_path}\n".encode()
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        digests[relative_path] = hashlib.sha256(body).hexdigest()
    return tmp_path, replace(_intended(), critical_source_digests=digests)


class _RemoteGitRunner:
    def __init__(
        self,
        remote_files: dict[str, bytes],
        *,
        remote_sha: str = PIN_SHA,
    ) -> None:
        self.remote_files = remote_files
        self.remote_sha = remote_sha
        self.calls: list[tuple[str, ...]] = []

    def __call__(
        self, args: tuple[str, ...] | list[str], timeout: float
    ) -> guard.GitCommandResult:
        call = tuple(args)
        self.calls.append(call)
        assert 0 < timeout <= guard.GIT_TIMEOUT_SECONDS
        if "ls-remote" in call:
            return guard.GitCommandResult(
                0, f"{self.remote_sha}\trefs/heads/main\n".encode()
            )
        if "show" in call:
            path = call[-1].split(":", 1)[1]
            if path not in self.remote_files:
                return guard.GitCommandResult(128, b"")
            return guard.GitCommandResult(0, self.remote_files[path])
        return guard.GitCommandResult(0, b"")


class _LocalGitRunner:
    def __init__(
        self,
        *,
        scheduler_sha: str = SCHEDULER_SHA,
        pin_available: bool = True,
        ancestor: bool = True,
        ahead_count: int = 7,
    ) -> None:
        self.scheduler_sha = scheduler_sha
        self.pin_available = pin_available
        self.ancestor = ancestor
        self.ahead_count = ahead_count
        self.calls: list[tuple[str, ...]] = []

    def __call__(
        self, args: tuple[str, ...] | list[str], timeout: float
    ) -> guard.GitCommandResult:
        call = tuple(args)
        self.calls.append(call)
        assert timeout == guard.LOCAL_GIT_TIMEOUT_SECONDS
        assert not {"fetch", "pull", "push", "ls-remote"}.intersection(call)
        assert not any("http://" in arg or "https://" in arg for arg in call)
        if "rev-parse" in call:
            return guard.GitCommandResult(0, f"{self.scheduler_sha}\n".encode())
        if "cat-file" in call:
            return guard.GitCommandResult(0 if self.pin_available else 128, b"")
        if "merge-base" in call:
            return guard.GitCommandResult(0 if self.ancestor else 1, b"")
        if "rev-list" in call:
            return guard.GitCommandResult(0, f"{self.ahead_count}\n".encode())
        raise AssertionError("Unexpected local Git command")


def _assert_no_network_git(calls: list[tuple[str, ...]]) -> None:
    for call in calls:
        assert not {"fetch", "pull", "push", "ls-remote"}.intersection(call)
        assert not any("http://" in arg or "https://" in arg for arg in call)


def _pin_root(tmp_path: Path) -> Path:
    manifest_path = tmp_path / guard.PIN_MANIFEST_RELATIVE_PATH
    schema_path = tmp_path / guard.PIN_SCHEMA_RELATIVE_PATH
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes((ROOT / guard.PIN_MANIFEST_RELATIVE_PATH).read_bytes())
    schema_path.write_bytes((ROOT / guard.PIN_SCHEMA_RELATIVE_PATH).read_bytes())
    return tmp_path


def test_manifest_identity_is_loaded_without_checkout_runtime_source() -> None:
    intended = _intended()

    assert intended.schema_version == guard.PIN_SCHEMA_VERSION
    assert intended.hf_main_sha == PIN_SHA
    assert intended.release_id == "UCPE-W4D3-OPS-2A0-20260622-A"
    assert intended.release_label == "Wave 4D.3-Ops Cadence Runtime Primitives"
    assert intended.environment == "HF_PRODUCTION"
    assert intended.source_milestone == "wave-4d3-ops-2a0-cadence-runtime"
    assert intended.fingerprint == "UCPE LIVE BUILD · W4D3-OPS-2A0-20260622-A"
    assert intended.asset_tokens == {
        "app_js": "w4c1-ka1-20260823-a",
        "styles_css": "w4c1-ka1-20260621-a",
    }
    assert set(intended.critical_source_digests) == set(guard.CRITICAL_SOURCE_PATHS)


def test_healthy_q1_and_no_deployment_delta(tmp_path: Path) -> None:
    checkout, intended = _fixture_checkout(tmp_path)
    runner = _LocalGitRunner(scheduler_sha=intended.hf_main_sha, ahead_count=0)
    rounds = [_round("HEALTHY", intended=intended) for _ in range(3)]

    summary = guard.summarize_rounds(
        intended,
        rounds,
        checkout_root=checkout,
        local_git_runner=runner,
        environ={"GITHUB_SHA": intended.hf_main_sha},
    )

    assert summary["final_classification"] == "HEALTHY"
    assert summary["exit_code"] == 0
    assert summary["advisory_status"] == "NONE"
    assert summary["deployment_delta_present"] is False
    assert summary["deployment_delta_paths"] == []
    assert summary["scheduler_ahead_count"] == 0
    _assert_no_network_git(runner.calls)


def test_current_false_positive_regression_is_healthy_with_scheduler_delta() -> None:
    intended = _intended()
    runner = _LocalGitRunner()
    sleeps: list[float] = []
    timestamps = iter(
        [
            datetime(2026, 6, 22, 0, 0, 0, tzinfo=UTC),
            datetime(2026, 6, 22, 0, 0, 20, tzinfo=UTC),
            datetime(2026, 6, 22, 0, 0, 40, tzinfo=UTC),
        ]
    )
    probe_calls: list[int] = []

    def round_probe(index: int, pinned: guard.IntendedContract):
        probe_calls.append(index)
        assert pinned == intended
        return _healthy_source(pinned), _healthy_live(pinned)

    summary = guard.run_guard(
        ROOT,
        sleep=sleeps.append,
        utc_now=lambda: next(timestamps),
        round_probe=round_probe,
        local_git_runner=runner,
        environ={"GITHUB_SHA": SCHEDULER_SHA},
    )

    assert probe_calls == [0, 1, 2]
    assert sleeps == [guard.ROUND_SPACING_SECONDS, guard.ROUND_SPACING_SECONDS]
    assert summary["final_classification"] == "HEALTHY"
    assert summary["exit_code"] == 0
    assert summary["deployment_delta_present"] is True
    assert summary["deployment_delta_paths"] == CURRENT_DELTA_PATHS
    assert summary["scheduler_ahead_count"] == 7
    assert summary["advisory_status"] == "SCHEDULER_AHEAD_OF_PIN"
    _assert_no_network_git(runner.calls)


def test_shallow_checkout_advisory_is_non_failing(tmp_path: Path) -> None:
    checkout, intended = _fixture_checkout(tmp_path)
    changed_path = "src/crypto_probability_engine/api/analysis_service.py"
    (checkout / changed_path).write_bytes(b"scheduler-only change\n")
    runner = _LocalGitRunner(pin_available=False)
    rounds = [_round("HEALTHY", intended=intended) for _ in range(3)]

    summary = guard.summarize_rounds(
        intended,
        rounds,
        checkout_root=checkout,
        local_git_runner=runner,
        environ={"GITHUB_SHA": SCHEDULER_SHA},
    )

    assert summary["final_classification"] == "HEALTHY"
    assert summary["exit_code"] == 0
    assert summary["scheduler_ahead_count"] is None
    assert summary["deployment_delta_paths"] == [changed_path]
    assert summary["advisory_status"] == "SCHEDULER_DIVERGENT_FROM_PIN"
    assert not any("merge-base" in call for call in runner.calls)
    _assert_no_network_git(runner.calls)


def test_advisory_internal_failure_cannot_fail_healthy_q1(tmp_path: Path) -> None:
    checkout, intended = _fixture_checkout(tmp_path)
    rounds = [_round("HEALTHY", intended=intended) for _ in range(3)]

    def broken_local_git(args, timeout):
        raise RuntimeError("local advisory fixture failure")

    summary = guard.summarize_rounds(
        intended,
        rounds,
        checkout_root=checkout,
        local_git_runner=broken_local_git,
        environ={"GITHUB_SHA": SCHEDULER_SHA},
    )

    assert summary["final_classification"] == "HEALTHY"
    assert summary["exit_code"] == 0
    assert summary["advisory_status"] == "SCHEDULER_DIVERGENT_FROM_PIN"
    assert summary["scheduler_ahead_count"] is None


def test_pin_drift_short_circuits_blob_and_live_probes(monkeypatch) -> None:
    intended = _intended()
    runner = _RemoteGitRunner({}, remote_sha=DRIFT_SHA)
    source = guard.verify_hf_source(intended, git_runner=runner)
    assert source.hf_main_sha == DRIFT_SHA
    assert len(runner.calls) == 1
    assert "ls-remote" in runner.calls[0]

    source_calls = 0
    live_calls = 0

    def drift_source(pinned: guard.IntendedContract) -> guard.SourceEvidence:
        nonlocal source_calls
        source_calls += 1
        return _healthy_source(pinned, hf_main_sha=DRIFT_SHA, critical_source_match=False)

    def forbidden_live(pinned: guard.IntendedContract) -> guard.LiveEvidence:
        nonlocal live_calls
        live_calls += 1
        raise AssertionError("Live probe must not run after pin drift")

    monkeypatch.setattr(guard, "verify_hf_source", drift_source)
    monkeypatch.setattr(guard, "probe_live_runtime", forbidden_live)
    summary = guard.run_guard(ROOT, sleep=lambda seconds: None, environ={})

    assert source_calls == guard.PROBE_ROUNDS
    assert live_calls == 0
    assert summary["final_classification"] == "PIN_DRIFT"
    assert summary["exit_code"] == 1
    assert summary["advisory_status"] == "NOT_EVALUATED"


def test_source_divergence_uses_manifest_digests() -> None:
    remote_files = {
        path: f"remote fixture: {path}\n".encode()
        for path in guard.CRITICAL_SOURCE_PATHS
    }
    digests = {
        path: hashlib.sha256(body).hexdigest() for path, body in remote_files.items()
    }
    intended = replace(_intended(), critical_source_digests=digests)
    remote_files["Dockerfile"] = b"different bytes\n"

    source = guard.verify_hf_source(
        intended, git_runner=_RemoteGitRunner(remote_files)
    )
    rounds = [
        _round(
            "SOURCE_DIVERGENCE",
            intended=intended,
            source=source,
            live=_healthy_live(intended),
        )
        for _ in range(3)
    ]
    summary = guard.summarize_rounds(intended, rounds, environ={})

    assert source.mismatched_path_names == ("Dockerfile",)
    assert summary["final_classification"] == "SOURCE_DIVERGENCE"
    assert summary["exit_code"] == 1


def test_all_eleven_remote_critical_blobs_match_manifest_digests() -> None:
    remote_files = {
        path: f"remote fixture: {path}\n".encode()
        for path in guard.CRITICAL_SOURCE_PATHS
    }
    digests = {
        path: hashlib.sha256(body).hexdigest() for path, body in remote_files.items()
    }
    intended = replace(_intended(), critical_source_digests=digests)
    runner = _RemoteGitRunner(remote_files)

    source = guard.verify_hf_source(intended, git_runner=runner)

    assert source.hf_main_sha == intended.hf_main_sha
    assert source.critical_source_match is True
    assert source.missing_path_names == ()
    assert source.mismatched_path_names == ()
    shown = {call[-1].split(":", 1)[1] for call in runner.calls if "show" in call}
    assert shown == set(guard.CRITICAL_SOURCE_PATHS)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("release_id", "UCPE-STALE"),
        ("source_milestone", "stale-milestone"),
        ("fingerprint", "UCPE LIVE BUILD · STALE"),
    ],
)
def test_stale_runtime_identity_fields_fail_after_confirmation(
    field: str, value: str
) -> None:
    intended = _intended()
    live = _healthy_live(intended, **{field: value})
    assert guard.classify_round(intended, _healthy_source(intended), live) == (
        "STALE_RUNTIME"
    )
    rounds = [_round("STALE_RUNTIME", intended=intended, live=live) for _ in range(3)]
    summary = guard.summarize_rounds(intended, rounds, environ={})
    assert summary["exit_code"] == 1


@pytest.mark.parametrize("mismatch", ["asset_token", "app_js", "styles_css"])
def test_stale_frontend_variants_fail_after_confirmation(mismatch: str) -> None:
    intended = _deployed_intended()
    kwargs: dict[str, bytes] = {}
    if mismatch == "asset_token":
        kwargs["root_body"] = _root_body(intended, app_token="stale-token")
    elif mismatch == "app_js":
        kwargs["app_body"] = b"stale app bytes\n"
    else:
        kwargs["styles_body"] = b"stale styles bytes\n"
    live = guard.probe_live_runtime(
        intended,
        http_get=_healthy_http_get(intended, **kwargs),
    )

    assert live.frontend_asset_match is False
    assert guard.classify_round(intended, _healthy_source(intended), live) == (
        "STALE_FRONTEND"
    )
    rounds = [_round("STALE_FRONTEND", intended=intended, live=live) for _ in range(3)]
    summary = guard.summarize_rounds(intended, rounds, environ={})
    assert summary["exit_code"] == 1


@pytest.mark.parametrize(
    "case",
    [
        "manifest_absent",
        "schema_absent",
        "invalid_json",
        "schema_invalid_json",
        "permissive_schema",
        "unsupported_schema_version",
        "missing_required_field",
        "extra_field",
        "missing_digest_key",
        "extra_digest_key",
        "invalid_sha",
        "invalid_digest",
    ],
)
def test_pin_missing_or_invalid_fails_before_any_probe(
    case: str, tmp_path: Path
) -> None:
    root = _pin_root(tmp_path)
    manifest_path = root / guard.PIN_MANIFEST_RELATIVE_PATH
    schema_path = root / guard.PIN_SCHEMA_RELATIVE_PATH
    manifest = json.loads(manifest_path.read_text())

    if case == "manifest_absent":
        manifest_path.unlink()
    elif case == "schema_absent":
        schema_path.unlink()
    elif case == "invalid_json":
        manifest_path.write_text("{invalid-json\n")
    elif case == "schema_invalid_json":
        schema_path.write_text("{invalid-json\n")
    elif case == "permissive_schema":
        schema = json.loads(schema_path.read_text())
        schema["additionalProperties"] = True
        schema_path.write_text(json.dumps(schema))
    elif case == "unsupported_schema_version":
        manifest["schema_version"] = "hf-runtime-baseline.v2"
    elif case == "missing_required_field":
        manifest.pop("release_label")
    elif case == "extra_field":
        manifest["unexpected"] = "value"
    elif case == "missing_digest_key":
        manifest["critical_source_digests"].pop("Dockerfile")
    elif case == "extra_digest_key":
        manifest["critical_source_digests"]["extra.py"] = "a" * 64
    elif case == "invalid_sha":
        manifest["hf_main_sha"] = "A" * 40
    elif case == "invalid_digest":
        manifest["critical_source_digests"]["Dockerfile"] = "z" * 64
    if case not in {"manifest_absent", "schema_absent", "invalid_json"}:
        manifest_path.write_text(json.dumps(manifest, sort_keys=True))

    probes = 0

    def forbidden_probe(index: int, intended: guard.IntendedContract):
        nonlocal probes
        probes += 1
        raise AssertionError("A pin failure must not start a probe round")

    summary = guard.run_guard(root, round_probe=forbidden_probe, environ={})

    assert probes == 0
    assert summary["final_classification"] == "PIN_MISSING"
    assert summary["exit_code"] == 1
    assert summary["http_statuses"] == []
    assert summary["probe_timestamps"] == []
    assert summary["per_round_classifications"] == []
    assert summary["advisory_status"] == "NOT_EVALUATED"


def test_contract_missing_behavior_is_preserved() -> None:
    intended = _deployed_intended()
    live = guard.probe_live_runtime(
        intended,
        http_get=_healthy_http_get(intended, build_status=404),
    )
    assert live.contract_missing is True
    assert guard.classify_round(intended, _healthy_source(intended), live) == (
        "CONTRACT_MISSING"
    )
    rounds = [_round("CONTRACT_MISSING", intended=intended, live=live) for _ in range(3)]
    summary = guard.summarize_rounds(intended, rounds, environ={})
    assert summary["exit_code"] == 1


@pytest.mark.parametrize(
    "body",
    [
        b"not-json",
        json.dumps({"schema_version": "build-info.v1"}).encode(),
        json.dumps(
            {
                "schema_version": "build-info.v2",
                "release_id": "UCPE-FIXTURE",
                "release_label": "Fixture",
                "environment": "HF_PRODUCTION",
                "source_milestone": "fixture",
                "fingerprint": "fixture",
            }
        ).encode(),
    ],
)
def test_malformed_live_build_contract_remains_contract_missing(body: bytes) -> None:
    intended = _deployed_intended()
    live = guard.probe_live_runtime(
        intended,
        http_get=_healthy_http_get(intended, build_body=body),
    )
    assert live.contract_missing is True
    assert guard.classify_round(intended, _healthy_source(intended), live) == (
        "CONTRACT_MISSING"
    )


def test_probe_unavailable_is_non_failing_and_skips_advisory() -> None:
    intended = _intended()
    calls = 0

    def unavailable(url: str, timeout: float) -> guard.HttpResponse:
        nonlocal calls
        calls += 1
        raise TimeoutError

    live = guard.probe_live_runtime(intended, http_get=unavailable)
    assert calls == 4 * guard.HTTP_MAX_ATTEMPTS
    rounds = [_round("PROBE_UNAVAILABLE", intended=intended, live=live) for _ in range(3)]
    summary = guard.summarize_rounds(
        intended,
        rounds,
        checkout_root=ROOT,
        local_git_runner=_LocalGitRunner(),
        environ={"GITHUB_SHA": SCHEDULER_SHA},
    )
    assert summary["final_classification"] == "PROBE_UNAVAILABLE"
    assert summary["exit_code"] == 0
    assert summary["advisory_status"] == "NOT_EVALUATED"


def test_mixed_rounds_are_transitioning_and_skip_advisory() -> None:
    intended = _intended()
    stale = _healthy_live(intended, release_id="UCPE-STALE")
    rounds = [
        _round("STALE_RUNTIME", intended=intended, live=stale),
        _round("HEALTHY", intended=intended),
        _round("HEALTHY", intended=intended),
    ]
    summary = guard.summarize_rounds(intended, rounds, environ={})
    assert summary["final_classification"] == "TRANSITIONING"
    assert summary["exit_code"] == 0
    assert summary["advisory_status"] == "NOT_EVALUATED"


def test_evidence_change_with_same_failure_class_is_transitioning() -> None:
    intended = _intended()
    first = _healthy_live(intended, release_id="UCPE-FIXTURE-A")
    second = _healthy_live(intended, release_id="UCPE-FIXTURE-B")
    rounds = [
        _round("STALE_RUNTIME", intended=intended, live=first),
        _round("STALE_RUNTIME", intended=intended, live=second),
        _round("STALE_RUNTIME", intended=intended, live=second),
    ]
    summary = guard.summarize_rounds(intended, rounds, environ={})
    assert summary["final_classification"] == "TRANSITIONING"
    assert summary["exit_code"] == 0


def test_advisory_cannot_rescue_q1_failure(tmp_path: Path) -> None:
    checkout, intended = _fixture_checkout(tmp_path)
    live = _healthy_live(intended, release_id="UCPE-STALE")
    rounds = [_round("STALE_RUNTIME", intended=intended, live=live) for _ in range(3)]
    runner = _LocalGitRunner(scheduler_sha=intended.hf_main_sha, ahead_count=0)

    summary = guard.summarize_rounds(
        intended,
        rounds,
        checkout_root=checkout,
        local_git_runner=runner,
        environ={"GITHUB_SHA": intended.hf_main_sha},
    )

    assert summary["final_classification"] == "STALE_RUNTIME"
    assert summary["exit_code"] == 1
    assert summary["advisory_status"] == "NOT_EVALUATED"
    assert summary["deployment_delta_present"] is False
    assert runner.calls == []


def test_output_allowlist_types_and_enums_are_strict(tmp_path: Path) -> None:
    checkout, intended = _fixture_checkout(tmp_path)
    rounds = [_round("HEALTHY", intended=intended) for _ in range(3)]
    summary = guard.summarize_rounds(
        intended,
        rounds,
        checkout_root=checkout,
        local_git_runner=_LocalGitRunner(
            scheduler_sha=intended.hf_main_sha, ahead_count=0
        ),
        environ={"GITHUB_SHA": intended.hf_main_sha},
    )
    assert set(summary) == guard.ALLOWED_SUMMARY_FIELDS
    assert isinstance(summary["pinned_hf_main_sha"], str)
    assert isinstance(summary["pin_schema_version"], str)
    assert isinstance(summary["deployment_delta_present"], bool)
    assert summary["advisory_status"] in guard.ADVISORY_STATUSES

    undeclared = dict(summary, undeclared="forbidden")
    with pytest.raises(ValueError, match="undeclared"):
        guard.validate_summary(undeclared)
    for key, value in (
        ("deployment_delta_present", 1),
        ("scheduler_head_sha", "not-a-sha"),
        ("scheduler_ahead_count", -1),
        ("deployment_delta_paths", ["protected.txt"]),
        ("advisory_status", "UNKNOWN"),
    ):
        invalid = dict(summary)
        invalid[key] = value
        with pytest.raises(ValueError):
            guard.validate_summary(invalid)


def test_stdout_and_step_summary_are_one_line_bounded_and_sanitized(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    intended = _deployed_intended()
    markers = {
        "debug": "raw-body-marker",
        "authorization": "Bearer secret-credential-marker",
        "cookie": "private-cookie-marker",
        "exception": "ValueError(exception-repr-marker)",
    }
    live = guard.probe_live_runtime(
        intended,
        http_get=_healthy_http_get(
            intended, build_body=_build_info_body(intended, **markers)
        ),
    )
    rounds = [_round("HEALTHY", intended=intended, live=live) for _ in range(3)]
    summary = guard.summarize_rounds(
        intended,
        rounds,
        checkout_root=ROOT,
        local_git_runner=_LocalGitRunner(),
        environ={"GITHUB_SHA": SCHEDULER_SHA},
    )
    serialized = json.dumps(summary)
    assert not any(marker in serialized for marker in markers.values())

    monkeypatch.setattr(guard, "run_guard", lambda checkout_root: summary)
    step_summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(step_summary))
    assert guard.main(["--checkout-root", str(ROOT)]) == 0
    output = capsys.readouterr().out
    assert output.count("\n") == 1
    parsed = json.loads(output)
    assert set(parsed) == guard.ALLOWED_SUMMARY_FIELDS
    combined = output + step_summary.read_text()
    assert "Traceback" not in combined
    assert not any(marker in combined for marker in markers.values())
    assert len(combined) < 16_384


def test_pin_parse_failure_emits_sanitized_single_json_line(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    root = _pin_root(tmp_path)
    raw_marker = "secret-parser-exception-marker"
    (root / guard.PIN_MANIFEST_RELATIVE_PATH).write_text(
        f'{{"secret":"{raw_marker}"'
    )
    step_summary = tmp_path / "step.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(step_summary))

    assert guard.main(["--checkout-root", str(root)]) == 1
    output = capsys.readouterr().out
    assert output.count("\n") == 1
    assert json.loads(output)["final_classification"] == "PIN_MISSING"
    combined = output + step_summary.read_text()
    assert raw_marker not in combined
    assert "JSONDecodeError" not in combined
    assert "Traceback" not in combined


def test_manifest_fidelity_against_unprefixed_pinned_git_objects(
    tmp_path: Path,
) -> None:
    blobs: dict[str, bytes] = {}
    for relative_path in guard.CRITICAL_SOURCE_PATHS:
        spec = f"{PIN_SHA}:{relative_path}"
        exists = subprocess.run(
            ["git", "cat-file", "-e", spec],
            cwd=ROOT,
            check=False,
            capture_output=True,
        )
        if exists.returncode != 0:
            pytest.fail(
                f"pinned Git object unavailable: {spec}. Fetch the pinned objects with "
                f"`git fetch --depth=1 origin {PIN_SHA}` before running this test. The "
                "pinned commit must remain fetchable; if it has been garbage-collected, "
                "the production pin is meaningless."
            )
        prefixed = subprocess.run(
            ["git", "cat-file", "-e", f"{PIN_SHA}:v8-crypto-api-clean/{relative_path}"],
            cwd=ROOT,
            check=False,
            capture_output=True,
        )
        assert prefixed.returncode != 0
        blobs[relative_path] = subprocess.run(
            ["git", "cat-file", "blob", spec],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
        ).stdout

    manifest = _manifest()
    generated = {
        path: hashlib.sha256(body).hexdigest() for path, body in blobs.items()
    }
    assert generated == manifest["critical_source_digests"]

    build_path = tmp_path / "pinned_build_info.py"
    build_path.write_bytes(
        blobs["src/crypto_probability_engine/config/build_info.py"]
    )
    values = guard._read_constant_assignments(build_path)
    index_text = blobs["frontend/index.html"].decode("utf-8")
    assert values["RELEASE_ID"] == manifest["release_id"]
    assert values["RELEASE_LABEL"] == manifest["release_label"]
    assert values["ENVIRONMENT"] == manifest["environment"]
    assert values["SOURCE_MILESTONE"] == manifest["source_milestone"]
    assert values["FINGERPRINT"] == manifest["fingerprint"]
    assert {
        "app_js": guard._extract_asset_token(index_text, "app.js"),
        "styles_css": guard._extract_asset_token(index_text, "styles.css"),
    } == manifest["frontend_asset_tokens"]


def test_committed_manifest_validates_against_committed_schema() -> None:
    manifest = _manifest()
    schema = json.loads((ROOT / guard.PIN_SCHEMA_RELATIVE_PATH).read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    guard._validate_pin_payload(manifest)


def test_manifest_format_is_deterministic_sorted_json() -> None:
    raw = (ROOT / guard.PIN_MANIFEST_RELATIVE_PATH).read_bytes()
    assert raw.endswith(b"\n")
    assert not raw.endswith(b"\n\n")
    expected = json.dumps(
        json.loads(raw),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    assert raw.decode("utf-8") == expected


def test_extra_live_build_info_field_is_tolerated() -> None:
    intended = _deployed_intended()
    live = guard.probe_live_runtime(
        intended,
        http_get=_healthy_http_get(
            intended,
            build_body=_build_info_body(intended, future_optional_field="ignored"),
        ),
    )
    assert live.contract_missing is False
    assert guard.classify_round(intended, _healthy_source(intended), live) == "HEALTHY"


def test_live_stage_anomaly_is_soft_and_advisory_not_evaluated() -> None:
    intended = _intended()
    live = _healthy_live(intended, runtime_stage="RUNNING_APP_STARTING")
    assert guard.classify_round(intended, _healthy_source(intended), live) == (
        "HEALTHY_WITH_METADATA_ANOMALY"
    )
    rounds = [
        _round("HEALTHY_WITH_METADATA_ANOMALY", intended=intended, live=live)
        for _ in range(3)
    ]
    summary = guard.summarize_rounds(intended, rounds, environ={})
    assert summary["exit_code"] == 0
    assert summary["advisory_status"] == "NOT_EVALUATED"


@pytest.mark.parametrize(
    "url",
    [
        f"{guard.SPACE_ORIGIN}/v1/analyze",
        f"{guard.SPACE_ORIGIN}/v1/auth",
        f"{guard.SPACE_ORIGIN}/v1/calibration",
        f"{guard.SPACE_ORIGIN}/v1/watchlist",
        "https://example.invalid/",
        f"http://{guard.SPACE_HOST}/",
        f"{guard.SPACE_ORIGIN}/app.js?v=wrong",
    ],
)
def test_forbidden_urls_are_rejected_before_transport(url: str) -> None:
    called = False

    def transport(request_url: str, timeout: float) -> guard.HttpResponse:
        nonlocal called
        called = True
        return guard.HttpResponse(200, b"")

    with pytest.raises(ValueError):
        guard.public_get(
            "GET",
            url,
            expected_asset_tokens=_intended().asset_tokens,
            http_get=transport,
        )
    assert called is False


def test_non_get_is_rejected_before_transport() -> None:
    with pytest.raises(ValueError):
        guard.public_get(
            "HEAD",
            f"{guard.SPACE_ORIGIN}/",
            expected_asset_tokens=_intended().asset_tokens,
            http_get=lambda url, timeout: guard.HttpResponse(200, b""),
        )


def test_http_response_size_cap_is_enforced_without_network(monkeypatch) -> None:
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self, limit: int) -> bytes:
            assert limit == guard.MAX_BODY_BYTES + 1
            return b"x" * limit

    class Opener:
        def open(self, request, timeout: float):
            assert timeout == guard.HTTP_TIMEOUT_SECONDS
            return Response()

    monkeypatch.setattr(guard.urllib.request, "build_opener", lambda handler: Opener())
    with pytest.raises(guard.ProbeTransportError, match="size limit"):
        guard._urllib_get(f"{guard.SPACE_ORIGIN}/", guard.HTTP_TIMEOUT_SECONDS)


def test_redirects_are_disabled() -> None:
    handler = guard._NoRedirectHandler()
    assert handler.redirect_request(None, None, 302, "Found", {}, "https://example.com") is None


@pytest.mark.parametrize(
    ("classification", "exit_code"),
    [
        ("HEALTHY_WITH_METADATA_ANOMALY", 0),
        ("PROBE_UNAVAILABLE", 0),
        ("PIN_DRIFT", 1),
        ("STALE_RUNTIME", 1),
        ("STALE_FRONTEND", 1),
        ("SOURCE_DIVERGENCE", 1),
        ("CONTRACT_MISSING", 1),
    ],
)
def test_exit_code_matrix(classification: str, exit_code: int) -> None:
    intended = _intended()
    source = (
        _healthy_source(intended, hf_main_sha=DRIFT_SHA, critical_source_match=False)
        if classification == "PIN_DRIFT"
        else _healthy_source(intended)
    )
    rounds = [
        _round(classification, intended=intended, source=source) for _ in range(3)
    ]
    summary = guard.summarize_rounds(intended, rounds, environ={})
    assert summary["final_classification"] == classification
    assert summary["exit_code"] == exit_code


def test_remote_missing_contract_and_non_contract_paths_are_distinct() -> None:
    remote_files = {
        path: f"remote fixture: {path}\n".encode()
        for path in guard.CRITICAL_SOURCE_PATHS
    }
    digests = {
        path: hashlib.sha256(body).hexdigest() for path, body in remote_files.items()
    }
    intended = replace(_intended(), critical_source_digests=digests)

    non_contract = dict(remote_files)
    non_contract.pop("Dockerfile")
    source = guard.verify_hf_source(
        intended, git_runner=_RemoteGitRunner(non_contract)
    )
    assert source.contract_missing is False
    assert guard.classify_round(intended, source, _healthy_live(intended)) == (
        "SOURCE_DIVERGENCE"
    )

    contract = dict(remote_files)
    contract.pop("schemas/build_info.schema.json")
    source = guard.verify_hf_source(intended, git_runner=_RemoteGitRunner(contract))
    assert source.contract_missing is True
    assert guard.classify_round(intended, source, _healthy_live(intended)) == (
        "CONTRACT_MISSING"
    )


def test_workflow_is_scheduled_read_only_unsecreted_and_unchanged() -> None:
    workflow = (ROOT / ".github/workflows/source-integrity-guard.yml").read_text()
    for required in (
        'cron: "27 */2 * * *"',
        "workflow_dispatch: {}",
        "contents: read",
        "group: source-integrity-guard",
        "cancel-in-progress: false",
        "timeout-minutes: 10",
        "actions/checkout@v7",
        "actions/setup-python@v7",
        'python-version: "3.11"',
        "python scripts/source_integrity_guard.py",
    ):
        assert required in workflow
    assert "secrets." not in workflow


def test_declared_worst_case_budget_fits_workflow_timeout() -> None:
    per_round_seconds = guard.GIT_TIMEOUT_SECONDS + (
        4 * guard.HTTP_MAX_ATTEMPTS * guard.HTTP_TIMEOUT_SECONDS
    )
    total_seconds = (
        guard.PROBE_ROUNDS * per_round_seconds
        + (guard.PROBE_ROUNDS - 1) * guard.ROUND_SPACING_SECONDS
    )
    assert guard.PROBE_ROUNDS == 3
    assert guard.ROUND_SPACING_SECONDS == 20
    assert per_round_seconds == 150
    assert total_seconds == 490
    assert total_seconds < 10 * 60
