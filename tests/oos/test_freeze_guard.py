from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import MappingProxyType

import pytest

from crypto_probability_engine.config import defaults
from crypto_probability_engine.oos import freeze_guard
from crypto_probability_engine.quant import pipeline, probability_distributional

ROOT = Path(__file__).resolve().parents[2]


def test_reviewed_candidate_freeze_passes() -> None:
    assert freeze_guard.assert_candidate_freeze()["schema_version"].endswith(".v3")


def test_resolved_parameter_mutation_blocks(monkeypatch) -> None:
    original = probability_distributional.FROZEN_B3_PARAMETERS
    changed = {key: dict(value) for key, value in original.items()}
    changed["15m"]["table"] = (
        (changed["15m"]["table"][0][0] + 0.01, 0.0),
        *changed["15m"]["table"][1:],
    )
    monkeypatch.setattr(
        probability_distributional,
        "FROZEN_B3_PARAMETERS",
        MappingProxyType(changed),
    )

    with pytest.raises(freeze_guard.FreezeGuardMismatch):
        freeze_guard.assert_candidate_freeze()


def test_fee_mutation_changes_behavioural_fingerprint() -> None:
    original = defaults.DEFAULT_PHASE1A.taker_fee_frac
    before = freeze_guard.behavioural_fingerprint()
    try:
        object.__setattr__(defaults.DEFAULT_PHASE1A, "taker_fee_frac", original + 0.0001)
        assert freeze_guard.behavioural_fingerprint() != before
    finally:
        object.__setattr__(defaults.DEFAULT_PHASE1A, "taker_fee_frac", original)


def test_distributional_band_selector_mutation_changes_fingerprint(monkeypatch) -> None:
    original = pipeline.compute_distributional_probabilities

    def changed(candles, *, timeframe, band_frac):
        return original(candles, timeframe=timeframe, band_frac=band_frac * 1.01)

    before = freeze_guard.behavioural_fingerprint()
    monkeypatch.setattr(pipeline, "compute_distributional_probabilities", changed)
    assert freeze_guard.behavioural_fingerprint() != before


def test_epistemic_null_path_mutation_changes_fingerprint(monkeypatch) -> None:
    original = pipeline.assess_epistemic_sufficiency

    def changed(snapshot):
        state = original(snapshot)
        return {**state, "action": "ALLOW"} if state.get("action") != "ALLOW" else state

    monkeypatch.setattr(pipeline, "assess_epistemic_sufficiency", changed)
    with pytest.raises(freeze_guard.FreezeGuardMismatch):
        freeze_guard.behavioural_fingerprint()


@pytest.mark.parametrize(
    "edit",
    (
        lambda text: text.replace(
            "from crypto_probability_engine.utils.invariants import "
            "validate_probability_triplet\n",
            "",
        ),
        lambda text: text.replace(
            "from crypto_probability_engine.adapters.types import MarketCandle\n",
            "from crypto_probability_engine.adapters.types import MarketCandle\n"
            "import crypto_probability_engine.news.contract\n",
        ),
    ),
)
def test_closure_addition_or_removal_blocks(tmp_path: Path, edit) -> None:
    shutil.copytree(ROOT / "src", tmp_path / "src")
    (tmp_path / "ops").mkdir()
    shutil.copy2(
        ROOT / "ops/oos_candidate_freeze.json",
        tmp_path / "ops/oos_candidate_freeze.json",
    )
    candidate = (
        tmp_path
        / "src/crypto_probability_engine/quant/probability_distributional.py"
    )
    original = candidate.read_text(encoding="utf-8")
    changed = edit(original)
    assert changed != original
    candidate.write_text(changed, encoding="utf-8")

    with pytest.raises(freeze_guard.FreezeGuardMismatch):
        freeze_guard.assert_candidate_freeze(root=tmp_path)

    assert json.loads(
        (tmp_path / "ops/oos_candidate_freeze.json").read_text(encoding="utf-8")
    )["closure_files"]
