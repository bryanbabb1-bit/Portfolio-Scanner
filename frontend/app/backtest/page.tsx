"use client";
import { useEffect, useRef, useState } from "react";
import { api, Backtest } from "../../lib/api";
import { EquityCurve } from "../../components/EquityCurve";
import { RobustnessMatrix } from "../../components/RobustnessMatrix";
import {
  DisplayHead,
  SheetRule,
  SpecEmpty,
  SpecHeader,
  SpecPanel,
  StatTile,
  TelemetryStrip,
} from "../../components/blueprint";
import "./backtest.css";

/* Backtest — sheet 04/08. Replays the live conviction rules over real history.
   The caveats are not fine print: a long-only screen replayed over the current
   book is flattering by construction, and the page says so above the fold. */

export default function BacktestPage() {
  const [d, setD] = useState<Backtest | null>(null);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const poll = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    api
      .backtest()
      .then(setD)
      .catch(() => {})
      .finally(() => setLoaded(true));
    return () => {
      if (poll.current) clearInterval(poll.current);
    };
  }, []);

  const run = async () => {
    if (running) return;
    setErr(null);
    setRunning(true);
    try {
      const { job_id } = await api.startBacktest(5);
      poll.current = setInterval(async () => {
        try {
          const j = await api.backtestJob(job_id);
          if (j.status === "done" && j.result) {
            if (poll.current) clearInterval(poll.current);
            setD(j.result);
            setRunning(false);
          } else if (j.status === "error") {
            if (poll.current) clearInterval(poll.current);
            setErr(j.error || "The replay failed");
            setRunning(false);
          }
        } catch {
          /* a dropped poll is not fatal */
        }
      }, 3000);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setRunning(false);
    }
  };

  const buys = d?.rules.filter((r) => r.side === "buy") ?? [];
  const sells = d?.rules.filter((r) => r.side === "sell") ?? [];

  return (
    <>
      <SpecHeader system="BACKTEST" version="2.0" />
      <SheetRule mark="04 / 08" />

      <div className="bt-top">
        <DisplayHead
          line1="Every rule"
          line2="gets backtested."
          sub={
            <>
              Before it fires
              <br />
              <span className="hot">a single alert at you.</span>
            </>
          }
        />

        <SpecPanel
          title="Replay Status"
          aux={d ? d.as_of.slice(0, 16) : "Never run"}
          className="bt-status"
        >
          <dl className="rs-rows">
            <Row k="Rules replayed" v={d ? `${d.rules.length}` : "—"} />
            <Row k="Symbols tested" v={d ? `${d.symbols_tested} of ${d.universe}` : "—"} />
            <Row
              k="Test period"
              v={d?.period ? `${d.period.start} → ${d.period.end}` : "—"}
            />
            <Row k="Mode" v="Long only, screen alone" />
          </dl>
          <button className="btn bt-run" onClick={run} disabled={running}>
            {running ? "Replaying…" : d ? "Re-run 5-year replay" : "Run 5-year replay"}
          </button>
          {d && (
            <p className="bt-elapsed">
              Last run took {d.elapsed_s}s over {d.signals.toLocaleString()} signals.
            </p>
          )}
        </SpecPanel>
      </div>

      {err && <div className="err">{err}</div>}

      {!d && loaded && !running && (
        <SpecEmpty>
          <b>No replay on record.</b> Nothing here is estimated or assumed —
          run the replay and every number below is computed from your own
          symbols&apos; price history.
        </SpecEmpty>
      )}

      {running && !d && (
        <p className="bt-running">Replaying every rule, bar by bar…</p>
      )}

      {d && (
        <>
          {d.curve.points.length > 1 && (
            <SpecPanel title="Equity Curve" aux={d.curve.note ? "" : undefined} className="bt-curve">
              <EquityCurve
                points={d.curve.points}
                totalReturn={d.curve.strategy_return_pct}
              />
              <p className="bt-policy">{d.curve.note}</p>
            </SpecPanel>
          )}

          <div className="tile-row bt-tiles">
            <StatTile
              label="Win rate"
              value={d.win_rate != null ? `${d.win_rate.toFixed(1)}%` : "—"}
              tone={d.win_rate != null && d.win_rate >= 50 ? "pos" : "neg"}
              foot={`At ${d.grade_horizon_days} sessions`}
            />
            <StatTile
              label="Max drawdown"
              value={d.max_drawdown_pct != null ? `${d.max_drawdown_pct.toFixed(1)}%` : "—"}
              tone="neg"
              foot="Peak to trough, strategy"
            />
            <StatTile
              label="Profit factor"
              value={d.profit_factor != null ? d.profit_factor.toFixed(2) : "—"}
              tone={d.profit_factor != null && d.profit_factor >= 1 ? "pos" : "neg"}
              foot="Gross won / gross lost"
            />
            <StatTile
              label="Avg return"
              value={d.avg_return_pct != null ? `${d.avg_return_pct.toFixed(2)}%` : "—"}
              tone={d.avg_return_pct != null && d.avg_return_pct >= 0 ? "pos" : "neg"}
              foot="Per signal, all rules"
            />
            <StatTile
              label="Vs SPY"
              value={
                d.curve.strategy_return_pct != null && d.curve.benchmark_return_pct != null
                  ? `${(d.curve.strategy_return_pct - d.curve.benchmark_return_pct).toFixed(0)}pt`
                  : "—"
              }
              tone={
                (d.curve.strategy_return_pct ?? 0) >= (d.curve.benchmark_return_pct ?? 0)
                  ? "pos"
                  : "neg"
              }
              foot={`${d.curve.days_invested_pct ?? 0}% of days invested`}
            />
          </div>

          <RuleTable title="Buy rules" rows={buys} horizon={d.grade_horizon_days} />
          <RuleTable title="Sell rules" rows={sells} horizon={d.grade_horizon_days} />

          {d.robustness && (
            <>
              {d.robustness.retirement_warnings?.length > 0 && (
                <SpecPanel title="Retirements The Data Does Not Support" className="bt-warn" plus={false}>
                  <ul className="bullets risk">
                    {d.robustness.retirement_warnings.map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                </SpecPanel>
              )}
              <SpecPanel
                title="Robustness Matrix"
                aux={`${d.robustness.rules.length} rules × ${d.robustness.columns.length} conditions`}
                className="bt-robust"
              >
                <p className="bt-policy" style={{ marginTop: 0, marginBottom: 14, paddingTop: 0, borderTop: 0 }}>
                  Each rule re-graded across every condition. A row that is one
                  colour is a real result; a row that flips colour means the
                  headline average was hiding a split.
                </p>
                <RobustnessMatrix r={d.robustness} />
              </SpecPanel>
            </>
          )}

          <SpecPanel title="Historical Validation Only" className="bt-caveats" plus={false}>
            <ul className="bullets risk">
              {d.caveats.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
            {d.skipped.length > 0 && (
              <p className="bt-skipped">
                Skipped for insufficient history: {d.skipped.join(", ")}.
              </p>
            )}
            <p className="bt-disclaimer">Past performance is not indicative of future results.</p>
          </SpecPanel>
        </>
      )}

      <TelemetryStrip
        left={[
          ["Horizon", `${d?.grade_horizon_days ?? 20}D`],
          ["Warmup", "200B"],
          ["Mode", "LONG ONLY"],
        ]}
        right={[
          ["Slippage", "NONE"],
          ["Fees", "NONE"],
          ["Engine", "LIVE RULES"],
        ]}
        line1="Test it before you trust it."
        line2="Validation, not prediction."
      />
    </>
  );
}

function RuleTable({
  title,
  rows,
  horizon,
}: {
  title: string;
  rows: Backtest["rules"];
  horizon: number;
}) {
  if (!rows.length) return null;
  return (
    <SpecPanel title={title} aux={`${rows.length} rules`} className="bt-rules">
      <div className="btr-row btr-head">
        <span>Rule</span>
        <span>Signals</span>
        <span>Win %</span>
        <span>Avg {horizon}d</span>
        <span>Profit factor</span>
        <span>Avg drawdown</span>
      </div>
      {rows.map((r) => (
        <div key={r.rule} className={`btr-row ${r.avg_20 >= 0 ? "good" : "bad"}`}>
          <span className="btr-rule">{r.rule}</span>
          <span>{r.signals}</span>
          <span>{r.win_rate.toFixed(1)}%</span>
          <span className={r.avg_20 >= 0 ? "pos" : "neg"}>
            {r.avg_20 >= 0 ? "+" : ""}
            {r.avg_20.toFixed(2)}%
          </span>
          <span className={(r.profit_factor ?? 0) >= 1 ? "pos" : "neg"}>
            {r.profit_factor != null ? r.profit_factor.toFixed(2) : "—"}
          </span>
          <span className="neg">{r.avg_mae.toFixed(1)}%</span>
        </div>
      ))}
    </SpecPanel>
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
