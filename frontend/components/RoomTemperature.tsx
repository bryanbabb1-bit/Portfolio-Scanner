"use client";
import { useEffect } from "react";

/* Room temperature — the page carries a faint colour cast from today's P/L.
 *
 * You register the mood before you read the number. Deliberately near the
 * threshold of perception: a red room on a bad day, a green room on a good
 * one, and almost nothing on a flat one. Intensity scales with the move, so a
 * -0.2% session looks like nothing and a -4% session is unmistakable.
 *
 * --mood-rgb already existed in globals.css and several components already
 * read it (the watchdog bar, the radar sweep) — but nothing ever SET it, so
 * every one of them was permanently stuck on the orange default. This wires it.
 */

const OLIVE = "61, 74, 42";
const RUST = "179, 52, 28";
const NEUTRAL = "110, 106, 96";

export function RoomTemperature({ dayPct }: { dayPct: number | null | undefined }) {
  useEffect(() => {
    const root = document.documentElement;
    const pct = dayPct ?? 0;

    // Saturate at 3%: beyond that a bigger number doesn't need a redder room.
    const strength = Math.min(1, Math.abs(pct) / 3);
    const rgb = Math.abs(pct) < 0.15 ? NEUTRAL : pct > 0 ? OLIVE : RUST;

    root.style.setProperty("--mood-rgb", rgb);
    // Cap the wash well below where it would fight the text on paper.
    root.style.setProperty("--mood-alpha", (0.05 + strength * 0.07).toFixed(3));

    return () => {
      root.style.removeProperty("--mood-rgb");
      root.style.removeProperty("--mood-alpha");
    };
  }, [dayPct]);

  return <div className="room-wash" aria-hidden />;
}
