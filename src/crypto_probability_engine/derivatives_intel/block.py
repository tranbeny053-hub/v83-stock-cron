"""Strict SHADOW_ONLY derivatives intelligence block synthesis."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from crypto_probability_engine.adapters.http_client import PublicHttpClient
from crypto_probability_engine.config.unit_discipline import utc_now
from crypto_probability_engine.derivatives_intel.instruments import (
    InstrumentResolutionStatus,
)
from crypto_probability_engine.derivatives_intel.provenance import (
    INFLUENCE_MODE,
    METHODOLOGY_VERSION,
    build_binance_current_funding_metric,
    build_binance_current_open_interest_metric,
    build_okx_current_funding_metric,
    build_okx_current_open_interest_metrics,
)
from crypto_probability_engine.derivatives_intel.runtime import (
    PROVIDERS_V0,
    PROVIDERS_V1_OKX_ONLY,
    RawDerivativesBundle,
    RawProviderBundle,
    get_raw_derivatives_bundle,
)
from crypto_probability_engine.derivatives_intel.schemas import (
    METHODOLOGY_VERSION_V0,
    METHODOLOGY_VERSION_V1,
    PROVIDER_POLICY_VERSION_V1,
    SCHEMA_VERSION_V0,
    SCHEMA_VERSION_V1,
)

SCHEMA_VERSION = SCHEMA_VERSION_V0
DECISION_INFLUENCE_FRAC = 0.0
PLAIN_ENGLISH = "Derivatives context — observe only, not used in the decision."
METHODOLOGY_PROVIDER_POLICIES = {
    METHODOLOGY_VERSION_V0: {
        "schema_version": SCHEMA_VERSION_V0,
        "providers": PROVIDERS_V0,
        "provider_policy_version": None,
    },
    METHODOLOGY_VERSION_V1: {
        "schema_version": SCHEMA_VERSION_V1,
        "providers": PROVIDERS_V1_OKX_ONLY,
        "provider_policy_version": PROVIDER_POLICY_VERSION_V1,
    },
}


class ProviderSummaryStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    DEGRADED_PARTIAL = "DEGRADED_PARTIAL"
    UNSUPPORTED_INSTRUMENT = "UNSUPPORTED_INSTRUMENT"
    INSTRUMENT_INACTIVE = "INSTRUMENT_INACTIVE"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    NO_VALID_METRIC = "NO_VALID_METRIC"


def build_derivatives_intelligence(
    *,
    normalized_symbol: str,
    core_prediction_as_of_utc: datetime,
    enabled: bool,
    http_client: PublicHttpClient | None = None,
    now_utc: datetime | None = None,
    rate_limit_per_min: int = 120,
    methodology_version: str = METHODOLOGY_VERSION,
) -> dict[str, Any]:
    """Build a request-specific block while containing all provider failures."""

    core_time = _require_utc(core_prediction_as_of_utc)
    policy = _policy_for_methodology(methodology_version)
    if not enabled:
        return _base_block(
            normalized_symbol=normalized_symbol,
            core_prediction_as_of_utc=core_time,
            observation_as_of_utc=None,
            block_status="DISABLED",
            provider_summary=[],
            metrics=[],
            comparability=[],
            warnings=[],
            methodology_version=methodology_version,
            schema_version=policy["schema_version"],
            provider_policy_version=policy["provider_policy_version"],
        )

    try:
        raw_bundle = get_raw_derivatives_bundle(
            normalized_symbol,
            providers=policy["providers"],
            http_client=http_client,
            rate_limit_per_min=rate_limit_per_min,
        )
    except Exception:
        observation = _require_utc(now_utc or utc_now())
        return _unavailable_block(
            normalized_symbol,
            core_time,
            observation,
            methodology_version=methodology_version,
            schema_version=policy["schema_version"],
            providers=policy["providers"],
            provider_policy_version=policy["provider_policy_version"],
        )

    observation = _require_utc(now_utc or utc_now())
    try:
        return _build_enabled_block(
            raw_bundle,
            core_time,
            observation,
            methodology_version=methodology_version,
            schema_version=policy["schema_version"],
            provider_policy_version=policy["provider_policy_version"],
        )
    except Exception:
        return _unavailable_block(
            normalized_symbol,
            core_time,
            observation,
            methodology_version=methodology_version,
            schema_version=policy["schema_version"],
            providers=policy["providers"],
            provider_policy_version=policy["provider_policy_version"],
        )


def _build_enabled_block(
    raw_bundle: RawDerivativesBundle,
    core_time: datetime,
    observation: datetime,
    *,
    methodology_version: str,
    schema_version: str,
    provider_policy_version: str | None,
) -> dict[str, Any]:
    metrics: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    warnings: list[str] = []

    for provider_bundle in raw_bundle.providers:
        provider_metrics = _provider_metrics(
            provider_bundle, observation, methodology_version=methodology_version
        )
        metrics.extend(provider_metrics)
        summary = _provider_summary(provider_bundle, provider_metrics)
        summaries.append(summary)
        if summary["status"] != ProviderSummaryStatus.AVAILABLE.value:
            warnings.append(f"{provider_bundle.provider}: {summary['reason']}")

    block_status = _block_status_for_methodology(
        summaries, methodology_version=methodology_version
    )
    return _base_block(
        normalized_symbol=raw_bundle.normalized_symbol,
        core_prediction_as_of_utc=core_time,
        observation_as_of_utc=observation,
        block_status=block_status,
        provider_summary=summaries,
        metrics=metrics,
        comparability=_comparability(metrics, methodology_version=methodology_version),
        warnings=warnings,
        methodology_version=methodology_version,
        schema_version=schema_version,
        provider_policy_version=provider_policy_version,
    )


def _provider_metrics(
    bundle: RawProviderBundle, observation: datetime, *, methodology_version: str
) -> list[dict[str, Any]]:
    if bundle.instrument is None:
        return []
    resolution = bundle.instrument.thaw()
    metrics: list[dict[str, Any]] = []
    funding = bundle.thaw_funding()
    oi = bundle.thaw_open_interest()
    if funding is not None and bundle.funding_fetched_at_utc is not None:
        if bundle.provider == "BINANCE_USDM":
            metrics.append(
                build_binance_current_funding_metric(
                    funding,
                    resolution,
                    fetched_at_utc=bundle.funding_fetched_at_utc,
                    prediction_as_of_utc=observation,
                )
            )
        else:
            metrics.append(
                build_okx_current_funding_metric(
                    funding,
                    resolution,
                    fetched_at_utc=bundle.funding_fetched_at_utc,
                    prediction_as_of_utc=observation,
                    methodology_version=methodology_version,
                )
            )
    if oi is not None and bundle.open_interest_fetched_at_utc is not None:
        if bundle.provider == "BINANCE_USDM":
            metrics.append(
                build_binance_current_open_interest_metric(
                    oi,
                    resolution,
                    fetched_at_utc=bundle.open_interest_fetched_at_utc,
                    prediction_as_of_utc=observation,
                )
            )
        else:
            metrics.extend(
                build_okx_current_open_interest_metrics(
                    oi,
                    resolution,
                    fetched_at_utc=bundle.open_interest_fetched_at_utc,
                    prediction_as_of_utc=observation,
                    methodology_version=methodology_version,
                )
            )
    return metrics


def _provider_summary(bundle: RawProviderBundle, metrics: list[dict[str, Any]]) -> dict[str, Any]:
    valid_count = sum(metric.get("status") == "VALID" for metric in metrics)
    total_count = 2 if bundle.provider == "BINANCE_USDM" else 4
    resolution_status = bundle.instrument.status if bundle.instrument is not None else None

    if resolution_status == InstrumentResolutionStatus.UNSUPPORTED_INSTRUMENT.value:
        status = ProviderSummaryStatus.UNSUPPORTED_INSTRUMENT
        reason = bundle.instrument.reason
    elif resolution_status == InstrumentResolutionStatus.INSTRUMENT_INACTIVE.value:
        status = ProviderSummaryStatus.INSTRUMENT_INACTIVE
        reason = bundle.instrument.reason
    elif bundle.fetch_status == "PROVIDER_UNAVAILABLE":
        status = ProviderSummaryStatus.PROVIDER_UNAVAILABLE
        reason = bundle.reason or "Public provider resources unavailable."
    elif valid_count == total_count and total_count > 0 and bundle.fetch_status == "OK":
        status = ProviderSummaryStatus.AVAILABLE
        reason = None
    elif valid_count > 0:
        status = ProviderSummaryStatus.DEGRADED_PARTIAL
        reason = bundle.reason or "Only part of the current provider evidence is valid."
    else:
        status = ProviderSummaryStatus.NO_VALID_METRIC
        reason = (
            bundle.instrument.reason
            if bundle.instrument is not None and bundle.instrument.reason
            else bundle.reason or "No current provider metric passed provenance validation."
        )
    return {
        "provider": bundle.provider,
        "status": status.value,
        "valid_metric_count": valid_count,
        "total_metric_count": total_count,
        "reason": reason,
    }


def _block_status_for_methodology(
    summaries: list[dict[str, Any]], *, methodology_version: str
) -> str:
    available_count = sum(
        summary["status"] == ProviderSummaryStatus.AVAILABLE.value for summary in summaries
    )
    if methodology_version == METHODOLOGY_VERSION_V1:
        okx = next((summary for summary in summaries if summary["provider"] == "OKX_SWAP"), None)
        if okx is None:
            return "UNAVAILABLE"
        if (
            okx["status"] == ProviderSummaryStatus.AVAILABLE.value
            and okx["valid_metric_count"] == okx["total_metric_count"] == 4
        ):
            return "ACTIVE"
        if okx["valid_metric_count"] > 0:
            return "DEGRADED"
        return "UNAVAILABLE"
    return (
        "ACTIVE"
        if available_count == len(summaries) and summaries
        else "DEGRADED"
        if available_count > 0
        else "UNAVAILABLE"
    )


def _comparability(
    metrics: list[dict[str, Any]], *, methodology_version: str = METHODOLOGY_VERSION
) -> list[dict[str, Any]]:
    if methodology_version == METHODOLOGY_VERSION_V1:
        return []
    funding = {
        metric["provider"]: metric
        for metric in metrics
        if metric["metric_id"]
        in {"binance.funding.current_estimate", "okx.funding.current_estimate"}
    }
    oi = {
        metric["provider"]: metric
        for metric in metrics
        if metric["metric_id"]
        in {"binance.open_interest.current", "okx.open_interest.current.contracts"}
    }
    return [
        _comparison(
            semantic_class="CURRENT_FUNDING",
            left=funding.get("BINANCE_USDM"),
            right=funding.get("OKX_SWAP"),
            funding=True,
        ),
        _comparison(
            semantic_class="CURRENT_OPEN_INTEREST",
            left=oi.get("BINANCE_USDM"),
            right=oi.get("OKX_SWAP"),
            funding=False,
        ),
    ]


def _comparison(
    *,
    semantic_class: str,
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
    funding: bool,
) -> dict[str, Any]:
    reason: str
    comparable = False
    if left is None or right is None:
        reason = "Both provider-native metrics are required for comparison."
    elif left["status"] != "VALID" or right["status"] != "VALID":
        reason = "Both provider-native metrics must be valid and fresh."
    elif not left["no_lookahead_assertion"] or not right["no_lookahead_assertion"]:
        reason = "Both provider-native metrics require valid observation ordering."
    elif any(
        left[field] != right[field]
        for field in ("family", "contract_type", "margin_asset", "settlement_asset", "unit")
    ):
        reason = "Provider-native contracts or units are not equivalent."
    elif funding and (left["timeframe_or_period"] is None or right["timeframe_or_period"] is None):
        reason = "Funding interval semantics are not confirmed for both providers."
    elif left["event_time"] != right["event_time"]:
        reason = "Provider event timestamps are not aligned."
    else:
        comparable = True
        reason = "Provider-native metric semantics are aligned."
    return {
        "semantic_class": semantic_class,
        "left_provider": "BINANCE_USDM",
        "right_provider": "OKX_SWAP",
        "comparable": comparable,
        "reason": reason,
    }


def _base_block(
    *,
    normalized_symbol: str,
    core_prediction_as_of_utc: datetime,
    observation_as_of_utc: datetime | None,
    block_status: str,
    provider_summary: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
    comparability: list[dict[str, Any]],
    warnings: list[str],
    methodology_version: str,
    schema_version: str,
    provider_policy_version: str | None,
) -> dict[str, Any]:
    block = {
        "schema_version": schema_version,
        "influence_mode": INFLUENCE_MODE,
        "decision_influence_frac": DECISION_INFLUENCE_FRAC,
        "methodology_version": methodology_version,
        "normalized_symbol": normalized_symbol,
        "core_prediction_as_of_utc": _timestamp(core_prediction_as_of_utc),
        "observation_as_of_utc": _timestamp(observation_as_of_utc),
        "block_status": block_status,
        "provider_summary": provider_summary,
        "metrics": metrics,
        "comparability": comparability,
        "disagreement": [],
        "warnings": warnings,
        "not_trade_command": True,
        "not_financial_advice": True,
        "plain_english": PLAIN_ENGLISH,
    }
    if provider_policy_version is not None:
        block["provider_policy_version"] = provider_policy_version
    return block


def _unavailable_block(
    normalized_symbol: str,
    core_time: datetime,
    observation: datetime,
    *,
    methodology_version: str = METHODOLOGY_VERSION,
    schema_version: str = SCHEMA_VERSION,
    providers: tuple[str, ...] = PROVIDERS_V0,
    provider_policy_version: str | None = None,
) -> dict[str, Any]:
    summaries = [
        {
            "provider": provider,
            "status": ProviderSummaryStatus.PROVIDER_UNAVAILABLE.value,
            "valid_metric_count": 0,
            "total_metric_count": 0,
            "reason": "Public provider resources unavailable.",
        }
        for provider in providers
    ]
    return _base_block(
        normalized_symbol=normalized_symbol,
        core_prediction_as_of_utc=core_time,
        observation_as_of_utc=observation,
        block_status="UNAVAILABLE",
        provider_summary=summaries,
        metrics=[],
        comparability=_comparability([], methodology_version=methodology_version),
        warnings=["Derivatives context unavailable; core analysis is unchanged."],
        methodology_version=methodology_version,
        schema_version=schema_version,
        provider_policy_version=provider_policy_version,
    )


def _policy_for_methodology(methodology_version: str) -> dict[str, Any]:
    try:
        return METHODOLOGY_PROVIDER_POLICIES[methodology_version]
    except KeyError as exc:
        raise ValueError("Unsupported derivatives methodology version.") from exc


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value is not None else None


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
        raise ValueError("Derivatives timestamps must be timezone-aware UTC values.")
    return value
