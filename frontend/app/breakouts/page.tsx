"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, BreakoutCandidate } from "../../lib/api";
import { Signals } from "../../components/Signals";
import { ScoreRing } from "../../components/ScoreRing";
import { AdvisorPanel } from "../../components/AdvisorPanel";
import { money, num, pct } from "../../components/format";

export default function BreakoutRadar() {
  const [results, setResults] = useState<BreakoutCandidate[]>([]);
  const [source, setSource] = useState("");
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    api
      .breakouts(0, 20)
      .then((d) => {
        setResults(d.results);
        setSource(d.source);
      })
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <>
      <div className="page-head">
        <h1>
          <span className="pulse" style={{ marginRight: 10 }} />
          Breakout Radar
        </h1>
        <p>
          Live pulse on names poised to break out, ranked by a composite readiness
          score (momentum · proximity to highs · volume · trend · squeeze). Source:{" "}
          {source || "…"}
        </p>
      </div>

      {loading && <div className="loading">Scoring breakout candidates…</div>}
      {err && <div className="err">{err}</div>}

      <div className="grid" style={{ gap: 14 }}>
        {results.map((c) => (
          <div key={c.symbol} className="card breakout-card">
            <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
              <ScoreRing score={c.score} />
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <Link href={`/stock/${c.symbol}`} className="sc-sym">
                    {c.symbol}
                  </Link>
                  {c.theme && <span className="theme-tag">{c.theme}</span>}
                  <span className="mut" style={{ fontSize: 13 }}>{money(c.price)}</span>
                  <span className="mut" style={{ fontSize: 12 }}>
                    RSI {num(c.indicators.rsi, 0)} · {pct(c.indicators.pct_from_52w_high, 1)} vs 52w hi
                  </span>
                </div>
                {c.thesis_points?.length ? (
                  <ul className="bullets insight" style={{ marginTop: 8 }}>
                    {c.thesis_points.map((t, i) => (
                      <li key={i}>{t}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="mut" style={{ fontSize: 13, marginTop: 6 }}>{c.thesis}</p>
                )}
                <div style={{ marginTop: 8 }}>
                  <Signals signals={c.signals} max={5} />
                </div>
              </div>
              <button
                className="btn"
                onClick={() => setOpen(open === c.symbol ? null : c.symbol)}
              >
                {open === c.symbol ? "Hide case" : "AI bull case"}
              </button>
            </div>
            {open === c.symbol && (
              <div style={{ marginTop: 14 }}>
                <AdvisorPanel symbol={c.symbol} mode="breakout" />
              </div>
            )}
          </div>
        ))}
      </div>
    </>
  );
}
