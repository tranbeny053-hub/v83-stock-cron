from __future__ import annotations

import json

from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.persistence import repository as repository_module
from scripts import calibration_report


def test_calibration_report_cli_json_smoke(monkeypatch, capsys) -> None:
    _clear_repository_env(monkeypatch)

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


def test_calibration_report_prefers_postgres_when_rest_secrets_also_exist(
    monkeypatch,
    capsys,
) -> None:
    class FakePostgresRepository:
        def __init__(self, db_url: str) -> None:
            self.db_url = db_url

        def repository_type(self) -> str:
            return "SUPABASE_POSTGRES"

        def fetch_resolved_prediction_outcomes_for_calibration(self, **kwargs) -> list[dict]:
            return []

        def close(self) -> None:
            pass

    class ExplodingRestRepository:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("REST repository must not be selected when DB URL exists")

    monkeypatch.setattr(repository_module, "SupabasePersistenceRepository", FakePostgresRepository)
    monkeypatch.setattr(repository_module, "SupabaseRestRepository", ExplodingRestRepository)
    monkeypatch.setattr(
        calibration_report.Settings,
        "from_env",
        lambda: Settings(
            **{
                "supabase_db_url": "postgresql://example.invalid/db",
                "supabase_url": "https://project.example.supabase.co",
                "supabase_service_role_key": "test-service-role-key",
            }
        ),
    )

    result = calibration_report.main(["--timeframe", "15m", "--limit", "10"])
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert result == 0
    assert payload["repository"] == "SUPABASE_POSTGRES"
    assert payload["sample_gate"] == "NO_SAMPLES"


def _clear_repository_env(monkeypatch) -> None:
    for name in ("SUPABASE_DB_URL", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"):
        monkeypatch.delenv(name, raising=False)
