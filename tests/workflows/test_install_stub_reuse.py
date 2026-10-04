"""Shared executables preserve each installed command's independent behaviour."""

import stat
import subprocess
from pathlib import Path

import pytest

from tests.workflows._workflow_steps import install_stub, stub_calls


def test_links_share_read_only_body_and_keep_logs_separate(tmp_path: Path) -> None:
    first_log = tmp_path / "first log.jsonl"
    second_log = tmp_path / "second log.jsonl"
    first = install_stub(tmp_path / "first bin", "python", first_log)
    second = install_stub(tmp_path / "second bin", "psql", second_log)

    assert first == tmp_path / "first bin" / "python"
    assert second == tmp_path / "second bin" / "psql"
    assert first.is_symlink() and second.is_symlink()
    assert first.resolve() == second.resolve()
    assert stat.S_IMODE(first.resolve().stat().st_mode) == 0o555

    for stub, arg, stdout, exit_code in (
        (first, "first argument", "first output\n", 7),
        (second, "second argument", "second output\n", 0),
        (first, "another argument", "again", 3),
    ):
        completed = subprocess.run(
            [stub.name, arg],
            env={
                "PATH": f"{stub.parent}:/usr/bin:/bin",
                "PYTHONPATH": "test-pythonpath",
                "STUB_STDOUT": stdout,
                "STUB_EXIT": str(exit_code),
            },
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == exit_code, completed.stderr
        assert completed.stdout == stdout
        assert completed.stderr == ""

    assert stub_calls(first_log) == [
        {"argv": ["first argument"], "PYTHONPATH": "test-pythonpath"},
        {"argv": ["another argument"], "PYTHONPATH": "test-pythonpath"},
    ]
    assert stub_calls(second_log) == [
        {"argv": ["second argument"], "PYTHONPATH": "test-pythonpath"},
    ]


@pytest.mark.parametrize("existing", ["file", "link", "broken-link"])
def test_reinstall_replaces_existing_command(tmp_path: Path, existing: str) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    command = bin_dir / "python"
    old_log = tmp_path / "old.jsonl"
    if existing == "file":
        command.write_text("old executable", encoding="utf-8")
    elif existing == "link":
        install_stub(bin_dir, command.name, old_log)
    else:
        command.symlink_to(tmp_path / "missing")

    new_log = tmp_path / "new.jsonl"
    installed = install_stub(bin_dir, command.name, new_log)
    assert installed == command
    assert installed.is_symlink()
    completed = subprocess.run(
        [str(installed), "new argument"], env={}, capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""
    assert stub_calls(old_log) == []
    assert stub_calls(new_log) == [{"argv": ["new argument"], "PYTHONPATH": None}]
