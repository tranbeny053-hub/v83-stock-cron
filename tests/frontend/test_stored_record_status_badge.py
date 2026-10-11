"""A stored run's own storage status never reaches the header badge.

The header badge is storage's status when it was last asked. In Dev Mode a run's export
(GET /v1/debug/export/{run_id}) is a stored record: it carries the run's detail view, and in it the
storage status of the moment the run was made. The reader of every answer took that for storage's
status now. So exporting an earlier run could turn the badge back: storage goes down, the
watchlist's answer says UNAVAILABLE, the export of a run made before says OK, and the badge read
"Storage, last checked: Storage available". Now the export is handed to its caller, shown whole, and
not read for the badge.

A run's detail (GET /v1/analyze/detail/{run_id}) is a stored record too, and the screen asks for it
far more often: from a row of Recent Analysis, from the watchlist's latest analysis, from any Detail
button. It carries the run's own status as well, but at its top level (`debug_lite`), where the
reader does not look. That is pinned here: opening an earlier run's detail leaves the badge alone.

The answers that matter are the real backend's own (the app, through its test client, with Dev Mode
on and a repository whose reported status the test changes after the run is made): the run, the
watchlist, the history, the run list, the detail, the receipt and the export. Two are scripted: the
watchlist's history where it does not matter (no runs), and the run list of the two refused
exports. The whole of app.js runs under Node on the DOM stand-in.
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

ROOT = Path(__file__).resolve().parents[2]
DEV_CODE = "operator-dev-test-code"
# Storage's status when the run was made, and when it is exported.
CASES = {
    "madeWhileStorageWasUp": ("OK", "UNAVAILABLE"),
    "madeWhileStorageWasDown": ("UNAVAILABLE", "OK"),
    "madeWithoutStorage": ("STATELESS", "OK"),
}

_SCENARIOS = r"""
const settle = async () => {
  for (let tick = 0; tick < 8; tick += 1) await new Promise((done) => realSetTimeout(done, 0));
};
const devResult = document.querySelector("#devResult");
const noRuns = { status: 200, body: { runs: [] } };
// The watchlist says what storage is now; then the run list; then one run's export.
const exportAfterTheWatchlist = async (answers) => {
  backend = async (path) => {
    if (path === "/v1/watchlist") return answers.watchlist;
    if (path === "/v1/runs") return noRuns;
    if (path === "/v1/debug/runs") return answers.debugRuns;
    if (path === answers.exportPath) return answers.export;
    throw new Error(`unexpected request: ${path}`);
  };
  updatePersistenceStatus("UNKNOWN");
  await loadWatchlist();
  await settle();
  const now = badgeState();
  badgeWrites.length = 0;
  await loadDebugRuns();
  await settle();
  const afterTheRunList = { badge: badgeState(), writes: [...badgeWrites] };
  requests.length = 0;
  await exportDebugRun({ run_id: answers.runId }, devResult);
  await settle();
  return {
    now,
    afterTheRunList,
    after: badgeState(),
    writes: [...badgeWrites],
    shown: devResult.textContent,
    asked: requests.map((item) => `${item.method} ${item.path}`),
  };
};

// The watchlist says what storage is now; then an earlier run's detail is opened: from the run's
// own card (`from` is the answer the run was shown from), or from its row in Recent Analysis.
const detailAfterTheWatchlist = async (answers, from) => {
  backend = async (path) => {
    if (path === "/v1/watchlist") return answers.watchlist;
    if (path === "/v1/runs") return answers.runs;
    if (path === answers.detailPath) return answers.detail;
    if (path === answers.receiptPath) return answers.receipt;
    if (path === "/v1/calibration") return answers.calibration;
    throw new Error(`unexpected request: ${path}`);
  };
  updatePersistenceStatus("UNKNOWN");
  await loadWatchlist();
  await settle();
  const now = badgeState();
  badgeWrites.length = 0;
  requests.length = 0;
  await openDetail(from);
  await settle();
  return {
    now,
    after: badgeState(),
    writes: [...badgeWrites],
    panel: visibleTexts(detailPanel),
    asked: requests.map((item) => `${item.method} ${item.path}`),
  };
};

(async () => {
  // What app.js starts as it loads is over before anything is recorded.
  await settle();
  badgeWrites.length = 0;
  updatePersistenceStatus("OK");
  const out = { recordSees: [...badgeWrites], exported: {}, readAsAReport: {}, failed: {} };
  out.detailOpened = {};
  for (const [name, answers] of Object.entries(data.cases)) {
    // The history lists the run only while it is read from this process (see the data).
    const row = answers.runs.body.runs.find((item) => item.run_id === answers.runId);
    out.detailOpened[name] = {
      fromItsCard: await detailAfterTheWatchlist(answers, answers.made.body),
      fromItsHistoryRow: row ? await detailAfterTheWatchlist(answers, row) : null,
    };
    out.exported[name] = await exportAfterTheWatchlist(answers);
    // The same export read as every other answer is, a report from storage now: the reader takes
    // the run's own status. This is what the export used to do to the badge.
    badgeWrites.length = 0;
    updateStatusFromPayload(structuredClone(answers.export.body));
    out.readAsAReport[name] = { badge: badgeState(), writes: [...badgeWrites] };
  }
  for (const [name, answers] of Object.entries(data.failed)) {
    out.failed[name] = await exportAfterTheWatchlist(answers);
  }
  process.stdout.write(JSON.stringify(out), () => process.exit(0));
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
"""


def _client(repository: watchlist._Repository) -> TestClient:
    session_limiter.reset()
    dev_limiter.reset()
    settings = Settings(
        access_code_hash=hash_code(watchlist.ACCESS_CODE),
        session_signing_key="test-signing-key",
        session_cookie_secure=False,
        data_mode="fixture",
        dev_mode_enabled=True,
        dev_mode_code_hash=hash_code(DEV_CODE),
    )
    client = TestClient(create_app(settings), raise_server_exceptions=False)
    client.app.state.persistence_repository = repository
    assert client.post("/v1/auth/login", json={"code": watchlist.ACCESS_CODE}).status_code == 200
    return client


def _reported(body: dict[str, Any]) -> list[str]:
    """Every storage status an answer names where the badge's reader looks, in its order."""

    places = (
        body.get("persistence_status"),
        (body.get("debug") or {}).get("persistence_status"),
        ((body.get("detail_view") or {}).get("debug_lite") or {}).get("persistence_status"),
        (body.get("system") or {}).get("persistence_status"),
    )
    return [status for status in places if status is not None]


@pytest.fixture(scope="module")
def data() -> dict[str, Any]:
    """A run made under one storage status, then the answers given once the status has changed."""

    cases = {}
    for name, (then, now) in CASES.items():
        repository = watchlist._Repository(then)
        client = _client(repository)
        made = client.post("/v1/analyze", json={"symbol": "BTC/USDT", "timeframe": "1H"})
        assert made.status_code == 200, name
        run_id = made.json()["run_id"]
        repository._status = now
        assert client.post("/v1/auth/dev", json={"code": DEV_CODE}).status_code == 200
        cases[name] = {
            "runId": run_id,
            "made": watchlist._reply(made),
            "watchlist": watchlist._reply(client.get("/v1/watchlist")),
            "runs": watchlist._reply(client.get("/v1/runs")),
            "detailPath": f"/v1/analyze/detail/{run_id}",
            "detail": watchlist._reply(client.get(f"/v1/analyze/detail/{run_id}")),
            "receiptPath": f"/v1/analyze/receipt/{run_id}",
            "receipt": watchlist._reply(client.get(f"/v1/analyze/receipt/{run_id}")),
            "calibration": watchlist._reply(client.get("/v1/calibration")),
            "debugRuns": watchlist._reply(client.get("/v1/debug/runs")),
            "exportPath": f"/v1/debug/export/{run_id}",
            "export": watchlist._reply(client.get(f"/v1/debug/export/{run_id}")),
        }
    # An export the backend refuses: a run it does not have, and a session without Dev Mode.
    repository = watchlist._Repository("OK")
    client = _client(repository)
    made = client.post("/v1/analyze", json={"symbol": "BTC/USDT", "timeframe": "1H"})
    run_id = made.json()["run_id"]
    repository._status = "UNAVAILABLE"
    current = {
        "watchlist": watchlist._reply(client.get("/v1/watchlist")),
        "debugRuns": {"status": 200, "body": {"runs": [{"run_id": run_id}]}},
    }
    without_dev_mode = watchlist._reply(client.get(f"/v1/debug/export/{run_id}"))
    assert client.post("/v1/auth/dev", json={"code": DEV_CODE}).status_code == 200
    failed = {
        "withoutDevMode": {
            **current,
            "runId": run_id,
            "exportPath": f"/v1/debug/export/{run_id}",
            "export": without_dev_mode,
        },
        "unknownRun": {
            **current,
            "runId": "run_unknown",
            "exportPath": "/v1/debug/export/run_unknown",
            "export": watchlist._reply(client.get("/v1/debug/export/run_unknown")),
        },
    }
    return {"cases": cases, "failed": failed}


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
def test_an_export_carries_the_runs_own_status_not_storages_status_now(
    data: dict, case: str
) -> None:
    """Why the export must not be read for the badge: what it names is the status of the moment
    the run was made. The answers given now (the watchlist's) name the status now."""

    then, now = CASES[case]
    answers = data["cases"][case]
    assert then != now
    made = _reported(answers["made"]["body"])
    assert made and set(made) == {then}, "the run's own answer, when it was made"
    assert answers["export"]["status"] == 200
    assert _reported(answers["export"]["body"]) == [then], "the export: still the run's own"
    assert answers["export"]["body"]["run"]["run_id"] == answers["runId"], "that run's export"
    assert _reported(answers["watchlist"]["body"]) == [now], "what storage says now"
    assert _reported(answers["debugRuns"]["body"]) == [], "the run list names no status"
    assert answers["runId"] in [item["run_id"] for item in answers["debugRuns"]["body"]["runs"]]


@pytest.mark.parametrize("case", sorted(CASES))
def test_a_runs_detail_carries_the_runs_own_status_where_the_reader_does_not_look(
    data: dict, case: str
) -> None:
    """The detail answer is a stored record too. The run's own status is in it, at the top level
    of the detail view, and in none of the places the badge's reader looks."""

    then, now = CASES[case]
    answers = data["cases"][case]
    detail = answers["detail"]
    assert detail["status"] == 200
    assert detail["body"]["debug_lite"]["persistence_status"] == then, "the run's own status"
    assert _reported(detail["body"]) == [], "not where the badge's reader looks"
    for name in ("runs", "receipt", "calibration"):
        assert answers[name]["status"] == 200, name
        assert _reported(answers[name]["body"]) == [], f"{name}: names no status"
    # The history lists this run only while it is read from this process: with storage up it is
    # read from the store, and this test's repository keeps no rows.
    listed = [item["run_id"] for item in answers["runs"]["body"]["runs"]]
    assert listed == ([answers["runId"]] if now != "OK" else [])


@pytest.mark.parametrize("case", sorted(CASES))
def test_opening_an_earlier_runs_detail_leaves_the_badge_as_it_was(
    run: dict, data: dict, case: str
) -> None:
    """From the run's own card, and from its row in Recent Analysis where the history lists it.
    The badge keeps storage's status now; the panel shows the run's own, under its own label."""

    then, now = CASES[case]
    answers = data["cases"][case]
    opened = run["detailOpened"][case]
    assert sorted(opened) == ["fromItsCard", "fromItsHistoryRow"]
    assert (opened["fromItsHistoryRow"] is not None) == (now != "OK")
    for how, outcome in opened.items():
        if outcome is None:
            continue
        assert outcome["now"] == watchlist._reads(now), how
        assert outcome["writes"] == [], f"{how}: opening a stored run's detail wrote to the badge"
        assert outcome["after"] == watchlist._reads(now), how
        assert outcome["asked"][0] == f"GET {answers['detailPath']}", how
        panel = outcome["panel"]
        label = panel.index("Storage when requested")
        assert panel[label + 1] == watchlist.SENTENCES[then], f"{how}: the run's own status"


@pytest.mark.parametrize("case", sorted(CASES))
def test_exporting_an_earlier_run_leaves_the_badge_as_it_was(
    run: dict, data: dict, case: str
) -> None:
    then, now = CASES[case]
    answers = data["cases"][case]
    outcome = run["exported"][case]
    assert {"text", "status", "classes"} <= set(run["recordSees"]), "the record sees a badge write"
    assert outcome["now"] == watchlist._reads(now), "the watchlist's answer set the badge"
    assert outcome["afterTheRunList"] == {"badge": watchlist._reads(now), "writes": []}
    assert outcome["writes"] == [], "the export wrote to the badge"
    assert outcome["after"] == watchlist._reads(now), "the badge still reads storage's status now"
    # The export is shown whole, the run's own status in it.
    assert json.loads(outcome["shown"]) == answers["export"]["body"]
    assert _reported(json.loads(outcome["shown"])) == [then]
    assert outcome["asked"] == [f"GET {answers['exportPath']}"], "asked once"


@pytest.mark.parametrize("case", sorted(CASES))
def test_the_same_export_read_as_a_report_would_turn_the_badge_back(run: dict, case: str) -> None:
    """What the export used to do, kept as the proof that the test above is live: read as every
    other answer is, the export's body sets the badge to the run's own, older status."""

    then, now = CASES[case]
    read = run["readAsAReport"][case]
    assert read["writes"] == run["recordSees"], "one badge update"
    assert read["badge"] == watchlist._reads(then) != watchlist._reads(now)


@pytest.mark.parametrize(
    ("failure", "status", "says"),
    [
        ("withoutDevMode", 401, "Dev Mode re-auth is needed; your normal session remains active."),
        ("unknownRun", 404, "Run not found."),
    ],
)
def test_a_refused_export_leaves_the_badge_as_it_was(
    run: dict, data: dict, failure: str, status: int, says: str
) -> None:
    answers = data["failed"][failure]
    assert answers["export"]["status"] == status
    assert _reported(answers["export"]["body"]) == []
    outcome = run["failed"][failure]
    assert outcome["now"] == watchlist._reads("UNAVAILABLE")
    assert outcome["writes"] == [] and outcome["after"] == watchlist._reads("UNAVAILABLE")
    assert outcome["shown"].startswith(f"Exporting run {answers['runId']} failed: ")
    assert says in outcome["shown"]


def test_only_the_export_is_marked_a_stored_record() -> None:
    """One caller hands api a stored record. Every other answer is read as before."""

    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    assert source.count("{ storedRecord: true }") == 1
    begin = source.index("async function exportDebugRun(run, target) {")
    body = source[begin : source.index("\n}\n", begin)]
    assert "{ storedRecord: true }" in body
