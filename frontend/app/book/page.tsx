"use client";
import { useEffect, useState } from "react";
import { API_BASE } from "../../lib/api";
import { DisplayHead } from "../../components/blueprint/DisplayHead";
import "./book.css";

/* The live thesis book. One view, held aggressively, scored in public.
 *
 * The falsifiers are on the page next to the P/L on purpose. A book you only
 * ever look at through its return is a book you will talk yourself into
 * keeping. */

interface Position {
  symbol: string;
  shares: number;
  entry: number;
  price: number;
  value: number;
  pl: number;
  pl_pct: number;
  conviction: string;
  why: string;
  stop?: number;
  trimmed?: boolean;
}

interface Book {
  thesis: {
    name: string;
    one_liner: string;
    argument: string[];
    falsifiers: string[];
    kill_switch: string;
    honest_odds: string;
  };
  started: string;
  cash: number;
  equity: number;
  realized: number;
  return_pct: number;
  goal: number;
  progress_pct: number;
  multiple_needed: number | null;
  positions: Position[];
  closed: Position[];
  log: { ts: string; action: string; symbol: string; shares: number; price: number; why: string }[];
  pending?: { symbol: string; dollars: number; conviction: string; why: string }[];
}

const money = (v: number) => `${v < 0 ? "-" : ""}$${Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;

export default function BookPage() {
  const [b, setB] = useState<Book | null>(null);
  const [pending, setPending] = useState<Book["pending"]>([]);
  const [err, setErr] = useState<string | null>(null);

  const load = () => {
    fetch(`${API_BASE}/api/book`, { cache: "no-store" })
      .then(async (r) => {
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
        return r.json();
      })
      .then((d) => {
        // A 404 body parses as valid JSON, so "did it parse" is not the same
        // question as "is this a book". Checking the shape is what stops a
        // dead endpoint from white-screening the page.
        if (!d || !d.thesis) throw new Error("the book endpoint returned no book");
        setB(d);
        setPending(d.pending || []);
        setErr(null);
      })
      .catch((e) => setErr(e?.message || String(e)));
  };

  useEffect(() => {
    load();
    // It trades on the heartbeat, so the page should not go stale while open.
    const id = setInterval(load, 60_000);
    return () => clearInterval(id);
  }, []);

  if (err)
    return (
      <>
        <DisplayHead line1="The" line2="Book" tone="hot" />
        <div className="err">Could not load the book: {err}</div>
      </>
    );
  if (!b) return <p className="loading">Loading the book…</p>;

  const up = b.return_pct >= 0;
  // Every list below is optional in the payload. Defaulting here rather than at
  // each use means a partial response degrades the page instead of blanking it.
  const positions = b.positions ?? [];
  const log = b.log ?? [];
  const falsifiers = b.thesis?.falsifiers ?? [];
  const argument = b.thesis?.argument ?? [];

  return (
    <>
      <DisplayHead line1="The" line2="Book" tone="hot" />
      <p className="dh-sub">
        {b.thesis?.name} · opened {b.started} · $1,000 start · equities only
      </p>

      <div className="bk-top">
        <div className="bk-equity">
          <div className="bk-k">Equity</div>
          <div className={`bk-v ${up ? "up" : "down"}`}>{money(b.equity)}</div>
          <div className={`bk-delta ${up ? "up" : "down"}`}>
            {up ? "+" : ""}{b.return_pct}% since open
          </div>
        </div>
        <div className="bk-stats">
          {[
            ["Cash", money(b.cash)],
            ["Realized", money(b.realized)],
            ["Goal", money(b.goal)],
            ["Still needed", b.multiple_needed ? `${b.multiple_needed}x` : "—"],
          ].map(([k, v]) => (
            <div className="bk-stat" key={k}>
              <div className="bk-k">{k}</div>
              <div className="bk-sv">{v}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="bk-progress" title={`${b.progress_pct}% of the way to $100k`}>
        <div className="bk-bar" style={{ width: `${Math.min(100, Math.max(0.4, b.progress_pct))}%` }} />
        <span className="bk-bar-label">{b.progress_pct}% of goal</span>
      </div>

      {pending && pending.length > 0 && (
        <>
          <div className="mfx-label">Queued for the next open</div>
          <div className="card">
            {pending.map((o) => (
              <div className="bk-row" key={o.symbol}>
                <span className="bk-sym">{o.symbol}</span>
                <span className="bk-conv">{o.conviction}</span>
                <span className="bk-why">{o.why}</span>
                <span className="bk-num">{money(o.dollars)}</span>
              </div>
            ))}
            <p className="mut bk-note">
              These fill at the session open on the watchdog heartbeat — not at a
              price already on the screen.
            </p>
          </div>
        </>
      )}

      {positions.length > 0 && (
        <>
          <div className="mfx-label">Open positions</div>
          <div className="card bk-scroll">
            <table className="bk-table">
              <thead>
                <tr>
                  <th>Symbol</th><th>Role</th><th>Shares</th><th>Entry</th>
                  <th>Price</th><th>Stop</th><th>Value</th><th>P/L</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p) => (
                  <tr key={p.symbol} className={p.pl >= 0 ? "up" : "down"}>
                    <td className="bk-sym">{p.symbol}</td>
                    <td className="bk-conv">{p.conviction}</td>
                    <td>{p.shares.toFixed(3)}</td>
                    <td>{p.entry.toFixed(2)}</td>
                    <td>{p.price.toFixed(2)}</td>
                    <td className={p.trimmed ? "bk-trail" : ""}>
                      {p.stop ? p.stop.toFixed(2) : "—"}
                    </td>
                    <td>{money(p.value)}</td>
                    <td className={p.pl >= 0 ? "bk-good" : "bk-bad"}>
                      {money(p.pl)} ({p.pl_pct >= 0 ? "+" : ""}{p.pl_pct}%)
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <div className="mfx-label">The thesis</div>
      <div className="card bk-thesis">
        <p className="bk-one">{b.thesis?.one_liner}</p>
        <ul>{argument.map((a) => <li key={a}>{a}</li>)}</ul>
      </div>

      {/* Next to the P/L on purpose. */}
      <div className="mfx-label">What would prove me wrong</div>
      <div className="card bk-falsify">
        <ul>{falsifiers.map((f) => <li key={f}>{f}</li>)}</ul>
        <p className="bk-kill"><b>Kill switch.</b> {b.thesis?.kill_switch}</p>
        <p className="bk-odds"><b>Honest odds.</b> {b.thesis?.honest_odds}</p>
      </div>

      {log.length > 0 && (
        <>
          <div className="mfx-label">Every action taken</div>
          <div className="card bk-scroll">
            <table className="bk-table">
              <thead>
                <tr><th>When</th><th>Action</th><th>Symbol</th><th>Shares</th><th>Price</th><th>Why</th></tr>
              </thead>
              <tbody>
                {[...log].reverse().map((l, i) => (
                  <tr key={i} className={l.action === "buy" ? "up" : "down"}>
                    <td>{l.ts.slice(5, 16)}</td>
                    <td className="bk-conv">{l.action}</td>
                    <td className="bk-sym">{l.symbol}</td>
                    <td>{l.shares?.toFixed(3)}</td>
                    <td>{l.price?.toFixed(2)}</td>
                    <td className="bk-why">{l.why}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}
