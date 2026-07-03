"use client";
import { useEffect, useState } from "react";
import { api, ConvictionSignal, PortfolioInsights } from "../lib/api";

function marketStatus(now: Date): { open: boolean; label: string } {
  // US equities, ET. Holidays not modeled — weekday sessions only.
  const et = new Date(now.toLocaleString("en-US", { timeZone: "America/New_York" }));
  const day = et.getDay();
  const mins = et.getHours() * 60 + et.getMinutes();
  const openMin = 9 * 60 + 30;
  const closeMin = 16 * 60;
  if (day >= 1 && day <= 5 && mins >= openMin && mins < closeMin) {
    const left = closeMin - mins;
    return { open: true, label: `MARKET OPEN · ${Math.floor(left / 60)}H ${left % 60}M TO CLOSE` };
  }
  return { open: false, label: "MARKET CLOSED · OPENS 9:30 ET" };
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

  return (
    <div className="watchdog-bar">
      <span className="radar" aria-hidden="true">
        <span className="radar-sweep" />
      </span>
      <span className="wd-title">WATCHDOG ACTIVE</span>
      <span className={`wd-market ${clock.open ? "open" : "closed"}`}>{clock.label}</span>
      <span className="wd-sep" />
      <span className="wd-stat">
        <strong>{armed ?? "–"}</strong> tripwires
      </span>
      <span className="wd-stat">
        <strong>{active}</strong> live signal{active === 1 ? "" : "s"}
      </span>
      <span className={`wd-stat ${criticals ? "neg" : ""}`}>
        <strong>{criticals}</strong> critical
      </span>
    </div>
  );
}
