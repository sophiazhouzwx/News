import { useState, useEffect } from "react";
import {
  fetchPodcasts,
  fetchPodcastEpisodes,
  fetchSpeeches,
  fetchPersonalities,
  deleteSpeech,
  deleteEpisode,
} from "../services/api";
import { useLanguage } from "../contexts/LanguageContext";
import PodcastEpisodeCard from "../components/PodcastEpisodeCard";
import {
  Loader2,
  ChevronDown,
  ChevronRight,
  Headphones,
  Mic2,
  ExternalLink,
  Trash2,
} from "lucide-react";
import ReactMarkdown from "react-markdown";

export default function PodcastsPage() {
  const { lang } = useLanguage();
  const [podcasts, setPodcasts] = useState([]);
  const [speeches, setSpeeches] = useState([]);
  const [personalities, setPersonalities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState({});
  const [episodes, setEpisodes] = useState({});
  const [expandedSpeech, setExpandedSpeech] = useState(null);

  useEffect(() => {
    Promise.all([
      fetchPodcasts().catch(() => []),
      fetchSpeeches().catch(() => []),
      fetchPersonalities().catch(() => []),
    ]).then(([pc, sp, pers]) => {
      setPodcasts(pc);
      const sorted = [...sp].sort(
        (a, b) => new Date(b.pub_date || 0) - new Date(a.pub_date || 0),
      );
      setSpeeches(sorted);
      setPersonalities(pers);
      setLoading(false);
    });
  }, []);

  const togglePodcast = async (name) => {
    if (expanded[name]) {
      setExpanded((prev) => ({ ...prev, [name]: false }));
      return;
    }
    setExpanded((prev) => ({ ...prev, [name]: true }));
    if (!episodes[name]) {
      try {
        const eps = await fetchPodcastEpisodes(name);
        setEpisodes((prev) => ({ ...prev, [name]: eps }));
      } catch {
        /* ignore */
      }
    }
  };

  const handleDeleteSpeech = async (id) => {
    try {
      await deleteSpeech(id);
      setSpeeches((prev) => prev.filter((s) => s.id !== id));
      if (expandedSpeech === id) setExpandedSpeech(null);
    } catch {
      /* ignore */
    }
  };

  const handleDismissEpisode = async (podcastName, episodeId) => {
    try {
      await deleteEpisode(episodeId);
      setEpisodes((prev) => ({
        ...prev,
        [podcastName]: prev[podcastName]?.filter((ep) => ep.id !== episodeId) || [],
      }));
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

  const scheduleLabel = (s) => {
    const map = {
      daily: lang === "en" ? "Daily" : "\u6BCF\u65E5",
      weekly: lang === "en" ? "Weekly" : "\u6BCF\u5468",
      biweekly: lang === "en" ? "Biweekly" : "\u53CC\u5468",
    };
    return map[s] || s;
  };

  return (
    <div className="space-y-14 animate-fade-in">
      {/* --- Personality Speeches --- */}
      {(speeches.length > 0 || personalities.length > 0) && (
        <section className="space-y-6">
          <div className="border-b border-stone-200 dark:border-stone-800 pb-4">
            <h2 className="font-serif text-3xl tracking-tight text-stone-900 dark:text-stone-100">
              {lang === "en" ? "Speeches & Interviews" : "\u6F14\u8BB2\u4E0E\u8BBF\u8C08"}
            </h2>
            <p className="mt-1 text-xs font-mono tracking-wider text-stone-400 dark:text-stone-600 uppercase">
              {personalities.map((p) => p.name).join(" \u00b7 ")}
            </p>
          </div>

          {speeches.length === 0 ? (
            <div className="py-12 text-center">
              <p className="font-serif text-lg italic text-stone-400 dark:text-stone-600">
                {lang === "en"
                  ? "No recent speeches found."
                  : "\u6682\u672A\u627E\u5230\u8FD1\u671F\u6F14\u8BB2\u3002"}
              </p>
            </div>
          ) : (
            <div className="space-y-0">
              {speeches.map((s) => {
                const isExpanded = expandedSpeech === s.id;
                const content = lang === "en" ? s.summary_en : s.summary_cn;
                return (
                  <div
                    key={s.id}
                    className="group border-b border-stone-100 dark:border-stone-800/50 last:border-0"
                  >
                    <div className="flex items-center justify-between py-4">
                      <button
                        onClick={() => setExpandedSpeech(isExpanded ? null : s.id)}
                        className="flex items-center gap-4 min-w-0 flex-1 text-left"
                      >
                        <div className="shrink-0 text-right min-w-[48px]">
                          <div className="text-xs font-mono text-accent dark:text-amber-500">
                            {s.pub_date
                              ? new Date(s.pub_date).toLocaleDateString(lang === "en" ? "en-US" : "zh-CN", { month: "short", day: "numeric" })
                              : "\u2014"}
                          </div>
                        </div>
                        <div className="min-w-0">
                          <h3 className="text-sm truncate text-stone-800 dark:text-stone-200">
                            {s.title}
                          </h3>
                          <p className="text-xs text-stone-400 dark:text-stone-600 mt-0.5">
                            {s.personality_name}
                          </p>
                        </div>
                      </button>
                      <div className="flex items-center gap-1 shrink-0 ml-3 opacity-0 group-hover:opacity-100 transition-opacity">
                        {s.video_url && (
                          <a
                            href={s.video_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="p-1.5 text-stone-400 hover:text-accent dark:hover:text-amber-500 transition-colors"
                          >
                            <ExternalLink size={12} strokeWidth={1.5} />
                          </a>
                        )}
                        <button
                          onClick={() => handleDeleteSpeech(s.id)}
                          title={lang === "en" ? "Remove" : "\u5220\u9664"}
                          className="p-1.5 text-stone-300 dark:text-stone-700 hover:text-red-500 dark:hover:text-red-400 transition-colors"
                        >
                          <Trash2 size={12} strokeWidth={1.5} />
                        </button>
                      </div>
                    </div>
                    {isExpanded && content && (
                      <div className="pl-16 pb-5 prose prose-sm prose-stone dark:prose-invert max-w-none animate-fade-in">
                        <ReactMarkdown>{content}</ReactMarkdown>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>
      )}

      {/* --- Tracked Podcasts --- */}
      <section className="space-y-6">
        <div className="border-b border-stone-200 dark:border-stone-800 pb-4">
          <h2 className="font-serif text-3xl tracking-tight text-stone-900 dark:text-stone-100">
            {lang === "en" ? "Podcasts" : "\u64AD\u5BA2"}
          </h2>
        </div>

        {podcasts.length === 0 && (
          <p className="text-center py-12 font-serif text-lg italic text-stone-400 dark:text-stone-600">
            {lang === "en"
              ? "No podcast episodes yet."
              : "\u6682\u65E0\u5DF2\u603B\u7ED3\u7684\u64AD\u5BA2\u8282\u76EE\u3002"}
          </p>
        )}

        <div className="space-y-0">
          {podcasts.map((pc) => (
            <div
              key={pc.name}
              className="border-b border-stone-100 dark:border-stone-800/50 last:border-0"
            >
              <button
                onClick={() => togglePodcast(pc.name)}
                className="w-full flex items-center justify-between py-4 text-left group"
              >
                <div className="flex items-center gap-3">
                  <Headphones size={16} strokeWidth={1.5} className="text-stone-400 dark:text-stone-600" />
                  <div>
                    <h3 className="text-sm font-medium text-stone-800 dark:text-stone-200">
                      {pc.name}
                    </h3>
                    <p className="text-xs text-stone-400 dark:text-stone-600 mt-0.5 font-mono">
                      {scheduleLabel(pc.schedule)} &middot; {pc.episode_count}{" "}
                      {lang === "en" ? "episodes" : "\u671F"}
                    </p>
                  </div>
                </div>
                <span className="text-stone-300 dark:text-stone-700">
                  {expanded[pc.name] ? (
                    <ChevronDown size={16} strokeWidth={1.5} />
                  ) : (
                    <ChevronRight size={16} strokeWidth={1.5} />
                  )}
                </span>
              </button>

              {expanded[pc.name] && (
                <div className="pl-8 pb-4 animate-fade-in">
                  {!episodes[pc.name] ? (
                    <div className="flex justify-center py-4">
                      <div className="h-4 w-4 rounded-full border-2 border-stone-300 border-t-accent animate-spin" />
                    </div>
                  ) : episodes[pc.name].length === 0 ? (
                    <p className="text-sm text-stone-400 dark:text-stone-600 text-center py-4 font-light">
                      {lang === "en" ? "No episodes yet." : "\u6682\u65E0\u8282\u76EE\u3002"}
                    </p>
                  ) : (
                    episodes[pc.name].map((ep) => (
                      <PodcastEpisodeCard
                        key={ep.id}
                        episode={ep}
                        onDismiss={() => handleDismissEpisode(pc.name, ep.id)}
                      />
                    ))
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
