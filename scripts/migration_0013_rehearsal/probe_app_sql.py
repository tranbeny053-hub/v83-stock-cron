#!/usr/bin/env python
"""Rehearsal probe for migration 0013: the APPLICATION's own SQL, on a real scratch PostgreSQL.

It runs after the rehearse-mode apply, against the same scratch database, as the tables' owner, and
drives the production classes themselves (``PostgresCredentialRegistry`` and
``PostgresAutomationLedger``), not copies of their SQL:
- REGISTRY: an unknown id; a valid credential; a ROTATION (a second credential inserted, both
  valid, then the first revoked) and a REVOCATION taking effect on the very next lookup through the
  same registry object, with no restart; expiry; fail-closed when the database is missing or
  unreachable;
- LEDGER: reserve NEW, IN_PROGRESS, CONFLICT; an on-time success, whose body is a full
  schema-valid radar_evidence.v1 body (the pinned synthetic example), replayed byte for byte
  through JSONB (RFC 8785 JCS of the stored body); a late success recorded as DEADLINE_EXCEEDED; a
  refusal that does not count against the quota; an abandoned reservation;
- CAPACITY: the rolling-day row ceiling and the row cap each refuse a NEW key and write nothing,
  while a recorded key is still answered;
- CONSTRAINTS: the apply route's own 42 constraint probes, re-run against tables that now hold the
  application's rows, each in a savepoint that is rolled back: every row shape the route and the
  owner write is accepted, and every other shape is refused by its named constraint.
The probe names no secret: its credential values are synthetic and generated here.

Runs ONLY in a scratch local PostgreSQL on a CI runner, reached through its unix socket, never
where the production database secret is present. Never run it against a real database.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _path in (ROOT / "src", ROOT):
    if str(_path) not in sys.path:
        sys.path.append(str(_path))

from crypto_probability_engine.automation.canonical import jcs_bytes  # noqa: E402
from crypto_probability_engine.automation.credentials import (  # noqa: E402
    CredentialRefusal,
    MachinePrincipal,
    PostgresCredentialRegistry,
    RegistryUnavailable,
    authenticate,
    secret_digest,
)
from crypto_probability_engine.automation.ledger import (  # noqa: E402
    LedgerUnavailable,
    Outcome,
    PostgresAutomationLedger,
    ReservationKind,
)
from scripts import apply_migration_0013 as apply_route  # noqa: E402

URL_VARIABLE = "MIGRATION_0013_REHEARSAL_URL"
_LOCAL_SOCKET_URL = re.compile(r"postgresql:///[a-z_][a-z0-9_]*\?host=/var/run/postgresql")
UNREACHABLE_URL = "postgresql:///migration_0013_no_such_database?host=/var/run/postgresql"
RELEASE_ID = "UCPE-REHEARSAL-PROBE"
FINGERPRINT_1 = "sha256:" + "1" * 64
FINGERPRINT_2 = "sha256:" + "2" * 64
# A full, schema-valid radar_evidence.v1 body: the pinned synthetic example (UOR_HANDOFF.md). Its
# numbers are stored by JSONB as numeric; the replay must still render to the same JCS bytes.
EXAMPLE = ROOT / "docs/automation/examples/radar_evidence.v1.synthetic-btc-4h-gate-blocked.json"
EVIDENCE_BODY = json.loads(EXAMPLE.read_text(encoding="utf-8"))
RUN_ID = EVIDENCE_BODY["run_id"]
ANALYSIS_HASH = EVIDENCE_BODY["analysis_hash"]
EVIDENCE_HASH = EVIDENCE_BODY["evidence_hash"]
LATE_BODY = {"schema_version": "radar_evidence_error.v1", "error": {"code": "DEADLINE_EXCEEDED"}}
QUOTA_BODY = {"schema_version": "radar_evidence_error.v1", "error": {"code": "QUOTA_EXCEEDED"}}

checks_passed: list[str] = []


def check(condition: bool, what: str) -> None:
    if not condition:
        raise SystemExit(f"PROBE FAILED: {what}")
    checks_passed.append(what)


def synthetic_value(label: str) -> str:
    """43 URL-safe characters derived from a label: obviously synthetic, never a real secret."""

    return hashlib.sha256(f"ucpe-rehearsal-{label}".encode()).hexdigest()[:43]


def token(credential_id: str, value: str) -> str:
    return f"ucpea.{credential_id}.{value}"


def main() -> int:
    url = os.environ.get(URL_VARIABLE, "")
    if not _LOCAL_SOCKET_URL.fullmatch(url):
        raise SystemExit(f"PROBE REFUSED: {URL_VARIABLE} must be a local unix-socket URL")
    if os.environ.get("SUPABASE_DB_URL"):
        raise SystemExit("PROBE REFUSED: never beside the production database secret")
    import psycopg

    def sql(statement: str, params: dict | None = None):
        with psycopg.connect(url, autocommit=False) as conn, conn.cursor() as cur:
            cur.execute(statement, params or {})
            rows = cur.fetchall() if cur.description else None
            conn.commit()
            return rows

    probe_registry(url, sql)
    probe_ledger(url, sql)
    probe_capacity(url, sql)
    probe_constraints(url, psycopg)
    probe_fail_closed()
    print(f"PROBE PASS: {len(checks_passed)} checks")
    for what in checks_passed:
        print(f"  ok  {what}")
    return 0


def probe_registry(url: str, sql) -> None:
    registry = PostgresCredentialRegistry(url)
    now = datetime.now(UTC)
    value_a, value_b, value_c = (synthetic_value(label) for label in ("a", "b", "c"))
    check(registry.lookup("rehearsal-a") is None, "registry: an unknown id reads as None")
    check(
        authenticate(token("rehearsal-a", value_a), registry, now=now) is CredentialRefusal.UNKNOWN,
        "registry: an unknown id is refused as UNKNOWN",
    )
    insert = (
        "INSERT INTO public.automation_credential (credential_id, secret_sha256, status,"
        " not_after_utc) VALUES (%(id)s, %(digest)s, 'ACTIVE', %(not_after)s)"
    )
    sql(insert, {"id": "rehearsal-a", "digest": secret_digest(value_a), "not_after": None})
    record = registry.lookup("rehearsal-a")
    check(
        record is not None
        and record.status == "ACTIVE"
        and record.secret_sha256 == secret_digest(value_a),
        "registry: a stored credential reads back as its digest and status",
    )
    check(
        authenticate(token("rehearsal-a", value_a), registry, now=now)
        == MachinePrincipal("rehearsal-a"),
        "registry: a valid credential authenticates",
    )
    check(
        authenticate(token("rehearsal-a", value_b), registry, now=now)
        is CredentialRefusal.MISMATCH,
        "registry: a wrong value for a known id is refused as MISMATCH",
    )
    # ROTATION: the new credential first, both valid, then the old one revoked.
    sql(insert, {"id": "rehearsal-b", "digest": secret_digest(value_b), "not_after": None})
    check(
        isinstance(authenticate(token("rehearsal-a", value_a), registry, now=now), MachinePrincipal)
        and isinstance(
            authenticate(token("rehearsal-b", value_b), registry, now=now), MachinePrincipal
        ),
        "rotation: the old and the new credential are both valid during the overlap",
    )
    sql(
        "UPDATE public.automation_credential SET status = 'REVOKED',"
        " revoked_at_utc = pg_catalog.now() WHERE credential_id = 'rehearsal-a'"
    )
    check(
        authenticate(token("rehearsal-a", value_a), registry, now=now) is CredentialRefusal.REVOKED,
        "revocation: the very next lookup refuses the revoked credential, with no restart",
    )
    check(
        authenticate(token("rehearsal-b", value_b), registry, now=now)
        == MachinePrincipal("rehearsal-b"),
        "rotation: the new credential stays valid after the old one is revoked",
    )
    not_after = now + timedelta(hours=1)
    sql(insert, {"id": "rehearsal-c", "digest": secret_digest(value_c), "not_after": not_after})
    stored = registry.lookup("rehearsal-c")
    check(
        stored is not None and stored.not_after_utc == not_after,
        "expiry: not_after_utc reads back as the same timezone-aware instant",
    )
    check(
        isinstance(
            authenticate(token("rehearsal-c", value_c), registry, now=not_after - timedelta(0, 1)),
            MachinePrincipal,
        )
        and authenticate(token("rehearsal-c", value_c), registry, now=not_after)
        is CredentialRefusal.EXPIRED,
        "expiry: valid before not_after_utc, refused from it on",
    )


def probe_ledger(url: str, sql) -> None:
    ledger = PostgresAutomationLedger(url)
    now = datetime.now(UTC)
    first = str(uuid.uuid4())

    def reserve(request_id: str, fingerprint: str = FINGERPRINT_1, at: datetime = now):
        return ledger.reserve(
            credential_id="rehearsal-b",
            client_request_id=request_id,
            request_fingerprint=fingerprint,
            release_id=RELEASE_ID,
            deadline_ms=30000,
            now=at,
        )

    check(reserve(first).kind is ReservationKind.NEW, "ledger: a new key is reserved NEW")
    check(
        reserve(first).kind is ReservationKind.IN_PROGRESS,
        "ledger: a repeat while running is IN_PROGRESS",
    )
    check(
        reserve(first, FINGERPRINT_2).kind is ReservationKind.CONFLICT,
        "ledger: a repeat with another fingerprint is a CONFLICT",
    )
    success = Outcome(
        outcome_code="SUCCEEDED",
        http_status=200,
        response_body=EVIDENCE_BODY,
        run_id=RUN_ID,
        analysis_hash=ANALYSIS_HASH,
        evidence_hash=EVIDENCE_HASH,
    )
    late = Outcome(outcome_code="DEADLINE_EXCEEDED", http_status=503, response_body=LATE_BODY)
    on_time = ledger.complete_success(
        credential_id="rehearsal-b",
        client_request_id=first,
        outcome=success,
        late_outcome=late,
        deadline_at_utc=datetime.now(UTC) + timedelta(seconds=30),
        now=datetime.now(UTC),
        timeout_seconds=5,
    )
    check(on_time is True, "ledger: a success within the deadline is recorded as SUCCEEDED")
    replay = reserve(first)
    check(
        replay.kind is ReservationKind.REPLAY
        and replay.entry is not None
        and replay.entry.http_status == 200
        and jcs_bytes(replay.entry.response_body) == jcs_bytes(EVIDENCE_BODY),
        "ledger: the replay is the stored body, byte-identical in JCS through JSONB",
    )
    second = str(uuid.uuid4())
    check(reserve(second).kind is ReservationKind.NEW, "ledger: a second key is reserved NEW")
    recorded_on_time = ledger.complete_success(
        credential_id="rehearsal-b",
        client_request_id=second,
        outcome=success,
        late_outcome=late,
        deadline_at_utc=datetime.now(UTC) - timedelta(seconds=1),
        now=datetime.now(UTC),
        timeout_seconds=5,
    )
    late_replay = reserve(second)
    check(
        recorded_on_time is False
        and late_replay.kind is ReservationKind.REPLAY
        and late_replay.entry.outcome_code == "DEADLINE_EXCEEDED"
        and late_replay.entry.run_id is None
        and late_replay.entry.response_body == LATE_BODY,
        "deadline: a success after the database clock passed the deadline is DEADLINE_EXCEEDED",
    )
    third = str(uuid.uuid4())
    before = reserve(str(uuid.uuid4()))
    ledger.complete(
        credential_id="rehearsal-b",
        client_request_id=before.entry.client_request_id,
        outcome=Outcome(outcome_code="QUOTA_EXCEEDED", http_status=429, response_body=QUOTA_BODY),
        now=datetime.now(UTC),
    )
    after = reserve(third)
    check(
        after.kind is ReservationKind.NEW and after.counted_5min == before.counted_5min,
        "quota: a QUOTA_EXCEEDED refusal does not count against the quota",
    )
    check(
        reserve(str(uuid.uuid4())).counted_5min == after.counted_5min + 1,
        "quota: an in-progress reservation counts against the quota",
    )
    stale = str(uuid.uuid4())
    reserve(stale, at=now - timedelta(minutes=10))
    check(
        reserve(stale).kind is ReservationKind.ABANDONED,
        "ledger: a reservation past its deadline and grace is ABANDONED, never re-run",
    )
    rows = sql(
        "SELECT count(*), count(*) FILTER (WHERE evidence_origin = 'AUTOMATED_RADAR')"
        " FROM public.automation_radar_ledger"
    )
    check(rows[0][0] == rows[0][1] > 0, "ledger: every row is stamped AUTOMATED_RADAR")


def probe_capacity(url: str, sql) -> None:
    ledger = PostgresAutomationLedger(url)
    now = datetime.now(UTC)

    def reserve(request_id: str, **limits):
        return ledger.reserve(
            credential_id="capacity-probe",
            client_request_id=request_id,
            request_fingerprint=FINGERPRINT_1,
            release_id=RELEASE_ID,
            deadline_ms=30000,
            now=now,
            **limits,
        )

    def own_rows() -> int:
        return sql(
            "SELECT count(*) FROM public.automation_radar_ledger"
            " WHERE credential_id = 'capacity-probe'"
        )[0][0]

    first = str(uuid.uuid4())
    kinds = [reserve(key, max_rows_per_day=2).kind for key in (first, str(uuid.uuid4()))]
    throttled = reserve(str(uuid.uuid4()), max_rows_per_day=2)
    check(
        kinds == [ReservationKind.NEW, ReservationKind.NEW]
        and throttled.kind is ReservationKind.THROTTLED
        and throttled.rows_day == 2
        and own_rows() == 2,
        "capacity: the rolling-day row ceiling refuses a new key and writes nothing",
    )
    total = sql("SELECT count(*) FROM public.automation_radar_ledger")[0][0]
    full = reserve(str(uuid.uuid4()), row_cap=total)
    check(
        full.kind is ReservationKind.FULL
        and sql("SELECT count(*) FROM public.automation_radar_ledger")[0][0] == total,
        "capacity: a full ledger refuses a new key and writes nothing",
    )
    check(
        reserve(first, row_cap=total).kind is ReservationKind.IN_PROGRESS,
        "capacity: a recorded key is still answered when the ledger is full",
    )


def probe_constraints(url: str, psycopg) -> None:
    """The apply route's constraint probes, against tables that hold the application's rows."""

    with psycopg.connect(url, autocommit=False) as conn, conn.cursor() as cur:
        captured: dict = {}
        observed = apply_route.run_constraint_probes(cur, captured)
        conn.rollback()
    failures = apply_route.probe_failures(observed)
    check(
        failures == [] and len(observed) == len(apply_route.CONSTRAINT_PROBES),
        f"constraints: all {len(observed)} apply-route probes behave as reviewed {failures}",
    )


def probe_fail_closed() -> None:
    for url, what in ((None, "missing"), (UNREACHABLE_URL, "unreachable")):
        try:
            PostgresCredentialRegistry(url).lookup("rehearsal-b")
        except RegistryUnavailable:
            registry_closed = True
        else:
            registry_closed = False
        try:
            PostgresAutomationLedger(url).reserve(
                credential_id="rehearsal-b",
                client_request_id=str(uuid.uuid4()),
                request_fingerprint=FINGERPRINT_1,
                release_id=RELEASE_ID,
                deadline_ms=30000,
                now=datetime.now(UTC),
            )
        except LedgerUnavailable:
            ledger_closed = True
        else:
            ledger_closed = False
        check(
            registry_closed and ledger_closed,
            f"transport: the registry and the ledger fail closed when the database is {what}",
        )


if __name__ == "__main__":
    sys.exit(main())
