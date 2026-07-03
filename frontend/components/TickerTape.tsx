"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";

interface Tick {
  symbol: string;
  price: number;
  change_pct: number;
  flash: "" | "up" | "down";
}

// Trading-floor ticker tape: every holding + watched name scrolling across
// the top of the app, price cells flashing on change. Pure CSS marquee.
export function TickerTape() {
  const [ticks, setTicks] = useState<Tick[]>([]);
  const prev = useRef<Record<string, number>>({});

  useEffect(() => {
    const load = () =>
      api
        .scan(true)
        .then((d) => {
          const next = d.results.map((r) => {
            const old = prev.current[r.symbol];
            const flash: Tick["flash"] =
              old == null || old === r.quote.price ? "" : r.quote.price > old ? "up" : "down";
            prev.current[r.symbol] = r.quote.price;
            return { symbol: r.symbol, price: r.quote.price, change_pct: r.quote.change_pct, flash };
          });
          setTicks(next);
          // clear flashes after the pulse animation completes
          setTimeout(() => setTicks((cur) => cur.map((t) => ({ ...t, flash: "" }))), 1400);
        })
        .catch(() => {});
    load();
    const t = setInterval(load, 60_000);
    return () => clearInterval(t);
  }, []);

  if (ticks.length < 3) return null;
  const loop = [...ticks, ...ticks]; // duplicated for a seamless wrap

  return (
    <div className="tape" aria-hidden="true">
      <div className="tape-track" style={{ animationDuration: `${ticks.length * 3.2}s` }}>
        {loop.map((t, i) => (
          <Link key={`${t.symbol}-${i}`} href={`/stock/${t.symbol}`} className={`tape-item ${t.flash ? `flash-${t.flash}` : ""}`}>
            <span className="tape-sym">{t.symbol}</span>
            <span className="tape-price">{t.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
            <span className={t.change_pct >= 0 ? "pos" : "neg"}>
              {t.change_pct >= 0 ? "▲" : "▼"} {Math.abs(t.change_pct).toFixed(2)}%
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}
