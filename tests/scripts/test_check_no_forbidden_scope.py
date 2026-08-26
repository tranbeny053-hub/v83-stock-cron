from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def test_forbidden_scope_scans_executable_scripts(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    scripts = repository / "scripts"
    scripts.mkdir(parents=True)
    scanner = Path(__file__).parents[2] / "scripts" / "check_no_forbidden_scope.py"
    copied_scanner = shutil.copy2(scanner, scripts / scanner.name)

    clean = subprocess.run(
        [sys.executable, copied_scanner],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )
    assert clean.returncode == 0, clean.stdout + clean.stderr

    banned_token = "_".join(("place", "order"))
    offending_script = scripts / "operator_trade.py"
    offending_script.write_text(f"def {banned_token}():\n    pass\n", encoding="utf-8")

    mutated = subprocess.run(
        [sys.executable, copied_scanner],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )
    output = mutated.stdout + mutated.stderr
    assert mutated.returncode != 0
    assert offending_script.name in output
    assert banned_token in output
