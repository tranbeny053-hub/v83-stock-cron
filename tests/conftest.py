from __future__ import annotations

import socket

import pytest


@pytest.fixture(autouse=True)
def block_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked_connect(*args, **kwargs):
        raise RuntimeError("Unit tests must not open real network sockets.")

    def blocked_create_connection(*args, **kwargs):
        raise RuntimeError("Unit tests must not open real network sockets.")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect)
    monkeypatch.setattr(socket, "create_connection", blocked_create_connection)
