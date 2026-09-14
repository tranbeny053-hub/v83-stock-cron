"""Apply idempotent SQL migrations to the configured Supabase Postgres database.

AUDIT FINDING (2026-09-12): this script has no migration ledger. It globs every ``*.sql``,
sorts, and applies them ALL in one transaction, relying only on each file being
idempotent. There is therefore no way to apply one migration without applying every
other — so adding a new migration and running the default path would FORCE the
deliberately-unapplied ``0008_analysis_run_details.sql``, consuming a T4 that has never
been authorized.

``--only NAME`` exists for exactly that reason. The default behaviour is unchanged.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "migrations"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply SQL migrations.")
    parser.add_argument(
        "--only",
        action="append",
        default=None,
        metavar="NAME",
        help=(
            "Apply ONLY the named migration file(s), e.g. "
            "--only 0009_section_5a_evaluation_seal.sql. Repeatable. Without this the "
            "script applies EVERY migration, which would include any deliberately "
            "unapplied one."
        ),
    )
    return parser


def select_migrations(paths: list[Path], only: list[str] | None) -> list[Path] | None:
    """Return the migrations to apply, or ``None`` when a requested name is absent."""

    if not only:
        return paths
    by_name = {path.name: path for path in paths}
    selected = []
    for name in only:
        if name not in by_name:
            return None
        selected.append(by_name[name])
    return sorted(set(selected))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        print("ERROR: SUPABASE_DB_URL is required to apply migrations.")
        return 2
    try:
        import psycopg
    except ImportError:
        print("ERROR: psycopg is not installed. Run: pip install -r requirements.txt")
        return 2

    migration_paths = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_paths:
        print("ERROR: no migrations found.")
        return 2

    selected = select_migrations(migration_paths, args.only)
    if selected is None:
        print("ERROR: --only named a migration that does not exist.")
        return 2
    print("WILL APPLY: " + ", ".join(path.name for path in selected))

    try:
        with psycopg.connect(db_url, connect_timeout=8) as conn:
            with conn.cursor() as cursor:
                for path in selected:
                    cursor.execute(path.read_text(encoding="utf-8"))
                    print(f"applied {path.name}")
    except Exception as exc:
        print(f"ERROR: migration failed without printing the database URL: {type(exc).__name__}")
        return 1
    print("PASS: migrations applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
