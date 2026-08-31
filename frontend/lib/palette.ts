"use client";
import { useEffect, useState } from "react";

/* Chart/canvas colours, resolved from the LIVE theme.
 *
 * This file used to be a hand-maintained duplicate of the tokens in
 * globals.css, with a comment asking whoever changed one to remember to change
 * the other. That was survivable with a single theme and became a liability the
 * moment After Hours added a second — every canvas would have kept painting in
 * ink on a black ground.
 *
 * So the tokens are now the only source of truth and this reads them off the
 * document at runtime. Anything that wants to follow a theme change calls
 * usePalette(); the exported BLUEPRINT is the paper theme frozen, used as the
 * server-render fallback before there is a DOM to ask.
 */

export type Palette = {
  paper: string; card: string; sunk: string;
  ink: string; muted: string;
  rule: string; hairline: string; grid: string;
  accent: string; olive: string; bull: string; bear: string; gold: string;
  onDark: string;
  heatFlat: RGB; heatUp: RGB; heatDown: RGB;
  /** For the rare case where a whole ramp swaps rather than a single colour. */
  isNight: boolean;
};

export type RGB = { r: number; g: number; b: number };

const rgb = (r: number, g: number, b: number): RGB => ({ r, g, b });

/** The bone room, literal. Also the SSR fallback for every lookup below. */
export const BLUEPRINT: Palette = {
  paper: "#EEEDE8",
  card: "#F7F6F2",
  sunk: "#E4E2DB",
  ink: "#11161C",
  muted: "#6E7680",
  rule: "rgba(17, 22, 28, 0.22)",
  hairline: "rgba(17, 22, 28, 0.09)",
  grid: "rgba(17, 22, 28, 0.09)",
  accent: "#8F7327", // brass
  olive: "#1B2A41", // navy — structural
  bull: "#2E6A4E",
  bear: "#9E3A2C",
  gold: "#8A6A12",
  onDark: "#F7F6F2",
  heatFlat: rgb(110, 118, 128),
  heatUp: rgb(46, 106, 78),
  heatDown: rgb(158, 58, 44),
  isNight: false,
};

/** Parse an "r, g, b" token value. Falls back rather than throwing on a typo. */
function triplet(raw: string, fb: RGB): RGB {
  const n = raw.split(",").map((s) => Number(s.trim()));
  return n.length === 3 && n.every((x) => Number.isFinite(x))
    ? rgb(n[0], n[1], n[2])
    : fb;
}

/** Resolve the palette from whatever theme is currently on <html>. */
export function readPalette(): Palette {
  if (typeof window === "undefined") return BLUEPRINT;
  const cs = getComputedStyle(document.documentElement);
  const v = (name: string, fb: string) => cs.getPropertyValue(name).trim() || fb;
  return {
    paper: v("--bg", BLUEPRINT.paper),
    card: v("--bg-card", BLUEPRINT.card),
    sunk: v("--surface-sunk", BLUEPRINT.sunk),
    ink: v("--text", BLUEPRINT.ink),
    muted: v("--muted", BLUEPRINT.muted),
    rule: v("--rule", BLUEPRINT.rule),
    hairline: v("--hairline", BLUEPRINT.hairline),
    grid: v("--chart-grid", BLUEPRINT.grid),
    accent: v("--accent", BLUEPRINT.accent),
    olive: v("--bull", BLUEPRINT.olive),
    bull: v("--bull", BLUEPRINT.bull),
    bear: v("--bear", BLUEPRINT.bear),
    gold: v("--gold", BLUEPRINT.gold),
    onDark: v("--chart-label", BLUEPRINT.onDark),
    heatFlat: triplet(v("--heat-flat", ""), BLUEPRINT.heatFlat),
    heatUp: triplet(v("--heat-up", ""), BLUEPRINT.heatUp),
    heatDown: triplet(v("--heat-down", ""), BLUEPRINT.heatDown),
    isNight: document.documentElement.getAttribute("data-theme") === "night",
  };
}

/** The live palette, re-read whenever the theme attribute changes. */
export function usePalette(): Palette {
  // Start from the fallback so server and first client paint agree; the effect
  // swaps in the real values immediately after mount.
  const [p, setP] = useState<Palette>(BLUEPRINT);
  useEffect(() => {
    const sync = () => setP(readPalette());
    sync();
    const obs = new MutationObserver(sync);
    obs.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => obs.disconnect();
  }, []);
  return p;
}

/** Translucent fill. Accepts a hex token; passes anything else through. */
export const alpha = (color: string, a: number) => {
  if (!color.startsWith("#")) return color;
  let h = color.slice(1);
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  const n = parseInt(h, 16);
  if (!Number.isFinite(n)) return color;
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
};

/** "r, g, b" from a hex token — for feeding CSS vars that take a bare triplet. */
export const tripletOf = (color: string, fb = "110, 106, 96") => {
  const m = alpha(color, 1).match(/rgba?\(([^)]+?),\s*[\d.]+\)/);
  return m ? m[1] : fb;
};

/** Green→red ramp for heat tiles, eased so an ordinary day is visibly tinted. */
export const heatColor = (metric: number, cap = 5, p: Palette = BLUEPRINT) => {
  const t = Math.max(-1, Math.min(1, metric / cap));
  const target = t >= 0 ? p.heatUp : p.heatDown;
  const k = Math.pow(Math.abs(t), 0.6);
  const mix = (a: number, b: number) => Math.round(a + (b - a) * k);
  const f = p.heatFlat;
  return `rgb(${mix(f.r, target.r)},${mix(f.g, target.g)},${mix(f.b, target.b)})`;
};
