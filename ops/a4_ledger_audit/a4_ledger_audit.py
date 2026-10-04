"""ucpe.a4_ledger_audit.v1: the sealed, read-only A4 per-request audit of the AUTOMATED_RADAR
ledger.

PURPOSE, and only this: during one owner-authorized UOR qualification episode, prove the one row
of ``public.automation_radar_ledger`` that records one qualification request, so UOR can
adjudicate A4. It is not a database tool. It runs exactly one sealed SELECT
(``a4_ledger_audit.sql``, whose sha256 is pinned below) with five inputs, inside a READ ONLY
transaction that it always rolls back.

INPUTS, copied from UOR's own request and its received 200 response. All are non-secret:
  --credential-id      the machine credential's id, never its value (e.g. uor-radar-2026-10)
  --client-request-id  the request's canonical lowercase UUID
  --run-id             the response's run_id
  --release-id         the response's build_info.release_id
  --evidence-hash      the response's evidence_hash
The database URL comes only from the environment variable A4_AUDIT_DATABASE_URL. It is never
printed, and no exception message is printed either: errors are named by their class only.

OUTPUT: one canonical JSON object on stdout (sorted keys, no whitespace). Exit codes:
  0 PASS · 1 FAIL (the audit ran and the row does not qualify)
  2 inputs refused, nothing contacted · 3 the sealed SQL does not match its pin, nothing contacted
  4 database error or refused session.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

ARTIFACT = "ucpe.a4_ledger_audit.v1"
SQL_PATH = Path(__file__).resolve().with_name("a4_ledger_audit.sql")
SQL_SHA256 = "c33aa3ad7bdbfcafe0d9f7e5bf3a16dafa3b885fac9f19d834d142d02f985eb1"
DATABASE_URL_ENV = "A4_AUDIT_DATABASE_URL"
STATEMENT_TIMEOUT = "5000ms"
LOCK_TIMEOUT = "1000ms"
CONNECT_TIMEOUT_SECONDS = 10

EXIT_PASS, EXIT_FAIL, EXIT_INPUT, EXIT_SEAL, EXIT_DATABASE = 0, 1, 2, 3, 4

# The same formats migration 0013's CHECK constraints enforce, so a value the ledger could never
# hold is refused before anything is contacted. A credential VALUE (ucpea.<id>.<value>) fails the
# id format.
CREDENTIAL_ID = re.compile(r"[a-z0-9][a-z0-9-]{2,31}")
RUN_ID = re.compile(r"run_[0-9a-f]{32}")
RELEASE_ID = re.compile(r"UCPE-[A-Z0-9-]{3,}")
EVIDENCE_HASH = re.compile(r"sha256:[0-9a-f]{64}")

# The sealed SELECT's output columns, in order. Anything else is refused.
SQL_COLUMNS = (
    "audit",
    "verdict",
    "reason",
    "bound_credential_id",
    "bound_client_request_id",
    "schema_ok",
    "matched_rows",
    "evidence_origin",
    "origin_automated_radar",
    "state",
    "outcome_code",
    "http_status",
    "run_id",
    "run_id_matches",
    "release_id",
    "release_id_matches",
    "evidence_hash",
    "evidence_hash_matches",
    "body_identity_consistent",
)
REASONS = (
    "SCHEMA_DRIFT",
    "NO_ROW",
    "AMBIGUOUS",
    "WRONG_ORIGIN",
    "NOT_COMPLETED",
    "NOT_SUCCEEDED",
    "BODY_IDENTITY_MISMATCH",
    "RUN_MISMATCH",
    "RELEASE_MISMATCH",
    "EVIDENCE_MISMATCH",
    "OK",
)


@dataclass(frozen=True)
class Binding:
    credential_id: str
    client_request_id: str
    run_id: str
    release_id: str
    evidence_hash: str

    def parameters(self) -> dict[str, str]:
        return {
            "credential_id": self.credential_id,
            "client_request_id": self.client_request_id,
            "expected_run_id": self.run_id,
            "expected_release_id": self.release_id,
            "expected_evidence_hash": self.evidence_hash,
        }


class Refusal(Exception):
    """A stop before or during the audit: only ``reason`` and ``exit_code`` are reported."""

    def __init__(self, reason: str, exit_code: int, error_class: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.exit_code = exit_code
        self.error_class = error_class


def validate(
    credential_id: str, client_request_id: str, run_id: str, release_id: str, evidence_hash: str
) -> Binding:
    """The binding, or Refusal(INPUT_REFUSED) naming only which input failed, never its value."""

    if not CREDENTIAL_ID.fullmatch(credential_id):
        raise Refusal("INPUT_REFUSED:credential_id", EXIT_INPUT)
    if not _canonical_uuid(client_request_id):
        raise Refusal("INPUT_REFUSED:client_request_id", EXIT_INPUT)
    if not RUN_ID.fullmatch(run_id):
        raise Refusal("INPUT_REFUSED:run_id", EXIT_INPUT)
    if not RELEASE_ID.fullmatch(release_id):
        raise Refusal("INPUT_REFUSED:release_id", EXIT_INPUT)
    if not EVIDENCE_HASH.fullmatch(evidence_hash):
        raise Refusal("INPUT_REFUSED:evidence_hash", EXIT_INPUT)
    return Binding(credential_id, client_request_id, run_id, release_id, evidence_hash)


def _canonical_uuid(value: str) -> bool:
    try:
        return str(uuid.UUID(value)) == value
    except (ValueError, AttributeError, TypeError):
        return False


def sealed_sql(path: Path | None = None) -> str:
    """The sealed SELECT, only if its bytes match the pinned sha256."""

    data = (path or SQL_PATH).read_bytes()
    if hashlib.sha256(data).hexdigest() != SQL_SHA256:
        raise Refusal("SEAL_MISMATCH", EXIT_SEAL)
    return data.decode("utf-8")


READ_ONLY_PREAMBLE = (
    "SET TRANSACTION READ ONLY",
    f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'",
    f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'",
)


def begin_read_only(cursor: Any) -> None:
    """Open the transaction READ ONLY, bounded, and prove it before anything else runs."""

    for statement in READ_ONLY_PREAMBLE:
        cursor.execute(statement)
    cursor.execute("SELECT pg_catalog.current_setting('transaction_read_only')")
    read_only = cursor.fetchone()
    if read_only is None or read_only[0] != "on":
        raise Refusal("NOT_READ_ONLY", EXIT_DATABASE)


def run_sealed_audit(
    database_url: str, binding: Binding, sql: str, *, connect: Callable[..., Any]
) -> dict[str, Any]:
    """One READ ONLY transaction: prove read-only, run the sealed SELECT, always roll back."""

    try:
        connection = connect(
            database_url,
            connect_timeout=CONNECT_TIMEOUT_SECONDS,
            autocommit=False,
            prepare_threshold=None,
            application_name="ucpe-a4-ledger-audit",
        )
    except Exception as exc:
        raise Refusal("DATABASE_ERROR", EXIT_DATABASE, type(exc).__name__) from None
    try:
        try:
            with connection.cursor() as cursor:
                begin_read_only(cursor)
                cursor.execute(sql, binding.parameters())
                rows = cursor.fetchall()
                names = tuple(_column_name(column) for column in cursor.description or ())
        finally:
            _end_quietly(connection)
    except Refusal:
        raise
    except Exception as exc:
        raise Refusal("DATABASE_ERROR", EXIT_DATABASE, type(exc).__name__) from None
    if names != SQL_COLUMNS or len(rows) != 1:
        raise Refusal("UNEXPECTED_RESULT_SHAPE", EXIT_DATABASE)
    return dict(zip(SQL_COLUMNS, rows[0], strict=True))


def _end_quietly(connection: Any) -> None:
    """Roll back, then close. A failure of either is not reported: nothing was written."""

    for step in (connection.rollback, connection.close):
        try:
            step()
        except Exception:  # noqa: BLE001 - the session ends either way
            pass


def _column_name(column: Any) -> str:
    return column.name if hasattr(column, "name") else column[0]


def expected_reason(facts: Mapping[str, Any], binding: Binding) -> str:
    """The runner's own recomputation of the SQL's decision, from the returned facts."""

    if facts["schema_ok"] is not True:
        return "SCHEMA_DRIFT"
    if facts["matched_rows"] == 0:
        return "NO_ROW"
    if facts["matched_rows"] != 1:
        return "AMBIGUOUS"
    if facts["evidence_origin"] != "AUTOMATED_RADAR":
        return "WRONG_ORIGIN"
    if facts["state"] != "COMPLETED":
        return "NOT_COMPLETED"
    if facts["outcome_code"] != "SUCCEEDED" or facts["http_status"] != 200:
        return "NOT_SUCCEEDED"
    if facts["origin_automated_radar"] is not True:  # the stored body's origin, too
        return "WRONG_ORIGIN"
    if facts["body_identity_consistent"] is not True:
        return "BODY_IDENTITY_MISMATCH"
    if facts["run_id"] != binding.run_id:
        return "RUN_MISMATCH"
    if facts["release_id"] != binding.release_id:
        return "RELEASE_MISMATCH"
    if facts["evidence_hash"] != binding.evidence_hash:
        return "EVIDENCE_MISMATCH"
    return "OK"


def cross_check(facts: Mapping[str, Any], binding: Binding) -> bool:
    """The SQL's own answer agrees with the runner's independent reading of its facts."""

    reason = expected_reason(facts, binding)
    return (
        facts["audit"] == ARTIFACT
        and facts["reason"] in REASONS
        and facts["reason"] == reason
        and facts["verdict"] == ("PASS" if reason == "OK" else "FAIL")
        and facts["bound_credential_id"] == binding.credential_id
        and facts["bound_client_request_id"] == binding.client_request_id
        and facts["run_id_matches"] is (facts["run_id"] == binding.run_id)
        and facts["release_id_matches"] is (facts["release_id"] == binding.release_id)
        and facts["evidence_hash_matches"] is (facts["evidence_hash"] == binding.evidence_hash)
    )


def audit(
    binding: Binding, environ: Mapping[str, str], *, connect: Callable[..., Any] | None = None
) -> tuple[dict[str, Any], int]:
    """The output object and the exit code. Refusals are reported, never raised."""

    base = {
        "artifact": ARTIFACT,
        "sql_sha256": SQL_SHA256,
        "bound_credential_id": binding.credential_id,
        "bound_client_request_id": binding.client_request_id,
    }
    try:
        return _audit(binding, environ, base, connect)
    except Exception as exc:  # noqa: BLE001 - never a traceback that could carry a value
        return {**base, "verdict": "FAIL", "reason": "INTERNAL_ERROR",
                "error_class": type(exc).__name__}, EXIT_DATABASE


def _audit(
    binding: Binding,
    environ: Mapping[str, str],
    base: dict[str, Any],
    connect: Callable[..., Any] | None,
) -> tuple[dict[str, Any], int]:
    try:
        sql = sealed_sql()
        database_url = environ.get(DATABASE_URL_ENV, "").strip()
        if not database_url:
            raise Refusal("DATABASE_URL_MISSING", EXIT_DATABASE)
        if connect is None:
            import psycopg

            connect = psycopg.connect
        facts = run_sealed_audit(database_url, binding, sql, connect=connect)
    except Refusal as refusal:
        failed = {**base, "verdict": "FAIL", "reason": refusal.reason}
        if refusal.error_class:
            failed["error_class"] = refusal.error_class
        return failed, refusal.exit_code
    output = {**base, **facts, "transaction_read_only": True}
    if not cross_check(facts, binding):
        output.update(verdict="FAIL", reason="RUNNER_DISAGREES")
        return output, EXIT_FAIL
    return output, EXIT_PASS if facts["verdict"] == "PASS" else EXIT_FAIL


class _Parser(argparse.ArgumentParser):
    """argparse that never echoes an argument: a pasted credential must not reach a terminal."""

    def error(self, message: str) -> None:  # type: ignore[override]
        del message
        raise Refusal("INPUT_REFUSED:arguments", EXIT_INPUT)


def render(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    connect: Callable[..., Any] | None = None,
    stdout: TextIO | None = None,
) -> int:
    parser = _Parser(prog="a4_ledger_audit", add_help=False)  # -h must not exit 0, the PASS code
    for name in ("credential-id", "client-request-id", "run-id", "release-id", "evidence-hash"):
        parser.add_argument(f"--{name}", required=True)
    out = stdout or sys.stdout
    try:
        args = parser.parse_args(argv)
        binding = validate(
            args.credential_id, args.client_request_id, args.run_id, args.release_id,
            args.evidence_hash,
        )
    except Refusal as refusal:
        refused = {"artifact": ARTIFACT, "verdict": "FAIL", "reason": refusal.reason}
        out.write(render(refused) + "\n")
        return refusal.exit_code
    payload, code = audit(binding, os.environ if environ is None else environ, connect=connect)
    out.write(render(payload) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
