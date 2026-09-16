"""Runtime freeze proof for the distributional OOS candidate.

Regenerate the reviewed pin after an intentional candidate change with::

    PYTHONPATH=src python -m crypto_probability_engine.oos.freeze_guard --write

Normal collection must call :func:`assert_candidate_freeze` immediately before
constructing a write-capable repository.  The guard performs no network or
database I/O.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from crypto_probability_engine.adapters.types import (
    MarketCandle,
    MarketSnapshot,
    OrderBookLevel,
    OrderBookSnapshot,
)
from crypto_probability_engine.quant import pipeline as quant_pipeline
from crypto_probability_engine.quant import probability_distributional

FREEZE_SCHEMA_VERSION = "oos-candidate-freeze.v3"
DEFAULT_PIN = Path("ops/oos_candidate_freeze.json")
_PACKAGE = "crypto_probability_engine"
_ENTRYPOINT = "src/crypto_probability_engine/quant/probability_distributional.py"
_DECLARED_INPUT_WIRING = frozenset(
    {
        "src/crypto_probability_engine/quant/pipeline.py",
        "src/crypto_probability_engine/execution_realism/realism.py",
        "src/crypto_probability_engine/features/liquidity_depth.py",
        "src/crypto_probability_engine/config/defaults.py",
        "src/crypto_probability_engine/quant/epistemic_sufficiency.py",
    }
)
_TIMEFRAMES = ("15m", "1H", "4H")
_BANDS = (0.00200, 0.00325, 0.00450, 0.00700)


class FreezeGuardMismatch(RuntimeError):
    """The reviewed candidate pin does not match the runtime candidate."""


def project_root() -> Path:
    """Return the repository root without consulting process environment."""

    return Path(__file__).resolve().parents[3]


def first_party_import_closure(root: Path | None = None) -> tuple[str, ...]:
    """Return the deterministic source closure plus declared input wiring."""

    repository_root = (root or project_root()).resolve()
    source_root = repository_root / "src"
    pending = [_ENTRYPOINT]
    closure: set[str] = set()
    while pending:
        relative = pending.pop()
        if relative in closure:
            continue
        path = repository_root / relative
        if not path.is_file():
            raise FreezeGuardMismatch(f"freeze closure file is missing: {relative}")
        closure.add(relative)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        except (OSError, SyntaxError, UnicodeError) as exc:
            raise FreezeGuardMismatch(f"freeze closure cannot parse: {relative}") from exc
        for module_name in _first_party_imports(tree, relative):
            imported = _module_source_path(source_root, module_name)
            if imported is not None:
                pending.append(imported.relative_to(repository_root).as_posix())
    closure.update(_DECLARED_INPUT_WIRING)
    missing = sorted(path for path in closure if not (repository_root / path).is_file())
    if missing:
        raise FreezeGuardMismatch(f"freeze closure files are missing: {', '.join(missing)}")
    return tuple(sorted(closure))


def closure_digest(root: Path | None = None) -> tuple[tuple[str, ...], str]:
    """Digest the sorted closure names and every byte of their contents."""

    repository_root = (root or project_root()).resolve()
    files = first_party_import_closure(repository_root)
    digest = hashlib.sha256()
    digest.update(_canonical_json(list(files)))
    for relative in files:
        content = (repository_root / relative).read_bytes()
        digest.update(b"\0path\0")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0content\0")
        digest.update(content)
    return files, digest.hexdigest()


def parameters_digest(parameters: Mapping[str, Any] | None = None) -> str:
    """Digest resolved parameter values rather than only their source text."""

    if parameters is None:
        parameters = probability_distributional.FROZEN_B3_PARAMETERS
    return hashlib.sha256(_canonical_json(_plain_value(parameters))).hexdigest()


def behavioural_fingerprint() -> str:
    """Digest candidate probabilities over the fixed v3 deterministic grid."""

    records: list[dict[str, object]] = []
    for timeframe in _TIMEFRAMES:
        for epistemic_label, candle_count in (("ALLOW", 200), ("NON_ALLOW", 24)):
            candles = _synthetic_candles(timeframe, candle_count)
            for band in _BANDS:
                snapshot = MarketSnapshot(
                    provider="freeze-guard",
                    normalized_symbol="BTC/USDT",
                    timeframe=timeframe,
                    candles=candles,
                    order_book=_synthetic_order_book(
                        band,
                        candles[-1].close_time_utc,
                    ),
                    as_of_utc=candles[-1].close_time_utc,
                )
                result = quant_pipeline.run_quant_pipeline(
                    snapshot,
                    {"status": "OK", "providers": {}},
                    methodology_version="distributional-v1",
                )
                action = result["epistemic_sufficiency_state"].get("action")
                if (epistemic_label == "ALLOW") != (action == "ALLOW"):
                    raise FreezeGuardMismatch(
                        "freeze fingerprint epistemic grid is invalid"
                    )
                state = result["probability_state"]["horizons"]["H_primary"]
                records.append(
                    {
                        "band_frac": band,
                        "epistemic": epistemic_label,
                        "p_down": round(float(state["p_down_frac"]), 12),
                        "p_timeout": round(float(state["p_timeout_frac"]), 12),
                        "p_up": round(float(state["p_up_frac"]), 12),
                        "timeframe": timeframe,
                    }
                )
    return hashlib.sha256(_canonical_json(records)).hexdigest()


def current_freeze_artifacts(root: Path | None = None) -> dict[str, object]:
    """Recompute all three freeze artifacts from current code."""

    files, content_digest = closure_digest(root)
    return {
        "schema_version": FREEZE_SCHEMA_VERSION,
        "closure_files": list(files),
        "closure_digest": content_digest,
        "frozen_b3_parameters_digest": parameters_digest(),
        "behavioural_fingerprint": behavioural_fingerprint(),
    }


def assert_candidate_freeze(
    *,
    pin_path: Path | None = None,
    root: Path | None = None,
) -> dict[str, object]:
    """Return the artifacts when pinned, otherwise fail closed before writes."""

    repository_root = (root or project_root()).resolve()
    resolved_pin = _resolved_pin_path(repository_root, pin_path)
    try:
        pinned = json.loads(resolved_pin.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FreezeGuardMismatch("candidate freeze pin is missing or invalid") from exc
    current = current_freeze_artifacts(repository_root)
    if pinned != current:
        mismatches = sorted(
            key
            for key in set(pinned) | set(current)
            if pinned.get(key) != current.get(key)
        )
        detail = ", ".join(mismatches) or "unknown artifact"
        raise FreezeGuardMismatch(f"candidate freeze mismatch: {detail}")
    return current


def write_candidate_freeze(
    *,
    pin_path: Path | None = None,
    root: Path | None = None,
) -> dict[str, object]:
    """Explicit generator path for a reviewed re-pin from current code."""

    repository_root = (root or project_root()).resolve()
    resolved_pin = _resolved_pin_path(repository_root, pin_path)
    artifacts = current_freeze_artifacts(repository_root)
    resolved_pin.parent.mkdir(parents=True, exist_ok=True)
    resolved_pin.write_bytes(_canonical_json(artifacts) + b"\n")
    return artifacts


def _first_party_imports(tree: ast.AST, relative: str) -> set[str]:
    current_module = _module_name_for_relative(relative)
    package_parts = current_module.split(".")[:-1]
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(
                alias.name
                for alias in node.names
                if alias.name == _PACKAGE
                or alias.name.startswith(f"{_PACKAGE}.")
            )
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                keep = len(package_parts) - node.level + 1
                base_parts = package_parts[: max(0, keep)]
                if node.module:
                    base_parts.extend(node.module.split("."))
                base = ".".join(base_parts)
            else:
                base = node.module or ""
            if base == _PACKAGE or base.startswith(f"{_PACKAGE}."):
                imports.add(base)
                imports.update(f"{base}.{alias.name}" for alias in node.names)
    return imports


def _module_name_for_relative(relative: str) -> str:
    module = relative.removeprefix("src/").removesuffix(".py").replace("/", ".")
    return module.removesuffix(".__init__")


def _module_source_path(source_root: Path, module_name: str) -> Path | None:
    relative = Path(*module_name.split("."))
    module_file = source_root / relative.with_suffix(".py")
    if module_file.is_file():
        return module_file
    package_file = source_root / relative / "__init__.py"
    return package_file if package_file.is_file() else None


def _synthetic_candles(timeframe: str, count: int) -> tuple[MarketCandle, ...]:
    seconds = {"15m": 900, "1H": 3600, "4H": 14_400}[timeframe]
    start = datetime(2024, 1, 1, tzinfo=UTC)
    closes: list[float] = []
    price = 100.0 + _TIMEFRAMES.index(timeframe) * 7.0
    for index in range(count):
        signed_cycle = ((index * 17 + 3) % 23) - 11
        price *= 1.0 + (signed_cycle * 0.00037) + ((index % 5) * 0.000041)
        closes.append(price)
    candles = []
    for index, close in enumerate(closes):
        open_price = closes[index - 1] if index else close / 1.0003
        open_time = start + timedelta(seconds=index * seconds)
        candles.append(
            MarketCandle(
                open_time_utc=open_time,
                close_time_utc=open_time + timedelta(seconds=seconds),
                open=open_price,
                high=max(open_price, close) * 1.001,
                low=min(open_price, close) * 0.999,
                close=close,
                volume=1000.0 + index * 3.0,
            )
        )
    return tuple(candles)


def _synthetic_order_book(
    band_frac: float, as_of_utc: datetime
) -> OrderBookSnapshot:
    # The reviewed taker fee is deliberately literal here.  A runtime fee
    # mutation must alter the output fingerprint rather than be cancelled by
    # adapting the synthetic input to the mutation.
    spread_frac = 2.0 * (band_frac - 0.002)
    mid = 100.0
    bid = mid * (1.0 - spread_frac / 2.0)
    ask = mid * (1.0 + spread_frac / 2.0)
    return OrderBookSnapshot(
        bids=(OrderBookLevel(price=bid, size=20.0),),
        asks=(OrderBookLevel(price=ask, size=20.0),),
        as_of_utc=as_of_utc,
    )


def _plain_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain_value(item) for item in value]
    return value


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _resolved_pin_path(repository_root: Path, pin_path: Path | None) -> Path:
    if pin_path is None:
        return repository_root / DEFAULT_PIN
    return pin_path if pin_path.is_absolute() else repository_root / pin_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify or regenerate the OOS candidate pin.")
    parser.add_argument("--write", action="store_true", help="rewrite the pin from current code")
    args = parser.parse_args(argv)
    if args.write:
        write_candidate_freeze()
        print("FREEZE_PIN=WRITTEN")
    else:
        assert_candidate_freeze()
        print("FREEZE_PIN=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
