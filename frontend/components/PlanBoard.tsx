"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, GamePlanData, PlanIdea, PlanMove } from "../lib/api";
import { money } from "./format";

// THE SEQUENCED PLAN — every staged move reconciled into ready-now vs
// waiting-on, with each move's price gate and funding dependency spelled out
// so the moves stop reading as independent silos.
export function PlanBoard() {
  const [data, setData] = useState<GamePlanData | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = () => api.plan().then((d) => { setData(d); setErr(null); }).catch((e) => setErr(e.message));
  useEffect(() => {
    load();
    const t = setInterval(load, 60_000);
    return () => clearInterval(t);
  }, []);

  const clear = async (m: PlanMove) => {
    setData((d) => d && {
      ...d,
      ready: d.ready.filter((x) => x.id !== m.id),
      waiting: d.waiting.filter((x) => x.id !== m.id),
      guards: d.guards.filter((x) => x.id !== m.id),
    });
    try {
      if (m.source === "pin" && m.pin_id) await api.deletePin(m.pin_id);
      else if (m.source === "trigger" && m.wp_id) await api.deleteWatchpoint(m.wp_id);
    } catch { load(); }
  };

  const pinIdea = async (idea: PlanIdea) => {
    // optimistic: drop it from the ideas list; it reappears as a staged move
    setData((d) => d && { ...d, ideas: d.ideas.filter((x) => x.id !== idea.id) });
    try {
      await api.addPin({ symbol: idea.symbol, source: "idea", text: idea.order });
      load();
    } catch { load(); }
  };

  const chip = (m: PlanMove) =>
    m.stop ? "STOP" : m.side === "buy" ? "BUY" : m.side === "sell" ? "SELL" : "HOLD";

  const Row = ({ m }: { m: PlanMove }) => (
    <div className={`plan-move ${m.stop ? "stop" : m.side}`}>
      <span className={`signal-side ${m.stop ? "stop" : m.side}`}>{chip(m)}</span>
      <div className="pm-body">
        <div className="pm-order">
          {m.symbol && <Link href={`/stock/${m.symbol}`} className="pm-sym">{m.symbol}</Link>}
          {m.text}
        </div>
        <div className="pm-meta">
          {m.gate && !m.gate.met && (
            <span className={`gp-dist${Math.abs(m.gate.distance_pct) <= 2 ? " hot" : ""}`}>
              {Math.abs(m.gate.distance_pct).toFixed(1)}{m.gate.rsi ? " pts" : "%"} away
            </span>
          )}
          {m.funded_by && <span className="pm-fund">funded by {m.funded_by} trim</span>}
          {m.wait_reason && <span className="pm-reason">{m.wait_reason}</span>}
          {m.status === "ready" && !m.wait_reason && <span className="pm-go">ready to act</span>}
        </div>
      </div>
      {(m.source === "pin" || m.source === "trigger") && (
        <button className="icon-btn jr-btn" title="Clear this from the plan" onClick={() => clear(m)}>✕</button>
      )}
    </div>
  );

  return (
    <div className="card plan" id="game-plan">
      <div className="section-title" style={{ marginBottom: 12 }}>Do this</div>

      {err && <div className="err" style={{ marginBottom: 10 }}>{err}</div>}

      {data && (
        <>
          {/* capital meter — risk capital available to put to work */}
          <div className="plan-fund">
            <div className="pf-top">
              <span>Dry powder to deploy <b>{money(data.dry_powder, 0)}</b></span>
              {data.queued_buys > 0 && <span className="pf-floor">{money(data.queued_buys, 0)} queued</span>}
            </div>
            {data.queued_buys > 0 && (
              <div className="pf-bar">
                <div className={`pf-fill${!data.fits ? " low" : ""}`}
                     style={{ width: `${Math.min(100, data.dry_powder > 0 ? (data.queued_buys / data.dry_powder) * 100 : 100)}%` }} />
              </div>
            )}
            <div className="pf-note">
              {data.queued_buys === 0
                ? <>{money(data.dry_powder, 0)} of risk capital ready to put to work.</>
                : data.fits
                  ? <><b>{money(data.dry_powder, 0)}</b> to deploy · {money(data.queued_buys, 0)} queued · {money(data.leftover, 0)} left after.</>
                  : <>Queued buys ({money(data.queued_buys, 0)}) top your {money(data.dry_powder, 0)} cash by <b>{money(data.over_by, 0)}</b> — prioritize{data.funders[0] ? <>, or the <b>{data.funders[0]} trim</b> funds the rest</> : ""}.</>}
            </div>
          </div>

          {/* ready now */}
          <div className="plan-group">
            <div className="pg-label ready">Ready now</div>
            {data.ready.length
              ? data.ready.map((m) => <Row key={m.id} m={m} />)
              : <div className="pg-empty">Nothing to act on yet — every move is waiting on a gate below.</div>}
          </div>

          {/* waiting */}
          {data.waiting.length > 0 && (
            <div className="plan-group">
              <div className="pg-label wait">Waiting on…</div>
              {data.waiting.map((m) => <Row key={m.id} m={m} />)}
            </div>
          )}

          {/* the advisor's fresh ideas — pin one to add it to your plan above */}
          {data.ideas.length > 0 && (
            <div className="plan-group">
              <div className="pg-label idea">Ideas to act on · the advisor's best calls</div>
              {data.ideas.map((idea) => (
                <div key={idea.id} className="plan-move idea">
                  <span className={`signal-side ideatag ${idea.tag}`}>{idea.tag === "spec" ? "SPEC" : "CONV"}</span>
                  <div className="pm-body">
                    <div className="pm-order">
                      <Link href={`/stock/${idea.symbol}`} className="pm-sym">{idea.symbol}</Link>
                      {idea.order}
                    </div>
                    <div className="pm-meta">
                      {idea.size && <span className="idea-chip">{idea.size}</span>}
                      {idea.entry && <span className="idea-chip">entry {idea.entry}</span>}
                      {idea.target && <span className="idea-chip up">target {idea.target}</span>}
                    </div>
                  </div>
                  <button className="idea-pin" title="Add to your plan" onClick={() => pinIdea(idea)}>+ Plan</button>
                </div>
              ))}
            </div>
          )}

          {data.count === 0 && data.ideas.length === 0 && (
            <div className="pg-empty">No moves staged. Pin advice from a brief or arm a trigger to build your plan.</div>
          )}
        </>
      )}
    </div>
  );
}
