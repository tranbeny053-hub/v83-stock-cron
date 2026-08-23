from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _clean_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key != "PYTHONPATH" and not key.startswith("PYTEST_")
    }


def _collect(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=_clean_environment(),
        capture_output=True,
        text=True,
        check=False,
    )


def _output(result: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(part for part in (result.stdout, result.stderr) if part)


def test_task_050_pythonpath_configuration_contract() -> None:
    with (REPO_ROOT / "pyproject.toml").open("rb") as file:
        configuration = tomllib.load(file)

    pythonpath = configuration["tool"]["pytest"]["ini_options"]["pythonpath"]
    assert pythonpath == ["src", "."], (
        "Task 050 requires the repo root on sys.path for both pytest invocation forms"
    )


def test_task_050_pytest_invocation_parity() -> None:
    bare_pytest = Path(sys.executable).parent / "pytest"
    assert bare_pytest.is_file() and os.access(bare_pytest, os.X_OK), (
        f"bare pytest console script is required at {bare_pytest}"
    )

    common_arguments = ["--collect-only", "-q", "-p", "no:cacheprovider"]
    results = {
        "python -m pytest": _collect([sys.executable, "-m", "pytest", *common_arguments]),
        "bare pytest": _collect([str(bare_pytest), *common_arguments]),
    }

    for form, result in results.items():
        preview = "\n".join(_output(result).splitlines()[:20])
        assert result.returncode == 0, f"{form} collection failed:\n{preview}"

    node_ids = {
        form: {line for line in _output(result).splitlines() if "::" in line}
        for form, result in results.items()
    }
    assert node_ids["python -m pytest"], "pytest collection produced no node IDs"
    assert node_ids["python -m pytest"] == node_ids["bare pytest"], (
        "python -m pytest and bare pytest collected different node IDs"
    )
