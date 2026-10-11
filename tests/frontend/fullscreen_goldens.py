"""The whole-screen regression pins of the screens (owner ruling: whole-screen tests).

The other frontend tests assert phrases and membership: a line that moves, and a line that is added,
both pass them. These goldens pin the rest. For every scenario and surface below, the complete
ordered list of the texts a user can read is committed, as the real frontend/app.js renders the
analyses the real backend builds.

They are regression detectors, not acceptance. A golden records a screen as it is, right or wrong:
it says that a screen changed, never that a screen is good. When a screen is meant to change,
regenerate, and read the diff.

    PYTHONPATH=src:. .venv/bin/python -m tests.frontend.fullscreen_goldens --write   # regenerate
    PYTHONPATH=src:. .venv/bin/python -m tests.frontend.fullscreen_goldens --check   # 1 if stale

One file per scenario and surface, goldens/fullscreen/<scenario>.<surface>.txt: one visible text per
line, in screen order. A text of several lines (a "View" block prints JSON) continues on lines that
start with CONTINUATION.

Surfaces:
- single: the timeframe card of a single analysis (horizonCard);
- batch: the card of a batch analysis (overviewCard);
- detail: the detail panel of a live analysis (renderStructuredDetail), once its requests settled;
- history: the detail panel of a saved run read back, from the row the recent list holds and the
  stored detail as the detail route returns it (sanitize_for_export of the detail view, which is
  what is saved, with the gate framing the route builds when it reads it: attach_gate_view).

Scenarios (SCENARIOS): every one is an analysis of the real service on the fixture candles. The
ones named SYNTHETIC cannot occur today: nothing is accepted in the governed registries, and the
evidence gate is active on every analysis (it is lifted for those builds only).

The screens are pinned as first rendered. The DOM stand-in has no backend, so the two requests the
detail panel makes get no answer: the Storage row stays what storage said at request time (no save
receipt is answered or made up; test_save_receipt_rendering.py covers the receipt), and the live
calibration diagnostics read as unavailable. The Raw JSON block is not in a golden: it prints the
payload itself, and test_fullscreen_goldens.py proves it is that payload verbatim.

Frozen, so that a build is the same on every machine and day:
- the candles, the clock (tests/fixtures/market_data.FIXED_NOW), the venue and the candle age are
  the harness's fixtures (test_accepted_state_rendering._select); no network, no database;
- storage at request time is the analysis function's default (STATELESS) or the scenario's own;
- app.js runs with its clock at FIXED_NOW and its time zone UTC, and a screen that prints text
  formatted for the machine's locale is refused (none does).

Exactly two things are normalized, and no wording (test_fullscreen_goldens.py proves it):
- a run id (`run_` and 32 hex digits, a new uuid4 for every analysis) reads `run_<RUN_ID>`;
- a decimal number written with more than 12 significant digits is rounded to 12 and marked "…".
  A float's last digits are not the same everywhere. Three such numbers on a screen (realized
  volatility, and the risk pressure and arbiter value made from it) come from math.log, which the
  platform's maths library computes; the percentages come from them through math.tanh. The test
  moves those results by a unit or two in the last place and the goldens stay what they are.
No screen prints a hash or the time of the build.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Context
from pathlib import Path
from typing import Any

import pytest

from crypto_probability_engine.api import analysis_service
from crypto_probability_engine.api.schemas import AnalysisRequest
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.detail.gate_kinds import attach_gate_view
from crypto_probability_engine.persistence.prediction_origin import PredictionOrigin
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from crypto_probability_engine.quant import pipeline
from crypto_probability_engine.utils.sanitize import sanitize_for_export
from tests.fixtures.market_data import FIXED_NOW, make_order_book

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:  # the harness is imported by module name, as under pytest
    sys.path.insert(0, str(HERE))

import test_accepted_state_rendering as harness  # noqa: E402

GOLDENS = HERE / "goldens" / "fullscreen"
REGENERATE = "PYTHONPATH=src:. .venv/bin/python -m tests.frontend.fullscreen_goldens --write"
CONTINUATION = "  | "
RUN_ID = re.compile(r"run_[0-9a-f]{32}")
RUN_ID_PLACEHOLDER = "run_<RUN_ID>"
SIGNIFICANT_DIGITS = 12
ROUNDED_MARK = "…"
_DECIMAL_NUMBER = re.compile(r"(?<![\w.])(\d+\.\d+)([eE][+-]?\d+)?")
_ROUNDING = Context(prec=SIGNIFICANT_DIGITS, rounding=ROUND_HALF_EVEN)

# The surfaces of a live analysis; a saved run read back has one more, "history".
SURFACES = ("single", "batch", "detail")
STORAGE_STATUSES = ("OK", "UNAVAILABLE", "STATELESS")
# What stands in a text that app.js formatted for the machine's locale: never in a golden.
LOCALE_MARK = "<TEXT FORMATTED FOR THE MACHINE'S LOCALE>"


# What a run saved before the gate framing existed stores as its brief's summary: the forced token
# alone. Its gate result is stored too, and the framing is built from that when it is read.
OLD_STORED_SUMMARY = (
    "BTC/USDT is classified as NO_TRADE for 1H setup / ~6H horizon using an uncalibrated "
    "heuristic. Gate action is NO_TRADE and backend disposition is ELEVATED_RISK_AVOID."
)
# The order book of an analysis: the fixture's own, none at all (the venue gave no book, so
# liquidity could not be measured), or a book whose spread is measured and too wide.
ORDER_BOOKS = ("fixture", "missing", "wide")


def _select_with(book: str) -> Callable[..., Any]:
    """The harness's market-data selection, with the order book the scenario names."""

    def select(symbol: Any, timeframe: str, *, settings: Any) -> Any:
        chosen = harness._select(symbol, timeframe, settings=settings)
        if book == "missing":
            return replace(chosen, snapshot=replace(chosen.snapshot, order_book=None))
        if book == "wide":
            wide = make_order_book(bid=100.0, ask=110.0)
            return replace(chosen, snapshot=replace(chosen.snapshot, order_book=wide))
        return chosen

    return select


def _analysis(
    *,
    tail: bool = False,
    kill: bool = False,
    lifted: bool = False,
    book: str = "fixture",
    storage: str | None = None,
) -> dict:
    """One real analysis of BTC/USDT 1H under the evidence gate, as it is served today. `tail` adds
    a tail-risk breach (the fixture candles have none, so the measured loss is set to twice its
    threshold), `kill` the kill switch, `book` the order book (ORDER_BOOKS), `storage` what storage
    said when the analysis was asked. `lifted` lifts the evidence gate for this build only: a
    SYNTHETIC state, the product's hold is untouched."""

    assert book in ORDER_BOOKS, book
    real_tail = pipeline.compute_tail_cvar

    def breached(candles: Any, *, timeframe: str) -> dict:
        state = real_tail(candles, timeframe=timeframe)
        return {**state, "cvar_loss": float(state["cvar_breach_threshold"]) * 2}

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(analysis_service, "select_market_data", _select_with(book))
        evidence = harness.SKILL if lifted else harness.NO_SKILL
        patch.setattr(analysis_service, "get_cached_skill_evidence", lambda _tf: dict(evidence))
        if lifted:
            patch.setattr(analysis_service, "evidence_for_gate", lambda found: (found, None))
        if tail:
            patch.setattr(pipeline, "compute_tail_cvar", breached)
        if kill:
            flags = {**pipeline.global_risk_state(), "kill_switch": True}
            patch.setattr(pipeline, "global_risk_state", lambda: dict(flags))
        extra = {} if storage is None else {"persistence_status": storage}
        return analysis_service.analyze_request(
            AnalysisRequest(symbol="BTC/USDT", timeframe="1H"),
            settings=Settings(data_mode="fixture"),
            run_store=InMemoryRunStore(limit=10),
            **extra,
        )


def _first_check_blocks() -> dict:
    """SYNTHETIC: the evidence-only analysis with another check of its stack blocking first, with a
    sentence of its own. No analysis of the service reads so today."""

    payload = _analysis()
    payload["decision_synthesis"]["actionability_stack"][0].update(
        status="BLOCK", plain_english="A sentence of the first check."
    )
    return payload


# Every scenario, in the order the files are listed; each is one analysis of the real service.
SCENARIOS: dict[str, Callable[[], dict]] = {
    # Today's normal analysis: the evidence gate is the only hard block.
    "evidence_only": lambda: _analysis(),
    # A real risk gate beside it: a measured tail-risk breach; a measured spread that is too wide.
    "risk_and_evidence": lambda: _analysis(tail=True),
    "wide_spread_and_evidence": lambda: _analysis(book="wide"),
    # A gate fired by missing data: the venue gave no order book (owner ruling G2).
    "missing_order_book_and_evidence": lambda: _analysis(book="missing"),
    # A system gate beside it.
    "kill_switch_and_evidence": lambda: _analysis(kill=True),
    # The same analysis, for each thing storage can say when it is asked.
    **{
        f"storage_{status}": (lambda status=status: _analysis(storage=status))
        for status in STORAGE_STATUSES
    },
    # SYNTHETIC: each kind of gate alone (the evidence gate lifted for the build).
    "risk_only_SYNTHETIC": lambda: _analysis(tail=True, lifted=True),
    "missing_order_book_only_SYNTHETIC": lambda: _analysis(book="missing", lifted=True),
    "system_only_SYNTHETIC": lambda: _analysis(kill=True, lifted=True),
    "first_check_blocks_SYNTHETIC": _first_check_blocks,
    # SYNTHETIC, as test_accepted_state_rendering.py builds them: an accepted forecast claim, and
    # a directional permission (1W; its evidence gate is lifted, so no gate blocks).
    "accepted_claim_SYNTHETIC": lambda: harness._analysis("1H", claim=True),
    "permission_SYNTHETIC": lambda: harness._analysis("1W", permission=True),
}
# The scenarios also pinned as a saved run read back. storage_OK is the one that is saved today.
HISTORY = (
    "evidence_only",
    "risk_and_evidence",
    "wide_spread_and_evidence",
    "missing_order_book_and_evidence",
    "kill_switch_and_evidence",
    "storage_OK",
    "risk_only_SYNTHETIC",
    "missing_order_book_only_SYNTHETIC",
    "system_only_SYNTHETIC",
)
# Pinned as a saved run only: the evidence-only analysis as a run saved before the gate framing
# existed stores it (OLD_STORED_SUMMARY).
SAVED_BEFORE = "saved_before_this_change"


def build_cases() -> dict[str, dict]:
    return {name: analysis() for name, analysis in SCENARIOS.items()}


def _reopened(payload: dict, *, saved_before: bool = False) -> dict:
    """A saved run as it is read back: the row the recent list holds for it (the run store's own
    listing, and `detail_available` as GET /v1/runs adds it) and the stored detail as the detail
    route returns it (what analysis_service saves, sanitize_for_export of the detail view, with
    the gate framing the route builds when it reads it). No decision view: a stored run has none.
    `saved_before` is a run stored before the gate framing existed."""

    origin = PredictionOrigin.USER_REQUESTED.value
    store = InMemoryRunStore(limit=1)
    store.put(payload["run_id"], payload, prediction_origin=origin)
    (row,) = store.list_runs()
    stored = sanitize_for_export(copy.deepcopy(payload["detail_view"]))
    if saved_before:
        stored["decision_brief"]["state_summary"] = OLD_STORED_SUMMARY
    return {"row": {**row, "detail_available": True}, "detail": attach_gate_view(stored)}


def build_reopened(cases: dict[str, dict]) -> dict[str, dict]:
    reopened = {name: _reopened(cases[name]) for name in HISTORY}
    reopened[SAVED_BEFORE] = _reopened(cases["evidence_only"], saved_before=True)
    return reopened


def expected_names() -> list[str]:
    """Every golden there must be, from the tables above alone (nothing is rendered)."""

    return sorted(
        [f"{scenario}.{surface}.txt" for scenario in SCENARIOS for surface in SURFACES]
        + [f"{scenario}.history.txt" for scenario in (*HISTORY, SAVED_BEFORE)]
    )


# Before app.js loads: its clock is frozen, and whatever it formats for the machine's locale
# becomes LOCALE_MARK, which render() refuses on a screen.
_FROZEN = """
(() => {
  const RealDate = Date;
  const now = __NOW__;
  globalThis.Date = class extends RealDate {
    constructor(...args) { super(...(args.length ? args : [now])); }
    static now() { return now; }
  };
  const mark = () => __MARK__;
  for (const name of ["toLocaleString", "toLocaleDateString", "toLocaleTimeString"]) {
    RealDate.prototype[name] = mark;
  }
  Number.prototype.toLocaleString = mark;
  // A node built without Intl has no formatter to mark.
  const formatters = typeof Intl === "object" ? [Intl.DateTimeFormat, Intl.NumberFormat] : [];
  for (const formatter of formatters) {
    Object.defineProperty(formatter.prototype, "format", { get: () => mark });
  }
})();
"""

# Every screen of every case, and beside each detail panel its Raw JSON block (not in a golden).
_RENDER = """
(async () => {
  const skipped = ["raw-json"];
  const panel = async (payload, detail) => {
    // As on a first visit: no diagnostics answer is remembered from the panel before.
    calibrationDiagnosticsCache = null;
    calibrationDiagnosticsCachedAt = 0;
    renderStructuredDetail(payload, detail);
    // Let the panel's requests settle: nothing answers them (the stand-in has no backend).
    for (let tick = 0; tick < 5; tick += 1) await new Promise((done) => setTimeout(done, 0));
    return {
      texts: visibleTexts(detailPanel, skipped),
      raw: detailPanel.querySelectorAll(".raw-json").map((block) => visibleTexts(block, [])),
    };
  };
  const screens = {};
  const rawJson = {};
  for (const [name, payload] of Object.entries(cases)) {
    const detail = await panel(payload, payload.detail_view);
    screens[name] = {
      single: visibleTexts(fakeElement("div", "", [horizonCard(payload)])),
      batch: visibleTexts(fakeElement("div", "", [overviewCard(payload)])),
      detail: detail.texts,
    };
    rawJson[name] = { detail: detail.raw };
  }
  for (const [name, item] of Object.entries(reopened)) {
    const history = await panel(item.row, item.detail);
    screens[name] = { ...(screens[name] || {}), history: history.texts };
    rawJson[name] = { ...(rawJson[name] || {}), history: history.raw };
  }
  // A pipe is written asynchronously: exit only once the whole result is flushed.
  process.stdout.write(JSON.stringify({ screens, raw_json: rawJson }), () => process.exit(0));
})();
"""


def frozen_clock(clock: datetime) -> str:
    """The script that runs before app.js loads: what app.js is told the time is."""

    script = _FROZEN.replace("__NOW__", str(int(clock.timestamp() * 1000)))
    return script.replace("__MARK__", json.dumps(LOCALE_MARK))


def _js(value: Any) -> str:
    """A payload as the API would send it: strict JSON, and no value that is not JSON's."""

    return json.dumps(value, allow_nan=False)


def render(
    cases: dict[str, dict],
    reopened: dict[str, dict],
    *,
    clock: datetime = FIXED_NOW,
    zone: str = "UTC",
) -> dict[str, dict]:
    """Every screen as the real app.js renders it: `screens` is scenario -> surface -> the visible
    texts in order, nothing normalized yet; `raw_json` is the Raw JSON block of each detail panel.
    `clock` and `zone` are what app.js is told the time and the time zone are."""

    if harness.NODE is None:
        raise RuntimeError("node is required to run the real app.js")
    script = "\n".join(
        [
            frozen_clock(clock),
            harness._DOM_STAND_IN,
            (harness.ROOT / "frontend" / "app.js").read_text(encoding="utf-8"),
            f"const cases = {_js(cases)};",
            f"const reopened = {_js(reopened)};",
            _RENDER,
        ]
    )
    # The script holds the whole of app.js and every case: node reads it on stdin (conftest.py).
    done = subprocess.run(  # noqa: S603 - node on a script built here
        [harness.NODE, "-"],
        input=script,
        capture_output=True,
        encoding="utf-8",
        env={**os.environ, "TZ": zone},
        check=False,
        timeout=120,
    )
    if done.returncode != 0:
        raise RuntimeError(f"app.js did not render the screens:\n{done.stderr[-2000:]}")
    rendered = json.loads(done.stdout)
    for scenario, surfaces in rendered["screens"].items():
        for surface, texts in surfaces.items():
            if any(LOCALE_MARK in text for text in texts):
                raise RuntimeError(
                    f"{scenario}.{surface} prints text formatted for the machine's locale or "
                    "time zone: it cannot be pinned as it is (freeze it here first)"
                )
    return rendered


def render_screens(**app_js: Any) -> dict[str, dict[str, list[str]]]:
    """One build: new analyses, rendered. scenario -> surface -> the visible texts in order."""

    cases = build_cases()
    return render(cases, build_reopened(cases), **app_js)["screens"]


def _rounded(match: re.Match[str]) -> str:
    mantissa, exponent = match.group(1), match.group(2) or ""
    if len(mantissa.replace(".", "").lstrip("0")) <= SIGNIFICANT_DIGITS:
        return match.group(0)
    return f"{_ROUNDING.create_decimal(mantissa):f}{ROUNDED_MARK}{exponent}"


def normalize(text: str) -> str:
    """One visible text with its volatile values made stable: run ids and long decimals only."""

    return _DECIMAL_NUMBER.sub(_rounded, RUN_ID.sub(RUN_ID_PLACEHOLDER, text))


def encode(texts: list[str]) -> str:
    """A screen as a golden file: one text per line, a text's further lines marked."""

    lines: list[str] = []
    for text in texts:
        first, *rest = text.split("\n")
        lines.append(first)
        lines.extend(CONTINUATION + line for line in rest)
    content = "".join(line + "\n" for line in lines)
    if decode(content) != texts:
        raise ValueError(
            "a visible text cannot be written unambiguously (it starts with the continuation "
            f"mark {CONTINUATION!r}): choose another mark"
        )
    return content


def decode(content: str) -> list[str]:
    """The screen a golden file holds: the inverse of encode."""

    texts: list[str] = []
    for line in content.split("\n")[:-1]:
        if line.startswith(CONTINUATION) and texts:
            texts[-1] += "\n" + line[len(CONTINUATION) :]
        else:
            texts.append(line)
    return texts


def golden_files(screens: dict[str, dict[str, list[str]]]) -> dict[str, str]:
    """File name -> content, for every scenario and surface rendered."""

    return {
        f"{scenario}.{surface}.txt": encode([normalize(text) for text in texts])
        for scenario, surfaces in screens.items()
        for surface, texts in surfaces.items()
    }


def build() -> dict[str, str]:
    return golden_files(render_screens())


def committed(directory: Path = GOLDENS) -> dict[str, str]:
    """Every file of the goldens directory, whatever its name: a stray file is a finding."""

    if not directory.is_dir():
        return {}
    return {
        path.name: path.read_bytes().decode("utf-8")
        for path in sorted(directory.iterdir())
        if path.is_file()
    }


def differences(files: dict[str, str], directory: Path = GOLDENS) -> list[str]:
    """What separates the directory from what the builder produces; empty when it is current."""

    found = committed(directory)
    return [
        *(f"missing: {name}" for name in sorted(files.keys() - found.keys())),
        *(f"stray: {name}" for name in sorted(found.keys() - files.keys())),
        *(
            f"stale: {name}"
            for name in sorted(files.keys() & found.keys())
            if files[name] != found[name]
        ),
    ]


def write(files: dict[str, str], directory: Path = GOLDENS) -> None:
    """The directory made exactly what the builder produces: stray files are removed."""

    directory.mkdir(parents=True, exist_ok=True)
    for name in committed(directory).keys() - files.keys():
        (directory / name).unlink()
    for name, content in files.items():
        (directory / name).write_bytes(content.encode("utf-8"))


def main(argv: list[str] | None = None, *, directory: Path = GOLDENS) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="regenerate the goldens")
    mode.add_argument("--check", action="store_true", help="exit 1 if the goldens differ")
    args = parser.parse_args(argv)
    files = build()
    root = HERE.parents[1]
    where = directory.relative_to(root) if directory.is_relative_to(root) else directory
    if args.write:
        write(files, directory)
        print(f"wrote {len(files)} files to {where}")
        return 0
    found = differences(files, directory)
    if found:
        print("\n".join([*found, f"{where} differs: run {REGENERATE}"]), file=sys.stderr)
        return 1
    print(f"{where} is current ({len(files)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
