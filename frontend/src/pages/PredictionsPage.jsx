import { useState, useEffect, useRef, useCallback } from "react";
import {
  fetchPredictions,
  fetchPredictionAccuracy,
  triggerDigest,
  fetchDigestStatus,
} from "../services/api";
import { useLanguage } from "../contexts/LanguageContext";
import {
  Loader2,
  TrendingUp,
  ChevronDown,
  ChevronRight,
  Zap,
  RefreshCw,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import AccuracyBadge from "../components/AccuracyBadge";
import PredictionItemsTable from "../components/PredictionItemsTable";

export default function PredictionsPage() {
  const { lang } = useLanguage();
  const [predictions, setPredictions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [overallAccuracy, setOverallAccuracy] = useState(null);
  const pollRef = useRef(null);

  const loadPredictions = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchPredictions(0, 60);
      setPredictions(data);
      if (data.length > 0) setExpandedId(data[0].id);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startPolling = useCallback(() => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const { running } = await fetchDigestStatus();
        if (!running) {
          stopPolling();
          setGenerating(false);
          await loadPredictions();
        }
      } catch {
        /* ignore */
      }
    }, 10000);
  }, [stopPolling, loadPredictions]);

  const handleGenerate = async (force = false) => {
    setGenerating(true);
    try {
      const res = await triggerDigest(force);
      if (res.status === "already_running") {
        startPolling();
        return;
      }
      startPolling();
    } catch {
      setGenerating(false);
    }
  };

  useEffect(() => {
    loadPredictions();
    fetchPredictionAccuracy()
      .then(setOverallAccuracy)
      .catch(() => {});
    fetchDigestStatus()
      .then(({ running }) => {
        if (running) {
          setGenerating(true);
          startPolling();
        }
      })
      .catch(() => {});
    return stopPolling;
  }, [loadPredictions, startPolling, stopPolling]);

  const todayStr = new Date().toISOString().split("T")[0];
  const hasToday = predictions.length > 0 && predictions[0].date === todayStr;

  if (loading && !generating) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="h-5 w-5 rounded-full border-2 border-stone-300 border-t-accent animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-10 animate-fade-in">
      {/* Header */}
      <div className="flex items-end justify-between border-b border-stone-200 dark:border-stone-800 pb-6">
        <div>
          <h2 className="font-serif text-4xl tracking-tight text-stone-900 dark:text-stone-100">
            {lang === "en" ? "Predictions" : "\u9884\u6D4B"}
          </h2>
          <p className="mt-1 text-sm text-stone-500 dark:text-stone-500 font-light">
            {lang === "en"
              ? "AI-powered market analysis & forecasts"
              : "AI\u9A71\u52A8\u7684\u5E02\u573A\u5206\u6790\u4E0E\u9884\u6D4B"}
          </p>
          {overallAccuracy?.total_verified > 0 && (
            <div className="mt-2 flex items-center gap-2 text-xs text-stone-500 dark:text-stone-500">
              <span className="font-light">
                {lang === "en" ? "Overall accuracy:" : "\u6574\u4F53\u51C6\u786E\u7387\uFF1A"}
              </span>
              <AccuracyBadge
                hits={overallAccuracy.hits}
                verified={overallAccuracy.total_verified}
                pct={overallAccuracy.accuracy_pct}
              />
              <span className="text-stone-300 dark:text-stone-700">
                ({overallAccuracy.total_verified}{" "}
                {lang === "en" ? "verified calls" : "\u5DF2\u9A8C\u8BC1\u9884\u6D4B"})
              </span>
            </div>
          )}
        </div>

        <div className="shrink-0">
          {generating ? (
            <div className="flex items-center gap-2 text-sm text-stone-500 dark:text-stone-400">
              <Loader2 size={14} className="animate-spin" />
              <span className="font-light">
                {lang === "en" ? "Generating\u2026" : "\u751F\u6210\u4E2D\u2026"}
              </span>
            </div>
          ) : hasToday ? (
            <button
              onClick={() => handleGenerate(true)}
              className="flex items-center gap-1.5 text-sm text-stone-500 hover:text-accent dark:hover:text-amber-500 transition-colors"
            >
              <RefreshCw size={14} strokeWidth={1.5} />
              {lang === "en" ? "Regenerate" : "\u91CD\u65B0\u751F\u6210"}
            </button>
          ) : (
            <button
              onClick={() => handleGenerate(false)}
              className="flex items-center gap-1.5 text-sm font-medium text-accent dark:text-amber-500 hover:text-accent-dark dark:hover:text-amber-400 transition-colors"
            >
              <Zap size={14} strokeWidth={1.5} />
              {lang === "en" ? "Generate Today" : "\u751F\u6210\u4ECA\u65E5\u9884\u6D4B"}
            </button>
          )}
        </div>
      </div>

      {/* Generating notice */}
      {generating && (
        <div className="border-l-2 border-accent/40 pl-4 py-2 animate-fade-in">
          <p className="text-sm text-stone-600 dark:text-stone-400 font-light">
            {lang === "en"
              ? "Generating predictions. Page will auto-refresh when done."
              : "\u6B63\u5728\u751F\u6210\u9884\u6D4B\u3002\u5B8C\u6210\u540E\u9875\u9762\u4F1A\u81EA\u52A8\u5237\u65B0\u3002"}
          </p>
        </div>
      )}

      {/* Empty state */}
      {predictions.length === 0 && !generating && (
        <div className="text-center py-20">
          <p className="font-serif text-xl italic text-stone-400 dark:text-stone-600">
            {lang === "en" ? "No predictions yet." : "\u6682\u65E0\u9884\u6D4B\u3002"}
          </p>
        </div>
      )}

      {/* Prediction list */}
      <div className="space-y-0">
        {predictions.map((p) => {
          const isExpanded = expandedId === p.id;
          const content = lang === "en" ? p.prediction_en : p.prediction_cn;
          return (
            <article
              key={p.id}
              className="border-b border-stone-100 dark:border-stone-800/50 last:border-0"
            >
              <button
                onClick={() => setExpandedId(isExpanded ? null : p.id)}
                className="w-full flex items-center justify-between py-4 text-left group"
              >
                <div className="flex items-center gap-3">
                  <time className="text-xs font-mono tracking-wider text-stone-400 dark:text-stone-600 min-w-[80px]">
                    {p.date}
                  </time>
                  {p.accuracy?.verified > 0 && (
                    <AccuracyBadge
                      hits={p.accuracy.hits}
                      verified={p.accuracy.verified}
                      pct={p.accuracy.pct}
                    />
                  )}
                  {p.id === predictions[0]?.id && (
                    <span className="text-[10px] font-mono tracking-widest uppercase text-accent dark:text-amber-500">
                      {lang === "en" ? "Latest" : "\u6700\u65B0"}
                    </span>
                  )}
                </div>
                <span className="text-stone-300 dark:text-stone-700">
                  {isExpanded ? (
                    <ChevronDown size={16} strokeWidth={1.5} />
                  ) : (
                    <ChevronRight size={16} strokeWidth={1.5} />
                  )}
                </span>
              </button>
              {isExpanded && (
                <div className="pb-6 animate-fade-in">
                  <div className="prose prose-sm prose-stone dark:prose-invert max-w-none">
                    <ReactMarkdown
                      components={{
                        a: ({ href, children }) => (
                          <a
                            href={href}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            {children}
                          </a>
                        ),
                      }}
                    >
                      {content}
                    </ReactMarkdown>
                  </div>
                  {p.items?.length > 0 && (
                    <PredictionItemsTable items={p.items} lang={lang} />
                  )}
                </div>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}
