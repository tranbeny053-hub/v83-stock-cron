"""W-A (plan §8.1, migration 0017): the receipt when the run identity, the detail payload and the
forecast bundle are written in ONE transaction.

- SAVED only when that one call kept all of it.
- NOT_SAVED when the call was refused (any CONFLICT: the run's, the detail's or the bundle's) or
  never sent (an open circuit), or when a required snapshot is missing.
- COMMIT_UNKNOWN when the call was sent and its outcome is not known.
The separate run upsert is never sent on this path: it would overwrite a conflicting stored run
before the bundle could refuse it. The W-B path (test_three_state_receipts.py) stays for writers
without the function.

Deterministic: production's REST writer runs unchanged against an httpx.MockTransport. The same
receipts are measured on scratch PostgreSQL by PERS-0, and behind a real PostgREST by P3-PRIV-R
(W10).
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from crypto_probability_engine.api.analysis_service import (
    RECEIPT_COMMIT_UNKNOWN,
    RECEIPT_NOT_SAVED,
    RECEIPT_SAVED,
    PersistenceWork,
    _persist_work_confirmed,
)
from crypto_probability_engine.persistence.repository import SupabaseRestRepository

BASE = "https://project.example.invalid"
FORECAST = "rpc/save_forecast_bundle"


class Endpoint:
    """A PostgREST stand-in: the forecast RPC answers from a queue; every other write succeeds.
    Every request is recorded, in order, with its body."""

    def __init__(self, *answers: object) -> None:
        self.answers = list(answers)
        self.calls: list[tuple[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/rest/v1/")
        self.calls.append((path, json.loads(request.content) if request.content else None))
        if path != FORECAST:
            return httpx.Response(201)
        answer_ = self.answers.pop(0)
        if isinstance(answer_, Exception):
            raise answer_
        if isinstance(answer_, httpx.Response):
            return answer_
        return httpx.Response(200, json=answer_)

    def paths(self) -> list[str]:
        return [path for path, _body in self.calls]

    def forecast_bodies(self) -> list[dict]:
        return [body for path, body in self.calls if path == FORECAST]


def rest(endpoint: Endpoint) -> SupabaseRestRepository:
    return SupabaseRestRepository(
        BASE, "test-key", client=httpx.Client(transport=httpx.MockTransport(endpoint))
    )


def answer(
    run: str = "INSERTED",
    run_detail: str | None = "INSERTED",
    prediction: str | None = "INSERTED",
    feature: str | None = "INSERTED",
    refused: bool = False,
) -> dict:
    return {"run": run, "run_detail": run_detail, "prediction": prediction,
            "feature_snapshot": feature, "derivatives_snapshot": None, "refused": refused}


KEPT_RUN_CONFLICT = answer("CONFLICT", None, None, None, refused=True)
KEPT_DETAIL_CONFLICT = answer("NOT_KEPT", "CONFLICT", None, None, refused=True)


def prediction_row(prediction_id: str = "run_r:4H:6") -> dict:
    return {"prediction_id": prediction_id, "run_id": "run_r",
            "prediction_origin": "USER_REQUESTED"}


def snapshot(prediction_id: str = "run_r:4H:6") -> dict:
    return {"prediction_id": prediction_id, "snapshot_payload": {"k": 1}, "snapshot_hash": "a" * 64}


DETAIL = {"run_id": "run_r", "analysis_hash": "h" * 64, "detail_payload": {"run_id": "run_r"}}
RUN = {"run_id": "run_r", "symbol": "BTC"}


def work(*rows: dict, detail: dict | None = DETAIL, snapshots: tuple[dict, ...] | None = None,
         **extra: Any) -> PersistenceWork:
    rows = rows or (prediction_row(),)
    if snapshots is None:
        snapshots = tuple(snapshot(row["prediction_id"]) for row in rows)
    return PersistenceWork(
        run_summary=RUN,
        timeframe_result={"run_id": "run_r", "timeframe": "4H"},
        provider_observations=(),
        prediction_rows=rows,
        feature_snapshot_rows=snapshots,
        run_detail_row=detail,
        **extra,
    )


def receipt(confirmation) -> tuple[str | None, str | None]:
    return confirmation.receipt, confirmation.receipt_reason


# ------------------------------------------------------------------------ one transaction


@pytest.mark.parametrize("status", ["INSERTED", "IDENTICAL_DUPLICATE"])
def test_one_kept_call_is_saved(status: str) -> None:
    endpoint = Endpoint(answer(status, status, status, status))
    confirmation = _persist_work_confirmed(work(), rest(endpoint))
    assert receipt(confirmation) == (RECEIPT_SAVED, None)
    assert confirmation.overall == "OK"


def test_the_run_and_the_detail_travel_only_inside_the_bundle() -> None:
    endpoint = Endpoint(answer())
    _persist_work_confirmed(work(), rest(endpoint))
    assert "analysis_runs" not in endpoint.paths(), "the run upsert would overwrite a conflict"
    assert "analysis_run_details" not in endpoint.paths()
    assert "analysis_timeframe_results" in endpoint.paths(), "other rows are written as before"
    (body,) = endpoint.forecast_bodies()
    assert body["p_run"] == RUN and body["p_run_detail"] == DETAIL
    assert body["p_feature_snapshot"] == snapshot()


def test_every_bundle_carries_the_same_run_and_detail() -> None:
    rows = (prediction_row("run_r:4H:6"), prediction_row("run_r:4H:7"))
    endpoint = Endpoint(answer(), answer("IDENTICAL_DUPLICATE", "IDENTICAL_DUPLICATE"))
    confirmation = _persist_work_confirmed(work(*rows), rest(endpoint))
    assert receipt(confirmation) == (RECEIPT_SAVED, None)
    bodies = endpoint.forecast_bodies()
    assert [body["p_prediction"]["prediction_id"] for body in bodies] == [
        "run_r:4H:6", "run_r:4H:7"]
    assert all(body["p_run"] == RUN and body["p_run_detail"] == DETAIL for body in bodies)


def test_without_a_required_detail_the_run_and_the_bundle_decide() -> None:
    endpoint = Endpoint(answer(run_detail=None))
    confirmation = _persist_work_confirmed(work(detail=None), rest(endpoint))
    assert receipt(confirmation) == (RECEIPT_SAVED, None)
    assert endpoint.forecast_bodies()[0]["p_run_detail"] is None


# ------------------------------------------------------------------------ NOT_SAVED


@pytest.mark.parametrize(
    "refusal",
    [
        KEPT_RUN_CONFLICT,
        KEPT_DETAIL_CONFLICT,
        answer("NOT_KEPT", "NOT_KEPT", "CONFLICT", None, refused=True),
        answer("IDENTICAL_DUPLICATE", "IDENTICAL_DUPLICATE", "IDENTICAL_DUPLICATE", "CONFLICT",
               refused=True),
    ],
    ids=["run-conflict", "detail-conflict", "prediction-conflict", "snapshot-conflict"],
)
def test_any_refusal_is_not_saved_and_never_acknowledged(refusal: dict) -> None:
    confirmation = _persist_work_confirmed(work(), rest(Endpoint(refusal)))
    assert receipt(confirmation) == (RECEIPT_NOT_SAVED, "CONFLICT")
    assert confirmation.overall != "OK"


def test_a_refused_run_reads_as_a_refused_prediction() -> None:
    confirmation = _persist_work_confirmed(work(), rest(Endpoint(KEPT_RUN_CONFLICT)))
    assert confirmation.prediction == "CONFLICT" and confirmation.overall == "UNAVAILABLE"


def test_an_open_circuit_is_not_saved_and_sends_nothing() -> None:
    endpoint = Endpoint()
    writer = rest(endpoint)
    writer.mark_unavailable()
    confirmation = _persist_work_confirmed(work(), writer)
    assert receipt(confirmation) == (RECEIPT_NOT_SAVED, "CIRCUIT_OPEN")
    assert FORECAST not in endpoint.paths()


def test_a_missing_required_snapshot_is_not_saved_even_though_the_rest_is_kept() -> None:
    endpoint = Endpoint(answer(feature=None))
    confirmation = _persist_work_confirmed(work(snapshots=()), rest(endpoint))
    assert receipt(confirmation) == (RECEIPT_NOT_SAVED, "INCOMPLETE_BUNDLE")
    assert endpoint.forecast_bodies()[0]["p_feature_snapshot"] is None


def test_several_bundles_report_the_least_certain_outcome() -> None:
    rows = (prediction_row("run_r:4H:6"), prediction_row("run_r:4H:7"))
    saved_then_refused = Endpoint(
        answer(), answer("IDENTICAL_DUPLICATE", "IDENTICAL_DUPLICATE", "CONFLICT", None,
                         refused=True))
    confirmation = _persist_work_confirmed(work(*rows), rest(saved_then_refused))
    assert receipt(confirmation) == (RECEIPT_NOT_SAVED, "CONFLICT")
    saved_then_lost = Endpoint(answer(), httpx.ReadError("lost after the commit"))
    confirmation = _persist_work_confirmed(work(*rows), rest(saved_then_lost))
    assert receipt(confirmation) == (RECEIPT_COMMIT_UNKNOWN, "NO_CONFIRMATION")


# ------------------------------------------------------------------------ COMMIT_UNKNOWN


@pytest.mark.parametrize(
    "failure",
    [httpx.Response(500), httpx.Response(400, json={"code": "22023"}),
     httpx.ReadError("lost after the commit"), httpx.ReadTimeout("no answer"),
     {"prediction": "INSERTED"}],
    ids=["500", "answered-400", "lost-response", "read-timeout", "unreadable-answer"],
)
def test_a_sent_unconfirmed_call_is_commit_unknown(failure: object) -> None:
    confirmation = _persist_work_confirmed(work(), rest(Endpoint(failure)))
    assert receipt(confirmation) == (RECEIPT_COMMIT_UNKNOWN, "NO_CONFIRMATION")
    assert confirmation.overall == "UNAVAILABLE"


def test_an_exception_mid_call_is_commit_unknown() -> None:
    class Raising(SupabaseRestRepository):
        def save_forecast_bundle(self, *args, **kwargs):
            raise RuntimeError("the client failed after sending")

    writer = Raising(BASE, "test-key", client=httpx.Client(
        transport=httpx.MockTransport(Endpoint())))
    confirmation = _persist_work_confirmed(work(), writer)
    assert receipt(confirmation) == (RECEIPT_COMMIT_UNKNOWN, "UNCONFIRMED_EXCEPTION")


# ------------------------------------------------------------------------ which path


def test_without_a_prediction_the_run_and_the_detail_are_written_as_before() -> None:
    endpoint = Endpoint()
    no_forecast = PersistenceWork(
        run_summary=RUN,
        timeframe_result={"run_id": "run_r", "timeframe": "4H"},
        provider_observations=(),
        run_detail_row=DETAIL,
    )
    confirmation = _persist_work_confirmed(no_forecast, rest(endpoint))
    assert confirmation.receipt is None, "no forecast bundle, no receipt"
    assert "analysis_runs" in endpoint.paths() and "analysis_run_details" in endpoint.paths()
    assert FORECAST not in endpoint.paths()


def test_oos_identities_keep_their_per_row_path_and_the_run_stays_separate() -> None:
    oos_id = "oosb-" + "1" * 32 + ":4H:CANDIDATE"
    oos = {**prediction_row(oos_id), "prediction_origin": "SCHEDULED_SHADOW_EVIDENCE"}
    endpoint = Endpoint()
    _persist_work_confirmed(work(oos, detail=None), rest(endpoint))
    assert FORECAST not in endpoint.paths()
    assert "analysis_runs" in endpoint.paths() and "predictions" in endpoint.paths()


def test_a_mixed_analysis_sends_its_run_only_inside_the_forecast_bundle() -> None:
    oos_id = "oosb-" + "2" * 32 + ":4H:CANDIDATE"
    oos = {**prediction_row(oos_id), "prediction_origin": "SCHEDULED_SHADOW_EVIDENCE"}
    endpoint = Endpoint(answer())
    _persist_work_confirmed(work(prediction_row(), oos), rest(endpoint))
    assert endpoint.paths().count(FORECAST) == 1
    assert "analysis_runs" not in endpoint.paths()
    assert "predictions" in endpoint.paths(), "the OOS row keeps its own write"
