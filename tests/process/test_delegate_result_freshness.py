"""A stale result must never be reported as a fresh verdict.

This guard exists because the failure mode was SILENT: a re-run whose model exhausted its
quota wrote no result, the previous run's file was still on disk, and the delegation
reported OK. The old verdict was very nearly read as the new one. A textual assertion
would not have caught it, so this drives the real script with a stub ``codex``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DELEGATE = ROOT / "delegate.sh"

_STUB_WRITES_NOTHING = """#!/usr/bin/env bash
# Stands in for a codex run that dies without writing its result (quota exhaustion).
cat >/dev/null
echo "simulated codex output"
exit 0
"""

_STUB_WRITES_RESULT = """#!/usr/bin/env bash
cat >/dev/null
out=""
while [ $# -gt 0 ]; do
  if [ "$1" = "-o" ]; then out="$2"; shift; fi
  shift
done
printf '%s' '{"status":"DONE","summary":"fresh","files_changed":[],' > "$out"
printf '%s' '"tests_run":0,"tests_passed":0,"blocker":""}' >> "$out"
exit 0
"""


@pytest.fixture
def harness(tmp_path: Path):
    """A copy of delegate.sh with a stub codex on PATH. Never touches the real repo."""

    shutil.copy2(DELEGATE, tmp_path / "delegate.sh")
    (tmp_path / ".work").mkdir()
    (tmp_path / ".work" / "task-999.md").write_text("stub task\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "x"], cwd=tmp_path,
                   check=True, env={**os.environ, "GIT_AUTHOR_NAME": "t",
                                    "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                                    "GIT_COMMITTER_EMAIL": "t@t"})
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    def run(stub: str):
        codex = bin_dir / "codex"
        codex.write_text(stub, encoding="utf-8")
        codex.chmod(0o755)
        return subprocess.run(
            [str(tmp_path / "delegate.sh"), ".work/task-999.md"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"},
        )

    return tmp_path, run


def test_a_stale_result_cannot_satisfy_completion(harness) -> None:
    """THE REGRESSION. A leftover result plus a codex that writes nothing must FAIL."""

    tmp_path, run = harness
    stale = tmp_path / ".work" / "result-999.json"
    stale.write_text(
        '{"status":"DONE","summary":"STALE VERDICT FROM AN EARLIER RUN",'
        '"files_changed":[],"tests_run":0,"tests_passed":0,"blocker":""}',
        encoding="utf-8",
    )

    completed = run(_STUB_WRITES_NOTHING)

    assert completed.returncode != 0, "a stale result must not report success"
    assert "DELEGATE=OK" not in completed.stdout
    assert "STALE VERDICT" not in completed.stdout, "the old verdict must not be echoed"


def test_the_stale_result_is_preserved_not_destroyed(harness) -> None:
    """Rotating beats deleting: the earlier verdict stays auditable."""

    tmp_path, run = harness
    stale = tmp_path / ".work" / "result-999.json"
    stale.write_text('{"status":"DONE","summary":"earlier","files_changed":[],'
                     '"tests_run":0,"tests_passed":0,"blocker":""}', encoding="utf-8")

    run(_STUB_WRITES_NOTHING)

    rotated = list((tmp_path / ".work").glob("result-999.prev-*.json"))
    assert len(rotated) == 1
    assert "earlier" in rotated[0].read_text(encoding="utf-8")


def test_a_genuinely_fresh_result_still_succeeds(harness) -> None:
    """Guard the guard: the hardening must not break the normal path."""

    tmp_path, run = harness
    completed = run(_STUB_WRITES_RESULT)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "DELEGATE=OK" in completed.stdout
    assert '"summary":"fresh"' in completed.stdout


def test_a_fresh_result_succeeds_even_when_one_was_rotated(harness) -> None:
    tmp_path, run = harness
    (tmp_path / ".work" / "result-999.json").write_text(
        '{"status":"DONE","summary":"earlier","files_changed":[],"tests_run":0,'
        '"tests_passed":0,"blocker":""}', encoding="utf-8")

    completed = run(_STUB_WRITES_RESULT)

    assert completed.returncode == 0
    assert '"summary":"fresh"' in completed.stdout
    assert list((tmp_path / ".work").glob("result-999.prev-*.json"))
