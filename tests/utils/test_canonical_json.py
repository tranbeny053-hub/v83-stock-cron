"""The single evidence serializer: lossless, driver-independent, round-trip stable."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from crypto_probability_engine.utils import canonical_json as c


def test_decimal_and_float_of_the_same_value_encode_identically() -> None:
    """G1.4: a digest must not depend on whether psycopg returned Decimal or float."""

    assert c.dumps(Decimal("0.6")) == c.dumps(0.6) == c.dumps(Decimal("0.60"))


def test_a_numeric_string_never_collides_with_the_number() -> None:
    assert c.dumps("0.6") != c.dumps(0.6)


def test_high_precision_decimals_are_never_rounded() -> None:
    """normalize() would round to the 28-digit context; this must stay exact."""

    exact = "0.12345678901234567890123456789012345678"
    assert c.canonical_decimal(Decimal(exact)) == exact


def test_genuinely_different_floats_stay_different() -> None:
    assert c.dumps(0.1 + 0.2) != c.dumps(0.3)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("-0.000"), "0"),
        (Decimal("1E+2"), "100"),
        (Decimal("10.500"), "10.5"),
        (1e-7, "0.0000001"),
        (0, "0"),
        (-3, "-3"),
    ],
)
def test_canonical_decimal_text(value, expected) -> None:
    assert c.canonical_decimal(value) == expected


def test_datetimes_are_timezone_independent() -> None:
    """A session timezone must not be able to change a digest."""

    local = datetime(2026, 8, 21, 11, 0, tzinfo=timezone(timedelta(hours=7)))
    utc = datetime(2026, 8, 21, 4, 0, tzinfo=UTC)
    assert c.dumps(local) == c.dumps(utc)


def test_datetime_precision_is_preserved_to_the_microsecond() -> None:
    a = datetime(2026, 8, 21, 4, 0, 0, 1, tzinfo=UTC)
    b = datetime(2026, 8, 21, 4, 0, 0, 0, tzinfo=UTC)
    assert c.dumps(a) != c.dumps(b)
    assert c.decode(c.encode(a)) == a


@pytest.mark.parametrize(
    "value",
    [
        {"p": Decimal("0.6"), "t": datetime(2026, 8, 21, 4, tzinfo=UTC), "n": None},
        [1, 2.5, "x", True, None, {"nested": [Decimal("1.25")]}],
        {"$looks_like_a_tag": "but is data", "$$double": 1},
        {"d": date(2026, 9, 12), "u": UUID(int=7), "b": b"\x00\xff"},
    ],
)
def test_encoding_is_round_trip_stable(value) -> None:
    """A snapshot written and read back must digest exactly as it did when captured."""

    once = c.encode(value)
    assert c.encode(c.decode(once)) == once
    assert c.encode(c.loads(c.dumps(value))) == once


def test_a_data_key_shaped_like_a_tag_is_not_mistaken_for_one() -> None:
    assert c.decode(c.encode({"$decimal": "not a number"})) == {"$decimal": "not a number"}


def test_booleans_are_not_numbers() -> None:
    assert c.dumps(True) != c.dumps(1)


def test_output_is_deterministic_regardless_of_key_order() -> None:
    assert c.dumps({"b": 1, "a": 2}) == c.dumps({"a": 2, "b": 1})


def test_multisets_are_order_independent() -> None:
    rows = [{"id": 1}, {"id": 2}, {"id": 3}]
    assert c.canonical_multiset(rows) == c.canonical_multiset(list(reversed(rows)))


@pytest.mark.parametrize(
    "bad",
    [float("nan"), float("inf"), Decimal("NaN"), datetime(2026, 1, 1), object(), {1: "x"}],
)
def test_unrepresentable_values_fail_closed(bad) -> None:
    with pytest.raises(c.CanonicalEncodingError):
        c.dumps(bad)


def test_malformed_tags_fail_closed_on_decode() -> None:
    with pytest.raises(c.CanonicalEncodingError):
        c.decode({"$decimal": "not-a-number"})
    with pytest.raises(c.CanonicalEncodingError):
        c.decode({"$datetime": "2026-01-01T00:00:00"})  # naive after decode


def test_serialized_text_contains_no_bare_json_number() -> None:
    """Every number is tagged text, so no JSON parser can silently turn it into a float."""

    parsed = json.loads(c.dumps({"x": Decimal("0.1"), "y": [3]}))
    assert parsed == {"x": {"$decimal": "0.1"}, "y": [{"$decimal": "3"}]}
