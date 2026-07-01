"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, PortfolioNewsItem } from "../../lib/api";

function timeAgo(iso?: string): string {
  if (!iso) return "";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  const mins = Math.max(0, Math.round((Date.now() - t) / 60000));
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  return days < 8 ? `${days}d ago` : new Date(t).toLocaleDateString();
}

export default function NewsFeed() {
  const [items, setItems] = useState<PortfolioNewsItem[]>([]);
  const [source, setSource] = useState("");
  const [filter, setFilter] = useState<string>("All");
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api
      .news(60)
      .then((d) => {
        setItems(d.results);
        setSource(d.source);
      })
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }, []);

  const symbols = useMemo(
    () => ["All", ...Array.from(new Set(items.flatMap((n) => n.symbols))).sort()],
    [items]
  );
  const shown = filter === "All" ? items : items.filter((n) => n.symbols.includes(filter));

  return (
    <>
      <div className="page-head">
        <h1>News Wire</h1>
        <p>
          Every recent headline across your holdings and watchlist, deduped and
          tagged. Source: <span className={source === "mock" ? "mut" : "pos"}>{source || "…"}</span>
        </p>
      </div>

      {symbols.length > 2 && (
        <div className="filter-chips" style={{ marginBottom: 18 }}>
          {symbols.map((s) => (
            <button key={s} className={filter === s ? "active" : ""} onClick={() => setFilter(s)}>
              {s}
            </button>
          ))}
        </div>
      )}

      {loading && <div className="loading">Pulling the wire…</div>}
      {err && <div className="err">{err}</div>}

      <div className="wire">
        {shown.map((n, i) => (
          <div key={`${n.title}-${i}`} className="wire-item card">
            <div className="wire-tags">
              {n.symbols.map((s) => (
                <Link key={s} href={`/stock/${s}`} className="theme-tag">
                  {s}
                </Link>
              ))}
              <span className="mut" style={{ fontSize: 11, marginLeft: "auto" }}>
                {n.publisher}
                {timeAgo(n.published) && ` · ${timeAgo(n.published)}`}
              </span>
            </div>
            {n.link ? (
              <a href={n.link} target="_blank" rel="noreferrer" className="wire-title">
                {n.title}
              </a>
            ) : (
              <span className="wire-title">{n.title}</span>
            )}
          </div>
        ))}
        {!loading && !shown.length && <div className="empty">No headlines right now.</div>}
      </div>
    </>
  );
}
