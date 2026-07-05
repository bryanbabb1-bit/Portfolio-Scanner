"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, Recommendation } from "../lib/api";
import { BulletList } from "./BulletList";

const ACTION_CLASS: Record<string, string> = {
  BUY: "buy", ADD: "buy", TRIM: "sell", SELL: "sell", AVOID: "sell", HOLD: "hold",
};

// The advisor's answer to "so what do I do?" for a notification/alert. Opens
// as a slap; fetches a portfolio-aware recommendation (may be HOLD, but the
// analysis is always done).
export function RecoSlap({
  symbol,
  event,
  kind = "alert",
  onClose,
}: {
  symbol: string;
  event: string;
  kind?: string;
  onClose: () => void;
}) {
  const [reco, setReco] = useState<Recommendation | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api
      .recommend(symbol, event, kind)
      .then((r) => live && setReco(r))
      .catch((e) => live && setErr(e.message || "Advisor unavailable"));
    return () => {
      live = false;
    };
  }, [symbol, event, kind]);

  const cls = reco ? ACTION_CLASS[reco.action] || "hold" : "hold";
  const buy = cls === "buy";

  return (
    <div className="slap-overlay" role="alertdialog" onClick={onClose}>
      <div className={`slap-card ${buy ? "buy" : cls === "sell" ? "sell" : "hold"}`} onClick={(e) => e.stopPropagation()}>
        <div className={`slap-banner ${buy ? "buy" : cls === "sell" ? "sell" : "hold"}`}>
          ADVISOR RECOMMENDATION
        </div>
        <div className="slap-head">
          <span className="slap-sym">{symbol}</span>
          <span className="mut" style={{ fontSize: 13 }}>{event}</span>
        </div>

        {!reco && !err && <p className="loading">Analyzing your position… (~10-20s)</p>}
        {err && <div className="err">{err}</div>}

        {reco && (
          <>
            <div className="reco-verdict">
              <span className={`reco-action ${cls}`}>{reco.action}</span>
              <span className="reco-headline">{reco.headline}</span>
            </div>
            <div className="slap-sec">
              <h4>What to do</h4>
              <p>{reco.what}</p>
            </div>
            {reco.why.length > 0 && (
              <div className="slap-sec">
                <h4>Why</h4>
                <BulletList items={reco.why} kind="insight" />
              </div>
            )}
            {(reco.target || reco.stop) && (
              <div className="slap-levels">
                <div className="slap-level">
                  <span className="label">Level that matters</span>
                  <span>{reco.target || "—"}</span>
                </div>
                <div className="slap-level">
                  <span className="label">Invalidation / stop</span>
                  <span>{reco.stop || "—"}</span>
                </div>
              </div>
            )}
            <p className="mut" style={{ fontSize: 11, marginTop: 10 }}>
              {reco.engine === "claude" ? "Senior advisor" : "Automated"} · {reco.generated_at} · Not personalized investment advice.
            </p>
          </>
        )}

        <div className="slap-actions">
          <Link href={`/stock/${symbol}`} className="btn" onClick={onClose}>Open {symbol}</Link>
          <button className="btn ghost" onClick={onClose}>Got it</button>
        </div>
      </div>
    </div>
  );
}
