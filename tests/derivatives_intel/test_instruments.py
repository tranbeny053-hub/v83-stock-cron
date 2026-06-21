from __future__ import annotations

import pytest

from crypto_probability_engine.derivatives_intel.instruments import (
    InstrumentResolutionStatus,
    derivatives_candidates,
    resolve_binance_usdm_instrument,
    resolve_okx_swap_instrument,
)


def _binance_row(**overrides) -> dict:
    row = {
        "symbol": "BTCUSDT",
        "pair": "BTCUSDT",
        "status": "TRADING",
        "contractType": "PERPETUAL",
        "baseAsset": "BTC",
        "quoteAsset": "USDT",
        "marginAsset": "USDT",
    }
    row.update(overrides)
    return row


def _okx_row(**overrides) -> dict:
    row = {
        "instId": "BTC-USDT-SWAP",
        "instType": "SWAP",
        "settleCcy": "USDT",
        "ctType": "linear",
        "state": "live",
        "ctVal": "0.01",
        "ctMult": "1",
        "ctValCcy": "BTC",
    }
    row.update(overrides)
    return row


def test_generic_usdt_candidate_mapping() -> None:
    assert derivatives_candidates("ETHUSDT") == {
        "BINANCE_USDM": "ETHUSDT",
        "OKX_SWAP": "ETH-USDT-SWAP",
    }
    assert derivatives_candidates("ETH/USDT") == {
        "BINANCE_USDM": "ETHUSDT",
        "OKX_SWAP": "ETH-USDT-SWAP",
    }
    assert derivatives_candidates("ETHUSD") is None


def test_supported_registries_validate_exact_candidates_and_preserve_metadata() -> None:
    binance = resolve_binance_usdm_instrument("BTC/USDT", {"symbols": [_binance_row()]})
    okx = resolve_okx_swap_instrument("BTC/USDT", [_okx_row()])
    assert binance.status == InstrumentResolutionStatus.SUPPORTED
    assert binance.candidate == "BTCUSDT"
    assert okx.status == InstrumentResolutionStatus.SUPPORTED
    assert okx.candidate == "BTC-USDT-SWAP"
    assert okx.metadata == {"ctVal": "0.01", "ctMult": "1", "ctValCcy": "BTC"}


@pytest.mark.parametrize(
    ("resolver", "registry", "expected"),
    [
        (
            resolve_binance_usdm_instrument,
            {"symbols": [_binance_row(status="SETTLING")]},
            InstrumentResolutionStatus.INSTRUMENT_INACTIVE,
        ),
        (
            resolve_binance_usdm_instrument,
            {"symbols": [_binance_row(contractType="CURRENT_QUARTER")]},
            InstrumentResolutionStatus.CONTRACT_MISMATCH,
        ),
        (
            resolve_binance_usdm_instrument,
            {"symbols": [_binance_row(marginAsset="BTC")]},
            InstrumentResolutionStatus.CONTRACT_MISMATCH,
        ),
        (
            resolve_okx_swap_instrument,
            [_okx_row(state="suspend")],
            InstrumentResolutionStatus.INSTRUMENT_INACTIVE,
        ),
        (
            resolve_okx_swap_instrument,
            [_okx_row(ctType="inverse", settleCcy="BTC")],
            InstrumentResolutionStatus.CONTRACT_MISMATCH,
        ),
        (
            resolve_okx_swap_instrument,
            [_okx_row(instType="FUTURES")],
            InstrumentResolutionStatus.CONTRACT_MISMATCH,
        ),
    ],
)
def test_registry_rejects_inactive_or_mismatched_contracts(resolver, registry, expected) -> None:
    assert resolver("BTCUSDT", registry).status == expected


def test_missing_exact_candidate_does_not_substitute_another_contract() -> None:
    binance = resolve_binance_usdm_instrument(
        "BTCUSDT", {"symbols": [_binance_row(symbol="ETHUSDT", pair="ETHUSDT")]}
    )
    okx = resolve_okx_swap_instrument("BTCUSDT", [_okx_row(instId="BTC-USDC-SWAP")])
    assert binance.status == InstrumentResolutionStatus.UNSUPPORTED_INSTRUMENT
    assert okx.status == InstrumentResolutionStatus.UNSUPPORTED_INSTRUMENT
