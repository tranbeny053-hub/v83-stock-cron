"""Applying one migration must not drag an unapplied one with it.

AUDIT FINDING: apply_migrations.py has no ledger. It globs every *.sql and applies them
ALL, so adding 0009 and running the default path would force the deliberately unapplied
0008_analysis_run_details.sql — a T4 that has never been authorized.
"""

from __future__ import annotations

from pathlib import Path

from scripts import apply_migrations

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = sorted((ROOT / "migrations").glob("*.sql"))


def test_the_hazard_is_real_the_default_applies_everything() -> None:
    selected = apply_migrations.select_migrations(MIGRATIONS, None)
    names = [path.name for path in selected]
    assert "0008_analysis_run_details.sql" in names
    assert "0009_section_5a_evaluation_seal.sql" in names


def test_only_applies_exactly_what_is_named() -> None:
    selected = apply_migrations.select_migrations(
        MIGRATIONS, ["0009_section_5a_evaluation_seal.sql"]
    )
    assert [path.name for path in selected] == ["0009_section_5a_evaluation_seal.sql"]


def test_only_never_pulls_in_the_unapplied_0008() -> None:
    selected = apply_migrations.select_migrations(
        MIGRATIONS, ["0009_section_5a_evaluation_seal.sql"]
    )
    assert all("0008" not in path.name for path in selected)


def test_an_unknown_name_is_refused_rather_than_ignored() -> None:
    assert apply_migrations.select_migrations(MIGRATIONS, ["nope.sql"]) is None


def test_default_behaviour_is_unchanged_when_only_is_absent() -> None:
    assert apply_migrations.select_migrations(MIGRATIONS, []) == MIGRATIONS
