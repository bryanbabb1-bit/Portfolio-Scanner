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
  StrategyDoc,
} from "../lib/api";
import { DailyAttribution } from "../components/DailyAttribution";
import { EarningsRunway } from "../components/EarningsRunway";
import { RelationshipGraph } from "../components/RelationshipGraph";
import { WatchdogBar } from "../components/WatchdogBar";
import { SignalSlap } from "../components/SignalSlap";
import { PortfolioChart } from "../components/PortfolioChart";
import { HoldingsHeatmap } from "../components/HoldingsHeatmap";
import { PlanBoard } from "../components/PlanBoard";
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
  const [strategy, setStrategy] = useState<StrategyDoc | null>(null);
  const [hist, setHist] = useState<PortfolioHistory | null>(null);
  const [focusSlap, setFocusSlap] = useState<string | null>(null);
  const [sort, setSort] = useState<SortKey>("value");
  const [view, setView] = useState<"chart" | "heatmap">("chart");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = () => {
      api.portfolio().then((d) => { setSummary(d.summary); setHoldings(d.holdings); setErr(null); }).catch((e) => setErr(e.message)).finally(() => setLoading(false));
      api.insights().then(setInsights).catch(() => setInsights(null));
      const demo = new URLSearchParams(window.location.search).has("demoSignal");
      api.signals(demo).then((d) => setSignals(d.results)).catch(() => {});
      api.strategy().then((s) => s && setStrategy(s)).catch(() => {});
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
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("slap");
    if (id) setFocusSlap(id);
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

  const target = strategy?.goals?.target_value ?? 25000;
  const monthly = strategy?.goals?.monthly_contribution ?? 0;
  const val = summary.total_market_value;
  const progress = Math.max(0, Math.min(100, (val / target) * 100));
  const gap = Math.max(0, target - val);

  // goal trajectory: annualized growth from the 6-month history + monthly
  // contributions, simulated forward to the target.
  const projMonths = (() => {
    if (val >= target) return 0;
    let g = 0.08; // fallback annual growth if history is unavailable
    if (hist && hist.points.length > 5) {
      const first = hist.points[0].value;
      const last = hist.points[hist.points.length - 1].value;
      if (first > 0) {
        const ann = Math.pow(last / first, 1 / 0.5) - 1; // 6-month window annualized
        if (isFinite(ann)) g = Math.max(-0.3, Math.min(0.6, ann));
      }
    }
    let cur = val, m = 0;
    while (cur < target && m < 600) { cur = cur * (1 + g / 12) + monthly; m++; }
    return m >= 600 ? null : m;
  })();
  const horizonM = (() => {
    const h = strategy?.goals?.horizon;
    const mt = h?.match(/(\d+)\s*(year|yr|month|mo)/i);
    return mt ? (/year|yr/i.test(mt[2]) ? +mt[1] * 12 : +mt[1]) : null;
  })();
  const projDate = (() => {
    if (projMonths == null) return null;
    const d = new Date();
    d.setMonth(d.getMonth() + projMonths);
    return d.toLocaleDateString("en-US", { month: "short", year: "numeric" });
  })();

  const themeEntries = Object.entries(summary.by_theme).sort((a, b) => b[1] - a[1]);

  const markDismissed = (ids: string[]) => {
    const set = new Set(ids);
    setSignals((cur) => cur.map((s) => (set.has(s.id) ? { ...s, dismissed: true } : s)));
  };

  return (
    <>
      <SignalSlap signals={signals} onDismissed={markDismissed} focusId={focusSlap} />

      <SpecHeader system="PORTFOLIO SCANNER" version="2.0" />

      <WatchdogBar signals={signals} insights={insights} />

      {/* account header */}
      <header className="mfx-head">
        <div className="lead">
          <div className="eyebrow"><span className="pulse" /> Book · {summary.positions} positions · {summary.source} data</div>
          <div className="val">{money(summary.total_market_value)}</div>
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
            </div>
          </div>
          {view === "chart" ? <PortfolioChart /> : <HoldingsHeatmap holdings={holdings} />}
        </div>
        <div className="mfx-col">
          <div className="card goal">
            <div className="goal-top">
              <span className="t">Goal progress</span>
              <span className="pctto">{progress.toFixed(0)}% there</span>
            </div>
            <div className="track">
              <div className="fill" style={{ width: `${progress}%` }} />
              {[0.25, 0.5, 0.75].map((m) => <div key={m} className="tick" style={{ left: `${m * 100}%` }} />)}
            </div>
            <div className="goal-foot">
              <span><b>{money(val, 0)}</b> today</span>
              <span><b>{money(gap, 0)}</b> to go · <span className="g">{money(target, 0)} goal</span></span>
            </div>
            <div className="pace">
              {strategy?.goals?.horizon ? <>Horizon <b>{strategy.goals.horizon}</b>{strategy.goals.risk_appetite ? <> · <b>{strategy.goals.risk_appetite}</b> risk</> : null}{monthly > 0 ? <> · adding <b>{money(monthly, 0)}/mo</b></> : null}.</> : "Set a target on the Strategy page to track the climb."}
              {val < target && (
                <div className="goal-proj">
                  {projMonths == null ? (
                    <>At the current pace you don&apos;t reach {money(target, 0)} yet — it needs more growth or contributions.</>
                  ) : (
                    <>On this pace: <b>{money(target, 0)} by {projDate}</b> (~{projMonths} mo)
                    {horizonM != null && projMonths <= horizonM ? <> · <span className="ahead">{horizonM - projMonths} mo ahead</span> of your goal.</>
                     : horizonM != null ? <> · <span className="behind">{projMonths - horizonM} mo behind</span> your goal.</> : <>.</>}</>
                  )}
                </div>
              )}
            </div>
          </div>
          {insights && <RiskStats risk={insights.risk} />}
          <DailyAttribution holdings={holdings} dayChange={summary.day_change} />
        </div>
      </div>

      <EarningsRunway holdings={holdings} />

      {/* row 2 — what to do */}
      <div className="mfx-label">What to do</div>
      <div className="mfx-grid two">
        <PlanBoard />
        {insights && insights.alerts.length > 0 ? <AlertsPanel alerts={insights.alerts} /> : <DailyBrief />}
      </div>

      {/* row 3 — the read */}
      <div className="mfx-label">The read</div>
      <div className="mfx-grid two">
        <PortfolioBrief />
        <PositionHealth holdings={holdings} />
      </div>

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
        <Link href="/strategy">Strategy</Link>
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
