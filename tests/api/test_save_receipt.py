"""The save receipt of one analysis (owner request, 2026-10-10; api/save_receipt.py).

The audit's finding: the storage status an analysis carries is read before the analysis and before
its background save, so a failed save still read "Storage available". `GET
/v1/analyze/receipt/{run_id}` says what happened to THIS analysis's save, and the analysis response
is unchanged.

The durable store here is production's REST writer, unchanged, over an httpx.MockTransport. A
receipt reads SAVED only when that store acknowledged the whole save, or returns the run.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import httpx
import pytest
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient

from crypto_probability_engine.api import analysis_service, commit_reconciliation, save_receipt
from crypto_probability_engine.api import app as app_module
from crypto_probability_engine.api.app import create_app
from crypto_probability_engine.api.auth import dev_limiter, hash_code, session_limiter
from crypto_probability_engine.api.errors import api_error
from crypto_probability_engine.api.save_receipt import (
    FAILED,
    NOT_RETAINED,
    PENDING,
    SAVED,
    SaveReceipts,
)
from crypto_probability_engine.api.schemas import ErrorCode
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.persistence.repository import (
    InMemoryPersistenceRepository,
    OOSArmIdentityConflict,
    SupabaseRestRepository,
)
from tests.api.test_analysis_endpoints import login, make_client
from tests.api.test_cadence_runtime_primitives import (
    EXPECTED_DEFAULT_ANALYSIS_HASH,
    EXPECTED_DEFAULT_RESPONSE_HASH,
    _selection,
)

FORECAST = "rpc/save_forecast_bundle"
KEPT = {
    "run": "INSERTED",
    "run_detail": "INSERTED",
    "prediction": "INSERTED",
    "feature_snapshot": "INSERTED",
    "derivatives_snapshot": None,
    "refused": False,
}
REFUSED = {
    "run": "CONFLICT",
    "run_detail": None,
    "prediction": None,
    "feature_snapshot": None,
    "derivatives_snapshot": None,
    "refused": True,
}
ANALYZE = {"symbol": "BTC", "analysis_mode": "METRICS_ONLY", "timeframe": "4H"}
SMOKE_CODE = "controlled-smoke-test-code"
persist = analysis_service._best_effort_persist  # noqa: SLF001
submit = analysis_service._submit_persistence_work  # noqa: SLF001


class Store:
    """A PostgREST stand-in that keeps what the forecast function kept.

    The forecast function keeps the call (KEPT), or answers `forecast` instead: an answer, a
    response or an exception. Every other write succeeds. A read returns a run only when it is
    kept under the origin that is asked for.
    """

    def __init__(self, forecast: object = KEPT) -> None:
        self.forecast = forecast
        self.kept: dict[str, tuple[str, dict | None]] = {}
        self.calls: list[tuple[str, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/rest/v1/")
        self.calls.append((request.method, path))
        if request.method == "GET":
            return self._read(path, request.url.params)
        if path != FORECAST:
            return httpx.Response(201)
        if isinstance(self.forecast, Exception):
            raise self.forecast
        if isinstance(self.forecast, httpx.Response):
            return self.forecast
        if self.forecast is not KEPT:
            return httpx.Response(200, json=self.forecast)
        body = json.loads(request.content)
        detail = body["p_run_detail"]
        self.kept[body["p_run"]["run_id"]] = (
            body["p_prediction"]["prediction_origin"],
            detail["detail_payload"] if detail is not None else None,
        )
        # The function answers for what was submitted: a part that was not sent is null.
        submitted = {"run_detail": detail, "feature_snapshot": body["p_feature_snapshot"]}
        answer = {
            key: None if submitted.get(key, True) is None else value for key, value in KEPT.items()
        }
        return httpx.Response(200, json=answer)

    def _read(self, path: str, params: httpx.QueryParams) -> httpx.Response:
        run_id = params.get("run_id", "").removeprefix("eq.")
        origin, detail = self.kept.get(run_id, (None, None))
        if path == "predictions":
            asked = params.get("prediction_origin", "").removeprefix("eq.")
            return httpx.Response(200, json=[{"run_id": run_id}] if origin == asked else [])
        if path == "analysis_run_details" and detail is not None:
            return httpx.Response(200, json=[{"run_id": run_id, "detail_payload": detail}])
        return httpx.Response(200, json=[])

    def sent(self, method: str, path: str) -> int:
        return self.calls.count((method, path))


def rest(store: Store) -> SupabaseRestRepository:
    return SupabaseRestRepository(
        "https://project.example.invalid",
        "test-key",
        client=httpx.Client(transport=httpx.MockTransport(store)),
    )


class InlineExecutor:
    """Runs a submitted save at once. A real executor keeps a job's exception in its future."""

    def submit(self, callable_, *args) -> None:
        try:
            callable_(*args)
        except Exception:
            return


class HeldExecutor:
    """Holds each submitted save until the test runs it."""

    def __init__(self) -> None:
        self.jobs: list[tuple] = []

    def submit(self, callable_, *args) -> None:
        self.jobs.append((callable_, args))

    def run(self) -> None:
        while self.jobs:
            callable_, args = self.jobs.pop(0)
            callable_(*args)


@pytest.fixture(autouse=True)
def receipts(monkeypatch: pytest.MonkeyPatch) -> SaveReceipts:
    """A fresh record, a fresh save queue, live market data and saves that run at once."""

    fresh = SaveReceipts()
    monkeypatch.setattr(save_receipt, "SAVE_RECEIPTS", fresh)
    monkeypatch.setattr(analysis_service, "_PERSISTENCE_EXECUTOR", InlineExecutor())
    capacity = analysis_service._MAX_IN_FLIGHT_PERSISTENCE_JOBS  # noqa: SLF001
    monkeypatch.setattr(
        analysis_service, "_PERSISTENCE_ADMISSION", threading.BoundedSemaphore(capacity)
    )
    # A save left unknown here must not be reconciled by another test's save, nor the reverse.
    monkeypatch.setattr(
        analysis_service, "_UNKNOWN_COMMITS", commit_reconciliation.UnknownCommits()
    )
    # Live data: only a live analysis has a forecast row, and only that can be SAVED.
    monkeypatch.setattr(analysis_service, "select_market_data", _selection())
    return fresh


def client_with(repository: object) -> TestClient:
    client = make_client()
    client.app.state.persistence_repository = repository
    login(client)
    return client


def analyze(client: TestClient) -> dict:
    response = client.post("/v1/analyze", json=ANALYZE)
    assert response.status_code == 200
    return response.json()


def receipt(client: TestClient, run_id: str) -> dict:
    response = client.get(f"/v1/analyze/receipt/{run_id}")
    assert response.status_code == 200, response.text
    return response.json()


def state(client: TestClient, run_id: str) -> str:
    return receipt(client, run_id)["state"]


def assert_run_not_found(client: TestClient, run_id: str) -> None:
    response = client.get(f"/v1/analyze/receipt/{run_id}")
    assert response.status_code == 404
    assert response.json()["detail"]["error"]["code"] == "RUN_NOT_FOUND"
    assert response.json() == {
        "detail": api_error(404, ErrorCode.RUN_NOT_FOUND, "Run not found.").detail
    }


# ------------------------------------------------------------------------ the contract


def test_an_acknowledged_durable_save_reads_saved_in_the_exact_contract() -> None:
    store = Store()
    client = client_with(rest(store))
    before = datetime.now(UTC)

    payload = analyze(client)
    body = receipt(client, payload["run_id"])

    assert set(body) == {"schema_version", "run_id", "state", "checked_at_utc"}
    assert body["schema_version"] == "save_receipt.v1"
    assert body["run_id"] == payload["run_id"]
    assert body["state"] == "SAVED"
    assert body["checked_at_utc"].endswith("Z") and "+" not in body["checked_at_utc"]
    checked = datetime.fromisoformat(body["checked_at_utc"].replace("Z", "+00:00"))
    assert checked.utcoffset() == timedelta(0)
    assert before <= checked <= datetime.now(UTC)
    assert store.sent("POST", FORECAST) == 1, "SAVED rests on the store's own acknowledgement"
    assert payload["debug"]["persistence_status"] == "OK"


@pytest.mark.parametrize(
    "forecast",
    [
        httpx.Response(503, json={"message": "database unavailable"}),
        httpx.ConnectError("connection refused"),
        REFUSED,
        {"unexpected": "answer"},
        {**KEPT, "run_detail": None},
        {**KEPT, "feature_snapshot": None},
    ],
    ids=["503", "transport-error", "refused", "unreadable", "detail-not-kept", "snapshot-not-kept"],
)
def test_a_save_the_store_did_not_acknowledge_reads_failed(forecast: object) -> None:
    """The audit's case: storage read "available" when the analysis ran, and the save failed."""

    store = Store(forecast)
    client = client_with(rest(store))

    payload = analyze(client)

    assert payload["debug"]["persistence_status"] == "OK", "the status at request time"
    assert store.sent("POST", FORECAST) == 1, "the save was sent"
    assert state(client, payload["run_id"]) == "FAILED"
    assert store.kept == {}


def test_unavailable_storage_reads_failed_and_sends_nothing() -> None:
    store = Store()
    repository = rest(store)
    repository.mark_unavailable()
    assert repository.circuit_state() == "OPEN"
    client = client_with(repository)

    payload = analyze(client)

    assert payload["debug"]["persistence_status"] == "UNAVAILABLE"
    assert state(client, payload["run_id"]) == "FAILED"
    assert store.sent("POST", FORECAST) == 0, "an open circuit sends no save"


def test_no_durable_store_reads_not_retained() -> None:
    client = make_client()
    login(client)
    assert isinstance(client.app.state.persistence_repository, InMemoryPersistenceRepository)

    payload = analyze(client)

    assert payload["debug"]["persistence_status"] == "STATELESS"
    assert state(client, payload["run_id"]) == "NOT_RETAINED"


def test_not_retained_is_known_before_the_background_save_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held = HeldExecutor()
    monkeypatch.setattr(analysis_service, "_PERSISTENCE_EXECUTOR", held)
    client = make_client()
    login(client)

    run_id = analyze(client)["run_id"]

    assert len(held.jobs) == 1 and state(client, run_id) == "NOT_RETAINED"
    held.run()
    assert state(client, run_id) == "NOT_RETAINED"


def test_without_a_repository_nothing_is_scheduled_and_the_receipt_is_not_retained() -> None:
    client = client_with(None)

    run_id = analyze(client)["run_id"]

    assert state(client, run_id) == "NOT_RETAINED"


def test_the_receipt_is_pending_until_the_background_save_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held = HeldExecutor()
    monkeypatch.setattr(analysis_service, "_PERSISTENCE_EXECUTOR", held)
    store = Store()
    client = client_with(rest(store))

    run_id = analyze(client)["run_id"]

    assert state(client, run_id) == "PENDING"
    assert store.sent("POST", FORECAST) == 0, "nothing is acknowledged yet"
    held.run()
    assert state(client, run_id) == "SAVED"


def test_the_real_executor_settles_the_receipt_from_its_own_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="receipt-test")
    monkeypatch.setattr(analysis_service, "_PERSISTENCE_EXECUTOR", executor)
    client = client_with(rest(Store()))

    run_id = analyze(client)["run_id"]
    executor.shutdown(wait=True)

    assert state(client, run_id) == "SAVED"


def test_a_pending_receipt_becomes_failed_when_the_held_save_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held = HeldExecutor()
    monkeypatch.setattr(analysis_service, "_PERSISTENCE_EXECUTOR", held)
    client = client_with(rest(Store(httpx.Response(503))))

    run_id = analyze(client)["run_id"]

    assert state(client, run_id) == "PENDING"
    held.run()
    assert state(client, run_id) == "FAILED"


def test_an_unknown_run_is_not_found_as_the_detail_route_says_it() -> None:
    durable = client_with(rest(Store()))
    assert_run_not_found(durable, "run_that_never_was")
    assert (
        durable.get("/v1/analyze/receipt/run_that_never_was").json()
        == durable.get("/v1/analyze/detail/run_that_never_was").json()
    )
    stateless = make_client()
    login(stateless)
    assert_run_not_found(stateless, "run_that_never_was")


def test_the_receipt_requires_a_session() -> None:
    client = client_with(rest(Store()))
    run_id = analyze(client)["run_id"]
    assert state(client, run_id) == "SAVED"
    client.cookies.clear()

    refused = client.get(f"/v1/analyze/receipt/{run_id}")

    assert refused.status_code == 401
    assert refused.json() == client.get(f"/v1/analyze/detail/{run_id}").json()
    assert "SAVED" not in refused.text and "save_receipt" not in refused.text


def test_reading_a_recorded_receipt_touches_no_store() -> None:
    store = Store()
    client = client_with(rest(store))
    run_id = analyze(client)["run_id"]
    calls = list(store.calls)

    assert [state(client, run_id) for _ in range(3)] == ["SAVED"] * 3

    assert store.calls == calls, "a polled receipt is answered from the record"


# ------------------------------------------------------------------------ the other origins


def smoke_client(repository: object) -> TestClient:
    session_limiter.reset()
    dev_limiter.reset()
    settings = Settings(
        access_code_hash=hash_code("operator-test-code"),
        controlled_smoke_code_hash=hash_code(SMOKE_CODE),
        session_signing_key="test-signing-key",
        session_cookie_secure=False,
        data_mode="fixture",
    )
    client = TestClient(create_app(settings))
    client.app.state.persistence_repository = repository
    assert client.post("/v1/auth/login", json={"code": SMOKE_CODE}).status_code == 200
    return client


def test_a_run_of_another_origin_is_not_found_and_is_never_recorded(
    receipts: SaveReceipts,
) -> None:
    store = Store()
    client = smoke_client(rest(store))

    run_id = analyze(client)["run_id"]

    assert store.kept[run_id][0] == "CONTROLLED_SMOKE", "it was saved, under its own origin"
    assert receipts.get(run_id) is None and len(receipts) == 0
    assert_run_not_found(client, run_id)
    assert client.get(f"/v1/analyze/detail/{run_id}").status_code == 404


def test_a_run_of_another_origin_is_not_found_even_with_a_record(
    receipts: SaveReceipts,
) -> None:
    """The visibility rule comes first: a record can never show a run the detail route hides."""

    client = client_with(rest(Store()))
    payload = analyze(client)
    client.app.state.run_store.put(
        "scheduled-run",
        {**payload, "run_id": "scheduled-run"},
        prediction_origin="SCHEDULED_SHADOW_EVIDENCE",
    )
    receipts.open("scheduled-run", SAVED)

    assert_run_not_found(client, "scheduled-run")


def test_a_stored_run_of_another_origin_is_not_found_after_a_restart() -> None:
    store = Store()
    run_id = analyze(smoke_client(rest(store)))["run_id"]
    assert run_id in store.kept

    restarted = client_with(rest(store))

    assert_run_not_found(restarted, run_id)
    assert store.sent("GET", "analysis_run_details") == 0, "its detail is never read"


# ------------------------------------------------------------------------ after a restart


def restart(monkeypatch: pytest.MonkeyPatch, repository: object) -> TestClient:
    """A new process: an empty run store and an empty record. Only the repository remains."""

    monkeypatch.setattr(save_receipt, "SAVE_RECEIPTS", SaveReceipts())
    return client_with(repository)


def test_after_a_restart_only_the_durable_store_can_say_saved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = Store()
    saved = analyze(client_with(rest(store)))["run_id"]
    store.forecast = httpx.Response(503)
    failed = analyze(client_with(rest(store)))["run_id"]

    restarted = restart(monkeypatch, rest(store))

    assert restarted.app.state.run_store.get(saved) is None
    assert state(restarted, saved) == "SAVED", "the durable store returns the run"
    assert store.sent("GET", "analysis_run_details") == 1
    # A save that failed left nothing durable: after the restart the run is simply unknown.
    assert_run_not_found(restarted, failed)


def test_after_a_restart_an_unreadable_store_proves_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = Store()
    run_id = analyze(client_with(rest(store)))["run_id"]

    class Unreadable:
        def persistence_status(self) -> str:
            return "OK"

        def get_run_detail(self, _run_id: str, *, prediction_origin: str) -> dict | None:
            raise RuntimeError("store unreachable")

    assert_run_not_found(restart(monkeypatch, Unreadable()), run_id)


def test_a_stateless_repository_never_reads_saved(monkeypatch: pytest.MonkeyPatch) -> None:
    """It answers the detail route from process memory. That is not a durable copy."""

    repository = InMemoryPersistenceRepository()
    run_id = analyze(client_with(repository))["run_id"]
    assert repository.get_run_detail(run_id, prediction_origin="USER_REQUESTED")

    same_repository_new_store = restart(monkeypatch, repository)

    assert same_repository_new_store.app.state.run_store.get(run_id) is None
    assert state(same_repository_new_store, run_id) == "NOT_RETAINED"
    assert_run_not_found(same_repository_new_store, "run_that_never_was")


def test_a_held_run_without_a_record_asks_the_store(
    receipts: SaveReceipts, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A record evicted before its run: the store decides, and no answer means FAILED."""

    store = Store()
    client = client_with(rest(store))
    kept = analyze(client)["run_id"]
    store.forecast = httpx.Response(503)
    lost = analyze(client)["run_id"]
    assert (receipts.get(kept), receipts.get(lost)) == (SAVED, FAILED)
    monkeypatch.setattr(save_receipt, "SAVE_RECEIPTS", SaveReceipts())

    assert client.app.state.run_store.get(kept) and client.app.state.run_store.get(lost)
    assert state(client, kept) == "SAVED"
    assert state(client, lost) == "FAILED"


@pytest.mark.parametrize(
    ("repository", "expected"),
    [
        (lambda: rest(Store()), "SAVED"),
        (lambda: rest(Store(httpx.Response(503))), "FAILED"),
        (lambda: None, "NOT_RETAINED"),
    ],
    ids=["saved", "failed", "no-repository"],
)
def test_a_record_still_answers_when_the_run_store_has_let_the_run_go(
    repository, expected: str
) -> None:
    """The record outlasts the run store (LIMIT): a run still on screen keeps its receipt. A
    failed save's run is in no store at all by then, so only the record can still say FAILED."""

    client = client_with(repository())
    run_id = analyze(client)["run_id"]

    client.app.state.run_store.runs.clear()

    assert client.app.state.run_store.get(run_id) is None
    assert state(client, run_id) == expected
    assert save_receipt.LIMIT > client.app.state.run_store.limit


# ------------------------------------------------------------------------ batch


def test_each_ok_item_of_a_batch_has_its_own_receipt() -> None:
    store = Store()
    client = client_with(rest(store))

    response = client.post(
        "/v1/analyze_batch",
        json={
            "requests": [
                {"symbol": "BTC", "analysis_mode": "METRICS_ONLY"},
                {"symbol": "$NOPE", "analysis_mode": "METRICS_ONLY"},
                {"symbol": "eth/usdt", "analysis_mode": "METRICS_ONLY"},
            ]
        },
    )

    items = response.json()["items"]
    assert [item["status"] for item in items] == ["OK", "ERROR", "OK"]
    run_ids = [item["run_id"] for item in items if item["status"] == "OK"]
    assert len(set(run_ids)) == 2
    assert [state(client, run_id) for run_id in run_ids] == ["SAVED", "SAVED"]
    assert set(store.kept) == set(run_ids)


def test_a_batch_item_whose_save_fails_reads_failed_beside_one_that_is_saved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held = HeldExecutor()
    monkeypatch.setattr(analysis_service, "_PERSISTENCE_EXECUTOR", held)
    store = Store()
    client = client_with(rest(store))

    response = client.post(
        "/v1/analyze_batch",
        json={"requests": [{"symbol": "BTC"}, {"symbol": "ETH"}]},
    )
    first, second = (item["run_id"] for item in response.json()["items"])
    assert [state(client, first), state(client, second)] == ["PENDING", "PENDING"]
    (first_job, second_job) = held.jobs
    held.jobs = [first_job]
    held.run()
    store.forecast = REFUSED
    held.jobs = [second_job]
    held.run()

    assert [state(client, first), state(client, second)] == ["SAVED", "FAILED"]


# ------------------------------------------------------------------------ the response is unchanged


def frozen_analysis(monkeypatch: pytest.MonkeyPatch, repository: object) -> httpx.Response:
    monkeypatch.setattr(analysis_service, "uuid4", lambda: UUID(int=73))
    monkeypatch.setattr(
        analysis_service,
        "get_cached_skill_evidence",
        lambda _timeframe: {
            "verdict": "INSUFFICIENT_EVIDENCE",
            "n": 0,
            "observed_directional_rate": None,
        },
    )
    client = make_client()
    if repository is not None:
        client.app.state.persistence_repository = repository
    login(client)
    response = client.post("/v1/analyze", json={"symbol": "BTC", "timeframe": "4H"})
    assert response.status_code == 200
    return response


def test_the_analyze_response_is_what_it_was_before_the_receipt_existed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The two hashes were pinned before this lane (test_cadence_runtime_primitives.py). The
    route's response still hashes to them, and it carries no receipt."""

    payload = frozen_analysis(monkeypatch, None).json()

    assert payload["analysis_hash"] == EXPECTED_DEFAULT_ANALYSIS_HASH
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == EXPECTED_DEFAULT_RESPONSE_HASH
    assert "save_receipt" not in payload and "saved" not in payload["decision_view"]
    assert "receipt" not in json.dumps(payload).lower()


def test_the_analyze_response_does_not_depend_on_what_becomes_of_its_save(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved = frozen_analysis(monkeypatch, rest(Store()))
    failed = frozen_analysis(monkeypatch, rest(Store(httpx.Response(503))))
    monkeypatch.setattr(app_module, "schedule_best_effort_persist", lambda *_a, **_k: None)
    never_scheduled = frozen_analysis(monkeypatch, rest(Store()))

    assert saved.content == failed.content == never_scheduled.content
    assert saved.json()["debug"]["persistence_status"] == "OK"


# ------------------------------------------------------------------------ the record


def test_the_record_is_bounded_and_evicts_the_oldest() -> None:
    record = SaveReceipts(limit=3)
    for index in range(5):
        record.open(f"run-{index}", PENDING)

    assert len(record) == 3
    assert [record.get(f"run-{index}") for index in range(5)] == [None, None, *[PENDING] * 3]
    record.settle("run-0", SAVED)
    assert record.get("run-0") is None and len(record) == 3, "settling never adds a record"
    record.open("run-2", PENDING)
    record.open("run-5", PENDING)
    assert record.get("run-3") is None and record.get("run-2") == PENDING, "reopened is newest"


def test_the_process_record_has_a_finite_bound() -> None:
    assert save_receipt.LIMIT == 500
    record = SaveReceipts()
    for index in range(save_receipt.LIMIT + 7):
        record.open(f"run-{index}", PENDING)
    assert len(record) == save_receipt.LIMIT
    with pytest.raises(ValueError, match="at least 1"):
        SaveReceipts(limit=0)
    assert len(SaveReceipts(limit=1)) == 0


def test_only_a_pending_record_is_settled_and_a_settled_state_is_final() -> None:
    record = SaveReceipts()
    record.open("pending", PENDING)
    record.open("stateless", NOT_RETAINED)

    record.settle("pending", SAVED)
    record.settle("pending", FAILED)
    record.settle("stateless", FAILED)
    record.settle("never-opened", SAVED)

    assert record.get("pending") == SAVED
    assert record.get("stateless") == NOT_RETAINED
    assert record.get("never-opened") is None and len(record) == 2


def test_the_record_is_safe_under_concurrent_writers() -> None:
    record = SaveReceipts(limit=50)

    def write(worker: int) -> None:
        for index in range(200):
            run_id = f"run-{worker}-{index}"
            record.open(run_id, PENDING)
            record.settle(run_id, SAVED)
            record.get(run_id)

    threads = [threading.Thread(target=write, args=(worker,)) for worker in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(record) == 50


def overlapped(
    record: SaveReceipts,
    held_in: str,
    first: Callable[[], None],
    second: Callable[[], None],
) -> list[tuple[str, str]]:
    """Two calls on one record that overlap for certain, with no sleep. Returns every write to the
    record's states, in order.

    `first` is held inside its own `held_in` read of the states, after the read is made, until
    `second` (on another thread) has moved: it has asked for the record's lock, where it now
    waits for `first`, or it has run to its end, which only a record without a lock lets it do.
    Either way `first` then goes on with what it read. The waits below end on those events; their
    timeouts only stop a broken run from hanging.
    """

    inside, moved = threading.Event(), threading.Event()
    lock = record._lock  # noqa: SLF001
    writes: list[tuple[str, str]] = []
    errors: list[BaseException] = []

    class AskedLock:
        def __enter__(self) -> bool:
            if inside.is_set():
                moved.set()
            return lock.__enter__()

        def __exit__(self, *exc_info: object) -> None:
            lock.__exit__(*exc_info)

    class States(OrderedDict):
        def _hold(self, read: str) -> None:
            if read == held_in and not inside.is_set():
                inside.set()
                assert moved.wait(timeout=30), "the second call never moved"

        def __setitem__(self, run_id: str, state: str) -> None:
            writes.append((run_id, state))
            super().__setitem__(run_id, state)

        def get(self, run_id: str, default: str | None = None) -> str | None:
            found = super().get(run_id, default)
            self._hold("get")
            return found

        def __len__(self) -> int:
            found = super().__len__()
            self._hold("len")
            return found

    def run(call: Callable[[], None], done: threading.Event | None) -> None:
        try:
            call()
        except BaseException as exc:  # noqa: BLE001 - reported to the test below
            errors.append(exc)
        finally:
            if done is not None:
                done.set()

    states = States(record._states)  # noqa: SLF001
    writes.clear()
    record._states, record._lock = states, AskedLock()  # noqa: SLF001
    threads = [
        threading.Thread(target=run, args=(first, None)),
        threading.Thread(target=run, args=(second, moved)),
    ]
    threads[0].start()
    assert inside.wait(timeout=30), f"the first call never read the states with {held_in}"
    threads[1].start()
    for thread in threads:
        thread.join(timeout=30)
    assert not any(thread.is_alive() for thread in threads) and errors == []
    return writes


def test_a_settled_state_is_final_when_two_settles_overlap() -> None:
    """Without the lock, the second settle would read PENDING too and write FAILED, and the first
    would then write SAVED over it: a settled state changed. With it the second waits, reads
    SAVED, and writes nothing."""

    record = SaveReceipts()
    record.open("run", PENDING)

    writes = overlapped(
        record,
        "get",
        lambda: record.settle("run", SAVED),
        lambda: record.settle("run", FAILED),
    )

    assert writes == [("run", SAVED)], "one settle wrote, once"
    assert record.get("run") == SAVED


def test_a_newly_opened_record_survives_two_opens_that_overlap() -> None:
    """Without the lock, the first open would act on a length it read before the second open made
    room, and evict once more: the record just opened would be gone. With it the second waits."""

    record = SaveReceipts(limit=1)
    record.open("oldest", PENDING)

    overlapped(
        record,
        "len",
        lambda: record.open("first", PENDING),
        lambda: record.open("second", PENDING),
    )

    assert len(record) == 1, "the bound holds, and nothing more is evicted"
    assert record.get("second") == PENDING, "the newest record is the one kept"
    assert record.get("oldest") is None and record.get("first") is None


def test_every_read_and_write_of_the_record_is_made_while_its_lock_is_held() -> None:
    """open, settle, get and len: none touches the states outside the lock."""

    record = SaveReceipts(limit=2)
    lock = record._lock  # noqa: SLF001
    touched: list[tuple[str, bool]] = []

    class States(OrderedDict):
        def __setitem__(self, run_id: str, state: str) -> None:
            touched.append(("set", lock.locked()))
            super().__setitem__(run_id, state)

        def move_to_end(self, run_id: str, last: bool = True) -> None:
            touched.append(("move", lock.locked()))
            super().move_to_end(run_id, last)

        def popitem(self, last: bool = True) -> tuple[str, str]:
            touched.append(("evict", lock.locked()))
            return super().popitem(last)

        def get(self, run_id: str, default: str | None = None) -> str | None:
            touched.append(("get", lock.locked()))
            return super().get(run_id, default)

        def __len__(self) -> int:
            touched.append(("len", lock.locked()))
            return super().__len__()

    record._states = States()  # noqa: SLF001
    touched.clear()

    for index in range(3):
        record.open(f"run-{index}", PENDING)
    opened = list(touched)
    record.settle("run-2", SAVED)
    settled = touched[len(opened) :]
    assert record.get("run-2") == SAVED
    assert len(record) == 2
    read = touched[len(opened) + len(settled) :]

    assert {name for name, _ in opened} == {"set", "move", "len", "evict"}
    assert [name for name, _ in settled] == ["get", "set"]
    assert [name for name, _ in read] == ["get", "len"]
    assert [name for name, locked in touched if not locked] == []
    assert not lock.locked()


@pytest.mark.parametrize(
    ("stateless", "held", "stored", "expected"),
    [
        (True, True, True, NOT_RETAINED),
        (True, True, False, NOT_RETAINED),
        (True, False, True, NOT_RETAINED),
        (True, False, False, None),
        (False, True, True, SAVED),
        (False, False, True, SAVED),
        (False, True, False, FAILED),
        (False, False, False, None),
    ],
)
def test_a_run_without_a_record_reads_from_the_repository_alone(
    stateless: bool, held: bool, stored: bool, expected: str | None
) -> None:
    assert save_receipt.unrecorded_state(stateless=stateless, held=held, stored=stored) == expected


def test_the_checked_time_is_utc_and_ends_in_z() -> None:
    local = datetime(2026, 10, 11, 2, 30, 5, 250000, tzinfo=timezone(timedelta(hours=7)))
    assert save_receipt.receipt_payload("run_x", SAVED, local) == {
        "schema_version": "save_receipt.v1",
        "run_id": "run_x",
        "state": "SAVED",
        "checked_at_utc": "2026-10-10T19:30:05.250000Z",
    }


# ------------------------------------------------------------------------ the wiring


def work_for(run_id: str, *, bundles: int = 1) -> analysis_service.PersistenceWork:
    ids = [f"{run_id}:{index}" for index in range(bundles)]
    return analysis_service.PersistenceWork(
        run_summary={"run_id": run_id},
        timeframe_result={"run_id": run_id, "timeframe": "4H"},
        provider_observations=(),
        prediction_rows=tuple({"prediction_id": pid, "run_id": run_id} for pid in ids),
        feature_snapshot_rows=tuple({"prediction_id": pid, "snapshot_hash": "h"} for pid in ids),
        run_detail_row={"run_id": run_id, "analysis_hash": "h", "detail_payload": {}},
    )


class Acknowledging:
    """A per-row writer (the W-B path) that acknowledges every write but the one named."""

    def __init__(self, unacknowledged: str | None = None, error: Exception | None = None) -> None:
        self.unacknowledged = unacknowledged
        self.error = error

    def _answer(self, write: str, acknowledged: str = "OK") -> str:
        if write == self.unacknowledged and self.error is not None:
            raise self.error
        return "UNAVAILABLE" if write == self.unacknowledged else acknowledged

    def persistence_status(self) -> str:
        return "OK"

    def save_run(self, _row: dict) -> str:
        return self._answer("run")

    def save_run_detail(self, _row: dict) -> str:
        return self._answer("detail")

    def save_timeframe_result(self, _row: dict) -> str:
        return "OK"

    def save_provider_observation(self, _row: dict) -> str:
        return "OK"

    def save_prediction(self, _row: dict) -> str:
        return self._answer("prediction")

    def save_feature_snapshot(self, _row: dict) -> str:
        return self._answer("snapshot", "INSERTED")


@pytest.mark.parametrize(
    ("unacknowledged", "expected"),
    [
        (None, SAVED),
        ("run", FAILED),
        ("detail", FAILED),
        ("prediction", FAILED),
        ("snapshot", FAILED),
    ],
)
def test_saved_needs_every_write_of_the_core_acknowledged(
    receipts: SaveReceipts, unacknowledged: str | None, expected: str
) -> None:
    receipts.open("receipt-run-core", PENDING)

    persist(work_for("receipt-run-core"), Acknowledging(unacknowledged))

    assert receipts.get("receipt-run-core") == expected


def test_an_analysis_without_a_forecast_row_is_never_saved(receipts: SaveReceipts) -> None:
    """Demo data has no forecast row, and History can only find a run by one."""

    receipts.open("receipt-run-demo", PENDING)

    persist(work_for("receipt-run-demo", bundles=0), Acknowledging())

    assert receipts.get("receipt-run-demo") == FAILED


def test_a_save_that_raises_reads_failed_and_still_raises(receipts: SaveReceipts) -> None:
    receipts.open("receipt-run-raises", PENDING)
    conflict = Acknowledging("run", OOSArmIdentityConflict("occupied"))

    with pytest.raises(OOSArmIdentityConflict):
        persist(work_for("receipt-run-raises"), conflict)

    assert receipts.get("receipt-run-raises") == FAILED


def test_a_refused_admission_and_a_failed_submission_read_failed(
    receipts: SaveReceipts, monkeypatch: pytest.MonkeyPatch
) -> None:
    full = threading.BoundedSemaphore(1)
    full.acquire()
    monkeypatch.setattr(analysis_service, "_PERSISTENCE_ADMISSION", full)
    receipts.open("receipt-run-refused", PENDING)

    submit(Acknowledging(), work_for("receipt-run-refused"))

    assert receipts.get("receipt-run-refused") == FAILED

    class Broken:
        def submit(self, *_args: object) -> None:
            raise RuntimeError("executor shut down")

    monkeypatch.setattr(analysis_service, "_PERSISTENCE_ADMISSION", threading.BoundedSemaphore(1))
    monkeypatch.setattr(analysis_service, "_PERSISTENCE_EXECUTOR", Broken())
    receipts.open("receipt-run-not-submitted", PENDING)

    submit(Acknowledging(), work_for("receipt-run-not-submitted"))

    assert receipts.get("receipt-run-not-submitted") == FAILED


def test_a_save_no_one_opened_a_receipt_for_leaves_no_record(
    receipts: SaveReceipts, monkeypatch: pytest.MonkeyPatch
) -> None:
    persist(work_for("receipt-run-other"), Acknowledging())
    full = threading.BoundedSemaphore(1)
    full.acquire()
    monkeypatch.setattr(analysis_service, "_PERSISTENCE_ADMISSION", full)
    submit(Acknowledging(), work_for("receipt-run-other"))

    assert len(receipts) == 0


@pytest.mark.parametrize(
    ("prediction_origin", "status", "expected"),
    [
        ("USER_REQUESTED", "OK", PENDING),
        ("USER_REQUESTED", "UNAVAILABLE", PENDING),
        ("USER_REQUESTED", "STATELESS", NOT_RETAINED),
        ("CONTROLLED_SMOKE", "OK", None),
        ("SCHEDULED_SHADOW_EVIDENCE", "OK", None),
    ],
)
def test_scheduling_opens_a_receipt_only_for_a_user_requested_run(
    receipts: SaveReceipts, prediction_origin: str, status: str, expected: str | None
) -> None:
    class Repository:
        def persistence_status(self) -> str:
            return status

    background_tasks = BackgroundTasks()

    analysis_service.schedule_best_effort_persist(
        background_tasks,
        Repository(),
        {"run_id": "receipt-run-scheduled", "detail_view": {}},
        prediction_origin=prediction_origin,
    )

    assert receipts.get("receipt-run-scheduled") == expected
    assert len(background_tasks.tasks) == 1, "the save is scheduled as before"


@pytest.mark.parametrize(
    ("prediction_origin", "expected"),
    [
        ("USER_REQUESTED", NOT_RETAINED),
        ("CONTROLLED_SMOKE", None),
        ("SCHEDULED_SHADOW_EVIDENCE", None),
    ],
)
def test_without_a_repository_a_receipt_is_opened_only_for_a_user_requested_run(
    receipts: SaveReceipts, prediction_origin: str, expected: str | None
) -> None:
    """No repository at all: nothing is scheduled, and the receipt of a run this screen can show
    is known at once. A run of another origin leaves no record here either."""

    background_tasks = BackgroundTasks()

    status = analysis_service.schedule_best_effort_persist(
        background_tasks,
        None,
        {"run_id": "receipt-run-no-repository", "detail_view": {}},
        prediction_origin=prediction_origin,
    )

    assert status == "STATELESS" and background_tasks.tasks == []
    assert receipts.get("receipt-run-no-repository") == expected
    assert len(receipts) == (0 if expected is None else 1)


def test_a_run_without_an_id_opens_no_receipt(receipts: SaveReceipts) -> None:
    class Repository:
        def persistence_status(self) -> str:
            return "OK"

    for payload in ({"detail_view": {}}, {"run_id": "", "detail_view": {}}, {"run_id": 7}):
        analysis_service.schedule_best_effort_persist(
            BackgroundTasks(), Repository(), payload, prediction_origin="USER_REQUESTED"
        )

    assert len(receipts) == 0


def test_a_broken_record_never_changes_a_save(monkeypatch: pytest.MonkeyPatch) -> None:
    class Broken:
        def open(self, *_args: object) -> None:
            raise RuntimeError("record down")

        settle = open

    quiet = persist(work_for("receipt-run-quiet"), Acknowledging())
    monkeypatch.setattr(save_receipt, "SAVE_RECEIPTS", Broken())
    background_tasks = BackgroundTasks()

    scheduled = analysis_service.schedule_best_effort_persist(
        background_tasks,
        Acknowledging(),
        {"run_id": "receipt-run-broken", "detail_view": {}},
        prediction_origin="USER_REQUESTED",
    )
    persisted = persist(work_for("receipt-run-broken"), Acknowledging())

    assert scheduled == "OK" and len(background_tasks.tasks) == 1
    assert persisted == quiet == "OK"
