"""After a batch, the header badge shows the latest storage status the batch reported.

The header badge is storage's status when it was last asked. A batch answer names no status of
its own: each result carries the one storage reported when that result's analysis began, in the
order the analyses ran. The screen took the first result's, which is the oldest. So when storage
went down part-way through a batch the badge still read "Storage, last checked: Storage
available", and when it came back the badge still read "unavailable". Now the last result's
status is the one shown.

Every answer here is the real backend's own (the app, through its test client), given by a
repository whose reported status changes while the batch runs. The whole of app.js runs under Node
on the DOM stand-in.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import test_accepted_state_rendering as harness
import test_save_receipt_rendering as receipts
import test_watchlist_failure_badge as watchlist
from fastapi.testclient import TestClient

from crypto_probability_engine.api.app import create_app
from crypto_probability_engine.api.auth import dev_limiter, hash_code, session_limiter
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.persistence.repository import InMemoryPersistenceRepository

ROOT = Path(__file__).resolve().parents[2]
SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
# What storage reports when the batch begins, and what it reports by the batch's end.
CASES = {
    "storageWentDownPartWay": ("OK", "UNAVAILABLE"),
    "storageCameBackPartWay": ("UNAVAILABLE", "OK"),
    "storageSteady": ("OK", "OK"),
    "storageAbsent": ("STATELESS", "STATELESS"),
}
# The repository changes its answer after this many questions. The backend asks storage as each
# analysis begins and again as its save is scheduled, so with three analyses the change falls
# between the first and the last. The data test below says so if that stops being true.
CHANGE_AFTER = 3

_SCENARIOS = r"""
const settle = async () => {
  for (let tick = 0; tick < 8; tick += 1) await new Promise((done) => realSetTimeout(done, 0));
};
// One batch, from a badge that reads "unknown".
const batch = async (answers) => {
  backend = async (path) => {
    if (path === "/v1/analyze_batch") return answers.batch;
    if (path in answers.receipts) return answers.receipts[path];
    if (path === "/v1/calibration") return answers.calibration;
    throw new Error(`unexpected request: ${path}`);
  };
  updatePersistenceStatus("UNKNOWN");
  badgeWrites.length = 0;
  requests.length = 0;
  await runBatchAnalysis({
    symbols: answers.symbols,
    analysisMode: "METRICS_ONLY",
    timeframe: "1H",
  });
  await settle();
  return {
    after: badgeState(),
    writes: [...badgeWrites],
    cards: document.querySelector("#batchResult").querySelectorAll(".timeframe-card").length,
    asked: requests.map((item) => `${item.method} ${item.path}`),
  };
};

(async () => {
  // What app.js starts as it loads is over before anything is recorded.
  await settle();
  badgeWrites.length = 0;
  updatePersistenceStatus("OK");
  const out = { recordSees: [...badgeWrites], batches: {} };
  for (const [name, answers] of Object.entries(data)) {
    out.batches[name] = await batch(answers);
  }
  process.stdout.write(JSON.stringify(out), () => process.exit(0));
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
"""


class _Changing(InMemoryPersistenceRepository):
    """The in-memory repository, reporting one status for its first questions and another after."""

    def __init__(self, first: str, then: str, change_after: int = CHANGE_AFTER) -> None:
        super().__init__()
        self._first = first
        self._then = then
        self._change_after = change_after
        self.asked = 0

    def persistence_status(self) -> str:
        self.asked += 1
        return self._first if self.asked <= self._change_after else self._then


def _client(repository: InMemoryPersistenceRepository) -> TestClient:
    session_limiter.reset()
    dev_limiter.reset()
    settings = Settings(
        access_code_hash=hash_code(watchlist.ACCESS_CODE),
        session_signing_key="test-signing-key",
        session_cookie_secure=False,
        data_mode="fixture",
    )
    client = TestClient(create_app(settings), raise_server_exceptions=False)
    assert client.post("/v1/auth/login", json={"code": watchlist.ACCESS_CODE}).status_code == 200
    client.app.state.persistence_repository = repository
    return client


def _named(result: dict[str, Any]) -> list[str]:
    """Every storage status a result names where the badge's reader looks."""

    places = (
        result.get("persistence_status"),
        (result.get("debug") or {}).get("persistence_status"),
        ((result.get("detail_view") or {}).get("debug_lite") or {}).get("persistence_status"),
        (result.get("system") or {}).get("persistence_status"),
    )
    return [status for status in places if status is not None]


def _batch(client: TestClient, symbols: list[str]) -> dict[str, Any]:
    requests = [
        {"symbol": symbol, "analysis_mode": "METRICS_ONLY", "timeframe": "1H"} for symbol in symbols
    ]
    answer = watchlist._reply(client.post("/v1/analyze_batch", json={"requests": requests}))
    run_ids = [result["run_id"] for result in answer["body"].get("results", [])]
    return {
        "symbols": symbols,
        "batch": answer,
        "receipts": {
            f"/v1/analyze/receipt/{run_id}": watchlist._reply(
                client.get(f"/v1/analyze/receipt/{run_id}")
            )
            for run_id in run_ids
        },
        "calibration": watchlist._reply(client.get("/v1/calibration")),
    }


@pytest.fixture(scope="module")
def data() -> dict[str, Any]:
    """A real batch for each case, and one whose every item the backend refuses."""

    batches = {
        name: _batch(_client(_Changing(first, then)), SYMBOLS)
        for name, (first, then) in CASES.items()
    }
    refused = _Changing("UNAVAILABLE", "UNAVAILABLE")
    batches["everyItemRefused"] = _batch(_client(refused), ["$NOPE", "$NADA"])
    # An ordinary batch: two symbols the backend analyses and two it refuses, in turn. A refused
    # item asks storage once (no save is scheduled), so the change falls before the second result.
    batches["someItemsRefused"] = _batch(
        _client(_Changing("OK", "UNAVAILABLE")), ["BTC/USDT", "$NOPE", "ETH/USDT", "$NADA"]
    )
    return batches


def _statuses(answer: dict[str, Any]) -> list[str]:
    """The one status each result of a batch answer names, in the results' order."""

    named = [sorted(set(_named(result))) for result in answer["body"]["results"]]
    assert all(len(one) == 1 for one in named), f"every result names one status: {named}"
    return [one[0] for one in named]


@pytest.fixture(scope="module")
def run(data: dict[str, Any]) -> dict[str, Any]:
    assert harness.NODE is not None, "node is required to run the real app.js"
    script = "\n".join(
        [
            harness._DOM_STAND_IN,
            receipts._FAKES,
            (ROOT / "frontend" / "app.js").read_text(encoding="utf-8"),
            receipts._BADGE_RECORD,
            f"const data = {json.dumps(data)};",
            _SCENARIOS,
        ]
    )
    # The script holds the whole of app.js: node reads it on stdin (conftest.py).
    done = subprocess.run(  # noqa: S603 - node on a script built here
        [harness.NODE, "-"],
        input=script,
        capture_output=True,
        encoding="utf-8",
        check=False,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr[-4000:]
    return json.loads(done.stdout)


@pytest.mark.parametrize("case", sorted(CASES))
def test_each_result_of_a_batch_names_the_status_of_its_own_moment(data: dict, case: str) -> None:
    """Why the last result is the one to show: the backend asks storage as each analysis begins,
    in order, and the batch answer names no status of its own."""

    first, then = CASES[case]
    answer = data[case]["batch"]
    assert answer["status"] == 200
    body = answer["body"]
    assert _named(body) == [], "the batch answer names no status of its own"
    assert body["errors"] == []
    assert [item["symbol"] for item in body["items"]] == SYMBOLS
    statuses = _statuses(answer)
    assert len(statuses) == len(SYMBOLS)
    assert statuses[0] == first, "the first analysis began under the first status"
    assert statuses[-1] == then, "the last analysis began under the later status"
    # Once storage's answer has changed it stays changed: the results read first..., then...
    changed = statuses.index(then)
    assert statuses == [first] * changed + [then] * (len(statuses) - changed)
    for reply in data[case]["receipts"].values():
        assert reply["status"] == 200 and _named(reply["body"]) == []


@pytest.mark.parametrize("case", sorted(CASES))
def test_a_batch_leaves_the_badge_on_the_latest_status_it_reported(
    run: dict, data: dict, case: str
) -> None:
    first, then = CASES[case]
    statuses = _statuses(data[case]["batch"])
    outcome = run["batches"][case]
    assert {"text", "status", "classes"} <= set(run["recordSees"]), "the record sees a badge write"
    assert outcome["cards"] == len(SYMBOLS), "every result is on the screen"
    assert outcome["asked"][0] == "POST /v1/analyze_batch"
    assert outcome["writes"] == run["recordSees"], "one badge update for the batch"
    assert outcome["after"] == watchlist._reads(statuses[-1]) == watchlist._reads(then), (
        f"the batch last reported {then}; its first result said {first}"
    )


def test_a_batch_with_some_items_refused_shows_its_last_results_status(
    run: dict, data: dict
) -> None:
    """One unsupported symbol among several is an ordinary batch. Its results are the analyses
    that ran, in order, and the last of them is still the latest report, wherever the refused
    items fall: here one between the two results and one after them."""

    answer = data["someItemsRefused"]["batch"]
    assert answer["status"] == 200
    body = answer["body"]
    assert [item["status"] for item in body["items"]] == ["OK", "ERROR", "OK", "ERROR"]
    assert len(body["results"]) == 2 and len(body["errors"]) == 2
    assert _named(body) == [], "the batch answer names no status of its own"
    assert _statuses(answer) == ["OK", "UNAVAILABLE"]
    outcome = run["batches"]["someItemsRefused"]
    assert outcome["cards"] == 2, "the two results are on the screen"
    assert outcome["writes"] == run["recordSees"], "one badge update for the batch"
    assert outcome["after"] == watchlist._reads("UNAVAILABLE"), "the last result's status"


def test_a_batch_whose_every_item_is_refused_leaves_the_badge_as_it_was(
    run: dict, data: dict
) -> None:
    """No analysis began to any effect: no result, so no status to show."""

    body = data["everyItemRefused"]["batch"]["body"]
    assert data["everyItemRefused"]["batch"]["status"] == 200
    assert body["results"] == [] and len(body["errors"]) == 2
    assert _named(body) == []
    outcome = run["batches"]["everyItemRefused"]
    assert outcome["writes"] == [] and outcome["after"] == watchlist._reads("UNKNOWN")
    assert outcome["cards"] == 0
