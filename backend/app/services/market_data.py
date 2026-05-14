import logging
import os
import time
from datetime import datetime, timedelta, timezone

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

        threshold = 2.0
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
