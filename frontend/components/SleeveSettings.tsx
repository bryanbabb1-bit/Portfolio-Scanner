"use client";
import { useEffect, useState } from "react";
import { api, SleeveConfig } from "../lib/api";

/* The trading sleeve's rulebook. Separate from the core book's settings on
 * purpose: these numbers are aggressive by design and should never be read
 * as guidance for the eleven compounders. Saves independently.
 */
export function SleeveSettings() {
  const [cfg, setCfg] = useState<SleeveConfig | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.sleeveConfig().then(setCfg).catch((e) => setErr(e.message));
  }, []);

  // Render the shell immediately so the card enters with its siblings
  // (the page's entry animation runs per child; a late mount looks blank).
  if (!cfg) {
    return (
      <div className="card" style={{ marginBottom: 20 }} id="sleeve">
        <div className="section-title" style={{ margin: 0 }}>Trading sleeve</div>
        <p className="mut" style={{ fontSize: 13, marginTop: 6 }}>{err ? `Could not load sleeve rules (${err}).` : "Loading sleeve rules…"}</p>
      </div>
    );
  }

  const set = <K extends keyof SleeveConfig>(k: K, v: SleeveConfig[K]) => setCfg({ ...cfg, [k]: v });
  const num = (v: string) => (v === "" ? NaN : parseFloat(v));
  const show = (v: number | null | undefined) => (v == null || Number.isNaN(v) ? "" : String(v));

  const save = async () => {
    setSaving(true); setMsg(null); setErr(null);
    try {
      const saved = await api.saveSleeveConfig({
        ...cfg,
        capital_usd: cfg.capital_usd && !Number.isNaN(cfg.capital_usd) ? cfg.capital_usd : null,
      });
      setCfg(saved);
      setMsg("Saved. New tickets size against these rules from the next scan.");
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  };

  const pctField = (k: "ignition_stop_pct" | "ignition_max_pct" | "trail_pct", label: string, hint: string) => (
    <label>
      <span>{label}</span>
      <input type="number" min={3} max={60} step={1}
             value={Number.isNaN(cfg[k]) ? "" : Math.round(cfg[k] * 100)}
             title={hint}
             onChange={(e) => set(k, num(e.target.value) / 100)} />
    </label>
  );

  return (
    <div className="card" style={{ marginBottom: 20 }} id="sleeve">
      <div className="editor-head">
        <div className="section-title" style={{ margin: 0 }}>Trading sleeve</div>
        <label className="cfg-toggle" style={{ margin: 0 }}>
          <input type="checkbox" checked={cfg.enabled} onChange={(e) => set("enabled", e.target.checked)} />
          <span>{cfg.enabled ? "On — issuing tickets" : "Off"}</span>
        </label>
      </div>
      <p className="mut" style={{ fontSize: 13, marginTop: 6 }}>
        A second book with its own capital and its own rules. Every idea becomes a ticket with an
        entry, a stop, a target and a size; the desk manages the exit and pushes when it changes.
        None of this applies to the core holdings.
      </p>

      <div className="cfg-grid">
        <label>
          <span>Capital — % of core book</span>
          <input type="number" min={0} max={100} step={1} value={show(cfg.capital_pct)}
                 onChange={(e) => set("capital_pct", num(e.target.value))} />
        </label>
        <label>
          <span>…or a fixed dollar figure</span>
          <input type="number" min={0} step="any" value={show(cfg.capital_usd)} placeholder="blank = use %"
                 onChange={(e) => set("capital_usd", e.target.value === "" ? null : num(e.target.value))} />
        </label>
        <label>
          <span>Risk per ticket — % of sleeve</span>
          <input type="number" min={0.5} max={25} step={0.5} value={show(cfg.risk_pct)}
                 title="The sizing study found 5-8% beat the index out of sample; the core runs 1%."
                 onChange={(e) => set("risk_pct", num(e.target.value))} />
        </label>
        <label>
          <span>Concurrent slots</span>
          <input type="number" min={1} max={20} step={1} value={show(cfg.max_slots)}
                 onChange={(e) => set("max_slots", num(e.target.value))} />
        </label>
        <label>
          <span>Tickets per day (max)</span>
          <input type="number" min={1} max={20} step={1} value={show(cfg.max_tickets_per_day)}
                 onChange={(e) => set("max_tickets_per_day", num(e.target.value))} />
        </label>
        <label>
          <span>Target (R multiples)</span>
          <input type="number" min={1} max={10} step={0.5} value={show(cfg.target_r)}
                 onChange={(e) => set("target_r", num(e.target.value))} />
        </label>
        {pctField("ignition_stop_pct", "Runner stop — % under entry", "Where a runner ticket's hard stop sits.")}
        {pctField("ignition_max_pct", "Runner cap — % of sleeve", "A runner is never bigger than this slice, whatever the risk math says.")}
        {pctField("trail_pct", "Trail — % off the high after +1R", "Once a trade is +1R the stop goes to breakeven and trails this far under the high-water mark.")}
        <label>
          <span>Runner time stop (sessions)</span>
          <input type="number" min={1} max={20} step={1} value={show(cfg.ignition_time_stop_sessions)}
                 onChange={(e) => set("ignition_time_stop_sessions", num(e.target.value))} />
        </label>
      </div>

      <div className="editor-foot" style={{ marginTop: 12, display: "flex", gap: 12, alignItems: "center" }}>
        <button className="btn" onClick={save} disabled={saving}>{saving ? "Saving…" : "Save sleeve rules"}</button>
        {msg && <span className="ok" style={{ fontSize: 13 }}>{msg}</span>}
        {err && <span className="err" style={{ fontSize: 13 }}>{err}</span>}
      </div>
    </div>
  );
}
