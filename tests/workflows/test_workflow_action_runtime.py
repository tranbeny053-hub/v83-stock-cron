"""Guard GitHub Actions workflows against unreviewed action runtimes."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted(
    (*ROOT.glob(".github/workflows/*.yml"), *ROOT.glob(".github/workflows/*.yaml"))
)

# Measured 2026-09-17 from each action.yml runs.using at these commits: all are node24.
# A bump is reviewed here rather than drifting in.
REVIEWED_NODE24 = {
    "actions/checkout": {"v7": "3d3c42e5aac5ba805825da76410c181273ba90b1"},
    "actions/setup-python": {"v7": "5fda3b95a4ea91299a34e894583c3862153e4b97"},
    "actions/upload-artifact": {"v7": "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"},
}

ActionRef = tuple[str, int, str, str, str | None]
Violation = tuple[str, int, str]

_USES_LINE = re.compile(
    r"^\s*(?:-\s+)?uses:\s*(?P<ref>\S+)(?:\s+#\s*(?P<comment>\S+))?\s*$"
)
_USES_PREFIX = re.compile(r"^\s*(?:-\s+)?uses\s*:")


def extract_action_refs(text: str, file_name: str) -> tuple[list[ActionRef], list[Violation]]:
    """Extract action references and retain malformed uses lines as violations."""

    refs: list[ActionRef] = []
    violations: list[Violation] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = _USES_LINE.fullmatch(line)
        if match is None:
            if _USES_PREFIX.match(line):
                violations.append((file_name, line_number, line.strip()))
            continue

        ref = match.group("ref")
        if "@" not in ref:
            violations.append((file_name, line_number, ref))
            continue
        action, version = ref.rsplit("@", 1)
        if not action or not version:
            violations.append((file_name, line_number, ref))
            continue
        refs.append((file_name, line_number, action, version, match.group("comment")))
    return refs, violations


def classify_action_refs(text: str, file_name: str) -> tuple[list[ActionRef], list[Violation]]:
    """Classify extracted references against the reviewed Node-24 allowlist."""

    refs, violations = extract_action_refs(text, file_name)
    allowed: list[ActionRef] = []
    for ref in refs:
        _, line_number, action, version, comment = ref
        reviewed_versions = REVIEWED_NODE24.get(action, {})
        is_reviewed_tag = version in reviewed_versions and comment is None
        is_reviewed_sha = any(
            version == sha and comment == major for major, sha in reviewed_versions.items()
        )
        if is_reviewed_tag or is_reviewed_sha:
            allowed.append(ref)
        else:
            violations.append((file_name, line_number, f"{action}@{version}"))
    violations.sort(key=lambda violation: violation[1])
    return allowed, violations


def workflow_refs() -> tuple[list[ActionRef], list[Violation]]:
    """Collect and classify action references from every workflow file."""

    refs: list[ActionRef] = []
    violations: list[Violation] = []
    for workflow in WORKFLOWS:
        found, malformed = extract_action_refs(
            workflow.read_text(encoding="utf-8"), workflow.name
        )
        refs.extend(found)
        violations.extend(malformed)
    return refs, violations


def test_the_extractor_is_itself_correct() -> None:
    """Guard the guard with known allowed, disallowed, and malformed references."""

    fixture = """steps:
  - uses: actions/checkout@v7
  - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97  # v7
  - uses: actions/checkout@v4
  - uses: actions/checkout
"""
    assert classify_action_refs(fixture, "fixture.yml") == (
        [
            ("fixture.yml", 2, "actions/checkout", "v7", None),
            (
                "fixture.yml",
                3,
                "actions/setup-python",
                "5fda3b95a4ea91299a34e894583c3862153e4b97",
                "v7",
            ),
        ],
        [
            ("fixture.yml", 4, "actions/checkout@v4"),
            ("fixture.yml", 5, "actions/checkout"),
        ],
    )


def test_every_workflow_parses_at_least_the_expected_number_of_refs() -> None:
    """Require the measured action-reference count across all workflows."""

    refs, _ = workflow_refs()
    # A changed count means a workflow step was added or removed and must be reviewed here.
    assert len(refs) == 35


def test_every_action_ref_is_a_reviewed_node24_pin() -> None:
    """Require every workflow action reference to use a reviewed Node-24 pin."""

    violations: list[Violation] = []
    for workflow in WORKFLOWS:
        _, found = classify_action_refs(workflow.read_text(encoding="utf-8"), workflow.name)
        violations.extend(found)

    message = "\n".join(
        f"{file_name}:{line_number} {ref}" for file_name, line_number, ref in violations
    )
    assert not violations, message


def test_the_database_workflows_that_were_on_node20_now_use_full_sha_pins() -> None:
    """Require the two former Node-20 workflows to use the reviewed full SHA pins."""

    expected = [
        ("actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1", "v7"),
        ("actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97", "v7"),
    ]
    for file_name in ("oos-pair-evidence.yml", "resolve-outcomes.yml"):
        text = (ROOT / ".github/workflows" / file_name).read_text(encoding="utf-8")
        refs, malformed = extract_action_refs(text, file_name)
        assert not malformed
        actual = [
            (f"{action}@{version}", comment) for _, _, action, version, comment in refs
        ]
        assert actual == expected


def test_no_workflow_references_a_node20_era_major() -> None:
    """Reject tag references to known Node-20-era action majors."""

    refs, _ = workflow_refs()
    node20_era = {
        "actions/checkout": {f"v{major}" for major in range(1, 5)},
        "actions/setup-python": {f"v{major}" for major in range(1, 6)},
        "actions/upload-artifact": {f"v{major}" for major in range(1, 5)},
    }
    violations = [
        (file_name, line_number, f"{action}@{version}")
        for file_name, line_number, action, version, _ in refs
        if version in node20_era.get(action, set())
    ]
    message = "\n".join(
        f"{file_name}:{line_number} {ref}" for file_name, line_number, ref in violations
    )
    assert not violations, message
