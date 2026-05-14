export default function AccuracyBadge({ hits, verified, pct }) {
  if (!verified) return null;
  const color =
    pct >= 60
      ? "text-emerald-600 dark:text-emerald-400"
      : pct >= 40
        ? "text-amber-600 dark:text-amber-400"
        : "text-red-500 dark:text-red-400";
  return (
    <span className={`text-xs font-mono ${color}`}>
      {hits}/{verified} ({pct}%)
    </span>
  );
}
