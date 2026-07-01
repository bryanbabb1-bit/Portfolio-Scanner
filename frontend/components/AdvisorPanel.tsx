"use client";
import { useState } from "react";
import { AdvisorNote, api } from "../lib/api";

export function AdvisorPanel({
  symbol,
  mode = "stock",
}: {
  symbol: string;
  mode?: "stock" | "breakout";
}) {
  const [note, setNote] = useState<AdvisorNote | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function run(force = false) {
    setLoading(true);
    setErr(null);
    try {
      const n =
        mode === "breakout"
          ? await api.adviseBreakout(symbol, force)
          : await api.adviseStock(symbol, force);
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
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
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
        <p className="loading">Consulting the advisor… (headless Claude, ~10-30s)</p>
      )}

      {note && (
        <>
          <div className="advisor-sec">
            <h4>Summary</h4>
            <p>{note.summary}</p>
          </div>
          {note.technical_read && (
            <div className="advisor-sec">
              <h4>Technical Read</h4>
              <p>{note.technical_read}</p>
            </div>
          )}
          {note.recommendation && (
            <div className="advisor-sec">
              <h4>Recommendation</h4>
              <p>{note.recommendation}</p>
            </div>
          )}
          {note.risks && (
            <div className="advisor-sec">
              <h4>Risks / Invalidation</h4>
              <p>{note.risks}</p>
            </div>
          )}
          <p className="mut" style={{ fontSize: 11, marginTop: 12 }}>
            {note.persona} · {note.generated_at} · Not personalized investment advice.
          </p>
        </>
      )}
    </div>
  );
}
