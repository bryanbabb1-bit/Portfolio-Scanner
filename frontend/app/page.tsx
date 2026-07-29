"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import "./mfx.css";
import {
  api,
  ConvictionSignal,
  PortfolioHistory,
  PortfolioInsights,
  PortfolioSummary,
  StockReport,
} from "../lib/api";
import { DailyAttribution } from "../components/DailyAttribution";
import { EarningsRunway } from "../components/EarningsRunway";
import { RelationshipGraph } from "../components/RelationshipGraph";
import { WatchdogBar } from "../components/WatchdogBar";
import { SignalSlap } from "../components/SignalSlap";
import { PortfolioChart } from "../components/PortfolioChart";
import { HoldingsHeatmap } from "../components/HoldingsHeatmap";
import { HoldingsBoard } from "../components/HoldingsBoard";
import { StayTheCourse } from "../components/StayTheCourse";
import { AlertsPanel } from "../components/AlertsPanel";
import { RiskStats } from "../components/RiskStats";
import { PositionHealth } from "../components/PositionHealth";
import { PortfolioBrief } from "../components/PortfolioBrief";
import { DailyBrief } from "../components/DailyBrief";
import { ProbabilityLattice } from "../components/ProbabilityLattice";
import { ActionJournal } from "../components/ActionJournal";
import { StockCard } from "../components/StockCard";
import { SortControl, SortKey, sortReports } from "../components/SortControl";
import { Odometer } from "../components/Odometer";
import { RoomTemperature } from "../components/RoomTemperature";
import { Bell } from "../components/Bell";
import { SpecHeader, TelemetryStrip } from "../components/blueprint";
import { money, pct } from "../components/format";

/* The home sheet. Blueprint chrome (masthead, telemetry footer) wraps the
   real dashboard components in a multi-column layout. Theme tokens are global
   (globals.css); blueprint primitives live in components/blueprint. */

export default function Dashboard() {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [holdings, setHoldings] = useState<StockReport[]>([]);
  const [insights, setInsights] = useState<PortfolioInsights | null>(null);
  const [signals, setSignals] = useState<ConvictionSignal[]>([]);
  const [hist, setHist] = useState<PortfolioHistory | null>(null);
  const [focusSlap, setFocusSlap] = useState<string | null>(null);
  const [forceBell, setForceBell] = useState<"open" | "close" | null>(null);
  const [sort, setSort] = useState<SortKey>("value");
  const [view, setView] = useState<"chart" | "heatmap" | "board">("chart");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = () => {
      api.portfolio().then((d) => { setSummary(d.summary); setHoldings(d.holdings); setErr(null); }).catch((e) => setErr(e.message)).finally(() => setLoading(false));
      api.insights().then(setInsights).catch(() => setInsights(null));
      const demo = new URLSearchParams(window.location.search).has("demoSignal");
      api.signals(demo).then((d) => setSignals(d.results)).catch(() => {});
      api.portfolioHistory("6mo").then(setHist).catch(() => {});
    };
    load();
    const t = setInterval(load, 60_000);
    const onFocus = () => load();
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onFocus);
    return () => {
      clearInterval(t);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onFocus);
    };
  }, []);

  // A tapped push notification lands on /?slap=<id> — surface that slap.
  // /?bell=open|close previews the ritual without waiting for 9:30.
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const id = q.get("slap");
    if (id) setFocusSlap(id);
    const b = q.get("bell");
    if (b === "open" || b === "close") setForceBell(b);
  }, []);

  const sortedHoldings = useMemo(() => sortReports(holdings, sort), [holdings, sort]);

  if (loading) return <div className="loading">Loading portfolio…</div>;
  if (err)
    return (
      <div className="err">
        Could not reach the backend ({err}). Start it with <code>uvicorn app.main:app --reload</code> in <code>backend/</code>.
      </div>
    );
  if (!summary) return null;

  // The goal-progress card and its projection were removed with the strategy
  // document. The standing mandate is qualitative — aggressive, double-digit
  // growth, little new capital — not a dated dollar target to grade against.
  const themeEntries = Object.entries(summary.by_theme).sort((a, b) => b[1] - a[1]);

  const markDismissed = (ids: string[]) => {
    const set = new Set(ids);
    setSignals((cur) => cur.map((s) => (set.has(s.id) ? { ...s, dismissed: true } : s)));
  };

  return (
    <>
      <RoomTemperature dayPct={summary.day_change_pct} />
      <Bell summary={summary} holdings={holdings} force={forceBell} />

      <SignalSlap signals={signals} onDismissed={markDismissed} focusId={focusSlap} />

      <SpecHeader system="PORTFOLIO SCANNER" version="2.0" />

      <WatchdogBar signals={signals} insights={insights} />

      {/* account header */}
      <header className="mfx-head">
        <div className="lead">
          <div className="eyebrow"><span className="pulse" /> Book · {summary.positions} positions · {summary.source} data</div>
          <div className="val">
            <Odometer value={summary.total_market_value} prefix="$" />
          </div>
          <div className="deltas">
            <span className={`mfx-chip ${summary.day_change >= 0 ? "up" : "down"}`}>
              <span className="k">Today</span>{money(summary.day_change, 0)} ({pct(summary.day_change_pct)})
            </span>
            <span className={`mfx-chip ${summary.total_unrealized_pl >= 0 ? "up" : "down"}`}>
              <span className="k">Unrealized</span>{money(summary.total_unrealized_pl, 0)} ({pct(summary.total_unrealized_pl_pct)})
            </span>
            {summary.realized_pl !== 0 && (
              <span className={`mfx-chip ${summary.realized_pl >= 0 ? "up" : "down"}`}>
                <span className="k">Realized</span>{money(summary.realized_pl, 0)}
              </span>
            )}
            <span className={`mfx-chip total ${summary.total_return >= 0 ? "up" : "down"}`}>
              <span className="k">Total return</span>{money(summary.total_return, 0)} ({pct(summary.total_return_pct)})
            </span>
          </div>
        </div>
        <div className="quickstats">
          <div className="qs"><div className="l">Cost basis</div><div className="v">{money(summary.total_cost, 0)}</div></div>
          <div className="qs"><div className="l">Dry powder</div><div className="v">{money(summary.cash, 0)}</div></div>
          <div className="qs"><div className="l">Positions</div><div className="v">{summary.positions}</div></div>
        </div>
      </header>

      {/* the long game — earned permission to hold (or a nudge to act) */}
      <StayTheCourse />

      {/* row 1 — chart (main) + goal & risk (rail) */}
      <div className="mfx-grid split">
        <div className="mfx-col">
          <div className="view-tabs">
            <div className="range-toggle">
              <button className={view === "chart" ? "active" : ""} onClick={() => setView("chart")}>Value</button>
              <button className={view === "heatmap" ? "active" : ""} onClick={() => setView("heatmap")}>Heatmap</button>
              <button className={view === "board" ? "active" : ""} onClick={() => setView("board")}>Board</button>
            </div>
          </div>
          {view === "chart" ? (
            <PortfolioChart />
          ) : view === "heatmap" ? (
            <HoldingsHeatmap holdings={holdings} />
          ) : (
            <HoldingsBoard holdings={holdings} />
          )}
        </div>
        <div className="mfx-col">
          {insights && <RiskStats risk={insights.risk} />}
          <DailyAttribution holdings={holdings} dayChange={summary.day_change} />
        </div>
      </div>

      <EarningsRunway holdings={holdings} />

      {/* row 2 — what to do. The brief owns the plan now; there is no separate
          plan board or transition feature to disagree with it. */}
      <div className="mfx-label">What to do</div>
      <div className="mfx-grid two">
        {insights && insights.alerts.length > 0 ? <AlertsPanel alerts={insights.alerts} /> : <DailyBrief />}
        <PositionHealth holdings={holdings} />
      </div>

      {/* row 3 — the read AND the plan. One surface, full width, because it is
          now the only thing in the app that issues orders. */}
      <div className="mfx-label">The read &amp; the plan</div>
      <PortfolioBrief />

      {/* holdings */}
      <div className="list-head">
        <div className="section-title" style={{ margin: 0 }}>Holdings</div>
        <SortControl sort={sort} setSort={setSort} />
      </div>
      <div className="grid grid-cards">
        {sortedHoldings.map((r) => <StockCard key={r.symbol} r={r} />)}
      </div>

      {/* track record — the probability lattice */}
      <div className="mfx-label" style={{ marginTop: 24 }}>Track record</div>
      <ProbabilityLattice />

      <div style={{ marginTop: 18 }}><RelationshipGraph /></div>

      {/* allocation */}
      {themeEntries.length > 0 && (
        <div className="card" style={{ marginTop: 18 }}>
          <div className="section-title" style={{ marginBottom: 14 }}>Allocation by theme</div>
          <div className="alloc-bars">
            {themeEntries.map(([theme, v]) => {
              const share = (v / summary.total_market_value) * 100;
              return (
                <div key={theme} className="alloc-row">
                  <span className="alloc-name">{theme}</span>
                  <div className="alloc-track"><div className="alloc-fill" style={{ width: `${Math.max(share, 1.5)}%` }} /></div>
                  <span className="alloc-val">{money(v, 0)} <span className="mut">· {share.toFixed(1)}%</span></span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div style={{ marginTop: 18 }}><ActionJournal /></div>

      <div className="mfx-foot">
        <div className="mfx-status">
          <span className="on" /> Watchdog online · advisor Claude · {summary.positions} positions · {summary.source} data
        </div>
        <Link href="/risk">Risk Desk</Link>
        <Link href="/debate">Agent Debate</Link>
        <Link href="/backtest">Backtest</Link>
        <Link href="/discover">Discovery</Link>
        <Link href="/settings">Settings</Link>
      </div>

      <TelemetryStrip
        right={[
          ["Engine", "LOCAL"],
          ["Model", "CLAUDE"],
          ["Data", summary.source.toUpperCase()],
        ]}
        line1="Discipline. Data. Decisions."
        line2="Built to compound."
      />
    </>
  );
}
