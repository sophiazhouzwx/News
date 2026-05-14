import { useState, useEffect, useCallback } from "react";
import { fetchMediaList, fetchMedia, deleteMedia } from "../services/api";
import { useLanguage } from "../contexts/LanguageContext";
import MediaForm from "../components/MediaForm";
import MediaSummaryCard from "../components/MediaSummaryCard";

export default function MediaPage() {
  const { lang } = useLanguage();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pollingIds, setPollingIds] = useState(new Set());

  const loadItems = useCallback(async () => {
    try {
      const data = await fetchMediaList();
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
          const updated = await fetchMedia(id);
          if (updated.status === "done" || updated.status === "error") {
            setItems((prev) =>
              prev.map((m) => (m.id === id ? updated : m)),
            );
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

  const handleSubmitted = (result) => {
    setItems((prev) => [
      { id: result.id, status: result.status, url: "", title: "", summary_en: "", summary_cn: "", error_message: "", media_type: "unknown", created_at: new Date().toISOString() },
      ...prev,
    ]);
    setPollingIds((prev) => new Set([...prev, result.id]));
    setTimeout(loadItems, 1000);
  };

  const handleDelete = async (id) => {
    try {
      await deleteMedia(id);
      setItems((prev) => prev.filter((m) => m.id !== id));
    } catch {
      /* ignore */
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
          {lang === "en" ? "Summarize Media" : "\u5A92\u4F53\u603B\u7ED3"}
        </h2>
        <p className="mt-1 text-sm text-stone-500 dark:text-stone-500 font-light">
          {lang === "en"
            ? "Paste any video or audio URL for an instant summary"
            : "\u7C98\u8D34\u4EFB\u4F55\u89C6\u9891\u6216\u97F3\u9891\u94FE\u63A5\u5373\u53EF\u83B7\u53D6\u6458\u8981"}
        </p>
      </div>

      <MediaForm onSubmitted={handleSubmitted} />

      <div className="space-y-0">
        {items.length === 0 && (
          <p className="text-center py-12 font-serif text-lg italic text-stone-400 dark:text-stone-600">
            {lang === "en"
              ? "No summaries yet."
              : "\u6682\u65E0\u603B\u7ED3\u3002"}
          </p>
        )}
        {items.map((m) => (
          <MediaSummaryCard
            key={m.id}
            media={m}
            onDelete={() => handleDelete(m.id)}
          />
        ))}
      </div>
    </div>
  );
}
