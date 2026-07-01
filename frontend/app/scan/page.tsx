"use client";
import { useEffect, useState } from "react";
import { api, StockReport } from "../../lib/api";
import { StockCard } from "../../components/StockCard";

export default function ScanHub() {
  const [results, setResults] = useState<StockReport[]>([]);
  const [source, setSource] = useState("");
  const [theme, setTheme] = useState<string>("All");
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api
      .scan(true)
      .then((d) => {
        setResults(d.results);
        setSource(d.source);
      })
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }, []);

  const themes = ["All", ...Array.from(new Set(results.map((r) => r.theme).filter(Boolean) as string[]))];
  const shown = theme === "All" ? results : results.filter((r) => r.theme === theme);

  return (
    <>
      <div className="page-head">
        <h1>Scan Hub</h1>
        <p>
          Holdings + watchlist scanned for price action, technical signals, analyst
          ratings and news. Sorted by bullish tilt. Source: {source || "…"}
        </p>
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 20 }}>
        {themes.map((t) => (
          <button
            key={t}
            className={`btn ${theme === t ? "" : "ghost"}`}
            onClick={() => setTheme(t)}
          >
            {t}
          </button>
        ))}
      </div>

      {loading && <div className="loading">Scanning universe…</div>}
      {err && <div className="err">{err}</div>}
      <div className="grid grid-cards">
        {shown.map((r) => (
          <StockCard key={r.symbol} r={r} />
        ))}
      </div>
    </>
  );
}
