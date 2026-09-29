"""Rows and fakes shared by the Route C tests. No database, no network."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from crypto_probability_engine.adapters.types import MarketCandle
from crypto_probability_engine.resolution.status_store import SCAN_COLUMNS
from crypto_probability_engine.targets import contract_v1

NOW = datetime(2026, 10, 1, 12, 17, tzinfo=UTC)
FOUR_HOURS = timedelta(hours=4)
PROVIDERS = {"BINANCE_PUBLIC": "binance", "OKX_PUBLIC": "okx"}
FILTERS = {
    "venues": ("BINANCE_PUBLIC", "OKX_PUBLIC"),
    "timeframes": ("15m", "1D", "1H", "1W", "4H"),
    "prediction_origins": ("USER_REQUESTED",),
}


def iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def v0_row(pid: str, *, source: str = "BINANCE_PUBLIC", age=timedelta(minutes=5), **overrides):
    """An unstamped live USER_REQUESTED 4H row due at NOW. Its symbol is its id, so a fake
    provider can tell rows apart by the window's normalized_symbol."""

    horizon = NOW - age
    reference = horizon - 6 * FOUR_HOURS
    row = {
        "prediction_id": pid,
        "run_id": f"run_{pid}",
        "operator_id": "operator",
        "symbol": pid,
        "normalized_symbol": pid,
        "timeframe": "4H",
        "horizon_bars": 6,
        "predicted_at_utc": iso(reference + timedelta(seconds=41)),
        "reference_close_utc": iso(reference),
        "reference_price": 100.0,
        "horizon_end_utc": iso(horizon),
        "p_up_frac": 0.35,
        "p_down_frac": 0.25,
        "p_timeout_frac": 0.40,
        "decision_band_frac": 0.003,
        "model_version": "phase1a-wave4b0",
        "methodology_version": "heuristic-v1-wave4b0",
        "calibration_status": "DEFAULT_PHASE1A",
        "reliability_status": "INSUFFICIENT_SAMPLE",
        "epistemic_sufficiency": "SUFFICIENT",
        "gate_action": "WATCH",
        "data_source": source,
        "is_live_data": True,
        "cross_provider_state": "UNAVAILABLE",
        "prediction_origin": "USER_REQUESTED",
    }
    row.update(overrides)
    return row


def tc_row(
    pid: str,
    *,
    venue: str = "OKX_PUBLIC",
    source: str = "CROSS_PROVIDER",
    age=timedelta(minutes=5),
    **overrides,
):
    """A valid tc-v1 row, stamped by the contract itself; ``overrides`` apply after stamping."""

    state = "COHERENT" if source == "CROSS_PROVIDER" else "UNAVAILABLE"
    row = v0_row(pid, source=source, age=age, cross_provider_state=state)
    predicted = parse(row["predicted_at_utc"])
    stamped = contract_v1.stamp_v1(
        row,
        snapshot_provider=PROVIDERS[venue],
        core_computed_at=predicted + timedelta(seconds=1, microseconds=500_000),
        issued_at=predicted + timedelta(seconds=1, microseconds=850_000),
    )
    assert contract_v1.classify_row(stamped) == contract_v1.CLASS_TC_V1, "fixture must be tc-v1"
    stamped.update(overrides)
    return stamped


def db_row(prediction: dict, status: dict | None = None) -> tuple:
    """The due scan's row as psycopg returns it: timestamps as datetimes, NUMERIC as Decimal."""

    values = {**{column: prediction.get(column) for column in SCAN_COLUMNS}, **(status or {})}
    return tuple(_as_db(column, values.get(column)) for column in SCAN_COLUMNS)


def _as_db(column: str, value):
    if isinstance(value, str) and column.endswith("_utc"):
        return parse(value)
    if isinstance(value, float) and column in {
        "reference_price",
        "p_up_frac",
        "p_down_frac",
        "p_timeout_frac",
        "decision_band_frac",
    }:
        return Decimal(str(value))
    return value


def candle(close_time: datetime, *, close: float = 101.0, span=FOUR_HOURS) -> MarketCandle:
    return MarketCandle(
        open_time_utc=close_time - span,
        close_time_utc=close_time,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1.0,
    )


def terminal(window):
    return (candle(window.terminal_close_utc),)


def missing(window):
    return ()


def raising(error):
    def behaviour(window):
        raise error

    return behaviour


class Fetch:
    """A fake provider: the terminal bar, unless a row (by symbol) has another behaviour."""

    def __init__(self, clock=None, *, seconds=0.0, by_symbol=None, default=None):
        self.clock = clock
        self.seconds = seconds
        self.by_symbol = by_symbol or {}
        self.default = default
        self.windows = []

    @property
    def symbols(self):
        return [window.normalized_symbol for window in self.windows]

    def __call__(self, window, settings):
        self.windows.append(window)
        if self.clock is not None:
            self.clock.now += self.seconds
        behaviour = self.by_symbol.get(window.normalized_symbol, self.default)
        return (behaviour or terminal)(window)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class Ledger:
    """A repository fake. Outcomes are first-write-wins, like ON CONFLICT DO NOTHING; share
    ``outcomes`` with an InMemoryStatusStore so its readback sees them. ``stored`` rewrites the
    row actually kept (a concurrent or earlier writer); ``write=False`` keeps nothing."""

    def __init__(self, outcomes, *, status="OK", write=True, stored=None):
        self.outcomes = outcomes
        self.status = status
        self.write = write
        self.stored = stored
        self.saved = []
        self.closed = False

    def fetch_due_unresolved_predictions(self, *args, **kwargs):
        raise AssertionError("Route C never runs the pinned due query")

    def save_prediction_outcome(self, row):
        self.saved.append(dict(row))
        if self.write:
            kept = dict(row) if self.stored is None else self.stored(dict(row))
            self.outcomes.setdefault(row["prediction_id"], kept)
        return self.status

    def repository_type(self):
        return "SYNTHETIC"

    def close(self):
        self.closed = True
