"use client";
import { useEffect, useState } from "react";
import { API_BASE } from "../../lib/api";
import { DisplayHead } from "../../components/blueprint/DisplayHead";
import "./paper.css";

/* Paper-trading lab.
 *
 * This page exists to answer one question honestly: does the rule set have an
 * edge worth real money? So the verdict leads, and it leads even when the answer
 * is no — a strategy page that only knows how to look encouraging is worse than
 * no page, because it will eventually talk you into funding something.
 */

interface Trade {
  symbol: string;
  day: string;
  entry_time: string;
  entry: number;
  stop: number;
  target: number;
  shares: number;
  risk_dollars: number;
  setup: string;
  realized: number;
  r_multiple: number | null;
  exit_reason: string;
}

interface Backtest {
  metrics: Record<string, number | null>;
  significance: {
    n: number;
    mean_r?: number;
    sd_r?: number;
    std_error?: number;
    t_stat?: number;
    significant?: boolean;
    trades_needed_for_95pct?: number | null;
    verdict: string;
  };
  blocked: Record<string, number>;
  days: number;
  symbols: string[];
  trades: Trade[];
  trades_per_session: number;
  config: Record<string, number>;
}

interface Swing {
  metrics: Record<string, number | null>;
  extra: Record<string, number | null>;
  significance: Backtest["significance"];
  benchmark: { symbol?: string; return_pct?: number; cagr_pct?: number; max_drawdown_pct?: number };
  by_year: { year: string; strategy_pct: number; benchmark_pct: number | null }[];
  blocked: Record<string, number>;
  days: number;
  symbols: string[];
  trades: Trade[];
}

interface Regime {
  metrics: Record<string, number | null>;
  extra: Record<string, number | null>;
  windows: {
    window: string; from: string; to: string;
    cagr_pct: number | null; max_drawdown_pct: number; trades: number;
    pct_risk_on: number;
    benchmark: { cagr_pct?: number; max_drawdown_pct?: number };
  }[];
  by_year: { year: string; strategy_pct: number; benchmark_pct: number | null }[];
}

interface Rules {
  account: Record<string, string>;
  setup: string[];
  execution: string[];
  risk: string[];
  universe: string[];
}

const money = (v: number) => `${v < 0 ? "-" : ""}$${Math.abs(v).toFixed(2)}`;

export default function PaperPage() {
  const [bt, setBt] = useState<Backtest | null>(null);
  const [sw, setSw] = useState<Swing | null>(null);
  const [rg, setRg] = useState<Regime | null>(null);
  const [rules, setRules] = useState<Rules | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const load = (force = false) => {
    setRunning(force);
    fetch(`${API_BASE}/api/paper/backtest${force ? "?force=true" : ""}`, {
      cache: "no-store",
    })
      .then((r) => r.json())
      .then(setBt)
      .catch((e) => setErr(String(e)))
      .finally(() => setRunning(false));
  };

  useEffect(() => {
    load();
    fetch(`${API_BASE}/api/paper/swing`, { cache: "no-store" })
      .then((r) => r.json())
      .then(setSw)
      .catch(() => {});
    fetch(`${API_BASE}/api/paper/regime`, { cache: "no-store" })
      .then((r) => r.json())
      .then((d) => !d.error && setRg(d))
      .catch(() => {});
    fetch(`${API_BASE}/api/paper/rules`, { cache: "no-store" })
      .then((r) => r.json())
      .then(setRules)
      .catch(() => {});
  }, []);

  const sig = bt?.significance;
  const proven = !!sig?.significant && (bt?.metrics.expectancy_r ?? 0) > 0;
  // Two to four weeks is what was asked for. Whether that is long enough is a
  // arithmetic question, not an opinion, so it gets answered here.
  const perSession = bt?.trades_per_session ?? 0;
  const sessionsNeeded =
    sig?.trades_needed_for_95pct && perSession
      ? Math.ceil(sig.trades_needed_for_95pct / perSession)
      : null;

  return (
    <>
      <DisplayHead line1="PAPER" line2="TRADING LAB" tone="hot" />
      <p className="dh-sub">
        $1,000 cash account · deterministic rules · replayed on 5-minute bars
      </p>

      {err && <div className="err">{err}</div>}

      {rg && (
        <>
          <div className="pl-verdict no">
            <div className="pl-verdict-tag">
              Best model found · still trails buy-and-hold
            </div>
            <p className="pl-verdict-line">
              Own SPY while it is above its 200-day; hunt pullbacks when it
              isn&apos;t. Over 15 years it compounds at{" "}
              <b>{rg.extra.cagr_pct}%</b> against SPY&apos;s{" "}
              <b>{rg.windows[0]?.benchmark.cagr_pct}%</b>, but cuts the worst
              drawdown from <b>{rg.windows[0]?.benchmark.max_drawdown_pct}%</b>{" "}
              to <b>{rg.metrics.max_drawdown_pct}%</b>. It is a risk-management
              result, not an alpha result.
            </p>
            <div className="pl-sig">
              <span>risk-on <b>{rg.extra.pct_risk_on}%</b> of days</span>
              <span><b>{rg.extra.index_trades}</b> index holds</span>
              <span><b>{rg.extra.hunt_trades}</b> pullback trades</span>
            </div>
          </div>

          {/* The split is the whole point: the second half chose nothing. */}
          <div className="mfx-label">Out-of-sample check</div>
          <div className="card pl-trades-wrap">
            <table className="pl-trades pl-bench">
              <thead>
                <tr>
                  <th>Window</th><th>Model CAGR</th><th>SPY CAGR</th>
                  <th>Model DD</th><th>SPY DD</th><th>Risk-on</th>
                </tr>
              </thead>
              <tbody>
                {rg.windows.map((w) => (
                  <tr key={w.window}>
                    <td>{w.window.replace(/_/g, " ")}</td>
                    <td>{w.cagr_pct}%</td>
                    <td>{w.benchmark.cagr_pct}%</td>
                    <td className="pl-good">{w.max_drawdown_pct}%</td>
                    <td className="pl-bad">{w.benchmark.max_drawdown_pct}%</td>
                    <td>{w.pct_risk_on}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mut pl-note" style={{ marginTop: 12, marginBottom: 0 }}>
              The out-of-sample half was used to choose nothing. The model holds
              up there — but it does not beat the index in any window.
            </p>
          </div>

          <div className="mfx-label">Regime model, year by year</div>
          <div className="card pl-trades-wrap">
            <table className="pl-trades pl-bench">
              <thead>
                <tr><th>Year</th><th>Model</th><th>SPY</th><th>Difference</th></tr>
              </thead>
              <tbody>
                {rg.by_year.map((y) => {
                  const d = y.benchmark_pct == null ? null : y.strategy_pct - y.benchmark_pct;
                  return (
                    <tr key={y.year}>
                      <td>{y.year}</td>
                      <td>{y.strategy_pct}%</td>
                      <td>{y.benchmark_pct == null ? "—" : `${y.benchmark_pct}%`}</td>
                      <td className={d == null ? "" : d >= 0 ? "pl-good" : "pl-bad"}>
                        {d == null ? "—" : `${d >= 0 ? "+" : ""}${d.toFixed(1)}`}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="mut pl-note" style={{ marginTop: 12, marginBottom: 0 }}>
              It matches the index in strong bull years because it is simply
              holding it, wins the sustained bears (2018, 2022), and loses to
              whipsaw when a crash reverses fast (2020).
            </p>
          </div>

          <div className="mfx-label">Pullback model on its own</div>
        </>
      )}

      {sw && (
        <>
          <div className={`pl-verdict ${sw.significance.significant ? "ok" : "no"}`}>
            <div className="pl-verdict-tag">
              Swing model · {sw.significance.significant ? "edge is real" : "not proven"}
            </div>
            <p className="pl-verdict-line">
              Buying pullbacks inside uptrends has a statistically real edge
              ({sw.significance.n} trades over {sw.extra.years} years,
              t-stat {sw.significance.t_stat}). But it is a <b>defensive</b> edge,
              not a return-maximising one — over this window it did not beat
              simply owning the index.
            </p>
            <div className="pl-sig">
              <span>expectancy <b>+{sw.metrics.expectancy_r}R</b></span>
              <span>profit factor <b>{sw.metrics.profit_factor}</b></span>
              <span>t-stat <b>{sw.significance.t_stat}</b> <i>(needs 2.0)</i></span>
              <span>avg hold <b>{sw.extra.avg_hold_days}d</b></span>
              <span><b>{sw.extra.trades_per_year}</b> trades/yr</span>
            </div>
          </div>

          <div className="mfx-label">Against just buying the index</div>
          <div className="card pl-trades-wrap">
            <table className="pl-trades pl-bench">
              <thead>
                <tr><th></th><th>Strategy</th><th>{sw.benchmark.symbol || "SPY"} buy &amp; hold</th></tr>
              </thead>
              <tbody>
                <tr><td>Total return</td>
                  <td>{sw.metrics.return_pct}%</td>
                  <td>{sw.benchmark.return_pct}%</td></tr>
                <tr><td>CAGR</td>
                  <td>{sw.extra.cagr_pct}%</td>
                  <td>{sw.benchmark.cagr_pct}%</td></tr>
                <tr><td>Max drawdown</td>
                  <td>{sw.metrics.max_drawdown_pct}%</td>
                  <td>{sw.benchmark.max_drawdown_pct}%</td></tr>
              </tbody>
            </table>
          </div>

          {/* The headline hides the whole character of this thing. */}
          <div className="mfx-label">Where it earns its keep</div>
          <div className="card pl-trades-wrap">
            <table className="pl-trades pl-bench">
              <thead>
                <tr><th>Year</th><th>Strategy</th><th>SPY</th><th>Difference</th></tr>
              </thead>
              <tbody>
                {sw.by_year.map((y) => {
                  const d = y.benchmark_pct == null ? null : y.strategy_pct - y.benchmark_pct;
                  return (
                    <tr key={y.year} className={(d ?? 0) >= 0 ? "up" : "down"}>
                      <td>{y.year}</td>
                      <td>{y.strategy_pct}%</td>
                      <td>{y.benchmark_pct == null ? "—" : `${y.benchmark_pct}%`}</td>
                      <td className={d == null ? "" : d >= 0 ? "pl-good" : "pl-bad"}>
                        {d == null ? "—" : `${d >= 0 ? "+" : ""}${d.toFixed(1)}`}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="mut pl-note" style={{ marginTop: 12, marginBottom: 0 }}>
              It wins when the index falls and lags when it runs. Money at risk
              roughly three days in four; the rest is cash. Survivorship caveat:
              the universe is names liquid enough to still matter today, which
              flatters any long-only backtest.
            </p>
          </div>

          <div className="mfx-label">Day-trading model, for contrast</div>
        </>
      )}

      {!bt && !err && <p className="loading">Replaying 60 sessions…</p>}

      {bt && (
        <>
          {/* The verdict, before anything that looks like a scoreboard. */}
          <div className={`pl-verdict ${proven ? "ok" : "no"}`}>
            <div className="pl-verdict-tag">{proven ? "Edge demonstrated" : "Not cleared for funding"}</div>
            <p className="pl-verdict-line">
              {proven
                ? "The measured edge is statistically distinguishable from luck."
                : "This rule set has no measurable edge on the sample tested. The result is indistinguishable from a coin flip, so nothing here justifies real money yet."}
            </p>
            <div className="pl-sig">
              <span><b>{sig?.n}</b> trades</span>
              <span>expectancy <b>{bt.metrics.expectancy_r ?? "—"}R</b></span>
              <span>t-stat <b>{sig?.t_stat ?? "—"}</b> <i>(needs 2.0)</i></span>
              <span>profit factor <b>{bt.metrics.profit_factor ?? "—"}</b></span>
            </div>
          </div>

          <div className="mfx-label">How it did</div>
          <div className="pl-stats">
            {[
              ["Trades", bt.metrics.trades],
              ["Win rate", `${bt.metrics.win_rate}%`],
              ["Profit factor", bt.metrics.profit_factor ?? "—"],
              ["Expectancy", `${bt.metrics.expectancy_r ?? "—"}R`],
              ["Net", money(Number(bt.metrics.net ?? 0))],
              ["Return", `${bt.metrics.return_pct}%`],
              ["Max drawdown", `${bt.metrics.max_drawdown_pct}%`],
              ["Ending equity", money(Number(bt.metrics.ending_equity ?? 0))],
            ].map(([k, v]) => (
              <div className="pl-stat" key={String(k)}>
                <div className="pl-stat-k">{k}</div>
                <div className="pl-stat-v">{String(v)}</div>
              </div>
            ))}
          </div>

          {/* The part that decides whether forward testing can settle anything. */}
          <div className="mfx-label">Can 2-4 weeks prove this?</div>
          <div className="card pl-power">
            <p>
              The model takes <b>{perSession}</b> trades a session, so two to four
              weeks (10-20 sessions) produces roughly{" "}
              <b>{Math.round(perSession * 10)}-{Math.round(perSession * 20)} trades</b>.
              Single-trade results scatter with a standard deviation of{" "}
              <b>{sig?.sd_r}R</b>.
            </p>
            <p>
              {sessionsNeeded ? (
                <>
                  Resolving an edge the size currently measured at 95% confidence
                  would take about <b>{sig?.trades_needed_for_95pct} trades</b> —
                  roughly <b>{sessionsNeeded} sessions</b>.
                </>
              ) : (
                <>
                  The measured edge is so close to zero that no realistic number
                  of sessions would separate it from noise. That is the finding.
                </>
              )}{" "}
              A good result over 2-4 weeks would be encouraging; it would not be
              evidence.
            </p>
          </div>

          <div className="mfx-label">Why signals did not become trades</div>
          <div className="card">
            <p className="mut pl-note">
              Bar counts, not distinct setups — one setup can trigger on several
              consecutive bars. <b>no_buying_power</b> is the cash-account
              constraint doing its job: the setup was valid and the money was
              either already deployed or still settling.
            </p>
            <div className="pl-blocked">
              {Object.entries(bt.blocked)
                .sort((a, b) => b[1] - a[1])
                .map(([k, v]) => (
                  <div className="pl-b" key={k}>
                    <span className="pl-b-k">{k.replace(/_/g, " ")}</span>
                    <span className="pl-b-v">{v}</span>
                  </div>
                ))}
            </div>
          </div>

          {rules && (
            <>
              <div className="mfx-label">The model</div>
              <div className="card pl-rules">
                <div className="pl-why">
                  <b>Cash account.</b> {rules.account.why} {rules.account.settlement}{" "}
                  {rules.account.budget}
                </div>
                {(["setup", "execution", "risk"] as const).map((k) => (
                  <div className="pl-rule-block" key={k}>
                    <h4>{k}</h4>
                    <ul>
                      {rules[k].map((r) => (
                        <li key={r}>{r}</li>
                      ))}
                    </ul>
                  </div>
                ))}
                <div className="pl-universe">
                  <h4>universe</h4>
                  <p>{rules.universe.join(" · ")}</p>
                </div>
              </div>
            </>
          )}

          <div className="mfx-label">
            Every trade
            <button className="btn ghost pl-rerun" onClick={() => load(true)} disabled={running}>
              {running ? "Replaying…" : "Re-run"}
            </button>
          </div>
          <div className="card pl-trades-wrap">
            <table className="pl-trades">
              <thead>
                <tr>
                  <th>Day</th><th>Symbol</th><th>Entry</th><th>Stop</th>
                  <th>Shares</th><th>Risk</th><th>P/L</th><th>R</th><th>Exit</th>
                </tr>
              </thead>
              <tbody>
                {bt.trades.map((t, i) => (
                  <tr key={i} className={(t.r_multiple ?? 0) >= 0 ? "up" : "down"}>
                    <td>{t.day}</td>
                    <td className="pl-sym">{t.symbol}</td>
                    <td>{t.entry.toFixed(2)}</td>
                    <td>{t.stop.toFixed(2)}</td>
                    <td>{t.shares.toFixed(3)}</td>
                    <td>{money(t.risk_dollars)}</td>
                    <td>{money(t.realized)}</td>
                    <td>{t.r_multiple ?? "—"}</td>
                    <td className="pl-exit">{t.exit_reason}</td>
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
