"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, PortfolioAlert } from "../lib/api";
import { RecoSlap } from "./RecoSlap";

const OPEN_KEY = "pscan-alerts-open";

const SEV_META: Record<string, { icon: string; title: string }> = {
  critical: { icon: "▲", title: "Critical" },
  warning: { icon: "!", title: "Warning" },
  opportunity: { icon: "◆", title: "Opportunity" },
};

const COLLAPSED_COUNT = 6;

export function AlertsPanel({ alerts: initial }: { alerts: PortfolioAlert[] }) {
  const [alerts, setAlerts] = useState(initial);
  const [expanded, setExpanded] = useState(false);
  const [open, setOpen] = useState(true);
  const [reco, setReco] = useState<PortfolioAlert | null>(null);

  useEffect(() => setAlerts(initial), [initial]);
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

  function dismiss(a: PortfolioAlert) {
    setAlerts((cur) => cur.filter((x) => x.id !== a.id));
    api.dismissAlert(a.id).catch(() => {});
  }
  function dismissAll() {
    setAlerts([]);
    api.dismissAlert().catch(() => {});
  }

  const shown = expanded ? alerts : alerts.slice(0, COLLAPSED_COUNT);
  const criticals = alerts.filter((a) => a.severity === "critical").length;
  const warnings = alerts.filter((a) => a.severity === "warning").length;

  return (
    <div className="card alerts-panel" id="needs-attention" style={{ marginBottom: 28 }}>
      <div className="chart-head" style={{ marginBottom: open ? 10 : 0 }}>
        <button className="section-title collapse-head" style={{ margin: 0 }} onClick={toggle}>
          <span className="chev">{open ? "▾" : "▸"}</span> Needs Your Attention{" "}
          <span className="mut" style={{ textTransform: "none", letterSpacing: 0 }}>
            · {criticals} critical · {warnings} warnings ·{" "}
            {alerts.length - criticals - warnings} opportunities
          </span>
        </button>
        {open && (
          <div style={{ display: "flex", gap: 8 }}>
            {alerts.length > COLLAPSED_COUNT && (
              <button className="btn ghost" onClick={() => setExpanded(!expanded)}>
                {expanded ? "Show less" : `Show all ${alerts.length}`}
              </button>
            )}
            <button className="btn ghost" onClick={dismissAll}>Clear all</button>
          </div>
        )}
      </div>
      {open && (
        <div className="alerts-list">
          {shown.map((a, idx) => (
            <div
              key={a.id || `${a.symbol}-${a.label}-${idx}`}
              className={`alert-row clickable ${a.severity}`}
              onClick={() => setReco(a)}
              title="What should I do? — ask the advisor"
            >
              <span className={`alert-icon ${a.severity}`} title={SEV_META[a.severity]?.title}>
                {SEV_META[a.severity]?.icon || "•"}
              </span>
              <span className="alert-sym">{a.symbol}</span>
              <span className="alert-label">{a.label}</span>
              <span className="alert-detail mut">{a.detail}</span>
              <button
                className="icon-btn jr-btn alert-x"
                title="Dismiss (returns tomorrow if still true)"
                onClick={(e) => { e.stopPropagation(); dismiss(a); }}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
      {reco && (
        <RecoSlap
          symbol={reco.symbol}
          event={`${reco.label} — ${reco.detail}`}
          kind="alert"
          onClose={() => setReco(null)}
        />
      )}
    </div>
  );
}
