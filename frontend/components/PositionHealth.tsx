"use client";
import Link from "next/link";
import { StockReport } from "../lib/api";
import { money } from "./format";

// A glanceable, always-fresh health read on every holding — computed from price
// action (no Claude call), in plain words. The quick "how are we doing" check
// so you don't have to re-run the whole brief.
type Health = { tier: string; label: string; note: string };

function health(r: StockReport): Health {
  const i = r.indicators;
  const price = r.quote.price;
  const pl = r.unrealized_pl_pct ?? 0;
  const from52 = i.pct_from_52w_high ?? -20; // negative = below the high
  const rsi = i.rsi ?? 50;
  const trend = i.trend ?? "sideways";
  const below200 = i.sma200 != null && price < i.sma200;

  if (trend === "downtrend" || below200) {
    return {
      tier: "weak",
      label: "Watch",
      note: `Below its long-term trend, ${pl >= 0 ? "up" : "down"} ${Math.abs(pl).toFixed(0)}% — watch the story, not just the price.`,
    };
  }
  if (rsi >= 70 || from52 >= -2) {
    return {
      tier: "extended",
      label: "Hot",
      note: from52 >= -2
        ? "Right at its high — expect a pullback; don't chase."
        : "Run's been hot — a breather is likely soon.",
    };
  }
  if (rsi <= 40 && trend === "uptrend") {
    return { tier: "cheap", label: "On sale", note: "Cheap in an uptrend — a spot to add, not sell." };
  }
  if (trend === "uptrend") {
    const room = from52 < -4 ? `, ~${Math.abs(from52).toFixed(0)}% below its high` : "";
    return { tier: "healthy", label: "Healthy", note: `Healthy uptrend${room} — room to run.` };
  }
  return { tier: "steady", label: "Steady", note: "Holding its ground — no action needed." };
}

const ORDER: Record<string, number> = { weak: 0, extended: 1, cheap: 2, steady: 3, healthy: 4 };

export function PositionHealth({ holdings }: { holdings: StockReport[] }) {
  const rows = holdings
    .filter((r) => (r.shares ?? 0) > 0 && r.theme !== "Cash & Income")
    .map((r) => ({ r, h: health(r) }))
    .sort((a, b) => (ORDER[a.h.tier] ?? 9) - (ORDER[b.h.tier] ?? 9));

  if (rows.length === 0) return null;

  return (
    <div className="card" id="position-health" style={{ marginBottom: 20 }}>
      <div className="section-title">Position Health · at a glance</div>
      <div className="ph-list">
        {rows.map(({ r, h }) => (
          <Link key={r.symbol} href={`/stock/${r.symbol}`} className={`ph-row ${h.tier}`}>
            <span className="ph-sym">{r.symbol}</span>
            <span className="ph-pos">
              {r.shares}sh @ {money(r.cost_basis)} · {money(r.quote.price)}
              <span className={(r.unrealized_pl_pct ?? 0) >= 0 ? "pos" : "neg"}>
                {" "}({(r.unrealized_pl_pct ?? 0) >= 0 ? "+" : ""}{(r.unrealized_pl_pct ?? 0).toFixed(0)}%)
              </span>
            </span>
            <span className={`ph-badge ${h.tier}`}>{h.label}</span>
            <span className="ph-note">{h.note}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}
