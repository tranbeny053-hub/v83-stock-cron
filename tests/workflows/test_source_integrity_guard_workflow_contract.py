from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.workflows._block_yaml import read_block_yaml


def _workflow() -> tuple[Path, str, dict[str, Any]]:
    root = Path(__file__).resolve().parents[2]
    path = root / ".github/workflows/source-integrity-guard.yml"
    text = path.read_text(encoding="utf-8")
    return root, text, read_block_yaml(text)


def _contains_key(value: Any, sought: str) -> bool:
    if isinstance(value, dict):
        return sought in value or any(_contains_key(child, sought) for child in value.values())
    if isinstance(value, list):
        return any(_contains_key(child, sought) for child in value)
    return False


def test_actions_use_node_24_native_majors() -> None:
    _, _, document = _workflow()
    steps = document["jobs"]["verify"]["steps"]

    # Current stable Node-24-native majors, measured from each action.yml runs.using.
    # Strict so a future bump is reviewed rather than drifting in.
    assert [step for step in steps if "uses" in step] == [
        {"uses": "actions/checkout@v7"},
        {
            "uses": "actions/setup-python@v7",
            "with": {"python-version": "3.11"},
        },
    ], "checkout and setup-python must remain on the reviewed Node-24-native v7 majors"


def test_guard_cadence_is_unchanged() -> None:
    _, _, document = _workflow()
    triggers = document["on"]

    assert set(triggers) == {"schedule", "workflow_dispatch"}, (
        "guard trigger types changed"
    )
    assert triggers["schedule"] == [{"cron": "27 */2 * * *"}], (
        "cron is the guard's cadence and must remain exactly 27 */2 * * *"
    )
    assert triggers["workflow_dispatch"] == {}, (
        "workflow_dispatch must remain an empty mapping"
    )


def test_guard_identity_and_isolation_are_unchanged() -> None:
    _, _, document = _workflow()

    assert document["name"] == "Runtime Source Integrity Guard", (
        "guard workflow identity changed"
    )
    assert document["permissions"] == {"contents": "read"}, (
        "guard permissions must remain read-only contents access"
    )
    for job_name, job in document["jobs"].items():
        assert "permissions" not in job, f"job {job_name!r} overrides guard permissions"
    # The block reader deliberately yields YAML scalars such as false as strings.
    assert document["concurrency"] == {
        "group": "source-integrity-guard",
        "cancel-in-progress": "false",
    }, "guard concurrency identity or cancellation behavior changed"


def test_verify_job_is_unchanged() -> None:
    _, _, document = _workflow()

    assert set(document["jobs"]) == {"verify"}, "guard must contain exactly the verify job"
    job = document["jobs"]["verify"]
    assert job["runs-on"] == "ubuntu-latest", "guard runner changed"
    assert job["timeout-minutes"] == "10", "guard timeout must remain 10 minutes"
    steps = job["steps"]
    assert len(steps) == 3, "verify must contain exactly three ordered steps"
    assert steps == [
        {"uses": "actions/checkout@v7"},
        {
            "uses": "actions/setup-python@v7",
            "with": {"python-version": "3.11"},
        },
        {
            "name": "Compare intended source with HF main and live serving",
            "run": "python scripts/source_integrity_guard.py",
        },
    ], "verify steps or their order changed"


def test_guard_script_exists() -> None:
    root, _, _ = _workflow()

    assert (root / "scripts/source_integrity_guard.py").is_file(), (
        "guard workflow points to a missing scripts/source_integrity_guard.py"
    )


def test_no_privileged_access_can_enter() -> None:
    _, text, document = _workflow()

    assert "${{" not in text, "guard workflow must not interpolate privileged contexts"
    # Do not prohibit HF/deploy words: HF legitimately appears in the guard step name.
    assert not _contains_key(document, "env"), "guard workflow must not define env at any depth"
