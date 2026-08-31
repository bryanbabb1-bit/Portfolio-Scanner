"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, SleeveState, Ticket } from "../../lib/api";
import { Blotter } from "../../components/Blotter";
import { SleeveCurve } from "../../components/SleeveCurve";
import { DisplayHead } from "../../components/blueprint/DisplayHead";
import { money } from "../../components/format";

/* The sleeve's own page: the whole record, not just what is open.
 *
 * The blotter on the dashboard answers "what needs me now". This answers "is
 * this working" — the equity curve against SPY, every engine's expectancy in
 * R with its sample size, and every ticket ever issued including the ones
 * that were passed on or expired unfilled. Those matter: a desk that only
 * shows you its fills is grading itself on a subset it chose.
 */

const ENGINE_LABEL: Record<string, string> = {
  ignition: "Ignition",
  pullback: "Pullback",
  footprint: "Footprint",
  manual: "Manual",
};

const ENGINE_BLURB: Record<string, string> = {
  ignition:
    "Whole market, every two minutes. A name running 7-25% on three times its normal volume, still near the day's high. Extended names are never ticketed — chasing them lost money in eight of eight measured variants.",
  pullback:
    "Once a session. Above the 200-day, RSI under 35 and turning up. The only setup here with a t-statistic above 2 (149 trades, 5 years, +0.233R).",
  footprint:
    "Unusual volume before any move. Held as a watch until price breaks the prior session's high — at 8x volume the median five-day return is negative, so the volume earns a watch and only the break earns a position.",
  manual: "Tickets you wrote yourself, sized by the same risk math.",
};

const r = (v: number | null | undefined) =>
  v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(2)}R`;

export default function SleevePage() {
  const [s, setS] = useState<SleeveState | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const load = () => api.sleeve().then(setS).catch((e) => setErr(e.message));
    load();
    const t = setInterval(load, 60_000);
    return () => clearInterval(t);
  }, []);

  if (err) return <div className="err">Could not reach the sleeve ({err}).</div>;
  if (!s) return <div className="loading">Loading the sleeve…</div>;

  const closed = s.tickets.filter((t) => t.status === "closed");
  const dead = s.tickets.filter((t) => t.status === "passed" || t.status === "expired");
  const totalR = closed.reduce((a, t) => a + (t.r_multiple ?? 0), 0);
  const engines = Object.keys(ENGINE_LABEL);

  return (
    <>
      <DisplayHead
        line1="The"
        line2="Sleeve"
        tone="hot"
        sub={
          <>
            A SECOND BOOK · {s.config.risk_pct}% RISK PER TICKET ·{" "}
            {s.config.max_slots} SLOTS · HARD STOPS ON EVERYTHING ·{" "}
            <Link href="/settings#sleeve">RULES</Link>
          </>
        }
      />

      <div className="slv-stats">
        <div className="slv-stat">
          <span className="l">Equity</span>
          <span className="v">{money(s.equity, 0)}</span>
          <span className="s">capital {money(s.capital, 0)}</span>
        </div>
        <div className="slv-stat">
          <span className="l">Realized</span>
          <span className={`v ${s.realized > 0 ? "up" : s.realized < 0 ? "dn" : ""}`}>
            {s.realized >= 0 ? "+" : ""}{money(s.realized, 0)}
          </span>
          <span className="s">{closed.length} closed</span>
        </div>
        <div className="slv-stat">
          <span className="l">Total</span>
          <span className={`v ${totalR >= 0 ? "up" : "dn"}`}>{r(totalR)}</span>
          <span className="s">sum of every graded ticket</span>
        </div>
        <div className="slv-stat">
          <span className="l">Deployed</span>
          <span className="v">{money(s.deployed, 0)}</span>
          <span className="s">{s.slots_used}/{s.config.max_slots} slots · {s.counts.watching} watching</span>
        </div>
      </div>

      <SleeveCurve state={s} />

      <Blotter compact />

      <div className="mfx-label">The engines</div>
      <div className="slv-engines">
        {engines.map((e) => {
          const sc = s.scorecard[e];
          return (
            <div key={e} className="card slv-eng">
              <div className="se-head">
                <span className="se-name">{ENGINE_LABEL[e]}</span>
                {sc ? (
                  <span className={`se-r ${sc.expectancy_r >= 0 ? "up" : "dn"}`}>
                    {r(sc.expectancy_r)} <span className="mut">expectancy</span>
                  </span>
                ) : (
                  <span className="se-r mut">no closed tickets yet</span>
                )}
              </div>
              <p className="se-blurb">{ENGINE_BLURB[e]}</p>
              {sc && (
                <div className="se-grid">
                  <span><i>n</i>{sc.n}</span>
                  <span><i>win</i>{sc.win_rate.toFixed(0)}%</span>
                  <span><i>total</i>{r(sc.total_r)}</span>
                  <span><i>best</i>{r(sc.best_r)}</span>
                  <span><i>worst</i>{r(sc.worst_r)}</span>
                  <span><i>t</i>{sc.t_stat ?? "—"}</span>
                </div>
              )}
              {sc && sc.n < 20 && (
                <p className="se-warn">
                  {sc.n} closed {sc.n === 1 ? "ticket" : "tickets"} cannot separate an edge
                  from luck — a t-statistic needs about 2.0 and a sample to earn it. Read this
                  as a record, not a result.
                </p>
              )}
            </div>
          );
        })}
      </div>

      {dead.length > 0 && (
        <>
          <div className="mfx-label">
            Passed and expired · {dead.length} · the ones that cost nothing
          </div>
          <div className="card slv-dead">
            {dead.slice(0, 20).map((t: Ticket) => (
              <div key={t.id} className="sd-row">
                <span className="sd-state">{t.status === "passed" ? "PASSED" : "EXPIRED"}</span>
                <Link href={`/stock/${t.symbol}`} className="sd-sym">{t.symbol}</Link>
                <span className="mut">{ENGINE_LABEL[t.engine]}</span>
                <span className="mut">
                  {t.trigger_above ? `never broke ${t.trigger_above.toFixed(2)}` : `${t.entry.toFixed(2)} entry`}
                </span>
                <span className="mut">{t.created.slice(0, 10)}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}
