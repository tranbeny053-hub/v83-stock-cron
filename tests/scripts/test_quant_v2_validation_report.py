from __future__ import annotations

import json

import pytest

from scripts import quant_v2_validation_report as cli
from tests.shadow_validation.conftest import ReadOnlyRepository, make_validation_row


def test_cli_json_is_deterministic_private_bounded_and_closes_repository(
    monkeypatch,
    capsys,
) -> None:
    repository = ReadOnlyRepository([make_validation_row(1)])
    monkeypatch.setattr(cli, "build_operator_repository", lambda settings: repository)

    result = cli.main(
        [
            "--generated-at-utc",
            "2026-06-21T00:00:00Z",
            "--limit",
            "50001",
            "--format",
            "json",
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["report_schema_version"] == "quant-v2-validation.v0"
    assert payload["data_window"]["row_limit"] == 50_000
    assert "snapshot_payload" not in json.dumps(payload)
    assert repository.closed is True
    row_call = next(call for call in repository.calls if call[0] == "rows")
    assert row_call[1]["limit"] == 50_000


def test_cli_text_is_compact_and_never_opens_holdout(monkeypatch, capsys) -> None:
    repository = ReadOnlyRepository([])
    monkeypatch.setattr(cli, "build_operator_repository", lambda settings: repository)

    result = cli.main(
        [
            "--generated-at-utc",
            "2026-06-21T00:00:00Z",
            "--format",
            "text",
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "holdout_status: SEALED_NOT_EVALUATED" in output
    assert "promotion_eligible: false" in output
    assert "snapshot_payload" not in output


def test_cli_has_no_holdout_option() -> None:
    with pytest.raises(SystemExit):
        cli.main(["--holdout", "open"])
