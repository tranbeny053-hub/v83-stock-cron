"""Route-only machine authentication for the automation route.

The credential is presented in exactly one header, ``X-UCPE-Automation-Credential``, as
``ucpea.<credential_id>.<secret>`` where the secret is 43 URL-safe base64 characters (256 bits).
The server stores only ``sha256(secret)`` and compares digests in constant time. The credential
authenticates this route and nothing else: the human routes read only their session cookies, and
this route refuses any request that also carries a human session cookie. Nothing here logs,
returns or stores a presented value.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from crypto_probability_engine.automation.config import CredentialRecord
from crypto_probability_engine.automation.origin import AUTOMATED_RADAR

CREDENTIAL_HEADER = "X-UCPE-Automation-Credential"
TOKEN_PREFIX = "ucpea"
_TOKEN = re.compile(r"^ucpea\.([a-z0-9][a-z0-9-]{2,31})\.([A-Za-z0-9_-]{43})$")
_MAX_PRESENTED_LENGTH = 128
# Compared against when the credential id is unknown, so every refusal does the same work.
_UNKNOWN_DIGEST = hashlib.sha256(b"ucpe-automation-unknown-credential").hexdigest()


class CredentialRefusal(StrEnum):
    MISSING = "MISSING"
    MALFORMED = "MALFORMED"
    UNKNOWN = "UNKNOWN"
    MISMATCH = "MISMATCH"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class MachinePrincipal:
    """An authenticated machine caller. The origin is stamped here, from the credential."""

    credential_id: str
    evidence_origin: str = AUTOMATED_RADAR


def secret_digest(secret: str) -> str:
    """Return the stored form of a secret: the lowercase hex SHA-256 of its ASCII bytes."""

    return hashlib.sha256(secret.encode("ascii")).hexdigest()


def authenticate(
    presented: str | None,
    records: Iterable[CredentialRecord],
    *,
    now: datetime,
) -> MachinePrincipal | CredentialRefusal:
    """Verify one presented credential against the registry. Never raises."""

    if presented is None or presented == "":
        return CredentialRefusal.MISSING
    if not isinstance(presented, str) or len(presented) > _MAX_PRESENTED_LENGTH:
        return CredentialRefusal.MALFORMED
    match = _TOKEN.fullmatch(presented)
    if match is None:
        return CredentialRefusal.MALFORMED
    credential_id, presented_secret = match.group(1), match.group(2)
    record = next((item for item in records if item.credential_id == credential_id), None)
    presented_digest = secret_digest(presented_secret)
    expected = record.secret_sha256 if record is not None else _UNKNOWN_DIGEST
    matches = hmac.compare_digest(presented_digest, expected)
    if record is None:
        return CredentialRefusal.UNKNOWN
    if not matches:
        return CredentialRefusal.MISMATCH
    if record.status != "ACTIVE":
        return CredentialRefusal.REVOKED
    if record.not_after_utc is not None and now >= record.not_after_utc:
        return CredentialRefusal.EXPIRED
    return MachinePrincipal(credential_id=credential_id)
