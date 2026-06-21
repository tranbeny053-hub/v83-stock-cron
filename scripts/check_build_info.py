"""Validate the source-controlled runtime build fingerprint contract."""

from __future__ import annotations

import re

from crypto_probability_engine.config.build_info import (
    ENVIRONMENT,
    FINGERPRINT,
    RELEASE_ID,
    RELEASE_LABEL,
    SCHEMA_VERSION,
    SHORT_RELEASE_ID,
    SOURCE_MILESTONE,
)

RELEASE_ID_PATTERN = re.compile(r"^UCPE-[A-Z0-9-]{3,}$")
PLACEHOLDER_MARKERS = ("PLACEHOLDER", "TODO", "DEFAULT", "CHANGEME", "UNKNOWN")


def validate_build_info(
    *,
    schema_version: str,
    release_id: str,
    release_label: str,
    environment: str,
    source_milestone: str,
    short_release_id: str,
    fingerprint: str,
) -> None:
    """Raise ValueError when the release contract is invalid."""

    required = {
        "release_id": release_id,
        "release_label": release_label,
        "environment": environment,
        "source_milestone": source_milestone,
        "fingerprint": fingerprint,
    }
    if any(not isinstance(value, str) or not value.strip() for value in required.values()):
        raise ValueError("Required build information is empty.")
    if schema_version != "build-info.v1":
        raise ValueError("Build information schema version is invalid.")
    if not RELEASE_ID_PATTERN.fullmatch(release_id):
        raise ValueError("Release ID format is invalid.")
    upper_release_id = release_id.upper()
    if any(marker in upper_release_id for marker in PLACEHOLDER_MARKERS):
        raise ValueError("Release ID contains a placeholder marker.")
    expected_short_id = release_id.removeprefix("UCPE-")
    if short_release_id != expected_short_id:
        raise ValueError("Short release ID does not match the release ID.")
    if fingerprint != f"UCPE LIVE BUILD · {short_release_id}":
        raise ValueError("Build fingerprint does not match the short release ID.")


def main() -> int:
    validate_build_info(
        schema_version=SCHEMA_VERSION,
        release_id=RELEASE_ID,
        release_label=RELEASE_LABEL,
        environment=ENVIRONMENT,
        source_milestone=SOURCE_MILESTONE,
        short_release_id=SHORT_RELEASE_ID,
        fingerprint=FINGERPRINT,
    )
    print("PASS: build information contract is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
