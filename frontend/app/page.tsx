"use client";
import { useEffect, useState } from "react";
import { api, PortfolioSummary, StockReport } from "../lib/api";
import { StockCard } from "../components/StockCard";
import { money, pct, signClass } from "../components/format";

export default function Dashboard() {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [holdings, setHoldings] = useState<StockReport[]>([]);
  const [watchlist, setWatchlist] = useState<StockReport[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .portfolio()
      .then((d) => {
        setSummary(d.summary);
        setHoldings(d.holdings);
      })
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
    // Watchlist loads independently — a slow/failed watch fetch never blocks holdings.
    api
      .watchlist()
      .then((d) => setWatchlist(d.results))
      .catch(() => setWatchlist([]));
  }, []);

  if (loading) return <div className="loading">Loading portfolio…</div>;
  if (err)
    return (
      <div className="err">
        Could not reach the backend ({err}). Start it with{" "}
        <code>uvicorn app.main:app --reload</code> in <code>backend/</code>.
      </div>
    );
  if (!summary) return null;

  return (
    <>
      <div className="page-head">
        <h1>Portfolio Dashboard</h1>
        <p>
          {summary.positions} positions · data source:{" "}
          <span className={summary.source === "mock" ? "" : "pos"}>{summary.source}</span>
        </p>
      </div>

      <div className="grid grid-stats" style={{ marginBottom: 28 }}>
        <div className="card stat">
          <span className="label">Market Value</span>
          <span className="value">{money(summary.total_market_value)}</span>
        </div>
        <div className="card stat">
          <span className="label">Day Change</span>
          <span className={`value ${signClass(summary.day_change)}`}>{money(summary.day_change)}</span>
          <span className={`sub ${signClass(summary.day_change_pct)}`}>{pct(summary.day_change_pct)}</span>
        </div>
        <div className="card stat">
          <span className="label">Unrealized P/L</span>
          <span className={`value ${signClass(summary.total_unrealized_pl)}`}>
            {money(summary.total_unrealized_pl)}
          </span>
          <span className={`sub ${signClass(summary.total_unrealized_pl_pct)}`}>
            {pct(summary.total_unrealized_pl_pct)}
          </span>
        </div>
        <div className="card stat">
          <span className="label">Cost Basis</span>
          <span className="value">{money(summary.total_cost)}</span>
        </div>
      </div>

      {Object.keys(summary.by_theme).length > 0 && (
        <div style={{ marginBottom: 28 }}>
          <div className="section-title">Allocation by Theme</div>
          <div className="grid grid-stats">
            {Object.entries(summary.by_theme)
              .sort((a, b) => b[1] - a[1])
              .map(([theme, val]) => (
                <div key={theme} className="card stat">
                  <span className="label">{theme}</span>
                  <span className="value" style={{ fontSize: 18 }}>{money(val, 0)}</span>
                  <span className="sub mut">
                    {((val / summary.total_market_value) * 100).toFixed(1)}% of book
                  </span>
                </div>
              ))}
          </div>
        </div>
      )}

      <div className="section-title">Holdings</div>
      <div className="grid grid-cards">
        {holdings.map((r) => (
          <StockCard key={r.symbol} r={r} />
        ))}
      </div>

      {watchlist.length > 0 && (
        <div style={{ marginTop: 32 }}>
          <div className="section-title">
            Watchlist <span className="mut" style={{ textTransform: "none", letterSpacing: 0 }}>· names you're tracking</span>
          </div>
          <div className="grid grid-cards">
            {watchlist.map((r) => (
              <StockCard key={r.symbol} r={r} />
            ))}
          </div>
        </div>
      )}
    </>
  );
}
