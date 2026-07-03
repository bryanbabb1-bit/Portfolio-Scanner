"use client";
import { useEffect, useState } from "react";
import { api, ConvictionSignal, PortfolioInsights } from "../lib/api";

// The watchdog heartbeat: proof the app is standing guard, at a glance.
export function WatchdogBar({
  signals,
  insights,
}: {
  signals: ConvictionSignal[];
  insights: PortfolioInsights | null;
}) {
  const [armed, setArmed] = useState<number | null>(null);
  const [lastSweep, setLastSweep] = useState<string>("");

  useEffect(() => {
    const load = () =>
      api
        .watchpoints()
        .then((d) => {
          setArmed(d.results.filter((w) => w.status === "armed").length);
          setLastSweep(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
        })
        .catch(() => {});
    load();
    const t = setInterval(load, 60_000);
    return () => clearInterval(t);
  }, []);

  const active = signals.filter((s) => !s.dismissed).length;
  const criticals = insights?.alerts.filter((a) => a.severity === "critical").length ?? 0;

  return (
    <div className="watchdog-bar">
      <span className="wd-pulse" />
      <span className="wd-title">🐕 Watchdog on duty</span>
      <span className="wd-stat">{armed ?? "…"} tripwires armed</span>
      <span className="wd-sep">·</span>
      <span className="wd-stat">{active} live signal{active === 1 ? "" : "s"}</span>
      <span className="wd-sep">·</span>
      <span className={`wd-stat ${criticals ? "neg" : ""}`}>
        {criticals} critical alert{criticals === 1 ? "" : "s"}
      </span>
      {lastSweep && (
        <span className="wd-sweep mut">last sweep {lastSweep}</span>
      )}
    </div>
  );
}
