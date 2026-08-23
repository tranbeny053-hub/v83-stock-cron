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


def _qualified_name(node: ast.expr) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def test_suite_contains_no_silent_skips() -> None:
    violations: list[str] = []
    for path in sorted(TESTS_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = _qualified_name(node.func)
                if name in SKIP_CALLS or name.endswith(".skipTest"):
                    violations.append(f"{path.relative_to(TESTS_ROOT)}:{node.lineno} ({name})")
            if isinstance(node, ast.Attribute):
                name = _qualified_name(node)
                if name in {"pytest.mark.skip", "pytest.mark.skipif"}:
                    violations.append(f"{path.relative_to(TESTS_ROOT)}:{node.lineno} ({name})")

    assert not violations, "silent skips are prohibited:\n" + "\n".join(violations)
