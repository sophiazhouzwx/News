import logging
import math
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

INDEX_TICKERS = {
    "S&P 500": "^GSPC",
    "NASDAQ": "^IXIC",
    "VIX": "^VIX",
    "SOX (Semiconductor)": "^SOX",
}

# yfinance 1.3+ uses curl_cffi which doesn't trust the system cert store
# in some environments. Disable SSL verification (same pattern as news_aggregator.py).
os.environ.setdefault("CURL_CA_BUNDLE", "")


_history_cache: dict[tuple[str, str], tuple[float, Any]] = {}
_HISTORY_TTL = 60 * 30  # 30 minutes — long enough for one digest run


def _make_ticker(symbol: str):
    import yfinance as yf
    from curl_cffi.requests import Session
    session = Session(verify=False, impersonate="chrome")
    return yf.Ticker(symbol, session=session)


def get_market_context() -> str:
    try:
        import yfinance  # noqa: F401
    except ImportError:
        logger.warning("yfinance not installed — market context unavailable")
        return ""

    lines = []
    for label, ticker in INDEX_TICKERS.items():
        try:
            hist = _make_ticker(ticker).history(period="5d")
            if hist.empty:
                continue
            close = hist["Close"].iloc[-1]
            prev_close = hist["Close"].iloc[-2] if len(hist) >= 2 else None
            change = ""
            if prev_close:
                pct = (close - prev_close) / prev_close * 100
                change = f" ({'+' if pct >= 0 else ''}{pct:.2f}%)"
            lines.append(f"- {label}: {close:.2f}{change}")
        except Exception:
            logger.exception("Failed to fetch index %s", ticker)
        time.sleep(0.3)

    if not lines:
        return ""
    return "MARKET CONTEXT (prior close):\n" + "\n".join(lines)


def get_price(ticker: str) -> float | None:
    try:
        import yfinance  # noqa: F401
        hist = _make_ticker(ticker).history(period="2d")
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception:
        logger.exception("Failed to get price for %s", ticker)
        return None


def get_ohlcv_history(ticker: str, period: str = "1y"):
    """Return a DataFrame of OHLCV for ticker. Cached per-process for 30 min."""
    key = (ticker.upper(), period)
    cached = _history_cache.get(key)
    if cached and time.time() - cached[0] < _HISTORY_TTL:
        return cached[1]
    try:
        hist = _make_ticker(ticker).history(period=period, auto_adjust=False)
        if hist is None or hist.empty:
            _history_cache[key] = (time.time(), None)
            return None
        _history_cache[key] = (time.time(), hist)
        return hist
    except Exception:
        logger.exception("Failed to fetch OHLCV history for %s", ticker)
        return None


def _safe_float(value) -> float | None:
    try:
        if value is None:
            return None
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def compute_technical_indicators(ticker: str) -> dict[str, Any]:
    """Compute standard technical signals on top of OHLCV history.

    Returns a dict of named indicators. Missing data falls back to None.
    All math is done with pandas/numpy — no extra dependency on `ta` libraries.
    """
    hist = get_ohlcv_history(ticker, period="1y")
    if hist is None or len(hist) < 30:
        return {"ticker": ticker, "available": False}

    import numpy as np

    close = hist["Close"].astype(float)
    high = hist["High"].astype(float)
    low = hist["Low"].astype(float)
    volume = hist["Volume"].astype(float)

    last_close = float(close.iloc[-1])

    # Moving averages
    sma_20 = close.rolling(20).mean().iloc[-1]
    sma_50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else float("nan")
    sma_200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else float("nan")
    ema_12 = close.ewm(span=12, adjust=False).mean().iloc[-1]
    ema_26 = close.ewm(span=26, adjust=False).mean().iloc[-1]

    # RSI (14)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi_series = 100 - (100 / (1 + rs))
    rsi = float(rsi_series.iloc[-1]) if not rsi_series.empty else float("nan")

    # MACD (12/26/9)
    macd_line = (close.ewm(span=12, adjust=False).mean()
                 - close.ewm(span=26, adjust=False).mean())
    macd_signal_line = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - macd_signal_line
    macd_now = float(macd_line.iloc[-1])
    macd_signal_now = float(macd_signal_line.iloc[-1])
    macd_hist_now = float(macd_hist.iloc[-1])
    macd_hist_prev = float(macd_hist.iloc[-2]) if len(macd_hist) >= 2 else macd_hist_now

    if macd_hist_prev <= 0 < macd_hist_now:
        macd_signal_label = "bullish_crossover"
    elif macd_hist_prev >= 0 > macd_hist_now:
        macd_signal_label = "bearish_crossover"
    elif macd_hist_now > 0:
        macd_signal_label = "bullish"
    elif macd_hist_now < 0:
        macd_signal_label = "bearish"
    else:
        macd_signal_label = "neutral"

    # Bollinger Bands (20, 2σ)
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    bb_pct_b = (last_close - bb_lower.iloc[-1]) / (bb_upper.iloc[-1] - bb_lower.iloc[-1]) \
        if bb_upper.iloc[-1] != bb_lower.iloc[-1] else float("nan")

    # ATR (14) — average true range
    prev_close_shift = close.shift(1)
    tr = np.maximum.reduce([
        (high - low).values,
        (high - prev_close_shift).abs().values,
        (low - prev_close_shift).abs().values,
    ])
    tr_series = close.copy()
    tr_series[:] = tr
    atr = float(tr_series.rolling(14).mean().iloc[-1])

    # On-Balance Volume
    obv = (np.sign(close.diff().fillna(0)) * volume).cumsum()
    obv_slope = float(obv.iloc[-1] - obv.iloc[-20]) if len(obv) >= 20 else 0.0

    # Returns / realized vol
    daily_returns = close.pct_change().dropna()
    realized_vol = float(daily_returns.tail(30).std()) if len(daily_returns) >= 30 else float("nan")
    realized_vol_annualized = realized_vol * math.sqrt(252) if not math.isnan(realized_vol) else float("nan")

    # 12-month minus last-month momentum (classic factor)
    if len(close) >= 21:
        ret_12m = (close.iloc[-1] / close.iloc[max(0, len(close) - 252)] - 1) if len(close) >= 252 else float("nan")
        ret_1m = (close.iloc[-1] / close.iloc[-21] - 1)
    else:
        ret_12m = float("nan")
        ret_1m = float("nan")
    momentum_12_1 = (ret_12m - ret_1m) if (not math.isnan(ret_12m) and not math.isnan(ret_1m)) else float("nan")

    return {
        "ticker": ticker,
        "available": True,
        "last_close": last_close,
        "sma_20": _safe_float(sma_20),
        "sma_50": _safe_float(sma_50),
        "sma_200": _safe_float(sma_200),
        "ema_12": _safe_float(ema_12),
        "ema_26": _safe_float(ema_26),
        "rsi_14": _safe_float(rsi),
        "macd": _safe_float(macd_now),
        "macd_signal": _safe_float(macd_signal_now),
        "macd_hist": _safe_float(macd_hist_now),
        "macd_signal_label": macd_signal_label,
        "bb_upper": _safe_float(bb_upper.iloc[-1]),
        "bb_lower": _safe_float(bb_lower.iloc[-1]),
        "bb_pct_b": _safe_float(bb_pct_b),
        "atr_14": _safe_float(atr),
        "obv_slope_20d": _safe_float(obv_slope),
        "realized_vol_daily": _safe_float(realized_vol),
        "realized_vol_annualized": _safe_float(realized_vol_annualized),
        "return_1m": _safe_float(ret_1m),
        "return_12m": _safe_float(ret_12m),
        "momentum_12_1": _safe_float(momentum_12_1),
    }


def get_fundamental_data(ticker: str) -> dict[str, Any]:
    """Return key fundamentals from yfinance .info. All fields default to None
    on missing data — never raises."""
    try:
        info = _make_ticker(ticker).info or {}
    except Exception:
        logger.exception("Failed to fetch fundamentals for %s", ticker)
        info = {}

    return {
        "ticker": ticker,
        "pe_ratio": _safe_float(info.get("trailingPE")),
        "forward_pe": _safe_float(info.get("forwardPE")),
        "peg_ratio": _safe_float(info.get("pegRatio")),
        "price_to_book": _safe_float(info.get("priceToBook")),
        "earnings_yield": (1.0 / _safe_float(info.get("trailingPE"))
                           if _safe_float(info.get("trailingPE")) else None),
        "revenue_growth": _safe_float(info.get("revenueGrowth")),
        "earnings_growth": _safe_float(info.get("earningsGrowth")),
        "profit_margin": _safe_float(info.get("profitMargins")),
        "return_on_equity": _safe_float(info.get("returnOnEquity")),
        "debt_to_equity": _safe_float(info.get("debtToEquity")),
        "market_cap": _safe_float(info.get("marketCap")),
        "sector": info.get("sector") or "",
        "industry": info.get("industry") or "",
        "short_ratio": _safe_float(info.get("shortRatio")),
        "short_percent_float": _safe_float(info.get("shortPercentOfFloat")),
        "beta": _safe_float(info.get("beta")),
    }


def compute_factor_scores(ticker: str,
                          tech: dict[str, Any] | None = None,
                          fund: dict[str, Any] | None = None) -> dict[str, Any]:
    """Produce standardized alpha factor scores.

    Each returned score is z-score-like — positive means the stock looks
    favorable on that factor, negative means unfavorable. Values are clipped
    to roughly [-3, +3] but not strictly normalized across the universe (we
    don't pull a universe of comparables here).
    """
    if tech is None:
        tech = compute_technical_indicators(ticker)
    if fund is None:
        fund = get_fundamental_data(ticker)

    def clip(x, lo=-3.0, hi=3.0):
        if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
            return None
        return max(lo, min(hi, float(x)))

    # Momentum: 12-1 momentum, scaled by ~20% std dev typical for tech
    momentum_z = None
    if tech.get("momentum_12_1") is not None:
        momentum_z = clip(tech["momentum_12_1"] / 0.20)

    # Value: earnings yield z (relative to a 5% "neutral" with 3% std)
    value_z = None
    if fund.get("earnings_yield") is not None:
        value_z = clip((fund["earnings_yield"] - 0.05) / 0.03)
    elif fund.get("forward_pe") and fund["forward_pe"] > 0:
        # Lower PE = more attractive. Use 20 as neutral with std 10.
        value_z = clip(-(fund["forward_pe"] - 20.0) / 10.0)

    # Volatility: LOWER realized vol = positive factor. 30% annualized = neutral.
    volatility_z = None
    if tech.get("realized_vol_annualized") is not None:
        volatility_z = clip(-(tech["realized_vol_annualized"] - 0.30) / 0.20)

    # Quality: ROE positive, debt/equity low. Combine with simple weighting.
    quality_components = []
    if fund.get("return_on_equity") is not None:
        # 15% ROE = neutral, std 10%
        quality_components.append((fund["return_on_equity"] - 0.15) / 0.10)
    if fund.get("debt_to_equity") is not None:
        # 100 (=1.0) ratio neutral; lower is better. yfinance reports as %.
        quality_components.append(-(fund["debt_to_equity"] - 100.0) / 100.0)
    if fund.get("profit_margin") is not None:
        quality_components.append((fund["profit_margin"] - 0.10) / 0.10)
    quality_z = clip(sum(quality_components) / len(quality_components)) if quality_components else None

    # Technical "momentum-confirm" overlay from RSI + MACD
    technical_z = None
    rsi = tech.get("rsi_14")
    macd_signal_label = tech.get("macd_signal_label", "neutral")
    if rsi is not None:
        # RSI 50 neutral; oversold (<30) → +ve mean reversion;
        # overbought (>70) → -ve. Use a piecewise mapping.
        if rsi < 30:
            base = (30 - rsi) / 15.0  # 0..2
        elif rsi > 70:
            base = -(rsi - 70) / 15.0  # 0..-2
        else:
            base = (rsi - 50) / 25.0  # mild trend bias
        macd_adj = {
            "bullish_crossover": 0.7,
            "bullish": 0.3,
            "neutral": 0.0,
            "bearish": -0.3,
            "bearish_crossover": -0.7,
        }.get(macd_signal_label, 0.0)
        technical_z = clip(base + macd_adj)

    return {
        "ticker": ticker,
        "momentum_score": momentum_z,
        "value_score": value_z,
        "volatility_score": volatility_z,
        "quality_score": quality_z,
        "technical_score": technical_z,
    }


def estimate_timeframe_days(tech: dict[str, Any], target_pct: float = 2.0) -> int:
    """Estimate days needed to realize a `target_pct` move given the stock's
    realized daily volatility. Defaults to 14 if data is unavailable.

    Uses sqrt-of-time scaling: expected_move(N) ≈ vol_daily * sqrt(N) * close.
    Solve for N s.t. expected_move == target_pct% of close.
    """
    vol = tech.get("realized_vol_daily")
    if vol is None or vol <= 0:
        return 14
    # target_pct% / 100 == vol_daily * sqrt(N)
    n_days = (target_pct / 100.0 / vol) ** 2
    return max(3, min(60, int(round(n_days))))


def adaptive_threshold_pct(tech: dict[str, Any], timeframe_days: int) -> float:
    """Per-ticker hit threshold based on the stock's own daily realized vol.

    Default is 2% (matches the legacy verifier). For higher-vol names we
    widen the threshold so a 'hit' represents a real move, not noise.
    """
    vol = tech.get("realized_vol_daily") if isinstance(tech, dict) else None
    if vol is None or vol <= 0:
        return 2.0
    # One standard deviation of expected timeframe move, as a percentage
    return max(1.0, min(8.0, vol * math.sqrt(max(1, timeframe_days)) * 100.0))


def verify_prediction_items(db) -> int:
    from ..database import PredictionItem, DailyPrediction

    now = datetime.now(timezone.utc)
    pending = (
        db.query(PredictionItem)
        .filter(PredictionItem.outcome.is_(None))
        .all()
    )

    verified_count = 0
    for item in pending:
        pred = db.query(DailyPrediction).get(item.prediction_id)
        if not pred:
            continue

        try:
            pred_date = datetime.strptime(pred.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        deadline = pred_date + timedelta(days=item.timeframe_days)
        if now < deadline:
            continue

        current_price = get_price(item.ticker)
        if current_price is None:
            logger.warning("Could not verify %s — price unavailable", item.ticker)
            continue

        if item.price_at_prediction is None:
            item.outcome = "expired"
            item.verified_at = now
            db.commit()
            verified_count += 1
            continue

        change_pct = (current_price - item.price_at_prediction) / item.price_at_prediction * 100
        item.price_at_verification = current_price
        item.actual_change_pct = round(change_pct, 2)
        item.verified_at = now

        # Use the threshold the model committed to at prediction time when
        # available; otherwise fall back to 2% (legacy behavior).
        threshold = item.threshold_pct if item.threshold_pct else 2.0
        if item.direction == "bull":
            item.outcome = "hit" if change_pct >= threshold else "miss"
        elif item.direction == "bear":
            item.outcome = "hit" if change_pct <= -threshold else "miss"
        else:
            item.outcome = "hit" if abs(change_pct) < threshold else "miss"

        db.commit()
        verified_count += 1
        time.sleep(0.3)

    return verified_count
