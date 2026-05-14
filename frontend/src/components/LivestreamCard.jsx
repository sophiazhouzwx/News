import ReactMarkdown from "react-markdown";
import { useLanguage } from "../contexts/LanguageContext";
import { Loader2, ExternalLink, Radio } from "lucide-react";

export default function LivestreamCard({ livestream }) {
  const { lang } = useLanguage();
  const content = lang === "en" ? livestream.summary_en : livestream.summary_cn;

  return (
    <div className="border-b border-stone-200 dark:border-stone-800 pb-6 last:border-0 last:pb-0 animate-slide-up">
      <div className="flex items-start gap-3 mb-3">
        <Radio size={14} strokeWidth={1.5} className="text-red-500/70 shrink-0 mt-1" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-stone-800 dark:text-stone-200 leading-snug">
            {livestream.title}
          </p>
          <div className="flex items-center gap-3 text-xs text-stone-400 dark:text-stone-600 mt-1 font-mono">
            <span>@{livestream.account_name}</span>
            {livestream.pub_date && (
              <span>{new Date(livestream.pub_date).toLocaleDateString()}</span>
            )}
            {livestream.post_url && (
              <a
                href={livestream.post_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-0.5 hover:text-accent dark:hover:text-amber-500 transition-colors"
              >
                <ExternalLink size={10} strokeWidth={1.5} />
                {lang === "en" ? "Original" : "\u539F\u6587"}
              </a>
            )}
          </div>
        </div>
        {livestream.status !== "done" && (
          <span className="text-[10px] font-mono tracking-wider uppercase text-stone-400 dark:text-stone-600">
            {livestream.status}
          </span>
        )}
      </div>

      {livestream.status === "done" && content && (
        <div className="pl-7 prose prose-sm prose-stone dark:prose-invert max-w-none">
          <ReactMarkdown>{content}</ReactMarkdown>
        </div>
      )}

      {livestream.status === "error" && livestream.error_message && (
        <div className="pl-7 text-sm text-red-600/80 dark:text-red-400/80 font-light">
          {livestream.error_message}
        </div>
      )}

      {(livestream.status === "pending" || livestream.status === "processing") && (
        <div className="pl-7 flex items-center gap-2 text-sm text-stone-400 dark:text-stone-600">
          <Loader2 size={14} className="animate-spin" />
          <span className="font-light">
            {lang === "en" ? "Processing\u2026" : "\u5904\u7406\u4E2D\u2026"}
          </span>
        </div>
      )}
    </div>
  );
}
