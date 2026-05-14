import threading

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import TRACKED_REDNOTE_ACCOUNTS
from ..database import LivestreamSummary, get_db, get_session_factory
from ..services.livestream_tracker import process_manual_url
from ..services.summarizer import summarize_livestream

router = APIRouter()


class LivestreamRequest(BaseModel):
    url: str
    title: str = ""


@router.get("")
def list_livestreams(
    account: str = "",
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    query = db.query(LivestreamSummary).filter(
        LivestreamSummary.status == "done"
    )
    if account:
        query = query.filter(LivestreamSummary.account_name == account)
    items = (
        query.order_by(LivestreamSummary.pub_date.desc().nullslast(), LivestreamSummary.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_ls_to_dict(ls) for ls in items]


@router.get("/accounts")
def list_accounts():
    return [
        {"name": a["name"], "language": a["language"]}
        for a in TRACKED_REDNOTE_ACCOUNTS
    ]


@router.get("/{ls_id}")
def get_livestream(ls_id: int, db: Session = Depends(get_db)):
    ls = db.query(LivestreamSummary).get(ls_id)
    if not ls:
        raise HTTPException(status_code=404, detail="Livestream summary not found")
    return _ls_to_dict(ls)


@router.post("/summarize")
def submit_livestream_url(req: LivestreamRequest, db: Session = Depends(get_db)):
    """Manually submit a Red Note livestream replay URL for summarization."""
    ls = LivestreamSummary(
        account_name="manual",
        post_id=req.url,
        title=req.title or req.url,
        post_url=req.url,
        video_url=req.url,
        status="pending",
    )
    db.add(ls)
    db.commit()
    db.refresh(ls)

    def _process():
        factory = get_session_factory()
        session = factory()
        try:
            record = session.query(LivestreamSummary).get(ls.id)
            if not record:
                return
            record.status = "processing"
            session.commit()

            from ..utils.transcript import download_audio, transcribe_audio, cleanup_audio
            audio_path = None
            try:
                audio_path = download_audio(req.url)
                transcript = transcribe_audio(audio_path, language="cn")
                record.transcript = transcript

                result = summarize_livestream(record.title, transcript, language="cn")
                record.summary_en = result["en"]
                record.summary_cn = result["cn"]
                record.status = "done"
                session.commit()
            except Exception as e:
                record.status = "error"
                record.error_message = str(e)[:500]
                session.commit()
            finally:
                if audio_path:
                    cleanup_audio(audio_path)
        finally:
            session.close()

    thread = threading.Thread(target=_process, daemon=True)
    thread.start()

    return {
        "id": ls.id,
        "status": "pending",
        "message": "Processing started. Poll GET /api/livestreams/{id} for results.",
    }


def _ls_to_dict(ls: LivestreamSummary) -> dict:
    return {
        "id": ls.id,
        "account_name": ls.account_name,
        "post_id": ls.post_id,
        "title": ls.title,
        "post_url": ls.post_url,
        "pub_date": ls.pub_date.isoformat() if ls.pub_date else None,
        "summary_en": ls.summary_en,
        "summary_cn": ls.summary_cn,
        "status": ls.status,
        "error_message": ls.error_message,
        "created_at": ls.created_at.isoformat() if ls.created_at else None,
    }
