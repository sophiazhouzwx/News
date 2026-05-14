import { useState } from "react";
import { submitMedia } from "../services/api";
import { useLanguage } from "../contexts/LanguageContext";
import { ArrowRight, Loader2 } from "lucide-react";

export default function MediaForm({ onSubmitted }) {
  const { lang } = useLanguage();
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!url.trim()) return;

    setSubmitting(true);
    setError(null);
    try {
      const result = await submitMedia(url.trim(), title.trim());
      setUrl("");
      setTitle("");
      onSubmitted?.(result);
    } catch (err) {
      setError(
        lang === "en"
          ? "Failed to submit. Please try again."
          : "\u63D0\u4EA4\u5931\u8D25\uFF0C\u8BF7\u91CD\u8BD5\u3002",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <input
        type="url"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        placeholder={
          lang === "en"
            ? "Paste a YouTube, podcast, or audio URL\u2026"
            : "\u7C98\u8D34YouTube\u3001\u64AD\u5BA2\u6216\u97F3\u9891\u94FE\u63A5\u2026"
        }
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
      {error && (
        <p className="text-xs text-red-600/80 dark:text-red-400/80">{error}</p>
      )}
    </form>
  );
}
