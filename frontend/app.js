const sessionStatus = document.querySelector("#sessionStatus");
const loginPanel = document.querySelector("#loginPanel");
const workspace = document.querySelector("#workspace");
const overviewTemplate = document.querySelector("#overviewTemplate");
const heatLegend = "Signal heat — not risk";

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload?.detail?.error?.message || "Request failed");
  }
  return payload;
}

function showPanel(name) {
  for (const button of document.querySelectorAll(".tab")) {
    button.classList.toggle("active", button.dataset.tab === name);
  }
  for (const panel of ["single", "batch", "dev"]) {
    document.querySelector(`#${panel}Panel`).classList.toggle("hidden", panel !== name);
  }
}

function setLoading(id, active) {
  document.querySelector(id).classList.toggle("hidden", !active);
}

function overviewCard(payload) {
  const node = overviewTemplate.content.firstElementChild.cloneNode(true);
  const display = payload.frontend_display;
  node.querySelector("h2").textContent = payload.normalized_symbol;
  const demoBanner = document.createElement("p");
  demoBanner.className = "demo-banner";
  demoBanner.textContent = display.is_live_data
    ? `LIVE DATA — ${display.data_source}`
    : `DEMO DATA — ${display.data_source}`;
  node.insertBefore(demoBanner, node.querySelector("dl"));
  const values = [
    ["Disposition", display.disposition],
    ["Score", display.total_score],
    ["Up", `${display.prob_up_pct.toFixed(2)}%`],
    ["Down", `${display.prob_down_pct.toFixed(2)}%`],
    ["Timeout", `${display.prob_timeout_pct.toFixed(2)}%`],
    ["Mode", display.analysis_mode_badge],
    ["Data", display.is_live_data ? "LIVE" : "DEMO"],
    ["Heat", display.heat_legend || heatLegend],
  ];
  const dl = node.querySelector("dl");
  for (const [label, value] of values) {
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = label;
    dd.textContent = value;
    dl.append(dt, dd);
  }
  const note = node.querySelector(".news-note");
  note.textContent =
    payload.analysis_mode === "METRICS_ONLY"
      ? "News disabled in METRICS_ONLY."
      : payload.news_addon_state.status;
  node.querySelector(".detail-button").addEventListener("click", async () => {
    const detail = await api(`/v1/analyze/detail/${payload.run_id}`);
    note.textContent = JSON.stringify(detail, null, 2);
  });
  return node;
}

function renderResults(target, payloads, errors = []) {
  target.replaceChildren();
  for (const payload of payloads) {
    target.append(overviewCard(payload));
  }
  for (const item of errors) {
    const node = document.createElement("article");
    node.className = "result-card";
    node.textContent = `Item ${item.index + 1}: ${item.detail.error.code}`;
    target.append(node);
  }
}

document.querySelector("#loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const code = new FormData(event.currentTarget).get("code");
  await api("/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
  loginPanel.classList.add("hidden");
  workspace.classList.remove("hidden");
  sessionStatus.textContent = "Ready";
});

for (const button of document.querySelectorAll(".tab")) {
  button.addEventListener("click", () => showPanel(button.dataset.tab));
}

document.querySelector("#singleForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  setLoading("#singleLoading", true);
  try {
    const form = new FormData(event.currentTarget);
    const payload = await api("/v1/analyze", {
      method: "POST",
      body: JSON.stringify(Object.fromEntries(form.entries())),
    });
    renderResults(document.querySelector("#singleResult"), [payload]);
  } finally {
    setLoading("#singleLoading", false);
  }
});

document.querySelector("#batchForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  setLoading("#batchLoading", true);
  try {
    const form = new FormData(event.currentTarget);
    const symbols = String(form.get("symbols"))
      .split(/\s+/)
      .map((item) => item.trim())
      .filter(Boolean)
      .slice(0, 5);
    const requests = symbols.map((symbol) => ({
      symbol,
      analysis_mode: form.get("analysis_mode"),
      timeframe: form.get("timeframe"),
    }));
    const payload = await api("/v1/analyze_batch", {
      method: "POST",
      body: JSON.stringify({ requests }),
    });
    renderResults(document.querySelector("#batchResult"), payload.results, payload.errors);
  } finally {
    setLoading("#batchLoading", false);
  }
});

document.querySelector("#devForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const code = new FormData(event.currentTarget).get("code");
  await api("/v1/auth/dev", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
  document.querySelector("#devResult").textContent = "Dev Mode ready.";
});

document.querySelector("#loadRuns").addEventListener("click", async () => {
  const runs = await api("/v1/debug/runs");
  const target = document.querySelector("#devResult");
  target.textContent = JSON.stringify(runs, null, 2);
  for (const run of runs.runs) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `Export ${run.run_id}`;
    button.addEventListener("click", async () => {
      const exported = await api(`/v1/debug/export/${run.run_id}`);
      target.textContent = JSON.stringify(exported, null, 2);
    });
    target.append(document.createElement("br"), button);
  }
});
