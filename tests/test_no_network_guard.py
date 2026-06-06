from __future__ import annotations

import socket

import pytest


def test_unit_test_socket_guard_blocks_deliberate_network_probe() -> None:
    with pytest.raises(RuntimeError, match="Unit tests must not open real network sockets"):
        socket.create_connection(("example.com", 80), timeout=0.01)
