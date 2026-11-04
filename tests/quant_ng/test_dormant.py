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


ALLOWED_GATE_IMPORT = (
    "crypto_probability_engine.gates.composite",
    (("apply_composite_gates", None),),
)


def _forbidden_names(source: str, path: Path) -> list[str]:
    """Every forbidden import name in a quant_ng file.

    The name check covers every form the helper resolves (absolute, relative and parent-package
    imports). The single exemption is exactly one statement,
    ``from crypto_probability_engine.gates.composite import apply_composite_gates`` (no alias, no
    other name), in the file ``NG_DIR / "pipeline_ng.py"``.
    """
    module_path = _module_path(path, ROOT / "src")
    tree = ast.parse(source)
    imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    exempt = [
        node
        for node in imports
        if path == NG_DIR / "pipeline_ng.py"
        and isinstance(node, ast.ImportFrom)
        and node.level == 0
        and (node.module, tuple((a.name, a.asname) for a in node.names)) == ALLOWED_GATE_IMPORT
    ]
    violations = []
    if len(exempt) > 1:
        violations.append("crypto_probability_engine.gates.composite (repeated)")
    for node in imports:
        if len(exempt) == 1 and node is exempt[0]:
            continue
        for name in _imported_module_names(ast.unparse(node), module_path):
            if any(_matches(name, prefix) for prefix in FORBIDDEN):
                violations.append(name)
    return violations


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
            found, _used = _ng_import_violations(
                path.read_text(encoding="utf-8"), path, _module_path(path, folder)
            )
            violations.extend((str(path.relative_to(ROOT)), name) for name in found)
    assert violations == []
    _found, used = _ng_import_violations(
        SERVING_IMPORTER.read_text(encoding="utf-8"),
        SERVING_IMPORTER,
        _module_path(SERVING_IMPORTER, ROOT / "src"),
    )
    assert used == set(ALLOWED_NG_IMPORTS)


SERVING_IMPORTER = ROOT / "src/crypto_probability_engine/api/analysis_service.py"
# NG3's dormant wiring (owner R3a, 2026-11-04): the only product statements that may name quant_ng.
ALLOWED_NG_IMPORTS = {
    f"{NG_PREFIX}.pipeline_ng": frozenset({("run_pipeline_ng", None)}),
    f"{NG_PREFIX}.registry": frozenset(
        {("SCHEMA_ID", None), ("SLOT_POLICY", None), ("Refusal", None)}
    ),
}


def _ng_import_violations(source: str, path: Path, module_path: str) -> tuple[list[str], set[str]]:
    """Every quant_ng name a product file imports, and the allowed statements it used.

    Every import statement's names are resolved by the helper (absolute, relative and
    parent-package forms alike). The only exemption is each ALLOWED_NG_IMPORTS statement, exactly
    (level 0, exactly those names, no alias), at most once, in SERVING_IMPORTER. The real-file
    guard and the negative tests below call this one function.
    """
    violations: list[str] = []
    used: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        names = [
            name
            for name in _imported_module_names(ast.unparse(node), module_path)
            if _matches(name, NG_PREFIX)
        ]
        if not names:
            continue
        exempt = (
            path == SERVING_IMPORTER
            and isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module in ALLOWED_NG_IMPORTS
            and node.module not in used
            and frozenset((a.name, a.asname) for a in node.names) == ALLOWED_NG_IMPORTS[node.module]
        )
        if exempt:
            used.add(node.module)
        else:
            violations.extend(names)
    return violations, used


def test_quant_ng_avoids_forbidden_internal_dependencies() -> None:
    violations = []
    for path in NG_DIR.rglob("*.py"):
        names = _forbidden_names(path.read_text(encoding="utf-8"), path)
        violations.extend((str(path.relative_to(ROOT)), name) for name in names)
    assert violations == []


def test_direct_gate_allowance_is_narrow() -> None:
    """Only the exact composite gate from-import in pipeline_ng is exempt; all else is caught."""
    path = NG_DIR / "pipeline_ng.py"
    allowed = "from crypto_probability_engine.gates.composite import apply_composite_gates"
    assert _forbidden_names(allowed, path) == []
    rejected = (
        ("import crypto_probability_engine.gates.composite", path),
        ("import crypto_probability_engine.gates", path),
        ("from crypto_probability_engine import gates", path),
        ("from crypto_probability_engine import gates as g", path),
        ("from crypto_probability_engine.gates import composite", path),
        ("from crypto_probability_engine.gates.composite import other_gate", path),
        (f"{allowed} as gate", path),
        (f"{allowed}, other_gate", path),
        ("from ..gates.composite import apply_composite_gates", path),
        ("from .. import gates", path),
        (f"{allowed}\n{allowed}", path),
        (f"{allowed}\nfrom crypto_probability_engine import gates", path),
        (f"{allowed}\nfrom crypto_probability_engine import api", path),
        (allowed, NG_DIR / "registry.py"),
    )
    for source, target in rejected:
        assert _forbidden_names(source, target), (source, target.name)
    dormant_modules = {
        f"{NG_PREFIX}.registry",
        f"{NG_PREFIX}.pipeline_ng",
    }
    external_importers = []
    for folder in (ROOT / "src", ROOT / "scripts"):
        if not folder.exists():
            continue
        for candidate in folder.rglob("*.py"):
            if NG_DIR == candidate or NG_DIR in candidate.parents:
                continue
            names = _imported_module_names(
                candidate.read_text(encoding="utf-8"), _module_path(candidate, folder)
            )
            if any(_matches(name, module) for name in names for module in dormant_modules):
                external_importers.append(str(candidate.relative_to(ROOT)))
    assert external_importers == ["src/crypto_probability_engine/api/analysis_service.py"]


def test_external_ng_import_allowance_rejects_other_forms() -> None:
    """The same function the real-file guard uses: only the two exact statements are exempt."""
    module_path = _module_path(SERVING_IMPORTER, ROOT / "src")
    pipeline = "from crypto_probability_engine.quant_ng.pipeline_ng import run_pipeline_ng"
    registry = (
        "from crypto_probability_engine.quant_ng.registry import SCHEMA_ID, SLOT_POLICY, Refusal"
    )
    allowed = f"{pipeline}\n{registry}"
    assert _ng_import_violations(allowed, SERVING_IMPORTER, module_path) == (
        [],
        set(ALLOWED_NG_IMPORTS),
    )
    rejected = (
        "import crypto_probability_engine.quant_ng.pipeline_ng",
        "import crypto_probability_engine.quant_ng",
        f"{pipeline} as run",
        "from crypto_probability_engine.quant_ng.registry import serving_state",
        "from crypto_probability_engine.quant_ng.registry import SCHEMA_ID, SLOT_POLICY",
        "from crypto_probability_engine import quant_ng",
        "from crypto_probability_engine.quant_ng import pipeline_ng",
        "from crypto_probability_engine.quant_ng.windows import acquire_window",
        "from ..quant_ng.pipeline_ng import run_pipeline_ng",
        "from .. import quant_ng",
        f"{allowed}\n{pipeline}",
        f"{allowed}\nimport crypto_probability_engine.quant_ng.windows",
    )
    for source in rejected:
        found, _used = _ng_import_violations(source, SERVING_IMPORTER, module_path)
        assert found, source
    other = ROOT / "src/crypto_probability_engine/api/errors.py"
    found, _used = _ng_import_violations(pipeline, other, _module_path(other, ROOT / "src"))
    assert found


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


def test_src_does_not_import_quant_ng_corpus() -> None:
    """The synthetic snapshot tool stays outside every product import path."""
    violations = []
    src = ROOT / "src"
    for path in src.rglob("*.py"):
        names = _imported_module_names(path.read_text(encoding="utf-8"), _module_path(path, src))
        imports_corpus = any(
            _matches(name, "scripts.quant_ng_corpus") or _matches(name, "quant_ng_corpus")
            for name in names
        )
        if imports_corpus:
            violations.append(str(path.relative_to(ROOT)))
    assert violations == []


def test_src_does_not_import_quant_ng_fetch() -> None:
    """The offline mock executor stays outside every product import path."""
    violations = []
    src = ROOT / "src"
    for path in src.rglob("*.py"):
        names = _imported_module_names(path.read_text(encoding="utf-8"), _module_path(path, src))
        if any(
            _matches(name, "scripts.quant_ng_fetch") or _matches(name, "quant_ng_fetch")
            for name in names
        ):
            violations.append(str(path.relative_to(ROOT)))
    assert violations == []
