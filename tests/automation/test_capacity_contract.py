"""The ledger capacity contract: storage is bounded and the route never deletes a row.

docs/automation/RETENTION_AND_IDEMPOTENCY.md states it. A NEW key is refused, with nothing written,
when the ledger holds its row cap (503) or the credential has recorded its rolling-day row ceiling,
refusals included (429). Replays of recorded keys are always served. No stored body exceeds the
byte bound. At the maximum quota, the retention period of one credential always fits the cap.
"""

import json
from datetime import timedelta
from uuid import uuid4

import pytest

from crypto_probability_engine.automation import config as automation_config
from crypto_probability_engine.automation import service as automation_service
from crypto_probability_engine.automation.config import (
    DEFAULT_QUOTA_PER_5MIN,
    DEFAULT_QUOTA_PER_DAY,
    ENV_QUOTA_PER_5MIN,
    ENV_QUOTA_PER_DAY,
    LEDGER_MAX_BODY_BYTES,
    LEDGER_RETENTION_DAYS,
    LEDGER_ROW_CAP,
    LEDGER_ROWS_PER_QUOTA_UNIT,
    MAX_QUOTA_PER_DAY,
)
from crypto_probability_engine.automation.contract import render
from crypto_probability_engine.automation.ledger import (
    DEFAULT_MAX_ROWS_PER_DAY,
    LEDGER_LOCK_KEY,
    InMemoryAutomationLedger,
    Outcome,
    PostgresAutomationLedger,
    ReservationKind,
)
from crypto_probability_engine.automation.quota import throttle_retry_after
from tests.automation.conftest import CREDENTIAL_ID, credential_env, request_body, utc

NOW = utc(2026, 9, 30)
FINGERPRINT = "sha256:" + "1" * 64
DOC = "docs/automation/RETENTION_AND_IDEMPOTENCY.md"


def reserve(ledger, request_id=None, *, credential_id=CREDENTIAL_ID, now=NOW, **limits):
    return ledger.reserve(
        credential_id=credential_id,
        client_request_id=request_id or str(uuid4()),
        request_fingerprint=FINGERPRINT,
        release_id="UCPE-SYNTHETIC-TEST",
        deadline_ms=30000,
        now=now,
        **limits,
    )


# ------------------------------------------------------------------------ the frozen numbers


def test_the_contract_numbers_are_frozen_and_coherent():
    assert (LEDGER_RETENTION_DAYS, LEDGER_ROW_CAP) == (90, 25_000)
    assert (LEDGER_ROWS_PER_QUOTA_UNIT, LEDGER_MAX_BODY_BYTES) == (2, 8_192)
    assert MAX_QUOTA_PER_DAY == DEFAULT_QUOTA_PER_DAY == 120, "G6 stays provisional at 120/day"
    assert DEFAULT_QUOTA_PER_5MIN == 6
    assert DEFAULT_MAX_ROWS_PER_DAY == LEDGER_ROWS_PER_QUOTA_UNIT * MAX_QUOTA_PER_DAY
    # The retention period of one credential at the maximum quota fits under the cap.
    assert MAX_QUOTA_PER_DAY * LEDGER_ROWS_PER_QUOTA_UNIT * LEDGER_RETENTION_DAYS <= LEDGER_ROW_CAP


def test_a_quota_above_the_capacity_contract_is_refused_as_misconfiguration():
    config = automation_config.load_config(
        credential_env(**{ENV_QUOTA_PER_DAY: str(MAX_QUOTA_PER_DAY + 1)})
    )
    assert config.problems and not config.usable


def test_the_doc_states_the_same_numbers():
    from pathlib import Path

    text = Path(__file__).resolve().parents[2].joinpath(DOC).read_text(encoding="utf-8")
    for fragment in ("25,000 rows", "2 x", "8,192 bytes", "at least 90 days", "120 per day"):
        assert fragment in text, fragment


# ------------------------------------------------------------------------ the in-memory ledger


def test_a_full_ledger_refuses_new_keys_without_writing_and_still_replays():
    ledger = InMemoryAutomationLedger()
    first = reserve(ledger, row_cap=2)
    reserve(ledger, row_cap=2)
    full = reserve(ledger, row_cap=2)
    assert full.kind is ReservationKind.FULL and full.entry is None
    assert len(ledger.entries()) == 2
    repeat = reserve(ledger, first.entry.client_request_id, row_cap=2)
    assert repeat.kind is ReservationKind.IN_PROGRESS, "a recorded key is still answered"


def test_the_row_ceiling_counts_refusals_and_is_per_credential():
    ledger = InMemoryAutomationLedger()
    for _ in range(2):
        new = reserve(ledger, max_rows_per_day=3)
        ledger.complete(
            credential_id=CREDENTIAL_ID,
            client_request_id=new.entry.client_request_id,
            outcome=Outcome("QUOTA_EXCEEDED", 429, {}),
            now=NOW,
        )
    assert reserve(ledger, max_rows_per_day=3).kind is ReservationKind.NEW
    throttled = reserve(ledger, max_rows_per_day=3)
    assert throttled.kind is ReservationKind.THROTTLED and throttled.entry is None
    assert throttled.rows_day == 3 and throttled.oldest_row_day == NOW
    assert len(ledger.entries()) == 3
    other = reserve(ledger, credential_id="other-radar", max_rows_per_day=3)
    assert other.kind is ReservationKind.NEW


def test_the_row_ceiling_rolls_with_the_day():
    ledger = InMemoryAutomationLedger()
    reserve(ledger, now=NOW - timedelta(hours=23), max_rows_per_day=1)
    assert reserve(ledger, max_rows_per_day=1).kind is ReservationKind.THROTTLED
    later = NOW + timedelta(hours=1, seconds=1)
    assert reserve(ledger, now=later, max_rows_per_day=1).kind is ReservationKind.NEW


def test_the_throttle_retry_after_is_when_the_oldest_row_leaves_the_day():
    ledger = InMemoryAutomationLedger()
    reserve(ledger, now=NOW - timedelta(hours=20), max_rows_per_day=1)
    throttled = reserve(ledger, max_rows_per_day=1)
    assert throttle_retry_after(throttled, NOW) == 4 * 3600


# ------------------------------------------------------------------------ the Postgres ledger


class FakeDatabase:
    def __init__(self, rows):
        self.rows = iter(rows)
        self.statements = []
        self.commits = 0

    def connect(self, *args, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self

    def execute(self, sql, params=None):
        self.statements.append(" ".join(sql.split()))

    def fetchone(self):
        return next(self.rows)

    def commit(self):
        self.commits += 1


def _counts(rows_day, oldest_row_day=None):
    return (0, 0, None, None, rows_day, oldest_row_day)


@pytest.mark.parametrize(
    ("rows", "limits", "expected"),
    [
        ([None, _counts(0), (25_000,)], {}, ReservationKind.FULL),
        ([None, _counts(0), (3,)], {"row_cap": 3}, ReservationKind.FULL),
        ([None, _counts(240, NOW), (10,)], {}, ReservationKind.THROTTLED),
        ([None, _counts(2, NOW), (10,)], {"max_rows_per_day": 2}, ReservationKind.THROTTLED),
    ],
)
def test_postgres_refusals_commit_nothing_but_the_reads(rows, limits, expected):
    db = FakeDatabase(rows)
    ledger = PostgresAutomationLedger("synthetic-offline-database", connect=db.connect)
    result = reserve(ledger, **limits)
    assert result.kind is expected and result.entry is None
    assert not any(statement.startswith("INSERT") for statement in db.statements)
    assert db.statements[-1] == "SELECT count(*) FROM public.automation_radar_ledger"
    assert db.commits == 1


def test_postgres_takes_one_lock_for_the_whole_ledger():
    assert LEDGER_LOCK_KEY == "ucpe.automation.ledger"


# ------------------------------------------------------------------------ over HTTP


class SmallLedger(InMemoryAutomationLedger):
    def reserve(self, **kwargs):
        return super().reserve(**{**kwargs, "row_cap": 1})


def test_a_full_ledger_answers_503_records_nothing_and_still_replays(harness_factory):
    harness = harness_factory(ledger=SmallLedger())
    first = harness.post()
    assert first.status_code == 200
    second = harness.post(body=request_body(client_request_id=str(uuid4())))
    assert second.status_code == 503 and second.json()["error"]["code"] == "LEDGER_UNAVAILABLE"
    assert len(harness.ledger.entries()) == 1
    replay = harness.post()
    assert replay.status_code == 200 and replay.content == first.content


def test_a_refusal_flood_cannot_grow_the_ledger_past_the_rolling_day_ceiling(harness_factory):
    harness = harness_factory(
        env=credential_env(**{ENV_QUOTA_PER_5MIN: "1", ENV_QUOTA_PER_DAY: "1"}),
        clock=lambda: NOW,
    )
    statuses = [
        harness.post(body=request_body(client_request_id=str(uuid4()))).status_code
        for _ in range(6)
    ]
    assert statuses == [200, 429, 429, 429, 429, 429]
    outcomes = sorted(entry.outcome_code for entry in harness.ledger.entries())
    assert outcomes == ["QUOTA_EXCEEDED", "SUCCEEDED"], "2 x quota rows, then nothing is written"
    throttled = harness.post(body=request_body(client_request_id=str(uuid4())))
    assert throttled.headers["retry-after"] == str(24 * 3600)
    assert throttled.json()["error"]["code"] == "QUOTA_EXCEEDED"
    assert "idempotent-replay" not in throttled.headers


def test_no_body_above_the_byte_bound_is_ever_stored(harness_factory, monkeypatch):
    harness = harness_factory()
    monkeypatch.setattr(automation_service, "LEDGER_MAX_BODY_BYTES", 100)
    response = harness.post()
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "CONTRACT_VIOLATION"
    [entry] = harness.ledger.entries()
    assert entry.outcome_code == "CONTRACT_VIOLATION" and entry.run_id is None
    assert len(render(entry.response_body)) <= LEDGER_MAX_BODY_BYTES


def test_a_real_success_body_is_far_below_the_byte_bound(harness_factory):
    response = harness_factory().post()
    assert response.status_code == 200
    assert len(response.content) < LEDGER_MAX_BODY_BYTES / 2
    assert json.loads(response.content)["schema_version"] == "radar_evidence.v1"
