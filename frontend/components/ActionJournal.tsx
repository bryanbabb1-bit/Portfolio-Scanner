"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, JournalEntry } from "../lib/api";

const ACTION_META: Record<string, { label: string; cls: string }> = {
  sold: { label: "SOLD", cls: "sell" },
  trimmed: { label: "TRIM", cls: "warn" },
  added: { label: "ADD", cls: "buy" },
  opened: { label: "NEW", cls: "buy" },
  completed: { label: "DONE", cls: "done" },
};

const COLLAPSED = 5;

// What you've actually done — auto-detected trades + completed pinned advice.
// The same log is fed to the advisor so it recommends the next step instead
// of re-prescribing from scratch.
export function ActionJournal() {
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    const load = () => api.journal().then((d) => setEntries(d.results)).catch(() => {});
    load();
    const t = setInterval(load, 60_000);
    return () => clearInterval(t);
  }, []);

  if (!entries.length) return null;
  const shown = expanded ? entries : entries.slice(0, COLLAPSED);

  return (
    <div className="card journal-panel" style={{ marginBottom: 24 }}>
      <div className="chart-head" style={{ marginBottom: 8 }}>
        <div className="section-title" style={{ margin: 0 }}>
          Action Journal{" "}
          <span className="mut" style={{ textTransform: "none", letterSpacing: 0 }}>
            · {entries.length} moves in 30 days · the advisor sees this
          </span>
        </div>
        {entries.length > COLLAPSED && (
          <button className="btn ghost" onClick={() => setExpanded(!expanded)}>
            {expanded ? "Show less" : `Show all ${entries.length}`}
          </button>
        )}
      </div>
      <div className="pins-list">
        {shown.map((e) => {
          const meta = ACTION_META[e.action] || { label: e.action.toUpperCase(), cls: "done" };
          return (
            <div key={e.id} className="pin-row">
              <span className={`journal-badge ${meta.cls}`}>{meta.label}</span>
              {e.symbol ? (
                <Link href={`/stock/${e.symbol}`} className="alert-sym">
                  {e.symbol}
                </Link>
              ) : (
                <span className="alert-sym mut">BOOK</span>
              )}
              <span className="pin-text">{e.detail}</span>
              <span className="mut pin-date">{e.date.slice(5)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
