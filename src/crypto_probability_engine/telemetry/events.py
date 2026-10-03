"""Bounded, sanitized structured events (governing plan §10).

Each event is one JSON object on one line of the `ucpe.events` logger (stdout), and the newest are
kept in a bounded in-process buffer. Only allowlisted events and fields survive, every value is
flattened to a short scalar, and recording never raises: telemetry failure must never change a
response, a persistence result or a probability. No secret, header, cookie, query string, client
address, operator id or payload is an allowed field.
"""

from __future__ import annotations

import json
import logging
import math
import sys
from collections import deque
from collections.abc import Mapping
from contextvars import ContextVar

EVENT_LOGGER_NAME = "ucpe.events"
# The current HTTP request's id, set by the request middleware; worker threads inherit it.
CURRENT_REQUEST_ID: ContextVar[str | None] = ContextVar("ucpe_request_id", default=None)
# The current analysis's stage timings (plan §9.4), set by the analysis itself and read by its
# analysis_completed event. Reset at the start of every analysis, so none outlives a failure.
CURRENT_STAGE_MS: ContextVar[dict[str, float] | None] = ContextVar("ucpe_stage_ms", default=None)
STAGE_FIELDS = ("provider_ms", "quant_ms", "gate_ms", "news_ms", "present_ms", "total_ms")
BUFFER_SIZE = 256
MAX_TEXT = 160

EVENTS = frozenset(
    {
        "http_request",
        "analysis_completed",
        "persistence_receipt",
        # WB3's R-1a: an unknown commit decided by one strict read of the database
        "persistence_reconciled",
        "persistence_admission_refused",
        "persistence_submit_failed",
    }
)
FIELDS = frozenset(
    {
        # correlation and identity
        "request_id",
        "run_id",
        "release_id",
        # the request
        "method",
        "route",
        "status",
        "duration_ms",
        "error_class",
        # the analysis
        "symbol",
        "timeframe",
        "prediction_origin",
        "data_source",
        "is_live_data",
        "persistence_status",
        # the analysis stages (plan §9.4), in milliseconds
        *STAGE_FIELDS,
        # the persistence receipt
        "repository",
        "overall",
        "background_status",
        "prediction",
        "feature_snapshot",
        "derivatives_snapshot",
        "prediction_rows",
        # plan §8.1's receipt for the forecast bundles (SAVED, NOT_SAVED, COMMIT_UNKNOWN) and why
        "receipt",
        "receipt_reason",
        # how many strict reads an unknown commit took to decide (R-1a)
        "attempts",
    }
)
_CONTAINERS = (Mapping, list, tuple, set, frozenset, bytes, bytearray)


def _scalar(value: object) -> object:
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        return round(value, 3) if math.isfinite(value) else None
    text = str(value)
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "..."


def sanitize(event: str, fields: Mapping[str, object]) -> dict[str, object] | None:
    """The allowlisted, flattened form of one event, or None when the event is not allowlisted."""

    if event not in EVENTS:
        return None
    clean: dict[str, object] = {"event": event}
    for key in sorted(fields):
        value = fields[key]
        if key in FIELDS and not isinstance(value, _CONTAINERS):
            clean[key] = _scalar(value)
    return clean


class _StdoutHandler(logging.Handler):
    """Writes to the current sys.stdout at emit time (a replaced or captured stream stays right)."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            sys.stdout.write(self.format(record) + "\n")
        except Exception:
            return


_LOGGER = logging.getLogger(EVENT_LOGGER_NAME)
if not _LOGGER.handlers:
    _HANDLER = _StdoutHandler()
    _HANDLER.setFormatter(logging.Formatter("%(message)s"))
    _LOGGER.addHandler(_HANDLER)
    _LOGGER.setLevel(logging.INFO)
    _LOGGER.propagate = False


class TelemetrySink:
    """The newest events, bounded; each one is also written as a JSON line."""

    def __init__(self, capacity: int = BUFFER_SIZE) -> None:
        self.events: deque[dict[str, object]] = deque(maxlen=capacity)

    def record(self, event: str, payload: Mapping[str, object]) -> None:
        try:
            clean = sanitize(event, payload)
            if clean is None:
                return
            self.events.append(clean)
            _LOGGER.info(json.dumps(clean, sort_keys=True, separators=(",", ":"), allow_nan=False))
        except Exception:
            return


EVENTS_SINK = TelemetrySink()


def emit(event: str, **fields: object) -> None:
    """Record one event on the process-wide sink. Never raises."""

    EVENTS_SINK.record(event, fields)
