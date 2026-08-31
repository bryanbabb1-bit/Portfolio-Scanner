"use client";
import { useEffect, useState } from "react";
import { AdvisorNote, api } from "../lib/api";
import { AdvisorChat } from "./AdvisorChat";
import { BulletList } from "./BulletList";

// Whole-book AI brief. On-demand (a Claude call takes ~15-45s) and cached
// server-side for an hour, so "Refresh" is instant until the cache expires.
export function PortfolioBrief() {
  const [note, setNote] = useState<AdvisorNote | null>(null);
  // The brief runs to thirty-five bullets across seven sections. The two that
  // are actionable were the sixth block down, so the read is now folded and
  // the plan is not.
  const [full, setFull] = useState(false);
  const [loading, setLoading] = useState(false);
  const [deep, setDeep] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [stale, setStale] = useState(false);

  // Restore the last brief. There is no strategy document to fall out of sync
  // with any more — the brief is the only thing that issues orders, so it is
  // never "stale relative to the plan"; it IS the plan.
  useEffect(() => {
    api
      .lastAdvisorNote("portfolio")
      .then((n) => n && setNote((cur) => cur ?? n))
      .catch(() => {});
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
          One senior-advisor read across the whole book: how you stand, whether
          your mix is still on-plan, color on your holdings, and the actions
          that matter this week — or just talk to the advisor below, no brief
          required.
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
          {/* THE PLAN. The brief generates this itself — there is no separate
              transition feature to contradict it. */}
          {(note.sequence?.length ?? 0) > 0 && (
            <div className="advisor-sec brief-plan">
              <h4>The plan — what to do, and when</h4>
              <ol className="bp-steps">
                {note.sequence!.map((s) => (
                  <li key={s.n}>
                    <div className="bp-when">
                      <span className="bp-n">{String(s.n).padStart(2, "0")}</span>
                      <span className="bp-trigger">{s.when}</span>
                    </div>
                    <p className="bp-do">{s.do}</p>
                    {s.why && <p className="bp-why">{s.why}</p>}
                    <button
                      className="btn ghost bp-pin"
                      onClick={() =>
                        api.addPin({ source: "brief", text: `${s.do} (when ${s.when})` })
                      }
                    >
                      Pin this step
                    </button>
                  </li>
                ))}
              </ol>
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
          {/* The rest of the read: true, useful, and not a decision. It opens
              on demand and stays open for the session. */}
          {((note.insights?.length ?? 0) + (note.mix?.length ?? 0) + (note.positions?.length ?? 0)) > 0 && (
            <>
              <button className="btn ghost brief-more" onClick={() => setFull((v) => !v)}
                      aria-expanded={full}>
                {full ? "Hide the full read" : "Read the rest"}
                <span className="mut">
                  {" "}· {(note.insights?.length ?? 0) + (note.mix?.length ?? 0) + (note.positions?.length ?? 0)} more points
                </span>
              </button>
              {full && (
                <>
                  {note.insights?.length > 0 && (
                    <div className="advisor-sec">
                      <h4>Where you stand</h4>
                      <BulletList items={note.insights} kind="insight" />
                    </div>
                  )}
                  {(note.mix?.length ?? 0) > 0 && (
                    <div className="advisor-sec">
                      <h4>Is your mix still right?</h4>
                      <BulletList items={note.mix!} kind="insight" />
                    </div>
                  )}
                  {(note.positions?.length ?? 0) > 0 && (
                    <div className="advisor-sec">
                      <h4>Your holdings</h4>
                      <BulletList items={note.positions!} kind="insight" />
                    </div>
                  )}
                </>
              )}
            </>
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
