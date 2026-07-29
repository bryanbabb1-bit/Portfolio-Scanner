"use client";
import Link from "next/link";
import { StockReport } from "../lib/api";
import { SplitFlapText } from "./SplitFlap";
import { money, pct } from "./format";

/* The board — holdings as a departure board.
 *
 * Ranked by weight, so the top of the board is what actually moves the book.
 * Ticker and price flip; the rest is set quietly, because a board where
 * everything moves is noise. */
export function HoldingsBoard({ holdings }: { holdings: StockReport[] }) {
  const rows = [...holdings]
    .filter((r) => (r.market_value ?? 0) > 0)
    .sort((a, b) => (b.market_value ?? 0) - (a.market_value ?? 0))
    .slice(0, 10);

  if (!rows.length) return null;
  const book = rows.reduce((s, r) => s + (r.market_value ?? 0), 0);

  return (
    <div className="board">
      <div className="board-head">
        <span>Holdings — live</span>
        <span>
          {rows.length} shown · {money(book, 0)}
        </span>
      </div>

      <div className="board-rows">
        {rows.map((r) => {
          const up = r.quote.change_pct >= 0;
          return (
            <Link key={r.symbol} href={`/stock/${r.symbol}`} className="board-row">
              <SplitFlapText value={r.symbol} width={5} className="sf-sym" />
              <SplitFlapText
                value={r.quote.price.toFixed(2)}
                width={8}
                className="sf-px"
              />
              <span className={`board-chg ${up ? "up" : "down"}`}>
                {up ? "▲" : "▼"} {Math.abs(r.quote.change_pct).toFixed(2)}%
              </span>
              <span className="board-wt">
                {(((r.market_value ?? 0) / book) * 100).toFixed(1)}%
              </span>
              <span className={`board-pl ${(r.unrealized_pl_pct ?? 0) >= 0 ? "up" : "down"}`}>
                {pct(r.unrealized_pl_pct)}
              </span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
