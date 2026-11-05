"""Offline checks of the 0019 rehearsal's own guards.

The rehearsal itself needs a scratch PostgreSQL.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/migration_0019_rehearsal/rehearse.py"
RUNNER = ROOT / "scripts/migration_0019_rehearsal/run_scratch.sh"
_spec = importlib.util.spec_from_file_location("rehearse_0019", SCRIPT)
rehearse = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rehearse)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://db.example.supabase.co/postgres",
        "postgresql://remote.example/db",
        "postgresql://10.0.0.5/db",
        "mysql://localhost/db",
        "postgresql:///db",
        "postgresql:///db?host=relative/dir",
        "postgresql:///db?host=/tmp/x&user=SUPABASE",
    ],
)
def test_non_local_urls_are_refused(url: str) -> None:
    assert rehearse.refuse_url(url) is not None


@pytest.mark.parametrize(
    "url",
    [
        "postgresql:///db?host=/tmp/u19.ab12&user=postgres",
        "postgresql://localhost/db",
        "postgresql://127.0.0.1/db",
    ],
)
def test_local_urls_are_accepted(url: str) -> None:
    assert rehearse.refuse_url(url) is None


def test_main_refuses_before_connecting_and_prints_no_url(capsys) -> None:
    url = "postgresql://remote.example/secret_db_name"
    code = rehearse.main(
        [
            "--url",
            url,
            "--super-url",
            "postgresql:///d?host=/tmp/x",
            "--commit-ts",
            "off",
            "--report",
            "/dev/null",
        ]
    )
    out = capsys.readouterr().out
    assert code == 2 and out.startswith("REFUSED: --url:") and "secret_db_name" not in out


def test_the_rehearsal_applies_the_authored_file_only() -> None:
    assert rehearse.MIGRATION == ROOT / "migrations/authored/0019_lattice_evidence.sql"
    text = SCRIPT.read_text(encoding="utf-8")
    assert "os.environ" not in text and "getenv" not in text
    assert "print(url" not in text and "print(args.url" not in text


def test_runner_script_refuses_a_bad_mode_and_reads_no_database_url(tmp_path: Path) -> None:
    text = RUNNER.read_text(encoding="utf-8")
    assert "listen_addresses=''" in text and "DATABASE_URL" not in text and "SUPABASE" not in text
    result = subprocess.run(
        [
            "bash",
            str(RUNNER),
            "/nonexistent",
            str(tmp_path / "w"),
            str(tmp_path / "r.json"),
            "maybe",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2 and "REFUSED" in result.stderr


def test_runner_script_refuses_an_existing_work_directory(tmp_path: Path) -> None:
    result = subprocess.run(
        ["bash", str(RUNNER), "/nonexistent", str(tmp_path), str(tmp_path / "r.json"), "off"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2 and "exists" in result.stderr
