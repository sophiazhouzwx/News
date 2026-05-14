import { useState, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import { useLanguage } from "../contexts/LanguageContext";
import { ThumbsUp, ThumbsDown } from "lucide-react";
import { submitFeedback, fetchFeedback } from "../services/api";

function getTextContent(node) {
  if (typeof node === "string") return node;
  if (!node) return "";
  if (Array.isArray(node)) return node.map(getTextContent).join("");
  if (node.props?.children) return getTextContent(node.props.children);
  return "";
}

export default function DigestCard({ digest }) {
  const { lang } = useLanguage();
  const content = lang === "en" ? digest.summary_en : digest.summary_cn;
  const [feedbackMap, setFeedbackMap] = useState({});

  useEffect(() => {
    if (!digest.id) return;
    fetchFeedback(digest.id)
      .then((rows) => {
        const map = {};
        for (const r of rows) map[r.article_title] = r.helpful;
        setFeedbackMap(map);
      })
      .catch(() => {});
  }, [digest.id]);

  const handleFeedback = useCallback(
    async (title, helpful) => {
      try {
        await submitFeedback(digest.id, title, helpful);
        setFeedbackMap((prev) => ({ ...prev, [title]: helpful }));
      } catch (e) {
        console.error("Feedback failed", e);
      }
    },
    [digest.id],
  );

  const extractTitle = (children) => {
    const text = getTextContent(children);
    const m = text.match(/^(.+?)[:：]/);
    return m ? m[1].trim() : text.slice(0, 80).trim();
  };

  const hasArticleLink = (children) => {
    const arr = Array.isArray(children) ? children : [children];
    for (const child of arr) {
      if (child?.props?.href) return true;
      if (child?.type === "strong" || child?.type === "b") {
        const inner = child.props?.children;
        if (inner?.props?.href) return true;
        if (Array.isArray(inner)) {
          for (const ic of inner) {
            if (ic?.props?.href) return true;
          }
        }
      }
    }
    return false;
  };

  return (
    <article className="animate-slide-up">
      {/* Date line */}
      <div className="flex items-center gap-3 mb-5">
        <time className="text-xs font-mono tracking-wider text-stone-400 dark:text-stone-600 uppercase">
          {digest.date}
        </time>
        <div className="flex-1 h-px bg-stone-200 dark:bg-stone-800" />
      </div>

      {/* Content */}
      <div className="prose prose-stone dark:prose-invert max-w-none prose-p:leading-relaxed prose-li:leading-relaxed">
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
            h3: ({ children }) => (
              <h3 className="font-serif text-lg font-normal tracking-tight text-stone-800 dark:text-stone-200 mt-8 mb-3 first:mt-0">
                {children}
              </h3>
            ),
            li: ({ children, ...props }) => {
              if (!hasArticleLink(children)) {
                return <li {...props}>{children}</li>;
              }
              const title = extractTitle(children);
              const state = feedbackMap[title];

              return (
                <li {...props} className="!mb-3 group">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">{children}</div>
                    <div className="flex gap-0.5 shrink-0 mt-1 not-prose opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                      <button
                        onClick={() => handleFeedback(title, true)}
                        title={lang === "en" ? "Helpful" : "\u6709\u7528"}
                        className={`p-1 rounded-full transition-all duration-200 ${
                          state === true
                            ? "text-emerald-600 dark:text-emerald-400 opacity-100"
                            : "text-stone-300 dark:text-stone-700 hover:text-emerald-500 dark:hover:text-emerald-400"
                        }`}
                      >
                        <ThumbsUp size={12} strokeWidth={1.5} />
                      </button>
                      <button
                        onClick={() => handleFeedback(title, false)}
                        title={lang === "en" ? "Not useful" : "\u6CA1\u7528"}
                        className={`p-1 rounded-full transition-all duration-200 ${
                          state === false
                            ? "text-red-500 dark:text-red-400 opacity-100"
                            : "text-stone-300 dark:text-stone-700 hover:text-red-500 dark:hover:text-red-400"
                        }`}
                      >
                        <ThumbsDown size={12} strokeWidth={1.5} />
                      </button>
                    </div>
                  </div>
                </li>
              );
            },
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    </article>
  );
}
