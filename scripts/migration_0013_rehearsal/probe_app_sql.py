#!/usr/bin/env python
"""Rehearsal probe for migration 0013: the APPLICATION's own SQL, on a real scratch PostgreSQL.

It runs after the rehearse-mode apply, against the same scratch database, as the tables' owner, and
drives the production classes themselves (``PostgresCredentialRegistry`` and
``PostgresAutomationLedger``), not copies of their SQL:
- REGISTRY: an unknown id; a valid credential; a ROTATION (a second credential inserted, both
  valid, then the first revoked) and a REVOCATION taking effect on the very next lookup through the
  same registry object, with no restart; expiry; fail-closed when the database is missing or
  unreachable;
- LEDGER: reserve NEW, IN_PROGRESS, CONFLICT; an on-time success replayed byte for byte through
  JSONB (RFC 8785 JCS of the stored body); a late success recorded as DEADLINE_EXCEEDED; a refusal
  that does not count against the quota; an abandoned reservation;
- HAZARDS: every row the constraints must refuse is refused, by the named constraint.
Every hazard runs in its own transaction and is rolled back. The probe names no secret: its
credential values are synthetic and generated here.

Runs ONLY in a scratch local PostgreSQL on a CI runner, reached through its unix socket, never
where the production database secret is present. Never run it against a real database.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.append(str(ROOT / "src"))

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

URL_VARIABLE = "MIGRATION_0013_REHEARSAL_URL"
_LOCAL_SOCKET_URL = re.compile(r"postgresql:///[a-z_][a-z0-9_]*\?host=/var/run/postgresql")
UNREACHABLE_URL = "postgresql:///migration_0013_no_such_database?host=/var/run/postgresql"
RELEASE_ID = "UCPE-REHEARSAL-PROBE"
FINGERPRINT_1 = "sha256:" + "1" * 64
FINGERPRINT_2 = "sha256:" + "2" * 64
RUN_ID = "run_" + "a" * 32
HASH = "sha256:" + "b" * 64
# Numbers that JSONB stores as numeric: the replay must still render to the same JCS bytes.
EVIDENCE_BODY = {
    "schema_version": "radar_evidence.v1",
    "probe": True,
    "numbers": [0.1, 1e-07, 123456.789, 1.0, -2.5, 0, 9007199254740991],
    "text": "synthetic",
    "nested": {"b": None, "a": [False, {"z": 1, "y": 2}]},
}
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
    probe_hazards(url, psycopg)
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
        analysis_hash=HASH,
        evidence_hash=HASH,
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


def probe_hazards(url: str, psycopg) -> None:
    digest = "c" * 64
    uuid_text = "3f9d2c1e-8a4b-4c2d-9e6f-1a2b3c4d5e6f"
    base_ledger = (
        "INSERT INTO public.automation_radar_ledger (credential_id, client_request_id,"
        " request_fingerprint, evidence_origin, state, outcome_code, http_status, response_body,"
        " run_id, analysis_hash, evidence_hash, release_id, deadline_ms, received_at_utc,"
        " completed_at_utc) VALUES ({credential_id}, '" + uuid_text + "', {fingerprint},"
        " {origin}, {state}, {outcome}, {status}, {body}, {run_id}, {analysis}, {evidence},"
        " {release}, {deadline}, pg_catalog.now(), {completed})"
    )
    good_ledger = {
        "credential_id": "'hazard-probe'",
        "fingerprint": f"'{FINGERPRINT_1}'",
        "origin": "'AUTOMATED_RADAR'",
        "state": "'IN_PROGRESS'",
        "outcome": "NULL",
        "status": "NULL",
        "body": "NULL",
        "run_id": "NULL",
        "analysis": "NULL",
        "evidence": "NULL",
        "release": f"'{RELEASE_ID}'",
        "deadline": "30000",
        "completed": "NULL",
    }
    completed = {
        "state": "'COMPLETED'",
        "body": "'{}'::jsonb",
        "completed": "pg_catalog.now()",
    }

    def ledger_row(**change: str) -> str:
        return base_ledger.format(**{**good_ledger, **change})

    base_registry = (
        "INSERT INTO public.automation_credential (credential_id, secret_sha256, status,"
        " not_after_utc, revoked_at_utc) VALUES ({credential_id}, {digest}, {status},"
        " {not_after}, {revoked})"
    )
    good_registry = {
        "credential_id": "'hazard-probe'",
        "digest": f"'{digest}'",
        "status": "'ACTIVE'",
        "not_after": "NULL",
        "revoked": "NULL",
    }

    def registry_row(**change: str) -> str:
        return base_registry.format(**{**good_registry, **change})

    registry_b = f"'{secret_digest(synthetic_value('b'))}'"
    hazards = [
        (registry_row(credential_id="'rehearsal-b'"), "automation_credential_pkey"),
        (registry_row(digest=registry_b), "ac_secret_sha256_unique"),
        (registry_row(credential_id="'BAD ID'"), "ac_credential_id_format"),
        (registry_row(credential_id="'ab'"), "ac_credential_id_format"),
        (registry_row(digest=f"'{'C' * 64}'"), "ac_secret_sha256_format"),
        (registry_row(digest=f"'{'c' * 63}'"), "ac_secret_sha256_format"),
        # PostgreSQL tests CHECK constraints in name order, so an unknown status is refused by
        # ac_revocation_shape, which implies ac_status_valid (likewise arl_state_shape below).
        (registry_row(status="'DISABLED'"), "ac_revocation_shape"),
        (registry_row(status="'REVOKED'"), "ac_revocation_shape"),
        (registry_row(revoked="pg_catalog.now()"), "ac_revocation_shape"),
        (
            registry_row(not_after="pg_catalog.now() - interval '1 second'"),
            "ac_expiry_after_creation",
        ),
        (ledger_row(credential_id="'BAD ID'"), "arl_credential_id_format"),
        (ledger_row(fingerprint="'sha256:xyz'"), "arl_fingerprint_format"),
        (ledger_row(origin="'USER_REQUESTED'"), "arl_origin_automated"),
        (ledger_row(origin="'CONTROLLED_SMOKE'"), "arl_origin_automated"),
        (ledger_row(state="'DONE'"), "arl_state_shape"),
        (ledger_row(release="'release-1'"), "arl_release_id_format"),
        (ledger_row(deadline="4999"), "arl_deadline_bounds"),
        (ledger_row(deadline="60001"), "arl_deadline_bounds"),
        (ledger_row(state="'COMPLETED'"), "arl_state_shape"),
        (ledger_row(outcome="'SUCCEEDED'", status="200"), "arl_state_shape"),
        (
            # The NULL-safety of the check: a success without its run id or hashes is refused.
            ledger_row(**completed, outcome="'SUCCEEDED'", status="200"),
            "arl_success_shape",
        ),
        (
            ledger_row(**completed, outcome="'SUCCEEDED'", status="200", run_id=f"'{RUN_ID}'"),
            "arl_success_shape",
        ),
        (
            ledger_row(
                **completed,
                outcome="'SUCCEEDED'",
                status="503",
                run_id=f"'{RUN_ID}'",
                analysis=f"'{HASH}'",
                evidence=f"'{HASH}'",
            ),
            "arl_success_shape",
        ),
        (
            ledger_row(**completed, outcome="'QUOTA_EXCEEDED'", status="200"),
            "arl_refusal_shape",
        ),
        (
            ledger_row(**completed, outcome="'QUOTA_EXCEEDED'", status="429", run_id=f"'{RUN_ID}'"),
            "arl_refusal_shape",
        ),
    ]
    for statement, constraint in hazards:
        refused_by = None
        with psycopg.connect(url, autocommit=False) as conn, conn.cursor() as cur:
            try:
                cur.execute(statement)
            except psycopg.errors.IntegrityError as exc:
                refused_by = exc.diag.constraint_name
            conn.rollback()
        check(refused_by == constraint, f"hazard refused by {constraint}: {statement[-90:]}")
    acceptable = ledger_row()
    with psycopg.connect(url, autocommit=False) as conn, conn.cursor() as cur:
        cur.execute(acceptable)
        conn.rollback()
    check(True, "hazard control: the reviewed shape of a row is accepted (then rolled back)")


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
