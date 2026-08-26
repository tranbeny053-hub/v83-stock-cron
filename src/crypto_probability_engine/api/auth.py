"""Server-side auth and signed session helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request, Response
from pydantic import BaseModel, Field, GetCoreSchemaHandler, ValidationError
from pydantic_core import core_schema

from crypto_probability_engine.api.errors import api_error
from crypto_probability_engine.api.schemas import ErrorCode
from crypto_probability_engine.config.defaults import DEFAULT_PHASE1A
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.persistence.prediction_origin import (
    DEFAULT_PREDICTION_ORIGIN,
    PredictionOrigin,
    validate_prediction_origin,
)

SESSION_COOKIE = "ucpe_session"
DEV_SESSION_COOKIE = "ucpe_dev_session"


MAX_ACCESS_CODE_LENGTH = 128


class LoginRequest(BaseModel):
    # 128 characters is generous for a human access code but too small to amplify PBKDF2.
    code: str = Field(max_length=MAX_ACCESS_CODE_LENGTH)

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        schema = handler(source_type)
        return core_schema.no_info_wrap_validator_function(
            cls._redact_validation_errors,
            schema,
        )

    @classmethod
    def _redact_validation_errors(
        cls,
        value: Any,
        handler: core_schema.ValidatorFunctionWrapHandler,
    ) -> Any:
        try:
            return handler(value)
        except ValidationError as exc:
            errors = exc.errors(include_url=False)
            for error in errors:
                if "input" in error:
                    error["input"] = "[REDACTED]"
            raise ValidationError.from_exception_data(cls.__name__, errors) from None

    def __init__(self, **data: object) -> None:
        try:
            super().__init__(**data)
        except ValidationError as exc:
            errors = exc.errors(include_url=False)
            for error in errors:
                if error["loc"] == ("code",) and "input" in error:
                    error["input"] = "[REDACTED]"
            raise ValidationError.from_exception_data(type(self).__name__, errors) from None


@dataclass
class AttemptLimiter:
    max_attempts: int = 5
    window_seconds: int = 60
    max_keys: int = 10_000
    attempts: dict[str, list[float]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _last_sweep: float = field(default=0.0, repr=False)

    def _prune_key(self, key: str, now: float) -> None:
        window_start = now - self.window_seconds
        recent = [item for item in self.attempts.get(key, []) if item >= window_start]
        if recent:
            self.attempts[key] = recent
        else:
            self.attempts.pop(key, None)

    def _sweep_if_due(self, now: float) -> None:
        if now - self._last_sweep < self.window_seconds:
            return
        window_start = now - self.window_seconds
        for key, items in list(self.attempts.items()):
            recent = [item for item in items if item >= window_start]
            if recent:
                self.attempts[key] = recent
            else:
                del self.attempts[key]
        self._last_sweep = now

    def _make_room_for(self, key: str, now: float) -> None:
        if key in self.attempts or len(self.attempts) < self.max_keys:
            return
        self._sweep_if_due(now)
        if len(self.attempts) < self.max_keys:
            return
        oldest_key = next(iter(self.attempts))
        del self.attempts[oldest_key]

    def check(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            self._prune_key(key, now)
            self._sweep_if_due(now)
            return len(self.attempts.get(key, [])) < self.max_attempts

    def check_and_record(self, key: str) -> float | None:
        """Atomically reserve one attempt, returning its timestamp if allowed."""

        now = time.time()
        with self._lock:
            self._prune_key(key, now)
            self._sweep_if_due(now)
            recent = self.attempts.get(key, [])
            if len(recent) >= self.max_attempts:
                return None
            self._make_room_for(key, now)
            self.attempts.setdefault(key, []).append(now)
            return now

    def record_failure(self, key: str) -> bool:
        return self.check_and_record(key) is not None

    def discard_reserved_attempt(self, key: str, reservation: float) -> None:
        with self._lock:
            recent = self.attempts.get(key)
            if not recent:
                return
            try:
                recent.remove(reservation)
            except ValueError:
                return
            if not recent:
                del self.attempts[key]

    def reset(self) -> None:
        with self._lock:
            self.attempts.clear()
            self._last_sweep = time.time()


session_limiter = AttemptLimiter()
dev_limiter = AttemptLimiter()


def hash_code(code: str) -> str:
    return pbkdf2_hash_code(
        code,
        salt=DEFAULT_PHASE1A.access_code_local_salt,
        iterations=DEFAULT_PHASE1A.access_code_pbkdf2_iterations,
    )


def pbkdf2_hash_code(code: str, *, salt: str, iterations: int) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        code.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )
    return digest.hex()


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _sign(payload: str, key: str) -> str:
    return hmac.new(key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def create_session_token(
    subject: str,
    settings: Settings,
    *,
    dev: bool = False,
    prediction_origin: str = DEFAULT_PREDICTION_ORIGIN,
) -> str:
    if not settings.session_signing_key:
        raise api_error(503, ErrorCode.UNAUTHORIZED, "Session signing key is not configured.")
    prediction_origin = validate_prediction_origin(prediction_origin)
    expires = datetime.now(UTC) + timedelta(seconds=settings.session_ttl_seconds)
    payload = {
        "sub": subject,
        "dev": dev,
        "exp": int(expires.timestamp()),
        "prediction_origin": prediction_origin,
    }
    body = _b64_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _sign(body, settings.session_signing_key)
    return f"{body}.{signature}"


def verify_session_token(
    token: str | None,
    settings: Settings,
    *,
    require_dev: bool = False,
) -> dict:
    if not token or not settings.session_signing_key:
        raise api_error(401, ErrorCode.UNAUTHORIZED, "Valid session is required.")
    try:
        body, signature = token.split(".", maxsplit=1)
        expected = _sign(body, settings.session_signing_key)
        if not hmac.compare_digest(signature, expected):
            raise ValueError("bad signature")
        payload = json.loads(_b64_decode(body))
    except Exception as exc:
        raise api_error(401, ErrorCode.UNAUTHORIZED, "Valid session is required.") from exc
    if int(payload.get("exp", 0)) < int(time.time()):
        raise api_error(401, ErrorCode.UNAUTHORIZED, "Session expired.")
    if require_dev and not payload.get("dev"):
        raise api_error(401, ErrorCode.UNAUTHORIZED, "Dev Mode re-auth is required.")
    session_prediction_origin(payload)
    return payload


def session_prediction_origin(payload: dict) -> str:
    """Return a verified session's origin, preserving the legacy-session default."""

    try:
        return validate_prediction_origin(
            payload.get("prediction_origin", DEFAULT_PREDICTION_ORIGIN)
        )
    except (TypeError, ValueError) as exc:
        raise api_error(401, ErrorCode.UNAUTHORIZED, "Valid session is required.") from exc


def _client_key(request: Request, purpose: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{purpose}:{host}"


def _hash_matches(candidate: str, expected_hash: str | None, settings: Settings) -> bool:
    if not expected_hash:
        return False
    candidate_hash = pbkdf2_hash_code(
        candidate,
        salt=settings.access_code_salt,
        iterations=settings.access_code_pbkdf2_iterations,
    )
    return hmac.compare_digest(candidate_hash, expected_hash)


def authenticate_login(request: Request, body: LoginRequest, settings: Settings) -> str:
    key = _client_key(request, "login")
    reservation = session_limiter.check_and_record(key)
    if reservation is None:
        raise api_error(429, ErrorCode.UNAUTHORIZED, "Too many attempts.", retry_after_seconds=60)
    if _hash_matches(body.code, settings.access_code_hash, settings):
        session_limiter.discard_reserved_attempt(key, reservation)
        return create_session_token("operator", settings)
    if _hash_matches(body.code, settings.controlled_smoke_code_hash, settings):
        session_limiter.discard_reserved_attempt(key, reservation)
        return create_session_token(
            "operator",
            settings,
            prediction_origin=PredictionOrigin.CONTROLLED_SMOKE,
        )
    raise api_error(401, ErrorCode.UNAUTHORIZED, "Invalid access code.")


def authenticate_dev(request: Request, body: LoginRequest, settings: Settings) -> str:
    if not settings.dev_mode_enabled:
        raise api_error(403, ErrorCode.UNAUTHORIZED, "Dev Mode is disabled.")
    key = _client_key(request, "dev")
    reservation = dev_limiter.check_and_record(key)
    if reservation is None:
        raise api_error(429, ErrorCode.UNAUTHORIZED, "Too many attempts.", retry_after_seconds=60)
    if not _hash_matches(body.code, settings.dev_mode_code_hash, settings):
        raise api_error(401, ErrorCode.UNAUTHORIZED, "Invalid Dev Mode code.")
    dev_limiter.discard_reserved_attempt(key, reservation)
    return create_session_token("operator", settings, dev=True)


def set_session_cookie(
    response: Response,
    token: str,
    settings: Settings,
    *,
    dev: bool = False,
) -> None:
    response.set_cookie(
        DEV_SESSION_COOKIE if dev else SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        max_age=3600,
    )
