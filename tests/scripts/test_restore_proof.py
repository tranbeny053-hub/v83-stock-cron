"""The structure-first restore proof (plan §12.1, §23 "Backup"; owner ruling DP-D=2), offline.

What a database is not needed for, checked here:
- the export gate refuses, at the first sight and without echoing it, a data entry, a COPY block, a
  password clause or hash, any psql meta-command but the \\restrict pair, a statement that is not
  schema or role DDL, a SET that is not one of pg_dump's own lines, the wrong pg_dump major, and a
  file that is not the owner's (its digest);
- its scanner splits a psql script by psql's own lexing rules (psqlscan.l): nothing inside a quoted
  string, a quoted identifier, a dollar-quoted body or a comment is taken for a statement or a
  meta-command, a dollar quote starts exactly where psql starts one, and whatever psql would lex
  by a state the scanner does not model (an escape string, a psql variable, a NUL) is refused,
  but for the escape strings pg_dumpall itself writes for a role's setting, comment or security
  label, which pass in the roles file only and split exactly where psql splits them;
- the comparison classifies exactly: the owner's documented LOGIN steps are operational; every
  privilege path into the app (through an API role, the owner or a migration role) is app; the
  platform's own roles, settings, memberships and default privileges are platform; a setting's
  value is compared by its digest and never shown;
- the owner's exact managed-platform exceptions (owner rulings DP-D-FINDINGS and
  DP-D-STORAGE-SETTINGS) are exactly the nine ruled differences, and against the same production
  without them they let nothing else pass; each is accepted only as ruled: the same membership with
  other options, a look-alike or another role, another predefined role, one more, one fewer or
  another setting value, the ruled settings elsewhere, the owner's grants with grant option, from
  another grantor, beside another grantee or under another key, CREATE on the schema, an item
  removed or doubled: each stays app and fails the proof; and an accepted membership passes its
  reach on: whoever holds a ruled member is app, and Storage's role, which may act as an API role,
  is one (any role it gains, any setting but timeouts alone or exactly its two ruled ones, any
  parameter grant); a role name that could be misread is app;
- the restore errors are classified: the two every restore raises are expected, a platform role's
  own setting (an API role's timeout) is platform, anything else fails, and a refused value is not
  repeated;
- the proof refuses before any server starts, and refuses an export that would take superuser from
  the bootstrap role or that names the owner as the bootstrap; it sees no PG* variable of the
  caller's, psql reads UTF-8, and a stopped cluster leaves no log;
- the migration roles come from the migration files, and the card's commands are the rehearsal's.
The database half runs in .github/workflows/restore-proof-rehearsal.yml (rehearse.py).
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from scripts.restore_proof import catalog, gate, prove, rehearse, scratch

ROOT = Path(__file__).resolve().parents[2]
CARD = (ROOT / "docs/runbooks/RESTORE_PROOF_EXPORT.md").read_text(encoding="utf-8")
MIGRATION = catalog.migration_roles(ROOT / "migrations")
KEY = "Abc123restrictKey"
SCHEMA = f"""--
-- PostgreSQL database dump
--

\\restrict {KEY}

-- Dumped from database version 17.6
-- Dumped by pg_dump version 17.6

SET statement_timeout = 0;
SELECT pg_catalog.set_config('search_path', '', false);

--
-- Name: f(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.f() RETURNS trigger
    LANGUAGE plpgsql
    AS $_$
BEGIN
-- a COPY from stdin; mention, and; semicolons
INSERT INTO public.t VALUES (1);
\\! not a meta-command inside a body
    RAISE EXCEPTION 'it''s; refused';
END;
$_$;

CREATE TABLE public."t;x" (id integer DEFAULT 1);
COMMENT ON TABLE public."t;x" IS 'a '' quote; and -- no comment';
/* a /* nested */ comment; */
GRANT SELECT ON TABLE public."t;x" TO anon;

\\unrestrict {KEY}
"""
ROLES = f"""--
-- PostgreSQL database cluster dump
--

\\restrict {KEY}

SET default_transaction_read_only = off;

CREATE ROLE anon;
ALTER ROLE anon WITH NOSUPERUSER NOINHERIT NOLOGIN;
CREATE ROLE supabase_admin;
ALTER ROLE supabase_admin WITH SUPERUSER INHERIT CREATEROLE CREATEDB LOGIN REPLICATION BYPASSRLS;
ALTER ROLE anon SET statement_timeout TO '3s';
GRANT anon TO authenticator WITH INHERIT FALSE GRANTED BY supabase_admin;

\\unrestrict {KEY}
"""


def kinds(refusals: list[gate.Refusal]) -> list[str]:
    return [item.kind for item in refusals]


def schema_with(old: str, new: str) -> bytes:
    assert old in SCHEMA
    return SCHEMA.replace(old, new, 1).encode()


def roles_with(old: str, new: str) -> bytes:
    assert old in ROLES
    return ROLES.replace(old, new, 1).encode()


# --------------------------------------------------------------------------- the gate
def test_the_card_export_passes_and_is_described() -> None:
    schema, refusals = gate.check_schema_dump("schema.sql", SCHEMA.encode())
    assert refusals == []
    assert (schema.tool_major, schema.tool_minor, schema.server_major) == (17, 6, 17)
    assert schema.sha256 == hashlib.sha256(SCHEMA.encode()).hexdigest()
    roles, refusals = gate.check_roles_dump("roles.sql", ROLES.encode())
    assert refusals == [] and roles.bytes == len(ROLES.encode())


@pytest.mark.parametrize(
    "line",
    [
        "-- Data for Name: t; Type: TABLE DATA; Schema: public; Owner: postgres",
        "-- Name: s; Type: SEQUENCE SET; Schema: public; Owner: postgres",
        "-- Name: blobs; Type: BLOBS; Schema: -; Owner: -",
        "COPY public.t (id) FROM stdin;",
        "\\.",
    ],
    ids=["table data", "sequence set", "blobs", "copy", "copy terminator"],
)
def test_data_is_refused_at_its_first_sight(line: str) -> None:
    raw = schema_with("SET statement_timeout = 0;", f"{line}\nSET statement_timeout = 0;")
    _, refusals = gate.check_schema_dump("schema.sql", raw)
    assert refusals == [gate.Refusal("schema.sql", 10, "DATA_ENTRY")], "one, at its line, then stop"


def test_a_data_look_alike_inside_a_body_is_still_refused() -> None:
    """The data scan runs before any lexing, so it never reads past a data marker: a function
    line that looks exactly like a COPY block is refused too. That is safe: a refusal, never a
    load."""

    raw = schema_with("BEGIN\n", "BEGIN\nCOPY public.t (id) FROM stdin;\n")
    _, refusals = gate.check_schema_dump("schema.sql", raw)
    assert kinds(refusals) == ["DATA_ENTRY"]


@pytest.mark.parametrize(
    ("line", "kind"),
    [
        ("INSERT INTO public.t VALUES (1);", "STATEMENT_INSERT"),
        ("UPDATE public.t SET id = 2;", "STATEMENT_UPDATE"),
        ("DO $$ BEGIN NULL; END $$;", "STATEMENT_DO"),
        ("SELECT pg_catalog.setval('public.s', 42, true);", "STATEMENT_SELECT"),
        ("DROP TABLE public.t;", "STATEMENT_DROP"),
    ],
)
def test_only_schema_ddl_is_allowed(line: str, kind: str) -> None:
    raw = schema_with("GRANT SELECT", f"{line}\nGRANT SELECT")
    _, refusals = gate.check_schema_dump("schema.sql", raw)
    assert kinds(refusals) == [kind]


def test_a_meta_command_is_refused_and_its_text_never_kept() -> None:
    raw = schema_with("SET statement_timeout", "\\! touch /tmp/pwned\nSET statement_timeout")
    _, refusals = gate.check_schema_dump("schema.sql", raw)
    assert refusals == [gate.Refusal("schema.sql", 10, "META_COMMAND")]
    assert "pwned" not in repr(refusals)


@pytest.mark.parametrize(
    ("old", "new", "kind"),
    [
        (f"\\restrict {KEY}\n", "", "RESTRICT_PAIR_MISSING"),
        (f"\\unrestrict {KEY}\n", "", "RESTRICT_PAIR_MISSING"),
        (f"\\unrestrict {KEY}", "\\unrestrict another", "RESTRICT_KEY_MISMATCH"),
        (f"\\unrestrict {KEY}", f"\\unrestrict {KEY}\u00a0", "RESTRICT_KEY_MISMATCH"),
        ("--\n-- PostgreSQL database dump", "SET a = 1;\n--\n-- PostgreSQL database dump", None),
    ],
    ids=[
        "no restrict",
        "no unrestrict",
        "another key",
        "a key with a no-break space, which psql keeps in it",
        "a statement before restrict",
    ],
)
def test_the_restrict_pair_frames_every_statement(old: str, new: str, kind: str | None) -> None:
    _, refusals = gate.check_schema_dump("schema.sql", schema_with(old, new))
    assert kind in kinds(refusals) if kind else "STATEMENT_OUTSIDE_RESTRICT" in kinds(refusals)


def test_another_pg_dump_major_and_non_text_are_refused() -> None:
    _, refusals = gate.check_schema_dump(
        "schema.sql", schema_with("pg_dump version 17.6", "pg_dump version 16.10")
    )
    assert kinds(refusals) == ["NOT_PG_DUMP_17"]
    _, refusals = gate.check_schema_dump("schema.sql", b"\xff\xfe not text")
    assert kinds(refusals) == ["NOT_UTF8_TEXT"]


@pytest.mark.parametrize(
    ("line", "kind"),
    [
        ("ALTER ROLE ucpe_resolver WITH LOGIN PASSWORD 'secret-value';", "PASSWORD_CLAUSE"),
        ("ALTER ROLE ucpe_resolver WITH LOGIN password NULL;", "PASSWORD_CLAUSE"),
        ("-- SCRAM-SHA-256$4096:c2FsdA==$c3RvcmVk:c2VydmVy", "PASSWORD_HASH"),
        ("-- md5" + "0123456789abcdef" * 2, "PASSWORD_HASH"),
    ],
    ids=["clause", "null clause", "scram verifier", "md5 hash"],
)
def test_a_password_is_refused_at_first_sight_and_never_echoed(line: str, kind: str) -> None:
    raw = roles_with("CREATE ROLE anon;", f"{line}\nCREATE ROLE anon;")
    _, refusals = gate.check_roles_dump("roles.sql", raw)
    assert refusals == [gate.Refusal("roles.sql", 9, kind)]
    assert "secret-value" not in repr(refusals) and "c3RvcmVk" not in repr(refusals)


def test_a_setting_named_password_is_not_a_password() -> None:
    raw = roles_with(
        "ALTER ROLE anon SET",
        "ALTER ROLE anon SET password_encryption TO 'scram-sha-256';\nALTER ROLE anon SET",
    )
    _, refusals = gate.check_roles_dump("roles.sql", raw)
    assert refusals == []


@pytest.mark.parametrize(
    ("line", "kind"),
    [
        ("CREATE TABLE public.t (id int);", "STATEMENT_CREATE_TABLE"),
        ("ALTER TABLE public.t OWNER TO anon;", "STATEMENT_ALTER_TABLE"),
        ("INSERT INTO public.t VALUES (1);", "STATEMENT_INSERT"),
    ],
)
def test_the_roles_file_holds_role_ddl_only(line: str, kind: str) -> None:
    _, refusals = gate.check_roles_dump(
        "roles.sql", roles_with("GRANT anon", f"{line}\nGRANT anon")
    )
    assert kinds(refusals) == [kind]


@pytest.mark.parametrize(
    "line",
    ["COMMENT ON ROLE anon IS 'the public API role';", "SECURITY LABEL FOR x ON ROLE anon IS 'y';"],
    ids=["role comment", "security label"],
)
def test_what_pg_dumpall_writes_for_a_role_passes(line: str) -> None:
    _, refusals = gate.check_roles_dump(
        "roles.sql", roles_with("GRANT anon", f"{line}\nGRANT anon")
    )
    assert refusals == []


def test_a_comment_on_anything_but_a_role_is_refused_in_the_roles_file() -> None:
    raw = roles_with("GRANT anon", "COMMENT ON TABLE public.t IS 'x';\nGRANT anon")
    _, refusals = gate.check_roles_dump("roles.sql", raw)
    assert kinds(refusals) == ["STATEMENT_COMMENT_TABLE"]


def test_a_grant_by_another_role_passes_as_pg_dump_writes_it() -> None:
    """pg_dump frames a grant made by a role other than the owner in SET/RESET SESSION
    AUTHORIZATION (review 1 of DP-D, finding 4)."""

    framed = "SET SESSION AUTHORIZATION ucpe_resolver;\nGRANT SELECT"
    raw = schema_with("GRANT SELECT", framed).replace(
        b"TO anon;\n", b"TO anon;\nRESET SESSION AUTHORIZATION;\n", 1
    )
    _, refusals = gate.check_schema_dump("schema.sql", raw)
    assert refusals == []


def test_a_roles_file_must_be_a_pg_dumpall_cluster_dump() -> None:
    raw = roles_with("-- PostgreSQL database cluster dump", "-- something else")
    _, refusals = gate.check_roles_dump("roles.sql", raw)
    assert kinds(refusals) == ["NOT_A_PG_DUMPALL_ROLES_DUMP"]


def test_the_export_folder_holds_two_regular_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert kinds(gate.check_export(tmp_path).refusals) == ["MISSING_OR_NOT_A_REGULAR_FILE"] * 2
    (tmp_path / "real.sql").write_text(SCHEMA, encoding="utf-8")
    (tmp_path / "schema.sql").symlink_to(tmp_path / "real.sql")
    (tmp_path / "roles.sql").write_text(ROLES, encoding="utf-8")
    assert kinds(gate.check_export(tmp_path).refusals) == ["MISSING_OR_NOT_A_REGULAR_FILE"]
    (tmp_path / "schema.sql").unlink()
    (tmp_path / "schema.sql").write_text(SCHEMA, encoding="utf-8")
    assert gate.check_export(tmp_path).passed
    monkeypatch.setattr(gate, "MAX_BYTES", 100)
    assert kinds(gate.check_export(tmp_path).refusals) == ["TOO_LARGE_FOR_A_STRUCTURE_EXPORT"] * 2


def test_the_scanner_splits_by_psqls_rules() -> None:
    statements, metas, hazards = gate.scan(SCHEMA)
    # Six statements: no split inside the quoted identifier "t;x", the string's "; and --" and
    # doubled quote, the nested comment or the dollar-quoted body (whose INSERT and backslash line
    # are not top level).
    assert [lead[:3] for _, lead in statements] == [
        ("SET", "STATEMENT_TIMEOUT"),
        ("SELECT", "PG_CATALOG", "SET_CONFIG"),
        ("CREATE", "FUNCTION", "PUBLIC"),
        ("CREATE", "TABLE", "PUBLIC"),
        ("COMMENT", "ON", "TABLE"),
        ("GRANT", "SELECT", "ON"),
    ]
    assert [(command, argument) for _, command, argument in metas] == [
        ("restrict", KEY),
        ("unrestrict", KEY),
    ]
    assert hazards == []


@pytest.mark.parametrize(
    ("text", "commands"),
    [
        ("CREATE TABLE t (a int DEFAULT 1$$ \\! x $$);", []),
        ("CREATE TABLE t (a int DEFAULT 1.5$$ \\! x $$);", []),
        ("CREATE TABLE x$$ \\! y $$;", ["!"]),
        ("CREATE TABLE x$a$ \\! y $a$;", ["!"]),
        ("CREATE TABLE t (a int DEFAULT 1_0$$ \\! y $$);", ["!"]),
        ("CREATE TABLE \u00e9$$ \\! y $$;", ["!"]),
        ("CREATE TABLE \u2014$$ \\! y $$;", ["!"]),
        ("CREATE TABLE \u00a0$$ \\! y $$;", ["!"]),
        ("CREATE TABLE t (a int DEFAULT $1$$ \\! y $$);", []),
        ("CREATE TABLE t (a int DEFAULT $\u2014$ \\! y $\u2014$);", []),
    ],
    ids=[
        "after a number",
        "after a decimal",
        "inside an identifier",
        "a tag inside an identifier",
        "after a number with trailing letters",
        "after a non-ASCII letter",
        "after a non-ASCII symbol",
        "after a no-break space",
        "after a parameter",
        "a non-ASCII tag",
    ],
)
def test_a_dollar_quote_starts_exactly_where_psql_starts_one(text: str, commands: list) -> None:
    """Review 2 of DP-D, finding 3: psql reads every non-ASCII character as an identifier
    character (and a no-break space is one, not a space), and an identifier takes its "$"; a "$"
    on its own after a number or a parameter starts a dollar quote. A meta-command outside a quote
    is seen, and one inside is not, exactly as psql would run or skip it."""

    assert [command for _, command, _ in gate.scan(text)[1]] == commands


@pytest.mark.parametrize(
    ("statement", "hazards"),
    [
        ("COMMENT ON TABLE public.t IS E'x';", ["ESCAPE_STRING"]),
        ("COMMENT ON TABLE public.t IS e'x';", ["ESCAPE_STRING"]),
        ("ALTER TABLE public.t ALTER a SET DEFAULT (E'x');", ["ESCAPE_STRING"]),
        ("ALTER TABLE public.t ALTER a SET DEFAULT :LAST_ERROR_MESSAGE;", ["PSQL_VARIABLE"]),
        ("ALTER TABLE public.t ALTER a SET DEFAULT :'ENCODING';", ["PSQL_VARIABLE"]),
        ('ALTER TABLE public.t ALTER a SET DEFAULT :"USER";', ["PSQL_VARIABLE"]),
        ("ALTER TABLE public.t ALTER a SET DEFAULT :{?ENCODING};", ["PSQL_VARIABLE"]),
        ("ALTER TABLE public.t ALTER a SET DEFAULT :::text;", ["PSQL_VARIABLE"]),
        ("ALTER TABLE public.t ALTER a SET DEFAULT 'x'::text;", []),
        ("ALTER TABLE public.t ALTER a SET DEFAULT (ARRAY[1, 2])[1:2];", []),
        ("COMMENT ON TABLE public.t IS 'E'':x';", []),
    ],
    ids=[
        "an escape string",
        "a lower-case one",
        "one after a parenthesis",
        "a variable",
        "a quoted variable",
        "an identifier variable",
        "a variable test",
        "a variable after a cast",
        "a cast",
        "a slice",
        "inside a string",
    ],
)
def test_what_psql_would_lex_by_a_state_of_its_own_is_refused(
    statement: str, hazards: list[str]
) -> None:
    """psql reads backslashes in an escape string and substitutes a variable's value and lexes it
    again, so neither is guessed at; pg_dump writes neither at the top level."""

    raw = schema_with("GRANT SELECT", f"{statement}\nGRANT SELECT")
    _, refusals = gate.check_schema_dump("schema.sql", raw)
    assert kinds(refusals) == hazards


# Owner ruling DP-D-ESCAPE=A. pg_dumpall 17's own lines for literals that hold a backslash
# (appendStringLiteralConn), as the PostgreSQL 17 tools wrote them for synthetic roles: " E'", every
# backslash and quote doubled, then ";" or ",". The database half (pg_dumpall writes them, psql
# lexes them as the gate does, the server reads the same values) is rehearse.py's.
PG_DUMPALL_ESCAPE_STRINGS = {
    "a comment": r"COMMENT ON ROLE anon IS E'C:\\path ''q'' \\\\ end';",
    "a comment over two lines": "COMMENT ON ROLE anon IS E'line1\n"
    + r"line2 \\ tab"
    + "\t"
    + r";\\! x --y /*z :v $$';",
    "a setting": r"ALTER ROLE anon SET application_name TO E'a\\b';",
    "a list setting": r"""ALTER ROLE anon SET search_path TO E'a\\b', 'public', 'we"ird';""",
    "a quoted setting": r"""ALTER ROLE anon SET "app.q" TO E'it''s \\ here';""",
    "a quoted role's setting": r"""ALTER ROLE "an;on" SET application_name TO E'a\\b';""",
    "a security label": r"SECURITY LABEL FOR dummy ON ROLE anon IS E'a\\b';",
}


@pytest.mark.parametrize(
    "statement", PG_DUMPALL_ESCAPE_STRINGS.values(), ids=PG_DUMPALL_ESCAPE_STRINGS.keys()
)
def test_the_escape_strings_pg_dumpall_writes_pass_in_the_roles_file(statement: str) -> None:
    """Each backslash comes with its pair, so psql ends the literal where a standard string ends:
    the line passes, and nothing inside it is a statement or a meta-command."""

    raw = roles_with("GRANT anon", f"{statement}\nGRANT anon")
    assert kinds(gate.check_roles_dump("roles.sql", raw)[1]) == []
    found: list[tuple[int, int, str]] = []
    statements, metas, hazards = gate.scan(raw.decode(), escape_strings=found)
    assert [command for _, command, _ in metas] == ["restrict", "unrestrict"]
    assert hazards == [] and len(found) == statement.count(" E'")
    assert len(statements) == len(gate.scan(ROLES)[0]) + 1
    # The statement after it starts on its own line, however many lines the literal spans.
    lines = raw.decode().split("\n")
    assert statements[-1] == (
        next(n for n, item in enumerate(lines, 1) if item.startswith("GRANT anon")),
        ("GRANT", "ANON", "TO", "AUTHENTICATOR", "WITH"),
    )


def test_an_escape_string_that_never_ends_is_a_hazard_however_it_ends() -> None:
    """At the end of the text, with no closing quote: never pg_dumpall's form."""

    for text in ("COMMENT ON ROLE anon IS E'x", "COMMENT ON ROLE anon IS E'x\n;", "x E'"):
        found: list[tuple[int, int, str]] = []
        assert gate.scan(text, escape_strings=found)[2] == [(1, "ESCAPE_STRING")], text
        assert found == [], text


def test_schema_sql_still_refuses_every_escape_string() -> None:
    """pg_dump writes no escape string (its literals are standard strings, as the PostgreSQL 17
    tools showed for every kind of schema object), so none passes in schema.sql."""

    for statement in (
        r"COMMENT ON TABLE public.t IS E'a\\b';",
        r"ALTER TABLE public.t ALTER a SET DEFAULT E'a\\b';",
    ):
        raw = schema_with("GRANT SELECT", f"{statement}\nGRANT SELECT")
        assert kinds(gate.check_schema_dump("schema.sql", raw)[1]) == ["ESCAPE_STRING"]


@pytest.mark.parametrize(
    "statement",
    [
        r"COMMENT ON ROLE anon IS E'it\'s';",
        r"COMMENT ON ROLE anon IS E'a\nb';",
        r"COMMENT ON ROLE anon IS E'\x41';",
        r"COMMENT ON ROLE anon IS E'\101';",
        r"COMMENT ON ROLE anon IS E'\u0041';",
        r"COMMENT ON ROLE anon IS E'a\\\';",
        r"COMMENT ON ROLE anon IS e'a\\b';",
        r"COMMENT ON ROLE anon IS(E'a\\b');",
        r"COMMENT ON ROLE anon IS xE'a\\b';",
        "COMMENT ON ROLE anon IS E'a'\n'b';",
        r"COMMENT ON ROLE anon IS E'a\\b' ;",
        r"COMMENT ON ROLE anon IS E'a\\b', 'c';",
        r"COMMENT ON ROLE anon IS E'unterminated",
        "ALTER ROLE anon SET application_name TO E'a'\n'b';",
        r"ALTER ROLE anon SET application_name TO E'a\\b' ;",
        r"ALTER ROLE anon SET application_name TO E'unterminated",
        r"ALTER ROLE anon WITH VALID UNTIL E'a\\b';",
        r"ALTER ROLE ALL SET application_name TO E'a\\b';",
        r"ALTER ROLE anon IN DATABASE postgres SET application_name TO E'a\\b';",
        r"GRANT anon TO E'a\\b';",
        r"SET application_name = E'a\\b';",
        r"COMMENT ON ROLE anon IS E'\'' \! touch x ';",
    ],
    ids=[
        "an escaped quote",
        "a C escape",
        "a hex escape",
        "an octal escape",
        "a Unicode escape",
        "an odd run of backslashes",
        "a lower-case e",
        "not after a space",
        "inside a word",
        "a continuation",
        "not followed at once by a semicolon",
        "a comma pg_dumpall writes only in a list setting",
        "unterminated",
        "a setting's continuation",
        "a setting not followed at once by a semicolon",
        "an unterminated setting",
        "not a setting",
        "every role at once",
        "one database's setting",
        "another statement",
        "a SET line",
        "a meta-command psql would run",
    ],
)
def test_any_other_escape_string_is_refused_in_the_roles_file(statement: str) -> None:
    """Anything but pg_dumpall's own form is lexed by psql where the scan cannot follow: an escaped
    quote ends nothing for psql (the last case would run a shell command were it accepted)."""

    raw = roles_with("GRANT anon", f"{statement}\nGRANT anon")
    assert "ESCAPE_STRING" in kinds(gate.check_roles_dump("roles.sql", raw)[1])


def test_a_nul_character_is_refused() -> None:
    """psql's line reader stops at a NUL, so the rest of that line would never reach it."""

    raw = SCHEMA.replace("BEGIN\n", "BEGIN\x00 '\n", 1).encode()
    assert kinds(gate.check_schema_dump("schema.sql", raw)[1]) == ["NUL_CHARACTER"]
    assert kinds(gate.check_roles_dump("roles.sql", raw)[1]) == ["NUL_CHARACTER"]


def test_a_bare_carriage_return_is_refused() -> None:
    """Review 3 of DP-D (owner-authorized third repair): psql ends a line (and a comment) at a
    bare carriage return as well as a newline, so a mid-line CR could resume lexing where the scan
    does not. Genuine pg_dump 17 output has none, so it is refused before any lexing or restore."""

    raw = SCHEMA.replace("BEGIN\n", "BEGIN\r more\n", 1).encode()
    assert kinds(gate.check_schema_dump("schema.sql", raw)[1]) == ["CARRIAGE_RETURN"]
    assert kinds(gate.check_roles_dump("roles.sql", raw)[1]) == ["CARRIAGE_RETURN"]
    # A CRLF file is refused too (the scan is newline-only by construction).
    crlf = SCHEMA.replace("\n", "\r\n").encode()
    assert kinds(gate.check_schema_dump("schema.sql", crlf)[1]) == ["CARRIAGE_RETURN"]


def test_a_superuser_role_granted_to_any_role_is_app() -> None:
    """Review 3 of DP-D, finding 2 (3rd occurrence; owner-authorized third repair): a role granted
    a superuser role — the bootstrap, or any role the fingerprint records as SUPERUSER — can act as
    every role, so the grant is an app difference even when neither end is an app role."""

    reference, restored = fingerprint(), fingerprint()
    restored["cluster"]["attributes"]["custom_super"] = {"rolsuper": True}
    restored["cluster"]["memberships"] = [
        *reference["cluster"]["memberships"],
        "custom_super to plain_role admin=False inherit=True set=True",
    ]
    found = catalog.compare(reference, restored, MIGRATION, "supabase_admin")
    paths = {(item.category, item.path) for item in found}
    assert ("app", "cluster/attributes/custom_super") in paths  # the new superuser itself
    assert (
        "app",
        "cluster/memberships/custom_super to plain_role admin=False inherit=True set=True",
    ) in paths
    assert all(category == "app" for category, _ in paths), found


@pytest.mark.parametrize(
    ("line", "found"),
    [
        ("SET standard_conforming_strings = on;", []),
        ("SET client_encoding = 'UTF8';", []),
        ("SET SESSION AUTHORIZATION ucpe_resolver;", []),
        ('SET SESSION AUTHORIZATION "a ""quoted"" role";', []),
        ("SET standard_conforming_strings = off;", ["STATEMENT_SET_STANDARD_CONFORMING_STRINGS"]),
        ("SET client_encoding = 'SJIS';", ["STATEMENT_SET_CLIENT_ENCODING"]),
        ("SET SESSION standard_conforming_strings = off;", ["STATEMENT_SET_FORM"]),
        ("SET LOCAL client_encoding = 'SJIS';", ["STATEMENT_SET_FORM"]),
        ('SET "standard_conforming_strings" = off;', ["STATEMENT_SET_FORM"]),
        ("SET standard_conforming_strings TO off;", ["STATEMENT_SET_FORM"]),
        ("SET a = 1; SET standard_conforming_strings = off;", ["STATEMENT_SET_FORM"] * 2),
    ],
    ids=[
        "standard strings on",
        "UTF-8",
        "a session authorization",
        "a quoted one",
        "standard strings off",
        "another encoding",
        "a session setting",
        "a local setting",
        "a quoted setting",
        "another syntax",
        "two on one line",
    ],
)
def test_a_set_is_one_of_pg_dumps_own_lines(line: str, found: list[str]) -> None:
    """Review 2 of DP-D, finding 3: psql reads standard_conforming_strings and client_encoding
    back from the server and lexes by them, so each may hold only pg_dump's value, in pg_dump's
    own form, in either file."""

    schema = schema_with("GRANT SELECT", f"{line}\nGRANT SELECT")
    assert kinds(gate.check_schema_dump("schema.sql", schema)[1]) == found
    roles = roles_with("GRANT anon", f"{line}\nGRANT anon")
    assert kinds(gate.check_roles_dump("roles.sql", roles)[1]) == found


@pytest.mark.parametrize(
    "line",
    [
        "SELECT pg_catalog.set_config('search_path', 'public', false);",
        " SELECT pg_catalog.set_config('search_path', '', false);",
        "SELECT pg_catalog.set_config('search_path', '', false); SELECT 1;",
    ],
    ids=["another path", "indented", "with another statement"],
)
def test_the_one_select_is_pg_dumps_exact_line(line: str) -> None:
    raw = schema_with("SELECT pg_catalog.set_config('search_path', '', false);", line)
    assert set(kinds(gate.check_schema_dump("schema.sql", raw)[1])) == {"STATEMENT_SELECT"}


# --------------------------------------------------------------------------- the comparison
def fingerprint(**changes: object) -> dict:
    base = {
        "relations": {"predictions": {"acl": ["anon:SELECT by <owner>"], "row_security": True}},
        "functions": {"f()": {"definition_sha256": "a", "definition": "CREATE f\nbody", "acl": []}},
        "default_privileges": {"<owner> r": ["anon:SELECT by <owner>"]},
        "cluster": {
            "attributes": {
                "ucpe_space_db": {"rolcanlogin": False},
                "ucpe_api_writer": {"rolcanlogin": False},
                "anon": {"rolbypassrls": False, "rolcanlogin": False, "rolconnlimit": -1},
                "authenticator": {"rolcanlogin": False},
            },
            "settings": {},
            "memberships": ["ucpe_api_writer to authenticator admin=False inherit=False set=True"],
            "parameter_acl": {},
        },
    }
    for path, value in changes.items():
        node = base
        *parents, leaf = path.split("__")
        for part in parents:
            node = node[part]
        node[leaf] = value
    return base


def test_identical_fingerprints_have_no_difference() -> None:
    assert catalog.compare(fingerprint(), fingerprint()) == []


def test_the_documented_login_steps_are_operational_and_nothing_else_is() -> None:
    restored = fingerprint()
    restored["cluster"]["attributes"]["ucpe_space_db"]["rolcanlogin"] = True
    restored["cluster"]["attributes"]["ucpe_api_writer"]["rolcanlogin"] = True
    found = {
        (item.category, item.path) for item in catalog.compare(fingerprint(), restored, MIGRATION)
    }
    assert found == {
        ("operational", "cluster/attributes/ucpe_space_db/rolcanlogin"),
        ("app", "cluster/attributes/ucpe_api_writer/rolcanlogin"),
    }
    reverse = {
        (item.category, item.path) for item in catalog.compare(restored, fingerprint(), MIGRATION)
    }
    assert {category for category, _ in reverse} == {"app"}, "losing a login is never operational"


def test_a_platform_roles_default_privileges_are_platform_and_the_appss_are_app() -> None:
    """Review 1 of DP-D, finding 1: a migration role's default privileges are the app's."""

    restored = fingerprint()
    restored["default_privileges"]["supabase_admin r"] = ["anon:SELECT by supabase_admin"]
    restored["default_privileges"]["<owner> r"] = []
    restored["default_privileges"]["ucpe_bundle_owner f"] = ["anon:EXECUTE by ucpe_bundle_owner"]
    migration = frozenset({"ucpe_bundle_owner"})
    found = {
        (item.category, item.path) for item in catalog.compare(fingerprint(), restored, migration)
    }
    assert found == {
        ("platform", "default_privileges/supabase_admin r"),
        ("app", "default_privileges/<owner> r"),
        ("app", "default_privileges/ucpe_bundle_owner f"),
    }


@pytest.mark.parametrize(
    ("section", "key", "before", "after", "category"),
    [
        ("attributes", "anon", {"rolbypassrls": False}, {"rolbypassrls": True}, "app"),
        ("attributes", "anon", {"rolcanlogin": False}, {"rolcanlogin": True}, "app"),
        ("attributes", "authenticator", {"rolcanlogin": False}, {"rolcanlogin": True}, "platform"),
        ("attributes", "anon", {"rolconnlimit": -1}, {"rolconnlimit": 5}, "platform"),
        ("attributes", "anon", {"rolbypassrls": True}, {"rolbypassrls": False}, "platform"),
        ("attributes", "<owner>", {"rolbypassrls": False}, {"rolbypassrls": True}, "platform"),
        ("attributes", "supabase_storage_admin", None, {"rolcanlogin": True}, "platform"),
        ("attributes", "anon", {"rolcanlogin": False}, None, "app"),
        ("attributes", "rehearsal_super", None, {"rolsuper": True}, "app"),
        ("attributes", "dashboard_user", {"rolsuper": False}, {"rolsuper": True}, "app"),
        (
            "attributes",
            "supabase_read_only_user",
            None,
            {"rolbypassrls": True, "rolsuper": False},
            "platform",
        ),
        ("attributes", "<owner>", {"rolsuper": False}, {"rolsuper": True}, "platform"),
        (
            "attributes",
            "supabase_admin",
            {"rolreplication": True},
            {"rolreplication": False},
            "platform",
        ),
        (
            "memberships",
            "pg_read_all_data to anon admin=False inherit=False set=True",
            None,
            "x",
            "app",
        ),
        (
            "memberships",
            "ucpe_api_writer to supabase_storage_admin admin=False inherit=True set=True",
            None,
            "x",
            "app",
        ),
        (
            "memberships",
            "supabase_admin to authenticator admin=False inherit=False set=True",
            None,
            "x",
            "app",
        ),
        (
            "memberships",
            "<owner> to rehearsal_x admin=False inherit=True set=True",
            None,
            "x",
            "app",
        ),
        (
            "memberships",
            "<owner> to supabase_admin admin=True inherit=False set=False",
            None,
            "x",
            "platform",
        ),
        (
            "memberships",
            "anon to supabase_storage_admin admin=False inherit=True set=True",
            None,
            "x",
            "app",
        ),
        (
            "memberships",
            "pg_read_all_data to <owner> admin=False inherit=True set=True",
            None,
            "x",
            "platform",
        ),
        (
            # Any platform role but the one edge the owner ruled exact (DP-D-FINDINGS, C3).
            "memberships",
            "pg_read_all_data to dashboard_user admin=False inherit=True set=True",
            None,
            "x",
            "app",
        ),
        (
            "memberships",
            "pg_monitor to supabase_read_only_user admin=False inherit=True set=True",
            None,
            "x",
            "platform",
        ),
        (
            "memberships",
            "anon to <owner> admin=False inherit=True set=True",
            None,
            "x",
            "platform",
        ),
        (
            "settings",
            "ucpe_api_writer in all databases",
            None,
            ["statement_timeout sha256:a"],
            "app",
        ),
        (
            "settings",
            "authenticator in all databases",
            None,
            ["statement_timeout sha256:a"],
            "platform",
        ),
        (
            "settings",
            "authenticator in all databases",
            None,
            ["session_replication_role sha256:a"],
            "app",
        ),
        (
            "settings",
            "anon in all databases",
            ["statement_timeout sha256:a"],
            ["search_path sha256:b", "statement_timeout sha256:a"],
            "app",
        ),
        (
            "settings",
            "supabase_storage_admin in all databases",
            None,
            ["search_path sha256:a"],
            "platform",
        ),
        ("settings", "<owner> in all databases", None, ["search_path sha256:a"], "platform"),
        (
            "parameter_acl",
            "session_replication_role",
            [],
            ["ucpe_api_writer:SET by <owner>"],
            "app",
        ),
        ("parameter_acl", "session_replication_role", [], ["anon:SET by <owner>"], "app"),
        ("parameter_acl", "session_replication_role", [], ["PUBLIC:SET by <owner>"], "app"),
        ("parameter_acl", "session_replication_role", [], ["<owner>:SET by x"], "platform"),
        (
            "parameter_acl",
            "log_min_duration_statement",
            [],
            ["dashboard_user:SET by x"],
            "platform",
        ),
        (
            "memberships",
            "supabase_admin to gap_holder admin=False inherit=True set=True",
            None,
            "x",
            "app",
        ),
        ("settings", "PUBLIC in all databases", None, ["session_replication_role sha256:a"], "app"),
    ],
    ids=[
        "an API role gains BYPASSRLS",
        "an API role gains LOGIN",
        "the API login role logs in",
        "an API role's connection limit",
        "an API role loses BYPASSRLS",
        "the owner's attributes",
        "another platform role",
        "an API role is gone",
        "a new superuser",
        "a platform role becoming a superuser",
        "a platform role bypassing row security, which reaches no app row alone",
        "the owner becoming a superuser",
        "the bootstrap's attributes",
        "a predefined role granted to an API role",
        "a migration role granted to a platform role",
        "the superuser granted to the API login",
        "a role holding the owner",
        "the bootstrap superuser holding the owner",
        "a platform role able to act as an API role",
        "a predefined role granted to the owner",
        "a platform role reading every table",
        "a platform role's other predefined role",
        "the owner holding an API role",
        "a migration role's setting",
        "an API role's timeout",
        "a setting that turns the seals off for every API session",
        "an API role's other setting beside a timeout",
        "a platform role's setting",
        "the owner's setting",
        "a parameter grant to a migration role",
        "a parameter grant to an API role",
        "a parameter grant to PUBLIC, which is every role",
        "a parameter grant to the owner, who owns every app object already",
        "a parameter grant to another role",
        "the bootstrap superuser granted to a plain role",
        "a setting applied to PUBLIC, which is every role",
    ],
)
def test_privilege_paths_fail_and_platform_notes_do_not(
    section: str, key: str, before: object, after: object, category: str
) -> None:
    """Review 2 of DP-D, finding 1: every privilege path the roles export restores is compared,
    and one into the app (through an API role, the owner or a migration role) fails."""

    reference, restored = fingerprint(), fingerprint()
    cluster = reference["cluster"]
    if section == "memberships":
        restored["cluster"]["memberships"] = [*cluster["memberships"], key]
    else:
        if before is not None:
            cluster[section][key] = before
            restored["cluster"][section][key] = before
        if after is None:
            restored["cluster"][section].pop(key)
        else:
            restored["cluster"][section][key] = after
    found = catalog.compare(reference, restored, MIGRATION, "supabase_admin")
    assert {item.category for item in found} == {category}, found


def test_memberships_differ_item_by_item_and_functions_by_digest() -> None:
    restored = fingerprint()
    restored["cluster"]["memberships"] = [
        "service_role to ucpe_space_db admin=False inherit=False set=True"
    ]
    restored["functions"]["f()"] = {
        "definition_sha256": "b",
        "definition": "CREATE f\nother",
        "acl": [],
    }
    found = {
        (item.category, item.path) for item in catalog.compare(fingerprint(), restored, MIGRATION)
    }
    assert found == {
        (
            "app",
            "cluster/memberships/ucpe_api_writer to authenticator "
            "admin=False inherit=False set=True",
        ),
        (
            "app",
            "cluster/memberships/service_role to ucpe_space_db admin=False inherit=False set=True",
        ),
        ("app", "functions/f()/definition_sha256"),
    }
    assert catalog.function_diff(fingerprint(), restored) == {
        "f()": {"line": 2, "reference": "body", "restored": "other"}
    }


def test_the_api_roles_are_the_ones_the_app_names_or_that_hold_a_migration_role() -> None:
    reference = {
        "schema": {"acl": ["anon:USAGE by <owner>", "<owner>:CREATE by <owner>"]},
        "relations": {"t": {"acl": ["authenticated:SELECT by <owner>", "PUBLIC:SELECT by x"]}},
        "functions": {"f()": {"acl": ["service_role:EXECUTE by <owner>"]}},
        "column_acl": {"t.a": ["column_reader:SELECT by <owner>"]},
        "default_privileges": {"<owner> r": ["supabase_admin:SELECT by <owner>"]},
        "policies": {"t": {"p": {"roles": ["policy_role", "ucpe_space_db"]}}},
        "cluster": {
            "memberships": [
                "ucpe_api_writer to authenticator admin=False inherit=False set=True",
                "anon to platform_member admin=False inherit=True set=True",
            ]
        },
    }
    found = catalog.api_roles(reference, MIGRATION, "supabase_admin")
    assert found == {
        "anon",
        "authenticated",
        "service_role",
        "column_reader",
        "policy_role",
        "authenticator",
    }, "never a migration role, the owner, PUBLIC or the bootstrap superuser"


def test_a_settings_value_is_kept_as_its_digest_only() -> None:
    kept = catalog._setting("app.settings.key=s3cr3t=value")  # noqa: SLF001
    digest = hashlib.sha256(b"s3cr3t=value").hexdigest()
    assert kept == f"app.settings.key sha256:{digest}" and "s3cr3t" not in kept


def test_the_migration_roles_come_from_the_migration_files() -> None:
    assert catalog.migration_roles(ROOT / "migrations") == {
        "ucpe_api_writer",
        "ucpe_bundle_owner",
        "ucpe_space_db",
        "ucpe_resolver",
    }


# --------------------------------------------------------------------------- the owner's exceptions
# Owner rulings DP-D-FINDINGS and DP-D-STORAGE-SETTINGS: the nine differences the owner's export
# showed, stated here on their own so that any change to catalog.PLATFORM_EXCEPTIONS shows in
# review. Setting values are digests.
EDGE_STORAGE = "authenticator to supabase_storage_admin admin=False inherit=False set=True"
EDGE_ETL = "pg_read_all_data to supabase_etl_admin admin=False inherit=True set=True"
EDGE_READ_ONLY = "pg_read_all_data to supabase_read_only_user admin=False inherit=True set=True"
TIMEOUT_DIGEST = "a5da9841fa3011b3c456f51181f7d7965ff96ee8a4f4c971920e2dce6d0cc0e1"
LIBRARIES_DIGEST = "c010590ae41b57ca804a08839c5da5c2d4308c508296f9ceee3986a3b7da9240"
OTHER_DIGEST = hashlib.sha256(b"another value").hexdigest()
SETTINGS = "authenticator in all databases"
STORAGE_SETTINGS = "supabase_storage_admin in all databases"
LOG_NONE_DIGEST = "140bedbf9c3f6d56a9846d2ba7088798683f4da0c248231336e6a05679e4fdfe"
STORAGE_PATH_DIGEST = "49a25f9feefaffecad0fcd30c50dc9331cff8b55ece53def6285c09e17e6f5d7"
TABLE_PRIVILEGES = (
    "DELETE",
    "INSERT",
    "MAINTAIN",
    "REFERENCES",
    "SELECT",
    "TRIGGER",
    "TRUNCATE",
    "UPDATE",
)
RULED = {
    f"cluster/memberships/{EDGE_STORAGE}": {EDGE_STORAGE},
    f"cluster/memberships/{EDGE_ETL}": {EDGE_ETL},
    f"cluster/memberships/{EDGE_READ_ONLY}": {EDGE_READ_ONLY},
    f"cluster/settings/{SETTINGS}": {
        f"lock_timeout sha256:{TIMEOUT_DIGEST}",
        f"session_preload_libraries sha256:{LIBRARIES_DIGEST}",
        f"statement_timeout sha256:{TIMEOUT_DIGEST}",
    },
    "default_privileges/<owner> S": {
        f"<owner>:{privilege} by <owner>" for privilege in ("SELECT", "UPDATE", "USAGE")
    },
    "default_privileges/<owner> f": {"<owner>:EXECUTE by <owner>"},
    "default_privileges/<owner> r": {
        f"<owner>:{privilege} by <owner>" for privilege in TABLE_PRIVILEGES
    },
    "schema/acl": {"<owner>:USAGE by pg_database_owner"},
    f"cluster/settings/{STORAGE_SETTINGS}": {
        f"log_statement sha256:{LOG_NONE_DIGEST}",
        f"search_path sha256:{STORAGE_PATH_DIGEST}",
    },
}
API = ("anon", "authenticated", "service_role")


def ruled_reference() -> dict:
    """A reference as the migrations declare it where the nine ruled differences fall."""

    reference = fingerprint()
    reference["schema"] = {
        "acl": sorted(
            [
                *(f"{role}:USAGE by pg_database_owner" for role in API),
                "pg_database_owner:CREATE by pg_database_owner",
                "pg_database_owner:USAGE by pg_database_owner",
            ]
        )
    }
    reference["default_privileges"] = {
        "<owner> S": sorted(f"{role}:{p} by <owner>" for role in API for p in ("SELECT", "USAGE")),
        "<owner> f": [f"{role}:EXECUTE by <owner>" for role in API],
        "<owner> r": [f"{role}:SELECT by <owner>" for role in API],
    }
    return reference


def ruled_production() -> dict:
    """The reference with the nine ruled differences, exactly as the owner's export showed them."""

    production = ruled_reference()
    cluster = production["cluster"]
    cluster["memberships"] = sorted(
        [*cluster["memberships"], EDGE_STORAGE, EDGE_ETL, EDGE_READ_ONLY]
    )
    cluster["settings"][SETTINGS] = sorted(RULED[f"cluster/settings/{SETTINGS}"])
    cluster["settings"][STORAGE_SETTINGS] = sorted(RULED[f"cluster/settings/{STORAGE_SETTINGS}"])
    for key in ("<owner> S", "<owner> f", "<owner> r"):
        production["default_privileges"][key] = sorted(
            [*production["default_privileges"][key], *RULED[f"default_privileges/{key}"]]
        )
    production["schema"]["acl"] = sorted([*production["schema"]["acl"], *RULED["schema/acl"]])
    return production


def test_the_platform_exceptions_are_exactly_the_nine_the_owner_ruled() -> None:
    exceptions = catalog.PLATFORM_EXCEPTIONS
    assert {item.path: set(item.added) for item in exceptions} == RULED
    assert len(exceptions) == len(RULED) == 9, "one exception per ruled difference"
    assert all(item.source.endswith(".sql") for item in exceptions), "each cites Supabase's file"


def test_the_nine_ruled_differences_are_accepted_and_nothing_else_is() -> None:
    found = catalog.compare(ruled_reference(), ruled_production(), MIGRATION, "supabase_admin")
    assert {(item.category, item.path) for item in found} == {("accepted", path) for path in RULED}
    # Losing them is never accepted: a ruled difference is only ever what production adds. Without
    # its ruled membership, Storage's role is a plain platform role again, its settings its own.
    lost = catalog.compare(ruled_production(), ruled_reference(), MIGRATION, "supabase_admin")
    storage = f"cluster/settings/{STORAGE_SETTINGS}"
    assert {(item.category, item.path) for item in lost} == {
        ("app", path) for path in RULED if path != storage
    } | {("platform", storage)}


def _membership(old: str | None, new: str) -> Callable[[dict], None]:
    def change(production: dict) -> None:
        edges = [edge for edge in production["cluster"]["memberships"] if edge != old]
        production["cluster"]["memberships"] = sorted([*edges, new])

    return change


def _settings(key: str, *items: str) -> Callable[[dict], None]:
    def change(production: dict) -> None:
        production["cluster"]["settings"][key] = sorted(items)

    return change


def _grants(section: str, key: str, *, add: tuple = (), drop: tuple = ()) -> Callable[[dict], None]:
    def change(production: dict) -> None:
        holder = production[section]
        kept = [item for item in holder.get(key, []) if item not in drop]
        holder[key] = sorted([*kept, *add])

    return change


RULED_SETTINGS = sorted(RULED[f"cluster/settings/{SETTINGS}"])
RULED_STORAGE = sorted(RULED[f"cluster/settings/{STORAGE_SETTINGS}"])
NEAR_MISSES = [
    (
        _membership(EDGE_STORAGE, EDGE_STORAGE.replace("inherit=False", "inherit=True")),
        "cluster/memberships/authenticator to supabase_storage_admin admin=False inherit=True "
        "set=True",
    ),
    (
        _membership(EDGE_STORAGE, EDGE_STORAGE.replace("admin=False", "admin=True")),
        "cluster/memberships/authenticator to supabase_storage_admin admin=True inherit=False "
        "set=True",
    ),
    (
        _membership(EDGE_STORAGE, EDGE_STORAGE.replace("set=True", "set=False")),
        "cluster/memberships/authenticator to supabase_storage_admin admin=False inherit=False "
        "set=False",
    ),
    (
        _membership(
            None, "authenticator to supabase_auth_admin admin=False inherit=False set=True"
        ),
        "cluster/memberships/authenticator to supabase_auth_admin admin=False inherit=False "
        "set=True",
    ),
    (
        _membership(
            None, "authenticator to supabase_storage_admin2 admin=False inherit=False set=True"
        ),
        "cluster/memberships/authenticator to supabase_storage_admin2 admin=False inherit=False "
        "set=True",
    ),
    (
        _membership(
            None, "service_role to supabase_storage_admin admin=False inherit=False set=True"
        ),
        "cluster/memberships/service_role to supabase_storage_admin admin=False inherit=False "
        "set=True",
    ),
    (
        _membership(EDGE_ETL, EDGE_ETL.replace("admin=False", "admin=True")),
        "cluster/memberships/pg_read_all_data to supabase_etl_admin admin=True inherit=True "
        "set=True",
    ),
    (
        _membership(
            None, "pg_write_all_data to supabase_etl_admin admin=False inherit=True set=True"
        ),
        "cluster/memberships/pg_write_all_data to supabase_etl_admin admin=False inherit=True "
        "set=True",
    ),
    (
        _membership(
            None, "pg_write_all_data to supabase_read_only_user admin=False inherit=True set=True"
        ),
        "cluster/memberships/pg_write_all_data to supabase_read_only_user admin=False inherit=True "
        "set=True",
    ),
    (
        _membership(
            None,
            "pg_read_server_files to supabase_read_only_user admin=False inherit=True set=True",
        ),
        "cluster/memberships/pg_read_server_files to supabase_read_only_user admin=False "
        "inherit=True set=True",
    ),
    (
        _membership(
            None, "pg_read_all_data to supabase_read_only_usr admin=False inherit=True set=True"
        ),
        "cluster/memberships/pg_read_all_data to supabase_read_only_usr admin=False inherit=True "
        "set=True",
    ),
    (
        _membership(
            None, "pg_read_all_data to supabase_storage_admin admin=False inherit=True set=True"
        ),
        "cluster/memberships/pg_read_all_data to supabase_storage_admin admin=False inherit=True "
        "set=True",
    ),
    (
        _settings(SETTINGS, *RULED_SETTINGS, f"session_replication_role sha256:{OTHER_DIGEST}"),
        f"cluster/settings/{SETTINGS}",
    ),
    (
        _settings(SETTINGS, *RULED_SETTINGS, f"idle_session_timeout sha256:{TIMEOUT_DIGEST}"),
        f"cluster/settings/{SETTINGS}",
    ),
    (
        _settings(
            SETTINGS,
            f"lock_timeout sha256:{TIMEOUT_DIGEST}",
            f"session_preload_libraries sha256:{OTHER_DIGEST}",
            f"statement_timeout sha256:{TIMEOUT_DIGEST}",
        ),
        f"cluster/settings/{SETTINGS}",
    ),
    (
        _settings(
            SETTINGS,
            f"lock_timeout sha256:{OTHER_DIGEST}",
            f"session_preload_libraries sha256:{LIBRARIES_DIGEST}",
            f"statement_timeout sha256:{TIMEOUT_DIGEST}",
        ),
        f"cluster/settings/{SETTINGS}",
    ),
    (
        _settings(
            SETTINGS,
            f"lock_timeout sha256:{TIMEOUT_DIGEST}",
            f"session_preload_libraries sha256:{LIBRARIES_DIGEST}",
        ),
        f"cluster/settings/{SETTINGS}",
    ),
    (_settings("anon in all databases", *RULED_SETTINGS), "cluster/settings/anon in all databases"),
    (
        _settings("authenticator in this database", *RULED_SETTINGS),
        "cluster/settings/authenticator in this database",
    ),
    (
        _grants("default_privileges", "<owner> r", add=("<owner>:SELECT* by <owner>",)),
        "default_privileges/<owner> r",
    ),
    (
        _grants("default_privileges", "<owner> r", drop=("<owner>:MAINTAIN by <owner>",)),
        "default_privileges/<owner> r",
    ),
    (
        _grants("default_privileges", "<owner> r", add=("ucpe_resolver:SELECT by <owner>",)),
        "default_privileges/<owner> r",
    ),
    (
        _grants("default_privileges", "<owner> f", add=("PUBLIC:EXECUTE by <owner>",)),
        "default_privileges/<owner> f",
    ),
    (
        _grants(
            "default_privileges",
            "<owner> f",
            add=("<owner>:EXECUTE by supabase_admin",),
            drop=("<owner>:EXECUTE by <owner>",),
        ),
        "default_privileges/<owner> f",
    ),
    (
        _grants("default_privileges", "<owner> r", drop=("anon:SELECT by <owner>",)),
        "default_privileges/<owner> r",
    ),
    (
        _grants("default_privileges", "<owner> T", add=("<owner>:USAGE by <owner>",)),
        "default_privileges/<owner> T",
    ),
    (
        _grants("default_privileges", "ucpe_bundle_owner f", add=("<owner>:EXECUTE by <owner>",)),
        "default_privileges/ucpe_bundle_owner f",
    ),
    (
        _grants("schema", "acl", add=("<owner>:CREATE by pg_database_owner",)),
        "schema/acl",
    ),
    (
        _grants(
            "schema",
            "acl",
            add=("<owner>:USAGE* by pg_database_owner",),
            drop=("<owner>:USAGE by pg_database_owner",),
        ),
        "schema/acl",
    ),
    (
        _grants(
            "schema",
            "acl",
            add=("<owner>:USAGE by supabase_admin",),
            drop=("<owner>:USAGE by pg_database_owner",),
        ),
        "schema/acl",
    ),
    (
        _grants("schema", "acl", add=("supabase_storage_admin:USAGE by pg_database_owner",)),
        "schema/acl",
    ),
    (_grants("schema", "acl", drop=("anon:USAGE by pg_database_owner",)), "schema/acl"),
    (_grants("schema", "acl", add=("<owner>:USAGE by pg_database_owner",)), "schema/acl"),
    (
        _settings(STORAGE_SETTINGS, *RULED_STORAGE, f"statement_timeout sha256:{TIMEOUT_DIGEST}"),
        f"cluster/settings/{STORAGE_SETTINGS}",
    ),
    (
        _settings(
            STORAGE_SETTINGS, *RULED_STORAGE, f"session_replication_role sha256:{OTHER_DIGEST}"
        ),
        f"cluster/settings/{STORAGE_SETTINGS}",
    ),
    (
        _settings(STORAGE_SETTINGS, *RULED_STORAGE, f"role sha256:{OTHER_DIGEST}"),
        f"cluster/settings/{STORAGE_SETTINGS}",
    ),
    (
        _settings(
            STORAGE_SETTINGS,
            f"log_statement sha256:{LOG_NONE_DIGEST}",
            f"search_path sha256:{OTHER_DIGEST}",
        ),
        f"cluster/settings/{STORAGE_SETTINGS}",
    ),
    (
        _settings(
            STORAGE_SETTINGS,
            f"log_statement sha256:{OTHER_DIGEST}",
            f"search_path sha256:{STORAGE_PATH_DIGEST}",
        ),
        f"cluster/settings/{STORAGE_SETTINGS}",
    ),
    (
        _settings(STORAGE_SETTINGS, f"search_path sha256:{STORAGE_PATH_DIGEST}"),
        f"cluster/settings/{STORAGE_SETTINGS}",
    ),
    (
        _settings("supabase_storage_admin in this database", *RULED_STORAGE),
        "cluster/settings/supabase_storage_admin in this database",
    ),
    (
        _settings("supabase_storage_admin in another database", *RULED_STORAGE),
        "cluster/settings/supabase_storage_admin in another database",
    ),
    (
        _settings("anon in all databases", *RULED_STORAGE),
        "cluster/settings/anon in all databases",
    ),
    (
        _settings("ucpe_api_writer in all databases", *RULED_STORAGE),
        "cluster/settings/ucpe_api_writer in all databases",
    ),
    (
        _settings(SETTINGS, *RULED_SETTINGS, *RULED_STORAGE),
        f"cluster/settings/{SETTINGS}",
    ),
]


NEAR_MISS_IDS = [
    "Storage's membership inheriting",
    "Storage's membership with ADMIN",
    "Storage's membership without SET",
    "authenticator granted to another platform role",
    "authenticator granted to a look-alike of Storage's role",
    "another API role granted to Storage's role",
    "the ETL role's membership with ADMIN",
    "the ETL role writing every table",
    "the read-only role writing every table",
    "the read-only role reading the server's files",
    "a look-alike of the read-only role reading every table",
    "Storage's role reading every table",
    "a setting beside the ruled ones that turns the seals off",
    "a timeout beside the ruled ones",
    "the preloaded libraries with another value",
    "a ruled timeout with another value",
    "a ruled setting missing",
    "the ruled settings on another API role",
    "the ruled settings in this database only",
    "the owner's table grant with grant option",
    "one ruled owner table grant missing",
    "another grantee beside the owner's table grants",
    "PUBLIC beside the owner's function grant",
    "the owner's function grant from another grantor",
    "an API role's table default dropped",
    "the owner's grant for another kind of object",
    "the owner's ruled grant under a migration role's defaults",
    "CREATE on the schema beside the ruled USAGE",
    "the ruled schema USAGE with grant option",
    "the ruled schema USAGE from another grantor",
    "schema USAGE to another role",
    "an API role's schema USAGE revoked",
    "the ruled schema USAGE twice",
    "a timeout beside Storage's two ruled settings",
    "a setting beside Storage's two that turns the seals off",
    "a login role setting beside Storage's two",
    "Storage's search path with another value",
    "Storage's statement logging with another value",
    "one of Storage's two ruled settings missing",
    "Storage's two ruled settings in this database only",
    "Storage's two ruled settings in another database",
    "Storage's two ruled settings on an API role",
    "Storage's two ruled settings on a migration role",
    "Storage's two ruled settings beside PostgREST's ruled ones",
]


@pytest.mark.parametrize(("change", "path"), NEAR_MISSES, ids=NEAR_MISS_IDS)
def test_near_a_ruled_difference_is_still_app(change: Callable[[dict], None], path: str) -> None:
    """Owner ruling DP-D-FINDINGS: no other role, membership, setting, grant or value inherits
    acceptance; whatever is not exactly a ruled difference stays app and fails the proof."""

    production = ruled_production()
    change(production)
    found = {
        (item.category, item.path)
        for item in catalog.compare(ruled_reference(), production, MIGRATION, "supabase_admin")
    }
    assert ("app", path) in found, found
    assert {path for category, path in found if category == "accepted"} <= set(RULED) - {path}


@pytest.mark.parametrize(("change", "path"), NEAR_MISSES, ids=NEAR_MISS_IDS)
def test_the_exceptions_loosen_nothing_but_the_ruled_differences(
    change: Callable[[dict], None], path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DP-D-STORAGE-SETTINGS, no broader exception: against the same production without the
    exceptions, every difference keeps its category or is stricter (app, the reach the ruled
    memberships pass on), and only an exactly ruled one is accepted. So nothing that fails without
    the exceptions passes with them but an exactly ruled difference."""

    production, reference = ruled_production(), ruled_reference()
    change(production)
    ruled = {
        item.path: item.category
        for item in catalog.compare(reference, production, MIGRATION, "supabase_admin")
    }
    monkeypatch.setattr(catalog, "PLATFORM_EXCEPTIONS", ())
    bare = {
        item.path: item.category
        for item in catalog.compare(reference, production, MIGRATION, "supabase_admin")
    }
    assert ruled.keys() == bare.keys()
    for key, category in ruled.items():
        exact = key in RULED and key != path
        assert category in {bare[key], "app"} or (category == "accepted" and exact), key
        assert category != "accepted" or exact, key


def test_only_an_app_difference_is_ever_accepted() -> None:
    """Where authenticator is no API role (it holds no migration role here), Storage's membership in
    it is the platform's already: an exception relabels only what would fail."""

    reference = ruled_reference()
    reference["cluster"]["memberships"] = []
    production = ruled_reference()
    production["cluster"]["memberships"] = [EDGE_STORAGE]
    found = catalog.compare(reference, production, MIGRATION, "supabase_admin")
    assert [(item.category, item.path) for item in found] == [
        ("platform", f"cluster/memberships/{EDGE_STORAGE}")
    ]


@pytest.mark.parametrize(
    ("section", "key", "value", "category"),
    [
        (
            "memberships",
            "supabase_etl_admin to evil admin=False inherit=True set=True",
            None,
            "app",
        ),
        (
            "memberships",
            "supabase_read_only_user to evil admin=False inherit=True set=True",
            None,
            "app",
        ),
        (
            "memberships",
            "supabase_storage_admin to evil admin=False inherit=False set=True",
            None,
            "app",
        ),
        (
            "memberships",
            "supabase_storage_admin to evil admin=False inherit=True set=False",
            None,
            "app",
        ),
        (
            "memberships",
            "supabase_read_only_user to supabase_etl_admin admin=False inherit=True set=True",
            None,
            "app",
        ),
        (
            "settings",
            "supabase_storage_admin in all databases",
            [f"session_replication_role sha256:{OTHER_DIGEST}"],
            "app",
        ),
        (
            "settings",
            "supabase_storage_admin in all databases",
            [f"search_path sha256:{OTHER_DIGEST}"],
            "app",
        ),
        (
            "settings",
            "supabase_storage_admin in this database",
            [f"search_path sha256:{OTHER_DIGEST}"],
            "app",
        ),
        (
            "parameter_acl",
            "session_replication_role",
            ["supabase_storage_admin:SET by supabase_admin"],
            "app",
        ),
        (
            "memberships",
            "pg_monitor to supabase_storage_admin admin=False inherit=False set=True",
            None,
            "app",
        ),
        (
            "memberships",
            "seal_param to supabase_storage_admin admin=False inherit=True set=False",
            None,
            "app",
        ),
        (
            "memberships",
            "pg_monitor to supabase_read_only_user admin=False inherit=True set=True",
            None,
            "platform",
        ),
        (
            "parameter_acl",
            "session_replication_role",
            ["supabase_read_only_user:SET by supabase_admin"],
            "platform",
        ),
        (
            "memberships",
            "supabase_etl_admin to <owner> admin=False inherit=True set=True",
            None,
            "platform",
        ),
        (
            "memberships",
            "supabase_read_only_user to supabase_admin admin=False inherit=True set=True",
            None,
            "platform",
        ),
        (
            "settings",
            "supabase_storage_admin in all databases",
            [f"statement_timeout sha256:{TIMEOUT_DIGEST}"],
            "platform",
        ),
        (
            "settings",
            "supabase_read_only_user in all databases",
            [f"default_transaction_read_only sha256:{OTHER_DIGEST}"],
            "platform",
        ),
    ],
    ids=[
        "a role holding the ETL role",
        "a role holding the read-only role",
        "a role able to become Storage's role",
        "a role inheriting from Storage's role",
        "one ruled reader holding the other",
        "Storage's role turning the seals off",
        "Storage's role's other setting",
        "Storage's role's setting in this database",
        "a parameter grant to Storage's role",
        "Storage's role gaining another role",
        "Storage's role inheriting another role",
        "a reader gaining another role, which gives it no write",
        "a parameter grant to a reader, which gives it no write",
        "the owner holding the ETL role, who owns every app object already",
        "the bootstrap superuser holding the read-only role",
        "Storage's role's timeout, as an API role's",
        "a reader's own setting, which gives it no write",
    ],
)
def test_what_a_ruled_membership_reaches_is_passed_on(
    section: str, key: str, value: object, category: str
) -> None:
    """Reviews 1 and 2 of DP-D-FINDINGS: the comparison looks one membership deep, so an accepted
    one must pass its reach on, or a path through it would pass as the platform's. Storage's role
    gaining a role that may set session_replication_role would turn the seals off for the API
    writes it makes through authenticator."""

    production = ruled_production()
    cluster = production["cluster"]
    if section == "memberships":
        cluster["memberships"] = sorted([*cluster["memberships"], key])
    else:
        cluster[section][key] = value
    found = catalog.compare(ruled_reference(), production, MIGRATION, "supabase_admin")
    changed = f"cluster/{section}/{key}"
    assert {(item.category, item.path) for item in found} == {
        ("accepted", path) for path in RULED if path != changed
    } | {(category, changed)}


def test_a_ruled_member_passes_on_only_what_production_lets_it_hold() -> None:
    api = catalog.api_roles(ruled_reference(), MIGRATION, "supabase_admin")
    acting, reaching = catalog.exception_reach(ruled_production(), api, MIGRATION)
    assert acting == {"supabase_storage_admin"}
    assert reaching == {"supabase_storage_admin", "supabase_etl_admin", "supabase_read_only_user"}
    # Without its ruled membership the ETL role reaches nothing of the app: holding it is the
    # platform's, as before.
    production = ruled_production()
    holder = "supabase_etl_admin to evil admin=False inherit=True set=True"
    production["cluster"]["memberships"] = sorted(
        [*(edge for edge in production["cluster"]["memberships"] if edge != EDGE_ETL), holder]
    )
    found = catalog.compare(ruled_reference(), production, MIGRATION, "supabase_admin")
    assert ("platform", f"cluster/memberships/{holder}") in {
        (item.category, item.path) for item in found
    }


@pytest.mark.parametrize(
    "name",
    ["a/b", "p to q", "supabase_admin admin=x", "<owner>", "PUBLIC", "Anon", "x:y", "x by y", "x*"],
)
def test_a_role_name_that_could_be_misread_is_app(name: str) -> None:
    """Review 2 of DP-D-FINDINGS: names are read back from paths, edges and grants, so a role
    named, say, "supabase_admin admin=x" holding a ruled role would be read as the bootstrap. Any
    name that is not a plain lowercase identifier fails the proof instead."""

    plain = ["anon", "pg_read_all_data", "supabase_storage_admin", "ucpe_api_writer", "x$1"]
    assert catalog.unsafe_role_names([*plain, name]) == [name]
    reference, production = ruled_reference(), ruled_production()
    reference["cluster"]["unsafe_role_names"] = []
    production["cluster"]["unsafe_role_names"] = [name]
    found = catalog.compare(reference, production, MIGRATION, "supabase_admin")
    assert ("app", "cluster/unsafe_role_names") in {(item.category, item.path) for item in found}


def test_a_whole_value_is_never_matched_as_an_item() -> None:
    for value in (
        {"<owner>:USAGE by pg_database_owner": True},
        [["<owner>:USAGE by pg_database_owner"]],
        ("<owner>:USAGE by pg_database_owner",),
    ):
        difference = catalog.Difference("app", "schema/acl", [], value)
        assert not catalog._accepted(difference)  # noqa: SLF001


# --------------------------------------------------------------------------- the proof
EXPECTED = {
    ("roles.sql", 'role "supabase_admin" already exists'),
    ("schema.sql", 'schema "public" already exists'),
}


@pytest.mark.parametrize(
    ("file", "line", "message", "statements", "category"),
    [
        ("schema.sql", 26, 'schema "public" already exists', {}, "expected"),
        ("roles.sql", 9, 'role "supabase_admin" already exists', {}, "expected"),
        (
            "roles.sql",
            7,
            "invalid value",
            {7: ("ALTER", "ROLE", "DASHBOARD_USER", "SET")},
            "platform",
        ),
        (
            "roles.sql",
            7,
            "invalid value",
            {7: ("ALTER", "ROLE", "DASHBOARD_USER", "IN")},
            "platform",
        ),
        ("roles.sql", 7, "invalid value", {7: ("ALTER", "ROLE", "UCPE_API_WRITER", "SET")}, "fail"),
        (
            "roles.sql",
            7,
            "invalid value",
            {7: ("ALTER", "ROLE", "ANON", "SET", "STATEMENT_TIMEOUT")},
            "platform",
        ),
        (
            "roles.sql",
            7,
            "invalid value",
            {7: ("ALTER", "ROLE", "AUTHENTICATOR", "SET", "SESSION_REPLICATION_ROLE")},
            "fail",
        ),
        ("roles.sql", 7, "invalid value", {7: ("ALTER", "ROLE", "ANON", "IN", "DATABASE")}, "fail"),
        ("roles.sql", 7, "permission denied", {7: ("GRANT", "ANON", "TO", "X")}, "fail"),
        ("schema.sql", 7, "invalid value", {7: ("ALTER", "ROLE", "ANON", "SET")}, "fail"),
        (
            "schema.sql",
            7,
            "does not exist",
            {7: ("ALTER", "PUBLICATION", "SUPABASE_REALTIME")},
            "platform",
        ),
        (
            "roles.sql",
            7,
            "does not exist",
            {7: ("ALTER", "PUBLICATION", "SUPABASE_REALTIME")},
            "fail",
        ),
        ("schema.sql", 7, "does not exist", {7: ("CREATE", "EXTENSION", "PGSODIUM")}, "fail"),
    ],
    ids=[
        "public",
        "bootstrap",
        "platform set",
        "platform in",
        "migration role",
        "an API role's timeout",
        "an API role's other setting",
        "an API role's database setting",
        "grant",
        "schema",
        "a publication entry",
        "a publication in the roles file",
        "an extension",
    ],
)
def test_restore_errors_are_classified(
    file: str, line: int, message: str, statements: dict, category: str
) -> None:
    error = scratch.RestoreError(file, line, message)
    by_file = {file: statements}
    api = frozenset({"anon", "authenticator"})
    found = prove._classify_error(error, by_file, MIGRATION, EXPECTED, api)  # noqa: SLF001
    assert found["category"] == category


@pytest.mark.parametrize(
    ("text", "kept"),
    [
        ("ALTER ROLE supabase_admin WITH SUPERUSER INHERIT LOGIN;", True),
        ("ALTER ROLE supabase_admin WITH NOSUPERUSER INHERIT LOGIN;", False),
        ("ALTER ROLE other WITH SUPERUSER;", False),
        (
            "ALTER ROLE supabase_admin WITH SUPERUSER;\nALTER ROLE supabase_admin WITH SUPERUSER;",
            False,
        ),
    ],
    ids=["kept", "demoted", "absent", "twice"],
)
def test_the_bootstrap_must_stay_a_superuser(tmp_path: Path, text: str, kept: bool) -> None:
    roles = tmp_path / "roles.sql"
    roles.write_text(text + "\n", encoding="utf-8")
    assert prove.keeps_superuser(roles, "supabase_admin") is kept


def write_export(folder: Path) -> dict[str, str]:
    folder.mkdir()
    (folder / "schema.sql").write_text(SCHEMA, encoding="utf-8")
    (folder / "roles.sql").write_text(ROLES, encoding="utf-8")
    return {
        name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
        for name in ("schema.sql", "roles.sql")
    }


@pytest.mark.parametrize(
    ("change", "kind"),
    [
        ({"digest": "schema.sql"}, "DIGEST_MISMATCH"),
        ({"owner": "supabase_admin"}, "BOOTSTRAP_IS_THE_OWNER"),
        ({"bootstrap": "another_superuser"}, "BOOTSTRAP_SUPERUSER_NOT_KEPT"),
    ],
    ids=["not the owner's file", "the owner as bootstrap", "a bootstrap the export lacks"],
)
def test_the_proof_refuses_before_any_server_starts(
    tmp_path: Path, change: dict[str, str], kind: str
) -> None:
    digests = write_export(tmp_path / "export")
    if "digest" in change:
        digests[change["digest"]] = "0" * 64
    work = tmp_path / "work"
    report = prove.run(
        tmp_path / "no-postgres-here",
        tmp_path / "export",
        work,
        restored_owner=change.get("owner", scratch.MIGRATION_OWNER),
        bootstrap=change.get("bootstrap", scratch.BOOTSTRAP_SUPERUSER),
        expected_sha256=digests,
    )
    assert report["verdict"] == "REFUSED_EXPORT"
    assert kinds([gate.Refusal(**item) for item in report["gate_refusals"]]) == [kind]
    assert not work.exists(), "no server was started, nothing was restored"


def fake_bin(folder: Path, release: str) -> Path:
    folder.mkdir()
    postgres = folder / "postgres"
    postgres.write_text(f"#!/bin/sh\necho 'postgres (PostgreSQL) {release}'\n", encoding="utf-8")
    postgres.chmod(0o755)
    return folder


@pytest.mark.parametrize("release", ["16.10", "17.5", "18.0"])
def test_the_proof_runs_only_on_postgresql_17_6_or_a_later_17(tmp_path: Path, release: str) -> None:
    digests = write_export(tmp_path / "export")
    work = tmp_path / "work"
    report = prove.run(
        fake_bin(tmp_path / "bin", release), tmp_path / "export", work, expected_sha256=digests
    )
    assert report["verdict"] == "REFUSED_TOOLS" and report["postgres"] == release
    assert not work.exists()
    assert scratch.server_version(tmp_path / "bin") == tuple(
        int(part) for part in release.split(".")
    )
    assert scratch.server_version(tmp_path / "none") is None


def test_the_restore_uses_the_checked_bytes_or_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The restore reads a private copy of the bytes the gate checked; a copy that differs from
    them (the files changed after the check) is refused before any server starts, and no copy is
    left behind."""

    digests = write_export(tmp_path / "export")

    def altered_copy(source: Path, target: Path) -> None:
        Path(target).write_bytes(Path(source).read_bytes() + b"-- changed after the check\n")

    monkeypatch.setattr(prove.shutil, "copyfile", altered_copy)
    work = tmp_path / "work"
    report = prove.run(
        fake_bin(tmp_path / "bin", "17.6"), tmp_path / "export", work, expected_sha256=digests
    )
    assert report["verdict"] == "REFUSED_EXPORT"
    assert [item["kind"] for item in report["gate_refusals"]] == ["DIGEST_CHANGED"]
    assert not (work / "export").exists() and not (work / "restored").exists()


def test_the_command_line_demands_both_digests(tmp_path: Path) -> None:
    write_export(tmp_path / "export")
    arguments = [
        "--pg-bin",
        str(tmp_path / "bin"),
        "--export",
        str(tmp_path / "export"),
        "--work",
        str(tmp_path / "work"),
        "--report",
        str(tmp_path / "report.json"),
        "--expect-sha256",
        "schema.sql=" + "0" * 64,
    ]
    assert prove.main(arguments) == 2
    assert not (tmp_path / "work").exists()


def test_no_pg_variable_of_the_callers_reaches_the_proof(monkeypatch: pytest.MonkeyPatch) -> None:
    """Review 2 of DP-D, finding 4: with PGHOSTADDR set, psql and psycopg ignore the socket."""

    monkeypatch.setenv("PGHOSTADDR", "192.0.2.1")
    monkeypatch.setenv("PGSERVICE", "production")
    with scratch.clean_pg_environment():
        assert [name for name in os.environ if name.startswith("PG")] == []
    assert os.environ["PGHOSTADDR"] == "192.0.2.1" and os.environ["PGSERVICE"] == "production"


def test_psql_reads_utf8_and_a_refused_value_is_not_repeated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict = {}
    stderr = (
        'psql:roles.sql:7: ERROR:  invalid value for parameter "statement_timeout": "s3cr3t"\n'
        'psql:roles.sql:9: ERROR:  role "supabase_admin" already exists\n'
    )

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.update(kwargs)
        return subprocess.CompletedProcess(args, 3, "", stderr)

    monkeypatch.setattr(scratch.subprocess, "run", fake_run)
    cluster = scratch.Cluster(tmp_path, tmp_path / "data", tmp_path / "socket", tmp_path / "x.log")
    done = cluster.psql(file=tmp_path / "roles.sql", stop_on_error=False)
    assert seen["env"]["PGCLIENTENCODING"] == "UTF8"
    assert scratch._errors(done, "roles.sql") == [  # noqa: SLF001
        scratch.RestoreError("roles.sql", 7, 'invalid value for parameter "statement_timeout"'),
        scratch.RestoreError("roles.sql", 9, 'role "supabase_admin" already exists'),
    ]


def test_a_stopped_cluster_leaves_no_data_and_no_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(scratch.subprocess, "run", fake_run)
    cluster = scratch.Cluster(tmp_path, tmp_path / "data", tmp_path / "socket", tmp_path / "x.log")
    for folder in (cluster.data, cluster.socket):
        folder.mkdir()
    cluster.log.write_text("ERROR:  a refused statement\n", encoding="utf-8")
    scratch.stop(cluster)
    assert not cluster.data.exists() and not cluster.socket.exists() and not cluster.log.exists()


# --------------------------------------------------------------------------- the card
def test_the_card_runs_the_rehearsed_commands_and_keeps_the_secret_out() -> None:
    schema = (
        " ".join(rehearse.SCHEMA_EXPORT[1:])
        + ' --file=schema.sql --password --dbname="$CONNECTION"'
    )
    roles = (
        " ".join(rehearse.ROLES_EXPORT[1:]) + ' --file=roles.sql --password --dbname="$CONNECTION"'
    )
    assert f'"$PGBIN/{rehearse.SCHEMA_EXPORT[0]}" {schema}' in CARD
    assert f'"$PGBIN/{rehearse.ROLES_EXPORT[0]}" {roles}' in CARD
    assert 'PGBIN="$(brew --prefix postgresql@17)/bin"' in CARD and "read -r CONNECTION" in CARD
    assert "shasum -a 256 schema.sql roles.sql" in CARD
    assert "--expect-sha256 schema.sql=" in CARD and "--expect-sha256 roles.sql=" in CARD
    # Only what a second export can fix sends the owner back to export again, and only once.
    assert "`DIGEST_MISMATCH`, `DATA_ENTRY` or a `PASSWORD_`" in CARD
    assert "again exactly, once. If the same kind comes back, stop" in " ".join(CARD.split())
    assert "nothing is changed or reclassified to hide one" in " ".join(CARD.split())
    assert "--expect-sha256" in prove.__doc__
    assert "Status: RUN ONCE, by the owner, on 2026-10-07." in CARD
    flat = " ".join(CARD.split())
    assert "delete `:[YOUR-PASSWORD]` from it" in flat, "typed at the prompt, never stored"
    for forbidden in ("PGPASSWORD", "export UCPE", "postgresql://postgres:"):
        assert forbidden not in CARD
