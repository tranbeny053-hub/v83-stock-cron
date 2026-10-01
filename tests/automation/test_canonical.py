"""RFC 8785 JCS: the canonical form behind evidence_hash, the fingerprint and the wire bytes."""

from __future__ import annotations

import math

import pytest

from crypto_probability_engine.automation.canonical import CanonicalError, es_number, jcs_bytes

NUMBER_VECTORS = [
    (0.0, "0"),
    (-0.0, "0"),
    (1.0, "1"),
    (-1.0, "-1"),
    (4.5, "4.5"),
    (0.002, "0.002"),
    (1e-6, "0.000001"),
    (1e-7, "1e-7"),
    (1.5e-7, "1.5e-7"),
    (-1e-7, "-1e-7"),
    (100.0, "100"),
    (1e20, "100000000000000000000"),
    (1e21, "1e+21"),
    (2.5e25, "2.5e+25"),
    (1.2345678901234568e20, "123456789012345680000"),
    (5e-324, "5e-324"),
    (1.7976931348623157e308, "1.7976931348623157e+308"),
    (9007199254740992.0, "9007199254740992"),
    (0.1 + 0.2, "0.30000000000000004"),
    (123e-20, "1.23e-18"),
    (333333333.3333332, "333333333.3333332"),
    (0.3668168938185069, "0.3668168938185069"),
    (6, "6"),
    (-(2**53 - 1), "-9007199254740991"),
]


@pytest.mark.parametrize(("value", "expected"), NUMBER_VECTORS)
def test_numbers_follow_ecmascript(value, expected):
    assert es_number(value) == expected
    assert jcs_bytes(value) == expected.encode("ascii")


def test_members_sort_by_utf16_code_units_and_nest():
    value = {"b": 1, "a": [1.0, True, None], "é": "·", "€": 2, "A": -0.0}
    assert jcs_bytes(value) == '{"A":0,"a":[1,true,null],"b":1,"é":"·","€":2}'.encode()


def test_supplementary_characters_sort_as_surrogate_pairs():
    # U+1F600 (surrogates D83D DE00) sorts before U+FB01 in UTF-16, after it in code points.
    value = {"ﬁ": 1, "\U0001f600": 2}
    assert jcs_bytes(value) == '{"\U0001f600":2,"ﬁ":1}'.encode()


def test_strings_escape_exactly_the_ecmascript_set():
    value = 'q"b\\n\nt\tc\x1fd\x7fé€/'
    assert jcs_bytes(value) == ('"q\\"b\\\\n\\nt\\tc\\u001fd\x7fé€/"').encode()


@pytest.mark.parametrize(
    "value",
    [math.nan, math.inf, -math.inf, 2**53, -(2**53), {1: "x"}, b"bytes", "\ud800", object()],
)
def test_values_outside_the_domain_are_refused(value):
    with pytest.raises(CanonicalError):
        jcs_bytes(value)


def test_a_boolean_is_never_a_number():
    with pytest.raises(CanonicalError):
        es_number(True)
