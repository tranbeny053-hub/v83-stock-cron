"""HTTP glue for the governed automation route: POST /v1/automation/radar-evidence.

All policy lives in ``automation.service``. This module only reads the request (the credential
header, the cookie names and a byte-bounded body), runs the service off the event loop and
writes its answer. It is registered on the same app as the human routes but shares nothing with
them: no session dependency, no run store, no persistence repository, no skill-evidence refresh.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from crypto_probability_engine.automation.config import REQUEST_BODY_MAX_BYTES
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
    async def radar_evidence(request: Request) -> JSONResponse:
        body = await _bounded_body(request)
        service = request.app.state.automation_service
        result = await run_in_threadpool(
            service.handle,
            credential=request.headers.get(CREDENTIAL_HEADER),
            cookies=dict(request.cookies),
            body=body,
        )
        return JSONResponse(status_code=result.status, content=result.body, headers=result.headers)


async def _bounded_body(request: Request) -> bytes:
    """Read at most one byte past the limit, so an oversized body is refused, never buffered."""

    received = bytearray()
    async for chunk in request.stream():
        received.extend(chunk)
        if len(received) > REQUEST_BODY_MAX_BYTES:
            break
    return bytes(received[: REQUEST_BODY_MAX_BYTES + 1])
