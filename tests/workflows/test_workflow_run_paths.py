"""Every workflow, registered or authored, names only repository paths that exist, and every scratch
step that connects without a user creates the runner's role first (W2 spec review R1-1: two authored
workflows had scratch steps that could never run, and every review had read them statically)."""

import re
from pathlib import Path

from tests.workflows._workflow_steps import WorkflowStepsError, read_jobs

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_FILES = sorted(
    [*ROOT.glob(".github/workflows/*.yml"), *ROOT.glob("ops/**/workflows/*.yml")]
)
PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_$/.-])((?:scripts|migrations|ops|tests|src)/[A-Za-z0-9_./+-]+)"
)
USERLESS_URL = re.compile(r"postgresql:///[^\s\"']*")
CREATE_RUNNER_ROLE = 'CREATE ROLE \\"$(id -un)\\"'


def _code_lines(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def test_the_scan_covers_the_authored_workflows():
    names = {p.relative_to(ROOT).as_posix() for p in WORKFLOW_FILES}
    assert "ops/ng4_pilot/workflows/apply-migration-0019.yml" in names
    assert "ops/ng4_pilot/workflows/ng4-pilot-preflight.yml" in names


def test_every_named_repository_path_exists():
    missing = []
    for file in WORKFLOW_FILES:
        for named in PATH_RE.findall(_code_lines(file.read_text(encoding="utf-8"))):
            clean = named.rstrip(".,:)\"'")
            if not (ROOT / clean).exists():
                missing.append(f"{file.relative_to(ROOT)}: {clean}")
    assert missing == []


def test_a_userless_postgres_url_step_creates_the_runner_role_first():
    problems = []
    for file in WORKFLOW_FILES:
        text = file.read_text(encoding="utf-8")
        if not USERLESS_URL.search(_code_lines(text)):
            continue
        try:
            jobs = read_jobs(text)
        except WorkflowStepsError:
            # The small reader does not parse every workflow (e.g. a strategy matrix); then the text
            # itself must create the runner's role before its first user-less URL.
            code = _code_lines(text)
            first_url = USERLESS_URL.search(code)
            role = code.find(CREATE_RUNNER_ROLE)
            if role < 0 or role > first_url.start():
                problems.append(f"{file.relative_to(ROOT)}: no runner role before its first URL")
            continue
        for name, job in jobs.items():
            seen_role = False
            for step in job.steps:
                env_text = " ".join(str(v) for v in (step.env or {}).values())
                if CREATE_RUNNER_ROLE in (step.run or ""):
                    seen_role = True
                urls = [u for u in USERLESS_URL.findall(env_text) if "user=" not in u]
                if urls and not seen_role:
                    problems.append(f"{file.relative_to(ROOT)}: job {name}: {step.name}")
    assert problems == []
