import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import PushSubscription, get_db

router = APIRouter()


class SubscriptionRequest(BaseModel):
    endpoint: str
    keys: dict


@router.get("/vapid-public-key")
def get_vapid_key():
    settings = get_settings()
    if not settings.vapid_public_key:
        raise HTTPException(status_code=503, detail="VAPID keys not configured")
    return {"public_key": settings.vapid_public_key}


@router.post("/subscribe")
def subscribe(req: SubscriptionRequest, db: Session = Depends(get_db)):
    existing = db.query(PushSubscription).filter(
        PushSubscription.endpoint == req.endpoint
    ).first()
    if existing:
        existing.keys_json = json.dumps(req.keys)
        db.commit()
        return {"status": "updated"}

    sub = PushSubscription(endpoint=req.endpoint, keys_json=json.dumps(req.keys))
    db.add(sub)
    db.commit()
    return {"status": "subscribed"}


@router.delete("/subscribe")
def unsubscribe(req: SubscriptionRequest, db: Session = Depends(get_db)):
    sub = db.query(PushSubscription).filter(
        PushSubscription.endpoint == req.endpoint
    ).first()
    if sub:
        db.delete(sub)
        db.commit()
    return {"status": "unsubscribed"}
