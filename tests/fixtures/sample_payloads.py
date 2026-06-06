"""Schema fixture payloads for Sprint 1 tests."""

from __future__ import annotations

from copy import deepcopy


def sample_analysis_payload(analysis_mode: str = "METRICS_ONLY") -> dict:
    disabled = analysis_mode == "METRICS_ONLY"
    news_status = "DISABLED_METRICS_ONLY" if disabled else "UNAVAILABLE"
    run_id = f"run_schema_{analysis_mode.lower()}"
    payload = {
        "schema_version": "1.1-crypto-probability",
        "run_id": run_id,
        "symbol": "BTC",
        "normalized_symbol": "BTC/USDT",
        "asset_class": "CRYPTO_SPOT",
        "analysis_mode": analysis_mode,
        "timeframes": {"primary": "4H", "trend": ["1H", "4H", "1D"]},
        "as_of_utc": "2026-06-06T00:00:00Z",
        "provider_state": {"status": "OK", "active_provider": "fixture"},
        "data_quality": {"status": "OK", "warnings": []},
        "market_features": {},
        "liquidity_state": {"status": "OK"},
        "execution_realism": {"status": "OK"},
        "quant_compute_state": {"status": "OK", "models_run": [], "models_skipped": []},
        "epistemic_sufficiency_state": {"sufficiency_level": "SUFFICIENT", "action": "ALLOW"},
        "probability_state": {
            "schema_version": "1.1-crypto-probability",
            "horizons": {
                "H_primary": {
                    "p_up_frac": 0.45,
                    "p_down_frac": 0.35,
                    "p_timeout_frac": 0.20,
                    "p_up_user_norm_frac": 0.5625,
                    "p_down_user_norm_frac": 0.4375,
                    "confidence_frac": 0.50,
                    "news_confidence_adj_frac": 0.0,
                    "status": "OK",
                    "null_reason": None,
                },
                "H_extended": {
                    "p_up_frac": 0.40,
                    "p_down_frac": 0.30,
                    "p_timeout_frac": 0.30,
                    "p_up_user_norm_frac": 0.5714285714,
                    "p_down_user_norm_frac": 0.4285714286,
                    "confidence_frac": 0.45,
                    "news_confidence_adj_frac": 0.0,
                    "status": "OK",
                    "null_reason": None,
                },
            },
            "calibration_status": "DEFAULT_PHASE1A",
            "null_reason": None,
        },
        "horizon_timeout_state": {"status": "OK"},
        "risk_arbiter_state": {"status": "OK"},
        "tail_risk_state": {"evt_status": "DISABLED_PHASE1A"},
        "calibration_state": {"reliability_status": "INSUFFICIENT_SAMPLE"},
        "macro_context": {"status": news_status},
        "micro_news_context": {"status": news_status, "items": []},
        "news_addon_state": {"status": news_status, "mode": analysis_mode},
        "news_materiality_state": {"status": news_status, "top_material_items": []},
        "event_horizon_state": {"status": news_status},
        "narrative_state": {"status": news_status},
        "novelty_surprise_state": {"status": news_status},
        "source_confidence_state": {"status": news_status},
        "information_state": {"status": news_status},
        "catalyst_state": {"status": news_status},
        "score_stack": {"total_score": 50},
        "trend_summary": {"label": "SIDEWAY", "magnitude_pct": 0.0},
        "frontend_display": {
            "prob_up_pct": 45.0,
            "prob_down_pct": 35.0,
            "prob_timeout_pct": 20.0,
            "total_score": 50,
            "risk_level": "UNKNOWN",
            "disposition": "WATCH",
            "analysis_mode_badge": analysis_mode,
            "detail_available": True,
            "key_reasons": [],
            "invalidation_conditions": [],
            "data_quality_warnings": [],
            "execution_warnings": [],
            "news_warnings": [],
        },
        "detail_view": {
            "symbol": "BTC",
            "run_id": run_id,
            "analysis_mode": analysis_mode,
            "sections": ["SUMMARY", "PROBABILITY", "NEWS"],
            "metrics_detail": {},
            "probability_detail": {},
            "score_detail": {},
            "risk_detail": {},
            "liquidity_execution_detail": {},
            "data_quality_detail": {},
            "invalidation_detail": {},
            "news_detail": {"status": news_status},
            "macro_detail": {"status": news_status},
            "debug_lite": {},
        },
        "gate_result": {"action": "WATCH", "hard_gate_passed": True},
        "debug": {"warnings": []},
        "analysis_hash": "sha256:schema-fixture",
    }
    return deepcopy(payload)

