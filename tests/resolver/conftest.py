from __future__ import annotations

import psycopg
import pytest


@pytest.fixture(autouse=True)
def block_real_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """libpq opens its own sockets, past the socket guard: a resolver test never reaches it.

    main() runs Route C's preflight whenever the repository is direct Postgres, so a test that
    sets SUPABASE_DB_URL gets this error instead: status_store=error, the legacy path. Tests that
    exercise the Postgres store patch psycopg.connect with a psycopg-shaped fake.
    """

    def blocked(*args, **kwargs):
        raise RuntimeError("Unit tests must not open real database connections.")

    monkeypatch.setattr(psycopg, "connect", blocked)
