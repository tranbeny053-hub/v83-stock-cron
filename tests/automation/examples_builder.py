"""Deterministic, synthetic ``radar_evidence.v1`` examples for the UOR handoff.

Provenance: SYNTHETIC_FIXTURE. The real analysis pipeline runs on the repository's deterministic
fixture candles (``tests/fixtures/market_data.make_snapshot``, all at ``FIXED_NOW``): no live data,
no holdout and no section 5A evidence. The release identity is synthetic too, and no UCPE release
serves it, so a consumer must never allowlist it. Every run is reproducible byte for byte.

    PYTHONPATH=src:. python -m tests.automation.examples_builder --write   # regenerate
    PYTHONPATH=src:. python -m tests.automation.examples_builder           # check only
"""

from __future__ import annotations

import argparse
import hashlib
import json
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from uuid import UUID

from crypto_probability_engine.api import analysis_service
from crypto_probability_engine.api.schemas import AnalysisRequest
from crypto_probability_engine.automation.contract import (
    ErrorCode,
    RadarEvidenceRequest,
    build_radar_evidence,
    error_body,
)
from crypto_probability_engine.config.settings import Settings
from tests.automation.conftest import fixture_selection
from tests.fixtures.market_data import FIXED_NOW

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "docs" / "automation" / "examples"
SYNTHETIC_BUILD_INFO = {
    "schema_version": "build-info.v1",
    "release_id": "UCPE-SYNTHETIC-EXAMPLE-V1",
    "release_label": "SYNTHETIC example: no UCPE release serves this identity",
    "environment": "SYNTHETIC_FIXTURE",
    "source_milestone": "synthetic-example",
    "fingerprint": "UCPE SYNTHETIC EXAMPLE · NOT A RELEASE",
}
ISSUED_AT = (FIXED_NOW + timedelta(seconds=3)).isoformat().replace("+00:00", "Z")
PROVENANCE = (
    "SYNTHETIC_FIXTURE: the real UCPE analysis pipeline on deterministic fixture candles "
    "(tests/fixtures/market_data.make_snapshot at FIXED_NOW); no live data, no holdout, no "
    "section 5A evidence; synthetic release identity served by no UCPE release."
)
# (file, symbol, timeframe, provider, data_source, run-id seed, client_request_id, skill evidence)
SUCCESS_CASES = (
    (
        "radar_evidence.v1.synthetic-btc-4h-gate-blocked.json",
        "BTC",
        "4H",
        "okx",
        "OKX_PUBLIC",
        101,
        "0b6f2a1c-3d4e-4f5a-8b6c-7d8e9f0a1b2c",
        {"verdict": "INSUFFICIENT_EVIDENCE", "n": 0, "observed_directional_rate": None},
        "Hard gate blocked (SKILL_NOT_DEMONSTRATED), no H2 hold: the ordinary branch.",
    ),
    (
        "radar_evidence.v1.synthetic-eth-1h-h2-hold.json",
        "ETH",
        "1H",
        "binance",
        "BINANCE_PUBLIC",
        102,
        "1c7a3b2d-4e5f-4a6b-9c7d-8e9f0a1b2c3d",
        {"verdict": "SKILL_DEMONSTRATED", "n": 150, "observed_directional_rate": 0.58},
        "A legacy verdict under the H2 hold: the hold is carried as {active, hold_reason} only; "
        "the legacy verdict, n and the observed rate are withheld.",
    ),
)
ERROR_CASE = (
    "radar_evidence_error.v1.synthetic-quota-exceeded.json",
    ErrorCode.QUOTA_EXCEEDED,
    120,
    "A 429 refusal body (with Retry-After: 120 in the headers).",
)


@contextmanager
def _fixture_pipeline(provider: str, data_source: str, seed: int, skill_evidence: dict):
    saved = {
        name: getattr(analysis_service, name)
        for name in ("select_market_data", "uuid4", "get_cached_skill_evidence")
    }
    analysis_service.select_market_data = fixture_selection(provider, data_source)
    analysis_service.uuid4 = lambda: UUID(int=seed)
    analysis_service.get_cached_skill_evidence = lambda _timeframe: dict(skill_evidence)
    try:
        yield
    finally:
        for name, value in saved.items():
            setattr(analysis_service, name, value)


def build_examples() -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for name, symbol, timeframe, provider, source, seed, request_id, skill, _note in SUCCESS_CASES:
        with _fixture_pipeline(provider, source, seed, skill):
            analysis = analysis_service.analyze_request_isolated(
                AnalysisRequest(symbol=symbol, timeframe=timeframe),
                settings=Settings(data_mode="fixture"),
            )
        body = build_radar_evidence(
            analysis,
            request=RadarEvidenceRequest(symbol, timeframe, request_id, 30000),
            build_info=SYNTHETIC_BUILD_INFO,
            issued_at_utc=ISSUED_AT,
        )
        files[name] = _encode(body)
    error_name, code, retry_after, _note = ERROR_CASE
    files[error_name] = _encode(error_body(code, retry_after))
    notes = {case[0]: case[-1] for case in SUCCESS_CASES} | {ERROR_CASE[0]: ERROR_CASE[-1]}
    manifest = {
        "provenance": PROVENANCE,
        "generator": "tests/automation/examples_builder.py",
        "files": [
            {
                "file": name,
                "sha256": hashlib.sha256(content).hexdigest(),
                "validates_against": "radar_evidence_error.v1"
                if name.startswith("radar_evidence_error")
                else "radar_evidence.v1",
                "note": notes[name],
            }
            for name, content in sorted(files.items())
        ],
    }
    files["MANIFEST.json"] = _encode(manifest)
    return files


def _encode(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    files = build_examples()
    if args.write:
        EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
        for name, content in files.items():
            (EXAMPLES_DIR / name).write_bytes(content)
        print(f"wrote {len(files)} files to {EXAMPLES_DIR}")
        return 0
    stale = [name for name, content in files.items() if _read(EXAMPLES_DIR / name) != content]
    print("examples up to date" if not stale else f"stale: {stale}")
    return 1 if stale else 0


def _read(path: Path) -> bytes | None:
    return path.read_bytes() if path.is_file() else None


if __name__ == "__main__":
    raise SystemExit(main())
