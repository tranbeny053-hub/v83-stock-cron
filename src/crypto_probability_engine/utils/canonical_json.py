"""Lossless, driver-independent canonical JSON for §5A evidence.

WHY THIS EXISTS. Verification finding G1: Postgres ``NUMERIC`` arrives through psycopg as
``Decimal``, the previous serializer handled only ``datetime``, and it ran after the
probability read — so on real data the first consumption would have read the holdout and
raised. G9: the Postgres seal claim used a *different*, plainer serializer, a second route to
the same failure. There is now exactly ONE serializer, and every evidence path uses it.

THE CONTRACT
- **Total over the types the driver returns** for the projected columns: ``NUMERIC`` ->
  ``Decimal``, ``TIMESTAMPTZ`` -> ``datetime``, ``TEXT`` -> ``str``, ``JSONB`` ->
  ``dict``/``list``/scalars, ``NULL`` -> ``None``, plus ``int``, ``float``, ``bool``, ``date``,
  ``UUID`` and bytes. Anything else fails closed with a precise error.
- **Lossless in value.** A ``Decimal`` is rendered exactly with ``format(d, "f")`` — never via
  ``normalize()``, whose context precision (28 digits) would silently ROUND a high-precision
  value. A ``float`` is taken as its shortest round-trip decimal (``repr``), which recovers
  the original decimal a driver approximated and round-trips to the identical float.
- **Driver-independent.** ``Decimal("0.6")``, ``0.6`` and ``Decimal("0.60")`` are one value and
  encode identically, so a digest cannot depend on whether psycopg handed back ``Decimal`` or
  ``float`` (G1.4). ``TEXT "0.6"`` stays a string and does NOT collide with the number.
- **Timezone-independent.** An aware ``datetime`` is converted to UTC with microsecond
  precision, so a session timezone cannot change a digest. A naive ``datetime`` is ambiguous
  and fails closed.
- **Round-trip stable.** ``encode(decode(encode(x))) == encode(x)``. A snapshot written to disk
  and read back digests to the same value, so a valid snapshot can never be mistaken for a
  tampered one — which would otherwise make every tamper test pass vacuously.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

TAG_DECIMAL = "$decimal"
TAG_DATETIME = "$datetime"
TAG_DATE = "$date"
TAG_UUID = "$uuid"
TAG_BYTES = "$bytes"
_TAGS = frozenset({TAG_DECIMAL, TAG_DATETIME, TAG_DATE, TAG_UUID, TAG_BYTES})


class CanonicalEncodingError(TypeError):
    """A value cannot be represented losslessly and unambiguously."""


def canonical_decimal(value: Any) -> str:
    """Return the exact, normalized decimal text of a finite number."""

    if isinstance(value, bool):
        raise CanonicalEncodingError("a boolean is not a number")
    if isinstance(value, Decimal):
        number = value
    elif isinstance(value, int):
        number = Decimal(value)
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalEncodingError(f"non-finite float cannot be evidence: {value!r}")
        number = Decimal(repr(value))
    else:
        raise CanonicalEncodingError(f"not a number: {type(value).__name__}")
    if not number.is_finite():
        raise CanonicalEncodingError(f"non-finite decimal cannot be evidence: {number!r}")
    text = format(number, "f")  # exact; no context precision, no rounding
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in {"-0", ""}:
        text = "0"
    return text


def encode(value: Any) -> Any:
    """Return a JSON-safe, tagged, canonical structure for ``value``."""

    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, (int, float, Decimal)):
        return {TAG_DECIMAL: canonical_decimal(value)}
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise CanonicalEncodingError("a naive datetime is ambiguous and cannot be evidence")
        return {TAG_DATETIME: value.astimezone(UTC).isoformat(timespec="microseconds")}
    if isinstance(value, date):
        return {TAG_DATE: value.isoformat()}
    if isinstance(value, UUID):
        return {TAG_UUID: str(value)}
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {TAG_BYTES: bytes(value).hex()}
    if isinstance(value, Mapping):
        encoded: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalEncodingError(f"mapping key must be a string: {key!r}")
            encoded[_escape_key(key)] = encode(item)
        return encoded
    if isinstance(value, (list, tuple)):
        return [encode(item) for item in value]
    raise CanonicalEncodingError(f"unsupported evidence type: {type(value).__name__}")


def decode(value: Any) -> Any:
    """Invert :func:`encode`."""

    if isinstance(value, list):
        return [decode(item) for item in value]
    if not isinstance(value, dict):
        return value
    if len(value) == 1:
        ((key, item),) = value.items()
        if key in _TAGS:
            return _decode_tag(key, item)
    return {_unescape_key(key): decode(item) for key, item in value.items()}


def serialize(encoded: Any, *, pretty: bool = False) -> bytes:
    """Serialize an ALREADY-ENCODED structure deterministically."""

    return json.dumps(
        encoded,
        sort_keys=True,
        separators=None if pretty else (",", ":"),
        indent=2 if pretty else None,
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def dumps(value: Any) -> bytes:
    return serialize(encode(value))


def pretty(value: Any) -> bytes:
    return serialize(encode(value), pretty=True)


def loads(data: bytes | str) -> Any:
    return decode(json.loads(data))


def canonical_multiset(items: Any) -> list[Any]:
    """Encode each item and sort by its canonical text.

    Evidence rows are a multiset: the order a driver returns them in carries no meaning, so
    it must not be able to change a digest (G5.3).
    """

    encoded = [encode(item) for item in items]
    return sorted(encoded, key=lambda item: serialize(item))


def _escape_key(key: str) -> str:
    return "$" + key if key.startswith("$") else key


def _unescape_key(key: str) -> str:
    return key[1:] if key.startswith("$$") else key


def _decode_tag(tag: str, text: Any) -> Any:
    if not isinstance(text, str):
        raise CanonicalEncodingError(f"malformed {tag} payload: {text!r}")
    try:
        if tag == TAG_DECIMAL:
            return Decimal(text)
        if tag == TAG_DATETIME:
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                raise CanonicalEncodingError("decoded datetime lost its timezone")
            return parsed
        if tag == TAG_DATE:
            return date.fromisoformat(text)
        if tag == TAG_UUID:
            return UUID(text)
        return bytes.fromhex(text)
    except (InvalidOperation, ValueError) as exc:
        raise CanonicalEncodingError(f"malformed {tag} payload: {text!r}") from exc
