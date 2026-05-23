"""Earnings calendar utilities.

Pure-function wrappers around yfinance for asking 'is this ticker close to
an earnings announcement?'. Used to suppress predictions during the noise
window around earnings.

Designed to be portable: no daily-news imports beyond a lazy import of
yfinance/curl_cffi, so any other project (e.g. a backtest forecaster) can
copy this file unchanged.

All fetches are best-effort. yfinance earnings data is patchy — we degrade
to 'don't suppress' (return False) rather than crash the caller.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

logger = logging.getLogger(__name__)


def _make_ticker(symbol: str):
    """Construct a yfinance Ticker the same way market_data.py does, so the
    SSL workaround for curl_cffi is consistent across the codebase."""
    import yfinance as yf
    from curl_cffi.requests import Session
    session = Session(verify=False, impersonate="chrome")
    return yf.Ticker(symbol, session=session)


def get_next_earnings_date(ticker: str) -> date | None:
    """Return the next scheduled earnings date for ``ticker``, or None.

    Resilient to yfinance returning the calendar as a dict, a Series, or
    a DataFrame depending on version. Returns None if no data, the field
    is missing, or any exception occurs.
    """
    try:
        cal = _make_ticker(ticker).calendar
    except Exception:
        logger.exception("Earnings calendar fetch failed for %s", ticker)
        return None

    if cal is None:
        return None

    # Newer yfinance returns dict; older returns DataFrame
    candidate = None
    if isinstance(cal, dict):
        candidate = cal.get("Earnings Date") or cal.get("Earnings date")
    else:
        try:
            candidate = cal.loc["Earnings Date"]
        except Exception:
            candidate = None

    if candidate is None:
        return None

    # Unwrap list / Series to a single value
    if isinstance(candidate, list) and candidate:
        candidate = candidate[0]
    elif hasattr(candidate, "iloc"):
        try:
            candidate = candidate.iloc[0]
        except Exception:
            return None

    if isinstance(candidate, datetime):
        return candidate.date()
    if isinstance(candidate, date):
        return candidate
    return None


def is_in_earnings_window(
    ticker: str,
    *,
    days_before: int = 2,
    days_after: int = 1,
    today: date | None = None,
) -> bool:
    """Return True iff ``ticker`` has an earnings date within
    ``[today - days_after, today + days_before]`` (inclusive).

    days_before / days_after are deliberately asymmetric defaults: signals
    are noisiest in the run-up to earnings and the day after, so we suppress
    more aggressively before than after.
    """
    target = today or datetime.now(timezone.utc).date()
    edate = get_next_earnings_date(ticker)
    if edate is None:
        return False
    return (target - timedelta(days=days_after)) <= edate <= (target + timedelta(days=days_before))


def filter_out_earnings_window(
    tickers: list[str],
    *,
    days_before: int = 2,
    days_after: int = 1,
    today: date | None = None,
) -> tuple[list[str], list[str]]:
    """Split ``tickers`` into (kept, suppressed) based on earnings proximity.

    Returns two lists in the original order. Tickers with no earnings data
    (or any fetch failure) are kept — we don't punish data gaps.
    """
    kept: list[str] = []
    suppressed: list[str] = []
    for t in tickers:
        if is_in_earnings_window(t, days_before=days_before, days_after=days_after, today=today):
            suppressed.append(t)
        else:
            kept.append(t)
    return kept, suppressed
