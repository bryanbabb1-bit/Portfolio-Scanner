"use client";
import { RiskMetrics } from "../lib/api";
import { num, pct } from "./format";

// Compact one-line risk strip — the numbers that matter, no card sprawl.
export function RiskStats({ risk }: { risk: RiskMetrics }) {
  const chips: { label: string; value: string; cls?: string }[] = [
    {
      label: "Beta",
      value: num(risk.beta, 2),
      cls: (risk.beta ?? 0) > 1.5 ? "neg" : "",
    },
    { label: "Vol", value: risk.volatility_pct != null ? `${num(risk.volatility_pct, 0)}%` : "—" },
    {
      label: "Sharpe",
      value: num(risk.sharpe, 2),
      cls: risk.sharpe == null ? "" : risk.sharpe >= 1 ? "pos" : risk.sharpe < 0 ? "neg" : "",
    },
    { label: "Max DD", value: pct(risk.max_drawdown_pct, 1), cls: "neg" },
    { label: "Best day", value: pct(risk.best_day_pct), cls: "pos" },
    { label: "Worst day", value: pct(risk.worst_day_pct), cls: "neg" },
    {
      label: "Top position",
      value: risk.top_symbol ? `${risk.top_symbol} ${num(risk.top_weight_pct, 0)}%` : "—",
      cls: (risk.top_weight_pct ?? 0) > 25 ? "neg" : "",
    },
    { label: "Top 5", value: risk.top5_weight_pct != null ? `${num(risk.top5_weight_pct, 0)}%` : "—" },
  ];

  return (
    <div className="card risk-strip" style={{ marginBottom: 28 }}>
      <span className="section-title" style={{ margin: 0, whiteSpace: "nowrap" }}>Risk</span>
      {chips.map((c) => (
        <span key={c.label} className="risk-chip">
          <span className="rc-label">{c.label}</span>
          <span className={`rc-value ${c.cls || ""}`}>{c.value}</span>
        </span>
      ))}
    </div>
  );
}
