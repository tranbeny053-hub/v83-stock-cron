"""Liquidity and depth features from public order-book data."""

from __future__ import annotations

from crypto_probability_engine.adapters.types import OrderBookSnapshot


def compute_liquidity_depth(book: OrderBookSnapshot | None) -> dict:
    if book is None or not book.bids or not book.asks:
        return {
            "status": "DEGRADED",
            "spread_frac": None,
            "top_depth_quote": 0.0,
            "warning": "Order book unavailable.",
        }
    best_bid = book.bids[0].price
    best_ask = book.asks[0].price
    mid = (best_bid + best_ask) / 2.0
    spread_frac = (best_ask - best_bid) / mid if mid > 0 else 0.0
    if spread_frac < 0.0 or spread_frac > 1.0:
        return {
            "status": "DEGRADED",
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread_frac": None,
            "top_depth_quote": 0.0,
            "warning": "Order-book spread is outside bounded fraction range.",
        }
    bid_depth = sum(level.price * level.size for level in book.bids[:5])
    ask_depth = sum(level.price * level.size for level in book.asks[:5])
    return {
        "status": "OK",
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread_frac": spread_frac,
        "top_depth_quote": min(bid_depth, ask_depth),
    }
