"use client";
import Link from "next/link";
import { StockReport } from "../lib/api";
import { money, pct } from "./format";

// "What moved you today" — ranks each holding's dollar contribution to today's
// P/L so the net number has a story: which names drove it, up and down.
export function DailyAttribution({ holdings, dayChange }: { holdings: StockReport[]; dayChange: number }) {
  const rows = holdings
    .map((h) => ({
      symbol: h.symbol,
      amt: (h.shares || 0) * (h.quote.change || 0),
      pct: h.quote.change_pct,
    }))
    .filter((r) => Math.abs(r.amt) >= 0.5)
    .sort((a, b) => Math.abs(b.amt) - Math.abs(a.amt))
    .slice(0, 8);

  if (!rows.length) return null;
  const maxAbs = Math.max(...rows.map((r) => Math.abs(r.amt)), 1);

  return (
    <div className="card attrib">
      <div className="chart-head" style={{ marginBottom: 10 }}>
        <div className="section-title" style={{ margin: 0 }}>What moved you today</div>
        <span className={`attrib-net ${dayChange >= 0 ? "pos" : "neg"}`}>
          {dayChange >= 0 ? "+" : ""}{money(dayChange, 0)}
        </span>
      </div>
      <div className="attrib-rows">
        {rows.map((r) => (
          <Link key={r.symbol} href={`/stock/${r.symbol}`} className="attrib-row">
            <span className="ar-sym">{r.symbol}</span>
            <div className="ar-track">
              <div className={`ar-bar ${r.amt >= 0 ? "pos" : "neg"}`}
                   style={{ width: `${(Math.abs(r.amt) / maxAbs) * 100}%` }} />
            </div>
            <span className={`ar-amt ${r.amt >= 0 ? "pos" : "neg"}`}>
              {r.amt >= 0 ? "+" : ""}{money(r.amt, 0)}
            </span>
            <span className="ar-pct mut">{pct(r.pct)}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}
