"""Formulaic Market Data v2 metrics from public provider resources."""

from __future__ import annotations

from datetime import UTC, datetime

from crypto_probability_engine.adapters.types import (
    MarketSnapshot,
    OrderBookSnapshot,
    RecentTrade,
)
from crypto_probability_engine.config.defaults import DEFAULT_PHASE1A


def build_derived_market_metrics(snapshot: MarketSnapshot) -> dict[str, dict]:
    """Build advisory, non-binding metrics from already-fetched public data."""

    return {
        "mid_price": _mid_price(snapshot.order_book, snapshot.provider, snapshot.as_of_utc),
        "spread_bps": _spread_bps(snapshot.order_book, snapshot.provider, snapshot.as_of_utc),
        "depth_imbalance": _depth_imbalance(
            snapshot.order_book,
            snapshot.provider,
            snapshot.as_of_utc,
        ),
        "shallow_slippage_estimate": _shallow_slippage_estimate(
            snapshot.order_book,
            snapshot.provider,
            snapshot.as_of_utc,
            notional_quote=DEFAULT_PHASE1A.liquidity_min_top_depth_quote,
        ),
        "recent_trade_buy_sell_pressure": _recent_trade_pressure(
            snapshot.recent_trades,
            snapshot.provider,
            snapshot.as_of_utc,
        ),
        "freshness_age_seconds": {
            "status": "OK",
            "value": _freshness_age_seconds(snapshot),
            "formula": "snapshot.as_of_utc - latest_candle.close_time_utc",
            "source_provider": snapshot.provider,
            "as_of_utc": _as_z(snapshot.as_of_utc),
        },
    }


def cross_provider_price_disagreement_metric(reports: list[dict]) -> dict:
    values = [report.get("disagreement_bps") for report in reports if "disagreement_bps" in report]
    if not values:
        return {
            "status": "UNAVAILABLE",
            "value": None,
            "formula": "latest_common_closed_candle_price_disagreement_bps",
            "source_provider": "cross_provider",
            "uncertainty": "INSUFFICIENT_DATA",
        }
    return {
        "status": "OK",
        "value": max(float(value) for value in values),
        "formula": "abs(left_price - right_price) / mid_price * 10000",
        "source_provider": "cross_provider",
        "inputs": {"reports": reports},
    }


def _mid_price(book: OrderBookSnapshot | None, provider: str, as_of_utc: datetime) -> dict:
    if not book or not book.bids or not book.asks:
        return _unavailable("mid_price", provider, "missing_order_book")
    best_bid = book.bids[0].price
    best_ask = book.asks[0].price
    return {
        "status": "OK",
        "value": (best_bid + best_ask) / 2.0,
        "formula": "(best_bid + best_ask) / 2",
        "source_provider": provider,
        "as_of_utc": _as_z(as_of_utc),
        "inputs": {"best_bid": best_bid, "best_ask": best_ask},
    }


def _spread_bps(book: OrderBookSnapshot | None, provider: str, as_of_utc: datetime) -> dict:
    if not book or not book.bids or not book.asks:
        return _unavailable("spread_bps", provider, "missing_order_book")
    best_bid = book.bids[0].price
    best_ask = book.asks[0].price
    mid = (best_bid + best_ask) / 2.0
    if mid <= 0:
        return _unavailable("spread_bps", provider, "invalid_mid_price")
    return {
        "status": "OK",
        "value": (best_ask - best_bid) / mid * 10_000.0,
        "formula": "(best_ask - best_bid) / mid_price * 10000",
        "source_provider": provider,
        "as_of_utc": _as_z(as_of_utc),
        "inputs": {"best_bid": best_bid, "best_ask": best_ask, "mid_price": mid},
    }


def _depth_imbalance(book: OrderBookSnapshot | None, provider: str, as_of_utc: datetime) -> dict:
    if not book or not book.bids or not book.asks:
        return _unavailable("depth_imbalance", provider, "missing_order_book")
    bid_depth = sum(level.price * level.size for level in book.bids)
    ask_depth = sum(level.price * level.size for level in book.asks)
    total = bid_depth + ask_depth
    if total <= 0:
        return _unavailable("depth_imbalance", provider, "empty_depth")
    return {
        "status": "OK",
        "value": (bid_depth - ask_depth) / total,
        "formula": "(bid_quote_depth - ask_quote_depth) / total_quote_depth",
        "source_provider": provider,
        "as_of_utc": _as_z(as_of_utc),
        "inputs": {"bid_quote_depth": bid_depth, "ask_quote_depth": ask_depth},
    }


def _shallow_slippage_estimate(
    book: OrderBookSnapshot | None,
    provider: str,
    as_of_utc: datetime,
    *,
    notional_quote: float,
) -> dict:
    if not book or not book.asks:
        return _unavailable("shallow_slippage_estimate", provider, "missing_order_book")
    best_ask = book.asks[0].price
    mid_value = _mid_price(book, provider, as_of_utc).get("value")
    if not isinstance(mid_value, int | float) or mid_value <= 0:
        return _unavailable("shallow_slippage_estimate", provider, "invalid_mid_price")
    remaining = notional_quote
    cost = 0.0
    filled_base = 0.0
    for level in book.asks:
        level_quote = level.price * level.size
        take_quote = min(remaining, level_quote)
        if take_quote <= 0:
            continue
        cost += take_quote
        filled_base += take_quote / level.price
        remaining -= take_quote
        if remaining <= 0:
            break
    if remaining > 0 or filled_base <= 0:
        return _unavailable("shallow_slippage_estimate", provider, "insufficient_ask_depth")
    average_price = cost / filled_base
    return {
        "status": "OK",
        "value": (average_price - mid_value) / mid_value * 10_000.0,
        "formula": "ask_sweep_average_price_vs_mid_bps",
        "source_provider": provider,
        "as_of_utc": _as_z(as_of_utc),
        "inputs": {
            "notional_quote": notional_quote,
            "best_ask": best_ask,
            "average_fill_price": average_price,
            "mid_price": mid_value,
        },
    }


def _recent_trade_pressure(
    trades: tuple[RecentTrade, ...],
    provider: str,
    as_of_utc: datetime,
) -> dict:
    if not trades:
        return _unavailable(
            "recent_trade_buy_sell_pressure",
            provider,
            "missing_recent_trades",
        )
    buy_quote = 0.0
    sell_quote = 0.0
    unknown_count = 0
    for trade in trades:
        quote_value = trade.price * trade.size
        if trade.side == "BUY":
            buy_quote += quote_value
        elif trade.side == "SELL":
            sell_quote += quote_value
        else:
            unknown_count += 1
    total = buy_quote + sell_quote
    if total <= 0 or unknown_count == len(trades):
        return _unavailable(
            "recent_trade_buy_sell_pressure",
            provider,
            "unreliable_trade_side_semantics",
        )
    return {
        "status": "OK",
        "value": (buy_quote - sell_quote) / total,
        "formula": "(buy_quote_volume - sell_quote_volume) / known_side_quote_volume",
        "source_provider": provider,
        "as_of_utc": _as_z(as_of_utc),
        "inputs": {
            "buy_quote_volume": buy_quote,
            "sell_quote_volume": sell_quote,
            "unknown_side_count": unknown_count,
            "trade_count": len(trades),
        },
    }


def _freshness_age_seconds(snapshot: MarketSnapshot) -> int | None:
    if not snapshot.candles:
        return None
    return max(0, int((snapshot.as_of_utc - snapshot.candles[-1].close_time_utc).total_seconds()))


def _unavailable(metric: str, provider: str, reason: str) -> dict:
    return {
        "status": "UNAVAILABLE",
        "value": None,
        "formula": metric,
        "source_provider": provider,
        "uncertainty": reason,
    }


def _as_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
