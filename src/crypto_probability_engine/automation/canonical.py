"""RFC 8785 JSON Canonicalization Scheme (JCS) for the automation contract.

The one serializer behind the published ``evidence_hash``, the request fingerprint and the wire
bytes of every automation response, so a first response and its replay are the same bytes and any
language with a JCS implementation can re-verify a hash. It covers exactly the JSON the contract
emits: objects with string keys, arrays, strings, booleans, null, integers within +/-(2**53 - 1)
and finite floats. Anything else fails closed with ``CanonicalError``.

- Object members are sorted by the UTF-16 code units of their keys.
- Strings are escaped as ECMAScript ``JSON.stringify`` does: ``\\"``, ``\\\\``, ``\\b``, ``\\f``,
  ``\\n``, ``\\r``, ``\\t``, other controls as lowercase ``\\u00xx``; everything else is emitted as
  UTF-8.
- Numbers are ECMAScript ``Number.prototype.toString``: the shortest round-trip digits, no
  ``.0`` on integral values, ``-0`` as ``0``, and exponent notation only below 1e-6 or from 1e21
  (``1e-7``, ``1e+21``).
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

MAX_SAFE_INTEGER = 2**53 - 1


class CanonicalError(ValueError):
    """A value outside the canonicalizable domain."""


def jcs_bytes(value: Any) -> bytes:
    return _serialize(value).encode("utf-8")


def es_number(value: float | int) -> str:
    """ECMAScript Number.prototype.toString of a finite number."""

    if isinstance(value, bool):
        raise CanonicalError("a boolean is not a number")
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_INTEGER:
            raise CanonicalError("integer outside the IEEE-754 safe range")
        return str(value)
    if not isinstance(value, float) or not math.isfinite(value):
        raise CanonicalError("only finite numbers are canonicalizable")
    if value == 0:
        return "0"
    if value < 0:
        return "-" + es_number(-value)
    text = repr(value).lower()  # the shortest round-trip digits
    mantissa, _, exponent_text = text.partition("e")
    exponent = int(exponent_text) if exponent_text else 0
    whole, _, fraction = mantissa.partition(".")
    raw = whole + fraction
    leading = len(raw) - len(raw.lstrip("0"))
    digits = raw.strip("0")
    k = len(digits)
    n = len(whole) + exponent - leading  # value == 0.<digits> * 10**n
    if k <= n <= 21:
        return digits + "0" * (n - k)
    if 0 < n <= 21:
        return digits[:n] + "." + digits[n:]
    if -6 < n <= 0:
        return "0." + "0" * (-n) + digits
    sign = "+" if n - 1 >= 0 else "-"
    head = digits if k == 1 else digits[0] + "." + digits[1:]
    return f"{head}e{sign}{abs(n - 1)}"


def _serialize(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int | float):
        return es_number(value)
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, Mapping):
        keys = list(value)
        if not all(isinstance(key, str) for key in keys):
            raise CanonicalError("object keys must be strings")
        ordered = sorted(keys, key=lambda key: key.encode("utf-16-be"))
        return "{" + ",".join(f"{_string(key)}:{_serialize(value[key])}" for key in ordered) + "}"
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return "[" + ",".join(_serialize(item) for item in value) + "]"
    raise CanonicalError(f"unsupported type {type(value).__name__}")


def _string(value: str) -> str:
    # json.dumps(ensure_ascii=False) escapes exactly the ECMAScript set, with lowercase hex.
    encoded = json.dumps(value, ensure_ascii=False)
    try:
        encoded.encode("utf-8")
    except UnicodeEncodeError:
        raise CanonicalError("a string is not well-formed Unicode") from None
    return encoded
