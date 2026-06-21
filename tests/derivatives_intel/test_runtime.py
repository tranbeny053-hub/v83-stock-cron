from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

import crypto_probability_engine.derivatives_intel.runtime as runtime
from crypto_probability_engine.derivatives_intel.block import build_derivatives_intelligence


class MutableClock:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


class FakeCalls:
    def __init__(self, event_time: datetime) -> None:
        self.event_ms = int(event_time.timestamp() * 1000)
        self.paths: list[str] = []
        self.entered = threading.Event()
        self.release = threading.Event()
        self.block_first_registry = False
        self.fail_binance = False
        self.fail_okx = False
        self.malformed_binance = False
        self.clock: MutableClock | None = None
        self.advance_seconds = 0.0

    def record(self, path: str) -> None:
        self.paths.append(path)
        if self.clock is not None:
            self.clock.value += self.advance_seconds


def install_fake_adapters(monkeypatch: pytest.MonkeyPatch, calls: FakeCalls) -> None:
    class Binance:
        def __init__(self, *, http_client) -> None:
            self.http_client = http_client

        def fetch_exchange_info(self):
            calls.paths.append("/fapi/v1/exchangeInfo")
            if calls.block_first_registry:
                calls.entered.set()
                assert calls.release.wait(timeout=2)
            if calls.clock is not None:
                calls.clock.value += calls.advance_seconds
            return {
                "symbols": [
                    {
                        "symbol": "BTCUSDT",
                        "status": "TRADING",
                        "contractType": "PERPETUAL",
                        "quoteAsset": "USDT",
                        "marginAsset": "USDT",
                    }
                ]
            }

        def fetch_current_funding(self, symbol):
            calls.record("/fapi/v1/premiumIndex")
            if calls.fail_binance:
                raise RuntimeError("fixture failure")
            if calls.malformed_binance:
                return {}
            return {
                "symbol": symbol,
                "lastFundingRate": "-0.0001",
                "time": calls.event_ms,
                "unexpectedField": "not cached",
            }

        def fetch_current_open_interest(self, symbol):
            calls.record("/fapi/v1/openInterest")
            if calls.fail_binance:
                raise RuntimeError("fixture failure")
            if calls.malformed_binance:
                return {}
            return {"symbol": symbol, "openInterest": "120", "time": calls.event_ms}

    class Okx:
        def __init__(self, *, http_client) -> None:
            self.http_client = http_client

        def fetch_instruments(self):
            calls.record("/api/v5/public/instruments")
            return [
                {
                    "instId": "BTC-USDT-SWAP",
                    "instType": "SWAP",
                    "settleCcy": "USDT",
                    "ctType": "linear",
                    "state": "live",
                    "ctVal": "0.01",
                    "ctMult": "1",
                }
            ]

        def fetch_current_funding(self, inst_id):
            calls.record("/api/v5/public/funding-rate")
            if calls.fail_okx:
                raise RuntimeError("fixture failure")
            return [{"instId": inst_id, "fundingRate": "0.0002", "ts": str(calls.event_ms)}]

        def fetch_current_open_interest(self, inst_id):
            calls.record("/api/v5/public/open-interest")
            if calls.fail_okx:
                raise RuntimeError("fixture failure")
            return [
                {
                    "instId": inst_id,
                    "instType": "SWAP",
                    "oi": "40",
                    "oiCcy": "0.4",
                    "oiUsd": "26000",
                    "ts": str(calls.event_ms),
                }
            ]

    monkeypatch.setattr(runtime, "BinanceUsdmDerivativesAdapter", Binance)
    monkeypatch.setattr(runtime, "OkxSwapDerivativesAdapter", Okx)


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    runtime.clear_runtime_caches()
    yield
    runtime.clear_runtime_caches()


def test_cold_warm_and_registry_warm_call_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    event = datetime(2026, 6, 22, 0, tzinfo=UTC)
    calls = FakeCalls(event)
    install_fake_adapters(monkeypatch, calls)

    def now() -> datetime:
        return event + timedelta(seconds=1)

    clock = MutableClock()

    first = runtime.get_raw_derivatives_bundle(
        "BTC/USDT", http_client=object(), monotonic_func=clock, utc_now_func=now
    )
    assert len(first.providers) == 2
    assert len(calls.paths) == 6
    assert "unexpectedField" not in dict(first.providers[0].funding_payload or ())

    for _ in range(5):
        runtime.get_raw_derivatives_bundle(
            "BTC/USDT", http_client=object(), monotonic_func=clock, utc_now_func=now
        )
    assert len(calls.paths) == 6

    with runtime._CACHE_GUARD:
        runtime._SYMBOL_CACHE.clear()
    runtime.get_raw_derivatives_bundle(
        "BTC/USDT", http_client=object(), monotonic_func=clock, utc_now_func=now
    )
    assert len(calls.paths) == 10
    assert not any("history" in path.lower() for path in calls.paths)


def test_concurrent_single_flight_rebuilds_request_specific_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = datetime.now(UTC)
    calls = FakeCalls(event)
    calls.block_first_registry = True
    install_fake_adapters(monkeypatch, calls)
    core = event - timedelta(minutes=1)
    cutoffs = [event + timedelta(minutes=1, seconds=index) for index in range(6)]
    barrier = threading.Barrier(len(cutoffs))

    def build(index: int) -> dict:
        barrier.wait(timeout=2)
        return build_derivatives_intelligence(
            normalized_symbol="BTC/USDT",
            core_prediction_as_of_utc=core,
            enabled=True,
            http_client=object(),
            now_utc=cutoffs[index],
        )

    with ThreadPoolExecutor(max_workers=len(cutoffs)) as executor:
        futures = [executor.submit(build, index) for index in range(len(cutoffs))]
        assert calls.entered.wait(timeout=2)
        calls.release.set()
        blocks = [future.result(timeout=3) for future in futures]

    assert len(calls.paths) == 6
    assert {block["block_status"] for block in blocks} == {"ACTIVE"}
    staleness = {block["metrics"][0]["input_staleness_seconds"] for block in blocks}
    assert len(staleness) == len(cutoffs)
    assert {block["metrics"][0]["raw_value"] for block in blocks} == {-0.0001}
    assert runtime.runtime_cache_sizes()["lock_stripes"] == 64


def test_cache_expiry_and_lru_capacity(monkeypatch: pytest.MonkeyPatch) -> None:
    event = datetime(2026, 6, 22, 0, tzinfo=UTC)
    calls = FakeCalls(event)
    install_fake_adapters(monkeypatch, calls)
    clock = MutableClock()

    def now() -> datetime:
        return event + timedelta(seconds=1)

    runtime.get_raw_derivatives_bundle(
        "BTC/USDT", http_client=object(), monotonic_func=clock, utc_now_func=now
    )
    assert len(calls.paths) == 6
    clock.value = 61
    runtime.get_raw_derivatives_bundle(
        "BTC/USDT", http_client=object(), monotonic_func=clock, utc_now_func=now
    )
    assert len(calls.paths) == 10

    sample = next(iter(runtime._SYMBOL_CACHE.values())).bundle
    for index in range(runtime.SYMBOL_CACHE_MAX_ENTRIES + 1):
        changed = runtime.RawProviderBundle(
            **{**sample.__dict__, "normalized_symbol": f"S{index}/USDT"}
        )
        runtime._put_symbol(changed, clock.value)
    assert runtime.runtime_cache_sizes() == {
        "registry": 2,
        "symbols": runtime.SYMBOL_CACHE_MAX_ENTRIES,
        "lock_stripes": runtime.LOCK_STRIPE_COUNT,
    }
    assert (sample.provider, "S0/USDT") not in runtime._SYMBOL_CACHE


def test_deadline_stops_new_calls_and_marks_remaining_provider_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = datetime(2026, 6, 22, 0, tzinfo=UTC)
    calls = FakeCalls(event)
    calls.clock = MutableClock()
    calls.advance_seconds = 3.1
    install_fake_adapters(monkeypatch, calls)
    bundle = runtime.get_raw_derivatives_bundle(
        "BTC/USDT",
        http_client=object(),
        monotonic_func=calls.clock,
        utc_now_func=lambda: event + timedelta(seconds=1),
    )
    assert len(calls.paths) == 3
    assert bundle.providers[0].fetch_status == "OK"
    assert bundle.providers[1].fetch_status == "PROVIDER_UNAVAILABLE"
    assert runtime.NEW_CALL_START_DEADLINE_SECONDS == 9.0
    assert runtime.REQUEST_TIMEOUT_SECONDS == 3.0


@pytest.mark.parametrize(
    ("fail_binance", "fail_okx", "expected"),
    [(False, True, "DEGRADED"), (True, True, "UNAVAILABLE")],
)
def test_provider_failures_are_contained(
    monkeypatch: pytest.MonkeyPatch,
    fail_binance: bool,
    fail_okx: bool,
    expected: str,
) -> None:
    event = datetime.now(UTC)
    calls = FakeCalls(event)
    calls.fail_binance = fail_binance
    calls.fail_okx = fail_okx
    install_fake_adapters(monkeypatch, calls)
    block = build_derivatives_intelligence(
        normalized_symbol="BTC/USDT",
        core_prediction_as_of_utc=event - timedelta(minutes=1),
        enabled=True,
        http_client=object(),
        now_utc=event + timedelta(minutes=1),
    )
    assert block["block_status"] == expected


def test_malformed_payload_degrades_without_escaping(monkeypatch: pytest.MonkeyPatch) -> None:
    event = datetime.now(UTC)
    calls = FakeCalls(event)
    calls.malformed_binance = True
    install_fake_adapters(monkeypatch, calls)
    block = build_derivatives_intelligence(
        normalized_symbol="BTC/USDT",
        core_prediction_as_of_utc=event - timedelta(minutes=1),
        enabled=True,
        http_client=object(),
        now_utc=event + timedelta(minutes=1),
    )
    assert block["block_status"] == "DEGRADED"
    assert block["provider_summary"][0]["status"] == "NO_VALID_METRIC"
    assert all(
        metric["status"] == "COMPUTE_ERROR"
        for metric in block["metrics"]
        if metric["provider"] == "BINANCE_USDM"
    )
