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
MAX_QUOTA_PER_DAY = 2000
MAX_CONCURRENT_ANALYSES = 1
DEADLINE_MS_MIN = 5_000
DEADLINE_MS_MAX = 60_000
REQUEST_BODY_MAX_BYTES = 1_024
LEDGER_RETENTION_DAYS = 90

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
