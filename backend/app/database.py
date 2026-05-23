from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, Float, String, Text, DateTime, Boolean, ForeignKey, create_engine, text
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
    review_en = Column(Text, default="")
    review_overall = Column(Text, default="")
    consensus_reached = Column(Boolean, default=True)
    rounds_taken = Column(Integer, default=1)
    disagreement_log_json = Column(Text, default="[]")
    alt_prediction_en = Column(Text, default="")
    alt_review_en = Column(Text, default="")
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
    source = Column(String, default="news_discovery")
    per_stock_analysis = Column(Text, default="")
    outcome = Column(String, nullable=True)
    price_at_prediction = Column(Float, nullable=True)
    price_at_verification = Column(Float, nullable=True)
    actual_change_pct = Column(Float, nullable=True)
    verified_at = Column(DateTime, nullable=True)
    # Quant model metadata (populated for source != "news_discovery")
    model_version = Column(String, default="")
    composite_score = Column(Float, nullable=True)
    momentum_score = Column(Float, nullable=True)
    value_score = Column(Float, nullable=True)
    volatility_score = Column(Float, nullable=True)
    quality_score = Column(Float, nullable=True)
    sentiment_score = Column(Float, nullable=True)
    rsi_at_prediction = Column(Float, nullable=True)
    macd_signal_at_prediction = Column(String, default="")
    confidence_interval_low = Column(Float, nullable=True)
    confidence_interval_high = Column(Float, nullable=True)
    predicted_change_pct = Column(Float, nullable=True)
    threshold_pct = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    endpoint = Column(String, unique=True, nullable=False)
    keys_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String, nullable=False, unique=True)
    label = Column(String, default="")
    added_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ModelPerformance(Base):
    __tablename__ = "model_performance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_version = Column(String, nullable=False, index=True)
    date = Column(String, nullable=False, index=True)
    total_predictions = Column(Integer, default=0)
    hits = Column(Integer, default=0)
    accuracy_pct = Column(Float, nullable=True)
    avg_confidence = Column(Float, nullable=True)
    avg_actual_change = Column(Float, nullable=True)
    factor_weights_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class FactorWeights(Base):
    """Persisted factor weights per model version. Updated by the learning loop."""
    __tablename__ = "factor_weights"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_version = Column(String, nullable=False, unique=True, index=True)
    weights_json = Column(Text, nullable=False, default="{}")
    fitted_on_samples = Column(Integer, default=0)
    fitted_at = Column(DateTime, nullable=True)
    notes = Column(Text, default="")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


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


def _migrate_db():
    engine = get_engine()
    migrations = [
        "ALTER TABLE daily_predictions ADD COLUMN review_en TEXT DEFAULT ''",
        "ALTER TABLE daily_predictions ADD COLUMN review_overall TEXT DEFAULT ''",
        "ALTER TABLE daily_predictions ADD COLUMN consensus_reached BOOLEAN DEFAULT 1",
        "ALTER TABLE daily_predictions ADD COLUMN rounds_taken INTEGER DEFAULT 1",
        "ALTER TABLE daily_predictions ADD COLUMN disagreement_log_json TEXT DEFAULT '[]'",
        "ALTER TABLE daily_predictions ADD COLUMN alt_prediction_en TEXT DEFAULT ''",
        "ALTER TABLE daily_predictions ADD COLUMN alt_review_en TEXT DEFAULT ''",
        "ALTER TABLE prediction_items ADD COLUMN source TEXT DEFAULT 'news_discovery'",
        "ALTER TABLE prediction_items ADD COLUMN per_stock_analysis TEXT DEFAULT ''",
        "ALTER TABLE prediction_items ADD COLUMN model_version TEXT DEFAULT ''",
        "ALTER TABLE prediction_items ADD COLUMN composite_score REAL",
        "ALTER TABLE prediction_items ADD COLUMN momentum_score REAL",
        "ALTER TABLE prediction_items ADD COLUMN value_score REAL",
        "ALTER TABLE prediction_items ADD COLUMN volatility_score REAL",
        "ALTER TABLE prediction_items ADD COLUMN quality_score REAL",
        "ALTER TABLE prediction_items ADD COLUMN sentiment_score REAL",
        "ALTER TABLE prediction_items ADD COLUMN rsi_at_prediction REAL",
        "ALTER TABLE prediction_items ADD COLUMN macd_signal_at_prediction TEXT DEFAULT ''",
        "ALTER TABLE prediction_items ADD COLUMN confidence_interval_low REAL",
        "ALTER TABLE prediction_items ADD COLUMN confidence_interval_high REAL",
        "ALTER TABLE prediction_items ADD COLUMN predicted_change_pct REAL",
        "ALTER TABLE prediction_items ADD COLUMN threshold_pct REAL",
    ]
    with engine.connect() as conn:
        for stmt in migrations:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass


def init_db():
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _migrate_db()


def get_db() -> Session:
    factory = get_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()
