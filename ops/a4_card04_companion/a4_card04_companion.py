"""ucpe.a4_card04_companion.v1: the sealed, read-only companion of ucpe.a4_ledger_audit.v1, for
UOR Card 04.

PURPOSE, and only this: during one owner-authorized UOR qualification episode, beside the accepted
A4 audit of the same request, prove the four durable facts Card 04 still needs: the request's
deadline_ms, the run's analysis_hash, how many prediction rows carry the run id, and how many
ledger rows the credential has since the qualification's activation. It is not a database tool.
It runs exactly one sealed SELECT (``a4_card04_companion.sql``, whose sha256 is pinned below) with
six inputs, inside a READ ONLY transaction with row security off, which it always rolls back.

INPUTS, all non-secret, from UOR's own record of the request and its received 200 response:
  --credential-id                 the machine credential's id, never its value
  --client-request-id             the request's canonical lowercase UUID
  --run-id                        the response's run_id
  --deadline-ms                   the request's deadline_ms, an integer from 5000 to 60000
  --analysis-hash                 the response's analysis_hash
  --qualification-activation-utc  the activation instant, UTC: YYYY-MM-DDTHH:MM:SS[.ffffff]Z
The database URL comes only from the environment variable A4_COMPANION_DATABASE_URL. It is never
printed, and no exception message is printed either: errors are named by their class only.

Before anything is contacted, every sealed file must match MANIFEST.json and the SQL its pin.

OUTPUT: one canonical JSON object on stdout (sorted keys, no whitespace). Exit codes:
  0 PASS · 1 FAIL (the audit ran and the row does not qualify)
  2 inputs refused, nothing contacted · 3 the package or the SQL does not match its seal, nothing
  contacted · 4 database error or refused session.
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
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

ARTIFACT = "ucpe.a4_card04_companion.v1"
PACKAGE = Path(__file__).resolve().parent
PACKAGE_PATH = "ops/a4_card04_companion"
SQL_PATH = PACKAGE / "a4_card04_companion.sql"
MANIFEST_PATH = PACKAGE / "MANIFEST.json"
SEALED_FILES = ("a4_card04_companion.sql", "a4_card04_companion.py", "CARD.md", "build_manifest.py")
SQL_SHA256 = "d0268ba15beb508e7e256dc40c5b72cd77b7aa66f4d81ee0604b59a3545187d1"
DATABASE_URL_ENV = "A4_COMPANION_DATABASE_URL"
STATEMENT_TIMEOUT = "5000ms"
LOCK_TIMEOUT = "1000ms"
CONNECT_TIMEOUT_SECONDS = 10

EXIT_PASS, EXIT_FAIL, EXIT_INPUT, EXIT_SEAL, EXIT_DATABASE = 0, 1, 2, 3, 4

# The formats migration 0013's CHECK constraints and the route's request contract enforce, so a
# value the ledger could never hold is refused before anything is contacted. A credential VALUE
# (ucpea.<id>.<value>) fails the id format.
CREDENTIAL_ID = re.compile(r"[a-z0-9][a-z0-9-]{2,31}")
RUN_ID = re.compile(r"run_[0-9a-f]{32}")
DEADLINE_MS = re.compile(r"[1-9][0-9]{3,4}")
DEADLINE_MS_MIN, DEADLINE_MS_MAX = 5000, 60000
ANALYSIS_HASH = re.compile(r"sha256:[0-9a-f]{64}")
ACTIVATION_UTC = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?Z"
)

# The sealed SELECT's output columns, in order. Anything else is refused.
SQL_COLUMNS = (
    "artifact",
    "verdict",
    "reason",
    "bound_credential_id",
    "bound_client_request_id",
    "bound_run_id",
    "schema_ok",
    "deadline_ms",
    "deadline_ms_matches",
    "analysis_hash",
    "analysis_hash_matches",
    "predictions_rows_for_run_id",
    "credential_ledger_rows_since_activation",
)
REASONS = (
    "SCHEMA_DRIFT",
    "NO_ROW",
    "AMBIGUOUS",
    "WRONG_ORIGIN",
    "NOT_COMPLETED",
    "NOT_SUCCEEDED",
    "RUN_MISMATCH",
    "DEADLINE_MISMATCH",
    "ANALYSIS_HASH_MISMATCH",
    "ACTIVATION_AFTER_REQUEST",
    "OK",
)


@dataclass(frozen=True)
class Binding:
    credential_id: str
    client_request_id: str
    run_id: str
    deadline_ms: str
    analysis_hash: str
    activation_utc: str

    def parameters(self) -> dict[str, str]:
        return {
            "credential_id": self.credential_id,
            "client_request_id": self.client_request_id,
            "expected_run_id": self.run_id,
            "expected_deadline_ms": self.deadline_ms,
            "expected_analysis_hash": self.analysis_hash,
            "qualification_activation_utc": self.activation_utc,
        }


class Refusal(Exception):
    """A stop before or during the audit: only ``reason`` and ``exit_code`` are reported."""

    def __init__(self, reason: str, exit_code: int, error_class: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.exit_code = exit_code
        self.error_class = error_class


def validate(
    credential_id: str,
    client_request_id: str,
    run_id: str,
    deadline_ms: str,
    analysis_hash: str,
    activation_utc: str,
) -> Binding:
    """The binding, or Refusal(INPUT_REFUSED) naming only which input failed, never its value."""

    if not CREDENTIAL_ID.fullmatch(credential_id):
        raise Refusal("INPUT_REFUSED:credential_id", EXIT_INPUT)
    if not _canonical_uuid(client_request_id):
        raise Refusal("INPUT_REFUSED:client_request_id", EXIT_INPUT)
    if not RUN_ID.fullmatch(run_id):
        raise Refusal("INPUT_REFUSED:run_id", EXIT_INPUT)
    if not DEADLINE_MS.fullmatch(deadline_ms) or not (
        DEADLINE_MS_MIN <= int(deadline_ms) <= DEADLINE_MS_MAX
    ):
        raise Refusal("INPUT_REFUSED:deadline_ms", EXIT_INPUT)
    if not ANALYSIS_HASH.fullmatch(analysis_hash):
        raise Refusal("INPUT_REFUSED:analysis_hash", EXIT_INPUT)
    if not _canonical_utc(activation_utc):
        raise Refusal("INPUT_REFUSED:qualification_activation_utc", EXIT_INPUT)
    return Binding(
        credential_id, client_request_id, run_id, deadline_ms, analysis_hash, activation_utc
    )


def _canonical_uuid(value: str) -> bool:
    """The route's own rule: lowercase, hyphenated, RFC 4122 variant, version 1 to 8."""

    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return str(parsed) == value and parsed.variant == uuid.RFC_4122 and 1 <= parsed.version <= 8


def _canonical_utc(value: str) -> bool:
    """A real UTC instant written YYYY-MM-DDTHH:MM:SS[.ffffff]Z, nothing else."""

    match = ACTIVATION_UTC.fullmatch(value)
    if not match:
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ" if match[1] else "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def verified_package() -> tuple[str, str]:
    """(the sealed SQL, the seal's sha256), only if every sealed file matches MANIFEST.json and the
    SQL matches its pin."""

    try:
        manifest_bytes = MANIFEST_PATH.read_bytes()
        files = json.loads(manifest_bytes)["files"]
        expected = {f"{PACKAGE_PATH}/{name}" for name in SEALED_FILES}
        intact = set(files) == expected and all(
            hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest()
            == files[f"{PACKAGE_PATH}/{name}"]
            for name in SEALED_FILES
        )
        data = SQL_PATH.read_bytes()
    except (OSError, ValueError, KeyError, TypeError):
        raise Refusal("SEAL_MISMATCH", EXIT_SEAL) from None
    if not intact:
        raise Refusal("SEAL_MISMATCH", EXIT_SEAL)
    if hashlib.sha256(data).hexdigest() != SQL_SHA256:
        raise Refusal("SEAL_MISMATCH", EXIT_SEAL)
    return data.decode("utf-8"), hashlib.sha256(manifest_bytes).hexdigest()


READ_ONLY_PREAMBLE = (
    "SET TRANSACTION READ ONLY",
    f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'",
    f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'",
    "SET LOCAL row_security = off",
)
SESSION_PROOF = (
    "SELECT pg_catalog.current_setting('transaction_read_only'),"
    " pg_catalog.current_setting('row_security')"
)


def begin_read_only(cursor: Any) -> None:
    """Open the transaction READ ONLY, bounded, with row security off, and prove both before
    anything else runs. With row security off, a policy that would hide a row raises an error, so
    a count can never be silently filtered."""

    for statement in READ_ONLY_PREAMBLE:
        cursor.execute(statement)
    cursor.execute(SESSION_PROOF)
    proof = cursor.fetchone()
    if proof is None or proof[0] != "on":
        raise Refusal("NOT_READ_ONLY", EXIT_DATABASE)
    if proof[1] != "off":
        raise Refusal("ROW_SECURITY_NOT_OFF", EXIT_DATABASE)


def run_sealed_audit(
    database_url: str, binding: Binding, sql: str, *, connect: Callable[..., Any]
) -> dict[str, Any]:
    """One READ ONLY transaction: prove the session, run the sealed SELECT, always roll back."""

    try:
        connection = connect(
            database_url,
            connect_timeout=CONNECT_TIMEOUT_SECONDS,
            autocommit=False,
            prepare_threshold=None,
            application_name="ucpe-a4-card04-companion",
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


def _count(value: Any) -> bool:
    return type(value) is int and value >= 0


def cross_check(facts: Mapping[str, Any], binding: Binding) -> bool:
    """The SQL's own answer agrees with the runner's independent reading of what it returned."""

    reason = facts["reason"]
    if reason not in REASONS:
        return False
    position = REASONS.index(reason)
    deadline, analysis_hash = facts["deadline_ms"], facts["analysis_hash"]
    deadline_matches = type(deadline) is int and deadline == int(binding.deadline_ms)
    hash_matches = type(analysis_hash) is str and analysis_hash == binding.analysis_hash
    agreements = (
        facts["artifact"] == ARTIFACT,
        facts["verdict"] == ("PASS" if reason == "OK" else "FAIL"),
        facts["bound_credential_id"] == binding.credential_id,
        facts["bound_client_request_id"] == binding.client_request_id,
        facts["bound_run_id"] == binding.run_id,
        type(facts["schema_ok"]) is bool,
        (facts["schema_ok"] is False) == (reason == "SCHEMA_DRIFT"),
        deadline is None or type(deadline) is int,
        analysis_hash is None or type(analysis_hash) is str,
        facts["deadline_ms_matches"] is deadline_matches,
        facts["analysis_hash_matches"] is hash_matches,
        _count(facts["predictions_rows_for_run_id"]),
        _count(facts["credential_ledger_rows_since_activation"]),
        # A missing or ambiguous row has no facts.
        reason not in ("NO_ROW", "AMBIGUOUS") or (deadline is None and analysis_hash is None),
        # A reason names the first failing check: its own check failed, every earlier one passed.
        reason != "DEADLINE_MISMATCH" or not deadline_matches,
        reason != "ANALYSIS_HASH_MISMATCH" or not hash_matches,
        position <= REASONS.index("DEADLINE_MISMATCH") or deadline_matches,
        position <= REASONS.index("ANALYSIS_HASH_MISMATCH") or hash_matches,
    )
    return all(agreements)


def audit(
    binding: Binding, environ: Mapping[str, str], *, connect: Callable[..., Any] | None = None
) -> tuple[dict[str, Any], int]:
    """The output object and the exit code. Refusals are reported, never raised."""

    base = {
        "artifact": ARTIFACT,
        "sql_sha256": SQL_SHA256,
        "bound_credential_id": binding.credential_id,
        "bound_client_request_id": binding.client_request_id,
        "bound_run_id": binding.run_id,
        "bound_qualification_activation_utc": binding.activation_utc,
    }
    try:
        return _audit(binding, environ, base, connect)
    except Exception as exc:  # noqa: BLE001 - never a traceback that could carry a value
        return {
            **base,
            "verdict": "FAIL",
            "reason": "INTERNAL_ERROR",
            "error_class": type(exc).__name__,
        }, EXIT_DATABASE


def _audit(
    binding: Binding,
    environ: Mapping[str, str],
    base: dict[str, Any],
    connect: Callable[..., Any] | None,
) -> tuple[dict[str, Any], int]:
    try:
        sql, artifact_sha256 = verified_package()
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
    output = {
        **base,
        **facts,
        "artifact_sha256": artifact_sha256,
        "transaction_read_only": True,
        "row_security_off": True,
    }
    if not cross_check(facts, binding):
        output.update(verdict="FAIL", reason="RUNNER_DISAGREES")
        return output, EXIT_FAIL
    return output, EXIT_PASS if facts["verdict"] == "PASS" else EXIT_FAIL


class _Parser(argparse.ArgumentParser):
    """argparse that never echoes an argument: a pasted credential must not reach a terminal."""

    def error(self, message: str) -> None:  # type: ignore[override]
        del message
        raise Refusal("INPUT_REFUSED:arguments", EXIT_INPUT)


class _Once(argparse.Action):
    """Each input exactly once: a repeated flag is refused, never silently overridden."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        if getattr(namespace, self.dest) is not None:
            parser.error("repeated")
        setattr(namespace, self.dest, values)


def render(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    connect: Callable[..., Any] | None = None,
    stdout: TextIO | None = None,
) -> int:
    parser = _Parser(prog="a4_card04_companion", add_help=False, allow_abbrev=False)  # -h: not 0
    for name in (
        "credential-id",
        "client-request-id",
        "run-id",
        "deadline-ms",
        "analysis-hash",
        "qualification-activation-utc",
    ):
        parser.add_argument(f"--{name}", required=True, action=_Once)
    out = stdout or sys.stdout
    try:
        args = parser.parse_args(argv)
        binding = validate(
            args.credential_id,
            args.client_request_id,
            args.run_id,
            args.deadline_ms,
            args.analysis_hash,
            args.qualification_activation_utc,
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
