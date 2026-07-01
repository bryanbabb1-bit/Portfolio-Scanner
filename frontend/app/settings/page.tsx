"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, Holding, PortfolioConfig, WatchItem } from "../../lib/api";

const BLANK: PortfolioConfig = {
  owner: "You",
  advisor_persona: "senior financial advisor at Charles Schwab",
  themes: {},
  holdings: [],
  watchlist: [],
};

export default function Settings() {
  const [cfg, setCfg] = useState<PortfolioConfig | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api
      .config()
      .then((c) => setCfg({ ...BLANK, ...c }))
      .catch((e) => setErr(e.message));
  }, []);

  if (err && !cfg) return <div className="err">Could not load config ({err}).</div>;
  if (!cfg) return <div className="loading">Loading config…</div>;

  const themeNames = Object.keys(cfg.themes);

  // -------- holdings --------
  const setHolding = (i: number, patch: Partial<Holding>) =>
    setCfg({ ...cfg, holdings: cfg.holdings.map((h, k) => (k === i ? { ...h, ...patch } : h)) });
  const addHolding = () =>
    setCfg({ ...cfg, holdings: [...cfg.holdings, { symbol: "", shares: 0, cost_basis: 0, theme: themeNames[0] }] });
  const delHolding = (i: number) =>
    setCfg({ ...cfg, holdings: cfg.holdings.filter((_, k) => k !== i) });

  // -------- watchlist --------
  const setWatch = (i: number, patch: Partial<WatchItem>) =>
    setCfg({ ...cfg, watchlist: cfg.watchlist.map((w, k) => (k === i ? { ...w, ...patch } : w)) });
  const addWatch = () =>
    setCfg({ ...cfg, watchlist: [...cfg.watchlist, { symbol: "", theme: themeNames[0] }] });
  const delWatch = (i: number) =>
    setCfg({ ...cfg, watchlist: cfg.watchlist.filter((_, k) => k !== i) });

  // -------- themes --------
  const renameTheme = (oldName: string, next: string) => {
    const themes: Record<string, string> = {};
    for (const [k, v] of Object.entries(cfg.themes)) themes[k === oldName ? next : k] = v;
    setCfg({ ...cfg, themes });
  };
  const setThemeDesc = (name: string, desc: string) =>
    setCfg({ ...cfg, themes: { ...cfg.themes, [name]: desc } });
  const addTheme = () => setCfg({ ...cfg, themes: { ...cfg.themes, "New Theme": "" } });
  const delTheme = (name: string) => {
    const themes = { ...cfg.themes };
    delete themes[name];
    setCfg({ ...cfg, themes });
  };

  const save = async () => {
    setSaving(true);
    setErr(null);
    setMsg(null);
    // Drop fully-empty rows so a blank trailing row doesn't fail validation.
    const clean: PortfolioConfig = {
      ...cfg,
      holdings: cfg.holdings.filter((h) => h.symbol.trim()),
      watchlist: cfg.watchlist.filter((w) => w.symbol.trim()),
    };
    try {
      const saved = await api.saveConfig(clean);
      setCfg({ ...BLANK, ...saved });
      setMsg("Saved. Dashboard and scans now reflect these changes.");
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <div className="page-head">
        <h1>Settings</h1>
        <p>Configure your holdings, watchlist and themes. Changes save to the backend and drive every view.</p>
      </div>

      {msg && <div className="ok-banner">{msg}</div>}
      {err && <div className="err" style={{ marginBottom: 16 }}>{err}</div>}

      {/* --------- profile --------- */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="section-title">Profile</div>
        <div className="form-grid">
          <label>
            <span>Owner</span>
            <input value={cfg.owner} onChange={(e) => setCfg({ ...cfg, owner: e.target.value })} />
          </label>
          <label>
            <span>Advisor persona</span>
            <input
              value={cfg.advisor_persona}
              onChange={(e) => setCfg({ ...cfg, advisor_persona: e.target.value })}
            />
          </label>
        </div>
      </div>

      {/* --------- holdings --------- */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="editor-head">
          <div className="section-title" style={{ margin: 0 }}>Holdings ({cfg.holdings.length})</div>
          <button className="btn ghost" onClick={addHolding}>+ Add holding</button>
        </div>
        <div className="edit-table">
          <div className="et-row et-head">
            <span>Symbol</span><span>Shares</span><span>Cost basis</span><span>Theme</span><span />
          </div>
          {cfg.holdings.map((h, i) => (
            <div className="et-row" key={i}>
              <input
                className="sym"
                value={h.symbol}
                placeholder="TICKER"
                onChange={(e) => setHolding(i, { symbol: e.target.value.toUpperCase() })}
              />
              <input
                type="number"
                value={h.shares}
                min={0}
                step="any"
                onChange={(e) => setHolding(i, { shares: parseFloat(e.target.value) || 0 })}
              />
              <input
                type="number"
                value={h.cost_basis}
                min={0}
                step="any"
                onChange={(e) => setHolding(i, { cost_basis: parseFloat(e.target.value) || 0 })}
              />
              <select value={h.theme ?? ""} onChange={(e) => setHolding(i, { theme: e.target.value || undefined })}>
                <option value="">— none —</option>
                {themeNames.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
              <button className="icon-btn" title="Remove" onClick={() => delHolding(i)}>✕</button>
            </div>
          ))}
          {cfg.holdings.length === 0 && <div className="empty">No holdings yet — add one.</div>}
        </div>
      </div>

      {/* --------- watchlist --------- */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="editor-head">
          <div className="section-title" style={{ margin: 0 }}>Watchlist ({cfg.watchlist.length})</div>
          <button className="btn ghost" onClick={addWatch}>+ Add symbol</button>
        </div>
        <div className="edit-table">
          <div className="et-row et-row-wl et-head">
            <span>Symbol</span><span>Theme</span><span />
          </div>
          {cfg.watchlist.map((w, i) => (
            <div className="et-row et-row-wl" key={i}>
              <input
                className="sym"
                value={w.symbol}
                placeholder="TICKER"
                onChange={(e) => setWatch(i, { symbol: e.target.value.toUpperCase() })}
              />
              <select value={w.theme ?? ""} onChange={(e) => setWatch(i, { theme: e.target.value || undefined })}>
                <option value="">— none —</option>
                {themeNames.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
              <button className="icon-btn" title="Remove" onClick={() => delWatch(i)}>✕</button>
            </div>
          ))}
          {cfg.watchlist.length === 0 && <div className="empty">Nothing watched yet — add a symbol.</div>}
        </div>
      </div>

      {/* --------- themes --------- */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="editor-head">
          <div className="section-title" style={{ margin: 0 }}>Themes ({themeNames.length})</div>
          <button className="btn ghost" onClick={addTheme}>+ Add theme</button>
        </div>
        <div className="edit-table">
          {themeNames.map((name) => (
            <div className="et-row et-row-theme" key={name}>
              <input
                className="sym"
                value={name}
                onChange={(e) => renameTheme(name, e.target.value)}
              />
              <input
                value={cfg.themes[name]}
                placeholder="Short description"
                onChange={(e) => setThemeDesc(name, e.target.value)}
              />
              <button className="icon-btn" title="Remove" onClick={() => delTheme(name)}>✕</button>
            </div>
          ))}
          {themeNames.length === 0 && <div className="empty">No themes — add one to group your names.</div>}
        </div>
      </div>

      <div className="save-bar">
        <Link href="/" className="btn ghost">Cancel</Link>
        <button className="btn" onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save changes"}
        </button>
      </div>
    </>
  );
}
