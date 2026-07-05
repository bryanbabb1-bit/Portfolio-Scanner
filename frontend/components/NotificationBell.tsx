"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, ConvictionSignal } from "../lib/api";

// In-app notification inbox: a bell in the nav with the active watchdog
// signals, so you can see your slaps from any page without leaving the app.
export function NotificationBell() {
  const [signals, setSignals] = useState<ConvictionSignal[]>([]);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const load = () =>
      api.signals().then((d) => setSignals(d.results.filter((s) => !s.dismissed))).catch(() => {});
    load();
    const t = setInterval(load, 60_000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  async function dismiss(id: string, e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setSignals((cur) => cur.filter((s) => s.id !== id));
    api.dismissSignal(id).catch(() => {});
  }

  const count = signals.length;

  return (
    <div className="bell-wrap" ref={ref}>
      <button
        className={`bell ${count ? "has" : ""}`}
        onClick={() => setOpen((o) => !o)}
        aria-label="Notifications"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.7 21a2 2 0 0 1-3.4 0" />
        </svg>
        {count > 0 && <span className="bell-badge">{count > 9 ? "9+" : count}</span>}
      </button>

      {open && (
        <div className="bell-menu">
          <div className="bell-head">
            Signals
            {count > 0 && (
              <button
                className="bell-clear"
                onClick={() => {
                  setSignals([]);
                  api.dismissSignal().catch(() => {});
                }}
              >
                Clear all
              </button>
            )}
          </div>
          {count === 0 ? (
            <div className="bell-empty">No active signals. The watchdog is quiet.</div>
          ) : (
            <div className="bell-list">
              {signals.map((s) => (
                <Link
                  key={s.id}
                  href={`/stock/${s.symbol}`}
                  className={`bell-item ${s.side}`}
                  onClick={() => setOpen(false)}
                >
                  <span className={`signal-side ${s.side}`}>{s.side === "buy" ? "BUY" : "SELL"}</span>
                  <span className="bell-sym">{s.symbol}</span>
                  <span className="bell-headline">{s.headline}</span>
                  <button className="icon-btn jr-btn" title="Dismiss" onClick={(e) => dismiss(s.id, e)}>✕</button>
                </Link>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
