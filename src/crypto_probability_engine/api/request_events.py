"""One structured `http_request` event per HTTP request (governing plan §10).

A pure ASGI middleware. It never reads a body, a header, a cookie, the query string or the client
address: it records the matched route's template (never the raw path), the status, the time to the
response's last byte (background tasks excluded) and a fresh request id, which this request's other
events share. The F1 automation route is passed through untouched (it keeps its own governed
ledger). A liveness probe that answers 200, and a static asset that answers below 400, are not
recorded. Recording never raises and never changes the response.

A POST to one of the two analysis routes also carries the observe-only analysis budget's counts
(owner ruling DP-C, 2026-10-05): this process's arrivals in the last minute and hour, and whether a
provisional threshold would have refused this one. Nothing is refused.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from crypto_probability_engine.api import analysis_budget
from crypto_probability_engine.api.analysis_budget import ANALYSIS_ROUTES, AnalysisBudgetObserver
from crypto_probability_engine.config.build_info import RELEASE_ID
from crypto_probability_engine.telemetry.events import CURRENT_REQUEST_ID, TelemetrySink

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

AUTOMATION_PREFIX = "/v1/automation/"
QUIET_ROUTES = frozenset({"/healthcheck"})
STATIC_ROUTE = "static"


class RequestEventMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        sink: TelemetrySink,
        budget: AnalysisBudgetObserver | None = None,
    ) -> None:
        self.app = app
        self.sink = sink
        self.budget = budget

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http" or str(scope.get("path", "")).startswith(AUTOMATION_PREFIX):
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        request_id = uuid.uuid4().hex[:16]
        budget = self._observe_budget(scope)
        statuses: list[int] = []
        finished: list[float] = []

        async def send_with_status(message: Message) -> None:
            if message.get("type") == "http.response.start":
                statuses.append(int(message.get("status", 0)))
            await send(message)
            # The response is complete at its last body chunk; background tasks run after it.
            if message.get("type") == "http.response.body" and not message.get("more_body"):
                finished.append(time.perf_counter())

        error_class: str | None = None
        token = CURRENT_REQUEST_ID.set(request_id)
        try:
            await self.app(scope, receive, send_with_status)
        except Exception as exc:
            error_class = type(exc).__name__
            raise
        finally:
            CURRENT_REQUEST_ID.reset(token)
            ended = finished[0] if finished else time.perf_counter()
            status = statuses[0] if statuses else 500
            self._record(scope, request_id, status, (ended - started) * 1000, error_class, budget)

    def _observe_budget(self, scope: Scope) -> dict[str, object]:
        """The observe-only budget's counts for an analysis request; empty for any other request.
        It reads only the method and the path, and never raises."""

        try:
            if scope.get("method") == "POST" and scope.get("path") in ANALYSIS_ROUTES:
                return (self.budget or analysis_budget.ANALYSIS_BUDGET).observe()
        except Exception:
            pass
        return {}

    def _record(
        self,
        scope: Scope,
        request_id: str,
        status: int,
        duration_ms: float,
        error_class: str | None,
        budget: dict[str, object] | None = None,
    ) -> None:
        try:
            route = _route_template(scope)
            quiet_probe = route in QUIET_ROUTES and status == 200
            if quiet_probe or (route == STATIC_ROUTE and status < 400):
                return
            self.sink.record(
                "http_request",
                {
                    "request_id": request_id,
                    "release_id": RELEASE_ID,
                    "method": scope.get("method"),
                    "route": route,
                    "status": status,
                    "duration_ms": duration_ms,
                    "error_class": error_class,
                    **(budget or {}),
                },
            )
        except Exception:
            return


def _route_template(scope: Scope) -> str:
    """The matched route's template; `static` for the frontend mount; `unmatched` otherwise."""

    path = getattr(scope.get("route"), "path", None)
    if isinstance(path, str) and path:
        return path
    if type(scope.get("endpoint")).__name__ == "StaticFiles":
        return STATIC_ROUTE
    return "unmatched"
