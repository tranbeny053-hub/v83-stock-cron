"""Detail view builder."""

from __future__ import annotations


def build_detail_view(
    *,
    symbol: str,
    run_id: str,
    analysis_mode: str,
    quant_result: dict,
    news_blocks: dict,
    provider_state: dict,
    data_quality: dict,
) -> dict:
    return {
        "symbol": symbol,
        "run_id": run_id,
        "analysis_mode": analysis_mode,
        "sections": [
            "SUMMARY",
            "PROBABILITY",
            "SCORE",
            "RISK",
            "LIQUIDITY_EXECUTION",
            "DATA_QUALITY",
            "MARKET_DATA_V2",
            "NEWS",
            "DEBUG_LITE",
        ],
        "metrics_detail": {
            "market_features": quant_result["market_features"],
            "trend_summary": quant_result["trend_summary"],
        },
        "probability_detail": quant_result["probability_state"],
        "score_detail": quant_result["score_stack"],
        "risk_detail": {
            "risk_arbiter": quant_result["risk_arbiter_state"],
            "tail_risk": quant_result["tail_risk_state"],
        },
        "liquidity_execution_detail": {
            "liquidity_state": quant_result["liquidity_state"],
            "execution_realism": quant_result["execution_realism"],
        },
        "data_quality_detail": {
            "provider_state": provider_state,
            "data_quality": data_quality,
            "epistemic_sufficiency": quant_result["epistemic_sufficiency_state"],
        },
        "market_data_v2_detail": {
            "provider_resources": data_quality.get("provider_resources", {}),
            "derived_market_metrics": data_quality.get("derived_market_metrics", {}),
            "symbol_availability": data_quality.get("symbol_availability"),
            "cross_provider_state": data_quality.get("cross_provider_state"),
            "fallback_to_single_provider": data_quality.get("fallback_to_single_provider"),
            "disagreement_bps": data_quality.get("disagreement_bps"),
            "warnings": data_quality.get("warnings", []),
        },
        "invalidation_detail": quant_result["gate_result"],
        "news_detail": {
            "news_addon_state": news_blocks["news_addon_state"],
            "micro_news_context": news_blocks["micro_news_context"],
            "news_influence": news_blocks["news_influence"],
        },
        "macro_detail": news_blocks["macro_context"],
        "debug_lite": {
            "analysis_hash": quant_result["analysis_hash"],
            "calibration_state": quant_result["calibration_state"],
        },
    }
