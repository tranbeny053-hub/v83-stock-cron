"""WB3's R-1a: SupabaseRestRepository.read_core_strict, the database's own answer or None.

The owner authorized this exact pinned crossing (2026-10-03): "add read_core_strict(run_id,
prediction_ids) to persistence/repository.py with no in-memory fallback, returning only the
database answer or unreadable". No database is contacted: PostgREST is an httpx.MockTransport.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from crypto_probability_engine.persistence.repository import SupabaseRestRepository

BASE = "https://project.example.invalid"
KEY = "service-role-test-key"
RUN = {"run_id": "run-1", "analysis_hash": "hash-1"}


class Endpoint:
    """PostgREST as the strict read meets it: scripted answers per table, every request kept."""

    def __init__(self, runs=(RUN,), predictions=({"prediction_id": "run-1-4H"},), *, fail=None):
        self.answers = {"analysis_runs": list(runs), "predictions": list(predictions)}
        self.fail = fail
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        table = request.url.path.removeprefix("/rest/v1/")
        if self.fail == table:
            return httpx.Response(500, json={"message": "boom"})
        answer = self.answers.get(table)
        if answer is None:
            return httpx.Response(404)
        return httpx.Response(200, json=answer)


def _repository(endpoint: Endpoint, **options) -> SupabaseRestRepository:
    return SupabaseRestRepository(
        BASE, KEY, client=httpx.Client(transport=httpx.MockTransport(endpoint)), **options
    )


def _query(request: httpx.Request) -> dict[str, list[str]]:
    return parse_qs(urlsplit(str(request.url)).query)


def test_it_reads_the_run_and_the_expected_predictions_exactly() -> None:
    endpoint = Endpoint()
    answer = _repository(endpoint).read_core_strict("run-1", ["run-1-4H", "run-1-1D"])
    assert answer == {"run": RUN, "prediction_ids": ["run-1-4H"]}
    runs, predictions = endpoint.requests
    assert (runs.method, runs.url.path, _query(runs)) == ("GET", "/rest/v1/analysis_runs", {
        "select": ["run_id,analysis_hash"], "run_id": ["eq.run-1"], "limit": ["1"]})
    assert (predictions.method, predictions.url.path, _query(predictions)) == (
        "GET", "/rest/v1/predictions",
        {"select": ["prediction_id"], "prediction_id": ['in.("run-1-4H","run-1-1D")']})


def test_an_absent_run_is_the_database_s_answer_not_unreadable() -> None:
    answer = _repository(Endpoint(runs=(), predictions=())).read_core_strict("run-1", ["run-1-4H"])
    assert answer == {"run": None, "prediction_ids": []}


@pytest.mark.parametrize("table", ["analysis_runs", "predictions"])
def test_a_failed_read_is_unreadable_and_opens_the_circuit(table: str) -> None:
    repository = _repository(Endpoint(fail=table))
    assert repository.read_core_strict("run-1", ["run-1-4H"]) is None
    assert repository.circuit_state() == "OPEN"


def test_an_open_circuit_is_unreadable_without_a_request() -> None:
    endpoint = Endpoint(fail="analysis_runs")
    repository = _repository(endpoint)
    assert repository.read_core_strict("run-1", ["run-1-4H"]) is None
    sent = len(endpoint.requests)
    endpoint.fail = None
    assert repository.read_core_strict("run-1", ["run-1-4H"]) is None
    assert len(endpoint.requests) == sent, "an OPEN circuit sends nothing"


@pytest.mark.parametrize(
    ("runs", "predictions"),
    [
        ([RUN, {"run_id": "run-1", "analysis_hash": "hash-2"}], [{"prediction_id": "run-1-4H"}]),
        (["not-a-row"], [{"prediction_id": "run-1-4H"}]),
        ([RUN], ["not-a-row"]),
        ({"run_id": "run-1"}, [{"prediction_id": "run-1-4H"}]),
    ],
    ids=["two-runs", "run-not-a-row", "prediction-not-a-row", "not-a-list"],
)
def test_a_malformed_answer_is_unreadable_never_absent(runs, predictions) -> None:
    endpoint = Endpoint()
    endpoint.answers = {"analysis_runs": runs, "predictions": predictions}
    assert _repository(endpoint).read_core_strict("run-1", ["run-1-4H"]) is None


def test_it_never_answers_from_the_in_memory_mirror() -> None:
    """get_run falls back to the mirror on a failed read; read_core_strict never does."""

    endpoint = Endpoint(fail="analysis_runs")
    repository = _repository(endpoint)
    repository._fallback.save_run({**RUN, "symbol": "BTC"})
    assert repository.get_run("run-1") is not None, "the mirror answers get_run"
    assert repository.read_core_strict("run-1", ["run-1-4H"]) is None
    endpoint.fail = None
    readable = _repository(Endpoint(runs=(), predictions=()))
    readable._fallback.save_run({**RUN, "symbol": "BTC"})
    assert readable.read_core_strict("run-1", ["run-1-4H"]) == {"run": None, "prediction_ids": []}


def test_without_expected_predictions_only_the_run_is_read() -> None:
    endpoint = Endpoint()
    assert _repository(endpoint).read_core_strict("run-1", []) == {"run": RUN, "prediction_ids": []}
    assert [request.url.path for request in endpoint.requests] == ["/rest/v1/analysis_runs"]


def test_the_least_privilege_writer_reads_with_its_two_headers() -> None:
    endpoint = Endpoint()
    repository = _repository(endpoint, publishable_key="sb_publishable_test", writer_jwt="jwt.t.k")
    repository.read_core_strict("run-1", ["run-1-4H"])
    for request in endpoint.requests:
        assert request.headers["apikey"] == "sb_publishable_test"
        assert request.headers["Authorization"] == "Bearer jwt.t.k"
