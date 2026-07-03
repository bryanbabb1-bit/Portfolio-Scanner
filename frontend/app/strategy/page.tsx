"use client";
import { useEffect, useState } from "react";
import { api, PortfolioSummary, StrategyDoc } from "../../lib/api";
import { AdvisorChat } from "../../components/AdvisorChat";
import { BulletList } from "../../components/BulletList";
import { money, num } from "../../components/format";

export default function Strategy() {
  const [doc, setDoc] = useState<StrategyDoc | null>(null);
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [deep, setDeep] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  // goals form
  const [targetValue, setTargetValue] = useState<string>("");
  const [horizon, setHorizon] = useState("5 years");
  const [monthly, setMonthly] = useState<string>("");
  const [risk, setRisk] = useState("balanced");
  const [notes, setNotes] = useState("");

  useEffect(() => {
    api.strategy().then((d) => {
      if (d) {
        setDoc(d);
        const g = d.goals || {};
        if (g.target_value) setTargetValue(String(g.target_value));
        if (g.horizon) setHorizon(g.horizon);
        if (g.monthly_contribution != null) setMonthly(String(g.monthly_contribution));
        if (g.risk_appetite) setRisk(g.risk_appetite);
        if (g.notes) setNotes(g.notes);
      }
    });
    api.portfolio().then((d) => setSummary(d.summary)).catch(() => {});
  }, []);

  async function generate() {
    setLoading(true);
    setErr(null);
    setMsg(null);
    try {
      const d = await api.generateStrategy({
        target_value: targetValue ? parseFloat(targetValue) : undefined,
        horizon,
        monthly_contribution: monthly ? parseFloat(monthly) : undefined,
        risk_appetite: risk,
        notes: notes || undefined,
        deep,
      });
      setDoc(d);
    } catch (e: any) {
      setErr(e.message || "Generation failed");
    } finally {
      setLoading(false);
    }
  }

  async function approve(approved: boolean) {
    if (!doc) return;
    setSaving(true);
    try {
      const d = await api.saveStrategy({ ...doc, approved });
      setDoc(d);
      setMsg(approved
        ? "Strategy activated — every brief now aligns to this plan."
        : "Strategy deactivated — briefs no longer reference it.");
    } catch (e: any) {
      setErr(e.message || "Save failed");
    } finally {
      setSaving(false);
    }
  }

  const totalValue = summary?.total_market_value ?? 0;
  const actualPct = (theme: string) =>
    totalValue > 0 ? ((summary?.by_theme?.[theme] ?? 0) / totalValue) * 100 : 0;

  return (
    <>
      <div className="page-head">
        <h1>Strategy</h1>
        <p>
          Set the goals, let the advisor draft a two-horizon plan, iterate in the
          chat, then approve it — every daily brief will align to the active plan.
        </p>
      </div>

      {/* --------- goals --------- */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="section-title">Goals</div>
        <div className="strat-form">
          <label>
            <span>Target value ($)</span>
            <input type="number" min={0} placeholder="e.g. 50000" value={targetValue}
              onChange={(e) => setTargetValue(e.target.value)} />
          </label>
          <label>
            <span>Horizon</span>
            <select value={horizon} onChange={(e) => setHorizon(e.target.value)}>
              {["1 year", "2 years", "3 years", "5 years", "10 years"].map((h) => (
                <option key={h} value={h}>{h}</option>
              ))}
            </select>
          </label>
          <label>
            <span>New capital ($/month)</span>
            <input type="number" min={0} placeholder="e.g. 500" value={monthly}
              onChange={(e) => setMonthly(e.target.value)} />
          </label>
          <label>
            <span>Risk appetite</span>
            <select value={risk} onChange={(e) => setRisk(e.target.value)}>
              <option value="conservative">Conservative</option>
              <option value="balanced">Balanced</option>
              <option value="aggressive">Aggressive</option>
            </select>
          </label>
        </div>
        <label style={{ display: "block", marginTop: 12, fontSize: 12, color: "var(--muted)" }}>
          <span>Anything else the advisor should know</span>
          <input placeholder='e.g. "I want to keep a miner position long-term" or "no options"'
            value={notes} onChange={(e) => setNotes(e.target.value)} style={{ marginTop: 5 }} />
        </label>
        <div style={{ display: "flex", gap: 12, alignItems: "center", marginTop: 14 }}>
          <button className="btn" onClick={generate} disabled={loading}>
            {loading ? "Drafting strategy…" : doc ? "Revise strategy" : "Draft my strategy"}
          </button>
          <label className="deep-toggle" title="Research the market first (slower)">
            <input type="checkbox" checked={deep} onChange={(e) => setDeep(e.target.checked)} disabled={loading} />
            Deep research
          </label>
          {loading && (
            <span className="mut" style={{ fontSize: 12 }}>
              {deep ? "researching + planning, 2-5 min" : "best model, ~1-2 min"}
            </span>
          )}
        </div>
      </div>

      {err && <div className="err" style={{ marginBottom: 16 }}>{err}</div>}
      {msg && <div className="ok-banner">{msg}</div>}

      {doc && (
        <>
          {/* --------- the plan --------- */}
          <div className={`card advisor ${doc.approved ? "strat-active" : ""}`} style={{ marginBottom: 20 }}>
            <div className="advisor-head">
              <span className="who">🎯 The Plan</span>
              <span className={`eng ${doc.approved ? "claude" : ""}`}>
                {doc.approved ? "ACTIVE" : "DRAFT"}
              </span>
              <div style={{ marginLeft: "auto" }}>
                <button className="btn" onClick={() => approve(!doc.approved)} disabled={saving}>
                  {saving ? "Saving…" : doc.approved ? "Deactivate" : "Approve & activate"}
                </button>
              </div>
            </div>
            <p style={{ fontSize: 15, fontWeight: 600 }}>{doc.thesis}</p>

            <div className="strat-grid">
              <div className="advisor-sec">
                <h4>Short-Term Playbook · 4-12 weeks</h4>
                <BulletList items={doc.short_term} kind="action"
                  onPin={(text) => api.addPin({ source: "brief", text })} />
              </div>
              <div className="advisor-sec">
                <h4>Long-Term Strategy · 1+ years</h4>
                <BulletList items={doc.long_term} kind="insight" />
              </div>
              <div className="advisor-sec">
                <h4>Guardrails</h4>
                <BulletList items={doc.guardrails} kind="risk" />
              </div>
              <div className="advisor-sec">
                <h4>Milestones</h4>
                <BulletList items={doc.milestones} kind="insight" />
              </div>
            </div>
            <p className="mut" style={{ fontSize: 11, marginTop: 12 }}>
              Drafted {doc.generated_at} · Not personalized investment advice.
            </p>
          </div>

          {/* --------- allocation: target vs actual --------- */}
          {doc.allocation_targets && Object.keys(doc.allocation_targets).length > 0 && (
            <div className="card" style={{ marginBottom: 20 }}>
              <div className="section-title">Allocation · target vs today</div>
              <div className="alloc-bars">
                {Object.entries(doc.allocation_targets)
                  .sort((a, b) => b[1] - a[1])
                  .map(([theme, target]) => {
                    const actual = actualPct(theme);
                    const drift = actual - target;
                    return (
                      <div key={theme} className="alloc-row strat-alloc">
                        <span className="alloc-name">{theme}</span>
                        <div className="alloc-track" style={{ position: "relative" }}>
                          <div className="alloc-fill" style={{ width: `${Math.min(Math.max(actual, 1), 100)}%` }} />
                          <div className="strat-target-tick" style={{ left: `${Math.min(target, 100)}%` }} />
                        </div>
                        <span className="alloc-val">
                          {num(actual, 1)}% <span className="mut">/ {num(target, 0)}% target</span>{" "}
                          <span className={Math.abs(drift) <= 5 ? "pos" : "neg"}>
                            {drift >= 0 ? "+" : ""}{num(drift, 1)}
                          </span>
                        </span>
                      </div>
                    );
                  })}
              </div>
              {summary && (
                <p className="mut" style={{ fontSize: 12, marginTop: 10 }}>
                  Book today: {money(totalValue, 0)} · white tick = target · green drift = within 5 points.
                </p>
              )}
            </div>
          )}

          {/* --------- iterate --------- */}
          <div className="card advisor" style={{ marginBottom: 20 }}>
            <div className="advisor-head">
              <span className="who">Talk it through</span>
              <span className="mut" style={{ fontSize: 12 }}>
                iterate on the plan, then hit Revise strategy to redraft
              </span>
            </div>
            <AdvisorChat kind="strategy" deep={deep} />
          </div>
        </>
      )}
    </>
  );
}
