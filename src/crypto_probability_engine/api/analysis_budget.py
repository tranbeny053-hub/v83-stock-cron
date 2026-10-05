"""The observe-only analysis budget (governing plan §13; owner ruling DP-C, 2026-10-05).

It counts this process's requests to the two analysis routes over the last minute and the last
hour, and says whether a provisional threshold would have refused one. It refuses nobody, changes no
response or payload, and records no user, session, operator, client or request identity: two counts
and a yes/no travel on that request's own http_request event, nothing else. The thresholds are
provisional, for the yes/no only; the owner sets real ones from these counts (P7-1).

What it counts is arrivals: every POST to either route counts once, before any check, so a request
later refused (401, 403, 413, 422) counts too, and a batch of several analyses counts as one.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

ANALYSIS_ROUTES = frozenset({"/v1/analyze", "/v1/analyze_batch"})
# Provisional, for the would-refuse flag only: nothing is ever refused.
PROVISIONAL_PER_MINUTE = 30
PROVISIONAL_PER_HOUR = 600


class AnalysisBudgetObserver:
    """Counts in one-second and one-minute buckets, so memory stays bounded at any request rate."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._seconds: dict[int, int] = {}
        self._minutes: dict[int, int] = {}

    def observe(self) -> dict[str, object]:
        """Count one arrival; return the counts it saw, itself included, and the yes/no."""

        second = int(self._clock())
        minute = second // 60
        with self._lock:
            self._seconds[second] = self._seconds.get(second, 0) + 1
            self._minutes[minute] = self._minutes.get(minute, 0) + 1
            for bucket in [bucket for bucket in self._seconds if bucket <= second - 60]:
                del self._seconds[bucket]
            for bucket in [bucket for bucket in self._minutes if bucket <= minute - 60]:
                del self._minutes[bucket]
            per_minute = sum(self._seconds.values())
            per_hour = sum(self._minutes.values())
        return {
            "budget_count_60s": per_minute,
            "budget_count_3600s": per_hour,
            "budget_would_refuse": per_minute > PROVISIONAL_PER_MINUTE
            or per_hour > PROVISIONAL_PER_HOUR,
        }


# The process's one observer (the budget is per process, as the provider rate limit is).
ANALYSIS_BUDGET = AnalysisBudgetObserver()
