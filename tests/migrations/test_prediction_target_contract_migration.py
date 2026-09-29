"""Migration 0011 adds target contract v1's four columns and three checks, and does nothing else.

The statements are read from the file itself, comments removed, and compared exactly. The names,
types and literal values they carry are the apply route's own constants, and the tables the route
compares are re-derived from the migrations that created them, so the lists cannot drift apart.

This runs inside the dispatch job, under the hash-locked runtime: it imports only the standard
library, pytest and the two migration scripts.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from scripts import apply_migration_0011 as apply_0011
from scripts import apply_migrations

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / apply_0011.MIGRATION
TEXT = PATH.read_text(encoding="utf-8")
# How each ADD COLUMN spells its type, and the name pg_catalog.format_type gives that type.
SPELLED_TYPES = {"TEXT": "text", "TIMESTAMPTZ": "timestamp with time zone"}
ADD_COLUMN = re.compile(r"ADD COLUMN IF NOT EXISTS ([a-z_]+) ([A-Z]+)")
# A constraint added only if pg_constraint has none of that name on public.predictions.
GUARDED_CHECK = re.compile(
    r"IF NOT EXISTS \( SELECT 1 FROM pg_catalog\.pg_constraint "
    r"WHERE conname = '(?P<guard>[a-z_]+)' AND conrelid = 'public\.predictions'::regclass \) "
    r"THEN ALTER TABLE public\.predictions ADD CONSTRAINT (?P<name>[a-z_]+) "
    r"CHECK (?P<check>\(.*?\)); END IF;"
)
EARLIER = [path for path in sorted((ROOT / "migrations").glob("*.sql")) if path.name < PATH.name]


def _statements() -> tuple[str, str]:
    """(the DO block, the ALTER TABLE), each with comments removed and whitespace collapsed."""

    body = "\n".join(line.split("--", 1)[0] for line in TEXT.splitlines())
    # The DO block is dollar-quoted and holds semicolons of its own: take it out whole first.
    do_blocks = re.findall(r"DO \$\$.*?\$\$;", body, re.S)
    assert len(do_blocks) == 1, do_blocks
    rest = body.replace(do_blocks[0], "")
    others = [" ".join(part.split()) for part in rest.split(";") if part.strip()]
    assert len(others) == 1, others
    return " ".join(do_blocks[0].split()), others[0]


def test_the_file_is_the_reviewed_bytes_and_says_how_it_is_applied() -> None:
    assert hashlib.sha256(PATH.read_bytes()).hexdigest() == apply_0011.MIGRATION_SHA256
    header = TEXT.split("\n\n", 1)[0]
    assert all(line.startswith("--") for line in header.splitlines()), "one comment block"
    assert "AUTHORIZED" not in header and "AUTHORED, NOT APPLIED" in header
    assert apply_0011.WORKFLOW in header and apply_0011.SCRIPT in header
    assert "scripts/apply_migrations.py" in header and "must never be used" in header
    assert "T4" in header and "ONCE" in header


def test_the_statements_are_one_alter_table_and_one_guarded_do_block() -> None:
    do_block, alter_table = _statements()

    prefix = "ALTER TABLE public.predictions "
    assert alter_table.startswith(prefix)
    clauses = alter_table.removeprefix(prefix).split(", ")
    assert [ADD_COLUMN.fullmatch(clause) is not None for clause in clauses] == [True] * 4, clauses
    added = [ADD_COLUMN.fullmatch(clause).groups() for clause in clauses]
    assert [(name, SPELLED_TYPES[spelled]) for name, spelled in added] == list(
        apply_0011.NEW_COLUMNS
    )

    guarded = list(GUARDED_CHECK.finditer(do_block))
    assert [match["name"] for match in guarded] == list(apply_0011.NEW_CONSTRAINTS)
    for match in guarded:
        assert match["guard"] == match["name"], "each guard looks for its own constraint"
    assert " ".join(GUARDED_CHECK.sub("", do_block).split()) == "DO $$ BEGIN END; $$;", (
        "the DO block holds the three guarded checks and nothing else"
    )


@pytest.mark.parametrize("name", list(apply_0011.NEW_CONSTRAINTS))
def test_each_check_names_exactly_its_columns_and_literal_values(name: str) -> None:
    do_block, _ = _statements()
    (check,) = [
        match["check"] for match in GUARDED_CHECK.finditer(do_block) if match["name"] == name
    ]
    columns, literals = apply_0011.NEW_CONSTRAINTS[name]
    assert apply_0011.constraint_literals(check) == literals
    identifiers = set(re.findall(r"\b[a-z_]+\b", re.sub(r"'[^']*'", "''", check)))
    assert sorted(identifiers) == list(columns), identifiers
    assert set(columns) <= set(apply_0011.NEW_COLUMN_NAMES)


def test_the_stamp_check_allows_only_unstamped_or_fully_stamped_rows_in_time_order() -> None:
    do_block, _ = _statements()
    (check,) = [
        match["check"]
        for match in GUARDED_CHECK.finditer(do_block)
        if match["name"] == "predictions_target_stamp_chk"
    ]
    names = apply_0011.NEW_COLUMN_NAMES
    unstamped = " AND ".join(f"{name} IS NULL" for name in names)
    stamped = " AND ".join(f"{name} IS NOT NULL" for name in names)
    assert check == (
        f"( ( {unstamped} ) OR ( {stamped} AND core_computed_at_utc <= issued_at_utc ) )"
    )


FORBIDDEN = (
    "DROP", "UPDATE", "DELETE", "INSERT", "TRUNCATE", "GRANT", "REVOKE", "POLICY", "OWNER",
    "INDEX", "TRIGGER", "FUNCTION", "DEFAULT", "SET ROLE", "SECURITY DEFINER",
)


def test_it_touches_nothing_else() -> None:
    do_block, alter_table = _statements()
    body = f"{alter_table} {do_block}"
    for word in FORBIDDEN:
        assert not re.search(rf"\b{word}\b", body, re.I), word
    assert "predicted_at_utc" not in body, "the existing timestamp keeps its meaning"
    for clause in alter_table.split(", "):
        assert "NOT NULL" not in clause.upper(), clause
    assert set(re.findall(r"public\.([a-z_0-9]+)", body)) == {apply_0011.TABLE}


def test_the_other_tables_are_every_table_of_migrations_0001_0009_but_predictions() -> None:
    created: set[str] = set()
    for number in range(1, 10):
        (path,) = (ROOT / "migrations").glob(f"{number:04d}_*.sql")
        created |= set(
            re.findall(
                r"CREATE TABLE (?:IF NOT EXISTS )?(?:public\.)?([a-z_0-9]+)",
                path.read_text(encoding="utf-8"),
            )
        )
    assert apply_0011.TABLE in created
    assert apply_0011.OTHER_TABLES == tuple(sorted(created - {apply_0011.TABLE}))


def test_no_earlier_migration_names_a_new_column_or_constraint() -> None:
    assert [path.name[:4] for path in EARLIER] == [f"{number:04d}" for number in range(1, 11)]
    for path in EARLIER:
        text = path.read_text(encoding="utf-8")
        for name in (*apply_0011.NEW_COLUMN_NAMES, *apply_0011.NEW_CONSTRAINTS):
            assert name not in text, (path.name, name)


def test_the_default_bulk_path_would_include_it_so_only_the_route_may_apply_it() -> None:
    paths = sorted((ROOT / "migrations").glob("*.sql"))
    every = [path.name for path in apply_migrations.select_migrations(paths, None)]
    assert PATH.name in every, "the documented hazard: the default path applies every file"
    only = apply_migrations.select_migrations(paths, [PATH.name])
    assert [path.name for path in only] == [PATH.name]
