"use client";
import { useEffect, useState } from "react";
import { api, ConvictionSignal, PortfolioInsights } from "../lib/api";

function marketStatus(now: Date): { open: boolean; label: string } {
  // US equities, ET. Watchdog is active across the full tradeable window:
  // pre-market 7:00, regular 9:30-16:00, after-hours to 20:00. Weekdays only.
  const et = new Date(now.toLocaleString("en-US", { timeZone: "America/New_York" }));
  const day = et.getDay();
  const mins = et.getHours() * 60 + et.getMinutes();
  const preOpen = 7 * 60, open = 9 * 60 + 30, close = 16 * 60, postClose = 20 * 60;
  if (day < 1 || day > 5) return { open: false, label: "MARKET CLOSED · OPENS MON 7:00 ET" };
  if (mins < preOpen) return { open: false, label: "MARKET CLOSED · PRE-MARKET 7:00 ET" };
  if (mins < open) return { open: true, label: `PRE-MARKET · OPENS 9:30 ET` };
  if (mins < close) {
    const left = close - mins;
    return { open: true, label: `MARKET OPEN · ${Math.floor(left / 60)}H ${left % 60}M TO CLOSE` };
  }
  if (mins < postClose) {
    const left = postClose - mins;
    return { open: true, label: `AFTER-HOURS · ${Math.floor(left / 60)}H ${left % 60}M LEFT` };
  }
  return { open: false, label: "MARKET CLOSED · OPENS 7:00 ET" };
}

// The watchdog heartbeat: radar sweep, live market clock, and proof the app
// is standing guard — tripwires armed, signals live, criticals counted.
export function WatchdogBar({
  signals,
  insights,
}: {
  signals: ConvictionSignal[];
  insights: PortfolioInsights | null;
}) {
  const [armed, setArmed] = useState<number | null>(null);
  const [clock, setClock] = useState(() => marketStatus(new Date()));

  useEffect(() => {
    const load = () =>
      api
        .watchpoints()
        .then((d) => setArmed(d.results.filter((w) => w.status === "armed").length))
        .catch(() => {});
    load();
    const t = setInterval(load, 60_000);
    const c = setInterval(() => setClock(marketStatus(new Date())), 30_000);
    return () => {
      clearInterval(t);
      clearInterval(c);
    };
  }, []);

  const active = signals.filter((s) => !s.dismissed).length;
  const criticals = insights?.alerts.filter((a) => a.severity === "critical").length ?? 0;

  const goto = (id: string) => {
    const el = document.getElementById(id);
    el?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className={`watchdog-bar ${clock.open ? "" : "resting"}`}>
      <span className="radar" aria-hidden="true">
        <span className="radar-sweep" />
      </span>
      <span className="wd-title">{clock.open ? "WATCHDOG ACTIVE" : "WATCHDOG RESTING"}</span>
      <span className={`wd-market ${clock.open ? "open" : "closed"}`}>{clock.label}</span>
      <span className="wd-sep" />
      <button className="wd-stat" onClick={() => goto("game-plan")} title="Jump to your Game Plan">
        <strong>{armed ?? "–"}</strong> tripwires
      </button>
      <button className="wd-stat" onClick={() => goto("signal-strip")} title="Jump to live signals">
        <strong>{active}</strong> live signal{active === 1 ? "" : "s"}
      </button>
      <button className={`wd-stat ${criticals ? "neg" : ""}`} onClick={() => goto("needs-attention")} title="Jump to Needs Your Attention">
        <strong>{criticals}</strong> critical
      </button>
    </div>
  );
}
