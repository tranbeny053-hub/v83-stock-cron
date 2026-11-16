import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.migration_0019_rehearsal.run_authored_steps import extract

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "marker", ["secrets.X", "inputs.x", "--mode=run", "--mode=apply", "SUPABASE_DB_URL"]
)
def test_refuses_unsafe_steps(tmp_path, marker):
    p = tmp_path / "x.yml"
    p.write_text(f"jobs:\n  x:\n    steps:\n      - name: target\n        run: echo {marker}\n")
    with pytest.raises(ValueError):
        extract(p, "target")


def test_real_authored_scratch_blocks_are_extracted_byte_exactly():
    for wf, name in (
        ("ng4-pilot-preflight.yml", "Rehearse preflight on scratch PostgreSQL (no secret)"),
        (
            "apply-migration-0019.yml",
            "Rehearse the apply on a scratch local PostgreSQL database (no secret)",
        ),
    ):
        base = (
            ROOT / ".github/workflows"
            if wf == "ng4-pilot-preflight.yml"
            else ROOT / "ops/ng4_pilot/workflows"
        )
        run, env = extract(base / wf, name)
        assert run.startswith("sudo systemctl start postgresql.service")
        assert "postgresql:///" in next(iter(env.values()))


def test_the_runner_writes_no_bytecode_into_the_checkout(tmp_path):
    # The authored steps' isolation audit refuses a checkout holding a bytecode cache; PR #332's
    # first CI run failed both authored-step jobs that way (IsolationRefused), because the runner,
    # started without -B, imported tests/workflows/_workflow_steps.py and cached it.
    for rel in (
        "scripts/migration_0019_rehearsal/run_authored_steps.py",
        "tests/workflows/_workflow_steps.py",
    ):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, tmp_path / rel)
    for package in ("tests", "tests/workflows"):
        if (ROOT / package / "__init__.py").exists():
            shutil.copyfile(ROOT / package / "__init__.py", tmp_path / package / "__init__.py")
    unset = ("PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX")
    env = {k: v for k, v in os.environ.items() if k not in unset}
    done = subprocess.run(
        [
            sys.executable,
            str(tmp_path / "scripts/migration_0019_rehearsal/run_authored_steps.py"),
            str(tmp_path / "missing.yml"),
            "x",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 2, done.stderr
    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("__pycache__")) == []


def test_both_authored_step_jobs_start_the_runner_without_bytecode():
    text = (ROOT / ".github/workflows/migration-0019-rehearsal.yml").read_text(encoding="utf-8")
    calls = [
        line.strip()
        for line in text.splitlines()
        if "run_authored_steps.py" in line and line.strip().startswith("run:")
    ]
    assert len(calls) == 2
    command = "run: python -B scripts/migration_0019_rehearsal/run_authored_steps.py "
    assert all(c.startswith(command) for c in calls)
