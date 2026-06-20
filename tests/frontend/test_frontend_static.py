from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read_frontend(name: str) -> str:
    return (ROOT / "frontend" / name).read_text(encoding="utf-8")


def test_heat_legend_and_metrics_only_news_copy_present() -> None:
    html = read_frontend("index.html")
    js = read_frontend("app.js")
    assert "Signal heat — not risk" in js
    assert "News disabled in METRICS_ONLY." in js
    assert "DEMO DATA" in js
    assert "DEGRADED DATA" in js
    assert "DATA UNAVAILABLE" in js
    assert "Watchlist persistence:" in js
    assert "Persistence:" in html


def test_frontend_assets_are_versioned_for_deploy_cachebust() -> None:
    html = read_frontend("index.html")
    js = read_frontend("app.js")
    version = "ui-d1-5b-trade-plan-render"
    assert f'href="/styles.css?v={version}"' in html
    assert f'src="/app.js?v={version}"' in html
    assert f'const UCPE_FRONTEND_BUILD = "{version}";' in js


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
    assert "horizon-results" in single_section
    for timeframe in ("15m", "1H", "4H", "1D", "1W", "1M"):
        assert f'"{timeframe}"' in js


def test_ui_d1_3_groups_tactical_and_regime_timeframes_in_order() -> None:
    js = read_frontend("app.js")
    assert 'const tacticalTimeframes = ["15m", "1H", "4H"]' in js
    assert 'const regimeTimeframes = ["1D", "1W", "1M"]' in js
    assert "Tactical Horizon Matrix" in js
    assert "Regime Context" in js
    groups = js.split("function horizonGroups", maxsplit=1)[1].split(
        "function appendDefinitionRows", maxsplit=1
    )[0]
    assert groups.index('key: "tactical"') < groups.index('key: "regime"')
    assert groups.index("timeframes: tacticalTimeframes") < groups.index(
        "timeframes: regimeTimeframes"
    )


def test_ui_d1_3_uses_backend_timeframe_role_with_safe_fallback() -> None:
    js = read_frontend("app.js")
    role_chunk = js.split("function timeframeRoleFor", maxsplit=1)[1].split(
        "function timeframeGroupFor", maxsplit=1
    )[0]
    assert "decision_synthesis?.timeframe_role" in role_chunk
    assert "backendRole.tactical" in role_chunk
    assert "backendRole.raw_probability_hidden_by_default" in role_chunk
    assert "backendRole.plain_english" in role_chunk
    assert "fallbackTimeframeRoles" in role_chunk


def test_ui_d1_3_hides_long_horizon_raw_probability_in_collapsed_context() -> None:
    js = read_frontend("app.js")
    assert "role.rawProbabilityHidden" in js
    assert 'document.createElement("details")' in js
    assert "Advanced (uncalibrated context)" in js
    assert "Uncalibrated context. Treat these values as informational only." in js
    assert '"1W"' in js and "rawProbabilityHidden: true" in js
    assert '"1M"' in js and "rawProbabilityHidden: true" in js


def test_ui_d1_3_hard_gate_dominates_muted_probability() -> None:
    js = read_frontend("app.js")
    css = read_frontend("styles.css")
    assert 'item.status === "BLOCK"' in js
    assert "matrix-block-banner" in js
    assert 'decisionBadge("BLOCK", "block")' in js
    assert "probability.informational_only === true" in js
    assert "Informational only" in js
    assert ".matrix-block-banner" in css
    assert ".matrix-probability-muted" in css


def test_ui_d1_3_tactical_alignment_is_label_and_status_derived_only() -> None:
    js = read_frontend("app.js")
    chunk = js.split("function tacticalAlignmentState", maxsplit=1)[1].split(
        "function tacticalAlignmentCopy", maxsplit=1
    )[0]
    assert "decision_synthesis?.decision_synthesis?.label" in chunk
    assert "actionability_stack" in chunk
    assert 'item.status === "BLOCK"' in chunk
    assert "model_quality_summary" in chunk
    for probability_name in (
        "p_" "up",
        "p_" "down",
        "prob_" "up",
        "prob_" "down",
        "directional_" "edge",
    ):
        assert probability_name not in chunk
    for state in ("blocked", "aligned", "mixed", "insufficient", "unavailable"):
        assert f'"{state}"' in chunk or f'"{state}"' in js
    assert "Display-only summary of currently shown backend labels." in js


def test_ui_d1_3_missing_timeframe_keeps_card_and_alignment_unavailable() -> None:
    js = read_frontend("app.js")
    assert "errorCard(timeframe, error)" in js
    assert "payloads.length < tacticalTimeframes.length" in js
    assert 'return "unavailable"' in js
    assert "Tactical alignment unavailable" in js
    assert "updateTacticalAlignment(target, payloadStore)" in js


def test_ui_d1_3_matrix_has_no_permission_label_or_zone_inference() -> None:
    js = read_frontend("app.js")
    alignment_chunk = js.split("function tacticalAlignmentState", maxsplit=1)[1].split(
        "function tacticalAlignmentCopy", maxsplit=1
    )[0]
    assert "can_enter_now = true" not in js
    assert "canEnterNow = true" not in js
    assert "> probability.p_" not in alignment_chunk
    assert "> display.prob_" not in alignment_chunk
    assert "decisionLabelCopy[decision.label]" in js
    matrix_chunk = js.split("function overviewCard", maxsplit=1)[1].split(
        "function errorCard", maxsplit=1
    )[0]
    assert "scenarioPlanTextFields" not in matrix_chunk


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
        "Market Data v2 / Provider Observability",
        "Decision Brief",
        "Quant Signals",
        "News Add-on",
        "News Authority / Macro & Micro Context",
        "Debug / Raw JSON",
    ):
        assert heading in js
    assert "raw-json" in js
    assert "News analysis disabled for this run." in js


def test_decision_section_reads_backend_contract_and_renders_first() -> None:
    js = read_frontend("app.js")
    html = read_frontend("index.html")
    for marker in (
        "decision_synthesis",
        "action_permission",
        "actionability_stack",
        "model_quality_summary",
        "trade_plan_skeleton",
        "advisor_explanations",
        "probability_interpretation",
    ):
        assert marker in js
    detail_chunk = js.split("function renderStructuredDetail", maxsplit=1)[1]
    replacement = detail_chunk.split("detailPanel.replaceChildren(", maxsplit=1)[1]
    assert replacement.index("renderDecisionSynthesis") < replacement.index('section("Overview"')
    assert replacement.index("renderDecisionSynthesis") < replacement.index(
        "renderModelQualitySection"
    )
    assert replacement.index("renderModelQualitySection") < replacement.index(
        'section("Overview"'
    )
    assert 'data-tab="decision"' not in html


def test_decision_renderer_has_no_client_side_decision_or_zone_inference() -> None:
    js = read_frontend("app.js")
    inference_patterns = (
        r"probability\.p_up\s*>\s*probability\.p_down",
        r"can_enter_now\s*=\s*true",
        r"canEnterNow\s*=\s*true",
        r"label\s*=\s*['\"](?:LONG|SHORT)['\"]",
    )
    assert not any(re.search(pattern, js, flags=re.IGNORECASE) for pattern in inference_patterns)
    scenario_chunk = js.split("const scenarioPlanTextFields", maxsplit=1)[1].split(
        "function renderFutureQuantHooks", maxsplit=1
    )[0]
    for zone_field in (
        "preferred_entry_zone",
        "acceptable_entry_zone",
        "chase_zone",
        "breakout_trigger",
        "pullback_trigger",
        "stop_invalidation",
        "take_profit_plan",
        "risk_reward_summary",
    ):
        assert js.count(zone_field) == 1
        assert zone_field in scenario_chunk
    assert "backendText(plan[key])" in scenario_chunk


def test_decision_renderer_uses_safe_candidate_and_probability_copy() -> None:
    js = read_frontend("app.js")
    assert "Long candidate (plan only)" in js
    assert "Short candidate (plan only)" in js
    assert "Candidate plan only — not a trade command." in js
    assert "Informational only" in js
    assert "probability.informational_only" in js
    candidate_copy = js.split("const decisionLabelCopy", maxsplit=1)[1].split("};", maxsplit=1)[0]
    assert '"Buy"' not in candidate_copy
    assert '"Sell"' not in candidate_copy


def test_frontend_contains_no_unsafe_decision_wording() -> None:
    combined = "\n".join(
        read_frontend(name).lower() for name in ("app.js", "index.html", "styles.css")
    )
    forbidden = (
        "buy " "now",
        "sell " "now",
        "guaran" "teed",
        "safe " "trade",
        "sure " "long",
        "sure " "short",
        "will " "pump",
        "will " "dump",
        "win " "rate",
        "profit" "able",
        "confidence is " "high",
        "accuracy " "proven",
        "guaran" "teed " "profit",
    )
    assert not any(phrase in combined for phrase in forbidden)


def test_decision_renderer_has_safe_missing_contract_and_null_plan_behavior() -> None:
    js = read_frontend("app.js")
    assert "Decision synthesis unavailable for this run." in js
    assert "decisionBrief.action" in js
    assert "decisionBrief.state_summary" in js
    assert "Scenario plan unavailable. Keep using the Decision summary and hard gates." in js
    assert "Numeric entry, stop, target, and risk/reward are disabled for now." in js
    assert "renderTradePlanSkeleton" in js
    assert "formatValue(null)" not in js


def test_ui_d1_5b_scenario_plan_renders_backend_contract_with_qa_hook() -> None:
    js = read_frontend("app.js")
    for marker in (
        "data-trade-plan-skeleton",
        "Scenario plan",
        "Plan status",
        "Direction context",
        "Immediate action",
        "Chase move",
        "Why this is limited",
        "Wait for confirmation",
        "What would change the plan",
        "Safety notes",
    ):
        assert marker in js
    for field in (
        "plan.mode",
        "plan.plan_status",
        "plan.setup_direction",
        "plan.can_enter_now",
        "plan.can_chase",
        "plan.disabled_reason",
        "plan.confirmation_required",
        "plan.chase_warning",
        "plan.what_would_change_plan",
        "plan.safety_copy",
    ):
        assert field in js


def test_ui_d1_5b_scenario_plan_has_safe_display_copy_and_fallbacks() -> None:
    js = read_frontend("app.js")
    for copy in (
        "No action now",
        "Missed move — do not chase",
        "Conditional candidate",
        "Long context",
        "Short context",
        "Candidate plan only — not a trade command.",
        "Not financial advice.",
        "Numeric entry, stop, and target are disabled until calibration is measured.",
        "No actionable plan is available from the current evidence.",
        "No confirmation path is available yet.",
        "No plan-changing condition is available yet.",
    ):
        assert copy in js


def test_ui_d1_5b_scenario_plan_does_not_invent_numeric_values_or_call_api() -> None:
    js = read_frontend("app.js")
    chunk = js.split("const scenarioModeCopy", maxsplit=1)[1].split(
        "function renderFutureQuantHooks", maxsplit=1
    )[0]
    zone_fields = (
        "preferred_entry_zone",
        "acceptable_entry_zone",
        "chase_zone",
        "breakout_trigger",
        "pullback_trigger",
        "stop_invalidation",
        "take_profit_plan",
        "risk_reward_summary",
    )
    for field in zone_fields:
        assert f'"{field}"' in chunk
    assert "backendText(plan[key])" in chunk
    for calculation_helper in ("formatNumber(", "formatPct(", "parseFloat(", "Number("):
        assert calculation_helper not in chunk
    assert not re.search(
        r"(?:preferred_entry_zone|stop_invalidation|take_profit_plan|risk_reward_summary)"
        r"[^\n]*(?:\+|-|\*|/)",
        chunk,
    )
    assert "api(" not in chunk
    assert "fetch(" not in chunk


def test_ui_d1_5b_scenario_plan_is_isolated_from_decision_logic() -> None:
    js = read_frontend("app.js")
    chunk = js.split("function renderTradePlanSkeleton", maxsplit=1)[1].split(
        "function renderFutureQuantHooks", maxsplit=1
    )[0]
    assert "plan = {}" in chunk
    for foreign_source in (
        "decision_label",
        "probability_interpretation",
        "actionability_stack",
        "gate_result",
        "model_quality_summary",
        "action_permission",
    ):
        assert foreign_source not in chunk
    assert "can_enter_now = true" not in chunk
    assert "can_chase = true" not in chunk


def test_ui_d1_5b_scenario_plan_avoids_actionable_wording() -> None:
    js = read_frontend("app.js")
    chunk = js.split("const scenarioModeCopy", maxsplit=1)[1].split(
        "function renderFutureQuantHooks", maxsplit=1
    )[0].lower()
    forbidden = (
        "buy " + "now",
        "sell " + "now",
        "enter " + "now",
        "guaran" + "teed",
        "safe " + "trade",
        "sure " + "long",
        "sure " + "short",
        "will " + "pump",
        "will " + "dump",
        "profit" + "able",
        "win " + "rate",
        "high " + "confidence",
        "accu" + "racy",
        "trade " + "ev",
        "lever" + "age",
        "position " + "size",
        "place " + "order",
        "execute " + "trade",
    )
    assert not any(phrase in chunk for phrase in forbidden)


def test_ui_d1_5b_scenario_plan_styles_preserve_containment_and_priority() -> None:
    css = read_frontend("styles.css")
    chunk = css.split(".scenario-plan {", maxsplit=1)[1].split(
        ".probability-informational", maxsplit=1
    )[0]
    for marker in (
        "grid-column: 1 / -1",
        "min-width: 0",
        "max-width: 100%",
        "flex-wrap: wrap",
        "overflow-wrap: anywhere",
        "white-space: normal",
    ):
        assert marker in chunk
    assert "overflow: hidden" not in chunk
    assert "decision-badge-candidate" not in chunk


def test_decision_renderer_prioritizes_backend_blocks_and_advanced_context() -> None:
    js = read_frontend("app.js")
    css = read_frontend("styles.css")
    assert 'stack.find((item) => item.status === "BLOCK")' in js
    assert 'stack.find((item) => item.status === "WARN")' in js
    assert 'item.key === "hard_gates" && item.status === "BLOCK"' in js
    assert 'item.key === "tail_risk"' in js
    assert "raw_probability_hidden_by_default" in js
    assert "decision-advanced-probability" in js
    assert "future_quant_v2_hooks" in js
    assert "influence_mode" in js
    assert "decision_influence_frac" in js
    assert ".actionability-block" in css
    assert "grid-column: 1 / -1" in css


def test_decision_reliability_uses_backend_summary_and_optional_samples() -> None:
    js = read_frontend("app.js")
    assert "quality.plain_english" in js
    assert "quality.warning" in js
    assert "quality.calibration_status" in js
    assert "quality.reliability_status" in js
    assert "quality.reliability_available" in js
    assert "quality.not_win_rate" in js
    assert "hasPayloadValue(quality.sample_count)" in js
    assert "hasPayloadValue(quality.sample_gate)" in js


def test_ui_d1_4_text_containment_safeguards_are_present() -> None:
    css = read_frontend("styles.css")
    for safeguard in (
        "overflow-wrap: anywhere",
        "min-width: 0",
        "minmax(0",
        "white-space: normal",
        "flex-wrap: wrap",
    ):
        assert safeguard in css
    for selector in (
        ".horizon-card",
        ".decision-context-card",
        ".actionability-row",
        ".detail-kv",
        ".detail-table",
        ".model-quality-education",
    ):
        assert selector in css
    assert "table-layout: fixed" in css


def test_ui_d1_4_does_not_clip_user_facing_cards() -> None:
    css = read_frontend("styles.css")
    assert "overflow: hidden" not in css
    assert "pre {" in css and "overflow: auto" in css


def test_ui_d1_4_model_quality_uses_payload_fields_and_safe_fallbacks() -> None:
    js = read_frontend("app.js")
    for field in (
        "model_quality_summary",
        "reliability_status",
        "reliability_available",
        "not_win_rate",
        "reliability_warning",
        "sample_gate",
    ):
        assert field in js
    for safe_copy in (
        "Model quality: not measured yet.",
        "Probabilities are heuristic until enough resolved samples exist.",
        "Resolved-sample metrics are not surfaced in this view yet.",
        "Keep collecting samples; this is not reliability evidence and not profitability evidence.",
    ):
        assert safe_copy in js
    assert "renderModelQualityEducation" in js
    assert 'document.createElement("details")' in js


def test_ui_d1_4_only_renders_non_null_calibration_metrics() -> None:
    js = read_frontend("app.js")
    for field in (
        "sample_count",
        "sample_gate",
        "brier_score",
        "log_loss",
        "top_label_hit_rate",
    ):
        assert f"hasPayloadValue(quality.{field})" in js
    for invented_fragment in (
        '"15m": 37',
        '"1H": 30',
        '"4H": 8',
        '"1D": 0',
    ):
        assert invented_fragment not in js


def test_ui_d1_4b_fetches_all_calibration_diagnostics_once_with_cache() -> None:
    js = read_frontend("app.js")
    load_chunk = js.split("async function loadCalibrationDiagnostics", maxsplit=1)[1].split(
        "function formatCalibrationMetric", maxsplit=1
    )[0]
    assert js.count('api("/v1/calibration")') == 1
    assert js.count("/v1/calibration") == 1
    assert "singleTimeframes" not in load_chunk
    assert "include_buckets" not in load_chunk
    assert "calibrationDiagnosticsCacheTtlMs = 60000" in js
    assert "calibrationDiagnosticsCache" in load_chunk
    assert "calibrationDiagnosticsRequest" in load_chunk


def test_ui_d1_4b_reads_calibration_contract_fields() -> None:
    js = read_frontend("app.js")
    for field in (
        "sample_gate",
        "sample_count",
        "valid_count",
        "reliability_status",
        "brier_score",
        "log_loss",
        "top_label_hit_rate",
        "outcome_distribution",
        "version_mix_warning",
        "versions_present",
    ):
        assert field in js
    assert "Top-label hit rate (diagnostic)" in js
    assert "UP ${formatCalibrationCount" in js


def test_ui_d1_4b_has_loading_unavailable_and_null_fallbacks() -> None:
    js = read_frontend("app.js")
    assert "Live calibration diagnostics" in js
    assert "Loading calibration diagnostics…" in js
    assert "Calibration diagnostics unavailable. Keep using heuristic status." in js
    assert 'setAttribute("data-calibration-diagnostics", "")' in js
    assert 'return "—";' in js
    assert "formatCalibrationMetric" in js
    assert "formatCalibrationPercent" in js
    assert "formatCalibrationCount" in js
    assert "error_class" not in js


def test_ui_d1_4b_calibration_render_is_non_blocking_and_diagnostic_only() -> None:
    js = read_frontend("app.js")
    model_quality_chunk = js.split("function renderModelQualitySection", maxsplit=1)[1].split(
        "function renderTradePlanSkeleton", maxsplit=1
    )[0]
    assert "calibrationDiagnosticsMount()" in model_quality_chunk
    assert "loadCalibrationDiagnostics()" in model_quality_chunk
    assert ".then((payload)" in model_quality_chunk
    assert "renderCalibrationDiagnostics(payload)" in model_quality_chunk
    assert "calibrationContent?.replaceChildren" in model_quality_chunk
    assert "await loadCalibrationDiagnostics()" not in model_quality_chunk
    assert "hydrateCalibrationDiagnostics" not in js
    calibration_chunk = js.split(
        "async function loadCalibrationDiagnostics", maxsplit=1
    )[1].split("function renderModelQualityEducation", maxsplit=1)[0]
    for field in (
        "sample_gate",
        "sample_count",
        "brier_score",
        "log_loss",
        "top_label_hit_rate",
    ):
        assert field in calibration_chunk
    for decision_target in (
        "decision_label",
        "can_enter_now",
        "can_chase",
        "candidate_is_not_entry_permission",
        "gate_result",
        "actionability_stack",
    ):
        assert decision_target not in calibration_chunk
    assert ".reduce(" not in calibration_chunk


def test_ui_d1_4b_fix_exposes_persistent_browser_qa_hooks() -> None:
    js = read_frontend("app.js")
    assert "Live calibration diagnostics" in js
    assert "Read-only diagnostic" in js
    assert "data-calibration-diagnostics" in js
    mount_chunk = js.split("function calibrationDiagnosticsMount", maxsplit=1)[1].split(
        "function renderModelQualityEducation", maxsplit=1
    )[0]
    assert "Loading calibration diagnostics…" in mount_chunk
    assert "calibration-diagnostics-content" in mount_chunk


def test_ui_d1_4b_calibration_wording_is_explicitly_safe() -> None:
    js = read_frontend("app.js")
    calibration_chunk = js.split(
        "async function loadCalibrationDiagnostics", maxsplit=1
    )[1].split("function renderModelQualityEducation", maxsplit=1)[0]
    assert "Early diagnostic only — not accuracy, not profitability evidence, not trade EV." in js
    assert "Top-label hit rate (diagnostic)" in calibration_chunk
    unsafe = (
        "win " + "rate",
        "profit" + "able",
        "reliable " + "signal",
        "high " + "confidence",
        "guaran" + "teed",
        "safe " + "trade",
        "buy " + "now",
        "sell " + "now",
    )
    assert not any(phrase in calibration_chunk.lower() for phrase in unsafe)
    for line in js.splitlines():
        lowered = line.lower()
        if "accuracy" in lowered:
            assert "not accuracy" in lowered
        if "profitability evidence" in lowered:
            assert "not profitability evidence" in lowered
        if "trade ev" in lowered:
            assert "not trade ev" in lowered


def test_ui_d1_4b_calibration_cards_preserve_containment() -> None:
    css = read_frontend("styles.css")
    for selector in (
        ".calibration-diagnostics",
        ".calibration-grid",
        ".calibration-timeframe-card",
        ".calibration-gate-badge",
        ".calibration-disclaimer",
    ):
        assert selector in css
    calibration_css = css.split(".calibration-diagnostics-mount", maxsplit=1)[1].split(
        ".decision-change-list", maxsplit=1
    )[0]
    assert "min-width: 0" in calibration_css
    assert "max-width: 100%" in calibration_css
    assert "overflow-wrap: anywhere" in calibration_css
    assert "flex-wrap: wrap" in calibration_css
    assert "overflow: hidden" not in calibration_css


def test_ui_d1_4b_does_not_hardcode_live_calibration_counts() -> None:
    js = read_frontend("app.js")
    for invented_fragment in (
        '"15m": 93',
        '"1H": 83',
        '"4H": 72',
        '"1D": 8',
        '"1W": 0',
        '"1M": 0',
    ):
        assert invented_fragment not in js


def test_ui_d1_4b_uses_endpoint_without_database_dependency() -> None:
    js = read_frontend("app.js").lower()
    assert "/v1/calibration" in js
    disallowed = (
        "supa" + "base",
        "psyco" + "pg",
        "db_" + "url",
        "post" + "gres://",
        "service" + "_role",
    )
    assert not any(marker in js for marker in disallowed)


def test_wave4a_honesty_copy_and_download_json_are_visible() -> None:
    html = read_frontend("index.html")
    js = read_frontend("app.js")
    css = read_frontend("styles.css")
    assert "Uncalibrated heuristic" in html
    assert "not validated forecasts" in html
    assert "Up/Down/Timeout are momentum-based estimates" in html
    assert "Open Detail for the full breakdown." in html
    assert "Download JSON" in js
    assert "downloadPayloadJson" in js
    assert "application/json" in js
    assert "decision_brief" in js
    assert "model readiness" in js.lower()
    assert "horizon_approx_label" in js
    assert ".honesty-banner" in css
    assert ".global-probability-legend" in css


def test_wave4a2_cards_show_probabilities_without_repeated_note() -> None:
    html = read_frontend("index.html")
    js = read_frontend("app.js")
    assert html.count("Up/Down/Timeout are momentum-based estimates") == 1
    assert "probability-explainer compact" not in js
    assert "qualitativeCardLean" not in js
    assert "uncalibrated" + " — see Detail" not in js
    assert "Open Detail for full probability" + " breakdown." not in js
    overview_chunk = js.split("function overviewCard", maxsplit=1)[1].split(
        "function loadingCard", maxsplit=1
    )[0]
    assert "prob_up_pct" in js
    assert "prob_down_pct" in js
    assert "prob_timeout_pct" in js
    assert "[\"Up\", formatPct(display.prob_up_pct)]" in overview_chunk
    assert "[\"Down\", formatPct(display.prob_down_pct)]" in overview_chunk
    assert "[\"Timeout\", formatPct(display.prob_timeout_pct)]" in overview_chunk
    assert "Probability" not in overview_chunk
    assert "Breakdown" not in overview_chunk
    assert "section(\"Probability\"" in js


def test_frontend_does_not_present_placeholder_confidence_as_real_confidence() -> None:
    js = read_frontend("app.js")
    html = read_frontend("index.html")
    assert "Confidence" not in js
    assert "confidence_frac" not in js
    assert (
        "Model readiness: Heuristic (uncalibrated) — not accuracy; quality is not yet measured."
        in js
    )
    assert "Model readiness" not in html or "Confidence" not in html


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


def test_watchlist_tab_symbol_view_and_detail_hooks_present() -> None:
    html = read_frontend("index.html")
    js = read_frontend("app.js")
    assert 'data-tab="watchlist"' in html
    assert 'id="watchlistPanel"' in html
    assert "Back to Watchlist" in html
    assert 'id="watchlistResult"' in html
    assert "horizon-results" in html
    assert "openWatchlistSymbol(symbol)" in js
    assert "runTimeframeSet" in js
    assert "watchlistPayloads" in js
    assert "/v1/watchlist" in js
    assert "openDetail(payload)" in js
    assert "/v1/analyze/detail/" in js


def test_refresh_control_and_persistence_badge_are_visible() -> None:
    html = read_frontend("index.html")
    js = read_frontend("app.js")
    css = read_frontend("styles.css")
    assert 'id="refreshButton"' in html
    assert "Re-analyze" in html
    assert 'id="lastRefreshed"' in html
    assert "last refreshed" in html
    assert 'id="persistenceStatusBadge"' in html
    assert "refreshCurrentView" in js
    assert "runSingleAnalysis" in js
    assert "runBatchAnalysis" in js
    assert "openWatchlistSymbol(currentWatchlistSymbol)" in js
    assert "refreshCooldownMs = 15000" in js
    assert "setAnalysisActive" in js
    assert ".shell-status-bar" in css
    assert ".status-badge" in css


def test_dev_mode_disabled_ux_copy_is_present_without_secret_names() -> None:
    html = read_frontend("index.html")
    js = read_frontend("app.js")
    assert "Dev Mode is disabled in this deployment." in html
    assert "Dev Mode is disabled in this deployment." in js
    assert "updateDevModeUx" in js
    assert "devModeStatus" in js


def test_frontend_has_no_direct_supabase_reference() -> None:
    combined = "\n".join(
        [
            read_frontend("index.html"),
            read_frontend("styles.css"),
            read_frontend("app.js"),
        ]
    )
    for marker in ("SUPABASE_DB_URL", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"):
        assert marker not in combined


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
        "FRED_API_KEY",
        "NEWSAPI_KEY",
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
