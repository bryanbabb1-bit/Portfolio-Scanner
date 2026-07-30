"use client";
import { useCallback, useEffect, useState } from "react";
import { api, Pin, PINS_CHANGED } from "../lib/api";

/* Where pinning actually goes.
 *
 * Every "Pin" button in the app wrote to data/pinned.json and nothing rendered
 * it: GamePlan was the only view of pins and it stopped being mounted when the
 * plan board was removed so it couldn't contradict the brief. Pinning worked
 * perfectly and was invisible, which is indistinguishable from broken.
 *
 * This is deliberately NOT a plan board — it doesn't schedule, trigger or
 * reorder anything, so it can't disagree with the brief. It is just the list of
 * things you chose to keep, with a way to check them off.
 */

const RECENT_DONE = 3;

export function PinnedActions() {
  const [pins, setPins] = useState<Pin[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [showDone, setShowDone] = useState(false);

  const refresh = useCallback(() => {
    api
      .pins()
      .then((r) => setPins(r.results))
      .catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    // Pinning from anywhere — the brief, the dock, a slap — lands here at once.
    window.addEventListener(PINS_CHANGED, refresh);
    return () => window.removeEventListener(PINS_CHANGED, refresh);
  }, [refresh]);

  const open = pins.filter((p) => p.status === "open");
  const done = pins.filter((p) => p.status === "done");

  const act = async (id: string, fn: () => Promise<unknown>) => {
    setBusy(id);
    try {
      await fn();
      refresh();
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="card" id="pinned" style={{ marginBottom: 20 }}>
      <div className="section-title">
        Pinned · your list
        {open.length > 0 && <span className="pa-count">{open.length}</span>}
      </div>

      {open.length === 0 ? (
        <p className="mut" style={{ fontSize: 13, lineHeight: 1.55 }}>
          Nothing pinned. Pin an action from the brief or from the advisor and it
          lands here.
        </p>
      ) : (
        <ul className="pa-list">
          {open.map((p) => (
            <li key={p.id} className="pa-row">
              <div className="pa-main">
                <span className="pa-text">{p.text}</span>
                <span className="pa-meta">
                  {p.source}
                  {" · "}
                  {p.created_at.slice(5, 16)}
                </span>
              </div>
              <div className="pa-acts">
                <button
                  className="btn ghost"
                  disabled={busy === p.id}
                  title="I did this"
                  onClick={() => act(p.id, () => api.setPinStatus(p.id, "done"))}
                >
                  Done
                </button>
                <button
                  className="pa-drop"
                  disabled={busy === p.id}
                  title="Remove from the list"
                  onClick={() => act(p.id, () => api.deletePin(p.id))}
                >
                  ×
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {done.length > 0 && (
        <div className="pa-done">
          <button className="pa-toggle" onClick={() => setShowDone((s) => !s)}>
            {showDone ? "Hide" : "Show"} {done.length} done
          </button>
          {showDone && (
            <ul className="pa-list">
              {(showDone ? done : done.slice(0, RECENT_DONE)).map((p) => (
                <li key={p.id} className="pa-row is-done">
                  <div className="pa-main">
                    <span className="pa-text">{p.text}</span>
                    <span className="pa-meta">
                      {p.retired_reason
                        ? `stood down — ${p.retired_reason}`
                        : `done ${(p.done_at || "").slice(5, 16)}`}
                    </span>
                  </div>
                  <div className="pa-acts">
                    <button
                      className="pa-drop"
                      disabled={busy === p.id}
                      title="Remove from the list"
                      onClick={() => act(p.id, () => api.deletePin(p.id))}
                    >
                      ×
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
