"""The observe-only analysis budget (plan §13; owner ruling DP-C, 2026-10-05).

It counts a process's requests to the two analysis routes over the last minute and hour, and says
whether a provisional threshold would have refused one. These tests prove that it refuses nobody and
changes no response, that only two counts and a yes/no travel (no user, session, operator, client or
request identity), that only POSTs to the two analysis routes are counted (never the F1 automation
route), that its windows and thresholds are what they say, and that its memory stays bounded.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from crypto_probability_engine.api import analysis_budget
from crypto_probability_engine.api.analysis_budget import (
    PROVISIONAL_PER_HOUR,
    PROVISIONAL_PER_MINUTE,
    AnalysisBudgetObserver,
)
from crypto_probability_engine.api.app import create_app
from crypto_probability_engine.api.auth import dev_limiter, hash_code, session_limiter
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.telemetry.events import BUDGET_FIELDS, EVENTS_SINK, FIELDS, sanitize


class Clock:
    def __init__(self, now: float = 1_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def test_it_counts_the_last_minute_and_the_last_hour() -> None:
    clock = Clock()
    observer = AnalysisBudgetObserver(clock)
    first = observer.observe()
    assert first == {"budget_count_60s": 1, "budget_count_3600s": 1, "budget_would_refuse": False}
    clock.now += 30
    assert observer.observe()["budget_count_60s"] == 2
    clock.now += 31  # the first arrival left the one-minute window, not the hour
    counts = observer.observe()
    assert counts["budget_count_60s"] == 2 and counts["budget_count_3600s"] == 3
    clock.now += 3600  # everything left both windows
    assert observer.observe() == first


def test_each_window_ends_exactly_at_its_edge() -> None:
    clock = Clock(now=60.0 * 20_000)  # on a minute boundary
    observer = AnalysisBudgetObserver(clock)
    observer.observe()
    clock.now += 59
    assert observer.observe()["budget_count_60s"] == 2, "59 seconds on: still inside the minute"
    clock.now += 1
    assert observer.observe()["budget_count_60s"] == 2, "60 seconds on: the first one left"
    hourly = AnalysisBudgetObserver(clock)
    start = clock.now
    hourly.observe()
    clock.now = start + 59 * 60
    assert hourly.observe()["budget_count_3600s"] == 2, "59 minutes on: still inside the hour"
    clock.now = start + 60 * 60
    assert hourly.observe()["budget_count_3600s"] == 2, "60 minutes on: the first one left"


def test_the_provisional_thresholds_only_flag() -> None:
    clock = Clock()
    observer = AnalysisBudgetObserver(clock)
    flags = [observer.observe()["budget_would_refuse"] for _ in range(PROVISIONAL_PER_MINUTE + 1)]
    assert flags == [False] * PROVISIONAL_PER_MINUTE + [True]
    hourly = AnalysisBudgetObserver(clock)
    flags = []
    for _ in range(PROVISIONAL_PER_HOUR + 1):
        clock.now += 5  # 12 a minute: never over the minute threshold
        flags.append(hourly.observe()["budget_would_refuse"])
    assert flags == [False] * PROVISIONAL_PER_HOUR + [True]


def test_its_memory_stays_bounded() -> None:
    clock = Clock()
    observer = AnalysisBudgetObserver(clock)
    for _ in range(20_000):
        clock.now += 0.37
        observer.observe()
    assert len(observer._seconds) <= 60 and len(observer._minutes) <= 60


def test_only_counts_and_a_yes_or_no_are_allowlisted() -> None:
    assert set(BUDGET_FIELDS) <= FIELDS
    event = sanitize(
        "http_request",
        {
            "budget_count_60s": 3,
            "budget_count_3600s": 9,
            "budget_would_refuse": False,
            "session_id": "s",
            "user": "u",
            "client": "c",
        },
    )
    assert event == {
        "event": "http_request",
        "budget_count_60s": 3,
        "budget_count_3600s": 9,
        "budget_would_refuse": False,
    }


def _client() -> TestClient:
    session_limiter.reset()
    dev_limiter.reset()
    settings = Settings(
        access_code_hash=hash_code("operator-test-code"),
        session_signing_key="test-signing-key",
        session_cookie_secure=False,
        data_mode="fixture",
    )
    client = TestClient(create_app(settings))
    assert client.post("/v1/auth/login", json={"code": "operator-test-code"}).status_code == 200
    return client


def _requests() -> list[dict]:
    return [event for event in EVENTS_SINK.events if event["event"] == "http_request"]


@pytest.fixture()
def observer(monkeypatch: pytest.MonkeyPatch) -> AnalysisBudgetObserver:
    """A fresh process observer, at a threshold the test can cross."""

    fresh = AnalysisBudgetObserver(Clock())
    monkeypatch.setattr(analysis_budget, "ANALYSIS_BUDGET", fresh)
    monkeypatch.setattr(analysis_budget, "PROVISIONAL_PER_MINUTE", 1)
    return fresh


def test_an_analysis_request_carries_the_counts_and_nothing_is_refused(
    observer: AnalysisBudgetObserver,
) -> None:
    client = _client()
    EVENTS_SINK.events.clear()
    body = {"symbol": "BTC/USDT", "timeframe": "4H"}
    first = client.post("/v1/analyze", json=body)
    second = client.post("/v1/analyze", json=body)  # over the threshold of 1: flagged, served
    assert first.status_code == second.status_code == 200, second.text
    analyses = [event for event in _requests() if event.get("route") == "/v1/analyze"]
    assert [event["budget_count_60s"] for event in analyses] == [1, 2]
    assert [event["budget_would_refuse"] for event in analyses] == [False, True]
    allowed = {
        "event",
        "request_id",
        "release_id",
        "method",
        "route",
        "status",
        "duration_ms",
        "error_class",
        *BUDGET_FIELDS,
    }
    for event in analyses:
        assert set(event) <= allowed, set(event) - allowed
    # The served analysis is the same analysis: the flag changed nothing in the payload.
    first_payload, second_payload = first.json(), second.json()
    for payload in (first_payload, second_payload):
        assert not any(field in json.dumps(payload) for field in BUDGET_FIELDS)


def test_other_routes_and_methods_are_not_counted(observer: AnalysisBudgetObserver) -> None:
    client = _client()
    EVENTS_SINK.events.clear()
    client.get("/v1/build-info")
    client.get("/v1/analyze")  # not a POST
    assert observer.observe()["budget_count_60s"] == 1, "nothing but this call was counted"
    for event in _requests():
        assert not set(BUDGET_FIELDS) & set(event)


def test_the_automation_route_is_never_counted(observer: AnalysisBudgetObserver) -> None:
    client = _client()
    client.post("/v1/automation/radar-evidence", json={})
    assert observer.observe()["budget_count_60s"] == 1


def test_an_observer_failure_changes_nothing(
    observer: AnalysisBudgetObserver, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken() -> dict[str, object]:
        raise RuntimeError("observer failed")

    monkeypatch.setattr(observer, "observe", broken)
    client = _client()
    EVENTS_SINK.events.clear()
    response = client.post("/v1/analyze", json={"symbol": "BTC/USDT", "timeframe": "4H"})
    assert response.status_code == 200, response.text
    (event,) = [event for event in _requests() if event.get("route") == "/v1/analyze"]
    assert not set(BUDGET_FIELDS) & set(event)
