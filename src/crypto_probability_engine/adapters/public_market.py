"""Public-only market-data adapter interfaces and fixture implementations."""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import replace
from typing import Protocol

from crypto_probability_engine.adapters.http_client import PublicHttpClient
from crypto_probability_engine.adapters.mappers import (
    BINANCE_BASE_URL,
    OKX_BASE_URL,
    map_interval,
    parse_binance_candles,
    parse_binance_order_book,
    parse_binance_recent_trades,
    parse_binance_symbol_universe,
    parse_binance_ticker,
    parse_okx_candles,
    parse_okx_order_book,
    parse_okx_recent_trades,
    parse_okx_symbol_universe,
    parse_okx_ticker,
    provider_symbol,
)
from crypto_probability_engine.adapters.market_metrics import build_derived_market_metrics
from crypto_probability_engine.adapters.symbol_universe import ProviderSymbolUniverse
from crypto_probability_engine.adapters.types import (
    MarketSnapshot,
    MarketTicker,
    OrderBookSnapshot,
    ProviderError,
    ProviderState,
    ProviderStatus,
    RecentTrade,
)
from crypto_probability_engine.config.defaults import min_history_for
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.config.unit_discipline import utc_now
from crypto_probability_engine.normalizers.symbols import NormalizedSymbol
from crypto_probability_engine.validation.market_data import (
    DataValidationError,
    assert_snapshots_coherent,
    validate_market_snapshot,
)


class PublicMarketAdapter(Protocol):
    name: str

    def fetch_market_snapshot(self, symbol: NormalizedSymbol, timeframe: str) -> MarketSnapshot:
        """Fetch or provide public market data for a normalized spot symbol."""

    def fetch_symbol_universe(self) -> ProviderSymbolUniverse:
        """Fetch public spot USDT symbol universe for this provider."""


class FixturePublicAdapter:
    """Offline adapter for tests and local smoke runs."""

    def __init__(
        self,
        name: str,
        snapshots: Mapping[tuple[str, str], MarketSnapshot],
        *,
        fail_code: str | None = None,
    ) -> None:
        self.name = name
        self._snapshots = dict(snapshots)
        self._fail_code = fail_code

    def fetch_market_snapshot(self, symbol: NormalizedSymbol, timeframe: str) -> MarketSnapshot:
        if self._fail_code:
            raise ProviderError(self._fail_code, "Fixture provider failure.", provider=self.name)
        key = (symbol.display, timeframe)
        try:
            return self._snapshots[key]
        except KeyError as exc:
            raise ProviderError(
                "DATA_UNAVAILABLE",
                "Fixture snapshot unavailable.",
                provider=self.name,
            ) from exc


class BinancePublicAdapter:
    """Keyless Binance spot market-data adapter."""

    name = "binance"

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        http_client: PublicHttpClient | None = None,
    ) -> None:
        self.settings = settings or Settings.from_env()
        self.http_client = http_client or PublicHttpClient.from_settings(self.settings)

    def fetch_market_snapshot(self, symbol: NormalizedSymbol, timeframe: str) -> MarketSnapshot:
        symbol_param = provider_symbol(symbol, self.name)
        interval = map_interval(timeframe, self.name)
        limit = min(min_history_for(timeframe) + 5, 1000)
        resource_statuses: dict[str, dict] = {}
        warnings: list[str] = []
        klines = self._get_json_resource(
            "candles",
            base_url=BINANCE_BASE_URL,
            path="/api/v3/klines",
            params={"symbol": symbol_param, "interval": interval, "limit": limit},
            resource_statuses=resource_statuses,
        )
        depth = self._get_json_resource(
            "depth",
            base_url=BINANCE_BASE_URL,
            path="/api/v3/depth",
            params={"symbol": symbol_param, "limit": self.settings.provider_depth_limit},
            resource_statuses=resource_statuses,
        )
        as_of_utc = utc_now()
        candles = parse_binance_candles(klines, timeframe=timeframe)
        order_book = parse_binance_order_book(depth, as_of_utc=as_of_utc)
        ticker = self._optional_ticker(symbol_param, resource_statuses, warnings, as_of_utc)
        trades = self._optional_trades(symbol_param, resource_statuses, warnings)
        snapshot = MarketSnapshot(
            provider=self.name,
            normalized_symbol=symbol.display,
            timeframe=timeframe,
            candles=candles,
            order_book=order_book,
            as_of_utc=as_of_utc,
            source_status=ProviderStatus.OK,
            warnings=tuple(warnings),
            ticker=ticker,
            recent_trades=trades,
            resource_statuses=_with_freshness(resource_statuses, snapshot_parts={
                "candles": _age_seconds(as_of_utc, candles[-1].close_time_utc) if candles else None,
                "depth": 0,
                "ticker": _age_seconds(as_of_utc, ticker.as_of_utc) if ticker else None,
                "trades": _age_seconds(as_of_utc, trades[-1].timestamp_utc) if trades else None,
            }),
        )
        return replace(snapshot, derived_metrics=build_derived_market_metrics(snapshot))

    def fetch_order_book(self, symbol: NormalizedSymbol, limit: int = 100) -> OrderBookSnapshot:
        as_of_utc = utc_now()
        payload = self.http_client.get_json(
            base_url=BINANCE_BASE_URL,
            path="/api/v3/depth",
            params={"symbol": provider_symbol(symbol, self.name), "limit": limit},
            provider=self.name,
        )
        return parse_binance_order_book(payload, as_of_utc=as_of_utc)

    def fetch_ticker(self, symbol: NormalizedSymbol) -> MarketTicker:
        as_of_utc = utc_now()
        payload = self.http_client.get_json(
            base_url=BINANCE_BASE_URL,
            path="/api/v3/ticker/24hr",
            params={"symbol": provider_symbol(symbol, self.name)},
            provider=self.name,
        )
        return parse_binance_ticker(payload, as_of_utc=as_of_utc)

    def fetch_recent_trades_or_agg_trades(
        self,
        symbol: NormalizedSymbol,
        limit: int | None = None,
    ) -> tuple[RecentTrade, ...]:
        payload = self.http_client.get_json(
            base_url=BINANCE_BASE_URL,
            path="/api/v3/trades",
            params={
                "symbol": provider_symbol(symbol, self.name),
                "limit": limit or self.settings.provider_trade_limit,
            },
            provider=self.name,
        )
        return parse_binance_recent_trades(payload)

    def fetch_symbol_universe(self) -> ProviderSymbolUniverse:
        payload = self.http_client.get_json(
            base_url=BINANCE_BASE_URL,
            path="/api/v3/exchangeInfo",
            params={},
            provider=self.name,
        )
        return ProviderSymbolUniverse(
            provider=self.name,
            symbols=parse_binance_symbol_universe(payload),
        )

    def _optional_ticker(
        self,
        symbol_param: str,
        resource_statuses: dict[str, dict],
        warnings: list[str],
        as_of_utc,
    ) -> MarketTicker | None:
        payload = self._get_json_resource(
            "ticker",
            base_url=BINANCE_BASE_URL,
            path="/api/v3/ticker/24hr",
            params={"symbol": symbol_param},
            resource_statuses=resource_statuses,
            required=False,
        )
        if payload is None:
            warnings.append("ticker resource unavailable")
            return None
        try:
            return parse_binance_ticker(payload, as_of_utc=as_of_utc)
        except ProviderError as exc:
            resource_statuses["ticker"] = _resource_status(
                "UNAVAILABLE",
                time.perf_counter(),
                error_code=exc.code,
            )
            warnings.append("ticker resource unavailable")
            return None

    def _optional_trades(
        self,
        symbol_param: str,
        resource_statuses: dict[str, dict],
        warnings: list[str],
    ) -> tuple[RecentTrade, ...]:
        payload = self._get_json_resource(
            "trades",
            base_url=BINANCE_BASE_URL,
            path="/api/v3/trades",
            params={"symbol": symbol_param, "limit": self.settings.provider_trade_limit},
            resource_statuses=resource_statuses,
            required=False,
        )
        if payload is None:
            warnings.append("trades resource unavailable")
            return ()
        try:
            return parse_binance_recent_trades(payload)
        except ProviderError as exc:
            resource_statuses["trades"] = _resource_status(
                "UNAVAILABLE",
                time.perf_counter(),
                error_code=exc.code,
            )
            warnings.append("trades resource unavailable")
            return ()

    def _get_json_resource(
        self,
        resource: str,
        *,
        base_url: str,
        path: str,
        params: Mapping[str, object],
        resource_statuses: dict[str, dict],
        required: bool = True,
    ):
        start = time.perf_counter()
        try:
            payload = self.http_client.get_json(
                base_url=base_url,
                path=path,
                params=params,
                provider=self.name,
            )
        except ProviderError as exc:
            resource_statuses[resource] = _resource_status(
                "UNAVAILABLE",
                start,
                error_code=exc.code,
            )
            if required:
                raise
            return None
        resource_statuses[resource] = _resource_status("OK", start)
        return payload


class OkxPublicAdapter:
    """Keyless OKX spot market-data adapter."""

    name = "okx"

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        http_client: PublicHttpClient | None = None,
    ) -> None:
        self.settings = settings or Settings.from_env()
        self.http_client = http_client or PublicHttpClient.from_settings(self.settings)

    def fetch_market_snapshot(self, symbol: NormalizedSymbol, timeframe: str) -> MarketSnapshot:
        inst_id = provider_symbol(symbol, self.name)
        bar = map_interval(timeframe, self.name)
        limit = min(min_history_for(timeframe) + 5, 300)
        resource_statuses: dict[str, dict] = {}
        warnings: list[str] = []
        candles_payload = self._get_json_resource(
            "candles",
            base_url=OKX_BASE_URL,
            path="/api/v5/market/candles",
            params={"instId": inst_id, "bar": bar, "limit": limit},
            resource_statuses=resource_statuses,
        )
        books_payload = self._get_json_resource(
            "depth",
            base_url=OKX_BASE_URL,
            path="/api/v5/market/books",
            params={"instId": inst_id, "sz": self.settings.provider_depth_limit},
            resource_statuses=resource_statuses,
        )
        as_of_utc = utc_now()
        candles = parse_okx_candles(candles_payload, timeframe=timeframe)
        order_book = parse_okx_order_book(books_payload, as_of_utc=as_of_utc)
        ticker = self._optional_ticker(inst_id, resource_statuses, warnings, as_of_utc)
        trades = self._optional_trades(inst_id, resource_statuses, warnings)
        snapshot = MarketSnapshot(
            provider=self.name,
            normalized_symbol=symbol.display,
            timeframe=timeframe,
            candles=candles,
            order_book=order_book,
            as_of_utc=as_of_utc,
            source_status=ProviderStatus.OK,
            warnings=tuple(warnings),
            ticker=ticker,
            recent_trades=trades,
            resource_statuses=_with_freshness(resource_statuses, snapshot_parts={
                "candles": _age_seconds(as_of_utc, candles[-1].close_time_utc) if candles else None,
                "depth": 0,
                "ticker": _age_seconds(as_of_utc, ticker.as_of_utc) if ticker else None,
                "trades": _age_seconds(as_of_utc, trades[-1].timestamp_utc) if trades else None,
            }),
        )
        return replace(snapshot, derived_metrics=build_derived_market_metrics(snapshot))

    def fetch_order_book(self, symbol: NormalizedSymbol, limit: int = 100) -> OrderBookSnapshot:
        as_of_utc = utc_now()
        payload = self.http_client.get_json(
            base_url=OKX_BASE_URL,
            path="/api/v5/market/books",
            params={"instId": provider_symbol(symbol, self.name), "sz": limit},
            provider=self.name,
        )
        return parse_okx_order_book(payload, as_of_utc=as_of_utc)

    def fetch_ticker(self, symbol: NormalizedSymbol) -> MarketTicker:
        as_of_utc = utc_now()
        payload = self.http_client.get_json(
            base_url=OKX_BASE_URL,
            path="/api/v5/market/ticker",
            params={"instId": provider_symbol(symbol, self.name)},
            provider=self.name,
        )
        return parse_okx_ticker(payload, as_of_utc=as_of_utc)

    def fetch_recent_trades_or_agg_trades(
        self,
        symbol: NormalizedSymbol,
        limit: int | None = None,
    ) -> tuple[RecentTrade, ...]:
        payload = self.http_client.get_json(
            base_url=OKX_BASE_URL,
            path="/api/v5/market/trades",
            params={
                "instId": provider_symbol(symbol, self.name),
                "limit": limit or self.settings.provider_trade_limit,
            },
            provider=self.name,
        )
        return parse_okx_recent_trades(payload)

    def fetch_symbol_universe(self) -> ProviderSymbolUniverse:
        payload = self.http_client.get_json(
            base_url=OKX_BASE_URL,
            path="/api/v5/public/instruments",
            params={"instType": "SPOT"},
            provider=self.name,
        )
        return ProviderSymbolUniverse(
            provider=self.name,
            symbols=parse_okx_symbol_universe(payload),
        )

    def _optional_ticker(
        self,
        inst_id: str,
        resource_statuses: dict[str, dict],
        warnings: list[str],
        as_of_utc,
    ) -> MarketTicker | None:
        payload = self._get_json_resource(
            "ticker",
            base_url=OKX_BASE_URL,
            path="/api/v5/market/ticker",
            params={"instId": inst_id},
            resource_statuses=resource_statuses,
            required=False,
        )
        if payload is None:
            warnings.append("ticker resource unavailable")
            return None
        try:
            return parse_okx_ticker(payload, as_of_utc=as_of_utc)
        except ProviderError as exc:
            resource_statuses["ticker"] = _resource_status(
                "UNAVAILABLE",
                time.perf_counter(),
                error_code=exc.code,
            )
            warnings.append("ticker resource unavailable")
            return None

    def _optional_trades(
        self,
        inst_id: str,
        resource_statuses: dict[str, dict],
        warnings: list[str],
    ) -> tuple[RecentTrade, ...]:
        payload = self._get_json_resource(
            "trades",
            base_url=OKX_BASE_URL,
            path="/api/v5/market/trades",
            params={"instId": inst_id, "limit": self.settings.provider_trade_limit},
            resource_statuses=resource_statuses,
            required=False,
        )
        if payload is None:
            warnings.append("trades resource unavailable")
            return ()
        try:
            return parse_okx_recent_trades(payload)
        except ProviderError as exc:
            resource_statuses["trades"] = _resource_status(
                "UNAVAILABLE",
                time.perf_counter(),
                error_code=exc.code,
            )
            warnings.append("trades resource unavailable")
            return ()

    def _get_json_resource(
        self,
        resource: str,
        *,
        base_url: str,
        path: str,
        params: Mapping[str, object],
        resource_statuses: dict[str, dict],
        required: bool = True,
    ):
        start = time.perf_counter()
        try:
            payload = self.http_client.get_json(
                base_url=base_url,
                path=path,
                params=params,
                provider=self.name,
            )
        except ProviderError as exc:
            resource_statuses[resource] = _resource_status(
                "UNAVAILABLE",
                start,
                error_code=exc.code,
            )
            if required:
                raise
            return None
        resource_statuses[resource] = _resource_status("OK", start)
        return payload


def _resource_status(
    status: str,
    start: float,
    *,
    error_code: str | None = None,
) -> dict:
    result = {
        "status": status,
        "latency_ms": round((time.perf_counter() - start) * 1000.0, 3),
    }
    if error_code:
        result["error_code"] = error_code
    return result


def _with_freshness(
    resource_statuses: dict[str, dict],
    *,
    snapshot_parts: dict[str, int | None],
) -> dict[str, dict]:
    enriched = {name: dict(value) for name, value in resource_statuses.items()}
    for name, age in snapshot_parts.items():
        enriched.setdefault(name, {"status": "UNAVAILABLE"})
        if age is not None:
            enriched[name]["freshness_age_seconds"] = age
    return enriched


def _age_seconds(now_utc, resource_time_utc) -> int:
    return max(0, int((now_utc - resource_time_utc).total_seconds()))


class ProviderRouter:
    """Failover/quarantine router for public market-data providers."""

    def __init__(self, providers: list[PublicMarketAdapter]) -> None:
        self.providers = providers
        self.provider_states = {
            provider.name: ProviderState(name=provider.name, status=ProviderStatus.TO_VERIFY)
            for provider in providers
        }

    def fetch_first_valid(self, symbol: NormalizedSymbol, timeframe: str) -> MarketSnapshot:
        errors: list[str] = []
        accepted: MarketSnapshot | None = None
        accepted_provider: str | None = None
        for provider in self.providers:
            try:
                snapshot = provider.fetch_market_snapshot(symbol, timeframe)
                validate_market_snapshot(snapshot, min_bars=3)
                self.provider_states[provider.name].status = ProviderStatus.OK
                if accepted is not None:
                    assert_snapshots_coherent(accepted, snapshot)
                accepted = snapshot
                accepted_provider = provider.name
            except (ProviderError, DataValidationError) as exc:
                message = str(exc)
                errors.append(f"{provider.name}:{message}")
                state = self.provider_states[provider.name]
                state.status = ProviderStatus.QUARANTINED
                state.quarantine_reason = message
                state.warnings.append(message)
        if accepted is not None:
            self.provider_states[accepted_provider or accepted.provider].status = ProviderStatus.OK
            return accepted
        raise ProviderError("PROVIDER_DEGRADED", "; ".join(errors), provider="router")

    def public_state(self) -> dict:
        active = next(
            (
                state.name
                for state in self.provider_states.values()
                if state.status == ProviderStatus.OK
            ),
            None,
        )
        return {
            "status": "OK" if active else "PROVIDER_DEGRADED",
            "active_provider": active,
            "providers": {
                name: state.to_public_dict() for name, state in sorted(self.provider_states.items())
            },
        }
