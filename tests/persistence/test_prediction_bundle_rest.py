"""B9 (plan §8.1): the REST writer's atomic forecast bundle through migration 0015's RPC.

No database is contacted here: the PostgREST endpoint is an httpx.MockTransport. The function's
behaviour on a real PostgreSQL, called exactly as PostgREST calls it, is proven by the PERS-0
rehearsal (scripts/persistence_rehearsal) and the 0015 migration rehearsal in CI.
"""

from __future__ import annotations

import json

import httpx
import pytest

from crypto_probability_engine.api.analysis_service import PersistenceWork, _persist_work_confirmed
from crypto_probability_engine.persistence.derivatives_snapshot import (
    DerivativesSnapshotWriteStatus,
)
from crypto_probability_engine.persistence.feature_snapshot import FeatureSnapshotWriteStatus
from crypto_probability_engine.persistence.repository import (
    InMemoryPersistenceRepository,
    PredictionBundleWrite,
    PredictionWriteStatus,
    SupabasePersistenceRepository,
    SupabaseRestRepository,
    _bundle_write_from_rpc,
)

BASE = "https://project.example.invalid"
RPC_URL = f"{BASE}/rest/v1/rpc/save_prediction_bundle"
KEY = "service-role-test-key"


def prediction(**changes) -> dict:
    row = {
        "prediction_id": "run_b9:4H:6",
        "run_id": "run_b9",
        "operator_id": "operator",
        "symbol": "BTC",
        "normalized_symbol": "BTC/USDT",
        "timeframe": "4H",
        "horizon_bars": 6,
        "predicted_at_utc": "2026-10-02T08:00:00Z",
        "reference_close_utc": "2026-10-02T08:00:00Z",
        "reference_price": 61234.56789012345,
        "horizon_end_utc": "2026-10-03T08:00:00Z",
        "p_up_frac": 0.33333333333333337,
        "p_down_frac": 0.33333333333333337,
        "p_timeout_frac": 0.33333333333333326,
        "decision_band_frac": 0.01,
        "model_version": "m",
        "methodology_version": "distributional-v1",
        "calibration_status": "UNCALIBRATED",
        "reliability_status": "INSUFFICIENT",
        "epistemic_sufficiency": "LOW",
        "gate_action": "WAIT",
        "data_source": "BINANCE_PUBLIC",
        "is_live_data": True,
        "cross_provider_state": "UNAVAILABLE",
        "prediction_origin": "USER_REQUESTED",
    }
    row.update(changes)
    return row


def snapshot(prediction_id: str = "run_b9:4H:6", hash_char: str = "a") -> dict:
    return {"prediction_id": prediction_id, "snapshot_payload": {"k": 1},
            "snapshot_hash": hash_char * 64}


class Endpoint:
    """A PostgREST stand-in: records every request and answers the RPC from a queue."""

    def __init__(self, *answers: object) -> None:
        self.answers = list(answers)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if str(request.url) != RPC_URL:
            return httpx.Response(201)
        answer = self.answers.pop(0) if self.answers else None
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, httpx.Response):
            return answer
        return httpx.Response(200, json=answer)

    def rpc_calls(self) -> list[dict]:
        return [json.loads(r.content) for r in self.requests if str(r.url) == RPC_URL]


def repository(endpoint: Endpoint) -> SupabaseRestRepository:
    return SupabaseRestRepository(
        BASE, KEY, client=httpx.Client(transport=httpx.MockTransport(endpoint))
    )


class B9Writer:
    """The REST writer without W-A's save_forecast_bundle (migration 0017): the W-B path, where the
    run and the detail are written beside B9's bundle. The W-A path is tested in
    test_forecast_bundle_receipts.py."""

    def __init__(self, inner: SupabaseRestRepository) -> None:
        self._inner = inner

    def __getattr__(self, name: str):
        if name == "save_forecast_bundle":
            raise AttributeError(name)
        return getattr(self._inner, name)


def answer(prediction_status: str, feature=None, derivatives=None, refused=False) -> dict:
    return {"prediction": prediction_status, "feature_snapshot": feature,
            "derivatives_snapshot": derivatives, "refused": refused}


# ------------------------------------------------------------------------ the one request


def test_the_bundle_is_one_post_to_the_rpc_with_the_normalized_rows() -> None:
    endpoint = Endpoint(answer("INSERTED", "INSERTED", "INSERTED"))
    row = prediction()
    del row["prediction_origin"]  # normalized exactly as save_prediction normalizes it
    written = repository(endpoint).save_prediction_bundle(row, snapshot(), snapshot(hash_char="d"))
    assert written == PredictionBundleWrite(
        PredictionWriteStatus.INSERTED,
        FeatureSnapshotWriteStatus.INSERTED,
        DerivativesSnapshotWriteStatus.INSERTED,
    )
    (request,) = endpoint.requests
    assert request.method == "POST" and str(request.url) == RPC_URL
    assert request.headers["apikey"] == KEY
    assert request.headers["authorization"] == f"Bearer {KEY}"
    body = json.loads(request.content)
    assert set(body) == {"p_prediction", "p_feature_snapshot", "p_derivatives_snapshot"}
    assert body["p_prediction"] == {**row, "prediction_origin": "USER_REQUESTED"}
    assert body["p_feature_snapshot"] == snapshot()
    assert body["p_derivatives_snapshot"] == snapshot(hash_char="d")


def test_an_absent_snapshot_is_sent_as_null() -> None:
    endpoint = Endpoint(answer("INSERTED"))
    written = repository(endpoint).save_prediction_bundle(prediction(), None)
    assert written == PredictionBundleWrite(PredictionWriteStatus.INSERTED)
    assert endpoint.rpc_calls()[0]["p_feature_snapshot"] is None
    assert endpoint.rpc_calls()[0]["p_derivatives_snapshot"] is None


def test_identical_replay_confirms_and_a_refusal_keeps_the_circuit_closed() -> None:
    endpoint = Endpoint(
        answer("IDENTICAL_DUPLICATE", "IDENTICAL_DUPLICATE"),
        answer("CONFLICT", refused=True),
        answer("IDENTICAL_DUPLICATE", "CONFLICT", refused=True),
    )
    repo = repository(endpoint)
    assert repo.save_prediction_bundle(prediction(), snapshot()) == PredictionBundleWrite(
        PredictionWriteStatus.IDENTICAL_DUPLICATE, FeatureSnapshotWriteStatus.IDENTICAL_DUPLICATE
    )
    assert repo.save_prediction_bundle(prediction(), snapshot()) == PredictionBundleWrite(
        PredictionWriteStatus.CONFLICT, refused=True
    )
    assert repo.save_prediction_bundle(prediction(), snapshot()) == PredictionBundleWrite(
        PredictionWriteStatus.IDENTICAL_DUPLICATE, FeatureSnapshotWriteStatus.CONFLICT,
        refused=True,
    )
    assert repo.circuit_state() == "CLOSED"  # the database answered: a refusal is not an outage


@pytest.mark.parametrize(
    "failure",
    [httpx.Response(400, json={"code": "22023"}), httpx.Response(500),
     httpx.Response(404, json={"code": "PGRST202"}), httpx.ConnectError("down"),
     httpx.ReadError("lost after the commit")],
    ids=["refused-input", "server-error", "function-missing", "connect", "lost-response"],
)
def test_a_failed_request_is_unavailable_and_opens_the_circuit(failure) -> None:
    endpoint = Endpoint(failure)
    repo = repository(endpoint)
    assert repo.save_prediction_bundle(prediction(), snapshot()) == PredictionBundleWrite(
        PredictionWriteStatus.UNAVAILABLE
    )
    assert repo.circuit_state() == "OPEN"
    assert repo.save_prediction_bundle(prediction(), snapshot()).prediction == "UNAVAILABLE"
    assert len(endpoint.rpc_calls()) == 1, "an open circuit sends nothing"


@pytest.mark.parametrize(
    ("reply", "feature", "derivatives"),
    [
        ({"prediction": "INSERTED"}, True, False),
        ({**answer("INSERTED", "INSERTED"), "extra": 1}, True, False),
        (answer("SAVED", "INSERTED"), True, False),
        (answer("INSERTED", "INSERTED", refused=True), True, False),
        (answer("CONFLICT", refused=False), True, False),
        (answer("INSERTED"), True, False),
        (answer("INSERTED", "INSERTED", "INSERTED"), True, False),
        (answer("INSERTED", "INSERTED", refused="false"), True, False),
        (["INSERTED"], True, False),
        (None, True, False),
    ],
    ids=["missing-keys", "extra-key", "unknown-status", "refused-without-conflict",
         "conflict-not-refused", "submitted-snapshot-without-status",
         "status-for-unsubmitted-snapshot", "refused-not-boolean", "a-list", "empty"],
)
def test_an_answer_the_function_cannot_give_is_unavailable(reply, feature, derivatives) -> None:
    assert _bundle_write_from_rpc(
        reply, feature_submitted=feature, derivatives_submitted=derivatives
    ) is None
    endpoint = Endpoint(reply)
    repo = repository(endpoint)
    written = repo.save_prediction_bundle(
        prediction(), snapshot() if feature else None, snapshot(hash_char="d") if derivatives
        else None,
    )
    assert written == PredictionBundleWrite(PredictionWriteStatus.UNAVAILABLE)
    assert repo.circuit_state() == "OPEN"


def test_oos_identities_never_reach_the_bundle() -> None:
    endpoint = Endpoint()
    oos = prediction(prediction_id="oosb-" + "0" * 32 + ":4H:BASELINE",
                     prediction_origin="SCHEDULED_SHADOW_EVIDENCE")
    with pytest.raises(ValueError):
        repository(endpoint).save_prediction_bundle(oos, snapshot(oos["prediction_id"]))
    assert endpoint.requests == []


def test_only_the_rest_writer_has_the_bundle() -> None:
    # The minimum REST route (RD-1 = R1): the direct-Postgres and in-memory writers are unchanged.
    assert callable(getattr(SupabaseRestRepository, "save_prediction_bundle", None))
    assert not hasattr(SupabasePersistenceRepository, "save_prediction_bundle")
    assert not hasattr(InMemoryPersistenceRepository, "save_prediction_bundle")


# ------------------------------------------------------------------------ the confirmation


def work(*rows: dict, snapshots: tuple[dict, ...] = ()) -> PersistenceWork:
    return PersistenceWork(
        run_summary={"run_id": "run_b9"},
        timeframe_result={"run_id": "run_b9", "timeframe": "4H"},
        provider_observations=(),
        prediction_rows=rows,
        feature_snapshot_rows=snapshots,
    )


def test_the_confirmation_acknowledges_only_a_complete_bundle() -> None:
    endpoint = Endpoint(answer("INSERTED", "INSERTED"))
    confirmation = _persist_work_confirmed(work(prediction(), snapshots=(snapshot(),)),
                                           B9Writer(repository(endpoint)))
    assert (confirmation.prediction, confirmation.feature_snapshot, confirmation.overall) == (
        "OK", "INSERTED", "OK")
    (call,) = endpoint.rpc_calls()
    assert call["p_feature_snapshot"] == snapshot()


def test_a_conflicting_prediction_is_refused_never_acknowledged() -> None:
    endpoint = Endpoint(answer("CONFLICT", refused=True))
    confirmation = _persist_work_confirmed(work(prediction(), snapshots=(snapshot(),)),
                                           B9Writer(repository(endpoint)))
    assert confirmation.prediction == "CONFLICT"
    assert confirmation.overall == "UNAVAILABLE"


def test_a_conflicting_snapshot_is_partial_as_before() -> None:
    endpoint = Endpoint(answer("IDENTICAL_DUPLICATE", "CONFLICT", refused=True))
    confirmation = _persist_work_confirmed(work(prediction(), snapshots=(snapshot(),)),
                                           B9Writer(repository(endpoint)))
    assert (confirmation.prediction, confirmation.feature_snapshot, confirmation.overall) == (
        "OK", "CONFLICT", "PARTIAL")


def test_a_failed_bundle_is_unavailable() -> None:
    endpoint = Endpoint(httpx.Response(500))
    confirmation = _persist_work_confirmed(work(prediction(), snapshots=(snapshot(),)),
                                           B9Writer(repository(endpoint)))
    assert (confirmation.prediction, confirmation.overall) == ("UNAVAILABLE", "UNAVAILABLE")


def test_a_missing_snapshot_still_writes_the_prediction_atomically_but_partial() -> None:
    endpoint = Endpoint(answer("INSERTED"))
    confirmation = _persist_work_confirmed(work(prediction()), B9Writer(repository(endpoint)))
    assert confirmation.overall == "PARTIAL"
    assert endpoint.rpc_calls()[0]["p_feature_snapshot"] is None


def test_oos_rows_keep_their_own_path() -> None:
    endpoint = Endpoint()
    oos_id = "oosb-" + "1" * 32 + ":4H:CANDIDATE"
    row = prediction(prediction_id=oos_id, prediction_origin="SCHEDULED_SHADOW_EVIDENCE")
    _persist_work_confirmed(
        work(row, snapshots=(snapshot(oos_id),)), B9Writer(repository(endpoint))
    )
    paths = [request.url.path for request in endpoint.requests]
    assert "/rest/v1/rpc/save_prediction_bundle" not in paths
    assert "/rest/v1/predictions" in paths
