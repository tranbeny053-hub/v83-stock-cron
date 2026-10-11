"""In-memory recent-run store."""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field

UNCLASSIFIED_RUN_ORIGIN = "UNCLASSIFIED"


@dataclass
class InMemoryRunStore:
    limit: int = 100
    runs: OrderedDict[str, dict] = field(default_factory=OrderedDict)
    _prediction_origins: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    # Each request runs on its own thread: one adds a run while another lists the store. put,
    # get and the copy a listing is made from each happen whole under this lock. Nothing waits,
    # reads a payload or calls out while it is held.
    _lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False, compare=False
    )

    def put(
        self,
        run_id: str,
        payload: dict,
        *,
        prediction_origin: str,
    ) -> None:
        with self._lock:
            self.runs[run_id] = payload
            self._prediction_origins[run_id] = prediction_origin
            self.runs.move_to_end(run_id)
            while len(self.runs) > self.limit:
                evicted_run_id = next(iter(self.runs))
                self.runs.popitem(last=False)
                self._prediction_origins.pop(evicted_run_id, None)

    def get(self, run_id: str) -> dict | None:
        with self._lock:
            return self.runs.get(run_id)

    def list_runs(self) -> list[dict]:
        # The rows are built after the lock is released, from what the store held under it.
        with self._lock:
            payloads = list(self.runs.values())
            origins = dict(self._prediction_origins)
        return [
            {
                "run_id": payload["run_id"],
                "symbol": payload["symbol"],
                "normalized_symbol": payload.get("normalized_symbol"),
                "analysis_mode": payload["analysis_mode"],
                "as_of_utc": payload["as_of_utc"],
                "analysis_hash": payload["analysis_hash"],
                "prediction_origin": origins.get(payload["run_id"], UNCLASSIFIED_RUN_ORIGIN),
                "primary_timeframe": payload.get("timeframes", {}).get("primary"),
                "data_source": payload.get("data_quality", {}).get("data_source"),
                "is_live_data": payload.get("data_quality", {}).get("is_live_data"),
            }
            for payload in reversed(payloads)
        ]
