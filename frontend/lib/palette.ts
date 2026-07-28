/* Single source of truth for chart/canvas colours.
   CSS gets these from the tokens in globals.css; canvas and inline-SVG can't
   read CSS variables cheaply, so they import from here instead of hardcoding.
   Keep the two in sync — if you change a token, change it here too. */
export const BLUEPRINT = {
  paper: "#F2EEE4",
  card: "#FAF7F0",
  sunk: "#E9E3D5",
  ink: "#14140F",
  muted: "#6B6558",
  rule: "rgba(20, 20, 15, 0.34)",
  hairline: "rgba(20, 20, 15, 0.12)",
  grid: "rgba(20, 20, 15, 0.10)",
  accent: "#C4551F", // orange
  olive: "#3D4A2A", // system / positive
  bull: "#3D4A2A",
  bear: "#B3341C",
  gold: "#8A6D1F",
  onDark: "#FAF7F0",
} as const;

/** Translucent fills for area charts and heat tiles. */
export const alpha = (hex: string, a: number) => {
  const h = hex.replace("#", "");
  const n = parseInt(h, 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
};

/** Green→red ramp for the holdings heatmap, in the blueprint's ink range. */
export const heatColor = (pct: number, cap = 5) => {
  const t = Math.max(-1, Math.min(1, pct / cap));
  return t >= 0
    ? alpha(BLUEPRINT.olive, 0.25 + 0.62 * t)
    : alpha(BLUEPRINT.bear, 0.25 + 0.62 * -t);
};
