"""HTTP glue for the governed automation route: POST /v1/automation/radar-evidence.

All policy lives in ``automation.service``. This module only reads the request (the credential
header, the cookie names and a byte-bounded body), runs the service off the event loop and writes
its answer as the RFC 8785 JCS bytes of the body, so a replay is byte-identical to the first
answer. The deadline budget starts here, before the body is read. The route shares no session,
run store, persistence repository or skill-evidence refresh with the human routes.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from crypto_probability_engine.automation.config import REQUEST_BODY_MAX_BYTES
from crypto_probability_engine.automation.contract import render
from crypto_probability_engine.automation.credentials import CREDENTIAL_HEADER
from crypto_probability_engine.automation.ledger import PostgresAutomationLedger
from crypto_probability_engine.automation.service import RadarEvidenceService
from crypto_probability_engine.config.settings import Settings

AUTOMATION_PATH = "/v1/automation/radar-evidence"


def register_automation_endpoint(app: FastAPI, *, settings: Settings) -> None:
    app.state.automation_service = RadarEvidenceService(
        settings=settings,
        ledger=PostgresAutomationLedger(settings.supabase_db_url),
    )

    @app.post(AUTOMATION_PATH, include_in_schema=False)
    async def radar_evidence(request: Request) -> Response:
        service = request.app.state.automation_service
        arrived = service.monotonic_now()  # the deadline budget starts before the body is read
        body = await _bounded_body(request)
        result = await run_in_threadpool(
            service.handle,
            credential=request.headers.get(CREDENTIAL_HEADER),
            cookies=dict(request.cookies),
            body=body,
            arrived_monotonic=arrived,
        )
        return Response(
            content=render(result.body),
            status_code=result.status,
            headers=result.headers,
            media_type="application/json",
        )


async def _bounded_body(request: Request) -> bytes:
    """Stop reading once the body exceeds the limit (after at most one transport chunk)."""

    received = bytearray()
    async for chunk in request.stream():
        received.extend(chunk)
        if len(received) > REQUEST_BODY_MAX_BYTES:
            break
    return bytes(received[: REQUEST_BODY_MAX_BYTES + 1])
