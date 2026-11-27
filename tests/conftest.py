from __future__ import annotations

import socket

import pytest

from crypto_probability_engine.api import analysis_service


@pytest.fixture
def lean_reference_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opt one test out of the Lean reference, ON by default since 2026-11-27 (owner).

    Only for a test that pins the legacy heuristic path on a named cell; every other test runs the
    shipped default.
    """
    monkeypatch.setattr(analysis_service, "LEAN_REFERENCE_ENABLED", False)


@pytest.fixture(autouse=True)
def disable_real_lattice_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep tests from starting the real lattice runner.
    monkeypatch.delenv("UCPE_LATTICE_DB_URL", raising=False)


@pytest.fixture(autouse=True)
def block_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked_connect(*args, **kwargs):
        raise RuntimeError("Unit tests must not open real network sockets.")

    def blocked_create_connection(*args, **kwargs):
        raise RuntimeError("Unit tests must not open real network sockets.")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect)
    monkeypatch.setattr(socket, "create_connection", blocked_create_connection)
