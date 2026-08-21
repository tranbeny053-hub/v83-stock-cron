from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from tests.workflows._block_yaml import WorkflowYamlError
from tests.workflows._block_yaml import read_block_yaml as _read_block_yaml


def _workflow() -> tuple[str, dict[str, Any]]:
    root = Path(__file__).resolve().parents[2]
    text = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    return text, _read_block_yaml(text)


def _run_commands(document: dict[str, Any]) -> list[str]:
    return [step["run"] for step in document["jobs"]["test"]["steps"] if "run" in step]


def _contains_key(value: Any, sought: str) -> bool:
    if isinstance(value, dict):
        return sought in value or any(_contains_key(child, sought) for child in value.values())
    if isinstance(value, list):
        return any(_contains_key(child, sought) for child in value)
    return False


def test_reader_preserves_nested_mapping_scope() -> None:
    document = _read_block_yaml(
        """push:
  branches:
  - main
branches:
- unrelated
marker: kept
"""
    )

    assert document["push"]["branches"] == ["main"]
    assert document["branches"] == ["unrelated"]
    assert document["marker"] == "kept"


def test_reader_distinguishes_empty_and_nested_keys() -> None:
    document = _read_block_yaml(
        """empty:
nested:
  child: value
"""
    )

    assert document == {"empty": None, "nested": {"child": "value"}}


def test_reader_distinguishes_empty_flow_mapping_and_missing_value() -> None:
    document = _read_block_yaml("empty_mapping: {}\nmissing_value:\n")

    assert document == {"empty_mapping": {}, "missing_value": None}


@pytest.mark.parametrize(
    "source",
    (
        "root:\n\tchild: value\n",
        "root: {child: value}\n",
        "root: [one, two]\n",
        "root: |\n  value\n",
        "root: >\n  value\n",
        "root: >-\n  value\n",
        "root: &anchor value\n",
        "root: *anchor\n",
        "root: !tag value\n",
        "? root: value\n",
        "<<: value\n",
        "root:\n  -\n",
        "not a mapping\n",
        "root:\n  child: value\n  - item\n",
    ),
)
def test_reader_rejects_unsupported_constructs(source: str) -> None:
    with pytest.raises(WorkflowYamlError):
        _read_block_yaml(source)


def test_post_merge_main_trigger_exists() -> None:
    _, document = _workflow()

    assert "main" in document["on"]["push"]["branches"], (
        "main push trigger is required so CI verifies the post-merge commit"
    )


def test_pre_existing_triggers_are_preserved() -> None:
    _, document = _workflow()
    triggers = document["on"]

    assert set(triggers) == {"push", "pull_request"}, "CI trigger types changed"
    assert set(triggers["push"]["branches"]) == {"main", "codex/**"}, (
        "push branches must preserve codex/** while adding main"
    )
    assert triggers["pull_request"] is None, (
        "pull requests must continue to run on every branch"
    )


def test_workflow_token_has_least_privilege() -> None:
    _, document = _workflow()

    assert document.get("permissions") == {"contents": "read"}, (
        "the workflow token must have read-only contents permission"
    )
    for job_name, job in document["jobs"].items():
        assert "permissions" not in job, f"job {job_name!r} overrides token permissions"


def test_verification_steps_are_unchanged() -> None:
    _, document = _workflow()
    job = document["jobs"]["test"]
    steps = job["steps"]

    assert job["runs-on"] == "ubuntu-latest", "the CI runner changed"
    assert _run_commands(document) == [
        "python -m pip install -r requirements.txt",
        "ruff check src tests scripts",
        "PYTHONPATH=src python -m pytest",
        "PYTHONPATH=src python scripts/validate_schemas.py",
        "PYTHONPATH=src python scripts/manual_smoke.py",
        "python scripts/check_no_forbidden_scope.py",
        "python scripts/check_no_full_article_body.py",
        "python scripts/check_no_secrets.py",
    ], "the ordered CI verification commands changed"
    # Current stable Node-24-native majors, measured from each action.yml runs.using field.
    # This stays strict so future bumps are reviewed rather than drifting in.
    assert [step for step in steps if "uses" in step] == [
        {"uses": "actions/checkout@v7"},
        {
            "uses": "actions/setup-python@v7",
            "with": {"python-version": "3.11"},
        },
    ], "checkout or Python setup steps changed"


def test_all_safety_scanners_still_run() -> None:
    root = Path(__file__).resolve().parents[2]
    _, document = _workflow()
    commands = _run_commands(document)

    for scanner in (
        "check_no_forbidden_scope",
        "check_no_full_article_body",
        "check_no_secrets",
    ):
        expected = f"python scripts/{scanner}.py"
        assert expected in commands, f"required safety scanner {scanner!r} is missing"

    verify_text = (root / "verify.sh").read_text(encoding="utf-8")
    scanners = set(re.findall(r"\bcheck_no_[a-z_]+\b", verify_text))
    assert scanners, "verify.sh must declare at least one safety scanner"
    for scanner in scanners:
        expected = f"python scripts/{scanner}.py"
        assert expected in commands, (
            f"CI is missing safety scanner {scanner!r} declared by verify.sh"
        )


def test_workflow_has_no_privileged_or_out_of_scope_access() -> None:
    text, document = _workflow()
    lowered = text.lower()

    for token in (
        "${{",
        "supabase",
        "_db_url",
        "database_url",
        "huggingface",
        "hf.space",
        "collect_oos_pair_evidence",
        "resolve_outcomes",
        "source_integrity_guard",
        "deploy",
        "git push",
        "workflow_dispatch",
        "schedule:",
        "cron",
        "id-token",
        "environment:",
    ):
        assert token not in lowered, f"always-on CI contains prohibited token {token!r}"
    assert not _contains_key(document, "env"), "always-on CI must not define env at any depth"
