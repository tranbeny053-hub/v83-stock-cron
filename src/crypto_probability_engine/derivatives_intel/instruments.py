"""Pure USDT-linear perpetual candidate mapping and registry validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class InstrumentResolutionStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED_INSTRUMENT = "UNSUPPORTED_INSTRUMENT"
    CONTRACT_MISMATCH = "CONTRACT_MISMATCH"
    INSTRUMENT_INACTIVE = "INSTRUMENT_INACTIVE"
    INVALID_SYMBOL = "INVALID_SYMBOL"


@dataclass(frozen=True)
class InstrumentResolution:
    normalized_symbol: str
    provider: str
    candidate: str | None
    status: InstrumentResolutionStatus
    reason: str | None
    contract_type: str | None
    margin_asset: str | None
    settlement_asset: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


def derivatives_candidates(normalized_symbol: str) -> dict[str, str] | None:
    compact = _compact_usdt_symbol(normalized_symbol)
    if compact is None:
        return None
    base = compact[: -len("USDT")]
    return {"BINANCE_USDM": compact, "OKX_SWAP": f"{base}-USDT-SWAP"}


def resolve_binance_usdm_instrument(
    normalized_symbol: str, exchange_info: Any
) -> InstrumentResolution:
    candidates = derivatives_candidates(normalized_symbol)
    if candidates is None:
        return _invalid(normalized_symbol, "BINANCE_USDM")
    candidate = candidates["BINANCE_USDM"]
    symbols = exchange_info.get("symbols") if isinstance(exchange_info, dict) else None
    if not isinstance(symbols, list):
        return _unsupported(normalized_symbol, "BINANCE_USDM", candidate)
    row = next(
        (item for item in symbols if isinstance(item, dict) and item.get("symbol") == candidate),
        None,
    )
    if row is None:
        return _unsupported(normalized_symbol, "BINANCE_USDM", candidate)
    contract_type = row.get("contractType")
    quote_asset = row.get("quoteAsset")
    margin_asset = row.get("marginAsset")
    if (
        contract_type != "PERPETUAL"
        or quote_asset not in {None, "USDT"}
        or margin_asset
        not in {
            None,
            "USDT",
        }
    ):
        return InstrumentResolution(
            normalized_symbol=_display_symbol(normalized_symbol),
            provider="BINANCE_USDM",
            candidate=candidate,
            status=InstrumentResolutionStatus.CONTRACT_MISMATCH,
            reason="Candidate is not the requested USDT-linear perpetual contract.",
            contract_type="CONTRACT_MISMATCH",
            margin_asset=str(margin_asset) if margin_asset is not None else None,
            settlement_asset=str(quote_asset) if quote_asset is not None else None,
        )
    if row.get("status") != "TRADING":
        return InstrumentResolution(
            normalized_symbol=_display_symbol(normalized_symbol),
            provider="BINANCE_USDM",
            candidate=candidate,
            status=InstrumentResolutionStatus.INSTRUMENT_INACTIVE,
            reason="Candidate perpetual contract is not active.",
            contract_type="USDT_LINEAR_PERPETUAL",
            margin_asset="USDT",
            settlement_asset="USDT",
        )
    return InstrumentResolution(
        normalized_symbol=_display_symbol(normalized_symbol),
        provider="BINANCE_USDM",
        candidate=candidate,
        status=InstrumentResolutionStatus.SUPPORTED,
        reason=None,
        contract_type="USDT_LINEAR_PERPETUAL",
        margin_asset="USDT",
        settlement_asset="USDT",
        metadata={
            key: row[key]
            for key in ("pair", "baseAsset", "quoteAsset", "marginAsset")
            if key in row
        },
    )


def resolve_okx_swap_instrument(
    normalized_symbol: str, instruments_payload: Any
) -> InstrumentResolution:
    candidates = derivatives_candidates(normalized_symbol)
    if candidates is None:
        return _invalid(normalized_symbol, "OKX_SWAP")
    candidate = candidates["OKX_SWAP"]
    rows = (
        instruments_payload.get("data")
        if isinstance(instruments_payload, dict)
        else instruments_payload
    )
    if not isinstance(rows, list):
        return _unsupported(normalized_symbol, "OKX_SWAP", candidate)
    row = next(
        (item for item in rows if isinstance(item, dict) and item.get("instId") == candidate),
        None,
    )
    if row is None:
        return _unsupported(normalized_symbol, "OKX_SWAP", candidate)
    if (
        row.get("instType") != "SWAP"
        or row.get("settleCcy") != "USDT"
        or row.get("ctType") != "linear"
    ):
        return InstrumentResolution(
            normalized_symbol=_display_symbol(normalized_symbol),
            provider="OKX_SWAP",
            candidate=candidate,
            status=InstrumentResolutionStatus.CONTRACT_MISMATCH,
            reason="Candidate is not the requested USDT-linear perpetual contract.",
            contract_type="CONTRACT_MISMATCH",
            margin_asset=str(row.get("settleCcy")) if row.get("settleCcy") is not None else None,
            settlement_asset=(
                str(row.get("settleCcy")) if row.get("settleCcy") is not None else None
            ),
            metadata=_okx_metadata(row),
        )
    if row.get("state") != "live":
        return InstrumentResolution(
            normalized_symbol=_display_symbol(normalized_symbol),
            provider="OKX_SWAP",
            candidate=candidate,
            status=InstrumentResolutionStatus.INSTRUMENT_INACTIVE,
            reason="Candidate perpetual contract is not active.",
            contract_type="USDT_LINEAR_PERPETUAL",
            margin_asset="USDT",
            settlement_asset="USDT",
            metadata=_okx_metadata(row),
        )
    return InstrumentResolution(
        normalized_symbol=_display_symbol(normalized_symbol),
        provider="OKX_SWAP",
        candidate=candidate,
        status=InstrumentResolutionStatus.SUPPORTED,
        reason=None,
        contract_type="USDT_LINEAR_PERPETUAL",
        margin_asset="USDT",
        settlement_asset="USDT",
        metadata=_okx_metadata(row),
    )


def _compact_usdt_symbol(value: str) -> str | None:
    compact = str(value).strip().upper().replace("/", "").replace("-", "")
    if not compact.endswith("USDT") or len(compact) <= 4 or not compact.isalnum():
        return None
    return compact


def _display_symbol(value: str) -> str:
    compact = _compact_usdt_symbol(value)
    return f"{compact[:-4]}/USDT" if compact else str(value).strip().upper()


def _invalid(normalized_symbol: str, provider: str) -> InstrumentResolution:
    return InstrumentResolution(
        normalized_symbol=str(normalized_symbol).strip().upper(),
        provider=provider,
        candidate=None,
        status=InstrumentResolutionStatus.INVALID_SYMBOL,
        reason="Normalized symbol is not a valid USDT pair.",
        contract_type=None,
        margin_asset=None,
        settlement_asset=None,
    )


def _unsupported(normalized_symbol: str, provider: str, candidate: str) -> InstrumentResolution:
    return InstrumentResolution(
        normalized_symbol=_display_symbol(normalized_symbol),
        provider=provider,
        candidate=candidate,
        status=InstrumentResolutionStatus.UNSUPPORTED_INSTRUMENT,
        reason="Exact provider candidate is absent from the public instrument registry.",
        contract_type=None,
        margin_asset=None,
        settlement_asset=None,
    )


def _okx_metadata(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row[key] for key in ("ctVal", "ctMult", "ctValCcy") if key in row}
