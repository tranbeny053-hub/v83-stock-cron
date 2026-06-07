from __future__ import annotations

from pathlib import Path

from crypto_probability_engine.persistence.repository import InMemoryPersistenceRepository

ROOT = Path(__file__).resolve().parents[2]


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
