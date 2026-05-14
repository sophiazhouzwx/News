import { useState, useEffect, useCallback } from "react";
import {
  fetchLivestreams,
  fetchLivestream,
  submitLivestream,
} from "../services/api";
import { useLanguage } from "../contexts/LanguageContext";
import LivestreamCard from "../components/LivestreamCard";
import { Loader2, ArrowRight } from "lucide-react";

export default function LivestreamsPage() {
  const { lang } = useLanguage();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [pollingIds, setPollingIds] = useState(new Set());

  const loadItems = useCallback(async () => {
    try {
      const data = await fetchLivestreams();
      setItems(data);
      const inProgress = data.filter(
        (m) => m.status === "pending" || m.status === "processing",
      );
      setPollingIds(new Set(inProgress.map((m) => m.id)));
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadItems();
  }, [loadItems]);

  useEffect(() => {
    if (pollingIds.size === 0) return;
    const interval = setInterval(async () => {
      for (const id of pollingIds) {
        try {
          const updated = await fetchLivestream(id);
          if (updated.status === "done" || updated.status === "error") {
            setItems((prev) => prev.map((m) => (m.id === id ? updated : m)));
            setPollingIds((prev) => {
              const next = new Set(prev);
              next.delete(id);
              return next;
            });
          }
        } catch {
          /* ignore */
        }
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [pollingIds]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!url.trim()) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const result = await submitLivestream(url.trim(), title.trim());
      setUrl("");
      setTitle("");
      setPollingIds((prev) => new Set([...prev, result.id]));
      setTimeout(loadItems, 1000);
    } catch {
      setSubmitError(
        lang === "en" ? "Failed to submit. Please try again." : "\u63D0\u4EA4\u5931\u8D25\uFF0C\u8BF7\u91CD\u8BD5\u3002",
      );
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="h-5 w-5 rounded-full border-2 border-stone-300 border-t-accent animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-10 animate-fade-in">
      <div className="border-b border-stone-200 dark:border-stone-800 pb-6">
        <h2 className="font-serif text-4xl tracking-tight text-stone-900 dark:text-stone-100">
          {lang === "en" ? "Livestreams" : "\u76F4\u64AD\u56DE\u653E"}
        </h2>
        <p className="mt-1 text-sm text-stone-500 dark:text-stone-500 font-light">
          {lang === "en"
            ? "Summaries of livestream replays"
            : "\u76F4\u64AD\u56DE\u653E\u6458\u8981"}
        </p>
      </div>

      {/* Submit form */}
      <form onSubmit={handleSubmit} className="space-y-3">
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://www.xiaohongshu.com/explore/..."
          required
          className="w-full border-b border-stone-300 dark:border-stone-700 bg-transparent px-0 py-3 text-sm placeholder-stone-400 dark:placeholder-stone-600 focus:border-accent dark:focus:border-amber-500 outline-none transition-colors"
        />
        <div className="flex gap-3 items-center">
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={lang === "en" ? "Title (optional)" : "\u6807\u9898\uFF08\u53EF\u9009\uFF09"}
            className="flex-1 border-b border-stone-200 dark:border-stone-800 bg-transparent px-0 py-2.5 text-sm placeholder-stone-400 dark:placeholder-stone-600 focus:border-accent dark:focus:border-amber-500 outline-none transition-colors"
          />
          <button
            type="submit"
            disabled={submitting || !url.trim()}
            className="flex items-center gap-2 text-sm font-medium text-accent dark:text-amber-500 hover:text-accent-dark dark:hover:text-amber-400 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            {submitting ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <ArrowRight size={14} strokeWidth={1.5} />
            )}
            {lang === "en" ? "Summarize" : "\u603B\u7ED3"}
          </button>
        </div>
        {submitError && (
          <p className="text-xs text-red-600/80 dark:text-red-400/80">{submitError}</p>
        )}
      </form>

      {/* Items */}
      <div className="space-y-6">
        {items.length === 0 && (
          <p className="text-center py-12 font-serif text-lg italic text-stone-400 dark:text-stone-600">
            {lang === "en"
              ? "No livestream summaries yet."
              : "\u6682\u65E0\u76F4\u64AD\u6458\u8981\u3002"}
          </p>
        )}
        {items.map((ls) => (
          <LivestreamCard key={ls.id} livestream={ls} />
        ))}
      </div>
    </div>
  );
}
