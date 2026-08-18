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
  float_shares?: number | null;
  float_turnover?: number | null;
}

interface Nightly {
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

export function NightlyDesk() {
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
              Low-float momentum names the screen surfaced overnight — nothing
              you own. The desk argued each one so you are reading a verdict,
              not a ticker list.
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
                      {r.price != null ? `$${r.price} ` : ""}
                      {r.change_pct != null ? `${r.change_pct >= 0 ? "+" : ""}${r.change_pct}% · ` : ""}
                      {r.rvol != null ? `${r.rvol}x rvol · ` : ""}
                      {r.float_shares ? `${(r.float_shares / 1e6).toFixed(0)}M float · ` : ""}
                      {r.float_turnover != null ? `${r.float_turnover}x float traded` : ""}
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
