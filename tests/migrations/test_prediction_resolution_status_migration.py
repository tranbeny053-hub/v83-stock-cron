"""Migration 0012 creates the resolution-status table of policy rq-v1, and does nothing else.

The statements are read from the file itself, comments removed, and compared exactly. The table's
columns, constraints and index are parsed from its CREATE statements and must be the apply route's
own constants, and the tables the route compares are re-derived from the migrations that created
them, so the lists cannot drift apart.

This runs inside the dispatch job, under the hash-locked runtime: it imports only the standard
library, pytest and the migration scripts.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from scripts import apply_migration_0011 as apply_0011
from scripts import apply_migration_0012 as apply_0012
from scripts import apply_migrations

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / apply_0012.MIGRATION
TEXT = PATH.read_text(encoding="utf-8")
TABLE = f"public.{apply_0012.TABLE}"
RETRY_IDX = "prediction_resolution_status_retry_idx"
# How the file spells each type, and the name pg_catalog.format_type gives that type.
SPELLED_TYPES = {"TEXT": "text", "INTEGER": "integer", "TIMESTAMPTZ": "timestamp with time zone"}
COLUMN = re.compile(
    r"(?P<name>[a-z_]+) (?P<type>[A-Z]+)(?P<not_null> NOT NULL)?(?: DEFAULT (?P<default>.+))?"
)
CONSTRAINT = re.compile(
    r"CONSTRAINT (?P<name>[a-z_]+) (?P<kind>PRIMARY KEY|CHECK) (?P<body>\(.*\))"
)
INDEX = re.compile(
    r"CREATE (?P<unique>UNIQUE )?INDEX IF NOT EXISTS (?P<name>[a-z_]+) "
    rf"ON {re.escape(TABLE)} \((?P<columns>[a-z_, ]+)\) WHERE (?P<predicate>.+)"
)
KINDS = {"PRIMARY KEY": "p", "CHECK": "c"}
_LITERAL = re.compile(r"'(?:[^']|'')*'")
EARLIER = [path for path in sorted((ROOT / "migrations").glob("*.sql")) if path.name < PATH.name]


def _statements() -> list[str]:
    """Every statement, with comments removed and whitespace collapsed."""

    body = "\n".join(line.split("--", 1)[0] for line in TEXT.splitlines())
    return [" ".join(part.split()) for part in body.split(";") if part.strip()]


def _split_top_level(text: str) -> list[str]:
    """``text`` split at its commas outside parentheses and quoted literals."""

    parts: list[str] = []
    current: list[str] = []
    depth = 0
    quoted = False
    for char in text:
        if char == "'":
            quoted = not quoted
        elif not quoted and char == "(":
            depth += 1
        elif not quoted and char == ")":
            depth -= 1
        if char == "," and depth == 0 and not quoted:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    parts.append("".join(current).strip())
    assert depth == 0 and not quoted, text
    return parts


def _table_elements() -> list[str]:
    """The column and constraint definitions of the CREATE TABLE, in the file's order."""

    create_table = _statements()[0]
    prefix = f"CREATE TABLE IF NOT EXISTS {TABLE} ("
    assert create_table.startswith(prefix) and create_table.endswith(")"), create_table
    return _split_top_level(create_table.removeprefix(prefix)[:-1].strip())


def _columns() -> list[tuple[str, str, bool, str | None]]:
    parsed = []
    for element in _table_elements():
        if element.startswith("CONSTRAINT "):
            continue
        match = COLUMN.fullmatch(element)
        assert match is not None, element
        parsed.append(
            (
                match["name"],
                SPELLED_TYPES[match["type"]],
                match["not_null"] is not None,
                match["default"],
            )
        )
    return parsed


def _constraints() -> list[tuple[str, str, str]]:
    """(name, contype, the parenthesized body) of every table constraint, in the file's order."""

    parsed = []
    for element in _table_elements():
        if not element.startswith("CONSTRAINT "):
            continue
        match = CONSTRAINT.fullmatch(element)
        assert match is not None, element
        parsed.append((match["name"], KINDS[match["kind"]], match["body"]))
    return parsed


def _identifiers(body: str) -> list[str]:
    """The column names a body reads: lowercase words, but not the functions it calls."""

    return re.findall(r"\b([a-z_][a-z0-9_]*)\b(?!\s*\()", _LITERAL.sub("''", body))


def test_the_file_is_the_reviewed_bytes_and_says_how_it_is_applied() -> None:
    assert hashlib.sha256(PATH.read_bytes()).hexdigest() == apply_0012.MIGRATION_SHA256
    header = TEXT.split("\n\n", 1)[0]
    assert all(line.startswith("--") for line in header.splitlines()), "one comment block"
    assert "AUTHORIZED" not in header and "AUTHORED, NOT APPLIED" in header
    assert apply_0012.WORKFLOW in header and apply_0012.SCRIPT in header
    assert "scripts/apply_migrations.py" in header and "must never be used" in header
    assert "T4" in header and "ONCE" in header


def test_the_statements_are_the_table_its_index_its_security_and_nothing_else() -> None:
    statements = _statements()
    assert len(statements) == 5, statements
    create_table, create_index, enable_rls, revoke_public, revoke_api_roles = statements
    assert create_table.startswith(f"CREATE TABLE IF NOT EXISTS {TABLE} (")
    assert create_index.startswith(f"CREATE INDEX IF NOT EXISTS {RETRY_IDX} ON {TABLE} (")
    assert enable_rls == f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY"
    assert revoke_public == f"REVOKE ALL ON TABLE {TABLE} FROM PUBLIC"
    assert revoke_api_roles == (
        f"REVOKE ALL ON TABLE {TABLE} FROM {', '.join(apply_0012.API_ROLES)}"
    )


def test_the_columns_are_the_route_s_expected_columns() -> None:
    elements = _table_elements()
    assert len(elements) == 13 + 9, elements
    assert [element.startswith("CONSTRAINT ") for element in elements] == [False] * 13 + [True] * 9
    assert tuple(_columns()) == apply_0012.EXPECTED_COLUMNS


def test_the_constraints_are_the_route_s_expected_constraints() -> None:
    parsed = {}
    for name, kind, body in _constraints():
        if kind == "p":
            columns = tuple(sorted(body.strip("()").split(", ")))
        else:
            columns = tuple(sorted(set(_identifiers(body))))
        parsed[name] = (kind, columns, apply_0012.constraint_literals(body))
    assert list(parsed) == list(apply_0012.EXPECTED_CONSTRAINTS), "in the file's order"
    assert parsed == dict(apply_0012.EXPECTED_CONSTRAINTS)
    for _, columns, _ in parsed.values():
        assert set(columns) <= set(apply_0012.EXPECTED_COLUMN_NAMES)


def _single_literal(name: str) -> str:
    (literal,) = apply_0012.EXPECTED_CONSTRAINTS[name][2]
    return literal


def _state_shape() -> str:
    """Each status carries exactly its own timestamp, and neither of the other two."""

    own = {
        "RETRYABLE": "next_eligible_utc",
        "QUARANTINED": "quarantined_at_utc",
        "RESOLVED": "resolved_at_utc",
    }
    branches = [
        "("
        + " AND ".join(
            [
                f"resolution_status = '{status}'",
                *(
                    f"{column} IS {'NOT ' if column == timestamp else ''}NULL"
                    for column in own.values()
                ),
            ]
        )
        + ")"
        for status, timestamp in own.items()
    ]
    return "( " + " OR ".join(branches) + ")"


def test_each_check_says_exactly_what_the_owner_accepted() -> None:
    reason = _single_literal("prs_reason_format")
    policy = _single_literal("prs_policy_version_format")
    statuses = ", ".join(f"'{status}'" for status in ("RETRYABLE", "QUARANTINED", "RESOLVED"))
    assert {name: body for name, kind, body in _constraints() if kind == "c"} == {
        "prs_prediction_id_nonblank": "(btrim(prediction_id) <> '')",
        "prs_status_valid": f"(resolution_status IN ({statuses}))",
        "prs_attempt_count_positive": "(attempt_count >= 1)",
        "prs_attempt_chronology": "(last_attempt_utc >= first_attempt_utc)",
        "prs_reason_format": f"( first_reason ~ '{reason}' AND last_reason ~ '{reason}')",
        "prs_policy_version_format": f"(policy_version ~ '{policy}')",
        "prs_resolver_version_nonblank": "(btrim(resolver_version) <> '')",
        "prs_state_shape": _state_shape(),
    }
    assert [(name, body) for name, kind, body in _constraints() if kind == "p"] == [
        ("prediction_resolution_status_pkey", "(prediction_id)")
    ]


def test_the_index_is_the_route_s_retry_index() -> None:
    match = INDEX.fullmatch(_statements()[1])
    assert match is not None, _statements()[1]
    assert match["name"] == RETRY_IDX
    unique, columns, literals = apply_0012.EXPECTED_INDEXES[RETRY_IDX]
    assert (match["unique"] is not None) is unique is False
    assert match["columns"].split(", ") == list(columns)
    assert apply_0012.constraint_literals(match["predicate"]) == literals
    assert apply_0012.PREDICATE_COLUMN in _identifiers(match["predicate"])
    assert match["predicate"] == "resolution_status = 'RETRYABLE'"
    # The other index is the primary key's, named after its constraint; together with the table
    # they are every relation the statements name.
    assert set(apply_0012.EXPECTED_INDEXES) == {RETRY_IDX, "prediction_resolution_status_pkey"}
    assert "prediction_resolution_status_pkey" in apply_0012.EXPECTED_CONSTRAINTS
    assert apply_0012.RELATION_NAMES == (apply_0012.TABLE, *sorted(apply_0012.EXPECTED_INDEXES))


FORBIDDEN = (
    "GRANT", "POLICY", "REFERENCES", "FOREIGN", "DROP", "FORCE", "FUNCTION", "TRIGGER", "OWNER",
    "INSERT", "UPDATE", "DELETE", "TRUNCATE", "SET ROLE", "SECURITY DEFINER", "predictions",
)


@pytest.mark.parametrize("word", FORBIDDEN)
def test_it_touches_nothing_else(word: str) -> None:
    body = " ".join(_statements())
    assert not re.search(rf"\b{word}\b", body, re.I), word


def test_it_names_no_relation_but_its_own() -> None:
    body = " ".join(_statements())
    assert set(re.findall(r"public\.([a-z_0-9]+)", body)) == {apply_0012.TABLE}
    assert "REFERENCES" not in body.upper(), "no foreign key, so no lock on any existing table"


def test_the_existing_tables_are_every_table_of_migrations_0001_0009() -> None:
    created: set[str] = set()
    for number in range(1, 10):
        (path,) = (ROOT / "migrations").glob(f"{number:04d}_*.sql")
        created |= set(
            re.findall(
                r"CREATE TABLE (?:IF NOT EXISTS )?(?:public\.)?([a-z_0-9]+)",
                path.read_text(encoding="utf-8"),
            )
        )
    assert apply_0012.EXISTING_TABLES == tuple(sorted(created))
    assert len(created) == 14 and "predictions" in created
    for number in (10, 11):
        (path,) = (ROOT / "migrations").glob(f"{number:04d}_*.sql")
        assert "CREATE TABLE" not in path.read_text(encoding="utf-8"), path.name


def test_the_0011_columns_it_records_are_0011_s_own() -> None:
    assert apply_0012.MIGRATION_0011_COLUMNS == tuple(name for name, _ in apply_0011.NEW_COLUMNS)
    assert apply_0012.MIGRATION_0011_COLUMNS == apply_0011.NEW_COLUMN_NAMES


def test_no_earlier_migration_names_the_table_its_indexes_or_its_constraints() -> None:
    assert [path.name[:4] for path in EARLIER] == [f"{number:04d}" for number in range(1, 12)]
    names = (*apply_0012.RELATION_NAMES, *apply_0012.EXPECTED_CONSTRAINTS)
    for path in EARLIER:
        text = path.read_text(encoding="utf-8")
        for name in names:
            assert name not in text, (path.name, name)


def test_the_default_bulk_path_would_include_it_so_only_the_route_may_apply_it() -> None:
    paths = sorted((ROOT / "migrations").glob("*.sql"))
    every = [path.name for path in apply_migrations.select_migrations(paths, None)]
    assert PATH.name in every, "the documented hazard: the default path applies every file"
    only = apply_migrations.select_migrations(paths, [PATH.name])
    assert [path.name for path in only] == [PATH.name]
