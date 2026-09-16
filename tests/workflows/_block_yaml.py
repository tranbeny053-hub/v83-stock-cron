from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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


def _scalar(raw_value: str, line_number: int) -> str | dict[str, Any]:
    value = raw_value.strip()
    if not value:
        raise WorkflowYamlError(f"line {line_number}: scalar value is empty")
    if value == "{}":
        return {}
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


def _entry(text: str, line_number: int) -> tuple[str, str | dict[str, Any] | None]:
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


def read_block_yaml(source: str) -> dict[str, Any]:
    return _BlockYamlReader(source).read()
