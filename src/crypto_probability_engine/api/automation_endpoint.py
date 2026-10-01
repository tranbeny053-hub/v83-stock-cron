"""HTTP glue for the governed automation route: POST /v1/automation/radar-evidence.

All policy lives in ``automation.service``. This module stamps the request's arrival (the deadline
budget starts there), ADMITS it before reading a single body byte (kill switch, configuration,
human session refusal, machine credential), and only then reads the body: never more than
``REQUEST_BODY_MAX_BYTES`` (a larger declared Content-Length is refused unread, and no chunk is
copied past the limit) and never longer than ``BODY_READ_TIMEOUT_SECONDS``. It runs the service off
the event loop and writes its answer as the RFC 8785 JCS bytes of the body, so a replay is
byte-identical to the first answer. The route shares no session, run store, persistence repository
or skill-evidence refresh with the human routes. Nothing here connects to the database at startup:
the ledger and the credential registry connect per call, with bounded timeouts, and fail closed
(503) when the database is missing or unreachable.
"""

from __future__ import annotations

import asyncio

from fastapi import FastAPI, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from crypto_probability_engine.automation.config import (
    BODY_READ_TIMEOUT_SECONDS,
    REQUEST_BODY_MAX_BYTES,
)
from crypto_probability_engine.automation.contract import render
from crypto_probability_engine.automation.credentials import (
    CREDENTIAL_HEADER,
    PostgresCredentialRegistry,
)
from crypto_probability_engine.automation.ledger import PostgresAutomationLedger
from crypto_probability_engine.automation.service import AutomationResult, RadarEvidenceService
from crypto_probability_engine.config.settings import Settings

AUTOMATION_PATH = "/v1/automation/radar-evidence"


def register_automation_endpoint(app: FastAPI, *, settings: Settings) -> None:
    app.state.automation_service = RadarEvidenceService(
        settings=settings,
        ledger=PostgresAutomationLedger(settings.supabase_db_url),
        registry=PostgresCredentialRegistry(settings.supabase_db_url),
    )

    @app.post(AUTOMATION_PATH, include_in_schema=False)
    async def radar_evidence(request: Request) -> Response:
        service = request.app.state.automation_service
        arrived = service.monotonic_now()  # the deadline budget starts before anything is read
        admitted = await run_in_threadpool(
            service.admit,
            credential=request.headers.get(CREDENTIAL_HEADER),
            cookies=dict(request.cookies),
        )
        if isinstance(admitted, AutomationResult):
            return _respond(admitted)  # refused before a single body byte was read
        body = await read_bounded_body(request)
        result = await run_in_threadpool(
            service.handle_admitted, admitted, body=body, arrived_monotonic=arrived
        )
        return _respond(result)


def _respond(result: AutomationResult) -> Response:
    return Response(
        content=render(result.body),
        status_code=result.status,
        headers=result.headers,
        media_type="application/json",
    )


async def read_bounded_body(
    request: Request,
    *,
    limit: int = REQUEST_BODY_MAX_BYTES,
    timeout_seconds: float | None = None,
) -> bytes | None:
    """The body, or None when declared or found larger than ``limit``, or when too slow."""

    declared = request.headers.get("content-length")
    if declared is not None and (not declared.isdigit() or int(declared) > limit):
        return None
    timeout = BODY_READ_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
    try:
        return await asyncio.wait_for(_read_capped(request, limit), timeout)
    except TimeoutError:
        return None


async def _read_capped(request: Request, limit: int) -> bytes | None:
    received = bytearray()
    async for chunk in request.stream():
        received += chunk[: limit + 1 - len(received)]  # never copies past the limit
        if len(received) > limit:
            return None
    return bytes(received)
