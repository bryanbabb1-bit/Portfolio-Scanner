"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, SleeveState, Ticket } from "../lib/api";
import { money } from "./format";

/* The blotter — the trading sleeve's tickets, and the one place the app asks
 * for a decision instead of offering a paragraph.
 *
 * Armed tickets want Filled or Pass. Live tickets show the stop the manager
 * is holding and where the trade sits in R. Exit tickets are the manager
 * saying SELL NOW; they want the price you actually got. Closed tickets are
 * graded in R and roll up into the scorecard beside it, with n, because a
 * number without its sample size is how a desk fools itself.
 */

const ENGINE_LABEL: Record<Ticket["engine"], string> = {
  ignition: "Ignition",
  pullback: "Pullback",
  footprint: "Footprint",
  manual: "Manual",
};

const px = (v: number | null | undefined) => (v == null ? "—" : v >= 100 ? v.toFixed(2) : v.toFixed(2));
const r = (v: number | null | undefined) => (v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(1)}R`);
const pct = (a: number, b: number) => `${(((a - b) / b) * 100).toFixed(0)}%`;

function PriceAction({ label, onSubmit, defaultValue, danger }: {
  label: string; onSubmit: (price: number) => Promise<void>; defaultValue?: number | null; danger?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [val, setVal] = useState(defaultValue != null ? String(defaultValue) : "");
  const [busy, setBusy] = useState(false);
  if (!open) {
    return (
      <button className={`bl-btn${danger ? " danger" : ""}`} onClick={() => setOpen(true)}>{label}</button>
    );
  }
  return (
    <form
      className="bl-inline"
      onSubmit={async (e) => {
        e.preventDefault();
        const p = parseFloat(val);
        if (!Number.isFinite(p) || p <= 0) return;
        setBusy(true);
        try { await onSubmit(p); } finally { setBusy(false); setOpen(false); }
      }}
    >
      <input type="number" step="any" min={0} value={val} placeholder="price" autoFocus
             onChange={(e) => setVal(e.target.value)} aria-label={`${label} price`} />
      <button className="bl-btn" type="submit" disabled={busy}>{busy ? "…" : "OK"}</button>
      <button className="bl-btn ghost" type="button" onClick={() => setOpen(false)}>Cancel</button>
    </form>
  );
}

export function Blotter({ focusId, compact }: { focusId?: string | null; compact?: boolean }) {
  const [s, setS] = useState<SleeveState | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [showClosed, setShowClosed] = useState(false);

  const load = useCallback(() => {
    api.sleeve().then((d) => { setS(d); setErr(null); }).catch((e) => setErr(e.message));
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 60_000);
    return () => clearInterval(t);
  }, [load]);

  useEffect(() => {
    if (focusId && s) {
      setTimeout(() => document.getElementById(`tk-${focusId}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 80);
    }
  }, [focusId, s]);

  if (err) return null;
  if (!s) return null;
  if (!s.config.enabled) return null;

  const armed = s.tickets.filter((t) => t.status === "armed");
  const watching = s.tickets.filter((t) => t.status === "watching");
  const exits = s.tickets.filter((t) => t.status === "exit");
  const live = s.tickets.filter((t) => t.status === "live");
  const closed = s.tickets.filter((t) => t.status === "closed");
  const waiting = armed.length + exits.length;
  const fundedPct = s.capital > 0 ? Math.min(100, (s.deployed / s.capital) * 100) : 0;
  const scoreRows = Object.entries(s.scorecard);

  return (
    <>
      <div className="mfx-label" id="blotter">
        Blotter · trading sleeve ·{" "}
        {waiting > 0
          ? `${waiting} waiting on you`
          : watching.length > 0
            ? `${watching.length} watching for a break`
            : "nothing waiting"}
      </div>
      <div className="card bl">
        {/* The sleeve's own page states equity, deployed and realized in its
            masthead, so the panel drops its header there rather than saying
            the same four numbers twice on one screen. */}
        {!compact && (
        <div className="bl-head">
          <div className="bl-stat">
            <span className="bl-k">Sleeve equity</span>
            <span className="bl-v">{money(s.equity, 0)}</span>
            <span className="bl-sub">
              {s.config.capital_usd ? "set" : `${s.config.capital_pct}% of core`} · capital {money(s.capital, 0)}
            </span>
          </div>
          <div className="bl-stat">
            <span className="bl-k">Deployed</span>
            <span className="bl-v">{money(s.deployed, 0)}</span>
            <span className="bl-sub">{fundedPct.toFixed(0)}% of capital in {s.slots_used}/{s.config.max_slots} slots</span>
          </div>
          <div className="bl-stat">
            <span className="bl-k">Realized</span>
            <span className={`bl-v ${s.realized > 0 ? "up" : s.realized < 0 ? "dn" : ""}`}>
              {s.realized >= 0 ? "+" : ""}{money(s.realized, 0)}
            </span>
            <span className="bl-sub">{s.counts.closed} closed · {s.issued_today}/{s.config.max_tickets_per_day} tickets today</span>
          </div>
          <div className="bl-stat rules">
            <span className="bl-k">Rules</span>
            <span className="bl-sub">
              {s.config.risk_pct}% risk per ticket · runner stop {Math.round(s.config.ignition_stop_pct * 100)}% ·
              trail {Math.round(s.config.trail_pct * 100)}% after +1R · target {s.config.target_r}R ·{" "}
              <Link href="/settings#sleeve">change</Link>
            </span>
          </div>
        </div>
        )}

        {!compact && s.deployed === 0 && s.counts.live === 0 && (
          <p className="bl-note">
            Nothing is deployed yet. Tickets size against {money(s.capital, 0)} from today; fund the
            sleeve by moving that much out of the core when you are ready. It never tops up from the
            core after a loss — its job is to earn its own growth or prove it cannot.
          </p>
        )}

        {exits.map((t) => (
          <TicketRow key={t.id} t={t} tone="exit" focus={focusId === t.id} onDone={load} />
        ))}
        {armed.map((t) => (
          <TicketRow key={t.id} t={t} tone="armed" focus={focusId === t.id} onDone={load} />
        ))}
        {live.map((t) => (
          <TicketRow key={t.id} t={t} tone="live" focus={focusId === t.id} onDone={load} />
        ))}
        {watching.map((t) => (
          <TicketRow key={t.id} t={t} tone="watching" focus={focusId === t.id} onDone={load} />
        ))}

        {waiting === 0 && live.length === 0 && watching.length === 0 && (
          <p className="bl-empty">
            No open tickets. Three engines feed this: <b>ignition</b> (whole market, every two
            minutes — a name running 7-25% on heavy volume gets an entry, stop, target and size
            pushed to your phone; extended names are never ticketed), <b>pullback</b> (once a
            session — oversold and turning up above the 200-day, the only setup here with a
            t-statistic above 2), and <b>footprint</b> (unusual volume before any move, held as a
            watch until price breaks the prior day's high).
          </p>
        )}

        <div className="bl-foot">
          <div className="bl-score">
            {s.benchmark_note && <span className="bl-bench">{s.benchmark_note}</span>}
            {scoreRows.length === 0 ? (
              <span className="mut">Scorecard starts with the first closed ticket. Grades are in R, with n beside them.</span>
            ) : scoreRows.map(([eng, sc]) => (
              <span key={eng} className="bl-score-row">
                <b>{ENGINE_LABEL[eng as Ticket["engine"]] ?? eng}</b> n={sc.n} · {sc.win_rate.toFixed(0)}% win ·{" "}
                <span className={sc.expectancy_r >= 0 ? "up" : "dn"}>{r(sc.expectancy_r)}</span> expectancy ·{" "}
                total {r(sc.total_r)} · t={sc.t_stat ?? "—"}
                {sc.n < 20 && <span className="mut"> · too few to trust yet</span>}
              </span>
            ))}
          </div>
          {closed.length > 0 && (
            <button className="bl-btn ghost" onClick={() => setShowClosed((v) => !v)}>
              {showClosed ? "Hide" : "Show"} {closed.length} closed
            </button>
          )}
        </div>
        {showClosed && closed.slice(0, 12).map((t) => (
          <TicketRow key={t.id} t={t} tone="closed" focus={false} onDone={load} />
        ))}
      </div>
    </>
  );
}

function TicketRow({ t, tone, focus, onDone }: {
  t: Ticket; tone: "watching" | "armed" | "live" | "exit" | "closed"; focus: boolean; onDone: () => void;
}) {
  const ref = t.fill_price ?? t.entry;
  const stopNow = t.current_stop ?? t.stop;
  return (
    <div id={`tk-${t.id}`} className={`bl-row ${tone}${focus ? " focus" : ""}`}>
      <div className="bl-c1">
        <span className={`bl-state ${tone}`}>
          {tone === "watching" ? "WATCHING" : tone === "armed" ? "ARMED"
            : tone === "live" ? "LIVE" : tone === "exit" ? "SELL NOW" : "CLOSED"}
        </span>
        <Link href={`/stock/${t.symbol}`} className="bl-sym">{t.symbol}</Link>
        <span className="bl-eng">{ENGINE_LABEL[t.engine]}{t.headline ? ` · ${t.headline}` : ""}</span>
      </div>

      <div className="bl-c2">
        {tone === "watching" && (
          <>
            <span><i>waits above</i> {px(t.trigger_above)}</span>
            <span><i>now</i> {px(t.last_price)}
              <span className="mut"> ({t.trigger_above && t.last_price ? pct(t.last_price, t.trigger_above) : "—"} away)</span></span>
            <span><i>then buy</i> {money(t.notional, 0)}</span>
            <span><i>stop</i> {px(t.stop)}</span>
            <span><i>expires</i> {new Date(t.expires * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span>
          </>
        )}
        {tone === "armed" && (
          <>
            <span><i>Buy</i> {money(t.notional, 0)} <span className="mut">({t.shares.toFixed(2)} sh)</span></span>
            <span><i>at</i> {px(t.entry)}</span>
            <span><i>stop</i> {px(t.stop)} <span className="mut">({pct(t.stop, t.entry)})</span></span>
            <span><i>target</i> {px(t.target)} <span className="mut">(+{((t.target - t.entry) / t.r_unit).toFixed(1)}R)</span></span>
            <span><i>risk</i> {money(t.risk_usd, 0)}</span>
          </>
        )}
        {(tone === "live" || tone === "exit") && (
          <>
            <span><i>filled</i> {px(t.fill_price)} <span className="mut">× {t.shares.toFixed(2)}</span></span>
            <span><i>now</i> {px(t.last_price)} <span className={(t.r_now ?? 0) >= 0 ? "up" : "dn"}>{r(t.r_now)}</span></span>
            <span><i>stop</i> {px(stopNow)} {t.trail_armed && <span className="bl-trail">trailing</span>}</span>
            <span><i>target</i> {px(t.target)}</span>
            <span><i>held</i> {t.sessions_held}d</span>
          </>
        )}
        {tone === "closed" && (
          <>
            <span><i>in</i> {px(t.fill_price)}</span>
            <span><i>out</i> {px(t.exit_price)}</span>
            <span><i>result</i> <span className={(t.r_multiple ?? 0) >= 0 ? "up" : "dn"}>{r(t.r_multiple)}</span> · {t.pnl_usd != null && (t.pnl_usd >= 0 ? "+" : "") + money(t.pnl_usd, 0)}</span>
            <span><i>why</i> {t.exit_reason}</span>
          </>
        )}
      </div>

      {tone === "exit" && t.exit_signal && (
        <div className="bl-why exit">
          {t.exit_signal.reason === "stop" ? "Stop hit" : t.exit_signal.reason === "target" ? "Target hit" : "Time stop — it has not paid"}
          {" "}at {px(t.exit_signal.price)} ({r(t.exit_signal.r)}). Sell it, then confirm the price you got.
        </div>
      )}
      {(tone === "armed" || tone === "watching") && t.why.length > 0 && (
        <ul className="bl-why">{t.why.slice(0, 3).map((w, i) => <li key={i}>{w}</li>)}</ul>
      )}
      {/* The trader's read. It arrives after the ticket and can never change
          a level, so its absence is normal and never blocks a decision. */}
      {(tone === "armed" || tone === "watching") && t.note && (
        <p className="bl-note-trader">
          {t.note}
          {t.note_risk && <span className="bl-risk"> Risk: {t.note_risk}</span>}
        </p>
      )}

      <div className="bl-c3">
        {tone === "watching" && (
          <button className="bl-btn ghost" onClick={async () => { await api.ticketPass(t.id); onDone(); }}>Drop</button>
        )}
        {tone === "armed" && (
          <>
            <PriceAction label="Filled at…" defaultValue={t.entry}
                         onSubmit={async (p) => { await api.ticketFill(t.id, p); onDone(); }} />
            <button className="bl-btn ghost" onClick={async () => { await api.ticketPass(t.id); onDone(); }}>Pass</button>
          </>
        )}
        {(tone === "live" || tone === "exit") && (
          <PriceAction label={tone === "exit" ? "Sold at…" : "Sold at…"} danger={tone === "exit"}
                       defaultValue={t.last_price ?? ref}
                       onSubmit={async (p) => { await api.ticketClose(t.id, p, tone === "exit" ? (t.exit_signal?.reason ?? "manual") : "manual"); onDone(); }} />
        )}
      </div>
    </div>
  );
}
