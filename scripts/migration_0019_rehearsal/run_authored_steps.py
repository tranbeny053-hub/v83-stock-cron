"""Execute explicitly selected, non-production run steps of an authored workflow, in order.

Each step is extracted byte-exactly (its run block and env) and refused if it names a secret, an
input or a production mode; the steps run one after another, as the dispatched job runs them."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:  # run as a script in CI: the repository root holds tests/
    sys.path.insert(0, str(ROOT))

from tests.workflows._workflow_steps import read_jobs  # noqa: E402

FORBIDDEN = ("secrets.", "inputs.", "SUPABASE", "--mode=run", "--mode=apply")


def extract(path: Path, step_name: str) -> tuple[str, dict[str, str]]:
    jobs = read_jobs(path.read_text(encoding="utf-8"))
    found = [step for job in jobs.values() for step in job.steps if step.name == step_name]
    if len(found) != 1 or not found[0].run:
        raise ValueError("expected exactly one named run step")
    step = found[0]
    combined = step.run + "\n" + "\n".join(step.env.values())
    if any(marker in combined for marker in FORBIDDEN):
        raise ValueError("selected step contains a forbidden production reference")
    return step.run, step.env


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workflow", type=Path)
    parser.add_argument("step_names", nargs="+")
    args = parser.parse_args(argv)
    try:
        steps = [extract(args.workflow, name) for name in args.step_names]
    except (OSError, ValueError, AssertionError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    for run, env in steps:
        child_env = os.environ.copy()
        child_env.update(env)
        done = subprocess.run(["bash", "-euo", "pipefail", "-c", run], env=child_env, check=False)
        if done.returncode != 0:
            return done.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
