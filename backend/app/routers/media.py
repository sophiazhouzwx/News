import threading

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import MediaSummary, get_db, get_session_factory
from ..services.media_processor import process_media_url

router = APIRouter()


class MediaRequest(BaseModel):
    url: str
    title: str = ""


@router.post("/summarize")
def submit_media(req: MediaRequest, db: Session = Depends(get_db)):
    media = MediaSummary(url=req.url, title=req.title, status="pending")
    db.add(media)
    db.commit()
    db.refresh(media)

    def _process():
        factory = get_session_factory()
        session = factory()
        try:
            process_media_url(session, media.id)
        finally:
            session.close()

    thread = threading.Thread(target=_process, daemon=True)
    thread.start()

    return {
        "id": media.id,
        "status": media.status,
        "message": "Processing started. Poll GET /api/media/{id} for results.",
    }


@router.get("")
def list_media(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    items = (
        db.query(MediaSummary)
        .order_by(MediaSummary.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_media_to_dict(m) for m in items]


@router.get("/{media_id}")
def get_media(media_id: int, db: Session = Depends(get_db)):
    m = db.query(MediaSummary).get(media_id)
    if not m:
        raise HTTPException(status_code=404, detail="Media summary not found")
    return _media_to_dict(m)


@router.delete("/{media_id}")
def delete_media(media_id: int, db: Session = Depends(get_db)):
    m = db.query(MediaSummary).get(media_id)
    if not m:
        raise HTTPException(status_code=404, detail="Media summary not found")
    db.delete(m)
    db.commit()
    return {"status": "deleted"}


def _media_to_dict(m: MediaSummary) -> dict:
    return {
        "id": m.id,
        "url": m.url,
        "title": m.title,
        "media_type": m.media_type,
        "summary_en": m.summary_en,
        "summary_cn": m.summary_cn,
        "status": m.status,
        "error_message": m.error_message,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }
