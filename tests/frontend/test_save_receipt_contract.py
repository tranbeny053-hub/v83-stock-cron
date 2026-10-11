"""The two halves of the save receipt agree: the states the backend can return are exactly the
states the screen has a sentence for, under the same schema version and the same route."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from crypto_probability_engine.api import save_receipt

ROOT = Path(__file__).resolve().parents[2]
APP_JS = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
APP_PY = (ROOT / "src" / "crypto_probability_engine" / "api" / "app.py").read_text(encoding="utf-8")


def test_the_screen_has_a_sentence_for_exactly_the_backends_states() -> None:
    block = APP_JS[APP_JS.index("const SAVE_RECEIPT_TEXT = {") :]
    block = block[: block.index("};")]
    shown = set(re.findall(r"^  ([A-Z_]+):", block, flags=re.MULTILINE))
    backend = {
        save_receipt.SAVED,
        save_receipt.PENDING,
        save_receipt.FAILED,
        save_receipt.NOT_RETAINED,
    }
    assert shown == backend


def test_both_halves_use_the_same_schema_version_and_route() -> None:
    assert f'const SAVE_RECEIPT_SCHEMA_VERSION = "{save_receipt.SCHEMA_VERSION}";' in APP_JS
    assert '@app.get("/v1/analyze/receipt/{run_id}")' in APP_PY
    assert "`/v1/analyze/receipt/${encodeURIComponent(payload.run_id)}`" in APP_JS


def test_the_backends_receipt_has_the_fields_the_screen_reads() -> None:
    receipt = save_receipt.receipt_payload(
        "run_x", save_receipt.SAVED, datetime(2026, 10, 10, tzinfo=UTC)
    )
    assert receipt == {
        "schema_version": "save_receipt.v1",
        "run_id": "run_x",
        "state": "SAVED",
        "checked_at_utc": "2026-10-10T00:00:00Z",
    }
    for field in ("schema_version", "run_id", "state"):
        assert f"receipt.{field}" in APP_JS or f"receipt?.{field}" in APP_JS, field
