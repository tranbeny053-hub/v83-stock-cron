"""A watchlist change that fails leaves the header badge as it was.

The header badge is storage's status when it was last asked. A watchlist change the backend
refuses (a rejected symbol, a full list, a malformed request, a rate limit, a server error), or
one that never reaches it (a network error), is no answer about storage, and its response carries
no storage status. So the badge is not written to: it reads what it read before. Earlier, every
such failure set it to UNAVAILABLE, and the badge then read "Storage, last checked: Storage
unavailable…" although storage had not been asked.

What still sets the badge on this path is an accepted change: its 200 answer carries the
repository's `persistence_status`, and the badge shows that one. (A 401 ends the session, and
the session's own reset puts the badge back to "unknown" with everything else.)

The whole of app.js runs under Node on the DOM stand-in. Every answer is the real backend's own
(the app, through its test client), except the two it cannot give: its watchlist route has no rate
limit of its own, so the 429s are scripted, and so is the network error. The watchlist's own
status line and its messages are asserted as they were: only the badge's behaviour changed.

Loading the watchlist is not a change and is left alone; the last test asserts it reads as it did.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import test_accepted_state_rendering as harness
import test_save_receipt_rendering as receipts
from fastapi.testclient import TestClient

from crypto_probability_engine.api.app import create_app
from crypto_probability_engine.api.auth import dev_limiter, hash_code, session_limiter
from crypto_probability_engine.api.errors import error_payload
from crypto_probability_engine.api.schemas import ErrorCode
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.persistence.repository import InMemoryPersistenceRepository

ROOT = Path(__file__).resolve().parents[2]
ACCESS_CODE = "operator-test-code"
FAILED = "Watchlist persistence: WRITE FAILED. "
NOT_SAVED = "The watchlist change could not be saved. Try again shortly."
# The watchlist's message for each failure, as before this change (watchlistFailureMessage).
MESSAGES = {
    "rejectedSymbol": NOT_SAVED,
    "fullList": NOT_SAVED,
    "malformedRequest": "The watchlist change was not accepted. Check the entry and try again.",
    "rateLimit": "Too many watchlist changes were requested. Wait a moment and try again.",
    "rateLimitWithoutABody": (
        "Too many watchlist changes were requested. Wait a moment and try again."
    ),
    "serverError": NOT_SAVED,
    "networkError": "Unable to reach the service. Check your connection and try again.",
}
SENTENCES = {
    "OK": receipts.AVAILABLE,
    "UNAVAILABLE": receipts.UNAVAILABLE,
    "STATELESS": receipts.NO_STORAGE,
    "UNKNOWN": "Storage status unknown",
}
CLASSES = {
    "OK": "status-ok",
    "UNAVAILABLE": "status-warn",
    "STATELESS": "status-warn",
    "UNKNOWN": "status-unknown",
}

_SCENARIOS = r"""
const settle = async () => {
  for (let tick = 0; tick < 8; tick += 1) await new Promise((done) => realSetTimeout(done, 0));
};
const statusTarget = document.querySelector("#watchlistStatus");
const listTarget = document.querySelector("#watchlistList");
const changes = {
  add: () => addWatchlistSymbol("BTC"),
  remove: () => removeWatchlistSymbol("BTC/USDT"),
  load: () => loadWatchlist(),
};
// One change (or one load), from a badge that reads `lastChecked`, answered by `reply`.
const attempt = async (lastChecked, reply, change) => {
  backend = async (path) => {
    // A load also asks for the history: it answers, with no runs.
    if (path === "/v1/runs") return { status: 200, body: { runs: [] } };
    if (reply === "NETWORK") throw new TypeError("Failed to fetch");
    return reply;
  };
  requests.length = 0;
  updatePersistenceStatus(lastChecked);
  statusTarget.textContent = "Watchlist persistence: OK";
  statusTarget.title = "stale";
  listTarget.replaceChildren(fakeElement("p", "", ["the list as it was"]));
  const before = badgeState();
  badgeWrites.length = 0;
  await changes[change]();
  await settle();
  return {
    before,
    after: badgeState(),
    writes: [...badgeWrites],
    message: statusTarget.textContent,
    title: statusTarget.title,
    list: visibleTexts(listTarget),
    asked: requests.map((item) => `${item.method} ${item.path}`),
  };
};

(async () => {
  // What app.js starts as it loads (its session check fails here, and sets the badge) is over
  // before anything is recorded.
  await settle();
  badgeWrites.length = 0;
  updatePersistenceStatus("OK");
  const out = { recordSees: [...badgeWrites], refused: {}, accepted: {} };
  for (const lastChecked of ["OK", "UNAVAILABLE", "STATELESS", "UNKNOWN"]) {
    for (const [name, replies] of Object.entries(data.refused)) {
      for (const [change, reply] of Object.entries(replies)) {
        out.refused[`${lastChecked}:${name}:${change}`] = await attempt(lastChecked, reply, change);
      }
    }
  }
  for (const [name, { from, replies }] of Object.entries(data.accepted)) {
    for (const [change, reply] of Object.entries(replies)) {
      out.accepted[`${name}:${change}`] = await attempt(from, reply, change);
    }
  }
  // Loading the watchlist, with one symbol in the browser's own list.
  out.loaded = {};
  for (const [name, { from, reply }] of Object.entries(data.loaded)) {
    writeLocalWatchlist(["ETH/USDT"]);
    out.loaded[name] = await attempt(from, reply, "load");
  }
  // Last: a 401 ends the session, and the stand-in is logged out.
  out.sessionExpired = {};
  for (const [change, reply] of Object.entries(data.sessionExpired)) {
    workspace.classList.remove("hidden");
    out.sessionExpired[change] = {
      ...(await attempt("OK", reply, change)),
      login: loginStatus.textContent,
      workspaceHidden: workspace.classList.contains("hidden"),
    };
  }
  process.stdout.write(JSON.stringify(out), () => process.exit(0));
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
"""


class _Repository(InMemoryPersistenceRepository):
    """The in-memory repository, reporting the storage status a test gives it."""

    def __init__(self, status: str) -> None:
        super().__init__()
        self._status = status

    def persistence_status(self) -> str:
        return self._status


class _Broken(InMemoryPersistenceRepository):
    """A repository whose watchlist writes raise: the backend answers 500."""

    def add_watchlist(self, symbol: str, operator_id: str = "operator") -> str:
        raise RuntimeError("the watchlist write failed")

    def remove_watchlist(self, symbol: str, operator_id: str = "operator") -> str:
        raise RuntimeError("the watchlist write failed")


def _client(repository: InMemoryPersistenceRepository | None = None) -> TestClient:
    session_limiter.reset()
    dev_limiter.reset()
    settings = Settings(
        access_code_hash=hash_code(ACCESS_CODE),
        session_signing_key="test-signing-key",
        session_cookie_secure=False,
        data_mode="fixture",
    )
    client = TestClient(create_app(settings), raise_server_exceptions=False)
    if repository is not None:
        client.app.state.persistence_repository = repository
    return client


def _signed_in(repository: InMemoryPersistenceRepository | None = None) -> TestClient:
    client = _client(repository)
    assert client.post("/v1/auth/login", json={"code": ACCESS_CODE}).status_code == 200
    return client


def _reply(response: Any) -> dict[str, Any]:
    return {"status": response.status_code, "body": response.json()}


@pytest.fixture(scope="module")
def data() -> dict[str, Any]:
    """The backend's own answers to a watchlist change, and the two it cannot give."""

    client = _signed_in()
    rejected = {
        "add": _reply(client.post("/v1/watchlist", json={"symbol": "$NOPE"})),
        "remove": _reply(client.delete("/v1/watchlist/$NOPE")),
    }
    malformed = {"add": _reply(client.post("/v1/watchlist", json={}))}
    for letter in "ABCDEFGHIJKLMNOPQRST":
        assert client.post("/v1/watchlist", json={"symbol": f"T{letter}X"}).status_code == 200
    full = {"add": _reply(client.post("/v1/watchlist", json={"symbol": "TUX"}))}
    broken = _signed_in(_Broken())
    server_error = {
        "add": _reply(broken.post("/v1/watchlist", json={"symbol": "BTC"})),
        "remove": _reply(broken.delete("/v1/watchlist/BTC/USDT")),
    }
    # The backend's watchlist route has no rate limit of its own. Scripted: a 429 in the
    # backend's own error envelope (its login limiter's), and one a proxy gives, without a body.
    limited = {
        "status": 429,
        "body": {
            "detail": error_payload(
                ErrorCode.UNAUTHORIZED, "Too many attempts.", retry_after_seconds=60
            )
        },
    }
    accepted = {}
    for status, shown_before in (("OK", "UNAVAILABLE"), ("UNAVAILABLE", "OK"), ("STATELESS", "OK")):
        stored = _signed_in(_Repository(status))
        accepted[status] = {
            "from": shown_before,
            "replies": {
                "add": _reply(stored.post("/v1/watchlist", json={"symbol": "BTC"})),
                "remove": _reply(stored.delete("/v1/watchlist/BTC/USDT")),
            },
        }
    loaded = {
        status: {
            "from": shown_before,
            "reply": _reply(_signed_in(_Repository(status)).get("/v1/watchlist")),
        }
        for status, shown_before in (("OK", "UNAVAILABLE"), ("UNAVAILABLE", "OK"))
    }
    loaded["networkError"] = {"from": "OK", "reply": "NETWORK"}
    loaded["rateLimit"] = {"from": "OK", "reply": limited}
    signed_out = _client()
    return {
        "refused": {
            "rejectedSymbol": rejected,
            "fullList": full,
            "malformedRequest": malformed,
            "rateLimit": {"add": limited, "remove": limited},
            "rateLimitWithoutABody": {"add": {"status": 429}, "remove": {"status": 429}},
            "serverError": server_error,
            "networkError": {"add": "NETWORK", "remove": "NETWORK"},
        },
        "accepted": accepted,
        "loaded": loaded,
        "sessionExpired": {
            "add": _reply(signed_out.post("/v1/watchlist", json={"symbol": "BTC"})),
            "remove": _reply(signed_out.delete("/v1/watchlist/BTC/USDT")),
        },
    }


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


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_keys(item) for item in value))
    return set()


def _envelope(body: dict[str, Any]) -> dict[str, Any] | None:
    detail = body.get("detail", body)
    return detail.get("error") if isinstance(detail, dict) else None


def test_the_backends_refusals_carry_no_storage_status(data: dict) -> None:
    """Why the badge has nothing to show after a refusal: the answer says nothing of storage. An
    accepted change's answer does."""

    refused = data["refused"]
    assert sorted(refused) == sorted(MESSAGES)
    assert set(refused["networkError"].values()) == {"NETWORK"}, "no answer at all"
    answered = sorted(set(refused) - {"networkError"})
    statuses = {name: {reply["status"] for reply in refused[name].values()} for name in answered}
    assert statuses == {
        "rejectedSymbol": {400},
        "fullList": {400},
        "malformedRequest": {422},
        "rateLimit": {429},
        "rateLimitWithoutABody": {429},
        "serverError": {500},
    }
    codes = {}
    for name in ("rejectedSymbol", "fullList", "malformedRequest", "serverError"):
        for change, reply in refused[name].items():
            assert "persistence_status" not in _keys(reply["body"]), (name, change)
            envelope = _envelope(reply["body"])
            if envelope is not None:
                assert envelope["system_status_snapshot"] == {}, (name, change)
                codes[name] = envelope["code"]
    assert codes == {
        "rejectedSymbol": "INVALID_SYMBOL",
        "fullList": "BATCH_LIMIT_EXCEEDED",
        "serverError": "BACKEND_TIMEOUT",
    }
    for status, answer in data["accepted"].items():
        for change, reply in answer["replies"].items():
            assert reply["status"] == 200, (status, change)
            assert reply["body"]["persistence_status"] == status, (status, change)
    for reply in data["sessionExpired"].values():
        assert reply["status"] == 401
        assert "persistence_status" not in _keys(reply["body"])


@pytest.mark.parametrize("failure", sorted(MESSAGES))
def test_a_failed_watchlist_change_leaves_the_badge_as_it_was(run: dict, failure: str) -> None:
    assert {"text", "status", "classes"} <= set(run["recordSees"]), "the record sees a badge write"
    outcomes = {name: got for name, got in run["refused"].items() if name.split(":")[1] == failure}
    changes = {name.split(":")[2] for name in outcomes}
    assert changes == (
        {"add"} if failure in ("fullList", "malformedRequest") else {"add", "remove"}
    )
    assert {name.split(":")[0] for name in outcomes} == set(SENTENCES)
    for name, outcome in outcomes.items():
        last_checked, _, change = name.split(":")
        assert outcome["writes"] == [], f"{name}: the badge was written to"
        assert outcome["after"] == outcome["before"], name
        assert outcome["after"] == {
            "text": receipts.BADGE_PREFIX + SENTENCES[last_checked],
            "status": last_checked,
            "classes": CLASSES[last_checked],
        }, name
        # The watchlist's own line says the change failed, as before; the list is not redrawn.
        assert outcome["message"] == FAILED + MESSAGES[failure], name
        assert outcome["title"] == "", name
        assert outcome["list"] == ["the list as it was"], name
        asked = "POST /v1/watchlist" if change == "add" else "DELETE /v1/watchlist/BTC%2FUSDT"
        assert outcome["asked"] == [asked], f"{name}: asked once, never again"


@pytest.mark.parametrize("status", ["OK", "UNAVAILABLE", "STATELESS"])
def test_an_accepted_watchlist_change_shows_the_storage_status_it_carries(
    run: dict, data: dict, status: str
) -> None:
    """The one case on this path that sets the badge: the backend answered, and said what storage
    is. UNAVAILABLE here is the backend's word (the store did not take the write)."""

    shown_before = data["accepted"][status]["from"]
    for change in ("add", "remove"):
        outcome = run["accepted"][f"{status}:{change}"]
        assert outcome["before"]["status"] == shown_before != status, change
        assert outcome["writes"], f"{change}: the badge was set"
        assert outcome["after"] == {
            "text": receipts.BADGE_PREFIX + SENTENCES[status],
            "status": status,
            "classes": CLASSES[status],
        }, change
        assert outcome["message"] == (
            "Watchlist persistence: OK"
            if status == "OK"
            else f"Watchlist persistence: {status}. Browser fallback is active."
        ), change
        assert outcome["list"] == (
            ["BTC/USDT", "Remove"] if change == "add" else ["No symbols yet."]
        )


def test_a_401_ends_the_session_and_the_badge_is_the_sessions_reset(run: dict) -> None:
    """The session's reset sets the badge to "unknown" once, with everything else it clears. The
    failed change then adds nothing: earlier it turned the signed-out badge to UNAVAILABLE."""

    for change in ("add", "remove"):
        outcome = run["sessionExpired"][change]
        assert outcome["login"] == receipts.EXPIRED and outcome["workspaceHidden"] is True
        assert outcome["writes"] == run["recordSees"], f"{change}: one badge update, the reset's"
        assert outcome["after"] == {
            "text": receipts.BADGE_PREFIX + SENTENCES["UNKNOWN"],
            "status": "UNKNOWN",
            "classes": CLASSES["UNKNOWN"],
        }, change
        assert outcome["message"] == (
            FAILED + "Your session is not authorized. Sign in and try the watchlist change again."
        )


def test_the_failure_handler_names_no_storage_status() -> None:
    """The handler writes the watchlist's own line and nothing else; the badge's function is
    called where a status is at hand (a 200 answer, a session reset), never with a made-up one."""

    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    start = source.index("function renderWatchlistMutationFailure(status) {")
    handler = source[start : source.index("\n}\n", start)]
    assert "updatePersistenceStatus" not in handler and "persistenceStatusBadge" not in handler
    assert handler.count(".textContent = ") == 1 and "target.textContent = " in handler
    assert 'updatePersistenceStatus("UNAVAILABLE")' not in source
    for change in ("addWatchlistSymbol", "removeWatchlistSymbol"):
        begin = source.index(f"async function {change}(")
        body = source[begin : source.index("\n}\n", begin)]
        assert body.count("renderWatchlistMutationFailure(failure?.status);") == 1, change
        assert "updatePersistenceStatus" not in body, change


def test_loading_the_watchlist_reads_as_it_did(run: dict, data: dict) -> None:
    """Loading the watchlist is not a change, and this round leaves it alone: asserted, so that
    it stays apart. An answered load shows the storage status it carries. A load that fails still
    falls back to the browser's own list and sets the badge to UNAVAILABLE, as it did before.
    Whether a failed load should leave the badge as it was, like a failed change, is not ruled."""

    fallback = "Watchlist persistence: UNAVAILABLE. Browser fallback is active."
    loaded = run["loaded"]
    assert sorted(loaded) == sorted(data["loaded"])
    for status, message, shown in (
        ("OK", "Watchlist persistence: OK", ["No symbols yet."]),
        # The browser's own list, and under its one symbol the history's answer: no runs.
        ("UNAVAILABLE", fallback, ["ETH/USDT", "Remove", "No recent analysis found."]),
    ):
        outcome = loaded[status]
        assert data["loaded"][status]["reply"]["body"]["persistence_status"] == status
        assert outcome["before"]["status"] == data["loaded"][status]["from"] != status
        assert outcome["after"]["status"] == status
        assert outcome["after"]["text"] == receipts.BADGE_PREFIX + SENTENCES[status]
        assert outcome["message"] == message and outcome["list"] == shown, status
    for failure, title in (
        ("networkError", "Failed to fetch"),
        ("rateLimit", "Too many attempts."),
    ):
        outcome = loaded[failure]
        assert outcome["before"]["status"] == "OK"
        assert outcome["after"] == {
            "text": receipts.BADGE_PREFIX + SENTENCES["UNAVAILABLE"],
            "status": "UNAVAILABLE",
            "classes": CLASSES["UNAVAILABLE"],
        }, failure
        assert outcome["message"] == fallback and outcome["title"] == title, failure
        assert outcome["list"] == ["ETH/USDT", "Remove"], failure
        assert outcome["asked"] == ["GET /v1/runs", "GET /v1/watchlist"], failure
