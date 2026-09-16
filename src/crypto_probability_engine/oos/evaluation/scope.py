"""The tranche-1 scope: the ONE definition every evaluation layer uses.

Contract: ``V1_QUANT_CONTRACT.md`` §5A.1 and §5A.7. Tranche 1 is exactly six cells — 15m, 1H and
4H over BTC/USDT and ETH/USDT. Every other cell stays on the current methodology, and "a
newly-appearing USDT asset inherits nothing".

WHY IT IS ENFORCED AT ADMISSION (finding V807-F1). Scope used to be applied only at
authorization, after A and B were computed. An out-of-tranche asset in the evidence was therefore
pooled into A and B: losing BTC evidence alone was NOT_PASS, and adding favourable SOL/USDT
flipped A and B to true. Scope now gates the population BEFORE any statistic, attainability
verdict, diagnostic or identity is computed.
"""

from __future__ import annotations

TRANCHE_1_SYMBOLS: tuple[str, ...] = ("BTC/USDT", "ETH/USDT")
TRANCHE_1_TIMEFRAMES: tuple[str, ...] = ("15m", "1H", "4H")


def in_tranche_scope(symbol: object, timeframe: object) -> bool:
    return symbol in TRANCHE_1_SYMBOLS and timeframe in TRANCHE_1_TIMEFRAMES
