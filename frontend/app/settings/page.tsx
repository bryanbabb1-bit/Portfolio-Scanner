"use client";
import { useEffect, useMemo, useState } from "react";
import { SleeveSettings } from "../../components/SleeveSettings";
import Link from "next/link";
import { api, Holding, PortfolioConfig, WatchItem } from "../../lib/api";
import { money } from "../../components/format";
import { Preferences } from "../../components/Preferences";

type Quote = { price: number | null; source: string };

// Let a numeric field sit empty while you retype it instead of snapping to 0.
// Empty is held as NaN in state (shown blank) and coerced to 0 on save.
const numDisplay = (x: number | null | undefined) =>
  x == null || Number.isNaN(x) ? "" : x;
const parseNum = (raw: string) => (raw === "" ? NaN : parseFloat(raw));
const num0 = (x: number | null | undefined) => (x == null || Number.isNaN(x) ? 0 : x);

const BLANK: PortfolioConfig = {
  owner: "You",
  advisor_persona: "senior financial advisor at Charles Schwab",
  cash: 0,
  core_convictions: [],
  themes: {},
  holdings: [],
  watchlist: [],
};

export default function Settings() {
  const [cfg, setCfg] = useState<PortfolioConfig | null>(null);
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});
  const [convInput, setConvInput] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api
      .config()
      .then((c) => setCfg({ ...BLANK, ...c }))
      .catch((e) => setErr(e.message));
  }, []);

  // Live prices for the holdings, so the "$ value" column and total reflect
  // real market data as you edit. Keyed on the sorted symbol set, debounced so
  // typing a ticker doesn't fire a request per keystroke.
  const heldSymbols = (cfg?.holdings ?? [])
    .map((h) => h.symbol.trim().toUpperCase())
    .filter(Boolean);
  const symbolKey = Array.from(new Set(heldSymbols)).sort().join(",");
  useEffect(() => {
    if (!symbolKey) return;
    const syms = symbolKey.split(",");
    const t = setTimeout(() => {
      api
        .quotes(syms)
        .then((d) => setQuotes((prev) => ({ ...prev, ...d.quotes })))
        .catch(() => {});
    }, 500);
    return () => clearTimeout(t);
  }, [symbolKey]);

  const bookValue = useMemo(
    () =>
      (cfg?.holdings ?? []).reduce((sum, h) => {
        const p = quotes[h.symbol.trim().toUpperCase()]?.price;
        return sum + (p != null ? p * (h.shares || 0) : 0);
      }, 0),
    [cfg?.holdings, quotes]
  );

  if (err && !cfg) return <div className="err">Could not load config ({err}).</div>;
  if (!cfg) return <div className="loading">Loading config…</div>;

  const themeNames = Object.keys(cfg.themes);

  // -------- holdings --------
  const setHolding = (i: number, patch: Partial<Holding>) =>
    setCfg({ ...cfg, holdings: cfg.holdings.map((h, k) => (k === i ? { ...h, ...patch } : h)) });
  const addHolding = () =>
    setCfg({ ...cfg, holdings: [...cfg.holdings, { symbol: "", shares: 0, cost_basis: 0 }] });
  const delHolding = (i: number) =>
    setCfg({ ...cfg, holdings: cfg.holdings.filter((_, k) => k !== i) });

  // -------- watchlist --------
  const setWatch = (i: number, patch: Partial<WatchItem>) =>
    setCfg({ ...cfg, watchlist: cfg.watchlist.map((w, k) => (k === i ? { ...w, ...patch } : w)) });
  const addWatch = () =>
    setCfg({ ...cfg, watchlist: [...cfg.watchlist, { symbol: "" }] });
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

  // -------- core convictions (checkbox per symbol) --------
  const core = (cfg.core_convictions ?? []).map((s) => s.toUpperCase());
  const isCore = (s: string) => core.includes(s.trim().toUpperCase());
  const toggleCore = (s: string) => {
    const S = s.trim().toUpperCase();
    if (!S) return;
    setCfg({
      ...cfg,
      core_convictions: isCore(S) ? core.filter((x) => x !== S) : [...core, S],
    });
  };
  // Add a conviction you don't own: adds it to the watchlist AND marks it core.
  const addConviction = () => {
    const S = convInput.trim().toUpperCase();
    if (!S) return;
    const owned = cfg.holdings.some((h) => h.symbol.trim().toUpperCase() === S);
    const watched = cfg.watchlist.some((w) => w.symbol.trim().toUpperCase() === S);
    setCfg({
      ...cfg,
      watchlist: owned || watched ? cfg.watchlist : [...cfg.watchlist, { symbol: S }],
      core_convictions: isCore(S) ? core : [...core, S],
    });
    setConvInput("");
  };

  const save = async () => {
    setSaving(true);
    setErr(null);
    setMsg(null);
    // Drop fully-empty rows so a blank trailing row doesn't fail validation.
    const clean: PortfolioConfig = {
      ...cfg,
      cash: num0(cfg.cash),
      holdings: cfg.holdings
        .filter((h) => h.symbol.trim())
        .map((h) => ({ ...h, shares: num0(h.shares), cost_basis: num0(h.cost_basis) })),
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
        <p>
          Configure your holdings, watchlist and themes. Themes are assigned
          automatically by ticker — the Theme column is only an override.
        </p>
      </div>

      {msg && <div className="ok-banner">{msg}</div>}
      {err && <div className="err" style={{ marginBottom: 16 }}>{err}</div>}

      {/* --------- what he has told the advisor, made visible + reversible --------- */}
      <div style={{ marginBottom: 20 }}>
        <Preferences />
      </div>

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
          <label>
            <span>Cash / buying power ($)</span>
            <input
              type="number"
              min={0}
              step="any"
              value={numDisplay(cfg.cash)}
              placeholder="0"
              title="Uninvested cash — counts toward your total and allocation, never quoted or scanned"
              onChange={(e) => setCfg({ ...cfg, cash: parseNum(e.target.value) })}
            />
          </label>
          <label className="cfg-toggle">
            <input
              type="checkbox"
              checked={cfg.signals_owned_only ?? true}
              onChange={(e) => setCfg({ ...cfg, signals_owned_only: e.target.checked })}
            />
            <span>
              Only signal on names I own or watch
              <span className="mut" style={{ display: "block", fontSize: 12, textTransform: "none", letterSpacing: 0, fontWeight: 400 }}>
                No buy/sell alerts for stocks outside your book. The discovery
                universe is market-wide now, so scanning it for alerts surfaces
                names with no place in the portfolio. Discovery and the
                advisor&apos;s scouting still see the whole market — this only
                gates the core book&apos;s signal engine. Runners belong to the
                trading sleeve below and are not affected.
              </span>
            </span>
          </label>

          <label className="cfg-toggle">
            <input
              type="checkbox"
              checked={cfg.quiet_unowned_low_cash ?? true}
              onChange={(e) => setCfg({ ...cfg, quiet_unowned_low_cash: e.target.checked })}
            />
            <span>
              Quiet mode when low on cash
              <span className="mut" style={{ display: "block", fontSize: 12, textTransform: "none", letterSpacing: 0, fontWeight: 400 }}>
                When dry powder runs out, stop alerting on runners and buy signals for stocks you don&apos;t own — only watch names you hold. Saves advisor usage on things you can&apos;t act on.
              </span>
            </span>
          </label>
        </div>
      </div>

      <SleeveSettings />

      {/* --------- holdings --------- */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="editor-head">
          <div className="section-title" style={{ margin: 0 }}>Holdings ({cfg.holdings.length})</div>
          <button className="btn ghost" onClick={addHolding}>+ Add holding</button>
        </div>
        <div className="edit-table">
          <div className="et-row et-row-h et-head">
            <span>Symbol</span><span>Shares</span><span>Cost basis</span><span>Price</span><span>$ Value</span><span>Theme</span><span />
          </div>
          {cfg.holdings.map((h, i) => {
            const q = quotes[h.symbol.trim().toUpperCase()];
            const price = q?.price ?? null;
            const value = price != null ? price * (h.shares || 0) : null;
            const share = value != null && bookValue > 0 ? value / bookValue : 0;
            // Flag a row that alone is >60% of the book — the classic fat-finger.
            const dominant = share > 0.6;
            return (
              <div className={`et-row et-row-h${dominant ? " et-flag" : ""}`} key={i}>
                <input
                  className="sym"
                  value={h.symbol}
                  placeholder="TICKER"
                  onChange={(e) => setHolding(i, { symbol: e.target.value.toUpperCase() })}
                />
                <input
                  type="number"
                  value={numDisplay(h.shares)}
                  min={0}
                  step="any"
                  onChange={(e) => setHolding(i, { shares: parseNum(e.target.value) })}
                />
                <input
                  type="number"
                  value={numDisplay(h.cost_basis)}
                  min={0}
                  step="any"
                  onChange={(e) => setHolding(i, { cost_basis: parseNum(e.target.value) })}
                />
                <span className="et-cell mut" title={q?.source === "mock" ? "mock data" : "live"}>
                  {price != null ? money(price) : "—"}
                </span>
                <span className={`et-cell val${dominant ? " neg" : ""}`} title={value != null ? `${(share * 100).toFixed(1)}% of book` : ""}>
                  {value != null ? money(value, 0) : "—"}
                </span>
                <select
                  value={h.theme ?? ""}
                  title="Themes are assigned automatically by ticker — pick one only to override"
                  onChange={(e) => setHolding(i, { theme: e.target.value || undefined })}
                >
                  <option value="">Auto</option>
                  {themeNames.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
                <button className="icon-btn" title="Remove" onClick={() => delHolding(i)}>✕</button>
              </div>
            );
          })}
          {cfg.holdings.length === 0 && <div className="empty">No holdings yet — add one.</div>}
          {(cfg.holdings.length > 0 || (cfg.cash ?? 0) > 0) && (
            <div className="et-total">
              <span>
                Book value (live){(cfg.cash ?? 0) > 0 ? ` + ${money(cfg.cash ?? 0, 0)} cash` : ""}
              </span>
              <strong>{money(bookValue + (cfg.cash ?? 0), 0)}</strong>
            </div>
          )}
        </div>
      </div>

      {/* --------- core convictions --------- */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="section-title">Core Convictions</div>
        <p className="mut" style={{ fontSize: 12.5, marginTop: -4, marginBottom: 12 }}>
          Tap to mark long-term convictions. The advisor accumulates these on weakness and
          will <strong>never</strong> tell you to sell them at a loss on a technical break —
          only if the business thesis actually breaks.
        </p>
        {[...heldSymbols, ...cfg.watchlist.map((w) => w.symbol.trim().toUpperCase())].filter(
          (s, i, a) => s && a.indexOf(s) === i
        ).length === 0 ? (
          <div className="empty">Add holdings or watchlist names first, then mark your convictions.</div>
        ) : (
          <div className="conv-chips">
            {Array.from(
              new Set([
                ...heldSymbols,
                ...cfg.watchlist.map((w) => w.symbol.trim().toUpperCase()).filter(Boolean),
              ])
            ).map((s) => {
              const held = heldSymbols.includes(s);
              return (
                <button
                  key={s}
                  type="button"
                  className={`conv-chip ${isCore(s) ? "on" : ""}`}
                  onClick={() => toggleCore(s)}
                  title={held ? "holding" : "watchlist"}
                >
                  <span className="tick">{isCore(s) ? "✓" : ""}</span>
                  {s}
                  {!held && <span className="conv-tag">watch</span>}
                </button>
              );
            })}
          </div>
        )}
        <div className="chat-input" style={{ marginTop: 14, maxWidth: 420 }}>
          <input
            value={convInput}
            placeholder="Add a conviction you don't own — e.g. GOOGL"
            onChange={(e) => setConvInput(e.target.value.toUpperCase())}
            onKeyDown={(e) => e.key === "Enter" && addConviction()}
          />
          <button className="btn" onClick={addConviction} disabled={!convInput.trim()}>
            Add
          </button>
        </div>
        <p className="mut" style={{ fontSize: 11, marginTop: 6 }}>
          A name you don't own gets added to your watchlist and marked a conviction.
        </p>
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
              <select
                value={w.theme ?? ""}
                title="Themes are assigned automatically by ticker — pick one only to override"
                onChange={(e) => setWatch(i, { theme: e.target.value || undefined })}
              >
                <option value="">Auto</option>
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
