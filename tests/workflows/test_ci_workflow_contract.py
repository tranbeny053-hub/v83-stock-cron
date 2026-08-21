from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest


class WorkflowYamlError(AssertionError):
    """Raised when workflow YAML exceeds the deliberately small supported subset."""


@dataclass(frozen=True)
class _Line:
    number: int
    indent: int
    text: str


def _lines(source: str) -> list[_Line]:
    result = []
    for number, raw_line in enumerate(source.splitlines(), start=1):
        if "\t" in raw_line:
            raise WorkflowYamlError(f"line {number}: tab characters are unsupported")
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        text = raw_line.lstrip(" ")
        result.append(_Line(number, len(raw_line) - len(text), text))
    return result


def _mapping_separator(text: str) -> int | None:
    quote = None
    for index, character in enumerate(text):
        if quote:
            if character == quote:
                quote = None
            continue
        if character in {"'", '"'}:
            quote = character
        elif character == ":" and (
            index + 1 == len(text) or text[index + 1].isspace()
        ):
            return index
    if quote:
        raise WorkflowYamlError("unterminated quoted string")
    return None


def _unquote_key(raw_key: str, line_number: int) -> str:
    key = raw_key.strip()
    if not key:
        raise WorkflowYamlError(f"line {line_number}: mapping key is empty")
    if key[0] in {"'", '"'}:
        if len(key) < 2 or key[-1] != key[0]:
            raise WorkflowYamlError(f"line {line_number}: malformed quoted key")
        key = key[1:-1]
    elif "'" in key or '"' in key:
        raise WorkflowYamlError(f"line {line_number}: malformed quoted key")
    if key == "<<" or key.startswith(("!", "?", "&", "*")):
        raise WorkflowYamlError(f"line {line_number}: unsupported mapping marker")
    if any(marker in key for marker in "{["):
        raise WorkflowYamlError(f"line {line_number}: flow-style keys are unsupported")
    return key


def _scalar(raw_value: str, line_number: int) -> str:
    value = raw_value.strip()
    if not value:
        raise WorkflowYamlError(f"line {line_number}: scalar value is empty")
    if value[0] in {"'", '"'}:
        if len(value) < 2 or value[-1] != value[0]:
            raise WorkflowYamlError(f"line {line_number}: malformed quoted scalar")
        return value[1:-1]
    if " #" in value:
        value = value.split(" #", maxsplit=1)[0].rstrip()
    if not value:
        raise WorkflowYamlError(f"line {line_number}: scalar value is empty")
    if value.startswith(("|", ">", "&", "*", "!", "?")):
        raise WorkflowYamlError(f"line {line_number}: unsupported scalar marker")
    if any(marker in value for marker in "{["):
        raise WorkflowYamlError(f"line {line_number}: flow style is unsupported")
    return value


def _entry(text: str, line_number: int) -> tuple[str, str | None]:
    separator = _mapping_separator(text)
    if separator is None:
        raise WorkflowYamlError(f"line {line_number}: expected a mapping entry")
    key = _unquote_key(text[:separator], line_number)
    remainder = text[separator + 1 :].strip()
    return key, _scalar(remainder, line_number) if remainder else None


class _BlockYamlReader:
    def __init__(self, source: str) -> None:
        self.lines = _lines(source)

    def read(self) -> dict[str, Any]:
        if not self.lines:
            return {}
        if self.lines[0].indent != 0:
            raise WorkflowYamlError("the document root must not be indented")
        value, index = self._block(0, 0)
        if index != len(self.lines):
            line = self.lines[index]
            raise WorkflowYamlError(f"line {line.number}: unexpected indentation")
        if not isinstance(value, dict):
            raise WorkflowYamlError("the document root must be a mapping")
        return value

    def _block(self, index: int, indent: int) -> tuple[Any, int]:
        line = self.lines[index]
        if line.indent != indent:
            raise WorkflowYamlError(f"line {line.number}: unexpected indentation")
        if line.text.startswith("-"):
            return self._sequence(index, indent)
        return self._mapping(index, indent)

    def _mapping(self, index: int, indent: int) -> tuple[dict[str, Any], int]:
        result: dict[str, Any] = {}
        while index < len(self.lines):
            line = self.lines[index]
            if line.indent < indent:
                break
            if line.indent > indent:
                raise WorkflowYamlError(f"line {line.number}: unexpected indentation")
            if line.text.startswith("-"):
                raise WorkflowYamlError(
                    f"line {line.number}: cannot mix a sequence with mapping keys"
                )
            key, value = _entry(line.text, line.number)
            if key in result:
                raise WorkflowYamlError(f"line {line.number}: duplicate key {key!r}")
            index += 1
            if value is None and index < len(self.lines):
                child = self.lines[index]
                if child.indent > indent:
                    value, index = self._block(index, child.indent)
                elif child.indent == indent and child.text.startswith("-"):
                    value, index = self._sequence(
                        index, indent, allow_mapping_end=True
                    )
            result[key] = value
        return result, index

    def _sequence(
        self, index: int, indent: int, *, allow_mapping_end: bool = False
    ) -> tuple[list[Any], int]:
        result = []
        while index < len(self.lines):
            line = self.lines[index]
            if line.indent < indent:
                break
            if line.indent > indent:
                raise WorkflowYamlError(f"line {line.number}: unexpected indentation")
            if not line.text.startswith("-"):
                if allow_mapping_end:
                    break
                raise WorkflowYamlError(
                    f"line {line.number}: cannot mix mapping keys with a sequence"
                )
            if not line.text.startswith("- ") or not line.text[2:].strip():
                raise WorkflowYamlError(f"line {line.number}: bare sequence item")
            item_text = line.text[2:].strip()
            separator = _mapping_separator(item_text)
            index += 1
            if separator is None:
                result.append(_scalar(item_text, line.number))
                continue
            key, value = _entry(item_text, line.number)
            if value is None:
                raise WorkflowYamlError(
                    f"line {line.number}: sequence mapping values cannot be empty"
                )
            item = {key: value}
            continuation_indent = indent + 2
            if index < len(self.lines) and self.lines[index].indent > indent:
                if self.lines[index].indent != continuation_indent:
                    child = self.lines[index]
                    raise WorkflowYamlError(
                        f"line {child.number}: sequence mapping keys are misaligned"
                    )
                continuation, index = self._mapping(index, continuation_indent)
                duplicates = item.keys() & continuation.keys()
                if duplicates:
                    duplicate = sorted(duplicates)[0]
                    raise WorkflowYamlError(f"duplicate sequence item key {duplicate!r}")
                item.update(continuation)
            result.append(item)
        return result, index


def _read_block_yaml(source: str) -> dict[str, Any]:
    return _BlockYamlReader(source).read()


def _workflow() -> tuple[str, dict[str, Any]]:
    root = Path(__file__).resolve().parents[2]
    text = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    return text, _read_block_yaml(text)


def _run_commands(document: dict[str, Any]) -> list[str]:
    return [step["run"] for step in document["jobs"]["test"]["steps"] if "run" in step]


def _contains_key(value: Any, sought: str) -> bool:
    if isinstance(value, dict):
        return sought in value or any(_contains_key(child, sought) for child in value.values())
    if isinstance(value, list):
        return any(_contains_key(child, sought) for child in value)
    return False


def test_reader_preserves_nested_mapping_scope() -> None:
    document = _read_block_yaml(
        """push:
  branches:
  - main
branches:
- unrelated
marker: kept
"""
    )

    assert document["push"]["branches"] == ["main"]
    assert document["branches"] == ["unrelated"]
    assert document["marker"] == "kept"


def test_reader_distinguishes_empty_and_nested_keys() -> None:
    document = _read_block_yaml(
        """empty:
nested:
  child: value
"""
    )

    assert document == {"empty": None, "nested": {"child": "value"}}


@pytest.mark.parametrize(
    "source",
    (
        "root:\n\tchild: value\n",
        "root: {child: value}\n",
        "root: [one, two]\n",
        "root: |\n  value\n",
        "root: >\n  value\n",
        "root: >-\n  value\n",
        "root: &anchor value\n",
        "root: *anchor\n",
        "root: !tag value\n",
        "? root: value\n",
        "<<: value\n",
        "root:\n  -\n",
        "not a mapping\n",
        "root:\n  child: value\n  - item\n",
    ),
)
def test_reader_rejects_unsupported_constructs(source: str) -> None:
    with pytest.raises(WorkflowYamlError):
        _read_block_yaml(source)


def test_post_merge_main_trigger_exists() -> None:
    _, document = _workflow()

    assert "main" in document["on"]["push"]["branches"], (
        "main push trigger is required so CI verifies the post-merge commit"
    )


def test_pre_existing_triggers_are_preserved() -> None:
    _, document = _workflow()
    triggers = document["on"]

    assert set(triggers) == {"push", "pull_request"}, "CI trigger types changed"
    assert set(triggers["push"]["branches"]) == {"main", "codex/**"}, (
        "push branches must preserve codex/** while adding main"
    )
    assert triggers["pull_request"] is None, (
        "pull requests must continue to run on every branch"
    )


def test_workflow_token_has_least_privilege() -> None:
    _, document = _workflow()

    assert document.get("permissions") == {"contents": "read"}, (
        "the workflow token must have read-only contents permission"
    )
    for job_name, job in document["jobs"].items():
        assert "permissions" not in job, f"job {job_name!r} overrides token permissions"


def test_verification_steps_are_unchanged() -> None:
    _, document = _workflow()
    job = document["jobs"]["test"]
    steps = job["steps"]

    assert job["runs-on"] == "ubuntu-latest", "the CI runner changed"
    assert _run_commands(document) == [
        "python -m pip install -r requirements.txt",
        "ruff check src tests scripts",
        "PYTHONPATH=src python -m pytest",
        "PYTHONPATH=src python scripts/validate_schemas.py",
        "PYTHONPATH=src python scripts/manual_smoke.py",
        "python scripts/check_no_forbidden_scope.py",
        "python scripts/check_no_full_article_body.py",
        "python scripts/check_no_secrets.py",
    ], "the ordered CI verification commands changed"
    # Current stable Node-24-native majors, measured from each action.yml runs.using field.
    # This stays strict so future bumps are reviewed rather than drifting in.
    assert [step for step in steps if "uses" in step] == [
        {"uses": "actions/checkout@v7"},
        {
            "uses": "actions/setup-python@v7",
            "with": {"python-version": "3.11"},
        },
    ], "checkout or Python setup steps changed"


def test_all_safety_scanners_still_run() -> None:
    root = Path(__file__).resolve().parents[2]
    _, document = _workflow()
    commands = _run_commands(document)

    for scanner in (
        "check_no_forbidden_scope",
        "check_no_full_article_body",
        "check_no_secrets",
    ):
        expected = f"python scripts/{scanner}.py"
        assert expected in commands, f"required safety scanner {scanner!r} is missing"

    verify_text = (root / "verify.sh").read_text(encoding="utf-8")
    scanners = set(re.findall(r"\bcheck_no_[a-z_]+\b", verify_text))
    assert scanners, "verify.sh must declare at least one safety scanner"
    for scanner in scanners:
        expected = f"python scripts/{scanner}.py"
        assert expected in commands, (
            f"CI is missing safety scanner {scanner!r} declared by verify.sh"
        )


def test_workflow_has_no_privileged_or_out_of_scope_access() -> None:
    text, document = _workflow()
    lowered = text.lower()

    for token in (
        "${{",
        "supabase",
        "_db_url",
        "database_url",
        "huggingface",
        "hf.space",
        "collect_oos_pair_evidence",
        "resolve_outcomes",
        "source_integrity_guard",
        "deploy",
        "git push",
        "workflow_dispatch",
        "schedule:",
        "cron",
        "id-token",
        "environment:",
    ):
        assert token not in lowered, f"always-on CI contains prohibited token {token!r}"
    assert not _contains_key(document, "env"), "always-on CI must not define env at any depth"
