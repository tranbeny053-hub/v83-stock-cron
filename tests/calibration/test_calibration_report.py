from __future__ import annotations

import json

from scripts import calibration_report


def test_calibration_report_cli_json_smoke(capsys) -> None:
    result = calibration_report.main(["--timeframe", "15m", "--limit", "10"])
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert result == 0
    assert payload["status"] == "OK"
    assert payload["repository"] == "IN_MEMORY"
    assert payload["sample_gate"] == "NO_SAMPLES"
    assert payload["sample_count"] == 0


def test_calibration_report_operational_error_returns_nonzero(monkeypatch, capsys) -> None:
    def raise_error(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(calibration_report, "build_calibration_report", raise_error)

    result = calibration_report.main(["--format", "json"])
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert result == 1
    assert payload == {"error_type": "RuntimeError", "status": "ERROR"}
    assert "database unavailable" not in output

