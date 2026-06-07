from __future__ import annotations

from fastapi.testclient import TestClient

from crypto_probability_engine.api.app import create_app
from crypto_probability_engine.api.auth import dev_limiter, hash_code, session_limiter
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.persistence.repository import InMemoryPersistenceRepository


def make_client() -> TestClient:
    session_limiter.reset()
    dev_limiter.reset()
    settings = Settings(
        access_code_hash=hash_code("operator-test-code"),
        session_signing_key="test-signing-key",
        session_cookie_secure=False,
        data_mode="fixture",
    )
    return TestClient(create_app(settings))


def login(client: TestClient) -> None:
    response = client.post("/v1/auth/login", json={"code": "operator-test-code"})
    assert response.status_code == 200


def test_watchlist_requires_session() -> None:
    client = make_client()
    response = client.get("/v1/watchlist")
    assert response.status_code == 401


def test_watchlist_crud_uses_in_memory_fallback_and_normalizer() -> None:
    client = make_client()
    login(client)

    empty = client.get("/v1/watchlist")
    assert empty.status_code == 200
    assert empty.json() == {"symbols": [], "persistence_status": "STATELESS"}

    created = client.post("/v1/watchlist", json={"symbol": "btc"})
    assert created.status_code == 200
    assert created.json()["symbols"] == ["BTC/USDT"]
    assert created.json()["persistence_status"] == "STATELESS"

    duplicate = client.post("/v1/watchlist", json={"symbol": "BTC/USDT"})
    assert duplicate.status_code == 200
    assert duplicate.json()["symbols"] == ["BTC/USDT"]

    removed = client.delete("/v1/watchlist/BTC/USDT")
    assert removed.status_code == 200
    assert removed.json()["symbols"] == []


def test_watchlist_rejects_invalid_symbol() -> None:
    client = make_client()
    login(client)
    response = client.post("/v1/watchlist", json={"symbol": "NOPE"})
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "INVALID_SYMBOL"


def test_watchlist_degrades_to_in_memory_repository_quickly() -> None:
    class DegradedRepository(InMemoryPersistenceRepository):
        def persistence_status(self) -> str:
            return "UNAVAILABLE"

        def add_watchlist(self, symbol: str, operator_id: str = "operator") -> str:
            super().add_watchlist(symbol, operator_id)
            return "UNAVAILABLE"

        def remove_watchlist(self, symbol: str, operator_id: str = "operator") -> str:
            super().remove_watchlist(symbol, operator_id)
            return "UNAVAILABLE"

    client = make_client()
    client.app.state.persistence_repository = DegradedRepository()
    login(client)
    response = client.post("/v1/watchlist", json={"symbol": "BTC"})
    assert response.status_code == 200
    assert response.json()["symbols"] == ["BTC/USDT"]
    assert response.json()["persistence_status"] == "UNAVAILABLE"
