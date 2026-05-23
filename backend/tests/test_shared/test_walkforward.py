"""Tests for the generic walk-forward harness."""

from __future__ import annotations

from datetime import date, timedelta

from app.shared.walkforward import walk_forward


def _date_range(start: date, n: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(n)]


def test_empty_dates_returns_zero_metrics():
    result = walk_forward(
        dates=[],
        fetch_train=lambda d: [],
        fit=lambda t: None,
        predict=lambda m, d: [],
        score=lambda p: [],
    )
    assert result["days"] == 0
    assert result["predictions"] == 0
    assert result["mean_score"] is None
    assert result["per_day"] == []


def test_skips_when_insufficient_train_data():
    """No fits happen below min_train_size; all days marked skipped."""
    result = walk_forward(
        dates=_date_range(date(2024, 1, 1), 5),
        fetch_train=lambda d: [1, 2],  # only 2 records — below min 30
        fit=lambda t: "model",
        predict=lambda m, d: [{"x": 1}],
        score=lambda p: [1.0],
        min_train_size=30,
    )
    assert result["predictions"] == 0
    assert all(r.get("skipped_reason") == "insufficient_train_data" for r in result["per_day"])


def test_happy_path_walks_and_accumulates():
    # Each call returns 200 train records → always above threshold
    fits_done: list[date] = []

    def fake_fit(train):
        return {"fit_count": len(fits_done)}

    def fake_predict(model, d):
        return [{"date": d.isoformat()}]

    def fake_score(preds):
        # Deterministic score per day = day-of-month
        return [float(p["date"][-2:]) for p in preds]

    dates = _date_range(date(2024, 1, 1), 5)

    # Wrap fit so we can count
    real_fit = fake_fit

    def counting_fit(t):
        fits_done.append(date.today())
        return real_fit(t)

    result = walk_forward(
        dates=dates,
        fetch_train=lambda d: list(range(50)),
        fit=counting_fit,
        predict=fake_predict,
        score=fake_score,
        min_train_size=10,
        refit_every_n_days=1,
    )

    assert result["days"] == 5
    assert result["predictions"] == 5
    # Refit every day → 5 fits
    assert len(fits_done) == 5
    # Scores 1, 2, 3, 4, 5 → mean 3.0
    assert result["mean_score"] == 3.0
    assert result["min_score"] == 1.0
    assert result["max_score"] == 5.0


def test_refit_cadence_respected():
    """With refit_every_n_days=3, fits happen on day 0, 3, 6, …"""
    fit_dates: list[date] = []

    def fit(t):
        fit_dates.append(date.today())
        return "m"

    walk_forward(
        dates=_date_range(date(2024, 1, 1), 10),
        fetch_train=lambda d: list(range(50)),
        fit=fit,
        predict=lambda m, d: [{"x": 1}],
        score=lambda p: [1.0],
        min_train_size=10,
        refit_every_n_days=3,
    )
    # day 0 (initial), day 3, day 6, day 9 → 4 fits
    assert len(fit_dates) == 4


def test_caught_fit_error_records_per_day():
    def bad_fit(t):
        raise ValueError("fit blew up")

    result = walk_forward(
        dates=_date_range(date(2024, 1, 1), 2),
        fetch_train=lambda d: list(range(50)),
        fit=bad_fit,
        predict=lambda m, d: [{"x": 1}],
        score=lambda p: [1.0],
        min_train_size=10,
    )
    assert result["predictions"] == 0
    assert all("error" in r and "fit:" in r["error"] for r in result["per_day"])


def test_caught_predict_error_does_not_kill_run():
    call_n = {"n": 0}

    def predict(model, d):
        call_n["n"] += 1
        if call_n["n"] == 2:
            raise RuntimeError("api timeout")
        return [{"d": d.isoformat()}]

    result = walk_forward(
        dates=_date_range(date(2024, 1, 1), 3),
        fetch_train=lambda d: list(range(50)),
        fit=lambda t: "m",
        predict=predict,
        score=lambda p: [1.0],
        min_train_size=10,
    )
    # Days 1 and 3 succeed, day 2 errors
    assert result["predictions"] == 2
    err_days = [r for r in result["per_day"] if "error" in r]
    assert len(err_days) == 1
    assert "predict:" in err_days[0]["error"]
