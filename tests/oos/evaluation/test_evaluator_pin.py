"""The evaluator pin: any change to what can move the answer must fail closed."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from crypto_probability_engine.oos.evaluation import evaluator_pin


@pytest.fixture
def mirrored(tmp_path: Path) -> Path:
    root = evaluator_pin.project_root()
    for relative in evaluator_pin.pinned_files(root):
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, destination)
    return tmp_path


def test_committed_pin_matches_the_evaluator_on_disk() -> None:
    assert evaluator_pin.assert_evaluator_pin()["closure_digest"]


def test_pinned_set_is_the_evaluator_plus_the_reused_definitions() -> None:
    files = evaluator_pin.pinned_files()
    assert "src/crypto_probability_engine/calibration/metrics.py" in files
    assert "src/crypto_probability_engine/calibration/schemas.py" in files
    assert "src/crypto_probability_engine/utils/invariants.py" in files
    assert all(
        name.startswith("src/crypto_probability_engine/oos/evaluation/")
        or name in evaluator_pin._REUSED_DEFINITIONS
        for name in files
    )
    assert files == tuple(sorted(files)), "order must be deterministic"


@pytest.mark.parametrize(
    "target",
    [
        "src/crypto_probability_engine/oos/evaluation/decision.py",
        "src/crypto_probability_engine/oos/evaluation/stats_kernel.py",
        "src/crypto_probability_engine/calibration/metrics.py",
        "src/crypto_probability_engine/utils/invariants.py",
    ],
)
def test_mutating_any_pinned_file_breaks_the_pin(mirrored: Path, target: str) -> None:
    pin = mirrored / "pin.json"
    pin.write_bytes(
        json.dumps(
            evaluator_pin.current_pin_artifacts(mirrored),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )
    evaluator_pin.assert_evaluator_pin(pin_path=pin, root=mirrored)

    path = mirrored / target
    path.write_text(path.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")
    with pytest.raises(evaluator_pin.EvaluatorPinMismatch, match="reviewed pin"):
        evaluator_pin.assert_evaluator_pin(pin_path=pin, root=mirrored)


def test_a_missing_pin_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(evaluator_pin.EvaluatorPinMismatch, match="missing or invalid"):
        evaluator_pin.assert_evaluator_pin(pin_path=tmp_path / "absent.json")


def test_deleting_an_evaluator_module_breaks_the_pin(mirrored: Path) -> None:
    """The module set is globbed, so a deletion shrinks the pinned list rather than
    tripping the existence check — the exact-dict comparison is what catches it."""

    pin = mirrored / "pin.json"
    pin.write_bytes(
        json.dumps(
            evaluator_pin.current_pin_artifacts(mirrored),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )
    (mirrored / "src/crypto_probability_engine/oos/evaluation/decision.py").unlink()
    with pytest.raises(evaluator_pin.EvaluatorPinMismatch, match="reviewed pin"):
        evaluator_pin.assert_evaluator_pin(pin_path=pin, root=mirrored)


def test_deleting_a_reused_definition_fails_closed_immediately(mirrored: Path) -> None:
    """The three reused definitions are named explicitly, so their absence is an error
    in its own right rather than a silently shorter list."""

    (mirrored / "src/crypto_probability_engine/calibration/metrics.py").unlink()
    with pytest.raises(evaluator_pin.EvaluatorPinMismatch, match="pinned file is missing"):
        evaluator_pin.pinned_files(mirrored)


def test_adding_a_module_to_the_package_breaks_the_pin(mirrored: Path) -> None:
    """A new evaluator module cannot slip in unreviewed."""

    pin = mirrored / "pin.json"
    pin.write_bytes(
        json.dumps(
            evaluator_pin.current_pin_artifacts(mirrored),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )
    smuggled = mirrored / "src/crypto_probability_engine/oos/evaluation/extra.py"
    smuggled.write_text("# unreviewed\n", encoding="utf-8")
    with pytest.raises(evaluator_pin.EvaluatorPinMismatch, match="reviewed pin"):
        evaluator_pin.assert_evaluator_pin(pin_path=pin, root=mirrored)
