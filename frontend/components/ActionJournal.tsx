"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, JournalDraft, JournalEntry } from "../lib/api";
import { money } from "./format";

const ACTION_META: Record<string, { label: string; cls: string }> = {
  buy: { label: "BUY", cls: "buy" },
  sell: { label: "SELL", cls: "sell" },
  note: { label: "NOTE", cls: "done" },
};

const COLLAPSED = 6;
const BLANK: JournalDraft = { action: "buy", symbol: "", note: "" };

// Structured, user-controlled trade log: date · ticker · buy/sell · shares ·
// price · note. Auto-detected trades land here too; everything is editable.
// The advisor reads this journal, so keeping it accurate keeps advice sane.
export function ActionJournal() {
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState<JournalDraft>(BLANK);
  const [err, setErr] = useState<string | null>(null);

  const load = () => api.journal(90).then((d) => setEntries(d.results)).catch(() => {});
  useEffect(() => {
    load();
    const t = setInterval(load, 60_000);
    return () => clearInterval(t);
  }, []);

  const startAdd = () => {
    setDraft({ ...BLANK, date: new Date().toISOString().slice(0, 10) });
    setEditing(null);
    setAdding(true);
  };
  const startEdit = (e: JournalEntry) => {
    setDraft({ symbol: e.symbol, action: e.action, date: e.date, shares: e.shares, price: e.price, note: e.note });
    setAdding(false);
    setEditing(e.id);
  };
  const cancel = () => {
    setAdding(false);
    setEditing(null);
    setErr(null);
  };

  async function save() {
    setErr(null);
    try {
      if (adding) await api.addJournal(draft);
      else if (editing) await api.updateJournal(editing, draft);
      cancel();
      load();
    } catch (e: any) {
      setErr(e.message || "Save failed");
    }
  }

  async function remove(e: JournalEntry) {
    setEntries((cur) => cur.filter((x) => x.id !== e.id));
    try {
      await api.deleteJournal(e.id);
    } catch {
      load();
    }
  }

  const shown = expanded ? entries : entries.slice(0, COLLAPSED);

  const editorRow = (
    <div className="jr-row jr-edit">
      <input
        type="date"
        value={draft.date ?? ""}
        onChange={(e) => setDraft({ ...draft, date: e.target.value })}
      />
      <select
        value={draft.action}
        onChange={(e) => setDraft({ ...draft, action: e.target.value as JournalDraft["action"] })}
      >
        <option value="buy">Buy</option>
        <option value="sell">Sell</option>
        <option value="note">Note</option>
      </select>
      <input
        className="sym"
        placeholder="TICKER"
        value={draft.symbol ?? ""}
        onChange={(e) => setDraft({ ...draft, symbol: e.target.value.toUpperCase() })}
      />
      <input
        type="number"
        placeholder="Shares"
        min={0}
        step="any"
        value={draft.shares ?? ""}
        onChange={(e) => setDraft({ ...draft, shares: e.target.value === "" ? null : parseFloat(e.target.value) })}
      />
      <input
        type="number"
        placeholder="Price"
        min={0}
        step="any"
        value={draft.price ?? ""}
        onChange={(e) => setDraft({ ...draft, price: e.target.value === "" ? null : parseFloat(e.target.value) })}
      />
      <input
        placeholder="Note (optional)"
        value={draft.note ?? ""}
        onChange={(e) => setDraft({ ...draft, note: e.target.value })}
      />
      <div style={{ display: "flex", gap: 6 }}>
        <button className="btn" style={{ padding: "6px 12px" }} onClick={save}>Save</button>
        <button className="btn ghost" style={{ padding: "6px 10px" }} onClick={cancel}>✕</button>
      </div>
    </div>
  );

  return (
    <div className="card journal-panel" style={{ marginBottom: 24 }}>
      <div className="chart-head" style={{ marginBottom: 8 }}>
        <div className="section-title" style={{ margin: 0 }}>
          Action Journal{" "}
          <span className="mut" style={{ textTransform: "none", letterSpacing: 0 }}>
            · {entries.length} moves in 90 days · the advisor sees this
          </span>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {entries.length > COLLAPSED && (
            <button className="btn ghost" onClick={() => setExpanded(!expanded)}>
              {expanded ? "Show less" : `Show all ${entries.length}`}
            </button>
          )}
          <button className="btn ghost" onClick={startAdd}>+ Add move</button>
        </div>
      </div>

      {err && <div className="err" style={{ marginBottom: 10 }}>{err}</div>}
      {adding && editorRow}

      <div className="pins-list">
        {shown.map((e) =>
          editing === e.id ? (
            <div key={e.id}>{editorRow}</div>
          ) : (
            <div key={e.id} className="jr-row">
              <span className="mut pin-date">{e.date.slice(5)}</span>
              <span className={`journal-badge ${ACTION_META[e.action]?.cls || "done"}`}>
                {ACTION_META[e.action]?.label || e.action.toUpperCase()}
              </span>
              {e.symbol ? (
                <Link href={`/stock/${e.symbol}`} className="alert-sym">{e.symbol}</Link>
              ) : (
                <span className="alert-sym mut">BOOK</span>
              )}
              <span className="jr-qty mut">
                {e.shares ? `${e.shares.toLocaleString(undefined, { maximumFractionDigits: 4 })} sh` : ""}
                {e.price ? ` @ ${money(e.price)}` : ""}
              </span>
              <span className="pin-text" title={`source: ${e.source}`}>{e.note}</span>
              <button className="icon-btn jr-btn" title="Edit" onClick={() => startEdit(e)}>✎</button>
              <button className="icon-btn jr-btn" title="Delete" onClick={() => remove(e)}>✕</button>
            </div>
          )
        )}
        {!entries.length && !adding && (
          <div className="empty">No moves recorded yet — trades you make are detected automatically, or add one.</div>
        )}
      </div>
    </div>
  );
}
