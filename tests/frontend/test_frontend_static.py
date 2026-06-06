from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read_frontend(name: str) -> str:
    return (ROOT / "frontend" / name).read_text(encoding="utf-8")


def test_heat_legend_and_metrics_only_news_copy_present() -> None:
    js = read_frontend("app.js")
    assert "Signal heat — not risk" in js
    assert "News disabled in METRICS_ONLY." in js
    assert "DEMO DATA" in js


def test_frontend_uses_backend_display_fields() -> None:
    js = read_frontend("app.js")
    assert "frontend_display" in js
    for forbidden in (
        "p_up_frac",
        "p_down_frac",
        "p_timeout_frac",
        "score_stack",
        "trend_summary",
        "news_influence_frac",
    ):
        assert forbidden not in js


def test_no_secret_markers_in_frontend() -> None:
    combined = "\n".join(
        [
            read_frontend("index.html"),
            read_frontend("styles.css"),
            read_frontend("app.js"),
        ]
    )
    for marker in (
        "APP_ACCESS_CODE_HASH",
        "DEV_MODE_CODE_HASH",
        "SESSION_SIGNING_KEY",
        "API_KEY",
        "PASSWORD",
        "PRIVATE_KEY",
    ):
        assert marker not in combined
