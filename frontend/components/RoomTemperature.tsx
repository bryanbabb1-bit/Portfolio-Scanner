"use client";
import { useEffect } from "react";
import { tripletOf, usePalette } from "../lib/palette";

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

export function RoomTemperature({ dayPct }: { dayPct: number | null | undefined }) {
  // The wash takes its hue from the theme's own bull/bear. The paper olive is
  // so dark it would be invisible washed over the after-hours ground; the night
  // palette's lifted siblings are what make the tint read there.
  const pal = usePalette();

  useEffect(() => {
    const root = document.documentElement;
    const pct = dayPct ?? 0;
    const f = pal.heatFlat;

    // Saturate at 3%: beyond that a bigger number doesn't need a redder room.
    const strength = Math.min(1, Math.abs(pct) / 3);
    const rgb =
      Math.abs(pct) < 0.15
        ? `${f.r}, ${f.g}, ${f.b}`
        : tripletOf(pct > 0 ? pal.bull : pal.bear);

    root.style.setProperty("--mood-rgb", rgb);
    // Cap the wash well below where it would fight the text. A dark ground
    // swallows a tint that reads fine on paper, so night gets a little more.
    const base = pal.isNight ? 0.07 : 0.05;
    const span = pal.isNight ? 0.10 : 0.07;
    root.style.setProperty("--mood-alpha", (base + strength * span).toFixed(3));

    return () => {
      root.style.removeProperty("--mood-rgb");
      root.style.removeProperty("--mood-alpha");
    };
  }, [dayPct, pal]);

  return <div className="room-wash" aria-hidden />;
}
