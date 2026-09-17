"""distributional-v2 on live candles. PREP ONLY: NOT WIRED, NOT FROZEN, NOT A METHODOLOGY VERSION.

WHERE THE CANDLES COME FROM, and why the wider history is used only for 15m. v2 needs a full run of
closed candles: 673 on 15m, 169 on 1H, 43 on 4H (R2 §6). A market snapshot carries
``min_history_for(timeframe) + 5`` requested rows, 204 closed candles on every timeframe. That run
is left exactly as it is, because the deployed methodology reads all of it.
- **1H and 4H** are served from the snapshot the rest of the analysis saw, with no extra request.
  A snapshot too short for them fails closed; it never falls back to another source.
- **15m** is the only cell that needs more. It fetches exactly 673 closed candles through the
  candle-history capability (``adapters/candle_history.py``):
  - from the snapshot's own provider;
  - validated like a snapshot;
  - proven to end at the snapshot's last closed candle and to agree with every candle the two
    share (``assert_history_extends_snapshot``).
  If a bar closes between the snapshot and the history request, the two no longer end together,
  and the request fails closed. It is not silently realigned.

Nothing imports this module. Wiring v2 into ``quant/pipeline.py`` and ``api/analysis_service.py``
is the owner's decision (docs/DISTRIBUTIONAL_V2_PREP.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from crypto_probability_engine.adapters.candle_history import (
    CandleHistoryAdapter,
    assert_history_extends_snapshot,
)
from crypto_probability_engine.adapters.types import MarketCandle, MarketSnapshot
from crypto_probability_engine.api.schemas import ErrorCode
from crypto_probability_engine.config.defaults import min_history_for
from crypto_probability_engine.normalizers.symbols import NormalizedSymbol
from crypto_probability_engine.quant.distributional_v2_tables import REQUIRED_CANDLES
from crypto_probability_engine.quant.probability_distributional_v2 import (
    SUPPORTED_SYMBOLS,
    DistributionalV2Probability,
    compute_distributional_v2_probabilities,
)
from crypto_probability_engine.validation.market_data import DataValidationError

SOURCE_SNAPSHOT = "snapshot"
SOURCE_HISTORY = "history"
# The closed candles a snapshot carries: the requested rows less the one still in progress.
SNAPSHOT_CLOSED_CANDLES = {
    timeframe: min_history_for(timeframe) + 5 - 1 for timeframe in REQUIRED_CANDLES
}
# Exactly the timeframes whose v2 window is longer than the snapshot's.
HISTORY_TIMEFRAMES = frozenset(
    timeframe
    for timeframe, required in REQUIRED_CANDLES.items()
    if required > SNAPSHOT_CLOSED_CANDLES[timeframe]
)


@dataclass(frozen=True)
class DistributionalV2Serving:
    """A v2 triplet and where its window came from."""

    probability: DistributionalV2Probability
    candle_source: str
    provider: str
    history_requests: int
    window_first_open_utc: datetime
    window_last_open_utc: datetime


def serve_distributional_v2(
    snapshot: MarketSnapshot,
    *,
    symbol: NormalizedSymbol,
    band_frac: float,
    history_adapter: CandleHistoryAdapter | None = None,
) -> DistributionalV2Serving:
    """v2 for the snapshot's symbol and timeframe, from exactly the window it requires."""

    timeframe = snapshot.timeframe
    if timeframe not in REQUIRED_CANDLES or snapshot.normalized_symbol not in SUPPORTED_SYMBOLS:
        raise ValueError(
            f"distributional-v2 does not serve {snapshot.normalized_symbol!r} {timeframe!r}"
        )
    if symbol.display != snapshot.normalized_symbol:
        raise ValueError(
            f"the symbol {symbol.display!r} is not the snapshot's {snapshot.normalized_symbol!r}"
        )
    required = REQUIRED_CANDLES[timeframe]
    if timeframe in HISTORY_TIMEFRAMES:
        window, requests = _history_window(snapshot, symbol, required, history_adapter)
        source = SOURCE_HISTORY
    else:
        if len(snapshot.candles) < required:
            raise DataValidationError(
                ErrorCode.INSUFFICIENT_DATA,
                f"distributional-v2 {timeframe} needs {required} closed candles from the "
                f"snapshot, which holds {len(snapshot.candles)}.",
            )
        window, requests = tuple(snapshot.candles[-required:]), 0
        source = SOURCE_SNAPSHOT
    probability = compute_distributional_v2_probabilities(
        window, symbol=snapshot.normalized_symbol, timeframe=timeframe, band_frac=band_frac
    )
    return DistributionalV2Serving(
        probability=probability,
        candle_source=source,
        provider=snapshot.provider,
        history_requests=requests,
        window_first_open_utc=window[0].open_time_utc,
        window_last_open_utc=window[-1].open_time_utc,
    )


def _history_window(
    snapshot: MarketSnapshot,
    symbol: NormalizedSymbol,
    required: int,
    adapter: CandleHistoryAdapter | None,
) -> tuple[tuple[MarketCandle, ...], int]:
    if adapter is None:
        raise ValueError(
            f"distributional-v2 {snapshot.timeframe} needs the candle-history capability"
        )
    if adapter.name != snapshot.provider:
        raise DataValidationError(
            ErrorCode.DATA_CONFLICT,
            "The candle history would come from another provider than the snapshot.",
        )
    history = adapter.fetch_candle_history(symbol, snapshot.timeframe, bars=required)
    if len(history.candles) != required or history.requested_bars != required:
        raise DataValidationError(
            ErrorCode.INSUFFICIENT_DATA,
            "The candle history does not hold exactly the window distributional-v2 needs.",
        )
    assert_history_extends_snapshot(history, snapshot)
    return history.candles, history.requests
