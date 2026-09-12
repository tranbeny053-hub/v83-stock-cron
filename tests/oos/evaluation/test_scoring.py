from __future__ import annotations

from pathlib import Path

import pytest

from crypto_probability_engine.calibration.metrics import compute_calibration_metrics
from crypto_probability_engine.oos.evaluation import scoring
from crypto_probability_engine.oos.evaluation.scoring import ece, per_row_d, window_mean


def _row(
    realized_label: str,
    p_up_frac: float,
    p_down_frac: float,
    p_timeout_frac: float,
) -> dict[str, object]:
    return {
        "realized_label": realized_label,
        "p_up_frac": p_up_frac,
        "p_down_frac": p_down_frac,
        "p_timeout_frac": p_timeout_frac,
    }


def test_per_row_d_is_negative_when_candidate_is_strictly_better() -> None:
    candidate = {"UP": 0.8, "DOWN": 0.1, "TIMEOUT": 0.1}
    baseline = {"UP": 1 / 3, "DOWN": 1 / 3, "TIMEOUT": 1 / 3}

    assert per_row_d(candidate, baseline, "UP") < 0.0


def test_window_mean_is_arithmetic_mean_and_rejects_empty_windows() -> None:
    assert window_mean([-0.4, -0.2, 0.3]) == pytest.approx(-0.1)
    with pytest.raises(ValueError, match="usable window"):
        window_mean([])


def test_ece_matches_hand_computation_and_enumerates_empty_bins() -> None:
    rows = [
        _row("UP", 0.6, 0.2, 0.2),
        _row("DOWN", 0.8, 0.1, 0.1),
    ]
    # The occupied gaps are |0.6 - 1| = 0.4 and |0.8 - 0| = 0.8.
    # ECE = (1/2)*0.4 + (1/2)*0.8 = 0.6; every other fixed bin weighs zero.
    assert ece(rows) == pytest.approx(0.6)

    buckets = compute_calibration_metrics(rows)["reliability_buckets"]
    assert len(buckets) == 7
    empty_buckets = [bucket for bucket in buckets if bucket["bucket_count"] == 0]
    assert len(empty_buckets) == 5
    assert all(bucket["calibration_gap"] is None for bucket in empty_buckets)

    occupied_only = [bucket for bucket in buckets if bucket["bucket_count"] > 0]
    drop_empties_result = sum(
        (bucket["bucket_count"] / len(rows)) * abs(bucket["calibration_gap"])
        for bucket in occupied_only
    )
    assert drop_empties_result == pytest.approx(ece(rows))


def test_perfectly_calibrated_rows_have_exactly_zero_ece() -> None:
    rows = [
        _row("UP", 0.5, 0.3, 0.2),
        _row("DOWN", 0.5, 0.3, 0.2),
    ]
    assert ece(rows) == 0.0


def test_empty_ece_is_zero() -> None:
    assert ece([]) == 0.0


def test_ece_raises_for_impossible_nonempty_bucket_without_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        scoring,
        "compute_calibration_metrics",
        lambda rows: {
            "reliability_buckets": [{"bucket_count": 1, "calibration_gap": None}]
        },
    )
    with pytest.raises(ValueError, match="non-empty reliability bucket"):
        scoring.ece([_row("UP", 0.6, 0.2, 0.2)])


def test_evaluation_package_does_not_reach_filtered_shadow_metrics() -> None:
    package_dir = Path(scoring.__file__).parent
    source = "\n".join(path.read_text(encoding="utf-8") for path in package_dir.glob("*.py"))
    assert "shadow_validation.metrics" not in source
    assert "MIN_CELL_COUNT" not in source

