"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, Pin } from "../lib/api";

// The persistent action list: advisor recommendations the user pinned.
// Server-side storage, so it survives refreshes and shows on every device.
export function PinnedActions() {
  const [pins, setPins] = useState<Pin[]>([]);

  const load = () => api.pins().then((d) => setPins(d.results)).catch(() => {});
  useEffect(() => {
    load();
    const t = setInterval(load, 60_000);
    return () => clearInterval(t);
  }, []);

  if (!pins.length) return null;
  const open = pins.filter((p) => p.status === "open").length;

  async function toggle(p: Pin) {
    const next = p.status === "done" ? "open" : "done";
    setPins((cur) => cur.map((x) => (x.id === p.id ? { ...x, status: next } : x)));
    try {
      await api.setPinStatus(p.id, next);
      load();
    } catch {
      load();
    }
  }

  async function remove(p: Pin) {
    setPins((cur) => cur.filter((x) => x.id !== p.id));
    try {
      await api.deletePin(p.id);
    } catch {
      load();
    }
  }

  return (
    <div className="card pins-panel" style={{ marginBottom: 24 }}>
      <div className="section-title" style={{ marginBottom: 8 }}>
        Pinned Actions{" "}
        <span className="mut" style={{ textTransform: "none", letterSpacing: 0 }}>
          · {open} open
        </span>
      </div>
      <div className="pins-list">
        {pins.map((p) => (
          <div key={p.id} className={`pin-row ${p.status}`}>
            <input
              type="checkbox"
              checked={p.status === "done"}
              onChange={() => toggle(p)}
              title={p.status === "done" ? "Reopen" : "Mark done"}
            />
            {p.symbol ? (
              <Link href={`/stock/${p.symbol}`} className="alert-sym">
                {p.symbol}
              </Link>
            ) : (
              <span className="alert-sym mut">BOOK</span>
            )}
            <span className="pin-text" title={p.points.join("\n")}>{p.text}</span>
            <span className="mut pin-date">{p.created_at.slice(5, 16)}</span>
            <button className="icon-btn" title="Remove pin" onClick={() => remove(p)}>
              ✕
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
