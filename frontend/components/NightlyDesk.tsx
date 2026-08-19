"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { API_BASE } from "../lib/api";
import { ageFrom, isStale } from "./format";

/* Last night's desk, on the homepage.
 *
 * The debates were already being run and cached and there was nowhere to see
 * them, which is the same failure the pins had: working perfectly and invisible.
 *
 * Before the desk sits it shows tonight's QUEUE instead of an empty panel —
 * "nothing here yet" and "four names lined up for tonight, and here is why"
 * are different states and only one of them is worth screen space. */

interface Ran {
  symbol: string;
  score: number;
  why: string[];
  verdict: string | null;
  action?: string | null;
  /** The ruling in one sentence — the reason to read further, or not. */
  headline?: string | null;
  /** When the desk actually sat, so a stale ruling can't read as current. */
  ts?: number | null;
}

interface Queued {
  symbol: string;
  score: number;
  why: string[];
}

/** A screen candidate the desk judged — a stranger, not a holding. */
interface Screened extends Ran {
  price?: number;
  change_pct?: number;
  rvol?: number;
  drawdown_pct?: number | null;
  higher_low?: boolean | null;
  days_below_20d?: number | null;
  run_20d_pct?: number | null;
  reclaim_score?: number | null;
}

export interface Nightly {
  last: { date?: string; ran?: Ran[]; screened?: Screened[]; note?: string };
  queue: Queued[];
  max_per_night: number;
}

function verdictClass(v: string | null) {
  const s = (v || "").toUpperCase();
  if (s.includes("APPROVE") || s.includes("BUY") || s.includes("ADD")) return "ok";
  if (s.includes("REJECT") || s.includes("SELL") || s.includes("TRIM")) return "no";
  return "";
}

/* The desk lives on a tab now, but the tab needs a count before you open it —
   so the fetch is a hook the page owns and the panel is handed the result. */
export function useNightly() {
  const [n, setN] = useState<Nightly | null>(null);

  useEffect(() => {
    // Rulings first — that request is a file read. Only if there is nothing to
    // show do we pay for the queue, which needs a whole portfolio scan.
    fetch(`${API_BASE}/api/debate/nightly`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!d || d.queue === undefined) return;
        setN(d);
        if (!(d.last?.ran ?? []).length) {
          fetch(`${API_BASE}/api/debate/nightly?include_queue=true`, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((full) => full && full.queue !== undefined && setN(full))
            .catch(() => {});
        }
      })
      .catch(() => {});
  }, []);

  return n;
}

/** How many things are actually waiting on this tab — rulings plus screens. */
export function nightlyCount(n: Nightly | null): number {
  if (!n) return 0;
  return (n.last?.ran ?? []).length + (n.last?.screened ?? []).length;
}

export function NightlyDesk({ n }: { n: Nightly | null }) {
  if (!n) return null;
  const ran = n.last?.ran ?? [];
  const screened = n.last?.screened ?? [];
  const queue = (n.queue ?? []).slice(0, n.max_per_night);
  if (!ran.length && !screened.length && !queue.length) return null;

  return (
    <>
      <div className="mfx-label">
        The desk {ran.length ? `· convened ${n.last.date}` : "· sitting tonight"}
      </div>
      <div className="card nd">
        {ran.length > 0 ? (
          <>
            <p className="nd-lead">
              The desk sat on {ran.length} name{ran.length > 1 ? "s" : ""} overnight.
              Full transcripts are ready — nothing to run.
            </p>
            <div className="nd-list">
              {ran.map((r) => (
                <Link key={r.symbol} href={`/debate?symbol=${r.symbol}`} className="nd-row">
                  <span className="nd-sym">{r.symbol}</span>
                  <span className={`nd-verdict ${verdictClass(r.action || r.verdict)}`}>
                    {r.action || r.verdict || "ruled"}
                  </span>
                  <span className="nd-why">
                    {r.headline && <span className="nd-head">{r.headline}</span>}
                    <span className="nd-picked">
                      {r.ts ? (
                        <span className={isStale(r.ts) ? "nd-stale" : ""}>
                          convened {ageFrom(r.ts)}
                          {isStale(r.ts) ? " · may be dated" : ""} ·{" "}
                        </span>
                      ) : null}
                      picked: {r.why.join(" · ")}
                    </span>
                  </span>
                  <span className="nd-go">Read the debate →</span>
                </Link>
              ))}
            </div>
          </>
        ) : (
          <>
            <p className="nd-lead">
              Tonight the desk sits on {queue.length} name
              {queue.length > 1 ? "s" : ""} — picked by what actually changed
              today. Rulings will be here in the morning.
            </p>
            <div className="nd-list">
              {queue.map((c) => (
                <div key={c.symbol} className="nd-row queued">
                  <span className="nd-sym">{c.symbol}</span>
                  <span className="nd-verdict pending">queued</span>
                  <span className="nd-why">{c.why.join(" · ")}</span>
                </div>
              ))}
            </div>
          </>
        )}
        {n.last?.note && <p className="mut nd-note">{n.last.note}</p>}
      </div>

      {screened.length > 0 && (
        <>
          <div className="mfx-label">Fresh from the screen · judged</div>
          <div className="card nd">
            <p className="nd-lead">
              Beaten-down names that have stopped falling and just turned —
              found across all 5,900 US listings, nothing you own. The desk
              argued each one, so you are reading a verdict rather than a
              ticker list.
            </p>
            <div className="nd-list">
              {screened.map((r) => (
                <Link key={r.symbol} href={`/debate?symbol=${r.symbol}`} className="nd-row">
                  <span className="nd-sym">{r.symbol}</span>
                  <span className={`nd-verdict ${verdictClass(r.action || r.verdict)}`}>
                    {r.action || r.verdict || "ruled"}
                  </span>
                  <span className="nd-why">
                    {r.headline && <span className="nd-head">{r.headline}</span>}
                    <span className="nd-picked">
                      {r.price != null ? `$${r.price} · ` : ""}
                      {r.drawdown_pct != null ? `${r.drawdown_pct}% off high · ` : ""}
                      {r.higher_low ? "higher low · " : ""}
                      {r.days_below_20d != null ? `${r.days_below_20d}d below 20d · ` : ""}
                      {r.rvol != null ? `${r.rvol}x volume` : ""}
                    </span>
                  </span>
                  <span className="nd-go">Read the debate →</span>
                </Link>
              ))}
            </div>
          </div>
        </>
      )}
    </>
  );
}
