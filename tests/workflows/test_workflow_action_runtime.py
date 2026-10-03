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
    # 41 -> 47 (F1): the migration-0013 apply and rehearsal workflows add checkout, setup-python
    # and upload-artifact each, all three at the reviewed Node-24 SHA pins.
    # 47 -> 50 (B3): the reproducible-build workflow adds checkout to build-a, build-b and
    # compare, at the reviewed Node-24 SHA pin.
    # 50 -> 52 (DBI-1): the migration-0014 rehearsal adds checkout and setup-python, both at the
    # reviewed pins.
    # 52 -> 56 (the 0014 apply route): the dispatch workflow adds checkout, setup-python and
    # upload-artifact, and the rehearsal uploads its report, all at the reviewed pins.
    # 56 -> 59 (PERS-0): the persistence fault rehearsal adds checkout, setup-python and
    # upload-artifact, all at the reviewed pins.
    # 59 -> 65 (B9): the migration-0015 dispatch and pull-request rehearsal workflows add
    # checkout, setup-python and upload-artifact each, all at the reviewed pins.
    # 65 -> 68 (P3-PRIV-R): the privilege rehearsal adds checkout, setup-python and
    # upload-artifact, all at the reviewed pins. PostgREST is a release binary checked by sha256,
    # not an action.
    # 68 -> 74 (migration 0016): the dispatch-only apply workflow and the pull-request rehearsal add
    # checkout, setup-python and upload-artifact each, all at the reviewed pins.
    # 74 -> 80 (migration 0017): its dispatch-only apply workflow and pull-request rehearsal add the
    # same three each, at the same pins.
    assert len(refs) == 80


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


def test_every_action_ref_is_a_full_sha_pin() -> None:
    """B2: every action is pinned to a reviewed full commit SHA, with its major as the comment."""

    refs, malformed = workflow_refs()
    assert not malformed
    unpinned = [
        f"{file_name}:{line_number} {action}@{version}"
        for file_name, line_number, action, version, comment in refs
        if not re.fullmatch(r"[0-9a-f]{40}", version)
        or REVIEWED_NODE24.get(action, {}).get(comment) != version
    ]
    assert not unpinned, "\n".join(unpinned)


def _jobs_without_timeout(text: str) -> list[str]:
    """Job names under `jobs:` whose own block has no `timeout-minutes:` line."""

    missing: list[str] = []
    in_jobs = False
    current: str | None = None
    has_timeout = False
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent == 0:
            if current is not None and not has_timeout:
                missing.append(current)
            current = None
            in_jobs = line.rstrip() == "jobs:"
            continue
        if not in_jobs:
            continue
        if indent == 2 and line.rstrip().endswith(":"):
            if current is not None and not has_timeout:
                missing.append(current)
            current, has_timeout = line.strip().rstrip(":"), False
        elif indent == 4 and line.strip().startswith("timeout-minutes:"):
            has_timeout = True
    if current is not None and not has_timeout:
        missing.append(current)
    return missing


def test_the_timeout_scanner_is_itself_correct() -> None:
    """Guard the guard: one job with a timeout, one without, and a later top-level key."""

    fixture = """jobs:
  good:
    runs-on: ubuntu-latest
    timeout-minutes: 5
  bad:
    runs-on: ubuntu-latest
    steps:
      - run: echo
concurrency:
  group: x
"""
    assert _jobs_without_timeout(fixture) == ["bad"]


def test_every_workflow_declares_token_permissions_and_job_timeouts() -> None:
    """B2: every workflow sets top-level token permissions, and every job a timeout."""

    problems: list[str] = []
    for workflow in WORKFLOWS:
        text = workflow.read_text(encoding="utf-8")
        if not re.search(r"^permissions:", text, flags=re.MULTILINE):
            problems.append(f"{workflow.name}: no top-level permissions")
        problems.extend(
            f"{workflow.name}: job {job} has no timeout-minutes"
            for job in _jobs_without_timeout(text)
        )
    assert not problems, "\n".join(problems)
