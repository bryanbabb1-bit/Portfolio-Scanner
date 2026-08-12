"use client";
import { use, useEffect, useState } from "react";
import Link from "next/link";
import { api, StockReport } from "../../../lib/api";
import { AdvisorPanel } from "../../../components/AdvisorPanel";
import { DeskStrip } from "../../../components/DeskStrip";
import { OptionsPlay } from "../../../components/OptionsPlay";
import { PriceChart } from "../../../components/PriceChart";
import { Signals } from "../../../components/Signals";
import { compact, money, num, pct, signClass } from "../../../components/format";

export default function StockDetail({
  params,
}: {
  params: Promise<{ symbol: string }>;
}) {
  const { symbol } = use(params);
  const sym = symbol.toUpperCase();
  const [r, setR] = useState<StockReport | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.stock(sym).then(setR).catch((e) => setErr(e.message));
  }, [sym]);

  if (err) return <div className="err">{err}</div>;
  if (!r) return <div className="loading">Loading {sym}…</div>;

  const i = r.indicators;
  const a = r.analyst;

  const rows: [string, string, string?][] = [
    ["Price", money(r.quote.price), signClass(r.quote.change_pct)],
    ["Day change", pct(r.quote.change_pct), signClass(r.quote.change_pct)],
    ["RSI (14)", num(i.rsi, 1)],
    ["Trend", i.trend || "—"],
    ["MACD", num(i.macd, 2)],
    ["MACD signal", num(i.macd_signal, 2)],
    ["SMA 20", money(i.sma20)],
    ["SMA 50", money(i.sma50)],
    ["SMA 200", money(i.sma200)],
    ["52w high", money(i.high_52w)],
    ["52w low", money(i.low_52w)],
    ["% from 52w high", pct(i.pct_from_52w_high, 1), signClass(i.pct_from_52w_high)],
    ["ATR", num(i.atr, 2)],
    ["Bollinger upper", money(i.bb_upper)],
    ["Bollinger lower", money(i.bb_lower)],
    ["Volume vs 20d", i.volume_ratio ? `${num(i.volume_ratio, 2)}x` : "—"],
  ];

  return (
    <>
      <div className="page-head">
        <Link href="/" className="mut" style={{ fontSize: 13 }}>← Back</Link>
        <h1 style={{ marginTop: 8 }}>
          {r.symbol}{" "}
          <span className="mut" style={{ fontSize: 16, fontWeight: 400 }}>{r.quote.name}</span>
        </h1>
        <p>
          {r.theme && <span className="theme-tag">{r.theme}</span>}{" "}
          <span className={signClass(r.quote.change_pct)}>
            {money(r.quote.price)} ({pct(r.quote.change_pct)})
          </span>{" "}
          · Vol {compact(r.quote.volume)} · source {r.quote.source}
        </p>
      </div>

      {/* Your position, stated in dollars first.
          The old version was four flat tiles with no daily figure at all — you
          could see what the STOCK did today but not what YOUR money did, which
          is the number you actually came to look at. */}
      {r.shares != null && r.shares > 0 && (() => {
        const shares = r.shares!;
        const cost = r.cost_basis ?? 0;
        const value = r.market_value ?? shares * r.quote.price;
        const invested = shares * cost;
        const pl = r.unrealized_pl ?? value - invested;
        const plPct = r.unrealized_pl_pct ?? (invested ? (pl / invested) * 100 : 0);
        // quote.change is the per-share move today, so this is what the
        // POSITION made or lost today rather than what one share did.
        const dayPl = shares * (r.quote.change ?? 0);

        return (
          <div className="card pos-panel">
            <div className="pos-top">
              <div className="pos-main">
                <div className="pos-k">Your position</div>
                <div className="pos-value">{money(value)}</div>
                <div className={`pos-pl ${signClass(pl)}`}>
                  {pl >= 0 ? "+" : ""}{money(pl)} ({pct(plPct)}) all time
                </div>
              </div>
              <div className={`pos-today ${signClass(dayPl)}`}>
                <div className="pos-k">Today</div>
                <div className="pos-today-v">
                  {dayPl >= 0 ? "+" : ""}{money(dayPl)}
                </div>
                <div className="pos-today-s">{pct(r.quote.change_pct)}</div>
              </div>
            </div>
            <div className="pos-grid">
              <div><span className="pos-k">Shares</span><span className="pos-v">{num(shares, 4)}</span></div>
              <div><span className="pos-k">Avg cost</span><span className="pos-v">{money(cost)}</span></div>
              <div><span className="pos-k">Last price</span><span className="pos-v">{money(r.quote.price)}</span></div>
              <div><span className="pos-k">Invested</span><span className="pos-v">{money(invested)}</span></div>
              <div>
                <span className="pos-k">Break-even</span>
                <span className="pos-v">
                  {r.quote.price >= cost
                    ? `${pct(((r.quote.price - cost) / cost) * 100, 1)} above`
                    : `${pct(((cost - r.quote.price) / cost) * 100, 1)} below`}
                </span>
              </div>
              {r.days_to_earnings != null && r.days_to_earnings >= 0 && (
                <div>
                  <span className="pos-k">Earnings</span>
                  <span className={`pos-v${r.days_to_earnings <= 7 ? " hot" : ""}`}>
                    {r.days_to_earnings === 0 ? "today" : `in ${r.days_to_earnings}d`}
                  </span>
                </div>
              )}
            </div>
          </div>
        );
      })()}

      <DeskStrip symbol={r.symbol} />

      <PriceChart symbol={r.symbol} quote={r.quote} />

      <OptionsPlay symbol={r.symbol} />

      <div className="detail-grid">
        <div>
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="section-title">Signals</div>
            <Signals signals={r.signals} />
          </div>

          <div className="card" style={{ marginBottom: 16 }}>
            <div className="section-title">Technicals</div>
            <div className="kv">
              {rows.map(([k, v, cls]) => (
                <div className="row" key={k}>
                  <span className="k">{k}</span>
                  <span className={cls || ""}>{v}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <div className="section-title">Analyst View</div>
            <div className="kv">
              <div className="row"><span className="k">Rating</span><span style={{ textTransform: "capitalize" }}>{a.recommendation?.replace("_", " ") || "—"}</span></div>
              <div className="row"><span className="k">Mean target</span><span>{money(a.mean_target)}</span></div>
              <div className="row"><span className="k">High / Low</span><span>{money(a.high_target)} / {money(a.low_target)}</span></div>
              <div className="row"><span className="k">Upside</span><span className={signClass(a.upside_pct)}>{pct(a.upside_pct, 1)}</span></div>
              <div className="row"><span className="k"># Analysts</span><span>{a.num_analysts ?? "—"}</span></div>
            </div>
          </div>
        </div>

        <div>
          <AdvisorPanel symbol={r.symbol} mode="stock" />

          <div className="card" style={{ marginTop: 16 }}>
            <div className="section-title">News</div>
            <div className="news-list">
              {r.news.length === 0 && <span className="mut">No recent headlines.</span>}
              {r.news.map((n, idx) => (
                <div className="news-item" key={idx}>
                  <a href={n.link} target="_blank" rel="noreferrer">{n.title}</a>
                  <div className="src">{n.publisher}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
