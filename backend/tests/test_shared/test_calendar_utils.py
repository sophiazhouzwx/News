"""Tests for the earnings-calendar helper.

We don't hit yfinance live — the network call is patched per-test so the
suite stays hermetic and fast.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from app.shared.calendar_utils import (
    filter_out_earnings_window,
    is_in_earnings_window,
)


@patch("app.shared.calendar_utils.get_next_earnings_date")
def test_is_in_window_when_earnings_tomorrow(mock_next):
    today = date(2026, 5, 23)
    mock_next.return_value = date(2026, 5, 24)
    assert is_in_earnings_window("AAPL", days_before=2, days_after=1, today=today)


@patch("app.shared.calendar_utils.get_next_earnings_date")
def test_is_in_window_when_earnings_yesterday(mock_next):
    today = date(2026, 5, 23)
    mock_next.return_value = date(2026, 5, 22)
    # days_after=1 → yesterday is still in the window
    assert is_in_earnings_window("AAPL", days_before=2, days_after=1, today=today)


@patch("app.shared.calendar_utils.get_next_earnings_date")
def test_not_in_window_when_earnings_next_week(mock_next):
    today = date(2026, 5, 23)
    mock_next.return_value = date(2026, 5, 30)
    assert not is_in_earnings_window("AAPL", days_before=2, days_after=1, today=today)


@patch("app.shared.calendar_utils.get_next_earnings_date")
def test_not_in_window_when_no_data(mock_next):
    """No earnings data → don't punish. False = 'don't suppress'."""
    mock_next.return_value = None
    assert not is_in_earnings_window("OBSCURE", today=date(2026, 5, 23))


@patch("app.shared.calendar_utils.get_next_earnings_date")
def test_filter_splits_correctly(mock_next):
    today = date(2026, 5, 23)

    def fake(ticker):
        return {
            "EARN_SOON": date(2026, 5, 24),    # in window
            "EARN_FAR":  date(2026, 7, 30),    # out of window
            "NO_DATA":   None,                  # no data
        }.get(ticker)

    mock_next.side_effect = fake

    kept, suppressed = filter_out_earnings_window(
        ["EARN_SOON", "EARN_FAR", "NO_DATA"], today=today,
    )
    assert suppressed == ["EARN_SOON"]
    assert kept == ["EARN_FAR", "NO_DATA"]
