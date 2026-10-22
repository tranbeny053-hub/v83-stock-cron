"""Synthetic target availability contract tests."""

import pytest

from crypto_probability_engine.quant_ng.availability import (
    H24_LABEL_STATUS,
    UnavailableTarget,
    target_unavailable_reason,
)


@pytest.mark.parametrize("timeframe", ["15m", "1H", "4H", "1D", "1W", "1M"])
@pytest.mark.parametrize("horizon", ["H_primary", "H_extended"])
def test_target_availability_matrix(timeframe: str, horizon: str) -> None:
    result = target_unavailable_reason(timeframe, horizon)
    if timeframe == "1M":
        assert result is UnavailableTarget.TARGET_NOT_RESOLVABLE_1M
    elif horizon == "H_extended":
        assert result is UnavailableTarget.NOT_MODELED
    else:
        assert result is None


def test_bad_horizon_and_deferred_24_bar_status() -> None:
    with pytest.raises(ValueError):
        target_unavailable_reason("1D", "H24")
    assert H24_LABEL_STATUS == "DEFERRED_NOT_CANCELLED"
