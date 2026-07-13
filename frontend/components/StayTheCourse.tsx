"use client";
import { useEffect, useState } from "react";
import { api, StayCourse } from "../lib/api";
import { money } from "./format";

/* Stay the Course — one dependable place to get EARNED permission to hold.
   When the book is steady it reassures with real facts (thesis intact, goal
   progress, positions held from their lows, gains booked); when something
   genuinely needs action it says so and points to the plan. Alerts are
   untouched — this only frames the quiet, which is when impatience bites. */

export function StayTheCourse() {
  const [data, setData] = useState<StayCourse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let live = true;
    const load = () =>
      api.stayTheCourse().then((d) => { if (live) { setData(d); setLoading(false); } });
    load();
    const t = setInterval(load, 120_000);
    return () => { live = false; clearInterval(t); };
  }, []);

  if (loading) return <div className="stc card stc-load">Reading the long game…</div>;
  if (!data) return null;

  const hold = data.posture === "hold";
  const g = data.metrics?.goal;

  return (
    <div className={`stc card ${hold ? "hold" : "act"}`}>
      <div className="stc-top">
        <span className="stc-tag">{hold ? "Stay the course" : "Action needed"}</span>
        {g && (
          <span className="stc-goal">
            {g.progress_pct.toFixed(0)}% to {money(g.target, 0)}
          </span>
        )}
      </div>

      <div className="stc-headline">{data.headline}</div>

      <ul className="stc-reasons">
        {data.reasons.map((r, i) => (
          <li key={i}><span className="stc-dot" />{r}</li>
        ))}
      </ul>

      {data.closer && <div className="stc-closer">{data.closer}</div>}

      <div className="stc-foot">
        {hold
          ? "You'll still get alerted the moment a plan actually changes."
          : "Handle what's flagged below — the rest of the book holds."}
      </div>
    </div>
  );
}
