"use client";
import { SleeveState } from "../lib/api";
import { usePalette } from "../lib/palette";
import { money } from "./format";

/* Profit against SPY. Both lines are DOLLARS EARNED and both start at zero.
 *
 * They used to be equity levels, and funding the sleeve from $1,640 to $2,000
 * drew a 22% leap that was a bank transfer, not a trade. Plotting profit makes
 * a deposit invisible to the chart, which is the only honest way to answer
 * "is this working" while capital is still moving around.
 *
 * The zero line is drawn heavier than the grid on purpose: above it the sleeve
 * has made money, below it has lost, and that is the first thing to read.
 *
 * Inline SVG, theme-aware through the palette tokens, no chart library.
 */
export function SleeveCurve({ state }: { state: SleeveState }) {
  const pal = usePalette();
  const curve = state.equity_history ?? [];
  const bench = state.benchmark ?? [];

  if (curve.length < 2) {
    return (
      <div className="card slv-curve-empty">
        <span className="mut">
          The curve starts once the sleeve has marked two days. It marks once a session,
          and SPY is drawn beside it from the same days.
        </span>
      </div>
    );
  }

  const W = 900;
  const H = 260;
  const PAD = { t: 16, r: 14, b: 26, l: 60 };
  const iw = W - PAD.l - PAD.r;
  const ih = H - PAD.t - PAD.b;

  // Both series come from the benchmark payload so they are computed the same
  // way server-side and cannot drift apart.
  if (bench.length < 2) {
    return (
      <div className="card slv-curve-empty">
        <span className="mut">{state.benchmark_note}</span>
      </div>
    );
  }
  const byDay = new Map(bench.map((b) => [b.day, b.equity]));
  const mine = new Map(bench.map((b) => [b.day, b.sleeve]));
  const vals = [...bench.map((b) => b.equity), ...bench.map((b) => b.sleeve), 0];
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const pad = (hi - lo) * 0.15 || 1;
  const y0 = lo - pad;
  const y1 = hi + pad;

  const x = (i: number) => PAD.l + (i / Math.max(curve.length - 1, 1)) * iw;
  const y = (v: number) => PAD.t + ih - ((v - y0) / (y1 - y0)) * ih;

  let openedSleeve = false;
  const sleeveLine = curve
    .map((c, i) => {
      const v = mine.get(c.day);
      if (v == null) return "";
      const cmd = openedSleeve ? "L" : "M";
      openedSleeve = true;
      return `${cmd}${x(i).toFixed(1)} ${y(v).toFixed(1)}`;
    })
    .filter(Boolean)
    .join(" ");
  const area =
    `${sleeveLine} L${x(curve.length - 1).toFixed(1)} ${y(0).toFixed(1)} ` +
    `L${x(0).toFixed(1)} ${y(0).toFixed(1)} Z`;

  // The benchmark is drawn on the sleeve's own x-positions so a market holiday
  // in one series cannot shear the two apart.
  let started = false;
  const benchLine = curve
    .map((c, i) => {
      const v = byDay.get(c.day);
      if (v == null) return "";
      const cmd = started ? "L" : "M";
      started = true;
      return `${cmd}${x(i).toFixed(1)} ${y(v).toFixed(1)}`;
    })
    .filter(Boolean)
    .join(" ");

  const ticks = [0, 1, 2, 3].map((i) => y0 + ((y1 - y0) / 3) * i);
  const last = bench[bench.length - 1];
  const ahead = state.benchmark_note.includes("ahead of");

  return (
    <div className="card slv-curve">
      <div className="sc-head">
        <span className="mfx-label" style={{ margin: 0 }}>Profit vs SPY · dollars earned</span>
        <span className={`sc-note ${ahead ? "up" : "dn"}`}>{state.benchmark_note}</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="sc-svg" role="img"
           aria-label={`Sleeve profit ${money(last.sleeve, 0)} against SPY. ${state.benchmark_note}`}>
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} stroke={pal.grid} strokeWidth={1} />
            <text x={PAD.l - 8} y={y(t) + 4} textAnchor="end" fontSize={11}
                  fill={pal.muted} fontFamily="var(--font-mono), monospace">
              {t >= 0 ? `+${money(t, 0)}` : money(t, 0)}
            </text>
          </g>
        ))}
        <path d={area} fill={pal.accent} opacity={0.10} />
        {/* Breakeven, drawn heavier than the grid: above it you made money. */}
        <line x1={PAD.l} x2={W - PAD.r} y1={y(0)} y2={y(0)}
              stroke={pal.muted} strokeWidth={1.5} opacity={0.7} />
        {benchLine && (
          <path d={benchLine} fill="none" stroke={pal.muted} strokeWidth={1.5}
                strokeDasharray="5 4" />
        )}
        <path d={sleeveLine} fill="none" stroke={pal.accent} strokeWidth={2} />
        <circle cx={x(curve.length - 1)} cy={y(last.sleeve)} r={4} fill={pal.accent} />
        <text x={PAD.l} y={H - 8} fontSize={11} fill={pal.muted}
              fontFamily="var(--font-mono), monospace">{curve[0].day}</text>
        <text x={W - PAD.r} y={H - 8} textAnchor="end" fontSize={11} fill={pal.muted}
              fontFamily="var(--font-mono), monospace">{last.day}</text>
      </svg>
      <div className="sc-key">
        <span><span className="sc-swatch sleeve" /> Sleeve profit</span>
        <span><span className="sc-swatch bench" /> SPY on the same capital</span>
      </div>
    </div>
  );
}
