"""A watchlist change or load that fails leaves the header badge as it was.

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
(the app, through its test client), except those it cannot give: its watchlist route has no rate
limit of its own, so the 429s are scripted, and so are the network error and, for a load, a 200
that is not JSON and a 200 without a status. The watchlist's own status line and its messages
are asserted as they were: only the badge's behaviour changed.

Loading the watchlist follows the same rule. (The first round left it alone, and a failed load
still set the badge to UNAVAILABLE.) A load that fails (a network error, a server error, a rate
limit, an answer that cannot be read), or that is answered without a storage status, leaves the
badge as it was. An answered load shows the status it carries, and UNAVAILABLE is then the
backend's own word: with its store down the route still answers 200, from its fallback. A 401 ends
the session, as it does for a change. The watchlist's own line, tooltip and list read as before.
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
from crypto_probability_engine.persistence.repository import (
    InMemoryPersistenceRepository,
    PersistenceRepository,
    SupabasePersistenceRepository,
)

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
# The watchlist's own line for a list drawn from the browser, and the tooltip a failed load leaves
# on it (the error's message): both as before the load's change.
FALLBACK = "Watchlist persistence: UNAVAILABLE. Browser fallback is active."
NOT_JSON = "Response was not valid JSON."
LOAD_TITLES = {
    "networkError": "Failed to fetch",
    "serverError": "Request failed",
    "rateLimit": "Too many attempts.",
    "rateLimitWithoutABody": NOT_JSON,
    "unreadableAnswer": NOT_JSON,
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
const noRuns = { status: 200, body: { runs: [] } };
// One change (or one load), from a badge that reads `lastChecked`, answered by `reply`.
const attempt = async (lastChecked, reply, change, history = noRuns) => {
  backend = async (path) => {
    // A load also asks for the history: it answers, with no runs unless the scenario says.
    const answer = path === "/v1/runs" ? history : reply;
    if (answer === "NETWORK") throw new TypeError("Failed to fetch");
    return answer;
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
  const load = (lastChecked, reply, history) => {
    writeLocalWatchlist(["ETH/USDT"]);
    return attempt(lastChecked, reply, "load", history);
  };
  out.loaded = {};
  out.loadedWithoutItsHistory = {};
  for (const [name, { from, reply }] of Object.entries(data.loaded)) {
    out.loaded[name] = await load(from, reply);
    // The same load when its history request fails: the watchlist is drawn once, without it.
    out.loadedWithoutItsHistory[name] = await load(from, reply, "NETWORK");
  }
  out.loadedWithoutAStatus = {};
  for (const lastChecked of ["OK", "UNAVAILABLE", "STATELESS", "UNKNOWN"]) {
    for (const [name, reply] of Object.entries(data.failedLoads)) {
      out.loadedWithoutAStatus[`${lastChecked}:${name}`] = await load(lastChecked, reply);
    }
  }
  // The watchlist's status line on its own, as its callers call it: a status, or null for none.
  out.line = {};
  for (const status of ["OK", "UNAVAILABLE", "STATELESS", null]) {
    updatePersistenceStatus("UNKNOWN");
    badgeWrites.length = 0;
    setWatchlistStatus(status);
    out.line[String(status)] = {
      after: badgeState(),
      writes: [...badgeWrites],
      message: statusTarget.textContent,
    };
  }
  // Last: a 401 ends the session, and the stand-in is logged out. A signed-out load is refused
  // twice: its history request too.
  out.sessionExpired = {};
  for (const [change, reply] of Object.entries(data.sessionExpired)) {
    workspace.classList.remove("hidden");
    const outcome = await (change === "load"
      ? load("OK", reply, data.signedOutHistory)
      : attempt("OK", reply, change));
    out.sessionExpired[change] = {
      ...outcome,
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


class _BrokenRead(InMemoryPersistenceRepository):
    """A repository whose watchlist read raises: the backend answers 500."""

    def list_watchlist(self, operator_id: str = "operator") -> list[str]:
        raise RuntimeError("the watchlist read failed")


def _store_down() -> SupabasePersistenceRepository:
    """The durable repository with its store down: no connection can be opened. Nothing is
    dialled: the pool cannot be made."""

    def no_pool() -> Any:
        raise OSError("the store is down")

    return SupabasePersistenceRepository("postgresql://example.invalid/db", pool_factory=no_pool)


def _client(repository: PersistenceRepository | None = None) -> TestClient:
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


def _signed_in(repository: PersistenceRepository | None = None) -> TestClient:
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
    # A load the backend answers. UNAVAILABLE is the durable repository's own answer with its
    # store down; STATELESS is the default repository's (no store configured).
    loaded = {
        status: {"from": shown_before, "reply": _reply(_signed_in(stored).get("/v1/watchlist"))}
        for status, shown_before, stored in (
            ("OK", "UNAVAILABLE", _Repository("OK")),
            ("UNAVAILABLE", "OK", _store_down()),
            ("STATELESS", "OK", None),
        )
    }
    # A load that brings no storage status back. The backend gives the 500; the rest are scripted:
    # the network error, the 429s (the route has no rate limit of its own), a 200 that is not
    # JSON, and a 200 without a status (the backend's 200 always carries one).
    failed_loads = {
        "networkError": "NETWORK",
        "serverError": _reply(_signed_in(_BrokenRead()).get("/v1/watchlist")),
        "rateLimit": limited,
        "rateLimitWithoutABody": {"status": 429},
        "unreadableAnswer": {"status": 200},
        "answerWithoutAStatus": {"status": 200, "body": {"symbols": ["BTC/USDT"]}},
    }
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
        "failedLoads": failed_loads,
        "sessionExpired": {
            "add": _reply(signed_out.post("/v1/watchlist", json={"symbol": "BTC"})),
            "remove": _reply(signed_out.delete("/v1/watchlist/BTC/USDT")),
            "load": _reply(signed_out.get("/v1/watchlist")),
        },
        "signedOutHistory": _reply(signed_out.get("/v1/runs")),
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


def _reads(status: str) -> dict[str, str]:
    """The badge, reading `status`."""

    return {
        "text": receipts.BADGE_PREFIX + SENTENCES[status],
        "status": status,
        "classes": CLASSES[status],
    }


def test_a_watchlist_load_carries_a_storage_status_only_when_the_backend_answers_200(
    data: dict,
) -> None:
    """What each load's answer says of storage. The backend's 200 always carries its repository's
    status, UNAVAILABLE included: with its store down it answers from its fallback and says so.
    Its 500 and its 401 carry none, and neither does a scripted answer."""

    assert sorted(data["loaded"]) == ["OK", "STATELESS", "UNAVAILABLE"]
    for status, answer in data["loaded"].items():
        assert answer["reply"]["status"] == 200, status
        assert answer["reply"]["body"]["persistence_status"] == status, status
        assert answer["from"] != status, f"{status}: the badge starts on another status"
    failed = data["failedLoads"]
    assert sorted(failed) == sorted([*LOAD_TITLES, "answerWithoutAStatus"])
    assert failed["networkError"] == "NETWORK", "no answer at all"
    answered = {name: reply for name, reply in failed.items() if name != "networkError"}
    assert {name: reply["status"] for name, reply in answered.items()} == {
        "serverError": 500,
        "rateLimit": 429,
        "rateLimitWithoutABody": 429,
        "unreadableAnswer": 200,
        "answerWithoutAStatus": 200,
    }
    for name, reply in answered.items():
        assert "persistence_status" not in _keys(reply.get("body")), name
    envelope = _envelope(failed["serverError"]["body"])
    assert envelope is not None and envelope["code"] == "BACKEND_TIMEOUT"
    assert envelope["system_status_snapshot"] == {}
    assert data["sessionExpired"]["load"]["status"] == data["signedOutHistory"]["status"] == 401
    assert "persistence_status" not in _keys(data["signedOutHistory"]["body"])


@pytest.mark.parametrize("status", ["OK", "UNAVAILABLE", "STATELESS"])
def test_an_answered_watchlist_load_shows_the_storage_status_it_carries(
    run: dict, data: dict, status: str
) -> None:
    """An answered load sets the badge: the backend said what storage is. UNAVAILABLE is its own
    word here (its store is down), and the badge shows it, as before."""

    assert sorted(run["loaded"]) == sorted(run["loadedWithoutItsHistory"]) == sorted(data["loaded"])
    # With the history answered (no runs), and with the history request failing.
    for history, outcome in (
        (["No recent analysis found."], run["loaded"][status]),
        ([], run["loadedWithoutItsHistory"][status]),
    ):
        assert outcome["before"] == _reads(data["loaded"][status]["from"])
        assert outcome["writes"], "the badge was set"
        assert outcome["after"] == _reads(status)
        if status == "OK":
            # The backend's list (empty here), not the browser's.
            assert outcome["message"] == "Watchlist persistence: OK"
            assert outcome["list"] == ["No symbols yet."]
        else:
            # The browser's own list, and under its one symbol what the history answered.
            assert outcome["message"] == (
                f"Watchlist persistence: {status}. Browser fallback is active."
            )
            assert outcome["list"] == ["ETH/USDT", "Remove", *history]
        assert outcome["asked"] == ["GET /v1/runs", "GET /v1/watchlist"]


@pytest.mark.parametrize("failure", sorted(LOAD_TITLES))
def test_a_failed_watchlist_load_leaves_the_badge_as_it_was(run: dict, failure: str) -> None:
    """A load that fails brings no storage status back, whatever the reason, so the badge reads
    what it read before. Earlier every such load set it to UNAVAILABLE. The watchlist's own line,
    its tooltip and the browser's list are what they were before this change."""

    outcomes = {
        name: got
        for name, got in run["loadedWithoutAStatus"].items()
        if name.split(":")[1] == failure
    }
    assert {name.split(":")[0] for name in outcomes} == set(SENTENCES)
    for name, outcome in outcomes.items():
        last_checked = name.split(":")[0]
        assert outcome["writes"] == [], f"{name}: the badge was written to"
        assert outcome["after"] == outcome["before"] == _reads(last_checked), name
        assert outcome["message"] == FALLBACK, name
        assert outcome["title"] == LOAD_TITLES[failure], name
        # The browser's own list. The history is not drawn under it after a failed load.
        assert outcome["list"] == ["ETH/USDT", "Remove"], name
        assert outcome["asked"] == ["GET /v1/runs", "GET /v1/watchlist"], f"{name}: asked once"


def test_a_watchlist_load_answered_without_a_status_leaves_the_badge_as_it_was(run: dict) -> None:
    """A 200 that names no storage status reports none, so the badge is not written to: showing
    UNAVAILABLE would be a status nobody gave. (The backend's own 200 always carries one; this is
    an answer altered on its way.) The watchlist reads as it did for such an answer: its own line
    says UNAVAILABLE, and the browser's list is drawn with the history under it."""

    for last_checked in SENTENCES:
        outcome = run["loadedWithoutAStatus"][f"{last_checked}:answerWithoutAStatus"]
        assert outcome["writes"] == [], f"{last_checked}: the badge was written to"
        assert outcome["after"] == outcome["before"] == _reads(last_checked)
        assert outcome["message"] == FALLBACK, last_checked
        assert outcome["list"] == ["ETH/USDT", "Remove", "No recent analysis found."]
        assert outcome["asked"] == ["GET /v1/runs", "GET /v1/watchlist"], last_checked


def test_a_401_on_a_watchlist_load_ends_the_session_and_the_load_adds_nothing(run: dict) -> None:
    """A signed-out load is refused twice (its history, its watchlist). The session-expiry code,
    unchanged, resets the screen once, and that reset sets the badge to "unknown". The failed load
    then adds nothing: earlier it turned the signed-out badge to UNAVAILABLE."""

    outcome = run["sessionExpired"]["load"]
    assert outcome["login"] == receipts.EXPIRED and outcome["workspaceHidden"] is True
    assert outcome["before"] == _reads("OK")
    assert outcome["writes"] == run["recordSees"], "one badge update, the reset's"
    assert outcome["after"] == _reads("UNKNOWN")
    assert outcome["message"] == FALLBACK and outcome["title"] == "Valid session is required."
    assert outcome["asked"] == ["GET /v1/runs", "GET /v1/watchlist"]


def test_the_watchlist_line_sets_the_badge_only_from_a_status(run: dict) -> None:
    """The watchlist's status line on its own. Given a status, it sets the badge to it, once.
    Given none, it leaves the badge alone and its own words are the ones it has for a list drawn
    from the browser."""

    assert sorted(run["line"]) == ["OK", "STATELESS", "UNAVAILABLE", "null"]
    for status in ("OK", "UNAVAILABLE", "STATELESS"):
        line = run["line"][status]
        assert line["writes"] == run["recordSees"], f"{status}: one badge update"
        assert line["after"] == _reads(status)
        assert line["message"] == (
            "Watchlist persistence: OK"
            if status == "OK"
            else f"Watchlist persistence: {status}. Browser fallback is active."
        )
    none = run["line"]["null"]
    assert none["writes"] == [] and none["after"] == _reads("UNKNOWN")
    assert none["message"] == FALLBACK


def test_the_load_names_no_storage_status() -> None:
    """loadWatchlist hands on the status its answer carried, or none. It never makes one up, and
    it does not write to the badge itself."""

    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    begin = source.index("async function loadWatchlist() {")
    body = source[begin : source.index("\n}\n", begin)]
    assert '"UNAVAILABLE"' not in body and "updatePersistenceStatus" not in body
    assert "persistenceStatusBadge" not in body
    assert body.count("const status = payload.persistence_status || null;") == 1
    assert body.count("renderWatchlist(readLocalWatchlist(), null);") == 1
