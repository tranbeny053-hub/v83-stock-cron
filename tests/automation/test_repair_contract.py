"""Regression tests for the F1 review repair: deadline, replay bytes, projection, validation.

Each test names the review finding it closes. Synthetic data only; clocks are injected.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from crypto_probability_engine.api import analysis_service
from crypto_probability_engine.automation import contract, service
from crypto_probability_engine.automation.contract import render
from crypto_probability_engine.automation.ledger import (
    InMemoryAutomationLedger,
    LedgerEntry,
    LedgerUnavailable,
    Outcome,
    PostgresAutomationLedger,
)
from tests.automation.conftest import request_body, utc

NOW = utc(2026, 9, 30, 12)


def _reversed(value):
    if isinstance(value, dict):
        return {key: _reversed(value[key]) for key in reversed(list(value))}
    if isinstance(value, list):
        return [_reversed(item) for item in value]
    return value


def test_every_response_is_sent_as_its_jcs_bytes(harness_factory):  # F3
    harness = harness_factory()
    success = harness.post()
    refusal = harness.post(request_body(primary_timeframe="1W"))
    for response in (success, refusal):
        assert response.headers["content-type"].startswith("application/json")
        assert response.content == render(response.json())


def test_a_replay_is_byte_identical_even_when_storage_reorders_keys(harness_factory):  # F3
    harness = harness_factory()
    first = harness.post()
    assert first.status_code == 200
    [entry] = harness.ledger.entries()
    key = (entry.credential_id, entry.client_request_id)
    harness.ledger._entries[key] = LedgerEntry(  # noqa: SLF001 - simulate JSONB key order
        **{**entry.__dict__, "response_body": _reversed(entry.response_body)}
    )
    assert list(harness.ledger.entries()[0].response_body) != list(first.json())
    replay = harness.post()
    assert replay.headers["idempotent-replay"] == "true"
    assert replay.content == first.content


def test_a_success_recorded_late_is_answered_and_recorded_as_deadline_exceeded(
    harness_factory,
):  # F1
    wall = iter([NOW, NOW])  # received, issued; every later read is past the deadline

    def clock():
        return next(wall, NOW + timedelta(seconds=40))

    harness = harness_factory(clock=clock, monotonic=lambda: 0.0)
    response = harness.post()
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DEADLINE_EXCEEDED"
    [entry] = harness.ledger.entries()
    assert entry.outcome_code == "DEADLINE_EXCEEDED" and entry.run_id is None
    assert "evidence_hash" not in response.text


def test_too_little_budget_after_building_never_attempts_the_success_record(
    harness_factory, monkeypatch
):  # F1
    ticks = iter([0.0, 0.0, 0.0])  # arrival, deadline stamp, analysis wait

    def monotonic():
        return next(ticks, 29.95)

    harness = harness_factory(monotonic=monotonic)

    def forbidden(**_kwargs):
        pytest.fail("a success must not be recorded without budget")

    monkeypatch.setattr(harness.ledger, "complete_success", forbidden)
    response = harness.post()
    assert response.json()["error"]["code"] == "DEADLINE_EXCEEDED"
    assert harness.ledger.entries()[0].outcome_code == "DEADLINE_EXCEEDED"


def test_an_analysis_without_live_data_yields_no_evidence(harness_factory):  # F10
    harness = harness_factory()
    automation = harness.app.state.automation_service
    real = automation._analyzer  # noqa: SLF001 - the real isolated analysis, fixture data

    def not_live(request):
        analysis = real(request)
        analysis["data_quality"]["is_live_data"] = False
        return analysis

    automation._analyzer = not_live  # noqa: SLF001
    response = harness.post()
    assert response.json()["error"]["code"] == "UPSTREAM_UNAVAILABLE"
    assert harness.ledger.entries()[0].outcome_code == "UPSTREAM_UNAVAILABLE"


def test_a_horizon_that_is_not_ok_carries_no_numbers(fixture_market):  # F5
    del fixture_market
    from crypto_probability_engine.api.schemas import AnalysisRequest
    from crypto_probability_engine.config.build_info import build_info_payload
    from crypto_probability_engine.config.settings import Settings

    analysis = analysis_service.analyze_request_isolated(
        AnalysisRequest(symbol="BTC", timeframe="4H"), settings=Settings(data_mode="fixture")
    )
    analysis["probability_state"]["horizons"]["H_extended"]["status"] = "NULL"
    body = contract.build_radar_evidence(
        analysis,
        request=contract.parse_request(json.dumps(request_body()).encode()),
        build_info=build_info_payload(),
        issued_at_utc="2026-09-30T12:00:01Z",
    )
    extended = body["probability_state"]["horizons"]["H_extended"]
    assert extended["status"] == "NULL"
    for field in ("p_up_frac", "p_down_frac", "p_timeout_frac", "confidence_frac"):
        assert extended[field] is None
    assert body["probability_state"]["horizons"]["H_primary"]["p_up_frac"] is not None
    assert contract.radar_evidence_valid(body)
    # And the schema itself refuses numbers on a non-OK horizon, or nulls on an OK one.
    tampered = json.loads(json.dumps(body))
    tampered["probability_state"]["horizons"]["H_extended"]["p_up_frac"] = 0.5
    assert not contract.radar_evidence_valid(tampered)
    tampered = json.loads(json.dumps(body))
    tampered["probability_state"]["horizons"]["H_primary"]["p_up_frac"] = None
    assert not contract.radar_evidence_valid(tampered)


def test_free_prose_cannot_ride_in_a_code_field(fixture_market):  # F5
    del fixture_market
    body = json.loads(
        (contract.SCHEMA_DIR.parent / "docs/automation/examples")
        .joinpath("radar_evidence.v1.synthetic-btc-4h-gate-blocked.json")
        .read_text()
    )
    body["calibration_state"]["reliability_status"] = "observed_directional_rate=0.58"
    body["evidence_hash"] = contract.evidence_hash(body)
    assert not contract.radar_evidence_valid(body)
    body = json.loads(json.dumps(body))
    body["calibration_state"]["reason"] = "anything"
    assert not contract.radar_evidence_valid(body)


def test_an_invalid_error_body_is_never_sent(monkeypatch):  # F5 / (7)
    real = contract.error_body

    def corrupt(code, retry_after_seconds=None):
        body = real(code, retry_after_seconds)
        if code is contract.ErrorCode.QUOTA_EXCEEDED:
            body["error"]["message"] = "leak: user data"
        return body

    monkeypatch.setattr(service, "error_body", corrupt)
    result = service._error(contract.ErrorCode.QUOTA_EXCEEDED, 60)  # noqa: SLF001
    assert result.status == 503 and result.body["error"]["code"] == "ANALYSIS_FAILED"
    assert "Retry-After" not in result.headers


def test_an_invalid_stored_body_is_not_replayed(harness_factory):  # (7)
    harness = harness_factory()
    assert harness.post().status_code == 200
    [entry] = harness.ledger.entries()
    body = json.loads(json.dumps(entry.response_body))
    body["gate_result"]["hard_gate_passed"] = "yes"
    key = (entry.credential_id, entry.client_request_id)
    harness.ledger._entries[key] = LedgerEntry(  # noqa: SLF001
        **{**entry.__dict__, "response_body": body}
    )
    response = harness.post()
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "LEDGER_UNAVAILABLE"


def _reserve(ledger, now=NOW):
    return ledger.reserve(
        credential_id="test-radar",
        client_request_id="3f9d2c1e-8a4b-4c2d-9e6f-1a2b3c4d5e6f",
        request_fingerprint="sha256:" + "0" * 64,
        release_id="UCPE-SYNTHETIC-EXAMPLE-V1",
        deadline_ms=30000,
        now=now,
    )


SUCCESS = Outcome(
    "SUCCEEDED",
    200,
    {"synthetic": "evidence"},
    "run_" + "a" * 32,
    "sha256:" + "1" * 64,
    "sha256:" + "2" * 64,
)
LATE = Outcome("DEADLINE_EXCEEDED", 503, {"synthetic": "late"})


def _complete_success(ledger, *, now, deadline):
    return ledger.complete_success(
        credential_id="test-radar",
        client_request_id="3f9d2c1e-8a4b-4c2d-9e6f-1a2b3c4d5e6f",
        outcome=SUCCESS,
        late_outcome=LATE,
        deadline_at_utc=deadline,
        now=now,
        timeout_seconds=2.5,
    )


def test_in_memory_success_is_recorded_only_on_time_and_never_before_reception():  # F1
    ledger = InMemoryAutomationLedger()
    _reserve(ledger)
    assert _complete_success(ledger, now=NOW, deadline=NOW + timedelta(seconds=30)) is True
    assert ledger.entries()[0].outcome_code == "SUCCEEDED"
    late = InMemoryAutomationLedger()
    _reserve(late)
    stepped_back = NOW - timedelta(seconds=5)  # a wall clock that jumped backwards
    assert _complete_success(late, now=stepped_back, deadline=NOW - timedelta(seconds=10)) is False
    [entry] = late.entries()
    assert entry.outcome_code == "DEADLINE_EXCEEDED" and entry.run_id is None
    assert entry.completed_at_utc == NOW  # clamped to received_at_utc


class _FakeDatabase:
    def __init__(self, rows):
        self.rows = iter(rows)
        self.statements = []
        self.commits = 0
        self.connect_kwargs = None

    def connect(self, *_args, **kwargs):
        self.connect_kwargs = kwargs
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def cursor(self):
        return self

    def execute(self, sql, params):
        self.statements.append((" ".join(sql.split()), dict(params)))

    def fetchone(self):
        return next(self.rows)

    def commit(self):
        self.commits += 1


def _pg(rows):
    db = _FakeDatabase(rows)
    return db, PostgresAutomationLedger("synthetic-offline-database", connect=db.connect)


def test_postgres_success_on_time_commits_once():  # F1
    db, ledger = _pg([("row",)])
    assert _complete_success(ledger, now=NOW, deadline=NOW + timedelta(seconds=3)) is True
    assert db.commits == 1 and db.connect_kwargs == {
        "connect_timeout": 3,
        "autocommit": False,
        "prepare_threshold": None,
    }
    (timeout_sql, timeout_params), (update_sql, params) = db.statements
    assert "set_config('statement_timeout'" in timeout_sql and timeout_params["timeout"] == "2500ms"
    assert "clock_timestamp() <= %(deadline_at_utc)s" in update_sql
    assert params["outcome_code"] == "SUCCEEDED" and params["deadline_at_utc"] == NOW + timedelta(
        seconds=3
    )


def test_postgres_late_success_records_the_late_outcome_in_the_same_transaction():  # F1
    db, ledger = _pg([None, ("row",)])
    assert _complete_success(ledger, now=NOW, deadline=NOW) is False
    assert db.commits == 1
    assert [params.get("outcome_code") for _, params in db.statements[1:]] == [
        "SUCCEEDED",
        "DEADLINE_EXCEEDED",
    ]
    assert "clock_timestamp()" not in db.statements[2][0]
    assert "GREATEST(%(completed_at_utc)s, received_at_utc)" in db.statements[2][0]


def test_postgres_success_without_an_in_progress_row_fails_closed():  # F1
    db, ledger = _pg([None, None])
    with pytest.raises(LedgerUnavailable):
        _complete_success(ledger, now=NOW, deadline=NOW)
    assert db.commits == 0
