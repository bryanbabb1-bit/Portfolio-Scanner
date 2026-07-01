"use client";
import { StockReport } from "../lib/api";

export type SortKey = "value" | "change" | "return" | "alpha" | "theme";

export const SORTS: { key: SortKey; label: string }[] = [
  { key: "value", label: "Market value" },
  { key: "change", label: "Day movers" },
  { key: "return", label: "Unreal. return" },
  { key: "alpha", label: "A–Z" },
  { key: "theme", label: "Theme" },
];

export function sortReports(rows: StockReport[], key: SortKey): StockReport[] {
  const v = (r: StockReport) => r.market_value ?? 0;
  const arr = [...rows];
  switch (key) {
    case "value":
      return arr.sort((a, b) => v(b) - v(a));
    case "change":
      return arr.sort((a, b) => b.quote.change_pct - a.quote.change_pct);
    case "return":
      return arr.sort(
        (a, b) => (b.unrealized_pl_pct ?? -Infinity) - (a.unrealized_pl_pct ?? -Infinity)
      );
    case "alpha":
      return arr.sort((a, b) => a.symbol.localeCompare(b.symbol));
    case "theme":
      return arr.sort(
        (a, b) => (a.theme || "~").localeCompare(b.theme || "~") || v(b) - v(a)
      );
  }
}

export function SortControl({
  sort,
  setSort,
  options = SORTS,
}: {
  sort: SortKey;
  setSort: (k: SortKey) => void;
  options?: { key: SortKey; label: string }[];
}) {
  return (
    <div className="sort-control">
      <span className="sort-label">Sort</span>
      {options.map((s) => (
        <button key={s.key} className={s.key === sort ? "active" : ""} onClick={() => setSort(s.key)}>
          {s.label}
        </button>
      ))}
    </div>
  );
}
