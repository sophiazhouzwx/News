import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { useLanguage } from "../contexts/LanguageContext";
import { Play, ChevronDown, ChevronRight, X } from "lucide-react";

export default function PodcastEpisodeCard({ episode, onDismiss }) {
  const { lang } = useLanguage();
  const [open, setOpen] = useState(false);
  const content = lang === "en" ? episode.summary_en : episode.summary_cn;

  return (
    <div className="group border-b border-stone-100 dark:border-stone-800/50 last:border-0">
      <div className="flex items-center justify-between py-3 transition-colors">
        <button
          onClick={() => setOpen(!open)}
          className="flex items-center gap-3 min-w-0 flex-1 text-left"
        >
          <span className="text-stone-300 dark:text-stone-700">
            {open ? (
              <ChevronDown size={14} strokeWidth={1.5} />
            ) : (
              <ChevronRight size={14} strokeWidth={1.5} />
            )}
          </span>
          <div className="min-w-0">
            <h4 className="text-sm leading-snug truncate text-stone-800 dark:text-stone-200">
              {episode.episode_title}
            </h4>
            {episode.pub_date && (
              <p className="text-xs text-stone-400 dark:text-stone-600 mt-0.5 font-mono">
                {new Date(episode.pub_date).toLocaleDateString()}
              </p>
            )}
          </div>
        </button>

        <div className="flex items-center gap-1 shrink-0 ml-3 opacity-0 group-hover:opacity-100 transition-opacity">
          {episode.audio_url && (
            <a
              href={episode.audio_url}
              target="_blank"
              rel="noopener noreferrer"
              className="p-1.5 text-stone-400 hover:text-accent dark:hover:text-amber-500 transition-colors"
              title={lang === "en" ? "Play" : "\u64AD\u653E"}
            >
              <Play size={12} strokeWidth={1.5} />
            </a>
          )}
          {onDismiss && (
            <button
              onClick={onDismiss}
              title={lang === "en" ? "Dismiss" : "\u79FB\u9664"}
              className="p-1.5 text-stone-300 dark:text-stone-700 hover:text-red-500 dark:hover:text-red-400 transition-colors"
            >
              <X size={12} strokeWidth={1.5} />
            </button>
          )}
        </div>
      </div>

      {open && content && (
        <div className="pl-8 pb-4 prose prose-sm prose-stone dark:prose-invert max-w-none animate-fade-in">
          <ReactMarkdown>{content}</ReactMarkdown>
        </div>
      )}
    </div>
  );
}
