from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, Float, String, Text, DateTime, Boolean, ForeignKey, create_engine
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from .config import get_settings

Base = declarative_base()


class Digest(Base):
    __tablename__ = "digests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String, unique=True, nullable=False, index=True)
    summary_en = Column(Text, nullable=False, default="")
    summary_cn = Column(Text, nullable=False, default="")
    raw_articles_json = Column(Text, default="[]")
    podcast_episode_ids_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class PodcastEpisode(Base):
    __tablename__ = "podcast_episodes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    podcast_name = Column(String, nullable=False, index=True)
    episode_guid = Column(String, unique=True, nullable=False, index=True)
    episode_title = Column(String, nullable=False)
    pub_date = Column(DateTime, nullable=True)
    audio_url = Column(String, default="")
    transcript = Column(Text, default="")
    summary_en = Column(Text, default="")
    summary_cn = Column(Text, default="")
    summarized_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class MediaSummary(Base):
    __tablename__ = "media_summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String, nullable=False)
    title = Column(String, default="")
    media_type = Column(String, default="unknown")  # youtube, podcast, audio
    transcript = Column(Text, default="")
    summary_en = Column(Text, default="")
    summary_cn = Column(Text, default="")
    status = Column(String, default="pending")  # pending, processing, done, error
    error_message = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class LivestreamSummary(Base):
    __tablename__ = "livestream_summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_name = Column(String, nullable=False, index=True)
    post_id = Column(String, unique=True, nullable=False, index=True)
    title = Column(String, default="")
    post_url = Column(String, default="")
    video_url = Column(String, default="")
    pub_date = Column(DateTime, nullable=True)
    transcript = Column(Text, default="")
    summary_en = Column(Text, default="")
    summary_cn = Column(Text, default="")
    status = Column(String, default="pending")  # pending, processing, done, error
    error_message = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ArticleFeedback(Base):
    __tablename__ = "article_feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    digest_id = Column(Integer, nullable=False, index=True)
    article_title = Column(String, nullable=False)
    helpful = Column(Boolean, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class PersonalitySpeech(Base):
    __tablename__ = "personality_speeches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    personality_name = Column(String, nullable=False, index=True)
    video_id = Column(String, unique=True, nullable=False, index=True)
    title = Column(String, nullable=False)
    video_url = Column(String, default="")
    pub_date = Column(DateTime, nullable=True)
    transcript = Column(Text, default="")
    summary_en = Column(Text, default="")
    summary_cn = Column(Text, default="")
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class DailyPrediction(Base):
    __tablename__ = "daily_predictions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String, nullable=False, index=True)
    prediction_en = Column(Text, nullable=False, default="")
    prediction_cn = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class PredictionItem(Base):
    __tablename__ = "prediction_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    prediction_id = Column(Integer, ForeignKey("daily_predictions.id"), nullable=False, index=True)
    ticker = Column(String, nullable=False)
    direction = Column(String, nullable=False)
    timeframe_days = Column(Integer, nullable=False)
    confidence_pct = Column(Integer, nullable=True)
    thesis = Column(Text, default="")
    outcome = Column(String, nullable=True)
    price_at_prediction = Column(Float, nullable=True)
    price_at_verification = Column(Float, nullable=True)
    actual_change_pct = Column(Float, nullable=True)
    verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    endpoint = Column(String, unique=True, nullable=False)
    keys_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(settings.database_url, echo=False)
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine())
    return _SessionLocal


def init_db():
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    factory = get_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()
