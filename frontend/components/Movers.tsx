"use client";
import Link from "next/link";
import { StockReport } from "../lib/api";
import { pct } from "./format";

// Top day movers across holdings + watchlist, as a compact chip strip.
export function Movers({ reports, count = 3 }: { reports: StockReport[]; count?: number }) {
  if (reports.length < 2) return null;
  const sorted = [...reports].sort((a, b) => b.quote.change_pct - a.quote.change_pct);
  const gainers = sorted.slice(0, count).filter((r) => r.quote.change_pct > 0);
  const losers = sorted
    .slice(-count)
    .filter((r) => r.quote.change_pct < 0)
    .reverse();
  if (!gainers.length && !losers.length) return null;

  const chip = (r: StockReport) => (
    <Link key={r.symbol} href={`/stock/${r.symbol}`} className={`mover-chip ${r.quote.change_pct >= 0 ? "up" : "down"}`}>
      <span className="mv-sym">{r.symbol}</span>
      <span className="mv-pct">
        {r.quote.change_pct >= 0 ? "▲" : "▼"} {pct(r.quote.change_pct)}
      </span>
    </Link>
  );

  return (
    <div className="movers">
      <span className="movers-label">Today</span>
      {gainers.map(chip)}
      {gainers.length > 0 && losers.length > 0 && <span className="movers-sep" />}
      {losers.map(chip)}
    </div>
  );
}
