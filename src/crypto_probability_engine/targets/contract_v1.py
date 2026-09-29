"""Target contract v1 (``tc-v1``): today's prediction target, made explicit and checkable per row.

Pure and unwired. It imports only the standard library and ``config.defaults``. No product module
imports it, and nothing is stamped or persisted yet (owner decision D1: dedicated provenance
columns, later). See ``docs/TARGET_CONTRACT_V1.md``.

The estimand is unchanged. For a live row built by ``api/analysis_service.py::_prediction_row``:
- the reference is the last closed candle: ``reference_close_utc`` and ``reference_price``;
- the horizon is CLOSE-ANCHORED: ``horizon_end_utc = reference_close_utc + horizon_bars * bar``;
- the band is ``decision_band_frac``, the round-trip cost as a fraction of the reference price;
- the label compares the terminal close with +/- band: UP, DOWN or TIMEOUT;
- resolution uses the bar whose close equals ``horizon_end_utc`` exactly, on the same venue.

``predicted_at_utc`` is ``snapshot.as_of_utc``. It is locked by the snapshot builders and the
section 5A embargo, so tc-v1 reads it as ``source_as_of`` and never redefines, renames or
overwrites it. quant_v2's ``computed_at_utc`` also means as_of, so the two new app-clock times get
new names: ``core_computed_at_utc`` (the quant core finished) and ``issued_at_utc`` (the response
was produced).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from typing import Any

from crypto_probability_engine.config.defaults import TIMEFRAME_SECONDS

TARGET_VERSION_V1 = "tc-v1"
# Provider name -> venue label. Equal to adapters/provider_selection.DATA_SOURCE_BY_PROVIDER and the
# inverse of scripts/resolve_outcomes.EXACT_SOURCE_PROVIDERS; only the tests import those modules.
VENUE_LABELS: Mapping[str, str] = MappingProxyType(
    {"binance": "BINANCE_PUBLIC", "okx": "OKX_PUBLIC"}
)
# Fixed-duration bars only. 1M is an approximate 30-day bar with no exact grid, so it fails closed.
TC_V1_TIMEFRAMES = frozenset({"15m", "1H", "4H", "1D", "1W"})
TC_V1_MAX_HORIZON_BARS = 96  # the resolver's bounded window
STAMP_FIELDS = ("target_version", "reference_venue", "core_computed_at_utc", "issued_at_utc")
BAND_UNITS = "FRACTION_OF_REFERENCE_PRICE"
LABEL_RULE = "TERMINAL_CLOSE_VS_BAND_3STATE"
RESOLUTION_RULE = "EXACT_TERMINAL_BAR_SAME_VENUE"

CLASS_TC_V1 = "tc-v1"
CLASS_TC_V1_INVALID = "tc-v1-invalid"
CLASS_V0_LEGACY = "v0-legacy"

CROSS_PROVIDER_SOURCE = "CROSS_PROVIDER"
COHERENT_STATE = "COHERENT"
SHADOW_EVIDENCE_ORIGIN = "SCHEDULED_SHADOW_EVIDENCE"
# Every section 5A OOS identity starts with this, including arm ids oosb-<32 hex>:<tf>:<ARM>.
OOS_ID_PREFIX = "oosb-"
PROBABILITY_FIELDS = ("p_up_frac", "p_down_frac", "p_timeout_frac")
PROBABILITY_SUM_TOLERANCE = 1e-9

# Violation codes returned by validate_v1. An empty result means a valid tc-v1 row.
ROW_NOT_MAPPING = "ROW_NOT_MAPPING"
ROW_UNREADABLE = "ROW_UNREADABLE"
TARGET_VERSION_NOT_TC_V1 = "TARGET_VERSION_NOT_TC_V1"
OOS_ARM_ROW = "OOS_ARM_ROW"
SHADOW_EVIDENCE_ROW = "SCHEDULED_SHADOW_EVIDENCE_ROW"
NOT_LIVE_DATA = "NOT_LIVE_DATA"
NORMALIZED_SYMBOL_INVALID = "NORMALIZED_SYMBOL_INVALID"
REFERENCE_PRICE_INVALID = "REFERENCE_PRICE_INVALID"
BAND_INVALID = "BAND_INVALID"
TIMESTAMP_INVALID: Mapping[str, str] = MappingProxyType(
    {
        "reference_close_utc": "REFERENCE_CLOSE_UTC_INVALID",
        "predicted_at_utc": "PREDICTED_AT_UTC_INVALID",
        "core_computed_at_utc": "CORE_COMPUTED_AT_UTC_INVALID",
        "issued_at_utc": "ISSUED_AT_UTC_INVALID",
        "horizon_end_utc": "HORIZON_END_UTC_INVALID",
    }
)
I1_REFERENCE_CLOSE_AFTER_PREDICTED_AT = "I1_REFERENCE_CLOSE_AFTER_PREDICTED_AT"
I1_PREDICTED_AT_AFTER_CORE_COMPUTED_AT = "I1_PREDICTED_AT_AFTER_CORE_COMPUTED_AT"
I1_CORE_COMPUTED_AT_AFTER_ISSUED_AT = "I1_CORE_COMPUTED_AT_AFTER_ISSUED_AT"
I2_HORIZON_END_MISMATCH = "I2_HORIZON_END_MISMATCH"
I3_NO_REMAINING_DURATION = "I3_NO_REMAINING_DURATION"
I5_PROBABILITY_INVALID = "I5_PROBABILITY_INVALID"
I5_PROBABILITY_SUM = "I5_PROBABILITY_SUM"
I8_REFERENCE_VENUE_INVALID = "I8_REFERENCE_VENUE_INVALID"
I8_DATA_SOURCE_VENUE_MISMATCH = "I8_DATA_SOURCE_VENUE_MISMATCH"
I8_CROSS_PROVIDER_NOT_COHERENT = "I8_CROSS_PROVIDER_NOT_COHERENT"
I8_DATA_SOURCE_UNSUPPORTED = "I8_DATA_SOURCE_UNSUPPORTED"
I9_TIMEFRAME_UNSUPPORTED = "I9_TIMEFRAME_UNSUPPORTED"
I9_HORIZON_BARS_OUT_OF_RANGE = "I9_HORIZON_BARS_OUT_OF_RANGE"

_VENUES = frozenset(VENUE_LABELS.values())


@dataclass(frozen=True)
class TargetContractV1:
    """What a tc-v1 probability forecasts. The last three fields are constants of the version."""

    target_version: str
    normalized_symbol: str
    timeframe: str
    reference_venue: str
    reference_close_utc: datetime
    reference_price: float
    horizon_bars: int
    horizon_end_utc: datetime
    band_frac: float
    band_units: str = BAND_UNITS
    label_rule: str = LABEL_RULE
    resolution_rule: str = RESOLUTION_RULE

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> TargetContractV1 | None:
        """Return the contract of a valid tc-v1 row, or None when ``validate_v1`` reports any."""

        if validate_v1(row):
            return None
        try:
            return cls(
                target_version=TARGET_VERSION_V1,
                normalized_symbol=row["normalized_symbol"],
                timeframe=row["timeframe"],
                reference_venue=row["reference_venue"],
                reference_close_utc=_required_utc(row, "reference_close_utc"),
                reference_price=float(row["reference_price"]),
                horizon_bars=row["horizon_bars"],
                horizon_end_utc=_required_utc(row, "horizon_end_utc"),
                band_frac=float(row["decision_band_frac"]),
            )
        except Exception:
            return None


@dataclass(frozen=True)
class ForecastTimestampsV1:
    """The clocks of one forecast. All are app-clock instants; the DB commit time is not one."""

    source_as_of_utc: datetime  # predicted_at_utc (snapshot.as_of_utc)
    candle_cutoff_utc: datetime  # reference_close_utc: the last closed candle used
    overall_cutoff_utc: datetime  # predicted_at_utc: book, band and liquidity are read at as_of
    core_computed_at_utc: datetime  # the quant core finished
    issued_at_utc: datetime  # the response was produced
    remaining_duration_at_issue: timedelta  # horizon_end_utc - issued_at_utc

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> ForecastTimestampsV1 | None:
        """Return the timestamps of a valid tc-v1 row, or None when ``validate_v1`` reports any."""

        if validate_v1(row):
            return None
        try:
            source_as_of = _required_utc(row, "predicted_at_utc")
            issued = _required_utc(row, "issued_at_utc")
            return cls(
                source_as_of_utc=source_as_of,
                candle_cutoff_utc=_required_utc(row, "reference_close_utc"),
                overall_cutoff_utc=source_as_of,
                core_computed_at_utc=_required_utc(row, "core_computed_at_utc"),
                issued_at_utc=issued,
                remaining_duration_at_issue=_required_utc(row, "horizon_end_utc") - issued,
            )
        except Exception:
            return None


def stamp_v1(
    row: Mapping[str, Any],
    *,
    snapshot_provider: str,
    core_computed_at: datetime | str,
    issued_at: datetime | str,
) -> dict[str, Any]:
    """Return a new dict: ``row`` plus the four STAMP_FIELDS, only if the result is valid tc-v1.

    Otherwise return an unchanged shallow copy of ``row`` (an empty dict if ``row`` is not a
    mapping). ``reference_venue`` is the venue label of ``snapshot_provider``, i.e.
    ``snapshot.provider``, the venue whose candles gave the reference close; an unknown provider
    is never guessed. The two times are app-clock instants (a naive datetime is UTC), written as
    ISO-8601 UTC ``Z`` strings in the writer's format.

    It never raises, never mutates ``row`` and never changes an existing key: ``predicted_at_utc``
    is untouched, and a row that already has any stamp key, even with a None value, is returned
    unchanged.
    """

    try:
        if not isinstance(row, Mapping):
            return {}
        unchanged = dict(row)
    except Exception:
        return {}
    try:
        if any(field in unchanged for field in STAMP_FIELDS):
            return unchanged
        if not isinstance(snapshot_provider, str) or snapshot_provider not in VENUE_LABELS:
            return unchanged
        stamped = dict(unchanged)
        stamped["target_version"] = TARGET_VERSION_V1
        stamped["reference_venue"] = VENUE_LABELS[snapshot_provider]
        stamped["core_computed_at_utc"] = _iso_utc(core_computed_at)
        stamped["issued_at_utc"] = _iso_utc(issued_at)
        return unchanged if validate_v1(stamped) else stamped
    except Exception:
        return unchanged


def validate_v1(row: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the tc-v1 violation codes of ``row``; an empty tuple means a valid tc-v1 row.

    Row-checkable invariants (docs/TARGET_CONTRACT_V1.md):
    - I1 chronology, app clock only: reference_close_utc <= predicted_at_utc <=
      core_computed_at_utc <= issued_at_utc. The DB-clock commit time is never checked.
    - I2 horizon_end_utc == reference_close_utc + horizon_bars * bar, exactly.
    - I3 horizon_end_utc > issued_at_utc: a positive remaining duration at issue.
    - I5 each probability is in [0, 1] and the three sum to 1 within 1e-9.
    - I8 reference_venue is a venue label; a venue data_source equals it; CROSS_PROVIDER requires
      cross_provider_state COHERENT; any other data_source fails.
    - I9 timeframe is in TC_V1_TIMEFRAMES (1M fails closed) and 1 <= horizon_bars <= 96.
    Also: target_version is tc-v1; the row is not in the section 5A OOS population (no ``oosb-``
    identity, origin not SCHEDULED_SHADOW_EVIDENCE); normalized_symbol is non-empty;
    reference_price is finite and > 0; the band is finite and >= 0; is_live_data is True.
    I4 (resolution rule), I6 (write-once) and I7 (NULL = v0) are not row-checkable.

    It never raises.
    """

    if not isinstance(row, Mapping):
        return (ROW_NOT_MAPPING,)
    try:
        return tuple(_violations(row))
    except Exception:
        return (ROW_UNREADABLE,)


def classify_row(row: Mapping[str, Any]) -> str:
    """Return ``tc-v1``, ``tc-v1-invalid`` or ``v0-legacy``. It never raises.

    A row is ``v0-legacy`` only when every stamp field is absent or None (NULL = v0). A row that
    carries any stamp but fails ``validate_v1``, including a partial stamp or another
    target_version, is ``tc-v1-invalid``, as is anything that is not a mapping.
    """

    if not isinstance(row, Mapping):
        return CLASS_TC_V1_INVALID
    try:
        if all(row.get(field) is None for field in STAMP_FIELDS):
            return CLASS_V0_LEGACY
        return CLASS_TC_V1_INVALID if validate_v1(row) else CLASS_TC_V1
    except Exception:
        return CLASS_TC_V1_INVALID


def resolution_venue(row: Mapping[str, Any]) -> str | None:
    """Return the venue label an outcome must come from, or None when there is none.

    A valid tc-v1 row resolves on its ``reference_venue``. An unstamped (v0) row resolves on its
    ``data_source`` only when that is exactly a venue label, so legacy CROSS_PROVIDER rows, which
    never recorded the reference venue, stay unresolvable. A stamped but invalid row has none.
    It never raises.
    """

    try:
        kind = classify_row(row)
        if kind == CLASS_TC_V1:
            return _text(row.get("reference_venue"))
        if kind == CLASS_V0_LEGACY:
            source = _text(row.get("data_source"))
            return source if source in _VENUES else None
    except Exception:
        return None
    return None


def _violations(row: Mapping[str, Any]) -> list[str]:
    found: list[str] = []
    if _text(row.get("target_version")) != TARGET_VERSION_V1:
        found.append(TARGET_VERSION_NOT_TC_V1)
    if any(
        (_text(row.get(key)) or "").startswith(OOS_ID_PREFIX) for key in ("prediction_id", "run_id")
    ):
        found.append(OOS_ARM_ROW)
    if _text(row.get("prediction_origin")) == SHADOW_EVIDENCE_ORIGIN:
        found.append(SHADOW_EVIDENCE_ROW)
    if row.get("is_live_data") is not True:
        found.append(NOT_LIVE_DATA)
    if not (_text(row.get("normalized_symbol")) or "").strip():
        found.append(NORMALIZED_SYMBOL_INVALID)
    price = _finite_number(row.get("reference_price"))
    if price is None or price <= 0:
        found.append(REFERENCE_PRICE_INVALID)
    band = _finite_number(row.get("decision_band_frac"))
    if band is None or band < 0:
        found.append(BAND_INVALID)

    timeframe = _text(row.get("timeframe"))
    if timeframe not in TC_V1_TIMEFRAMES:
        found.append(I9_TIMEFRAME_UNSUPPORTED)
        timeframe = None
    bars = _strict_int(row.get("horizon_bars"))
    if bars is None or not 1 <= bars <= TC_V1_MAX_HORIZON_BARS:
        found.append(I9_HORIZON_BARS_OUT_OF_RANGE)
        bars = None

    times: dict[str, datetime | None] = {}
    for field, code in TIMESTAMP_INVALID.items():
        times[field] = _parse_utc(row.get(field))
        if times[field] is None:
            found.append(code)
    reference_close = times["reference_close_utc"]
    source_as_of = times["predicted_at_utc"]
    core_computed = times["core_computed_at_utc"]
    issued = times["issued_at_utc"]
    horizon_end = times["horizon_end_utc"]

    for earlier, later, code in (
        (reference_close, source_as_of, I1_REFERENCE_CLOSE_AFTER_PREDICTED_AT),
        (source_as_of, core_computed, I1_PREDICTED_AT_AFTER_CORE_COMPUTED_AT),
        (core_computed, issued, I1_CORE_COMPUTED_AT_AFTER_ISSUED_AT),
    ):
        if earlier is not None and later is not None and earlier > later:
            found.append(code)
    if (
        timeframe is not None
        and bars is not None
        and reference_close is not None
        and horizon_end is not None
        and horizon_end != _horizon_end(reference_close, bars, timeframe)
    ):
        found.append(I2_HORIZON_END_MISMATCH)
    if horizon_end is not None and issued is not None and horizon_end <= issued:
        found.append(I3_NO_REMAINING_DURATION)

    values = [_finite_number(row.get(key)) for key in PROBABILITY_FIELDS]
    probabilities = [value for value in values if value is not None and 0 <= value <= 1]
    if len(probabilities) != len(values):
        found.append(I5_PROBABILITY_INVALID)
    elif abs(math.fsum(float(value) for value in probabilities) - 1.0) > PROBABILITY_SUM_TOLERANCE:
        found.append(I5_PROBABILITY_SUM)

    venue = _text(row.get("reference_venue"))
    if venue not in _VENUES:
        found.append(I8_REFERENCE_VENUE_INVALID)
    source = _text(row.get("data_source"))
    if source in _VENUES:
        if source != venue:
            found.append(I8_DATA_SOURCE_VENUE_MISMATCH)
    elif source == CROSS_PROVIDER_SOURCE:
        if _text(row.get("cross_provider_state")) != COHERENT_STATE:
            found.append(I8_CROSS_PROVIDER_NOT_COHERENT)
    else:
        found.append(I8_DATA_SOURCE_UNSUPPORTED)
    return found


def _horizon_end(reference_close: datetime, bars: int, timeframe: str) -> datetime | None:
    try:
        return reference_close + timedelta(seconds=bars * TIMEFRAME_SECONDS[timeframe])
    except (KeyError, OverflowError):
        return None


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _strict_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _finite_number(value: object) -> int | float | Decimal | None:
    """Return a finite int, float or Decimal unchanged, else None (bool and strings are refused).

    The value keeps its own type, so bounds are checked exactly: converting a Decimal to float first
    would round 1.00000000000000000001 down to 1.0 and -1E-400 up to -0.0 and let them through.
    """

    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def _parse_utc(value: object) -> datetime | None:
    """Parse a datetime or an ISO-8601 string (Z or offset); naive means UTC. None if invalid."""

    try:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str) and value.strip():
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        else:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except (OverflowError, TypeError, ValueError):
        return None


def _required_utc(row: Mapping[str, Any], field: str) -> datetime:
    parsed = _parse_utc(row.get(field))
    if parsed is None:
        raise ValueError(f"{field} is not a timestamp")
    return parsed


def _iso_utc(value: datetime | str) -> str:
    """The writer's format (api/analysis_service.py::_iso_utc): UTC isoformat with a Z suffix."""

    parsed = _parse_utc(value)
    if parsed is None:
        raise ValueError("not a timestamp")
    return parsed.isoformat().replace("+00:00", "Z")
