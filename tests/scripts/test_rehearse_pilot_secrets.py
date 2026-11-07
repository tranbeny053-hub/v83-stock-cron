from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DRIVER = ROOT / "scripts/migration_0019_rehearsal/rehearse_pilot.py"


def test_with_secret_receives_only_ephemeral_passwords_or_the_negative_fixture():
    tree = ast.parse(DRIVER.read_text(encoding="utf-8"))
    token_names = {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr == "token_urlsafe"
        and isinstance(node.value.func.value, ast.Name)
        and node.value.func.value.id == "secrets"
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_with_secret"
    ]
    assert calls
    for call in calls:
        assert len(call.args) == 1
        arg = call.args[0]
        assert (
            isinstance(arg, ast.Name) and arg.id in token_names
        ) or (
            isinstance(arg, ast.Constant) and arg.value == "not-the-password"
        )
