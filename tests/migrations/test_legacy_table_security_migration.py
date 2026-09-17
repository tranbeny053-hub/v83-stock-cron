"""Migration 0010 codifies the legacy tables' audited security posture, and does nothing else.

The statements are read from the file itself, comments removed, and compared exactly. The tables and
sequences they name are re-derived from the migrations that created them and from the audit route,
so the lists cannot drift apart.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from scripts import apply_migration_0010 as apply_0010
from scripts import apply_migrations
from scripts import audit_table_privileges as audit

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / apply_0010.MIGRATION
TEXT = PATH.read_text(encoding="utf-8")


def _statements() -> list[str]:
    body = "\n".join(line.split("--", 1)[0] for line in TEXT.splitlines())
    # The DO block is dollar-quoted and holds semicolons of its own: take it out whole first.
    do_block = re.search(r"DO \$\$.*?\$\$;", body, re.S)
    assert do_block is not None
    rest = body[: do_block.start()] + body[do_block.end() :]
    statements = [" ".join(do_block.group(0).split())]
    statements += [" ".join(part.split()) for part in rest.split(";") if part.strip()]
    return statements


def _relations(clause: str) -> list[str]:
    return re.findall(r"public\.([a-z_0-9]+)", clause)


def test_the_file_is_the_reviewed_bytes_and_says_how_it_is_applied() -> None:
    assert hashlib.sha256(PATH.read_bytes()).hexdigest() == apply_0010.MIGRATION_SHA256
    header = TEXT.split("\n\n", 1)[0]
    assert "AUTHORIZED" not in header and "AUTHORED, NOT APPLIED" in header
    assert apply_0010.WORKFLOW in header and apply_0010.SCRIPT in header
    assert "scripts/apply_migrations.py" in header and "must never be used" in header
    assert "35120616278" in header, "the audit run it codifies"


def test_the_legacy_tables_are_exactly_those_the_old_migrations_create_and_the_audit_read() -> None:
    created: set[str] = set()
    for relative in apply_0010.LEGACY_MIGRATIONS:
        created |= set(
            re.findall(
                r"CREATE TABLE IF NOT EXISTS (?:public\.)?([a-z_]+)",
                (ROOT / relative).read_text(encoding="utf-8"),
            )
        )
    assert set(apply_0010.LEGACY_TABLES) == created
    assert apply_0010.LEGACY_TABLES == audit.AUDITED_TABLES
    assert apply_0010.LEGACY_MIGRATIONS == audit.AUDIT_MIGRATIONS


def test_the_serial_sequences_are_exactly_the_bigserial_columns_of_the_old_migrations() -> None:
    serial: set[tuple[str, str]] = set()
    for relative in apply_0010.LEGACY_MIGRATIONS:
        text = (ROOT / relative).read_text(encoding="utf-8")
        for table, body in re.findall(
            r"CREATE TABLE IF NOT EXISTS (?:public\.)?([a-z_]+) \((.*?)\n\);", text, re.S
        ):
            for column in re.findall(r"^\s*([a-z_]+)\s+(?:BIG)?SERIAL\b", body, re.M | re.I):
                serial.add((table, column))
    assert serial == {(table, column) for table, column, _ in apply_0010.LEGACY_SEQUENCES}
    for table, column, sequence in apply_0010.LEGACY_SEQUENCES:
        assert sequence == f"public.{table}_{column}_seq"


def test_the_later_tables_whose_security_is_compared_are_those_later_migrations_create() -> None:
    created: set[str] = set()
    for number in ("0005", "0006", "0008", "0009"):
        (path,) = (ROOT / "migrations").glob(f"{number}_*.sql")
        created |= set(
            re.findall(
                r"CREATE TABLE IF NOT EXISTS (?:public\.)?([a-z_0-9]+)",
                path.read_text(encoding="utf-8"),
            )
        )
    assert set(apply_0010.OTHER_TABLES) == created


def test_the_statements_are_exactly_the_reviewed_four() -> None:
    statements = _statements()
    assert len(statements) == 4, statements
    do_block, revoke_tables, grant_service_role, revoke_sequences = statements

    assert do_block.startswith("DO $$ DECLARE legacy_table text; BEGIN FOREACH legacy_table IN")
    assert re.findall(r"'([a-z_]+)'", do_block.split("LOOP", 1)[0]) == list(
        apply_0010.LEGACY_TABLES
    )
    assert "IF NOT ( SELECT c.relrowsecurity FROM pg_catalog.pg_class AS c" in do_block
    assert (
        "EXECUTE pg_catalog.format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', "
        "legacy_table);" in do_block
    )
    assert do_block.count("EXECUTE") == 1, "the only dynamic statement enables row-level security"

    assert revoke_tables.startswith("REVOKE ALL ON TABLE ")
    assert revoke_tables.endswith(" FROM PUBLIC, anon, authenticated")
    assert _relations(revoke_tables) == list(apply_0010.LEGACY_TABLES)

    assert grant_service_role.startswith(
        "GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLE "
    )
    assert grant_service_role.endswith(" TO service_role")
    assert _relations(grant_service_role) == list(apply_0010.LEGACY_TABLES)
    granted = grant_service_role.split(" ON TABLE", 1)[0].removeprefix("GRANT ").split(", ")
    assert sorted(granted) == list(apply_0010.TABLE_PRIVILEGES)

    assert revoke_sequences.startswith("REVOKE ALL ON SEQUENCE ")
    assert revoke_sequences.endswith(" FROM PUBLIC, anon, authenticated")
    assert ["public." + name for name in _relations(revoke_sequences)] == [
        sequence for _, _, sequence in apply_0010.LEGACY_SEQUENCES
    ]


def test_it_never_takes_anything_from_service_role_or_touches_anything_else() -> None:
    body = " ".join(" ".join(_statements()).split())
    assert "service_role" not in body.split("GRANT SELECT", 1)[0], "nothing is revoked from it"
    for forbidden in (
        "DROP", "POLICY", "OWNER", "FORCE", "DISABLE", "CREATE", "INSERT INTO", "UPDATE public",
        "DELETE FROM", "TRUNCATE public", "DEFAULT PRIVILEGES", "PUBLICATION", "FUNCTION",
        "SET ROLE", "SECURITY DEFINER",
    ):
        assert forbidden not in body, forbidden
    for other in apply_0010.OTHER_TABLES:
        assert other not in body


def test_the_default_bulk_path_would_include_it_so_only_the_route_may_apply_it() -> None:
    paths = sorted((ROOT / "migrations").glob("*.sql"))
    every = [path.name for path in apply_migrations.select_migrations(paths, None)]
    assert PATH.name in every, "the documented hazard: the default path applies every file"
    only = apply_migrations.select_migrations(paths, [PATH.name])
    assert [path.name for path in only] == [PATH.name]
