"""Pydantic models for the stable API response contract."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

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
    news_detail: JsonObject = Field(default_factory=dict)
    macro_detail: JsonObject = Field(default_factory=dict)
    debug_lite: JsonObject = Field(default_factory=dict)


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
