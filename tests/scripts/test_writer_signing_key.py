"""E3: the owner's writer signing key and token (scripts/writer_signing_key.py).

Every key here is a throwaway in pytest's tmp_path; no real key or token is ever made. The import
format is pinned to Supabase's own sources (re-read 2026-10-03):
- the CLI, `supabase gen signing-key --algorithm ES256` (supabase/cli, develop 28b8aa04a1a5,
  apps/cli/src/commands/gen/signing-key/signing-key.handler.ts), prints one compact JSON object:
  kty, kid (randomUUID), use, key_ops, alg, ext, d, crv, x, y;
- the dashboard's "Import an existing private key" box (apps/studio, create-key-dialog.tsx) requires
  kty "EC", crv "P-256" and the strings kty, crv, x, y, d, and sends the parsed object unchanged;
- the Management API's CreateSigningKeyBody (packages/api-types, api-v1.d.ts) allows exactly the
  CLI's members for an ES256 private_jwk, with kid in UUID format.
That the JWK is the PEM's key is checked independently of the code under test: by P-256 arithmetic
written out here, by `openssl dgst -verify` against a public key built from the JWK alone, and by
Node's JWK import.
"""

from __future__ import annotations

import base64
import json
import os
import stat
import subprocess
import textwrap
import uuid
from pathlib import Path

import pytest

from scripts import writer_signing_key as signing
from scripts.privilege_rehearsal import es256

# NIST P-256 (SEC 2, secp256r1).
_P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
_A = _P - 3
_B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
_G = (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
      0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5)
_SPKI_PREFIX = bytes.fromhex("3059301306072a8648ce3d020106082a8648ce3d030107034200")
_NODE_CHECK = r"""
const crypto = require("node:crypto");
let input = "";
process.stdin.on("data", (chunk) => (input += chunk)).on("end", () => {
  const { jwk, token } = JSON.parse(input);
  const privateKey = crypto.createPrivateKey({ key: jwk, format: "jwk" });
  const publicKey = crypto.createPublicKey({
    key: { kty: jwk.kty, crv: jwk.crv, x: jwk.x, y: jwk.y }, format: "jwk",
  });
  const p1363 = { dsaEncoding: "ieee-p1363" };
  const probe = Buffer.from("ucpe-writer-signing-key-probe");
  const probeSignature = crypto.sign("sha256", probe, { key: privateKey, ...p1363 });
  const [header, claims, signature] = token.split(".");
  process.stdout.write(JSON.stringify({
    curve: privateKey.asymmetricKeyDetails.namedCurve,
    scalar_matches_point: crypto.verify("sha256", probe, { key: publicKey, ...p1363 },
      probeSignature),
    token_verifies: crypto.verify("sha256", Buffer.from(`${header}.${claims}`),
      { key: publicKey, ...p1363 }, Buffer.from(signature, "base64url")),
  }));
});
"""


def _decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def _times_g(k: int) -> tuple[int, int]:
    """k·G on P-256, by double-and-add in affine coordinates."""

    def add(p, q):
        if p is None:
            return q
        if q is None:
            return p
        if p[0] == q[0] and (p[1] + q[1]) % _P == 0:
            return None
        if p == q:
            slope = (3 * p[0] * p[0] + _A) * pow(2 * p[1], -1, _P) % _P
        else:
            slope = (q[1] - p[1]) * pow(q[0] - p[0], -1, _P) % _P
        x = (slope * slope - p[0] - q[0]) % _P
        return x, (slope * (p[0] - x) - p[1]) % _P

    result, addend = None, _G
    while k:
        if k & 1:
            result = add(result, addend)
        addend = add(addend, addend)
        k >>= 1
    return result


def _der_from_jose(raw: bytes) -> bytes:
    def integer(value: bytes) -> bytes:
        value = value.lstrip(b"\0") or b"\0"
        if value[0] & 0x80:
            value = b"\0" + value
        return b"\x02" + bytes([len(value)]) + value

    body = integer(raw[:32]) + integer(raw[32:])
    return b"\x30" + bytes([len(body)]) + body


def _verifies_with_jwk(tmp_path: Path, jwk: dict, signing_input: str, signature: str) -> bool:
    """openssl dgst -verify, with a public key built from the JWK's x and y alone."""

    spki = _SPKI_PREFIX + b"\x04" + _decode(jwk["x"]) + _decode(jwk["y"])
    body = "\n".join(textwrap.wrap(base64.b64encode(spki).decode("ascii"), 64))
    public = tmp_path / "imported-public.pem"
    public.write_text(f"-----BEGIN PUBLIC KEY-----\n{body}\n-----END PUBLIC KEY-----\n")
    (tmp_path / "signature.der").write_bytes(_der_from_jose(_decode(signature)))
    checked = subprocess.run(
        ["openssl", "dgst", "-sha256", "-verify", str(public), "-signature",
         str(tmp_path / "signature.der")],
        input=signing_input.encode("ascii"), capture_output=True,
    )
    return checked.returncode == 0


@pytest.fixture()
def key_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "ucpe-keys"
    signing.generate(folder)
    return folder


def _jwk(folder: Path) -> dict:
    return json.loads((folder / signing.JWK_NAME).read_text(encoding="ascii"))


def test_generate_writes_the_cli_s_private_jwk_and_the_pem_owner_only(key_folder: Path) -> None:
    text = (key_folder / signing.JWK_NAME).read_text(encoding="ascii")
    jwk = json.loads(text)
    assert tuple(jwk) == ("kty", "kid", "use", "key_ops", "alg", "ext", "d", "crv", "x", "y")
    assert text == json.dumps(jwk, separators=(",", ":")) + "\n", "the CLI's compact JSON"
    assert {name: jwk[name] for name in ("kty", "use", "key_ops", "alg", "ext", "crv")} == {
        "kty": "EC", "use": "sig", "key_ops": ["sign", "verify"], "alg": "ES256", "ext": True,
        "crv": "P-256",
    }
    assert str(uuid.UUID(jwk["kid"])) == jwk["kid"] and uuid.UUID(jwk["kid"]).version == 4
    for name in ("d", "x", "y"):
        assert "=" not in jwk[name] and len(_decode(jwk[name])) == 32, name
    assert (key_folder / signing.PEM_NAME).read_bytes().startswith(b"-----BEGIN EC PRIVATE KEY")
    modes = [stat.S_IMODE(os.stat(path).st_mode) for path in
             (key_folder, key_folder / signing.PEM_NAME, key_folder / signing.JWK_NAME)]
    assert modes == [0o700, 0o600, 0o600]


def test_the_jwk_passes_the_dashboard_check_and_the_management_api_schema(
    key_folder: Path,
) -> None:
    jwk = _jwk(key_folder)
    # create-key-dialog.tsx, for ES256.
    assert jwk["kty"] == "EC" and jwk["crv"] == "P-256"
    assert all(isinstance(jwk[name], str) and jwk[name] for name in ("kty", "crv", "x", "y", "d"))
    # CreateSigningKeyBody's ES256 private_jwk: these members and no other.
    assert set(jwk) <= {"alg", "crv", "d", "ext", "key_ops", "kid", "kty", "use", "x", "y"}
    assert set(jwk["key_ops"]) <= {"sign", "verify"} and jwk["ext"] is True


def test_the_jwk_is_the_pem_s_key_by_p256_arithmetic_written_out_here(key_folder: Path) -> None:
    assert (_G[1] ** 2 - _G[0] ** 3 - _A * _G[0] - _B) % _P == 0, "the constants are P-256's"
    jwk = _jwk(key_folder)
    d = int.from_bytes(_decode(jwk["d"]), "big")
    point = tuple(int.from_bytes(_decode(jwk[name]), "big") for name in ("x", "y"))
    assert _times_g(d) == point
    x, y = es256.public_point(str(key_folder / signing.PEM_NAME))
    assert (es256.b64url(x), es256.b64url(y)) == (jwk["x"], jwk["y"])
    assert signing.public_of_scalar(_decode(jwk["d"])) == (x, y)


def test_the_writer_token_carries_the_jwk_s_kid_and_verifies_with_its_public_half(
    key_folder: Path, tmp_path: Path
) -> None:
    pem_path, jwk = signing.load(key_folder)
    token = signing.writer_token(str(pem_path), kid=jwk["kid"], now=1_800_000_000)
    header, claims, signature = token.split(".")
    assert json.loads(_decode(header)) == {"alg": "ES256", "kid": jwk["kid"], "typ": "JWT"}
    assert json.loads(_decode(claims)) == {
        "role": "ucpe_api_writer", "iat": 1_800_000_000, "exp": 1_800_000_000 + 2_592_000,
    }
    assert signing.LIFETIME == 2_592_000, "E3-B: 30 days"
    assert _verifies_with_jwk(tmp_path, jwk, f"{header}.{claims}", signature)
    forged = f"{header}.{claims[:-2]}{'B' if claims[-2] != 'B' else 'C'}{claims[-1]}"
    assert not _verifies_with_jwk(tmp_path, jwk, forged, signature)


def test_node_imports_the_jwk_as_one_key_and_verifies_the_token(key_folder: Path) -> None:
    """Node's crypto, which the Supabase CLI uses to make its JWK, imports the exact file. (Node is
    already required: the frontend tests run it.)"""

    pem_path, jwk = signing.load(key_folder)
    checked = subprocess.run(
        ["node", "-e", _NODE_CHECK], capture_output=True, check=True,
        input=json.dumps({"jwk": jwk, "token": signing.writer_token(str(pem_path),
                                                                    kid=jwk["kid"])}).encode(),
    )
    assert json.loads(checked.stdout) == {
        "curve": "prime256v1", "scalar_matches_point": True, "token_verifies": True,
    }


def test_generate_never_overwrites_and_leaves_the_key_untouched(key_folder: Path) -> None:
    before = {name: (key_folder / name).read_bytes() for name in (signing.PEM_NAME,
                                                                   signing.JWK_NAME)}
    with pytest.raises(signing.SigningKeyError, match="refusing to overwrite"):
        signing.generate(key_folder)
    assert {name: (key_folder / name).read_bytes() for name in before} == before


def test_a_failed_generate_removes_only_what_it_wrote(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "keys"
    write = signing._write_owner_only

    def a_jwk_appears_first(path: Path, data: bytes) -> None:
        if path.name == signing.JWK_NAME:
            path.write_text("someone else's file")
            raise FileExistsError(path)
        write(path, data)

    monkeypatch.setattr(signing, "_write_owner_only", a_jwk_appears_first)
    with pytest.raises(FileExistsError):
        signing.generate(folder)
    assert not (folder / signing.PEM_NAME).exists()
    assert (folder / signing.JWK_NAME).read_text() == "someone else's file"


def test_generate_closes_an_existing_folder_to_its_owner(tmp_path: Path) -> None:
    folder = tmp_path / "keys"
    folder.mkdir(mode=0o755)
    folder.chmod(0o755)
    signing.generate(folder)
    assert stat.S_IMODE(os.stat(folder).st_mode) == 0o700


def test_a_key_file_is_created_only_new_and_owner_only(tmp_path: Path) -> None:
    path = tmp_path / "secret"
    signing._write_owner_only(path, b"one")
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    with pytest.raises(FileExistsError):
        signing._write_owner_only(path, b"two")
    assert path.read_bytes() == b"one"


def test_the_key_folder_must_be_outside_the_repository() -> None:
    inside = signing.ROOT / ".work" / "ucpe-keys-never"
    with pytest.raises(signing.SigningKeyError, match="outside this repository"):
        signing.generate(inside)
    assert not inside.exists()
    with pytest.raises(signing.SigningKeyError, match="outside this repository"):
        signing.load(signing.ROOT)
    assert signing.KEY_DIR == Path.home() / "ucpe-keys"


def _rewrite(folder: Path, jwk: dict) -> None:
    (folder / signing.JWK_NAME).write_text(json.dumps(jwk, separators=(",", ":")) + "\n")


def test_two_different_keys_are_never_one(key_folder: Path, tmp_path: Path) -> None:
    other = tmp_path / "other"
    signing.generate(other)
    _rewrite(key_folder, _jwk(other))
    with pytest.raises(signing.SigningKeyError, match="are not the same key"):
        signing.load(key_folder)


def test_a_scalar_that_does_not_give_the_point_is_refused(key_folder: Path, monkeypatch) -> None:
    monkeypatch.setattr(signing, "public_of_scalar", lambda d: (b"\1" * 32, b"\2" * 32))
    with pytest.raises(signing.SigningKeyError, match="does not give its public point"):
        signing.load(key_folder)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda jwk: dict(reversed(list(jwk.items()))), "exactly the members"),
        (lambda jwk: {**jwk, "n": "AQAB"}, "exactly the members"),
        (lambda jwk: {name: value for name, value in jwk.items() if name != "use"},
         "exactly the members"),
        (lambda jwk: {**jwk, "kid": "ucpe-writer"}, "kid must be a lowercase UUID"),
        (lambda jwk: {**jwk, "kid": jwk["kid"].upper()}, "kid must be a lowercase UUID"),
        (lambda jwk: {**jwk, "ext": 1}, "ext must be true"),
        (lambda jwk: {**jwk, "alg": "RS256"}, 'alg must be "ES256"'),
        (lambda jwk: {**jwk, "key_ops": ["sign"]}, "key_ops must be"),
    ],
    ids=["reordered", "extra-member", "missing-member", "kid-not-uuid", "kid-uppercase",
         "ext-not-boolean", "alg", "key-ops"],
)
def test_a_jwk_that_is_not_the_cli_s_shape_is_refused(key_folder: Path, change, message) -> None:
    _rewrite(key_folder, change(_jwk(key_folder)))
    with pytest.raises(signing.SigningKeyError, match=message):
        signing.load(key_folder)


@pytest.mark.parametrize("name", [None, signing.PEM_NAME, signing.JWK_NAME])
def test_a_key_open_to_others_is_refused(key_folder: Path, name: str | None) -> None:
    (key_folder / name if name else key_folder).chmod(0o755 if name is None else 0o644)
    with pytest.raises(signing.SigningKeyError, match="open to others"):
        signing.load(key_folder)


def test_a_missing_key_says_run_generate(tmp_path: Path) -> None:
    with pytest.raises(signing.SigningKeyError, match="run generate first"):
        signing.load(tmp_path / "nothing-here")


def _sec1(d: bytes, *, version: bytes = b"\x01", curve: bytes = bytes.fromhex("2a8648ce3d030107"),
          point: bytes = b"\x00\x04" + b"\x05" * 64, trailing: bytes = b"") -> bytes:
    def element(tag: int, value: bytes) -> bytes:
        return bytes([tag, len(value)]) + value

    body = (element(0x02, version) + element(0x04, d) + element(0xA0, element(0x06, curve))
            + element(0xA1, element(0x03, point)))
    return element(0x30, body) + trailing


def test_a_short_scalar_is_left_padded_to_32_bytes() -> None:
    """RFC 5915 fixes d at 32 bytes; an older encoder may drop its leading zeros (1 key in 256)."""

    d, x, y = signing.sec1_material(_sec1(b"\x07" * 31))
    assert d == b"\x00" + b"\x07" * 31 and (x, y) == (b"\x05" * 32, b"\x05" * 32)


@pytest.mark.parametrize(
    "der",
    [
        _sec1(b"\x07" * 32, version=b"\x02"),
        _sec1(b"\x07" * 32, curve=bytes.fromhex("2b81040022")),
        _sec1(b"\x07" * 32, point=b"\x00\x02" + b"\x05" * 32),
        _sec1(b"\x07" * 33),
        _sec1(b""),
        _sec1(b"\x07" * 32, trailing=b"\x00"),
        _sec1(b"\x07" * 32)[:-1],
        b"",
    ],
    ids=["version", "not-p256", "compressed-point", "scalar-too-long", "scalar-empty",
         "trailing-bytes", "truncated", "empty"],
)
def test_anything_but_a_p256_sec1_key_is_refused(der: bytes) -> None:
    with pytest.raises(signing.SigningKeyError):
        signing.sec1_material(der)


def test_the_commands_print_the_kid_and_never_the_key_or_the_token(tmp_path: Path, capsys) -> None:
    folder = tmp_path / "ucpe-keys"
    clipboard: list[str] = []
    assert signing.main(["generate", "--dir", str(folder)], clipboard=clipboard.append) == 0
    assert signing.main(["copy-jwk", "--dir", str(folder)], clipboard=clipboard.append) == 0
    assert signing.main(["mint", "--dir", str(folder)], clipboard=clipboard.append) == 0
    printed = capsys.readouterr()
    jwk = _jwk(folder)
    pem_body = (folder / signing.PEM_NAME).read_text().splitlines()[1]
    jwk_copy, token = clipboard
    assert jwk_copy == (folder / signing.JWK_NAME).read_text(encoding="ascii")
    assert json.loads(_decode(token.split(".")[0]))["kid"] == jwk["kid"]
    assert printed.out.count(f"kid: {jwk['kid']}") == 3
    assert f"import file: {folder / signing.JWK_NAME}" in printed.out
    for secret in (jwk["d"], token, token.split(".")[2], pem_body, "PRIVATE KEY"):
        assert secret not in printed.out and secret not in printed.err


def test_without_pbcopy_the_token_is_never_printed_instead(
    key_folder: Path, capsys, monkeypatch
) -> None:
    class NoPbcopy:
        @staticmethod
        def run(arguments, **options):
            if arguments[0] == "pbcopy":
                raise FileNotFoundError("pbcopy")
            return subprocess.run(arguments, **options)

    monkeypatch.setattr(signing, "subprocess", NoPbcopy)
    assert signing.main(["mint", "--dir", str(key_folder)]) == 1
    printed = capsys.readouterr()
    assert "REFUSED: pbcopy (the macOS clipboard) is missing" in printed.err
    assert printed.out == ""


def test_a_refusal_never_carries_key_material(key_folder: Path, tmp_path: Path, capsys) -> None:
    other = tmp_path / "other"
    signing.generate(other)
    _rewrite(key_folder, _jwk(other))
    assert signing.main(["mint", "--dir", str(key_folder)], clipboard=lambda _: None) == 1
    printed = capsys.readouterr()
    assert "are not the same key" in printed.err
    for jwk in (_jwk(key_folder), _jwk(other)):
        assert jwk["d"] not in printed.err + printed.out
