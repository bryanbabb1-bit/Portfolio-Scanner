"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { PortfolioAlert } from "../lib/api";

const OPEN_KEY = "pscan-alerts-open";

const SEV_META: Record<string, { icon: string; title: string }> = {
  critical: { icon: "▲", title: "Critical" },
  warning: { icon: "!", title: "Warning" },
  opportunity: { icon: "◆", title: "Opportunity" },
};

const COLLAPSED_COUNT = 6;

export function AlertsPanel({ alerts }: { alerts: PortfolioAlert[] }) {
  const [expanded, setExpanded] = useState(false);
  const [open, setOpen] = useState(true);
  useEffect(() => {
    try {
      const v = localStorage.getItem(OPEN_KEY);
      if (v != null) setOpen(v === "1");
    } catch {}
  }, []);
  if (!alerts.length) return null;

  const toggle = () => {
    setOpen((o) => {
      try {
        localStorage.setItem(OPEN_KEY, o ? "0" : "1");
      } catch {}
      return !o;
    });
  };

  const shown = expanded ? alerts : alerts.slice(0, COLLAPSED_COUNT);
  const criticals = alerts.filter((a) => a.severity === "critical").length;
  const warnings = alerts.filter((a) => a.severity === "warning").length;

  return (
    <div className="card alerts-panel" style={{ marginBottom: 28 }}>
      <div className="chart-head" style={{ marginBottom: open ? 10 : 0 }}>
        <button className="section-title collapse-head" style={{ margin: 0 }} onClick={toggle}>
          <span className="chev">{open ? "▾" : "▸"}</span> Needs Your Attention{" "}
          <span className="mut" style={{ textTransform: "none", letterSpacing: 0 }}>
            · {criticals} critical · {warnings} warnings ·{" "}
            {alerts.length - criticals - warnings} opportunities
          </span>
        </button>
        {open && alerts.length > COLLAPSED_COUNT && (
          <button className="btn ghost" onClick={() => setExpanded(!expanded)}>
            {expanded ? "Show less" : `Show all ${alerts.length}`}
          </button>
        )}
      </div>
      {open && (
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
      )}
    </div>
  );
}
