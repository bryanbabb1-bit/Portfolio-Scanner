"use client";
import { useEffect, useMemo, useState } from "react";
import { api, ConvictionSignal, PortfolioInsights, PortfolioSummary, StockReport } from "../lib/api";
import { SignalSlap } from "../components/SignalSlap";
import { PinnedActions } from "../components/PinnedActions";
import { ActionJournal } from "../components/ActionJournal";
import { StockCard } from "../components/StockCard";
import { PortfolioChart } from "../components/PortfolioChart";
import { HoldingsHeatmap } from "../components/HoldingsHeatmap";
import { AlertsPanel } from "../components/AlertsPanel";
import { RiskStats } from "../components/RiskStats";
import { Movers } from "../components/Movers";
import { PortfolioBrief } from "../components/PortfolioBrief";
import { SortControl, SortKey, sortReports } from "../components/SortControl";
import { money, pct, signClass } from "../components/format";

const REFRESH_MS = 60_000;

export default function Dashboard() {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [holdings, setHoldings] = useState<StockReport[]>([]);
  const [watchlist, setWatchlist] = useState<StockReport[]>([]);
  const [insights, setInsights] = useState<PortfolioInsights | null>(null);
  const [signals, setSignals] = useState<ConvictionSignal[]>([]);
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
      api
        .insights()
        .then(setInsights)
        .catch(() => setInsights(null));
      const demo = new URLSearchParams(window.location.search).has("demoSignal");
      api
        .signals(demo)
        .then((d) => setSignals(d.results))
        .catch(() => {});
    };
    load();
    const timer = setInterval(load, REFRESH_MS);
    const onFocus = () => load();
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onFocus);
    return () => {
      clearInterval(timer);
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

  const markDismissed = (ids: string[]) => {
    const set = new Set(ids);
    setSignals((cur) => cur.map((s) => (set.has(s.id) ? { ...s, dismissed: true } : s)));
  };
  const dismissOne = (id: string) => {
    markDismissed([id]);
    api.dismissSignal(id).catch(() => {});
  };
  const activeSignals = signals.filter((s) => !s.dismissed);

  return (
    <>
      <SignalSlap signals={signals} onDismissed={markDismissed} />

      {activeSignals.length > 0 && (
        <div className="card signal-strip" style={{ marginBottom: 24 }}>
          <div className="chart-head" style={{ marginBottom: 8 }}>
            <div className="section-title" style={{ margin: 0 }}>Conviction Signals · last 48h</div>
            <button
              className="btn ghost"
              onClick={() => {
                markDismissed(activeSignals.map((s) => s.id));
                api.dismissSignal().catch(() => {});
              }}
            >
              Clear all
            </button>
          </div>
          {activeSignals.map((s) => (
            <div key={s.id} className={`signal-row ${s.side}`}>
              <span className={`signal-side ${s.side}`}>{s.side === "buy" ? "BUY" : "SELL"}</span>
              <a href={`/stock/${s.symbol}`} className="alert-sym">{s.symbol}</a>
              <a href={`/stock/${s.symbol}`} className="signal-headline">{s.headline}</a>
              <span className="mut" style={{ fontSize: 11, marginLeft: "auto", whiteSpace: "nowrap" }}>
                {s.generated_at.slice(5, 16)}
              </span>
              <button
                className="icon-btn jr-btn"
                title="Dismiss — a new signal on this stock will pop again"
                onClick={() => dismissOne(s.id)}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      <PinnedActions />

      <ActionJournal />

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

      <Movers reports={[...holdings, ...watchlist]} />

      {insights && <AlertsPanel alerts={insights.alerts} />}

      <HoldingsHeatmap holdings={holdings} />

      <PortfolioChart />

      {insights && <RiskStats risk={insights.risk} />}

      <PortfolioBrief />

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
