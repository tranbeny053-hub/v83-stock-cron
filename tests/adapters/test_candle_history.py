"""Candle history wider than the snapshot window: explicit, bounded, validated, and uncalled.

No network: every provider response is served by an ``httpx.MockTransport``.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest

from crypto_probability_engine.adapters import candle_history
from crypto_probability_engine.adapters.candle_history import (
    CANDLE_HISTORY_MAX_BARS,
    CandleHistory,
    assert_history_extends_snapshot,
    fetch_binance_candle_history,
    fetch_okx_candle_history,
    validate_candle_history,
)
from crypto_probability_engine.adapters.http_client import PublicHttpClient
from crypto_probability_engine.adapters.public_market import BinancePublicAdapter, OkxPublicAdapter
from crypto_probability_engine.adapters.types import ProviderError
from crypto_probability_engine.api.schemas import ErrorCode
from crypto_probability_engine.config.defaults import TIMEFRAME_SECONDS, min_history_for
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.normalizers.symbols import normalize_symbol
from crypto_probability_engine.validation.market_data import DataValidationError

ROOT = Path(__file__).resolve().parents[2]
BTC = normalize_symbol("BTC")


def _client(handler) -> PublicHttpClient:
    return PublicHttpClient(
        timeout_seconds=8.0,
        max_retries=0,
        rate_limit_per_min=60,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep_func=lambda _: None,
    )


def _millis(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def _series(count: int, timeframe: str) -> list[dict[str, Any]]:
    """``count`` adjacent bars ending with the bar in progress now, oldest first."""

    seconds = TIMEFRAME_SECONDS[timeframe]
    now = datetime.now(UTC)
    current_open = datetime.fromtimestamp(
        (int(now.timestamp()) // seconds) * seconds, tz=UTC
    )
    start = current_open - timedelta(seconds=(count - 1) * seconds)
    bars = []
    for index in range(count):
        open_time = start + timedelta(seconds=index * seconds)
        base = 100.0 + index * 0.1
        bars.append(
            {
                "open_ms": _millis(open_time),
                "close_ms": _millis(open_time + timedelta(seconds=seconds)) - 1,
                "open": base,
                "high": base + 1.0,
                "low": base - 1.0,
                "close": base + 0.05,
                "volume": 1000.0 + index,
                "in_progress": index == count - 1,
            }
        )
    return bars


def _binance_rows(bars: list[dict[str, Any]]) -> list[list[Any]]:
    return [
        [
            bar["open_ms"],
            str(bar["open"]),
            str(bar["high"]),
            str(bar["low"]),
            str(bar["close"]),
            str(bar["volume"]),
            bar["close_ms"],
            "0",
            0,
            "0",
            "0",
            "0",
        ]
        for bar in bars
    ]


def _okx_row(bar: dict[str, Any], *, close: float | None = None) -> list[str]:
    return [
        str(bar["open_ms"]),
        str(bar["open"]),
        str(bar["high"]),
        str(bar["low"]),
        str(bar["close"] if close is None else close),
        str(bar["volume"]),
        "0",
        "0",
        "0" if bar["in_progress"] else "1",
    ]


def _okx_pager(bars: list[dict[str, Any]], seen: list[dict[str, str]], *, page: int = 300):
    """Serve OKX's documented paging: newest first, ``after`` = strictly older than ts."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "www.okx.com"
        assert request.url.path == "/api/v5/market/candles"
        params = dict(request.url.params)
        seen.append(params)
        limit = int(params["limit"])
        after = int(params["after"]) if "after" in params else None
        older = [bar for bar in bars if after is None or bar["open_ms"] < after]
        rows = [_okx_row(bar) for bar in reversed(older)][: min(limit, page)]
        return httpx.Response(200, json={"code": "0", "data": rows})

    return handler


# --------------------------------------------------------------------------- the legacy window


@pytest.mark.parametrize("timeframe", ["15m", "1H", "4H", "1D", "1W", "1M"])
def test_the_snapshot_request_is_unchanged_for_both_providers(timeframe: str) -> None:
    """The methodology-neutral promise: the snapshot still asks for exactly min_history + 5."""

    seen: dict[str, dict[str, str]] = {}
    bars = _series(min_history_for(timeframe) + 5, timeframe)

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if request.url.path == "/api/v3/klines":
            seen["binance"] = params
            return httpx.Response(200, json=_binance_rows(bars))
        if request.url.path == "/api/v5/market/candles":
            seen["okx"] = params
            rows = [_okx_row(bar) for bar in reversed(bars)]
            return httpx.Response(200, json={"code": "0", "data": rows})
        if request.url.path == "/api/v3/depth":
            return httpx.Response(200, json={"bids": [["99", "1"]], "asks": [["101", "1"]]})
        if request.url.path == "/api/v5/market/books":
            book = {"bids": [["99", "1", "0", "1"]], "asks": [["101", "1", "0", "1"]]}
            return httpx.Response(200, json={"code": "0", "data": [book]})
        return httpx.Response(404)

    settings = Settings(data_mode="live")
    for adapter in (
        BinancePublicAdapter(settings=settings, http_client=_client(handler)),
        OkxPublicAdapter(settings=settings, http_client=_client(handler)),
    ):
        snapshot = adapter.fetch_market_snapshot(BTC, timeframe)
        assert len(snapshot.candles) == min_history_for(timeframe) + 4
    assert seen["binance"]["limit"] == str(min_history_for(timeframe) + 5)
    assert seen["okx"]["limit"] == str(min_history_for(timeframe) + 5)
    assert "after" not in seen["okx"]


def test_no_production_path_calls_the_history_capability() -> None:
    """Zero behaviour change: the first caller is a future, owner-authorized wiring."""

    package = ROOT / "src" / "crypto_probability_engine"
    callers = sorted(
        str(path.relative_to(package))
        for path in package.rglob("*.py")
        if "candle_history" in path.read_text(encoding="utf-8")
    )
    assert callers == ["adapters/candle_history.py", "adapters/public_market.py"]


# --------------------------------------------------------------------------- request bounds


@pytest.mark.parametrize(
    ("timeframe", "bars"),
    [
        ("15m", 0),
        ("15m", CANDLE_HISTORY_MAX_BARS + 1),
        ("15m", True),
        ("15m", 700.0),
        ("15m", "700"),
        ("1D", 100),
        ("1M", 100),
        ("15M", 100),
    ],
)
def test_a_request_outside_the_capability_refuses_before_any_network(
    timeframe: str, bars: object
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request may be sent")

    for fetch in (fetch_binance_candle_history, fetch_okx_candle_history):
        with pytest.raises(ValueError):
            fetch(_client(handler), BTC, timeframe, bars=bars)  # type: ignore[arg-type]


def test_the_cap_stays_inside_the_measured_provider_depth() -> None:
    """Measured 2026-09-15: Binance 1000 rows per request; OKX three pages of 300, 900 rows."""

    assert CANDLE_HISTORY_MAX_BARS + 1 <= 1000
    assert -(-(CANDLE_HISTORY_MAX_BARS + 1) // candle_history.OKX_CANDLES_PAGE_LIMIT) <= 3
    assert CANDLE_HISTORY_MAX_BARS >= 700, "distributional-v2 15m needs 673; R2 recommends 700"


# --------------------------------------------------------------------------- Binance


def test_binance_history_is_one_request_that_drops_the_bar_in_progress() -> None:
    seen: list[dict[str, str]] = []
    bars = _series(1000, "15m")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "data-api.binance.vision"
        assert request.url.path == "/api/v3/klines"
        params = dict(request.url.params)
        seen.append(params)
        return httpx.Response(200, json=_binance_rows(bars[-int(params["limit"]) :]))

    history = fetch_binance_candle_history(_client(handler), BTC, "15m", bars=700)

    assert seen == [{"symbol": "BTCUSDT", "interval": "15m", "limit": "701"}]
    assert history.requests == 1 and history.requested_bars == 700
    assert len(history.candles) == 700
    assert history.provider == "binance" and history.normalized_symbol == "BTC/USDT"
    assert _millis(history.candles[-1].open_time_utc) == bars[-2]["open_ms"]
    assert all(
        later.open_time_utc == earlier.close_time_utc
        for earlier, later in zip(history.candles, history.candles[1:], strict=False)
    )
    validate_candle_history(history)


@pytest.mark.parametrize("bars", [1, CANDLE_HISTORY_MAX_BARS])
def test_binance_history_at_both_edges_of_the_bound_is_exact(bars: int) -> None:
    series = _series(1000, "15m")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_binance_rows(series[-int(request.url.params["limit"]) :]))

    history = fetch_binance_candle_history(_client(handler), BTC, "15m", bars=bars)
    assert len(history.candles) == bars and history.requests == 1
    assert _millis(history.candles[-1].open_time_utc) == series[-2]["open_ms"]
    validate_candle_history(history)


def test_binance_history_shorter_than_requested_fails_closed() -> None:
    bars = _series(400, "15m")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_binance_rows(bars))

    with pytest.raises(ProviderError) as refused:
        fetch_binance_candle_history(_client(handler), BTC, "15m", bars=700)
    assert refused.value.code == "INSUFFICIENT_DATA"


def test_a_binance_history_with_a_gap_fails_validation() -> None:
    bars = _series(702, "15m")
    del bars[300]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_binance_rows(bars))

    with pytest.raises(DataValidationError, match="adjacent"):
        fetch_binance_candle_history(_client(handler), BTC, "15m", bars=700)


def test_a_provider_http_error_propagates_as_a_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"msg": "unavailable"})

    with pytest.raises(ProviderError):
        fetch_binance_candle_history(_client(handler), BTC, "4H", bars=100)


# --------------------------------------------------------------------------- OKX


def test_okx_history_pages_strictly_older_and_stops_at_the_bound() -> None:
    seen: list[dict[str, str]] = []
    bars = _series(1200, "15m")
    history = fetch_okx_candle_history(_client(_okx_pager(bars, seen)), BTC, "15m", bars=800)

    assert [params.get("after") for params in seen] == [
        None,
        str(bars[-300]["open_ms"]),
        str(bars[-600]["open_ms"]),
    ]
    assert all(params["limit"] == "300" and params["instId"] == "BTC-USDT" for params in seen)
    assert history.requests == 3 and len(history.candles) == 800
    assert _millis(history.candles[-1].open_time_utc) == bars[-2]["open_ms"], "unconfirmed dropped"
    assert _millis(history.candles[0].open_time_utc) == bars[-801]["open_ms"]
    validate_candle_history(history)


def test_okx_history_asks_for_no_more_pages_than_it_needs() -> None:
    seen: list[dict[str, str]] = []
    bars = _series(1200, "1H")
    history = fetch_okx_candle_history(_client(_okx_pager(bars, seen)), BTC, "1H", bars=250)
    assert len(seen) == 1 and history.requests == 1 and len(history.candles) == 250


def test_okx_history_that_runs_out_of_depth_fails_closed() -> None:
    bars = _series(350, "15m")
    with pytest.raises(ProviderError) as refused:
        fetch_okx_candle_history(_client(_okx_pager(bars, [])), BTC, "15m", bars=700)
    assert refused.value.code == "INSUFFICIENT_DATA"


def test_okx_history_with_short_pages_stops_at_the_request_bound() -> None:
    seen: list[dict[str, str]] = []
    bars = _series(1200, "15m")
    with pytest.raises(ProviderError) as refused:
        fetch_okx_candle_history(_client(_okx_pager(bars, seen, page=200)), BTC, "15m", bars=800)
    assert refused.value.code == "INSUFFICIENT_DATA"
    assert len(seen) == 3, "never more requests than the bound"


def test_an_okx_page_that_does_not_move_older_fails_closed() -> None:
    bars = _series(1200, "15m")

    def handler(request: httpx.Request) -> httpx.Response:
        rows = [_okx_row(bar) for bar in reversed(bars)][:300]
        return httpx.Response(200, json={"code": "0", "data": rows})

    with pytest.raises(ProviderError) as refused:
        fetch_okx_candle_history(_client(handler), BTC, "15m", bars=700)
    assert refused.value.code == "SCHEMA_VALIDATION_FAILED"


def test_an_okx_page_that_reports_one_candle_two_ways_fails_closed() -> None:
    bars = _series(1200, "15m")

    def handler(request: httpx.Request) -> httpx.Response:
        rows = [_okx_row(bar) for bar in reversed(bars)][:300]
        rows.append(_okx_row(bars[-150], close=bars[-150]["close"] + 0.01))
        return httpx.Response(200, json={"code": "0", "data": rows})

    with pytest.raises(ProviderError) as refused:
        fetch_okx_candle_history(_client(handler), BTC, "15m", bars=250)
    assert refused.value.code == "DATA_CONFLICT"


def test_an_okx_status_error_on_a_later_page_fails_closed() -> None:
    bars = _series(1200, "15m")
    pager = _okx_pager(bars, [])

    def handler(request: httpx.Request) -> httpx.Response:
        if "after" in request.url.params:
            return httpx.Response(200, json={"code": "50011", "data": []})
        return pager(request)

    with pytest.raises(ProviderError):
        fetch_okx_candle_history(_client(handler), BTC, "15m", bars=700)


# --------------------------------------------------------------------------- validation


def _history(bars: int = 300, timeframe: str = "4H", **changes: Any) -> CandleHistory:
    series = _series(bars + 1, timeframe)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_binance_rows(series))

    history = fetch_binance_candle_history(_client(handler), BTC, timeframe, bars=bars)
    return replace(history, **changes)


def test_a_history_must_hold_exactly_the_requested_bars() -> None:
    history = _history()
    with pytest.raises(DataValidationError) as refused:
        validate_candle_history(replace(history, candles=history.candles[1:]))
    assert refused.value.code == ErrorCode.INSUFFICIENT_DATA


@pytest.mark.parametrize("defect", ["duplicate", "high-below-close", "naive-time", "non-utc-time"])
def test_a_malformed_history_fails_validation(defect: str) -> None:
    history = _history()
    candles = list(history.candles)
    if defect == "duplicate":
        candles[100] = candles[99]
    elif defect == "high-below-close":
        candles[100] = replace(candles[100], high=candles[100].close * 0.99)
    elif defect == "naive-time":
        candles[100] = replace(
            candles[100], open_time_utc=candles[100].open_time_utc.replace(tzinfo=None)
        )
    else:
        seven = timezone(timedelta(hours=7))
        candles[100] = replace(
            candles[100],
            open_time_utc=candles[100].open_time_utc.astimezone(seven),
            close_time_utc=candles[100].close_time_utc.astimezone(seven),
        )
    with pytest.raises(DataValidationError):
        validate_candle_history(replace(history, candles=tuple(candles)))


def test_a_stale_or_future_history_fails_validation() -> None:
    history = _history()
    stale_now = history.as_of_utc + timedelta(hours=12)
    with pytest.raises(DataValidationError) as stale:
        validate_candle_history(history, now_utc=stale_now)
    assert stale.value.code == ErrorCode.STALE_CANDLES
    early_now = history.candles[-1].close_time_utc - timedelta(minutes=1)
    with pytest.raises(DataValidationError, match="future"):
        validate_candle_history(history, now_utc=early_now)


# --------------------------------------------------------------------------- the snapshot link


def _snapshot_and_history(timeframe: str = "15m"):
    series = _series(900, timeframe)

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if request.url.path == "/api/v3/klines":
            return httpx.Response(200, json=_binance_rows(series[-int(params["limit"]) :]))
        if request.url.path == "/api/v3/depth":
            return httpx.Response(200, json={"bids": [["99", "1"]], "asks": [["101", "1"]]})
        return httpx.Response(404)

    adapter = BinancePublicAdapter(
        settings=Settings(data_mode="live"), http_client=_client(handler)
    )
    snapshot = adapter.fetch_market_snapshot(BTC, timeframe)
    history = adapter.fetch_candle_history(BTC, timeframe, bars=700)
    return snapshot, history


def test_a_history_from_the_same_series_extends_the_snapshot() -> None:
    snapshot, history = _snapshot_and_history()
    assert len(snapshot.candles) == min_history_for("15m") + 4
    assert_history_extends_snapshot(history, snapshot)
    assert history.candles[-len(snapshot.candles) :] == snapshot.candles


@pytest.mark.parametrize("change", ["provider", "symbol", "timeframe"])
def test_a_history_of_another_series_is_refused(change: str) -> None:
    snapshot, history = _snapshot_and_history()
    other = {
        "provider": {"provider": "okx"},
        "symbol": {"normalized_symbol": "ETH/USDT"},
        "timeframe": {"timeframe": "1H"},
    }[change]
    with pytest.raises(DataValidationError) as refused:
        assert_history_extends_snapshot(replace(history, **other), snapshot)
    assert refused.value.code == ErrorCode.DATA_CONFLICT


def test_a_history_that_ends_elsewhere_or_disagrees_on_a_shared_candle_is_refused() -> None:
    snapshot, history = _snapshot_and_history()
    with pytest.raises(DataValidationError, match="same closed candle"):
        assert_history_extends_snapshot(replace(history, candles=history.candles[:-1]), snapshot)
    changed = list(snapshot.candles)
    changed[50] = replace(changed[50], close=changed[50].close + 0.5)
    with pytest.raises(DataValidationError, match="shared candle"):
        assert_history_extends_snapshot(history, replace(snapshot, candles=tuple(changed)))
    volume_only = list(snapshot.candles)
    volume_only[50] = replace(volume_only[50], volume=volume_only[50].volume + 1.0)
    with pytest.raises(DataValidationError, match="shared candle"):
        assert_history_extends_snapshot(history, replace(snapshot, candles=tuple(volume_only)))
