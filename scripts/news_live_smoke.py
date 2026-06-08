"""Optional live smoke for advisory news providers.

Runs only when UCPE_NEWS_LIVE_SMOKE_ENABLED=true. It never prints secret values.
"""

from __future__ import annotations

from crypto_probability_engine.api.schemas import AnalysisMode
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.news.contract import build_news_blocks


def main() -> int:
    settings = Settings.from_env()
    if not settings.news_live_smoke_enabled:
        print("SKIP: set UCPE_NEWS_LIVE_SMOKE_ENABLED=true to run live news smoke.")
        return 0
    blocks = build_news_blocks(
        analysis_mode=AnalysisMode.NEWS_ADDON,
        symbol="BTC/USDT",
        settings=settings,
    )
    addon = blocks["news_addon_state"]
    if addon["news_influence_frac"] != 0.0:
        print("FAIL: news influence must remain 0.0.")
        return 1
    if addon["influence_mode"] != "ADVISORY_DISPLAY_ONLY":
        print("FAIL: influence mode must remain advisory display only.")
        return 1
    print(
        "PASS: news smoke completed "
        f"status={addon['status']} providers={addon['configured_source_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
