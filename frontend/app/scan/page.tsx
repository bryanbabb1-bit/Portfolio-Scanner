"use client";
import { useEffect, useMemo, useState } from "react";
import { api, StockReport } from "../../lib/api";
import { StockCard } from "../../components/StockCard";
import { SortControl, SortKey, sortReports } from "../../components/SortControl";

export default function ScanHub() {
  const [results, setResults] = useState<StockReport[]>([]);
  const [source, setSource] = useState("");
  const [theme, setTheme] = useState<string>("All");
  const [sort, setSort] = useState<SortKey>("change");
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
  const shown = useMemo(() => {
    const filtered = theme === "All" ? results : results.filter((r) => r.theme === theme);
    return sortReports(filtered, sort);
  }, [results, theme, sort]);

  return (
    <>
      <div className="page-head">
        <h1>Scan Hub</h1>
        <p>
          Holdings + watchlist scanned for price action, technical signals, analyst
          ratings and news. Source: <span className={source === "mock" ? "mut" : "pos"}>{source || "…"}</span>
        </p>
      </div>

      <div className="list-head" style={{ alignItems: "flex-start" }}>
        <div className="filter-chips">
          {themes.map((t) => (
            <button key={t} className={theme === t ? "active" : ""} onClick={() => setTheme(t)}>
              {t}
            </button>
          ))}
        </div>
        <SortControl sort={sort} setSort={setSort} />
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
