import Link from "next/link";
import { StockReport } from "../lib/api";
import { money, num, pct, signClass } from "./format";
import { Signals } from "./Signals";
import { Sparkline } from "./Sparkline";

const RATING_LABEL: Record<string, string> = {
  strong_buy: "Strong Buy",
  buy: "Buy",
  outperform: "Outperform",
  hold: "Hold",
  underperform: "Underperform",
  sell: "Sell",
};

function ratingClass(rec?: string) {
  if (!rec) return "neutral";
  if (rec.includes("buy") || rec === "outperform") return "bullish";
  if (rec.includes("sell") || rec === "underperform") return "bearish";
  return "neutral";
}

export function StockCard({ r }: { r: StockReport }) {
  const i = r.indicators;
  // The one signal most worth surfacing: prefer bullish, then bearish, then neutral.
  const top =
    r.signals.find((s) => s.kind === "bullish") ||
    r.signals.find((s) => s.kind === "bearish") ||
    r.signals[0];

  return (
    <Link href={`/stock/${r.symbol}`} className="card stock-card">
      <div className="sc-head">
        <div className="sc-id">
          <div className="sc-sym">{r.symbol}</div>
          <div className="sc-name">{r.quote.name}</div>
          {r.theme && <span className="theme-tag" style={{ marginTop: 6 }}>{r.theme}</span>}
        </div>
        <div className="sc-right">
          <div className="p">{money(r.quote.price)}</div>
          <div className={`sc-chg ${signClass(r.quote.change_pct)}`}>
            {r.quote.change_pct >= 0 ? "▲" : "▼"} {pct(r.quote.change_pct)}
          </div>
          <Sparkline data={r.spark} />
        </div>
      </div>

      {/* headline insight brought forward from the detail page */}
      <div className="sc-insight">
        {top && (
          <span className={`sig ${top.kind}`} title={top.detail}>
            {top.kind === "bullish" ? "▲" : top.kind === "bearish" ? "▼" : "•"} {top.label}
          </span>
        )}
        {r.analyst.recommendation && (
          <span className={`rating-pill ${ratingClass(r.analyst.recommendation)}`}>
            {RATING_LABEL[r.analyst.recommendation] || r.analyst.recommendation.replace("_", " ")}
          </span>
        )}
        {r.analyst.upside_pct != null && (
          <span className="mut" style={{ fontSize: 11 }}>
            {pct(r.analyst.upside_pct, 0)} to target
          </span>
        )}
      </div>

      <div className="metrics">
        <div className="metric">
          <span className="m-l">RSI</span>
          <span className="m-v">{num(i.rsi, 0)}</span>
        </div>
        <div className="metric">
          <span className="m-l">Trend</span>
          <span className="m-v" style={{ textTransform: "capitalize" }}>{i.trend || "—"}</span>
        </div>
        <div className="metric">
          <span className="m-l">vs 52w hi</span>
          <span className={`m-v ${signClass(i.pct_from_52w_high)}`}>{pct(i.pct_from_52w_high, 1)}</span>
        </div>
        {r.market_value != null ? (
          <div className="metric">
            <span className="m-l">Value</span>
            <span className="m-v">{money(r.market_value, 0)}</span>
          </div>
        ) : r.analyst.mean_target != null ? (
          <div className="metric">
            <span className="m-l">Target</span>
            <span className="m-v">{money(r.analyst.mean_target)}</span>
          </div>
        ) : null}
        {r.unrealized_pl_pct != null && (
          <div className="metric">
            <span className="m-l">Unreal. P/L</span>
            <span className={`m-v ${signClass(r.unrealized_pl_pct)}`}>{pct(r.unrealized_pl_pct, 1)}</span>
          </div>
        )}
        {r.unrealized_pl != null && (
          <div className="metric">
            <span className="m-l">P/L $</span>
            <span className={`m-v ${signClass(r.unrealized_pl)}`}>{money(r.unrealized_pl, 0)}</span>
          </div>
        )}
      </div>

      <Signals signals={r.signals} max={4} />
    </Link>
  );
}
