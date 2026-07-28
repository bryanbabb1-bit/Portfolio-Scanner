"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, Learning, RuleHealth } from "../../lib/api";
import {
  DisplayHead,
  SheetRule,
  SpecEmpty,
  SpecHeader,
  SpecPanel,
  TelemetryStrip,
} from "../../components/blueprint";
import "./loop.css";

/* Learning Loop — sheet 06/08. Research -> Trade -> Review -> Optimize ->
   Repeat, with the real numbers at each node.

   Proposals are suggest-only. Accepting one records intent; it never changes
   what fires, because thresholds that send real alerts should move in a
   reviewed diff, not silently from a button. */

const VERDICT_ORDER = ["RETIRE", "RETUNE", "MARGINAL", "EARNING"] as const;

export default function LoopPage() {
  const [d, setD] = useState<Learning | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = () =>
    api
      .learning()
      .then(setD)
      .catch((e) => setErr(e.message));

  useEffect(() => {
    load();
  }, []);

  const toggle = async (r: RuleHealth) => {
    setBusy(r.rule);
    try {
      if (r.accepted) await api.unacceptProposal(r.rule);
      else await api.acceptProposal(r.rule, r.proposal ?? "");
      await load();
    } finally {
      setBusy(null);
    }
  };

  if (err) return <div className="err">Rule health unavailable ({err}).</div>;
  if (!d) return <div className="loading">Grading every rule…</div>;

  const cycle = [
    {
      n: "01",
      t: "Research",
      d: "Scan the book, the watchlist and the discovery universe for setups.",
      stat: `${d.rules.length} rules live`,
    },
    {
      n: "02",
      t: "Trade",
      d: "Signals that survive the screen and the desk reach you as calls.",
      stat: `${d.live_signals_graded} graded so far`,
    },
    {
      n: "03",
      t: "Review",
      d: "Every fired signal is replayed against what price actually did next.",
      stat: d.live_win_rate != null ? `${d.live_win_rate}% live win rate` : "Awaiting sample",
    },
    {
      n: "04",
      t: "Optimize",
      d: "Rules that lose money get flagged with a proposal you can accept.",
      stat: `${(d.counts.RETUNE ?? 0) + (d.counts.RETIRE ?? 0)} need work`,
    },
    {
      n: "05",
      t: "Repeat",
      d: "The advisor is told which screens have paid, so it weights them by record.",
      stat: `${d.counts.EARNING ?? 0} earning their bar`,
    },
  ];

  return (
    <>
      <SpecHeader system="LEARNING LOOP" version="2.0" />
      <SheetRule mark="06 / 08" />

      <div className="loop-top">
        <DisplayHead
          line1="It improves"
          line2="after every trade."
          sub={
            <>
              Learn.
              <br />
              Adapt.
              <br />
              <span className="hot">Repeat.</span>
            </>
          }
        />

        <ol className="loop-cycle">
          {cycle.map((c) => (
            <li key={c.n}>
              <SpecPanel plus={false}>
                <span className="step-num">{c.n}</span>
                <h3 className="lc-title">{c.t}</h3>
                <div className="dh-rule lc-rule" />
                <p className="lc-body">{c.d}</p>
                <p className="lc-stat">{c.stat}</p>
              </SpecPanel>
            </li>
          ))}
        </ol>
      </div>

      {!d.has_backtest && (
        <SpecEmpty>
          <b>No replay on record.</b> Verdicts below need a backtest to stand
          on. Run one on the <Link href="/backtest" className="ds-link">Backtest sheet</Link>,
          then come back.
        </SpecEmpty>
      )}

      <div className="loop-counts">
        {VERDICT_ORDER.map((v) => (
          <div key={v} className={`lct ${v.toLowerCase()}`}>
            <span className="lct-n">{d.counts[v] ?? 0}</span>
            <span className="lct-v">{v}</span>
          </div>
        ))}
      </div>

      <SpecPanel
        title="Rule Health"
        aux={d.backtest_period ? `${d.backtest_period.start} → ${d.backtest_period.end}` : ""}
        className="loop-table"
      >
        <div className="lr-row lr-head">
          <span>Rule</span>
          <span>Verdict</span>
          <span>Replay</span>
          <span>Live</span>
          <span>PF</span>
          <span />
        </div>
        {d.rules.map((r) => (
          <div key={r.rule} className={`lr-block ${r.verdict.toLowerCase()}`}>
            <div className="lr-row">
              <span className="lr-rule">{r.rule}</span>
              <span className={`lr-verdict ${r.verdict.toLowerCase()}`}>{r.verdict}</span>
              <span className="lr-num">
                {r.backtest_signals ? (
                  <>
                    {r.backtest_signals} sig
                    <i className={(r.backtest_avg_pct ?? 0) >= 0 ? "pos" : "neg"}>
                      {(r.backtest_avg_pct ?? 0) >= 0 ? "+" : ""}
                      {r.backtest_avg_pct?.toFixed(2)}%
                    </i>
                  </>
                ) : (
                  <em>none</em>
                )}
              </span>
              <span className="lr-num">
                {r.live_signals ? (
                  <>
                    {r.live_signals} sig
                    <i className={(r.live_avg_pct ?? 0) >= 0 ? "pos" : "neg"}>
                      {(r.live_avg_pct ?? 0) >= 0 ? "+" : ""}
                      {r.live_avg_pct?.toFixed(2)}%
                    </i>
                  </>
                ) : (
                  <em>none</em>
                )}
              </span>
              <span className={`lr-pf ${(r.profit_factor ?? 0) >= 1 ? "pos" : "neg"}`}>
                {r.profit_factor != null ? r.profit_factor.toFixed(2) : "—"}
              </span>
              <span>
                {r.proposal && (
                  <button
                    className={`btn ghost lr-accept ${r.accepted ? "on" : ""}`}
                    onClick={() => toggle(r)}
                    disabled={busy === r.rule}
                  >
                    {r.accepted ? "Accepted" : "Accept"}
                  </button>
                )}
              </span>
            </div>
            <p className="lr-reason">{r.reason}</p>
            {r.proposal && (
              <p className="lr-proposal">
                <span className="lr-tag">Proposal</span>
                {r.proposal}
              </p>
            )}
            {r.accepted && (
              <p className="lr-accepted">
                Accepted {r.accepted.accepted_at.slice(0, 10)} — recorded as intent.
                Nothing changed in what fires; that stays a code change.
              </p>
            )}
          </div>
        ))}
      </SpecPanel>

      <SpecPanel title="Read This With The Numbers" className="loop-notes" plus={false}>
        <ul className="bullets risk">
          {d.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      </SpecPanel>

      <TelemetryStrip
        left={[
          ["Rules", `${d.rules.length}`],
          ["Live", `${d.live_signals_graded}`],
          ["Replay", d.has_backtest ? "YES" : "NO"],
        ]}
        right={[
          ["Auto-apply", "OFF"],
          ["Mode", "SUGGEST"],
          ["Review", "MANUAL"],
        ]}
        line1="Every cycle makes the system stronger."
        line2="Measured, not assumed."
      />
    </>
  );
}
