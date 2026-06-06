"""Crypto spot symbol normalization."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedSymbol:
    raw: str
    base: str
    quote: str
    display: str
    provider_symbols: dict[str, str]


class SymbolNormalizationError(ValueError):
    pass


SUPPORTED_QUOTES = ("USDT",)
SUPPORTED_BASES = {"BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE"}
SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,12}([/-]?[A-Z0-9]{2,12})?$")


def normalize_symbol(raw_symbol: str, *, default_quote: str = "USDT") -> NormalizedSymbol:
    raw = raw_symbol.strip()
    cleaned = raw.upper().replace("_", "-")
    if not raw or not SYMBOL_RE.match(cleaned):
        raise SymbolNormalizationError("Invalid crypto symbol format.")

    if "/" in cleaned:
        base, quote = cleaned.split("/", maxsplit=1)
    elif "-" in cleaned:
        base, quote = cleaned.split("-", maxsplit=1)
    else:
        quote = next(
            (candidate for candidate in SUPPORTED_QUOTES if cleaned.endswith(candidate)),
            "",
        )
        if quote and cleaned != quote:
            base = cleaned[: -len(quote)]
        else:
            base = cleaned
            quote = default_quote

    if quote not in SUPPORTED_QUOTES or base not in SUPPORTED_BASES or base == quote:
        raise SymbolNormalizationError("Unsupported crypto symbol.")

    display = f"{base}/{quote}"
    return NormalizedSymbol(
        raw=raw_symbol,
        base=base,
        quote=quote,
        display=display,
        provider_symbols={
            "binance": f"{base}{quote}",
            "okx": f"{base}-{quote}",
        },
    )
