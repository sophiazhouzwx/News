import logging
import math
import ssl
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any

import feedparser
from rapidfuzz import fuzz

from ..config import NEWS_RSS_FEEDS, REDDIT_SUBREDDITS, get_settings

logger = logging.getLogger(__name__)

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE
_handler = urllib.request.HTTPSHandler(context=_ssl_ctx)


def _fetch_one_feed(feed_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Fetch a single RSS feed. Runs in a thread pool."""
    try:
        feed = feedparser.parse(feed_cfg["url"], handlers=[_handler])
        results = []
        for entry in feed.entries[:15]:
            pub = entry.get("published_parsed") or entry.get("updated_parsed")
            pub_dt = datetime(*pub[:6], tzinfo=timezone.utc) if pub else None
            results.append({
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "source": feed_cfg["name"],
                "published": pub_dt.isoformat() if pub_dt else "",
                "summary": entry.get("summary", "")[:500],
                "tier": feed_cfg.get("tier", 2),
            })
        return results
    except Exception:
        logger.exception("Failed to fetch RSS feed: %s", feed_cfg["name"])
        return []


def fetch_rss_articles() -> list[dict[str, Any]]:
    """Fetch all RSS feeds in parallel."""
    articles = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(_fetch_one_feed, cfg): cfg for cfg in NEWS_RSS_FEEDS
        }
        for future in as_completed(futures, timeout=30):
            try:
                articles.extend(future.result())
            except Exception:
                cfg = futures[future]
                logger.exception("Failed to fetch RSS feed: %s", cfg["name"])
    return articles


def fetch_reddit_posts() -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.reddit_client_id or not settings.reddit_client_secret:
        logger.warning("Reddit credentials not configured, skipping Reddit sources")
        return []

    try:
        import praw
        reddit = praw.Reddit(
            client_id=settings.reddit_client_id,
            client_secret=settings.reddit_client_secret,
            user_agent=settings.reddit_user_agent,
        )
    except Exception:
        logger.exception("Failed to initialize Reddit client")
        return []

    posts = []
    for sub_cfg in REDDIT_SUBREDDITS:
        try:
            subreddit = reddit.subreddit(sub_cfg["subreddit"])
            for submission in subreddit.top(time_filter="day", limit=sub_cfg["limit"]):
                created = datetime.fromtimestamp(submission.created_utc, tz=timezone.utc)
                posts.append({
                    "title": submission.title,
                    "url": submission.url if not submission.is_self else f"https://reddit.com{submission.permalink}",
                    "source": sub_cfg["name"],
                    "published": created.isoformat(),
                    "summary": (submission.selftext[:500] if submission.is_self else ""),
                    "score": submission.score,
                    "tier": sub_cfg.get("tier", 2),
                })
        except Exception:
            logger.exception("Failed to fetch subreddit: %s", sub_cfg["name"])
    return posts


def deduplicate(articles: list[dict[str, Any]], threshold: float = 75.0) -> list[dict[str, Any]]:
    """Remove near-duplicate articles by fuzzy title matching."""
    unique: list[dict[str, Any]] = []
    for article in articles:
        is_dup = False
        for existing in unique:
            if fuzz.token_sort_ratio(article["title"], existing["title"]) >= threshold:
                is_dup = True
                break
        if not is_dup:
            unique.append(article)
    return unique


def _score_article(article: dict[str, Any], now: datetime) -> float:
    tier = article.get("tier", 2)
    tier_weight = {1: 1.0, 2: 0.6, 3: 0.3}.get(tier, 0.6)

    recency_score = 0.0
    pub_str = article.get("published", "")
    if pub_str:
        try:
            pub = datetime.fromisoformat(pub_str)
            age_hours = max(0, (now - pub).total_seconds() / 3600)
            recency_score = max(0.0, 1.0 - (age_hours / 36))
        except ValueError:
            pass

    reddit_score = 0.0
    if "score" in article and article["score"]:
        reddit_score = min(0.5, math.log1p(article["score"]) / 20)

    return tier_weight * 0.5 + recency_score * 0.35 + reddit_score * 0.15


def aggregate_news() -> list[dict[str, Any]]:
    """Fetch from all sources, deduplicate, score, and return top articles."""
    rss_articles = fetch_rss_articles()
    reddit_posts = fetch_reddit_posts()

    all_articles = rss_articles + reddit_posts
    unique = deduplicate(all_articles)

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=36)
    recent = []
    for a in unique:
        pub_str = a.get("published", "")
        if not pub_str:
            continue
        try:
            pub = datetime.fromisoformat(pub_str)
            if pub >= cutoff:
                recent.append(a)
        except ValueError:
            continue

    recent.sort(key=lambda a: _score_article(a, now), reverse=True)
    return recent[:30]
