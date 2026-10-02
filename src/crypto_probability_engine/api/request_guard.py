"""Cheap early refusals for the human routes, and browser security headers (governing plan §13).

A pure ASGI middleware. It sits inside the request-event middleware, so every refusal is still
recorded, and outside every route. The F1 automation route passes through untouched: it keeps its
own governed contract, body bound and headers.

For every other HTTP request it:
- refuses an unsafe-method request (POST, PUT, PATCH, DELETE) that a browser marks as sent from
  another site. That means `Sec-Fetch-Site` other than `same-origin` or `none`, unless its `Origin`
  is one the operator allowed for CORS. Response: 403 CROSS_SITE_REFUSED. A request without the
  header (no browser, or an old one) is left to the SameSite session cookie;
- refuses an unsafe-method request whose body is declared or found larger than
  HUMAN_BODY_MAX_BYTES. Response: 413 REQUEST_TOO_LARGE. The body is read here, never more than one
  byte past the bound, and replayed to the app;
- adds nosniff, no-referrer and a self-only content security policy to every response. Framing is
  allowed only to the app itself and to the Hugging Face page that embeds the Space;
- adds `Cache-Control: no-store` to every /v1/ response that sets none of its own. The static
  frontend keeps its caching.

Both refusals happen before any route runs, so a refused request makes no provider or database call.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from fastapi.responses import JSONResponse

from crypto_probability_engine.api.errors import error_payload
from crypto_probability_engine.api.request_events import (
    AUTOMATION_PREFIX,
    ASGIApp,
    Message,
    Receive,
    Scope,
    Send,
)
from crypto_probability_engine.api.schemas import ErrorCode

# The largest legitimate human request is a five-item batch, well under 1 KiB.
HUMAN_BODY_MAX_BYTES = 16_384
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
SAME_SITE_FETCHES = frozenset({b"same-origin", b"none"})
API_PREFIX = "/v1/"
# The frontend loads one same-origin stylesheet and one same-origin module script, fetches only its
# own origin, and has no inline script, inline style attribute or external resource. So self-only
# holds with no exceptions.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; "
    "font-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; "
    "frame-ancestors 'self' https://huggingface.co"
)
SECURITY_HEADERS = (
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"content-security-policy", CONTENT_SECURITY_POLICY.encode("ascii")),
)


class RequestGuardMiddleware:
    def __init__(self, app: ASGIApp, allowed_origins: Iterable[str] = ()) -> None:
        self.app = app
        self.allowed_origins = frozenset(origin.encode("latin-1") for origin in allowed_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = str(scope.get("path", ""))
        if scope.get("type") != "http" or path.startswith(AUTOMATION_PREFIX):
            await self.app(scope, receive, send)
            return
        no_store = path.startswith(API_PREFIX)

        async def send_with_headers(message: Message) -> None:
            if message.get("type") == "http.response.start":
                headers = list(message.get("headers", []))
                present = {bytes(name).lower() for name, _ in headers}
                headers.extend(header for header in SECURITY_HEADERS if header[0] not in present)
                if no_store and b"cache-control" not in present:
                    headers.append((b"cache-control", b"no-store"))
                message["headers"] = headers
            await send(message)

        if str(scope.get("method", "")).upper() in UNSAFE_METHODS:
            raw = scope.get("headers", [])
            headers = {bytes(name).lower(): bytes(value) for name, value in raw}
            if not self._same_site(headers):
                await _refuse(scope, receive, send_with_headers, 403,
                              ErrorCode.CROSS_SITE_REFUSED, "Cross-site request refused.")
                return
            outcome = await _read_bounded(headers, receive)
            if outcome is _CLIENT_GONE:
                return
            if outcome is None:
                await _refuse(scope, receive, send_with_headers, 413,
                              ErrorCode.REQUEST_TOO_LARGE, "Request body is too large.")
                return
            receive = _replay(outcome, receive)
        await self.app(scope, receive, send_with_headers)

    def _same_site(self, headers: Mapping[bytes, bytes]) -> bool:
        site = headers.get(b"sec-fetch-site")
        if site is None or site.lower() in SAME_SITE_FETCHES:
            return True
        return headers.get(b"origin") in self.allowed_origins


_CLIENT_GONE = object()


async def _read_bounded(headers: Mapping[bytes, bytes], receive: Receive) -> bytes | object | None:
    """The whole body; None when declared or found too large; _CLIENT_GONE if the client left."""

    declared = headers.get(b"content-length")
    if declared is not None and not (
        declared.isdigit() and len(declared) <= 10 and int(declared) <= HUMAN_BODY_MAX_BYTES
    ):
        return None
    received = bytearray()
    while True:
        message = await receive()
        if message.get("type") != "http.request":
            return _CLIENT_GONE
        received += message.get("body", b"")[: HUMAN_BODY_MAX_BYTES + 1 - len(received)]
        if len(received) > HUMAN_BODY_MAX_BYTES:
            return None
        if not message.get("more_body", False):
            return bytes(received)


def _replay(body: bytes, receive: Receive) -> Receive:
    delivered = False

    async def replay() -> Message:
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await receive()

    return replay


async def _refuse(
    scope: Scope, receive: Receive, send: Send, status: int, code: ErrorCode, message: str
) -> None:
    # The same envelope an HTTPException raised by a route carries.
    response = JSONResponse({"detail": error_payload(code, message)}, status_code=status)
    await response(scope, receive, send)
