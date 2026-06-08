from __future__ import annotations

from pathlib import Path

import httpx

from crypto_probability_engine.api.analysis_service import PersistenceWork, _best_effort_persist
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.persistence.repository import (
    InMemoryPersistenceRepository,
    SupabasePersistenceRepository,
    SupabaseRestRepository,
    build_persistence_repository,
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


def rest_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_runtime_selection_prefers_supabase_rest_over_postgres_url() -> None:
    repo = build_persistence_repository(
        Settings(
            **{
                "supabase_url": "https://project.example.supabase.co",
                "supabase_service_role_key": "test-service-role-key",
                "supabase_db_url": "postgresql://example.invalid/db",
            }
        )
    )

    assert isinstance(repo, SupabaseRestRepository)
    assert repo.repository_type() == "SUPABASE_REST"
    repo.close()


def test_runtime_selection_keeps_direct_postgres_when_rest_is_absent() -> None:
    repo = build_persistence_repository(
        Settings(**{"supabase_db_url": "postgresql://example.invalid/db"})
    )

    assert isinstance(repo, SupabasePersistenceRepository)
    assert repo.repository_type() == "SUPABASE_POSTGRES"


def test_supabase_rest_writes_compact_rows_with_backend_only_headers() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.url.host == "project.example.supabase.co"
        assert request.headers["apikey"] == "test-service-role-key"
        assert request.headers["authorization"] == "Bearer test-service-role-key"
        return httpx.Response(201, json=[])

    repo = SupabaseRestRepository(
        "https://project.example.supabase.co",
        "test-service-role-key",
        client=rest_client(handler),
    )

    assert repo.save_run(_sample_run_summary()) == "OK"
    assert repo.save_timeframe_result(_sample_timeframe_result()) == "OK"
    assert repo.save_provider_observation(_sample_provider_observation()) == "OK"
    assert [request.url.path for request in seen] == [
        "/rest/v1/analysis_runs",
        "/rest/v1/analysis_timeframe_results",
        "/rest/v1/provider_observations",
    ]
    assert "test-service-role-key" not in repo.repository_type()
    assert repo.persistence_status() == "OK"


def test_supabase_rest_writes_compact_news_metadata_rows() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = request.read().decode("utf-8")
        assert "article_body" not in body
        assert "full_text" not in body
        return httpx.Response(201, json=[])

    repo = SupabaseRestRepository(
        "https://project.example.supabase.co",
        "test-service-role-key",
        client=rest_client(handler),
    )

    assert repo.save_news_item(_sample_news_item()) == "OK"
    assert repo.save_news_cluster(_sample_news_cluster()) == "OK"
    assert repo.save_news_evidence_link(_sample_news_link()) == "OK"
    assert [request.url.path for request in seen] == [
        "/rest/v1/news_items",
        "/rest/v1/news_clusters",
        "/rest/v1/news_evidence_links",
    ]


def test_supabase_rest_watchlist_crud_uses_mocked_https() -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(200, json=[{"display_symbol": "BTC/USDT"}])
        return httpx.Response(201 if request.method == "POST" else 204)

    repo = SupabaseRestRepository(
        "https://project.example.supabase.co",
        "test-service-role-key",
        client=rest_client(handler),
    )

    assert repo.add_watchlist("BTC/USDT") == "OK"
    assert repo.list_watchlist() == ["BTC/USDT"]
    assert repo.remove_watchlist("BTC/USDT") == "OK"
    assert seen == [
        ("POST", "/rest/v1/watchlist"),
        ("GET", "/rest/v1/watchlist"),
        ("DELETE", "/rest/v1/watchlist"),
    ]


def test_supabase_rest_failure_opens_circuit_and_uses_fallback() -> None:
    clock = FakeClock()
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, json={"message": "database unavailable"})

    repo = SupabaseRestRepository(
        "https://project.example.supabase.co",
        "test-service-role-key",
        client=rest_client(handler),
        circuit_cooldown_seconds=60.0,
        clock=clock,
    )

    assert repo.save_run(_sample_run_summary()) == "UNAVAILABLE"
    assert repo.persistence_status() == "UNAVAILABLE"
    assert repo.circuit_state() == "OPEN"
    assert attempts == 1

    assert repo.save_timeframe_result(_sample_timeframe_result()) == "UNAVAILABLE"
    assert attempts == 1
    assert repo.get_run("run_rest")["run_id"] == "run_rest"


def _sample_run_summary() -> dict:
    return {
        "run_id": "run_rest",
        "operator_id": "operator",
        "symbol": "BTC",
        "normalized_symbol": "BTC/USDT",
        "analysis_mode": "METRICS_ONLY",
        "asset_class": "CRYPTO_SPOT",
        "primary_timeframe": "4H",
        "disposition": "NO_TRADE",
        "total_score": 50.0,
        "data_source": "FIXTURE_DEMO",
        "is_live_data": False,
        "persistence_status": "OK",
        "analysis_hash": "hash",
        "as_of_utc": "2026-06-07T00:00:00Z",
    }


def _sample_timeframe_result() -> dict:
    return {
        "run_id": "run_rest",
        "timeframe": "4H",
        "disposition": "NO_TRADE",
        "total_score": 50.0,
        "prob_up_pct": 40.0,
        "prob_down_pct": 40.0,
        "prob_timeout_pct": 20.0,
        "gate_action": "NO_TRADE",
        "data_source": "FIXTURE_DEMO",
        "is_live_data": False,
    }


def _sample_provider_observation() -> dict:
    return {
        "run_id": "run_rest",
        "provider": "fixture",
        "provider_status": "OK",
        "active_provider": "fixture",
        "data_source": "FIXTURE_DEMO",
        "is_live_data": False,
        "warning_count": 0,
    }


def _sample_news_item() -> dict:
    return {
        "item_id": "urlhash",
        "run_id": "run_rest",
        "normalized_symbol": "BTC/USDT",
        "provider": "gdelt",
        "source_name": "Example",
        "domain": "example.com",
        "title": "Bitcoin ETF metadata item",
        "snippet": "Metadata summary only.",
        "url": "https://example.com/news",
        "url_hash": "urlhash",
        "title_hash": "titlehash",
        "published_at": "2026-06-08T10:00:00Z",
        "fetched_at": "2026-06-08T12:00:00Z",
        "language": "en",
        "macro_or_micro": "MICRO",
        "event_class": "ASSET_SPECIFIC",
        "relevance_score": 0.8,
        "freshness_score": 1.0,
        "source_authority_score": 0.7,
        "confidence_score": 0.8,
        "cluster_id": "cluster_1",
    }


def _sample_news_cluster() -> dict:
    return {
        "cluster_id": "cluster_1",
        "run_id": "run_rest",
        "normalized_symbol": "BTC/USDT",
        "representative_title": "Bitcoin ETF metadata item",
        "macro_or_micro": "MICRO",
        "event_class": "ASSET_SPECIFIC",
        "source_count": 1,
        "item_count": 1,
        "dropped_count": 0,
        "max_relevance_score": 0.8,
    }


def _sample_news_link() -> dict:
    return {
        "run_id": "run_rest",
        "cluster_id": "cluster_1",
        "item_id": "urlhash",
        "evidence_type": "ADVISORY_NEWS_METADATA",
        "relevance_score": 0.8,
    }
