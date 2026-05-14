import { TrendingUp, TrendingDown, Minus } from "lucide-react";

const DIRECTION_ICON = {
  bull: <TrendingUp size={12} className="text-emerald-500" />,
  bear: <TrendingDown size={12} className="text-red-500" />,
  hold: <Minus size={12} className="text-stone-400" />,
};

const OUTCOME_CLASS = {
  hit: "text-emerald-600 dark:text-emerald-400",
  miss: "text-red-500 dark:text-red-400",
  pending: "text-stone-400",
  expired: "text-stone-300 dark:text-stone-600 line-through",
};

export default function PredictionItemsTable({ items, lang }) {
  if (!items?.length) return null;
  return (
    <div className="mt-4 not-prose overflow-x-auto">
      <table className="w-full text-xs font-mono border-collapse">
        <thead>
          <tr className="border-b border-stone-200 dark:border-stone-700">
            <th className="text-left pb-2 text-stone-400 font-normal">
              Ticker
            </th>
            <th className="text-left pb-2 text-stone-400 font-normal">
              {lang === "en" ? "Call" : "方向"}
            </th>
            <th className="text-left pb-2 text-stone-400 font-normal">
              {lang === "en" ? "Conf." : "信心"}
            </th>
            <th className="text-left pb-2 text-stone-400 font-normal">
              {lang === "en" ? "Window" : "周期"}
            </th>
            <th className="text-left pb-2 text-stone-400 font-normal">
              {lang === "en" ? "Result" : "结果"}
            </th>
            <th className="text-right pb-2 text-stone-400 font-normal">
              {lang === "en" ? "Change" : "涨跌"}
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const outcome = item.outcome || "pending";
            const changePct = item.actual_change_pct;
            return (
              <tr
                key={item.id}
                className="border-b border-stone-100 dark:border-stone-800/40"
              >
                <td className="py-1.5 font-medium text-stone-800 dark:text-stone-200">
                  {item.ticker}
                </td>
                <td className="py-1.5">
                  <span className="flex items-center gap-1">
                    {DIRECTION_ICON[item.direction] || null}
                    <span className="capitalize">{item.direction}</span>
                  </span>
                </td>
                <td className="py-1.5 text-stone-500">
                  {item.confidence_pct ? `${item.confidence_pct}%` : "—"}
                </td>
                <td className="py-1.5 text-stone-500">
                  {item.timeframe_days}d
                </td>
                <td
                  className={`py-1.5 capitalize ${OUTCOME_CLASS[outcome]}`}
                >
                  {outcome}
                </td>
                <td
                  className={`py-1.5 text-right ${
                    changePct != null
                      ? changePct >= 0
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-red-500 dark:text-red-400"
                      : "text-stone-400"
                  }`}
                >
                  {changePct != null
                    ? `${changePct >= 0 ? "+" : ""}${changePct.toFixed(1)}%`
                    : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
