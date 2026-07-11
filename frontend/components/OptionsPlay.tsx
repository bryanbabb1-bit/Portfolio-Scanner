"use client";
import { useEffect, useState } from "react";
import { api, OptionsIdea } from "../lib/api";
import { money } from "./format";

// Defined-risk options play for a name: a long call (bullish) or put (bearish),
// aligned to the advisor's stance. Max loss = premium, shown up front. The
// deterministic trade loads immediately; the advisor's read is on demand.
export function OptionsPlay({ symbol }: { symbol: string }) {
  const [side, setSide] = useState<"call" | "put">("call");
  const [data, setData] = useState<OptionsIdea | null>(null);
  const [loading, setLoading] = useState(true);
  const [thesisLoading, setThesisLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    setData(null);
    api.optionsIdea(symbol, side).then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }, [symbol, side]);

  const getThesis = () => {
    setThesisLoading(true);
    api.optionsThesis(symbol, side).then(setData).catch(() => {}).finally(() => setThesisLoading(false));
  };

  const t = data?.trade;
  return (
    <div className="card options-card" style={{ marginBottom: 24 }}>
      <div className="chart-head" style={{ marginBottom: 12 }}>
        <div className="section-title" style={{ margin: 0 }}>
          Options play <span className="mut" style={{ textTransform: "none", letterSpacing: 0 }}>· defined risk, no shares</span>
        </div>
        <div className="range-toggle">
          <button className={side === "call" ? "active" : ""} onClick={() => setSide("call")}>Call (bullish)</button>
          <button className={side === "put" ? "active" : ""} onClick={() => setSide("put")}>Put (bearish)</button>
        </div>
      </div>

      {loading ? (
        <div className="mut">Scanning the option chain…</div>
      ) : !t ? (
        <div className="mut">No liquid {side} market for {symbol} right now — try the other side, or the chain data is thin.</div>
      ) : (
        <>
          <div className="opt-headline">
            Buy the <b>{t.expiration} ${t.strike} {side}</b> at ~<b>${t.premium}</b>
            <span className="mut"> · {t.dte} days · Δ{t.delta} · IV {t.iv_pct}%</span>
          </div>
          <div className="opt-grid">
            <div className="opt-cell">
              <span className="l">Max risk (capped)</span>
              <span className="v neg">{money(t.cost_per_contract, 0)}<span className="mut" style={{ fontSize: 11, fontWeight: 400 }}> /contract</span></span>
            </div>
            <div className="opt-cell"><span className="l">Breakeven</span><span className="v">${t.breakeven}</span></div>
            <div className="opt-cell"><span className="l">Open interest</span><span className="v">{t.open_interest.toLocaleString()}</span></div>
            {t.value_at_target != null && data && (
              <>
                <div className="opt-cell"><span className="l">If it hits ${data.target}</span><span className="v pos">{money(t.value_at_target, 0)}</span></div>
                <div className="opt-cell"><span className="l">Return</span><span className="v pos">~{t.return_at_target_x}x</span></div>
              </>
            )}
          </div>
          <div className="mut" style={{ fontSize: 12, marginTop: 8, lineHeight: 1.5 }}>
            Max loss is the {money(t.cost_per_contract, 0)} premium — no share assignment, no exercise needed.
            {data?.stance ? <> Aligned to your standing <b>{data.stance}</b> call</> : null}{data ? <> · target ${data.target}.</> : null}
          </div>

          {data?.advice ? (
            <div className="opt-advice">
              <div className="oa-row"><span className="oa-k">Thesis</span><span>{data.advice.thesis}</span></div>
              {data.advice.contract && <div className="oa-row"><span className="oa-k">This contract</span><span>{data.advice.contract}</span></div>}
              <div className="oa-row"><span className="oa-k">Sizing</span><span>{data.advice.sizing}</span></div>
              <div className="oa-row"><span className="oa-k">Risk</span><span>{data.advice.risk}</span></div>
            </div>
          ) : (
            <button className="btn ghost" style={{ marginTop: 12 }} onClick={getThesis} disabled={thesisLoading}>
              {thesisLoading ? "Thinking…" : "Get the advisor's read"}
            </button>
          )}
        </>
      )}
    </div>
  );
}
