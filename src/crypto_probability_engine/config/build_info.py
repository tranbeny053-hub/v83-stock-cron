"""Source-controlled runtime build fingerprint."""

SCHEMA_VERSION = "build-info.v1"
RELEASE_ID = "UCPE-W4C1-KA1-20260621-A"
RELEASE_LABEL = "Wave 4C.1 + Ops-KA.1 Runtime Fingerprint"
ENVIRONMENT = "HF_PRODUCTION"
SOURCE_MILESTONE = "wave-4c1-quant-v2-shadow-contract"

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
