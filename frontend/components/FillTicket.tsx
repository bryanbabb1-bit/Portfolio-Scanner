"use client";
import { useEffect, useState } from "react";
import { JournalEntry } from "../lib/api";
import { money } from "./format";

/* The fill — a physical ticket stamps down when a trade is logged.
 *
 * Deliberately this rewards RECORDING the trade, not making one. The journal
 * is what stops the advisor re-recommending a move you already made and what
 * powers the rule against reversing a fresh buy — so logging is the habit the
 * whole system depends on, and it is the habit that gets the moment.
 */
export function FillTicket({
  entry,
  onDone,
}: {
  entry: JournalEntry | null;
  onDone: () => void;
}) {
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    if (!entry) return;
    setLeaving(false);
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const hold = reduce ? 1200 : 2600;
    const out = setTimeout(() => setLeaving(true), hold);
    const gone = setTimeout(onDone, hold + 420);
    return () => {
      clearTimeout(out);
      clearTimeout(gone);
    };
  }, [entry, onDone]);

  if (!entry) return null;

  const side = String(entry.action || "").toLowerCase();
  const verb = side === "sell" ? "Sold" : side === "buy" ? "Bought" : "Logged";
  const value =
    entry.shares && entry.price ? entry.shares * entry.price : null;

  return (
    <div className={`fill-wrap ${leaving ? "out" : ""}`} role="status" aria-live="polite">
      <div className="fill-ticket">
        <div className="ft-k">Watchdog · execution</div>
        <h4 className="ft-head">
          {verb} {entry.symbol || "position"}
        </h4>

        <div className="ft-lines">
          {entry.shares != null && (
            <div className="ft-line">
              <span>Shares</span>
              <b>{entry.shares}</b>
            </div>
          )}
          {entry.price != null && (
            <div className="ft-line">
              <span>Price</span>
              <b>{money(entry.price)}</b>
            </div>
          )}
          {value != null && (
            <div className="ft-line">
              <span>Value</span>
              <b>{money(value)}</b>
            </div>
          )}
          <div className="ft-line">
            <span>Date</span>
            <b>{entry.date}</b>
          </div>
        </div>

        <span className={`ft-stamp ${side}`}>
          {side === "sell" ? "Sold" : side === "buy" ? "Filled" : "Logged"}
        </span>
      </div>
    </div>
  );
}
