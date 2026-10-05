"""The structure-first restore proof (plan §12.1, §23 "Backup"; owner ruling DP-D=2), offline.

What a database is not needed for, checked here:
- the export gate refuses, at the first sight and without echoing it, a data entry, a COPY block, a
  password clause or hash, any psql meta-command but the \\restrict pair, a statement that is not
  schema or role DDL, the wrong pg_dump major, and a file that is not the owner's (its digest);
- its scanner splits a psql script as psql does: nothing inside a quoted string, a quoted
  identifier, a dollar-quoted body or a comment is taken for a statement or a meta-command;
- the comparison classifies exactly: the owner's documented LOGIN steps are operational, a platform
  role's default privileges are platform, and everything else is app;
- the restore errors are classified: the two every restore raises are expected, a platform role's
  own setting is platform, anything else fails;
- the proof refuses before any server starts, and refuses an export that would take superuser from
  the bootstrap role or that names the owner as the bootstrap;
- the migration roles come from the migration files, and the card's commands are the rehearsal's.
The database half runs in .github/workflows/restore-proof-rehearsal.yml (rehearse.py).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.restore_proof import catalog, gate, prove, rehearse, scratch

ROOT = Path(__file__).resolve().parents[2]
CARD = (ROOT / "docs/runbooks/RESTORE_PROOF_EXPORT.md").read_text(encoding="utf-8")
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
COMMENT ON TABLE public."t;x" IS E'a \\' quote; and -- no comment';
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
        ("--\n-- PostgreSQL database dump", "SET a = 1;\n--\n-- PostgreSQL database dump", None),
    ],
    ids=["no restrict", "no unrestrict", "another key", "a statement before restrict"],
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


def test_the_scanner_splits_as_psql_does() -> None:
    statements, metas = gate.scan(SCHEMA)
    # Six statements: no split inside the quoted identifier "t;x", the E-string's "; and --", the
    # nested comment or the dollar-quoted body (whose INSERT and backslash line are not top level).
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


# --------------------------------------------------------------------------- the comparison
def fingerprint(**changes: object) -> dict:
    base = {
        "relations": {"predictions": {"acl": ["anon:SELECT by <owner>"], "row_security": True}},
        "functions": {"f()": {"definition_sha256": "a", "definition": "CREATE f\nbody", "acl": []}},
        "default_privileges": {"<owner> r": ["anon:SELECT by <owner>"]},
        "roles": {
            "attributes": {
                "ucpe_space_db": {"rolcanlogin": False},
                "ucpe_api_writer": {"rolcanlogin": False},
            },
            "memberships": ["ucpe_api_writer to authenticator admin=False inherit=False set=True"],
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
    restored["roles"]["attributes"]["ucpe_space_db"]["rolcanlogin"] = True
    restored["roles"]["attributes"]["ucpe_api_writer"]["rolcanlogin"] = True
    found = {(item.category, item.path) for item in catalog.compare(fingerprint(), restored)}
    assert found == {
        ("operational", "roles/attributes/ucpe_space_db/rolcanlogin"),
        ("app", "roles/attributes/ucpe_api_writer/rolcanlogin"),
    }
    reverse = {(item.category, item.path) for item in catalog.compare(restored, fingerprint())}
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


def test_the_api_roles_are_reported_as_platform() -> None:
    reference = {
        "platform_roles": {"attributes": {"anon": {"rolbypassrls": False}}, "memberships": []}
    }
    restored = {
        "platform_roles": {
            "attributes": {"anon": {"rolbypassrls": True}},
            "memberships": ["anon to authenticator admin=False inherit=False set=True"],
        }
    }
    found = {(item.category, item.path) for item in catalog.compare(reference, restored)}
    assert found == {
        ("platform", "platform_roles/attributes/anon/rolbypassrls"),
        (
            "platform",
            "platform_roles/memberships/anon to authenticator admin=False inherit=False set=True",
        ),
    }


def test_memberships_differ_item_by_item_and_functions_by_digest() -> None:
    restored = fingerprint()
    restored["roles"]["memberships"] = [
        "service_role to ucpe_space_db admin=False inherit=False set=True"
    ]
    restored["functions"]["f()"] = {
        "definition_sha256": "b",
        "definition": "CREATE f\nother",
        "acl": [],
    }
    found = {(item.category, item.path) for item in catalog.compare(fingerprint(), restored)}
    assert found == {
        (
            "app",
            "roles/memberships/ucpe_api_writer to authenticator admin=False inherit=False set=True",
        ),
        (
            "app",
            "roles/memberships/service_role to ucpe_space_db admin=False inherit=False set=True",
        ),
        ("app", "functions/f()/definition_sha256"),
    }
    assert catalog.function_diff(fingerprint(), restored) == {
        "f()": {"line": 2, "reference": "body", "restored": "other"}
    }


def test_the_migration_roles_come_from_the_migration_files() -> None:
    assert catalog.migration_roles(ROOT / "migrations") == {
        "ucpe_api_writer",
        "ucpe_bundle_owner",
        "ucpe_space_db",
        "ucpe_resolver",
    }


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
        ("roles.sql", 7, "invalid value", {7: ("ALTER", "ROLE", "ANON", "SET")}, "platform"),
        ("roles.sql", 7, "invalid value", {7: ("ALTER", "ROLE", "ANON", "IN")}, "platform"),
        ("roles.sql", 7, "invalid value", {7: ("ALTER", "ROLE", "UCPE_API_WRITER", "SET")}, "fail"),
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
    roles = catalog.migration_roles(ROOT / "migrations")
    by_file = {file: statements}
    assert prove._classify_error(error, by_file, roles, EXPECTED)["category"] == category  # noqa: SLF001


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
    # Only what a second export can fix sends the owner back to export again.
    assert "`DIGEST_MISMATCH`, `DATA_ENTRY` or a `PASSWORD_`" in CARD
    assert "--expect-sha256" in prove.__doc__
    assert "Status: PREPARED, NOT RUN." in CARD
    flat = " ".join(CARD.split())
    assert "delete `:[YOUR-PASSWORD]` from it" in flat, "typed at the prompt, never stored"
    for forbidden in ("PGPASSWORD", "export UCPE", "postgresql://postgres:"):
        assert forbidden not in CARD
