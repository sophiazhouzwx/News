import json
import logging
import ssl
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
from sqlalchemy.orm import Session

from ..config import TRACKED_PODCASTS
from ..database import PodcastEpisode
from ..utils.transcript import download_audio, transcribe_audio_with_timeout, cleanup_audio

logger = logging.getLogger(__name__)

# Max time (seconds) for downloading + transcribing a single episode
EPISODE_PROCESS_TIMEOUT = 300  # 5 minutes

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE
_handler = urllib.request.HTTPSHandler(context=_ssl_ctx)

ITUNES_LOOKUP_URL = "https://itunes.apple.com/lookup?id={apple_id}&entity=podcastEpisode&limit={limit}"


def _itunes_fetch_episodes(apple_id: int, limit: int = 15) -> list[dict[str, Any]]:
    """Fetch recent episodes via Apple iTunes Lookup API."""
    url = ITUNES_LOOKUP_URL.format(apple_id=apple_id, limit=limit)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=_ssl_ctx, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception:
        logger.exception("iTunes API failed for apple_id=%s", apple_id)
        return []

    episodes = []
    for r in data.get("results", []):
        if r.get("kind") != "podcast-episode":
            continue
        pub_date = None
        if r.get("releaseDate"):
            try:
                pub_date = datetime.fromisoformat(r["releaseDate"].replace("Z", "+00:00"))
            except Exception:
                pass
        episodes.append({
            "episode_guid": str(r.get("trackId", r.get("episodeUrl", ""))),
            "episode_title": r.get("trackName", "Untitled"),
            "pub_date": pub_date,
            "audio_url": r.get("episodeUrl", ""),
            "description": r.get("description", ""),
        })
    return episodes


def _parse_pub_date(entry: dict) -> datetime | None:
    raw = entry.get("published") or entry.get("updated")
    if raw:
        try:
            return parsedate_to_datetime(raw).astimezone(timezone.utc)
        except Exception:
            pass
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        try:
            return datetime(*parsed[:6], tzinfo=timezone.utc)
        except Exception:
            pass
    return None


def _get_audio_url(entry: dict) -> str:
    for link in entry.get("links", []):
        if link.get("type", "").startswith("audio/") or link.get("href", "").endswith(".mp3"):
            return link["href"]
    for enc in entry.get("enclosures", []):
        if enc.get("type", "").startswith("audio/") or enc.get("href", "").endswith(".mp3"):
            return enc["href"]
    return entry.get("link", "")


def poll_podcast_feed(podcast_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Fetch episodes: try iTunes API first, fall back to RSS."""
    apple_id = podcast_cfg.get("apple_podcast_id")
    if apple_id:
        episodes = _itunes_fetch_episodes(apple_id)
        if episodes:
            for ep in episodes:
                ep["podcast_name"] = podcast_cfg["name"]
            logger.info("iTunes API: got %d episodes for %s", len(episodes), podcast_cfg["name"])
            return episodes

    logger.info("Falling back to RSS for %s", podcast_cfg["name"])
    try:
        feed = feedparser.parse(podcast_cfg["rss_url"], handlers=[_handler])
    except Exception:
        logger.exception("Failed to parse podcast RSS: %s", podcast_cfg["name"])
        return []

    episodes = []
    for entry in feed.entries:
        guid = entry.get("id") or entry.get("guid") or entry.get("link", "")
        episodes.append({
            "podcast_name": podcast_cfg["name"],
            "episode_guid": guid,
            "episode_title": entry.get("title", "Untitled"),
            "pub_date": _parse_pub_date(entry),
            "audio_url": _get_audio_url(entry),
            "description": entry.get("summary", ""),
        })
    return episodes


def find_new_episodes(db: Session, podcast_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Return episodes that haven't been summarized yet, respecting the schedule strategy."""
    all_episodes = poll_podcast_feed(podcast_cfg)
    if not all_episodes:
        return []

    existing_guids = set(
        row[0] for row in
        db.query(PodcastEpisode.episode_guid)
        .filter(PodcastEpisode.podcast_name == podcast_cfg["name"])
        .all()
    )

    unseen = [ep for ep in all_episodes if ep["episode_guid"] not in existing_guids]

    schedule = podcast_cfg.get("schedule", "daily")
    if schedule == "daily":
        cutoff = datetime.now(timezone.utc) - timedelta(hours=28)
        recent = [
            ep for ep in unseen
            if ep["pub_date"] is None or ep["pub_date"] >= cutoff
        ]
        if recent:
            return recent
        if unseen:
            logger.info("No recent episodes for %s, falling back to latest unsummarized",
                        podcast_cfg["name"])
            return unseen[:1]
        return []
    else:
        return unseen[:1] if unseen else []


def _try_youtube_audio(episode_title: str, podcast_name: str) -> str | None:
    """Search YouTube for a podcast episode and download the audio."""
    search_query = f"{podcast_name} {episode_title}"
    logger.info("Searching YouTube for: %s", search_query[:60])
    try:
        result = subprocess.run(
            [
                "yt-dlp", "--no-check-certificates",
                "--flat-playlist", "--print", "%(id)s",
                f"ytsearch1:{search_query}",
            ],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None

        video_id = result.stdout.strip().split("\n")[0]
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        logger.info("Found YouTube match: %s", video_url)
        return download_audio(video_url)
    except Exception:
        logger.debug("YouTube audio fallback failed for: %s", episode_title[:40])
        return None


def _download_and_transcribe(episode: dict[str, Any], language: str) -> str | None:
    """Download audio and transcribe. Returns the transcript text or None."""
    audio_path = None
    try:
        logger.info("Downloading audio for: %s", episode["episode_title"])
        audio_path = download_audio(episode["audio_url"])
    except Exception:
        logger.warning("Direct audio download failed for: %s", episode["episode_title"])

    if audio_path is None:
        try:
            audio_path = _try_youtube_audio(episode["episode_title"], episode["podcast_name"])
        except Exception:
            logger.warning("YouTube fallback failed for: %s", episode["episode_title"])

    if audio_path:
        try:
            logger.info("Transcribing: %s", episode["episode_title"])
            return transcribe_audio_with_timeout(audio_path, language=language, timeout=240)
        except Exception:
            logger.exception("Transcription failed for: %s", episode["episode_title"])
            return None
        finally:
            cleanup_audio(audio_path)
    return None


def process_episode(db: Session, episode: dict[str, Any], language: str = "en") -> PodcastEpisode:
    """Download, transcribe, and store a podcast episode.
    Falls back to YouTube search, then episode description if audio is inaccessible.
    Timeout is handled internally by transcribe_audio_with_timeout() via multiprocessing.
    """
    existing = db.query(PodcastEpisode).filter(
        PodcastEpisode.episode_guid == episode["episode_guid"]
    ).first()
    if existing:
        logger.info("Episode already exists, skipping: %s", episode["episode_title"])
        return existing

    db_episode = PodcastEpisode(
        podcast_name=episode["podcast_name"],
        episode_guid=episode["episode_guid"],
        episode_title=episode["episode_title"],
        pub_date=episode["pub_date"],
        audio_url=episode.get("audio_url", ""),
    )
    db.add(db_episode)
    db.flush()

    transcript = None
    try:
        transcript = _download_and_transcribe(episode, language)
    except Exception:
        logger.exception("Failed to process episode: %s", episode["episode_title"])

    if transcript:
        db_episode.transcript = transcript
        db.commit()
    else:
        description = episode.get("description", "")
        if description and len(description) > 50:
            logger.info("Using episode description as source text for: %s", episode["episode_title"])
            db_episode.transcript = f"[Episode Description / Show Notes]\n\n{description}"
            db.commit()
        else:
            logger.warning("No audio or description available for: %s", episode["episode_title"])
            db.commit()

    return db_episode


def get_new_episodes_for_all_podcasts(db: Session) -> list[PodcastEpisode]:
    """Poll all tracked podcasts, process new episodes, return list of DB records needing summarization.

    Feed polling is parallelized (I/O-bound). Transcription is sequential
    (CPU-bound — running multiple Whisper processes simultaneously would OOM).
    """
    all_new: list[PodcastEpisode] = []

    # Phase 1: Poll all feeds in parallel (I/O-bound)
    feed_results: list[tuple[dict, list[dict]]] = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(find_new_episodes, db, cfg): cfg
            for cfg in TRACKED_PODCASTS
        }
        for future in as_completed(futures, timeout=60):
            cfg = futures[future]
            try:
                new_eps = future.result()
                if new_eps:
                    feed_results.append((cfg, new_eps))
            except Exception:
                logger.exception("Error polling podcast: %s", cfg["name"])

    # Phase 2: Process episodes sequentially (CPU-bound Whisper)
    for cfg, episodes in feed_results:
        for ep_data in episodes:
            try:
                db_ep = process_episode(db, ep_data, language=cfg["language"])
                if db_ep.transcript:
                    all_new.append(db_ep)
            except Exception:
                logger.exception("Error processing episode from: %s", cfg["name"])

    return all_new
