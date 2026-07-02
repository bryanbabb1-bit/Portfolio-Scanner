"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, BreakoutCandidate } from "../../lib/api";
import { Signals } from "../../components/Signals";
import { ScoreRing } from "../../components/ScoreRing";
import { AdvisorPanel } from "../../components/AdvisorPanel";
import { money, num, pct } from "../../components/format";

export default function Discover() {
  const [results, setResults] = useState<BreakoutCandidate[]>([]);
  const [universe, setUniverse] = useState(0);
  const [source, setSource] = useState("");
  const [theme, setTheme] = useState<string>("All");
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [watched, setWatched] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState<string | null>(null);

  useEffect(() => {
    api
      .discover(0, 40)
      .then((d) => {
        setResults(d.results);
        setUniverse(d.universe);
        setSource(d.source);
      })
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }, []);

  const themes = useMemo(
    () => ["All", ...Array.from(new Set(results.map((r) => r.theme).filter(Boolean) as string[]))],
    [results]
  );
  const shown = theme === "All" ? results : results.filter((r) => r.theme === theme);

  async function watch(c: BreakoutCandidate) {
    setSaving(c.symbol);
    try {
      const cfg = await api.config();
      if (!cfg.watchlist.some((w) => w.symbol.toUpperCase() === c.symbol)) {
        cfg.watchlist.push({ symbol: c.symbol, theme: c.theme });
        await api.saveConfig(cfg);
      }
      setWatched((prev) => new Set(prev).add(c.symbol));
    } catch (e: any) {
      setErr(e.message || "Could not save watchlist");
    } finally {
      setSaving(null);
    }
  }

  return (
    <>
      <div className="page-head">
        <h1>Discovery</h1>
        <p>
          Names you <em>don't</em> own from a curated universe adjacent to your themes,
          ranked by the same breakout-readiness score as the radar.
          {universe > 0 && ` Scanned ${universe} tickers.`} Source:{" "}
          <span className={source === "mock" ? "mut" : "pos"}>{source || "…"}</span>
        </p>
      </div>

      {themes.length > 2 && (
        <div className="filter-chips" style={{ marginBottom: 18 }}>
          {themes.map((t) => (
            <button key={t} className={theme === t ? "active" : ""} onClick={() => setTheme(t)}>
              {t}
            </button>
          ))}
        </div>
      )}

      {loading && (
        <div className="loading">
          Sweeping the market for setups… (first scan warms ~70 tickers, up to ~30s)
        </div>
      )}
      {err && <div className="err">{err}</div>}

      <div className="grid" style={{ gap: 14 }}>
        {shown.map((c) => (
          <div key={c.symbol} className="card breakout-card">
            <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
              <ScoreRing score={c.score} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                  <Link href={`/stock/${c.symbol}`} className="sc-sym">
                    {c.symbol}
                  </Link>
                  <span className="mut" style={{ fontSize: 13 }}>{c.quote.name}</span>
                  {c.theme && <span className="theme-tag">{c.theme}</span>}
                  <span className="mut" style={{ fontSize: 13 }}>{money(c.price)}</span>
                  <span className="mut" style={{ fontSize: 12 }}>
                    RSI {num(c.indicators.rsi, 0)} · {pct(c.indicators.pct_from_52w_high, 1)} vs 52w hi
                  </span>
                </div>
                <p className="mut" style={{ fontSize: 13, marginTop: 6 }}>{c.thesis}</p>
                <div style={{ marginTop: 8 }}>
                  <Signals signals={c.signals} max={5} />
                </div>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <button
                  className="btn ghost"
                  disabled={watched.has(c.symbol) || saving === c.symbol}
                  onClick={() => watch(c)}
                >
                  {watched.has(c.symbol) ? "✓ Watching" : saving === c.symbol ? "Saving…" : "+ Watch"}
                </button>
                <button
                  className="btn"
                  onClick={() => setOpen(open === c.symbol ? null : c.symbol)}
                >
                  {open === c.symbol ? "Hide case" : "AI bull case"}
                </button>
              </div>
            </div>
            {open === c.symbol && (
              <div style={{ marginTop: 14 }}>
                <AdvisorPanel symbol={c.symbol} mode="breakout" />
              </div>
            )}
          </div>
        ))}
        {!loading && !shown.length && (
          <div className="empty">No candidates above the bar right now — the universe is quiet.</div>
        )}
      </div>
    </>
  );
}
