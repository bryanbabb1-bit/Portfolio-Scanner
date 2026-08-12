"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, Debate, PositionPlan } from "../lib/api";
import { ageFrom, isStale, money } from "./format";

/* Desk strip for a stock page: the deterministic sizing (free) plus the
   standing debate ruling if the desk has already sat on this name.

   Deliberately does NOT convene — that costs six model calls, so it links to
   /debate instead of firing on every stock page view. */
export function DeskStrip({ symbol }: { symbol: string }) {
  const [plan, setPlan] = useState<PositionPlan | null>(null);
  const [d, setD] = useState<Debate | null>(null);

  useEffect(() => {
    api.sizePosition(symbol).then(setPlan).catch(() => setPlan(null));
    api.debate(symbol).then(setD).catch(() => setD(null));
  }, [symbol]);

  return (
    <div className="desk-strip">
      <div className="ds-block">
        <span className="ds-label">Risk desk · size</span>
        {plan ? (
          <>
            <b className="ds-val">{plan.dollars ? money(plan.dollars, 0) : "—"}</b>
            <span className="ds-note">{plan.note}</span>
          </>
        ) : (
          <span className="ds-note">Sizing unavailable.</span>
        )}
      </div>

      <div className="ds-block">
        <span className="ds-label">Agent debate</span>
        {d ? (
          <>
            <b className={`ds-val ds-verdict ${d.verdict === "APPROVE" ? "approve" : "reject"}`}>
              {d.action}
            </b>
            <span className="ds-note">
              {d.headline}{" "}
              <Link href={`/debate?symbol=${symbol}`} className="ds-link">
                See the debate →
              </Link>
              {d.ts && (
                <span className={`ds-age${isStale(d.ts) ? " stale" : ""}`}>
                  convened {ageFrom(d.ts)}
                  {isStale(d.ts) ? " · may be dated" : ""}
                </span>
              )}
            </span>
          </>
        ) : (
          <>
            <b className="ds-val ds-idle">Not convened</b>
            <span className="ds-note">
              Five agents haven&apos;t argued this name yet.{" "}
              <Link href={`/debate?symbol=${symbol}`} className="ds-link">
                Convene the desk →
              </Link>
            </span>
          </>
        )}
      </div>
    </div>
  );
}
