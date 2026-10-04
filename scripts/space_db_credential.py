"""E2: the owner's login credential for the Space's evidence reader, ucpe_space_db.

Owner-only, on the owner's own Mac, run from the repository root. Migration 0016 made the role
NOLOGIN until the owner's credential step (docs/runbooks/SPACE_DB_CUTOVER.md). Three commands:

    .venv/bin/python -m scripts.space_db_credential generate
    .venv/bin/python -m scripts.space_db_credential copy-sql
    .venv/bin/python -m scripts.space_db_credential copy-url

They are G1's resolver helper (scripts/resolver_credential.py) for another role, unchanged in every
rule: generate reads the dashboard's connection URI from the clipboard, its [YOUR-PASSWORD]
placeholder still in it, makes a random password, and writes two owner-only files in ~/ucpe-keys,
never inside this repository and never over an existing file:
- ucpe-space-db-login.sql: ALTER ROLE ucpe_space_db WITH LOGIN PASSWORD '<SCRAM-SHA-256 secret>',
  computed here, so the password itself never reaches the database;
- ucpe-space-db-url.txt: the template with ucpe_space_db as its user ([ROLE].[PROJECT-REF] through
  the shared pooler) and the password.
copy-sql copies the SQL, for the dashboard's SQL Editor; copy-url copies the URL, for the Space
secret UCPE_SPACE_DB_URL. Nothing secret is ever printed: not the password, the SCRAM secret or the
URL.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from scripts import resolver_credential as base

ROLE = "ucpe_space_db"
SQL_NAME = "ucpe-space-db-login.sql"
URL_NAME = "ucpe-space-db-url.txt"
SECRET_NAME = "UCPE_SPACE_DB_URL"


def main(
    argv: Sequence[str] | None = None,
    *,
    paste: Callable[[], str] = base.pbpaste,
    clipboard: Callable[[str], None] = base.pbcopy,
) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.space_db_credential",
        description="E2: the Space reader's login (generate), SQL (copy-sql), URL (copy-url).",
    )
    parser.add_argument("command", choices=("generate", "copy-sql", "copy-url"))
    parser.add_argument("--dir", type=Path, default=base.KEY_DIR,
                        help="the key folder, outside this repository (default: ~/ucpe-keys)")
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "generate":
            made = base.generate(
                arguments.dir, paste(), role=ROLE, sql_name=SQL_NAME, url_name=URL_NAME
            )
            print(f"role: {ROLE}")
            print(f"connection: {made['mode']}")
            print(f"login SQL: {made['sql']}")
            print(f"Space URL: {made['url']}")
            print("Both files are secret: never in a repository, a chat or a log.")
        elif arguments.command == "copy-sql":
            clipboard(base.read(arguments.dir, SQL_NAME))
            print("The login SQL is on the clipboard, for the dashboard's SQL Editor.")
        else:
            clipboard(base.read(arguments.dir, URL_NAME).strip())
            print(f"The Space URL is on the clipboard, for the Space secret {SECRET_NAME}.")
    except base.CredentialError as refusal:
        print(f"REFUSED: {refusal}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
