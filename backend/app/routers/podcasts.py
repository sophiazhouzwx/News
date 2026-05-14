from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..config import TRACKED_PODCASTS
from ..database import PodcastEpisode, get_db

router = APIRouter()


@router.get("")
def list_podcasts(db: Session = Depends(get_db)):
    """List all tracked podcasts with episode counts and latest episode info."""
    result = []
    for pc in TRACKED_PODCASTS:
        count = (
            db.query(func.count(PodcastEpisode.id))
            .filter(
                PodcastEpisode.podcast_name == pc["name"],
                PodcastEpisode.summarized_at.isnot(None),
            )
            .scalar()
        )
        latest = (
            db.query(PodcastEpisode)
            .filter(
                PodcastEpisode.podcast_name == pc["name"],
                PodcastEpisode.summarized_at.isnot(None),
            )
            .order_by(PodcastEpisode.pub_date.desc())
            .first()
        )
        result.append({
            "name": pc["name"],
            "language": pc["language"],
            "schedule": pc["schedule"],
            "episode_count": count,
            "latest_episode": _episode_brief(latest) if latest else None,
        })
    return result


@router.get("/{podcast_name}/episodes")
def list_episodes(
    podcast_name: str,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    episodes = (
        db.query(PodcastEpisode)
        .filter(
            PodcastEpisode.podcast_name == podcast_name,
            PodcastEpisode.summarized_at.isnot(None),
        )
        .order_by(PodcastEpisode.pub_date.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_episode_to_dict(ep) for ep in episodes]


@router.get("/episodes/{episode_id}")
def get_episode(episode_id: int, db: Session = Depends(get_db)):
    ep = db.query(PodcastEpisode).get(episode_id)
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    return _episode_to_dict(ep)


@router.delete("/episodes/{episode_id}")
def delete_episode(episode_id: int, db: Session = Depends(get_db)):
    ep = db.query(PodcastEpisode).get(episode_id)
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    db.delete(ep)
    db.commit()
    return {"status": "deleted"}


def _episode_brief(ep: PodcastEpisode) -> dict:
    return {
        "id": ep.id,
        "title": ep.episode_title,
        "pub_date": ep.pub_date.isoformat() if ep.pub_date else None,
    }


def _episode_to_dict(ep: PodcastEpisode) -> dict:
    return {
        "id": ep.id,
        "podcast_name": ep.podcast_name,
        "episode_title": ep.episode_title,
        "pub_date": ep.pub_date.isoformat() if ep.pub_date else None,
        "audio_url": ep.audio_url,
        "summary_en": ep.summary_en,
        "summary_cn": ep.summary_cn,
        "summarized_at": ep.summarized_at.isoformat() if ep.summarized_at else None,
    }
