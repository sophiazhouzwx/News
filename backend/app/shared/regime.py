"""Market regime factor.

Compresses broad-market context (VIX, S&P 500 vs its 50-day SMA, a sector
ETF's recent return) into a single z-score-like factor in roughly [-3, +3].

- Positive = risk-on / calm tape — bullish stock calls have tailwind.
- Negative = risk-off / nervous tape — bullish calls face headwind.

The function is split into two layers so it's trivially testable:
- ``regime_factor_from_levels`` is pure: takes already-fetched numbers,
  returns a score. Easy to backtest with point-in-time data.
- ``get_live_regime_factor`` is the I/O wrapper that calls yfinance.

A forecaster project that loads historical OHLCV from parquet should
call ``regime_factor_from_levels`` directly and skip the live wrapper.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def regime_factor_from_levels(
    *,
    vix_level: float | None,
    spx_close: float | None = None,
    spx_sma50: float | None = None,
    sector_etf_return_5d: float | None = None,
) -> float | None:
    """Compute the regime z-score from raw market levels. Pure function.

    VIX is required (anchors the score). The other inputs are optional;
    each one present adds another component to the average. Returns None
    only if VIX is missing.

    Calibration:
    - VIX 22 → 0, VIX 12 → +1.5, VIX 32 → -1.5
    - SPX +3% above SMA50 → +1, -3% below → -1
    - Sector 5d return +2% → +1, -2% → -1
    """
    if vix_level is None:
        return None

    components: list[float] = []

    # VIX component — historically std ~6.7 around 22
    vix_z = (22.0 - float(vix_level)) / 6.7
    components.append(vix_z)

    if spx_close is not None and spx_sma50 is not None and spx_sma50 > 0:
        spx_z = (float(spx_close) / float(spx_sma50) - 1.0) / 0.03
        components.append(spx_z)

    if sector_etf_return_5d is not None:
        sec_z = float(sector_etf_return_5d) / 0.02
        components.append(sec_z)

    raw = sum(components) / len(components)
    return max(-3.0, min(3.0, raw))


def get_live_regime_factor(
    fetcher: Callable[[str], Any] | None = None,
) -> float | None:
    """Fetch current market levels via yfinance and compute the regime factor.

    ``fetcher(symbol)`` should return an OHLCV DataFrame (with ``Close``
    column) or None. Defaults to ``daily_news.market_data.get_ohlcv_history``.
    Tests / backtests inject their own fetcher with synthetic data.
    """
    if fetcher is None:
        try:
            from ..services.market_data import get_ohlcv_history
        except ImportError:
            logger.warning("market_data not importable — regime factor unavailable")
            return None

        def _default(sym: str):
            return get_ohlcv_history(sym, period="3mo")

        fetcher = _default

    vix_hist = fetcher("^VIX")
    spx_hist = fetcher("^GSPC")
    sox_hist = fetcher("^SOX")

    vix_level = _safe_last_close(vix_hist)
    spx_close = _safe_last_close(spx_hist)
    spx_sma50 = _safe_sma(spx_hist, 50)
    sec_ret_5d = _safe_return_n(sox_hist, 5)

    return regime_factor_from_levels(
        vix_level=vix_level,
        spx_close=spx_close,
        spx_sma50=spx_sma50,
        sector_etf_return_5d=sec_ret_5d,
    )


def _safe_last_close(hist) -> float | None:
    try:
        if hist is None or len(hist) == 0:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception:
        return None


def _safe_sma(hist, n: int) -> float | None:
    try:
        if hist is None or len(hist) < n:
            return None
        return float(hist["Close"].rolling(n).mean().iloc[-1])
    except Exception:
        return None


def _safe_return_n(hist, n: int) -> float | None:
    try:
        if hist is None or len(hist) <= n:
            return None
        start = hist["Close"].iloc[-(n + 1)]
        end = hist["Close"].iloc[-1]
        if start <= 0:
            return None
        return float(end / start - 1.0)
    except Exception:
        return None
