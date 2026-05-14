from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import ArticleFeedback, get_db

router = APIRouter()


class FeedbackRequest(BaseModel):
    digest_id: int
    article_title: str
    helpful: bool


@router.post("")
def submit_feedback(req: FeedbackRequest, db: Session = Depends(get_db)):
    existing = (
        db.query(ArticleFeedback)
        .filter(
            ArticleFeedback.digest_id == req.digest_id,
            ArticleFeedback.article_title == req.article_title,
        )
        .first()
    )
    if existing:
        existing.helpful = req.helpful
    else:
        db.add(ArticleFeedback(
            digest_id=req.digest_id,
            article_title=req.article_title,
            helpful=req.helpful,
        ))
    db.commit()
    return {"status": "ok"}


@router.get("")
def list_feedback(digest_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(ArticleFeedback)
    if digest_id is not None:
        query = query.filter(ArticleFeedback.digest_id == digest_id)
    rows = query.order_by(ArticleFeedback.created_at.desc()).limit(200).all()
    return [
        {
            "id": r.id,
            "digest_id": r.digest_id,
            "article_title": r.article_title,
            "helpful": r.helpful,
        }
        for r in rows
    ]


@router.get("/summary")
def feedback_summary(db: Session = Depends(get_db)):
    """Aggregate feedback stats for learning."""
    helpful_count = db.query(func.count(ArticleFeedback.id)).filter(ArticleFeedback.helpful == True).scalar()
    unhelpful_count = db.query(func.count(ArticleFeedback.id)).filter(ArticleFeedback.helpful == False).scalar()

    helpful_titles = [
        r[0] for r in
        db.query(ArticleFeedback.article_title)
        .filter(ArticleFeedback.helpful == True)
        .order_by(ArticleFeedback.created_at.desc())
        .limit(30)
        .all()
    ]
    unhelpful_titles = [
        r[0] for r in
        db.query(ArticleFeedback.article_title)
        .filter(ArticleFeedback.helpful == False)
        .order_by(ArticleFeedback.created_at.desc())
        .limit(30)
        .all()
    ]

    return {
        "total_helpful": helpful_count,
        "total_unhelpful": unhelpful_count,
        "recent_helpful_titles": helpful_titles,
        "recent_unhelpful_titles": unhelpful_titles,
    }
