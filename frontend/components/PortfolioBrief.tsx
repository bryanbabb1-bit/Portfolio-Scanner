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
  const [stale, setStale] = useState(false); // brief predates the active strategy

  // Restore the last brief; if the strategy was revised AFTER this brief was
  // written, it's stale — regenerate so the brief reflects the new plan.
  useEffect(() => {
    Promise.all([api.lastAdvisorNote("portfolio"), api.strategy().catch(() => null)])
      .then(([n, strat]) => {
        if (n) setNote((cur) => cur ?? n);
        const briefTime = n?.generated_at || "";
        const stratTime = strat?.updated_at || strat?.generated_at || "";
        if (strat?.approved && stratTime && (!n || stratTime > briefTime)) {
          setStale(true);
          run(false); // cache was cleared on the strategy save → regenerates
        }
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function run(force = false) {
    setLoading(true);
    setErr(null);
    try {
      setNote(await api.advisePortfolio(force, deep));
      setStale(false);
      // Arm any 'if price/RSI hits X' conditions from the fresh advice as
      // watchpoints, silently in the background.
      api.extractWatchpoints().catch(() => {});
    } catch (e: any) {
      setErr(e.message || "Brief failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card advisor" style={{ marginBottom: 28 }}>
      <div className="advisor-head">
        <span className="who">Portfolio Brief</span>
        {note && (
          <span className={`eng ${note.engine === "claude" ? "claude" : ""}`}>
            {note.engine === "claude" ? "Claude" : "auto"}
          </span>
        )}
        {note?.posture && (
          <span className={`posture-badge ${note.posture}`}>
            {note.posture === "watch" ? "PATIENCE WEEK" : "ACTION WEEK"}
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
            <h4>Bottom line</h4>
            <p>{note.summary}</p>
          </div>
          {note.insights?.length > 0 && (
            <div className="advisor-sec">
              <h4>Where you stand</h4>
              <BulletList items={note.insights} kind="insight" />
            </div>
          )}
          {note.actions?.length > 0 && (
            <div className="advisor-sec">
              <h4>Do this</h4>
              <BulletList
                items={note.actions}
                kind="action"
                onPin={(text) => api.addPin({ source: "brief", text })}
              />
            </div>
          )}
          {note.risks?.length > 0 && (
            <div className="advisor-sec">
              <h4>Watch out</h4>
              <BulletList items={note.risks} kind="risk" />
            </div>
          )}
          {(note.scout?.length ?? 0) > 0 && (
            <div className="advisor-sec">
              <h4>Ideas to buy</h4>
              <p className="mut" style={{ fontSize: 12.5, lineHeight: 1.5 }}>
                Your conviction &amp; speculative ideas are now in the <b>Do this</b> board above — pin one to act on it.
              </p>
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
