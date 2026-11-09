"""Owner-only credential helper for ucpe_lattice_space, after the 0019 + 0020 apply T4.

Never run by Claude. Authoring this helper issues nothing. The Space then holds two DB secrets,
each path narrowed; a Space compromise exposes both. Nothing secret is printed.
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
            made = base.generate(args.dir, paste(), role=ROLE, sql_name=SQL_NAME, url_name=URL_NAME)
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
