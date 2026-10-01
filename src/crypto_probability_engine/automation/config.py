"""Runtime configuration of the automation route, read from the environment on every call.

Fail closed: the route is OFF unless ``UCPE_AUTOMATION_ENABLED`` is exactly ``1`` or ``true``,
and any malformed value makes the configuration unusable (``problems`` is non-empty), which the
service answers with 503 ``NOT_CONFIGURED``. No credential, and no credential digest, lives in the
environment: credentials live in the database registry (``automation.credentials``), so rotating
or revoking one never needs a restart. This module is new and self-contained: it does not touch
the pinned ``config`` package.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

ENV_ENABLED = "UCPE_AUTOMATION_ENABLED"
ENV_QUOTA_PER_5MIN = "UCPE_AUTOMATION_QUOTA_PER_5MIN"
ENV_QUOTA_PER_DAY = "UCPE_AUTOMATION_QUOTA_PER_DAY"

DEFAULT_QUOTA_PER_5MIN = 6
MAX_QUOTA_PER_5MIN = 60
DEFAULT_QUOTA_PER_DAY = 120
# The daily quota is bounded by the ledger capacity contract below. G6 stays provisional; raising
# this needs measured production resource evidence and a reviewed change of the contract.
MAX_QUOTA_PER_DAY = 120
MAX_CONCURRENT_ANALYSES = 1
DEADLINE_MS_MIN = 5_000
DEADLINE_MS_MAX = 60_000
REQUEST_BODY_MAX_BYTES = 1_024

# THE LEDGER CAPACITY CONTRACT (docs/automation/RETENTION_AND_IDEMPOTENCY.md). Storage is bounded,
# and the route itself never deletes a row:
# - every row is kept at least LEDGER_RETENTION_DAYS; only an owner-run purge, of rows older than
#   that, ever removes one;
# - the ledger never takes a new row once it holds LEDGER_ROW_CAP rows: a new request is refused
#   (503) and recorded nowhere, while replays of recorded requests are still served;
# - a credential never records more than LEDGER_ROWS_PER_QUOTA_UNIT x its daily quota rows in any
#   rolling day, refusals included: beyond that, a new request is refused (429) and recorded
#   nowhere, so no client can fill the ledger;
# - no stored response body exceeds LEDGER_MAX_BODY_BYTES (its RFC 8785 JCS bytes).
# At the maximum quota, LEDGER_RETENTION_DAYS of one credential's rows always fit under the cap.
LEDGER_RETENTION_DAYS = 90
LEDGER_ROW_CAP = 25_000
LEDGER_ROWS_PER_QUOTA_UNIT = 2
LEDGER_MAX_BODY_BYTES = 8_192

_TRUE = frozenset({"1", "true"})
_FALSE = frozenset({"", "0", "false"})


@dataclass(frozen=True)
class AutomationConfig:
    enabled: bool
    quota_per_5min: int
    quota_per_day: int
    problems: tuple[str, ...]

    @property
    def usable(self) -> bool:
        return self.enabled and not self.problems


def load_config(environ: Mapping[str, str]) -> AutomationConfig:
    """Parse the automation configuration; never raises."""

    problems: list[str] = []
    enabled_text = str(environ.get(ENV_ENABLED, "")).strip().lower()
    if enabled_text in _TRUE:
        enabled = True
    else:
        enabled = False
        if enabled_text not in _FALSE:
            problems.append(f"{ENV_ENABLED} must be 1/true or 0/false")
    quota_5min = _bounded_int(
        environ, ENV_QUOTA_PER_5MIN, DEFAULT_QUOTA_PER_5MIN, MAX_QUOTA_PER_5MIN, problems
    )
    quota_day = _bounded_int(
        environ, ENV_QUOTA_PER_DAY, DEFAULT_QUOTA_PER_DAY, MAX_QUOTA_PER_DAY, problems
    )
    if quota_5min > quota_day:
        problems.append("the 5-minute quota cannot exceed the daily quota")
    return AutomationConfig(
        enabled=enabled,
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
