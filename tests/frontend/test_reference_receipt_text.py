"""The save receipt's text for a served Lean reference comes from the backend's history_line."""

from __future__ import annotations

import json
import shutil
import subprocess

from tests.frontend.test_decision_view_rendering import ROOT, _extract_constant, _extract_function

NODE = shutil.which("node")
SAVED_REFERENCE_LINE = "Saved as an analysis run. Held in session memory (test line)."


def _object_constant(source: str, name: str) -> str:
    start = source.index(f"const {name} = {{")
    return source[start : source.index("\n};", start) + 3]


def _receipt_texts() -> dict:
    assert NODE is not None, "node is required to run the real app.js"
    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    script = "\n".join(
        [
            _extract_constant(source, "SAVE_RECEIPT_SCHEMA_VERSION"),
            _object_constant(source, "SAVE_RECEIPT_TEXT"),
            _extract_function(source, "saveReceiptText"),
            f"const line = {json.dumps(SAVED_REFERENCE_LINE)};",
            """
const receipt = (state) => ({schema_version: SAVE_RECEIPT_SCHEMA_VERSION, run_id: "r1", state});
const served = {reference_state: {status: "SERVED", display: {history_line: line}}};
const fallback = {reference_state: {status: "UNAVAILABLE", display: {history_line: line}}};
console.log(JSON.stringify({
  servedSaved: saveReceiptText(receipt("SAVED"), "r1", served),
  servedFailed: saveReceiptText(receipt("FAILED"), "r1", served),
  heuristicSaved: saveReceiptText(receipt("SAVED"), "r1", {}),
  fallbackSaved: saveReceiptText(receipt("SAVED"), "r1", fallback),
  generic: SAVE_RECEIPT_TEXT,
}));
""",
        ]
    )
    done = subprocess.run(  # noqa: S603 - node on a script built here
        [NODE, "-e", script], capture_output=True, text=True, check=True, timeout=30
    )
    return json.loads(done.stdout)


def test_a_saved_served_reference_shows_the_backend_history_line() -> None:
    texts = _receipt_texts()
    assert texts["servedSaved"] == SAVED_REFERENCE_LINE


def test_other_states_and_runs_keep_the_generic_receipt_text() -> None:
    texts = _receipt_texts()
    assert texts["servedFailed"] == texts["generic"]["FAILED"]
    assert texts["heuristicSaved"] == texts["generic"]["SAVED"]
    assert texts["fallbackSaved"] == texts["generic"]["SAVED"]
