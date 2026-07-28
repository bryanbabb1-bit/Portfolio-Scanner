"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, RiskDesk } from "../../lib/api";
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
import "./risk.css";

/* Risk Desk — sheet 05/08.
   Everything here is deterministic: no AI, no narrative. It answers "how much,
   where's the exit, and how much is already on the table". */

const FLOW = [
  {
    n: "01",
    title: "Position Size",
    body: "Size from the stop distance and the risk budget, not from conviction. A wider stop buys a smaller position.",
  },
  {
    n: "02",
    title: "Stop Loss",
    body: "Every exit is defined before entry — the tighter of a 2x ATR stop and the 200-day.",
  },
  {
    n: "03",
    title: "Daily Limits",
    body: "A hard loss limit for the session. Hit it and the desk stops taking new risk.",
  },
  {
    n: "04",
    title: "Portfolio Risk",
    body: "Total open risk from every position down to its stop, plus how correlated those bets really are.",
  },
  {
    n: "05",
    title: "Capital Allocation",
    body: "How much of the book is deployed against how much is held back as dry powder.",
  },
];

const RULES = [
  "Never risk more than you can afford to lose.",
  "Cut losses fast. Let winners run.",
  "Protect the portfolio, not the position.",
  "Consistency beats high returns.",
];

export default function RiskPage() {
  const [d, setD] = useState<RiskDesk | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.risk().then(setD).catch((e) => setErr(e.message));
  }, []);

  if (err) return <div className="err">Risk desk unavailable ({err}).</div>;
  if (!d) return <div className="loading">Computing open risk…</div>;

  const statusTone =
    d.status === "BREACHED" ? "breached" : d.status === "ELEVATED" ? "elevated" : "protected";

  // How much of today's loss allowance is already spent.
  const limitUsed =
    d.daily_loss_limit_amount > 0 && d.day_pl < 0
      ? Math.min(100, (Math.abs(d.day_pl) / d.daily_loss_limit_amount) * 100)
      : 0;

  return (
    <>
      <SpecHeader system="RISK DESK" version="2.0" />
      <SheetRule mark="05 / 08" />

      <div className="risk-top">
        <div>
          <DisplayHead
            line1="Risk always"
            line2="comes first."
            tone="hot"
            sub={
              <>
                Protect capital
                <br />
                <span className="hot">before chasing returns.</span>
              </>
            }
          />

          <SpecPanel title="Risk Status" className="risk-status">
            <div className={`rs-badge ${statusTone}`}>
              <Shield />
              {d.status}
            </div>
            <dl className="rs-rows">
              <Row
                k="Portfolio risk"
                v={d.portfolio_risk_pct != null ? `${d.portfolio_risk_pct.toFixed(2)}%` : "—"}
              />
              <Row k="Daily loss limit" v={`${d.daily_loss_limit_pct.toFixed(2)}%`} />
              <Row k="Exposure utilization" v={`${d.exposure_utilization_pct.toFixed(0)}%`} />
              <Row k="Risk budget / trade" v={money(d.risk_budget_amount, 0)} />
            </dl>
          </SpecPanel>

          <SpecPanel title="Risk Rules" className="risk-rules">
            <ul className="rr-list">
              {RULES.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </SpecPanel>
        </div>

        {/* the 01-05 flow */}
        <ol className="risk-flow">
          {FLOW.map((s, i) => (
            <li key={s.n}>
              <SpecPanel plus={false}>
                <span className="step-num rf-n">{s.n}</span>
                <h3 className="rf-title">{s.title}</h3>
                <div className="dh-rule rf-rule" />
                <p className="rf-body">{s.body}</p>
                {s.n === "01" && (
                  <p className="rf-live">
                    {money(d.risk_budget_amount, 0)} per trade
                    <span className="mut"> · {d.risk_per_trade_pct}% of {money(d.equity, 0)}</span>
                  </p>
                )}
                {s.n === "03" && (
                  <>
                    <div className="rf-limit">
                      <div className="rfl-track">
                        <div
                          className={`rfl-fill ${limitUsed >= 100 ? "over" : ""}`}
                          style={{ width: `${limitUsed}%` }}
                        />
                      </div>
                      <p className="rf-live">
                        Today {money(d.day_pl, 0)} ({pct(d.day_pl_pct)})
                        <span className="mut"> of {money(d.daily_loss_limit_amount, 0)} allowed</span>
                      </p>
                    </div>
                    {d.limit_breached && (
                      <p className="rf-breach">Limit breached — no new risk today.</p>
                    )}
                  </>
                )}
                {s.n === "04" && d.portfolio_risk_amount != null && (
                  <p className="rf-live">
                    {money(d.portfolio_risk_amount, 0)} open
                    <span className="mut">
                      {" "}
                      · {d.portfolio_risk_pct?.toFixed(2)}% of equity
                      {d.avg_correlation != null && ` · corr ${d.avg_correlation.toFixed(2)}`}
                    </span>
                  </p>
                )}
                {s.n === "05" && (
                  <p className="rf-live">
                    {money(d.invested, 0)} deployed
                    <span className="mut"> · {money(d.cash, 0)} dry powder</span>
                  </p>
                )}
              </SpecPanel>
              {i < FLOW.length - 1 && <span className="rf-arrow">↓</span>}
            </li>
          ))}
        </ol>
      </div>

      {/* per-position open risk */}
      <SpecPanel
        title="Open Risk by Position"
        aux={`${d.positions.length} positions`}
        className="risk-book"
      >
        <div className="rb-row rb-head">
          <span>Symbol</span>
          <span>Value</span>
          <span>Weight</span>
          <span>Stop</span>
          <span>Basis</span>
          <span>Distance</span>
          <span>At risk</span>
        </div>
        {d.positions.map((p) => (
          <Link key={p.symbol} href={`/stock/${p.symbol}`} className={`rb-row ${p.over_size ? "over" : ""}`}>
            <span className="rb-sym">{p.symbol}</span>
            <span>{money(p.market_value, 0)}</span>
            <span>{p.weight_pct.toFixed(1)}%</span>
            <span>{p.stop != null ? money(p.stop) : <em className="mut">none</em>}</span>
            <span className="mut">{p.stop_basis ?? "—"}</span>
            <span>{p.stop_distance_pct != null ? `${p.stop_distance_pct.toFixed(1)}%` : "—"}</span>
            <span className="rb-risk">
              {p.risk_amount != null ? money(p.risk_amount, 0) : "—"}
            </span>
          </Link>
        ))}
      </SpecPanel>

      {/* the overview strip */}
      <div className="section-title" style={{ marginTop: 26 }}>
        Risk overview
      </div>
      <div className="tile-row">
        <StatTile
          label="Max drawdown"
          value={d.max_drawdown_pct != null ? `${d.max_drawdown_pct.toFixed(1)}%` : "—"}
          tone={d.max_drawdown_pct != null ? "neg" : "plain"}
          foot="Worst peak-to-trough, 1 year"
        />
        <StatTile
          label="VaR (95%)"
          value={d.var95_pct != null ? `${d.var95_pct.toFixed(2)}%` : "—"}
          tone={d.var95_pct != null ? "neg" : "plain"}
          foot={
            d.var95_amount != null
              ? `${money(d.var95_amount, 0)} on a bad day`
              : `Needs more history`
          }
        />
        <StatTile
          label="Beta"
          value={d.beta != null ? d.beta.toFixed(2) : "—"}
          foot="vs SPY, 6 months"
        />
        <StatTile
          label="Correlation"
          value={d.avg_correlation != null ? d.avg_correlation.toFixed(2) : "—"}
          foot="Average pairwise"
        />
        <StatTile label="Liquidity" value={d.liquidity ?? "—"} foot="Median dollar volume" />
      </div>

      {d.notes.length > 0 && (
        <SpecEmpty>
          <b>Reported honestly:</b>
          <ul className="rn-list">
            {d.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </SpecEmpty>
      )}

      <TelemetryStrip
        left={[
          ["Sample", `${d.history_days}D`],
          ["Source", d.source.toUpperCase()],
          ["Model", "NONE"],
        ]}
        right={[
          ["Stop", "2.0x ATR"],
          ["Risk/trade", `${d.risk_per_trade_pct}%`],
          ["Cap", "25%"],
        ]}
        line1="Your edge means nothing without capital."
        line2="Survive to win."
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

function Shield() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden>
      <path d="M12 2.5 20 6v6c0 4.6-3.2 8.5-8 9.6-4.8-1.1-8-5-8-9.6V6l8-3.5Z" />
      <path d="m8.6 12 2.4 2.4 4.4-4.6" />
    </svg>
  );
}
