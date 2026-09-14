"""The evaluator pin, derived mechanically from the full import closure (owner ruling D1)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from crypto_probability_engine.oos.evaluation import evaluator_pin as ep

ROOT = ep.project_root()


@pytest.fixture
def mirrored(tmp_path: Path) -> Path:
    """A copy of exactly the pinned files, with a pin computed over the copy."""

    for relative in ep.pinned_files(ROOT):
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    (tmp_path / "pin.json").write_text(json.dumps(ep.current_pin_artifacts(tmp_path)))
    return tmp_path


def _assert_pin(root: Path) -> None:
    ep.assert_evaluator_pin(pin_path=root / "pin.json", root=root)


def test_committed_pin_matches_the_evaluator_on_disk() -> None:
    assert ep.assert_evaluator_pin()["closure_digest"]


def test_the_pinned_set_is_exactly_the_import_closure_plus_declared_surfaces() -> None:
    assert set(ep.pinned_files()) == set(ep.import_closure()) | set(ep.DECLARED_SURFACES)


def test_the_closure_covers_every_surface_earlier_rounds_missed() -> None:
    """F6, G4 and V807-F7 each found an unpinned control surface. None may be missing now."""

    files = set(ep.pinned_files())
    for surface in (
        "scripts/evaluate_section_5a.py",  # G4
        "src/crypto_probability_engine/persistence/repository.py",  # F6
        "src/crypto_probability_engine/config/settings.py",  # V807-F7
        "src/crypto_probability_engine/utils/canonical_json.py",  # G1/G9
        "src/crypto_probability_engine/oos/__init__.py",  # executed on import
        "src/crypto_probability_engine/oos/evaluation/scope.py",  # V807-F1
        "migrations/0009_section_5a_evaluation_seal.sql",  # V807-F7
        ".github/workflows/section-5a-evaluation.yml",  # V807-F7
    ):
        assert surface in files, surface


def test_everything_python_actually_loads_is_inside_the_static_closure() -> None:
    """The static derivation must be a SUPERSET of what really executes.

    A subprocess imports the entrypoint and exercises readiness, decision and identity code, then
    reports every first-party module file Python loaded. Any file outside the static closure
    would mean the derivation is missing a live import.
    """

    program = """
import json, sys
from pathlib import Path
import scripts.evaluate_section_5a  # noqa: F401
# The CLI imports these lazily, after isolation (V809-F1); import them as its live modes do.
from crypto_probability_engine import runtime_isolation  # noqa: F401
from crypto_probability_engine.config.settings import Settings  # noqa: F401
from crypto_probability_engine.oos.evaluation import evaluator_pin, provenance  # noqa: F401
from crypto_probability_engine.oos.evaluation import runner
from crypto_probability_engine.persistence.repository import build_operator_repository  # noqa: F401
from tests.oos.evaluation.conftest import daily_4h_evidence
rows = daily_4h_evidence()
runner.decision_population_id(rows)
runner.evidence_snapshot_id(rows)
root = Path.cwd().resolve()
loaded = set()
for module in list(sys.modules.values()):
    path = getattr(module, "__file__", None)
    if not path:
        continue
    p = Path(path).resolve()
    if "crypto_probability_engine" in p.parts and p.is_relative_to(root / "src"):
        loaded.add(p.relative_to(root).as_posix())
print(json.dumps(sorted(loaded)))
"""
    environment = dict(os.environ, PYTHONPATH=os.pathsep.join(("src", ".")))
    completed = subprocess.run(
        [sys.executable, "-c", program],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=environment,
        check=True,
    )
    loaded = set(json.loads(completed.stdout.strip().splitlines()[-1]))
    closure = set(ep.import_closure())
    assert loaded, "the probe loaded nothing, so it proves nothing"
    assert loaded <= closure, f"live imports outside the pin: {sorted(loaded - closure)}"


@pytest.mark.parametrize(
    "target",
    [
        "src/crypto_probability_engine/oos/evaluation/decision.py",
        "src/crypto_probability_engine/oos/evaluation/scope.py",
        "src/crypto_probability_engine/calibration/metrics.py",
        "src/crypto_probability_engine/config/settings.py",
        "src/crypto_probability_engine/oos/__init__.py",
        "scripts/evaluate_section_5a.py",
    ],
)
def test_mutating_any_closure_file_breaks_the_pin(mirrored: Path, target: str) -> None:
    _assert_pin(mirrored)
    path = mirrored / target
    path.write_text(path.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")
    with pytest.raises(ep.EvaluatorPinMismatch, match="reviewed pin"):
        _assert_pin(mirrored)


@pytest.mark.parametrize("surface", ep.DECLARED_SURFACES)
def test_mutating_any_declared_surface_breaks_the_pin(mirrored: Path, surface: str) -> None:
    """Rules and runtime surfaces are pinned too: a rule change is visible by construction."""

    path = mirrored / surface
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ep.EvaluatorPinMismatch, match="reviewed pin"):
        _assert_pin(mirrored)


def test_a_new_import_pulls_its_module_into_the_pin(mirrored: Path) -> None:
    """Adding a dependency cannot slip past the pin: the importer changes AND the module joins."""

    new_module = mirrored / "src/crypto_probability_engine/oos/evaluation/smuggled.py"
    new_module.write_text("VALUE = 1\n", encoding="utf-8")
    assert "src/crypto_probability_engine/oos/evaluation/smuggled.py" not in ep.pinned_files(
        mirrored
    ), "an unimported file is outside the closure by definition"

    decision = mirrored / "src/crypto_probability_engine/oos/evaluation/decision.py"
    decision.write_text(
        "from crypto_probability_engine.oos.evaluation import smuggled  # noqa\n"
        + decision.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    assert "src/crypto_probability_engine/oos/evaluation/smuggled.py" in ep.pinned_files(mirrored)
    with pytest.raises(ep.EvaluatorPinMismatch, match="reviewed pin"):
        _assert_pin(mirrored)


def test_an_unresolvable_first_party_import_fails_closed(mirrored: Path) -> None:
    (mirrored / "src/crypto_probability_engine/oos/evaluation/scope.py").unlink()
    with pytest.raises(ep.EvaluatorPinMismatch, match="cannot be resolved"):
        ep.pinned_files(mirrored)


def test_a_missing_declared_surface_fails_closed(mirrored: Path) -> None:
    (mirrored / "migrations/0009_section_5a_evaluation_seal.sql").unlink()
    with pytest.raises(ep.EvaluatorPinMismatch, match="declared pinned surface is missing"):
        ep.pinned_files(mirrored)


def test_a_relative_import_is_refused_rather_than_silently_skipped(mirrored: Path) -> None:
    decision = mirrored / "src/crypto_probability_engine/oos/evaluation/decision.py"
    decision.write_text(
        "from . import scope  # noqa\n" + decision.read_text(encoding="utf-8"), encoding="utf-8"
    )
    with pytest.raises(ep.EvaluatorPinMismatch, match="relative imports"):
        ep.pinned_files(mirrored)


def test_a_missing_pin_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ep.EvaluatorPinMismatch, match="missing or invalid"):
        ep.assert_evaluator_pin(pin_path=tmp_path / "absent.json")


def test_the_closure_does_not_reach_the_hugging_face_application_surface() -> None:
    """Recorded because it bounds churn: product UI/API changes cannot invalidate the pin."""

    files = set(ep.pinned_files())
    assert "src/crypto_probability_engine/api/analysis_service.py" not in files
    assert "src/crypto_probability_engine/api/app.py" not in files
    assert not any(name.startswith("frontend/") for name in files)
