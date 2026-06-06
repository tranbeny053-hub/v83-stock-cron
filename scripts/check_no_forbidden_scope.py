"""Check implementation paths for forbidden capability strings."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_PATHS = [
    ROOT / "src",
    ROOT / "tests",
    ROOT / "schemas",
    ROOT / "frontend",
    ROOT / ".github" / "workflows",
]
FORBIDDEN_TERMS = (
    "place_order",
    "create_order",
    "submit_order",
    "cancel_order",
    "order_manager",
    "order_router",
    "execution_engine",
    "autonomous_execution",
    "auto_trade",
    "withdraw",
    "withdrawal",
    "transfer_funds",
    "internal_transfer",
    "sapi_withdraw",
    "enable_trading",
    "trade_permission",
    "margin_borrow",
    "leverage_set",
)


def iter_files() -> list[Path]:
    files: list[Path] = []
    for path in SCAN_PATHS:
        if path.is_file():
            files.append(path)
        elif path.exists():
            files.extend(item for item in path.rglob("*") if item.is_file())
    return files


def main() -> int:
    findings: list[str] = []
    for path in iter_files():
        if path.suffix in {".pyc", ".png", ".jpg", ".jpeg", ".gif"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for term in FORBIDDEN_TERMS:
            if term in text:
                findings.append(f"{path.relative_to(ROOT)}: contains {term}")
    if findings:
        print("\n".join(findings))
        return 1
    print("PASS: no forbidden capability strings found in implementation paths.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

