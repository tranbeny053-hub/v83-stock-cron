"""Plan §8.1: the forecast bundle's receipt is SAVED, NOT_SAVED or COMMIT_UNKNOWN, and never lies.

- SAVED only when the complete bundle is confirmed stored.
- NOT_SAVED only when it is known not to be stored complete: an open circuit (no request is sent),
  a refused conflict, a missing required snapshot, no durable store, or a write never attempted.
- COMMIT_UNKNOWN whenever a write was attempted and not confirmed: a failed request, a lost
  response, an unreadable answer, an exception mid-write.

Deterministic: production's REST writer runs unchanged against an httpx.MockTransport, with each
fault injected exactly where named. The same receipts are measured against migration 0015 on
scratch PostgreSQL by PERS-0 (criterion C5).
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from crypto_probability_engine.api.analysis_service import (
    _DETAIL_NOT_SENT,
    RECEIPT_COMMIT_UNKNOWN,
    RECEIPT_NOT_SAVED,
    RECEIPT_SAVED,
    PersistenceWork,
    _core_receipt,
    _emit_persistence_receipt,
    _persist_work_confirmed,
)
from crypto_probability_engine.persistence.repository import (
    InMemoryPersistenceRepository,
    SupabaseRestRepository,
)

BASE = "https://project.example.invalid"
RPC_URL = f"{BASE}/rest/v1/rpc/save_prediction_bundle"


class Endpoint:
    """A PostgREST stand-in: the RPC answers from a queue; every other write succeeds, unless a
    table's answer is overridden. Every request's table is recorded, in order."""

    def __init__(self, *answers: object, tables: dict[str, object] | None = None) -> None:
        self.answers = list(answers)
        self.rpc_calls = 0
        self.tables = dict(tables or {})
        self.paths: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.paths.append(request.url.path.removeprefix("/rest/v1/"))
        if str(request.url) != RPC_URL:
            override = self.tables.get(request.url.path.removeprefix("/rest/v1/"))
            if isinstance(override, Exception):
                raise override
            return override if isinstance(override, httpx.Response) else httpx.Response(201)
        self.rpc_calls += 1
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, httpx.Response):
            return answer
        return httpx.Response(200, json=answer)


def rest(endpoint: Endpoint) -> SupabaseRestRepository:
    return SupabaseRestRepository(
        BASE, "test-key", client=httpx.Client(transport=httpx.MockTransport(endpoint))
    )


def answer(prediction: str, feature: str | None = None, refused: bool = False) -> dict:
    return {"prediction": prediction, "feature_snapshot": feature, "derivatives_snapshot": None,
            "refused": refused}


def prediction(prediction_id: str = "run_r:4H:6") -> dict:
    return {"prediction_id": prediction_id, "run_id": "run_r",
            "prediction_origin": "USER_REQUESTED"}


def snapshot(prediction_id: str = "run_r:4H:6") -> dict:
    return {"prediction_id": prediction_id, "snapshot_payload": {"k": 1}, "snapshot_hash": "a" * 64}


def detail(run_id: str = "run_r") -> dict:
    return {"run_id": run_id, "analysis_hash": "h" * 64, "detail_payload": {"run_id": run_id}}


def work(*rows: dict, snapshots: tuple[dict, ...] | None = None, build_failed: bool = False,
         **extra: Any) -> PersistenceWork:
    rows = rows or (prediction(),)
    if snapshots is None:
        snapshots = tuple(snapshot(row["prediction_id"]) for row in rows)
    return PersistenceWork(
        run_summary={"run_id": "run_r"},
        timeframe_result={"run_id": "run_r", "timeframe": "4H"},
        provider_observations=(),
        prediction_rows=rows,
        feature_snapshot_rows=snapshots,
        feature_snapshot_build_failed=build_failed,
        **extra,
    )


def receipt(confirmation) -> tuple[str | None, str | None]:
    return confirmation.receipt, confirmation.receipt_reason


# ------------------------------------------------------------------------ SAVED


@pytest.mark.parametrize("status", ["INSERTED", "IDENTICAL_DUPLICATE"])
def test_a_confirmed_complete_bundle_is_saved(status: str) -> None:
    confirmation = _persist_work_confirmed(work(), rest(Endpoint(answer(status, status))))
    assert receipt(confirmation) == (RECEIPT_SAVED, None)
    assert confirmation.overall == "OK"


# ------------------------------------------------------------------------ NOT_SAVED (known)


def test_a_refused_conflict_is_not_saved() -> None:
    for refused in (answer("CONFLICT", refused=True),
                    answer("IDENTICAL_DUPLICATE", "CONFLICT", refused=True)):
        confirmation = _persist_work_confirmed(work(), rest(Endpoint(refused)))
        assert receipt(confirmation) == (RECEIPT_NOT_SAVED, "CONFLICT")


def test_an_open_circuit_is_not_saved_and_sends_nothing() -> None:
    endpoint = Endpoint(httpx.Response(500))
    repository = rest(endpoint)
    first = _persist_work_confirmed(work(), repository)
    assert receipt(first) == (RECEIPT_COMMIT_UNKNOWN, "NO_CONFIRMATION")
    assert repository.circuit_state() == "OPEN"
    second = _persist_work_confirmed(work(prediction("run_r:4H:7")), repository)
    assert receipt(second) == (RECEIPT_NOT_SAVED, "CIRCUIT_OPEN")
    assert endpoint.rpc_calls == 1, "the open circuit's bundle was never sent"
    assert second.overall == "UNAVAILABLE"


def test_a_missing_required_snapshot_is_not_saved_even_though_the_prediction_is() -> None:
    endpoint = Endpoint(answer("INSERTED"))
    confirmation = _persist_work_confirmed(work(snapshots=(), build_failed=True), rest(endpoint))
    assert receipt(confirmation) == (RECEIPT_NOT_SAVED, "INCOMPLETE_BUNDLE")
    assert confirmation.prediction == "OK" and confirmation.overall == "PARTIAL"
    assert endpoint.rpc_calls == 1


def test_no_durable_store_is_not_saved() -> None:
    assert receipt(_persist_work_confirmed(work(), None)) == (RECEIPT_NOT_SAVED, "NO_DURABLE_STORE")
    in_memory = _persist_work_confirmed(work(), InMemoryPersistenceRepository())
    assert receipt(in_memory) == (RECEIPT_NOT_SAVED, "NO_DURABLE_STORE")


def test_a_failure_before_any_bundle_write_is_not_attempted() -> None:
    class AuxiliaryFails(SupabaseRestRepository):
        def save_run(self, summary):
            raise RuntimeError("the run summary could not be built")

    endpoint = Endpoint()
    repository = AuxiliaryFails(
        BASE, "test-key", client=httpx.Client(transport=httpx.MockTransport(endpoint))
    )
    confirmation = _persist_work_confirmed(work(), repository)
    assert receipt(confirmation) == (RECEIPT_NOT_SAVED, "NOT_ATTEMPTED")
    assert endpoint.rpc_calls == 0


# ------------------------------------------------------------------------ COMMIT_UNKNOWN


@pytest.mark.parametrize(
    "failure",
    [httpx.Response(500), httpx.Response(504), httpx.Response(400, json={"code": "22023"}),
     httpx.ReadError("lost after the commit"), httpx.ReadTimeout("no answer"),
     httpx.RemoteProtocolError("cut"), {"prediction": "INSERTED"}],
    ids=["500", "gateway-504", "answered-400", "lost-response", "read-timeout", "protocol",
         "unreadable-answer"],
)
def test_an_attempted_unconfirmed_write_is_commit_unknown(failure: object) -> None:
    confirmation = _persist_work_confirmed(work(), rest(Endpoint(failure)))
    assert receipt(confirmation) == (RECEIPT_COMMIT_UNKNOWN, "NO_CONFIRMATION")
    assert confirmation.overall == "UNAVAILABLE"


def test_an_exception_mid_write_is_commit_unknown() -> None:
    class Raising(SupabaseRestRepository):
        def save_prediction_bundle(self, *args, **kwargs):
            raise RuntimeError("the client failed after sending")

    repository = Raising(BASE, "test-key", client=httpx.Client(
        transport=httpx.MockTransport(Endpoint())))
    confirmation = _persist_work_confirmed(work(), repository)
    assert receipt(confirmation) == (RECEIPT_COMMIT_UNKNOWN, "UNCONFIRMED_EXCEPTION")


# ------------------------------------------------------------------------ several bundles, none


def test_several_bundles_report_the_least_certain_outcome() -> None:
    rows = (prediction("run_r:4H:6"), prediction("run_r:4H:7"))
    saved_then_refused = Endpoint(answer("INSERTED", "INSERTED"), answer("CONFLICT", refused=True))
    assert receipt(_persist_work_confirmed(work(*rows), rest(saved_then_refused))) == (
        RECEIPT_NOT_SAVED, "CONFLICT")
    refused_then_unknown = Endpoint(answer("CONFLICT", refused=True), httpx.ReadError("lost"))
    assert receipt(_persist_work_confirmed(work(*rows), rest(refused_then_unknown))) == (
        RECEIPT_COMMIT_UNKNOWN, "NO_CONFIRMATION")
    both_saved = Endpoint(answer("INSERTED", "INSERTED"), answer("INSERTED", "INSERTED"))
    assert receipt(_persist_work_confirmed(work(*rows), rest(both_saved))) == (RECEIPT_SAVED, None)


def test_an_analysis_without_a_bundle_has_no_receipt() -> None:
    no_bundle = PersistenceWork(
        run_summary={"run_id": "run_r"}, timeframe_result={"run_id": "run_r"},
        provider_observations=(),
    )
    assert receipt(_persist_work_confirmed(no_bundle, rest(Endpoint()))) == (None, None)


# ------------------------------------------------------------------------ never a false claim


@pytest.mark.parametrize(
    "fault",
    [answer("CONFLICT", refused=True), answer("IDENTICAL_DUPLICATE", "CONFLICT", refused=True),
     httpx.Response(500), httpx.ReadError("lost"), {"refused": False}],
)
def test_saved_is_never_claimed_for_a_bundle_not_confirmed_complete(fault: object) -> None:
    assert _persist_work_confirmed(work(), rest(Endpoint(fault))).receipt != RECEIPT_SAVED


# ------------------------------------------------------------------------ the telemetry


def test_the_persistence_receipt_event_carries_the_receipt(monkeypatch) -> None:
    from crypto_probability_engine.api import analysis_service

    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(analysis_service, "emit",
                        lambda name, **fields: events.append((name, fields)))
    confirmation = _persist_work_confirmed(work(), rest(Endpoint(answer("CONFLICT", refused=True))))
    _emit_persistence_receipt(work(), None, 0.0, confirmation, None)
    _emit_persistence_receipt(work(), None, 0.0, None, "RuntimeError")
    (first_name, first), (_, second) = events
    assert first_name == "persistence_receipt"
    assert (first["receipt"], first["receipt_reason"]) == (RECEIPT_NOT_SAVED, "CONFLICT")
    assert (second["receipt"], second["receipt_reason"]) == (
        RECEIPT_COMMIT_UNKNOWN, "UNCONFIRMED_EXCEPTION")


def test_the_receipt_fields_are_on_the_telemetry_allowlist() -> None:
    from crypto_probability_engine.telemetry.events import FIELDS

    assert {"receipt", "receipt_reason"} <= FIELDS
    assert json.dumps(sorted({RECEIPT_SAVED, RECEIPT_NOT_SAVED, RECEIPT_COMMIT_UNKNOWN})) == (
        '["COMMIT_UNKNOWN", "NOT_SAVED", "SAVED"]')


# ------------------------------------------------------------------------ §8.1's wider core (W-B)


def test_a_confirmed_detail_keeps_a_saved_bundle_saved() -> None:
    endpoint = Endpoint(answer("INSERTED", "INSERTED"))
    confirmation = _persist_work_confirmed(work(run_detail_row=detail()), rest(endpoint))
    assert receipt(confirmation) == (RECEIPT_SAVED, None)
    assert "analysis_run_details" in endpoint.paths


def test_the_detail_is_written_before_the_bundle() -> None:
    endpoint = Endpoint(answer("INSERTED", "INSERTED"))
    _persist_work_confirmed(work(run_detail_row=detail()), rest(endpoint))
    assert endpoint.paths.index("analysis_run_details") < endpoint.paths.index(
        "rpc/save_prediction_bundle"
    )


@pytest.mark.parametrize(
    "failure", [httpx.Response(500), httpx.Response(400), httpx.ReadError("lost")],
    ids=["500", "answered-400", "lost-response"],
)
def test_an_unconfirmed_detail_makes_a_saved_bundle_commit_unknown(failure: object) -> None:
    endpoint = Endpoint(answer("INSERTED", "INSERTED"), tables={"analysis_run_details": failure})
    confirmation = _persist_work_confirmed(work(run_detail_row=detail()), rest(endpoint))
    assert receipt(confirmation) == (RECEIPT_COMMIT_UNKNOWN, "DETAIL_UNCONFIRMED")
    assert endpoint.rpc_calls == 1, "the forecast bundle itself was still stored"


def test_an_unconfirmed_run_identity_is_never_saved() -> None:
    endpoint = Endpoint(
        answer("INSERTED", "INSERTED"), tables={"analysis_runs": httpx.Response(500)}
    )
    confirmation = _persist_work_confirmed(work(run_detail_row=detail()), rest(endpoint))
    assert confirmation.receipt != RECEIPT_SAVED
    # The failed run write opened the circuit, so neither the detail nor the bundle was sent.
    assert receipt(confirmation) == (RECEIPT_NOT_SAVED, "CIRCUIT_OPEN")
    assert endpoint.rpc_calls == 0 and "analysis_run_details" not in endpoint.paths


def test_an_open_circuit_sends_no_detail() -> None:
    endpoint = Endpoint(httpx.Response(500))
    repository = rest(endpoint)
    _persist_work_confirmed(work(), repository)
    assert repository.circuit_state() == "OPEN"
    sent = len(endpoint.paths)
    confirmation = _persist_work_confirmed(
        work(prediction("run_r:4H:7"), run_detail_row=detail()), repository
    )
    assert receipt(confirmation) == (RECEIPT_NOT_SAVED, "CIRCUIT_OPEN")
    assert "analysis_run_details" not in endpoint.paths[sent:]


def test_without_a_required_detail_the_receipt_is_the_bundles() -> None:
    endpoint = Endpoint(
        answer("INSERTED", "INSERTED"), tables={"analysis_run_details": httpx.Response(500)}
    )
    assert receipt(_persist_work_confirmed(work(), rest(endpoint))) == (RECEIPT_SAVED, None)
    assert "analysis_run_details" not in endpoint.paths


SAVED = (RECEIPT_SAVED, None)
UNKNOWN_RUN = (RECEIPT_COMMIT_UNKNOWN, "RUN_UNCONFIRMED")
UNKNOWN_DETAIL = (RECEIPT_COMMIT_UNKNOWN, "DETAIL_UNCONFIRMED")
INCOMPLETE = (RECEIPT_NOT_SAVED, "INCOMPLETE_BUNDLE")
REFUSED = (RECEIPT_NOT_SAVED, "CONFLICT")
NO_CONFIRMATION = (RECEIPT_COMMIT_UNKNOWN, "NO_CONFIRMATION")


@pytest.mark.parametrize(
    ("given", "run", "detail_status", "required", "expected"),
    [
        (SAVED, "OK", "OK", True, SAVED),
        (SAVED, "UNAVAILABLE", "OK", True, UNKNOWN_RUN),
        (SAVED, None, None, False, UNKNOWN_RUN),
        (SAVED, "OK", _DETAIL_NOT_SENT, True, INCOMPLETE),
        (SAVED, "OK", "UNAVAILABLE", True, UNKNOWN_DETAIL),
        (SAVED, "OK", None, True, UNKNOWN_DETAIL),
        (SAVED, "OK", "UNAVAILABLE", False, SAVED),
        (REFUSED, "UNAVAILABLE", "UNAVAILABLE", True, REFUSED),
        (NO_CONFIRMATION, "OK", _DETAIL_NOT_SENT, True, NO_CONFIRMATION),
        ((None, None), "UNAVAILABLE", "UNAVAILABLE", True, (None, None)),
    ],
)
def test_the_core_receipt_never_upgrades_and_saved_needs_every_core_part(
    given, run, detail_status, required, expected
) -> None:
    found = _core_receipt(*given, run=run, detail=detail_status, detail_required=required)
    assert found == expected
