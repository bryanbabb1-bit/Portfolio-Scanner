"use client";
import Link from "next/link";
import { StockReport } from "../lib/api";
import { money } from "./format";

// A glanceable, always-fresh health read on every holding — computed from price
// action (no Claude call), in plain words. The quick "how are we doing" check
// so you don't have to re-run the whole brief.
//
// The badge states the tier. Everything after it has to say something the badge
// does NOT already say. This used to be one canned sentence per tier, so a
// sixteen-position book rendered four sentences — five rows of "Below its
// long-term trend", four byte-identical "Holding its ground" — and the line was
// pure restatement of the badge sitting next to it. Now each row carries the
// facts that separate it from its neighbours.
type Health = { tier: string; label: string };

function health(r: StockReport): Health {
  const i = r.indicators;
  const price = r.quote.price;
  const from52 = i.pct_from_52w_high ?? -20; // negative = below the high
  const rsi = i.rsi ?? 50;
  const trend = i.trend ?? "sideways";
  const below200 = i.sma200 != null && price < i.sma200;

  if (trend === "downtrend" || below200) return { tier: "weak", label: "Watch" };
  if (rsi >= 70 || from52 >= -2) return { tier: "extended", label: "Hot" };
  if (rsi <= 40 && trend === "uptrend") return { tier: "cheap", label: "On sale" };
  if (trend === "uptrend") return { tier: "healthy", label: "Healthy" };
  return { tier: "steady", label: "Steady" };
}

const ORDER: Record<string, number> = { weak: 0, extended: 1, cheap: 2, steady: 3, healthy: 4 };

// A fact worth a row's space. `lead` marks the ones that should catch the eye —
// the book-wide superlatives and a near-term earnings date, which are the only
// facts here that can actually demand a decision.
type Fact = { t: string; lead?: boolean };

// Book-level context. The superlatives are what stop the list reading as a
// template: each one is true of exactly one row, by construction.
type Book = {
  total: number;
  worstDrawdown?: string;
  biggest?: string;
  bestRun?: string;
  worstRun?: string;
};

function survey(rows: StockReport[]): Book {
  const total = rows.reduce((s, r) => s + (r.market_value ?? 0), 0);
  // Pick the single row that maximises `better` among those passing `keep`.
  const pick = (
    of: (r: StockReport) => number | null | undefined,
    keep: (v: number) => boolean,
    better: (a: number, b: number) => boolean
  ): string | undefined => {
    let win: StockReport | undefined;
    let wv = 0;
    for (const r of rows) {
      const v = of(r);
      if (v == null || !keep(v)) continue;
      if (!win || better(v, wv)) {
        win = r;
        wv = v;
      }
    }
    return win?.symbol;
  };
  return {
    total,
    // Thresholds keep a superlative from being awarded in a flat book, where
    // "worst drawdown" would just mean "least green" and mislead.
    worstDrawdown: pick((r) => r.unrealized_pl_pct, (v) => v <= -10, (a, b) => a < b),
    biggest: pick((r) => r.market_value, () => true, (a, b) => a > b),
    bestRun: pick((r) => r.indicators.ret_20d_pct, (v) => v >= 10, (a, b) => a > b),
    worstRun: pick((r) => r.indicators.ret_20d_pct, (v) => v <= -10, (a, b) => a < b),
  };
}

const MAX_FACTS = 4;
const pctStr = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(0)}%`;

function facts(r: StockReport, book: Book): Fact[] {
  const i = r.indicators;
  const out: Fact[] = [];
  const from52 = i.pct_from_52w_high;
  const weight = book.total > 0 ? ((r.market_value ?? 0) / book.total) * 100 : 0;

  if (i.rsi != null) out.push({ t: `RSI ${i.rsi.toFixed(0)}` });

  if (from52 != null) {
    // Inside 2% is "at the high" — the same test the Hot tier uses. Below 3%
    // isn't worth a fact; it's noise on a 52-week range.
    if (from52 >= -2) out.push({ t: "at 52w high" });
    else if (from52 <= -3) out.push({ t: `${Math.abs(from52).toFixed(0)}% off high` });
  }

  // Momentum only when it's actually moving, carrying the volume that drove it.
  const vr = i.volume_ratio;
  const heavy = vr != null && vr >= 1.5 ? ` on ${vr.toFixed(1)}x volume` : "";
  const r5 = i.ret_5d_pct;
  const r20 = i.ret_20d_pct;
  if (r5 != null && Math.abs(r5) >= 4) out.push({ t: `5d ${pctStr(r5)}${heavy}` });
  else if (r20 != null && Math.abs(r20) >= 10) out.push({ t: `20d ${pctStr(r20)}${heavy}` });
  else if (heavy) out.push({ t: `${vr!.toFixed(1)}x volume` });

  // Concentration cuts both ways: too big to ignore, or too small to matter.
  if (weight >= 10) out.push({ t: `${weight.toFixed(0)}% of book` });
  else if (weight > 0 && weight <= 2) out.push({ t: `only ${weight.toFixed(1)}% of book` });

  // One superlative per row at most, worst news first.
  if (book.worstDrawdown === r.symbol) out.push({ t: "worst drawdown in book", lead: true });
  else if (book.worstRun === r.symbol) out.push({ t: "worst 20d in book", lead: true });
  else if (book.bestRun === r.symbol) out.push({ t: "best 20d in book", lead: true });
  else if (book.biggest === r.symbol && weight < 10) out.push({ t: "biggest position", lead: true });

  // Earnings is the one fact with a clock on it, so it never gets cut by the
  // cap — it takes the last slot instead of falling off the end.
  const dte = r.days_to_earnings;
  const soon: Fact | null =
    dte != null && dte >= 0 && dte <= 14
      ? { t: dte === 0 ? "earnings today" : `earnings in ${dte}d`, lead: true }
      : null;

  const rest = out.slice(0, soon ? MAX_FACTS - 1 : MAX_FACTS);
  return soon ? [...rest, soon] : rest;
}

export function PositionHealth({ holdings }: { holdings: StockReport[] }) {
  const held = holdings.filter((r) => (r.shares ?? 0) > 0 && r.theme !== "Cash & Income");
  // Weights and superlatives are relative to the equity book — the rows shown
  // here — so the percentages add to what's on screen.
  const book = survey(held);
  const rows = held
    .map((r) => ({ r, h: health(r), f: facts(r, book) }))
    .sort((a, b) => (ORDER[a.h.tier] ?? 9) - (ORDER[b.h.tier] ?? 9));

  if (rows.length === 0) return null;

  return (
    <div className="card" id="position-health" style={{ marginBottom: 20 }}>
      <div className="section-title">Position Health · at a glance</div>
      <div className="ph-list">
        {rows.map(({ r, h, f }) => (
          <Link key={r.symbol} href={`/stock/${r.symbol}`} className={`ph-row ${h.tier}`}>
            <span className="ph-sym">{r.symbol}</span>
            <span className="ph-pos">
              {r.shares}sh @ {money(r.cost_basis)} · {money(r.quote.price)}
              <span className={(r.unrealized_pl_pct ?? 0) >= 0 ? "pos" : "neg"}>
                {" "}({(r.unrealized_pl_pct ?? 0) >= 0 ? "+" : ""}{(r.unrealized_pl_pct ?? 0).toFixed(0)}%)
              </span>
            </span>
            <span className={`ph-badge ${h.tier}`}>{h.label}</span>
            <span className="ph-note">
              {f.map((fact, n) => (
                <span key={n} className={`ph-f${fact.lead ? " lead" : ""}`}>
                  {fact.t}
                </span>
              ))}
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}
