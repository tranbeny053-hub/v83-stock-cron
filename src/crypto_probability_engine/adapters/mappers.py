"""Provider-specific public market-data mappers."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from crypto_probability_engine.adapters.types import (
    MarketCandle,
    MarketTicker,
    OrderBookLevel,
    OrderBookSnapshot,
    ProviderError,
    RecentTrade,
)
from crypto_probability_engine.config.defaults import TIMEFRAME_SECONDS
from crypto_probability_engine.normalizers.symbols import NormalizedSymbol

BINANCE_BASE_URL = "https://data-api.binance.vision"
OKX_BASE_URL = "https://www.okx.com"
BINANCE_INTERVALS = {
    "15m": "15m",
    "1H": "1h",
    "4H": "4h",
    "1D": "1d",
    "1W": "1w",
    "1M": "1M",
}
OKX_INTERVALS = {
    "15m": "15m",
    "1H": "1H",
    "4H": "4H",
    "1D": "1Dutc",
    "1W": "1Wutc",
    "1M": "1Mutc",
}


def provider_symbol(symbol: NormalizedSymbol, provider: str) -> str:
    try:
        return symbol.provider_symbols[provider]
    except KeyError as exc:
        raise ProviderError(
            "INVALID_SYMBOL",
            "Unsupported provider symbol.",
            provider=provider,
        ) from exc


def map_interval(timeframe: str, provider: str) -> str:
    mappings = {"binance": BINANCE_INTERVALS, "okx": OKX_INTERVALS}
    try:
        return mappings[provider][timeframe]
    except KeyError as exc:
        raise ProviderError(
            "SCHEMA_VALIDATION_FAILED",
            "Unsupported timeframe.",
            provider=provider,
        ) from exc


def interval_delta(timeframe: str, *, provider: str) -> timedelta:
    try:
        return timedelta(seconds=TIMEFRAME_SECONDS[timeframe])
    except KeyError as exc:
        raise ProviderError(
            "SCHEMA_VALIDATION_FAILED",
            "Unsupported timeframe.",
            provider=provider,
        ) from exc


def parse_binance_candles(rows: Any, *, timeframe: str) -> tuple[MarketCandle, ...]:
    if not isinstance(rows, list):
        raise ProviderError(
            "SCHEMA_VALIDATION_FAILED",
            "Binance candle payload is invalid.",
            provider="binance",
        )
    closed_rows = rows[:-1]
    candles = [_parse_binance_candle(row, timeframe=timeframe) for row in closed_rows]
    return tuple(sorted(candles, key=lambda candle: candle.open_time_utc))


def parse_okx_candles(payload: Any, *, timeframe: str) -> tuple[MarketCandle, ...]:
    rows = _okx_data(payload, provider="okx")
    confirmed_rows = [row for row in rows if _sequence_value(row, 8, provider="okx") != "0"]
    candles = [_parse_okx_candle(row, timeframe=timeframe) for row in reversed(confirmed_rows)]
    return tuple(sorted(candles, key=lambda candle: candle.open_time_utc))


def parse_binance_order_book(payload: Any, *, as_of_utc: datetime) -> OrderBookSnapshot:
    if not isinstance(payload, dict):
        raise ProviderError(
            "SCHEMA_VALIDATION_FAILED",
            "Binance book payload is invalid.",
            provider="binance",
        )
    return OrderBookSnapshot(
        bids=_parse_levels(payload.get("bids", ()), provider="binance"),
        asks=_parse_levels(payload.get("asks", ()), provider="binance"),
        as_of_utc=as_of_utc,
    )


def parse_okx_order_book(payload: Any, *, as_of_utc: datetime) -> OrderBookSnapshot:
    data = _okx_data(payload, provider="okx")
    if not data or not isinstance(data[0], dict):
        raise ProviderError(
            "SCHEMA_VALIDATION_FAILED",
            "OKX book payload is invalid.",
            provider="okx",
        )
    item = data[0]
    return OrderBookSnapshot(
        bids=_parse_levels(item.get("bids", ()), provider="okx"),
        asks=_parse_levels(item.get("asks", ()), provider="okx"),
        as_of_utc=as_of_utc,
    )


def parse_binance_ticker(payload: Any, *, as_of_utc: datetime) -> MarketTicker:
    if not isinstance(payload, dict):
        raise ProviderError(
            "SCHEMA_VALIDATION_FAILED",
            "Binance ticker payload is invalid.",
            provider="binance",
        )
    return MarketTicker(
        provider="binance",
        last_price=_to_float(payload.get("lastPrice"), provider="binance"),
        bid_price=_to_optional_float(payload.get("bidPrice"), provider="binance"),
        ask_price=_to_optional_float(payload.get("askPrice"), provider="binance"),
        base_volume_24h=_to_optional_float(payload.get("volume"), provider="binance"),
        quote_volume_24h=_to_optional_float(payload.get("quoteVolume"), provider="binance"),
        as_of_utc=as_of_utc,
    )


def parse_okx_ticker(payload: Any, *, as_of_utc: datetime) -> MarketTicker:
    data = _okx_data(payload, provider="okx")
    if not data or not isinstance(data[0], dict):
        raise ProviderError(
            "SCHEMA_VALIDATION_FAILED",
            "OKX ticker payload is invalid.",
            provider="okx",
        )
    item = data[0]
    ticker_time = _from_millis(item.get("ts"), provider="okx") if item.get("ts") else as_of_utc
    return MarketTicker(
        provider="okx",
        last_price=_to_float(item.get("last"), provider="okx"),
        bid_price=_to_optional_float(item.get("bidPx"), provider="okx"),
        ask_price=_to_optional_float(item.get("askPx"), provider="okx"),
        base_volume_24h=_to_optional_float(item.get("vol24h"), provider="okx"),
        quote_volume_24h=_to_optional_float(item.get("volCcy24h"), provider="okx"),
        as_of_utc=ticker_time,
    )


def parse_binance_recent_trades(payload: Any) -> tuple[RecentTrade, ...]:
    if not isinstance(payload, list):
        raise ProviderError(
            "SCHEMA_VALIDATION_FAILED",
            "Binance trades payload is invalid.",
            provider="binance",
        )
    trades: list[RecentTrade] = []
    for row in payload:
        if not isinstance(row, dict):
            raise ProviderError(
                "SCHEMA_VALIDATION_FAILED",
                "Binance trade row is invalid.",
                provider="binance",
            )
        buyer_is_maker = row.get("isBuyerMaker")
        side = None if buyer_is_maker is None else ("SELL" if bool(buyer_is_maker) else "BUY")
        trades.append(
            RecentTrade(
                provider="binance",
                price=_to_float(row.get("price"), provider="binance"),
                size=_to_float(row.get("qty"), provider="binance"),
                side=side,
                timestamp_utc=_from_millis(row.get("time"), provider="binance"),
            )
        )
    return tuple(trades)


def parse_okx_recent_trades(payload: Any) -> tuple[RecentTrade, ...]:
    data = _okx_data(payload, provider="okx")
    trades: list[RecentTrade] = []
    for row in data:
        if not isinstance(row, dict):
            raise ProviderError(
                "SCHEMA_VALIDATION_FAILED",
                "OKX trade row is invalid.",
                provider="okx",
            )
        side_value = row.get("side")
        side = str(side_value).upper() if side_value in {"buy", "sell", "BUY", "SELL"} else None
        trades.append(
            RecentTrade(
                provider="okx",
                price=_to_float(row.get("px"), provider="okx"),
                size=_to_float(row.get("sz"), provider="okx"),
                side=side,
                timestamp_utc=_from_millis(row.get("ts"), provider="okx"),
            )
        )
    return tuple(trades)


def parse_binance_symbol_universe(payload: Any) -> frozenset[str]:
    if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list):
        raise ProviderError(
            "SCHEMA_VALIDATION_FAILED",
            "Binance exchangeInfo payload is invalid.",
            provider="binance",
        )
    symbols: set[str] = set()
    for row in payload["symbols"]:
        if not isinstance(row, dict):
            continue
        if row.get("status") != "TRADING" or row.get("quoteAsset") != "USDT":
            continue
        base = row.get("baseAsset")
        quote = row.get("quoteAsset")
        if isinstance(base, str) and isinstance(quote, str):
            symbols.add(f"{base.upper()}/{quote.upper()}")
    return frozenset(symbols)


def parse_okx_symbol_universe(payload: Any) -> frozenset[str]:
    data = _okx_data(payload, provider="okx")
    symbols: set[str] = set()
    for row in data:
        if not isinstance(row, dict):
            continue
        if row.get("instType") != "SPOT" or row.get("state") != "live":
            continue
        quote = row.get("quoteCcy")
        base = row.get("baseCcy")
        inst_id = row.get("instId")
        if quote == "USDT" and isinstance(base, str):
            symbols.add(f"{base.upper()}/USDT")
        elif isinstance(inst_id, str) and inst_id.endswith("-USDT"):
            symbols.add(inst_id.replace("-", "/").upper())
    return frozenset(symbols)


def _parse_binance_candle(row: Sequence[Any], *, timeframe: str) -> MarketCandle:
    open_time = _from_millis(_sequence_value(row, 0, provider="binance"), provider="binance")
    close_time = open_time + interval_delta(timeframe, provider="binance")
    return MarketCandle(
        open_time_utc=open_time,
        close_time_utc=close_time,
        open=_to_float(_sequence_value(row, 1, provider="binance"), provider="binance"),
        high=_to_float(_sequence_value(row, 2, provider="binance"), provider="binance"),
        low=_to_float(_sequence_value(row, 3, provider="binance"), provider="binance"),
        close=_to_float(_sequence_value(row, 4, provider="binance"), provider="binance"),
        volume=_to_float(_sequence_value(row, 5, provider="binance"), provider="binance"),
    )


def _parse_okx_candle(row: Sequence[Any], *, timeframe: str) -> MarketCandle:
    open_time = _from_millis(_sequence_value(row, 0, provider="okx"), provider="okx")
    close_time = open_time + interval_delta(timeframe, provider="okx")
    return MarketCandle(
        open_time_utc=open_time,
        close_time_utc=close_time,
        open=_to_float(_sequence_value(row, 1, provider="okx"), provider="okx"),
        high=_to_float(_sequence_value(row, 2, provider="okx"), provider="okx"),
        low=_to_float(_sequence_value(row, 3, provider="okx"), provider="okx"),
        close=_to_float(_sequence_value(row, 4, provider="okx"), provider="okx"),
        volume=_to_float(_sequence_value(row, 5, provider="okx"), provider="okx"),
    )


def _parse_levels(rows: Iterable[Any], *, provider: str) -> tuple[OrderBookLevel, ...]:
    levels: list[OrderBookLevel] = []
    for row in rows:
        levels.append(
            OrderBookLevel(
                price=_to_float(_sequence_value(row, 0, provider=provider), provider=provider),
                size=_to_float(_sequence_value(row, 1, provider=provider), provider=provider),
            )
        )
    return tuple(levels)


def _okx_data(payload: Any, *, provider: str) -> list[Any]:
    if not isinstance(payload, dict) or payload.get("code") not in {"0", 0}:
        code = payload.get("code") if isinstance(payload, dict) else None
        if code in {"51001", "51000", "50011"}:
            raise ProviderError("INVALID_SYMBOL", "OKX rejected symbol.", provider=provider)
        raise ProviderError("PROVIDER_DEGRADED", "OKX payload status is not OK.", provider=provider)
    data = payload.get("data")
    if not isinstance(data, list):
        raise ProviderError(
            "SCHEMA_VALIDATION_FAILED",
            "OKX payload data is invalid.",
            provider=provider,
        )
    return data


def _sequence_value(row: Any, index: int, *, provider: str) -> Any:
    if not isinstance(row, Sequence) or len(row) <= index:
        raise ProviderError(
            "SCHEMA_VALIDATION_FAILED",
            "Provider row shape is invalid.",
            provider=provider,
        )
    return row[index]


def _to_float(value: Any, *, provider: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ProviderError(
            "SCHEMA_VALIDATION_FAILED",
            "Provider numeric field is invalid.",
            provider=provider,
        ) from exc


def _to_optional_float(value: Any, *, provider: str) -> float | None:
    if value in {None, ""}:
        return None
    return _to_float(value, provider=provider)


def _from_millis(value: Any, *, provider: str) -> datetime:
    try:
        millis = int(value)
    except (TypeError, ValueError) as exc:
        raise ProviderError(
            "SCHEMA_VALIDATION_FAILED",
            "Provider timestamp is invalid.",
            provider=provider,
        ) from exc
    return datetime.fromtimestamp(millis / 1000.0, tz=UTC)
