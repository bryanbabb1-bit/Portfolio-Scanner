"use client";
import { useEffect, useState } from "react";
import { AdvisorNote, api } from "../lib/api";
import { AdvisorChat } from "./AdvisorChat";
import { BulletList } from "./BulletList";

// Whole-book AI brief. On-demand (a Claude call takes ~15-45s) and cached
// server-side for an hour, so "Refresh" is instant until the cache expires.
export function PortfolioBrief() {
  const [note, setNote] = useState<AdvisorNote | null>(null);
  const [loading, setLoading] = useState(false);
  const [deep, setDeep] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Restore the last brief after navigation/refresh — no Claude call.
  useEffect(() => {
    api.lastAdvisorNote("portfolio").then((n) => {
      if (n) setNote((cur) => cur ?? n);
    });
  }, []);

  async function run(force = false) {
    setLoading(true);
    setErr(null);
    try {
      setNote(await api.advisePortfolio(force, deep));
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
            {loading ? "Analyzing…" : note ? "Refresh" : "Generate brief"}
          </button>
        </div>
      </div>

      {err && <div className="err">{err}</div>}

      {!note && !loading && !err && (
        <p className="mut" style={{ fontSize: 14 }}>
          One senior-advisor read across the whole book: posture, concentration,
          and the 2-3 actions that matter this week — or just talk to the
          advisor below, no brief required.
        </p>
      )}

      {loading && !note && (
        <p className="loading">
          {deep
            ? "Researching live news + sentiment across the book, then analyzing… (2-4 min)"
            : "Reviewing the whole portfolio… (headless Claude, ~15-45s)"}
        </p>
      )}

      {note && (
        <>
          <div className="advisor-sec">
            <h4>Overall Take</h4>
            <p>{note.summary}</p>
          </div>
          {note.insights?.length > 0 && (
            <div className="advisor-sec">
              <h4>Portfolio Health</h4>
              <BulletList items={note.insights} kind="insight" />
            </div>
          )}
          {note.actions?.length > 0 && (
            <div className="advisor-sec">
              <h4>Actions This Week</h4>
              <BulletList
                items={note.actions}
                kind="action"
                onPin={(text) => api.addPin({ source: "brief", text })}
              />
            </div>
          )}
          {note.risks?.length > 0 && (
            <div className="advisor-sec">
              <h4>Biggest Risks</h4>
              <BulletList items={note.risks} kind="risk" />
            </div>
          )}
          <p className="mut" style={{ fontSize: 11, marginTop: 12 }}>
            {note.persona} · {note.generated_at} · Not personalized investment advice.
          </p>
        </>
      )}

      {/* Always-open line to the advisor — no brief required. */}
      <AdvisorChat kind="portfolio" deep={deep} />
    </div>
  );
}
