from __future__ import annotations

from pathlib import Path

ROOT = Path("src/crypto_probability_engine")
NEW_SOURCE = [
    ROOT / "adapters" / "derivatives_endpoints.py",
    *sorted((ROOT / "adapters" / "derivatives").glob("*.py")),
    *sorted((ROOT / "derivatives_intel").glob("*.py")),
]


def test_derivatives_foundation_has_no_runtime_or_storage_imports() -> None:
    text = "\n".join(path.read_text() for path in NEW_SOURCE)
    import_text = "\n".join(
        line for line in text.splitlines() if line.startswith(("from ", "import "))
    )
    forbidden_imports = [
        ".api",
        ".quant",
        ".score_stack",
        ".gates",
        ".detail",
        ".persistence",
    ]
    assert all(value not in import_text for value in forbidden_imports)
    mutation_fragments = ["save_", "INSERT ", "UPDATE ", "DELETE ", "MERGE "]
    assert all(value not in text for value in mutation_fragments)


def test_provenance_has_no_wall_clock_or_network_dependency() -> None:
    text = (ROOT / "derivatives_intel" / "provenance.py").read_text()
    fragments = ["datetime." + "now", "utc" + "now", "time." + "time", "random"]
    assert all(value not in text for value in fragments)


def test_no_runtime_analysis_or_response_wiring_changed() -> None:
    assert not any("derivatives_intel" in path.read_text() for path in (ROOT / "api").glob("*.py"))
