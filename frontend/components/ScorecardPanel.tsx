"use client";
import { useEffect, useState } from "react";
import { api, Scorecard } from "../lib/api";
import { num, pct } from "./format";

const OPEN_KEY = "pscan-scorecard-open";

// The receipts: every slap graded against what the price did afterwards.
// Sign-adjusted — a SELL signal wins when the price falls.
export function ScorecardPanel() {
  const [card, setCard] = useState<Scorecard | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    try {
      const v = localStorage.getItem(OPEN_KEY);
      if (v != null) setOpen(v === "1");
    } catch {}
    api.scorecard().then(setCard).catch(() => {});
  }, []);

  const toggle = () => {
    setOpen((o) => {
      try {
        localStorage.setItem(OPEN_KEY, o ? "0" : "1");
      } catch {}
      return !o;
    });
  };

  if (!card || !card.count) return null;

  return (
    <div className="card scorecard-panel" style={{ marginBottom: 24 }}>
      <div className="chart-head" style={{ marginBottom: open ? 8 : 0 }}>
        <button className="section-title collapse-head" style={{ margin: 0 }} onClick={toggle}>
          <span className="chev">{open ? "▾" : "▸"}</span> Signal Scorecard{" "}
          <span className="mut" style={{ textTransform: "none", letterSpacing: 0 }}>
            · {card.count} calls graded · {card.overall_win_rate ?? "–"}% right ·{" "}
            <span className={(card.overall_avg_pct ?? 0) >= 0 ? "pos" : "neg"}>
              {pct(card.overall_avg_pct)} avg edge
            </span>
          </span>
        </button>
      </div>

      {open && (
        <>
          <div className="sc-rules">
            <div className="sc-row sc-head-row">
              <span>Rule</span><span>Calls</span><span>Win rate</span><span>Avg edge</span><span>Best / worst</span>
            </div>
            {card.rules.map((r) => (
              <div key={r.rule} className="sc-row">
                <span className="sc-rule">{r.rule}</span>
                <span>{r.signals}</span>
                <span className={r.win_rate >= 50 ? "pos" : "neg"}>{num(r.win_rate, 0)}%</span>
                <span className={r.avg_effective_pct >= 0 ? "pos" : "neg"}>
                  {pct(r.avg_effective_pct)}
                </span>
                <span className="mut">
                  {pct(r.best_pct)} / {pct(r.worst_pct)}
                </span>
              </div>
            ))}
          </div>
          <p className="mut" style={{ fontSize: 11, marginTop: 10 }}>
            Edge is sign-adjusted: a SELL call scores positive when the price falls
            after it fired. Young calls (&lt;5 days) haven&apos;t proven anything yet.
          </p>
        </>
      )}
    </div>
  );
}
