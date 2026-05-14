import logging
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..config import TRACKED_PERSONALITIES
from ..database import PersonalitySpeech
from ..utils.transcript import download_audio, transcribe_audio_with_timeout, cleanup_audio, get_youtube_transcript

logger = logging.getLogger(__name__)

LOOKBACK_DAYS = 7
SPEECH_PROCESS_TIMEOUT = 300  # 5 minutes per speech


def _get_upload_date(video_id: str) -> datetime | None:
    """Fetch the actual upload date for a single video."""
    try:
        result = subprocess.run(
            [
                "yt-dlp", "--no-check-certificates", "--skip-download",
                "--print", "%(upload_date)s",
                f"https://www.youtube.com/watch?v={video_id}",
            ],
            capture_output=True, text=True, timeout=30,
        )
        date_str = result.stdout.strip()
        if date_str and date_str != "NA":
            return datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=timezone.utc)
    except Exception:
        logger.debug("Could not fetch upload date for %s", video_id)
    return None


def _youtube_search(query: str, max_results: int = 3) -> list[dict[str, Any]]:
    """Search YouTube and return video metadata with accurate upload dates."""
    try:
        result = subprocess.run(
            [
                "yt-dlp", "--no-check-certificates",
                "--flat-playlist",
                "--print", "%(id)s\t%(title)s",
                f"ytsearch{max_results}:{query}",
            ],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return []

        videos = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t", 1)
            if len(parts) < 2:
                continue
            vid_id, title = parts
            pub_date = _get_upload_date(vid_id)
            videos.append({
                "video_id": vid_id,
                "title": title,
                "pub_date": pub_date,
                "video_url": f"https://www.youtube.com/watch?v={vid_id}",
            })
        return videos
    except Exception:
        logger.exception("YouTube search failed for: %s", query)
        return []


SPAM_KEYWORDS = [
    "live", "reaction", "#shorts", "shorts", "compilation", "fan made",
    "parody", "meme", "funny", "deepfake", "ai generated", "ai voice",
    "motivational", "sigma", "grindset", "edit", "remix",
]


def _looks_authentic(title: str, personality_name: str) -> bool:
    """Filter out fan compilations, reaction videos, and AI-generated fakes."""
    t = title.lower()
    name_lower = personality_name.lower()
    if name_lower not in t:
        return False
    for kw in SPAM_KEYWORDS:
        if kw in t:
            return False
    if sum(c == '|' or c == '🔴' or c == '🚨' for c in title) > 1:
        return False
    return True


def _dedup_by_title(candidates: list[dict[str, Any]], existing_titles: set[str]) -> list[dict[str, Any]]:
    """Remove near-duplicate titles (same video re-uploaded by different channels)."""
    from rapidfuzz import fuzz
    unique: list[dict[str, Any]] = []
    seen_titles: list[str] = list(existing_titles)
    for v in candidates:
        t = v["title"].lower().strip()
        is_dup = False
        for prev in seen_titles:
            if fuzz.token_sort_ratio(t, prev.lower()) > 80:
                is_dup = True
                break
        if not is_dup:
            unique.append(v)
            seen_titles.append(t)
    return unique


def find_new_speeches(db: Session, personality: dict[str, Any]) -> list[dict[str, Any]]:
    """Search YouTube for recent speeches/interviews by a personality.
    Returns at most 1 video per run to avoid noise.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    existing_ids = set(
        row[0] for row in
        db.query(PersonalitySpeech.video_id)
        .filter(PersonalitySpeech.personality_name == personality["name"])
        .all()
    )
    existing_titles = set(
        row[0] for row in
        db.query(PersonalitySpeech.title)
        .filter(PersonalitySpeech.personality_name == personality["name"])
        .all()
    )

    candidates = []
    for query in personality["youtube_search_queries"]:
        results = _youtube_search(query, max_results=3)
        for v in results:
            if v["video_id"] in existing_ids:
                continue
            if v["pub_date"] and v["pub_date"] < cutoff:
                continue
            if not _looks_authentic(v["title"], personality["name"]):
                logger.info("Skipping non-authentic: %s", v["title"][:60])
                continue
            candidates.append(v)
            existing_ids.add(v["video_id"])

    candidates = _dedup_by_title(candidates, existing_titles)
    return candidates[:1]


def _transcribe_speech(video: dict[str, Any], language: str) -> str | None:
    """Get transcript for a speech. Returns transcript text or None."""
    transcript = get_youtube_transcript(video["video_url"])
    if transcript:
        return transcript

    audio_path = None
    try:
        logger.info("Downloading audio for speech: %s", video["title"][:50])
        audio_path = download_audio(video["video_url"])
        logger.info("Transcribing speech: %s", video["title"][:50])
        return transcribe_audio_with_timeout(audio_path, language=language, timeout=240)
    except Exception:
        logger.exception("Failed to process speech: %s", video["title"][:50])
        return None
    finally:
        if audio_path:
            cleanup_audio(audio_path)


def process_speech(db: Session, video: dict[str, Any], personality: dict[str, Any]) -> PersonalitySpeech | None:
    """Download, transcribe, and store a personality speech/interview.
    Timeout is handled internally by transcribe_audio_with_timeout() via multiprocessing.
    """
    record = PersonalitySpeech(
        personality_name=personality["name"],
        video_id=video["video_id"],
        title=video["title"],
        video_url=video["video_url"],
        pub_date=video["pub_date"],
        status="processing",
    )
    db.add(record)
    db.flush()

    transcript = None
    try:
        transcript = _transcribe_speech(video, personality["language"])
    except Exception:
        logger.exception("Unexpected error processing speech: %s", video["title"][:50])

    if transcript:
        record.transcript = transcript
        record.status = "transcribed"
        db.commit()
        return record
    else:
        record.status = "error"
        db.commit()
        return None


def get_new_speeches_for_all_personalities(db: Session) -> list[PersonalitySpeech]:
    """Search YouTube for all tracked personalities, process new speeches."""
    all_new: list[PersonalitySpeech] = []
    for personality in TRACKED_PERSONALITIES:
        try:
            new_videos = find_new_speeches(db, personality)
            logger.info("Found %d new videos for %s", len(new_videos), personality["name"])
            for video in new_videos:
                record = process_speech(db, video, personality)
                if record and record.transcript:
                    all_new.append(record)
        except Exception:
            logger.exception("Error processing personality: %s", personality["name"])
    return all_new
