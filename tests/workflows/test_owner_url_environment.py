"""C4: the owner URL (the GitHub secret SUPABASE_DB_URL, the table owner) is for dispatch-only jobs,
and only inside the protected Environment production-db-owner.

The privilege design's C4: "The existing owner URL stays only in a GitHub Environment ... with
required reviewers. Only the dispatch-only apply, audit and evaluation workflows reference it."
The repository is public, and the resolver (G1) never receives the owner URL. The pinned section 5A
evaluation workflow takes the Environment too, by the owner's ruling C4-PIN (2026-10-03: "add only
the production-db-owner environment line to section-5a-evaluation.yml and re-pin it").
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from tests.workflows._workflow_steps import read_jobs

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
OWNER_URL_REF = "secrets.SUPABASE_DB_URL"
ENVIRONMENT = "production-db-owner"
PINNED_EVALUATION = "section-5a-evaluation.yml"
TRIGGER = re.compile(
    r"^  (schedule|push|pull_request|pull_request_target|workflow_run|workflow_dispatch"
    r"|workflow_call):",
    re.M,
)


def _users() -> dict[str, str]:
    texts = {path.name: path.read_text(encoding="utf-8") for path in WORKFLOWS.glob("*.yml")}
    return {name: texts[name] for name in sorted(texts) if OWNER_URL_REF in texts[name]}


def test_only_dispatch_only_workflows_may_use_the_owner_url() -> None:
    users = _users()
    assert "resolve-outcomes.yml" not in users, "G1: the resolver has its own login"
    assert len(users) == 15  # 14 -> 15: D6's read-only core-write inventory
    for name, text in users.items():
        assert set(TRIGGER.findall(text)) == {"workflow_dispatch"}, name


def test_every_job_using_the_owner_url_runs_in_the_protected_environment() -> None:
    for name, text in _users().items():
        for job_name, job in read_jobs(text).items():
            steps = " ".join(str(step.env) for step in job.steps)
            if OWNER_URL_REF not in str(job.env) + steps:
                continue
            environment = str(job.fields.get("environment", "")).split("#")[0].strip()
            assert environment == ENVIRONMENT, f"{name}: job {job_name}"


def test_c4_pin_the_pinned_evaluation_workflow_changed_only_by_its_environment_line() -> None:
    """C4-PIN: the evaluator pin still holds the workflow (re-pinned), and the one added line is the
    Environment's; nothing else of the pinned workflow changed."""

    pin = json.loads((ROOT / "ops/section_5a_evaluator_pin.json").read_text(encoding="utf-8"))
    pinned = {entry["path"] if isinstance(entry, dict) else entry for entry in pin["pinned_files"]}
    assert f".github/workflows/{PINNED_EVALUATION}" in pinned
    text = (WORKFLOWS / PINNED_EVALUATION).read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if line.strip().startswith("environment:")]
    assert lines == [f"    environment: {ENVIRONMENT}  # C4: the owner URL lives only in this "
                     "protected Environment"]
