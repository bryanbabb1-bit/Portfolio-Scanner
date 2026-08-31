"use client";
import { SleeveState } from "../lib/api";
import { usePalette } from "../lib/palette";
import { money } from "./format";

/* Sleeve equity against SPY, rebased to the same starting capital.
 *
 * Rebased rather than raw, because two unrelated squiggles on a shared axis
 * tell you nothing: with both lines starting at the sleeve's capital, the GAP
 * between them is the out- or under-performance, read directly off the chart.
 * Standing rule in this codebase — never show a return without the index
 * beside it, including when the index is winning.
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

  const byDay = new Map(bench.map((b) => [b.day, b.equity]));
  const vals = [...curve.map((c) => c.equity), ...bench.map((b) => b.equity)];
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const pad = (hi - lo) * 0.1 || Math.max(hi * 0.02, 1);
  const y0 = lo - pad;
  const y1 = hi + pad;

  const x = (i: number) => PAD.l + (i / Math.max(curve.length - 1, 1)) * iw;
  const y = (v: number) => PAD.t + ih - ((v - y0) / (y1 - y0)) * ih;

  const sleeveLine = curve
    .map((c, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(c.equity).toFixed(1)}`)
    .join(" ");
  const area =
    `${sleeveLine} L${x(curve.length - 1).toFixed(1)} ${y(y0).toFixed(1)} ` +
    `L${x(0).toFixed(1)} ${y(y0).toFixed(1)} Z`;

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
  const last = curve[curve.length - 1];
  const ahead = state.benchmark_note.includes("ahead of");

  return (
    <div className="card slv-curve">
      <div className="sc-head">
        <span className="mfx-label" style={{ margin: 0 }}>Sleeve vs SPY</span>
        <span className={`sc-note ${ahead ? "up" : "dn"}`}>{state.benchmark_note}</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="sc-svg" role="img"
           aria-label={`Sleeve equity ${money(last.equity, 0)} against SPY. ${state.benchmark_note}`}>
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} stroke={pal.grid} strokeWidth={1} />
            <text x={PAD.l - 8} y={y(t) + 4} textAnchor="end" fontSize={11}
                  fill={pal.muted} fontFamily="var(--font-mono), monospace">
              {money(t, 0)}
            </text>
          </g>
        ))}
        <path d={area} fill={pal.accent} opacity={0.10} />
        {benchLine && (
          <path d={benchLine} fill="none" stroke={pal.muted} strokeWidth={1.5}
                strokeDasharray="5 4" />
        )}
        <path d={sleeveLine} fill="none" stroke={pal.accent} strokeWidth={2} />
        <circle cx={x(curve.length - 1)} cy={y(last.equity)} r={4} fill={pal.accent} />
        <text x={PAD.l} y={H - 8} fontSize={11} fill={pal.muted}
              fontFamily="var(--font-mono), monospace">{curve[0].day}</text>
        <text x={W - PAD.r} y={H - 8} textAnchor="end" fontSize={11} fill={pal.muted}
              fontFamily="var(--font-mono), monospace">{last.day}</text>
      </svg>
      <div className="sc-key">
        <span><span className="sc-swatch sleeve" /> Sleeve</span>
        <span><span className="sc-swatch bench" /> SPY, rebased to the same capital</span>
      </div>
    </div>
  );
}
