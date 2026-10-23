from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from inspect import getsource

import pytest

from crypto_probability_engine.adapters.candle_history import CandleHistory
from crypto_probability_engine.adapters.types import (
    MarketCandle,
    MarketSnapshot,
    ProviderError,
)
from crypto_probability_engine.normalizers.symbols import normalize_symbol
from crypto_probability_engine.quant_ng.windows import (
    UnavailableReason,
    Window,
    WindowSource,
    WindowUnavailable,
    acquire_window,
    require_well_formed,
)
from crypto_probability_engine.validation.market_data import DataValidationError

BAR = 900
START = datetime(2025, 1, 1, tzinfo=UTC)
SYMBOL = normalize_symbol("BTCUSDT")


def candles(count: int, *, start: datetime = START) -> tuple[MarketCandle, ...]:
    """Build adjacent 15m candles with exact UTC boundaries and positive prices."""
    result = []
    for index in range(count):
        opened = start + timedelta(seconds=BAR * index)
        close = 100.0 + index
        result.append(MarketCandle(
            open_time_utc=opened,
            close_time_utc=opened + timedelta(seconds=BAR),
            open=close,
            high=close + 1,
            low=close - 1,
            close=close + 0.5,
            volume=1.0,
        ))
    return tuple(result)


def snapshot(items: tuple[MarketCandle, ...], *, provider: str = "binance") -> MarketSnapshot:
    return MarketSnapshot(
        provider=provider,
        normalized_symbol=SYMBOL.display,
        timeframe="15m",
        candles=items,
        order_book=None,
        as_of_utc=items[-1].close_time_utc,
    )


class FakeAdapter:
    def __init__(self, result: CandleHistory | Exception) -> None:
        self.result = result
        self.calls: list[tuple[object, str, int]] = []

    def fetch_candle_history(
        self, symbol: object, timeframe: str, *, bars: int
    ) -> CandleHistory:
        self.calls.append((symbol, timeframe, bars))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def history(
    items: tuple[MarketCandle, ...],
    *,
    provider: str = "binance",
    requested_bars: int | None = None,
) -> CandleHistory:
    return CandleHistory(
        provider=provider,
        normalized_symbol=SYMBOL.display,
        timeframe="15m",
        requested_bars=len(items) if requested_bars is None else requested_bars,
        candles=items,
        as_of_utc=items[-1].close_time_utc,
        requests=2,
    )


def assert_reason(reason: UnavailableReason, call: object) -> None:
    with pytest.raises(WindowUnavailable) as error:
        call()  # type: ignore[operator]
    assert error.value.reason is reason
    assert str(error.value).startswith(reason.value)


def test_snapshot_supplies_last_requested_candles_without_adapter_call() -> None:
    items = candles(5)
    adapter = FakeAdapter(history(items))

    result = acquire_window(snapshot(items), symbol=SYMBOL, bars_required=3,
                            history_adapter=adapter)

    assert result.source is WindowSource.SNAPSHOT
    assert result.candles == items[-3:]
    assert result.requests == 0
    assert result.last_close_utc == items[-1].close_time_utc
    assert adapter.calls == []


def test_short_snapshot_uses_one_history_request_and_copies_metadata() -> None:
    items = candles(5)
    adapter = FakeAdapter(history(items))

    result = acquire_window(snapshot(items[-2:]), symbol=SYMBOL, bars_required=5,
                            history_adapter=adapter, now_utc=items[-1].close_time_utc)

    assert result.source is WindowSource.HISTORY
    assert result.candles == items
    assert result.requests == 2
    assert result.provider == "binance"
    assert adapter.calls == [(SYMBOL, "15m", 5)]
    assert len(adapter.calls) <= 1


def test_short_snapshot_without_adapter_is_unavailable() -> None:
    items = candles(1)
    assert_reason(UnavailableReason.SHORT_SNAPSHOT, lambda: acquire_window(
        snapshot(items), symbol=SYMBOL, bars_required=2
    ))


@pytest.mark.parametrize("timeframe,bars", [
    ("1D", 1), ("15m", 0), ("15m", 801), ("15m", True), ("15m", 3.0),
])
def test_request_refusals_precede_history_calls(timeframe: str, bars: object) -> None:
    item = candles(1)
    adapter = FakeAdapter(history(candles(2)))
    snap = replace(snapshot(item), timeframe=timeframe)
    expected = (UnavailableReason.TIMEFRAME_UNSUPPORTED if timeframe == "1D"
                else UnavailableReason.BARS_OUT_OF_RANGE)

    assert_reason(expected, lambda: acquire_window(
        snap, symbol=SYMBOL, bars_required=bars, history_adapter=adapter  # type: ignore[arg-type]
    ))
    assert adapter.calls == []


def test_symbol_mismatch_is_refused_without_history_call() -> None:
    items = candles(1)
    adapter = FakeAdapter(history(candles(2)))
    assert_reason(UnavailableReason.SNAPSHOT_MISMATCH, lambda: acquire_window(
        snapshot(items), symbol=normalize_symbol("ETHUSDT"), bars_required=2,
        history_adapter=adapter,
    ))
    assert adapter.calls == []


@pytest.mark.parametrize("error", [
    ProviderError("FAILED", "provider down", provider="binance"),
    ValueError("bad response"),
    DataValidationError("SCHEMA_VALIDATION_FAILED", "bad history"),
])
def test_adapter_failures_are_mapped_without_retry(error: Exception) -> None:
    item = candles(1)
    adapter = FakeAdapter(error)
    expected = (UnavailableReason.HISTORY_INVALID if isinstance(error, DataValidationError)
                else UnavailableReason.HISTORY_FAILED)
    assert_reason(expected, lambda: acquire_window(
        snapshot(item), symbol=SYMBOL, bars_required=2, history_adapter=adapter
    ))
    assert len(adapter.calls) == 1


def test_wrong_history_count_is_invalid_and_called_once() -> None:
    items = candles(3)
    adapter = FakeAdapter(history(items, requested_bars=4))
    assert_reason(UnavailableReason.HISTORY_INVALID, lambda: acquire_window(
        snapshot(items[-1:]), symbol=SYMBOL, bars_required=4, history_adapter=adapter,
        now_utc=items[-1].close_time_utc,
    ))
    assert len(adapter.calls) == 1


def test_consistently_short_history_is_invalid_and_called_once() -> None:
    items = candles(4)
    adapter = FakeAdapter(history(items[-3:], requested_bars=3))
    assert_reason(UnavailableReason.HISTORY_INVALID, lambda: acquire_window(
        snapshot(items[-1:]), symbol=SYMBOL, bars_required=4, history_adapter=adapter,
        now_utc=items[-1].close_time_utc,
    ))
    assert len(adapter.calls) == 1


def test_plain_validator_value_error_is_mapped_to_history_invalid() -> None:
    items = candles(2)
    invalid = CandleHistory(
        provider="binance",
        normalized_symbol=SYMBOL.display,
        timeframe="1D",
        requested_bars=2,
        candles=items,
        as_of_utc=items[-1].close_time_utc,
        requests=1,
    )
    adapter = FakeAdapter(invalid)
    assert_reason(UnavailableReason.HISTORY_INVALID, lambda: acquire_window(
        snapshot(items[-1:]), symbol=SYMBOL, bars_required=2, history_adapter=adapter,
        now_utc=items[-1].close_time_utc,
    ))
    assert len(adapter.calls) == 1


def test_history_fetch_has_one_source_call_site() -> None:
    assert getsource(acquire_window).count("fetch_candle_history(") == 1


@pytest.mark.parametrize("kind", ["different_end", "shared_candle", "provider"])
def test_history_conflicts_fail_closed(kind: str) -> None:
    snap_items = candles(3)
    if kind == "different_end":
        hist_items = candles(4, start=START + timedelta(seconds=BAR))
        provider = "binance"
    elif kind == "shared_candle":
        hist_items_list = list(candles(4))
        hist_items_list[1] = replace(hist_items_list[1], close=101.25)
        hist_items = tuple(hist_items_list)
        provider = "binance"
    else:
        hist_items = candles(4)
        provider = "okx"
    adapter = FakeAdapter(history(hist_items, provider=provider))
    assert_reason(UnavailableReason.HISTORY_CONFLICT, lambda: acquire_window(
        snapshot(snap_items), symbol=SYMBOL, bars_required=len(hist_items),
        history_adapter=adapter, now_utc=hist_items[-1].close_time_utc,
    ))
    assert len(adapter.calls) == 1


def test_valid_series_and_stale_historical_series_pass_well_formedness() -> None:
    require_well_formed(candles(3), "15m")
    old = candles(3, start=datetime(2010, 1, 1, tzinfo=UTC))
    require_well_formed(old, "15m")


@pytest.mark.parametrize("mutation", [
    "non_utc", "misaligned", "wrong_span", "gap", "out_of_order", "zero_price",
    "infinite_price", "low_above_high",
])
def test_malformed_series_is_refused(mutation: str) -> None:
    items = list(candles(3))
    if mutation == "non_utc":
        items[0] = replace(items[0], open_time_utc=items[0].open_time_utc.astimezone(
            timezone(timedelta(hours=1))
        ))
    elif mutation == "misaligned":
        items[0] = replace(items[0], open_time_utc=items[0].open_time_utc + timedelta(seconds=60),
                           close_time_utc=items[0].close_time_utc + timedelta(seconds=60))
    elif mutation == "wrong_span":
        items[0] = replace(items[0], close_time_utc=items[0].close_time_utc - timedelta(seconds=1))
    elif mutation == "gap":
        items[1] = replace(items[1], open_time_utc=items[1].open_time_utc + timedelta(seconds=BAR),
                           close_time_utc=items[1].close_time_utc + timedelta(seconds=BAR))
    elif mutation == "out_of_order":
        items[1], items[2] = items[2], items[1]
    elif mutation == "zero_price":
        items[0] = replace(items[0], open=0.0)
    elif mutation == "infinite_price":
        items[0] = replace(items[0], high=float("inf"))
    else:
        items[0] = replace(items[0], high=items[0].low - 1)

    assert_reason(UnavailableReason.WINDOW_MALFORMED,
                  lambda: require_well_formed(items, "15m"))


def test_empty_and_unsupported_well_formed_windows_are_refused() -> None:
    assert_reason(UnavailableReason.WINDOW_MALFORMED, lambda: require_well_formed([], "15m"))
    assert_reason(UnavailableReason.TIMEFRAME_UNSUPPORTED,
                  lambda: require_well_formed(candles(1), "1D"))


def test_window_dataclass_refuses_empty_candles() -> None:
    with pytest.raises(ValueError):
        Window("binance", SYMBOL.display, "15m", (), WindowSource.SNAPSHOT, 0)


def test_malformed_snapshot_tail_precedes_available_adapter() -> None:
    items = list(candles(5))
    items[-1] = replace(items[-1], open_time_utc=items[-1].open_time_utc + timedelta(seconds=BAR))
    adapter = FakeAdapter(history(candles(5)))

    assert_reason(UnavailableReason.WINDOW_MALFORMED, lambda: acquire_window(
        snapshot(tuple(items)), symbol=SYMBOL, bars_required=3, history_adapter=adapter
    ))
    assert adapter.calls == []


def test_stale_history_uses_supplied_now_and_calls_adapter_once() -> None:
    stale = candles(3, start=datetime(2010, 1, 1, tzinfo=UTC))
    adapter = FakeAdapter(history(stale))

    assert_reason(UnavailableReason.HISTORY_INVALID, lambda: acquire_window(
        snapshot(candles(1)), symbol=SYMBOL, bars_required=3, history_adapter=adapter,
        now_utc=datetime(2025, 1, 1, tzinfo=UTC),
    ))
    assert len(adapter.calls) == 1
