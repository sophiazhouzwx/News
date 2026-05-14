from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..config import TRACKED_PERSONALITIES
from ..database import PersonalitySpeech, get_db

router = APIRouter()

DISPLAY_WINDOW_DAYS = 7


@router.get("")
def list_speeches(
    personality: str = "",
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    cutoff = datetime.now(timezone.utc) - timedelta(days=DISPLAY_WINDOW_DAYS)
    query = (
        db.query(PersonalitySpeech)
        .filter(PersonalitySpeech.summary_en != "")
        .filter(PersonalitySpeech.pub_date >= cutoff)
    )
    if personality:
        query = query.filter(PersonalitySpeech.personality_name == personality)
    speeches = query.order_by(PersonalitySpeech.pub_date.desc()).offset(skip).limit(limit).all()
    return [_speech_to_dict(s) for s in speeches]


@router.get("/personalities")
def list_personalities():
    return [{"name": p["name"], "language": p["language"]} for p in TRACKED_PERSONALITIES]


@router.get("/{speech_id}")
def get_speech(speech_id: int, db: Session = Depends(get_db)):
    s = db.query(PersonalitySpeech).get(speech_id)
    if not s:
        return {"error": "Not found"}
    return _speech_to_dict(s)


@router.delete("/{speech_id}")
def delete_speech(speech_id: int, db: Session = Depends(get_db)):
    s = db.query(PersonalitySpeech).get(speech_id)
    if not s:
        return {"error": "Not found"}
    db.delete(s)
    db.commit()
    return {"status": "deleted"}


def _speech_to_dict(s: PersonalitySpeech) -> dict:
    return {
        "id": s.id,
        "personality_name": s.personality_name,
        "title": s.title,
        "video_url": s.video_url,
        "pub_date": s.pub_date.isoformat() if s.pub_date else None,
        "summary_en": s.summary_en,
        "summary_cn": s.summary_cn,
        "status": s.status,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }
