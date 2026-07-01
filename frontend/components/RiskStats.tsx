"use client";
import { RiskMetrics } from "../lib/api";
import { num, pct, signClass } from "./format";

export function RiskStats({ risk }: { risk: RiskMetrics }) {
  const stats: { label: string; value: string; cls?: string; sub?: string }[] = [
    {
      label: "Beta vs SPY",
      value: num(risk.beta, 2),
      sub: risk.beta == null ? undefined : risk.beta > 1.3 ? "aggressive" : risk.beta > 0.8 ? "market-like" : "defensive",
    },
    { label: "Volatility (ann.)", value: pct(risk.volatility_pct, 1).replace("+", "") },
    {
      label: "Sharpe",
      value: num(risk.sharpe, 2),
      cls: risk.sharpe == null ? "" : risk.sharpe >= 1 ? "pos" : risk.sharpe < 0 ? "neg" : "",
    },
    { label: "Max Drawdown (1y)", value: pct(risk.max_drawdown_pct, 1), cls: "neg" },
    {
      label: "Best Day",
      value: pct(risk.best_day_pct),
      cls: "pos",
      sub: risk.best_day_date,
    },
    {
      label: "Worst Day",
      value: pct(risk.worst_day_pct),
      cls: "neg",
      sub: risk.worst_day_date,
    },
    {
      label: "Largest Position",
      value: risk.top_symbol ? `${risk.top_symbol} · ${num(risk.top_weight_pct, 1)}%` : "—",
      cls: (risk.top_weight_pct ?? 0) > 25 ? "neg" : "",
      sub: risk.top5_weight_pct != null ? `top 5 = ${num(risk.top5_weight_pct, 0)}%` : undefined,
    },
  ];

  return (
    <div style={{ marginBottom: 28 }}>
      <div className="section-title">Risk Profile</div>
      <div className="grid grid-stats">
        {stats.map((s) => (
          <div key={s.label} className="card stat">
            <span className="label">{s.label}</span>
            <span className={`value ${s.cls || ""}`} style={{ fontSize: 19 }}>
              {s.value}
            </span>
            {s.sub && <span className="sub mut">{s.sub}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}
