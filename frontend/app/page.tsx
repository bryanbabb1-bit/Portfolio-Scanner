"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import "./mfx.css";
import {
  api,
  ConvictionSignal,
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
import { NightlyDesk, nightlyCount, useNightly } from "../components/NightlyDesk";
import { PinnedActions } from "../components/PinnedActions";
import { PortfolioBrief } from "../components/PortfolioBrief";
import { BigMoves } from "../components/BigMoves";
import { Blotter } from "../components/Blotter";
import { CatalystMap } from "../components/CatalystMap";
import { Accumulation } from "../components/Accumulation";
import { ProbabilityLattice } from "../components/ProbabilityLattice";
import { ActionJournal } from "../components/ActionJournal";
import { BalanceBar } from "../components/BalanceBar";
import { StockCard } from "../components/StockCard";
import { SortControl, SortKey, sortReports } from "../components/SortControl";
import { Bell } from "../components/Bell";
import { TelemetryStrip } from "../components/blueprint";
import { money } from "../components/format";

/* The home sheet.
 *
 * It had grown into one endless column: rulings, reassurance, chart, risk,
 * attribution, earnings, alerts, pins, brief, holdings, track record, graph,
 * allocation, journal. Everything worked and nothing could be found.
 *
 * Now the balance is pinned at the very top (BalanceBar keeps it on screen
 * while you scroll) and the rest is split into four tabs by the question each
 * one answers: what do I do today, what do I own, what did the desk rule, and
 * how have I actually done. Nothing was deleted — it was filed.
 */

const TABS = [
  { id: "today", label: "Today", hint: "What needs you" },
  { id: "book", label: "The Book", hint: "What you own" },
  { id: "desk", label: "The Desk", hint: "Overnight rulings" },
  { id: "record", label: "Track record", hint: "How it has gone" },
] as const;

type TabId = (typeof TABS)[number]["id"];
const isTab = (v: string | null): v is TabId => TABS.some((t) => t.id === v);
const TAB_KEY = "ps.dash.tab";

export default function Dashboard() {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [holdings, setHoldings] = useState<StockReport[]>([]);
  const [insights, setInsights] = useState<PortfolioInsights | null>(null);
  const [signals, setSignals] = useState<ConvictionSignal[]>([]);
  const [focusSlap, setFocusSlap] = useState<string | null>(null);
  const [forceBell, setForceBell] = useState<"open" | "close" | null>(null);
  const [sort, setSort] = useState<SortKey>("value");
  const [view, setView] = useState<"chart" | "heatmap" | "board">("chart");
  const [tab, setTab] = useState<TabId>("today");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const nightly = useNightly();

  useEffect(() => {
    const load = () => {
      api.portfolio().then((d) => { setSummary(d.summary); setHoldings(d.holdings); setErr(null); }).catch((e) => setErr(e.message)).finally(() => setLoading(false));
      api.insights().then(setInsights).catch(() => setInsights(null));
      const demo = new URLSearchParams(window.location.search).has("demoSignal");
      api.signals(demo).then((d) => setSignals(d.results)).catch(() => {});
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
  // /?tab=desk deep-links a tab; otherwise the last tab you used wins.
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const id = q.get("slap");
    if (id) setFocusSlap(id);
    // A tapped ticket push lands here too — it lives on the Today tab.
    if (id && id.startsWith("tk_")) setTab("today");
    const b = q.get("bell");
    if (b === "open" || b === "close") setForceBell(b);
    const t = q.get("tab");
    if (isTab(t)) setTab(t);
    else {
      const saved = localStorage.getItem(TAB_KEY);
      if (isTab(saved)) setTab(saved);
    }
  }, []);

  // A tab is somewhere you can link to and come back to, so it lives in the
  // URL — replaced rather than pushed, so Back still leaves the app.
  const goTab = useCallback((next: TabId) => {
    setTab(next);
    localStorage.setItem(TAB_KEY, next);
    const url = new URL(window.location.href);
    url.searchParams.set("tab", next);
    window.history.replaceState(null, "", url);
  }, []);

  // The watchdog strip's critical count jumps to the alerts, wherever they live.
  const jumpToAlerts = useCallback(() => {
    goTab("today");
    setTimeout(
      () => document.getElementById("needs-attention")?.scrollIntoView({ behavior: "smooth", block: "start" }),
      60,
    );
  }, [goTab]);

  const sortedHoldings = useMemo(() => sortReports(holdings, sort), [holdings, sort]);

  if (loading) return <div className="loading">Loading portfolio…</div>;
  if (err)
    return (
      <div className="err">
        Could not reach the backend ({err}). Start it with <code>uvicorn app.main:app --reload</code> in <code>backend/</code>.
      </div>
    );
  if (!summary) return null;

  const themeEntries = Object.entries(summary.by_theme).sort((a, b) => b[1] - a[1]);
  const alerts = insights?.alerts ?? [];
  const deskCount = nightlyCount(nightly);
  const badges: Record<TabId, number> = {
    today: alerts.length,
    book: 0,
    desk: deskCount,
    record: 0,
  };

  const markDismissed = (ids: string[]) => {
    const set = new Set(ids);
    setSignals((cur) => cur.map((s) => (set.has(s.id) ? { ...s, dismissed: true } : s)));
  };

  return (
    <>
      <Bell summary={summary} holdings={holdings} force={forceBell} />
      <SignalSlap signals={signals} onDismissed={markDismissed} focusId={focusSlap} />

      {/* 1 — the balance. First on the page, and pinned once it scrolls away. */}
      <BalanceBar summary={summary} />

      {/* 2 — the heartbeat strip: market clock, tripwires, criticals. */}
      <WatchdogBar signals={signals} insights={insights} onAlerts={jumpToAlerts} />

      {/* 3 — everything else, filed by the question it answers. */}
      <div className="dash-tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            className={tab === t.id ? "active" : ""}
            onClick={() => goTab(t.id)}
          >
            <span className="dt-label">
              {t.label}
              {badges[t.id] > 0 && <span className="dt-badge">{badges[t.id]}</span>}
            </span>
            <span className="dt-hint">{t.hint}</span>
          </button>
        ))}
      </div>

      {tab === "today" && (
        <>
          {/* The blotter first: tickets waiting on a decision. This is the
              one panel that asks for an action instead of offering a read. */}
          <Blotter focusId={focusSlap && focusSlap.startsWith("tk_") ? focusSlap : null} />

          {/* The whole market, above the book. He asked to be told what is
              happening regardless of whether he can act on it. */}
          <BigMoves />

          <StayTheCourse />

          {alerts.length > 0 && (
            <>
              <div className="mfx-label">Needs your attention</div>
              <AlertsPanel alerts={alerts} />
            </>
          )}

          <div className="mfx-label">The read &amp; the plan</div>
          <PortfolioBrief />

          <PinnedActions />

          {/* What could move a holding hard, and which smaller name it would
              move harder. Built after MRNA. */}
          <CatalystMap />

          {/* The general case, and the only one measured to lead the move:
              an 8-K is filed with the press release, volume shows up before
              it. This replaced the filings feed. */}
          <Accumulation />

          <div className="mfx-grid two">
            <DailyAttribution holdings={holdings} dayChange={summary.day_change} />
            <EarningsRunway holdings={holdings} />
          </div>
        </>
      )}

      {tab === "book" && (
        <>
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

          {insights && <RiskStats risk={insights.risk} />}

          <div className="list-head">
            <div className="section-title" style={{ margin: 0 }}>Holdings</div>
            <SortControl sort={sort} setSort={setSort} />
          </div>
          <div className="grid grid-cards">
            {sortedHoldings.map((r) => <StockCard key={r.symbol} r={r} />)}
          </div>

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
        </>
      )}

      {tab === "desk" && (
        <>
          <NightlyDesk n={nightly} />
          {nightly && deskCount === 0 && !(nightly.queue ?? []).length && (
            <div className="card tab-empty">
              The desk has not sat yet. It convenes overnight — the rulings land here.
            </div>
          )}
          <div className="tab-more">
            <Link href="/debate">Convene a debate →</Link>
            <Link href="/risk">Risk Desk →</Link>
            <Link href="/backtest">Backtest a rule →</Link>
          </div>
        </>
      )}

      {tab === "record" && (
        <>
          <ProbabilityLattice />
          <div style={{ marginTop: 18 }}><RelationshipGraph /></div>
          <div style={{ marginTop: 18 }}><ActionJournal /></div>
          <div className="tab-more">
            <Link href="/loop">Learning Loop →</Link>
            <Link href="/book">The thesis book →</Link>
          </div>
        </>
      )}

      <div className="mfx-foot">
        <div className="mfx-status">
          <span className="on" /> Watchdog online · advisor Claude · {summary.positions} positions · {summary.source} data
        </div>
        <Link href="/discover">Discovery</Link>
        <Link href="/scan">Scan Hub</Link>
        <Link href="/news">News Wire</Link>
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
