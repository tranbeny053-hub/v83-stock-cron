"""The save receipt on screen (owner ruling D4; plan §14.2 item 4).

Whether an analysis was saved is known only after its response. Once a live analysis is shown
(a Single card, a Batch card, the Detail panel), the screen asks the backend for that analysis's
receipt and shows the backend's state in the analysis's Storage row. The frozen contract:

    GET /v1/analyze/receipt/{run_id} -> 200 {"schema_version": "save_receipt.v1", "run_id": ...,
        "state": "SAVED" | "PENDING" | "FAILED" | "NOT_RETAINED", "checked_at_utc": ...}
    404 when the run is unknown; the same session as every other endpoint.

The backend endpoint is built in another lane, so every answer here is a fake one, given to the
real app.js through a fake fetch. The analyses are real: the backend builds them. Proven:
- each state's text, on each surface, in the analysis's own row, and no other line moves;
- while PENDING, at most three further tries, each after its delay, and then no timer at all;
- a failed request, a 404, an unknown state, another schema version or another run's receipt
  leaves the row as it was;
- a reopened run, and a card that is built but not shown, ask for nothing;
- a card that is replaced takes its watch with it: its timer is cleared, a late answer ignored;
- the rows themselves (decisionViewRows) are still the request-time rows;
- the receipt's text is set as text (textContent), never as markup;
- the Overview's request-time row is labelled "Storage when requested", so it cannot be read as
  contradicting the receipt above it;
- the request-time status forecasts nothing a receipt can refute: with "Saved…" in the Storage
  row after an UNAVAILABLE status, no line on screen says the analysis is not or will not be kept;
- a receipt, in any state and on any surface, leaves the header badge untouched.
The wording is PROVISIONAL, pending the owner's approval.
"""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import test_accepted_state_rendering as harness

from crypto_probability_engine.api import analysis_service
from crypto_probability_engine.api.schemas import AnalysisRequest
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.detail.saved_run_view import attach_saved_run_view
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from crypto_probability_engine.utils.sanitize import sanitize_for_export

ROOT = Path(__file__).resolve().parents[2]
TIMEFRAMES = ("15m", "1H", "4H", "1D", "1W", "1M")
TEXT = {
    "SAVED": "Saved to Recent Analysis history",
    "PENDING": "Saving… not yet confirmed",
    # The backend's FAILED is every save it holds no acknowledgement of, one that may have
    # committed among them: the sentence says "not confirmed", never that nothing was saved.
    "FAILED": (
        "Save not confirmed: this analysis may be missing from Recent Analysis history after a "
        "restart"
    ),
    "NOT_RETAINED": "Not retained: no storage is configured",
}
WHEN_REQUESTED = "Storage when requested"
BADGE_PREFIX = "Storage, last checked: "
# The request-time status sentences. They state what storage said when it was asked and never
# forecast a save: the receipt can say "Saved…" after an UNAVAILABLE status.
AVAILABLE = "Storage available"
NO_STORAGE = "No storage configured — analyses are kept only until the server restarts"
UNAVAILABLE = (
    "Storage unavailable when requested — this analysis may not be kept in Recent Analysis history"
)
EXPIRED = "Your session expired. Please sign in again."

# A backend that answers what each scenario scripts, and timers a scenario can read and fire.
# Placed before app.js, so everything app.js asks for or schedules is seen.
_FAKES = r"""
const RECEIPT = "/v1/analyze/receipt/";
const WHEN_REQUESTED = "Storage when requested";
const requests = [];
const noBackend = () => { throw new Error("no backend behind the DOM stand-in"); };
let backend = noBackend;
globalThis.fetch = async (path, options = {}) => {
  requests.push({ path: String(path), method: options.method || "GET" });
  const reply = await backend(String(path), options);
  return {
    ok: reply.status >= 200 && reply.status < 300,
    status: reply.status,
    json: async () => {
      if (reply.body === undefined) throw new SyntaxError("not JSON");
      return structuredClone(reply.body);
    },
  };
};
const realSetTimeout = setTimeout;
const timers = [];
let timerIds = 0;
globalThis.setTimeout = (callback, delay) => {
  timerIds += 1;
  timers.push({ id: timerIds, callback, delay, cleared: false, fired: false });
  return timerIds;
};
globalThis.clearTimeout = (id) => {
  const timer = timers.find((item) => item.id === id);
  if (timer) timer.cleared = true;
};
// The stand-in matches an attribute selector by its name alone and knows no parentElement. A
// Single run finds the card it replaces by its data value, in its parent, as a browser does.
const matchesByName = FakeElement.prototype.matches;
FakeElement.prototype.matches = function (selector) {
  const data = /^\[data-([a-z-]+)="([^"]*)"\]$/.exec(selector);
  if (!data) return matchesByName.call(this, selector);
  const key = data[1].replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
  return this.dataset[key] === data[2];
};
Object.defineProperty(FakeElement.prototype, "parentElement", {
  get() { return this.parent; },
});
// The stand-in reads innerHTML as text, so a cell set as markup would show the same words. This
// record tells the two apart: every element whose content was set as markup.
const writtenAsMarkup = new Set();
const setAsMarkup = Object.getOwnPropertyDescriptor(FakeElement.prototype, "innerHTML").set;
Object.defineProperty(FakeElement.prototype, "innerHTML", {
  configurable: true,
  set(value) {
    writtenAsMarkup.add(this);
    setAsMarkup.call(this, value);
  },
});
"""

# Placed after app.js: a record of every write to the header badge (its text, its status, its
# classes). It is kept on the element itself, so a write that leaves the same words is seen too.
_BADGE_RECORD = r"""
const badgeWrites = [];
{
  const text = Object.getOwnPropertyDescriptor(FakeElement.prototype, "textContent");
  Object.defineProperty(persistenceStatusBadge, "textContent", {
    get() { return text.get.call(this); },
    set(value) {
      badgeWrites.push("text");
      text.set.call(this, value);
    },
  });
  let classes = persistenceStatusBadge.className;
  Object.defineProperty(persistenceStatusBadge, "className", {
    get: () => classes,
    set(value) {
      badgeWrites.push("classes");
      classes = value;
    },
  });
  persistenceStatusBadge.dataset = new Proxy(persistenceStatusBadge.dataset, {
    set(target, key, value) {
      badgeWrites.push("status");
      target[key] = value;
      return true;
    },
  });
}
const badgeState = () => ({
  text: persistenceStatusBadge.textContent,
  status: persistenceStatusBadge.dataset.persistenceStatus,
  classes: persistenceStatusBadge.className,
});
"""

_SCENARIOS = r"""
const skipped = ["raw-json", "calibration-timeframe-card"];
const settle = async () => {
  for (let tick = 0; tick < 8; tick += 1) await new Promise((done) => realSetTimeout(done, 0));
};
const receiptBody = (runId, state, extra = {}) => ({
  schema_version: "save_receipt.v1",
  run_id: runId,
  state,
  checked_at_utc: "2026-10-10T12:00:00Z",
  ...extra,
});
const notFound = {
  status: 404,
  body: { detail: { error: { code: "RUN_NOT_FOUND", message: "Run not found." } } },
};
// scripts: run id -> the replies its receipt requests get, in order (the last one repeats). A
// state's name is a well-formed receipt in that state. An unknown run gets the contract's 404.
const serve = (scripts, others = () => undefined) => {
  backend = async (path, options) => {
    if (path.startsWith(RECEIPT)) {
      const runId = decodeURIComponent(path.slice(RECEIPT.length));
      const replies = scripts[runId];
      if (!replies) return notFound;
      const reply = replies.length > 1 ? replies.shift() : replies[0];
      if (reply === "NETWORK") throw new Error("network down");
      if (typeof reply === "string") return { status: 200, body: receiptBody(runId, reply) };
      return typeof reply === "function" ? reply() : reply;
    }
    const other = others(path, options);
    if (other === undefined) throw new Error("no backend behind the DOM stand-in");
    return other;
  };
};
const asked = () =>
  requests
    .filter((item) => item.path.startsWith(RECEIPT))
    .map((item) => item.path.slice(RECEIPT.length));
const receiptTimers = () => timers.filter((timer) => timer.callback !== updateRefreshButton);
const pending = () => receiptTimers().filter((timer) => !timer.cleared && !timer.fired);
const fire = async (timer) => {
  timer.fired = true;
  timer.callback();
  await settle();
};
const fireAll = async () => {
  for (let round = 0; round < 10 && pending().length; round += 1) await fire(pending()[0]);
};
const watches = () => [...saveReceiptWatches.values()].reduce((sum, set) => sum + set.size, 0);
const cleared = () => receiptTimers().map((timer) => timer.cleared);
const reset = () => {
  cancelAllSaveReceipts();
  hideDetail();
  calibrationDiagnosticsCache = null;
  calibrationDiagnosticsCachedAt = 0;
  requests.length = 0;
  timers.length = 0;
  backend = noBackend;
};
const storageText = (node) => {
  const texts = visibleTexts(node, skipped);
  return texts[texts.indexOf("Storage") + 1];
};
const watchState = () => ({
  asked: asked(),
  pending: pending().map((timer) => timer.delay),
  watches: watches(),
});
const showDetail = async (payload, scripts) => {
  reset();
  serve(scripts);
  renderStructuredDetail(payload, payload.detail_view);
  await settle();
};
const analyzeFrom = (path, options) =>
  path === "/v1/analyze"
    ? { status: 200, body: data.analyses[JSON.parse(options.body).timeframe] }
    : undefined;
const runSingle = () =>
  runTimeframeSet({
    symbol: "BTC/USDT",
    analysisMode: "METRICS_ONLY",
    target: singleResult,
    loadingSelector: "#singleLoading",
    payloadStore: singlePayloads,
  });
const singleRows = () =>
  Object.fromEntries(
    singleResult
      .querySelectorAll(".horizon-card")
      .map((card) => [card.dataset.timeframeCard, storageText(card)]),
  );
const batchTarget = () => document.querySelector("#batchResult");
const batchRows = () =>
  batchTarget()
    .querySelectorAll(".timeframe-card")
    .map((card) => [card.dataset.runId, storageText(card)]);
const batchOf = (payloads, items) => (path) =>
  path === "/v1/analyze_batch"
    ? { status: 200, body: { results: payloads, errors: [], items } }
    : undefined;
const runBatch = () =>
  runBatchAnalysis({ symbols: ["ETH", "BTC"], analysisMode: "METRICS_ONLY", timeframe: "1H" });

const scenarios = {
  // Each state on the Detail panel, over one analysis whose request-time row reads the same.
  async detailStates() {
    const payload = data.stored.OK;
    await showDetail(payload, {});
    const out = { unanswered: visibleTexts(detailPanel, skipped), unansweredState: watchState() };
    for (const name of ["SAVED", "PENDING", "FAILED", "NOT_RETAINED"]) {
      const before = JSON.stringify(decisionViewRows(payload, payload.decision_view));
      await showDetail(payload, { [payload.run_id]: [name] });
      out[name] = {
        ...watchState(),
        shown: visibleTexts(detailPanel, skipped),
        rows: decisionViewRows(payload, payload.decision_view),
        rowsUnchanged: JSON.stringify(decisionViewRows(payload, payload.decision_view)) === before,
      };
    }
    return out;
  },

  // The state shown is the backend's, whatever storage said when the analysis was requested.
  async backendStateOnly() {
    const out = {};
    for (const [storageAtRequest, name] of [["UNAVAILABLE", "SAVED"], ["OK", "NOT_RETAINED"]]) {
      const payload = data.stored[storageAtRequest];
      await showDetail(payload, { [payload.run_id]: [name] });
      const texts = visibleTexts(detailPanel, skipped);
      const rowsLabelled = (label) => texts.filter((text) => text === label).length;
      out[`${storageAtRequest}_${name}`] = {
        storage: storageText(detailPanel),
        whenRequested: texts[texts.indexOf(WHEN_REQUESTED) + 1],
        labels: ["Storage", WHEN_REQUESTED, "Persistence"].map(rowsLabelled),
      };
    }
    return out;
  },

  // Single: six cards, each asked for once, each given its own analysis's state.
  async single() {
    reset();
    const id = (timeframe) => data.analyses[timeframe].run_id;
    serve(
      {
        [id("15m")]: ["SAVED"],
        [id("1H")]: ["PENDING", "SAVED"],
        [id("4H")]: ["FAILED"],
        [id("1D")]: ["NOT_RETAINED"],
        [id("1M")]: ["NETWORK"],
      },
      analyzeFrom,
    );
    await runSingle();
    await settle();
    const first = { rows: singleRows(), ...watchState() };
    await fireAll();
    return {
      first,
      after: { rows: singleRows(), ...watchState() },
      analyzed: requests.filter((item) => item.path === "/v1/analyze").length,
      cards: singleResult.querySelectorAll(".horizon-card").length,
    };
  },

  // Batch: the cards are in the items' order, the results in another; an item failed between.
  async batch() {
    reset();
    const [first, second, third] = ["1H", "4H", "1D"].map((name) => data.analyses[name]);
    const failed = { error: { code: "INVALID_SYMBOL", message: "Unsupported." } };
    serve(
      { [first.run_id]: ["SAVED"], [second.run_id]: ["FAILED"], [third.run_id]: ["PENDING"] },
      batchOf(
        [first, second, third],
        [
          { index: 0, symbol: "ETH", status: "OK", run_id: third.run_id },
          { index: 1, symbol: "$NOPE", status: "ERROR", detail: failed },
          { index: 2, symbol: "BTC", status: "OK", run_id: first.run_id },
          { index: 3, symbol: "SOL", status: "OK", run_id: second.run_id },
        ],
      ),
    );
    await runBatch();
    await settle();
    return {
      rows: batchRows(),
      ...watchState(),
      children: batchTarget().children.length,
      ids: { first: first.run_id, second: second.run_id, third: third.run_id },
    };
  },

  // The Detail panel as the user opens it: the detail comes from the backend, then the receipt.
  async openedDetail() {
    reset();
    const payload = data.stored.OK;
    serve({ [payload.run_id]: ["SAVED"] }, (path) =>
      path === `/v1/analyze/detail/${payload.run_id}`
        ? { status: 200, body: data.liveDetail }
        : undefined,
    );
    await openDetail(payload);
    await settle();
    return {
      storage: storageText(detailPanel),
      ...watchState(),
      paths: requests.map((item) => item.path),
    };
  },

  // The backend never leaves PENDING: one request, three further tries, and then nothing.
  async retryBound() {
    const payload = data.stored.OK;
    await showDetail(payload, { [payload.run_id]: ["PENDING"] });
    const steps = [{ storage: storageText(detailPanel), ...watchState() }];
    for (let round = 0; round < 10 && pending().length; round += 1) {
      await fire(pending()[0]);
      steps.push({ storage: storageText(detailPanel), ...watchState() });
    }
    return {
      steps,
      delays: receiptTimers().map((timer) => timer.delay),
      constant: [...SAVE_RECEIPT_RETRY_DELAYS_MS],
      cleared: receiptTimers().filter((timer) => timer.cleared).length,
    };
  },

  // What a further try can find.
  async retryOutcomes() {
    const payload = data.stored.OK;
    const id = payload.run_id;
    const sequences = {
      savedOnTheThirdTry: ["PENDING", "PENDING", "SAVED"],
      failedOnTheSecondTry: ["PENDING", "FAILED"],
      notRetainedOnTheSecondTry: ["PENDING", "NOT_RETAINED"],
      requestFailsOnTheSecondTry: ["PENDING", "NETWORK"],
      unknownRunOnTheSecondTry: ["PENDING", notFound],
      unknownStateOnTheSecondTry: ["PENDING", "ARCHIVED"],
    };
    const out = {};
    for (const [name, replies] of Object.entries(sequences)) {
      await showDetail(payload, { [id]: [...replies] });
      await fireAll();
      out[name] = { storage: storageText(detailPanel), ...watchState() };
    }
    return out;
  },

  // No receipt this screen can show: the row keeps its request-time text, and nothing is retried.
  async failurePaths() {
    const payload = data.stored.OK;
    const id = payload.run_id;
    const ok = (body) => ({ status: 200, body });
    const without = (key) => {
      const body = receiptBody(id, "SAVED");
      delete body[key];
      return ok(body);
    };
    const replies = {
      requestFails: "NETWORK",
      unknownRun: notFound,
      serverError: { status: 500, body: { detail: { error: { message: "Internal error." } } } },
      notJson: { status: 200, body: undefined },
      nullBody: ok(null),
      listBody: ok([receiptBody(id, "SAVED")]),
      textBody: ok("SAVED"),
      otherSchemaVersion: ok(receiptBody(id, "SAVED", { schema_version: "save_receipt.v2" })),
      noSchemaVersion: without("schema_version"),
      unknownState: "ARCHIVED",
      lowerCaseState: "saved",
      stateOfEveryObject: "constructor",
      anotherStateOfEveryObject: "toString",
      noState: without("state"),
      listState: ok(receiptBody(id, ["SAVED"])),
      nullState: ok(receiptBody(id, null)),
      anotherRunsReceipt: ok(receiptBody("run_another", "SAVED")),
      noRunId: without("run_id"),
    };
    const out = {};
    for (const [name, reply] of Object.entries(replies)) {
      await showDetail(payload, { [id]: [reply] });
      out[name] = { ...watchState(), shown: visibleTexts(detailPanel, skipped) };
    }
    return out;
  },

  // Nothing is asked for a reopened run, an analysis without a view or a run id, or a card that
  // is only built.
  async nothingToAsk() {
    const out = {};
    reset();
    serve({});
    renderStructuredDetail(data.reopened.row, data.reopened.detail);
    await settle();
    out.reopened = {
      ...watchState(),
      storageRow: visibleTexts(detailPanel, skipped).includes("Storage"),
    };

    reset();
    serve({}, (path) =>
      path === `/v1/analyze/detail/${data.reopened.row.run_id}`
        ? { status: 200, body: data.reopened.detail }
        : undefined,
    );
    await openDetail(data.reopened.row);
    await settle();
    out.reopenedFromHistory = {
      ...watchState(),
      details: requests.filter((item) => item.path.startsWith("/v1/analyze/detail/")).length,
      shown: visibleTexts(detailPanel, skipped).includes("Saved analysis"),
    };

    await showDetail(data.legacy, {});
    out.withoutAView = watchState();

    const { run_id: _dropped, ...anonymous } = data.stored.OK;
    await showDetail(anonymous, {});
    out.withoutARunId = { ...watchState(), storage: storageText(detailPanel) };

    reset();
    serve({});
    const cards = [horizonCard(data.stored.OK), overviewCard(data.stored.OK)];
    await settle();
    out.builtNotShown = { ...watchState(), rows: cards.map((card) => storageText(card)) };

    // Cards of an analysis without a view have no Storage row, on either screen.
    reset();
    const legacyItems = [{ index: 0, symbol: "BTC", status: "OK", run_id: data.legacy.run_id }];
    serve({}, (path) =>
      path === "/v1/analyze"
        ? { status: 200, body: data.legacy }
        : batchOf([data.legacy], legacyItems)(path),
    );
    await runSingle();
    await runBatch();
    await settle();
    const shownCards = [
      ...singleResult.querySelectorAll(".horizon-card"),
      ...batchTarget().querySelectorAll(".timeframe-card"),
    ];
    out.cardsWithoutAView = {
      ...watchState(),
      single: singleResult.querySelectorAll(".horizon-card").length > 0,
      batch: batchTarget().querySelectorAll(".timeframe-card").length,
      storageRows: shownCards.filter((card) => visibleTexts(card).includes("Storage")).length,
    };
    return out;
  },

  // Where the Storage row is found, and whose card a Batch card says it is.
  async rowsAndCards() {
    reset();
    const rows = (...lists) => fakeElement("div", "", lists.map((values) => keyValueTable(values)));
    const text = (node) => {
      const cell = storageValueCell(node);
      return cell ? cell.textContent : null;
    };
    const lone = fakeElement("dl", "", [fakeElement("dt", "", ["Storage"])]);
    const { run_id: _dropped, ...anonymous } = data.stored.OK;
    return {
      first: text(rows([["Storage", "first row"], ["Evidence", "another"]])),
      last: text(rows([["Evidence", "another"], ["Storage", "last row"]])),
      secondList: text(rows([["Evidence", "another"]], [["Data", "more"], ["Storage", "second"]])),
      firstOfTwo: text(rows([["Storage", "one"]], [["Storage", "two"]])),
      none: text(rows([["Evidence", "another"], [WHEN_REQUESTED, "not this row"]])),
      noList: text(fakeElement("div", "", [fakeElement("p", "", ["Storage"])])),
      noValueCell: text(fakeElement("div", "", [lone])),
      cardOfARun: overviewCard(data.stored.OK).dataset.runId === data.stored.OK.run_id,
      cardWithoutARun: Object.keys(overviewCard(anonymous).dataset),
    };
  },

  // A replaced card takes its watch with it.
  async replacement() {
    const out = {};
    const payload = data.stored.OK;
    const other = data.analyses["4H"];

    await showDetail(payload, { [payload.run_id]: ["PENDING"] });
    const before = watchState();
    hideDetail();
    out.hidden = { before, after: watchState(), cleared: cleared() };

    await showDetail(payload, { [payload.run_id]: ["PENDING"], [other.run_id]: ["SAVED"] });
    await openDetail(other);
    await settle();
    out.anotherOpened = {
      ...watchState(),
      storage: storageText(detailPanel),
      cleared: cleared(),
    };

    await showDetail(payload, { [payload.run_id]: ["PENDING"] });
    serve({}, (path) =>
      path === `/v1/analyze/detail/${data.reopened.row.run_id}`
        ? { status: 200, body: data.reopened.detail }
        : undefined,
    );
    await openDetail(data.reopened.row);
    await settle();
    out.aSavedRunOpened = { ...watchState(), cleared: cleared() };

    // A further try is on its way when the card goes: there is no timer left to clear.
    reset();
    let answerTheSecondTry;
    const secondTry = new Promise((resolve) => { answerTheSecondTry = resolve; });
    serve({
      [payload.run_id]: [
        "PENDING",
        async () => {
          await secondTry;
          return { status: 200, body: receiptBody(payload.run_id, "PENDING") };
        },
      ],
    });
    renderStructuredDetail(payload, payload.detail_view);
    await settle();
    await fire(pending()[0]);
    hideDetail();
    answerTheSecondTry();
    await settle();
    out.goneDuringAFurtherTry = {
      ...watchState(),
      fired: receiptTimers().map((timer) => timer.fired),
      cleared: cleared(),
    };

    // The panel rendered again without being opened: the place still shows one analysis.
    await showDetail(payload, { [payload.run_id]: ["PENDING"], [other.run_id]: ["PENDING"] });
    renderStructuredDetail(other, other.detail_view);
    await settle();
    out.renderedAgain = { ...watchState(), cleared: cleared() };

    // The answer is still on its way when the card goes.
    for (const late of ["PENDING", "SAVED"]) {
      reset();
      let release;
      const held = new Promise((resolve) => { release = resolve; });
      serve({
        [payload.run_id]: [
          async () => {
            await held;
            return { status: 200, body: receiptBody(payload.run_id, late) };
          },
        ],
      });
      renderStructuredDetail(payload, payload.detail_view);
      await settle();
      const cell = storageValueCell(detailPanel);
      const inFlight = watchState();
      hideDetail();
      release();
      await settle();
      out[`late${late}`] = {
        inFlight,
        after: watchState(),
        cell: cell.textContent,
        timers: receiptTimers().length,
      };
    }
    return out;
  },

  // Each surface's watches end with that surface's cards, and with no other's.
  async surfaces() {
    reset();
    const everyRunPending = new Proxy({}, { get: () => ["PENDING"] });
    const [first, second] = [data.analyses["1H"], data.analyses["4H"]];
    const items = [first, second].map((payload, index) => ({
      index,
      symbol: payload.symbol,
      status: "OK",
      run_id: payload.run_id,
    }));
    serve(everyRunPending, (path, options) =>
      analyzeFrom(path, options) || batchOf([first, second], items)(path),
    );
    await runSingle();
    await runBatch();
    renderStructuredDetail(data.stored.OK, data.stored.OK.detail_view);
    await settle();
    const out = { shown: watchState() };

    // A new Single run: its placeholders replace the Single cards, and only those.
    backend = noBackend;
    const rerun = runSingle();
    out.singleReplaced = watchState();
    await rerun;
    await settle();
    out.afterTheFailedRun = watchState();

    // A Batch run the backend refuses: the cards go, and a failure is shown.
    backend = async (path) => {
      if (path === "/v1/analyze_batch") return { status: 422, body: { detail: [] } };
      throw new Error("no backend behind the DOM stand-in");
    };
    await runBatch();
    await settle();
    out.batchRefused = { ...watchState(), message: visibleTexts(batchTarget()) };

    // Batch cards and a Detail panel again: clearing the operator's data ends every watch.
    serve(everyRunPending, (path, options) =>
      analyzeFrom(path, options) || batchOf([first, second], items)(path),
    );
    await runBatch();
    renderStructuredDetail(data.stored.OK, data.stored.OK.detail_view);
    await settle();
    out.batchAndDetail = watchState();
    clearOperatorData();
    out.cleared = watchState();
    return out;
  },

  // Two runs at once: the later run's card replaces the earlier run's, and takes over its place.
  async overlappingRuns() {
    const out = {};
    const everyRunPending = new Proxy({}, { get: () => ["PENDING"] });
    const held = () => {
      let release;
      const gate = new Promise((resolve) => { release = resolve; });
      return { gate, release };
    };

    reset();
    const runs = [held(), held()];
    let analyzeCalls = 0;
    serve(everyRunPending, (path, options) => {
      if (path !== "/v1/analyze") return undefined;
      const mine = runs[Math.floor(analyzeCalls / 6)];
      analyzeCalls += 1;
      return mine.gate.then(() => analyzeFrom(path, options));
    });
    const earlier = runSingle();
    const later = runSingle();
    runs[0].release();
    await earlier;
    await settle();
    out.singleEarlier = { ...watchState(), cards: Object.keys(singleRows()).length };
    runs[1].release();
    await later;
    await settle();
    out.singleLater = {
      ...watchState(),
      cards: singleResult.querySelectorAll(".horizon-card").length,
      cleared: cleared().filter(Boolean).length,
      rows: singleRows(),
    };
    // One timeframe's card gives way to an error card: that card's watch, and no other.
    replaceTimeframeCard(singleResult, "1H", errorCard("1H", new Error("Failed.")), "tactical");
    out.oneCardReplaced = {
      ...watchState(),
      cards: singleResult.querySelectorAll(".horizon-card").length,
    };

    // Two Batch runs of different analyses: the later run's cards replace all the earlier ones.
    reset();
    const itemsOf = (payloads) =>
      payloads.map((payload, index) => ({
        index,
        symbol: payload.symbol,
        status: "OK",
        run_id: payload.run_id,
      }));
    const results = [
      [data.analyses["1H"], data.analyses["4H"]],
      [data.analyses["1D"], data.analyses["1W"]],
    ];
    const batches = [held(), held()];
    let batchCalls = 0;
    serve(everyRunPending, (path) => {
      if (path !== "/v1/analyze_batch") return undefined;
      const call = batchCalls;
      batchCalls += 1;
      return batches[call].gate.then(() => batchOf(results[call], itemsOf(results[call]))(path));
    });
    const earlierBatch = runBatch();
    const laterBatch = runBatch();
    batches[0].release();
    await earlierBatch;
    await settle();
    out.batchEarlier = watchState();
    batches[1].release();
    await laterBatch;
    await settle();
    out.batchLater = {
      ...watchState(),
      cards: batchRows().map(([runId]) => runId),
      expected: results[1].map((payload) => payload.run_id),
      cleared: cleared().filter(Boolean).length,
    };
    return out;
  },

  // The receipt's text is set as text, never as markup, on every surface. The record of markup
  // works: a Single run's loading placeholders are set as markup, and it holds them.
  async textNotMarkup() {
    const payload = data.stored.OK;
    const cellOf = (node) => {
      const cell = storageValueCell(node);
      return {
        text: cell.textContent,
        nodes: cell.children.map((child) => child.constructor.name),
        markup: writtenAsMarkup.has(cell),
      };
    };
    const out = { detail: {} };
    for (const name of Object.keys(SAVE_RECEIPT_TEXT)) {
      writtenAsMarkup.clear();
      await showDetail(payload, { [payload.run_id]: [name] });
      out.detail[name] = { ...cellOf(detailPanel), markupWrites: writtenAsMarkup.size };
    }
    const everyRunFailed = new Proxy({}, { get: () => ["FAILED"] });
    const [first, second] = [data.analyses["1H"], data.analyses["4H"]];
    const items = [first, second].map((item, index) => ({
      index,
      symbol: item.symbol,
      status: "OK",
      run_id: item.run_id,
    }));
    reset();
    writtenAsMarkup.clear();
    serve(everyRunFailed, (path, options) =>
      analyzeFrom(path, options) || batchOf([first, second], items)(path),
    );
    await runSingle();
    await runBatch();
    await settle();
    out.placeholders = writtenAsMarkup.size;
    out.single = singleResult.querySelectorAll(".horizon-card").map(cellOf);
    out.batch = batchTarget().querySelectorAll(".timeframe-card").map(cellOf);
    return out;
  },

  // An outage's cooldown: storage is UNAVAILABLE when the analysis is requested, and its save
  // then succeeds. The real Batch flow, then the card's Detail panel.
  async savedAfterAnOutage() {
    reset();
    const payload = data.stored.UNAVAILABLE;
    const items = [{ index: 0, symbol: payload.symbol, status: "OK", run_id: payload.run_id }];
    serve({ [payload.run_id]: ["SAVED"] }, (path) =>
      path === `/v1/analyze/detail/${payload.run_id}`
        ? { status: 200, body: payload.detail_view }
        : batchOf([payload], items)(path),
    );
    updatePersistenceStatus("OK");
    await runBatch();
    await settle();
    const card = {
      rows: batchRows().map(([, text]) => text),
      badge: badgeState(),
      shown: visibleTexts(batchTarget(), skipped),
    };
    await openDetail(payload);
    await settle();
    return {
      card,
      storage: storageText(detailPanel),
      badge: badgeState(),
      shown: visibleTexts(detailPanel, skipped),
    };
  },

  // A receipt is one analysis's. Whatever its state, and whatever the badge reads, the badge is
  // not written to: its text, its status and its classes are as they were.
  async badgeUntouched() {
    const payload = data.stored.UNAVAILABLE;
    const answers = {
      SAVED: ["SAVED"],
      PENDING: ["PENDING"],
      FAILED: ["FAILED"],
      NOT_RETAINED: ["NOT_RETAINED"],
      savedOnTheThirdTry: ["PENDING", "PENDING", "SAVED"],
      requestFails: ["NETWORK"],
      unknownRun: [notFound],
    };
    reset();
    badgeWrites.length = 0;
    updatePersistenceStatus("OK");
    const out = { recordSees: [...badgeWrites], detail: {} };
    for (const lastChecked of ["OK", "UNAVAILABLE", "STATELESS"]) {
      for (const [name, replies] of Object.entries(answers)) {
        reset();
        serve({ [payload.run_id]: [...replies] });
        updatePersistenceStatus(lastChecked);
        const before = badgeState();
        badgeWrites.length = 0;
        renderStructuredDetail(payload, payload.detail_view);
        await settle();
        await fireAll();
        out.detail[`${lastChecked}:${name}`] = {
          before,
          after: badgeState(),
          writes: [...badgeWrites],
          storage: storageText(detailPanel),
          asked: asked().length,
        };
      }
    }
    // Single and Batch. The analyses' own responses set the badge (api does that), so the
    // receipts are held back until the cards are shown, and only what follows is recorded.
    const four = ["1H", "4H", "1D", "1W"].map((name) => data.analyses[name]);
    const items = four.map((item, index) => ({
      index,
      symbol: item.symbol,
      status: "OK",
      run_id: item.run_id,
    }));
    const states = Object.keys(SAVE_RECEIPT_TEXT);
    for (const [surface, show, rows] of [
      ["single", runSingle, () => Object.values(singleRows())],
      ["batch", runBatch, () => batchRows().map(([, text]) => text)],
    ]) {
      reset();
      let release;
      const held = new Promise((resolve) => { release = resolve; });
      let receipts = 0;
      backend = async (path, options) => {
        if (path.startsWith(RECEIPT)) {
          const state = states[receipts % states.length];
          receipts += 1;
          await held;
          const runId = decodeURIComponent(path.slice(RECEIPT.length));
          return { status: 200, body: receiptBody(runId, state) };
        }
        const other = analyzeFrom(path, options) || batchOf(four, items)(path);
        if (other === undefined) throw new Error("no backend behind the DOM stand-in");
        return other;
      };
      updatePersistenceStatus("UNKNOWN");
      await show();
      await settle();
      const before = badgeState();
      const rowsBefore = rows();
      badgeWrites.length = 0;
      release();
      await settle();
      out[surface] = {
        before,
        after: badgeState(),
        writes: [...badgeWrites],
        rowsBefore,
        rows: rows(),
      };
    }
    return out;
  },

  // The receipt is asked for with the session's own helper: a 401 ends the session. Run last:
  // it logs the stand-in out.
  async sessionExpired() {
    const payload = data.stored.OK;
    reset();
    backend = async (path) => {
      if (path.startsWith(RECEIPT)) {
        return { status: 401, body: { detail: { error: { message: "Session required." } } } };
      }
      throw new Error("no backend behind the DOM stand-in");
    };
    renderStructuredDetail(payload, payload.detail_view);
    const shownBefore = !detailPanel.classList.contains("hidden");
    await settle();
    return {
      ...watchState(),
      shownBefore,
      login: loginStatus.textContent,
      detailHidden: detailPanel.classList.contains("hidden"),
      workspaceHidden: workspace.classList.contains("hidden"),
    };
  },
};

(async () => {
  const out = {};
  for (const [name, scenario] of Object.entries(scenarios)) out[name] = await scenario();
  process.stdout.write(JSON.stringify(out), () => process.exit(0));
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
"""


def _requested_with(storage: str) -> dict:
    """One real 1H analysis whose storage status at request time is the one given."""

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(analysis_service, "select_market_data", harness._select)
        patch.setattr(
            analysis_service, "get_cached_skill_evidence", lambda _tf: dict(harness.NO_SKILL)
        )
        return analysis_service.analyze_request(
            AnalysisRequest(symbol="BTC/USDT", timeframe="1H"),
            settings=Settings(data_mode="fixture"),
            run_store=InMemoryRunStore(limit=10),
            persistence_status=storage,
        )


def _reopened(payload: dict) -> dict:
    """A saved run as it is read back: a history row, and the detail as the detail route returns
    it (what the store exports, with the view the route builds from it when it reads it)."""

    row = {
        "run_id": payload["run_id"],
        "symbol": payload["symbol"],
        "normalized_symbol": payload["normalized_symbol"],
        "analysis_mode": payload["analysis_mode"],
        "as_of_utc": payload["as_of_utc"],
        "analysis_hash": payload["analysis_hash"],
        "prediction_origin": "USER_REQUESTED",
        "detail_available": True,
        "primary_timeframe": "1H",
        "data_source": payload["data_quality"]["data_source"],
        "is_live_data": True,
    }
    stored = sanitize_for_export(copy.deepcopy(payload["detail_view"]))
    return {"row": row, "detail": attach_saved_run_view(stored)}


@pytest.fixture(scope="module")
def data() -> dict[str, Any]:
    """Real analyses: one for each timeframe of a Single run, two whose storage state at request
    time is given, the detail the backend returns for a live one, a saved run read back, and an
    analysis without a decision view."""

    analyses = {timeframe: harness._analysis(timeframe) for timeframe in TIMEFRAMES}
    stored = {status: _requested_with(status) for status in ("OK", "UNAVAILABLE")}
    return {
        "analyses": analyses,
        "stored": stored,
        # The detail route answers a held run with the response's own detail view.
        "liveDetail": stored["OK"]["detail_view"],
        "reopened": _reopened(stored["OK"]),
        "legacy": harness._without(analyses["1H"], "decision_view"),
    }


@pytest.fixture(scope="module")
def run(data: dict[str, Any]) -> dict[str, Any]:
    assert harness.NODE is not None, "node is required to run the real app.js"
    script = "\n".join(
        [
            harness._DOM_STAND_IN,
            _FAKES,
            (ROOT / "frontend" / "app.js").read_text(encoding="utf-8"),
            _BADGE_RECORD,
            f"const data = {json.dumps(data, default=str)};",
            _SCENARIOS,
        ]
    )
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


def _storage(texts: list[str]) -> str:
    return harness._value(texts, "Storage")


def test_the_analyses_are_live_and_say_what_storage_was_at_request_time(data: dict) -> None:
    assert sorted(data["analyses"]) == sorted(TIMEFRAMES)
    run_ids = {payload["run_id"] for payload in data["analyses"].values()}
    assert len(run_ids) == len(TIMEFRAMES)
    for payload in (*data["analyses"].values(), *data["stored"].values()):
        assert payload["decision_view"]["schema_version"] == "decision_view.v2"
        assert "save_receipt" not in payload, "the response carries no receipt (owner ruling D4)"
    assert data["stored"]["OK"]["debug"]["persistence_status"] == "OK"
    assert data["stored"]["UNAVAILABLE"]["debug"]["persistence_status"] == "UNAVAILABLE"
    assert "decision_view" not in data["reopened"]["row"]
    assert "decision_view" not in data["legacy"]


def test_each_state_is_shown_in_the_storage_row_and_no_other_line_moves(
    run: dict, data: dict
) -> None:
    states = run["detailStates"]
    unanswered = states["unanswered"]
    assert _storage(unanswered) == AVAILABLE
    assert unanswered.count(AVAILABLE) == 2, "the Storage row, and the Overview's row"
    assert harness._value(unanswered, "Overview", WHEN_REQUESTED) == AVAILABLE
    row = unanswered.index("Storage") + 1
    for name, text in TEXT.items():
        shown = states[name]["shown"]
        assert shown[row] == text, name
        assert shown[:row] == unanswered[:row] and shown[row + 1 :] == unanswered[row + 1 :], name
        assert states[name]["asked"] == [data["stored"]["OK"]["run_id"]], f"{name}: asked once"
    for name in ("SAVED", "FAILED", "NOT_RETAINED"):
        assert states[name]["pending"] == [] and states[name]["watches"] == 0, name
    assert states["PENDING"]["pending"] == [1000] and states["PENDING"]["watches"] == 1
    assert len(set(TEXT.values())) == 4


def test_the_rows_themselves_stay_the_request_time_rows(run: dict) -> None:
    """decisionViewRows is a pure function of (payload, view): the receipt is a separate step on
    the rendered row, so the UX card and every caller still get the request-time row."""

    for name in TEXT:
        rows = dict(run["detailStates"][name]["rows"])
        assert rows["Storage"] == AVAILABLE, name
        assert run["detailStates"][name]["rowsUnchanged"] is True, name


def test_the_state_shown_is_the_backends_and_nothing_is_worked_out(run: dict) -> None:
    shown = run["backendStateOnly"]
    assert shown["UNAVAILABLE_SAVED"]["storage"] == TEXT["SAVED"]
    assert shown["OK_NOT_RETAINED"]["storage"] == TEXT["NOT_RETAINED"]


def test_the_overviews_row_is_labelled_storage_when_requested(run: dict) -> None:
    """The receipt can contradict the request-time status ("Saved…" over "Storage unavailable…").
    The Overview's row keeps its request-time value under a label that says so: one Storage row,
    one "Storage when requested" row, and no row named Persistence."""

    shown = run["backendStateOnly"]
    assert shown["UNAVAILABLE_SAVED"]["whenRequested"] == UNAVAILABLE
    assert shown["OK_NOT_RETAINED"]["whenRequested"] == AVAILABLE
    for name, outcome in shown.items():
        assert outcome["labels"] == [1, 1, 0], name
        assert outcome["storage"] != outcome["whenRequested"], name
    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    assert source.count(f'"{WHEN_REQUESTED}"') == 1, "the Overview's row, and no other"
    assert 'const STORAGE_ROW_LABEL = "Storage";' in source


def test_a_saved_receipt_is_not_contradicted_by_the_request_time_status(run: dict) -> None:
    """An outage's cooldown: storage is UNAVAILABLE when the analysis is requested, and its save
    then succeeds. The Storage row says "Saved…" while the badge and the Overview's row still
    give the request-time status. That status names its moment and states a possibility, so no
    line on screen says the analysis is not, or will not be, kept (owner ruling "relabel")."""

    outage = run["savedAfterAnOutage"]
    card = outage["card"]
    assert card["rows"] == [TEXT["SAVED"]] and outage["storage"] == TEXT["SAVED"]
    # The analysis's own response set the badge, and neither receipt moved it.
    assert outage["badge"] == card["badge"]
    assert outage["badge"]["status"] == "UNAVAILABLE"
    assert outage["badge"]["text"] == BADGE_PREFIX + UNAVAILABLE
    assert harness._value(outage["shown"], "Overview", WHEN_REQUESTED) == UNAVAILABLE
    on_screen = [*card["shown"], *outage["shown"], outage["badge"]["text"]]
    about_history = {line for line in on_screen if "Recent Analysis history" in line}
    assert about_history == {TEXT["SAVED"], UNAVAILABLE, BADGE_PREFIX + UNAVAILABLE}
    for line in on_screen:
        for refuted in ("will not", "not being", "not retained", "not appear"):
            assert refuted not in line.lower(), line
    assert UNAVAILABLE.startswith("Storage unavailable when requested — ")
    assert "may not be kept" in UNAVAILABLE


def test_no_request_time_sentence_forecasts_a_save(run: dict) -> None:
    """The three request-time sentences, as the screen renders them, beside the four receipt
    sentences. None of the three says that an analysis was saved, or that it is not or will not
    be kept: so none can be refuted by the receipt shown beside it."""

    for sentence in (AVAILABLE, NO_STORAGE, UNAVAILABLE):
        for forecast in ("will not", "not being", "not retained", "not appear", "saved"):
            assert forecast not in sentence.lower(), sentence
    assert NO_STORAGE == run["single"]["first"]["rows"]["1W"], "as rendered, with no receipt"
    assert UNAVAILABLE == run["backendStateOnly"]["UNAVAILABLE_SAVED"]["whenRequested"]
    assert AVAILABLE == _storage(run["detailStates"]["unanswered"])
    # Without storage the receipt and the status name the same cause.
    assert "No storage configured" in NO_STORAGE
    assert "no storage is configured" in TEXT["NOT_RETAINED"]


def test_a_receipt_in_any_state_leaves_the_header_badge_untouched(run: dict) -> None:
    """The badge is storage's status when it was last asked; a receipt is one analysis's. The
    receipt's code writes that analysis's Storage row and nothing of the badge: not its text, not
    its status, not its classes. In every state, on every surface, whatever the badge reads."""

    badge = run["badgeUntouched"]
    assert badge["recordSees"], "the record sees a badge write: the badge's own function's"
    assert {"text", "status", "classes"} <= set(badge["recordSees"])
    shown = {
        "SAVED": TEXT["SAVED"],
        "PENDING": TEXT["PENDING"],
        "FAILED": TEXT["FAILED"],
        "NOT_RETAINED": TEXT["NOT_RETAINED"],
        "savedOnTheThirdTry": TEXT["SAVED"],
        # No receipt this screen can show: the row keeps its request-time text.
        "requestFails": UNAVAILABLE,
        "unknownRun": UNAVAILABLE,
    }
    last_checked = {"OK": AVAILABLE, "UNAVAILABLE": UNAVAILABLE, "STATELESS": NO_STORAGE}
    assert sorted(badge["detail"]) == sorted(f"{a}:{b}" for a in last_checked for b in shown)
    for name, outcome in badge["detail"].items():
        status, answer = name.split(":")
        assert outcome["storage"] == shown[answer], f"{name}: the receipt was shown"
        assert outcome["asked"] >= 1, name
        assert outcome["writes"] == [], f"{name}: the badge was written to"
        assert outcome["after"] == outcome["before"], name
        assert outcome["before"]["status"] == status, name
        assert outcome["before"]["text"] == BADGE_PREFIX + last_checked[status], name
    assert badge["detail"]["OK:savedOnTheThirdTry"]["asked"] == 3
    for surface, cards in (("single", 6), ("batch", 4)):
        outcome = badge[surface]
        # The analyses' responses had set the badge; the receipts then reached every card.
        assert outcome["before"]["text"] == BADGE_PREFIX + NO_STORAGE, surface
        assert outcome["rowsBefore"] == [NO_STORAGE] * cards, surface
        assert len(outcome["rows"]) == cards and set(outcome["rows"]) == set(TEXT.values()), surface
        assert outcome["writes"] == [], f"{surface}: the badge was written to"
        assert outcome["after"] == outcome["before"], surface


def test_a_single_run_shows_each_cards_own_receipt(run: dict, data: dict) -> None:
    single = run["single"]
    assert single["analyzed"] == 6 and single["cards"] == 6
    ids = {timeframe: data["analyses"][timeframe]["run_id"] for timeframe in TIMEFRAMES}
    assert sorted(single["first"]["asked"]) == sorted(ids.values()), "each card once"
    assert single["first"]["rows"] == {
        "15m": TEXT["SAVED"],
        "1H": TEXT["PENDING"],
        "4H": TEXT["FAILED"],
        "1D": TEXT["NOT_RETAINED"],
        "1W": NO_STORAGE,  # an unknown run: 404
        "1M": NO_STORAGE,  # the request failed
    }
    assert single["first"]["pending"] == [1000] and single["first"]["watches"] == 1
    # The one further try, for the one card that was PENDING.
    assert single["after"]["rows"] == {**single["first"]["rows"], "1H": TEXT["SAVED"]}
    assert single["after"]["asked"] == [*single["first"]["asked"], ids["1H"]]
    assert single["after"]["pending"] == [] and single["after"]["watches"] == 0


def test_a_batch_run_shows_each_cards_own_receipt(run: dict) -> None:
    batch = run["batch"]
    ids = batch["ids"]
    # The cards are in the items' order; the results came in another.
    assert batch["rows"] == [
        [ids["third"], TEXT["PENDING"]],
        [ids["first"], TEXT["SAVED"]],
        [ids["second"], TEXT["FAILED"]],
    ]
    assert batch["children"] == 4, "three cards and the failed item's message"
    assert sorted(batch["asked"]) == sorted(ids.values())
    assert batch["pending"] == [1000] and batch["watches"] == 1


def test_the_detail_panel_asks_after_the_detail_is_shown(run: dict, data: dict) -> None:
    opened = run["openedDetail"]
    run_id = data["stored"]["OK"]["run_id"]
    assert opened["storage"] == TEXT["SAVED"]
    assert opened["asked"] == [run_id]
    assert opened["paths"] == [
        f"/v1/analyze/detail/{run_id}",
        "/v1/calibration",
        f"/v1/analyze/receipt/{run_id}",
    ]


def test_pending_is_tried_three_more_times_and_then_no_timer_is_left(run: dict) -> None:
    bound = run["retryBound"]
    assert bound["constant"] == [1000, 2000, 4000]
    assert [step["storage"] for step in bound["steps"]] == [TEXT["PENDING"]] * 4
    assert [len(step["asked"]) for step in bound["steps"]] == [1, 2, 3, 4]
    assert [step["pending"] for step in bound["steps"]] == [[1000], [2000], [4000], []]
    assert [step["watches"] for step in bound["steps"]] == [1, 1, 1, 0]
    assert bound["delays"] == bound["constant"], "one timer per further try, never two at once"
    assert bound["cleared"] == 0


def test_a_further_try_shows_what_it_finds_and_stops(run: dict) -> None:
    outcomes = run["retryOutcomes"]
    expected = {
        "savedOnTheThirdTry": (TEXT["SAVED"], 3),
        "failedOnTheSecondTry": (TEXT["FAILED"], 2),
        "notRetainedOnTheSecondTry": (TEXT["NOT_RETAINED"], 2),
        # No receipt on the further try: the row keeps the last state the backend gave.
        "requestFailsOnTheSecondTry": (TEXT["PENDING"], 2),
        "unknownRunOnTheSecondTry": (TEXT["PENDING"], 2),
        "unknownStateOnTheSecondTry": (TEXT["PENDING"], 2),
    }
    assert sorted(outcomes) == sorted(expected)
    for name, (text, requests) in expected.items():
        outcome = outcomes[name]
        assert outcome["storage"] == text, name
        assert len(outcome["asked"]) == requests, name
        assert outcome["pending"] == [] and outcome["watches"] == 0, name


def test_without_a_receipt_it_can_show_the_row_keeps_its_request_time_text(run: dict) -> None:
    unanswered = run["detailStates"]["unanswered"]
    paths = run["failurePaths"]
    assert len(paths) == 18
    for name, outcome in paths.items():
        assert outcome["shown"] == unanswered, name
        assert _storage(outcome["shown"]) == AVAILABLE, name
        assert len(outcome["asked"]) == 1, f"{name}: asked once, never again"
        assert outcome["pending"] == [] and outcome["watches"] == 0, name
    assert run["detailStates"]["unansweredState"]["pending"] == []


def test_nothing_is_asked_where_there_is_no_live_analysis_on_screen(run: dict) -> None:
    nothing = run["nothingToAsk"]
    for name in ("reopened", "reopenedFromHistory", "withoutAView", "withoutARunId"):
        assert nothing[name]["asked"] == [], name
        assert nothing[name]["pending"] == [] and nothing[name]["watches"] == 0, name
    assert nothing["reopened"]["storageRow"] is False, "a reopened run has no Storage row"
    assert nothing["reopenedFromHistory"]["details"] == 1
    assert nothing["reopenedFromHistory"]["shown"] is True
    assert nothing["withoutARunId"]["storage"] == AVAILABLE
    # A card that is built is not yet shown: the flows that show it ask.
    assert nothing["builtNotShown"] == {
        "asked": [],
        "pending": [],
        "watches": 0,
        "rows": [AVAILABLE, AVAILABLE],
    }
    assert nothing["cardsWithoutAView"] == {
        "asked": [],
        "pending": [],
        "watches": 0,
        "single": True,
        "batch": 1,
        "storageRows": 0,
    }


def test_the_storage_row_is_found_wherever_it_is_and_a_batch_card_says_whose_it_is(
    run: dict,
) -> None:
    found = run["rowsAndCards"]
    assert found["first"] == "first row" and found["last"] == "last row"
    assert found["secondList"] == "second" and found["firstOfTwo"] == "one"
    assert found["none"] is None and found["noList"] is None and found["noValueCell"] is None
    assert found["cardOfARun"] is True
    assert found["cardWithoutARun"] == ["timeframeCard"], "no run id is made up for a card"


def test_a_replaced_detail_takes_its_watch_with_it(run: dict, data: dict) -> None:
    replaced = run["replacement"]
    hidden = replaced["hidden"]
    assert hidden["before"]["pending"] == [1000] and hidden["before"]["watches"] == 1
    assert hidden["after"]["pending"] == [] and hidden["after"]["watches"] == 0
    assert hidden["cleared"] == [True]
    opened = replaced["anotherOpened"]
    assert opened["storage"] == TEXT["SAVED"]
    assert opened["asked"] == [data["stored"]["OK"]["run_id"], data["analyses"]["4H"]["run_id"]]
    assert opened["cleared"] == [True] and opened["pending"] == [] and opened["watches"] == 0
    gone = replaced["goneDuringAFurtherTry"]
    assert gone["fired"] == [True] and gone["cleared"] == [False], "only a waiting timer is cleared"
    assert len(gone["asked"]) == 2 and gone["pending"] == [] and gone["watches"] == 0
    again = replaced["renderedAgain"]
    assert again["cleared"] == [True, False] and again["pending"] == [1000]
    assert again["watches"] == 1 and len(again["asked"]) == 2
    saved_run = replaced["aSavedRunOpened"]
    assert saved_run["cleared"] == [True], "a saved run starts no watch, and still ends the old one"
    assert saved_run["asked"] == [data["stored"]["OK"]["run_id"]], "nothing for the saved run"
    assert saved_run["pending"] == [] and saved_run["watches"] == 0


@pytest.mark.parametrize("late", ["PENDING", "SAVED"])
def test_an_answer_that_arrives_after_its_card_is_gone_is_ignored(run: dict, late: str) -> None:
    outcome = run["replacement"][f"late{late}"]
    assert len(outcome["inFlight"]["asked"]) == 1 and outcome["inFlight"]["watches"] == 1
    assert outcome["cell"] == AVAILABLE, "the row that was replaced is not written to"
    assert outcome["timers"] == 0, "and no further try is scheduled for it"
    assert outcome["after"] == {"asked": outcome["inFlight"]["asked"], "pending": [], "watches": 0}


def test_each_surfaces_watches_end_with_its_own_cards(run: dict) -> None:
    surfaces = run["surfaces"]
    # Six Single cards, two Batch cards and the Detail panel, all PENDING.
    assert len(surfaces["shown"]["asked"]) == 9
    assert surfaces["shown"]["pending"] == [1000] * 9 and surfaces["shown"]["watches"] == 9
    # A new Single run replaces the Single cards at once, before any answer: theirs alone.
    # (Its placeholders also hide the Detail panel, as before.)
    assert surfaces["singleReplaced"]["pending"] == [1000] * 2
    assert surfaces["singleReplaced"]["watches"] == 2
    assert surfaces["afterTheFailedRun"]["watches"] == 2
    assert surfaces["batchRefused"]["pending"] == [] and surfaces["batchRefused"]["watches"] == 0
    assert surfaces["batchRefused"]["message"] == [
        "Batch request was not accepted. Enter at least one symbol and try again."
    ]
    assert surfaces["batchAndDetail"]["pending"] == [1000] * 3
    assert surfaces["batchAndDetail"]["watches"] == 3
    assert surfaces["cleared"] == {
        "asked": surfaces["batchAndDetail"]["asked"],
        "pending": [],
        "watches": 0,
    }


def test_a_later_runs_card_takes_over_the_place_of_the_card_it_replaces(run: dict) -> None:
    """Two runs can be in flight at once (a second submit). Whichever card is on screen is the one
    watched: the card it replaced leaves no timer behind."""

    overlap = run["overlappingRuns"]
    assert overlap["singleEarlier"]["pending"] == [1000] * 6
    assert overlap["singleEarlier"]["cards"] == 6
    later = overlap["singleLater"]
    assert later["cards"] == 6, "each later card replaced the earlier one of its timeframe"
    assert later["cleared"] == 6 and later["pending"] == [1000] * 6 and later["watches"] == 6
    assert len(later["asked"]) == 12
    assert set(later["rows"].values()) == {TEXT["PENDING"]} and len(later["rows"]) == 6
    replaced = overlap["oneCardReplaced"]
    assert replaced["pending"] == [1000] * 5 and replaced["watches"] == 5
    assert replaced["cards"] == 5
    assert overlap["batchEarlier"]["pending"] == [1000] * 2
    batch = overlap["batchLater"]
    assert batch["cards"] == batch["expected"] and len(batch["cards"]) == 2
    assert batch["cleared"] == 2, "the earlier run's two cards are gone, and their timers"
    assert batch["pending"] == [1000] * 2 and batch["watches"] == 2


def test_the_receipt_uses_the_sessions_own_helper(run: dict) -> None:
    expired = run["sessionExpired"]
    assert expired["shownBefore"] is True
    assert len(expired["asked"]) == 1
    assert expired["login"] == EXPIRED
    assert expired["detailHidden"] is True and expired["workspaceHidden"] is True
    assert expired["pending"] == [] and expired["watches"] == 0


def test_the_receipt_reaches_its_cell_as_text_and_never_as_markup(run: dict) -> None:
    """app.js sets the cell's textContent. The DOM stand-in reads innerHTML as text too, so the
    words alone cannot tell: its record of markup writes would hold the cell if app.js had set
    innerHTML on it, on any surface."""

    shown = run["textNotMarkup"]
    assert sorted(shown["detail"]) == sorted(TEXT)
    for name, cell in shown["detail"].items():
        assert cell == {
            "text": TEXT[name],
            "nodes": ["FakeText"],
            "markup": False,
            "markupWrites": 0,
        }, name
    assert shown["placeholders"] > 0, "the record sees markup: a Single run's loading placeholders"
    assert len(shown["single"]) == 6 and len(shown["batch"]) == 2
    for cell in (*shown["single"], *shown["batch"]):
        assert cell == {"text": TEXT["FAILED"], "nodes": ["FakeText"], "markup": False}


def test_the_receipt_code_never_sets_markup() -> None:
    """app.js sets markup in one legitimate place (a loading placeholder), so this is asserted of
    the receipt's own code: everything from its first comment to the next card builder."""

    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    start = source.index("// The save receipt (owner ruling D4")
    receipt_code = source[start : source.index("function overviewCard(", start)]
    for part in ("const SAVE_RECEIPT_TEXT = {", "function storageValueCell(", "void ask(0);"):
        assert part in receipt_code, f"the receipt's code is not where this test reads it: {part}"
    for markup in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
        assert markup not in receipt_code, markup
    assert receipt_code.count("cell.textContent = text;") == 1
    assert receipt_code.count(".textContent = ") == 1, "one write, and it is the cell's text"


def test_the_failed_sentence_never_says_the_analysis_was_not_saved() -> None:
    """The backend's FAILED is every save it holds no acknowledgement of: a write that may have
    committed unconfirmed, and a partial save, among them (api/save_receipt.py). "Not saved" and
    "will not be" would be false of those; the sentence says what is known."""

    failed = TEXT["FAILED"]
    assert failed == (
        "Save not confirmed: this analysis may be missing from Recent Analysis history after a "
        "restart"
    )
    for false_of_an_unconfirmed_save in ("not saved", "save failed", "will not"):
        assert false_of_an_unconfirmed_save not in failed.lower()
    assert "the save failed" not in (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")


def test_the_wording_is_named_constants_in_one_place() -> None:
    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    start = source.index("const SAVE_RECEIPT_TEXT = {")
    block = source[start : source.index("};", start)]
    joined = block.replace('" +\n    "', "")
    for state, text in TEXT.items():
        assert f"  {state}:" in block, state
        assert f'"{text}"' in joined, state
        assert source.replace('" +\n    "', "").count(text) == 1, f"{state}: written once"
    assert (
        "PROVISIONAL wording, pending the owner's approval." in source[:start].rsplit("\n\n", 1)[-1]
    )
    assert 'const SAVE_RECEIPT_SCHEMA_VERSION = "save_receipt.v1";' in source
    assert "const SAVE_RECEIPT_RETRY_DELAYS_MS = [1000, 2000, 4000];" in source
    # One request site, with the session's helper; no polling primitive anywhere.
    assert source.count("/v1/analyze/receipt/") == 1
    assert "sessionApi(`/v1/analyze/receipt/${encodeURIComponent(payload.run_id)}`)" in source
    assert "setInterval" not in source


def test_the_ux_cards_note_says_what_the_screen_does(run: dict) -> None:
    """The owner's UX card prints the Storage row as the save receipt leaves it
    (scripts/ux_comprehension/card.py). Its note says the screen asks the backend whether the
    analysis was saved and shows the state it gives, and that the row reads storage's status at
    request time until then: true of app.js, and proven above."""

    card = (ROOT / "docs" / "runbooks" / "UX_COMPREHENSION_CHECK.md").read_text(encoding="utf-8")
    note = " ".join(card[card.index("- Question 4 reads the Storage row") :].split())
    assert "shows no per-analysis save" not in card
    assert "the screen asks the backend whether that analysis was saved" in note
    assert "and shows the state the backend gives" in note
    assert "Until a receipt answers, the row shows storage's status when the analysis was" in note
    assert run["detailStates"]["SAVED"]["shown"] != run["detailStates"]["unanswered"]
    # The two rows the card shows are the rows the screen shows for those receipt states.
    for state in ("SAVED", "FAILED"):
        row = run["detailStates"][state]["shown"]
        (text,) = [line for line in row if line in card and line.startswith(("Saved", "Save "))]
        assert f"| Storage | {text} |" in card, state
