"""C4: the owner URL (the GitHub secret SUPABASE_DB_URL, the table owner) is for dispatch-only jobs,
and only inside the protected Environment production-db-owner.

The privilege design's C4: "The existing owner URL stays only in a GitHub Environment ... with
required reviewers. Only the dispatch-only apply, audit and evaluation workflows reference it."
The repository is public, and the resolver (G1) never receives the owner URL. One exception is
named, not hidden: the pinned section 5A evaluation workflow, whose change needs the owner's
authorization (the evaluator pin).
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
PINNED_EXCEPTION = "section-5a-evaluation.yml"
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
    assert len(users) == 14
    for name, text in users.items():
        assert set(TRIGGER.findall(text)) == {"workflow_dispatch"}, name


def test_every_job_using_the_owner_url_runs_in_the_protected_environment() -> None:
    for name, text in _users().items():
        for job_name, job in read_jobs(text).items():
            steps = " ".join(str(step.env) for step in job.steps)
            if OWNER_URL_REF not in str(job.env) + steps:
                continue
            environment = str(job.fields.get("environment", "")).split("#")[0].strip()
            if name == PINNED_EXCEPTION:
                assert environment == "", "if the owner authorized it, drop the exception"
                continue
            assert environment == ENVIRONMENT, f"{name}: job {job_name}"


def test_the_one_exception_is_the_pinned_evaluation_workflow() -> None:
    pin = json.loads((ROOT / "ops/section_5a_evaluator_pin.json").read_text(encoding="utf-8"))
    pinned = {entry["path"] if isinstance(entry, dict) else entry for entry in pin["pinned_files"]}
    assert f".github/workflows/{PINNED_EXCEPTION}" in pinned
    assert PINNED_EXCEPTION in _users()
