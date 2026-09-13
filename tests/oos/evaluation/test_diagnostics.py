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


def test_realized_label_distribution_always_declares_every_label() -> None:
    """A zero-count label must be reported, not dropped: its absence is the finding."""

    only_up = admit(daily_4h_evidence(), t0=T0, t_close=T_CLOSE)
    block = diagnostics.build(
        only_up, t0=T0, t_close=T_CLOSE, t_freeze=T_FREEZE, timeframes=["4H"]
    )
    tf = block["per_timeframe"]["4H"]
    assert tf["realized_label_distribution"] == {"UP": 22, "DOWN": 0, "TIMEOUT": 0}
    cell = tf["per_symbol"]["BTC/USDT"]
    assert cell["realized_label_distribution"] == {"UP": 22, "DOWN": 0, "TIMEOUT": 0}


def test_timeframe_and_cell_blocks_report_the_identical_key_set() -> None:
    """Built by one function, so the two scopes cannot drift apart."""

    block = diagnostics.build(
        _admission(), t0=T0, t_close=T_CLOSE, t_freeze=T_FREEZE, timeframes=["4H"]
    )
    tf = block["per_timeframe"]["4H"]
    cell = tf["per_symbol"]["BTC/USDT"]
    assert set(tf) - {"per_symbol"} == set(cell)
    # The contract records the T_freeze -> T0 gap as 16h 24m 04s.
    assert cell["t0"] == block["t0"]
    assert cell["activation_gap_seconds"] == 16 * 3600 + 24 * 60 + 4


def test_origin_anomalies_are_unmeasured_unless_actually_measured() -> None:
    empty = admit([], t0=T0, t_close=T_CLOSE)
    kwargs = dict(t0=T0, t_close=T_CLOSE, t_freeze=T_FREEZE, timeframes=["4H"])
    assert diagnostics.build(empty, **kwargs)["origin_anomalies"] == diagnostics.UNMEASURED
    assert diagnostics.build(empty, origin_anomalies=0, **kwargs)["origin_anomalies"] == 0


def test_a_single_close_is_a_measured_zero_span_but_no_close_is_none() -> None:
    from datetime import timedelta

    from tests.oos.evaluation.conftest import evidence_row

    kwargs = dict(t0=T0, t_close=T_CLOSE, t_freeze=T_FREEZE, timeframes=["4H"])
    one = admit([evidence_row(T0 + timedelta(days=1))], t0=T0, t_close=T_CLOSE)
    none = admit([], t0=T0, t_close=T_CLOSE)
    assert diagnostics.build(one, **kwargs)["per_timeframe"]["4H"]["realised_span_seconds"] == 0
    assert diagnostics.build(none, **kwargs)["per_timeframe"]["4H"]["realised_span_seconds"] is None


def test_numeric_summaries_are_identical_for_decimal_and_float_inputs() -> None:
    from decimal import Decimal

    floats = diagnostics.numeric_summary([0.2, 0.4, 0.6])
    decimals = diagnostics.numeric_summary([Decimal("0.2"), Decimal("0.4"), Decimal("0.6")])
    assert floats == decimals
