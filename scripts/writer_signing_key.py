"""E3: the owner's signing key for the least-privilege REST writer, and the writer's token.

Owner-only, on the owner's own Mac, run from the repository root. Supabase's documented path
(docs/runbooks/WRITER_CUTOVER.md): import your own private key as a JWK, rotate it in, then sign
ES256 tokens whose kid header is the imported key's kid. Three commands:

    .venv/bin/python -m scripts.writer_signing_key generate
    .venv/bin/python -m scripts.writer_signing_key copy-jwk
    .venv/bin/python -m scripts.writer_signing_key mint

- generate: OpenSSL makes one P-256 key. It is written twice, in ~/ucpe-keys and never inside this
  repository, each file owner-only (0600) in an owner-only folder (0700):
  - ucpe-writer-signing.pem, the key OpenSSL signs with;
  - ucpe-writer-signing.jwk.json, the same key as the private JWK that the dashboard imports. Its
    members, their order and its compact JSON are exactly what `supabase gen signing-key
    --algorithm ES256` prints: kty, kid, use, key_ops, alg, ext, d, crv, x, y. Its kid is a random
    UUID, which the Management API requires of an imported key.
  It refuses to overwrite, and prints only the kid and the two paths.
- copy-jwk: checks the two files are one key, then copies the private JWK to the clipboard, for
  the dashboard's import box.
- mint: checks the two files are one key, then signs the writer token from the PEM, with the JWK's
  kid in its header: role ucpe_api_writer, iat, and exp 30 days later (E3-B). It has no sub. The
  token goes to the clipboard.

"One key" is checked three ways: the JWK's d, x and y are the PEM's own, and OpenSSL, given the
JWK's d alone, computes the JWK's public point. Nothing secret is ever printed: not the key, not
the token. The clipboard is macOS's pbcopy; without it the command refuses rather than print.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from scripts.privilege_rehearsal import es256

ROOT = Path(__file__).resolve().parents[1]
KEY_DIR = Path.home() / "ucpe-keys"
PEM_NAME = "ucpe-writer-signing.pem"
JWK_NAME = "ucpe-writer-signing.jwk.json"
ROLE = "ucpe_api_writer"
LIFETIME = 30 * 24 * 60 * 60  # E3-B, the owner's ruling: 30 days.
# `supabase gen signing-key --algorithm ES256` (the CLI's signing-key.handler.ts), member for
# member and in its order.
JWK_MEMBERS = ("kty", "kid", "use", "key_ops", "alg", "ext", "d", "crv", "x", "y")
_CONSTANTS: dict[str, Any] = {
    "kty": "EC", "use": "sig", "key_ops": ["sign", "verify"], "alg": "ES256", "ext": True,
    "crv": "P-256",
}
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_P256_OID = bytes.fromhex("2a8648ce3d030107")  # 1.2.840.10045.3.1.7, prime256v1
_COORDINATE = 32


class SigningKeyError(Exception):
    """A refusal. Its message never carries key material."""


def _element(der: bytes, index: int, tag: int) -> tuple[bytes, int]:
    """The DER element at index, which must carry tag: its value and the index after it. A P-256
    SEC1 key is 121 bytes, so every length is short-form."""

    if index + 2 > len(der) or der[index] != tag or der[index + 1] & 0x80:
        raise SigningKeyError("the key is not a P-256 SEC1 private key")
    end = index + 2 + der[index + 1]
    if end > len(der):
        raise SigningKeyError("the key is not a P-256 SEC1 private key")
    return der[index + 2:end], end


def key_material(pem: bytes) -> tuple[bytes, bytes, bytes]:
    """The private scalar d and the public point (x, y), 32 bytes each, of one SEC1 key."""

    return sec1_material(subprocess.run(
        ["openssl", "ec", "-outform", "DER"], input=pem, capture_output=True, check=True,
    ).stdout)


def sec1_material(der: bytes) -> tuple[bytes, bytes, bytes]:
    """RFC 5915: SEQUENCE { INTEGER 1, OCTET STRING d, [0] the curve's OID, [1] BIT STRING point },
    for P-256 only."""

    body, end = _element(der, 0, 0x30)
    version, index = _element(body, 0, 0x02)
    scalar, index = _element(body, index, 0x04)
    parameters, index = _element(body, index, 0xA0)
    public, index = _element(body, index, 0xA1)
    curve, curve_end = _element(parameters, 0, 0x06)
    point, point_end = _element(public, 0, 0x03)
    if (end, index, curve_end, point_end) != (len(der), len(body), len(parameters), len(public)):
        raise SigningKeyError("the key is not a P-256 SEC1 private key")
    if version != b"\x01" or curve != _P256_OID or not 0 < len(scalar) <= _COORDINATE:
        raise SigningKeyError("the key is not a P-256 SEC1 private key")
    if len(point) != 2 + 2 * _COORDINATE or point[:2] != b"\x00\x04":
        raise SigningKeyError("the key is not a P-256 SEC1 private key")
    # RFC 5915 fixes d at 32 bytes; an older encoder may have dropped its leading zeros.
    d = scalar.rjust(_COORDINATE, b"\0")
    return d, point[2:2 + _COORDINATE], point[2 + _COORDINATE:]


def public_of_scalar(d: bytes) -> tuple[bytes, bytes]:
    """The public point that OpenSSL computes from d alone: a SEC1 key without its point."""

    body = (b"\x02\x01\x01" + b"\x04" + bytes([len(d)]) + d
            + b"\xa0\x0a\x06\x08" + _P256_OID)
    der = subprocess.run(
        ["openssl", "ec", "-inform", "DER", "-pubout", "-outform", "DER"],
        input=b"\x30" + bytes([len(body)]) + body, capture_output=True, check=True,
    ).stdout
    point = der[-(1 + 2 * _COORDINATE):]
    if len(point) != 1 + 2 * _COORDINATE or point[0] != 0x04:
        raise SigningKeyError("OpenSSL did not compute an uncompressed P-256 point")
    return point[1:1 + _COORDINATE], point[1 + _COORDINATE:]


def private_jwk(d: bytes, x: bytes, y: bytes, kid: str) -> dict[str, Any]:
    """The key as `supabase gen signing-key --algorithm ES256` prints it."""

    return {
        "kty": "EC", "kid": kid, "use": "sig", "key_ops": ["sign", "verify"], "alg": "ES256",
        "ext": True, "d": es256.b64url(d), "crv": "P-256", "x": es256.b64url(x),
        "y": es256.b64url(y),
    }


def jwk_text(jwk: dict[str, Any]) -> str:
    """Compact JSON and a newline, as the CLI prints one key."""

    return json.dumps(jwk, separators=(",", ":")) + "\n"


def _key_folder(directory: Path) -> Path:
    folder = directory.expanduser().resolve()
    if folder == ROOT or ROOT in folder.parents:
        raise SigningKeyError(f"the key folder must be outside this repository, not {folder}")
    return folder


def _owner_only(path: Path) -> None:
    if path.stat().st_mode & 0o077:
        raise SigningKeyError(f"{path} is open to others: chmod 600 the files, 700 the folder")


def _write_owner_only(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(data)


def load(directory: Path = KEY_DIR) -> tuple[Path, dict[str, Any]]:
    """The PEM's path and the private JWK, once proven to be one key, as generate wrote them."""

    folder = _key_folder(directory)
    pem_path, jwk_path = folder / PEM_NAME, folder / JWK_NAME
    for path in (folder, pem_path, jwk_path):
        if not path.exists():
            raise SigningKeyError(f"{path} is missing: run generate first")
        _owner_only(path)
    try:
        jwk = json.loads(jwk_path.read_text(encoding="ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SigningKeyError(f"{JWK_NAME} is not JSON") from None
    if not isinstance(jwk, dict) or tuple(jwk) != JWK_MEMBERS:
        raise SigningKeyError(f"{JWK_NAME} must have exactly the members {', '.join(JWK_MEMBERS)}")
    for name, value in _CONSTANTS.items():
        if type(jwk[name]) is not type(value) or jwk[name] != value:
            raise SigningKeyError(f"{JWK_NAME}: {name} must be {json.dumps(value)}")
    if not isinstance(jwk["kid"], str) or not _UUID.fullmatch(jwk["kid"]):
        raise SigningKeyError(f"{JWK_NAME}: kid must be a lowercase UUID")
    d, x, y = key_material(pem_path.read_bytes())
    if [jwk["d"], jwk["x"], jwk["y"]] != [es256.b64url(part) for part in (d, x, y)]:
        raise SigningKeyError(f"{JWK_NAME} and {PEM_NAME} are not the same key")
    if public_of_scalar(d) != (x, y):
        raise SigningKeyError(f"the private scalar in {JWK_NAME} does not give its public point")
    return pem_path, jwk


def generate(directory: Path = KEY_DIR) -> dict[str, str]:
    """One new key, written as the PEM and as the importable private JWK. Never overwrites."""

    folder = _key_folder(directory)
    pem_path, jwk_path = folder / PEM_NAME, folder / JWK_NAME
    existing = [path.name for path in (pem_path, jwk_path) if path.exists()]
    if existing:
        raise SigningKeyError(f"refusing to overwrite {', '.join(existing)} in {folder}")
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    folder.chmod(0o700)
    pem = subprocess.run(
        ["openssl", "ecparam", "-name", "prime256v1", "-genkey", "-noout"],
        capture_output=True, check=True,
    ).stdout
    d, x, y = key_material(pem)
    jwk = private_jwk(d, x, y, str(uuid.uuid4()))
    written: list[Path] = []
    try:
        for path, data in ((pem_path, pem), (jwk_path, jwk_text(jwk).encode("ascii"))):
            _write_owner_only(path, data)
            written.append(path)
        load(folder)
    except BaseException:
        # Only what this call wrote: a half-made key must not stay behind.
        for path in written:
            path.unlink(missing_ok=True)
        raise
    return {"kid": jwk["kid"], "pem": str(pem_path), "jwk": str(jwk_path)}


def writer_token(key_file: str, *, kid: str, now: int | None = None) -> str:
    """The writer's token, as J1 mints it behind a real PostgREST: ES256 with the kid header;
    role ucpe_api_writer, iat, and exp 30 days later; no sub."""

    return es256.mint(key_file, ROLE, kid=kid, now=now, lifetime=LIFETIME)


def pbcopy(text: str) -> None:
    """macOS's clipboard. Without it, refuse: a secret is never printed instead."""

    try:
        subprocess.run(["pbcopy"], input=text.encode("ascii"), check=True)
    except FileNotFoundError:
        raise SigningKeyError(
            "pbcopy (the macOS clipboard) is missing; nothing was copied"
        ) from None


def main(argv: Sequence[str] | None = None, *, clipboard: Callable[[str], None] = pbcopy) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.writer_signing_key",
        description="E3: the owner's writer signing key (generate, copy-jwk) and token (mint).",
    )
    parser.add_argument("command", choices=("generate", "copy-jwk", "mint"))
    parser.add_argument("--dir", type=Path, default=KEY_DIR,
                        help="the key folder, outside this repository (default: ~/ucpe-keys)")
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "generate":
            made = generate(arguments.dir)
            print(f"kid: {made['kid']}")
            print(f"import file: {made['jwk']}")
            print(f"signing key: {made['pem']}")
            print("Both files are secret: never in a repository, a chat, GitHub or the Space.")
        elif arguments.command == "copy-jwk":
            _, jwk = load(arguments.dir)
            clipboard(jwk_text(jwk))
            print(f"kid: {jwk['kid']}")
            print("The private JWK is on the clipboard, for the dashboard's import box.")
        else:
            pem_path, jwk = load(arguments.dir)
            issued = int(time.time())
            clipboard(writer_token(str(pem_path), kid=jwk["kid"], now=issued))
            expiry = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(issued + LIFETIME))
            print(f"kid: {jwk['kid']}")
            print(f"role: {ROLE}")
            print(f"expires: {expiry}")
            print("The writer token is on the clipboard, for the Space secret SUPABASE_WRITER_JWT.")
    except SigningKeyError as refusal:
        print(f"REFUSED: {refusal}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
