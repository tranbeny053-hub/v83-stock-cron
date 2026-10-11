"""The run list and the dev run list answer while runs are added (GET /v1/runs, /v1/debug/runs).

Both list the in-memory run store: `/v1/runs` when durable storage is not OK (its fallback, and
the only source in a process with no storage), `/v1/debug/runs` always. Neither makes a failed
listing again; only the detail and receipt routes do (tests/api/test_run_listing_retry.py). So
while the store's listing could raise when another request added a run at that moment, these two
answered 500. The store now lists under its own lock (persistence/run_store.py,
tests/persistence/test_run_store_lock.py), and they answer.

Nothing here asserts on time: the rounds, the adds and the second only end the stress, and every
other wait is a guard against a hang.
"""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from tests.api.test_analysis_endpoints import dev_login, login, make_client

RUN_LIST, DEV_RUN_LIST = "/v1/runs", "/v1/debug/runs"
USER, ANOTHER_ORIGIN = "USER_REQUESTED", "SCHEDULED_SHADOW_EVIDENCE"
WRITERS = 2
SWITCH_EVERY_SECONDS = 1e-6
# The stress ends at whichever comes first: its rounds, its second, or one writer's adds.
ROUNDS = 10
STRESS_SECONDS = 1.0
ADDS_PER_WRITER = 200_000
# No test waits this long unless the store hangs; then it fails instead of hanging the suite.
HANG_GUARD_SECONDS = 30.0


@pytest.fixture
def client() -> TestClient:
    """Signed in, with Dev Mode, over the real run store. No storage: `/v1/runs` lists the store.
    An unhandled error is answered, as a server answers it, instead of being raised here."""

    answering = TestClient(make_client().app, raise_server_exceptions=False)
    login(answering)
    dev_login(answering)
    assert type(answering.app.state.run_store) is InMemoryRunStore
    return answering


@pytest.fixture
def threads_switched_every_microsecond() -> Iterator[None]:
    """A server switches threads every five milliseconds. Every microsecond, a listing is all but
    sure to meet an add half made; the usual interval is back as soon as the test ends."""

    usual = sys.getswitchinterval()
    sys.setswitchinterval(SWITCH_EVERY_SECONDS)
    try:
        yield
    finally:
        sys.setswitchinterval(usual)


def analyzed(client: TestClient) -> str:
    response = client.post("/v1/analyze", json={"symbol": "BTC", "analysis_mode": "METRICS_ONLY"})
    assert response.status_code == 200
    return response.json()["run_id"]


def listed(client: TestClient, route: str) -> list[dict]:
    response = client.get(route)
    assert response.status_code == 200, response.text
    if route == RUN_LIST:
        assert response.json()["source"] == "in_process", "the fallback: the store is listed"
    return response.json()["runs"]


class ReadWhileARunIsAdded(dict):
    """A held analysis that stands for another request: the first time the store's listing reads
    it, another thread adds a run to the store and ends, as an analysis finishing then does."""

    def __init__(self, held: dict, store: InMemoryRunStore) -> None:
        super().__init__(held)
        self.store, self.added = store, []

    def get(self, key: str, default: object = None) -> object:
        if key == "normalized_symbol" and not self.added:
            adding = threading.Thread(
                target=self.store.put,
                args=("run-added", {**self, "run_id": "run-added"}),
                kwargs={"prediction_origin": USER},
                daemon=True,
            )
            adding.start()
            adding.join(HANG_GUARD_SECONDS)
            self.added.append("run-added" if not adding.is_alive() else "an add that had to wait")
        return super().get(key, default)


@pytest.mark.parametrize("route", [RUN_LIST, DEV_RUN_LIST])
def test_a_run_list_answers_when_a_run_is_added_while_the_store_is_listed(
    client: TestClient, route: str
) -> None:
    store = client.app.state.run_store
    older, newer = analyzed(client), analyzed(client)
    reading = ReadWhileARunIsAdded(store.get(newer), store)
    store.put(newer, reading, prediction_origin=USER)

    rows = listed(client, route)

    assert reading.added == ["run-added"], "a run was added while the store was listed"
    assert [row["run_id"] for row in rows] == [newer, older], "the store as it stood"
    assert {row["prediction_origin"] for row in rows} == {USER}
    assert [row["run_id"] for row in listed(client, route)] == ["run-added", newer, older]


def test_both_run_lists_answer_while_other_threads_add_runs(
    client: TestClient, threads_switched_every_microsecond: None
) -> None:
    store = client.app.state.run_store
    held = store.get(analyzed(client))

    def add(name: str, number: int) -> None:
        """One run in four is of another origin, and its id says so."""

        origin = ANOTHER_ORIGIN if number % 4 == 3 else USER
        run_id = f"{origin}:{name}-{number}"
        store.put(run_id, {**held, "run_id": run_id}, prediction_origin=origin)

    for number in range(store.limit):  # a full store: every later add evicts a run
        add("held", number)
    stop = threading.Event()
    failed_adds = []

    def write(writer: int) -> None:
        for number in range(ADDS_PER_WRITER):
            try:
                add(f"writer-{writer}", number)
            except Exception as error:
                failed_adds.append(f"{type(error).__name__}: {error}")
            if stop.is_set():
                return
        stop.set()

    writers = [
        threading.Thread(target=write, args=(writer,), daemon=True) for writer in range(WRITERS)
    ]
    answers = []
    end = time.monotonic() + STRESS_SECONDS
    try:
        for writer in writers:
            writer.start()
        for _round in range(ROUNDS):
            answers += [(route, client.get(route)) for route in (RUN_LIST, DEV_RUN_LIST)]
            if stop.is_set() or time.monotonic() >= end:
                break
    finally:
        stop.set()
        for writer in writers:
            writer.join(HANG_GUARD_SECONDS)

    assert not any(writer.is_alive() for writer in writers)
    assert failed_adds == []
    assert [
        (route, answer.status_code) for route, answer in answers if answer.status_code != 200
    ] == []
    for route, answer in answers:
        rows = answer.json()["runs"]
        origins = [(row["run_id"].split(":")[0], row["prediction_origin"]) for row in rows]
        if route == RUN_LIST:
            assert answer.json()["source"] == "in_process"
            assert set(origins) == {(USER, USER)}, "no run of another origin is in the run list"
        else:
            assert len(rows) == store.limit, "the whole store, not one run over or short"
            assert set(origins) == {(USER, USER), (ANOTHER_ORIGIN, ANOTHER_ORIGIN)}
    assert len(store.runs) == store.limit
    assert set(store._prediction_origins) == set(store.runs)  # noqa: SLF001
