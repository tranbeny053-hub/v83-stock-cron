"""distributional-v2 on live candles: the snapshot for 1H and 4H, the wider history only for 15m.

No network. The history adapter is a fake that records every request. Synthetic candles are the
golden test's deterministic series.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from crypto_probability_engine.adapters.candle_history import CandleHistory
from crypto_probability_engine.adapters.types import MarketSnapshot, ProviderError
from crypto_probability_engine.api.schemas import ErrorCode
from crypto_probability_engine.normalizers.symbols import normalize_symbol
from crypto_probability_engine.quant import distributional_v2_serving as serving
from crypto_probability_engine.quant.distributional_v2_tables import REQUIRED_CANDLES
from crypto_probability_engine.quant.probability_distributional_v2 import (
    compute_distributional_v2_probabilities,
)
from crypto_probability_engine.validation.market_data import DataValidationError
from tests.quant._distributional_v2_synthetic import (
    BAR_SECONDS,
    epoch_seconds,
    synthetic_candles,
)

ROOT = Path(__file__).resolve().parents[2]
BTC = normalize_symbol("BTC")
ETH = normalize_symbol("ETH")
LAST_OPEN = {
    "15m": "2025-03-12T13:45:00Z",
    "1H": "2025-03-12T13:00:00Z",
    "4H": "2025-03-12T12:00:00Z",
}
BAND = 0.002


def _series(timeframe: str, count: int, *, seed: int = 11):
    return synthetic_candles(
        timeframe,
        last_open_seconds=epoch_seconds(LAST_OPEN[timeframe]),
        count=count,
        seed=seed,
    )


def _snapshot(timeframe: str, *, symbol: str = "BTC/USDT", provider: str = "okx", candles=None):
    candles = _series(timeframe, 204) if candles is None else candles
    return MarketSnapshot(
        provider=provider,
        normalized_symbol=symbol,
        timeframe=timeframe,
        candles=tuple(candles),
        order_book=None,
        as_of_utc=datetime(2025, 3, 12, 14, 0, tzinfo=UTC),
    )


class FakeHistory:
    """A candle-history adapter that serves one prepared series and records each request."""

    def __init__(self, name: str, candles, *, requests: int = 3, error: Exception | None = None):
        self.name = name
        self.candles = tuple(candles)
        self.request_count = requests
        self.error = error
        self.calls: list[tuple[str, str, int]] = []

    def fetch_candle_history(self, symbol, timeframe: str, *, bars: int) -> CandleHistory:
        self.calls.append((symbol.display, timeframe, bars))
        if self.error is not None:
            raise self.error
        return CandleHistory(
            provider=self.name,
            normalized_symbol=symbol.display,
            timeframe=timeframe,
            requested_bars=bars,
            candles=self.candles[-bars:],
            as_of_utc=datetime(2025, 3, 12, 14, 0, tzinfo=UTC),
            requests=self.request_count,
        )


def test_only_15m_needs_more_than_the_snapshot_carries() -> None:
    assert serving.SNAPSHOT_CLOSED_CANDLES == {"15m": 204, "1H": 204, "4H": 204}
    assert REQUIRED_CANDLES == {"15m": 673, "1H": 169, "4H": 43}
    assert serving.HISTORY_TIMEFRAMES == frozenset({"15m"})


@pytest.mark.parametrize("timeframe", ["1H", "4H"])
def test_1h_and_4h_are_served_from_the_snapshot_without_a_request(timeframe: str) -> None:
    snapshot = _snapshot(timeframe)
    adapter = FakeHistory("okx", _series(timeframe, 800))
    served = serving.serve_distributional_v2(
        snapshot, symbol=BTC, band_frac=BAND, history_adapter=adapter
    )
    assert adapter.calls == []
    required = REQUIRED_CANDLES[timeframe]
    expected = compute_distributional_v2_probabilities(
        snapshot.candles[-required:], symbol="BTC/USDT", timeframe=timeframe, band_frac=BAND
    )
    assert served.probability == expected
    assert served.candle_source == serving.SOURCE_SNAPSHOT and served.history_requests == 0
    assert served.provider == "okx"
    assert served.window_first_open_utc == snapshot.candles[-required].open_time_utc
    assert served.window_last_open_utc == snapshot.candles[-1].open_time_utc
    # The adapter is optional where it is not needed.
    alone = serving.serve_distributional_v2(snapshot, symbol=BTC, band_frac=BAND)
    assert alone.probability == expected


def test_15m_fetches_exactly_its_window_once_from_the_snapshot_s_provider() -> None:
    history = _series("15m", 673)
    snapshot = _snapshot("15m", candles=history[-204:], provider="binance")
    adapter = FakeHistory("binance", history, requests=1)
    served = serving.serve_distributional_v2(
        snapshot, symbol=BTC, band_frac=BAND, history_adapter=adapter
    )
    assert adapter.calls == [("BTC/USDT", "15m", 673)]
    expected = compute_distributional_v2_probabilities(
        history, symbol="BTC/USDT", timeframe="15m", band_frac=BAND
    )
    assert served.probability == expected
    assert served.probability.candles_used == 673
    assert served.candle_source == serving.SOURCE_HISTORY and served.history_requests == 1
    assert served.window_first_open_utc == history[0].open_time_utc
    assert served.window_last_open_utc == snapshot.candles[-1].open_time_utc


def test_15m_without_the_history_capability_refuses() -> None:
    history = _series("15m", 673)
    with pytest.raises(ValueError, match="candle-history capability"):
        serving.serve_distributional_v2(
            _snapshot("15m", candles=history[-204:]), symbol=BTC, band_frac=BAND
        )


def test_15m_never_mixes_providers_and_asks_nothing_of_the_other_one() -> None:
    history = _series("15m", 673)
    adapter = FakeHistory("binance", history)
    with pytest.raises(DataValidationError) as refused:
        serving.serve_distributional_v2(
            _snapshot("15m", candles=history[-204:], provider="okx"),
            symbol=BTC,
            band_frac=BAND,
            history_adapter=adapter,
        )
    assert refused.value.code == ErrorCode.DATA_CONFLICT
    assert adapter.calls == []


def test_a_bar_that_closed_between_snapshot_and_history_fails_closed() -> None:
    later = _series("15m", 674)
    snapshot = _snapshot("15m", candles=later[-205:-1])
    adapter = FakeHistory("okx", later)
    with pytest.raises(DataValidationError) as refused:
        serving.serve_distributional_v2(
            snapshot, symbol=BTC, band_frac=BAND, history_adapter=adapter
        )
    assert refused.value.code == ErrorCode.DATA_CONFLICT


def test_a_history_that_disagrees_on_a_shared_candle_fails_closed() -> None:
    history = list(_series("15m", 673))
    snapshot = _snapshot("15m", candles=tuple(history[-204:]))
    history[-10] = replace(history[-10], volume=history[-10].volume + 1.0)
    adapter = FakeHistory("okx", history)
    with pytest.raises(DataValidationError) as refused:
        serving.serve_distributional_v2(
            snapshot, symbol=BTC, band_frac=BAND, history_adapter=adapter
        )
    assert refused.value.code == ErrorCode.DATA_CONFLICT


def test_a_history_that_is_not_exactly_the_window_fails_closed() -> None:
    history = _series("15m", 672)
    adapter = FakeHistory("okx", history)
    with pytest.raises(DataValidationError) as refused:
        serving.serve_distributional_v2(
            _snapshot("15m", candles=history[-204:]),
            symbol=BTC,
            band_frac=BAND,
            history_adapter=adapter,
        )
    assert refused.value.code == ErrorCode.INSUFFICIENT_DATA


def test_a_provider_failure_propagates_unchanged() -> None:
    history = _series("15m", 673)
    error = ProviderError("INSUFFICIENT_DATA", "OKX history is short.", provider="okx")
    adapter = FakeHistory("okx", history, error=error)
    with pytest.raises(ProviderError) as raised:
        serving.serve_distributional_v2(
            _snapshot("15m", candles=history[-204:]),
            symbol=BTC,
            band_frac=BAND,
            history_adapter=adapter,
        )
    assert raised.value is error


@pytest.mark.parametrize(
    ("symbol", "timeframe"),
    [("SOL/USDT", "1H"), ("BTC/USDT", "1D"), ("BTC/USDT", "1W")],
)
def test_unsupported_cells_refuse_before_any_request(symbol: str, timeframe: str) -> None:
    candles = _series("1H", 204)
    snapshot = replace(
        _snapshot("1H", candles=candles), normalized_symbol=symbol, timeframe=timeframe
    )
    adapter = FakeHistory("okx", candles)
    with pytest.raises(ValueError, match="does not serve"):
        serving.serve_distributional_v2(
            snapshot,
            symbol=normalize_symbol(symbol.split("/")[0]),
            band_frac=BAND,
            history_adapter=adapter,
        )
    assert adapter.calls == []


def test_the_symbol_must_be_the_snapshot_s() -> None:
    with pytest.raises(ValueError, match="not the snapshot"):
        serving.serve_distributional_v2(_snapshot("1H"), symbol=ETH, band_frac=BAND)


def test_a_short_1h_snapshot_fails_closed_and_never_falls_back_to_history() -> None:
    candles = _series("1H", 168)
    adapter = FakeHistory("okx", _series("1H", 800))
    with pytest.raises(DataValidationError) as refused:
        serving.serve_distributional_v2(
            _snapshot("1H", candles=candles), symbol=BTC, band_frac=BAND, history_adapter=adapter
        )
    assert refused.value.code == ErrorCode.INSUFFICIENT_DATA
    assert adapter.calls == []


def test_v2_s_own_refusals_still_apply_to_the_served_window() -> None:
    with pytest.raises(ValueError, match="non-negative band"):
        serving.serve_distributional_v2(_snapshot("4H"), symbol=BTC, band_frac=-0.001)
    gapped = list(_series("4H", 204))
    gapped[-5] = replace(
        gapped[-5],
        open_time_utc=gapped[-5].open_time_utc.replace(minute=30),
    )
    with pytest.raises(ValueError, match="distributional-v2"):
        serving.serve_distributional_v2(_snapshot("4H", candles=gapped), symbol=BTC, band_frac=BAND)


def test_every_supported_cell_is_servable() -> None:
    for symbol in (BTC, ETH):
        for timeframe, required in REQUIRED_CANDLES.items():
            if timeframe in serving.HISTORY_TIMEFRAMES:
                history = _series(timeframe, required, seed=5)
                snapshot = _snapshot(timeframe, symbol=symbol.display, candles=history[-204:])
                adapter = FakeHistory("okx", history)
            else:
                snapshot = _snapshot(timeframe, symbol=symbol.display)
                adapter = None
            served = serving.serve_distributional_v2(
                snapshot, symbol=symbol, band_frac=BAND, history_adapter=adapter
            )
            total = (
                served.probability.p_up_frac
                + served.probability.p_down_frac
                + served.probability.p_timeout_frac
            )
            assert abs(total - 1.0) < 1e-12
            assert (served.window_last_open_utc - served.window_first_open_utc).total_seconds() == (
                (required - 1) * BAR_SECONDS[timeframe]
            )


def test_nothing_wires_the_serving_path_yet() -> None:
    """The adapters' own guard (tests/adapters/test_candle_history.py) owns the caller list."""

    source = ROOT / "src" / "crypto_probability_engine"
    importers = [
        path.relative_to(ROOT).as_posix()
        for path in source.rglob("*.py")
        if "distributional_v2_serving" in path.read_text(encoding="utf-8")
        and path.name != "distributional_v2_serving.py"
    ]
    assert importers == []
