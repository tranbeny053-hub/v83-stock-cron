from __future__ import annotations

import ast
from pathlib import Path

TESTS_ROOT = Path(__file__).resolve().parent
SKIP_CALLS = {
    "pytest.importorskip",
    "pytest.skip",
    "pytest.xfail",
    "unittest.skip",
    "unittest.skipIf",
    "unittest.skipUnless",
}
SKIP_MARKS = {"pytest.mark.skip", "pytest.mark.skipif", "pytest.mark.xfail"}


def _qualified_name(node: ast.expr) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for imported in node.names:
                local_name = imported.asname or imported.name.split(".", maxsplit=1)[0]
                aliases[local_name] = imported.name if imported.asname else local_name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for imported in node.names:
                local_name = imported.asname or imported.name
                aliases[local_name] = f"{node.module}.{imported.name}"
    return aliases


def _resolved_name(node: ast.expr, aliases: dict[str, str]) -> str:
    name = _qualified_name(node)
    root, separator, remainder = name.partition(".")
    resolved_root = aliases.get(root, root)
    return f"{resolved_root}{separator}{remainder}"


def _skip_violations(source: str, filename: str) -> list[str]:
    tree = ast.parse(source, filename=filename)
    aliases = _import_aliases(tree)
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Attribute, ast.Name)):
            continue
        name = _resolved_name(node, aliases)
        if (
            name in SKIP_CALLS
            or name.endswith(".skipTest")
            or name in SKIP_MARKS
        ):
            violations.append(f"{filename}:{node.lineno} ({name})")
    return violations


def test_suite_contains_no_silent_skips() -> None:
    violations: list[str] = []
    for path in sorted(TESTS_ROOT.rglob("*.py")):
        relative_path = str(path.relative_to(TESTS_ROOT))
        violations.extend(
            _skip_violations(path.read_text(encoding="utf-8"), relative_path)
        )

    assert not violations, "silent skips are prohibited:\n" + "\n".join(violations)


def test_skip_guard_resolves_import_aliases() -> None:
    examples = (
        "import pytest as pt\npt.skip('hidden')\n",
        "from pytest import importorskip as optional\noptional('package')\n",
        "from unittest import skipUnless as conditional\nconditional(False, 'hidden')\n",
        "from pytest import mark as m\n@m.skip\ndef test_hidden(): pass\n",
        "import pytest as pt\n@pt.mark.xfail\ndef test_hidden(): pass\n",
    )

    for source in examples:
        assert _skip_violations(source, "mutation.py"), source
