"""Pydantic models for the stable API response contract."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from crypto_probability_engine.utils.invariants import validate_probability_state
from crypto_probability_engine.utils.validation import (
    ensure_json_sentinel_rules,
    ensure_utc_datetime,
)


class AnalysisMode(StrEnum):
    METRICS_ONLY = "METRICS_ONLY"
    NEWS_ADDON = "NEWS_ADDON"


class AssetClass(StrEnum):
    CRYPTO_SPOT = "CRYPTO_SPOT"
    CRYPTO_PERP = "CRYPTO_PERP"


class ErrorCode(StrEnum):
    INVALID_SYMBOL = "INVALID_SYMBOL"
    UNSUPPORTED_ASSET_CLASS = "UNSUPPORTED_ASSET_CLASS"
    PROVIDER_DEGRADED = "PROVIDER_DEGRADED"
    DATA_CONFLICT = "DATA_CONFLICT"
    STALE_CANDLES = "STALE_CANDLES"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    QUANT_COMPUTE_FAILED = "QUANT_COMPUTE_FAILED"
    EPISTEMIC_VOID = "EPISTEMIC_VOID"
    EXCHANGE_HEALTH_BLOCK = "EXCHANGE_HEALTH_BLOCK"
    SHELTER_MODE_BLOCK = "SHELTER_MODE_BLOCK"
    SCHEMA_VALIDATION_FAILED = "SCHEMA_VALIDATION_FAILED"
    BACKEND_TIMEOUT = "BACKEND_TIMEOUT"
    BATCH_LIMIT_EXCEEDED = "BATCH_LIMIT_EXCEEDED"
    RUN_NOT_FOUND = "RUN_NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"


JsonObject = dict[str, Any]


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: ErrorCode
    message: str
    retry_after_seconds: int | None = None
    run_id: str | None = None
    provider_state_snapshot: JsonObject = Field(default_factory=dict)
    system_status_snapshot: JsonObject = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ErrorEnvelope


class BuildInfoResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["build-info.v1"]
    release_id: str = Field(min_length=1, pattern=r"^UCPE-[A-Z0-9-]{3,}$")
    release_label: str = Field(min_length=1)
    environment: str = Field(min_length=1)
    source_milestone: str = Field(min_length=1)
    fingerprint: str = Field(min_length=1)


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    analysis_mode: AnalysisMode = AnalysisMode.METRICS_ONLY
    timeframe: str = "4H"
    asset_class: AssetClass = AssetClass.CRYPTO_SPOT
    include_detail: bool = True


class BatchAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requests: list[AnalysisRequest] = Field(min_length=1, max_length=5)


class WatchlistRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str


CalibrationTimeframe = Literal["15m", "1H", "4H", "1D", "1W", "1M"]


class CalibrationReliabilityBucket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bucket: str
    bucket_count: int = Field(ge=0)
    avg_predicted_max_prob: float | None = None
    empirical_hit_rate: float | None = None
    calibration_gap: float | None = None
    bucket_sample_status: str


class CalibrationTimeframeItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeframe: CalibrationTimeframe
    sample_count: int = Field(ge=0)
    valid_count: int = Field(ge=0)
    sample_gate: str
    reliability_status: str
    metrics_available: bool
    brier_score: float | None = None
    log_loss: float | None = None
    top_label_hit_rate: float | None = None
    reliability_buckets: list[CalibrationReliabilityBucket] | None = None
    outcome_distribution: dict[str, int] = Field(default_factory=dict)
    version_mix_warning: bool
    versions_present: dict[str, list[str]] = Field(default_factory=dict)
    warning: str


class CalibrationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["OK", "UNAVAILABLE"]
    repository: str
    generated_at: str
    source: Literal["CALIBRATION_SERVICE"] = "CALIBRATION_SERVICE"
    influence_mode: Literal["READ_ONLY_DIAGNOSTIC"] = "READ_ONLY_DIAGNOSTIC"
    not_win_rate: Literal[True] = True
    not_profitability_evidence: Literal[True] = True
    not_trade_ev: Literal[True] = True
    timeframes: list[CalibrationTimeframeItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error_class: str | None = None


class QuantV2Status(StrEnum):
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    DISABLED = "DISABLED"


class QuantV2FeatureStatus(StrEnum):
    VALID = "VALID"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    STALE_INPUT = "STALE_INPUT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    COMPUTE_ERROR = "COMPUTE_ERROR"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    DEGRADED = "DEGRADED"


class QuantV2Family(StrEnum):
    VOLATILITY = "VOLATILITY"
    TREND = "TREND"
    VOLUME = "VOLUME"
    REGIME = "REGIME"


class QuantV2FeatureDataQuality(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upstream_status: str | None
    provider_state_status: str | None
    snapshot_source_status: str | None
    timestamp_evidence_complete: bool


class QuantV2Feature(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    feature_name: str
    feature_id: str
    family: QuantV2Family
    timeframe: str
    symbol: str
    source_provider: str | None
    source_priority: int | None = Field(ge=1)
    lookback: int | None = Field(ge=1)
    candle_count: int = Field(ge=0)
    computed_at: datetime | None
    input_start_time: datetime | None
    input_end_time: datetime | None
    input_staleness_seconds: float | None = Field(ge=0)
    status: QuantV2FeatureStatus
    reason_if_invalid: str | None
    raw_value: float | str | None
    normalized_value: None
    bucket: None
    direction_hint: Literal["UP", "DOWN", "SIDEWAYS"] | None
    confidence_hint: None
    risk_hint: None
    explanation_short: str
    explanation_detail: str
    influence_mode: Literal["SHADOW_ONLY"]
    methodology_version: Literal["quant-v2-shadow-v0"]
    data_quality: QuantV2FeatureDataQuality
    no_lookahead_assertion: bool

    @model_validator(mode="after")
    def validate_health_reason(self) -> QuantV2Feature:
        if self.status == QuantV2FeatureStatus.VALID and self.reason_if_invalid is not None:
            raise ValueError("VALID Quant V2 features must not include an invalid reason.")
        if self.status != QuantV2FeatureStatus.VALID and not self.reason_if_invalid:
            raise ValueError("Non-VALID Quant V2 features require an invalid reason.")
        return self


class QuantV2Block(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    schema_version: Literal["quant_v2.0"]
    status: QuantV2Status
    influence_mode: Literal["SHADOW_ONLY"]
    feature_methodology_version: Literal["quant-v2-shadow-v0"]
    computed_at_utc: datetime | None
    symbol: str
    normalized_symbol: str
    timeframe: str
    reference_close_utc: datetime | None
    input_staleness_seconds: float | None = Field(ge=0)
    no_lookahead_assertion: bool
    feature_count: Literal[0, 4]
    degraded_count: int = Field(ge=0, le=4)
    features: list[QuantV2Feature]
    plain_english: Literal[
        "Shadow diagnostics — evidence only, not used in the decision yet. "
        "Not a trade command. Not financial advice. Not profitability evidence. Not accuracy."
    ]
    not_trade_command: Literal[True]
    not_financial_advice: Literal[True]

    @model_validator(mode="after")
    def validate_feature_counts(self) -> QuantV2Block:
        actual_degraded_count = sum(
            feature.status != QuantV2FeatureStatus.VALID for feature in self.features
        )
        if self.status == QuantV2Status.DISABLED:
            if self.features or self.feature_count or self.degraded_count:
                raise ValueError("DISABLED Quant V2 must contain no features.")
        elif len(self.features) != 4 or self.feature_count != 4:
            raise ValueError("Enabled Quant V2 must contain exactly four features.")
        if self.status == QuantV2Status.ACTIVE and (
            actual_degraded_count or self.degraded_count or not self.no_lookahead_assertion
        ):
            raise ValueError("ACTIVE Quant V2 requires valid no-lookahead feature evidence.")
        if self.status == QuantV2Status.DEGRADED and (
            not actual_degraded_count or self.degraded_count < 1
        ):
            raise ValueError("DEGRADED Quant V2 requires degraded feature evidence.")
        return self


class DerivativesProviderSummaryStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    DEGRADED_PARTIAL = "DEGRADED_PARTIAL"
    UNSUPPORTED_INSTRUMENT = "UNSUPPORTED_INSTRUMENT"
    INSTRUMENT_INACTIVE = "INSTRUMENT_INACTIVE"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    NO_VALID_METRIC = "NO_VALID_METRIC"


class DerivativesProviderSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["BINANCE_USDM", "OKX_SWAP"]
    status: DerivativesProviderSummaryStatus
    valid_metric_count: int = Field(ge=0)
    total_metric_count: int = Field(ge=0)
    reason: str | None

    @model_validator(mode="after")
    def validate_reason_and_counts(self) -> DerivativesProviderSummary:
        if self.valid_metric_count > self.total_metric_count:
            raise ValueError("Valid derivatives metric count exceeds total count.")
        if self.status == DerivativesProviderSummaryStatus.AVAILABLE and self.reason is not None:
            raise ValueError("AVAILABLE derivatives provider summaries have no failure reason.")
        if self.status != DerivativesProviderSummaryStatus.AVAILABLE and not self.reason:
            raise ValueError("Non-AVAILABLE derivatives provider summaries require a reason.")
        if self.status == DerivativesProviderSummaryStatus.AVAILABLE and (
            self.total_metric_count == 0 or self.valid_metric_count != self.total_metric_count
        ):
            raise ValueError("AVAILABLE derivatives providers require all expected metrics valid.")
        if self.status == DerivativesProviderSummaryStatus.DEGRADED_PARTIAL and not (
            0 < self.valid_metric_count < self.total_metric_count
        ):
            raise ValueError("DEGRADED_PARTIAL requires mixed valid and invalid metrics.")
        return self


class DerivativesMetricResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    metric_id: Literal[
        "binance.funding.current_estimate",
        "binance.funding.settled",
        "binance.open_interest.current",
        "binance.open_interest.history.quantity",
        "binance.open_interest.history.quote_value",
        "okx.funding.current_estimate",
        "okx.funding.settled",
        "okx.open_interest.current.contracts",
        "okx.open_interest.current.base",
        "okx.open_interest.current.usd",
    ]
    family: Literal["FUNDING", "OPEN_INTEREST"]
    provider: Literal["BINANCE_USDM", "OKX_SWAP"]
    provider_endpoint: Literal[
        "/fapi/v1/premiumIndex",
        "/fapi/v1/fundingRate",
        "/fapi/v1/openInterest",
        "/futures/data/openInterestHist",
        "/api/v5/public/funding-rate",
        "/api/v5/public/funding-rate-history",
        "/api/v5/public/open-interest",
    ]
    provider_instrument: str = Field(min_length=1)
    normalized_symbol: str = Field(min_length=1)
    contract_type: Literal["USDT_LINEAR_PERPETUAL", "CONTRACT_MISMATCH", "UNKNOWN"]
    margin_asset: str = Field(min_length=1)
    settlement_asset: str = Field(min_length=1)
    timeframe_or_period: str | None
    event_time: datetime | None
    interval_start: datetime | None
    interval_end: datetime | None
    interval_final: bool
    fetched_at_utc: datetime
    prediction_as_of_utc: datetime
    input_staleness_seconds: float | None = Field(ge=0)
    status: Literal[
        "VALID",
        "INSUFFICIENT_HISTORY",
        "STALE_INPUT",
        "PROVIDER_UNAVAILABLE",
        "UNSUPPORTED_INSTRUMENT",
        "CONTRACT_MISMATCH",
        "INSTRUMENT_INACTIVE",
        "PARTIAL_INTERVAL",
        "INVALID_UNIT",
        "COMPUTE_ERROR",
        "DEGRADED",
    ]
    reason_if_invalid: str | None
    raw_value: float | None
    normalized_value: None
    bucket: None
    direction_hint: None
    confidence_hint: None
    risk_hint: None
    unit: Literal[
        "FRACTION_PER_INTERVAL",
        "PROVIDER_NATIVE_CONTRACT_QUANTITY",
        "USDT_NOTIONAL",
        "CONTRACTS",
        "BASE_ASSET_QUANTITY",
        "USD_NOTIONAL",
    ]
    source_count: int = Field(ge=0)
    provider_priority: int = Field(ge=1)
    influence_mode: Literal["SHADOW_ONLY"]
    methodology_version: Literal["deriv-intel-shadow-v0"]
    no_lookahead_assertion: bool

    @field_validator(
        "event_time",
        "interval_start",
        "interval_end",
        "fetched_at_utc",
        "prediction_as_of_utc",
    )
    @classmethod
    def validate_metric_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_utc_datetime(value, "derivatives metric timestamp")

    @model_validator(mode="after")
    def validate_metric_reason(self) -> DerivativesMetricResponse:
        if self.status == "VALID" and self.reason_if_invalid is not None:
            raise ValueError("VALID derivatives metrics have no invalid reason.")
        if self.status != "VALID" and not self.reason_if_invalid:
            raise ValueError("Non-VALID derivatives metrics require an invalid reason.")
        return self


class DerivativesComparability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    semantic_class: Literal["CURRENT_FUNDING", "CURRENT_OPEN_INTEREST"]
    left_provider: Literal["BINANCE_USDM"]
    right_provider: Literal["OKX_SWAP"]
    comparable: bool
    reason: str = Field(min_length=1)


class DerivativesIntelligenceBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    schema_version: Literal["deriv-intel.v0"]
    influence_mode: Literal["SHADOW_ONLY"]
    decision_influence_frac: Literal[0.0]
    methodology_version: Literal["deriv-intel-shadow-v0"]
    normalized_symbol: str = Field(min_length=1)
    core_prediction_as_of_utc: datetime
    observation_as_of_utc: datetime | None
    block_status: Literal["ACTIVE", "DEGRADED", "UNAVAILABLE", "DISABLED"]
    provider_summary: list[DerivativesProviderSummary]
    metrics: list[DerivativesMetricResponse]
    comparability: list[DerivativesComparability]
    disagreement: list[JsonObject] = Field(max_length=0)
    warnings: list[str]
    not_trade_command: Literal[True]
    not_financial_advice: Literal[True]
    plain_english: Literal["Derivatives context — observe only, not used in the decision."]

    @field_validator("core_prediction_as_of_utc", "observation_as_of_utc")
    @classmethod
    def validate_block_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_utc_datetime(value, "derivatives block timestamp")

    @model_validator(mode="after")
    def validate_block_state(self) -> DerivativesIntelligenceBlock:
        available = sum(
            item.status == DerivativesProviderSummaryStatus.AVAILABLE
            for item in self.provider_summary
        )
        if self.block_status == "DISABLED":
            if self.observation_as_of_utc is not None or self.provider_summary or self.metrics:
                raise ValueError("DISABLED derivatives block contains no observation evidence.")
        elif self.observation_as_of_utc is None:
            raise ValueError("Enabled derivatives blocks require an observation timestamp.")
        elif {item.provider for item in self.provider_summary} != {
            "BINANCE_USDM",
            "OKX_SWAP",
        } or len(self.provider_summary) != 2:
            raise ValueError("Enabled derivatives blocks require both provider summaries.")
        if self.block_status == "ACTIVE" and available != len(self.provider_summary):
            raise ValueError("ACTIVE derivatives block requires every provider available.")
        if self.block_status == "DEGRADED" and not 0 < available < len(self.provider_summary):
            raise ValueError("DEGRADED derivatives block requires mixed provider availability.")
        if self.block_status == "UNAVAILABLE" and available:
            raise ValueError("UNAVAILABLE derivatives block cannot have an available provider.")
        return self


class HorizonProbability(BaseModel):
    model_config = ConfigDict(extra="allow")

    p_up_frac: float
    p_down_frac: float
    p_timeout_frac: float
    p_up_user_norm_frac: float | None = None
    p_down_user_norm_frac: float | None = None
    confidence_frac: float = 0.0
    news_confidence_adj_frac: float = 0.0
    status: str = "OK"
    null_reason: str | None = None

    @model_validator(mode="after")
    def validate_invariant(self) -> HorizonProbability:
        from crypto_probability_engine.utils.invariants import validate_probability_triplet

        validate_probability_triplet(self.p_up_frac, self.p_down_frac, self.p_timeout_frac)
        return self


class ProbabilityState(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str
    horizons: dict[str, HorizonProbability]
    calibration_status: str
    null_reason: str | None = None


class DetailView(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: str
    run_id: str
    analysis_mode: AnalysisMode
    sections: list[str]
    metrics_detail: JsonObject = Field(default_factory=dict)
    probability_detail: JsonObject = Field(default_factory=dict)
    score_detail: JsonObject = Field(default_factory=dict)
    risk_detail: JsonObject = Field(default_factory=dict)
    liquidity_execution_detail: JsonObject = Field(default_factory=dict)
    data_quality_detail: JsonObject = Field(default_factory=dict)
    invalidation_detail: JsonObject = Field(default_factory=dict)
    decision_brief: JsonObject = Field(default_factory=dict)
    news_detail: JsonObject = Field(default_factory=dict)
    macro_detail: JsonObject = Field(default_factory=dict)
    debug_lite: JsonObject = Field(default_factory=dict)


class VolatilityReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    realized_vol: float | None = None
    note: str


class DecisionBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["NO_TRADE", "WATCHLIST", "SPOT_WATCH"]
    symbol: str
    normalized_symbol: str
    timeframe_label: str
    horizon_label: str
    horizon_bars: int
    probability_type: Literal["UNCALIBRATED_HEURISTIC_6BAR_OUTCOME"]
    model_readiness: str
    calibration_status: str
    reliability_status: str
    profitability_claim: Literal[False]
    state_summary: str
    key_reasons: list[str]
    hard_blockers: list[str]
    watchlist_triggers: list[str]
    invalidation_conditions: list[str]
    volatility_reference: VolatilityReference
    risk_note: str
    disclaimer: str


class AnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    run_id: str
    symbol: str
    normalized_symbol: str
    asset_class: AssetClass
    analysis_mode: AnalysisMode
    timeframes: JsonObject
    as_of_utc: datetime
    provider_state: JsonObject
    data_quality: JsonObject
    market_features: JsonObject
    liquidity_state: JsonObject
    execution_realism: JsonObject
    quant_compute_state: JsonObject
    epistemic_sufficiency_state: JsonObject
    probability_state: ProbabilityState
    horizon_timeout_state: JsonObject
    risk_arbiter_state: JsonObject
    tail_risk_state: JsonObject
    calibration_state: JsonObject
    macro_context: JsonObject
    micro_news_context: JsonObject
    news_addon_state: JsonObject
    news_evidence: JsonObject
    news_materiality_state: JsonObject
    event_horizon_state: JsonObject
    narrative_state: JsonObject
    novelty_surprise_state: JsonObject
    source_confidence_state: JsonObject
    information_state: JsonObject
    catalyst_state: JsonObject
    score_stack: JsonObject
    trend_summary: JsonObject
    decision_brief: DecisionBrief
    decision_synthesis: JsonObject = Field(default_factory=dict)
    quant_v2: QuantV2Block
    derivatives_intelligence: DerivativesIntelligenceBlock
    frontend_display: JsonObject
    detail_view: DetailView
    gate_result: JsonObject
    debug: JsonObject
    analysis_hash: str

    @field_validator("as_of_utc")
    @classmethod
    def validate_as_of_utc(cls, value: datetime) -> datetime:
        return ensure_utc_datetime(value, "as_of_utc")

    @model_validator(mode="after")
    def validate_contract_invariants(self) -> AnalysisResponse:
        payload = self.model_dump(mode="json")
        ensure_json_sentinel_rules(payload)
        validate_probability_state(payload["probability_state"])
        return self


def validate_analysis_response(payload: JsonObject) -> AnalysisResponse:
    return AnalysisResponse.model_validate(payload)
