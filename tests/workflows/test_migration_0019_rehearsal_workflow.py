"""The 0019 rehearsal workflow.

Pull requests only, a read-only token, no secret, both commit-timestamp modes.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / ".github/workflows/migration-0019-rehearsal.yml").read_text(encoding="utf-8")


def test_triggers_and_permissions() -> None:
    assert '"on":\n  pull_request:\n    paths:\n' in TEXT
    for path in (
        "migrations/**",
        "scripts/migration_0019_rehearsal/**",
        ".github/workflows/migration-0019-rehearsal.yml",
    ):
        assert f"      - {path}\n" in TEXT
    assert "permissions:\n  contents: read\n" in TEXT


def test_actions_are_pinned_to_the_same_shas_as_the_0018_rehearsal() -> None:
    reference = (ROOT / ".github/workflows/migration-0018-rehearsal.yml").read_text(
        encoding="utf-8"
    )
    for action in ("actions/checkout@", "actions/setup-python@", "actions/upload-artifact@"):
        pin = reference.split(action, 1)[1].split()[0]
        assert f"{action}{pin}" in TEXT


def test_both_modes_run_and_no_secret_is_referenced() -> None:
    assert "run_scratch.sh /usr/lib/postgresql/16/bin" in TEXT
    assert '"$RUNNER_TEMP/r19-off" migration-0019-commit-ts-off.json off' in TEXT
    assert '"$RUNNER_TEMP/r19-on" migration-0019-commit-ts-on.json on' in TEXT
    for forbidden in ("secrets.", "environment:", "SUPABASE", "DB_URL", "workflow_dispatch"):
        assert forbidden not in TEXT
