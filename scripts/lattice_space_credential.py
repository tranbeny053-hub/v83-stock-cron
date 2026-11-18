"""Owner-only credential helper for ucpe_lattice_space, after the 0019 + 0020 apply T4.

Never run by Claude. Authoring this helper issues nothing. The login SQL is guarded per owner
ruling D, 2026-11-18; a refusal grants nothing. The Space then holds two DB secrets, each path
narrowed; a Space compromise exposes both. Nothing secret is printed.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from scripts import resolver_credential as base

ROLE = "ucpe_lattice_space"
SQL_NAME = "ucpe-lattice-space-login.sql"
URL_NAME = "ucpe-lattice-space-db-url.txt"
SECRET_NAME = "UCPE_LATTICE_DB_URL"


def guarded_login_sql(plain: str, role: str = ROLE) -> str:
    """Build login SQL that validates the complete post-0020 security boundary first."""

    if role != ROLE:
        raise ValueError("the guarded login is only for ucpe_lattice_space")

    verifier = base.scram_verifier(plain)
    tag = "$ucpe_login$"
    assert tag not in verifier
    role_literal = "'" + role.replace("'", "''") + "'"
    return f"""-- Owner ruling D, 2026-11-18: refuse LOGIN unless all boundary checks pass.
DO $ucpe_login$
DECLARE
    space_oid oid;
    writer_oid oid;
    setting_rows integer;
    member_rows integer;
    outside_count bigint;
    accepted_count bigint;
    extensions_usage boolean := false;
BEGIN
    PERFORM pg_catalog.set_config('search_path', 'pg_catalog, pg_temp', true);

    SELECT (SELECT r.oid FROM pg_catalog.pg_roles r
             WHERE r.rolname = 'ucpe_lattice_space'),
           (SELECT r.oid FROM pg_catalog.pg_roles r
             WHERE r.rolname = 'ucpe_lattice_writer')
      INTO space_oid, writer_oid;
    IF space_oid IS NULL OR writer_oid IS NULL THEN
        RAISE EXCEPTION 'required roles are missing' USING ERRCODE = 'UPL01';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles r
         WHERE r.oid = space_oid AND NOT r.rolcanlogin AND NOT r.rolinherit
           AND NOT r.rolsuper AND NOT r.rolcreatedb AND NOT r.rolcreaterole
           AND NOT r.rolreplication AND NOT r.rolbypassrls AND r.rolconnlimit = 3
           AND r.rolvaliduntil IS NULL
    ) THEN
        RAISE EXCEPTION 'space role attributes changed' USING ERRCODE = 'UPL02';
    END IF;

    SELECT pg_catalog.count(*) INTO member_rows
      FROM pg_catalog.pg_auth_members m WHERE m.member = space_oid;
    IF member_rows <> 1 OR NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_auth_members m
         WHERE m.member = space_oid AND m.roleid = writer_oid
           AND m.inherit_option AND NOT m.set_option AND NOT m.admin_option
    ) THEN
        RAISE EXCEPTION 'space role membership changed' USING ERRCODE = 'UPL03';
    END IF;

    SELECT pg_catalog.count(*) INTO setting_rows
      FROM pg_catalog.pg_db_role_setting s WHERE s.setrole = space_oid;
    IF setting_rows <> 1 OR NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_db_role_setting s
         WHERE s.setrole = space_oid AND s.setdatabase = 0
           AND (SELECT pg_catalog.array_agg(u.setting ORDER BY u.setting)
                  FROM pg_catalog.unnest(s.setconfig) AS u(setting)) =
               ARRAY['idle_in_transaction_session_timeout=30s', 'lock_timeout=2s',
                     'statement_timeout=5s']::text[]
    ) THEN
        RAISE EXCEPTION 'space role settings changed' USING ERRCODE = 'UPL04';
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles r
         WHERE r.oid <> space_oid AND NOT r.rolsuper
           AND pg_catalog.pg_has_role(r.oid, space_oid, 'SET')
    ) THEN
        RAISE EXCEPTION 'another role can SET ROLE to the space role' USING ERRCODE = 'UPL05';
    END IF;

    SELECT pg_catalog.count(*) INTO outside_count
      FROM (
          SELECT n.nspname, c.relname
            FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
           WHERE n.nspname NOT IN
                 ('pg_catalog', 'information_schema', 'pg_toast', 'public', 'ucpe_lattice')
             AND n.nspname NOT LIKE 'pg_temp_%'
             AND n.nspname NOT LIKE 'pg_toast_temp_%'
             AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
             AND (pg_catalog.has_table_privilege(space_oid, c.oid,
                    'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
                  OR pg_catalog.has_any_column_privilege(space_oid, c.oid,
                    'SELECT,INSERT,UPDATE,REFERENCES')
                  OR CASE WHEN c.relkind = 'S' THEN
                       pg_catalog.has_sequence_privilege(space_oid, c.oid, 'USAGE,SELECT,UPDATE')
                     ELSE false END)
             AND NOT (
                 n.nspname = 'extensions'
                 AND c.relname IN ('pg_stat_statements', 'pg_stat_statements_info')
                 AND c.relkind <> 'S'
                 AND NOT pg_catalog.has_table_privilege(space_oid, c.oid,
                       'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
                 AND NOT pg_catalog.has_any_column_privilege(space_oid, c.oid,
                       'INSERT,UPDATE,REFERENCES')
             )
      ) AS x;
    IF outside_count > 0 THEN
        RAISE EXCEPTION 'outside relation reach %, examples: %', outside_count,
            (SELECT pg_catalog.string_agg(y.relation_name, ', ' ORDER BY y.nspname, y.relname)
               FROM (
                   SELECT n.nspname, c.relname,
                          pg_catalog.quote_ident(n.nspname) || '.' ||
                          pg_catalog.quote_ident(c.relname) AS relation_name
                     FROM pg_catalog.pg_class c
                     JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname NOT IN
                          ('pg_catalog', 'information_schema', 'pg_toast', 'public',
                           'ucpe_lattice')
                      AND n.nspname NOT LIKE 'pg_temp_%'
                      AND n.nspname NOT LIKE 'pg_toast_temp_%'
                      AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
                      AND (pg_catalog.has_table_privilege(space_oid, c.oid,
                             'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
                           OR pg_catalog.has_any_column_privilege(space_oid, c.oid,
                             'SELECT,INSERT,UPDATE,REFERENCES')
                           OR CASE WHEN c.relkind = 'S' THEN
                                pg_catalog.has_sequence_privilege(space_oid, c.oid,
                                  'USAGE,SELECT,UPDATE') ELSE false END)
                      AND NOT (n.nspname = 'extensions'
                        AND c.relname IN ('pg_stat_statements', 'pg_stat_statements_info')
                        AND c.relkind <> 'S'
                        AND NOT pg_catalog.has_table_privilege(space_oid, c.oid,
                              'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
                        AND NOT pg_catalog.has_any_column_privilege(space_oid, c.oid,
                              'INSERT,UPDATE,REFERENCES'))
                    ORDER BY n.nspname, c.relname LIMIT 20
               ) AS y) USING ERRCODE = 'UPL06';
    END IF;

    SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_namespace n
                    WHERE n.nspname = 'extensions'
                      AND pg_catalog.has_schema_privilege(space_oid, n.oid, 'USAGE'))
      INTO extensions_usage;
    SELECT pg_catalog.count(*) INTO accepted_count
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'extensions'
       AND c.relname IN ('pg_stat_statements', 'pg_stat_statements_info')
       AND c.relkind <> 'S'
       AND (pg_catalog.has_table_privilege(space_oid, c.oid,
              'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
            OR pg_catalog.has_any_column_privilege(space_oid, c.oid,
              'SELECT,INSERT,UPDATE,REFERENCES'));
    RAISE NOTICE 'extensions USAGE: %, accepted relations reached: %',
        extensions_usage, accepted_count;

    EXECUTE pg_catalog.format('ALTER ROLE %I WITH LOGIN PASSWORD %L',
                              {role_literal}, '{verifier}');
    RAISE NOTICE 'every guarded login check passed; LOGIN was granted';
END
$ucpe_login$;
"""


def main(
    argv: Sequence[str] | None = None,
    *,
    paste: Callable[[], str] = base.pbpaste,
    clipboard: Callable[[str], None] = base.pbcopy,
) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.lattice_space_credential")
    parser.add_argument("command", choices=("generate", "copy-sql", "copy-url"))
    parser.add_argument("--dir", type=Path, default=base.KEY_DIR)
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            made = base.generate(
                args.dir, paste(), role=ROLE, sql_name=SQL_NAME, url_name=URL_NAME,
                login=guarded_login_sql,
            )
            print(
                f"role: {ROLE}\nconnection: {made['mode']}\n"
                f"login SQL: {made['sql']}\nSpace URL: {made['url']}"
            )
            print("Both files are secret: never in a repository, a chat or a log.")
        elif args.command == "copy-sql":
            clipboard(base.read(args.dir, SQL_NAME))
            print("The login SQL is on the clipboard for the applying role's SQL Editor.")
        else:
            clipboard(base.read(args.dir, URL_NAME).strip())
            print(f"The Space URL is on the clipboard for Space secret {SECRET_NAME}.")
    except base.CredentialError as refusal:
        print(f"REFUSED: {refusal}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
