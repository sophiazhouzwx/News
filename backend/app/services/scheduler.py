import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone

from ..config import TRACKED_PODCASTS, TRACKED_REDNOTE_ACCOUNTS
from ..database import (
    ArticleFeedback, DailyPrediction, Digest, PodcastEpisode,
    LivestreamSummary, PersonalitySpeech, PredictionItem, get_session_factory,
)
from .news_aggregator import aggregate_news
from .podcast_tracker import get_new_episodes_for_all_podcasts
from .personality_tracker import get_new_speeches_for_all_personalities
from .livestream_tracker import get_new_livestreams_for_all_accounts
from .summarizer import (
    summarize_news_digest, summarize_podcast_episode, summarize_livestream,
    generate_daily_prediction, generate_quant_prediction, summarize_media,
)
from .push_service import send_push_to_all

logger = logging.getLogger(__name__)

_running = False
_last_run_report: dict | None = None

# --- Timeouts (seconds) for each stage ---
# Reduced from original values since Whisper now uses faster tiny/small models
# and each transcription has its own multiprocessing timeout internally.
STEP_TIMEOUT_VERIFY = 60            # 1 min for verifying past predictions
STEP_TIMEOUT_NEWS = 120            # 2 min for RSS + Reddit aggregation
STEP_TIMEOUT_NEWS_SUMMARIZE = 120  # 2 min for Claude news summary
STEP_TIMEOUT_PODCAST_TOTAL = 300   # 5 min total for all podcasts (was 10 min)
STEP_TIMEOUT_PODCAST_SINGLE = 180  # 3 min per podcast episode (was 5 min)
STEP_TIMEOUT_SPEECH_TOTAL = 300    # 5 min total for all speeches (was 10 min)
STEP_TIMEOUT_SPEECH_SINGLE = 180   # 3 min per speech (was 5 min)
STEP_TIMEOUT_LIVESTREAM_TOTAL = 300  # 5 min total for livestreams
STEP_TIMEOUT_PREDICTION = 180     # 3 min for prediction generation (extended thinking)
STEP_TIMEOUT_SUMMARIZE_SINGLE = 120  # 2 min per Claude summarization call


def is_running() -> bool:
    return _running


def cancel_running():
    """Admin escape hatch: force-reset the running flag.
    Use when the flag is stuck due to a bug or hung process.
    """
    global _running
    _running = False
    logger.warning("ADMIN: _running flag force-reset to False")


def get_last_run_report() -> dict | None:
    """Return the status report from the most recent digest run."""
    return _last_run_report


def _run_with_timeout(fn, timeout_seconds: int, step_name: str, *args, **kwargs):
    """Run a function with a timeout. Returns (result, error_msg).
    If the function completes, returns (result, None).
    If it times out or errors, returns (None, error_description).
    """
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fn, *args, **kwargs)
        try:
            result = future.result(timeout=timeout_seconds)
            return result, None
        except FuturesTimeoutError:
            msg = f"TIMEOUT: {step_name} exceeded {timeout_seconds}s limit — skipping"
            logger.error(msg)
            return None, msg
        except Exception as e:
            msg = f"ERROR in {step_name}: {e}"
            logger.exception(msg)
            return None, msg


def _build_feedback_summary(db) -> str:
    """Build a text summary of user feedback for the Claude prompt."""
    helpful = (
        db.query(ArticleFeedback.article_title)
        .filter(ArticleFeedback.helpful == True)
        .order_by(ArticleFeedback.created_at.desc())
        .limit(20)
        .all()
    )
    unhelpful = (
        db.query(ArticleFeedback.article_title)
        .filter(ArticleFeedback.helpful == False)
        .order_by(ArticleFeedback.created_at.desc())
        .limit(20)
        .all()
    )
    if not helpful and not unhelpful:
        return ""

    parts = []
    if helpful:
        parts.append("Articles the user found HELPFUL:\n" + "\n".join(f"- {r[0]}" for r in helpful))
    if unhelpful:
        parts.append("Articles the user found NOT HELPFUL:\n" + "\n".join(f"- {r[0]}" for r in unhelpful))
    return "\n\n".join(parts)


def daily_digest_job(force: bool = False):
    """Main job: aggregate news, process podcasts, personalities, predictions, push.

    RESILIENCE POLICY: Each step (news, podcasts, speeches, livestreams, predictions)
    runs independently with its own timeout. If any step fails or times out, the error
    is logged and reported in the final status, but the remaining steps still execute.
    The digest is always saved with whatever content was successfully generated.
    """
    global _running
    if _running:
        logger.info("Digest job already running, skipping")
        return
    _running = True

    start_time = time.time()
    logger.info("Starting daily digest job (force=%s)", force)
    SessionLocal = get_session_factory()
    db = SessionLocal()

    # Track status of each step for the final report
    step_status: dict[str, str] = {}

    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if force:
            existing_digest = db.query(Digest).filter(Digest.date == today).first()
            if existing_digest:
                logger.info("Force mode: deleting existing digest for %s", today)
                db.delete(existing_digest)
                db.commit()
            existing_pred = db.query(DailyPrediction).filter(DailyPrediction.date == today).first()
            if existing_pred:
                logger.info("Force mode: deleting existing prediction for %s", today)
                db.delete(existing_pred)
                db.commit()
        else:
            existing = db.query(Digest).filter(Digest.date == today).first()
            if existing:
                logger.info("Digest for %s already exists, skipping", today)
                return

        # =====================================================================
        # STEP 0: Verify past predictions + learn from history
        # =====================================================================
        logger.info("[0/5] Verifying past predictions...")
        try:
            from .market_data import verify_prediction_items
            verified_result, verr = _run_with_timeout(
                verify_prediction_items, STEP_TIMEOUT_VERIFY,
                "Prediction verification", db
            )
            if verr:
                step_status["verify_predictions"] = verr
            else:
                step_status["verify_predictions"] = f"OK — {verified_result or 0} items verified"
        except Exception as e:
            logger.exception("Prediction verification failed — continuing")
            step_status["verify_predictions"] = f"FAILED: {e}"

        # After verification, try to refit quant factor weights and snapshot
        # cumulative model performance. Both are no-ops without enough data.
        try:
            from .quant_models import fit_weights_from_history, record_model_performance_snapshot
            fit_result = fit_weights_from_history(db)
            step_status["quant_weight_fit"] = f"{fit_result.get('status')}: {fit_result.get('samples', 0)} samples"
            snap = record_model_performance_snapshot(db)
            step_status["quant_perf_snapshot"] = snap.get("status", "unknown")
        except Exception as e:
            logger.exception("Quant learning loop failed — continuing")
            step_status["quant_learning"] = f"FAILED: {e}"

        # =====================================================================
        # STEP 1: News Aggregation
        # =====================================================================
        logger.info("[1/5] Aggregating news...")
        articles = []
        news_summary = {"en": "", "cn": ""}
        try:
            articles_result, err = _run_with_timeout(
                aggregate_news, STEP_TIMEOUT_NEWS, "News aggregation"
            )
            if err:
                step_status["news_fetch"] = err
            else:
                articles = articles_result or []
                step_status["news_fetch"] = f"OK — {len(articles)} articles"

            if articles:
                feedback_text = _build_feedback_summary(db)
                summary_result, err = _run_with_timeout(
                    summarize_news_digest, STEP_TIMEOUT_NEWS_SUMMARIZE,
                    "News summarization", articles, feedback_summary=feedback_text
                )
                if err:
                    step_status["news_summarize"] = err
                else:
                    news_summary = summary_result or {"en": "", "cn": ""}
                    step_status["news_summarize"] = "OK"
            else:
                step_status["news_summarize"] = "SKIPPED — no articles fetched"
        except Exception as e:
            logger.exception("News step failed entirely")
            step_status["news"] = f"FAILED: {e}"

        # =====================================================================
        # STEP 2: Podcasts (each podcast isolated with its own timeout)
        # =====================================================================
        logger.info("[2/5] Processing podcast episodes...")
        episode_ids = []
        try:
            new_episodes_result, err = _run_with_timeout(
                get_new_episodes_for_all_podcasts, STEP_TIMEOUT_PODCAST_TOTAL,
                "Podcast feed polling & download", db
            )
            if err:
                step_status["podcasts_fetch"] = err
                new_episodes = []
            else:
                new_episodes = new_episodes_result or []
                step_status["podcasts_fetch"] = f"OK — {len(new_episodes)} new episodes"

            for ep in new_episodes:
                try:
                    lang = "en"
                    for pc in TRACKED_PODCASTS:
                        if pc["name"] == ep.podcast_name:
                            lang = pc["language"]
                            break

                    result, err = _run_with_timeout(
                        summarize_podcast_episode, STEP_TIMEOUT_SUMMARIZE_SINGLE,
                        f"Summarize podcast '{ep.episode_title[:40]}'",
                        ep.episode_title, ep.transcript, language=lang
                    )
                    if err:
                        step_status[f"podcast_{ep.episode_title[:30]}"] = err
                        continue

                    ep.summary_en = result["en"]
                    ep.summary_cn = result["cn"]
                    ep.summarized_at = datetime.now(timezone.utc)
                    db.commit()
                    episode_ids.append(ep.id)
                except Exception:
                    logger.exception("Failed to summarize episode: %s — continuing with rest", ep.episode_title)
                    step_status[f"podcast_{ep.episode_title[:30]}"] = f"FAILED"
        except Exception as e:
            logger.exception("Podcast step failed entirely — continuing with rest of digest")
            step_status["podcasts"] = f"FAILED: {e}"
            db.rollback()

        # =====================================================================
        # STEP 3: Personality Speeches (each personality isolated)
        # =====================================================================
        logger.info("[3/5] Searching for new speeches/interviews...")
        speech_ids = []
        try:
            speeches_result, err = _run_with_timeout(
                get_new_speeches_for_all_personalities, STEP_TIMEOUT_SPEECH_TOTAL,
                "Speech search & transcription", db
            )
            if err:
                step_status["speeches_fetch"] = err
                new_speeches = []
            else:
                new_speeches = speeches_result or []
                step_status["speeches_fetch"] = f"OK — {len(new_speeches)} new speeches"

            for speech in new_speeches:
                try:
                    result, err = _run_with_timeout(
                        summarize_media, STEP_TIMEOUT_SUMMARIZE_SINGLE,
                        f"Summarize speech '{speech.title[:40]}'",
                        speech.title, speech.transcript, speech.video_url
                    )
                    if err:
                        step_status[f"speech_{speech.title[:30]}"] = err
                        speech.status = "error"
                        db.commit()
                        continue

                    speech.summary_en = result["en"]
                    speech.summary_cn = result["cn"]
                    speech.status = "done"
                    db.commit()
                    speech_ids.append(speech.id)
                except Exception:
                    logger.exception("Failed to summarize speech: %s — continuing", speech.title)
                    speech.status = "error"
                    db.commit()
        except Exception as e:
            logger.exception("Speech step failed entirely — continuing with rest of digest")
            step_status["speeches"] = f"FAILED: {e}"
            db.rollback()

        # =====================================================================
        # STEP 4: Livestreams (each account isolated)
        # =====================================================================
        logger.info("[4/5] Processing Red Note livestreams...")
        livestream_ids = []
        try:
            livestreams_result, err = _run_with_timeout(
                get_new_livestreams_for_all_accounts, STEP_TIMEOUT_LIVESTREAM_TOTAL,
                "Livestream feed polling & download", db
            )
            if err:
                step_status["livestreams_fetch"] = err
                new_livestreams = []
            else:
                new_livestreams = livestreams_result or []
                step_status["livestreams_fetch"] = f"OK — {len(new_livestreams)} new livestreams"

            for ls in new_livestreams:
                try:
                    lang = "cn"
                    for acc in TRACKED_REDNOTE_ACCOUNTS:
                        if acc["name"] == ls.account_name:
                            lang = acc.get("language", "cn")
                            break
                    result, err = _run_with_timeout(
                        summarize_livestream, STEP_TIMEOUT_SUMMARIZE_SINGLE,
                        f"Summarize livestream '{ls.title[:40]}'",
                        ls.title, ls.transcript, language=lang
                    )
                    if err:
                        step_status[f"livestream_{ls.title[:30]}"] = err
                        ls.status = "error"
                        db.commit()
                        continue

                    ls.summary_en = result["en"]
                    ls.summary_cn = result["cn"]
                    ls.status = "done"
                    db.commit()
                    livestream_ids.append(ls.id)
                except Exception:
                    logger.exception("Failed to summarize livestream: %s — continuing", ls.title)
                    ls.status = "error"
                    db.commit()
        except Exception as e:
            logger.exception("Livestream step failed entirely — continuing with rest of digest")
            step_status["livestreams"] = f"FAILED: {e}"
            db.rollback()

        # =====================================================================
        # STEP 5: Predictions
        # =====================================================================
        logger.info("[5/5] Generating daily predictions...")
        try:
            recent_preds = (
                db.query(DailyPrediction)
                .order_by(DailyPrediction.date.desc())
                .limit(5)
                .all()
            )
            history = []
            for p in reversed(recent_preds):
                item_rows = db.query(PredictionItem).filter(
                    PredictionItem.prediction_id == p.id
                ).all()
                history.append({
                    "date": p.date,
                    "prediction_en": p.prediction_en,
                    "items": [
                        {"ticker": i.ticker, "direction": i.direction, "outcome": i.outcome}
                        for i in item_rows
                    ],
                })

            from .market_data import get_market_context
            market_ctx = ""
            try:
                market_ctx = get_market_context()
            except Exception:
                logger.exception("Failed to get market context — continuing without it")

            # --- 5a. Legacy LLM-driven prediction (source="news_discovery")
            pred_result, err = _run_with_timeout(
                generate_daily_prediction, STEP_TIMEOUT_PREDICTION,
                "Daily prediction generation (LLM)",
                news_summary["en"],
                recent_predictions=history,
                raw_articles=articles,
                market_context=market_ctx,
            )
            if err:
                step_status["predictions"] = err
                prediction = None
            else:
                prediction = DailyPrediction(
                    date=today,
                    prediction_en=pred_result["en"],
                    prediction_cn=pred_result["cn"],
                )
                db.add(prediction)
                db.commit()

                from .market_data import get_price
                items_saved = 0
                for item_data in pred_result.get("items", []):
                    ticker = item_data.get("ticker", "").upper().strip()
                    if not ticker:
                        continue
                    entry_price = get_price(ticker)
                    pi = PredictionItem(
                        prediction_id=prediction.id,
                        ticker=ticker,
                        direction=item_data.get("direction", "hold"),
                        timeframe_days=int(item_data.get("timeframe_days", 14)),
                        confidence_pct=item_data.get("confidence_pct"),
                        thesis=item_data.get("thesis", ""),
                        price_at_prediction=entry_price,
                        source="news_discovery",
                    )
                    db.add(pi)
                    items_saved += 1
                db.commit()

                step_status["predictions"] = f"OK — {items_saved} LLM stock calls saved"
                logger.info("LLM prediction saved for %s with %d items", today, items_saved)

            # --- 5b. Quant model prediction (source="quant_v1") — runs in parallel
            try:
                from .quant_models import (
                    MODEL_VERSION, run_quantitative_pipeline,
                )

                quant_items, qerr = _run_with_timeout(
                    run_quantitative_pipeline, STEP_TIMEOUT_PREDICTION,
                    "Quant model scoring",
                    db, articles, history,
                )
                if qerr:
                    step_status["quant_predictions"] = qerr
                elif not quant_items:
                    step_status["quant_predictions"] = "SKIPPED — no scorable candidates"
                else:
                    # Ask Claude to format the quant output as a narrative
                    quant_report, rerr = _run_with_timeout(
                        generate_quant_prediction, STEP_TIMEOUT_PREDICTION,
                        "Quant report formatting",
                        quant_items, market_ctx,
                    )
                    if rerr:
                        logger.warning("Quant report formatting failed: %s", rerr)
                        quant_report = {"en": "", "cn": ""}

                    # If the LLM step failed, create a standalone DailyPrediction
                    # to hang the quant items off of so they're still queryable.
                    if prediction is None:
                        prediction = DailyPrediction(
                            date=today,
                            prediction_en=quant_report.get("en", ""),
                            prediction_cn=quant_report.get("cn", ""),
                        )
                        db.add(prediction)
                        db.commit()
                    else:
                        # Append quant narrative below the LLM narrative so both
                        # are viewable in the same prediction record.
                        if quant_report.get("en"):
                            prediction.prediction_en = (
                                (prediction.prediction_en or "") +
                                "\n\n---\n\n## Quant Model (quant_v1)\n\n" +
                                quant_report["en"]
                            )
                        if quant_report.get("cn"):
                            prediction.prediction_cn = (
                                (prediction.prediction_cn or "") +
                                "\n\n---\n\n## 量化模型 (quant_v1)\n\n" +
                                quant_report["cn"]
                            )
                        db.commit()

                    qsaved = 0
                    for it in quant_items:
                        pi = PredictionItem(
                            prediction_id=prediction.id,
                            ticker=it["ticker"],
                            direction=it["direction"],
                            timeframe_days=int(it["timeframe_days"]),
                            confidence_pct=it.get("confidence_pct"),
                            thesis=it.get("thesis", ""),
                            source=MODEL_VERSION,
                            price_at_prediction=it.get("price_at_prediction"),
                            model_version=it.get("model_version", MODEL_VERSION),
                            composite_score=it.get("composite_score"),
                            momentum_score=it.get("momentum_score"),
                            value_score=it.get("value_score"),
                            volatility_score=it.get("volatility_score"),
                            quality_score=it.get("quality_score"),
                            sentiment_score=it.get("sentiment_score"),
                            rsi_at_prediction=it.get("rsi_at_prediction"),
                            macd_signal_at_prediction=it.get("macd_signal_at_prediction", ""),
                            confidence_interval_low=it.get("confidence_interval_low"),
                            confidence_interval_high=it.get("confidence_interval_high"),
                            predicted_change_pct=it.get("predicted_change_pct"),
                            threshold_pct=it.get("threshold_pct"),
                        )
                        db.add(pi)
                        qsaved += 1
                    db.commit()
                    step_status["quant_predictions"] = f"OK — {qsaved} quant stock calls saved"
                    logger.info("Quant prediction saved for %s with %d items", today, qsaved)
            except Exception as e:
                logger.exception("Quant pipeline failed — continuing")
                step_status["quant_predictions"] = f"FAILED: {e}"
                db.rollback()
        except Exception as e:
            logger.exception("Prediction generation failed — continuing to save digest")
            step_status["predictions"] = f"FAILED: {e}"
            db.rollback()

        # =====================================================================
        # SAVE DIGEST (always — even if some steps failed)
        # =====================================================================
        digest = Digest(
            date=today,
            summary_en=news_summary["en"],
            summary_cn=news_summary["cn"],
            raw_articles_json=json.dumps(articles, default=str),
            podcast_episode_ids_json=json.dumps(episode_ids),
        )
        db.add(digest)
        db.commit()

        elapsed = time.time() - start_time

        # --- Final status report ---
        global _last_run_report
        failures = {k: v for k, v in step_status.items() if not v.startswith("OK")}
        _last_run_report = {
            "date": today,
            "elapsed_seconds": round(elapsed, 1),
            "articles": len(articles),
            "podcasts": len(episode_ids),
            "speeches": len(speech_ids),
            "livestreams": len(livestream_ids),
            "steps": step_status,
            "failures": failures,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info("=" * 60)
        logger.info("DIGEST JOB COMPLETED in %.1fs for %s", elapsed, today)
        logger.info("  Articles: %d | Podcasts: %d | Speeches: %d | Livestreams: %d",
                     len(articles), len(episode_ids), len(speech_ids), len(livestream_ids))
        if failures:
            logger.warning("  ISSUES ENCOUNTERED:")
            for step, status in failures.items():
                logger.warning("    - %s: %s", step, status)
        else:
            logger.info("  All steps completed successfully")
        logger.info("=" * 60)

        # --- Push notification ---
        title = "Your Morning Digest / 今日早报"
        parts_en = [f"{len(articles)} tech news"]
        parts_cn = [f"{len(articles)}条科技新闻"]
        if episode_ids:
            parts_en.append(f"{len(episode_ids)} podcasts")
            parts_cn.append(f"{len(episode_ids)}期播客")
        if speech_ids:
            parts_en.append(f"{len(speech_ids)} speeches")
            parts_cn.append(f"{len(speech_ids)}场演讲")
        if livestream_ids:
            parts_en.append(f"{len(livestream_ids)} livestreams")
            parts_cn.append(f"{len(livestream_ids)}场直播回放")
        body = " | ".join(parts_en) + "\n" + " | ".join(parts_cn)
        sent = send_push_to_all(db, title=title, body=body, url="/")
        logger.info("Push sent to %d subscribers", sent)

    except Exception:
        logger.exception("Daily digest job failed")
    finally:
        _running = False
        db.close()
