from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import Digest, get_db

router = APIRouter()


@router.get("")
def list_digests(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    digests = (
        db.query(Digest)
        .order_by(Digest.date.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [
        {
            "id": d.id,
            "date": d.date,
            "summary_en": d.summary_en[:300] + "..." if len(d.summary_en) > 300 else d.summary_en,
            "summary_cn": d.summary_cn[:300] + "..." if len(d.summary_cn) > 300 else d.summary_cn,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in digests
    ]


@router.get("/latest")
def get_latest_digest(db: Session = Depends(get_db)):
    d = db.query(Digest).order_by(Digest.date.desc()).first()
    if not d:
        raise HTTPException(status_code=404, detail="No digests found")
    return _digest_to_dict(d)


@router.get("/{digest_id}")
def get_digest(digest_id: int, db: Session = Depends(get_db)):
    d = db.query(Digest).get(digest_id)
    if not d:
        raise HTTPException(status_code=404, detail="Digest not found")
    return _digest_to_dict(d)


def _digest_to_dict(d: Digest) -> dict:
    return {
        "id": d.id,
        "date": d.date,
        "summary_en": d.summary_en,
        "summary_cn": d.summary_cn,
        "raw_articles_json": d.raw_articles_json,
        "podcast_episode_ids_json": d.podcast_episode_ids_json,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }
