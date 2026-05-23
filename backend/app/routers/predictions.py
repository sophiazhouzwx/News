import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import DailyPrediction, ModelPerformance, PredictionItem, get_db

router = APIRouter()


@router.get("")
def list_predictions(skip: int = 0, limit: int = 30, db: Session = Depends(get_db)):
    predictions = (
        db.query(DailyPrediction)
        .order_by(DailyPrediction.date.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_prediction_to_dict(p, db) for p in predictions]


@router.get("/accuracy")
def prediction_accuracy(
    model_version: str | None = Query(None, description="Filter to a specific model version"),
    source: str | None = Query(None, description="Filter by source (news_discovery, quant_v1, ...)"),
    db: Session = Depends(get_db),
):
    q_total = db.query(func.count(PredictionItem.id)).filter(
        PredictionItem.outcome.in_(["hit", "miss"])
    )
    q_hits = db.query(func.count(PredictionItem.id)).filter(
        PredictionItem.outcome == "hit"
    )
    if model_version:
        q_total = q_total.filter(PredictionItem.model_version == model_version)
        q_hits = q_hits.filter(PredictionItem.model_version == model_version)
    if source:
        q_total = q_total.filter(PredictionItem.source == source)
        q_hits = q_hits.filter(PredictionItem.source == source)
    total = q_total.scalar() or 0
    hits = q_hits.scalar() or 0
    return {
        "model_version": model_version,
        "source": source,
        "total_verified": total,
        "hits": hits,
        "accuracy_pct": round(hits / total * 100, 1) if total else None,
    }


@router.get("/model-performance")
def model_performance(
    model_version: str | None = Query(None),
    limit: int = 90,
    db: Session = Depends(get_db),
):
    """Time-series of cumulative model accuracy snapshots."""
    q = db.query(ModelPerformance).order_by(ModelPerformance.created_at.desc())
    if model_version:
        q = q.filter(ModelPerformance.model_version == model_version)
    rows = q.limit(limit).all()
    return [
        {
            "id": r.id,
            "model_version": r.model_version,
            "date": r.date,
            "total_predictions": r.total_predictions,
            "hits": r.hits,
            "accuracy_pct": r.accuracy_pct,
            "avg_confidence": r.avg_confidence,
            "avg_actual_change": r.avg_actual_change,
            "factor_weights": _safe_load_json(r.factor_weights_json),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/backtest")
def run_backtest(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    model_version: str = Query("quant_v1"),
    db: Session = Depends(get_db),
):
    from ..services.quant_models import backtest_model

    try:
        datetime.strptime(start, "%Y-%m-%d")
        datetime.strptime(end, "%Y-%m-%d")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Bad date: {e}")
    return backtest_model(db, start, end, model_version)


@router.get("/latest")
def get_latest_prediction(db: Session = Depends(get_db)):
    p = db.query(DailyPrediction).order_by(DailyPrediction.date.desc()).first()
    if not p:
        raise HTTPException(status_code=404, detail="No predictions found")
    return _prediction_to_dict(p, db)


@router.get("/{prediction_id}")
def get_prediction(prediction_id: int, db: Session = Depends(get_db)):
    p = db.query(DailyPrediction).get(prediction_id)
    if not p:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return _prediction_to_dict(p, db)


@router.get("/items/{item_id}/factors")
def get_item_factors(item_id: int, db: Session = Depends(get_db)):
    """Return the full factor / signal breakdown for a single quant prediction."""
    i = db.query(PredictionItem).get(item_id)
    if not i:
        raise HTTPException(status_code=404, detail="Item not found")
    return {
        "id": i.id,
        "ticker": i.ticker,
        "direction": i.direction,
        "model_version": i.model_version,
        "composite_score": i.composite_score,
        "factors": {
            "momentum_score": i.momentum_score,
            "value_score": i.value_score,
            "volatility_score": i.volatility_score,
            "quality_score": i.quality_score,
            "sentiment_score": i.sentiment_score,
        },
        "technical_indicators": {
            "rsi_at_prediction": i.rsi_at_prediction,
            "macd_signal_at_prediction": i.macd_signal_at_prediction,
        },
        "predicted_change_pct": i.predicted_change_pct,
        "confidence_interval": [i.confidence_interval_low, i.confidence_interval_high],
        "threshold_pct": i.threshold_pct,
        "actual_change_pct": i.actual_change_pct,
        "outcome": i.outcome,
    }


def _prediction_to_dict(p: DailyPrediction, db: Session) -> dict:
    items = db.query(PredictionItem).filter(
        PredictionItem.prediction_id == p.id
    ).all()
    hits = sum(1 for i in items if i.outcome == "hit")
    verified = sum(1 for i in items if i.outcome in ("hit", "miss"))
    by_source: dict[str, dict] = {}
    for i in items:
        bucket = by_source.setdefault(i.source or "news_discovery", {"hits": 0, "verified": 0, "total": 0})
        bucket["total"] += 1
        if i.outcome == "hit":
            bucket["hits"] += 1
        if i.outcome in ("hit", "miss"):
            bucket["verified"] += 1
    for src, b in by_source.items():
        b["accuracy_pct"] = round(b["hits"] / b["verified"] * 100) if b["verified"] else None
    return {
        "id": p.id,
        "date": p.date,
        "prediction_en": p.prediction_en,
        "prediction_cn": p.prediction_cn,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "items": [_item_to_dict(i) for i in items],
        "accuracy": {
            "hits": hits,
            "verified": verified,
            "pct": round(hits / verified * 100) if verified else None,
        },
        "accuracy_by_source": by_source,
    }


def _item_to_dict(i: PredictionItem) -> dict:
    return {
        "id": i.id,
        "ticker": i.ticker,
        "direction": i.direction,
        "timeframe_days": i.timeframe_days,
        "confidence_pct": i.confidence_pct,
        "thesis": i.thesis,
        "source": i.source,
        "outcome": i.outcome,
        "price_at_prediction": i.price_at_prediction,
        "price_at_verification": i.price_at_verification,
        "actual_change_pct": i.actual_change_pct,
        "verified_at": i.verified_at.isoformat() if i.verified_at else None,
        # Quant metadata (may be null for legacy LLM items)
        "model_version": i.model_version or None,
        "composite_score": i.composite_score,
        "momentum_score": i.momentum_score,
        "value_score": i.value_score,
        "volatility_score": i.volatility_score,
        "quality_score": i.quality_score,
        "sentiment_score": i.sentiment_score,
        "rsi_at_prediction": i.rsi_at_prediction,
        "macd_signal_at_prediction": i.macd_signal_at_prediction or None,
        "predicted_change_pct": i.predicted_change_pct,
        "confidence_interval_low": i.confidence_interval_low,
        "confidence_interval_high": i.confidence_interval_high,
        "threshold_pct": i.threshold_pct,
    }


def _safe_load_json(blob: str | None) -> dict:
    if not blob:
        return {}
    try:
        return json.loads(blob)
    except (ValueError, TypeError):
        return {}
