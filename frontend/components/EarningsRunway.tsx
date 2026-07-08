"use client";
import Link from "next/link";
import { StockReport } from "../lib/api";

// Earnings runway — a slim strip of upcoming report dates across the book, so
// a print never surprises you (and it mirrors the advisor's no-buy-within-2-days
// rule: names inside that window are flagged).
export function EarningsRunway({ holdings }: { holdings: StockReport[] }) {
  const upcoming = holdings
    .filter((h) => h.days_to_earnings != null && (h.days_to_earnings as number) <= 45)
    .sort((a, b) => (a.days_to_earnings as number) - (b.days_to_earnings as number));

  if (!upcoming.length) return null;

  return (
    <div className="card earnings">
      <div className="section-title" style={{ marginBottom: 10 }}>
        Earnings ahead <span className="mut" style={{ textTransform: "none", letterSpacing: 0 }}>· next 45 days</span>
      </div>
      <div className="earn-strip">
        {upcoming.map((h) => {
          const d = h.days_to_earnings as number;
          const soon = d <= 2; // advisor won't open new buys inside this window
          return (
            <Link key={h.symbol} href={`/stock/${h.symbol}`} className={`earn-chip${soon ? " soon" : ""}`}>
              <span className="ec-sym">{h.symbol}</span>
              <span className="ec-days">{d === 0 ? "today" : d === 1 ? "1 day" : `${d} days`}</span>
              {soon && <span className="ec-flag">no new buys</span>}
            </Link>
          );
        })}
      </div>
    </div>
  );
}
