"""Runtime configuration of the automation route, read from the environment on every call.

Fail closed: the route is OFF unless ``UCPE_AUTOMATION_ENABLED`` is exactly ``1`` or ``true``,
and any malformed value makes the configuration unusable (``problems`` is non-empty), which the
service answers with 503 ``NOT_CONFIGURED``. The environment holds only credential DIGESTS,
never a credential value. This module is new and self-contained: it does not touch the pinned
``config`` package.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

ENV_ENABLED = "UCPE_AUTOMATION_ENABLED"
ENV_CREDENTIALS = "UCPE_AUTOMATION_CREDENTIALS"
ENV_QUOTA_PER_5MIN = "UCPE_AUTOMATION_QUOTA_PER_5MIN"
ENV_QUOTA_PER_DAY = "UCPE_AUTOMATION_QUOTA_PER_DAY"

DEFAULT_QUOTA_PER_5MIN = 6
MAX_QUOTA_PER_5MIN = 60
DEFAULT_QUOTA_PER_DAY = 120
MAX_QUOTA_PER_DAY = 2000
MAX_CONCURRENT_ANALYSES = 1
DEADLINE_MS_MIN = 5_000
DEADLINE_MS_MAX = 60_000
REQUEST_BODY_MAX_BYTES = 1_024
LEDGER_RETENTION_DAYS = 90

CREDENTIAL_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,31}$")
SECRET_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
CREDENTIAL_STATUSES = frozenset({"ACTIVE", "REVOKED"})
_CREDENTIAL_KEYS = frozenset({"credential_id", "secret_sha256", "status"})
_OPTIONAL_CREDENTIAL_KEYS = frozenset({"not_after_utc"})
_TRUE = frozenset({"1", "true"})
_FALSE = frozenset({"", "0", "false"})


@dataclass(frozen=True)
class CredentialRecord:
    """One machine credential, known only by its id and the SHA-256 digest of its secret."""

    credential_id: str
    secret_sha256: str
    status: str
    not_after_utc: datetime | None = None


@dataclass(frozen=True)
class AutomationConfig:
    enabled: bool
    credentials: tuple[CredentialRecord, ...]
    quota_per_5min: int
    quota_per_day: int
    problems: tuple[str, ...]

    @property
    def usable(self) -> bool:
        return self.enabled and not self.problems


def load_config(environ: Mapping[str, str]) -> AutomationConfig:
    """Parse the automation configuration; never raises, never returns a secret."""

    problems: list[str] = []
    enabled_text = str(environ.get(ENV_ENABLED, "")).strip().lower()
    if enabled_text in _TRUE:
        enabled = True
    else:
        enabled = False
        if enabled_text not in _FALSE:
            problems.append(f"{ENV_ENABLED} must be 1/true or 0/false")
    credentials = _credentials(environ.get(ENV_CREDENTIALS), problems)
    quota_5min = _bounded_int(
        environ, ENV_QUOTA_PER_5MIN, DEFAULT_QUOTA_PER_5MIN, MAX_QUOTA_PER_5MIN, problems
    )
    quota_day = _bounded_int(
        environ, ENV_QUOTA_PER_DAY, DEFAULT_QUOTA_PER_DAY, MAX_QUOTA_PER_DAY, problems
    )
    if quota_5min > quota_day:
        problems.append("the 5-minute quota cannot exceed the daily quota")
    if enabled and not any(record.status == "ACTIVE" for record in credentials):
        problems.append("no ACTIVE credential is configured")
    return AutomationConfig(
        enabled=enabled,
        credentials=credentials,
        quota_per_5min=quota_5min,
        quota_per_day=quota_day,
        problems=tuple(problems),
    )


def _bounded_int(
    environ: Mapping[str, str], name: str, default: int, maximum: int, problems: list[str]
) -> int:
    raw = environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    text = str(raw).strip()
    if not text.isdigit():
        problems.append(f"{name} must be an integer from 1 to {maximum}")
        return default
    value = int(text)
    if not 1 <= value <= maximum:
        problems.append(f"{name} must be an integer from 1 to {maximum}")
        return default
    return value


def _credentials(raw: str | None, problems: list[str]) -> tuple[CredentialRecord, ...]:
    if raw is None or not str(raw).strip():
        return ()
    try:
        items = json.loads(raw, parse_constant=_refuse_constant)
    except (ValueError, TypeError):
        problems.append(f"{ENV_CREDENTIALS} is not valid JSON")
        return ()
    if not isinstance(items, list):
        problems.append(f"{ENV_CREDENTIALS} must be a JSON array")
        return ()
    records: list[CredentialRecord] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        record = _credential(item, index, problems)
        if record is None:
            continue
        if record.credential_id in seen:
            problems.append(f"credential {index}: duplicate credential_id")
            continue
        seen.add(record.credential_id)
        records.append(record)
    return tuple(records)


def _credential(item: object, index: int, problems: list[str]) -> CredentialRecord | None:
    if not isinstance(item, dict):
        problems.append(f"credential {index}: must be an object")
        return None
    keys = set(item)
    if not _CREDENTIAL_KEYS <= keys or keys - _CREDENTIAL_KEYS - _OPTIONAL_CREDENTIAL_KEYS:
        problems.append(f"credential {index}: unexpected or missing keys")
        return None
    credential_id = item["credential_id"]
    digest = item["secret_sha256"]
    status = item["status"]
    if not isinstance(credential_id, str) or not CREDENTIAL_ID_PATTERN.fullmatch(credential_id):
        problems.append(f"credential {index}: invalid credential_id")
        return None
    if not isinstance(digest, str) or not SECRET_DIGEST_PATTERN.fullmatch(digest):
        problems.append(f"credential {index}: secret_sha256 must be 64 lowercase hex characters")
        return None
    if status not in CREDENTIAL_STATUSES:
        problems.append(f"credential {index}: status must be ACTIVE or REVOKED")
        return None
    not_after = None
    if "not_after_utc" in item:
        not_after = _utc_instant(item["not_after_utc"])
        if not_after is None:
            problems.append(f"credential {index}: not_after_utc must be an ISO-8601 UTC instant")
            return None
    return CredentialRecord(credential_id, digest, status, not_after)


def _utc_instant(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None
    return parsed.astimezone(UTC)


def _refuse_constant(name: str) -> object:
    raise ValueError(f"non-finite JSON constant {name}")
