"""Resolve due predictions using bounded candles from their exact reference-price venue.
Require an exact terminal bar, exclude lookahead, and count only successful outcome saves.
Each run attempts a deterministic fresh/stuck selection within a time budget; rows the budget
does not reach are deferred to a later run, never counted as failed.
"""

from __future__ import annotations

import argparse
import hashlib
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite
from types import MappingProxyType
from typing import Any

from crypto_probability_engine.adapters.http_client import PublicHttpClient
from crypto_probability_engine.adapters.mappers import (
    BINANCE_BASE_URL,
    OKX_BASE_URL,
    map_interval,
    parse_binance_candles,
    parse_okx_candles,
    provider_symbol,
)
from crypto_probability_engine.adapters.types import MarketCandle, ProviderError
from crypto_probability_engine.config.defaults import (
    DEFAULT_PHASE1A,
    TIMEFRAME_SECONDS,
)
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.normalizers.symbols import normalize_symbol
from crypto_probability_engine.persistence.prediction_origin import PredictionOrigin
from crypto_probability_engine.persistence.repository import (
    InMemoryPersistenceRepository,
    PersistenceRepository,
    SupabasePersistenceRepository,
    SupabaseRestRepository,
)

RESOLVER_VERSION = "resolver-v2a-exact-eligibility"
EXACT_SOURCE_PROVIDERS = MappingProxyType({"BINANCE_PUBLIC": "binance", "OKX_PUBLIC": "okx"})
# Fixed-duration bars only. 1M uses an approximate 30-day duration, so it has no exact terminal bar.
EXACT_TIMEFRAMES = frozenset({"15m", "1H", "4H", "1D", "1W"})
MAX_WINDOW_BARS = 96
BINANCE_KLINES_PATH = "/api/v3/klines"
OKX_CANDLES_PATH = "/api/v5/market/candles"  # serves only the latest 1,440 bars
OKX_HISTORY_CANDLES_PATH = "/api/v5/market/history-candles"
OKX_RECENT_MAX_BARS_BACK = 1400  # margin below 1,440
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

# A provider call can take ~20 s at worst and the workflow job has a hard timeout, so a run stops
# STARTING rows once its budget is spent. Rows it did not start are deferred, never failed.
DEFAULT_TIME_BUDGET_SECONDS = 600
# The due query returns the oldest horizons first, so a backlog of rows that never resolve would
# take every slot, every run. The resolver scans past it and splits the rows: fresh ones (horizon
# at most FRESH_WINDOW before now) go first; stuck ones (older, or unreadable) share a quota whose
# members rotate every hour, so neither group can starve the other.
FRESH_WINDOW = timedelta(hours=48)
SCAN_LIMIT_FACTOR = 20
SCAN_LIMIT_CAP = 1000
STUCK_QUOTA_FLOOR = 5
STUCK_QUOTA_DIVISOR = 5
# Every reason an attempted row can stay unresolved, in the detail line's fixed order. No key may
# contain "failed": the workflow fails any run whose output matches failed=[1-9] anywhere.
SKIP_REASONS = (
    "skip_ineligible",
    "skip_invalid_target",
    "skip_not_due",
    "skip_terminal_bar_missing",
)
ERROR_REASONS = (
    "error_row_unreadable",
    "error_provider_rejected",
    "error_provider_unavailable",
    "error_candle_invalid",
    "error_save_not_ok",
    "error_save_exception",
    "error_other",
)
REASON_KEYS = SKIP_REASONS + ERROR_REASONS
DETAIL_COUNT_KEYS = ("scanned", "selected", "fresh", "stuck", "deferred")

_RESOLVED = "resolved"
# How far one row's attempt got. When the attempt raises, the stage names the failure's reason.
_STAGE_READ = "read"  # reading the row: every check before the provider is called
_STAGE_FETCH = "fetch"
_STAGE_CANDLES = "candles"
_STAGE_BUILD = "build"
_STAGE_SAVE = "save"
_STAGE_STATUS = "status"


@dataclass(slots=True)
class _Progress:
    stage: str = _STAGE_READ


@dataclass(frozen=True)
class _Selection:
    rows: tuple[Any, ...]  # attempt order: selected fresh rows, then selected stuck rows
    fresh: int  # fresh rows among those scanned
    stuck: int  # stuck rows among those scanned


@dataclass(frozen=True)
class CandleWindow:
    provider: str
    data_source: str
    normalized_symbol: str
    timeframe: str
    first_open_utc: datetime
    terminal_open_utc: datetime
    terminal_close_utc: datetime
    bars: int
    now_utc: datetime


FetchCandles = Callable[[CandleWindow, Settings], Sequence[MarketCandle]]


def build_resolver_repository(settings: Settings) -> PersistenceRepository:
    """Build the operator resolver repository, preferring direct DB access when present."""

    if settings.supabase_db_url:
        return SupabasePersistenceRepository(settings.supabase_db_url)
    if settings.supabase_url and settings.supabase_service_role_key:
        return SupabaseRestRepository(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
    return InMemoryPersistenceRepository()


def resolve_due_predictions(
    repository: PersistenceRepository,
    *,
    settings: Settings | None = None,
    now_utc: datetime | None = None,
    limit: int = 100,
    fetch_candles: FetchCandles | None = None,
    time_budget_seconds: float = DEFAULT_TIME_BUDGET_SECONDS,
    monotonic: Callable[[], float] | None = None,
) -> dict[str, int]:
    """Resolve a fair, time-bounded selection of due predictions without failing the batch.

    ``due`` counts the SELECTED rows (at most ``limit``): due = resolved + skipped + failed +
    deferred. Deferred rows were never started: no provider call, no write, not failed.
    """

    if not time_budget_seconds > 0:
        raise ValueError("time_budget_seconds must be > 0.")
    clock = time.monotonic if monotonic is None else monotonic
    started = clock()
    settings = settings or Settings.from_env()
    now = _coerce_utc(now_utc or datetime.now(tz=UTC))
    scanned = list(
        repository.fetch_due_unresolved_predictions(
            now,
            _scan_limit(limit),
            data_sources=tuple(EXACT_SOURCE_PROVIDERS),
            timeframes=tuple(sorted(EXACT_TIMEFRAMES)),
            prediction_origins=(PredictionOrigin.USER_REQUESTED.value,),
        )
    )
    selection = _select_rows(scanned, now=now, limit=limit)
    selected = len(selection.rows)
    stats = {
        "due": selected,
        "resolved": 0,
        "skipped": 0,
        "failed": 0,
        "deferred": 0,
        "scanned": len(scanned),
        "selected": selected,
        "fresh": selection.fresh,
        "stuck": selection.stuck,
        **dict.fromkeys(REASON_KEYS, 0),
    }
    candle_fetcher = fetch_candles or fetch_public_candles
    for index, prediction in enumerate(selection.rows):
        if clock() - started >= time_budget_seconds:
            stats["deferred"] = selected - index
            break
        reason = _attempt_row(
            repository, prediction, now=now, settings=settings, fetch_candles=candle_fetcher
        )
        if reason == _RESOLVED:
            stats["resolved"] += 1
            continue
        stats[reason] += 1
        stats["skipped" if reason in SKIP_REASONS else "failed"] += 1
    return stats


def _scan_limit(limit: int) -> int:
    return min(max(limit * SCAN_LIMIT_FACTOR, limit), SCAN_LIMIT_CAP)


def _select_rows(rows: Sequence[Any], *, now: datetime, limit: int) -> _Selection:
    """At most ``limit`` rows: fresh in query order, then stuck in this hour's rotated order."""

    oldest_fresh = now - FRESH_WINDOW
    fresh: list[Any] = []
    stuck: list[Any] = []
    for row in rows:
        horizon = _horizon_or_none(row)
        (fresh if horizon is not None and horizon >= oldest_fresh else stuck).append(row)
    hour_bucket = (now - EPOCH) // timedelta(hours=1)
    rotated = sorted(stuck, key=lambda row: _rotation_key(row, hour_bucket))
    capacity = max(0, int(limit))
    stuck_quota = min(capacity, max(STUCK_QUOTA_FLOOR, capacity // STUCK_QUOTA_DIVISOR))
    take_stuck = min(len(rotated), stuck_quota)
    # fresh_take = capacity - stuck_quota, plus any stuck quota left unused; then the reverse.
    take_fresh = min(len(fresh), capacity - take_stuck)
    take_stuck = min(len(rotated), capacity - take_fresh)
    return _Selection(
        rows=(*fresh[:take_fresh], *rotated[:take_stuck]),
        fresh=len(fresh),
        stuck=len(stuck),
    )


def _horizon_or_none(row: Any) -> datetime | None:
    if not isinstance(row, Mapping):
        return None
    try:
        return _parse_utc(row.get("horizon_end_utc"))
    except Exception:
        return None


def _rotation_key(row: Any, hour_bucket: int) -> str:
    prediction_id = row.get("prediction_id") if isinstance(row, Mapping) else None
    token = f"{prediction_id}|{hour_bucket}".encode("utf-8", "surrogatepass")
    return hashlib.sha256(token).hexdigest()


def _attempt_row(
    repository: PersistenceRepository,
    prediction: dict,
    *,
    now: datetime,
    settings: Settings,
    fetch_candles: FetchCandles,
) -> str:
    """Attempt one row. Return "resolved" or the one reason it stayed unresolved; never raise."""

    progress = _Progress()
    try:
        outcome, skip_reason = _evaluate_outcome_row(
            prediction,
            now_utc=now,
            settings=settings,
            fetch_candles=fetch_candles,
            progress=progress,
        )
        if outcome is None:
            return skip_reason
        progress.stage = _STAGE_SAVE
        status = repository.save_prediction_outcome(outcome)
        progress.stage = _STAGE_STATUS
        return _RESOLVED if status == "OK" else "error_save_not_ok"
    except Exception as exc:
        return _error_reason(exc, progress.stage)


def _error_reason(exc: Exception, stage: str) -> str:
    if stage == _STAGE_READ:
        return "error_row_unreadable"
    if stage == _STAGE_SAVE:
        return "error_save_exception"
    if stage == _STAGE_STATUS:
        return "error_save_not_ok"
    if isinstance(exc, ProviderError):
        if exc.code == "INVALID_SYMBOL":
            return "error_provider_rejected"
        return "error_provider_unavailable"
    if stage == _STAGE_CANDLES and isinstance(exc, ValueError):
        return "error_candle_invalid"
    return "error_other"


def build_outcome_row(
    prediction: dict,
    *,
    now_utc: datetime,
    settings: Settings,
    fetch_candles: FetchCandles,
) -> dict | None:
    """The outcome row for a resolvable prediction, or None when it is skipped.

    Raises exactly what evaluating the prediction raises.
    """

    outcome, _skip_reason = _evaluate_outcome_row(
        prediction,
        now_utc=now_utc,
        settings=settings,
        fetch_candles=fetch_candles,
        progress=_Progress(),
    )
    return outcome


def _evaluate_outcome_row(
    prediction: dict,
    *,
    now_utc: datetime,
    settings: Settings,
    fetch_candles: FetchCandles,
    progress: _Progress,
) -> tuple[dict | None, str | None]:
    """(outcome row, None) or (None, skip reason); on raising, ``progress`` holds the stage."""

    source = prediction.get("data_source")
    if not isinstance(source, str) or source not in EXACT_SOURCE_PROVIDERS:
        return None, "skip_ineligible"
    timeframe = prediction.get("timeframe")
    if not isinstance(timeframe, str) or timeframe not in EXACT_TIMEFRAMES:
        return None, "skip_ineligible"
    reference_close_utc = _parse_utc(prediction["reference_close_utc"])
    reference_price = float(prediction["reference_price"])
    horizon_end_utc = _parse_utc(prediction["horizon_end_utc"])
    if not isfinite(reference_price) or reference_price <= 0.0:
        return None, "skip_invalid_target"
    interval = timedelta(seconds=TIMEFRAME_SECONDS[timeframe])
    span = horizon_end_utc - reference_close_utc
    if span <= timedelta(0) or span % interval != timedelta(0):
        return None, "skip_invalid_target"
    bars = span // interval
    if bars > MAX_WINDOW_BARS:
        return None, "skip_invalid_target"
    if prediction.get("horizon_bars") is not None:
        try:
            if int(prediction["horizon_bars"]) != bars:
                return None, "skip_invalid_target"
        except (TypeError, ValueError, OverflowError):
            return None, "skip_invalid_target"
    now = _coerce_utc(now_utc)
    if now <= horizon_end_utc:
        return None, "skip_not_due"
    window = CandleWindow(
        provider=EXACT_SOURCE_PROVIDERS[source],
        data_source=source,
        normalized_symbol=str(prediction["normalized_symbol"]),
        timeframe=timeframe,
        first_open_utc=reference_close_utc,
        terminal_open_utc=horizon_end_utc - interval,
        terminal_close_utc=horizon_end_utc,
        bars=bars,
        now_utc=now,
    )
    progress.stage = _STAGE_FETCH
    candles = fetch_candles(window, settings)
    progress.stage = _STAGE_CANDLES
    by_close: dict[datetime, MarketCandle] = {}
    for candle in candles:
        close = _coerce_utc(candle.close_time_utc)
        if not reference_close_utc < close <= horizon_end_utc:
            continue
        open_time = _coerce_utc(candle.open_time_utc)
        if close - open_time != interval:
            raise ValueError("resolver candle does not span exactly one bar")
        if close in by_close and by_close[close] != candle:
            raise ValueError("conflicting duplicate candles in resolver window")
        by_close[close] = candle
    outcome_candle = by_close.get(horizon_end_utc)
    if outcome_candle is None:
        return None, "skip_terminal_bar_missing"
    progress.stage = _STAGE_BUILD
    observed = [by_close[close] for close in sorted(by_close)]
    terminal_return_frac = (float(outcome_candle.close) - reference_price) / reference_price
    decision_band_frac = _decision_band(prediction)
    return {
        "prediction_id": str(prediction["prediction_id"]),
        "resolved_at_utc": _iso_utc(now_utc),
        "outcome_close_utc": _iso_utc(horizon_end_utc),
        "outcome_reference_price": float(outcome_candle.close),
        "terminal_return_frac": terminal_return_frac,
        "realized_label": _realized_label(terminal_return_frac, decision_band_frac),
        "decision_band_frac": decision_band_frac,
        "max_favorable_frac": (max(float(candle.high) for candle in observed) - reference_price)
        / reference_price,
        "max_adverse_frac": (min(float(candle.low) for candle in observed) - reference_price)
        / reference_price,
        "candles_observed": len(observed),
        "resolver_version": RESOLVER_VERSION,
        "data_source": window.data_source,
        "is_live_data": True,
    }, None


def fetch_public_candles(
    window: CandleWindow,
    settings: Settings,
) -> Sequence[MarketCandle]:
    """Fetch a bounded candle window from the reference-price venue only."""

    normalized = normalize_symbol(window.normalized_symbol)
    client = PublicHttpClient.from_settings(settings)
    timeframe = window.timeframe
    provider = window.provider
    if provider == "binance":
        interval_ms = TIMEFRAME_SECONDS[timeframe] * 1000
        payload = client.get_json(
            base_url=BINANCE_BASE_URL,
            path=BINANCE_KLINES_PATH,
            params={
                "symbol": provider_symbol(normalized, provider),
                "interval": map_interval(timeframe, provider),
                "startTime": _millis(window.first_open_utc),
                "endTime": _millis(window.terminal_close_utc) + interval_ms,
                "limit": window.bars + 3,
            },
            provider=provider,
        )
        return parse_binance_candles(payload, timeframe=timeframe)
    if provider == "okx":
        payload = client.get_json(
            base_url=OKX_BASE_URL,
            path=_okx_candles_path(window),
            params={
                "instId": provider_symbol(normalized, provider),
                "bar": map_interval(timeframe, provider),
                "after": _millis(window.terminal_close_utc),
                "limit": window.bars + 2,
            },
            provider=provider,
        )
        return parse_okx_candles(payload, timeframe=timeframe)
    raise ProviderError("PROVIDER_DEGRADED", "Unsupported resolver provider.", provider=provider)


def _millis(dt: datetime) -> int:
    return (dt - EPOCH) // timedelta(milliseconds=1)


def _okx_candles_path(window: CandleWindow) -> str:
    interval = timedelta(seconds=TIMEFRAME_SECONDS[window.timeframe])
    bars_since = -((window.terminal_close_utc - window.now_utc) // interval)
    if bars_since + window.bars + 2 <= OKX_RECENT_MAX_BARS_BACK:
        return OKX_CANDLES_PATH
    return OKX_HISTORY_CANDLES_PATH


def _decision_band(prediction: dict) -> float:
    value = prediction.get("decision_band_frac")
    try:
        band = float(value)
    except (TypeError, ValueError):
        band = 0.0
    if band <= 0.0:
        return 2.0 * DEFAULT_PHASE1A.taker_fee_frac
    return band


def _realized_label(terminal_return_frac: float, decision_band_frac: float) -> str:
    if terminal_return_frac > decision_band_frac:
        return "UP"
    if terminal_return_frac < -decision_band_frac:
        return "DOWN"
    return "TIMEOUT"


def _parse_utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        return _coerce_utc(value)
    return _coerce_utc(datetime.fromisoformat(str(value).replace("Z", "+00:00")))


def _coerce_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso_utc(value: datetime) -> str:
    return _coerce_utc(value).isoformat().replace("+00:00", "Z")


def format_detail_line(stats: Mapping[str, int], *, budget_s: float) -> str:
    """The second summary line: every key, zeros included, in a fixed order.

    It can never contain "failed=": the workflow fails a run on failed=[1-9] in ANY line.
    """

    counts = " ".join(f"{key}={stats.get(key, 0)}" for key in DETAIL_COUNT_KEYS)
    reasons = " ".join(f"{key}={stats.get(key, 0)}" for key in REASON_KEYS)
    return f"resolver_detail {counts} budget_s={budget_s} {reasons}"


def _positive_seconds(value: str) -> int:
    try:
        seconds = int(value)
    except ValueError:
        seconds = 0
    if seconds <= 0:
        raise argparse.ArgumentTypeError(f"must be a positive whole number, got {value!r}")
    return seconds


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve due UCPE prediction outcomes.")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument(
        "--time-budget-seconds",
        type=_positive_seconds,
        default=DEFAULT_TIME_BUDGET_SECONDS,
        help="Start no new row after this many seconds; rows not started are deferred.",
    )
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    repository = build_resolver_repository(settings)
    repository_type = repository.repository_type()
    try:
        stats = resolve_due_predictions(
            repository,
            settings=settings,
            limit=args.limit,
            time_budget_seconds=args.time_budget_seconds,
        )
    except Exception as exc:
        print(
            "resolved_outcomes "
            f"repository={repository_type} limit={args.limit} "
            "due=0 resolved=0 skipped=0 failed=1 "
            f"error={type(exc).__name__}: {exc}"
        )
        close = getattr(repository, "close", None)
        if callable(close):
            close()
        return 1
    print(
        "resolved_outcomes "
        f"repository={repository_type} limit={args.limit} "
        f"due={stats['due']} resolved={stats['resolved']} "
        f"skipped={stats['skipped']} failed={stats['failed']}"
    )
    print(format_detail_line(stats, budget_s=args.time_budget_seconds))
    close = getattr(repository, "close", None)
    if callable(close):
        close()
    return 1 if stats["failed"] > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
