"""Error helpers for API responses."""

from __future__ import annotations

from fastapi import HTTPException

from crypto_probability_engine.api.schemas import ErrorCode, ErrorResponse


def error_payload(
    code: ErrorCode,
    message: str,
    *,
    retry_after_seconds: int | None = None,
    run_id: str | None = None,
    provider_state_snapshot: dict | None = None,
    system_status_snapshot: dict | None = None,
) -> dict:
    return ErrorResponse(
        error={
            "code": code,
            "message": message,
            "retry_after_seconds": retry_after_seconds,
            "run_id": run_id,
            "provider_state_snapshot": provider_state_snapshot or {},
            "system_status_snapshot": system_status_snapshot or {},
        }
    ).model_dump(mode="json")


def api_error(
    status_code: int,
    code: ErrorCode,
    message: str,
    *,
    retry_after_seconds: int | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=error_payload(code, message, retry_after_seconds=retry_after_seconds),
    )

