"""Generate PBKDF2 access-code hashes for deployment secrets."""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from crypto_probability_engine.api.auth import pbkdf2_hash_code
from crypto_probability_engine.config.defaults import DEFAULT_PHASE1A


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a PBKDF2-HMAC-SHA256 access-code hash for APP_ACCESS_CODE_HASH "
            "or DEV_MODE_CODE_HASH. The plaintext code is never printed."
        )
    )
    parser.add_argument(
        "--name",
        choices=("APP_ACCESS_CODE_HASH", "DEV_MODE_CODE_HASH"),
        default="APP_ACCESS_CODE_HASH",
        help="Hugging Face Secret name to print with the generated hash.",
    )
    parser.add_argument(
        "--code-env",
        default="UCPE_ACCESS_CODE",
        help="Environment variable containing the plaintext code for non-interactive use.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=_configured_iterations(),
        help=(
            "PBKDF2 iteration count. Defaults to UCPE_ACCESS_CODE_PBKDF2_ITERATIONS "
            "or DEFAULT_PHASE1A."
        ),
    )
    args = parser.parse_args(argv)

    salt = os.environ.get("UCPE_ACCESS_CODE_SALT")
    if not salt:
        print(
            "ERROR: UCPE_ACCESS_CODE_SALT is required. Generate one with: "
            "python3 -c \"import secrets; print(secrets.token_urlsafe(24))\"",
            file=sys.stderr,
        )
        return 2
    if args.iterations <= 0:
        print("ERROR: iterations must be a positive integer.", file=sys.stderr)
        return 2

    code = os.environ.get(args.code_env)
    if code is None:
        if not sys.stdin.isatty():
            print(
                f"ERROR: no access code provided. Set {args.code_env} or run interactively.",
                file=sys.stderr,
            )
            return 2
        code = getpass.getpass("Access code (hidden): ")
    if not code:
        print("ERROR: access code must not be empty.", file=sys.stderr)
        return 2

    digest = pbkdf2_hash_code(code, salt=salt, iterations=args.iterations)
    print(f"{args.name}={digest}")
    return 0


def _configured_iterations() -> int:
    raw = os.environ.get("UCPE_ACCESS_CODE_PBKDF2_ITERATIONS")
    if raw is None:
        return DEFAULT_PHASE1A.access_code_pbkdf2_iterations
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_PHASE1A.access_code_pbkdf2_iterations


if __name__ == "__main__":
    raise SystemExit(main())
