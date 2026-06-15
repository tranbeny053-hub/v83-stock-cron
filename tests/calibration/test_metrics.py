from __future__ import annotations

import math

import pytest

from crypto_probability_engine.calibration.metrics import (
    compute_calibration_metrics,
    top_prediction_label,
)


def test_brier_score_exact_fixture() -> None:
    report = compute_calibration_metrics(
        [_row("UP", p_up_frac=0.7, p_down_frac=0.2, p_timeout_frac=0.1)]
    )

    assert report["metrics"]["brier_score"] == pytest.approx(0.14)
    assert report["metrics"]["top_label_hit_rate"] == 1.0


def test_log_loss_clipping_is_finite_with_eps() -> None:
    report = compute_calibration_metrics(
        [_row("UP", p_up_frac=0.0, p_down_frac=0.6, p_timeout_frac=0.4)]
    )

    assert math.isfinite(report["metrics"]["log_loss"])
    assert report["metrics"]["log_loss"] == pytest.approx(-math.log(1e-12))


def test_top_label_tie_break_is_up_down_timeout() -> None:
    assert top_prediction_label({"UP": 0.5, "DOWN": 0.5, "TIMEOUT": 0.0}) == "UP"
    assert top_prediction_label({"UP": 0.2, "DOWN": 0.4, "TIMEOUT": 0.4}) == "DOWN"


def test_reliability_bucket_boundaries_and_low_sample_status() -> None:
    report = compute_calibration_metrics(
        [
            _row("UP", p_up_frac=0.39, p_down_frac=0.31, p_timeout_frac=0.30),
            _row("UP", p_up_frac=0.40, p_down_frac=0.30, p_timeout_frac=0.30),
            _row("UP", p_up_frac=0.90, p_down_frac=0.05, p_timeout_frac=0.05),
            _row("UP", p_up_frac=1.00, p_down_frac=0.00, p_timeout_frac=0.00),
        ]
    )
    buckets = {bucket["bucket"]: bucket for bucket in report["reliability_buckets"]}

    assert buckets["0.00-0.40"]["bucket_count"] == 1
    assert buckets["0.40-0.50"]["bucket_count"] == 1
    assert buckets["0.90-1.00"]["bucket_count"] == 2
    assert buckets["0.90-1.00"]["bucket_sample_status"] == "LOW_BUCKET_SAMPLE"


def test_reliability_bucket_calibration_gap_is_signed() -> None:
    overconfident = compute_calibration_metrics(
        [
            _row("DOWN", p_up_frac=0.80, p_down_frac=0.10, p_timeout_frac=0.10),
            _row("DOWN", p_up_frac=0.80, p_down_frac=0.10, p_timeout_frac=0.10),
        ]
    )
    underconfident = compute_calibration_metrics(
        [
            _row("UP", p_up_frac=0.60, p_down_frac=0.20, p_timeout_frac=0.20),
            _row("UP", p_up_frac=0.60, p_down_frac=0.20, p_timeout_frac=0.20),
        ]
    )
    over_bucket = {
        bucket["bucket"]: bucket for bucket in overconfident["reliability_buckets"]
    }["0.80-0.90"]
    under_bucket = {
        bucket["bucket"]: bucket for bucket in underconfident["reliability_buckets"]
    }["0.60-0.70"]

    assert over_bucket["calibration_gap"] == pytest.approx(0.80)
    assert under_bucket["calibration_gap"] == pytest.approx(-0.40)


def test_outcome_distribution_and_directional_subset_excludes_timeout() -> None:
    report = compute_calibration_metrics(
        [
            _row("UP", p_up_frac=0.7, p_down_frac=0.2, p_timeout_frac=0.1),
            _row("DOWN", p_up_frac=0.2, p_down_frac=0.7, p_timeout_frac=0.1),
            _row("TIMEOUT", p_up_frac=0.2, p_down_frac=0.2, p_timeout_frac=0.6),
        ]
    )

    assert report["outcome_distribution"] == {"UP": 1, "DOWN": 1, "TIMEOUT": 1}
    assert report["metrics"]["directional_subset_count"] == 2
    assert report["metrics"]["directional_hit_rate"] == 1.0


def test_probability_normalization_and_invalid_rows() -> None:
    report = compute_calibration_metrics(
        [
            _row("UP", p_up_frac=0.2, p_down_frac=0.2, p_timeout_frac=0.2),
            _row("DOWN", p_up_frac=1.2, p_down_frac=0.0, p_timeout_frac=0.0),
            _row("BAD", p_up_frac=0.3, p_down_frac=0.3, p_timeout_frac=0.4),
            _row("UP", p_up_frac=0.0, p_down_frac=0.0, p_timeout_frac=0.0),
        ]
    )

    assert report["sample_count"] == 4
    assert report["valid_count"] == 1
    assert report["invalid_row_count"] == 3
    assert report["metrics"]["brier_score"] == pytest.approx(
        (1 / 3 - 1) ** 2 + (1 / 3) ** 2 + (1 / 3) ** 2
    )


def test_terminal_return_diagnostics_are_not_trade_ev() -> None:
    report = compute_calibration_metrics(
        [
            _row("UP", terminal_return_frac=0.02),
            _row("DOWN", terminal_return_frac=-0.01),
            _row("TIMEOUT", terminal_return_frac=0.0),
        ]
    )

    diagnostics = report["terminal_return_diagnostics"]
    assert diagnostics["count"] == 3
    assert diagnostics["mean_terminal_return"] == pytest.approx(0.01 / 3)
    assert diagnostics["note"] == "Terminal return diagnostics only; NOT trade EV."


def _row(
    label: str,
    *,
    p_up_frac: float = 0.6,
    p_down_frac: float = 0.2,
    p_timeout_frac: float = 0.2,
    terminal_return_frac: float = 0.01,
) -> dict:
    return {
        "p_up_frac": p_up_frac,
        "p_down_frac": p_down_frac,
        "p_timeout_frac": p_timeout_frac,
        "realized_label": label,
        "terminal_return_frac": terminal_return_frac,
    }
