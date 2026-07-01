import Link from "next/link";
import { StockReport } from "../lib/api";
import { money, num, pct, signClass } from "./format";
import { Signals } from "./Signals";

export function StockCard({ r }: { r: StockReport }) {
  const i = r.indicators;
  return (
    <Link href={`/stock/${r.symbol}`} className="card stock-card">
      <div className="sc-head">
        <div>
          <div className="sc-sym">{r.symbol}</div>
          <div className="sc-name">{r.quote.name}</div>
          {r.theme && <span className="theme-tag" style={{ marginTop: 6 }}>{r.theme}</span>}
        </div>
        <div className="sc-price">
          <div className="p">{money(r.quote.price)}</div>
          <div className={signClass(r.quote.change_pct)} style={{ fontSize: 13 }}>
            {pct(r.quote.change_pct)}
          </div>
        </div>
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
        {r.analyst.mean_target != null && (
          <div className="metric">
            <span className="m-l">Target</span>
            <span className="m-v">{money(r.analyst.mean_target)}</span>
          </div>
        )}
        {r.analyst.upside_pct != null && (
          <div className="metric">
            <span className="m-l">Upside</span>
            <span className={`m-v ${signClass(r.analyst.upside_pct)}`}>{pct(r.analyst.upside_pct, 0)}</span>
          </div>
        )}
        {r.unrealized_pl_pct != null && (
          <div className="metric">
            <span className="m-l">Position P/L</span>
            <span className={`m-v ${signClass(r.unrealized_pl_pct)}`}>{pct(r.unrealized_pl_pct, 1)}</span>
          </div>
        )}
      </div>

      <Signals signals={r.signals} max={4} />
    </Link>
  );
}
