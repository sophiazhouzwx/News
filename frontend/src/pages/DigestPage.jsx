import { useState, useEffect, useRef, useCallback } from "react";
import {
  fetchLatestDigest,
  fetchDigests,
  triggerDigest,
  fetchDigestStatus,
  cancelDigest,
} from "../services/api";
import { useLanguage } from "../contexts/LanguageContext";
import DigestCard from "../components/DigestCard";
import { Loader2, RefreshCw, ChevronDown, Zap } from "lucide-react";

export default function DigestPage() {
  const { lang } = useLanguage();
  const [latest, setLatest] = useState(null);
  const [older, setOlder] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showOlder, setShowOlder] = useState(false);
  const [error, setError] = useState(null);
  const [generating, setGenerating] = useState(false);
  const pollRef = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await fetchLatestDigest();
      setLatest(d);
    } catch (err) {
      if (err.response?.status === 404) {
        setLatest(null);
      } else {
        setError(lang === "en" ? "Failed to load digest" : "\u52A0\u8F7D\u6458\u8981\u5931\u8D25");
      }
    } finally {
      setLoading(false);
    }
  }, [lang]);

  const loadOlder = async () => {
    try {
      const list = await fetchDigests(1, 10);
      setOlder(list);
      setShowOlder(true);
    } catch {
      /* ignore */
    }
  };

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
          await load();
        }
      } catch {
        /* ignore */
      }
    }, 10000);
  }, [stopPolling, load]);

  const handleCancel = async () => {
    try {
      await cancelDigest();
      setGenerating(false);
      stopPolling();
    } catch {
      /* ignore */
    }
  };

  const handleGenerate = async (force = false) => {
    setGenerating(true);
    setError(null);
    try {
      const res = await triggerDigest(force);
      if (res.status === "already_running") {
        startPolling();
        return;
      }
      startPolling();
    } catch {
      setError(lang === "en" ? "Failed to start generation" : "\u542F\u52A8\u751F\u6210\u5931\u8D25");
      setGenerating(false);
    }
  };

  useEffect(() => {
    load();
    fetchDigestStatus()
      .then(({ running }) => {
        if (running) {
          setGenerating(true);
          startPolling();
        }
      })
      .catch(() => {});
    return stopPolling;
  }, [load, startPolling, stopPolling]);

  const todayStr = new Date().toISOString().split("T")[0];
  const hasToday = latest?.date === todayStr;

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
            {lang === "en" ? "Daily Digest" : "\u6BCF\u65E5\u6458\u8981"}
          </h2>
          <p className="mt-1 text-sm text-stone-500 dark:text-stone-500 font-light">
            {lang === "en"
              ? "Your curated morning briefing"
              : "\u7CBE\u9009\u6BCF\u65E5\u65E9\u62A5"}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {generating ? (
            <>
              <div className="flex items-center gap-2 text-sm text-stone-500 dark:text-stone-400">
                <Loader2 size={14} className="animate-spin" />
                <span className="font-light">
                  {lang === "en" ? "Generating\u2026" : "\u751F\u6210\u4E2D\u2026"}
                </span>
              </div>
              <button
                onClick={handleCancel}
                className="text-xs text-stone-400 hover:text-red-600 dark:hover:text-red-400 underline underline-offset-2 transition-colors"
              >
                {lang === "en" ? "Cancel" : "\u53D6\u6D88"}
              </button>
            </>
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
              {lang === "en" ? "Generate Today\u2019s Digest" : "\u751F\u6210\u4ECA\u65E5\u6458\u8981"}
            </button>
          )}
        </div>
      </div>

      {/* Generating notice */}
      {generating && (
        <div className="border-l-2 border-accent/40 pl-4 py-2 animate-fade-in">
          <p className="text-sm text-stone-600 dark:text-stone-400 font-light leading-relaxed">
            {lang === "en"
              ? "Fetching news, podcasts, speeches, and predictions. This page will auto-refresh when done."
              : "\u6B63\u5728\u83B7\u53D6\u65B0\u95FB\u3001\u64AD\u5BA2\u3001\u6F14\u8BB2\u548C\u9884\u6D4B\u3002\u5B8C\u6210\u540E\u9875\u9762\u4F1A\u81EA\u52A8\u5237\u65B0\u3002"}
          </p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="border-l-2 border-red-400/60 pl-4 py-2 text-sm text-red-700 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Empty state */}
      {!latest && !error && !generating && (
        <div className="text-center py-20 animate-fade-in">
          <p className="font-serif text-xl text-stone-400 dark:text-stone-600 italic">
            {lang === "en"
              ? "No digest yet."
              : "\u6682\u65E0\u6458\u8981\u3002"}
          </p>
          <p className="mt-2 text-sm text-stone-400 dark:text-stone-600">
            {lang === "en"
              ? "Click the button above to generate one."
              : "\u70B9\u51FB\u4E0A\u65B9\u6309\u94AE\u751F\u6210\u3002"}
          </p>
        </div>
      )}

      {/* Latest digest */}
      {latest && <DigestCard digest={latest} />}

      {/* Load older */}
      {latest && !showOlder && (
        <button
          onClick={loadOlder}
          className="flex items-center gap-1.5 mx-auto text-xs text-stone-400 hover:text-stone-600 dark:hover:text-stone-300 tracking-wide uppercase transition-colors"
        >
          <ChevronDown size={14} strokeWidth={1.5} />
          {lang === "en" ? "Previous digests" : "\u67E5\u770B\u5386\u53F2\u6458\u8981"}
        </button>
      )}

      {showOlder && (
        <div className="space-y-8">
          {older.map((d) => (
            <DigestCard key={d.id} digest={d} />
          ))}
        </div>
      )}
    </div>
  );
}
