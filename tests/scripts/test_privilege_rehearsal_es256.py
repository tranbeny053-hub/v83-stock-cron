"""E3: the scratch ES256 tokens of P3-PRIV-R (scripts/privilege_rehearsal/es256.py).

OpenSSL generates a throwaway P-256 key in pytest's tmp_path. The test checks each token's
signature independently with `openssl dgst -verify`, never with the code under test. Behind a real
PostgREST, J1 proves the same tokens are accepted and refused as Supabase documents.
"""

from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path

import pytest

from scripts.privilege_rehearsal import es256


def _key(tmp_path: Path, name: str = "key.pem") -> str:
    path = tmp_path / name
    subprocess.run(["openssl", "ecparam", "-name", "prime256v1", "-genkey", "-noout",
                    "-out", str(path)], check=True, capture_output=True)
    return str(path)


def _decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def _der_from_jose(raw: bytes) -> bytes:
    def integer(value: bytes) -> bytes:
        value = value.lstrip(b"\0") or b"\0"
        if value[0] & 0x80:
            value = b"\0" + value
        return b"\x02" + bytes([len(value)]) + value

    body = integer(raw[:32]) + integer(raw[32:])
    return b"\x30" + bytes([len(body)]) + body


def _verifies(tmp_path: Path, key_file: str, token: str) -> bool:
    signing_input, _, signature = token.rpartition(".")
    public = tmp_path / "public.pem"
    subprocess.run(["openssl", "ec", "-in", key_file, "-pubout", "-out", str(public)],
                   check=True, capture_output=True)
    (tmp_path / "signature.der").write_bytes(_der_from_jose(_decode(signature)))
    checked = subprocess.run(
        ["openssl", "dgst", "-sha256", "-verify", str(public), "-signature",
         str(tmp_path / "signature.der")],
        input=signing_input.encode("ascii"), capture_output=True,
    )
    return checked.returncode == 0


def test_a_token_carries_the_kid_the_role_and_a_short_expiry_and_verifies(tmp_path: Path) -> None:
    key_file = _key(tmp_path)
    token = es256.mint(key_file, "ucpe_api_writer", now=1_800_000_000)
    header, claims, signature = token.split(".")
    assert json.loads(_decode(header)) == {"alg": "ES256", "kid": es256.KID, "typ": "JWT"}
    assert json.loads(_decode(claims)) == {
        "role": "ucpe_api_writer", "sub": "ucpe-rehearsal", "iat": 1_800_000_000,
        "exp": 1_800_000_600,
    }
    assert len(_decode(signature)) == 64, "JOSE r || s, never DER"
    assert _verifies(tmp_path, key_file, token)


def test_another_key_s_signature_does_not_verify(tmp_path: Path) -> None:
    token = es256.mint(_key(tmp_path, "one.pem"), "ucpe_api_writer")
    assert not _verifies(tmp_path, _key(tmp_path, "other.pem"), token)


def test_the_jwks_publishes_only_the_public_point(tmp_path: Path) -> None:
    key_file = _key(tmp_path)
    (key,) = es256.jwks(key_file)["keys"]
    assert set(key) == {"kty", "crv", "x", "y", "kid", "alg", "use"}
    assert (key["kty"], key["crv"], key["alg"], key["kid"]) == ("EC", "P-256", "ES256", es256.KID)
    assert len(_decode(key["x"])) == len(_decode(key["y"])) == 32
    private = Path(key_file).read_text(encoding="ascii")
    assert "d" not in key and key["x"] not in private


@pytest.mark.parametrize(
    "signature",
    [b"", b"\x31\x06\x02\x01\x01\x02\x01\x01", b"\x30\x06\x03\x01\x01\x02\x01\x01",
     b"\x30\x07\x02\x01\x01\x02\x01\x01\x00", b"\x30\x26\x02\x21" + b"\x01" * 33 + b"\x02\x01\x01"],
    ids=["empty", "not-a-sequence", "not-an-integer", "trailing-bytes", "integer-too-long"],
)
def test_a_malformed_der_signature_is_refused(signature: bytes) -> None:
    with pytest.raises(ValueError):
        es256.der_to_jose(signature)


def test_short_and_sign_padded_integers_become_exactly_32_bytes_each() -> None:
    """DER drops leading zero bytes and prefixes 0x00 to a high-bit integer; JOSE wants each
    integer as exactly 32 big-endian bytes. Random keys rarely show either case, so pin both."""

    r = b"\x01" * 31
    s = b"\x80" + b"\x02" * 31
    der = b"\x30" + bytes([2 + 31 + 2 + 33]) + b"\x02\x1f" + r + b"\x02\x21\x00" + s
    assert es256.der_to_jose(der) == b"\x00" + r + s
