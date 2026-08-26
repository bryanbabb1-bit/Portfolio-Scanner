"use client";
import { useCallback, useEffect, useState } from "react";
import { API_BASE } from "../lib/api";

/* What the advisor is not allowed to recommend, and what you want instead.
 *
 * Bryan told the advisor four times to stop suggesting SBUX, VXUS and DE. It
 * agreed each time and then led the next brief with "Buy $250 VXUS". The chat
 * log had every word; the brief never read it.
 *
 * These are now enforced rather than requested — a blocked name is stripped
 * from the plan after the model writes it. This panel exists so the rule is
 * visible and, more importantly, REVERSIBLE: a constraint you cannot see or
 * undo is its own kind of broken.
 */

interface Blocked {
  symbol: string;
  reason?: string;
  source?: string;
  ts?: number;
}
interface Wanted {
  theme: string;
  source?: string;
}
interface Note {
  text: string;
}
interface Prefs {
  blocked: Blocked[];
  wanted: Wanted[];
  notes: Note[];
}

export function Preferences() {
  const [p, setP] = useState<Prefs | null>(null);
  const [sym, setSym] = useState("");
  const [theme, setTheme] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    fetch(`${API_BASE}/api/preferences`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d && setP(d))
      .catch(() => {});
  }, []);
  useEffect(load, [load]);

  const call = async (path: string, init: RequestInit) => {
    setBusy(true);
    try {
      await fetch(`${API_BASE}${path}`, init);
      load();
    } finally {
      setBusy(false);
    }
  };

  const addBlock = () => {
    const s = sym.trim().toUpperCase();
    if (!s) return;
    setSym("");
    call("/api/preferences/block", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol: s, reason: "added from settings" }),
    });
  };

  const addWant = () => {
    const t = theme.trim();
    if (!t) return;
    setTheme("");
    call("/api/preferences/want", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ theme: t }),
    });
  };

  if (!p) return null;

  return (
    <div className="card prefs">
      <div className="section-title">Standing instructions</div>
      <p className="prefs-lead">
        The advisor is <strong>blocked</strong> from putting these in a plan or
        an idea list. This is enforced after it writes the brief, not just asked
        for — it ignored the request four times before this existed.
      </p>

      <div className="prefs-label">Never recommend</div>
      <div className="prefs-chips">
        {p.blocked.length === 0 && <span className="mut">Nothing blocked.</span>}
        {p.blocked.map((b) => (
          <span key={b.symbol} className="prefs-chip block" title={b.reason || ""}>
            {b.symbol}
            <button
              disabled={busy}
              title={`Allow ${b.symbol} again`}
              onClick={() =>
                call(`/api/preferences/block/${b.symbol}`, { method: "DELETE" })
              }
            >
              ×
            </button>
          </span>
        ))}
      </div>
      <div className="prefs-add">
        <input
          value={sym}
          placeholder="Ticker"
          onChange={(e) => setSym(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && addBlock()}
          maxLength={6}
        />
        <button className="btn ghost" onClick={addBlock} disabled={busy}>
          Block
        </button>
      </div>

      <div className="prefs-label">Wants ideas from</div>
      <div className="prefs-chips">
        {p.wanted.length === 0 && <span className="mut">No sector preference set.</span>}
        {p.wanted.map((w) => (
          <span key={w.theme} className="prefs-chip want">
            {w.theme}
            <button
              disabled={busy}
              title={`Stop favouring ${w.theme}`}
              onClick={() =>
                call(`/api/preferences/want/${encodeURIComponent(w.theme)}`, {
                  method: "DELETE",
                })
              }
            >
              ×
            </button>
          </span>
        ))}
      </div>
      <div className="prefs-add">
        <input
          value={theme}
          placeholder="e.g. energy"
          onChange={(e) => setTheme(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && addWant()}
          maxLength={40}
        />
        <button className="btn ghost" onClick={addWant} disabled={busy}>
          Want
        </button>
      </div>

      {p.notes.length > 0 && (
        <>
          <div className="prefs-label">Standing notes</div>
          <ul className="prefs-notes">
            {p.notes.map((n, i) => (
              <li key={i}>{n.text}</li>
            ))}
          </ul>
        </>
      )}

      <p className="prefs-foot">
        Telling the advisor in chat works too — &ldquo;stop recommending X&rdquo;
        is captured automatically now, in the same call that answers you.
      </p>
    </div>
  );
}
