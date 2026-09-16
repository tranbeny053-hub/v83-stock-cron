"""Closed candle history longer than a market snapshot's window, only for a caller that asks for it.

WHY A SEPARATE CAPABILITY. ``fetch_market_snapshot`` deliberately carries ``min_history + 5``
candles, and every existing consumer reads the whole of ``snapshot.candles``. Realized volatility,
tail CVaR and the frozen distributional-v1 EWMA would all move if that window grew, silently
changing the deployed methodology without a new ``methodology_version``. So the snapshot stays
exactly as it is, and a longer series is fetched only by a consumer that asks for it.

NO CALLER TODAY. Nothing in ``api/`` or ``quant/`` uses this module. The first consumer is a future
distributional-v2 wiring, whose 15m recipe needs 673 closed candles (R2 §6), and that wiring is an
owner decision.

PROVIDER FACTS, MEASURED 2026-09-15 (``.work/816/l3/probe``, raw captured before parsing):
- Binance ``/api/v3/klines`` returns up to 1000 ascending rows, the last one still in progress.
- OKX ``/api/v5/market/candles`` returns up to 300 rows newest first, the first possibly
  unconfirmed. ``after=<ts>`` returns strictly older, gap-free rows; three pages held 900
  contiguous 15m bars.
``CANDLE_HISTORY_MAX_BARS`` stays inside what was measured on both providers.

Every request goes through ``PublicHttpClient``, so the byte cap, per-attempt deadline, rate limit
and retry policy apply unchanged, and every history is validated exactly like a snapshot's candles.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from crypto_probability_engine.adapters.http_client import PublicHttpClient
from crypto_probability_engine.adapters.mappers import (
    BINANCE_BASE_URL,
    OKX_BASE_URL,
    map_interval,
    parse_binance_candles,
    parse_okx_candles,
    provider_symbol,
)
from crypto_probability_engine.adapters.types import MarketCandle, MarketSnapshot, ProviderError
from crypto_probability_engine.api.schemas import ErrorCode
from crypto_probability_engine.config.unit_discipline import utc_now
from crypto_probability_engine.normalizers.symbols import NormalizedSymbol
from crypto_probability_engine.validation.market_data import DataValidationError, validate_candles

CANDLE_HISTORY_MAX_BARS = 800
CANDLE_HISTORY_TIMEFRAMES = frozenset({"15m", "1H", "4H"})
BINANCE_KLINES_PATH = "/api/v3/klines"
OKX_CANDLES_PATH = "/api/v5/market/candles"
OKX_CANDLES_PAGE_LIMIT = 300


@dataclass(frozen=True)
class CandleHistory:
    """Exactly ``requested_bars`` closed, adjacent candles ending at the latest closed bar."""

    provider: str
    normalized_symbol: str
    timeframe: str
    requested_bars: int
    candles: tuple[MarketCandle, ...]
    as_of_utc: datetime
    requests: int


class CandleHistoryAdapter(Protocol):
    name: str

    def fetch_candle_history(
        self, symbol: NormalizedSymbol, timeframe: str, *, bars: int
    ) -> CandleHistory:
        """Fetch exactly ``bars`` closed candles, or raise."""


def check_history_request(timeframe: str, bars: object) -> int:
    """Refuse a request this capability does not serve. A caller error, never a provider one."""

    if timeframe not in CANDLE_HISTORY_TIMEFRAMES:
        raise ValueError(
            f"candle history serves {sorted(CANDLE_HISTORY_TIMEFRAMES)}, not {timeframe!r}"
        )
    if isinstance(bars, bool) or not isinstance(bars, int):
        raise ValueError("bars must be an integer")
    if not 1 <= bars <= CANDLE_HISTORY_MAX_BARS:
        raise ValueError(f"bars must be between 1 and {CANDLE_HISTORY_MAX_BARS}")
    return bars


def fetch_binance_candle_history(
    http_client: PublicHttpClient,
    symbol: NormalizedSymbol,
    timeframe: str,
    *,
    bars: int,
) -> CandleHistory:
    """ONE klines request for ``bars + 1`` rows; the parser drops the in-progress last row."""

    requested = check_history_request(timeframe, bars)
    payload = http_client.get_json(
        base_url=BINANCE_BASE_URL,
        path=BINANCE_KLINES_PATH,
        params={
            "symbol": provider_symbol(symbol, "binance"),
            "interval": map_interval(timeframe, "binance"),
            "limit": requested + 1,
        },
        provider="binance",
    )
    as_of_utc = utc_now()
    candles = parse_binance_candles(payload, timeframe=timeframe)
    return _history("binance", symbol, timeframe, requested, candles, as_of_utc, requests=1)


def fetch_okx_candle_history(
    http_client: PublicHttpClient,
    symbol: NormalizedSymbol,
    timeframe: str,
    *,
    bars: int,
) -> CandleHistory:
    """Newest page first, then ``after=<oldest open>`` pages, bounded, each strictly older.

    A page with no closed candle, a page that does not move strictly older, or a candle that two
    pages report differently all fail closed. So does running out of pages before ``bars``.
    """

    requested = check_history_request(timeframe, bars)
    instrument = provider_symbol(symbol, "okx")
    bar = map_interval(timeframe, "okx")
    # The newest page may hold one unconfirmed row, so bars + 1 rows always suffice.
    max_requests = -(-(requested + 1) // OKX_CANDLES_PAGE_LIMIT)
    by_open: dict[datetime, MarketCandle] = {}
    after_millis: int | None = None
    requests = 0
    while True:
        params: dict[str, object] = {
            "instId": instrument,
            "bar": bar,
            "limit": OKX_CANDLES_PAGE_LIMIT,
        }
        if after_millis is not None:
            params["after"] = str(after_millis)
        payload = http_client.get_json(
            base_url=OKX_BASE_URL, path=OKX_CANDLES_PATH, params=params, provider="okx"
        )
        requests += 1
        page = parse_okx_candles(payload, timeframe=timeframe)
        if not page:
            raise ProviderError(
                "INSUFFICIENT_DATA",
                "OKX returned a history page with no closed candle.",
                provider="okx",
            )
        if after_millis is not None and _millis(page[-1].open_time_utc) >= after_millis:
            raise ProviderError(
                "SCHEMA_VALIDATION_FAILED",
                "OKX history page did not move strictly older.",
                provider="okx",
            )
        for candle in page:
            seen = by_open.get(candle.open_time_utc)
            if seen is not None and seen != candle:
                raise ProviderError(
                    "DATA_CONFLICT",
                    "OKX history pages disagree about one candle.",
                    provider="okx",
                )
            by_open[candle.open_time_utc] = candle
        if len(by_open) >= requested:
            break
        if requests >= max_requests:
            raise ProviderError(
                "INSUFFICIENT_DATA",
                "OKX history is shorter than requested.",
                provider="okx",
            )
        after_millis = _millis(page[0].open_time_utc)
    as_of_utc = utc_now()
    candles = tuple(by_open[open_time] for open_time in sorted(by_open))
    return _history("okx", symbol, timeframe, requested, candles, as_of_utc, requests=requests)


def validate_candle_history(history: CandleHistory, *, now_utc: datetime | None = None) -> None:
    """The snapshot rules, applied to the whole history: adjacent, sane, closed, fresh, exact."""

    check_history_request(history.timeframe, history.requested_bars)
    if len(history.candles) != history.requested_bars:
        raise DataValidationError(
            ErrorCode.INSUFFICIENT_DATA,
            "Candle history does not hold exactly the requested number of candles.",
        )
    validate_candles(
        history.candles,
        history.timeframe,
        now_utc=history.as_of_utc if now_utc is None else now_utc,
        min_bars=history.requested_bars,
    )


def assert_history_extends_snapshot(history: CandleHistory, snapshot: MarketSnapshot) -> None:
    """The long series IS the series the rest of the analysis saw.

    Same provider, symbol and timeframe; the same latest closed candle; and every snapshot candle
    the history also covers is identical in every field.
    """

    if (history.provider, history.normalized_symbol, history.timeframe) != (
        snapshot.provider,
        snapshot.normalized_symbol,
        snapshot.timeframe,
    ):
        raise DataValidationError(
            ErrorCode.DATA_CONFLICT,
            "Candle history and snapshot differ in provider, symbol or timeframe.",
        )
    if not history.candles or not snapshot.candles:
        raise DataValidationError(ErrorCode.INSUFFICIENT_DATA, "No candles to compare.")
    if history.candles[-1] != snapshot.candles[-1]:
        raise DataValidationError(
            ErrorCode.DATA_CONFLICT,
            "Candle history and snapshot do not end at the same closed candle.",
        )
    by_open = {candle.open_time_utc: candle for candle in history.candles}
    first_open = history.candles[0].open_time_utc
    for candle in snapshot.candles:
        if candle.open_time_utc < first_open:
            continue
        if by_open.get(candle.open_time_utc) != candle:
            raise DataValidationError(
                ErrorCode.DATA_CONFLICT,
                "Candle history disagrees with the snapshot on a shared candle.",
            )


def _history(
    provider: str,
    symbol: NormalizedSymbol,
    timeframe: str,
    requested: int,
    candles: tuple[MarketCandle, ...],
    as_of_utc: datetime,
    *,
    requests: int,
) -> CandleHistory:
    if len(candles) < requested:
        raise ProviderError(
            "INSUFFICIENT_DATA",
            "Provider candle history is shorter than requested.",
            provider=provider,
        )
    history = CandleHistory(
        provider=provider,
        normalized_symbol=symbol.display,
        timeframe=timeframe,
        requested_bars=requested,
        candles=tuple(candles[-requested:]),
        as_of_utc=as_of_utc,
        requests=requests,
    )
    validate_candle_history(history)
    return history


def _millis(value: datetime) -> int:
    return int(round(value.timestamp() * 1000.0))
