"use client";
import { useEffect, useRef, useState } from "react";
import { api, TransitionPlan } from "../../lib/api";
import {
  DisplayHead,
  SheetRule,
  SpecEmpty,
  SpecHeader,
  SpecPanel,
  StatTile,
  TelemetryStrip,
} from "../../components/blueprint";
import { money, pct } from "../../components/format";
import "./transition.css";

/* Transition Plan — sheet 08/08. The bridge between the book you have and the
   one the Clean Sheet says you want: what to sell, what to buy, in what order,
   at what price, and what it costs in tax. */

export default function TransitionPage() {
  const [d, setD] = useState<TransitionPlan | null>(null);
  const [running, setRunning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const poll = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    api
      .transition()
      .then((p) => {
        setD(p);
        setLoadFailed(false);
      })
      // A failed load is NOT "no plan". Conflating them showed the empty state,
      // which invited a rebuild that silently replaced a perfectly good saved
      // plan — the plan looked like it never persisted.
      .catch(() => setLoadFailed(true))
      .finally(() => setLoaded(true));
    return () => {
      if (poll.current) clearInterval(poll.current);
    };
  }, []);

  const run = async () => {
    if (running) return;
    // Rebuilding replaces the sequence. Completed steps survive (the ledger
    // outlives the plan), but the remaining order will change — so ask.
    if (d?.steps.length && !window.confirm(
      `This replaces the current ${d.steps.length}-step plan with a new one. ` +
      `Steps you have marked done stay done. Continue?`
    )) return;
    setErr(null);
    setRunning(true);
    try {
      const { job_id } = await api.startTransition();
      poll.current = setInterval(async () => {
        try {
          const j = await api.transitionJob(job_id);
          if (j.status === "done" && j.result) {
            if (poll.current) clearInterval(poll.current);
            setD(j.result);
            setRunning(false);
          } else if (j.status === "error") {
            if (poll.current) clearInterval(poll.current);
            setErr(j.error || "The plan failed");
            setRunning(false);
          }
        } catch {
          /* dropped poll is not fatal */
        }
      }, 4000);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setRunning(false);
    }
  };

  const activate = async () => {
    setBusy(true);
    try {
      await api.activateTransition();
      setD(await api.transition());
    } finally {
      setBusy(false);
    }
  };

  const toggleStep = async (n: number, done: boolean) => {
    setBusy(true);
    try {
      await api.transitionStep(n, done);
      setD(await api.transition());
    } finally {
      setBusy(false);
    }
  };

  const a = d?.analysis;
  const doneCount = d?.steps.filter((s) => s.done).length ?? 0;
  const progress = d?.steps.length ? (doneCount / d.steps.length) * 100 : 0;

  return (
    <>
      <SpecHeader system="TRANSITION PLAN" version="2.0" />
      <SheetRule mark="08 / 08" />

      <div className="tr-top">
        <DisplayHead
          line1="A path,"
          line2="not a verdict."
          tone="hot"
          sub={
            <>
              What to sell, what to buy,
              <br />
              <span className="hot">and what has to happen first.</span>
            </>
          }
        />

        <SpecPanel
          title="Plan Status"
          aux={d?.as_of ? d.as_of.slice(0, 16) : "None"}
          className="tr-status"
        >
          <dl className="rs-rows">
            <Row k="Book must move" v={a ? `${a.drift_pct}%` : "—"} />
            <Row k="Dry powder" v={a ? money(a.cash, 0) : "—"} />
            <Row
              k="Monitoring"
              v={d?.activated ? `${d.watchpoints_created ?? 0} triggers live` : "Not active"}
            />
            <Row k="Progress" v={d?.steps.length ? `${doneCount} of ${d.steps.length}` : "—"} />
          </dl>
          <button
            className="btn tr-run"
            onClick={run}
            disabled={running || busy || loadFailed}
          >
            {running ? "Building…" : d ? "Rebuild the plan" : "Build the plan"}
          </button>
          {d && d.steps.length > 0 && !d.activated && (
            <button className="btn ghost tr-act" onClick={activate} disabled={busy}>
              Activate &amp; monitor
            </button>
          )}
          {d?.activated && (
            <p className="tr-active-note">
              Active since {d.activated_at?.slice(0, 10)}. Targets are on your
              watchlist and every level is a live trigger — the app will tell
              you when a step is ready.
            </p>
          )}
        </SpecPanel>
      </div>

      {err && <div className="err">{err}</div>}
      {d?.error && <div className="err">{d.error}</div>}

      {loadFailed && (
        <SpecEmpty>
          <b>Could not reach the plan.</b> Your saved plan is still on the
          server — this is a loading problem, not an empty one.{" "}
          <button className="btn ghost tr-retry" onClick={() => location.reload()}>
            Retry
          </button>
          <br />
          Do not rebuild to make this go away; that would replace the plan you
          already have.
        </SpecEmpty>
      )}

      {!d && loaded && !loadFailed && !running && (
        <SpecEmpty>
          <b>No plan on record.</b> This turns the Clean Sheet target into a
          sequence you can actually execute — funded sells, staged buys, and a
          trigger for each. Build the Clean Sheet first if you haven&apos;t.
        </SpecEmpty>
      )}

      {running && !d && <p className="tr-running">Working out the sequence…</p>}

      {d && d.steps.length > 0 && a && (
        <>
          <SpecPanel title="The Plan" className="tr-headline-panel">
            <p className="tr-headline">{d.headline}</p>
            <p className="tr-approach">{d.approach}</p>
            {d.first_move && (
              <p className="tr-first">
                <span className="tr-first-k">Do this first</span>
                {d.first_move}
              </p>
            )}
            <div className="tr-progress">
              <div className="tr-prog-track">
                <div className="tr-prog-fill" style={{ width: `${progress}%` }} />
              </div>
              <span className="tr-prog-label">
                {doneCount} of {d.steps.length} steps complete
              </span>
            </div>
          </SpecPanel>

          <div className="tile-row tr-tiles">
            <StatTile
              label="Book to move"
              value={`${a.drift_pct}%`}
              tone="neg"
              foot="Must change hands to reach target"
            />
            <StatTile
              label="Total return"
              value={pct(a.total_return_pct)}
              tone={a.total_return_pct >= 0 ? "pos" : "neg"}
              foot="Where you are today"
            />
            <StatTile
              label="Funding sources"
              value={`${a.funding.length}`}
              foot="Overweight positions to draw from"
            />
            <StatTile
              label="To acquire"
              value={`${a.acquire.length}`}
              foot="Wanted, not yet owned"
            />
          </div>

          {/* the steps */}
          <div className="section-title" style={{ marginTop: 26 }}>
            The sequence
          </div>
          <ol className="tr-steps">
            {d.steps.map((s) => (
              <li key={s.n}>
                <SpecPanel plus={false} className={`tr-step ${s.done ? "done" : ""}`}>
                  <div className="trs-head">
                    <span className="step-num">STEP {String(s.n).padStart(2, "0")}</span>
                    <span className="trs-trigger">
                      <i>when</i> {s.trigger}
                    </span>
                    <button
                      className={`btn ghost trs-check ${s.done ? "on" : ""}`}
                      onClick={() => toggleStep(s.n, !s.done)}
                      disabled={busy}
                    >
                      {s.done ? "Done" : "Mark done"}
                    </button>
                  </div>
                  <div className="trs-orders">
                    {s.sell && (
                      <p className="trs-order sell">
                        <span className="trs-tag">Sell</span>
                        {s.sell}
                      </p>
                    )}
                    {s.buy && (
                      <p className="trs-order buy">
                        <span className="trs-tag">Buy</span>
                        {s.buy}
                      </p>
                    )}
                  </div>
                  <p className="trs-why">{s.why}</p>
                  {s.realizes && (
                    <p className="trs-tax">
                      <span className="trs-tax-k">Tax</span>
                      {s.realizes}
                    </p>
                  )}
                </SpecPanel>
              </li>
            ))}
          </ol>

          {d.guardrails && d.guardrails.length > 0 && (
            <SpecPanel title="Stop If" className="tr-guard" plus={false}>
              <ul className="bullets risk">
                {d.guardrails.map((g) => (
                  <li key={g}>{g}</li>
                ))}
              </ul>
            </SpecPanel>
          )}

          {/* the funding ledger */}
          <SpecPanel
            title="Funding Sources"
            aux="what pays for the buys"
            className="tr-fund"
          >
            <div className="trf-row trf-head">
              <span>Symbol</span>
              <span>Value</span>
              <span>Weight</span>
              <span>P/L</span>
              <span>Tax on sale</span>
            </div>
            {a.funding.map((f) => (
              <div key={f.symbol} className={`trf-row ${f.in_target_book ? "keep" : "cut"}`}>
                <span className="trf-sym">
                  {f.symbol}
                  {f.in_target_book && <i>target book</i>}
                </span>
                <span className="trf-n">{money(f.value, 0)}</span>
                <span className="trf-n">{f.weight_pct.toFixed(1)}%</span>
                <span className={`trf-n ${f.pl_pct >= 0 ? "pos" : "neg"}`}>
                  {pct(f.pl_pct)}
                </span>
                <span className="trf-tax">{f.tax.detail}</span>
              </div>
            ))}
          </SpecPanel>

          {/* the bench */}
          <SpecPanel
            title="The Bench"
            aux={d.activated ? "on your watchlist" : "not yet monitored"}
            className="tr-bench"
          >
            <p className="tr-bench-lead">
              Names the target book wants that you don&apos;t own.{" "}
              {d.activated
                ? "These are on your watchlist now, so the scanner, signals and news wire track them beside your holdings."
                : "Activate the plan and these move onto your watchlist, so the app watches them for the right entry."}
            </p>
            <div className="trb-row trb-head">
              <span>Symbol</span>
              <span>Theme</span>
              <span>Target</span>
              <span>Price</span>
              <span>Why</span>
            </div>
            {a.acquire.map((t) => (
              <div key={t.symbol} className="trb-row">
                <span className="trb-sym">{t.symbol}</span>
                <span className="trb-theme">{t.theme}</span>
                <span className="trb-n">
                  {money(t.target_dollars, 0)}
                  <i>{t.target_pct.toFixed(0)}%</i>
                </span>
                <span className="trb-n">{t.price ? money(t.price) : "—"}</span>
                <span className="trb-why">{t.why}</span>
              </div>
            ))}
          </SpecPanel>
        </>
      )}

      <TelemetryStrip
        left={[
          ["Funded", "BY SALES"],
          ["Horizon", "WEEKS"],
          ["Cash", a ? money(a.cash, 0) : "—"],
        ]}
        right={[
          ["Targets", a ? String(a.acquire.length) : "—"],
          ["Monitor", d?.activated ? "LIVE" : "OFF"],
          ["Tax", "AWARE"],
        ]}
        line1="A plan you can execute beats a target you can't."
        line2="Staged, funded, monitored."
      />
    </>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="rs-row">
      <dt>{k}</dt>
      <dd>{v}</dd>
    </div>
  );
}
