"""The detail route and the receipt route make a failed listing of the run store again
(api/app.py, `_listed_as_user_requested`).

Both routes decide whether a held run may be shown by listing the run store. That listing used to
raise RuntimeError ("OrderedDict mutated during iteration") when another request added a run at
that moment, and the route answered 500 for a run that was there. So a listing that raises it is
made again, three attempts in all. A store that still fails is the error it always was, and no
other error is retried.

The store now lists under its own lock, and no longer raises when a run is added while it is
listed (persistence/run_store.py, tests/persistence/test_run_store_lock.py). The routes' retry
stays: it is tested here against a store made to raise, and the real store answers the first
listing.
"""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

from crypto_probability_engine.api import app as app_module
from crypto_probability_engine.api import save_receipt
from crypto_probability_engine.api.errors import api_error
from crypto_probability_engine.api.schemas import ErrorCode
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from tests.api.test_analysis_endpoints import login, make_client

ROUTES = ("/v1/analyze/detail/{run_id}", "/v1/analyze/receipt/{run_id}")
MUTATED = "OrderedDict mutated during iteration"
UNEXPECTED = api_error(500, ErrorCode.BACKEND_TIMEOUT, "Unexpected backend failure.").detail
NOT_FOUND = {"detail": api_error(404, ErrorCode.RUN_NOT_FOUND, "Run not found.").detail}
# No test waits this long unless the store hangs; then it fails instead of hanging the suite.
HANG_GUARD_SECONDS = 30.0


class ChangingRunStore(InMemoryRunStore):
    """A run store whose listing fails as the real one's did when it was changed while it was
    listed: its first `failures` listings raise, and the rest answer. `failures=None`: every
    listing raises."""

    failures = 0
    error = RuntimeError
    listings = 0

    def fail(self, failures: int | None, error: type[Exception] = RuntimeError) -> None:
        self.failures, self.error, self.listings = failures, error, 0

    def list_runs(self) -> list[dict]:
        self.listings += 1
        if self.failures is None or self.listings <= self.failures:
            raise self.error(MUTATED)
        return super().list_runs()


@pytest.fixture(autouse=True)
def receipts(monkeypatch: pytest.MonkeyPatch) -> save_receipt.SaveReceipts:
    fresh = save_receipt.SaveReceipts()
    monkeypatch.setattr(save_receipt, "SAVE_RECEIPTS", fresh)
    return fresh


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """A signed-in client over a ChangingRunStore. An unhandled error is answered, as a server
    answers it, instead of being raised into the test."""

    monkeypatch.setattr(app_module, "InMemoryRunStore", ChangingRunStore)
    answering = TestClient(make_client().app, raise_server_exceptions=False)
    login(answering)
    assert type(answering.app.state.run_store) is ChangingRunStore
    return answering


def analyzed(client: TestClient) -> str:
    response = client.post("/v1/analyze", json={"symbol": "BTC", "analysis_mode": "METRICS_ONLY"})
    assert response.status_code == 200
    return response.json()["run_id"]


def without_the_time(body: dict) -> dict:
    return {key: value for key, value in body.items() if key != "checked_at_utc"}


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("failures", [1, 2])
def test_a_listing_that_fails_is_made_again_and_the_route_answers(
    client: TestClient, route: str, failures: int
) -> None:
    store = client.app.state.run_store
    path = route.format(run_id=analyzed(client))
    undisturbed = client.get(path)
    assert undisturbed.status_code == 200 and store.listings == 1

    store.fail(failures)
    response = client.get(path)

    assert response.status_code == 200, response.text
    assert store.listings == failures + 1, "one listing for each failure, and the one that answers"
    assert without_the_time(response.json()) == without_the_time(undisturbed.json())


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("failures", [3, None], ids=["three-failures", "every-listing-fails"])
def test_a_listing_that_keeps_failing_is_still_an_error_after_three_attempts(
    client: TestClient, route: str, failures: int | None
) -> None:
    store = client.app.state.run_store
    path = route.format(run_id=analyzed(client))

    store.fail(failures)
    response = client.get(path)

    assert response.status_code == 500 and response.json() == UNEXPECTED
    assert store.listings == 3, "three attempts, and no more"
    assert app_module._RUN_LISTING_ATTEMPTS == 3  # noqa: SLF001


@pytest.mark.parametrize("route", ROUTES)
def test_the_error_that_surfaces_is_the_stores_own(
    monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    """Re-raised as it is: the server sees, logs and answers the very error it saw before."""

    monkeypatch.setattr(app_module, "InMemoryRunStore", ChangingRunStore)
    raising = make_client()
    login(raising)
    path = route.format(run_id=analyzed(raising))

    raising.app.state.run_store.fail(None)
    with pytest.raises(RuntimeError, match=MUTATED):
        raising.get(path)

    assert raising.app.state.run_store.listings == 3


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("error", [KeyError, ValueError, LookupError])
def test_no_other_error_is_retried(client: TestClient, route: str, error: type[Exception]) -> None:
    store = client.app.state.run_store
    path = route.format(run_id=analyzed(client))

    store.fail(1, error)
    response = client.get(path)

    assert response.status_code == 500 and response.json() == UNEXPECTED
    assert store.listings == 1, "only a store changed under its listing is listed again"


@pytest.mark.parametrize("route", ROUTES)
def test_a_run_of_another_origin_stays_hidden_when_the_listing_is_made_again(
    client: TestClient, route: str, receipts: save_receipt.SaveReceipts
) -> None:
    """The retry decides nothing: the visibility rule is read from the listing that answers."""

    store = client.app.state.run_store
    held = store.get(analyzed(client))
    store.put(
        "scheduled-run",
        {**held, "run_id": "scheduled-run"},
        prediction_origin="SCHEDULED_SHADOW_EVIDENCE",
    )
    receipts.open("scheduled-run", save_receipt.SAVED)

    store.fail(2)
    response = client.get(route.format(run_id="scheduled-run"))

    assert response.status_code == 404 and response.json() == NOT_FOUND
    assert store.listings == 3


@pytest.mark.parametrize("route", ROUTES)
def test_a_run_that_is_not_held_lists_nothing(client: TestClient, route: str) -> None:
    store = client.app.state.run_store
    store.fail(None)

    response = client.get(route.format(run_id="run_that_never_was"))

    assert response.status_code == 404 and response.json() == NOT_FOUND
    assert store.listings == 0, "the store is listed only for a run it holds"


class AddsARunWhenListed(dict):
    """A held analysis that stands for another request: while the store's listing reads it, a run
    is added to the store on another thread, as an analysis finishing at that moment adds one.
    `times`: how many listings it does that to."""

    def __init__(self, payload: dict, store: InMemoryRunStore, times: int) -> None:
        super().__init__(payload)
        self.store, self.times, self.added = store, times, 0

    def get(self, key: str, default: object = None) -> object:
        if key == "normalized_symbol" and self.added < self.times:
            run_id = f"run-added-{self.added + 1}"
            adding = threading.Thread(
                target=self.store.put,
                args=(run_id, {**self, "run_id": run_id}),
                kwargs={"prediction_origin": "USER_REQUESTED"},
                daemon=True,
            )
            adding.start()
            adding.join(HANG_GUARD_SECONDS)
            # An add that had to wait for the listing to end is not counted: the test then fails.
            self.added += not adding.is_alive()
        return super().get(key, default)


def held_by_the_real_store(times: int) -> tuple[TestClient, str, AddsARunWhenListed]:
    """The real run store, holding two runs: an older one, and a newer one that adds a run while
    it is listed. The listing reads the newer first, so the store changes before it is done."""

    client = TestClient(make_client().app, raise_server_exceptions=False)
    login(client)
    store = client.app.state.run_store
    assert type(store) is InMemoryRunStore
    older, newer = analyzed(client), analyzed(client)
    changing = AddsARunWhenListed(store.get(newer), store, times)
    store.put(newer, changing, prediction_origin="USER_REQUESTED")
    return client, older, changing


def test_the_real_run_store_answers_when_a_run_is_added_while_it_is_listed() -> None:
    """Before it had its lock, this listing raised RuntimeError ("... during iteration")."""

    client, older, changing = held_by_the_real_store(times=1)
    store = client.app.state.run_store

    listed = [row["run_id"] for row in store.list_runs()]

    assert changing.added == 1 and store.get("run-added-1") is not None
    assert listed == [changing["run_id"], older], "the runs it held when the listing began"
    assert [row["run_id"] for row in store.list_runs()] == ["run-added-1", *listed], "and the next"


@pytest.mark.parametrize("route", ROUTES)
def test_both_routes_answer_at_their_first_listing_when_the_real_store_changes_under_it(
    route: str,
) -> None:
    """The real store changes under every listing here, and each request answers at its first.
    Before the store had its lock, one request made all three listings and still answered 500."""

    client, older, changing = held_by_the_real_store(times=3)

    for request in (1, 2, 3):
        response = client.get(route.format(run_id=older))

        assert response.status_code == 200, response.text
        assert changing.added == request, "one listing a request, and the store changed under it"
        assert response.json()["run_id"] == older
        if "receipt" in route:
            assert response.json()["state"] == save_receipt.NOT_RETAINED
