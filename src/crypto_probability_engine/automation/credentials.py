"""Route-only machine authentication, backed by a credential registry in the database.

The credential is presented in exactly one header, ``X-UCPE-Automation-Credential``, as
``ucpea.<credential_id>.<value>`` where the value is 43 URL-safe base64 characters (256 bits).
UCPE never issues or stores a value: the registry (``public.automation_credential``, migration
0013) holds only ``sha256(value)``, and the presented value is hashed in memory and compared in
constant time. The credential authenticates this route and nothing else: the human routes read only
their session cookies, and this route refuses any request that also carries a human session cookie.

ROTATION WITHOUT DOWNTIME, REVOCATION ON THE NEXT REQUEST. The registry is read on every request,
with no cache, so a registry change takes effect at the next request and never needs a restart:
- rotate: insert the new ACTIVE digest, move the consumer to the new token, then revoke the old one;
  both are valid in between, so no request is refused;
- revoke: set the record REVOKED (with its revocation time); the next request presenting it is
  refused.
A registry that cannot be read, or holds a malformed record, authenticates nothing: the call fails
closed (503), never falls back to anything else.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import re
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from crypto_probability_engine.automation.origin import AUTOMATED_RADAR

CREDENTIAL_HEADER = "X-UCPE-Automation-Credential"
TOKEN_PREFIX = "ucpea"
CREDENTIAL_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,31}$")
SECRET_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
CREDENTIAL_STATUSES = frozenset({"ACTIVE", "REVOKED"})
REGISTRY_TIMEOUT_SECONDS = 2.0
# Registry reads in flight at once, process-wide. A well-formed token reaches the database before it
# is authenticated, so this bounds what an unauthenticated flood can take from the shared database.
MAX_CONCURRENT_REGISTRY_LOOKUPS = 2
_TOKEN = re.compile(r"^ucpea\.([a-z0-9][a-z0-9-]{2,31})\.([A-Za-z0-9_-]{43})$")
_MAX_PRESENTED_LENGTH = 128
# Compared against when the id is unknown, so every well-formed refusal does the same work.
_UNKNOWN_DIGEST = hashlib.sha256(b"ucpe-automation-unknown-credential").hexdigest()


class CredentialRefusal(StrEnum):
    MISSING = "MISSING"
    MALFORMED = "MALFORMED"
    UNKNOWN = "UNKNOWN"
    MISMATCH = "MISMATCH"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class RegistryUnavailable(Exception):
    """The registry cannot be read or holds a malformed record: nothing is authenticated."""


@dataclass(frozen=True)
class CredentialRecord:
    """One machine credential, known only by its id and the SHA-256 digest of its value."""

    credential_id: str
    secret_sha256: str
    status: str
    not_after_utc: datetime | None = None


@dataclass(frozen=True)
class MachinePrincipal:
    """An authenticated machine caller. The origin is stamped here, from the credential."""

    credential_id: str
    evidence_origin: str = AUTOMATED_RADAR


class CredentialRegistry(Protocol):
    def lookup(self, credential_id: str) -> CredentialRecord | None:
        """The record for this id, or None; raises RegistryUnavailable."""


def secret_digest(value: str) -> str:
    """The stored form of a credential value: the lowercase hex SHA-256 of its ASCII bytes."""

    return hashlib.sha256(value.encode("ascii")).hexdigest()


def validated_record(
    credential_id: Any, digest: Any, status: Any, not_after_utc: Any
) -> CredentialRecord:
    """A registry row as a record, or RegistryUnavailable if any field is out of shape."""

    if (
        not isinstance(credential_id, str)
        or not CREDENTIAL_ID_PATTERN.fullmatch(credential_id)
        or not isinstance(digest, str)
        or not SECRET_DIGEST_PATTERN.fullmatch(digest)
        or not isinstance(status, str)
        or status not in CREDENTIAL_STATUSES
        or not (
            not_after_utc is None
            or (isinstance(not_after_utc, datetime) and not_after_utc.tzinfo is not None)
        )
    ):
        raise RegistryUnavailable("a registry record is malformed")
    return CredentialRecord(credential_id, digest, status, not_after_utc)


def authenticate(
    presented: str | None,
    registry: CredentialRegistry,
    *,
    now: datetime,
) -> MachinePrincipal | CredentialRefusal:
    """Verify one presented credential. Raises only RegistryUnavailable."""

    if presented is None or presented == "":
        return CredentialRefusal.MISSING
    if not isinstance(presented, str) or len(presented) > _MAX_PRESENTED_LENGTH:
        return CredentialRefusal.MALFORMED
    match = _TOKEN.fullmatch(presented)
    if match is None:
        return CredentialRefusal.MALFORMED
    credential_id, presented_value = match.group(1), match.group(2)
    record = registry.lookup(credential_id)
    presented_digest = secret_digest(presented_value)
    expected = record.secret_sha256 if record is not None else _UNKNOWN_DIGEST
    matches = hmac.compare_digest(presented_digest, expected)
    if record is None:
        return CredentialRefusal.UNKNOWN
    if record.credential_id != credential_id or not matches:
        return CredentialRefusal.MISMATCH
    if record.status != "ACTIVE":
        return CredentialRefusal.REVOKED
    if record.not_after_utc is not None and now >= record.not_after_utc:
        return CredentialRefusal.EXPIRED
    return MachinePrincipal(credential_id=credential_id)


class InMemoryCredentialRegistry:
    """A registry for tests and local runs; it is never wired in production."""

    def __init__(self, records: Iterable[CredentialRecord] = ()) -> None:
        self._records = {record.credential_id: record for record in records}
        self.lookups = 0

    def lookup(self, credential_id: str) -> CredentialRecord | None:
        self.lookups += 1
        return self._records.get(credential_id)

    def put(self, record: CredentialRecord) -> None:
        self._records[record.credential_id] = record


_TIMEOUT_SQL = (
    "SELECT set_config('statement_timeout', %(timeout)s, true), "
    "set_config('lock_timeout', %(timeout)s, true)"
)
_LOOKUP_SQL = """
SELECT credential_id, secret_sha256, status, not_after_utc
  FROM public.automation_credential
 WHERE credential_id = %(credential_id)s
"""


class PostgresCredentialRegistry:
    """The production registry: one bounded read per request, its own short-lived connection.

    Beyond ``MAX_CONCURRENT_REGISTRY_LOOKUPS`` reads in flight, a lookup is refused at once (the
    call fails closed with 503) instead of queueing for the database.
    """

    def __init__(
        self,
        database_url: str | None,
        *,
        connect: Callable[..., Any] | None = None,
        max_concurrent_lookups: int = MAX_CONCURRENT_REGISTRY_LOOKUPS,
    ):
        self._database_url = database_url
        self._connect = connect
        self._gate = threading.BoundedSemaphore(max_concurrent_lookups)

    def lookup(self, credential_id: str) -> CredentialRecord | None:
        if not self._database_url:
            raise RegistryUnavailable("no database is configured")
        if not self._gate.acquire(blocking=False):
            raise RegistryUnavailable("too many registry reads in flight")
        try:
            return self._lookup(credential_id)
        finally:
            self._gate.release()

    def _lookup(self, credential_id: str) -> CredentialRecord | None:
        connect = self._connect
        try:
            if connect is None:
                import psycopg

                connect = psycopg.connect
            params = {
                "credential_id": credential_id,
                "timeout": f"{int(REGISTRY_TIMEOUT_SECONDS * 1000)}ms",
            }
            with (
                connect(
                    self._database_url,
                    connect_timeout=max(1, math.ceil(REGISTRY_TIMEOUT_SECONDS)),
                    autocommit=False,
                    prepare_threshold=None,  # as the ledger: safe behind a transaction pooler
                    # A stalled network after connecting is bounded too, not left to the OS.
                    tcp_user_timeout=int(REGISTRY_TIMEOUT_SECONDS * 1000),
                ) as conn,
                conn.cursor() as cur,
            ):
                cur.execute(_TIMEOUT_SQL, params)
                cur.execute(_LOOKUP_SQL, params)
                row = cur.fetchone()
                conn.rollback()  # read only: nothing to keep
        except Exception as exc:
            raise RegistryUnavailable("the credential registry could not be read") from exc
        if row is None:
            return None
        if len(row) != 4:
            raise RegistryUnavailable("a registry record is malformed")
        return validated_record(*row)
