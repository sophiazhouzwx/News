"""Generic walk-forward backtest harness.

Knows nothing about stocks, news, predictions, or this codebase. You give
it 4 callables and a list of dates; it walks chronologically and reports
out-of-sample performance.

The whole point of walking forward (rather than fitting once on everything
and scoring on the same set) is to avoid information leakage: at each
prediction date, the model has ONLY seen training data observable as of
that date. This is the standard way to validate any time-series predictor.

Usage shape:

    metrics = walk_forward(
        dates=[date(2024,1,2), date(2024,1,3), ...],
        fetch_train=lambda cutoff: rows_with_outcome_before(cutoff),
        fit=lambda train_rows: fit_my_model(train_rows),
        predict=lambda model, d: [{"id": ..., "actual": ..., "pred": ...}, ...],
        score=lambda preds: [pred_was_hit(p) for p in preds],
        min_train_size=30,
        refit_every_n_days=7,
    )

The forecaster project (regression on OHLCV) uses the same harness:
- fetch_train returns parquet rows older than cutoff
- fit trains a LightGBM regressor
- predict yields {"actual_close": x, "pred_close": y, ...}
- score returns squared errors

No code changes needed — the harness doesn't care what the model is.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Callable

FetchTrainFn = Callable[[date], list[Any]]
FitFn = Callable[[list[Any]], Any]
PredictFn = Callable[[Any, date], list[dict]]
ScoreFn = Callable[[list[dict]], list[float]]


def walk_forward(
    dates: list[date],
    *,
    fetch_train: FetchTrainFn,
    fit: FitFn,
    predict: PredictFn,
    score: ScoreFn,
    min_train_size: int = 30,
    refit_every_n_days: int = 1,
) -> dict[str, Any]:
    """Walk through ``dates`` in order. For each date:

    1. Call ``fetch_train(date)`` to get training data observable BEFORE that date.
    2. If we haven't fit yet, OR refit_every_n_days has elapsed since the
       last fit, AND we have at least ``min_train_size`` records → refit.
    3. Call ``predict(model, date)`` → list of prediction dicts.
    4. Call ``score(predictions)`` → list of per-prediction floats.

    Returns aggregate metrics + a per-day breakdown. Exceptions inside
    ``fit``/``predict``/``score`` are caught and recorded per-day so one
    bad day doesn't abort the whole backtest.
    """
    if not dates:
        return {
            "days": 0, "predictions": 0, "mean_score": None,
            "min_score": None, "max_score": None, "per_day": [],
        }

    model: Any | None = None
    last_fit_date: date | None = None
    per_day: list[dict] = []
    all_scores: list[float] = []
    total_preds = 0

    for d in dates:
        train_records = fetch_train(d)
        n_train = len(train_records)

        # Refit if we don't have a model yet OR enough days passed AND we have data
        should_refit = (
            n_train >= min_train_size
            and (
                model is None
                or last_fit_date is None
                or (d - last_fit_date).days >= refit_every_n_days
            )
        )
        if should_refit:
            try:
                model = fit(train_records)
                last_fit_date = d
            except Exception as exc:
                per_day.append({
                    "date": d.isoformat(),
                    "n_train": n_train,
                    "predictions": 0,
                    "scores": [],
                    "error": f"fit: {type(exc).__name__}: {exc}",
                })
                continue

        if model is None:
            per_day.append({
                "date": d.isoformat(),
                "n_train": n_train,
                "predictions": 0,
                "scores": [],
                "skipped_reason": "insufficient_train_data",
            })
            continue

        try:
            preds = predict(model, d)
        except Exception as exc:
            per_day.append({
                "date": d.isoformat(),
                "n_train": n_train,
                "predictions": 0,
                "scores": [],
                "error": f"predict: {type(exc).__name__}: {exc}",
            })
            continue

        if not preds:
            per_day.append({
                "date": d.isoformat(),
                "n_train": n_train,
                "predictions": 0,
                "scores": [],
                "skipped_reason": "no_predictions",
            })
            continue

        try:
            scores = score(preds)
        except Exception as exc:
            per_day.append({
                "date": d.isoformat(),
                "n_train": n_train,
                "predictions": len(preds),
                "scores": [],
                "error": f"score: {type(exc).__name__}: {exc}",
            })
            continue

        all_scores.extend(scores)
        total_preds += len(preds)
        per_day.append({
            "date": d.isoformat(),
            "n_train": n_train,
            "predictions": len(preds),
            "scores": scores,
            "mean_score": (sum(scores) / len(scores)) if scores else None,
            "refit": d == last_fit_date,
        })

    return {
        "days": len(dates),
        "predictions": total_preds,
        "mean_score": (sum(all_scores) / len(all_scores)) if all_scores else None,
        "min_score": min(all_scores) if all_scores else None,
        "max_score": max(all_scores) if all_scores else None,
        "per_day": per_day,
    }
