"""Quantitative prediction engine.

Replaces the LLM as the *decision maker* for stock calls. Claude is still used
as one signal (news sentiment scoring) but never picks tickers, directions, or
confidence. Outputs match the legacy PredictionItem shape so the rest of the
pipeline (DB save, verification, API responses) keeps working unchanged.

Model versioning:
- `MODEL_VERSION` is bumped whenever scoring math changes, so verified
  predictions remain attributable to the math that produced them.
- Factor weights are stored separately in the `factor_weights` table and
  updated by the learning loop.
"""

from __future__ import annotations

import json
import logging
import math
import re
import time
from datetime import datetime, timezone
from typing import Any

from ..config import get_settings
from .market_data import (
    adaptive_threshold_pct,
    compute_factor_scores,
    compute_technical_indicators,
    estimate_timeframe_days,
    get_fundamental_data,
    get_price,
)

logger = logging.getLogger(__name__)

MODEL_VERSION = "quant_v1"

# Default factor weights — used until the learning loop has enough data to
# fit a model. Tuned so momentum and the technical overlay dominate, with
# sentiment a meaningful tiebreaker.
DEFAULT_WEIGHTS: dict[str, float] = {
    "momentum_score": 0.30,
    "value_score": 0.10,
    "volatility_score": 0.10,
    "quality_score": 0.15,
    "technical_score": 0.20,
    "sentiment_score": 0.15,
}

# Composite-score thresholds for the direction classifier.
BULL_THRESHOLD = 0.6
BEAR_THRESHOLD = -0.6


# ---------------------------------------------------------------------------
# Weight loading / persistence
# ---------------------------------------------------------------------------

def load_weights(db, model_version: str = MODEL_VERSION) -> dict[str, float]:
    from ..database import FactorWeights

    row = db.query(FactorWeights).filter_by(model_version=model_version).first()
    if not row or not row.weights_json:
        return DEFAULT_WEIGHTS.copy()
    try:
        weights = json.loads(row.weights_json)
        if not isinstance(weights, dict):
            return DEFAULT_WEIGHTS.copy()
        # Fill in any factors absent from the persisted blob using defaults
        for k, v in DEFAULT_WEIGHTS.items():
            weights.setdefault(k, v)
        return {k: float(v) for k, v in weights.items()}
    except (ValueError, TypeError):
        return DEFAULT_WEIGHTS.copy()


def save_weights(db, weights: dict[str, float], samples: int,
                 notes: str = "", model_version: str = MODEL_VERSION) -> None:
    from ..database import FactorWeights

    row = db.query(FactorWeights).filter_by(model_version=model_version).first()
    now = datetime.now(timezone.utc)
    payload = json.dumps({k: float(v) for k, v in weights.items()})
    if row:
        row.weights_json = payload
        row.fitted_on_samples = samples
        row.fitted_at = now
        row.notes = notes
        row.updated_at = now
    else:
        db.add(FactorWeights(
            model_version=model_version,
            weights_json=payload,
            fitted_on_samples=samples,
            fitted_at=now,
            notes=notes,
            updated_at=now,
        ))
    db.commit()


# ---------------------------------------------------------------------------
# Ticker discovery
# ---------------------------------------------------------------------------

_TICKER_RE = re.compile(r"\b([A-Z]{1,5})\b")

# Common English words written in ALL CAPS that we should never treat as
# tickers, even if they pass the regex.
_TICKER_STOPWORDS = {
    "A", "I", "THE", "AI", "ML", "API", "CEO", "CFO", "CTO", "IPO", "GPU",
    "CPU", "USA", "US", "UK", "EU", "FDA", "SEC", "GDP", "URL", "HTTP",
    "JSON", "HTML", "CSS", "RAM", "SSD", "SaaS", "OS", "OK", "PR",
    "ETF", "SPAC", "Q1", "Q2", "Q3", "Q4", "YOY", "QOQ", "MOM",
    "RSS", "PDF", "PNG", "JPG", "CNN", "BBC", "NPR", "WSJ", "NYT", "FT",
    "TLDR", "IMO", "TIL", "DOJ", "FTC", "FCC", "NSA", "FBI", "WHO", "WTO",
}

# Hand-curated watchlist used when nothing else is configured.
DEFAULT_CANDIDATES = [
    "NVDA", "AAPL", "MSFT", "GOOGL", "META", "AMZN", "TSLA", "AMD",
    "AVGO", "TSM", "ORCL", "CRM", "PLTR", "SMCI", "ARM",
]


def extract_tickers_from_text(text: str) -> set[str]:
    if not text:
        return set()
    found = set()
    for m in _TICKER_RE.finditer(text):
        sym = m.group(1)
        if sym in _TICKER_STOPWORDS:
            continue
        if len(sym) == 1:
            continue
        found.add(sym)
    return found


def discover_candidate_tickers(
    db,
    raw_articles: list[dict[str, Any]] | None,
    recent_predictions: list[dict[str, Any]] | None,
    max_candidates: int = 12,
) -> list[str]:
    """Build the candidate list the quant model will score this run.

    Sources, in priority order:
      1. Watchlist (always included)
      2. Tickers mentioned in today's article titles + summaries
      3. Tickers from the last few days of predictions (continuity)
      4. DEFAULT_CANDIDATES (filler when everything else is empty)
    """
    from ..database import WatchlistItem

    candidates: list[str] = []
    seen: set[str] = set()

    def add(sym: str):
        s = sym.upper().strip()
        if s and s not in seen and s not in _TICKER_STOPWORDS:
            candidates.append(s)
            seen.add(s)

    try:
        for w in db.query(WatchlistItem).all():
            add(w.ticker)
    except Exception:
        logger.exception("Failed to read watchlist — continuing without it")

    if raw_articles:
        joined = " ".join(
            (a.get("title", "") + " " + a.get("summary", ""))
            for a in raw_articles
        )
        for sym in extract_tickers_from_text(joined):
            add(sym)

    if recent_predictions:
        for p in recent_predictions[-3:]:
            for it in p.get("items", []) or []:
                add(it.get("ticker", ""))

    if len(candidates) < 3:
        for sym in DEFAULT_CANDIDATES:
            add(sym)

    candidates = candidates[:max_candidates]

    # Opt-in: drop tickers within their earnings noise window.
    try:
        if get_settings().quant_suppress_earnings_window:
            from ..shared.calendar_utils import filter_out_earnings_window
            kept, suppressed = filter_out_earnings_window(candidates)
            if suppressed:
                logger.info(
                    "Earnings suppression dropped %d tickers: %s",
                    len(suppressed), ", ".join(suppressed),
                )
            candidates = kept
    except Exception:
        logger.exception("Earnings suppression failed — proceeding with full candidate list")

    return candidates


# ---------------------------------------------------------------------------
# News sentiment (only place we still call Claude in the quant flow)
# ---------------------------------------------------------------------------

def score_news_sentiment(articles: list[dict[str, Any]],
                         tickers: list[str]) -> dict[str, float]:
    """Ask Claude to rate today's news sentiment for each ticker on [-1, +1].

    Returns {ticker: sentiment_score}. Tickers with no mention get 0.0.
    """
    if not articles or not tickers:
        return {t: 0.0 for t in tickers}

    # Build a compact article digest (titles + summaries) the model can scan.
    lines = []
    for a in articles[:40]:
        title = (a.get("title") or "").strip()
        if not title:
            continue
        summary = (a.get("summary") or "").strip()[:300]
        lines.append(f"- {title}: {summary}" if summary else f"- {title}")
    if not lines:
        return {t: 0.0 for t in tickers}

    articles_blob = "\n".join(lines)
    tickers_blob = ", ".join(sorted(set(tickers)))

    prompt = (
        "You are a sentiment scorer. For each ticker, rate today's news "
        "sentiment toward THAT company on a scale of -1.0 (very bearish) to "
        "+1.0 (very bullish). 0.0 means no relevant news or neutral.\n\n"
        f"TICKERS: {tickers_blob}\n\n"
        f"TODAY'S NEWS:\n{articles_blob}\n\n"
        "Output ONE JSON object, no prose: "
        '{"NVDA": 0.4, "AAPL": -0.1, ...}. Only include tickers from the '
        "TICKERS list. Numbers must be between -1 and 1."
    )

    try:
        # Import here so quant_models stays importable without anthropic in
        # tests / lightweight contexts.
        from .summarizer import _get_client, _get_model

        client = _get_client()
        resp = client.messages.create(
            model=_get_model(),
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        text = ""
        for block in resp.content:
            if getattr(block, "type", "") == "text":
                text += block.text
        # Find the first {...} blob in the response
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("no JSON object in sentiment response")
        scores_raw = json.loads(text[start:end + 1])
        scores = {}
        for t in tickers:
            v = scores_raw.get(t, scores_raw.get(t.upper(), 0.0))
            try:
                scores[t] = max(-1.0, min(1.0, float(v)))
            except (TypeError, ValueError):
                scores[t] = 0.0
        return scores
    except Exception:
        logger.exception("News sentiment scoring failed — defaulting to 0")
        return {t: 0.0 for t in tickers}


# ---------------------------------------------------------------------------
# Composite scoring & direction classification
# ---------------------------------------------------------------------------

def _weighted_score(factors: dict[str, float | None],
                    weights: dict[str, float]) -> tuple[float | None, dict[str, float]]:
    """Combine factor z-scores with weights, skipping missing factors and
    re-normalizing the remaining weights so missing data doesn't shrink the
    composite. Returns (composite, contribution_breakdown)."""
    present = {k: v for k, v in factors.items() if v is not None and k in weights}
    if not present:
        return None, {}
    total_weight = sum(abs(weights[k]) for k in present)
    if total_weight == 0:
        return None, {}
    contributions = {k: weights[k] * v for k, v in present.items()}
    composite = sum(contributions.values()) / total_weight
    return composite, contributions


def classify_direction(composite: float | None, confidence_pct: int | None) -> str:
    if composite is None:
        return "hold"
    if composite >= BULL_THRESHOLD:
        return "bull"
    if composite <= BEAR_THRESHOLD:
        return "bear"
    return "hold"


def composite_to_confidence(composite: float | None) -> int:
    """Map composite score magnitude to a 0-100 confidence."""
    if composite is None:
        return 0
    mag = min(abs(composite), 3.0)
    # 0 → 30%, 1 → ~55%, 2 → ~80%, 3 → 95%
    pct = 30 + mag * 22
    return int(max(20, min(95, round(pct))))


def expected_change_pct(composite: float | None, vol_daily: float | None,
                        timeframe_days: int) -> float | None:
    """Translate composite signal + realized vol into a point-estimate of
    expected % return over the timeframe. Calibrated so |composite|=1 implies
    ~1 standard deviation of timeframe-scaled move."""
    if composite is None or vol_daily is None or vol_daily <= 0:
        return None
    move = composite * vol_daily * math.sqrt(max(1, timeframe_days)) * 100.0
    return round(move, 2)


def build_thesis(ticker: str, tech: dict, fund: dict, factors: dict,
                 sentiment: float, direction: str) -> str:
    parts = [f"{direction.upper()} {ticker}."]
    if factors.get("technical_score") is not None:
        rsi = tech.get("rsi_14")
        macd_label = tech.get("macd_signal_label", "")
        if rsi is not None:
            if rsi < 30:
                parts.append(f"RSI oversold ({rsi:.0f})")
            elif rsi > 70:
                parts.append(f"RSI overbought ({rsi:.0f})")
            else:
                parts.append(f"RSI {rsi:.0f}")
        if macd_label and macd_label != "neutral":
            parts.append(f"MACD {macd_label.replace('_', ' ')}")
    if factors.get("momentum_score") is not None and tech.get("momentum_12_1") is not None:
        parts.append(f"12-1m momentum {tech['momentum_12_1'] * 100:+.1f}%")
    if factors.get("value_score") is not None and fund.get("forward_pe"):
        parts.append(f"fwd P/E {fund['forward_pe']:.1f}")
    if abs(sentiment) >= 0.2:
        parts.append(f"news sentiment {sentiment:+.1f}")
    return " · ".join(parts)


def score_ticker(ticker: str, weights: dict[str, float],
                 sentiment_score: float) -> dict[str, Any] | None:
    """Run the full quant pipeline on one ticker. Returns the scored item
    dict (PredictionItem-shaped) or None if the ticker has no usable data."""
    tech = compute_technical_indicators(ticker)
    if not tech.get("available"):
        logger.info("Skipping %s — no OHLCV history", ticker)
        return None
    fund = get_fundamental_data(ticker)
    factor_scores = compute_factor_scores(ticker, tech=tech, fund=fund)

    factors_for_composite = {
        "momentum_score": factor_scores.get("momentum_score"),
        "value_score": factor_scores.get("value_score"),
        "volatility_score": factor_scores.get("volatility_score"),
        "quality_score": factor_scores.get("quality_score"),
        "technical_score": factor_scores.get("technical_score"),
        "sentiment_score": sentiment_score,
    }
    composite, contributions = _weighted_score(factors_for_composite, weights)
    if composite is None:
        return None

    timeframe_days = estimate_timeframe_days(tech, target_pct=2.0)
    threshold_pct = adaptive_threshold_pct(tech, timeframe_days)
    confidence_pct = composite_to_confidence(composite)
    direction = classify_direction(composite, confidence_pct)
    pred_change = expected_change_pct(composite, tech.get("realized_vol_daily"), timeframe_days)

    last_close = tech.get("last_close")
    ci_low = ci_high = None
    if last_close and tech.get("realized_vol_daily"):
        sigma_move = tech["realized_vol_daily"] * math.sqrt(timeframe_days) * last_close
        midpoint = last_close + (pred_change or 0) / 100.0 * last_close
        ci_low = round(midpoint - sigma_move, 2)
        ci_high = round(midpoint + sigma_move, 2)

    thesis = build_thesis(ticker, tech, fund, factor_scores, sentiment_score, direction)

    return {
        "ticker": ticker,
        "direction": direction,
        "timeframe_days": timeframe_days,
        "confidence_pct": confidence_pct,
        "thesis": thesis,
        "model_version": MODEL_VERSION,
        "composite_score": round(composite, 4),
        "momentum_score": factor_scores.get("momentum_score"),
        "value_score": factor_scores.get("value_score"),
        "volatility_score": factor_scores.get("volatility_score"),
        "quality_score": factor_scores.get("quality_score"),
        "technical_score": factor_scores.get("technical_score"),
        "sentiment_score": sentiment_score,
        "rsi_at_prediction": tech.get("rsi_14"),
        "macd_signal_at_prediction": tech.get("macd_signal_label", ""),
        "predicted_change_pct": pred_change,
        "confidence_interval_low": ci_low,
        "confidence_interval_high": ci_high,
        "threshold_pct": round(threshold_pct, 2),
        "price_at_prediction": last_close,
        "contributions": contributions,
    }


# ---------------------------------------------------------------------------
# Top-level pipeline
# ---------------------------------------------------------------------------

def run_quantitative_pipeline(
    db,
    raw_articles: list[dict[str, Any]] | None,
    recent_predictions: list[dict[str, Any]] | None,
    top_n: int = 5,
) -> list[dict[str, Any]]:
    """End-to-end: discover candidates → score each → keep the strongest signals.

    Returns the top N items by |composite_score|, sorted by composite descending
    (most-bullish first, most-bearish last)."""
    candidates = discover_candidate_tickers(db, raw_articles, recent_predictions)
    if not candidates:
        return []

    weights = load_weights(db)
    sentiment = score_news_sentiment(raw_articles or [], candidates)

    scored: list[dict[str, Any]] = []
    for ticker in candidates:
        try:
            item = score_ticker(ticker, weights, sentiment.get(ticker, 0.0))
            if item is not None:
                scored.append(item)
        except Exception:
            logger.exception("Scoring failed for %s — skipping", ticker)
        # be polite to yfinance
        time.sleep(0.2)

    if not scored:
        return []

    # Keep the top N by absolute composite (i.e. strongest conviction either way)
    scored.sort(key=lambda x: abs(x["composite_score"]), reverse=True)
    selected = scored[:top_n]
    # Present them by composite descending so bulls appear before bears
    selected.sort(key=lambda x: x["composite_score"], reverse=True)
    return selected


# ---------------------------------------------------------------------------
# Learning loop — fit factor weights against verified history
# ---------------------------------------------------------------------------

FACTOR_COLUMNS = [
    "momentum_score", "value_score", "volatility_score",
    "quality_score", "sentiment_score",
]
# Note: technical_score is intentionally NOT learned — it overlaps heavily
# with momentum_score and confuses the fit.


def fit_weights_from_history(db, model_version: str = MODEL_VERSION,
                             min_samples: int = 25) -> dict[str, Any]:
    """Fit factor weights from verified PredictionItem history.

    Trains a small LogisticRegression where:
      X = factor scores at prediction time (signed by direction so bear calls
          get features inverted, putting all hits on the +ve side)
      y = 1 if outcome == "hit", 0 if "miss"

    The learned coefficients (absolute values, normalized to sum to ~1) become
    the new factor weights. Items with outcome == "expired" or None are skipped.
    """
    from ..database import PredictionItem

    rows = (
        db.query(PredictionItem)
        .filter(PredictionItem.model_version == model_version)
        .filter(PredictionItem.outcome.in_(["hit", "miss"]))
        .all()
    )
    samples = []
    for r in rows:
        feats = []
        any_missing = False
        for col in FACTOR_COLUMNS:
            v = getattr(r, col, None)
            if v is None:
                any_missing = True
                break
            feats.append(float(v))
        if any_missing:
            continue
        # Flip the sign for bear predictions so hits always look 'good'.
        if r.direction == "bear":
            feats = [-f for f in feats]
        elif r.direction == "hold":
            continue  # holds don't fit a directional regression cleanly
        samples.append((feats, 1 if r.outcome == "hit" else 0))

    if len(samples) < min_samples:
        return {
            "status": "insufficient_data",
            "samples": len(samples),
            "min_required": min_samples,
        }

    try:
        import numpy as np
        from sklearn.linear_model import LogisticRegression

        X = np.array([s[0] for s in samples])
        y = np.array([s[1] for s in samples])
        # Need both classes present for logistic regression to converge
        if len(set(y.tolist())) < 2:
            return {"status": "no_class_variance", "samples": len(samples)}

        clf = LogisticRegression(max_iter=500, C=1.0)
        clf.fit(X, y)
        coefs = clf.coef_[0]
        # Take absolute coefficients as importances, normalize to sum to 1
        importances = np.abs(coefs)
        total = importances.sum()
        if total == 0:
            return {"status": "degenerate_fit", "samples": len(samples)}
        normalized = importances / total

        new_weights = dict(zip(FACTOR_COLUMNS, normalized.tolist()))
        # Keep technical_score weight at its default — not part of the fit
        new_weights["technical_score"] = DEFAULT_WEIGHTS["technical_score"]
        # Renormalize so everything sums to ~1 again
        total_with_tech = sum(new_weights.values())
        if total_with_tech > 0:
            new_weights = {k: v / total_with_tech for k, v in new_weights.items()}

        save_weights(
            db, new_weights, samples=len(samples),
            notes=f"LogisticRegression fit on {len(samples)} verified items",
            model_version=model_version,
        )
        return {
            "status": "fitted",
            "samples": len(samples),
            "weights": new_weights,
            "train_accuracy": float(clf.score(X, y)),
        }
    except Exception as e:
        logger.exception("Weight fitting failed")
        return {"status": "error", "error": str(e), "samples": len(samples)}


# ---------------------------------------------------------------------------
# Backtesting
# ---------------------------------------------------------------------------

def backtest_model(db, start_date: str, end_date: str,
                   model_version: str = MODEL_VERSION) -> dict[str, Any]:
    """Replay accuracy stats against PredictionItem rows in [start, end].

    This is a 'paper backtest' — it measures how this model version did on
    its own historical predictions. A true walk-forward backtest would need
    point-in-time OHLCV reconstruction and is intentionally out of scope.
    """
    from ..database import DailyPrediction, PredictionItem

    items = (
        db.query(PredictionItem)
        .join(DailyPrediction, PredictionItem.prediction_id == DailyPrediction.id)
        .filter(DailyPrediction.date >= start_date)
        .filter(DailyPrediction.date <= end_date)
        .filter(PredictionItem.model_version == model_version)
        .filter(PredictionItem.outcome.in_(["hit", "miss"]))
        .all()
    )
    if not items:
        return {
            "model_version": model_version,
            "start_date": start_date,
            "end_date": end_date,
            "samples": 0,
            "hits": 0,
            "accuracy_pct": None,
            "avg_actual_change_pct": None,
            "by_direction": {},
        }
    hits = sum(1 for i in items if i.outcome == "hit")
    avg_change = sum((i.actual_change_pct or 0) for i in items) / len(items)
    by_dir: dict[str, dict[str, Any]] = {}
    for d in ("bull", "bear", "hold"):
        subset = [i for i in items if i.direction == d]
        if not subset:
            continue
        sub_hits = sum(1 for i in subset if i.outcome == "hit")
        by_dir[d] = {
            "samples": len(subset),
            "hits": sub_hits,
            "accuracy_pct": round(sub_hits / len(subset) * 100, 1),
        }
    return {
        "model_version": model_version,
        "start_date": start_date,
        "end_date": end_date,
        "samples": len(items),
        "hits": hits,
        "accuracy_pct": round(hits / len(items) * 100, 1),
        "avg_actual_change_pct": round(avg_change, 2),
        "by_direction": by_dir,
    }


def record_model_performance_snapshot(db, model_version: str = MODEL_VERSION) -> dict[str, Any]:
    """Snapshot the model's cumulative performance into ModelPerformance.
    Called from the scheduler after each verification pass."""
    from ..database import ModelPerformance, PredictionItem

    items = (
        db.query(PredictionItem)
        .filter(PredictionItem.model_version == model_version)
        .filter(PredictionItem.outcome.in_(["hit", "miss"]))
        .all()
    )
    if not items:
        return {"status": "no_data", "model_version": model_version}

    hits = sum(1 for i in items if i.outcome == "hit")
    avg_conf = sum((i.confidence_pct or 0) for i in items) / len(items)
    avg_change = sum((i.actual_change_pct or 0) for i in items) / len(items)
    weights_json = json.dumps(load_weights(db, model_version=model_version))

    snap = ModelPerformance(
        model_version=model_version,
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        total_predictions=len(items),
        hits=hits,
        accuracy_pct=round(hits / len(items) * 100, 2),
        avg_confidence=round(avg_conf, 2),
        avg_actual_change=round(avg_change, 2),
        factor_weights_json=weights_json,
    )
    db.add(snap)
    db.commit()
    return {
        "status": "recorded",
        "model_version": model_version,
        "samples": len(items),
        "accuracy_pct": snap.accuracy_pct,
    }
