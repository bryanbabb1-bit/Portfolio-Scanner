"use client";
import { useEffect, useState } from "react";
import { PortfolioSummary, StockReport } from "../lib/api";
import { money, pct } from "./format";

/* The bell — the two moments that bracket a session.
 *
 * 9:30: the book wakes and the positions deal in.
 * 16:00: the day resolves into one card and the book goes to sleep.
 *
 * Fires ONCE per event per day, tracked in localStorage, so a refresh or a
 * second tab doesn't replay it. Three seconds, then it gets out of the way —
 * the whole premise of the excitement layer is that the baseline stays calm,
 * so a ritual that overstays becomes the thing you dread.
 */

type Kind = "open" | "close";

function nowET() {
  // The market keeps New York hours regardless of where the client is.
  const s = new Date().toLocaleString("en-US", { timeZone: "America/New_York" });
  return new Date(s);
}

function todayET() {
  return nowET().toISOString().slice(0, 10);
}

/** Which bell, if any, is within its window right now. */
function dueBell(): Kind | null {
  const et = nowET();
  if (et.getDay() === 0 || et.getDay() === 6) return null;
  const mins = et.getHours() * 60 + et.getMinutes();
  // A generous window so the ritual still fires if you open the app a few
  // minutes late — but not so wide it ambushes you mid-afternoon.
  if (mins >= 570 && mins <= 585) return "open";   // 9:30 – 9:45
  if (mins >= 960 && mins <= 975) return "close";  // 16:00 – 16:15
  return null;
}

export function Bell({
  summary,
  holdings,
  force,
  onDone,
}: {
  summary: PortfolioSummary;
  holdings: StockReport[];
  /** Set from ?bell=open|close to preview it on demand. */
  force?: Kind | null;
  onDone?: () => void;
}) {
  const [kind, setKind] = useState<Kind | null>(null);
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    if (force) {
      setKind(force);
      return;
    }
    const due = dueBell();
    if (!due) return;
    const key = `wd.bell.${due}.${todayET()}`;
    try {
      if (localStorage.getItem(key)) return; // already rung today
      localStorage.setItem(key, "1");
    } catch {
      /* private mode — ring it, just don't remember */
    }
    setKind(due);
  }, [force]);

  useEffect(() => {
    if (!kind) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const hold = reduce ? 1400 : 4200;
    const a = setTimeout(() => setLeaving(true), hold);
    const b = setTimeout(() => {
      setKind(null);
      setLeaving(false);
      onDone?.();
    }, hold + 500);
    return () => {
      clearTimeout(a);
      clearTimeout(b);
    };
  }, [kind, onDone]);

  if (!kind) return null;

  const cards = [...holdings]
    .filter((r) => (r.market_value ?? 0) > 0)
    .sort((a, b) => (b.market_value ?? 0) - (a.market_value ?? 0))
    .slice(0, 15);

  const up = summary.day_change >= 0;

  return (
    <div
      className={`bell ${kind} ${leaving ? "out" : ""}`}
      role="status"
      aria-live="polite"
      onClick={() => setLeaving(true)}
    >
      <div className="bell-flash" aria-hidden />

      <div className="bell-word">
        <span className="display">{kind === "open" ? "The Open" : "The Close"}</span>
      </div>

      {kind === "open" ? (
        <div className="bell-deal" aria-hidden>
          {cards.map((r, i) => {
            const rup = r.quote.change_pct >= 0;
            return (
              <div
                key={r.symbol}
                className="bell-card"
                style={{ animationDelay: `${1.05 + i * 0.035}s` }}
              >
                <span className="bc-sym">{r.symbol}</span>
                <span className={`bc-chg ${rup ? "up" : "down"}`}>
                  {rup ? "+" : ""}
                  {r.quote.change_pct.toFixed(2)}%
                </span>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="bell-resolve">
          <div className="br-card">
            <span className="br-k">Session closed</span>
            <span className={`br-v ${up ? "up" : "down"}`}>
              {money(summary.day_change, 0)}
            </span>
            <span className="br-sub">
              {pct(summary.day_change_pct)} · book {money(summary.total_market_value, 0)}
            </span>
          </div>
        </div>
      )}

      <span className="bell-dismiss">Tap to dismiss</span>
    </div>
  );
}
