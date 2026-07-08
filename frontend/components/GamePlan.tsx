"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, Pin, Watchpoint } from "../lib/api";

const OPEN_KEY = "pscan-gameplan-open";

const KIND_LABEL: Record<Watchpoint["kind"], string> = {
  price_below: "≤ $",
  price_above: "≥ $",
  rsi_below: "RSI ≤ ",
  rsi_above: "RSI ≥ ",
};

// THE GAME PLAN — one panel for everything you intend to do.
// Armed triggers (watchpoints) sorted by how close they are to firing,
// recent hits highlighted until cleared, and plain to-dos (pins) with
// checkboxes. Replaces the separate Pinned Actions + Watchpoints panels.
export function GamePlan() {
  const [wps, setWps] = useState<Watchpoint[]>([]);
  const [pins, setPins] = useState<Pin[]>([]);
  const [open, setOpen] = useState(true);
  const [adding, setAdding] = useState(false);
  const [mode, setMode] = useState<"trigger" | "task">("trigger");
  const [extracting, setExtracting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [draft, setDraft] = useState({
    symbol: "", kind: "price_below" as Watchpoint["kind"], level: "",
    note: "", confirm: "touch" as "touch" | "close", text: "",
  });

  const load = () => {
    api.watchpoints().then((d) => setWps(d.results)).catch(() => {});
    api.pins().then((d) => setPins(d.results)).catch(() => {});
  };
  useEffect(() => {
    load();
    try {
      const v = localStorage.getItem(OPEN_KEY);
      if (v != null) setOpen(v === "1");
    } catch {}
    const t = setInterval(load, 60_000);
    return () => clearInterval(t);
  }, []);

  const toggle = () => {
    setOpen((o) => {
      try { localStorage.setItem(OPEN_KEY, o ? "0" : "1"); } catch {}
      return !o;
    });
  };

  async function save() {
    setErr(null);
    try {
      if (mode === "trigger") {
        await api.addWatchpoint({
          symbol: draft.symbol, kind: draft.kind, level: parseFloat(draft.level),
          note: draft.note, confirm: draft.confirm,
        });
      } else {
        await api.addPin({ symbol: draft.symbol || undefined, source: "manual", text: draft.text });
      }
      setDraft({ symbol: "", kind: "price_below", level: "", note: "", confirm: "touch", text: "" });
      setAdding(false);
      load();
    } catch (e: any) {
      setErr(e.message || "Save failed");
    }
  }

  async function extract() {
    setExtracting(true); setErr(null); setMsg(null);
    try {
      const d = await api.extractWatchpoints();
      setMsg(d.created ? `Armed ${d.created} trigger${d.created > 1 ? "s" : ""} from the advisor's advice.`
                       : "No new numeric conditions in the latest advice.");
      load();
    } catch (e: any) {
      setErr(e.message || "Extraction failed");
    } finally {
      setExtracting(false);
    }
  }

  const now = Date.now() / 1000;
  const armed = wps
    .filter((w) => w.status === "armed")
    .sort((a, b) => Math.abs((a as any).distance_pct ?? 99) - Math.abs((b as any).distance_pct ?? 99));
  const hits = wps.filter((w) => w.status === "triggered" &&
    (w as any).ts != null ? now - (w as any).ts < 48 * 3600 : w.status === "triggered");
  const todos = pins.filter((p) => p.status === "open");

  const distance = (w: Watchpoint) => {
    const d = (w as any).distance_pct as number | null | undefined;
    if (d == null) return null;
    const away = Math.abs(d);
    const unit = w.kind.startsWith("price") ? "%" : " pts";
    return { text: `${away.toFixed(1)}${unit} away`, hot: away <= (w.kind.startsWith("price") ? 2 : 4) };
  };

  return (
    <div className="card gp-panel" id="game-plan" style={{ marginBottom: 28 }}>
      <div className="chart-head" style={{ marginBottom: open ? 8 : 0 }}>
        <button className="section-title collapse-head" style={{ margin: 0 }} onClick={toggle}>
          <span className="chev">{open ? "▾" : "▸"}</span> Game Plan{" "}
          <span className="mut" style={{ textTransform: "none", letterSpacing: 0 }}>
            · {armed.length} armed · {todos.length} to-do
            {hits.length > 0 && <span className="neg"> · {hits.length} hit</span>}
          </span>
        </button>
        {open && (
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn ghost" onClick={extract} disabled={extracting}
              title="Mine the latest brief + strategy for conditions and arm them">
              {extracting ? "Scanning…" : "Arm from advice"}
            </button>
            <button className="btn ghost" onClick={() => setAdding(!adding)}>
              {adding ? "✕" : "+ Add"}
            </button>
          </div>
        )}
      </div>

      {open && (
        <>
          {err && <div className="err" style={{ marginBottom: 8 }}>{err}</div>}
          {msg && <div className="ok-banner" style={{ marginBottom: 8 }}>{msg}</div>}

          {adding && (
            <div className="gp-form">
              <div className="range-toggle" style={{ marginBottom: 8 }}>
                <button className={mode === "trigger" ? "active" : ""} onClick={() => setMode("trigger")}>
                  Trigger (alerts you)
                </button>
                <button className={mode === "task" ? "active" : ""} onClick={() => setMode("task")}>
                  Task (checklist)
                </button>
              </div>
              {mode === "trigger" ? (
                <div className="wp-form">
                  <input className="sym" placeholder="TICKER" value={draft.symbol}
                    onChange={(e) => setDraft({ ...draft, symbol: e.target.value.toUpperCase() })} />
                  <select value={draft.kind}
                    onChange={(e) => setDraft({ ...draft, kind: e.target.value as Watchpoint["kind"] })}>
                    <option value="price_below">Price drops to</option>
                    <option value="price_above">Price rises to</option>
                    <option value="rsi_below">RSI drops to</option>
                    <option value="rsi_above">RSI rises to</option>
                  </select>
                  <input type="number" min={0} step="any" placeholder="Level" value={draft.level}
                    onChange={(e) => setDraft({ ...draft, level: e.target.value })} />
                  <select value={draft.confirm}
                    onChange={(e) => setDraft({ ...draft, confirm: e.target.value as "touch" | "close" })}>
                    <option value="touch">On touch</option>
                    <option value="close">On close</option>
                  </select>
                  <input placeholder="What to do when it fires" value={draft.note}
                    onChange={(e) => setDraft({ ...draft, note: e.target.value })} />
                  <button className="btn" onClick={save} disabled={!draft.symbol || !draft.level}>Arm</button>
                </div>
              ) : (
                <div className="gp-task-form">
                  <input className="sym" placeholder="TICKER (optional)" value={draft.symbol}
                    onChange={(e) => setDraft({ ...draft, symbol: e.target.value.toUpperCase() })} />
                  <input placeholder="The action to remember" value={draft.text}
                    onChange={(e) => setDraft({ ...draft, text: e.target.value })} />
                  <button className="btn" onClick={save} disabled={!draft.text.trim()}>Add</button>
                </div>
              )}
            </div>
          )}

          <div className="gp-hint mut" style={{ fontSize: 11.5, lineHeight: 1.5, marginBottom: 8 }}>
            Reminders &amp; triggers only — clearing one won&apos;t log a trade. Your journal fills from the changes you make in Settings.
          </div>

          <div className="pins-list">
            {/* recent hits — act on these */}
            {hits.map((w) => (
              <div key={w.id} className="pin-row gp-hit">
                <span className="journal-badge warn">HIT</span>
                <Link href={`/stock/${w.symbol}`} className="alert-sym">{w.symbol}</Link>
                <span className="wp-cond">{KIND_LABEL[w.kind]}{w.level.toLocaleString()}</span>
                <span className="pin-text">{w.note || "condition met"}</span>
                <span className="mut pin-date">{w.triggered_at?.slice(5)}</span>
                <button className="icon-btn jr-btn" title="Clear" onClick={async () => {
                  setWps((c) => c.filter((x) => x.id !== w.id));
                  try { await api.deleteWatchpoint(w.id); } catch { load(); }
                }}>✕</button>
              </div>
            ))}

            {/* armed triggers, closest to firing first */}
            {armed.map((w) => {
              const d = distance(w);
              return (
                <div key={w.id} className="pin-row">
                  <span className={`signal-side ${w.side}`}>{w.side === "buy" ? "BUY" : "SELL"}</span>
                  <Link href={`/stock/${w.symbol}`} className="alert-sym">{w.symbol}</Link>
                  <span className="wp-cond">
                    {KIND_LABEL[w.kind]}{w.level.toLocaleString()}
                    {w.confirm === "close" && <span className="mut"> close</span>}
                  </span>
                  {d && <span className={`gp-dist${d.hot ? " hot" : ""}`}>{d.text}</span>}
                  <span className="pin-text" title={w.note}>{w.note || "alert me"}</span>
                  <span className="mut pin-date" title={`source: ${w.source}`}>
                    {w.source === "advisor" ? "AI" : "you"}
                  </span>
                  <button className="icon-btn jr-btn" title="Remove" onClick={async () => {
                    setWps((c) => c.filter((x) => x.id !== w.id));
                    try { await api.deleteWatchpoint(w.id); } catch { load(); }
                  }}>✕</button>
                </div>
              );
            })}

            {/* pinned reminders — clearing one does NOT log a trade; the
                journal fills only from real portfolio edits in Settings */}
            {todos.map((p) => (
              <div key={p.id} className="pin-row">
                {p.symbol ? (
                  <Link href={`/stock/${p.symbol}`} className="alert-sym">{p.symbol}</Link>
                ) : (
                  <span className="alert-sym mut">PORTFOLIO</span>
                )}
                <span className="pin-text" title={p.points.join("\n")}>{p.text}</span>
                <span className="mut pin-date">{p.created_at.slice(5, 10)}</span>
                <button className="icon-btn jr-btn" title="Clear this reminder (does not record a trade)" onClick={async () => {
                  setPins((c) => c.filter((x) => x.id !== p.id));
                  try { await api.deletePin(p.id); } catch { load(); }
                }}>✕</button>
              </div>
            ))}

            {!armed.length && !todos.length && !hits.length && !adding && (
              <div className="empty">
                Nothing planned. Pin advice, arm a trigger, or hit &quot;Arm from advice&quot; after a brief.
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
