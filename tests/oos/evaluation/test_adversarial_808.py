"""Fresh outside-in checks added by task-808. No live repository is contacted."""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from crypto_probability_engine.oos.evaluation import (
    admission,
    decision,
    diagnostics,
    evaluator_pin,
    runner,
)
from tests.oos.evaluation.conftest import T0, T_CLOSE, daily_4h_evidence, evidence_row
from tests.oos.evaluation.test_runner import FakeRepository


def test_consumption_refuses_a_naive_clock_before_touching_the_repository(tmp_path: Path) -> None:
    repository = FakeRepository()
    with pytest.raises(runner.ConsumptionRefused, match="timezone-aware"):
        runner.run_consumption(
            repository,
            confirmation=runner.CONFIRMATION_TOKEN,
            artifact_dir=tmp_path,
            now_utc=datetime(2026, 9, 13),
        )
    assert repository.calls == [] and repository.events == []


def test_existing_secondary_snapshot_refuses_before_the_durable_claim(tmp_path: Path) -> None:
    (tmp_path / runner.SNAPSHOT_FILENAME).write_text("already spent", encoding="utf-8")
    repository = FakeRepository()
    with pytest.raises(runner.OneLookAlreadyConsumed, match="snapshot already exists"):
        runner.run_consumption(
            repository,
            confirmation=runner.CONFIRMATION_TOKEN,
            artifact_dir=tmp_path,
            now_utc=T_CLOSE + timedelta(hours=1),
        )
    assert repository.calls == [] and repository.events == []


def test_consumption_api_exposes_no_pin_bypass_parameter() -> None:
    assert "verify_pin" not in inspect.signature(runner.run_consumption).parameters
    assert "verify_pin" not in inspect.signature(runner.recompute_from_seal).parameters


def test_pin_derivation_follows_function_imports_and_every_parent_init(tmp_path: Path) -> None:
    entrypoint = tmp_path / "scripts/evaluate_section_5a.py"
    entrypoint.parent.mkdir()
    entrypoint.write_text(
        "def later():\n"
        "    from crypto_probability_engine.alpha.beta import worker\n"
        "    return worker\n",
        encoding="utf-8",
    )
    package = tmp_path / "src/crypto_probability_engine"
    nested = package / "alpha/beta"
    nested.mkdir(parents=True)
    for path in (package / "__init__.py", package / "alpha/__init__.py", nested / "__init__.py"):
        path.write_text("", encoding="utf-8")
    (nested / "worker.py").write_text("VALUE = 1\n", encoding="utf-8")

    closure = set(evaluator_pin.import_closure(tmp_path))
    assert closure == {
        "scripts/evaluate_section_5a.py",
        "src/crypto_probability_engine/__init__.py",
        "src/crypto_probability_engine/alpha/__init__.py",
        "src/crypto_probability_engine/alpha/beta/__init__.py",
        "src/crypto_probability_engine/alpha/beta/worker.py",
    }


def test_decision_population_ignores_feature_rows_and_anomaly_counts() -> None:
    rows = daily_4h_evidence()
    baseline = runner.run_readiness(FakeRepository(rows), verify_pin=False)
    noisy = runner.run_readiness(
        FakeRepository(
            rows,
            origin_anomalies=17,
            features=(
                {
                    "prediction_id": rows[0]["candidate_prediction_id"],
                    "regime": "invented-noise",
                    "realized_vol": 999,
                    "trend_mtf": "invented-noise",
                    "volume_anomaly": 999,
                },
            ),
        ),
        now_utc=T_CLOSE + timedelta(days=1),
        verify_pin=False,
    )
    assert noisy["decision_population_id"] == baseline["decision_population_id"]
    assert noisy["evidence_snapshot_id"] != baseline["evidence_snapshot_id"]


def test_per_scope_counts_do_not_repeat_global_counts_across_timeframes() -> None:
    rows = [
        evidence_row(T0 + timedelta(hours=1), timeframe="4H"),
        evidence_row(T0 + timedelta(hours=2), timeframe="1H", symbol="ETH/USDT"),
    ]
    admitted = admission.admit(rows, t0=T0, t_close=T_CLOSE)
    block = diagnostics.build(
        admitted,
        t0=T0,
        t_close=T_CLOSE,
        t_freeze=runner.T_FREEZE,
        timeframes=runner.TIMEFRAMES,
    )
    assert block["tier1_in_holdout"] == 2
    assert block["per_timeframe"]["4H"]["tier1_in_holdout"] == 1
    assert block["per_timeframe"]["1H"]["tier1_in_holdout"] == 1
    assert block["per_timeframe"]["15m"]["tier1_in_holdout"] == 0
    assert block["per_timeframe"]["4H"]["per_symbol"]["BTC/USDT"]["tier1_in_holdout"] == 1
    assert block["per_timeframe"]["4H"]["per_symbol"]["ETH/USDT"]["tier1_in_holdout"] == 0


def test_b2_and_c_count_exact_ties_against_the_candidate() -> None:
    row = evidence_row(
        T0 + timedelta(hours=1),
        baseline_up=0.6,
        candidate_up=0.6,
    )
    admitted = admission.admit([row], t0=T0, t_close=T_CLOSE)
    result = decision.evaluate_timeframe("4H", admitted, t0=T0, t_close=T_CLOSE)
    assert (result.b2_n_worse, result.b2_n_better, result.b2_holds) == (1, 0, False)
    symbol = result.per_symbol["BTC/USDT"]
    assert (symbol.n_worse, symbol.n_better, symbol.holds) == (1, 0, False)
