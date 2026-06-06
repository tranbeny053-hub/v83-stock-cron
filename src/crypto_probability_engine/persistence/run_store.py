"""In-memory recent-run store."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field


@dataclass
class InMemoryRunStore:
    limit: int = 100
    runs: OrderedDict[str, dict] = field(default_factory=OrderedDict)

    def put(self, run_id: str, payload: dict) -> None:
        self.runs[run_id] = payload
        self.runs.move_to_end(run_id)
        while len(self.runs) > self.limit:
            self.runs.popitem(last=False)

    def get(self, run_id: str) -> dict | None:
        return self.runs.get(run_id)

    def list_runs(self) -> list[dict]:
        return [
            {
                "run_id": payload["run_id"],
                "symbol": payload["symbol"],
                "analysis_mode": payload["analysis_mode"],
                "as_of_utc": payload["as_of_utc"],
                "analysis_hash": payload["analysis_hash"],
            }
            for payload in reversed(self.runs.values())
        ]

