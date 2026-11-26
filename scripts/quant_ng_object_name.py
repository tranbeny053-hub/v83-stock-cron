"""Token-safe reversible names for digest-derived local objects."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

_FIT_SPEC = importlib.util.spec_from_file_location(
    "quant_ng_fit", Path(__file__).with_name("quant_ng_fit.py")
)
if _FIT_SPEC is None or _FIT_SPEC.loader is None:
    raise RuntimeError("cannot load fit helper")
_FIT = importlib.util.module_from_spec(_FIT_SPEC)
sys.modules["quant_ng_fit"] = _FIT
_PREVIOUS_BYTECODE = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    _FIT_SPEC.loader.exec_module(_FIT)
finally:
    sys.dont_write_bytecode = _PREVIOUS_BYTECODE

Refusal = _FIT.Refusal
PROTECTED = _FIT.PROTECTED
if PROTECTED != ("5a", "f3", "look_run", "holdout", "sealed", "f2_"):
    raise RuntimeError("protected tokens changed; review the object-name alphabet")

ALPHABET = "ghijklmnopqrstuv"
NAME_LENGTH = 64
_HEX = "0123456789abcdef"
_ENCODE = str.maketrans(_HEX, ALPHABET)
_DECODE = str.maketrans(ALPHABET, _HEX)


def is_token_safe(text: str) -> bool:
    """Return whether text contains none of the protected tokens."""
    lowered = text.lower()
    return not any(token.lower() in lowered for token in PROTECTED)


if not all(any(char.lower() not in ALPHABET for char in token) for token in PROTECTED):
    raise RuntimeError("protected tokens changed; review the object-name alphabet")


def encode_digest(hex_digest: str) -> str:
    if (
        not isinstance(hex_digest, str)
        or len(hex_digest) != NAME_LENGTH
        or any(char not in _HEX for char in hex_digest)
    ):
        raise Refusal("digest must be 64 lowercase hex characters")
    return hex_digest.translate(_ENCODE)


def decode_name(name: str) -> str:
    if (
        not isinstance(name, str)
        or len(name) != NAME_LENGTH
        or any(char not in ALPHABET for char in name)
    ):
        raise Refusal("not a canonical object name")
    return name.translate(_DECODE)


def _root_parts(root: Path) -> tuple[str, ...]:
    return tuple(part for part in root.parts if part not in (root.anchor, ""))


def object_path(root: str | os.PathLike[str], hex_digest: str) -> Path:
    try:
        root_path = Path(root)
    except (TypeError, ValueError):
        raise Refusal("root must be an absolute path") from None
    if not root_path.is_absolute():
        raise Refusal("root must be an absolute path")
    if not all(is_token_safe(part) for part in _root_parts(root_path)):
        raise Refusal("protected root component")
    name = encode_digest(hex_digest)
    result = root_path / name
    if result.parent != root_path:
        raise Refusal("object path escapes its root")
    lexical_root = os.path.normpath(os.fspath(root_path))
    lexical_result = os.path.normpath(os.fspath(result))
    if (
        os.path.commonpath((lexical_root, lexical_result)) != lexical_root
        or lexical_result == lexical_root
    ):
        raise Refusal("object path escapes its root")
    if not all(is_token_safe(part) for part in result.parts if part not in (result.anchor, "")):
        raise Refusal("protected object path")
    return result
