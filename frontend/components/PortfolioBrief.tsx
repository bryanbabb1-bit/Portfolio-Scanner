"use client";
import { useState } from "react";
import { AdvisorNote, api } from "../lib/api";

// Whole-book AI brief. On-demand (a Claude call takes ~15-45s) and cached
// server-side for an hour, so "Refresh" is instant until the cache expires.
export function PortfolioBrief() {
  const [note, setNote] = useState<AdvisorNote | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function run(force = false) {
    setLoading(true);
    setErr(null);
    try {
      setNote(await api.advisePortfolio(force));
    } catch (e: any) {
      setErr(e.message || "Brief failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card advisor" style={{ marginBottom: 28 }}>
      <div className="advisor-head">
        <span className="who">🎯 Portfolio Brief</span>
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
            {loading ? "Analyzing…" : note ? "Refresh" : "Generate brief"}
          </button>
        </div>
      </div>

      {err && <div className="err">{err}</div>}

      {!note && !loading && !err && (
        <p className="mut" style={{ fontSize: 14 }}>
          One senior-advisor read across the whole book: posture, concentration,
          and the 2-3 actions that matter this week.
        </p>
      )}

      {loading && !note && (
        <p className="loading">Reviewing the whole portfolio… (headless Claude, ~15-45s)</p>
      )}

      {note && (
        <>
          <div className="advisor-sec">
            <h4>Overall Take</h4>
            <p>{note.summary}</p>
          </div>
          {note.technical_read && (
            <div className="advisor-sec">
              <h4>Portfolio Health</h4>
              <p>{note.technical_read}</p>
            </div>
          )}
          {note.recommendation && (
            <div className="advisor-sec">
              <h4>Actions This Week</h4>
              <p>{note.recommendation}</p>
            </div>
          )}
          {note.risks && (
            <div className="advisor-sec">
              <h4>Biggest Risks</h4>
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
