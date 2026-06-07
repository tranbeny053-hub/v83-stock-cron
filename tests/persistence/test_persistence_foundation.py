from __future__ import annotations

from pathlib import Path

from crypto_probability_engine.api.analysis_service import PersistenceWork, _best_effort_persist
from crypto_probability_engine.persistence.repository import (
    InMemoryPersistenceRepository,
    SupabasePersistenceRepository,
)

ROOT = Path(__file__).resolve().parents[2]


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeCursor:
    def __init__(self, rows=None, row=None) -> None:
        self.rows = rows or []
        self.row = row
        self.statements: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def execute(self, statement, params=None) -> None:
        self.statements.append(str(statement))

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, cursor: FakeCursor | None = None) -> None:
        self._cursor = cursor or FakeCursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def cursor(self) -> FakeCursor:
        return self._cursor


class FakePool:
    def __init__(self) -> None:
        self.attempts = 0
        self.fail = True
        self.closed = False

    def connection(self, timeout=None):
        self.attempts += 1
        if self.fail:
            raise RuntimeError("database unavailable")
        return FakeConnection()

    def close(self) -> None:
        self.closed = True


def test_in_memory_repository_watchlist_and_runs_are_stateless() -> None:
    repo = InMemoryPersistenceRepository()
    assert repo.persistence_status() == "STATELESS"
    assert repo.add_watchlist("BTC/USDT") == "STATELESS"
    assert repo.list_watchlist() == ["BTC/USDT"]
    assert repo.remove_watchlist("BTC/USDT") == "STATELESS"
    assert repo.list_watchlist() == []

    repo.save_run(
        {
            "run_id": "run_test",
            "symbol": "BTC",
            "normalized_symbol": "BTC/USDT",
            "analysis_mode": "METRICS_ONLY",
        }
    )
    assert repo.get_run("run_test")["normalized_symbol"] == "BTC/USDT"
    assert repo.recent_runs(1)[0]["run_id"] == "run_test"


def test_initial_migration_is_idempotent_and_contains_no_secret_values() -> None:
    sql = (ROOT / "migrations" / "0001_init.sql").read_text(encoding="utf-8")
    for table in (
        "watchlist",
        "analysis_runs",
        "analysis_timeframe_results",
        "provider_observations",
        "app_events",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    assert "CREATE INDEX IF NOT EXISTS" in sql
    assert "ALTER TABLE" not in sql
    assert "DROP TABLE" not in sql
    for marker in ("SUPABASE_DB_URL", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"):
        assert marker not in sql


def test_best_effort_persist_defensively_marks_unavailable() -> None:
    class RaisingRepository:
        def __init__(self) -> None:
            self.marked = False

        def persistence_status(self) -> str:
            return "OK"

        def mark_unavailable(self) -> str:
            self.marked = True
            return "UNAVAILABLE"

        def save_run(self, summary: dict) -> str:
            raise RuntimeError("unexpected persistence failure")

        def save_timeframe_result(self, row: dict) -> str:
            return "OK"

        def save_provider_observation(self, row: dict) -> str:
            return "OK"

    repo = RaisingRepository()
    work = PersistenceWork(
        run_summary={"run_id": "run_test"},
        timeframe_result={"run_id": "run_test", "timeframe": "4H"},
        provider_observations=({"run_id": "run_test", "provider": "fixture"},),
    )
    assert _best_effort_persist(work, repo) == "UNAVAILABLE"
    assert repo.marked is True


def test_supabase_circuit_breaker_skips_attempts_until_cooldown() -> None:
    clock = FakeClock()
    pool = FakePool()
    repo = SupabasePersistenceRepository(
        "postgresql://example.invalid/db",
        pool_factory=lambda: pool,
        circuit_cooldown_seconds=60.0,
        clock=clock,
    )

    assert repo.save_run({"run_id": "run_test"}) == "UNAVAILABLE"
    assert pool.attempts == 1
    assert repo.persistence_status() == "UNAVAILABLE"

    assert repo.save_timeframe_result({"run_id": "run_test"}) == "UNAVAILABLE"
    assert pool.attempts == 1

    clock.advance(61.0)
    pool.fail = False
    assert repo.save_provider_observation({"run_id": "run_test"}) == "OK"
    assert pool.attempts == 2
    assert repo.persistence_status() == "OK"
    repo.close()
    assert pool.closed is True
