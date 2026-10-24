from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NG_DIR = ROOT / "src/crypto_probability_engine/quant_ng"
NG_PREFIX = "crypto_probability_engine.quant_ng"
FORBIDDEN = ("crypto_probability_engine.api", "crypto_probability_engine.persistence",
             "crypto_probability_engine.gates", "crypto_probability_engine.detail",
             "crypto_probability_engine.calibration")


def _imported_module_names(source: str, module_path: str) -> list[str]:
    """Return absolute import names, including names selected from imported modules."""
    tree = ast.parse(source)
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # module_path keeps "__init__" for a package's own file, so in every case the
                # importing package is everything but the last part.
                package = module_path.split(".")[:-1]
                keep = max(0, len(package) - node.level + 1)
                base = ".".join(package[:keep] + ([node.module] if node.module else []))
            else:
                base = node.module or ""
            if base:
                names.append(base)
            names.extend(f"{base}.{alias.name}" if base else alias.name for alias in node.names)
    return names


def _matches(name: str, prefix: str) -> bool:
    return name == prefix or name.startswith(prefix + ".")


def _module_path(path: Path, root: Path) -> str:
    # "a/b/__init__.py" -> "a.b.__init__": its package is a.b, as for "a/b/c.py" -> "a.b.c".
    return ".".join(path.relative_to(root).with_suffix("").parts)


def test_import_name_helper_resolves_absolute_and_relative_forms() -> None:
    cases = (
        ("import crypto_probability_engine.quant_ng.evidence", "consumer.mod",
         "crypto_probability_engine.quant_ng.evidence"),
        ("from crypto_probability_engine import quant_ng", "consumer.mod",
         "crypto_probability_engine.quant_ng"),
        ("from . import quant_ng", "crypto_probability_engine.consumer.mod",
         "crypto_probability_engine.consumer.quant_ng"),
        ("from .quant_ng import x", "crypto_probability_engine.consumer.mod",
         "crypto_probability_engine.consumer.quant_ng.x"),
        ("from ..quant_ng import x", "crypto_probability_engine.consumer.mod",
         "crypto_probability_engine.quant_ng.x"),
        ("from crypto_probability_engine import gates", "consumer.mod",
         "crypto_probability_engine.gates"),
        ("from ..gates import x", "crypto_probability_engine.consumer.mod",
         "crypto_probability_engine.gates.x"),
        ("import pathlib", "consumer.mod", "pathlib"),
        ("from .quant_ng import x", "crypto_probability_engine.__init__",
         "crypto_probability_engine.quant_ng.x"),
        ("from . import quant_ng", "crypto_probability_engine.__init__",
         "crypto_probability_engine.quant_ng"),
        ("from ..gates import x", "crypto_probability_engine.quant_ng.__init__",
         "crypto_probability_engine.gates.x"),
    )
    for source, module_path, expected in cases:
        names = _imported_module_names(source, module_path)
        assert expected in names
        if expected.startswith(NG_PREFIX):
            assert any(_matches(name, NG_PREFIX) for name in names)
        elif expected.startswith("crypto_probability_engine.gates"):
            assert any(_matches(name, FORBIDDEN[2]) for name in names)
        else:
            assert not any(_matches(name, NG_PREFIX) for name in names)
            assert not any(_matches(name, prefix) for prefix in FORBIDDEN for name in names)


def test_module_path_keeps_init_so_the_package_resolves() -> None:
    src = ROOT / "src"
    assert _module_path(NG_DIR / "__init__.py", src) == f"{NG_PREFIX}.__init__"
    assert _module_path(NG_DIR / "evidence.py", src) == f"{NG_PREFIX}.evidence"


def test_quant_ng_has_no_importers_outside_its_package_or_tests() -> None:
    violations = []
    for folder in (ROOT / "src", ROOT / "scripts"):
        if not folder.exists():
            continue
        for path in folder.rglob("*.py"):
            if NG_DIR == path or NG_DIR in path.parents:
                continue
            names = _imported_module_names(path.read_text(encoding="utf-8"),
                                           _module_path(path, folder))
            if any(_matches(name, NG_PREFIX) for name in names):
                violations.append(str(path.relative_to(ROOT)))
    assert violations == []


def test_quant_ng_avoids_forbidden_internal_dependencies() -> None:
    violations = []
    for path in NG_DIR.rglob("*.py"):
        names = _imported_module_names(path.read_text(encoding="utf-8"),
                                       _module_path(path, ROOT / "src"))
        for name in names:
            if any(_matches(name, prefix) for prefix in FORBIDDEN):
                violations.append((str(path.relative_to(ROOT)), name))
    assert violations == []


def test_src_does_not_import_quant_ng_fit() -> None:
    """No product module imports the dormant fit gate.

    This reads import statements only, so a reference through subprocess, runpy or
    spec_from_file_location would pass it; the inventory row and the T1 tier are what keep the
    script out of the serving path.
    """
    violations = []
    src = ROOT / "src"
    for path in src.rglob("*.py"):
        names = _imported_module_names(
            path.read_text(encoding="utf-8"), _module_path(path, src)
        )
        imports_fit = any(
            _matches(name, "scripts.quant_ng_fit") or _matches(name, "quant_ng_fit")
            for name in names
        )
        if imports_fit:
            violations.append(str(path.relative_to(ROOT)))
    assert violations == []
