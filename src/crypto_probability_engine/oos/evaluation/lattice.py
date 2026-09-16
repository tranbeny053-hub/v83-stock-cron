"""Integer-second Section 5A window-lattice calculations."""

from __future__ import annotations

from datetime import UTC, datetime

EVALUATION_HORIZON_SECONDS = {
    "15m": 5_400,
    "1H": 21_600,
    "4H": 86_400,
}
COARSENINGS = frozenset({1, 2, 4})


def window_count(timeframe: str, c: int, t0: datetime, t_close: datetime) -> int:
    """Return ``k_c`` before empty-window dropping."""

    horizon_seconds = _lattice_parameters(timeframe, c)[0]
    span_seconds = _whole_seconds_between(t_close, t0)
    period_seconds = (1 + c) * horizon_seconds
    return max(0, (span_seconds - 2 * horizon_seconds) // period_seconds + 1)


def assign_window_index(
    reference_close_utc: datetime,
    timeframe: str,
    c: int,
    t0: datetime,
    t_close: datetime,
) -> int | None:
    """Assign a close to its half-open window, or return ``None`` outside/in a gap."""

    horizon_seconds, period_seconds = _lattice_parameters(timeframe, c)
    delta_seconds = _whole_seconds_between(reference_close_utc, t0)
    if delta_seconds < 0:
        return None

    index, offset_seconds = divmod(delta_seconds, period_seconds)
    if index >= window_count(timeframe, c, t0, t_close):
        return None
    if offset_seconds >= horizon_seconds:
        return None
    return index


def _lattice_parameters(timeframe: str, c: int) -> tuple[int, int]:
    try:
        horizon_seconds = EVALUATION_HORIZON_SECONDS[timeframe]
    except KeyError as exc:
        raise ValueError(f"unsupported timeframe: {timeframe!r}") from exc
    if c not in COARSENINGS:
        raise ValueError(f"unsupported coarsening: {c!r}")
    return horizon_seconds, (1 + c) * horizon_seconds


def _whole_seconds_between(later: datetime, earlier: datetime) -> int:
    for value, name in ((later, "later"), (earlier, "earlier")):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{name} datetime must be timezone-aware")
        if value.microsecond:
            raise ValueError(f"{name} datetime must use whole seconds")
    delta = later.astimezone(UTC) - earlier.astimezone(UTC)
    return delta.days * 86_400 + delta.seconds

