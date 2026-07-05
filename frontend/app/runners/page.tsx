"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, RunnerCandidate } from "../../lib/api";
import { ScoreRing } from "../../components/ScoreRing";
import { money, num, pct } from "../../components/format";

const STAGE_META: Record<RunnerCandidate["stage"], { label: string; cls: string }> = {
  coiled: { label: "COILED", cls: "coiled" },
  igniting: { label: "IGNITING", cls: "igniting" },
  extended: { label: "EXTENDED", cls: "extended" },
  cooling: { label: "COOLING", cls: "cooling" },
};

function compact(n?: number | null): string {
  if (n == null) return "—";
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
  return `${n}`;
}

export default function Runners() {
  const [rows, setRows] = useState<RunnerCandidate[]>([]);
  const [universe, setUniverse] = useState(0);
  const [liveMovers, setLiveMovers] = useState(0);
  const [source, setSource] = useState("");
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [extra, setExtra] = useState("");
  const [added, setAdded] = useState<string[]>([]);

  const load = (tickers: string[]) => {
    setLoading(true);
    api
      .runners(tickers)
      .then((d) => {
        setRows(d.results);
        setUniverse(d.universe);
        setLiveMovers(d.live_movers ?? 0);
        setSource(d.source);
      })
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  };
  useEffect(() => {
    load([]);
  }, []);

  function addTicker() {
    const t = extra.trim().toUpperCase();
    if (!t || added.includes(t)) return;
    const next = [...added, t];
    setAdded(next);
    setExtra("");
    load(next);
  }

  const igniting = useMemo(() => rows.filter((r) => r.stage === "igniting").length, [rows]);

  return (
    <>
      <div className="page-head">
        <h1>Runner Radar</h1>
        <p>
          The anatomy of an explosive mover. MGRT ran 1,000%+ on a ~2M-share
          float — a different animal from a large-cap momentum name. This scans
          the <em>right type</em> of stock for that DNA.{" "}
          {liveMovers > 0
            ? `Scanning ${liveMovers} live market movers + watch seeds (${universe} total) — what's actually running now, not a fixed list.`
            : universe > 0 && `${universe} names.`}{" "}
          Source: <span className={source === "mock" ? "mut" : "pos"}>{source || "…"}</span>
        </p>
      </div>

      {/* the education panel — what actually makes these pop */}
      <div className="card runner-anatomy">
        <div className="section-title" style={{ marginBottom: 10 }}>What makes a stock 10x</div>
        <div className="anatomy-grid">
          <div><span className="an-k">Tiny float</span><span className="an-v">The fuel — under 20M tradeable shares. A few million dollars moves it vertically.</span></div>
          <div><span className="an-k">Recent IPO</span><span className="an-v">Under a year public — little overhead supply, insiders locked up, float stays tight.</span></div>
          <div><span className="an-k">Volume explosion</span><span className="an-v">The ignition — 3x+ average volume is real money forcing the imbalance.</span></div>
          <div><span className="an-k">Already breaking out</span><span className="an-v">Near or at 52-week highs on that volume, no overhead resistance left.</span></div>
          <div><span className="an-k">Short interest</span><span className="an-v">Optional accelerant — a heavily-shorted thin float can squeeze parabolic.</span></div>
          <div className="an-warn"><span className="an-k">The other edge</span><span className="an-v">The same thinness that enables a 10x enables a -90% with no bid. Lottery-ticket size, exit set before entry.</span></div>
        </div>
      </div>

      <div className="runner-add">
        <input
          placeholder="Add a ticker you're eyeing (e.g. MGRT)"
          value={extra}
          onChange={(e) => setExtra(e.target.value.toUpperCase())}
          onKeyDown={(e) => e.key === "Enter" && addTicker()}
        />
        <button className="btn ghost" onClick={addTicker} disabled={!extra.trim()}>Add & score</button>
        {igniting > 0 && <span className="mut" style={{ fontSize: 12 }}>{igniting} igniting now</span>}
      </div>

      {loading && <div className="loading">Scanning the runner universe… (structural data, up to ~30s)</div>}
      {err && <div className="err">{err}</div>}

      <div className="grid" style={{ gap: 12 }}>
        {rows.map((r) => {
          const stage = STAGE_META[r.stage];
          return (
            <div key={r.symbol} className={`card runner-card ${r.stage}`}>
              <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
                <ScoreRing score={r.runner_score} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    <Link href={`/stock/${r.symbol}`} className="sc-sym">{r.symbol}</Link>
                    <span className="mut" style={{ fontSize: 13 }}>{r.name}</span>
                    <span className={`stage-badge ${stage.cls}`}>{stage.label}</span>
                    <span className="mut" style={{ fontSize: 13 }}>{money(r.price)}</span>
                    <span className={r.change_pct >= 0 ? "pos" : "neg"} style={{ fontSize: 13, fontWeight: 700 }}>
                      {r.change_pct >= 0 ? "▲" : "▼"} {Math.abs(r.change_pct).toFixed(1)}%
                    </span>
                    {r.recent_ipo && <span className="theme-tag">recent IPO</span>}
                  </div>

                  <div className="runner-stats">
                    <span><span className="rs-l">Float</span> {compact(r.float_shares)}{r.float_pct != null ? ` · ${num(r.float_pct, 0)}%` : ""}</span>
                    <span><span className="rs-l">Mkt cap</span> ${compact(r.market_cap)}</span>
                    <span><span className="rs-l">Short</span> {r.short_pct_float != null ? `${(r.short_pct_float * 100).toFixed(0)}%` : "—"}</span>
                    <span><span className="rs-l">Vol</span> {r.volume_ratio != null ? `${num(r.volume_ratio, 1)}x` : "—"}</span>
                    <span><span className="rs-l">5d</span> <span className={(r.ret_5d_pct ?? 0) >= 0 ? "pos" : "neg"}>{pct(r.ret_5d_pct, 0)}</span></span>
                    <span><span className="rs-l">20d</span> <span className={(r.ret_20d_pct ?? 0) >= 0 ? "pos" : "neg"}>{pct(r.ret_20d_pct, 0)}</span></span>
                    <span><span className="rs-l">RSI</span> {num(r.rsi, 0)}</span>
                  </div>

                  {r.reasons.length > 0 && (
                    <ul className="bullets insight" style={{ marginTop: 8 }}>
                      {r.reasons.map((t, i) => <li key={i}>{t}</li>)}
                    </ul>
                  )}
                  {r.caution && <div className="runner-caution">{r.caution}</div>}
                </div>
              </div>
            </div>
          );
        })}
        {!loading && !rows.length && <div className="empty">No runner setups scoring right now.</div>}
      </div>
    </>
  );
}
