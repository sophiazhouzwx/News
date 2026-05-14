import json
import logging
from typing import Any

import httpx
from anthropic import Anthropic

from ..config import get_settings

logger = logging.getLogger(__name__)

_client: Anthropic | None = None
MAX_TRANSCRIPT_CHARS = 80_000
API_TIMEOUT = 120  # 2 minutes max for any single Claude API call


def _get_model() -> str:
    return get_settings().anthropic_model


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        settings = get_settings()
        kwargs: dict[str, Any] = {"api_key": settings.anthropic_api_key}
        if settings.anthropic_base_url:
            kwargs["base_url"] = settings.anthropic_base_url
        headers: dict[str, str] = {}
        if settings.anthropic_custom_header_name and settings.anthropic_custom_header_value:
            headers[settings.anthropic_custom_header_name] = settings.anthropic_custom_header_value
        if settings.anthropic_base_url:
            headers["Authorization"] = f"Bearer {settings.anthropic_api_key}"
        if headers:
            kwargs["default_headers"] = headers
        kwargs["timeout"] = httpx.Timeout(API_TIMEOUT, connect=15.0)
        _client = Anthropic(**kwargs)
    return _client


def summarize_news_digest(
    articles: list[dict[str, Any]],
    feedback_summary: str = "",
) -> dict[str, str]:
    """Produce a bilingual daily news digest from a list of articles.
    Returns {"en": ..., "cn": ...}.
    """
    def _fmt_article(a: dict) -> str:
        parts = [f"[{a['source']}] {a['title']}"]
        meta = []
        if a.get("published"):
            meta.append(f"published: {a['published'][:10]}")
        if a.get("score") is not None:
            meta.append(f"upvotes: {a['score']}")
        if meta:
            parts.append(f"({', '.join(meta)})")
        parts.append(f"URL: {a['url']}")
        if a.get("summary"):
            parts.append(a["summary"])
        return "\n".join(parts)

    articles_text = "\n\n".join(_fmt_article(a) for a in articles)

    feedback_block = ""
    if feedback_summary:
        feedback_block = f"""
USER FEEDBACK ON PAST DIGESTS (use this to improve relevance):
{feedback_summary}

Based on the above feedback, prioritize the types of articles the user found helpful and de-prioritize topics they marked as unhelpful.
"""

    prompt = f"""You are a senior tech analyst writing a crisp daily briefing. The reader is busy — every sentence must earn its place.
{feedback_block}
ARTICLES:
{articles_text}

---

Write in markdown. Format each item exactly as:
`- **[Title](url)**: One punchy sentence stating what happened and why it matters.`

## English Digest

### Big Tech Moves
### AI & Machine Learning
### Industry & Market
### Data Science & Engineering
### Emerging Trends

---

## 中文摘要

### 科技巨头动态
### AI与机器学习
### 行业与市场
### 数据科学与工程
### 前沿趋势

Rules:
- ONE sentence per article. Lead with the "so what" — what changed, what it means. No filler.
- 2-4 items per section. Omit a section entirely if < 2 items fit.
- Only include genuinely important news. Skip routine updates, minor product tweaks, and opinion pieces.
- Use the published date to assess recency. Prefer articles from the last 12 hours over older ones.
- Articles with high upvote counts indicate community interest — weigh them accordingly.
- Keep source URLs intact.
- Chinese must be a proper translation, same items, same order."""

    client = _get_client()
    response = client.messages.create(
        model=_get_model(),
        max_tokens=5000,
        messages=[{"role": "user", "content": prompt}],
    )
    full_text = response.content[0].text

    en_part, cn_part = _split_bilingual(full_text)
    return {"en": en_part, "cn": cn_part}


def summarize_podcast_episode(
    title: str, transcript: str, language: str = "en"
) -> dict[str, str]:
    """Summarize a podcast episode transcript bilingually. Returns {"en": ..., "cn": ...}."""
    truncated = transcript[:MAX_TRANSCRIPT_CHARS]
    primary = "English" if language == "en" else "Chinese"
    secondary = "Chinese" if language == "en" else "English"

    is_description = transcript.lstrip().startswith("[Episode Description")
    source_label = "SHOW NOTES / DESCRIPTION" if is_description else "TRANSCRIPT"
    extra_rules = (
        "\n- You are working from show notes/description only (no full transcript). "
        "Expand on the topics as much as possible based on the information given."
        if is_description else ""
    )

    prompt = f"""Summarize this podcast episode. Be direct — no filler, no restating the title.

Episode: {title}
Language: {primary}

{source_label}:
{truncated}

---

## English Summary

**TLDR**: 1-2 sentences — the single most important thing from this episode.

**Key Points**:
1. (specific fact or insight)
2. (specific fact or insight)
3. (specific fact or insight)

**Best Quote**: "..." (only if genuinely memorable — skip if nothing stands out)

---

## 中文摘要

**要点**: (mirror English TLDR)

**关键内容**:
1.
2.
3.

**精彩语录**: "..."

Rules:
- {primary} is primary; {secondary} is a translation.
- 100-200 words per language. Cut anything a reader could infer from the title.
- Specific facts > vague descriptions. Numbers, names, and claims > "they discussed..."{extra_rules}"""

    client = _get_client()
    response = client.messages.create(
        model=_get_model(),
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )
    full_text = response.content[0].text

    en_part, cn_part = _split_bilingual(full_text)
    return {"en": en_part, "cn": cn_part}


def summarize_media(title: str, transcript: str, url: str) -> dict[str, str]:
    """Summarize an on-demand video/podcast transcript bilingually."""
    truncated = transcript[:MAX_TRANSCRIPT_CHARS]

    prompt = f"""Summarize this video/podcast. Be direct — skip preamble.

Title: {title}
URL: {url}

TRANSCRIPT:
{truncated}

---

## English Summary

**TLDR**: 1-2 sentences — the core message or finding.

**Key Points**:
1. (specific insight with details)
2. (specific insight with details)
3. (specific insight with details)

---

## 中文摘要

**要点**: (mirror TLDR)

**关键内容**:
1.
2.
3.

Rules:
- 100-200 words per language. Every sentence must add information.
- Lead with specifics: numbers, names, claims, timelines.
- Chinese is a proper translation, not transliteration."""

    client = _get_client()
    response = client.messages.create(
        model=_get_model(),
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}],
    )
    full_text = response.content[0].text

    en_part, cn_part = _split_bilingual(full_text)
    return {"en": en_part, "cn": cn_part}


def summarize_livestream(title: str, transcript: str, language: str = "cn") -> dict[str, str]:
    """Summarize a livestream replay transcript bilingually. Returns {"en": ..., "cn": ...}."""
    truncated = transcript[:MAX_TRANSCRIPT_CHARS]
    primary = "Chinese" if language == "cn" else "English"
    secondary = "English" if language == "cn" else "Chinese"

    prompt = f"""Summarize this livestream replay. Be direct.

Title: {title}
Language: {primary}

TRANSCRIPT:
{truncated}

---

## English Summary

**TLDR**: 1-2 sentences — what the livestream was about and the key takeaway.

**Key Points**:
1. (specific advice, product rec, or insight)
2. (specific advice, product rec, or insight)
3. (specific advice, product rec, or insight)

**Best Moment**: (one-liner — skip if nothing stands out)

---

## 中文摘要

**要点**:
**关键内容**:
1.
2.
3.

**精彩时刻**:

Rules:
- {primary} is primary; {secondary} is a translation.
- 100-200 words per language. Specific product names, prices, and advice > vague descriptions."""

    client = _get_client()
    response = client.messages.create(
        model=_get_model(),
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )
    full_text = response.content[0].text

    en_part, cn_part = _split_bilingual(full_text)
    return {"en": en_part, "cn": cn_part}


def generate_daily_prediction(
    news_summary_en: str,
    recent_predictions: list[dict[str, Any]] | None = None,
    raw_articles: list[dict[str, Any]] | None = None,
    market_context: str = "",
) -> dict[str, Any]:
    """Generate AI future predictions and stock recommendations.
    Returns {"en": ..., "cn": ..., "items": [...]}.
    """
    history_block = ""
    if recent_predictions:
        entries = []
        for p in recent_predictions[-5:]:
            items_summary = ""
            if p.get("items"):
                hits = sum(1 for i in p["items"] if i.get("outcome") == "hit")
                total = sum(1 for i in p["items"] if i.get("outcome") in ("hit", "miss"))
                if total:
                    items_summary = f"\n  Verified accuracy: {hits}/{total} calls correct"
            entries.append(f"[{p['date']}]{items_summary}\n{p['prediction_en'][:600]}")
        history_block = (
            "\n\nYOUR PREVIOUS PREDICTIONS (for continuity and accountability):\n"
            + "\n---\n".join(entries)
            + "\n\nReview whether your previous predictions are tracking correctly. "
            "Use the verified accuracy data above (not your own judgment) for the scorecard.\n"
        )

    if raw_articles:
        article_lines = []
        for a in raw_articles[:25]:
            pub = a.get("published", "")[:10]
            score_str = f" [{a['score']} upvotes]" if a.get("score") else ""
            article_lines.append(
                f"- [{a['source']}, {pub}{score_str}] {a['title']}: {a.get('summary', '')[:200]}"
            )
        news_input = "\n".join(article_lines)
    else:
        news_input = news_summary_en[:4000]

    market_block = f"\n{market_context}\n" if market_context else ""

    prompt = f"""You are a sharp-eyed AI/tech investment analyst. Be specific and direct. No hedging fluff.

TODAY'S NEWS:
{news_input}
{market_block}{history_block}
---

## English Predictions

### What Today's News Means
2-3 predictions. Each one: **[Prediction]** (Timeframe, Confidence: X%) — 1-2 sentences of reasoning grounded in today's news.

### Prediction Scorecard
If previous predictions exist above, one line each: prediction → on track / off track / too early to tell. Skip if no history.

### Stocks to Watch
Table format:
| Ticker | Action | Why (one sentence) |
Each row = one specific, actionable call tied to today's news. 3-5 rows max.

**Caution**: (any names to avoid, one line)

*AI-generated analysis, not financial advice.*

---

## 中文预测

### 今日新闻解读
### 预测追踪
### 值得关注的股票

(Mirror English exactly.)

*以上为AI生成的分析，仅供参考，不构成投资建议。*

### STRUCTURED_ITEMS
Output one JSON object per stock call from the Stocks to Watch table, one per line:
{{"ticker":"NVDA","direction":"bull","timeframe_days":14,"confidence_pct":75,"thesis":"One sentence why"}}

Rules:
- Every prediction must cite a specific news item from today.
- Stocks: ticker + one-sentence thesis. No generic "AI is growing" filler.
- Confidence as a number. Timeframe as specific days (e.g. 7, 14, 30).
- Direction must be "bull", "bear", or "hold".
- Chinese is a proper translation.
- STRUCTURED_ITEMS must include every stock from the Stocks to Watch table."""

    client = _get_client()
    settings = get_settings()
    create_kwargs: dict[str, Any] = {
        "model": _get_model(),
        "max_tokens": 10000,
        "messages": [{"role": "user", "content": prompt}],
    }
    if getattr(settings, "prediction_extended_thinking", False):
        create_kwargs["thinking"] = {
            "type": "enabled",
            "budget_tokens": getattr(settings, "prediction_thinking_budget", 8000),
        }

    response = client.messages.create(**create_kwargs)

    full_text = ""
    for block in response.content:
        if getattr(block, "type", "") == "text":
            full_text += block.text

    en_part, cn_part = _split_bilingual(full_text)
    items = _parse_structured_items(full_text)
    return {"en": en_part, "cn": cn_part, "items": items}


def _parse_structured_items(text: str) -> list[dict[str, Any]]:
    items = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{") and '"ticker"' in line:
            try:
                obj = json.loads(line)
                if all(k in obj for k in ("ticker", "direction", "timeframe_days")):
                    items.append(obj)
            except json.JSONDecodeError:
                pass
    return items


def _split_bilingual(text: str) -> tuple[str, str]:
    """Split Claude's bilingual output into English and Chinese parts.
    Handles both EN-first and CN-first orderings.
    """
    cn_markers = ["## 中文摘要", "## 中文预测", "## 中文"]
    en_markers = ["## English Summary", "## English Digest", "## English Predictions", "## English"]

    cn_idx = -1
    for marker in cn_markers:
        idx = text.find(marker)
        if idx != -1:
            cn_idx = idx
            break

    en_idx = -1
    for marker in en_markers:
        idx = text.find(marker)
        if idx != -1:
            en_idx = idx
            break

    if cn_idx == -1 and en_idx == -1:
        return text.strip(), text.strip()

    if cn_idx != -1 and en_idx != -1:
        if en_idx < cn_idx:
            en_part = text[en_idx:cn_idx].strip()
            cn_part = text[cn_idx:].strip()
        else:
            cn_part = text[cn_idx:en_idx].strip()
            en_part = text[en_idx:].strip()
    elif cn_idx != -1:
        en_part = text[:cn_idx].strip()
        cn_part = text[cn_idx:].strip()
    else:
        en_part = text[en_idx:].strip()
        cn_part = text[:en_idx].strip()

    for sep in ["---", "***"]:
        en_part = en_part.strip(sep).strip()
        cn_part = cn_part.strip(sep).strip()

    return en_part, cn_part
