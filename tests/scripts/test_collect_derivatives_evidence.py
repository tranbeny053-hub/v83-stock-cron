from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts import collect_derivatives_evidence as collector

ROOT = Path(__file__).resolve().parents[2]
FIXED_NOW = datetime(2026, 6, 22, 12, 0, tzinfo=UTC)


class _Monotonic:
    def __init__(self) -> None:
        self.value = 50.0

    def __call__(self) -> float:
        self.value += 0.25
        return self.value


class _FixtureRuntime:
    def __init__(
        self,
        *,
        provider_status: str = "ACTIVE",
        persist_result: dict[str, object] | None = None,
        fail_symbols: set[str] | None = None,
    ) -> None:
        self.provider_status = provider_status
        self.persist_result = persist_result or {
            "prediction": "OK",
            "feature_snapshot": "INSERTED",
            "derivatives_snapshot": "INSERTED",
            "overall": "OK",
        }
        self.fail_symbols = fail_symbols or set()
        self.analysis_calls: list[dict[str, object]] = []
        self.persist_calls: list[tuple[dict, object]] = []
        self.repository_calls: list[object] = []
        self.pending: dict[str, dict] = {}
        self.repository = object()

    def analyze(self, request, **kwargs) -> dict:
        self.analysis_calls.append({"request": request, **kwargs})
        if request.symbol in self.fail_symbols:
            raise RuntimeError("credential=must-not-leak")
        digest = hashlib.sha256(
            f"{request.symbol}|{request.timeframe}".encode()
        ).hexdigest()[:32]
        run_id = f"cadence-{digest}"
        prediction_id = f"{run_id}:{request.timeframe}"
        payload = {
            "run_id": run_id,
            "normalized_symbol": request.symbol.replace("/", ""),
            "probability_state": {"p": 1.0},
            "score_stack": {"score": 0.0},
            "gate_result": {"action": "NO_TRADE"},
            "decision_synthesis": {
                "future_quant_v2_hooks": {"decision_influence_frac": 0.0}
            },
            "derivatives_intelligence": {
                "methodology_version": collector.DERIVATIVES_METHODOLOGY,
                "influence_mode": "SHADOW_ONLY",
                "decision_influence_frac": 0.0,
                "block_status": self.provider_status,
            },
        }
        self.pending[run_id] = {
            "prediction_id": prediction_id,
            "run_id": run_id,
            "symbol": request.symbol,
            "normalized_symbol": payload["normalized_symbol"],
            "timeframe": request.timeframe,
            "reference_close_utc": "2026-06-22T08:00:00Z",
            "prediction_origin": kwargs["prediction_origin"],
        }
        return payload

    def inspect(self, payload: dict):
        row = self.pending.get(payload.get("run_id"))
        return ([row] if row else [], [], False, [], False)

    def persist(self, payload: dict, repository: object) -> dict[str, object]:
        self.persist_calls.append((payload, repository))
        return dict(self.persist_result)

    def build_repository(self, settings) -> object:
        self.repository_calls.append(settings)
        return self.repository

    def dependencies(self) -> collector.CollectorDependencies:
        return collector.CollectorDependencies(
            analyze=self.analyze,
            persist=self.persist,
            inspect_pending=self.inspect,
            repository_factory=self.build_repository,
            now_utc=lambda: FIXED_NOW,
            monotonic=_Monotonic(),
        )


class _NoDatabaseRead(dict):
    def get(self, key, default=None):
        if key == "SUPABASE_DB_URL":
            raise AssertionError("disabled/dry-run path read the database URL")
        return super().get(key, default)


def _run(
    runtime: _FixtureRuntime,
    *,
    enabled: str = "true",
    dry_run: bool = True,
    confirm: str = "",
    scope: str = "BTC_ONLY",
    database_url: str | None = None,
) -> dict:
    environ = {collector.ENABLE_ENV: enabled}
    if database_url is not None:
        environ["SUPABASE_DB_URL"] = database_url
    return collector.run_collector(
        collector.CollectorOptions(
            dry_run=dry_run,
            confirm_write=confirm,
            matrix_scope=scope,
        ),
        environ=environ,
        dependencies=runtime.dependencies(),
    )


@pytest.mark.parametrize("raw", [None, "", "false", "FALSE"])
def test_kill_switch_disabled_has_zero_runtime_or_repository_activity(raw) -> None:
    runtime = _FixtureRuntime()
    environ = _NoDatabaseRead()
    if raw is not None:
        environ[collector.ENABLE_ENV] = raw

    report = collector.run_collector(
        collector.CollectorOptions(),
        environ=environ,
        dependencies=runtime.dependencies(),
    )

    assert report["final_classification"] == "DISABLED"
    assert report["exit_code"] == 0
    assert all(row["classification"] == "SKIPPED_DISABLED" for row in report["matrix_cells"])
    assert runtime.analysis_calls == []
    assert runtime.persist_calls == []
    assert runtime.repository_calls == []


def test_invalid_kill_switch_fails_closed_without_dependencies() -> None:
    runtime = _FixtureRuntime()
    report = _run(runtime, enabled="yes")

    assert report["final_classification"] == "CONFIGURATION_ERROR"
    assert report["exit_code"] == 1
    assert runtime.analysis_calls == runtime.repository_calls == []


def test_cli_defaults_and_boolean_parser_are_strict() -> None:
    options = collector.parse_args([])
    assert options == collector.CollectorOptions()
    assert collector.parse_bool("true") is True
    assert collector.parse_bool("false") is False
    for invalid in ("1", " true ", "yes"):
        with pytest.raises(argparse.ArgumentTypeError):
            collector.parse_bool(invalid)


def test_enabled_dry_run_uses_process_local_settings_and_zero_persistence() -> None:
    runtime = _FixtureRuntime()
    before = dict(os.environ)
    report = collector.run_collector(
        collector.CollectorOptions(dry_run=True, matrix_scope="BTC_ONLY"),
        environ=_NoDatabaseRead({collector.ENABLE_ENV: "true"}),
        dependencies=runtime.dependencies(),
    )

    assert report["final_classification"] == "DRY_RUN_COMPLETE"
    assert [row["classification"] for row in report["matrix_cells"]] == [
        "SKIPPED_DRY_RUN",
        "SKIPPED_DRY_RUN",
    ]
    assert runtime.repository_calls == []
    assert runtime.persist_calls == []
    assert all(call["settings"].data_mode == "live" for call in runtime.analysis_calls)
    assert all(
        call["settings"].enable_derivatives_intel is True
        for call in runtime.analysis_calls
    )
    assert all(
        call["prediction_origin"] == collector.SCHEDULED_ORIGIN
        for call in runtime.analysis_calls
    )
    assert all(call["deterministic_identity"] is True for call in runtime.analysis_calls)
    assert dict(os.environ) == before


@pytest.mark.parametrize(
    ("confirm", "database_url", "classification"),
    [
        ("", "postgresql://fixture", "CONFIRMATION_REQUIRED"),
        ("wrong", "postgresql://fixture", "CONFIRMATION_REQUIRED"),
        (collector.WRITE_CONFIRMATION, None, "CONFIGURATION_ERROR"),
    ],
)
def test_write_gate_fails_before_provider_or_repository_activity(
    confirm: str,
    database_url: str | None,
    classification: str,
) -> None:
    runtime = _FixtureRuntime()
    report = _run(
        runtime,
        dry_run=False,
        confirm=confirm,
        database_url=database_url,
    )

    assert report["final_classification"] == classification
    assert report["exit_code"] == 1
    assert runtime.analysis_calls == runtime.repository_calls == []


def test_fixed_scopes_order_and_circuit_breakers(monkeypatch) -> None:
    assert collector._validated_cells("FULL_4_CELL") == collector.MATRIX  # noqa: SLF001
    assert collector._validated_cells("BTC_ONLY") == collector.MATRIX[:2]  # noqa: SLF001
    assert collector._validated_cells("ETH_ONLY") == collector.MATRIX[2:]  # noqa: SLF001
    with pytest.raises(ValueError):
        collector._validated_cells("SOL_ONLY")  # noqa: SLF001
    monkeypatch.setitem(
        collector.MATRIX_SCOPES,
        "TOO_LARGE",
        (*collector.MATRIX, ("BTC/USDT", "1H")),
    )
    with pytest.raises(ValueError):
        collector._validated_cells("TOO_LARGE")  # noqa: SLF001
    monkeypatch.setitem(
        collector.MATRIX_SCOPES,
        "DUPLICATE",
        (("BTC/USDT", "1H"), ("BTC/USDT", "1H")),
    )
    with pytest.raises(ValueError):
        collector._validated_cells("DUPLICATE")  # noqa: SLF001
    monkeypatch.setitem(collector.MATRIX_SCOPES, "BAD_CELL", (("SOL/USDT", "1H"),))
    with pytest.raises(ValueError):
        collector._validated_cells("BAD_CELL")  # noqa: SLF001


def test_deterministic_identity_and_pending_origin_are_required_before_persistence() -> None:
    runtime = _FixtureRuntime()
    valid = _run(
        runtime,
        dry_run=False,
        confirm=collector.WRITE_CONFIRMATION,
        scope="BTC_ONLY",
        database_url="postgresql://fixture",
    )
    assert all(collector.RUN_ID_PATTERN.fullmatch(row["run_id"]) for row in valid["matrix_cells"])
    assert all(
        row["prediction_id"] == f"{row['run_id']}:{row['timeframe']}"
        for row in valid["matrix_cells"]
    )
    assert len(runtime.persist_calls) == 2

    invalid_runtime = _FixtureRuntime()

    def invalid_analyze(*args, **kwargs):
        payload = invalid_runtime.analyze(*args, **kwargs)
        payload["run_id"] = "run_not_cadence"
        return payload

    deps = replace(invalid_runtime.dependencies(), analyze=invalid_analyze)
    report = collector.run_collector(
        collector.CollectorOptions(
            dry_run=False,
            confirm_write=collector.WRITE_CONFIRMATION,
            matrix_scope="BTC_ONLY",
        ),
        environ={collector.ENABLE_ENV: "true", "SUPABASE_DB_URL": "postgresql://fixture"},
        dependencies=deps,
    )
    assert all(
        row["classification"] == "SKIPPED_REFERENCE_UNCERTAIN"
        for row in report["matrix_cells"]
    )
    assert invalid_runtime.persist_calls == []


def test_safety_invariant_failure_prevents_persistence() -> None:
    runtime = _FixtureRuntime()

    def unsafe_analyze(*args, **kwargs):
        payload = runtime.analyze(*args, **kwargs)
        payload["derivatives_intelligence"]["decision_influence_frac"] = 0.1
        return payload

    report = collector.run_collector(
        collector.CollectorOptions(
            dry_run=False,
            confirm_write=collector.WRITE_CONFIRMATION,
            matrix_scope="BTC_ONLY",
        ),
        environ={collector.ENABLE_ENV: "true", "SUPABASE_DB_URL": "postgresql://fixture"},
        dependencies=replace(runtime.dependencies(), analyze=unsafe_analyze),
    )

    assert report["final_classification"] == "FAILED_SAFETY_INVARIANT"
    assert runtime.persist_calls == []


@pytest.mark.parametrize(
    ("persist_result", "expected", "final", "exit_code"),
    [
        (
            {
                "prediction": "OK",
                "feature_snapshot": "INSERTED",
                "derivatives_snapshot": "INSERTED",
                "overall": "OK",
            },
            "INSERTED",
            "COMPLETE",
            0,
        ),
        (
            {
                "prediction": "OK",
                "feature_snapshot": "IDENTICAL_DUPLICATE",
                "derivatives_snapshot": "IDENTICAL_DUPLICATE",
                "overall": "OK",
            },
            "ALREADY_EXISTS",
            "COMPLETE",
            0,
        ),
        (
            {
                "prediction": "OK",
                "feature_snapshot": "INSERTED",
                "derivatives_snapshot": "CONFLICT",
                "overall": "PARTIAL",
            },
            "PARTIAL_PERSISTENCE",
            "PARTIAL_PERSISTENCE",
            1,
        ),
        (
            {
                "prediction": "UNAVAILABLE",
                "feature_snapshot": None,
                "derivatives_snapshot": None,
                "overall": "UNAVAILABLE",
            },
            "FAILED",
            "FAILED",
            1,
        ),
    ],
)
def test_persistence_status_classification(
    persist_result: dict[str, object],
    expected: str,
    final: str,
    exit_code: int,
) -> None:
    runtime = _FixtureRuntime(persist_result=persist_result)
    report = _run(
        runtime,
        dry_run=False,
        confirm=collector.WRITE_CONFIRMATION,
        database_url="postgresql://fixture",
    )

    assert all(row["classification"] == expected for row in report["matrix_cells"])
    assert report["final_classification"] == final
    assert report["exit_code"] == exit_code
    assert len(runtime.persist_calls) == 2


def test_degraded_and_unavailable_provider_states_remain_separate() -> None:
    degraded = _run(
        _FixtureRuntime(provider_status="DEGRADED"),
        dry_run=False,
        confirm=collector.WRITE_CONFIRMATION,
        database_url="postgresql://fixture",
    )
    assert degraded["final_classification"] == "COMPLETE_WITH_DEGRADED_PROVIDER"
    assert all(row["classification"] == "INSERTED" for row in degraded["matrix_cells"])
    assert all(row["provider_status"] == "DEGRADED" for row in degraded["matrix_cells"])

    unavailable_runtime = _FixtureRuntime(provider_status="UNAVAILABLE")
    unavailable = _run(
        unavailable_runtime,
        dry_run=False,
        confirm=collector.WRITE_CONFIRMATION,
        database_url="postgresql://fixture",
    )
    assert unavailable["final_classification"] == "FAILED"
    assert all(
        row["classification"] == "PROVIDER_UNAVAILABLE"
        for row in unavailable["matrix_cells"]
    )
    assert all(
        row["derivatives_snapshot_status"] == "INSERTED"
        for row in unavailable["matrix_cells"]
    )


def test_one_cell_failure_is_sanitized_and_later_cell_runs() -> None:
    runtime = _FixtureRuntime(fail_symbols={"BTC/USDT"})
    report = _run(runtime, scope="FULL_4_CELL")

    assert [row["classification"] for row in report["matrix_cells"]] == [
        "FAILED",
        "FAILED",
        "SKIPPED_DRY_RUN",
        "SKIPPED_DRY_RUN",
    ]
    assert report["exit_code"] == 1
    encoded = json.dumps(report)
    assert "must-not-leak" not in encoded
    assert "credential=" not in encoded


def test_output_allowlist_and_single_json_stdout(monkeypatch, capsys) -> None:
    monkeypatch.delenv(collector.ENABLE_ENV, raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    exit_code = collector.main([])
    output = capsys.readouterr().out.strip()
    report = json.loads(output)

    assert exit_code == 0
    assert set(report) == collector.REPORT_FIELDS
    assert all(set(row) == collector.CELL_RESULT_FIELDS for row in report["matrix_cells"])
    assert output.count("{") >= 1
    assert "SUPABASE" not in output


def test_step_summary_is_allowlisted(tmp_path) -> None:
    path = tmp_path / "summary.md"
    report = _run(_FixtureRuntime())
    collector.append_step_summary(str(path), report)
    text = path.read_text()

    assert "DRY_RUN_COMPLETE" in text
    assert "SUPABASE" not in text
    assert "postgres" not in text.lower()


def test_provider_call_ceiling_matches_current_bounded_adapter_policy() -> None:
    assert collector.FULL_MATRIX_LOGICAL_REQUEST_CAP == 58
    assert collector.FULL_MATRIX_HTTP_ATTEMPT_CAP == 98
    assert collector.MAX_MATRIX_CELLS == 4
    assert collector.MAX_NEW_PREDICTIONS == 4
    assert collector.MAX_NEW_DERIVATIVES_SNAPSHOTS == 4


def test_observed_insert_cap_breach_stops_subsequent_cells(monkeypatch) -> None:
    runtime = _FixtureRuntime()
    monkeypatch.setattr(collector, "MAX_NEW_PREDICTIONS", 0)
    report = _run(
        runtime,
        dry_run=False,
        confirm=collector.WRITE_CONFIRMATION,
        scope="FULL_4_CELL",
        database_url="postgresql://fixture",
    )

    assert report["cap_status"] == "BREACHED"
    assert report["exit_code"] == 1
    assert len(report["matrix_cells"]) == 1
    assert len(runtime.analysis_calls) == 1


def test_collector_source_uses_only_approved_persistence_entrypoint() -> None:
    source = (ROOT / "scripts/collect_derivatives_evidence.py").read_text()
    assert "persist_analysis_now" in source
    assert ".save_prediction(" not in source
    assert ".save_feature_snapshot(" not in source
    assert ".save_derivatives_snapshot(" not in source
    assert "INSERT INTO" not in source
    assert "/v1/analyze" not in source


def test_manual_workflow_contract_and_existing_integrity_workflow_unchanged() -> None:
    path = ROOT / ".github/workflows/derivatives-evidence-cadence.yml"
    text = path.read_text()
    assert text.startswith("name: UCPE Derivatives Evidence Collector\n")
    assert "workflow_dispatch:" in text
    assert "schedule:" not in text
    assert "cron:" not in text
    assert "actions/checkout@v4" in text
    assert "actions/setup-python@v5" in text
    assert 'python-version: "3.11"' in text
    assert "group: derivatives-evidence-cadence" in text
    assert "cancel-in-progress: false" in text
    assert "timeout-minutes: 15" in text
    assert "contents: read" in text
    for name in ("enable_collector", "dry_run", "matrix_scope", "confirm_write"):
        assert f"      {name}:\n" in text
    assert re.search(
        r"enable_collector:\n(?: {8}.+\n)*? {8}type: boolean\n"
        r"(?: {8}.+\n)*? {8}default: false\n",
        text,
    )
    assert re.search(
        r"dry_run:\n(?: {8}.+\n)*? {8}type: boolean\n"
        r"(?: {8}.+\n)*? {8}default: true\n",
        text,
    )
    for option in ("FULL_4_CELL", "BTC_ONLY", "ETH_ONLY"):
        assert f"          - {option}\n" in text
    assert '        default: ""\n' in text
    assert "UCPE_DERIV_CADENCE_ENABLED: ${{ inputs.enable_collector }}" in text
    assert "SUPABASE_DB_URL: ${{ secrets.SUPABASE_DB_URL }}" in text
    assert "HF_TOKEN" not in text
    assert "Authorization" not in text

    integrity = (ROOT / ".github/workflows/source-integrity-guard.yml").read_text()
    assert 'cron: "27 */2 * * *"' in integrity
    assert "actions/checkout@v4" in integrity
    assert "actions/setup-python@v5" in integrity
