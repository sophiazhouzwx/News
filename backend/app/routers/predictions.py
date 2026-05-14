from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import DailyPrediction, PredictionItem, get_db

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
def prediction_accuracy(db: Session = Depends(get_db)):
    total = db.query(func.count(PredictionItem.id)).filter(
        PredictionItem.outcome.in_(["hit", "miss"])
    ).scalar()
    hits = db.query(func.count(PredictionItem.id)).filter(
        PredictionItem.outcome == "hit"
    ).scalar()
    return {
        "total_verified": total,
        "hits": hits,
        "accuracy_pct": round(hits / total * 100, 1) if total else None,
    }


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


def _prediction_to_dict(p: DailyPrediction, db: Session) -> dict:
    items = db.query(PredictionItem).filter(
        PredictionItem.prediction_id == p.id
    ).all()
    hits = sum(1 for i in items if i.outcome == "hit")
    verified = sum(1 for i in items if i.outcome in ("hit", "miss"))
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
    }


def _item_to_dict(i: PredictionItem) -> dict:
    return {
        "id": i.id,
        "ticker": i.ticker,
        "direction": i.direction,
        "timeframe_days": i.timeframe_days,
        "confidence_pct": i.confidence_pct,
        "thesis": i.thesis,
        "outcome": i.outcome,
        "price_at_prediction": i.price_at_prediction,
        "price_at_verification": i.price_at_verification,
        "actual_change_pct": i.actual_change_pct,
        "verified_at": i.verified_at.isoformat() if i.verified_at else None,
    }
