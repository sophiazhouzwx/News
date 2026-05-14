import { useLanguage } from "../contexts/LanguageContext";

export default function LanguageToggle() {
  const { lang, toggle } = useLanguage();

  return (
    <button
      onClick={toggle}
      className="rounded-full px-3 py-1.5 text-xs font-mono font-medium tracking-wider text-stone-500 dark:text-stone-500 hover:text-stone-800 dark:hover:text-stone-200 hover:bg-stone-200/50 dark:hover:bg-stone-800/50 transition-all duration-200 uppercase"
      title={lang === "en" ? "Switch to Chinese" : "\u5207\u6362\u5230\u82F1\u6587"}
    >
      {lang === "en" ? "EN" : "\u4E2D"}
    </button>
  );
}
