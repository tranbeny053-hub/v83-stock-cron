"""Server-side auth and signed session helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from fastapi import Request, Response
from pydantic import BaseModel

from crypto_probability_engine.api.errors import api_error
from crypto_probability_engine.api.schemas import ErrorCode
from crypto_probability_engine.config.defaults import DEFAULT_PHASE1A
from crypto_probability_engine.config.settings import Settings

SESSION_COOKIE = "ucpe_session"
DEV_SESSION_COOKIE = "ucpe_dev_session"


class LoginRequest(BaseModel):
    code: str


@dataclass
class AttemptLimiter:
    max_attempts: int = 5
    window_seconds: int = 60
    attempts: dict[str, list[float]] = field(default_factory=dict)

    def check(self, key: str) -> bool:
        now = time.time()
        window_start = now - self.window_seconds
        recent = [item for item in self.attempts.get(key, []) if item >= window_start]
        self.attempts[key] = recent
        return len(recent) < self.max_attempts

    def record_failure(self, key: str) -> None:
        self.attempts.setdefault(key, []).append(time.time())

    def reset(self) -> None:
        self.attempts.clear()


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


def create_session_token(subject: str, settings: Settings, *, dev: bool = False) -> str:
    if not settings.session_signing_key:
        raise api_error(503, ErrorCode.UNAUTHORIZED, "Session signing key is not configured.")
    expires = datetime.now(UTC) + timedelta(seconds=settings.session_ttl_seconds)
    payload = {
        "sub": subject,
        "dev": dev,
        "exp": int(expires.timestamp()),
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
    return payload


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
    if not session_limiter.check(key):
        raise api_error(429, ErrorCode.UNAUTHORIZED, "Too many attempts.", retry_after_seconds=60)
    if not _hash_matches(body.code, settings.access_code_hash, settings):
        session_limiter.record_failure(key)
        raise api_error(401, ErrorCode.UNAUTHORIZED, "Invalid access code.")
    return create_session_token("operator", settings)


def authenticate_dev(request: Request, body: LoginRequest, settings: Settings) -> str:
    if not settings.dev_mode_enabled:
        raise api_error(403, ErrorCode.UNAUTHORIZED, "Dev Mode is disabled.")
    key = _client_key(request, "dev")
    if not dev_limiter.check(key):
        raise api_error(429, ErrorCode.UNAUTHORIZED, "Too many attempts.", retry_after_seconds=60)
    if not _hash_matches(body.code, settings.dev_mode_code_hash, settings):
        dev_limiter.record_failure(key)
        raise api_error(401, ErrorCode.UNAUTHORIZED, "Invalid Dev Mode code.")
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
