from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from scripts import source_integrity_guard as guard

ROOT = Path(__file__).resolve().parents[2]
REMOTE_SHA = "d" * 40


def _intended() -> guard.IntendedContract:
    return guard.load_intended_contract(ROOT)


def _healthy_source(**overrides) -> guard.SourceEvidence:
    values = {
        "available": True,
        "hf_main_sha": REMOTE_SHA,
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
    source: guard.SourceEvidence | None = None,
    live: guard.LiveEvidence | None = None,
) -> guard.RoundEvidence:
    return guard.RoundEvidence(
        timestamp="2026-06-22T00:00:00Z",
        source=source or _healthy_source(),
        live=live or _healthy_live(),
        classification=classification,
    )


def _build_info_body(intended: guard.IntendedContract, **overrides) -> bytes:
    payload = {
        "schema_version": guard.EXPECTED_SCHEMA_VERSION,
        "release_id": intended.release_id,
        "release_label": "Fixture release label",
        "environment": "HF_PRODUCTION",
        "source_milestone": intended.source_milestone,
        "fingerprint": intended.fingerprint,
    }
    payload.update(overrides)
    return json.dumps(payload).encode()


def _healthy_http_get(
    intended: guard.IntendedContract,
    *,
    build_body: bytes | None = None,
    app_body: bytes | None = None,
    styles_body: bytes | None = None,
    build_status: int = 200,
):
    bodies = {
        "/": (ROOT / "frontend/index.html").read_bytes(),
        "/v1/build-info": build_body or _build_info_body(intended),
        "/app.js": app_body or (ROOT / "frontend/app.js").read_bytes(),
        "/styles.css": styles_body or (ROOT / "frontend/styles.css").read_bytes(),
    }

    def get(url: str, timeout: float) -> guard.HttpResponse:
        assert timeout == guard.HTTP_TIMEOUT_SECONDS
        path = urlsplit(url).path
        status = build_status if path == "/v1/build-info" else 200
        return guard.HttpResponse(status=status, body=bodies[path])

    return get


def test_intended_identity_is_read_without_importing_runtime() -> None:
    intended = _intended()

    assert intended.release_id == "UCPE-W4D3-OPS-COHORT-20260622-A"
    assert intended.source_milestone == "wave-4d3-ops-prediction-origin"
    assert intended.fingerprint == "UCPE LIVE BUILD · W4D3-OPS-COHORT-20260622-A"
    assert intended.asset_tokens == {
        "styles_css": "w4c1-ka1-20260621-a",
        "app_js": "w4c1-ka1-20260621-a",
    }
    assert intended.fingerprint_marker is True


def test_live_probe_all_evidence_healthy_and_stage_anomaly_is_soft() -> None:
    intended = _intended()
    live = guard.probe_live_runtime(
        ROOT,
        intended,
        http_get=_healthy_http_get(intended),
    )
    source = _healthy_source()

    assert live.frontend_asset_match is True
    assert guard.classify_round(intended, source, live) == "HEALTHY"
    anomaly = replace(live, runtime_stage="RUNNING_APP_STARTING")
    assert (
        guard.classify_round(intended, source, anomaly)
        == "HEALTHY_WITH_METADATA_ANOMALY"
    )


def test_one_transient_mismatch_is_transitioning_and_non_failing() -> None:
    intended = _intended()
    stale = _healthy_live(intended, release_id="UCPE-FIXTURE-DIFFERENT")
    rounds = [
        _round("STALE_RUNTIME", live=stale),
        _round("HEALTHY"),
        _round("HEALTHY"),
    ]

    summary = guard.summarize_rounds(intended, rounds)

    assert summary["final_classification"] == "TRANSITIONING"
    assert summary["exit_code"] == 0


@pytest.mark.parametrize(
    ("classification", "source", "live"),
    [
        (
            "STALE_RUNTIME",
            _healthy_source(),
            _healthy_live(release_id="UCPE-FIXTURE-DIFFERENT"),
        ),
        (
            "STALE_FRONTEND",
            _healthy_source(),
            _healthy_live(frontend_asset_match=False),
        ),
        (
            "SOURCE_DIVERGENCE",
            _healthy_source(
                critical_source_match=False,
                mismatched_path_names=("Dockerfile",),
            ),
            _healthy_live(),
        ),
        (
            "CONTRACT_MISSING",
            _healthy_source(),
            _healthy_live(
                http_statuses={
                    "root": 200,
                    "build_info": 404,
                    "app_js": 200,
                    "styles_css": 200,
                },
                contract_missing=True,
                schema_version=None,
                release_id=None,
                source_milestone=None,
                fingerprint=None,
            ),
        ),
    ],
)
def test_three_identical_divergence_rounds_fail(
    classification: str,
    source: guard.SourceEvidence,
    live: guard.LiveEvidence,
) -> None:
    intended = _intended()
    rounds = [_round(classification, source=source, live=live) for _ in range(3)]

    summary = guard.summarize_rounds(intended, rounds)

    assert summary["final_classification"] == classification
    assert summary["exit_code"] == 1


def test_evidence_change_with_same_divergence_class_is_transitioning() -> None:
    intended = _intended()
    first = _healthy_live(intended, release_id="UCPE-FIXTURE-A")
    second = _healthy_live(intended, release_id="UCPE-FIXTURE-B")
    rounds = [
        _round("STALE_RUNTIME", live=first),
        _round("STALE_RUNTIME", live=second),
        _round("STALE_RUNTIME", live=second),
    ]

    summary = guard.summarize_rounds(intended, rounds)

    assert summary["final_classification"] == "TRANSITIONING"
    assert summary["exit_code"] == 0


def test_root_200_build_info_404_is_contract_missing() -> None:
    intended = _intended()
    live = guard.probe_live_runtime(
        ROOT,
        intended,
        http_get=_healthy_http_get(intended, build_status=404),
    )

    assert live.root_reachable is True
    assert live.http_statuses["build_info"] == 404
    assert live.contract_missing is True
    assert guard.classify_round(intended, _healthy_source(), live) == "CONTRACT_MISSING"


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
def test_malformed_or_missing_build_contract_is_contract_missing(body: bytes) -> None:
    intended = _intended()
    live = guard.probe_live_runtime(
        ROOT,
        intended,
        http_get=_healthy_http_get(intended, build_body=body),
    )

    assert live.contract_missing is True
    assert guard.classify_round(intended, _healthy_source(), live) == "CONTRACT_MISSING"


def test_timeout_dns_and_partial_probe_failure_are_non_failing_unavailable() -> None:
    intended = _intended()
    calls = 0

    def unavailable(url: str, timeout: float) -> guard.HttpResponse:
        nonlocal calls
        calls += 1
        raise TimeoutError

    live = guard.probe_live_runtime(ROOT, intended, http_get=unavailable)
    assert calls == 4 * guard.HTTP_MAX_ATTEMPTS
    assert guard.classify_round(intended, _healthy_source(), live) == "PROBE_UNAVAILABLE"

    healthy = _healthy_http_get(intended)

    def partial(url: str, timeout: float) -> guard.HttpResponse:
        if urlsplit(url).path == "/styles.css":
            raise OSError
        return healthy(url, timeout)

    partial_live = guard.probe_live_runtime(ROOT, intended, http_get=partial)
    rounds = [_round("PROBE_UNAVAILABLE", live=partial_live) for _ in range(3)]
    summary = guard.summarize_rounds(intended, rounds)
    assert summary["final_classification"] == "PROBE_UNAVAILABLE"
    assert summary["exit_code"] == 0


def test_live_asset_hash_mismatch_is_stale_frontend() -> None:
    intended = _intended()
    live = guard.probe_live_runtime(
        ROOT,
        intended,
        http_get=_healthy_http_get(intended, app_body=b"fixture mismatch"),
    )

    assert live.frontend_asset_match is False
    assert guard.classify_round(intended, _healthy_source(), live) == "STALE_FRONTEND"


class _FixtureGitRunner:
    def __init__(self, remote_files: dict[str, bytes]) -> None:
        self.remote_files = remote_files
        self.calls: list[tuple[str, ...]] = []

    def __call__(
        self, args: tuple[str, ...] | list[str], timeout: float
    ) -> guard.GitCommandResult:
        call = tuple(args)
        self.calls.append(call)
        assert 0 < timeout <= guard.GIT_TIMEOUT_SECONDS
        if "ls-remote" in call:
            return guard.GitCommandResult(0, f"{REMOTE_SHA}\trefs/heads/main\n".encode())
        if "show" in call:
            path = call[-1].split(":", 1)[1]
            if path not in self.remote_files:
                return guard.GitCommandResult(128, b"")
            return guard.GitCommandResult(0, self.remote_files[path])
        return guard.GitCommandResult(0, b"")


def _critical_files() -> dict[str, bytes]:
    return {path: (ROOT / path).read_bytes() for path in guard.CRITICAL_SOURCE_PATHS}


def test_remote_sha_difference_is_not_divergence_when_critical_blobs_match() -> None:
    runner = _FixtureGitRunner(_critical_files())
    source = guard.verify_hf_source(ROOT, git_runner=runner)

    assert source.hf_main_sha == REMOTE_SHA
    assert source.critical_source_match is True
    assert source.mismatched_path_names == ()
    assert guard.classify_round(_intended(), source, _healthy_live()) == "HEALTHY"
    fetch_call = next(call for call in runner.calls if "fetch" in call)
    assert REMOTE_SHA in fetch_call
    shown = {call[-1].split(":", 1)[1] for call in runner.calls if "show" in call}
    assert shown == set(guard.CRITICAL_SOURCE_PATHS)


def test_remote_critical_path_missing_and_contract_path_missing_are_distinct() -> None:
    non_contract_files = _critical_files()
    non_contract_files.pop("Dockerfile")
    source = guard.verify_hf_source(
        ROOT, git_runner=_FixtureGitRunner(non_contract_files)
    )
    assert source.critical_source_match is False
    assert source.contract_missing is False
    assert guard.classify_round(_intended(), source, _healthy_live()) == (
        "SOURCE_DIVERGENCE"
    )

    contract_files = _critical_files()
    contract_files.pop("schemas/build_info.schema.json")
    contract_source = guard.verify_hf_source(
        ROOT, git_runner=_FixtureGitRunner(contract_files)
    )
    assert contract_source.contract_missing is True
    assert guard.classify_round(_intended(), contract_source, _healthy_live()) == (
        "CONTRACT_MISSING"
    )


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


@pytest.mark.parametrize(
    ("classification", "exit_code"),
    [
        ("HEALTHY", 0),
        ("HEALTHY_WITH_METADATA_ANOMALY", 0),
        ("PROBE_UNAVAILABLE", 0),
        ("STALE_RUNTIME", 1),
        ("STALE_FRONTEND", 1),
        ("SOURCE_DIVERGENCE", 1),
        ("CONTRACT_MISSING", 1),
    ],
)
def test_exit_code_matrix(classification: str, exit_code: int) -> None:
    rounds = [_round(classification) for _ in range(3)]
    summary = guard.summarize_rounds(_intended(), rounds)
    assert summary["final_classification"] == classification
    assert summary["exit_code"] == exit_code


def test_guard_runs_three_rounds_with_injected_sleep_and_allowlisted_output() -> None:
    sleeps: list[float] = []
    timestamps = iter(
        [
            datetime(2026, 6, 22, 0, 0, 0, tzinfo=UTC),
            datetime(2026, 6, 22, 0, 0, 20, tzinfo=UTC),
            datetime(2026, 6, 22, 0, 0, 40, tzinfo=UTC),
        ]
    )
    calls: list[int] = []

    def round_probe(index: int, intended: guard.IntendedContract):
        calls.append(index)
        return _healthy_source(), _healthy_live(intended)

    summary = guard.run_guard(
        ROOT,
        sleep=sleeps.append,
        utc_now=lambda: next(timestamps),
        round_probe=round_probe,
    )

    assert calls == [0, 1, 2]
    assert sleeps == [guard.ROUND_SPACING_SECONDS, guard.ROUND_SPACING_SECONDS]
    assert set(summary) == guard.ALLOWED_SUMMARY_FIELDS
    assert summary["final_classification"] == "HEALTHY"
    assert summary["exit_code"] == 0


def test_stdout_and_step_summary_do_not_leak_raw_bodies_or_extra_fields(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    intended = _intended()
    raw_marker = "fixture-raw-response-marker"
    http_get = _healthy_http_get(
        intended,
        build_body=_build_info_body(intended, debug=raw_marker),
    )
    live = guard.probe_live_runtime(ROOT, intended, http_get=http_get)
    rounds = [_round("HEALTHY", live=live) for _ in range(3)]
    summary = guard.summarize_rounds(intended, rounds)
    assert raw_marker not in json.dumps(summary)

    monkeypatch.setattr(guard, "run_guard", lambda checkout_root: summary)
    step_summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(step_summary))
    assert guard.main(["--checkout-root", str(ROOT)]) == 0
    output = capsys.readouterr().out
    parsed = json.loads(output)
    assert set(parsed) == guard.ALLOWED_SUMMARY_FIELDS
    assert raw_marker not in output
    assert raw_marker not in step_summary.read_text()


def test_workflow_is_scheduled_read_only_unsecreted_and_uses_current_majors() -> None:
    workflow = (ROOT / ".github/workflows/source-integrity-guard.yml").read_text()

    for required in (
        'cron: "27 */2 * * *"',
        "workflow_dispatch: {}",
        "contents: read",
        "group: source-integrity-guard",
        "cancel-in-progress: false",
        "timeout-minutes: 10",
        "actions/checkout@v4",
        "actions/setup-python@v5",
        'python-version: "3.11"',
        "python scripts/source_integrity_guard.py",
    ):
        assert required in workflow
    assert "secrets." not in workflow
    assert "actions/checkout@v7" not in workflow
    assert "actions/setup-python@v6" not in workflow


def test_declared_worst_case_budget_fits_workflow_timeout() -> None:
    per_round_seconds = guard.GIT_TIMEOUT_SECONDS + (
        4 * guard.HTTP_MAX_ATTEMPTS * guard.HTTP_TIMEOUT_SECONDS
    )
    total_seconds = (
        guard.PROBE_ROUNDS * per_round_seconds
        + (guard.PROBE_ROUNDS - 1) * guard.ROUND_SPACING_SECONDS
    )

    assert per_round_seconds == 150
    assert total_seconds == 490
    assert total_seconds < 10 * 60
