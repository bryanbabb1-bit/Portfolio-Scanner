"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, Watchpoint } from "../lib/api";

const KIND_LABEL: Record<Watchpoint["kind"], string> = {
  price_below: "price ≤ $",
  price_above: "price ≥ $",
  rsi_below: "RSI ≤",
  rsi_above: "RSI ≥",
};

// Standing tripwires from advisor advice ("sell half below $38.80") or set
// by hand. When one triggers, the conviction scan fires a full-screen slap
// and journals it — no chart-stalking required.
export function Watchpoints() {
  const [items, setItems] = useState<Watchpoint[]>([]);
  const [adding, setAdding] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [draft, setDraft] = useState({
    symbol: "", kind: "price_below" as Watchpoint["kind"], level: "", note: "",
  });

  const load = () => api.watchpoints().then((d) => setItems(d.results)).catch(() => {});
  useEffect(() => {
    load();
    const t = setInterval(load, 60_000);
    return () => clearInterval(t);
  }, []);

  async function save() {
    setErr(null);
    try {
      await api.addWatchpoint({
        symbol: draft.symbol,
        kind: draft.kind,
        level: parseFloat(draft.level),
        note: draft.note,
      });
      setDraft({ symbol: "", kind: "price_below", level: "", note: "" });
      setAdding(false);
      load();
    } catch (e: any) {
      setErr(e.message || "Could not arm watchpoint");
    }
  }

  async function extract() {
    setExtracting(true);
    setErr(null);
    setMsg(null);
    try {
      const d = await api.extractWatchpoints();
      setMsg(d.created
        ? `Armed ${d.created} watchpoint${d.created > 1 ? "s" : ""} from the advisor's advice.`
        : "No new numeric conditions found in the latest advice.");
      load();
    } catch (e: any) {
      setErr(e.message || "Extraction failed");
    } finally {
      setExtracting(false);
    }
  }

  const armed = items.filter((w) => w.status === "armed");

  return (
    <div className="card wp-panel" style={{ marginBottom: 28 }}>
      <div className="chart-head" style={{ marginBottom: 8 }}>
        <div className="section-title" style={{ margin: 0 }}>
          Watchpoints{" "}
          <span className="mut" style={{ textTransform: "none", letterSpacing: 0 }}>
            · {armed.length} armed · slaps you when a level hits
          </span>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn ghost" onClick={extract} disabled={extracting}
            title="Scan the latest brief + strategy for conditions like 'sell below $X' and arm them">
            {extracting ? "Scanning advice…" : "⚡ Arm from advice"}
          </button>
          <button className="btn ghost" onClick={() => setAdding(!adding)}>
            {adding ? "✕" : "+ Add"}
          </button>
        </div>
      </div>

      {err && <div className="err" style={{ marginBottom: 8 }}>{err}</div>}
      {msg && <div className="ok-banner" style={{ marginBottom: 8 }}>{msg}</div>}

      {adding && (
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
          <input type="number" min={0} step="any" placeholder="Level"
            value={draft.level} onChange={(e) => setDraft({ ...draft, level: e.target.value })} />
          <input placeholder="What to do when it hits (shown on the alert)"
            value={draft.note} onChange={(e) => setDraft({ ...draft, note: e.target.value })} />
          <button className="btn" onClick={save}
            disabled={!draft.symbol || !draft.level}>Arm</button>
        </div>
      )}

      <div className="pins-list">
        {items.map((w) => (
          <div key={w.id} className={`pin-row ${w.status === "triggered" ? "done" : ""}`}>
            <span className={`signal-side ${w.side}`}>{w.side === "buy" ? "BUY" : "SELL"}</span>
            <Link href={`/stock/${w.symbol}`} className="alert-sym">{w.symbol}</Link>
            <span className="wp-cond">
              {KIND_LABEL[w.kind]}{w.level.toLocaleString()}
            </span>
            <span className="pin-text" title={w.note}>
              {w.status === "triggered" ? `HIT ${w.triggered_at} — ` : ""}
              {w.note || "alert me"}
            </span>
            <span className="mut pin-date" title={`source: ${w.source}`}>
              {w.source === "advisor" ? "AI" : "you"} · {w.created_at.slice(5, 10)}
            </span>
            <button className="icon-btn jr-btn" title="Remove" onClick={async () => {
              setItems((cur) => cur.filter((x) => x.id !== w.id));
              try { await api.deleteWatchpoint(w.id); } catch { load(); }
            }}>✕</button>
          </div>
        ))}
        {!items.length && !adding && (
          <div className="empty">
            Nothing armed. Hit "Arm from advice" after a brief, or add a level by hand.
          </div>
        )}
      </div>
    </div>
  );
}
