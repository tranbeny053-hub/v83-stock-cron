"""Best-effort telemetry recording."""

from __future__ import annotations


class TelemetrySink:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def record(self, event: str, payload: dict) -> None:
        try:
            self.events.append({"event": event, "payload": dict(payload)})
        except Exception:
            return

