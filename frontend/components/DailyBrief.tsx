"use client";
import { useEffect, useState } from "react";
import { api, DailyBrief as Brief } from "../lib/api";
import { BulletList } from "./BulletList";

// The pre-market "what to watch today" / end-of-day recap. A one-time read:
// dismiss it when done and it stays hidden until the next brief posts.
export function DailyBrief() {
  const [brief, setBrief] = useState<Brief | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const [expanded, setExpanded] = useState(false); // re-open a dismissed one without un-dismissing
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.summary().then((d) => {
      setBrief(d.brief);
      setDismissed(d.dismissed);
    }).catch(() => {});
  }, []);

  async function gen(kind: "morning" | "eod") {
    setBusy(true);
    try {
      setBrief(await api.generateBrief(kind));
      setDismissed(false); // a freshly generated brief is unread
      setExpanded(false);
    } catch {
      /* ignore */
    } finally {
      setBusy(false);
    }
  }

  async function dismiss() {
    setDismissed(true);
    setExpanded(false);
    api.dismissBrief().catch(() => {});
  }

  const morning = brief?.type === "morning";
  const title = brief ? (morning ? "Morning Brief" : "Close Recap") : "Daily Brief";

  // Dismissed + not re-opened: a slim bar you can reopen, out of the way.
  if (brief && dismissed && !expanded) {
    return (
      <div className="card daily-brief collapsed" id="daily-brief">
        <span className="mut" style={{ fontSize: 13 }}>
          {title} read — {brief.headline}
        </span>
        <button className="btn ghost" onClick={() => setExpanded(true)}>Show</button>
      </div>
    );
  }

  return (
    <div className="card daily-brief" id="daily-brief">
      <div className="editor-head">
        <div className="section-title" style={{ margin: 0 }}>
          {title}
          {brief && (
            <span className="mut" style={{ fontSize: 11, fontWeight: 400, marginLeft: 8 }}>
              {brief.generated_at?.slice(0, 16)}
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <span className="mut" style={{ fontSize: 11 }}>Generate</span>
          <button className="btn ghost" onClick={() => gen("morning")} disabled={busy} title="Generate the morning 'what to watch today' brief now">
            {busy ? "…" : "Morning brief"}
          </button>
          <button className="btn ghost" onClick={() => gen("eod")} disabled={busy} title="Generate the end-of-day recap now">
            {busy ? "…" : "Day recap"}
          </button>
          {brief && (
            <button className="icon-btn jr-btn" title="Dismiss — hides until the next brief" onClick={dismiss}>✕</button>
          )}
        </div>
      </div>

      {!brief ? (
        <p className="mut" style={{ fontSize: 14 }}>
          No brief yet today. It posts automatically pre-market and after the close — or generate one now.
        </p>
      ) : (
        <>
          <div className="brief-headline">{brief.headline}</div>
          {brief.summary && <p className="brief-summary">{brief.summary}</p>}
          {brief.recap?.length > 0 && (
            <div className="advisor-sec">
              <h4>Today</h4>
              <BulletList items={brief.recap} kind="insight" />
            </div>
          )}
          {brief.watch?.length > 0 && (
            <div className="advisor-sec">
              <h4>{morning ? "Watch today" : "Watch tomorrow"}</h4>
              <BulletList items={brief.watch} kind="action" />
            </div>
          )}
          <div style={{ marginTop: 14 }}>
            <button className="btn ghost" onClick={dismiss}>Got it, dismiss</button>
          </div>
        </>
      )}
    </div>
  );
}
