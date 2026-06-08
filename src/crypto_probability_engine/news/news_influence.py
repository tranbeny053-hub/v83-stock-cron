"""News influence authority limits."""

from __future__ import annotations


def compute_news_influence(news_addon_state: dict) -> dict:
    return {
        "status": news_addon_state.get("status", "UNAVAILABLE"),
        "influence_mode": news_addon_state.get("influence_mode", "ADVISORY_DISPLAY_ONLY"),
        "news_influence_frac": 0.0,
        "can_force_constructive": False,
        "can_override_hard_gates": False,
        "sentiment_only_action": "FORBIDDEN",
    }


def apply_news_to_score(score_state: dict, news_influence: dict) -> dict:
    adjusted = dict(score_state)
    adjusted["news_influence_frac"] = 0.0
    adjusted["news_authority_applied"] = False
    adjusted["news_can_force_constructive"] = False
    adjusted["disposition"] = score_state.get("disposition", "WATCH")
    return adjusted
