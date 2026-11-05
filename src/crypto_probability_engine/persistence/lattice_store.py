"""Isolated parameterized writer for the dormant lattice schema."""

from __future__ import annotations

import json
from typing import Any


class LatticeStore:
    def __init__(self, connect: Any) -> None:
        self._connect = connect

    def _call(self, function: str, value: Any, accepted: set[str]) -> Any:
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"SELECT ucpe_lattice.{function}(%s::jsonb)", (json.dumps(value),)
                    )
                    result = cursor.fetchone()[0]
            if result not in accepted:
                raise RuntimeError("Lattice function returned an unknown status")
            return result
        except RuntimeError:
            raise
        except Exception:
            raise RuntimeError("Lattice store operation failed") from None

    def record_row(self, row: dict[str, Any]) -> str:
        return self._call(
            "record_lattice_row",
            row,
            {"INSERTED", "INSERTED_WARN", "DUPLICATE", "CAPACITY_UNSET", "CAPACITY_STOP"},
        )

    def record_missed(self, entry: dict[str, Any]) -> str:
        return self._call(
            "record_missed_instant",
            entry,
            {"LOGGED", "DUPLICATE", "CAPACITY_UNSET", "CAPACITY_STOP"},
        )

    def capture_commit_receipts(self, limit: int) -> int:
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT ucpe_lattice.capture_commit_receipts(%s)", (limit,))
                    result = cursor.fetchone()[0]
            return result
        except Exception:
            raise RuntimeError("Lattice receipt capture failed") from None
