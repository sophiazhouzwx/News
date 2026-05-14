from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    anthropic_base_url: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    anthropic_custom_header_name: str = ""
    anthropic_custom_header_value: str = ""

    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "daily-ai-news/1.0"

    vapid_private_key: str = ""
    vapid_public_key: str = ""
    vapid_contact_email: str = "you@example.com"

    digest_hour: int = 7
    digest_minute: int = 0

    database_url: str = "sqlite:///./data/app.db"

    prediction_extended_thinking: bool = False
    prediction_thinking_budget: int = 8000

    xiaohongshu_cookie: str = ""
    rsshub_base_url: str = "https://rsshub.app"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


NEWS_RSS_FEEDS = [
    # Authoritative general tech news (tier 1)
    {"name": "Hacker News", "url": "https://hnrss.org/frontpage?count=20", "tier": 1},
    {"name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/", "tier": 1},
    {"name": "The Verge Tech", "url": "https://www.theverge.com/rss/tech/index.xml", "tier": 2},
    {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/technology-lab", "tier": 2},
    {"name": "MIT Technology Review", "url": "https://www.technologyreview.com/feed/", "tier": 1},
    {"name": "Reuters Technology", "url": "https://www.reutersagency.com/feed/?best-topics=tech", "tier": 1},
    {"name": "Wired AI", "url": "https://www.wired.com/feed/tag/ai/latest/rss", "tier": 2},
    # Big company AI blogs (tier 1)
    {"name": "OpenAI Blog", "url": "https://openai.com/blog/rss.xml", "tier": 1},
    {"name": "Anthropic Blog", "url": "https://www.anthropic.com/rss.xml", "tier": 1},
    {"name": "Google AI Blog", "url": "https://blog.google/technology/ai/rss/", "tier": 1},
    {"name": "Meta AI Blog", "url": "https://ai.meta.com/blog/rss/", "tier": 2},
    {"name": "NVIDIA Blog", "url": "https://blogs.nvidia.com/feed/", "tier": 2},
    {"name": "Microsoft AI Blog", "url": "https://blogs.microsoft.com/ai/feed/", "tier": 2},
    {"name": "Apple ML Research", "url": "https://machinelearning.apple.com/rss.xml", "tier": 2},
    {"name": "Amazon Science", "url": "https://www.amazon.science/index.rss", "tier": 2},
    # AI research (tier 1-2)
    {"name": "DeepMind Blog", "url": "https://deepmind.google/blog/rss.xml", "tier": 1},
    {"name": "Hugging Face Blog", "url": "https://huggingface.co/blog/feed.xml", "tier": 2},
    # AI research papers
    {"name": "arXiv CS.AI", "url": "https://rss.arxiv.org/rss/cs.AI", "tier": 2},
    {"name": "arXiv CS.LG", "url": "https://rss.arxiv.org/rss/cs.LG", "tier": 2},
    {"name": "arXiv CS.CL", "url": "https://rss.arxiv.org/rss/cs.CL", "tier": 2},
    # Financial / market news
    {"name": "Yahoo Finance Tech", "url": "https://finance.yahoo.com/news/rssindex", "tier": 3},
    {"name": "MarketWatch", "url": "https://feeds.marketwatch.com/marketwatch/topstories", "tier": 3},
]

TRACKED_PERSONALITIES = [
    {
        "name": "Elon Musk",
        "youtube_search_queries": [
            "Elon Musk interview",
            "Elon Musk speech",
            "Elon Musk podcast",
        ],
        "language": "en",
    },
    {
        "name": "Jensen Huang",
        "youtube_search_queries": [
            "Jensen Huang interview",
            "Jensen Huang speech",
            "Jensen Huang keynote",
        ],
        "language": "en",
    },
]

REDDIT_SUBREDDITS = [
    {"name": "r/artificial", "subreddit": "artificial", "limit": 10, "tier": 2},
    {"name": "r/technology", "subreddit": "technology", "limit": 10, "tier": 2},
    {"name": "r/MachineLearning", "subreddit": "MachineLearning", "limit": 10, "tier": 1},
]

TRACKED_PODCASTS = [
    {
        "name": "WSJ Tech News Briefing",
        "rss_url": "https://video-api.wsj.com/podcast/rss/wsj/tech-news-briefing",
        "apple_podcast_id": 74844126,
        "language": "en",
        "schedule": "daily",
    },
    {
        "name": "WSJ What's News",
        "rss_url": "https://video-api.wsj.com/podcast/rss/wsj/whats-news",
        "apple_podcast_id": 152016440,
        "language": "en",
        "schedule": "daily",
    },
    {
        "name": "NPR Up First",
        "rss_url": "https://feeds.npr.org/510318/podcast.xml",
        "apple_podcast_id": 1222114325,
        "language": "en",
        "schedule": "daily",
    },
    {
        "name": "天真不天真",
        "rss_url": "https://feed.xyzfm.space/mcklbwxjdvfu",
        "apple_podcast_id": 1731784296,
        "language": "cn",
        "schedule": "biweekly",
    },
    {
        "name": "半拿铁｜商业浮沉录",
        "rss_url": "https://proxy.wavpub.com/caffebreve.xml",
        "apple_podcast_id": 1615939013,
        "language": "cn",
        "schedule": "weekly",
    },
]

TRACKED_REDNOTE_ACCOUNTS = [
    {
        "name": "xb99681",
        "user_id": "xb99681",
        "language": "cn",
        "rss_path": "/xiaohongshu/user/{user_id}/notes",
    },
]
