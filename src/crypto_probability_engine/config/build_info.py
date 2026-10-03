"""Source-controlled runtime build fingerprint."""

SCHEMA_VERSION = "build-info.v1"
RELEASE_ID = "UCPE-PROD-WA-20261003-A"
RELEASE_LABEL = "PROD-WA release of main"
ENVIRONMENT = "HF_PRODUCTION"
SOURCE_MILESTONE = "prod-wa"

SHORT_RELEASE_ID = RELEASE_ID.removeprefix("UCPE-")
FINGERPRINT = f"UCPE LIVE BUILD · {SHORT_RELEASE_ID}"


def build_info_payload() -> dict[str, str]:
    """Return the deterministic public build contract."""

    return {
        "schema_version": SCHEMA_VERSION,
        "release_id": RELEASE_ID,
        "release_label": RELEASE_LABEL,
        "environment": ENVIRONMENT,
        "source_milestone": SOURCE_MILESTONE,
        "fingerprint": FINGERPRINT,
    }
