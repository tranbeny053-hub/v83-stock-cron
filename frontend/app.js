const sessionStatus = document.querySelector("#sessionStatus");
const loginPanel = document.querySelector("#loginPanel");
const loginStatus = document.querySelector("#loginStatus");
const workspace = document.querySelector("#workspace");
const overviewTemplate = document.querySelector("#overviewTemplate");
const singleResult = document.querySelector("#singleResult");
const detailPanel = document.querySelector("#detailPanel");
const refreshButton = document.querySelector("#refreshButton");
const lastRefreshed = document.querySelector("#lastRefreshed");
const persistenceStatusBadge = document.querySelector("#persistenceStatusBadge");
const devModeStatus = document.querySelector("#devModeStatus");
const watchlistStorageKey = "ucpe_watchlist_symbols";
const heatLegend = "Signal heat — not risk";
const modelReadinessCopy =
  "Model readiness: Heuristic (uncalibrated) — not accuracy; quality is not yet measured.";
const UCPE_FRONTEND_BUILD = "ops-ka1-build-fingerprint";
const calibrationDiagnosticsCacheTtlMs = 60000;
const singleTimeframes = ["15m", "1H", "4H", "1D", "1W", "1M"];
const tacticalTimeframes = ["15m", "1H", "4H"];
const regimeTimeframes = ["1D", "1W", "1M"];
const fallbackTimeframeRoles = {
  "15m": {
    role: "TACTICAL_TIMING",
    tactical: true,
    rawProbabilityHidden: false,
  },
  "1H": {
    role: "TACTICAL_SWING_BRIDGE",
    tactical: true,
    rawProbabilityHidden: false,
  },
  "4H": {
    role: "SETUP_QUALITY",
    tactical: true,
    rawProbabilityHidden: false,
  },
  "1D": {
    role: "SWING_CONTEXT",
    tactical: false,
    rawProbabilityHidden: false,
  },
  "1W": {
    role: "REGIME_CONTEXT",
    tactical: false,
    rawProbabilityHidden: true,
  },
  "1M": {
    role: "MACRO_BACKDROP",
    tactical: false,
    rawProbabilityHidden: true,
  },
};
const singlePayloads = new Map();
const watchlistPayloads = new Map();
const refreshCooldownMs = 15000;
let refreshReadyAt = 0;
let refreshTimer = null;
let analysisActive = false;
let lastBatchRequest = null;
let currentWatchlistSymbol = null;
let calibrationDiagnosticsCache = null;
let calibrationDiagnosticsCachedAt = 0;
let calibrationDiagnosticsRequest = null;
let recentRuns = [];
let recentRunsSource = null;
let sessionGeneration = 0;
const scoreHeatBands = [
  {
    min: 86,
    max: 100,
    level: "Extreme / Burning",
    mainColor: "#FF1A1A",
    className: "heat-extreme",
  },
  { min: 71, max: 85, level: "Very Hot", mainColor: "#F43F3F", className: "heat-very-hot" },
  { min: 56, max: 70, level: "Hot", mainColor: "#DC2626", className: "heat-hot" },
  { min: 41, max: 55, level: "Warm", mainColor: "#9F3A3A", className: "heat-warm" },
  { min: 21, max: 40, level: "Low", mainColor: "#5A4545", className: "heat-low" },
  { min: 0, max: 20, level: "Cold / Neutral", mainColor: "#374151", className: "heat-cold" },
];

async function loadBuildFingerprint() {
  const markers = document.querySelectorAll("[data-build-fingerprint]");
  try {
    const response = await fetch("/v1/build-info", {
      cache: "no-store",
      credentials: "include",
    });
    if (!response.ok) {
      throw new Error("Build information request failed.");
    }
    const payload = await response.json();
    if (typeof payload.fingerprint !== "string" || !payload.fingerprint.trim()) {
      throw new Error("Build information fingerprint is unavailable.");
    }
    for (const marker of markers) {
      marker.textContent = payload.fingerprint;
    }
  } catch {
    for (const marker of markers) {
      marker.textContent = "Build fingerprint unavailable";
    }
  }
}

// `storedRecord: true` is for an answer that is a stored record, not a report from storage now:
// the storage status in it is from when the record was made. The header badge is what storage
// said when it was last asked, so such an answer is returned to its caller and not read for it.
async function api(path, options = {}, { storedRecord = false } = {}) {
  const response = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  let payload;
  try {
    payload = await response.json();
  } catch {
    const error = new Error("Response was not valid JSON.");
    error.status = response.status;
    error.payload = null;
    throw error;
  }
  if (response.ok && !storedRecord) {
    updateStatusFromPayload(payload);
  }
  if (!response.ok) {
    const error = new Error(payload?.detail?.error?.message || "Request failed");
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

async function sessionApi(path, options = {}) {
  const generation = sessionGeneration;
  try {
    return await api(path, options);
  } catch (error) {
    if (error?.status === 401) {
      handleSessionExpired(generation);
    }
    throw error;
  }
}

function loginFailureMessage(status, payload) {
  const detail =
    payload && typeof payload === "object" && !Array.isArray(payload) ? payload.detail : null;
  const errorEnvelope =
    detail && typeof detail === "object" && !Array.isArray(detail) ? detail.error : null;
  const backendMessage =
    errorEnvelope &&
    typeof errorEnvelope === "object" &&
    !Array.isArray(errorEnvelope) &&
    typeof errorEnvelope.message === "string" &&
    errorEnvelope.message.trim()
      ? errorEnvelope.message.trim()
      : null;

  if (status === 401) {
    return backendMessage || "Access code not accepted. Check the code and try again.";
  }
  if (status === 429) {
    const retryAfter = errorEnvelope?.retry_after_seconds;
    const baseMessage = backendMessage || "Too many login attempts.";
    if (typeof retryAfter === "number" && Number.isFinite(retryAfter) && retryAfter > 0) {
      return `${baseMessage} Try again in ${retryAfter} seconds.`;
    }
    return `${baseMessage} Wait a moment, then try again.`;
  }
  if (status === 422) {
    return backendMessage || "The access code was not accepted. Check the entry and try again.";
  }
  if (backendMessage) {
    return backendMessage;
  }
  if (typeof status !== "number") {
    return "Unable to reach the service. Check your connection and try again.";
  }
  return "Login is temporarily unavailable. Try again shortly.";
}

// The storage status an answer names: text that is not blank. Anything else names none (null).
function namedStorageStatus(value) {
  return typeof value === "string" && value.trim() ? value : null;
}

// The one place an answer's storage status reaches the header badge: every answered request
// passes here (api), and the badge is written only when the answer names a status.
function updateStatusFromPayload(payload = {}) {
  const status =
    namedStorageStatus(payload.persistence_status) ||
    namedStorageStatus(payload.debug?.persistence_status) ||
    namedStorageStatus(payload.detail_view?.debug_lite?.persistence_status) ||
    namedStorageStatus(payload.system?.persistence_status);
  if (status) {
    updatePersistenceStatus(status);
  }
  if (payload.system?.dev_mode) {
    updateDevModeUx(payload.system.dev_mode);
  }
}

// What storage said when it was asked: a status, never a forecast of whether one analysis is
// saved. That is the analysis's save receipt, and it can say otherwise. PROVISIONAL wording.
function persistenceStatusText(status) {
  return status === "OK"
      ? "Storage available"
      : status === "STATELESS"
        ? "No storage configured — analyses are kept only until the server restarts"
        : status === "UNAVAILABLE"
          ? "Storage unavailable when requested — this analysis may not be kept in Recent Analysis history"
          : "Storage status unknown";
}

function updatePersistenceStatus(status) {
  const safeStatus = status || "UNKNOWN";
  const statusText = persistenceStatusText(safeStatus);
  // What storage said when it was last asked, not whether any one analysis was saved: an
  // analysis's save receipt (its Storage row) can say otherwise. PROVISIONAL wording.
  persistenceStatusBadge.textContent = `Storage, last checked: ${statusText}`;
  persistenceStatusBadge.dataset.persistenceStatus = safeStatus;
  persistenceStatusBadge.classList.remove("status-ok", "status-warn", "status-unknown");
  if (safeStatus === "OK") {
    persistenceStatusBadge.classList.add("status-ok");
  } else if (safeStatus === "STATELESS" || safeStatus === "UNAVAILABLE") {
    persistenceStatusBadge.classList.add("status-warn");
  } else {
    persistenceStatusBadge.classList.add("status-unknown");
  }
}

function updateDevModeUx(devMode = {}) {
  const enabled = devMode.enabled === true;
  const configured = devMode.configured === true;
  const codeInput = document.querySelector("#devCode");
  const submitButton = document.querySelector("#devForm button[type='submit']");
  const loadRunsButton = document.querySelector("#loadRuns");
  if (!enabled) {
    devModeStatus.textContent = "Dev Mode is disabled in this deployment.";
    codeInput.disabled = true;
    submitButton.disabled = true;
    loadRunsButton.disabled = true;
    return;
  }
  if (!configured) {
    devModeStatus.textContent = "Dev Mode is enabled, but no Dev Mode code is configured.";
    codeInput.disabled = true;
    submitButton.disabled = true;
    loadRunsButton.disabled = true;
    return;
  }
  devModeStatus.textContent = "Dev Mode is available. Re-auth to load debug tools.";
  codeInput.disabled = false;
  submitButton.disabled = false;
  loadRunsButton.disabled = false;
}

async function loadSystemStatus() {
  try {
    await sessionApi("/v1/system_status");
    return true;
  } catch {
    updatePersistenceStatus("UNKNOWN");
    return false;
  }
}

function showPanel(name) {
  for (const button of document.querySelectorAll(".tab")) {
    button.classList.toggle("active", button.dataset.tab === name);
  }
  for (const panel of ["single", "batch", "watchlist", "recent", "dev"]) {
    document.querySelector(`#${panel}Panel`).classList.toggle("hidden", panel !== name);
  }
  hideDetail();
  if (name === "watchlist") {
    loadWatchlist();
  }
  if (name === "recent") {
    loadRecentRuns();
  }
  updateRefreshButton();
}

function setLoading(id, active) {
  document.querySelector(id).classList.toggle("hidden", !active);
}

function setAnalysisActive(active) {
  analysisActive = active;
  updateRefreshButton();
}

function refreshActionLabel() {
  const tab = activeTabName();
  if (tab === "recent") return "Refresh";
  if (tab === "dev") return "Refresh status";
  return "Re-analyze";
}

function updateRefreshButton() {
  const now = Date.now();
  const cooldownActive = now < refreshReadyAt;
  refreshButton.disabled = analysisActive || cooldownActive || workspace.classList.contains("hidden");
  if (analysisActive) {
    refreshButton.textContent = "Re-analyzing...";
  } else if (cooldownActive) {
    refreshButton.textContent = `${refreshActionLabel()} (${Math.ceil((refreshReadyAt - now) / 1000)}s)`;
  } else {
    refreshButton.textContent = refreshActionLabel();
  }
  if (refreshTimer) {
    clearTimeout(refreshTimer);
    refreshTimer = null;
  }
  if (cooldownActive) {
    refreshTimer = setTimeout(updateRefreshButton, 1000);
  }
}

function startRefreshCooldown() {
  refreshReadyAt = Date.now() + refreshCooldownMs;
  updateRefreshButton();
}

function markRefreshed(label = "last refreshed") {
  lastRefreshed.textContent = `${label} at ${new Date().toLocaleTimeString()}`;
  startRefreshCooldown();
}

function activeTabName() {
  return document.querySelector(".tab.active")?.dataset.tab || "single";
}

function dataBannerText(display = {}) {
  if (display.is_live_data) {
    return `LIVE DATA - ${display.data_source}`;
  }
  if (display.data_source === "FIXTURE_DEMO") {
    return `DEMO DATA - ${display.data_source}`;
  }
  if (display.data_source === "UNAVAILABLE") {
    return `DATA UNAVAILABLE - ${display.data_source}`;
  }
  return `DEGRADED DATA - ${display.data_source || "DEGRADED"}`;
}

function formatNumber(value, digits = 2) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "n/a";
  }
  return value.toFixed(digits);
}

function formatPct(value) {
  return `${formatNumber(value)}%`;
}

function formatFractionPct(value) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "n/a";
  }
  return formatPct(value * 100);
}

function formatValue(value) {
  if (value === null || value === undefined) {
    return "n/a";
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : formatNumber(value, 4);
  }
  if (typeof value === "boolean") {
    return value ? "yes" : "no";
  }
  if (Array.isArray(value)) {
    return value.length ? value.join(", ") : "none";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function getScoreHeatBand(score) {
  const value = typeof score === "number" && Number.isFinite(score) ? score : 0;
  const safeScore = Math.max(0, Math.min(100, value));
  return (
    scoreHeatBands.find((band) => safeScore >= band.min && safeScore <= band.max) ||
    scoreHeatBands[scoreHeatBands.length - 1]
  );
}

function firstReason(payload) {
  const display = payload.frontend_display || {};
  const blockingReasons = Array.isArray(display.blocking_reasons)
    ? display.blocking_reasons
        .map((reason) => {
          const headline = typeof reason?.headline === "string" ? reason.headline : "";
          const detail = typeof reason?.detail === "string" ? reason.detail : "";
          return [headline, detail].filter(Boolean).join(": ");
        })
        .filter(Boolean)
    : [];
  const candidates = [
    ...(blockingReasons.length ? blockingReasons : display.key_reasons || []),
    ...(display.data_quality_warnings || []),
    ...(display.execution_warnings || []),
    ...(display.news_warnings || []),
  ];
  return candidates.find(Boolean) || "OK";
}

// The one authoritative view (plan §14.1-§14.3; owner rulings DP-A and DP-F). The backend builds it;
// this only renders its values, in the plan's information order, and recomputes nothing.
const NOT_ASSESSED_TEXT = "Not assessed (the data cannot support an assessment)";
const VENUE_LABELS = { cross_provider: "cross-checked venues" };

// The gates' disposition, labelled by what the view allows (owner ruling 2026-10-06): never a
// market call without an accepted directional permission; with one, the permission is shown, and
// the label stays explicitly non-advisory.
function dispositionLabel(view) {
  return view && view.directional_permission
    ? "Gate disposition (accepted directional permission; not financial advice)"
    : "Gate disposition (not a market call)";
}

// A raw gate token or block code shown outside the decision view says what it is (owner ruling
// S3): the gates' own internal token, not a market call. The value under it is shown as the
// backend gives it. Under an accepted directional permission the label stays non-advisory
// without the words the owner's ruling of 2026-10-06 keeps off a permission's screen.
function gateTokenLabel(name, kind, view) {
  return view && view.directional_permission
    ? `${name} (${kind}; not financial advice)`
    : `${name} (${kind}, not a market call)`;
}

// Under an accepted claim the view states the evidence level, as it states the data's health
// (owner ruling 2026-10-06). Legacy copy written for the uncalibrated heuristic then defers to it:
// a label reads the view's headline, an explanation its detail, and a reading the view already
// states beside it is not repeated. The backend's data (statuses, counts, verdicts), the gates
// and the scenario plan's prerequisites are shown as the backend states them. Without an accepted
// claim every surface reads exactly as before.
function acceptedViewOf(payload) {
  const view = decisionViewOf(payload);
  return view && view.accepted_claim ? view : null;
}

// A status the payload does not carry, under an accepted claim: missing, never "not measured".
const NOT_REPORTED_TEXT = "Not reported";

function decisionViewOf(payload) {
  const view = payload?.decision_view;
  return view && view.schema_version === "decision_view.v2" ? view : null;
}

// The one gate authority (owner ruling AD1=A): a gate view the backend built, for a live analysis
// in its decision view and for a saved run in the view built when it was read back. This only
// renders it.
function gateView(gates) {
  return gates && gates.schema_version === "gate_view.v1" ? gates : null;
}

function gateViewOf(payload) {
  return gateView(decisionViewOf(payload)?.gates);
}

// The view of a saved run (detail/saved_run_view.py): the backend builds it from what the run
// stores when the run is read back, and it travels with the detail, never with the history row.
function savedRunViewOf(detailView) {
  const saved = detailView?.saved_run_view;
  return saved && saved.schema_version === "saved_run_view.v1" ? saved : null;
}

// How a banner, a pill or a status that restates the gate result is styled (owner ruling X2):
// one CSS class, picked from the kinds the backend's gate view names and from nothing else.
// - a risk gate with a measured finding: the risk style;
// - a system or data gate and no risk gate: the safety/data style;
// - anything else: the neutral style. That is the evidence gate alone, a reopened run's liquidity
//   gate whose measurement the record does not hold, a gate result that cannot be read, and an
//   analysis without a view. The neutral style is never the risk one.
// Colour is a signal too, so it is the backend's kinds that choose it. This words nothing and
// changes no token: the text on a banner or a pill is what it was.
const GATE_ALERT_CLASSES = {
  RISK: "gate-alert-risk",
  SYSTEM_OR_DATA: "gate-alert-safety",
  NEUTRAL: "gate-alert-neutral",
};

function gateAlertClass(gates) {
  const kinds = Array.isArray(gateView(gates)?.kinds) ? gates.kinds : [];
  if (kinds.includes("RISK")) return GATE_ALERT_CLASSES.RISK;
  if (kinds.includes("SYSTEM_OR_DATA")) return GATE_ALERT_CLASSES.SYSTEM_OR_DATA;
  return GATE_ALERT_CLASSES.NEUTRAL;
}

// The gate authority as every surface shows it: the backend's summary, and directly under it the
// backend's framing of that summary. Both sentences are the backend's own, for every state
// (detail/gate_kinds.py); nothing here words a framing, and the two are never shown apart. They
// share one alert class, so the stylesheet draws them as one group.
function hasGateFraming(gates) {
  return Boolean(gates && backendText(gates.summary) && backendText(gates.framing));
}

function gateFramingBlocks(gates) {
  if (!hasGateFraming(gates)) return [];
  const alert = gateAlertClass(gates);
  return [
    textBlock("p", gates.summary, `decision-gates ${alert}`),
    textBlock("p", gates.framing, `decision-gate-framing ${alert}`),
  ];
}

// Each active gate, listed under the authority: the backend's headline and its detail sentence,
// one gate a line (as the older gate brief listed its reasons).
function gateDetailList(gates) {
  const lines = (Array.isArray(gates?.blocks) ? gates.blocks : [])
    .map((block) => [backendText(block?.headline), backendText(block?.detail)])
    .filter(([headline, detail]) => headline && detail)
    .map(([headline, detail]) => `${headline}: ${detail}`);
  if (!lines.length) return [];
  const list = listBlock(lines);
  list.classList.add("decision-gate-list");
  return [list];
}

function decisionDataBanner(data = {}) {
  if (data.state === "OK") {
    return `LIVE DATA - ${data.data_source}`;
  }
  if (data.state === "DEMO") {
    return `DEMO DATA - ${data.data_source}`;
  }
  if (data.state === "UNAVAILABLE") {
    return `DATA UNAVAILABLE - ${data.data_source || "UNAVAILABLE"}`;
  }
  return `DEGRADED DATA - ${data.data_source || "DEGRADED"}`;
}

function decisionDataText(data = {}) {
  const age = Number.isFinite(data.latest_candle_age_seconds)
    ? ` Latest candle ${data.latest_candle_age_seconds}s old.`
    : "";
  return data.summary ? `${data.state}: ${data.summary}${age}` : data.state || "n/a";
}

// Wherever the legacy display repeats data health or probabilities, it defers to the view: the
// view's data banner, and no percentage at all when the view holds no assessment.
function dataBannerFor(payload) {
  const view = decisionViewOf(payload);
  return view ? decisionDataBanner(view.data) : dataBannerText(payload?.frontend_display || {});
}

function notAssessedByView(payload) {
  return decisionViewOf(payload)?.range?.assessed === false;
}

function legacyProbabilityRows(payload, rows) {
  return notAssessedByView(payload)
    ? rows.map(([label]) => [label, NOT_ASSESSED_TEXT])
    : rows;
}

function decisionEvidenceText(evidence = {}) {
  if (evidence.directional_evidence_hold) {
    return "Directional evidence under review (the hold is active)";
  }
  const outcomes =
    evidence.resolved_outcomes === null || evidence.resolved_outcomes === undefined
      ? null
      : `${evidence.resolved_outcomes} resolved outcomes`;
  return [evidence.skill_verdict, outcomes, evidence.reliability_status].filter(Boolean).join(" · ")
    || "Unavailable";
}

function decisionViewRows(payload, view) {
  const display = payload.frontend_display || {};
  const data = view.data || {};
  const time = view.time || {};
  const range = view.range || {};
  const cost = view.cost || {};
  const notAssessed = range.assessed === false;
  return [
    [
      "Asset · venue",
      `${payload.normalized_symbol} · ${VENUE_LABELS[data.venue] || data.venue || "n/a"}`,
    ],
    ["Reference close (UTC)", time.reference_close_utc || "n/a"],
    ["Horizon end (UTC)", time.horizon_end_utc || "n/a"],
    ["Data", decisionDataText(data)],
    [
      // §14.2 item 4: storage, because whether this analysis was saved is known only after the
      // response (its persistence receipt), never in it.
      "Storage",
      persistenceStatusText(
        payload.debug?.persistence_status || payload.detail_view?.debug_lite?.persistence_status,
      ),
    ],
    [
      "In band (inside the decision band)",
      notAssessed
        ? NOT_ASSESSED_TEXT
        : `${formatFractionPct(range.in_band_frac)} (band ±${formatFractionPct(range.decision_band_frac)})`,
    ],
    ["Up (above the band)", notAssessed ? "Not assessed" : formatFractionPct(range.up_frac)],
    ["Down (below the band)", notAssessed ? "Not assessed" : formatFractionPct(range.down_frac)],
    [
      "Evidence level",
      view.accepted_claim
        ? view.headline
        : display.model_readiness_label || range.evidence_level || "n/a",
    ],
    ["Round-trip cost", formatFractionPct(cost.round_trip_cost_frac)],
    ...costCaveatRows(cost),
    ["Evidence", decisionEvidenceText(view.evidence)],
    [dispositionLabel(view), display.disposition],
  ];
}

// What the backend says about a cost it could not estimate in full (the view's `cost.caveat`, a
// saved run's too): its own sentence, on a row of its own directly under the cost. The frontend
// words nothing: with no sentence there is no row.
function costCaveatRows(cost) {
  const caveat = cost && typeof cost.caveat === "string" ? cost.caveat.trim() : "";
  return caveat ? [["Cost note", caveat]] : [];
}

// A value a reopened run's rows OUTSIDE its own block read from the view built from its stored
// record (the exact-final review's minor m3): the row's own value when the screen has one; else,
// for a reopened run, what that view holds, or the sentence that the record does not hold it. So
// one row never reads "n/a" for a value another row of the same screen shows. Without such a view
// the row's own value stands.
function keptValue(saved, own, kept) {
  if (own !== null && own !== undefined) return own;
  return saved ? savedValue(kept) : own;
}

// A reopened run's stored market-data block (the release-prep review's minor M-1). The screen's
// Market Data v2 section shows it whole: detail/builder.py copies each of its values from the
// analysis's data quality. A live analysis has none here: its rows read its own response.
function storedMarketBlock(saved, details) {
  const block = details?.market_data_v2_detail;
  return saved && block && typeof block === "object" && !Array.isArray(block) ? block : null;
}

// A row that repeats a value of that block: the row's own value when the screen has one; else,
// for a reopened run, the value the block holds, as its table below shows it (one it holds as
// null reads "n/a" in both places). Without the block the row's own value stands.
function storedMarketValue(market, own, key) {
  if (own !== null && own !== undefined) return own;
  return market ? market[key] : own;
}

// The Provider State rows whose values the market-data block also holds. A reopened run's history
// row carries no provider state, so for a value the block holds the row is left out: the block's
// table below shows it, and the row would only read "n/a" beside it.
function providerCrossRows(providerState, market) {
  const rows = [
    ["Cross-provider state", "cross_provider_state"],
    ["Fallback to single provider", "fallback_to_single_provider"],
    ["Disagreement bps", "disagreement_bps"],
  ];
  return rows.filter(([, key]) => {
    const own = providerState[key];
    const shownBelow = market && Object.prototype.hasOwnProperty.call(market, key);
    return (own !== null && own !== undefined) || !shownBelow;
  }).map(([label, key]) => [label, providerState[key]]);
}

// A reopened run's stored news add-on state (the release-prep review's minor MINOR-1). The
// screen's News Add-on section shows it whole: detail/builder.py stores the analysis's own news
// add-on state, the object a live analysis's news rows read. A live analysis has none here.
function storedNewsState(saved, details) {
  const state = details?.news_detail?.news_addon_state;
  return saved && state && typeof state === "object" && !Array.isArray(state) ? state : null;
}

// A news row that repeats a value of that state: the row's own value when the screen has one;
// else, for a reopened run, the value the state holds, as its table shows it. Without the state
// the row's own value stands.
function storedNewsValue(news, own, key) {
  if (own !== null && own !== undefined) return own;
  return news ? news[key] : own;
}

// A value of a saved run's view: what the stored record holds, or, where the backend gives none,
// the sentence that says it is not kept. Never "n/a": a reopened run says what it does not store.
function savedValue(value, format = (kept) => kept) {
  return value === null || value === undefined ? LIST_NOT_KEPT_TEXT : format(value);
}

// The rows of a reopened run, under the labels a live analysis uses for the same values.
function savedRunRows(payload, saved) {
  const time = saved.time || {};
  const range = saved.range || {};
  const evidence = saved.evidence || {};
  const notAssessed = range.assessed === false;
  const asset = payload.normalized_symbol || payload.symbol;
  const venue = savedValue(saved.venue, (kept) => VENUE_LABELS[kept] || kept);
  const band = range.decision_band_frac;
  const banded = band === null || band === undefined ? "" : ` (band ±${formatFractionPct(band)})`;
  return [
    // A value the record does not hold is said on a row of its own, never inside another value.
    ...(saved.venue
      ? [["Asset · venue", `${asset} · ${venue}`]]
      : [["Asset", asset], ["Venue", venue]]),
    ["Reference close (UTC)", savedValue(time.reference_close_utc)],
    ["Horizon end (UTC)", savedValue(time.horizon_end_utc)],
    [
      "In band (inside the decision band)",
      notAssessed
        ? NOT_ASSESSED_TEXT
        : savedValue(range.in_band_frac, (kept) => `${formatFractionPct(kept)}${banded}`),
    ],
    [
      "Up (above the band)",
      notAssessed ? "Not assessed" : savedValue(range.up_frac, formatFractionPct),
    ],
    [
      "Down (below the band)",
      notAssessed ? "Not assessed" : savedValue(range.down_frac, formatFractionPct),
    ],
    ["Evidence level", savedValue(evidence.level ?? evidence.probability_type)],
    ["Round-trip cost", savedValue(saved.cost?.round_trip_cost_frac, formatFractionPct)],
    ...costCaveatRows(saved.cost),
    [
      "Evidence",
      evidence.directional_evidence_hold
        ? decisionEvidenceText(evidence)
        : savedValue(evidence.skill_verdict),
    ],
    ["Calibration", savedValue(evidence.calibration_status)],
    ["Reliability", savedValue(evidence.reliability_status)],
    // Without a readable gate result there is no disposition to show: the block says so above.
    ...(gateView(saved.gates) ? [[dispositionLabel(null), savedValue(saved.disposition)]] : []),
  ];
}

// The block of a reopened run: what its percentages are, its gate authority (built by the backend
// when the run was read), then what the stored record holds. Every sentence is the backend's.
function renderSavedRun(payload, saved) {
  const gates = gateView(saved.gates);
  const range = saved.range || {};
  const sentence = (text, className) => (backendText(text) ? [textBlock("p", text, className)] : []);
  return section("Saved analysis", [
    ...sentence(range.explanation, "decision-detail"),
    // Without a readable gate result, the backend's note stands in the summary's place, in the
    // neutral style: never the risk or the amber one (the release-prep review's minor M-4).
    ...(gates
      ? [...gateFramingBlocks(gates), ...gateDetailList(gates)]
      : sentence(saved.gates_note, `decision-gate-note ${GATE_ALERT_CLASSES.NEUTRAL}`)),
    keyValueTable(savedRunRows(payload, saved)),
    ...sentence(range.meaning, "muted"),
    ...sentence(saved.cost?.label, "muted"),
  ]);
}

// The save receipt (owner ruling D4; plan §14.2 item 4). Whether an analysis was saved is known
// only after its response. So once a live analysis is shown, the backend is asked for that
// analysis's receipt, and the state it gives replaces the request-time text of the analysis's
// Storage row. Nothing is worked out here: the row shows the backend's state, or stays as it was.
// PROVISIONAL wording, pending the owner's approval.
const SAVE_RECEIPT_SCHEMA_VERSION = "save_receipt.v1";
const SAVE_RECEIPT_TEXT = {
  SAVED: "Saved to Recent Analysis history",
  PENDING: "Saving… not yet confirmed",
  // FAILED is every save the backend holds no acknowledgement of, among them one that may have
  // committed unconfirmed and a partial one. So the sentence says "not confirmed", never "not
  // saved".
  FAILED:
    "Save not confirmed: this analysis may be missing from Recent Analysis history after a " +
    "restart",
  NOT_RETAINED: "Not retained: no storage is configured",
};
// While the backend says PENDING: one further try after each of these delays, and no more.
const SAVE_RECEIPT_RETRY_DELAYS_MS = [1000, 2000, 4000];
// The label decisionViewRows gives the row that states storage.
const STORAGE_ROW_LABEL = "Storage";
// surface -> place -> watch. A surface is the element whose cards are replaced together. A place
// is where one card sits in it (a timeframe, a run, the panel): it shows one analysis at a time.
const saveReceiptWatches = new Map();

// The text of a receipt the backend gave for this run, or null when the answer is not one this
// screen can show: no answer, another schema version, another run's receipt, an unknown state.
function saveReceiptText(receipt, runId) {
  if (
    !receipt ||
    receipt.schema_version !== SAVE_RECEIPT_SCHEMA_VERSION ||
    receipt.run_id !== runId ||
    typeof receipt.state !== "string" ||
    !Object.prototype.hasOwnProperty.call(SAVE_RECEIPT_TEXT, receipt.state)
  ) {
    return null;
  }
  return SAVE_RECEIPT_TEXT[receipt.state];
}

// The value cell of the Storage row among the decision-view rows rendered under a node, or null.
function storageValueCell(container) {
  for (const list of container.querySelectorAll("dl")) {
    const labels = [...list.querySelectorAll("dt")];
    const index = labels.findIndex((label) => label.textContent === STORAGE_ROW_LABEL);
    if (index >= 0) {
      return list.querySelectorAll("dd")[index] || null;
    }
  }
  return null;
}

// Stops the receipt watches of what is being replaced, one place of a surface or all of it: no
// timer outlives its card, and an answer still on its way is ignored.
function cancelSaveReceipts(surface, place = null) {
  const watches = saveReceiptWatches.get(surface);
  for (const [watched, watch] of [...(watches || [])]) {
    if (place !== null && watched !== place) {
      continue;
    }
    watch.stopped = true;
    if (watch.timer !== null) {
      clearTimeout(watch.timer);
    }
    watches.delete(watched);
  }
}

// The same for every surface, when the operator's data is cleared.
function cancelAllSaveReceipts() {
  for (const surface of saveReceiptWatches.keys()) {
    cancelSaveReceipts(surface);
  }
}

// The receipts of the analyses a surface now shows as cards: each card asks for its own.
function watchSaveReceipts(surface, payloads) {
  cancelSaveReceipts(surface);
  for (const card of surface.querySelectorAll(".timeframe-card")) {
    const payload = payloads.find((item) => item.run_id && item.run_id === card.dataset.runId);
    if (payload) {
      watchSaveReceipt(surface, payload.run_id, payload, card);
    }
  }
}

// Asks for the receipt of one analysis that is now shown, and shows its state in that analysis's
// Storage row. Bounded: one request, and while the backend says PENDING one further try per entry
// of SAVE_RECEIPT_RETRY_DELAYS_MS. Each try schedules at most the next; nothing polls. Without a
// Storage row nothing is asked: a run reopened from history has no decision view, so no such row.
function watchSaveReceipt(surface, place, payload, container) {
  // Whatever this place showed before is replaced: its watch ends.
  cancelSaveReceipts(surface, place);
  const cell = payload.run_id ? storageValueCell(container) : null;
  if (!cell) {
    return;
  }
  const watch = { timer: null, stopped: false };
  if (!saveReceiptWatches.has(surface)) {
    saveReceiptWatches.set(surface, new Map());
  }
  saveReceiptWatches.get(surface).set(place, watch);
  const ask = async (attempt) => {
    watch.timer = null;
    let receipt = null;
    try {
      receipt = await sessionApi(`/v1/analyze/receipt/${encodeURIComponent(payload.run_id)}`);
    } catch {
      // The request failed or the run is unknown (404): there is no receipt to show.
      receipt = null;
    }
    if (watch.stopped) {
      return;
    }
    const text = saveReceiptText(receipt, payload.run_id);
    if (text !== null) {
      cell.textContent = text;
    }
    const delay = SAVE_RECEIPT_RETRY_DELAYS_MS[attempt];
    if (text === null || receipt.state !== "PENDING" || delay === undefined) {
      saveReceiptWatches.get(surface).delete(place);
      return;
    }
    watch.timer = setTimeout(() => void ask(attempt + 1), delay);
  };
  void ask(0);
}

function overviewCard(payload) {
  const node = overviewTemplate.content.firstElementChild.cloneNode(true);
  const display = payload.frontend_display;
  const view = decisionViewOf(payload);
  const timeframe = payload.timeframes?.primary || "n/a";
  const heatBand = getScoreHeatBand(display.total_score);
  node.classList.add("timeframe-card");
  node.classList.add(heatBand.className);
  node.dataset.timeframeCard = timeframe;
  if (payload.run_id) {
    // Whose card this is, so its save receipt reaches its own Storage row.
    node.dataset.runId = payload.run_id;
  }
  node.style.setProperty("--heat-main", heatBand.mainColor);
  node.style.setProperty("--heat-border", heatBand.mainColor);
  node.querySelector("h2").textContent = `${payload.normalized_symbol} · ${
    display.horizon_approx_label || timeframe
  }`;
  const demoBanner = document.createElement("p");
  demoBanner.className = "demo-banner";
  demoBanner.textContent = view ? decisionDataBanner(view.data) : dataBannerText(display);
  node.insertBefore(demoBanner, node.querySelector("dl"));
  if (view) {
    const headline = document.createElement("p");
    headline.className = "decision-headline";
    headline.dataset.decisionState = view.state;
    headline.textContent = view.headline;
    node.insertBefore(headline, node.querySelector("dl"));
    // The view's own sentence says what its state means (owner ruling CLASS-B-4=A).
    const sentence = document.createElement("p");
    sentence.className = "decision-detail";
    sentence.textContent = view.detail;
    node.insertBefore(sentence, node.querySelector("dl"));
    for (const line of gateFramingBlocks(gateViewOf(payload))) {
      node.insertBefore(line, node.querySelector("dl"));
    }
  }
  const heatRow = ["Signal heat (not risk)", heatBand.level];
  // The heat is a reading of the percentages: none is shown where the view assesses none.
  const viewHeat = notAssessedByView(payload) ? [] : [heatRow];
  const values = view ? [...decisionViewRows(payload, view), ...viewHeat] : [
    [dispositionLabel(null), display.disposition],
    ["Score", display.total_score],
    ["Setup", display.timeframe_label || timeframe],
    ["Horizon", display.horizon_label || "multi-bar horizon"],
    ["Up", formatPct(display.prob_up_pct)],
    ["Down", formatPct(display.prob_down_pct)],
    ["In band", formatPct(display.prob_timeout_pct)],
    ["Model readiness", display.model_readiness_label || modelReadinessCopy],
    ["Data", display.is_live_data ? "LIVE" : display.data_source],
    ["Source", display.data_source],
    ["Gate", firstReason(payload)],
    ["Heat", heatBand.level],
  ];
  appendDefinitionRows(node.querySelector("dl"), values);
  const note = node.querySelector(".news-note");
  note.textContent =
    payload.analysis_mode === "METRICS_ONLY"
      ? "News disabled in METRICS_ONLY."
      : payload.news_addon_state.status;
  node.querySelector(".detail-button").addEventListener("click", () => openDetail(payload));
  node.addEventListener("click", (event) => {
    if (event.target.closest("button")) {
      return;
    }
    openDetail(payload);
  });
  return node;
}

function loadingCard(timeframe) {
  const node = document.createElement("article");
  node.className = "result-card timeframe-card loading-card";
  node.dataset.timeframeCard = timeframe;
  node.innerHTML = `
    <header><h2>${timeframe}</h2><span class="badge">Loading</span></header>
    <p class="muted">Awaiting backend analysis.</p>
    <p class="heat-mini">${heatLegend}</p>
  `;
  return node;
}

function errorCard(timeframe, error) {
  const node = document.createElement("article");
  node.className = "result-card timeframe-card error-card";
  node.dataset.timeframeCard = timeframe;
  const header = document.createElement("header");
  const heading = document.createElement("h2");
  const badge = document.createElement("span");
  const message = document.createElement("p");
  const heat = document.createElement("p");
  heading.textContent = timeframe;
  badge.className = "badge danger";
  badge.textContent = "Error";
  message.textContent = error.message || "Analysis failed.";
  heat.className = "heat-mini";
  heat.textContent = heatLegend;
  header.append(heading, badge);
  node.append(header, message, heat);
  return node;
}

function timeframeRoleFor(payload, timeframe) {
  const backendRole = payload?.decision_synthesis?.timeframe_role || {};
  const fallback = fallbackTimeframeRoles[timeframe] || {
    role: "ROLE_UNAVAILABLE",
    tactical: tacticalTimeframes.includes(timeframe),
    rawProbabilityHidden: regimeTimeframes.includes(timeframe),
  };
  return {
    role: backendText(backendRole.role) || fallback.role,
    tactical:
      typeof backendRole.tactical === "boolean" ? backendRole.tactical : fallback.tactical,
    rawProbabilityHidden:
      typeof backendRole.raw_probability_hidden_by_default === "boolean"
        ? backendRole.raw_probability_hidden_by_default
        : fallback.rawProbabilityHidden,
    plainEnglish:
      backendText(backendRole.plain_english) || "Backend timeframe role description unavailable.",
  };
}

function timeframeGroupFor(payload, timeframe) {
  return timeframeRoleFor(payload, timeframe).tactical ? "tactical" : "regime";
}

function displayRole(role) {
  return backendText(role)?.replaceAll("_", " ").toLowerCase() || "role unavailable";
}

function matrixBlockingItem(stack) {
  return shownChecks(stack).find((item) => item.status === "BLOCK") || null;
}

function matrixRawProbability(probability = {}) {
  return keyValueTable([
    ["Up", formatFractionPct(probability.p_up)],
    ["Down", formatFractionPct(probability.p_down)],
    ["In band", formatFractionPct(probability.p_timeout)],
  ]);
}

function matrixProbabilityBlock(probability = {}, role = {}) {
  const block = document.createElement("div");
  block.className = "matrix-probability";
  if (probability.informational_only === true) {
    block.classList.add("matrix-probability-muted");
    block.append(decisionBadge("Informational only", "warn"));
  }
  if (role.rawProbabilityHidden) {
    const advanced = document.createElement("details");
    advanced.className = "matrix-advanced-context";
    advanced.append(textBlock("summary", "Advanced (uncalibrated context)"));
    advanced.append(
      textBlock(
        "p",
        "Uncalibrated context. Treat these values as informational only.",
        "matrix-context-warning",
      ),
    );
    advanced.append(matrixRawProbability(probability));
    block.append(advanced);
  } else {
    block.append(matrixRawProbability(probability));
  }
  if (backendText(probability.reliability_warning)) {
    block.append(textBlock("p", probability.reliability_warning, "matrix-reliability-note"));
  }
  return block;
}

function horizonCard(payload) {
  const node = document.createElement("article");
  const display = payload.frontend_display || {};
  const timeframe = payload.timeframes?.primary || "n/a";
  const synthesis = payload.decision_synthesis || {};
  const probability = synthesis.probability_interpretation || {};
  const quality = synthesis.model_quality_summary || {};
  const role = timeframeRoleFor(payload, timeframe);
  const blocking = matrixBlockingItem(synthesis.actionability_stack);
  const heatBand = getScoreHeatBand(display.total_score);

  node.className = `result-card timeframe-card horizon-card ${
    role.tactical ? "tactical-horizon-card" : "regime-horizon-card"
  }`;
  node.dataset.timeframeCard = timeframe;
  node.style.setProperty("--heat-main", heatBand.mainColor);
  node.style.setProperty("--heat-border", heatBand.mainColor);

  if (blocking) {
    const blockBanner = document.createElement("div");
    // The banner restates the gate result: its style is the gate view's kind, not a fixed red.
    const alert = gateAlertClass(gateViewOf(payload));
    blockBanner.className = `matrix-block-banner ${alert}`;
    blockBanner.append(decisionBadge("BLOCK", "block", alert));
    // With a view, the banner names the check that blocks, and the view below it carries the
    // gate summary with its framing: the summary is never shown apart from its framing.
    const viewLeads = Boolean(decisionViewOf(payload));
    blockBanner.append(
      textBlock(
        "span",
        (viewLeads ? null : backendText(blocking.plain_english)) ||
          backendText(blocking.label) ||
          "Blocked",
      ),
    );
    node.append(blockBanner);
  }

  const header = document.createElement("header");
  const headingGroup = document.createElement("div");
  headingGroup.append(textBlock("p", displayRole(role.role), "matrix-role"));
  headingGroup.append(textBlock("h2", timeframe));
  headingGroup.append(textBlock("p", payload.normalized_symbol || payload.symbol, "muted"));
  const detailButton = document.createElement("button");
  detailButton.type = "button";
  detailButton.className = "detail-button";
  detailButton.textContent = "Detail";
  header.append(headingGroup, detailButton);
  node.append(header);

  const view = decisionViewOf(payload);
  if (view) {
    // The one authoritative view leads (plan §14.1-§14.2): its state, its sentence, then its
    // rows. No raw probability is shown beside it.
    const headline = textBlock("p", view.headline, "decision-headline");
    headline.dataset.decisionState = view.state;
    node.append(headline);
    node.append(textBlock("p", view.detail, "decision-detail"));
    node.append(...gateFramingBlocks(gateViewOf(payload)));
    node.append(textBlock("p", role.plainEnglish, "matrix-role-description"));
    node.append(
      keyValueTable([
        ...decisionViewRows(payload, view),
        // The heat is a reading of the percentages: none is shown where the view assesses none.
        ...(notAssessedByView(payload) ? [] : [["Signal heat (not risk)", heatBand.level]]),
      ]),
    );
  } else {
    // A payload without a view (none is served today): its readings, and no older decision.
    node.append(textBlock("p", role.plainEnglish, "matrix-role-description"));
    node.append(
      keyValueTable([
        ["Interpretation", probability.interpretation_label],
        ["Directional edge", formatFractionPct(probability.directional_edge)],
        ["Reliability", quality.reliability_status],
      ]),
    );
    if (quality.not_win_rate === true) {
      node.append(textBlock("p", "Historical outcome-rate metric: Not established.", "muted"));
    }
    node.append(matrixProbabilityBlock(probability, role));
  }

  const demoBanner = textBlock("p", dataBannerFor(payload), "demo-banner");
  node.append(demoBanner);
  detailButton.addEventListener("click", () => openDetail(payload));
  node.addEventListener("click", (event) => {
    if (event.target.closest("button, details")) {
      return;
    }
    openDetail(payload);
  });
  return node;
}

function horizonGroupSection(group) {
  const wrapper = document.createElement("section");
  wrapper.className = `horizon-group horizon-group-${group.key}`;
  wrapper.dataset.horizonGroupSection = group.key;
  const header = document.createElement("div");
  header.className = "horizon-group-header";
  const heading = document.createElement("div");
  heading.append(textBlock("p", group.kicker, "eyebrow"));
  heading.append(textBlock("h2", group.title));
  heading.append(textBlock("p", group.description, "muted"));
  header.append(heading);
  const grid = document.createElement("div");
  grid.className = "timeframe-group-grid";
  grid.dataset.horizonGroup = group.key;
  for (const timeframe of group.timeframes) {
    grid.append(loadingCard(timeframe));
  }
  wrapper.append(header, grid);
  return wrapper;
}

function horizonGroups() {
  return [
    horizonGroupSection(
      {
        key: "tactical",
        kicker: "15m · 1H · 4H",
        title: "Tactical Horizon Matrix",
        description: "Backend timing and setup views.",
        timeframes: tacticalTimeframes,
      },
    ),
    horizonGroupSection(
      {
        key: "regime",
        kicker: "1D · 1W · 1M",
        title: "Regime Context",
        description: "Higher-horizon context, not an equal tactical forecast.",
        timeframes: regimeTimeframes,
      },
    ),
  ];
}

function appendDefinitionRows(dl, values) {
  for (const [label, value] of values) {
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = label;
    // A list of objects (a news provider's status, for one) is shown whole, as the detail tables
    // show one: its JSON, every field the backend gives. As text it would read "[object Object]".
    if (Array.isArray(value) && value.some((item) => item && typeof item === "object")) {
      dd.append(nestedValueBlock(value));
    } else {
      dd.textContent = formatValue(value);
    }
    dl.append(dt, dd);
  }
}

function batchErrorMessage(item) {
  const errorItem = item && typeof item === "object" && !Array.isArray(item) ? item : null;
  const detail =
    errorItem?.detail &&
    typeof errorItem.detail === "object" &&
    !Array.isArray(errorItem.detail)
      ? errorItem.detail
      : null;
  const error =
    detail?.error && typeof detail.error === "object" && !Array.isArray(detail.error)
      ? detail.error
      : null;
  const message =
    typeof error?.message === "string" && error.message.trim()
      ? error.message.trim()
      : "Batch item could not be analyzed.";
  const code =
    typeof error?.code === "string" && error.code.trim() ? error.code.trim() : null;
  const symbol =
    typeof errorItem?.symbol === "string" && errorItem.symbol.trim()
      ? ` (${errorItem.symbol.trim()})`
      : "";
  const label =
    Number.isInteger(errorItem?.index) && errorItem.index >= 0
      ? `Item ${errorItem.index + 1}${symbol}`
      : `Batch item${symbol}`;
  const codeSuffix = code ? ` (Code: ${code})` : "";

  return `${label}: ${message}${codeSuffix}`;
}

function batchFailureMessage(status, payload) {
  const detail =
    payload && typeof payload === "object" && !Array.isArray(payload) ? payload.detail : null;
  const errorEnvelope =
    detail && typeof detail === "object" && !Array.isArray(detail) ? detail.error : null;
  const backendMessage =
    errorEnvelope &&
    typeof errorEnvelope === "object" &&
    !Array.isArray(errorEnvelope) &&
    typeof errorEnvelope.message === "string" &&
    errorEnvelope.message.trim()
      ? errorEnvelope.message.trim()
      : null;

  if (status === 401) {
    return loginFailureMessage(status, payload);
  }
  if (status === 422) {
    return "Batch request was not accepted. Enter at least one symbol and try again.";
  }
  if (backendMessage) {
    return backendMessage;
  }
  if (typeof status !== "number") {
    return "Unable to reach the service. Check your connection and try again.";
  }
  return "Batch analysis is temporarily unavailable. Try again shortly.";
}

function renderBatchFailure(target, message) {
  const node = document.createElement("article");
  node.className = "result-card error-card";
  node.textContent = message;
  target.replaceChildren(node);
}

function renderResults(target, payloads, errors = [], items) {
  target.replaceChildren();
  if (Array.isArray(items)) {
    const payloadsByRunId = new Map(payloads.map((payload) => [payload.run_id, payload]));
    for (const item of items) {
      if (item.status === "OK") {
        const payload = payloadsByRunId.get(item.run_id);
        if (payload) target.append(overviewCard(payload));
      } else if (item.status === "ERROR") {
        const node = document.createElement("article");
        node.className = "result-card";
        node.textContent = batchErrorMessage(item);
        target.append(node);
      }
    }
    return;
  }
  for (const payload of payloads) {
    target.append(overviewCard(payload));
  }
  for (const item of errors) {
    const node = document.createElement("article");
    node.className = "result-card";
    node.textContent = batchErrorMessage(item);
    target.append(node);
  }
}

function replaceTimeframeCard(target, timeframe, node, groupKey) {
  // The card this timeframe showed is replaced: its receipt watch ends with it.
  cancelSaveReceipts(target, timeframe);
  const current = target.querySelector(`[data-timeframe-card="${timeframe}"]`);
  const group = target.querySelector(`[data-horizon-group="${groupKey}"]`);
  if (current && current.parentElement === group) {
    current.replaceWith(node);
    return;
  }
  current?.remove();
  if (!group) {
    target.append(node);
    return;
  }
  const order = groupKey === "tactical" ? tacticalTimeframes : regimeTimeframes;
  const position = order.indexOf(timeframe);
  const next = [...group.querySelectorAll("[data-timeframe-card]")].find(
    (item) => order.indexOf(item.dataset.timeframeCard) > position,
  );
  group.insertBefore(node, next || null);
}

function renderTimeframePlaceholders(target) {
  cancelSaveReceipts(target);
  target.replaceChildren(...horizonGroups());
  hideDetail();
}

async function runTimeframeSet({ symbol, analysisMode, target, loadingSelector, payloadStore }) {
  payloadStore.clear();
  renderTimeframePlaceholders(target);
  setLoading(loadingSelector, true);
  setAnalysisActive(true);
  try {
    const requests = singleTimeframes.map(async (timeframe) => {
      try {
        const payload = await sessionApi("/v1/analyze", {
          method: "POST",
          body: JSON.stringify({
            symbol,
            analysis_mode: analysisMode,
            timeframe,
          }),
        });
        payloadStore.set(timeframe, payload);
        payloadStore.set(payload.run_id, payload);
        const card = horizonCard(payload);
        replaceTimeframeCard(target, timeframe, card, timeframeGroupFor(payload, timeframe));
        watchSaveReceipt(target, timeframe, payload, card);
      } catch (error) {
        replaceTimeframeCard(
          target,
          timeframe,
          errorCard(timeframe, error),
          tacticalTimeframes.includes(timeframe) ? "tactical" : "regime",
        );
      }
    });
    await Promise.allSettled(requests);
    markRefreshed();
  } finally {
    setAnalysisActive(false);
    setLoading(loadingSelector, false);
  }
}

async function runSingleAnalysis(form) {
  await runTimeframeSet({
    symbol: String(form.get("symbol") || "").trim(),
    analysisMode: form.get("analysis_mode"),
    target: singleResult,
    loadingSelector: "#singleLoading",
    payloadStore: singlePayloads,
  });
}

async function openDetail(payload) {
  let detailView = null;
  if (payload.run_id && payload.frontend_display?.detail_available !== false) {
    try {
      detailView = await sessionApi(`/v1/analyze/detail/${payload.run_id}`);
    } catch {
      detailView = null;
    }
  }
  if (!detailView && payload.detail_view && Object.keys(payload.detail_view).length > 0) {
    detailView = payload.detail_view;
  }
  // Whatever the panel showed is replaced now: its receipt watch ends with it.
  cancelSaveReceipts(detailPanel);
  if (!detailView) {
    renderDetailUnavailable(payload);
    return;
  }
  renderStructuredDetail(payload, detailView);
  detailPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function formatRecentTime(value) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? String(value || "Time unavailable")
    : parsed.toLocaleString();
}

function uniqueRecentValues(runs, key, preferredOrder = null) {
  const values = [...new Set(runs.map((run) => run[key]).filter((value) => value != null))];
  if (preferredOrder == null) {
    return values.sort();
  }
  return values.sort((left, right) => {
    const leftIndex = preferredOrder.indexOf(left);
    const rightIndex = preferredOrder.indexOf(right);
    if (leftIndex === -1 && rightIndex === -1) {
      return left < right ? -1 : left > right ? 1 : 0;
    }
    if (leftIndex === -1) return 1;
    if (rightIndex === -1) return -1;
    return leftIndex - rightIndex;
  });
}

function filterRecentRuns(runs, filters) {
  return runs.filter(
    (run) =>
      (!filters.symbol || run.symbol === filters.symbol) &&
      (!filters.timeframe || run.primary_timeframe === filters.timeframe) &&
      (!filters.mode || run.analysis_mode === filters.mode),
  );
}

function recentSourceLabel(run) {
  const parts = [];
  const dataSource = String(run.data_source || "").trim();
  if (dataSource) {
    parts.push(dataSource);
  }
  if (run.is_live_data === true) {
    parts.push("Live data");
  } else if (run.is_live_data === false) {
    parts.push("Not live data");
  }
  return parts.join(" · ");
}

function recentEmptyMessage(totalCount, sourceNote) {
  return totalCount === 0
    ? `No recent analyses yet.${sourceNote}`
    : `No recent analyses match the selected filters.${sourceNote}`;
}

function setRecentFilterOptions(select, values, allLabel) {
  const selected = select.value;
  select.replaceChildren();
  const all = document.createElement("option");
  all.value = "";
  all.textContent = allLabel;
  select.append(all);
  for (const value of values) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.append(option);
  }
  select.value = values.includes(selected) ? selected : "";
}

function populateRecentFilters(runs) {
  setRecentFilterOptions(
    document.querySelector("#recentSymbolFilter"),
    uniqueRecentValues(runs, "symbol"),
    "All symbols",
  );
  setRecentFilterOptions(
    document.querySelector("#recentTimeframeFilter"),
    uniqueRecentValues(runs, "primary_timeframe", singleTimeframes),
    "All timeframes",
  );
  setRecentFilterOptions(
    document.querySelector("#recentModeFilter"),
    uniqueRecentValues(runs, "analysis_mode"),
    "All modes",
  );
}

function selectedRecentFilters() {
  return {
    symbol: document.querySelector("#recentSymbolFilter").value,
    timeframe: document.querySelector("#recentTimeframeFilter").value,
    mode: document.querySelector("#recentModeFilter").value,
  };
}

function renderRecentRuns(runs, source) {
  const target = document.querySelector("#recentList");
  const status = document.querySelector("#recentStatus");
  target.replaceChildren();
  const sourceNote = source === "in_process" ? " History is not durable right now." : "";
  if (runs.length === 0) {
    status.textContent = recentEmptyMessage(recentRuns.length, sourceNote);
    return;
  }
  status.textContent = `${runs.length} recent ${runs.length === 1 ? "analysis" : "analyses"}.${sourceNote}`;
  for (const run of runs) {
    const row = document.createElement(run.detail_available ? "button" : "div");
    const symbol = document.createElement("strong");
    const mode = document.createElement("span");
    const timeframe = document.createElement("span");
    const sourceIndicator = document.createElement("span");
    const time = document.createElement("time");
    row.className = "recent-row";
    symbol.textContent = run.symbol || "Symbol unavailable";
    mode.textContent = run.analysis_mode || "Mode unavailable";
    if (run.primary_timeframe != null) {
      timeframe.textContent = run.primary_timeframe;
    }
    sourceIndicator.textContent = recentSourceLabel(run);
    time.dateTime = run.as_of_utc || "";
    time.textContent = formatRecentTime(run.as_of_utc);
    row.append(symbol, mode);
    if (run.primary_timeframe != null) {
      row.append(timeframe);
    }
    if (sourceIndicator.textContent) {
      row.append(sourceIndicator);
    }
    row.append(time);
    if (run.detail_available) {
      row.type = "button";
      row.addEventListener("click", () => openDetail(run));
    } else {
      row.classList.add("recent-row-disabled");
      const note = document.createElement("small");
      note.textContent = "Full breakdown not available after restart.";
      row.append(note);
    }
    target.append(row);
  }
}

async function loadRecentRuns() {
  const target = document.querySelector("#recentList");
  const status = document.querySelector("#recentStatus");
  target.replaceChildren();
  status.textContent = "Loading recent analyses…";
  try {
    const payload = await sessionApi("/v1/runs");
    recentRuns = Array.isArray(payload.runs) ? payload.runs : [];
    recentRunsSource = payload.source;
    populateRecentFilters(recentRuns);
    renderRecentRuns(filterRecentRuns(recentRuns, selectedRecentFilters()), recentRunsSource);
    return true;
  } catch (error) {
    target.replaceChildren();
    status.textContent = `Recent analyses could not be loaded: ${error.message || "Request failed"}`;
    return false;
  }
}

for (const selector of ["#recentSymbolFilter", "#recentTimeframeFilter", "#recentModeFilter"]) {
  document.querySelector(selector).addEventListener("change", () => {
    renderRecentRuns(filterRecentRuns(recentRuns, selectedRecentFilters()), recentRunsSource);
  });
}

document.querySelector("#clearRecentFilters").addEventListener("click", () => {
  for (const selector of ["#recentSymbolFilter", "#recentTimeframeFilter", "#recentModeFilter"]) {
    document.querySelector(selector).value = "";
  }
  renderRecentRuns(recentRuns, recentRunsSource);
});

function hideDetail() {
  cancelSaveReceipts(detailPanel);
  detailPanel.replaceChildren();
  detailPanel.classList.add("hidden");
}

function renderDetailUnavailable(payload) {
  const message = document.createElement("p");
  message.className = "muted";
  message.textContent = "Detail Analysis is unavailable for this result.";
  detailPanel.replaceChildren(
    section("Detail Analysis", [
      keyValueTable([
        ["Symbol", payload?.normalized_symbol],
        ["Run ID", payload?.run_id],
        ["Status", "Unavailable"],
      ]),
      message,
    ]),
  );
  detailPanel.classList.remove("hidden");
  detailPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function section(title, children) {
  const node = document.createElement("section");
  node.className = "detail-section";
  const heading = document.createElement("h3");
  heading.textContent = title;
  node.append(heading, ...children);
  return node;
}

function keyValueTable(values) {
  const dl = document.createElement("dl");
  dl.className = "detail-kv";
  appendDefinitionRows(dl, values);
  return dl;
}

// An object or a list the backend gives, shown whole: a fold that names its size, over its JSON.
// A list's size reads "0 items", "1 item", "2 items"; an object's fold reads "View".
function nestedValueBlock(item) {
  const nested = document.createElement("details");
  const summary = document.createElement("summary");
  summary.textContent = Array.isArray(item)
    ? `${item.length} ${item.length === 1 ? "item" : "items"}`
    : "View";
  const pre = document.createElement("pre");
  pre.textContent = JSON.stringify(item, null, 2);
  nested.append(summary, pre);
  return nested;
}

function objectTable(value) {
  const table = document.createElement("table");
  table.className = "detail-table";
  const body = document.createElement("tbody");
  for (const [key, item] of Object.entries(value || {})) {
    const row = document.createElement("tr");
    const label = document.createElement("th");
    const content = document.createElement("td");
    label.textContent = key.replaceAll("_", " ");
    if (item && typeof item === "object") {
      content.append(nestedValueBlock(item));
    } else {
      content.textContent = formatValue(item);
    }
    row.append(label, content);
    body.append(row);
  }
  table.append(body);
  return table;
}

function listBlock(items = []) {
  const list = document.createElement("ul");
  list.className = "detail-list";
  for (const item of items || []) {
    const entry = document.createElement("li");
    entry.textContent = String(item);
    list.append(entry);
  }
  if (!list.children.length) {
    const entry = document.createElement("li");
    entry.textContent = "none";
    list.append(entry);
  }
  return list;
}

function jsonFilename(payload) {
  const symbol = String(payload.normalized_symbol || payload.symbol || "symbol")
    .replaceAll("/", "-")
    .replace(/[^\w.-]+/g, "-");
  const timeframe = payload.timeframes?.primary ? `${payload.timeframes.primary}_` : "";
  const runId = payload.run_id || "run";
  return `ucpe_${symbol}_${timeframe}${runId}.json`;
}

function downloadPayloadJson(payload) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = jsonFilename(payload);
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function downloadJsonButton(payload) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "download-json-button";
  button.textContent = "Download JSON";
  button.addEventListener("click", () => downloadPayloadJson(payload));
  return button;
}

// What a reopened run shows for a value its stored record does not hold (savedValue).
const LIST_NOT_KEPT_TEXT = "Not kept in saved history.";

function backendText(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function textBlock(tagName, text, className = "") {
  const node = document.createElement(tagName);
  node.textContent = text;
  if (className) {
    node.className = className;
  }
  return node;
}

function decisionBadge(text, tone = "neutral", alert = "") {
  const classes = `decision-badge decision-badge-${tone}${alert ? ` ${alert}` : ""}`;
  return textBlock("span", text, classes);
}

function orderedActionability(items) {
  if (!Array.isArray(items)) {
    return [];
  }
  return [...items]
    .filter((item) => item && typeof item === "object")
    .sort((left, right) => {
      const leftPriority = Number.isFinite(left.priority) ? left.priority : 999;
      const rightPriority = Number.isFinite(right.priority) ? right.priority : 999;
      return leftPriority - rightPriority;
    });
}

// The checks the screen lists. The backend's last check restates the label of the older
// decision card ("Final decision"), which is retired from the default screen: it is not listed,
// and it never puts up the card's BLOCK banner by itself.
const RETIRED_CHECKS = ["final_decision"];

function shownChecks(items) {
  return orderedActionability(items).filter((item) => !RETIRED_CHECKS.includes(item.key));
}

function decisionStatusTone(status) {
  return {
    BLOCK: "block",
    WARN: "warn",
    PASS: "pass",
    INFO: "info",
    UNKNOWN: "unknown",
  }[status] || "unknown";
}

function renderActionabilityRow(item = {}, payload = {}) {
  const status = backendText(item.status) || "UNKNOWN";
  const row = document.createElement("article");
  // A check that blocks restates the gate result: it takes the gate view's alert class. Every
  // other status keeps its own style.
  const alert = status === "BLOCK" ? gateAlertClass(gateViewOf(payload)) : "";
  row.className = `actionability-row actionability-${decisionStatusTone(status)}${
    alert ? ` ${alert}` : ""
  }`;
  const header = document.createElement("div");
  header.className = "actionability-row-header";
  header.append(decisionBadge(status, decisionStatusTone(status), alert));
  header.append(textBlock("strong", backendText(item.label) || backendText(item.key) || "Check"));
  if (Number.isFinite(item.priority)) {
    header.append(textBlock("span", `#${item.priority}`, "actionability-priority"));
  }
  row.append(header);
  if (backendText(item.plain_english)) {
    row.append(textBlock("p", item.plain_english));
  }
  const view = decisionViewOf(payload);
  if (item.key === "data_quality" && view && view.data?.state !== "OK") {
    // The view's data state qualifies this check: the data passed it, and the view says why it is
    // still not plain live data.
    row.append(textBlock("p", `Decision view: ${decisionDataText(view.data)}`, "decision-warning"));
  }
  const evidence = Array.isArray(item.evidence_refs) ? item.evidence_refs.filter(Boolean) : [];
  if (evidence.length) {
    row.append(textBlock("p", `Evidence: ${evidence.join(", ")}`, "actionability-evidence"));
  }
  return row;
}

function renderActionabilityStack(items, payload = {}) {
  const wrapper = document.createElement("div");
  wrapper.className = "decision-subsection";
  wrapper.append(textBlock("h4", "Actionability stack"));
  const stack = document.createElement("div");
  stack.className = "actionability-stack";
  const ordered = shownChecks(items);
  for (const item of ordered) {
    stack.append(renderActionabilityRow(item, payload));
  }
  if (!ordered.length) {
    stack.append(textBlock("p", "Actionability detail unavailable.", "muted"));
  }
  wrapper.append(stack);
  return wrapper;
}

function probabilityValues(probability = {}) {
  return [
    ["Up", formatFractionPct(probability.p_up)],
    ["Down", formatFractionPct(probability.p_down)],
    ["In band", formatFractionPct(probability.p_timeout)],
    ["Directional edge", formatFractionPct(probability.directional_edge)],
    ["Up + Down (outside the band)", formatFractionPct(probability.resolution_probability)],
    ["Directional balance", formatFractionPct(probability.directional_balance)],
  ];
}

function renderProbabilityInterpretation(probability = {}, timeframeRole = {}, payload = {}) {
  // Under an accepted claim the view's detail states what the percentages carry, in place of
  // the heuristic reading, its "informational only" badge and its reliability warning.
  const accepted = acceptedViewOf(payload);
  const card = document.createElement("article");
  card.className = "decision-context-card probability-interpretation";
  if (probability.informational_only === true && !accepted) {
    card.classList.add("probability-informational");
  }
  const heading = document.createElement("div");
  heading.className = "decision-context-heading";
  heading.append(textBlock("h4", "Probability interpretation"));
  if (probability.informational_only === true && !accepted) {
    heading.append(decisionBadge("Informational only", "warn"));
  }
  card.append(heading);
  // Where the view assesses nothing, no directional reading is shown beside it.
  const assessed = !notAssessedByView(payload);
  if (assessed && backendText(probability.interpretation_label)) {
    card.append(decisionBadge(probability.interpretation_label, "info"));
  }
  if (accepted) {
    card.append(textBlock("p", accepted.detail, "decision-context-copy"));
  } else if (assessed && backendText(probability.plain_english)) {
    card.append(textBlock("p", probability.plain_english, "decision-context-copy"));
  }

  const rawValues = keyValueTable(legacyProbabilityRows(payload, probabilityValues(probability)));
  if (timeframeRole.raw_probability_hidden_by_default === true) {
    const advanced = document.createElement("details");
    advanced.className = "decision-advanced-probability";
    advanced.append(
      textBlock("summary", accepted ? "Advanced probability" : "Advanced heuristic probability"),
    );
    advanced.append(rawValues);
    card.append(advanced);
  } else {
    card.append(rawValues);
  }

  if (!accepted && backendText(probability.reliability_warning)) {
    card.append(textBlock("p", probability.reliability_warning, "decision-warning"));
  }
  if (backendText(timeframeRole.plain_english)) {
    card.append(textBlock("p", timeframeRole.plain_english, "muted"));
  }
  card.append(
    keyValueTable([
      ["Timeframe role", timeframeRole.role],
      ["Tactical", timeframeRole.tactical],
      ["Raw probability secondary", timeframeRole.raw_probability_hidden_by_default],
    ]),
  );
  return card;
}

function hasPayloadValue(value) {
  return value !== null && value !== undefined;
}

async function loadCalibrationDiagnostics() {
  const now = Date.now();
  if (
    calibrationDiagnosticsCache &&
    now - calibrationDiagnosticsCachedAt < calibrationDiagnosticsCacheTtlMs
  ) {
    return calibrationDiagnosticsCache;
  }
  if (calibrationDiagnosticsRequest) {
    return calibrationDiagnosticsRequest;
  }

  calibrationDiagnosticsRequest = sessionApi("/v1/calibration")
    .catch(() => ({
      status: "UNAVAILABLE",
      timeframes: [],
      warnings: ["Calibration diagnostics unavailable. Keep using heuristic status."],
    }))
    .then((payload) => {
      calibrationDiagnosticsCache = payload;
      calibrationDiagnosticsCachedAt = Date.now();
      return payload;
    })
    .finally(() => {
      calibrationDiagnosticsRequest = null;
    });
  return calibrationDiagnosticsRequest;
}

function formatCalibrationMetric(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "—";
  }
  return value.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
}

function formatCalibrationPercent(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "—";
  }
  return `${(value * 100).toFixed(1)}%`;
}

function formatCalibrationCount(value) {
  return Number.isInteger(value) && value >= 0 ? String(value) : "—";
}

function calibrationGateLabel(gate) {
  return (
    {
      NO_SAMPLES: "No samples",
      INSUFFICIENT_SAMPLE: "Insufficient sample",
      WARMING_UP: "Warming up",
      PRELIMINARY_MEASURED: "Preliminary measured",
      MEASURED: "Measured",
    }[gate] || "Unavailable"
  );
}

function calibrationGateClass(gate) {
  return (
    {
      NO_SAMPLES: "none",
      INSUFFICIENT_SAMPLE: "insufficient",
      WARMING_UP: "warming",
      PRELIMINARY_MEASURED: "preliminary",
      MEASURED: "measured",
    }[gate] || "unknown"
  );
}

function calibrationGateNote(gate) {
  return (
    {
      NO_SAMPLES: "No resolved samples yet.",
      INSUFFICIENT_SAMPLE: "Early diagnostic — not measured yet.",
      WARMING_UP: "Early diagnostic — reliability not established.",
      PRELIMINARY_MEASURED: "Preliminary diagnostic — reliability remains limited.",
      MEASURED: "Measured calibration diagnostic — not a guarantee.",
    }[gate] || "Calibration status unavailable."
  );
}

function formatOutcomeDistribution(distribution) {
  if (!distribution || typeof distribution !== "object") {
    return "—";
  }
  return `UP ${formatCalibrationCount(distribution.UP)} / DOWN ${formatCalibrationCount(
    distribution.DOWN,
  )} / IN BAND ${formatCalibrationCount(distribution.TIMEOUT)}`;
}

function renderCalibrationVersions(item = {}) {
  const versions = item.versions_present || {};
  const modelVersions = Array.isArray(versions.model_versions)
    ? versions.model_versions.filter((value) => backendText(value))
    : [];
  const methodologyVersions = Array.isArray(versions.methodology_versions)
    ? versions.methodology_versions.filter((value) => backendText(value))
    : [];
  if (!modelVersions.length && !methodologyVersions.length) {
    return null;
  }
  const advanced = document.createElement("details");
  advanced.className = "calibration-version-context";
  advanced.append(textBlock("summary", "Version context"));
  advanced.append(
    keyValueTable([
      ["Model versions", modelVersions.join(", ") || "—"],
      ["Methodology versions", methodologyVersions.join(", ") || "—"],
    ]),
  );
  return advanced;
}

function renderCalibrationTimeframe(item = {}) {
  const gate = backendText(item.sample_gate) || "UNKNOWN";
  const card = document.createElement("article");
  card.className = `calibration-timeframe-card calibration-gate-${calibrationGateClass(gate)}`;
  card.dataset.calibrationTimeframe = backendText(item.timeframe) || "unknown";

  const header = document.createElement("header");
  header.className = "calibration-card-header";
  header.append(textBlock("h5", backendText(item.timeframe) || "Timeframe unavailable"));
  header.append(
    textBlock(
      "span",
      calibrationGateLabel(gate),
      `calibration-gate-badge calibration-gate-badge-${calibrationGateClass(gate)}`,
    ),
  );
  card.append(header);
  card.append(textBlock("p", calibrationGateNote(gate), "calibration-gate-note"));

  const values = [
    ["Resolved sample count", formatCalibrationCount(item.sample_count)],
    ["Reliability status", calibrationGateLabel(item.reliability_status)],
    ["Brier score", formatCalibrationMetric(item.brier_score)],
    ["Log loss", formatCalibrationMetric(item.log_loss)],
    ["Top-label hit rate (diagnostic)", formatCalibrationPercent(item.top_label_hit_rate)],
    ["Outcomes", formatOutcomeDistribution(item.outcome_distribution)],
    [
      "Version mix warning",
      typeof item.version_mix_warning === "boolean"
        ? item.version_mix_warning
          ? "Yes"
          : "No"
        : "—",
    ],
  ];
  if (
    hasPayloadValue(item.valid_count) &&
    item.valid_count !== item.sample_count
  ) {
    values.splice(1, 0, ["Valid resolved samples", formatCalibrationCount(item.valid_count)]);
  }
  card.append(keyValueTable(values));

  const versions = renderCalibrationVersions(item);
  if (versions) {
    card.append(versions);
  }
  if (backendText(item.warning)) {
    card.append(textBlock("p", item.warning, "calibration-item-warning"));
  }
  return card;
}

function renderCalibrationUnavailable(accepted = null) {
  const fallback = document.createElement("div");
  fallback.className = "calibration-unavailable";
  fallback.append(
    textBlock(
      "p",
      accepted
        ? "Calibration diagnostics unavailable."
        : "Calibration diagnostics unavailable. Keep using heuristic status.",
      "muted",
    ),
  );
  return fallback;
}

function renderCalibrationDiagnostics(payload, accepted = null) {
  if (
    payload?.status !== "OK" ||
    !Array.isArray(payload.timeframes) ||
    payload.timeframes.length === 0
  ) {
    return renderCalibrationUnavailable(accepted);
  }

  const wrapper = document.createElement("section");
  wrapper.className = "calibration-diagnostics";
  wrapper.append(textBlock("h4", "Per-timeframe calibration diagnostics"));
  wrapper.append(
    textBlock(
      "p",
      accepted
        ? "Diagnostic only — not profitability evidence, not trade EV."
        : "Early diagnostic only — not accuracy, not profitability evidence, not trade EV.",
      "calibration-disclaimer",
    ),
  );
  const grid = document.createElement("div");
  grid.className = "calibration-grid";
  for (const item of payload.timeframes) {
    grid.append(renderCalibrationTimeframe(item || {}));
  }
  wrapper.append(grid);
  return wrapper;
}

function calibrationDiagnosticsMount() {
  const mount = document.createElement("section");
  mount.className = "calibration-diagnostics-mount";
  mount.setAttribute("data-calibration-diagnostics", "");
  mount.setAttribute("aria-live", "polite");
  mount.append(textBlock("h4", "Live calibration diagnostics"));
  mount.append(textBlock("p", "Read-only diagnostic", "calibration-read-only-label"));
  const content = document.createElement("div");
  content.className = "calibration-diagnostics-content";
  content.append(textBlock("p", "Loading calibration diagnostics…", "muted"));
  mount.append(content);
  return mount;
}

function renderModelQualityEducation() {
  const education = document.createElement("details");
  education.className = "model-quality-education";
  education.append(textBlock("summary", "How to read model quality"));
  education.append(
    keyValueTable([
      ["Heuristic probability", "An early estimate produced before measured calibration is established."],
      ["Insufficient sample", "Too few resolved outcomes are available for a stable quality assessment."],
      ["Measured calibration", "A comparison between forecast probabilities and resolved outcomes after the sample gate is met."],
      ["Brier score", "Average squared probability error; interpret only with a comparable resolved sample."],
      ["Log loss", "A probability error measure that weighs confidently wrong forecasts more heavily."],
      ["Top-label hit rate", "How often the highest-probability label matched the resolved outcome; it is not a complete quality measure."],
      ["Why correctness alone is incomplete", "Probability quality also depends on calibration, sample size, outcome mix, and evaluation context."],
      ["Why this is not profitability evidence", "Forecast diagnostics do not include execution costs, sizing, or realized returns."],
    ]),
  );
  return education;
}

function renderModelQuality(quality = {}, probability = {}, accepted = null) {
  const card = document.createElement("article");
  card.className = "decision-context-card decision-model-quality";
  card.append(textBlock("h4", "Current status"));
  const explanation = accepted
    ? accepted.detail
    : backendText(quality.plain_english) || backendText(quality.warning);
  card.append(
    textBlock(
      "p",
      explanation || "Model quality: not measured yet.",
      "decision-context-copy",
    ),
  );
  const missing = accepted ? NOT_REPORTED_TEXT : "Not measured yet";
  const values = [
    ["Calibration status", quality.calibration_status || missing],
    ["Reliability status", quality.reliability_status || missing],
  ];
  if (hasPayloadValue(quality.reliability_available)) {
    values.push(["Reliability available", quality.reliability_available]);
  }
  if (hasPayloadValue(quality.sample_count)) {
    values.push(["Resolved sample count", quality.sample_count]);
  }
  if (hasPayloadValue(quality.sample_gate)) {
    values.push(["Sample gate", quality.sample_gate]);
  }
  if (hasPayloadValue(quality.brier_score)) {
    values.push(["Brier score", quality.brier_score]);
  }
  if (hasPayloadValue(quality.log_loss)) {
    values.push(["Log loss", quality.log_loss]);
  }
  if (hasPayloadValue(quality.top_label_hit_rate)) {
    values.push(["Top-label hit rate", quality.top_label_hit_rate]);
  }
  card.append(keyValueTable(values));
  if (quality.not_win_rate === true) {
    card.append(textBlock("p", "Historical outcome-rate metric: Not established.", "muted"));
  }
  if (accepted) {
    // The view's detail above states the evidence; no heuristic warning is repeated.
  } else if (backendText(probability.reliability_warning)) {
    card.append(
      textBlock("p", probability.reliability_warning, "model-quality-probability-warning"),
    );
  } else {
    card.append(
      textBlock(
        "p",
        "Probabilities are heuristic until enough resolved samples exist.",
        "model-quality-probability-warning",
      ),
    );
  }
  const surfacedMetrics = [
    quality.sample_count,
    quality.sample_gate,
    quality.brier_score,
    quality.log_loss,
    quality.top_label_hit_rate,
  ].some(hasPayloadValue);
  if (!surfacedMetrics) {
    card.append(
      textBlock("p", "Resolved-sample metrics are not surfaced in this view yet.", "muted"),
    );
  }
  card.append(
    textBlock(
      "p",
      accepted
        ? "No profitability claim."
        : "Keep collecting samples; this is not reliability evidence and not profitability evidence.",
      "muted",
    ),
  );
  return card;
}

function renderModelQualitySection(synthesis = {}, accepted = null) {
  const calibrationMount = calibrationDiagnosticsMount();
  const calibrationContent = calibrationMount.querySelector(
    ".calibration-diagnostics-content",
  );
  void loadCalibrationDiagnostics().then((payload) => {
    calibrationContent?.replaceChildren(renderCalibrationDiagnostics(payload, accepted));
  });
  return section("Model Quality", [
    renderModelQuality(
      synthesis.model_quality_summary || {},
      synthesis.probability_interpretation || {},
      accepted,
    ),
    calibrationMount,
    renderModelQualityEducation(),
  ]);
}

// The kept checks of a live analysis: how its percentages read, and the checks in order. The
// older decision card, gate checks card, advisor explanation, scenario plan and future-quant block
// are retired from the default screen (the parity review, 2026-10-11): the decision view above
// carries the gate authority, and nothing here restates it in words of its own. A run without a
// decision synthesis (a reopened run) has no such section.
function renderDecisionSynthesis(synthesis, payload = {}) {
  const available =
    synthesis && typeof synthesis === "object" && Object.keys(synthesis).length > 0;
  if (!available) {
    return null;
  }
  return section("Decision", [
    renderProbabilityInterpretation(
      synthesis.probability_interpretation || {},
      synthesis.timeframe_role || {},
      payload,
    ),
    renderActionabilityStack(synthesis.actionability_stack, payload),
  ]);
}

// The decision view as the detail panel shows it: its headline and sentence, the gate authority
// (the summary, its framing, each active gate), its rows, then its notes. Every sentence is the
// backend's. The owner's UX card prints exactly what this draws (scripts/ux_comprehension).
function renderDecisionViewSection(payload, view) {
  const gates = gateViewOf(payload);
  return section("Decision view", [
    textBlock("p", view.headline, "decision-headline"),
    textBlock("p", view.detail, "decision-detail"),
    ...gateFramingBlocks(gates),
    ...gateDetailList(gates),
    keyValueTable(decisionViewRows(payload, view)),
    textBlock("p", view.range?.meaning || "", "muted"),
    // What the percentages are: the backend's sentence, where the view carries one.
    ...(backendText(view.range?.explanation)
      ? [textBlock("p", view.range.explanation, "muted")]
      : []),
    textBlock("p", view.cost?.label || "", "muted"),
    listBlock(view.evidence?.limitations || []),
  ]);
}

function renderStructuredDetail(payload, detailView) {
  // Raw JSON and Download JSON are the backend's response exactly as it was returned: nothing
  // the renderers need is ever added to it.
  const backendResponse = payload;
  // A saved run has no view; the backend built one from what the run stores when it was read
  // back, and the run's own block shows it.
  const saved = decisionViewOf(payload) ? null : savedRunViewOf(detailView);
  const display = payload.frontend_display || {};
  const dataQuality = payload.data_quality || {};
  const providerState = payload.provider_state || {};
  const gate = payload.gate_result || {};
  const details = detailView || {};
  // A reopened run's history row carries none of these rows' values. Where the view built from
  // its stored record holds one, the row shows it, as the run's own block does: in Overview, in
  // Gates, and for the data source, the live-data flag and the venue in the data sections below.
  // A row that repeats a value of the stored market-data block (the warnings, the symbol's
  // availability, the cross-provider values) shows the block's value; in Provider State it is left
  // out instead. The news rows that repeat a value of the stored news add-on state (its status,
  // its warnings and its influence mode) show that value, as News Add-on's table of it does; a
  // METRICS_ONLY run's "State" row still says news analysis was disabled, and with news analysis
  // on a record without that state reads "UNAVAILABLE", as before. A value none of these holds
  // (the score; the data-quality status, age and failures; the provider's status and reason)
  // still reads "n/a". So does the news "Provider status" row, though that table shows a stored
  // list: utils/sanitize.py masks a provider's `last_failure_error_code` in the record, so the
  // stored list is not a copy of the one the row reads.
  const kept = saved || {};
  const keptMarket = storedMarketBlock(saved, details);
  const keptNews = storedNewsState(saved, details);
  const newsCopy =
    payload.analysis_mode === "METRICS_ONLY"
      ? "News analysis disabled for this run."
      : storedNewsValue(keptNews, payload.news_addon_state?.status, "status") || "UNAVAILABLE";

  const rawJson = document.createElement("details");
  rawJson.className = "raw-json";
  const summary = document.createElement("summary");
  summary.textContent = "Debug / Raw JSON";
  const pre = document.createElement("pre");
  pre.textContent = JSON.stringify(backendResponse, null, 2);
  rawJson.append(summary, pre);

  const view = decisionViewOf(payload);
  const accepted = acceptedViewOf(payload);
  const decisionSection = view ? renderDecisionViewSection(payload, view) : null;
  // A reopened run leads with its own block instead.
  const savedSection = saved ? renderSavedRun(backendResponse, saved) : null;
  const checksSection = renderDecisionSynthesis(payload.decision_synthesis, payload);

  detailPanel.replaceChildren(
    ...(decisionSection ? [decisionSection] : []),
    ...(savedSection ? [savedSection] : []),
    ...(checksSection ? [checksSection] : []),
    renderModelQualitySection(payload.decision_synthesis || {}, accepted),
    section("Overview", [
      downloadJsonButton(backendResponse),
      keyValueTable([
        ["Symbol", payload.normalized_symbol || payload.symbol || details.symbol],
        [
          "Timeframe",
          payload.timeframes?.timeframe_label || payload.timeframes?.primary || kept.timeframe_label,
        ],
        ["Horizon", payload.timeframes?.horizon_label || kept.horizon_label],
        ["Analysis mode", payload.analysis_mode],
        // The same value as the decision view's own row, under the same label.
        [dispositionLabel(view), display.disposition ?? kept.disposition],
        ["Score", display.total_score],
        ["As of UTC", payload.as_of_utc],
        ["Run ID", payload.run_id],
        ["Data source", keptValue(saved, display.data_source, kept.data?.data_source)],
        view
          ? ["Data", decisionDataText(view.data)]
          : ["Live data", keptValue(saved, display.is_live_data, kept.data?.is_live_data)],
        [
          // Storage's status when the analysis was requested. A live analysis's Storage row (the
          // decision view's) shows its save receipt, which can say otherwise: so this label says
          // which of the two it is.
          "Storage when requested",
          persistenceStatusText(
            payload.debug?.persistence_status || details.debug_lite?.persistence_status,
          ),
        ],
      ]),
    ]),
    section("Gates", [
      keyValueTable([
        [
          gateTokenLabel("Gate action", "internal gate token", view),
          gate.action ?? kept.gate_action,
        ],
        [
          gateTokenLabel("Hard blocks", "internal gate tokens", view),
          gate.hard_blocks ?? kept.hard_blocks,
        ],
        ["Warnings", storedMarketValue(keptMarket, dataQuality.warnings, "warnings")],
      ]),
      objectTable(details.risk_detail),
    ]),
    section("Market Data Quality", [
      keyValueTable([
        ...(view ? [["Decision view", decisionDataText(view.data)]] : []),
        ["Status", dataQuality.status],
        ["Latest age seconds", dataQuality.latest_candle_age_seconds],
        ["Warnings", storedMarketValue(keptMarket, dataQuality.warnings, "warnings")],
        ["Failures", dataQuality.provider_failures],
        ["Data source", keptValue(saved, dataQuality.data_source, kept.data?.data_source)],
        ["Live data", keptValue(saved, dataQuality.is_live_data, kept.data?.is_live_data)],
      ]),
    ]),
    section("Provider State", [
      keyValueTable([
        ["Active provider", keptValue(saved, providerState.active_provider, kept.venue)],
        ["Status", providerState.status],
        ...providerCrossRows(providerState, keptMarket),
        ["Reason", providerState.cross_provider_reason],
      ]),
      objectTable(providerState.providers),
    ]),
    section("Market Data v2 / Provider Observability", [
      keyValueTable([
        [
          "Symbol availability",
          storedMarketValue(keptMarket, dataQuality.symbol_availability, "symbol_availability"),
        ],
        [
          "Cross-provider state",
          storedMarketValue(keptMarket, dataQuality.cross_provider_state, "cross_provider_state"),
        ],
        [
          "Fallback to single provider",
          storedMarketValue(
            keptMarket,
            dataQuality.fallback_to_single_provider,
            "fallback_to_single_provider",
          ),
        ],
        [
          "Disagreement bps",
          storedMarketValue(keptMarket, dataQuality.disagreement_bps, "disagreement_bps"),
        ],
      ]),
      objectTable(details.market_data_v2_detail || dataQuality.derived_market_metrics),
    ]),
    section("Quant Signals", [
      objectTable(details.metrics_detail),
      objectTable(details.liquidity_execution_detail),
    ]),
    section("News Add-on", [
      keyValueTable([
        ["State", newsCopy],
        ["Mode", payload.analysis_mode],
        ["Warnings", storedNewsValue(keptNews, display.news_warnings, "warnings")],
      ]),
      objectTable(details.news_detail),
    ]),
    section("News Authority / Macro & Micro Context", [
      keyValueTable([
        [
          "Influence mode",
          storedNewsValue(keptNews, payload.news_addon_state?.influence_mode, "influence_mode"),
        ],
        ["Influence", "0.0 advisory display only"],
        ["Provider status", payload.news_addon_state?.provider_status],
      ]),
      objectTable(details.news_detail?.news_evidence || payload.news_evidence),
      objectTable(details.news_detail?.macro_context || payload.macro_context),
      objectTable(payload.micro_news_context),
    ]),
    section("Debug / Raw JSON", [rawJson]),
  );
  detailPanel.classList.remove("hidden");
  if (decisionSection) {
    // A live analysis is shown: its Storage row is among the decision view's rows. (A reopened
    // run's block has no such row: it is read back from history, so nothing is asked.)
    watchSaveReceipt(detailPanel, "detail", payload, decisionSection);
  }
}

async function restoreSession() {
  if (!(await loadSystemStatus())) {
    return false;
  }
  sessionGeneration += 1;
  loginPanel.classList.add("hidden");
  clearOperatorData();
  workspace.classList.remove("hidden");
  document.querySelector("#logoutButton").classList.remove("hidden");
  sessionStatus.textContent = "Ready";
  updateRefreshButton();
  return true;
}

document.querySelector("#loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const code = new FormData(event.currentTarget).get("code");
  loginStatus.textContent = "";
  try {
    await api("/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ code }),
    });
    sessionGeneration += 1;
    loginPanel.classList.add("hidden");
    clearOperatorData();
    workspace.classList.remove("hidden");
    document.querySelector("#logoutButton").classList.remove("hidden");
    sessionStatus.textContent = "Ready";
    updateRefreshButton();
    await loadSystemStatus();
  } catch (error) {
    loginStatus.textContent = loginFailureMessage(error?.status, error?.payload);
  }
});

function clearOperatorData() {
  cancelAllSaveReceipts();
  hideDetail();
  singleResult.replaceChildren();
  renderTimeframePlaceholders(singleResult);
  for (const selector of ["#batchResult", "#recentList", "#watchlistList", "#devResult"]) {
    document.querySelector(selector).replaceChildren();
  }
  document.querySelector("#recentStatus").textContent = "Recent analyses not loaded yet.";
  for (const selector of ["#recentSymbolFilter", "#recentTimeframeFilter", "#recentModeFilter"]) {
    document.querySelector(selector).value = "";
  }
  recentRuns = [];
  recentRunsSource = null;
  lastBatchRequest = null;
  currentWatchlistSymbol = null;
  calibrationDiagnosticsCache = null;
  calibrationDiagnosticsCachedAt = 0;
  calibrationDiagnosticsRequest = null;
}

function resetToLoggedOut() {
  loginPanel.classList.remove("hidden");
  workspace.classList.add("hidden");
  document.querySelector("#logoutButton").classList.add("hidden");
  sessionStatus.textContent = "Locked";
  loginStatus.textContent = "";
  document.querySelector("#accessCode").value = "";
  clearOperatorData();
  analysisActive = false;
  refreshReadyAt = 0;
  lastRefreshed.textContent = "last refreshed: never";
  updatePersistenceStatus("UNKNOWN");
  updateDevModeUx({ enabled: false, configured: false });
  showPanel("single");
  updateRefreshButton();
}

function handleSessionExpired(generation) {
  if (generation !== sessionGeneration) return;
  if (workspace.classList.contains("hidden")) return;
  resetToLoggedOut();
  loginStatus.textContent = "Your session expired. Please sign in again.";
}

document.querySelector("#logoutButton").addEventListener("click", async () => {
  try {
    await api("/v1/auth/logout", { method: "POST" });
    resetToLoggedOut();
  } catch (error) {
    if (error?.status === 401) {
      resetToLoggedOut();
      return;
    }
    sessionStatus.textContent = "Log out failed — you are still signed in.";
  }
});

for (const button of document.querySelectorAll(".tab")) {
  button.addEventListener("click", () => showPanel(button.dataset.tab));
}

document.querySelector("#singleForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  await runSingleAnalysis(new FormData(event.currentTarget));
});

function batchRequestFromForm(form) {
  const symbols = String(form.get("symbols"))
    .split(/\s+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 5);
  return {
    symbols,
    analysisMode: form.get("analysis_mode"),
    timeframe: form.get("timeframe"),
  };
}

async function runBatchAnalysis(batchRequest) {
  hideDetail();
  const target = document.querySelector("#batchResult");
  // The cards shown are about to be replaced, by results or by a failure.
  cancelSaveReceipts(target);
  if (!Array.isArray(batchRequest?.symbols) || batchRequest.symbols.length === 0) {
    renderBatchFailure(target, "Enter at least one symbol to run batch analysis.");
    return;
  }
  setLoading("#batchLoading", true);
  setAnalysisActive(true);
  try {
    lastBatchRequest = batchRequest;
    const requests = batchRequest.symbols.map((symbol) => ({
      symbol,
      analysis_mode: batchRequest.analysisMode,
      timeframe: batchRequest.timeframe,
    }));
    const payload = await sessionApi("/v1/analyze_batch", {
      method: "POST",
      body: JSON.stringify({ requests }),
    });
    renderResults(target, payload.results, payload.errors, payload.items);
    watchSaveReceipts(target, payload.results);
    // Each result carries storage's status from when its own analysis began, in the order they
    // ran. The last one is the latest report, and the badge is storage's status when last asked.
    const reported = Array.isArray(payload.results) ? payload.results : [];
    updateStatusFromPayload(reported[reported.length - 1] || {});
    markRefreshed();
  } catch (error) {
    renderBatchFailure(target, batchFailureMessage(error?.status, error?.payload));
  } finally {
    setAnalysisActive(false);
    setLoading("#batchLoading", false);
  }
}

document.querySelector("#batchForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  await runBatchAnalysis(batchRequestFromForm(new FormData(event.currentTarget)));
});

function readLocalWatchlist() {
  try {
    const parsed = JSON.parse(localStorage.getItem(watchlistStorageKey) || "[]");
    return Array.isArray(parsed) ? parsed.filter((item) => typeof item === "string") : [];
  } catch {
    return [];
  }
}

function writeLocalWatchlist(symbols) {
  localStorage.setItem(watchlistStorageKey, JSON.stringify([...new Set(symbols)].slice(0, 20)));
}

// The watchlist's own line. It never writes the header badge: an answer's storage status reaches
// the badge where the answer is read (updateStatusFromPayload), once. Written from here as well,
// the badge took a made-up UNAVAILABLE from a load or change that reported nothing, and an older
// answer's status over a newer one when the list was drawn again with its history.
// `status` is null when a load or change brought no storage status back (a load that failed, or
// an answer that names none); the line then reads as it always did for a list drawn from the
// browser: UNAVAILABLE. The line's tooltip is an earlier failed load's error: it goes when the
// line is written again (a failed load sets its own after this).
function setWatchlistStatus(status) {
  const target = document.querySelector("#watchlistStatus");
  target.title = "";
  const shown = status ?? "UNAVAILABLE";
  const browserFallback = status !== "OK";
  target.textContent = browserFallback
    ? `Watchlist persistence: ${shown}. Browser fallback is active.`
    : "Watchlist persistence: OK";
}

function watchlistFailureMessage(status) {
  if (status === 401) {
    return "Your session is not authorized. Sign in and try the watchlist change again.";
  }
  if (status === 422) {
    return "The watchlist change was not accepted. Check the entry and try again.";
  }
  if (status === 429) {
    return "Too many watchlist changes were requested. Wait a moment and try again.";
  }
  if (typeof status !== "number") {
    return "Unable to reach the service. Check your connection and try again.";
  }
  return "The watchlist change could not be saved. Try again shortly.";
}

// A watchlist change the backend refused or that never reached it (a rejected symbol, a rate
// limit, a network error). Such an answer carries no storage status, so the header badge is left
// as it was: storage was not asked. An accepted change carries one (renderWatchlist shows it).
function renderWatchlistMutationFailure(status) {
  const target = document.querySelector("#watchlistStatus");
  target.textContent = `Watchlist persistence: WRITE FAILED. ${watchlistFailureMessage(status)}`;
  target.title = "";
}

function latestRunsByNormalizedSymbol(runs) {
  const latestBySymbol = new Map();
  for (const run of runs) {
    if (
      typeof run.normalized_symbol === "string" &&
      !latestBySymbol.has(run.normalized_symbol)
    ) {
      latestBySymbol.set(run.normalized_symbol, run);
    }
  }
  return latestBySymbol;
}

function appendWatchlistAnalysis(row, run) {
  const context = document.createElement("div");
  context.className = "watchlist-analysis-context";
  if (!run) {
    context.textContent = "No recent analysis found.";
    row.append(context);
    return;
  }

  const lastAnalyzed = document.createElement("time");
  lastAnalyzed.dateTime = run.as_of_utc || "";
  lastAnalyzed.textContent = `Last analyzed: ${formatRecentTime(run.as_of_utc)}`;
  context.append(lastAnalyzed);

  const timeframe = String(run.primary_timeframe || "").trim();
  if (timeframe) {
    const timeframeLabel = document.createElement("span");
    timeframeLabel.textContent = `Primary timeframe: ${timeframe}`;
    context.append(timeframeLabel);
  }

  const source = recentSourceLabel(run);
  if (source) {
    const sourceIndicator = document.createElement("span");
    sourceIndicator.textContent = source;
    context.append(sourceIndicator);
  }

  if (run.detail_available === true) {
    const openLatest = document.createElement("button");
    openLatest.type = "button";
    openLatest.className = "watchlist-open-latest";
    openLatest.textContent = "Open latest analysis";
    openLatest.addEventListener("click", () => openDetail(run));
    context.append(openLatest);
  } else {
    const note = document.createElement("small");
    note.textContent = "Full breakdown not available after restart.";
    context.append(note);
  }
  row.append(context);
}

function renderWatchlist(symbols, status, runs = null) {
  const target = document.querySelector("#watchlistList");
  setWatchlistStatus(status);
  target.replaceChildren();
  if (!symbols.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "No symbols yet.";
    target.append(empty);
    return;
  }
  const latestBySymbol = Array.isArray(runs) ? latestRunsByNormalizedSymbol(runs) : null;
  for (const symbol of symbols) {
    const row = document.createElement("article");
    row.className = "watchlist-row";
    const symbolButton = document.createElement("button");
    symbolButton.type = "button";
    symbolButton.className = "watchlist-symbol";
    symbolButton.textContent = symbol;
    symbolButton.addEventListener("click", () => openWatchlistSymbol(symbol));
    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.className = "watchlist-remove";
    removeButton.textContent = "Remove";
    removeButton.addEventListener("click", () => removeWatchlistSymbol(symbol));
    row.append(symbolButton, removeButton);
    if (latestBySymbol) {
      appendWatchlistAnalysis(row, latestBySymbol.get(symbol));
    }
    target.append(row);
  }
}

async function loadWatchlist() {
  const historyRequest = sessionApi("/v1/runs")
    .then((payload) => (Array.isArray(payload.runs) ? payload.runs : []))
    .catch(() => null);
  try {
    const payload = await sessionApi("/v1/watchlist");
    let symbols = payload.symbols || [];
    if (payload.persistence_status !== "OK") {
      const localSymbols = readLocalWatchlist();
      symbols = localSymbols.length ? localSymbols : symbols;
      writeLocalWatchlist(symbols);
    }
    // An answer that names no storage status reports none (null).
    const status = namedStorageStatus(payload.persistence_status);
    renderWatchlist(symbols, status);
    const runs = await historyRequest;
    if (runs !== null) {
      renderWatchlist(symbols, status, runs);
    }
  } catch (error) {
    // The load failed (a network error, a refusal, a server error): no storage status came back.
    renderWatchlist(readLocalWatchlist(), null);
    document.querySelector("#watchlistStatus").title = error.message || "Watchlist unavailable";
  }
}

async function addWatchlistSymbol(symbol) {
  try {
    const payload = await sessionApi("/v1/watchlist", {
      method: "POST",
      body: JSON.stringify({ symbol }),
    });
    const envelope =
      payload && typeof payload === "object" && !Array.isArray(payload) ? payload : {};
    let symbols = Array.isArray(envelope.symbols)
      ? envelope.symbols.filter((item) => typeof item === "string")
      : [];
    // An answer that names no storage status reports none (null).
    const persistenceStatus = namedStorageStatus(envelope.persistence_status);
    if (persistenceStatus !== "OK") {
      symbols = [...new Set([...readLocalWatchlist(), ...symbols])].slice(0, 20);
      writeLocalWatchlist(symbols);
    }
    renderWatchlist(symbols, persistenceStatus);
  } catch (error) {
    const failure = error && typeof error === "object" && !Array.isArray(error) ? error : null;
    renderWatchlistMutationFailure(failure?.status);
  }
}

async function removeWatchlistSymbol(symbol) {
  try {
    const payload = await sessionApi(`/v1/watchlist/${encodeURIComponent(symbol)}`, {
      method: "DELETE",
    });
    const envelope =
      payload && typeof payload === "object" && !Array.isArray(payload) ? payload : {};
    let symbols = Array.isArray(envelope.symbols)
      ? envelope.symbols.filter((item) => typeof item === "string")
      : [];
    // An answer that names no storage status reports none (null).
    const persistenceStatus = namedStorageStatus(envelope.persistence_status);
    if (persistenceStatus !== "OK") {
      symbols = readLocalWatchlist().filter((item) => item !== symbol);
      writeLocalWatchlist(symbols);
    }
    renderWatchlist(symbols, persistenceStatus);
  } catch (error) {
    const failure = error && typeof error === "object" && !Array.isArray(error) ? error : null;
    renderWatchlistMutationFailure(failure?.status);
  }
}

async function openWatchlistSymbol(symbol) {
  currentWatchlistSymbol = symbol;
  hideDetail();
  document.querySelector("#watchlistList").classList.add("hidden");
  document.querySelector("#watchlistView").classList.remove("hidden");
  document.querySelector("#watchlistSymbolTitle").textContent = `${symbol} Watchlist Symbol View`;
  await runTimeframeSet({
    symbol,
    analysisMode: document.querySelector("#watchlistMode").value,
    target: document.querySelector("#watchlistResult"),
    loadingSelector: "#watchlistLoading",
    payloadStore: watchlistPayloads,
  });
}

document.querySelector("#watchlistForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const symbol = String(new FormData(event.currentTarget).get("symbol") || "").trim();
  if (!symbol) {
    return;
  }
  await addWatchlistSymbol(symbol);
});

document.querySelector("#backToWatchlist").addEventListener("click", () => {
  hideDetail();
  document.querySelector("#watchlistView").classList.add("hidden");
  document.querySelector("#watchlistList").classList.remove("hidden");
});

async function refreshCurrentView() {
  if (analysisActive || Date.now() < refreshReadyAt) {
    updateRefreshButton();
    return;
  }
  const tab = activeTabName();
  if (tab === "single") {
    await runSingleAnalysis(new FormData(document.querySelector("#singleForm")));
    return;
  }
  if (tab === "watchlist") {
    if (!document.querySelector("#watchlistView").classList.contains("hidden") && currentWatchlistSymbol) {
      await openWatchlistSymbol(currentWatchlistSymbol);
    } else {
      await loadWatchlist();
      markRefreshed();
    }
    return;
  }
  if (tab === "batch") {
    const request = lastBatchRequest || batchRequestFromForm(new FormData(document.querySelector("#batchForm")));
    await runBatchAnalysis(request);
    return;
  }
  if (tab === "recent") {
    const reloaded = await loadRecentRuns();
    if (reloaded) {
      markRefreshed("history reloaded");
    } else {
      startRefreshCooldown();
    }
    return;
  }
  if (tab === "dev") {
    const refreshed = await loadSystemStatus();
    if (refreshed) {
      markRefreshed("status refreshed");
    } else {
      startRefreshCooldown();
    }
    return;
  }
  const refreshed = await loadSystemStatus();
  if (refreshed) {
    markRefreshed();
  } else {
    startRefreshCooldown();
  }
}

refreshButton.addEventListener("click", async () => {
  try {
    await refreshCurrentView();
  } catch (error) {
    sessionStatus.textContent = error.message || "Refresh failed";
  }
});

async function handleDevFormSubmit(event) {
  event.preventDefault();
  const code = new FormData(event.currentTarget).get("code");
  try {
    await api("/v1/auth/dev", {
      method: "POST",
      body: JSON.stringify({ code }),
    });
    document.querySelector("#devResult").textContent = "Dev Mode ready.";
  } catch (error) {
    document.querySelector("#devResult").textContent = loginFailureMessage(
      error?.status,
      error?.payload,
    );
  }
}

function devToolFailureMessage(action, status, payload) {
  const failure = loginFailureMessage(status, payload);
  if (status === 401) {
    return `${action} failed: Dev Mode re-auth is needed; your normal session remains active. ${failure}`;
  }
  return `${action} failed: ${failure}`;
}

async function exportDebugRun(run, target) {
  try {
    // A run's export carries the run's own storage status, from when the run was made.
    const exported = await api(`/v1/debug/export/${run.run_id}`, {}, { storedRecord: true });
    target.textContent = JSON.stringify(exported, null, 2);
  } catch (error) {
    target.textContent = devToolFailureMessage(
      `Exporting run ${run.run_id}`,
      error?.status,
      error?.payload,
    );
  }
}

async function loadDebugRuns() {
  const target = document.querySelector("#devResult");
  try {
    const runs = await api("/v1/debug/runs");
    target.textContent = JSON.stringify(runs, null, 2);
    for (const run of runs.runs) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `Export ${run.run_id}`;
      button.addEventListener("click", async () => {
        await exportDebugRun(run, target);
      });
      target.append(document.createElement("br"), button);
    }
  } catch (error) {
    target.textContent = devToolFailureMessage(
      "Loading the run list",
      error?.status,
      error?.payload,
    );
  }
}

document.querySelector("#devForm").addEventListener("submit", handleDevFormSubmit);
document.querySelector("#loadRuns").addEventListener("click", loadDebugRuns);

renderTimeframePlaceholders(singleResult);
void loadBuildFingerprint();
updatePersistenceStatus("UNKNOWN");
updateDevModeUx({ enabled: false, configured: false });
updateRefreshButton();
void restoreSession();
