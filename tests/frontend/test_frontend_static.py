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
    assert "DEGRADED DATA" in js
    assert "DATA UNAVAILABLE" in js


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


def test_single_analysis_has_six_timeframe_cards_not_primary_dropdown() -> None:
    html = read_frontend("index.html")
    js = read_frontend("app.js")
    single_section = html.split('id="singlePanel"', maxsplit=1)[1].split(
        'id="batchPanel"', maxsplit=1
    )[0]
    assert 'name="timeframe"' not in single_section
    assert "timeframe-card-grid" in single_section
    for timeframe in ("15m", "1H", "4H", "1D", "1W", "1M"):
        assert f'"{timeframe}"' in js


def test_batch_timeframe_dropdown_includes_monthly() -> None:
    html = read_frontend("index.html")
    batch_section = html.split('id="batchPanel"', maxsplit=1)[1].split(
        'id="devPanel"', maxsplit=1
    )[0]
    assert 'name="timeframe"' in batch_section
    assert "<option>1M</option>" in batch_section


def test_single_cards_and_detail_view_have_polished_layout_hooks() -> None:
    css = read_frontend("styles.css")
    js = read_frontend("app.js")
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in css
    assert "renderStructuredDetail" in js
    for heading in (
        "Overview",
        "Probability",
        "Risk / Gates",
        "Market Data Quality",
        "Provider State",
        "Quant Signals",
        "News Add-on",
        "Debug / Raw JSON",
    ):
        assert heading in js
    assert "raw-json" in js
    assert "News analysis disabled for this run." in js


def test_score_heat_uses_six_discrete_backend_score_bands() -> None:
    js = read_frontend("app.js")
    css = read_frontend("styles.css")
    for threshold in ("86", "71", "56", "41", "21"):
        assert threshold in js
    for color in ("#FF1A1A", "#F43F3F", "#DC2626", "#9F3A3A", "#5A4545", "#374151"):
        assert color in js
    for class_name in (
        "heat-extreme",
        "heat-very-hot",
        "heat-hot",
        "heat-warm",
        "heat-low",
        "heat-cold",
    ):
        assert class_name in js
        assert f".{class_name}" in css
    assert "getScoreHeatBand" in js
    assert "display.total_score" in js


def test_batch_cards_reuse_structured_detail_renderer() -> None:
    html = read_frontend("index.html")
    js = read_frontend("app.js")
    single_section = html.split('id="singlePanel"', maxsplit=1)[1].split(
        'id="batchPanel"', maxsplit=1
    )[0]
    assert 'id="detailPanel"' not in single_section
    assert (
        "renderResults(document.querySelector(\"#batchResult\"), payload.results, payload.errors)"
        in js
    )
    assert "target.append(overviewCard(payload))" in js
    assert "openDetail(payload)" in js
    assert "/v1/analyze/detail/" in js
    assert "payload.detail_view" in js
    assert "renderStructuredDetail(payload, detailView)" in js
    assert "Detail Analysis is unavailable for this result." in js


def test_site_signature_is_visible_and_in_normal_flow() -> None:
    html = read_frontend("index.html")
    css = read_frontend("styles.css")
    assert "Copyright © 2026 by Kha" in html
    assert "site-signature" in html
    assert "font-family: Georgia" in css
    assert "position: fixed" not in css


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


def test_live_smoke_script_is_flag_gated() -> None:
    script = (ROOT / "scripts" / "live_smoke.py").read_text(encoding="utf-8")
    assert "UCPE_LIVE_SMOKE_ENABLED" in script
    assert "SKIP:" in script
    assert "data_mode=\"live\"" in script
