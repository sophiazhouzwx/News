import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { useLanguage } from "../contexts/LanguageContext";
import {
  Loader2,
  ExternalLink,
  ChevronDown,
  ChevronRight,
  X,
} from "lucide-react";

export default function MediaSummaryCard({ media, onDelete }) {
  const { lang } = useLanguage();
  const [open, setOpen] = useState(false);
  const content = lang === "en" ? media.summary_en : media.summary_cn;
  const isDone = media.status === "done";
  const isProcessing = media.status === "pending" || media.status === "processing";

  return (
    <div className="group border-b border-stone-200 dark:border-stone-800 pb-4 last:border-0 last:pb-0 animate-slide-up">
      <div className="flex items-center gap-3 py-2">
        {isDone ? (
          <button
            onClick={() => setOpen(!open)}
            className="shrink-0 text-stone-300 dark:text-stone-700"
          >
            {open ? (
              <ChevronDown size={14} strokeWidth={1.5} />
            ) : (
              <ChevronRight size={14} strokeWidth={1.5} />
            )}
          </button>
        ) : isProcessing ? (
          <Loader2 size={14} className="shrink-0 animate-spin text-stone-400" />
        ) : (
          <span className="shrink-0 w-3.5 h-3.5 rounded-full bg-red-400/20 border border-red-400/40" />
        )}

        <button
          onClick={() => isDone && setOpen(!open)}
          className="flex-1 min-w-0 text-left"
        >
          <p className="text-sm truncate text-stone-800 dark:text-stone-200">
            {media.title || media.url}
          </p>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-xs font-mono text-stone-400 dark:text-stone-600">
              {media.created_at?.split("T")[0] || ""}
            </span>
            {!isDone && (
              <span className="text-[10px] font-mono tracking-wider uppercase text-stone-400 dark:text-stone-600">
                {media.status}
              </span>
            )}
          </div>
        </button>

        <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
          <a
            href={media.url}
            target="_blank"
            rel="noopener noreferrer"
            className="p-1 text-stone-400 hover:text-accent dark:hover:text-amber-500 transition-colors"
          >
            <ExternalLink size={12} strokeWidth={1.5} />
          </a>
          {onDelete && (
            <button
              onClick={onDelete}
              title={lang === "en" ? "Remove" : "\u5220\u9664"}
              className="p-1 text-stone-300 dark:text-stone-700 hover:text-red-500 dark:hover:text-red-400 transition-colors"
            >
              <X size={12} strokeWidth={1.5} />
            </button>
          )}
        </div>
      </div>

      {open && isDone && content && (
        <div className="pl-7 pb-2 prose prose-sm prose-stone dark:prose-invert max-w-none animate-fade-in">
          <ReactMarkdown>{content}</ReactMarkdown>
        </div>
      )}

      {media.status === "error" && media.error_message && (
        <div className="pl-7 text-xs text-red-600/80 dark:text-red-400/80 font-light">
          {media.error_message}
        </div>
      )}

      {isProcessing && (
        <div className="pl-7 text-xs text-stone-400 dark:text-stone-600 font-light">
          {lang === "en" ? "Processing\u2026" : "\u5904\u7406\u4E2D\u2026"}
        </div>
      )}
    </div>
  );
}
