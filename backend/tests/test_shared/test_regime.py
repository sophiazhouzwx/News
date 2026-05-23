"""Tests for the market regime factor."""

from __future__ import annotations

import pandas as pd

from app.shared.regime import (
    get_live_regime_factor,
    regime_factor_from_levels,
)


# ---------------------------------------------------------------------------
# Pure function: regime_factor_from_levels
# ---------------------------------------------------------------------------
def test_returns_none_when_vix_missing():
    assert regime_factor_from_levels(vix_level=None) is None


def test_calm_tape_positive():
    # Low VIX, SPX above SMA, sector up 1% in 5d → all positive
    score = regime_factor_from_levels(
        vix_level=14.0,
        spx_close=4500.0,
        spx_sma50=4400.0,    # spx 2.27% above SMA → ~+0.76 z
        sector_etf_return_5d=0.015,  # +0.75 z
    )
    assert score is not None
    assert score > 0.5


def test_stressed_tape_negative():
    score = regime_factor_from_levels(
        vix_level=35.0,
        spx_close=4400.0,
        spx_sma50=4600.0,    # SPX -4.3% vs SMA
        sector_etf_return_5d=-0.04,
    )
    assert score is not None
    assert score < -0.5


def test_only_vix_works():
    score = regime_factor_from_levels(vix_level=22.0)
    assert score is not None
    # VIX 22 = neutral baseline
    assert abs(score) < 0.01


def test_clipped_to_3():
    score = regime_factor_from_levels(
        vix_level=1.0, spx_close=10000.0, spx_sma50=1.0,
        sector_etf_return_5d=10.0,
    )
    assert score == 3.0

    score = regime_factor_from_levels(
        vix_level=120.0, spx_close=1.0, spx_sma50=10000.0,
        sector_etf_return_5d=-10.0,
    )
    assert score == -3.0


# ---------------------------------------------------------------------------
# I/O wrapper: get_live_regime_factor with a fake fetcher
# ---------------------------------------------------------------------------
def test_get_live_uses_injected_fetcher():
    def fake_fetch(sym):
        # Tiny synthetic 60-day series so SMA50 is computable
        closes = list(range(60))  # ramp up
        if sym == "^VIX":
            return pd.DataFrame({"Close": [14.0] * 60})
        if sym == "^GSPC":
            return pd.DataFrame({"Close": closes})  # last=59, sma50 ≈ 34.5
        if sym == "^SOX":
            return pd.DataFrame({"Close": closes})
        return None

    score = get_live_regime_factor(fetcher=fake_fetch)
    assert score is not None
    # Low VIX + SPX way above SMA + positive 5d return → strongly positive
    assert score > 1.0


def test_get_live_handles_no_data():
    score = get_live_regime_factor(fetcher=lambda s: None)
    # No VIX → None
    assert score is None
