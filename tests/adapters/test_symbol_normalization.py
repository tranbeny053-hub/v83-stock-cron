from __future__ import annotations

import pytest

from crypto_probability_engine.normalizers.symbols import SymbolNormalizationError, normalize_symbol


@pytest.mark.parametrize(
    ("raw", "display", "binance", "okx"),
    [
        ("BTC", "BTC/USDT", "BTCUSDT", "BTC-USDT"),
        ("BTCUSDT", "BTC/USDT", "BTCUSDT", "BTC-USDT"),
        ("ETH-USDT", "ETH/USDT", "ETHUSDT", "ETH-USDT"),
        ("eth-usdt", "ETH/USDT", "ETHUSDT", "ETH-USDT"),
        ("SOLUSDT", "SOL/USDT", "SOLUSDT", "SOL-USDT"),
        ("SUI/USDT", "SUI/USDT", "SUIUSDT", "SUI-USDT"),
    ],
)
def test_normalize_supported_symbols(raw: str, display: str, binance: str, okx: str) -> None:
    normalized = normalize_symbol(raw)
    assert normalized.display == display
    assert normalized.provider_symbols["binance"] == binance
    assert normalized.provider_symbols["okx"] == okx


@pytest.mark.parametrize("raw", ["", "BTC/EUR", "BTC-", "$BTC"])
def test_invalid_symbols_fail_closed(raw: str) -> None:
    with pytest.raises(SymbolNormalizationError):
        normalize_symbol(raw)
