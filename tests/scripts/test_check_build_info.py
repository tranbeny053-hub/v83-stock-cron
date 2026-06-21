from __future__ import annotations

import pytest

from crypto_probability_engine.config import build_info
from scripts import check_build_info


def _contract(**overrides) -> dict[str, str]:
    values = {
        "schema_version": build_info.SCHEMA_VERSION,
        "release_id": build_info.RELEASE_ID,
        "release_label": build_info.RELEASE_LABEL,
        "environment": build_info.ENVIRONMENT,
        "source_milestone": build_info.SOURCE_MILESTONE,
        "short_release_id": build_info.SHORT_RELEASE_ID,
        "fingerprint": build_info.FINGERPRINT,
    }
    values.update(overrides)
    return values


def test_current_build_info_contract_passes(capsys) -> None:
    assert check_build_info.main() == 0
    assert capsys.readouterr().out == "PASS: build information contract is valid.\n"


@pytest.mark.parametrize(
    "overrides",
    [
        {"release_id": ""},
        {
            "release_id": "UCPE-TODO-123",
            "short_release_id": "TODO-123",
            "fingerprint": "UCPE LIVE BUILD · TODO-123",
        },
        {"release_id": "invalid"},
        {"short_release_id": "MISMATCH"},
        {"fingerprint": "UCPE LIVE BUILD · MISMATCH"},
        {"schema_version": "build-info.v2"},
    ],
)
def test_invalid_build_info_contract_fails(overrides: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        check_build_info.validate_build_info(**_contract(**overrides))
