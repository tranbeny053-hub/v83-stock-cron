"""Visible DEFAULT_PHASE1A values from the approved Sprint 1 plan."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class Phase1ADefaults:
    timeframes: tuple[str, ...] = ("15m", "1H", "4H", "1D", "1W", "1M")
    primary_timeframe: str = "4H"
    trend_timeframes: tuple[str, ...] = ("1H", "4H", "1D")
    h_primary_bars: int = 6
    h_extended_bars: int = 24
    freshness_multiplier: float = 1.5
    min_history_bars: int = 200
    price_disagreement_bps: float = 50.0
    taker_fee_frac: float = 0.001
    maker_fee_frac: float = 0.001
    w_alpha: float = 1.0
    w_omega: float = 1.0
    w_sigma: float = 1.5
    risk_arbiter_version: str = "risk_arbiter_v1"
    probability_version: str = "probability_v1_phase1a"
    timeout_min_frac: float = 0.10
    timeout_max_frac: float = 0.80
    tail_method: str = "HISTORICAL_CVAR"
    tail_confidence_frac: float = 0.99
    evt_status: str = "DISABLED_PHASE1A"
    calibration_status: str = "DEFAULT_PHASE1A"
    reliability_status: str = "INSUFFICIENT_SAMPLE"
    news_evidence_frac: float = 0.0
    analysis_mode_default: str = "METRICS_ONLY"
    asset_class_default: str = "CRYPTO_SPOT"
    probability_signal_sensitivity: float = 25.0
    probability_tilt_midpoint: float = 0.5
    probability_tilt_scale: float = 0.5
    probability_extended_confidence_multiplier: float = 0.9
    timeout_base_frac: float = 0.20
    timeout_vol_cap_frac: float = 0.30
    timeout_spread_multiplier: float = 5.0
    timeout_spread_cap_frac: float = 0.20
    score_base: float = 50.0
    score_directional_edge_multiplier: float = 50.0
    score_min: float = 0.0
    score_max: float = 100.0
    score_constructive_cautious_min: int = 65
    score_elevated_risk_max: int = 35
    score_risk_pressure_cap: float = 25.0
    liquidity_max_spread_frac: float = 0.01
    liquidity_min_top_depth_quote: float = 100.0
    tail_cvar_breach_frac: float = 0.05
    execution_cost_hard_gate_frac: float = 0.02
    access_code_pbkdf2_iterations: int = 210_000
    access_code_local_salt: str = "ucpe-local-dev-salt-change-per-deploy"
    data_mode_default: str = "live"
    provider_priority: tuple[str, ...] = ("binance", "okx")
    provider_timeout_seconds: float = 8.0
    provider_max_retries: int = 1
    provider_rate_limit_per_min: int = 60
    candle_cache_ttl_seconds: int = 300
    symbol_universe_cache_ttl_seconds: int = 3_600
    provider_depth_limit: int = 100
    provider_trade_limit: int = 50
    news_item_limit: int = 12
    news_timeout_seconds: float = 6.0
    news_live_smoke_enabled: bool = False
    cross_provider_required: bool = False
    live_smoke_enabled: bool = False


DEFAULT_PHASE1A = Phase1ADefaults()

MIN_HISTORY_BARS_BY_TIMEFRAME = MappingProxyType({"1M": 24})

TIMEFRAME_SECONDS = MappingProxyType(
    {
        "15m": 15 * 60,
        "1H": 60 * 60,
        "4H": 4 * 60 * 60,
        "1D": 24 * 60 * 60,
        "1W": 7 * 24 * 60 * 60,
        # Monthly candles use an approximate 30-day duration for validation/freshness windows.
        "1M": 30 * 24 * 60 * 60,
    }
)


def min_history_for(timeframe: str) -> int:
    return MIN_HISTORY_BARS_BY_TIMEFRAME.get(timeframe, DEFAULT_PHASE1A.min_history_bars)
