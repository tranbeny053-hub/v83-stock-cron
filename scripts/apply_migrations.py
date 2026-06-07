"""Apply idempotent SQL migrations to the configured Supabase Postgres database."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "migrations"


def main() -> int:
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

    try:
        with psycopg.connect(db_url, connect_timeout=8) as conn:
            with conn.cursor() as cursor:
                for path in migration_paths:
                    cursor.execute(path.read_text(encoding="utf-8"))
                    print(f"applied {path.name}")
    except Exception as exc:
        print(f"ERROR: migration failed without printing the database URL: {type(exc).__name__}")
        return 1
    print("PASS: migrations applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
