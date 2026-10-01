"""The route admits a request before reading its body, and reads the body only within bounds.

Driven at the ASGI level, below the test client, so that a body the route never asks for is
provably never read: ``receive`` records every call and stalls once its events run out.
"""

import asyncio
from datetime import timedelta

import pytest

from crypto_probability_engine.api import automation_endpoint
from crypto_probability_engine.api.automation_endpoint import read_bounded_body
from crypto_probability_engine.automation.config import REQUEST_BODY_MAX_BYTES
from crypto_probability_engine.automation.credentials import CREDENTIAL_HEADER
from crypto_probability_engine.automation.ledger import InMemoryAutomationLedger
from crypto_probability_engine.automation.service import COMMIT_RESERVE_SECONDS
from tests.automation.conftest import AUTOMATION_PATH, credential_env, token, utc

NOW = utc(2026, 9, 30)
BODY = (
    b'{"symbol": "BTC", "primary_timeframe": "4H",'
    b' "client_request_id": "3f9d2c1e-8a4b-4c2d-9e6f-1a2b3c4d5e6f", "deadline_ms": 30000}'
)


def call_asgi(app, headers: list[tuple[str, str]], events: list[dict]) -> tuple[int, list]:
    receive_calls: list[int] = []
    sent: list[dict] = []

    async def receive():
        receive_calls.append(1)
        if events:
            return events.pop(0)
        await asyncio.sleep(3600)  # a body that never arrives

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": AUTOMATION_PATH,
        "raw_path": AUTOMATION_PATH.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(name.lower().encode(), value.encode()) for name, value in headers],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    asyncio.run(asyncio.wait_for(app(scope, receive, send), timeout=10))
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, [receive_calls, body]


@pytest.mark.parametrize(
    ("env", "headers", "status"),
    [
        (credential_env(enabled="0"), [(CREDENTIAL_HEADER, token())], 503),
        (credential_env(), [], 401),
        (credential_env(), [(CREDENTIAL_HEADER, "synthetic-malformed")], 401),
        (credential_env(), [(CREDENTIAL_HEADER, token("unknown-radar"))], 401),
        (
            credential_env(),
            [(CREDENTIAL_HEADER, token()), ("cookie", "ucpe_session=synthetic")],
            403,
        ),
    ],
)
def test_a_refused_request_is_answered_without_reading_its_body(
    harness_factory, env, headers, status
):
    harness = harness_factory(env=env)
    answer, (receive_calls, _body) = call_asgi(
        harness.app, [*headers, ("content-length", str(len(BODY)))], events=[]
    )
    assert answer == status
    assert receive_calls == [], "no body byte was asked for"
    assert harness.ledger.entries() == []


def test_an_admitted_request_reads_its_body_and_is_answered(harness_factory):
    harness = harness_factory()
    events = [{"type": "http.request", "body": BODY, "more_body": False}]
    answer, (receive_calls, _body) = call_asgi(
        harness.app,
        [(CREDENTIAL_HEADER, token()), ("content-length", str(len(BODY)))],
        events=events,
    )
    assert answer == 200 and len(receive_calls) >= 1


def test_a_declared_oversize_body_is_refused_unread(harness_factory):
    harness = harness_factory()
    answer, (receive_calls, body) = call_asgi(
        harness.app,
        [(CREDENTIAL_HEADER, token()), ("content-length", str(REQUEST_BODY_MAX_BYTES + 1))],
        events=[],
    )
    assert answer == 400 and b"MALFORMED_REQUEST" in body
    assert receive_calls == []
    assert harness.ledger.entries() == []


def test_a_stalled_body_times_out_as_malformed(harness_factory, monkeypatch):
    monkeypatch.setattr(automation_endpoint, "BODY_READ_TIMEOUT_SECONDS", 0.05)
    harness = harness_factory()
    answer, (_calls, body) = call_asgi(
        harness.app,
        [(CREDENTIAL_HEADER, token()), ("content-length", str(len(BODY)))],
        events=[{"type": "http.request", "body": BODY[:10], "more_body": True}],
    )
    assert answer == 400 and b"MALFORMED_REQUEST" in body
    assert harness.ledger.entries() == []


class FakeRequest:
    def __init__(self, chunks: list[bytes], headers: dict | None = None, stall: bool = False):
        self.headers = headers or {}
        self._chunks = chunks
        self._stall = stall

    async def stream(self):
        for chunk in self._chunks:
            yield chunk
        if self._stall:
            await asyncio.sleep(3600)


def test_no_chunk_is_copied_past_the_limit():
    huge = b"x" * (2 * 1024 * 1024)
    assert asyncio.run(read_bounded_body(FakeRequest([huge]))) is None
    exact = asyncio.run(read_bounded_body(FakeRequest([b"a" * 1000, b"b" * 24])))
    assert exact == b"a" * 1000 + b"b" * 24
    assert asyncio.run(read_bounded_body(FakeRequest([b"a" * 1000, b"b" * 25]))) is None


@pytest.mark.parametrize("declared", ["1025", "-1", "abc", "99999999999"])
def test_a_bad_or_large_content_length_is_refused(declared):
    request = FakeRequest([b"{}"], headers={"content-length": declared})
    assert asyncio.run(read_bounded_body(request)) is None


def test_a_slow_body_returns_none_within_its_timeout():
    request = FakeRequest([b"{"], stall=True)
    assert asyncio.run(read_bounded_body(request, timeout_seconds=0.05)) is None


def test_a_success_is_recorded_only_with_the_commit_reserve_inside_the_deadline(harness_factory):
    seen = {}

    class SpyLedger(InMemoryAutomationLedger):
        def complete_success(self, **kwargs):
            seen.update(kwargs)
            return super().complete_success(**kwargs)

    harness = harness_factory(ledger=SpyLedger(), clock=lambda: NOW, monotonic=lambda: 100.0)
    assert harness.post().status_code == 200
    assert seen["deadline_at_utc"] == NOW + timedelta(seconds=30 - COMMIT_RESERVE_SECONDS)


def test_a_success_inside_the_commit_reserve_is_recorded_late(harness_factory):
    times = iter([NOW, NOW, NOW + timedelta(seconds=29.9), NOW + timedelta(seconds=29.9)])
    harness = harness_factory(
        clock=lambda: next(times, NOW + timedelta(seconds=29.9)), monotonic=lambda: 100.0
    )
    response = harness.post()
    assert response.status_code == 503 and response.json()["error"]["code"] == "DEADLINE_EXCEEDED"
    [entry] = harness.ledger.entries()
    assert entry.outcome_code == "DEADLINE_EXCEEDED" and entry.run_id is None


class TrackingBytearray(bytearray):
    largest = 0

    def __iadd__(self, other):
        result = super().__iadd__(other)
        TrackingBytearray.largest = max(TrackingBytearray.largest, len(self))
        return result


def test_the_copy_never_grows_past_the_limit_whatever_the_chunk(monkeypatch):
    monkeypatch.setattr(automation_endpoint, "bytearray", TrackingBytearray, raising=False)
    TrackingBytearray.largest = 0
    huge = b"x" * (2 * 1024 * 1024)
    assert asyncio.run(read_bounded_body(FakeRequest([b"{", huge, huge]))) is None
    assert 0 < TrackingBytearray.largest <= REQUEST_BODY_MAX_BYTES + 1


@pytest.mark.parametrize("declared", ["\u00b2", "\u0661\u0662", "1" * 11, "1" * 5000, " 12", "+12"])
def test_a_non_ascii_or_overlong_content_length_is_refused_without_error(declared):
    request = FakeRequest([b"{}"], headers={"content-length": declared})
    assert asyncio.run(read_bounded_body(request)) is None


def test_the_deadline_instant_counts_from_arrival_not_from_admission(harness_factory):
    seen = {}

    class SpyLedger(InMemoryAutomationLedger):
        def complete_success(self, **kwargs):
            seen.update(kwargs)
            return super().complete_success(**kwargs)

    instants = iter([NOW, NOW + timedelta(seconds=1)])
    ticks = iter([100.0, 101.0])
    harness = harness_factory(
        ledger=SpyLedger(),
        clock=lambda: next(instants, NOW + timedelta(seconds=1)),
        monotonic=lambda: next(ticks, 101.0),
    )
    assert harness.post().status_code == 200
    # Arrival at NOW (monotonic 100), a 30 s budget: the deadline is NOW + 30 s, whatever the body
    # read cost; the success must be recorded the commit reserve before it.
    assert seen["deadline_at_utc"] == NOW + timedelta(seconds=30 - COMMIT_RESERVE_SECONDS)
