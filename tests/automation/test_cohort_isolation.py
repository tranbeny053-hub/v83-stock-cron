"""Cohort isolation (F1, non-negotiable): an automated run can never enter a human cohort.

Proven here, against the real analysis pipeline on fixture data:
- AUTOMATED_RADAR is not, and cannot be validated as, a prediction origin;
- the isolated analysis is byte-identical to the recorded one but for the human route's
  DecisionView, yet builds no prediction row, hands nothing to persistence and writes no
  run-store entry;
- a successful automated call touches no persistence method, no human run store, no
  skill-evidence refresh and no recent-runs listing;
- the evidence carries no cohort origin and none of the withheld fields;
- the automation package never imports a cohort writer or names a cohort table.
"""

from __future__ import annotations

import ast
import inspect
import json
from copy import deepcopy
from pathlib import Path
from uuid import UUID

import pytest

from crypto_probability_engine.api import analysis_service, calibration_endpoint
from crypto_probability_engine.api.schemas import AnalysisRequest
from crypto_probability_engine.automation.origin import AUTOMATED_RADAR, AutomationOrigin
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.persistence import prediction_origin as cohort_origins
from crypto_probability_engine.persistence.run_store import InMemoryRunStore

AUTOMATION_DIR = Path(analysis_service.__file__).resolve().parents[1] / "automation"
PENDING = (
    "_PENDING_PREDICTION_ROWS",
    "_PENDING_FEATURE_SNAPSHOT_ROWS",
    "_PENDING_DERIVATIVES_SNAPSHOT_ROWS",
    "_PENDING_DERIVATIVES_SNAPSHOT_REQUIRED",
)
WITHHELD = (
    "USER_REQUESTED",
    "CONTROLLED_SMOKE",
    "SCHEDULED_SHADOW_EVIDENCE",
    "observed_directional_rate",
    "legacy_verdict",
    "quant_v2",
    "derivatives_intelligence",
)


def _pending_sizes() -> dict[str, int]:
    return {name: len(getattr(analysis_service, name)) for name in PENDING}


def _request() -> AnalysisRequest:
    return AnalysisRequest(symbol="BTC", timeframe="4H")


def test_automated_radar_is_not_a_prediction_origin() -> None:
    assert AUTOMATED_RADAR == AutomationOrigin.AUTOMATED_RADAR.value == "AUTOMATED_RADAR"
    assert AUTOMATED_RADAR not in cohort_origins.ALLOWED_PREDICTION_ORIGINS
    assert {origin.value for origin in cohort_origins.PredictionOrigin} == {
        "USER_REQUESTED",
        "CONTROLLED_SMOKE",
        "SCHEDULED_SHADOW_EVIDENCE",
    }
    with pytest.raises(ValueError):
        cohort_origins.validate_prediction_origin(AUTOMATED_RADAR)


def test_the_isolated_analysis_takes_no_origin_store_pair_or_cadence_identity() -> None:
    params = inspect.signature(analysis_service.analyze_request_isolated).parameters
    assert list(params) == [
        "request",
        "settings",
        "persistence_status",
        "derivatives_methodology_version",
        "methodology_version",
    ]
    for forbidden in ("prediction_origin", "run_store", "pair_context", "arm"):
        assert forbidden not in params


@pytest.mark.parametrize(
    ("record_prediction", "prediction_origin", "run_store"),
    [
        (True, None, InMemoryRunStore()),
        (True, "USER_REQUESTED", None),
        (False, "USER_REQUESTED", None),
        (False, None, InMemoryRunStore()),
    ],
)
def test_the_core_refuses_a_mixed_recorded_and_isolated_call(
    record_prediction: bool, prediction_origin: str | None, run_store: InMemoryRunStore | None
) -> None:
    with pytest.raises(ValueError):
        analysis_service._analyze(  # noqa: SLF001 - the shared core's own guard
            _request(),
            settings=Settings(data_mode="fixture"),
            run_store=run_store,
            persistence_status="STATELESS",
            prediction_origin=prediction_origin,
            deterministic_identity=False,
            derivatives_methodology_version=analysis_service.METHODOLOGY_VERSION_V0,
            methodology_version=analysis_service.METHODOLOGY_VERSION,
            pair_context=None,
            arm=None,
            record_prediction=record_prediction,
        )


def test_isolated_and_recorded_analyses_are_byte_identical_but_for_the_human_view(
    fixture_market, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The human route alone carries the DecisionView (owner rulings DP-A and DP-F, 2026-10-05):
    the isolated payload has none, every other field is byte-identical, and the two
    analysis_hash inputs differ by the view alone."""

    del fixture_market
    monkeypatch.setattr(analysis_service, "uuid4", lambda: UUID(int=1313))
    hashed: list[dict] = []
    real_hash = analysis_service.stable_hash

    def capture(payload: dict) -> str:
        hashed.append(deepcopy(payload))
        return real_hash(payload)

    monkeypatch.setattr(analysis_service, "stable_hash", capture)
    settings = Settings(data_mode="fixture")
    isolated = analysis_service.analyze_request_isolated(_request(), settings=settings)
    store = InMemoryRunStore()
    recorded = analysis_service.analyze_request(_request(), settings=settings, run_store=store)
    try:
        isolated_input, recorded_input = hashed
        assert "decision_view" not in isolated and "decision_view" not in isolated_input
        assert recorded["decision_view"]["schema_version"] == "decision_view.v1"
        assert recorded_input.pop("decision_view") == recorded["decision_view"]
        assert recorded_input == isolated_input
        assert real_hash(recorded_input) == isolated["analysis_hash"] != recorded["analysis_hash"]
        human = {key: value for key, value in recorded.items() if key != "decision_view"}
        assert json.dumps({**isolated, "analysis_hash": ""}, sort_keys=True) == json.dumps(
            {**human, "analysis_hash": ""}, sort_keys=True
        )
    finally:
        analysis_service._pop_prediction_persistence(recorded)  # noqa: SLF001 - clean up


def test_the_isolated_analysis_hands_nothing_to_persistence_or_a_run_store(
    fixture_market,
) -> None:
    del fixture_market
    settings = Settings(data_mode="fixture")
    before = _pending_sizes()
    analysis_service.analyze_request_isolated(_request(), settings=settings)
    assert _pending_sizes() == before
    # The control proves the check can see a write: a recorded analysis does park rows.
    store = InMemoryRunStore()
    recorded = analysis_service.analyze_request(_request(), settings=settings, run_store=store)
    try:
        rows = "_PENDING_PREDICTION_ROWS"
        assert _pending_sizes()[rows] == before[rows] + 1
        assert store.get(recorded["run_id"]) is not None
    finally:
        analysis_service._pop_prediction_persistence(recorded)  # noqa: SLF001 - clean up
    assert _pending_sizes() == before


def test_a_successful_automated_call_touches_no_cohort_surface(
    harness_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    touched: list[str] = []

    def spy(name):
        def record(*_args, **_kwargs):
            touched.append(name)

        return record

    monkeypatch.setattr(analysis_service, "schedule_best_effort_persist", spy("persist"))
    monkeypatch.setattr(analysis_service, "_submit_persistence_work", spy("submit"))
    monkeypatch.setattr(analysis_service, "persist_analysis_now", spy("persist_now"))
    monkeypatch.setattr(calibration_endpoint, "schedule_skill_evidence_refresh", spy("refresh"))
    harness = harness_factory()
    repository = harness.app.state.persistence_repository
    for name in dir(repository):
        if name.startswith("save_"):
            monkeypatch.setattr(repository, name, spy(f"repository.{name}"))
    before = _pending_sizes()
    human_runs_before = list(harness.app.state.run_store.runs)

    response = harness.post()

    assert response.status_code == 200, response.json()
    assert touched == []
    assert _pending_sizes() == before
    assert list(harness.app.state.run_store.runs) == human_runs_before
    [entry] = harness.ledger.entries()
    assert entry.evidence_origin == AUTOMATED_RADAR and entry.outcome_code == "SUCCEEDED"
    assert entry.run_id == response.json()["run_id"]


def test_the_evidence_carries_no_cohort_origin_or_withheld_field(harness_factory) -> None:
    response = harness_factory().post()
    assert response.status_code == 200
    body = response.json()
    assert body["evidence_origin"] == AUTOMATED_RADAR
    text = json.dumps(body)
    for withheld in WITHHELD:
        assert withheld not in text, withheld


def _automation_modules() -> list[Path]:
    return sorted(AUTOMATION_DIR.glob("*.py"))


def test_the_automation_package_never_imports_a_cohort_writer() -> None:
    forbidden_modules = (
        "crypto_probability_engine.persistence.repository",
        "crypto_probability_engine.persistence.run_store",
        "crypto_probability_engine.calibration",
        "crypto_probability_engine.oos",
        "crypto_probability_engine.shadow_validation",
        "crypto_probability_engine.resolution",
    )
    forbidden_names = {
        "analyze_request",
        "schedule_best_effort_persist",
        "persist_analysis_now",
        "schedule_skill_evidence_refresh",
        "PredictionOrigin",
    }
    assert _automation_modules(), "the automation package must exist"
    for path in _automation_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith(forbidden_modules), (path.name, node.module)
                imported = {alias.name for alias in node.names}
                assert not imported & forbidden_names, (path.name, imported & forbidden_names)
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith(forbidden_modules), (path.name, alias.name)


def test_the_automation_package_names_no_cohort_table() -> None:
    for path in _automation_modules():
        text = path.read_text(encoding="utf-8")
        for table in ("public.predictions", "prediction_outcomes", "analysis_runs"):
            assert table not in text, (path.name, table)
