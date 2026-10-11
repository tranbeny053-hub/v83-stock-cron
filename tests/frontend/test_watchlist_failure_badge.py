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

A change answered 200 without a storage status follows it too. (The second round left it alone:
the badge was set to UNAVAILABLE, a status nobody gave.) The backend's own 200 always carries one,
so these answers are scripted. The browser's list is kept as before, and the watchlist's own line
reads UNAVAILABLE as before.

The watchlist line's tooltip is a failed load's error. It is cleared whenever the line is written
again, so an answered load or change no longer shows an earlier failure's error beside its words.

The third round made the rule structural. An answer's storage status reaches the badge in one
place, where every answered request is read (updateStatusFromPayload), and only text that is not
blank counts as a status there. The watchlist's own line no longer writes the badge at all. Written
from there as well, the badge took an older answer's status over a newer one when the list was
drawn a second time with its history.
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

# What an answer can carry in place of a storage status without naming one.
NOT_A_STATUS: dict[str, Any] = {
    "Null": None,
    "EmptyText": "",
    "BlankText": "  ",
    "ANumber": 7,
    "True": True,
    "AnObject": {"a": 1},
    "AList": ["OK"],
}
CHANGES_WITHOUT_A_STATUS = [
    "answerWithoutAStatus",
    *(f"answerWhoseStatusIs{name}" for name in NOT_A_STATUS),
    "answerThatIsAList",
]

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
  // A change answered 200 without a storage status, with the browser's own list set first.
  const ownList = { add: ["ETH/USDT"], remove: ["ETH/USDT", "BTC/USDT"] };
  out.changedWithoutAStatus = {};
  for (const lastChecked of ["OK", "UNAVAILABLE", "STATELESS", "UNKNOWN"]) {
    for (const [name, replies] of Object.entries(data.changesWithoutAStatus)) {
      for (const [change, reply] of Object.entries(replies)) {
        writeLocalWatchlist(ownList[change]);
        const outcome = await attempt(lastChecked, reply, change);
        outcome.kept = readLocalWatchlist();
        out.changedWithoutAStatus[`${lastChecked}:${name}:${change}`] = outcome;
      }
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
  // A load answered 200 whose status is not one (not text, or blank).
  out.loadedNamingNoStatus = {};
  out.loadedNamingNoStatusWithoutItsHistory = {};
  for (const lastChecked of ["OK", "UNAVAILABLE", "STATELESS", "UNKNOWN"]) {
    for (const [name, reply] of Object.entries(data.loadsNamingNoStatus)) {
      const key = `${lastChecked}:${name}`;
      out.loadedNamingNoStatus[key] = await load(lastChecked, reply);
      // The same load when its history request fails: the first draw is the only one.
      out.loadedNamingNoStatusWithoutItsHistory[key] = await load(lastChecked, reply, "NETWORK");
    }
  }
  // A refusal or an error whose body names a storage status (scripted: the backend's name none).
  out.failedNamingAStatus = {};
  for (const [code, reply] of Object.entries(data.failuresNamingAStatus)) {
    for (const change of ["add", "remove", "load"]) {
      out.failedNamingAStatus[`${code}:${change}`] = await (change === "load"
        ? load("OK", reply)
        : attempt("OK", reply, change));
    }
  }
  // The reader of every answer's storage status, on its own: each place an answer can name one.
  const places = {
    top: (value) => ({ persistence_status: value }),
    debug: (value) => ({ debug: { persistence_status: value } }),
    debugLite: (value) => ({ detail_view: { debug_lite: { persistence_status: value } } }),
    system: (value) => ({ system: { persistence_status: value } }),
  };
  const read = (from, payload) => {
    updatePersistenceStatus(from);
    badgeWrites.length = 0;
    updateStatusFromPayload(payload);
    return { after: badgeState(), writes: [...badgeWrites] };
  };
  out.reader = { named: {}, notNamed: {} };
  for (const [place, wrap] of Object.entries(places)) {
    for (const status of ["OK", "UNAVAILABLE", "STATELESS", "SOMETHING_NEW", " OK "]) {
      out.reader.named[`${place}:${status}`] = read("OK", wrap(status));
    }
    for (const [name, value] of Object.entries(data.notAStatus)) {
      out.reader.notNamed[`${place}:${name}`] = read("OK", wrap(value));
    }
  }
  // What is not a status in one place does not hide a status named in a later one.
  out.reader.laterPlace = read("OK", {
    persistence_status: 7,
    debug: { persistence_status: "  " },
    system: { persistence_status: "STATELESS" },
  });
  out.reader.firstPlace = read("UNKNOWN", {
    persistence_status: "OK",
    system: { persistence_status: "STATELESS" },
  });
  out.reader.nothing = read("OK", {});
  // Which place is shown when two name a status: the top, then debug, then debug_lite, then system.
  const ok = { persistence_status: "OK" };
  const other = { persistence_status: "STATELESS" };
  out.reader.order = {
    topBeforeDebug: read("UNKNOWN", { ...ok, debug: other }),
    debugBeforeDebugLite: read("UNKNOWN", { debug: ok, detail_view: { debug_lite: other } }),
    debugBeforeSystem: read("UNKNOWN", { debug: ok, system: other }),
    debugLiteBeforeSystem: read("UNKNOWN", { detail_view: { debug_lite: ok }, system: other }),
  };
  // A load answered OK whose history is still on its way; a later answer (another request's) says
  // UNAVAILABLE; then the history arrives and the list is drawn a second time.
  {
    let answerTheHistory;
    const history = new Promise((done) => { answerTheHistory = done; });
    backend = async (path) => (path === "/v1/runs" ? history : data.loaded.OK.reply);
    updatePersistenceStatus("UNKNOWN");
    writeLocalWatchlist(["ETH/USDT"]);
    const loading = loadWatchlist();
    await settle();
    const firstDraw = { badge: badgeState(), message: statusTarget.textContent };
    updateStatusFromPayload({ persistence_status: "UNAVAILABLE" });
    const laterAnswer = badgeState();
    badgeWrites.length = 0;
    answerTheHistory(noRuns);
    await loading;
    await settle();
    out.secondDraw = {
      firstDraw,
      laterAnswer,
      after: badgeState(),
      writes: [...badgeWrites],
      message: statusTarget.textContent,
      list: visibleTexts(listTarget),
    };
  }
  // The watchlist's status line on its own, as its callers call it: a status, or null for none.
  out.line = {};
  for (const status of ["OK", "UNAVAILABLE", "STATELESS", null]) {
    updatePersistenceStatus("UNKNOWN");
    statusTarget.title = "stale";
    badgeWrites.length = 0;
    setWatchlistStatus(status);
    out.line[String(status)] = {
      after: badgeState(),
      writes: [...badgeWrites],
      message: statusTarget.textContent,
      title: statusTarget.title,
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

    # A change answered 200 that names no storage status: all scripted (the backend's 200 always
    # carries one). No status at all; in its place something that is not a status (not text, or
    # blank text); and a body that is a list.
    def without_a_status(extra: dict[str, Any]) -> dict[str, Any]:
        return {
            "add": {"status": 200, "body": {"symbols": ["BTC/USDT"], **extra}},
            "remove": {"status": 200, "body": {"symbols": [], **extra}},
        }

    changes_without_a_status = {
        "answerWithoutAStatus": without_a_status({}),
        **{
            f"answerWhoseStatusIs{name}": without_a_status({"persistence_status": value})
            for name, value in NOT_A_STATUS.items()
        },
        "answerThatIsAList": {
            "add": {"status": 200, "body": ["BTC/USDT"]},
            "remove": {"status": 200, "body": []},
        },
    }
    # A refusal or an error whose body names a storage status, in every place an answer can name
    # one. Scripted: the backend's own refusals and errors name none (asserted below).
    naming = {
        "persistence_status": "UNAVAILABLE",
        "debug": {"persistence_status": "UNAVAILABLE"},
        "detail_view": {"debug_lite": {"persistence_status": "UNAVAILABLE"}},
        "system": {"persistence_status": "UNAVAILABLE"},
    }
    failures_naming_a_status = {
        str(code): {"status": code, "body": naming} for code in (400, 429, 500)
    }
    # The same for a load: a 200 whose status is not one.
    loads_naming_no_status = {
        name: {"status": 200, "body": {"symbols": ["BTC/USDT"], "persistence_status": value}}
        for name, value in NOT_A_STATUS.items()
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
        "changesWithoutAStatus": changes_without_a_status,
        "loadsNamingNoStatus": loads_naming_no_status,
        "failuresNamingAStatus": failures_naming_a_status,
        "notAStatus": NOT_A_STATUS,
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
        assert outcome["title"] == "", f"{change}: an earlier failure's tooltip is gone"
        assert outcome["list"] == (
            ["BTC/USDT", "Remove"] if change == "add" else ["No symbols yet."]
        )


@pytest.mark.parametrize("answer", CHANGES_WITHOUT_A_STATUS)
def test_a_watchlist_change_answered_without_a_status_leaves_the_badge_as_it_was(
    run: dict, data: dict, answer: str
) -> None:
    """A 200 that names no storage status reports none, so the badge is not written to. Earlier
    such an answer set it to UNAVAILABLE, a status nobody gave, or (a number, a blank) to
    "unknown". (The backend's own 200 always carries one; this is an answer altered on its way.)
    The rest is as before: the browser's own list is kept, with what the answer added to it, and
    the watchlist's line says UNAVAILABLE."""

    assert (
        sorted(data["changesWithoutAStatus"])
        == sorted({name.split(":")[1] for name in run["changedWithoutAStatus"]})
        == sorted(CHANGES_WITHOUT_A_STATUS)
    )
    for change, reply in data["changesWithoutAStatus"][answer].items():
        assert reply["status"] == 200, change
        body = reply["body"]
        named = body.get("persistence_status") if isinstance(body, dict) else None
        assert not (isinstance(named, str) and named.strip()), f"{change}: no status is named"
    outcomes = {
        name: got for name, got in run["changedWithoutAStatus"].items() if f":{answer}:" in name
    }
    assert {name.split(":")[0] for name in outcomes} == set(SENTENCES)
    assert {name.split(":")[2] for name in outcomes} == {"add", "remove"}
    # The answer's own symbol joins the browser's list on an add; a list for a body names none.
    added = ["ETH/USDT"] if answer == "answerThatIsAList" else ["ETH/USDT", "BTC/USDT"]
    for name, outcome in outcomes.items():
        last_checked, _, change = name.split(":")
        assert outcome["writes"] == [], f"{name}: the badge was written to"
        assert outcome["after"] == outcome["before"] == _reads(last_checked), name
        assert outcome["message"] == FALLBACK, name
        assert outcome["title"] == "", name
        kept = added if change == "add" else ["ETH/USDT"]
        assert outcome["kept"] == kept, f"{name}: the browser's own list"
        assert outcome["list"] == [text for symbol in kept for text in (symbol, "Remove")], name
        asked = "POST /v1/watchlist" if change == "add" else "DELETE /v1/watchlist/BTC%2FUSDT"
        assert outcome["asked"] == [asked], f"{name}: asked once, never again"


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
        # The status handed on is the answer's own, or none: never a made-up one.
        assert '"UNAVAILABLE"' not in body and "persistenceStatusBadge" not in body, change
    # The watchlist's own line does not write the badge either.
    begin = source.index("function setWatchlistStatus(status) {")
    line = source[begin : source.index("\n}\n", begin)]
    assert "updatePersistenceStatus" not in line and "persistenceStatusBadge" not in line


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
        assert outcome["title"] == "", "an earlier failed load's tooltip is gone"
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
        assert outcome["title"] == "", "the answer was read: no error to show"
        assert outcome["list"] == ["ETH/USDT", "Remove", "No recent analysis found."]
        assert outcome["asked"] == ["GET /v1/runs", "GET /v1/watchlist"], last_checked


@pytest.mark.parametrize("named", sorted(NOT_A_STATUS))
def test_a_watchlist_load_whose_status_is_not_one_leaves_the_badge_as_it_was(
    run: dict, data: dict, named: str
) -> None:
    """A load answered 200 with something in the status's place that is not a status: a number,
    a blank, an object. It names none, so the badge is left alone, and the watchlist's line reads
    UNAVAILABLE as for any list drawn from the browser. Earlier the badge went to "unknown", and
    the line printed the value ("Watchlist persistence: 7.")."""

    assert sorted(data["loadsNamingNoStatus"]) == sorted(NOT_A_STATUS)
    assert data["loadsNamingNoStatus"][named]["body"]["persistence_status"] == NOT_A_STATUS[named]
    # With the history answered (no runs), and with the history request failing: then the first
    # draw is the only one, and its line is the one read here.
    for history, outcomes in (
        (["No recent analysis found."], run["loadedNamingNoStatus"]),
        ([], run["loadedNamingNoStatusWithoutItsHistory"]),
    ):
        for last_checked in SENTENCES:
            outcome = outcomes[f"{last_checked}:{named}"]
            assert outcome["writes"] == [], f"{last_checked}: the badge was written to"
            assert outcome["after"] == outcome["before"] == _reads(last_checked)
            assert outcome["message"] == FALLBACK, last_checked
            assert outcome["title"] == "", last_checked
            assert outcome["list"] == ["ETH/USDT", "Remove", *history], last_checked
            assert outcome["asked"] == ["GET /v1/runs", "GET /v1/watchlist"], last_checked


@pytest.mark.parametrize("code", ["400", "429", "500"])
def test_a_failed_answer_that_names_a_storage_status_does_not_reach_the_badge(
    run: dict, data: dict, code: str
) -> None:
    """Only an answered request's storage status is read. A refusal or an error is not an answer
    about storage, whatever its body says: here it names UNAVAILABLE in every place an answer
    can, and the badge still reads what it read. (The backend's own refusals and errors name no
    status; this pins the rule itself.)"""

    reply = data["failuresNamingAStatus"][code]
    assert reply["status"] == int(code)
    body = reply["body"]
    named = [
        body["persistence_status"],
        body["debug"]["persistence_status"],
        body["detail_view"]["debug_lite"]["persistence_status"],
        body["system"]["persistence_status"],
    ]
    assert named == ["UNAVAILABLE"] * 4
    assert sorted(run["failedNamingAStatus"]) == sorted(
        f"{status}:{change}"
        for status in data["failuresNamingAStatus"]
        for change in ("add", "remove", "load")
    )
    for change in ("add", "remove", "load"):
        outcome = run["failedNamingAStatus"][f"{code}:{change}"]
        assert outcome["writes"] == [], f"{change}: the badge was written to"
        assert outcome["after"] == outcome["before"] == _reads("OK"), change
        # The watchlist's own line says what failed, as for any refusal or failed load.
        assert outcome["message"].startswith(FAILED if change != "load" else FALLBACK), change


def test_the_second_draw_of_the_watchlist_keeps_a_later_answers_status(run: dict) -> None:
    """The list is drawn once when the watchlist answers, and again when its history arrives. In
    between, another request's answer can report a newer storage status. The second draw used to
    write the watchlist answer's older status back over it. Now it writes nothing to the badge."""

    second = run["secondDraw"]
    assert second["firstDraw"] == {"badge": _reads("OK"), "message": "Watchlist persistence: OK"}
    assert second["laterAnswer"] == _reads("UNAVAILABLE")
    assert second["writes"] == [], "the second draw wrote to the badge"
    assert second["after"] == _reads("UNAVAILABLE"), "the later answer's status is still shown"
    # The watchlist's own line and list are the watchlist answer's, as before.
    assert second["message"] == "Watchlist persistence: OK"
    assert second["list"] == ["No symbols yet."]


def test_an_answers_storage_status_reaches_the_badge_only_when_it_names_one(run: dict) -> None:
    """The one reader of every answer's storage status (updateStatusFromPayload). Text that is
    not blank is a status, in any of the four places an answer can name one; a status the screen
    does not know is shown as unknown, not dropped, and is taken as it was sent (a padded " OK "
    is not OK). Anything else names none, and the badge is not written to. Earlier any truthy
    value was taken: a number, a list, a blank."""

    reader = run["reader"]
    places = ("top", "debug", "debugLite", "system")
    known = ("OK", "UNAVAILABLE", "STATELESS")
    not_known = ("SOMETHING_NEW", " OK ")
    assert sorted(reader["named"]) == sorted(
        f"{place}:{status}" for place in places for status in (*known, *not_known)
    )
    for place in places:
        for status in known:
            got = reader["named"][f"{place}:{status}"]
            assert got["writes"] == run["recordSees"], f"{place}:{status}: one badge update"
            assert got["after"] == _reads(status), (place, status)
        for status in not_known:
            assert reader["named"][f"{place}:{status}"]["after"] == {
                "text": receipts.BADGE_PREFIX + SENTENCES["UNKNOWN"],
                "status": status,
                "classes": CLASSES["UNKNOWN"],
            }, (place, status)
    assert sorted(reader["notNamed"]) == sorted(
        f"{place}:{name}" for place in places for name in NOT_A_STATUS
    )
    for name, got in reader["notNamed"].items():
        assert got["writes"] == [], f"{name}: the badge was written to"
        assert got["after"] == _reads("OK"), name
    assert reader["nothing"] == {"after": _reads("OK"), "writes": []}
    # The first place that names a status is the one shown; a non-status before it hides nothing.
    assert sorted(reader["order"]) == [
        "debugBeforeDebugLite",
        "debugBeforeSystem",
        "debugLiteBeforeSystem",
        "topBeforeDebug",
    ]
    for name, got in reader["order"].items():
        assert got["after"] == _reads("OK"), f"{name}: the later place's status was shown"
    assert reader["firstPlace"]["after"] == _reads("OK")
    assert reader["laterPlace"]["after"] == _reads("STATELESS")
    assert reader["laterPlace"]["writes"] == run["recordSees"]


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


def test_the_watchlist_line_never_writes_the_badge(run: dict) -> None:
    """The watchlist's status line on its own. It writes its own words and nothing else: the badge
    is written where an answer is read. Given no status, its words are the ones it has for a list
    drawn from the browser."""

    assert sorted(run["line"]) == ["OK", "STATELESS", "UNAVAILABLE", "null"]
    for status in ("OK", "UNAVAILABLE", "STATELESS"):
        line = run["line"][status]
        assert line["writes"] == [], f"{status}: the line wrote to the badge"
        assert line["after"] == _reads("UNKNOWN"), status
        assert line["message"] == (
            "Watchlist persistence: OK"
            if status == "OK"
            else f"Watchlist persistence: {status}. Browser fallback is active."
        )
    none = run["line"]["null"]
    assert none["writes"] == [] and none["after"] == _reads("UNKNOWN")
    assert none["message"] == FALLBACK
    # Written again, the line drops the tooltip it had (a failed load's error), with a status or
    # without one. A failed load sets its own afterwards.
    assert {line["title"] for line in run["line"].values()} == {""}


def test_the_load_names_no_storage_status() -> None:
    """loadWatchlist hands on the status its answer carried, or none. It never makes one up, and
    it does not write to the badge itself."""

    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    begin = source.index("async function loadWatchlist() {")
    body = source[begin : source.index("\n}\n", begin)]
    assert '"UNAVAILABLE"' not in body and "updatePersistenceStatus" not in body
    assert "persistenceStatusBadge" not in body
    assert body.count("const status = namedStorageStatus(payload.persistence_status);") == 1
    assert body.count("renderWatchlist(readLocalWatchlist(), null);") == 1
