from __future__ import annotations

from dataclasses import replace

from crypto_probability_engine.adapters.market_metrics import build_derived_market_metrics
from crypto_probability_engine.adapters.types import OrderBookLevel, OrderBookSnapshot, RecentTrade
from tests.fixtures.market_data import FIXED_NOW, make_snapshot


def test_derived_metrics_are_formulaic_and_nonbinding() -> None:
    snapshot = replace(
        make_snapshot(provider="binance"),
        order_book=OrderBookSnapshot(
            bids=(
                OrderBookLevel(price=100.0, size=2.0),
                OrderBookLevel(price=99.5, size=3.0),
            ),
            asks=(
                OrderBookLevel(price=101.0, size=2.0),
                OrderBookLevel(price=101.5, size=3.0),
            ),
            as_of_utc=FIXED_NOW,
        ),
        recent_trades=(
            RecentTrade(
                provider="binance",
                price=100.5,
                size=1.0,
                side="BUY",
                timestamp_utc=FIXED_NOW,
            ),
            RecentTrade(
                provider="binance",
                price=100.4,
                size=0.5,
                side="SELL",
                timestamp_utc=FIXED_NOW,
            ),
        ),
    )

    metrics = build_derived_market_metrics(snapshot)

    assert metrics["mid_price"]["value"] == 100.5
    assert metrics["spread_bps"]["formula"] == "(best_ask - best_bid) / mid_price * 10000"
    assert metrics["spread_bps"]["value"] > 0
    assert metrics["depth_imbalance"]["status"] == "OK"
    assert metrics["shallow_slippage_estimate"]["status"] == "OK"
    assert metrics["recent_trade_buy_sell_pressure"]["status"] == "OK"
    assert "score" not in str(metrics).lower()


def test_derived_metrics_mark_insufficient_data_unavailable() -> None:
    snapshot = replace(make_snapshot(provider="okx"), order_book=None, recent_trades=())

    metrics = build_derived_market_metrics(snapshot)

    assert metrics["spread_bps"]["status"] == "UNAVAILABLE"
    assert metrics["depth_imbalance"]["status"] == "UNAVAILABLE"
    assert metrics["shallow_slippage_estimate"]["status"] == "UNAVAILABLE"
    assert metrics["recent_trade_buy_sell_pressure"]["status"] == "UNAVAILABLE"
