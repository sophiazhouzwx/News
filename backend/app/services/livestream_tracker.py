import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
from sqlalchemy.orm import Session

from ..config import TRACKED_REDNOTE_ACCOUNTS, get_settings
from ..database import LivestreamSummary
from ..utils.transcript import download_audio, transcribe_audio_with_timeout, cleanup_audio

logger = logging.getLogger(__name__)

XHS_VIDEO_URL_PATTERN = re.compile(r"xiaohongshu\.com/explore/([a-f0-9]+)")
XHS_DISCOVERY_PATTERN = re.compile(r"xiaohongshu\.com/discovery/item/([a-f0-9]+)")


def _build_rss_url(account: dict[str, Any]) -> str:
    settings = get_settings()
    path = account["rss_path"].format(user_id=account["user_id"])
    return f"{settings.rsshub_base_url}{path}"


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


def _extract_post_id(entry: dict) -> str:
    """Extract the Xiaohongshu post ID from the entry link or guid."""
    link = entry.get("link", "")
    for pattern in (XHS_VIDEO_URL_PATTERN, XHS_DISCOVERY_PATTERN):
        m = pattern.search(link)
        if m:
            return m.group(1)
    guid = entry.get("id") or entry.get("guid") or link
    return guid


def _is_video_post(entry: dict) -> bool:
    """Heuristic: check if the RSS entry looks like a video/livestream replay."""
    content = (
        entry.get("summary", "")
        + entry.get("title", "")
        + str(entry.get("links", []))
    ).lower()
    video_signals = ["video", "mp4", "直播", "回放", "livestream", "replay"]
    if any(sig in content for sig in video_signals):
        return True
    for link in entry.get("links", []):
        href = link.get("href", "").lower()
        ltype = link.get("type", "").lower()
        if "video" in ltype or href.endswith(".mp4"):
            return True
    return True  # treat all posts as potential video for Xiaohongshu


def _get_video_url(entry: dict) -> str:
    """Extract video URL from entry, or fall back to the post link (yt-dlp handles it)."""
    for link in entry.get("links", []):
        href = link.get("href", "")
        ltype = link.get("type", "").lower()
        if "video" in ltype or href.endswith(".mp4"):
            return href
    return entry.get("link", "")


def poll_rednote_feed(account: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse the RSSHub feed for a Red Note account and return video post entries."""
    rss_url = _build_rss_url(account)
    logger.info("Polling Red Note feed: %s", rss_url)
    try:
        feed = feedparser.parse(rss_url)
    except Exception:
        logger.exception("Failed to parse Red Note RSS: %s", account["name"])
        return []

    posts = []
    for entry in feed.entries:
        if not _is_video_post(entry):
            continue
        post_id = _extract_post_id(entry)
        posts.append({
            "account_name": account["name"],
            "post_id": post_id,
            "title": entry.get("title", "Untitled"),
            "post_url": entry.get("link", ""),
            "video_url": _get_video_url(entry),
            "pub_date": _parse_pub_date(entry),
        })
    return posts


def find_new_livestreams(db: Session, account: dict[str, Any]) -> list[dict[str, Any]]:
    """Return posts from the account that haven't been processed yet."""
    all_posts = poll_rednote_feed(account)
    if not all_posts:
        return []

    existing_ids = set(
        row[0] for row in
        db.query(LivestreamSummary.post_id)
        .filter(LivestreamSummary.account_name == account["name"])
        .all()
    )

    return [p for p in all_posts if p["post_id"] not in existing_ids]


def process_livestream_video(
    db: Session, post: dict[str, Any], language: str = "cn"
) -> LivestreamSummary:
    """Download video, transcribe, and store. Returns DB record (without summary yet)."""
    ls = LivestreamSummary(
        account_name=post["account_name"],
        post_id=post["post_id"],
        title=post["title"],
        post_url=post["post_url"],
        video_url=post["video_url"],
        pub_date=post["pub_date"],
        status="processing",
    )
    db.add(ls)
    db.flush()

    audio_path = None
    try:
        url = post["video_url"] or post["post_url"]
        logger.info("Downloading video for livestream: %s", post["title"])
        audio_path = download_audio(url)
        logger.info("Transcribing livestream: %s", post["title"])
        transcript = transcribe_audio_with_timeout(audio_path, language=language, timeout=300)
        ls.transcript = transcript
        db.commit()
    except Exception as e:
        logger.exception("Failed to process livestream video: %s", post["title"])
        ls.status = "error"
        ls.error_message = str(e)[:500]
        db.commit()
    finally:
        if audio_path:
            cleanup_audio(audio_path)

    return ls


def process_manual_url(db: Session, url: str, title: str = "") -> LivestreamSummary:
    """Process a manually submitted Red Note replay URL."""
    post_id_match = XHS_VIDEO_URL_PATTERN.search(url) or XHS_DISCOVERY_PATTERN.search(url)
    post_id = post_id_match.group(1) if post_id_match else url

    existing = db.query(LivestreamSummary).filter(
        LivestreamSummary.post_id == post_id
    ).first()
    if existing:
        return existing

    ls = LivestreamSummary(
        account_name="manual",
        post_id=post_id,
        title=title or url,
        post_url=url,
        video_url=url,
        status="processing",
    )
    db.add(ls)
    db.flush()

    audio_path = None
    try:
        logger.info("Downloading manually submitted livestream: %s", url)
        audio_path = download_audio(url)
        logger.info("Transcribing manual livestream: %s", url)
        transcript = transcribe_audio_with_timeout(audio_path, language="cn", timeout=300)
        ls.transcript = transcript
        db.commit()
    except Exception as e:
        logger.exception("Failed to process manual livestream: %s", url)
        ls.status = "error"
        ls.error_message = str(e)[:500]
        db.commit()
    finally:
        if audio_path:
            cleanup_audio(audio_path)

    return ls


def get_new_livestreams_for_all_accounts(db: Session) -> list[LivestreamSummary]:
    """Poll all tracked Red Note accounts, process new videos, return records needing summarization."""
    all_new: list[LivestreamSummary] = []
    for account in TRACKED_REDNOTE_ACCOUNTS:
        try:
            new_posts = find_new_livestreams(db, account)
            for post in new_posts:
                ls = process_livestream_video(db, post, language=account.get("language", "cn"))
                if ls.transcript and ls.status != "error":
                    all_new.append(ls)
        except Exception:
            logger.exception("Error processing Red Note account: %s", account["name"])
    return all_new
