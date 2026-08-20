"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { API_BASE } from "../lib/api";

/* The whole market, not the book.
 *
 * "The goal is to get notified when big shit happens so we can be a part of a
 * big rally. Ignore the current cash available. I need to know."
 *
 * So this panel does not care what is owned, what is affordable, or whether the
 * desk would approve. It reports what is happening. The loud tier — +40% on a
 * name that already traded $50M a day — is also a push, and was measured at
 * 0.35 a session so it stays worth reading.
 */

interface Mover {
  symbol: string;
  name: string;
  change_pct: number;
  price: number;
  prior_dollar_vol: number;
  tier: "alert" | "big" | "runner";
  why?: string;
}

interface Feed {
  ts: number | null;
  date: string | null;
  movers: Mover[];
  cluster: boolean;
}

const money = (v: number) =>
  v >= 1e9 ? `$${(v / 1e9).toFixed(1)}B` : `$${(v / 1e6).toFixed(0)}M`;

const TIER_LABEL: Record<Mover["tier"], string> = {
  alert: "Woke you",
  big: "Real size",
  runner: "Running",
};

export function BigMoves() {
  const [f, setF] = useState<Feed | null>(null);

  useEffect(() => {
    const load = () =>
      fetch(`${API_BASE}/api/bigmoves`, { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => d && Array.isArray(d.movers) && setF(d))
        .catch(() => {});
    load();
    const t = setInterval(load, 120_000);
    return () => clearInterval(t);
  }, []);

  if (!f || !f.movers.length) return null;

  const alerts = f.movers.filter((m) => m.tier === "alert");

  return (
    <>
      <div className="mfx-label">
        Moving now · whole market · nothing to do with what you own
      </div>
      <div className="card bmv">
        <p className="bmv-lead">
          {alerts.length > 0 ? (
            <>
              <strong>{alerts.length} name{alerts.length === 1 ? "" : "s"} cleared
              the loud bar</strong> — up 40%+ on a company that already traded
              $50M a day. That happens about once every three sessions, and it
              is what buzzes your phone.
            </>
          ) : f.cluster ? (
            <>
              <strong>Broad tape today.</strong> {f.movers.length} names running
              — when this many move together it is the sector, not the story.
              One digest after the close, not one push each.
            </>
          ) : (
            <>
              {f.movers.length} name{f.movers.length === 1 ? "" : "s"} moving hard.
              Nothing at the wake-you-up threshold yet.
            </>
          )}
        </p>

        <div className="bmv-list">
          {f.movers.slice(0, 14).map((m) => (
            <Link key={m.symbol} href={`/stock/${m.symbol}`} className={`bmv-row t-${m.tier}`}>
              <span className="bmv-chg">+{m.change_pct.toFixed(0)}%</span>
              <span className="bmv-sym">
                <span className="bs-t">{m.symbol}</span>
                <span className="bs-n">{m.name}</span>
              </span>
              <span className="bmv-tier">{TIER_LABEL[m.tier]}</span>
              <span className="bmv-what">
                {m.why || <span className="mut">no headline on the wire yet</span>}
              </span>
              <span className="bmv-liq">{money(m.prior_dollar_vol)}/day before</span>
            </Link>
          ))}
        </div>

        <p className="bmv-foot">
          The dollar-volume figure is what the name traded on a NORMAL day, at
          its pre-move price — it is the line between a company being repriced
          and a shell being pumped. Measured over 43 sessions, chasing these
          into the close lost money in all eight variants tested; this panel
          exists so you see them, not because the desk endorses buying them.
        </p>
      </div>
    </>
  );
}
