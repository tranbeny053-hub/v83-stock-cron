"""§5A.10 diagnostics: complete, and provably unable to change a verdict."""

from __future__ import annotations

from crypto_probability_engine.oos.evaluation import decision, diagnostics
from crypto_probability_engine.oos.evaluation.admission import admit
from tests.oos.evaluation.conftest import T0, T_CLOSE, T_FREEZE, daily_4h_evidence


def _admission():
    return admit(daily_4h_evidence(), t0=T0, t_close=T_CLOSE)


def test_every_pre_declared_diagnostic_is_present() -> None:
    block = diagnostics.build(
        _admission(), t0=T0, t_close=T_CLOSE, t_freeze=T_FREEZE, timeframes=["4H"]
    )
    for key in (
        "t_freeze", "t0", "t_close", "activation_gap_seconds",
        "tier1_in_holdout", "tier1_outside_holdout", "tier2_admitted",
        "tier2_rejections", "admitted_resolved_after_t_close", "origin_anomalies",
    ):
        assert key in block, key
    tf = block["per_timeframe"]["4H"]
    for key in (
        "admitted_pairs", "k_pre_drop", "missed_attempts",
        "realized_label_distribution", "regime_distribution", "trend_mtf_distribution",
        "realized_vol_summary", "volume_anomaly_summary",
        "first_reference_close_utc", "last_reference_close_utc", "realised_span_seconds",
    ):
        assert key in tf, key
    assert tf["k_pre_drop"] == {"1": 11, "2": 7, "4": 5}


def test_activation_gap_matches_the_recorded_contract_value() -> None:
    block = diagnostics.build(
        _admission(), t0=T0, t_close=T_CLOSE, t_freeze=T_FREEZE, timeframes=["4H"]
    )
    assert block["activation_gap_seconds"] == 16 * 3600 + 24 * 60 + 4


def test_diagnostics_can_never_change_a_verdict() -> None:
    """Run the same decision against wildly different diagnostics and compare verdicts."""

    admission = _admission()
    verdict = decision.evaluate_timeframe("4H", admission, t0=T0, t_close=T_CLOSE)

    plain = diagnostics.build(
        admission, t0=T0, t_close=T_CLOSE, t_freeze=T_FREEZE, timeframes=["4H"]
    )
    loaded = diagnostics.build(
        admission,
        t0=T0,
        t_close=T_CLOSE,
        t_freeze=T_FREEZE,
        timeframes=["4H"],
        feature_rows=[
            {"prediction_id": row["candidate_prediction_id"], "regime": "CHAOS",
             "realized_vol": 99.0, "trend_mtf": "DOWN", "volume_anomaly": -50.0}
            for row in admission.admitted
        ],
        origin_anomalies=10_000,
        missed_attempts={"4H": 10_000},
    )
    assert plain != loaded, "the two diagnostic blocks must genuinely differ"

    again = decision.evaluate_timeframe("4H", admission, t0=T0, t_close=T_CLOSE)
    assert again.state == verdict.state
    assert again.authorized_cells == verdict.authorized_cells
    assert [c.holds for c in again.coarsenings] == [c.holds for c in verdict.coarsenings]


def test_numeric_summary_handles_absent_and_present_values() -> None:
    assert diagnostics.numeric_summary([])["median"] is None
    assert diagnostics.numeric_summary([None, None])["count"] == 0
    summary = diagnostics.numeric_summary([1.0, 2.0, 3.0, 4.0])
    assert summary["median"] == 2.5
    assert summary["iqr"] == 1.5


def test_distribution_reports_absent_features_rather_than_dropping_them() -> None:
    assert diagnostics.distribution(["UP", "UP", None]) == {"UNKNOWN": 1, "UP": 2}


def test_missed_attempts_is_reported_absent_not_zero() -> None:
    """FINDING F7. No attempt ledger exists in the database, so zero would be fabricated.

    "Never convert NOT_RUN into PASS" applies to counts as much as to gates.
    """

    block = diagnostics.build(
        _admission(), t0=T0, t_close=T_CLOSE, t_freeze=T_FREEZE, timeframes=["4H"]
    )
    tf = block["per_timeframe"]["4H"]
    assert tf["missed_attempts"] == diagnostics.UNMEASURED
    assert tf["missed_attempts"] != 0
    assert "not derivable" in tf["missed_attempts_basis"]


def test_a_supplied_attempt_ledger_is_reported_as_measured() -> None:
    block = diagnostics.build(
        _admission(),
        t0=T0,
        t_close=T_CLOSE,
        t_freeze=T_FREEZE,
        timeframes=["4H"],
        missed_attempts={"4H": 41},
    )
    tf = block["per_timeframe"]["4H"]
    assert tf["missed_attempts"] == 41
    assert "attempt ledger" in tf["missed_attempts_basis"]


def test_dropped_windows_are_reported_per_coarsening() -> None:
    """FINDING F7. §5A.10 requires the dropped-window count, which was absent."""

    block = diagnostics.build(
        _admission(), t0=T0, t_close=T_CLOSE, t_freeze=T_FREEZE, timeframes=["4H"]
    )
    tf = block["per_timeframe"]["4H"]
    assert tf["usable_windows"] == {"1": 11, "2": 7, "4": 5}
    assert tf["dropped_windows"] == {"1": 0, "2": 0, "4": 0}


def test_diagnostics_are_reported_PER_CELL_not_only_per_timeframe() -> None:
    """FINDING F7. §5A.10 says "per timeframe AND per cell"."""

    block = diagnostics.build(
        _admission(), t0=T0, t_close=T_CLOSE, t_freeze=T_FREEZE, timeframes=["4H"]
    )
    cell = block["per_timeframe"]["4H"]["per_symbol"]["BTC/USDT"]
    for key in (
        "admitted_pairs", "usable_windows", "dropped_windows",
        "realized_label_distribution",
        "first_reference_close_utc", "last_reference_close_utc",
    ):
        assert key in cell, key
    assert cell["usable_windows"] == {"1": 11, "2": 7, "4": 5}
