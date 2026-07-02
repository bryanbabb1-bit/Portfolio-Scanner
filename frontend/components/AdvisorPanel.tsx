"use client";
import { useEffect, useState } from "react";
import { AdvisorNote, api } from "../lib/api";
import { AdvisorChat } from "./AdvisorChat";
import { BulletList } from "./BulletList";

export function AdvisorPanel({
  symbol,
  mode = "stock",
}: {
  symbol: string;
  mode?: "stock" | "breakout";
}) {
  const [note, setNote] = useState<AdvisorNote | null>(null);
  const [loading, setLoading] = useState(false);
  const [deep, setDeep] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Restore this symbol's last note after navigation — no Claude call.
  useEffect(() => {
    api.lastAdvisorNote(mode, symbol).then((n) => {
      if (n) setNote((cur) => cur ?? n);
    });
  }, [symbol, mode]);

  async function run(force = false) {
    setLoading(true);
    setErr(null);
    try {
      const n =
        mode === "breakout"
          ? await api.adviseBreakout(symbol, force, deep)
          : await api.adviseStock(symbol, force, deep);
      setNote(n);
    } catch (e: any) {
      setErr(e.message || "Advisor failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card advisor">
      <div className="advisor-head">
        <span className="who">🎯 Senior Advisor</span>
        {note && (
          <span className={`eng ${note.engine === "claude" ? "claude" : ""}`}>
            {note.engine === "claude" ? "Claude" : "auto"}
          </span>
        )}
        <div style={{ marginLeft: "auto", display: "flex", gap: 10, alignItems: "center" }}>
          <label className="deep-toggle" title="Let the advisor search the web for live news, analyst moves and sentiment (slower)">
            <input type="checkbox" checked={deep} onChange={(e) => setDeep(e.target.checked)} disabled={loading} />
            Deep research
          </label>
          {note && (
            <button className="btn ghost" onClick={() => run(true)} disabled={loading}>
              ↻
            </button>
          )}
          <button className="btn" onClick={() => run(false)} disabled={loading}>
            {loading ? "Analyzing…" : note ? "Refresh" : `Analyze ${mode === "breakout" ? "breakout" : symbol}`}
          </button>
        </div>
      </div>

      {err && <div className="err">{err}</div>}

      {!note && !loading && !err && (
        <p className="mut" style={{ fontSize: 14 }}>
          {mode === "breakout"
            ? "Get the AI bull case, entry zone, confirmation level and stop."
            : "Get a senior-advisor technical read and recommendation for this position."}
        </p>
      )}

      {loading && !note && (
        <p className="loading">
          {deep
            ? "Researching live news + sentiment, then analyzing… (1-3 min)"
            : "Consulting the advisor… (headless Claude, ~10-30s)"}
        </p>
      )}

      {note && (
        <>
          <div className="advisor-sec">
            <h4>The Take</h4>
            <p>{note.summary}</p>
          </div>
          {note.insights?.length > 0 && (
            <div className="advisor-sec">
              <h4>Technical Read</h4>
              <BulletList items={note.insights} kind="insight" />
            </div>
          )}
          {note.actions?.length > 0 && (
            <div className="advisor-sec">
              <h4>Actions</h4>
              <BulletList
                items={note.actions}
                kind="action"
                onPin={(text) =>
                  api.addPin({ symbol, source: mode === "breakout" ? "breakout" : "advisor", text })
                }
              />
            </div>
          )}
          {note.risks?.length > 0 && (
            <div className="advisor-sec">
              <h4>Risks / Invalidation</h4>
              <BulletList items={note.risks} kind="risk" />
            </div>
          )}
          <p className="mut" style={{ fontSize: 11, marginTop: 12 }}>
            {note.persona} · {note.generated_at} · Not personalized investment advice.
          </p>
        </>
      )}

      {/* Always-open line to the advisor — no note required. */}
      <AdvisorChat kind={mode} symbol={symbol} deep={deep} />
    </div>
  );
}
