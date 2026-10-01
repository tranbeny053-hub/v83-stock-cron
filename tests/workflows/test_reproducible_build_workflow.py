"""B3: the reproducibility workflow's contract.

Two independent builds on separate runners, compared; build A smoke-tested; a read-only token; no
secret, push, schedule or dispatch. SHA pins and job timeouts are enforced for every workflow by
test_workflow_action_runtime.py.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / ".github/workflows/reproducible-build.yml").read_text(encoding="utf-8")


def _top_level_block(name: str) -> str:
    match = re.search(rf"^{name}:\n((?:[ #].*\n|\n)*)", TEXT, flags=re.M)
    assert match, f"no top-level {name}:"
    return match.group(1)


def _jobs() -> dict[str, str]:
    body = _top_level_block("jobs")
    parts = re.split(r"^  ([a-z0-9-]+):\n", body, flags=re.M)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


def test_it_runs_on_pull_requests_and_main_only() -> None:
    triggers = _top_level_block("on")
    assert re.findall(r"^  ([a-z_]+):", triggers, flags=re.M) == ["pull_request", "push"]
    assert "      - main\n" in triggers
    for forbidden in ("schedule", "workflow_dispatch", "cron"):
        assert forbidden not in TEXT


def test_it_holds_no_secret_and_pushes_nothing() -> None:
    assert _top_level_block("permissions").strip() == "contents: read"
    for forbidden in ("secrets.", "git push", "docker push", "--push", "hf.space", "huggingface",
                      "id-token", "environment:"):
        assert forbidden not in TEXT, forbidden


def test_two_independent_builds_are_compared_and_build_a_is_smoked() -> None:
    jobs = _jobs()
    assert set(jobs) == {"build-a", "build-b", "compare"}
    assert 'reproducible_build.sh build "$RUNNER_TEMP/build-a"' in jobs["build-a"]
    assert 'reproducible_build.sh smoke "$RUNNER_TEMP/build-a"' in jobs["build-a"]
    assert 'reproducible_build.sh build "$RUNNER_TEMP/build-b"' in jobs["build-b"]
    assert "smoke" not in jobs["build-b"]
    compare = jobs["compare"]
    assert "      - build-a\n" in compare and "      - build-b\n" in compare
    assert 'reproducible_build.sh compare "$DIGEST_A" "$DIGEST_B"' in compare
    assert "DIGEST_A: ${{ needs.build-a.outputs.digest }}" in compare
    assert "DIGEST_B: ${{ needs.build-b.outputs.digest }}" in compare
    for name in ("build-a", "build-b"):
        assert "digest: ${{ steps.build.outputs.digest }}" in jobs[name]
        assert "      - id: build\n" in jobs[name]


def test_a_main_commits_proof_is_never_cancelled() -> None:
    concurrency = _top_level_block("concurrency")
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in concurrency


def test_every_job_checks_out_the_pr_head_itself_without_a_persisted_token() -> None:
    for name, job in _jobs().items():
        assert job.count("ref: ${{ github.event.pull_request.head.sha || github.sha }}") == 1, name
        assert job.count("persist-credentials: false") == 1, name
