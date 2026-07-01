"use client";
import Link from "next/link";
import { useState } from "react";
import { PortfolioAlert } from "../lib/api";

const SEV_META: Record<string, { icon: string; title: string }> = {
  critical: { icon: "▲", title: "Critical" },
  warning: { icon: "!", title: "Warning" },
  opportunity: { icon: "◆", title: "Opportunity" },
};

const COLLAPSED_COUNT = 6;

export function AlertsPanel({ alerts }: { alerts: PortfolioAlert[] }) {
  const [expanded, setExpanded] = useState(false);
  if (!alerts.length) return null;

  const shown = expanded ? alerts : alerts.slice(0, COLLAPSED_COUNT);
  const criticals = alerts.filter((a) => a.severity === "critical").length;
  const warnings = alerts.filter((a) => a.severity === "warning").length;

  return (
    <div className="card alerts-panel" style={{ marginBottom: 28 }}>
      <div className="chart-head" style={{ marginBottom: 10 }}>
        <div className="section-title" style={{ margin: 0 }}>
          Needs Your Attention{" "}
          <span className="mut" style={{ textTransform: "none", letterSpacing: 0 }}>
            · {criticals} critical · {warnings} warnings ·{" "}
            {alerts.length - criticals - warnings} opportunities
          </span>
        </div>
        {alerts.length > COLLAPSED_COUNT && (
          <button className="btn ghost" onClick={() => setExpanded(!expanded)}>
            {expanded ? "Show less" : `Show all ${alerts.length}`}
          </button>
        )}
      </div>
      <div className="alerts-list">
        {shown.map((a, idx) => (
          <Link
            key={`${a.symbol}-${a.label}-${idx}`}
            href={`/stock/${a.symbol}`}
            className={`alert-row ${a.severity}`}
          >
            <span className={`alert-icon ${a.severity}`} title={SEV_META[a.severity]?.title}>
              {SEV_META[a.severity]?.icon || "•"}
            </span>
            <span className="alert-sym">{a.symbol}</span>
            <span className="alert-label">{a.label}</span>
            <span className="alert-detail mut">{a.detail}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}
