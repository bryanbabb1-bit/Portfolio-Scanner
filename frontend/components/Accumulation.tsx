"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { API_BASE } from "../lib/api";

/* Where the volume showed up BEFORE the move.
 *
 * This replaced the SEC filings feed, which was complete, official and useless
 * for the one thing Bryan wants: an 8-K is filed alongside the press release,
 * so by the time it exists the move has happened.
 *
 * This asks the other question. Across 101,240 tradeable stock-days, screening
 * on prior-day volume at 8x its own 60-day average concentrated the names that
 * touched +50% within a week from 1.3% to 13.7% — more than tenfold. The same
 * screen has a median five-day outcome of -8.1%.
 *
 * Both numbers are on the panel, always. A hit rate without its median beside
 * it is a lie by omission, and this is a hunting ground, not a buy list.
 */

interface Row {
  symbol: string;
  price: number;
  vol_ratio: number;
  week_ratio: number;
  avg_dollar_vol: number;
  drift_20d: number;
  change_pct: number;
  beaten_down: boolean;
  loud: boolean;
}

interface Feed {
  ts: number;
  scanned: number;
  universe: number;
  results: Row[];
  measured: {
    baseline_touch_50: number;
    at_8x_touch_50: number;
    at_8x_median_5d: number;
    alerts_per_day_at_8x: number;
  };
}

const money = (v: number) =>
  v >= 1e9 ? `$${(v / 1e9).toFixed(1)}B` : `$${(v / 1e6).toFixed(1)}M`;

export function Accumulation() {
  const [f, setF] = useState<Feed | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/accumulation`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d && Array.isArray(d.results) && setF(d))
      .catch(() => {});
  }, []);

  if (!f || !f.results.length) return null;
  const m = f.measured;

  return (
    <>
      <div className="mfx-label">
        Volume showed up first · whole market · before the move, not after
      </div>
      <div className="card acc">
        <p className="acc-lead">
          Names trading far more than they normally do. Across{" "}
          <strong>101,240 stock-days</strong>, screening here concentrated the
          ones that touched +50% within a week from{" "}
          <strong>{m.baseline_touch_50}%</strong> to{" "}
          <strong>{m.at_8x_touch_50}%</strong> — more than tenfold, a day before
          the move.
        </p>

        <div className="acc-list">
          {f.results.slice(0, 16).map((r) => (
            <Link key={r.symbol} href={`/stock/${r.symbol}`} className={`acc-row ${r.loud ? "loud" : ""}`}>
              <span className="acc-vol">{r.vol_ratio}x</span>
              <span className="acc-sym">{r.symbol}</span>
              <span className="acc-px">
                ${r.price.toFixed(2)}
                <span className={`acc-day ${r.change_pct >= 0 ? "pos" : "neg"}`}>
                  {r.change_pct >= 0 ? "+" : ""}{r.change_pct.toFixed(1)}%
                </span>
              </span>
              <span className="acc-tags">
                {r.loud && <span className="acc-tag hot">unusual</span>}
                {r.beaten_down && <span className="acc-tag down">beaten down</span>}
                <span className="acc-note">
                  {r.drift_20d >= 0 ? "+" : ""}{r.drift_20d.toFixed(0)}% on the month ·
                  normally {money(r.avg_dollar_vol)}/day · week {r.week_ratio}x
                </span>
              </span>
              <span className="acc-go">Look →</span>
            </Link>
          ))}
        </div>

        <p className="acc-warn">
          <strong>Read the other column too.</strong> The same screen has a
          median five-day outcome of <strong>{m.at_8x_median_5d}%</strong>, and
          it gets worse as the filter tightens — both tails fatten and the left
          one is heavier. Buying everything here loses money exactly as chasing
          runners did. This is a hunting ground: roughly two and a half names a
          day that are about to move are somewhere in a list of{" "}
          {m.alerts_per_day_at_8x}, and picking among them needs a reason —
          a catalyst, a partner trial, a thesis.
        </p>
        <p className="acc-cover">
          Scanned {f.scanned.toLocaleString()} of {f.universe.toLocaleString()}{" "}
          US listings. &ldquo;Beaten down&rdquo; is flagged because the median
          name that ran 50% was down 25% on the month first.
        </p>
      </div>
    </>
  );
}
