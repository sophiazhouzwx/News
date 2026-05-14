import logging
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..database import MediaSummary
from ..utils.transcript import download_audio, transcribe_audio, get_youtube_transcript, cleanup_audio
from .summarizer import summarize_media

logger = logging.getLogger(__name__)

YOUTUBE_PATTERN = re.compile(r"(youtube\.com|youtu\.be)")


def detect_media_type(url: str) -> str:
    if YOUTUBE_PATTERN.search(url):
        return "youtube"
    if any(ext in url.lower() for ext in [".mp3", ".m4a", ".wav", ".ogg"]):
        return "audio"
    return "podcast"


def process_media_url(db: Session, media_id: int) -> None:
    """Process a submitted media URL: transcribe and summarize."""
    media = db.query(MediaSummary).get(media_id)
    if not media:
        return

    media.status = "processing"
    db.commit()

    audio_path = None
    try:
        media.media_type = detect_media_type(media.url)

        transcript = None
        if media.media_type == "youtube":
            transcript = get_youtube_transcript(media.url)

        if not transcript:
            audio_path = download_audio(media.url)
            transcript = transcribe_audio(audio_path, language="en")

        media.transcript = transcript
        title = media.title or media.url
        result = summarize_media(title, transcript, media.url)
        media.summary_en = result["en"]
        media.summary_cn = result["cn"]
        media.status = "done"
        db.commit()

    except Exception as e:
        logger.exception("Failed to process media: %s", media.url)
        media.status = "error"
        media.error_message = str(e)[:500]
        db.commit()
    finally:
        if audio_path:
            cleanup_audio(audio_path)
