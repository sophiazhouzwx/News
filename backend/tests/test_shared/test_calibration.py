"""Tests for the calibration helpers."""

from __future__ import annotations

import pytest

from app.shared.calibration import (
    DEFAULT_BUCKETS,
    brier_score,
    bucket_for,
    calibration_curve,
    shrunk_confidence,
)


# ---------------------------------------------------------------------------
# bucket_for
# ---------------------------------------------------------------------------
def test_bucket_for_basic():
    assert bucket_for(0) == "0-9"
    assert bucket_for(55) == "50-59"
    assert bucket_for(89.5) == "80-89"
    assert bucket_for(95) == "90-100"
    assert bucket_for(100) == "90-100"


def test_bucket_for_clamps_out_of_range():
    assert bucket_for(-5) == "0-9"
    assert bucket_for(150) == "90-100"


# ---------------------------------------------------------------------------
# calibration_curve
# ---------------------------------------------------------------------------
def test_curve_perfectly_calibrated():
    # 10 items in the 80-89 bucket, 8 hits → 80% observed vs 84.5% midpoint
    items = [{"confidence_pct": 85, "outcome": "hit"} for _ in range(8)] + [
        {"confidence_pct": 85, "outcome": "miss"} for _ in range(2)
    ]
    curve = calibration_curve(items)
    bucket = next(r for r in curve if r["bucket"] == "80-89")
    assert bucket["n"] == 10
    assert bucket["hits"] == 8
    assert bucket["observed_hit_rate_pct"] == 80.0
    assert bucket["gap_pct"] == -4.5  # slightly overconfident


def test_curve_overconfident():
    # All 20 items claim 90+%, but only half hit → big negative gap
    items = [{"confidence_pct": 95, "outcome": "hit"} for _ in range(10)] + [
        {"confidence_pct": 95, "outcome": "miss"} for _ in range(10)
    ]
    curve = calibration_curve(items)
    bucket = next(r for r in curve if r["bucket"] == "90-100")
    assert bucket["observed_hit_rate_pct"] == 50.0
    # gap = observed - claimed_midpoint = 50 - 95 = -45
    assert bucket["gap_pct"] == -45.0


def test_curve_handles_empty_buckets():
    items = [{"confidence_pct": 55, "outcome": "hit"}]
    curve = calibration_curve(items)
    empty = next(r for r in curve if r["bucket"] == "0-9")
    assert empty["n"] == 0
    assert empty["observed_hit_rate_pct"] is None
    assert empty["gap_pct"] is None


def test_curve_skips_invalid_rows():
    items = [
        {"confidence_pct": None, "outcome": "hit"},
        {"confidence_pct": 50, "outcome": None},
        {"confidence_pct": "not-a-number", "outcome": "hit"},
        {"confidence_pct": 55, "outcome": "hit"},
    ]
    curve = calibration_curve(items)
    bucket = next(r for r in curve if r["bucket"] == "50-59")
    assert bucket["n"] == 1
    assert bucket["hits"] == 1


# ---------------------------------------------------------------------------
# brier_score
# ---------------------------------------------------------------------------
def test_brier_perfect():
    items = [{"confidence_pct": 100, "outcome": "hit"} for _ in range(5)] + [
        {"confidence_pct": 0, "outcome": "miss"} for _ in range(5)
    ]
    assert brier_score(items) == 0.0


def test_brier_random_50_50_predictor():
    items = [{"confidence_pct": 50, "outcome": "hit"} for _ in range(5)] + [
        {"confidence_pct": 50, "outcome": "miss"} for _ in range(5)
    ]
    # p=0.5, y=1: (0.5)^2 = 0.25; p=0.5, y=0: (0.5)^2 = 0.25
    assert brier_score(items) == 0.25


def test_brier_empty():
    assert brier_score([]) is None


# ---------------------------------------------------------------------------
# shrunk_confidence
# ---------------------------------------------------------------------------
def test_shrunk_no_data_returns_raw():
    items = [{"confidence_pct": 95, "outcome": "miss"}]  # n=1 in 90-100
    curve = calibration_curve(items)
    # < min_bucket_n (default 10) → no shrinkage
    assert shrunk_confidence(95, curve) == 95.0


def test_shrunk_full_data_returns_observed():
    # 30 items at 90% confidence, only 10 hit → 33% observed
    items = [{"confidence_pct": 95, "outcome": "hit"} for _ in range(10)] + [
        {"confidence_pct": 95, "outcome": "miss"} for _ in range(20)
    ]
    curve = calibration_curve(items)
    # n=30, min_bucket_n=10 → weight = min(1, 30/30) = 1.0 → returns observed
    shrunk = shrunk_confidence(95, curve)
    # observed_hit_rate_pct rounds to 33.3
    assert abs(shrunk - 33.3) < 0.1


def test_shrunk_partial_data_blends():
    # n=10, weight = min(1, 10/30) = 0.333
    items = [{"confidence_pct": 95, "outcome": "hit"} for _ in range(5)] + [
        {"confidence_pct": 95, "outcome": "miss"} for _ in range(5)
    ]
    curve = calibration_curve(items)
    # observed=50, raw=95, blended ≈ 95 * 0.667 + 50 * 0.333 ≈ 80.0
    shrunk = shrunk_confidence(95, curve)
    assert 75 < shrunk < 85
