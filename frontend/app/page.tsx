"use client";
import { useEffect, useMemo, useState } from "react";
import { api, PortfolioSummary, StockReport } from "../lib/api";
import { StockCard } from "../components/StockCard";
import { PortfolioChart } from "../components/PortfolioChart";
import { SortControl, SortKey, sortReports } from "../components/SortControl";
import { money, pct, signClass } from "../components/format";

export default function Dashboard() {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [holdings, setHoldings] = useState<StockReport[]>([]);
  const [watchlist, setWatchlist] = useState<StockReport[]>([]);
  const [sort, setSort] = useState<SortKey>("value");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = () => {
      api
        .portfolio()
        .then((d) => {
          setSummary(d.summary);
          setHoldings(d.holdings);
          setErr(null);
        })
        .catch((e) => setErr(e.message))
        .finally(() => setLoading(false));
      api
        .watchlist()
        .then((d) => setWatchlist(d.results))
        .catch(() => setWatchlist([]));
    };
    load();
    const onFocus = () => load();
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onFocus);
    return () => {
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onFocus);
    };
  }, []);

  const sortedHoldings = useMemo(() => sortReports(holdings, sort), [holdings, sort]);
  const sortedWatch = useMemo(
    () => sortReports(watchlist, sort === "return" ? "change" : sort),
    [watchlist, sort]
  );

  if (loading) return <div className="loading">Loading portfolio…</div>;
  if (err)
    return (
      <div className="err">
        Could not reach the backend ({err}). Start it with{" "}
        <code>uvicorn app.main:app --reload</code> in <code>backend/</code>.
      </div>
    );
  if (!summary) return null;

  const themeEntries = Object.entries(summary.by_theme).sort((a, b) => b[1] - a[1]);

  return (
    <>
      <div className="hero">
        <div className="hero-glow" />
        <div className="hero-main">
          <span className="eyebrow">
            <span className="pulse" /> Portfolio · {summary.positions} positions ·{" "}
            <span className={summary.source === "mock" ? "mut" : "pos"}>{summary.source} data</span>
          </span>
          <div className="hero-value">{money(summary.total_market_value)}</div>
          <div className="hero-sub">
            <span className={signClass(summary.day_change)}>
              {summary.day_change >= 0 ? "▲" : "▼"} {money(summary.day_change)} ({pct(summary.day_change_pct)}) today
            </span>
            <span className="dot">·</span>
            <span className={signClass(summary.total_unrealized_pl)}>
              {money(summary.total_unrealized_pl)} ({pct(summary.total_unrealized_pl_pct)}) all-time
            </span>
          </div>
        </div>
        <div className="hero-stats">
          <div className="hstat">
            <span className="label">Unrealized P/L</span>
            <span className={`value ${signClass(summary.total_unrealized_pl)}`}>{money(summary.total_unrealized_pl, 0)}</span>
          </div>
          <div className="hstat">
            <span className="label">Cost Basis</span>
            <span className="value">{money(summary.total_cost, 0)}</span>
          </div>
          <div className="hstat">
            <span className="label">Day Change</span>
            <span className={`value ${signClass(summary.day_change)}`}>{money(summary.day_change, 0)}</span>
          </div>
        </div>
      </div>

      <PortfolioChart />

      {themeEntries.length > 0 && (
        <div style={{ marginBottom: 28 }}>
          <div className="section-title">Allocation by Theme</div>
          <div className="alloc-bars">
            {themeEntries.map(([theme, val]) => {
              const share = (val / summary.total_market_value) * 100;
              return (
                <div key={theme} className="alloc-row">
                  <span className="alloc-name">{theme}</span>
                  <div className="alloc-track">
                    <div className="alloc-fill" style={{ width: `${Math.max(share, 1.5)}%` }} />
                  </div>
                  <span className="alloc-val">{money(val, 0)} <span className="mut">· {share.toFixed(1)}%</span></span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="list-head">
        <div className="section-title" style={{ margin: 0 }}>Holdings</div>
        <SortControl sort={sort} setSort={setSort} />
      </div>
      <div className="grid grid-cards">
        {sortedHoldings.map((r) => (
          <StockCard key={r.symbol} r={r} />
        ))}
      </div>

      {sortedWatch.length > 0 && (
        <div style={{ marginTop: 32 }}>
          <div className="section-title">
            Watchlist <span className="mut" style={{ textTransform: "none", letterSpacing: 0 }}>· names you're tracking</span>
          </div>
          <div className="grid grid-cards">
            {sortedWatch.map((r) => (
              <StockCard key={r.symbol} r={r} />
            ))}
          </div>
        </div>
      )}
    </>
  );
}
