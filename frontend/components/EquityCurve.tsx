"use client";
import { BacktestCurvePoint } from "../lib/api";

/* Strategy equity vs benchmark — the 04/08 chart. Inline SVG, no chart lib. */
export function EquityCurve({
  points,
  totalReturn,
}: {
  points: BacktestCurvePoint[];
  totalReturn?: number;
}) {
  if (points.length < 2) return null;

  const W = 900;
  const H = 340;
  const PAD = { t: 18, r: 16, b: 30, l: 58 };
  const iw = W - PAD.l - PAD.r;
  const ih = H - PAD.t - PAD.b;

  const vals = points.flatMap((p) => [p.strategy, p.benchmark]);
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const pad = (hi - lo) * 0.08 || 0.1;
  const y0 = lo - pad;
  const y1 = hi + pad;

  const x = (i: number) => PAD.l + (i / (points.length - 1)) * iw;
  const y = (v: number) => PAD.t + ih - ((v - y0) / (y1 - y0)) * ih;

  const line = (key: "strategy" | "benchmark") =>
    points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(p[key]).toFixed(1)}`).join(" ");

  const area =
    `${line("strategy")} L${x(points.length - 1).toFixed(1)} ${y(y0).toFixed(1)} ` +
    `L${x(0).toFixed(1)} ${y(y0).toFixed(1)} Z`;

  // Gridlines at round multiples of starting capital.
  const ticks: number[] = [];
  const step = (y1 - y0) / 4;
  for (let i = 0; i <= 4; i++) ticks.push(y0 + step * i);

  const years = new Map<string, number>();
  points.forEach((p, i) => {
    const yr = p.date.slice(0, 4);
    if (!years.has(yr)) years.set(yr, i);
  });

  const peak = points.reduce(
    (best, p, i) => (p.strategy > points[best].strategy ? i : best),
    0
  );

  return (
    <svg className="equity-curve" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Equity curve">
      {ticks.map((t) => (
        <g key={t}>
          <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} className="eq-grid" />
          <text x={PAD.l - 9} y={y(t) + 4} className="eq-ylab">
            {t.toFixed(2)}x
          </text>
        </g>
      ))}

      {[...years.entries()].map(([yr, i]) => (
        <text key={yr} x={x(i)} y={H - 9} className="eq-xlab">
          {yr}
        </text>
      ))}

      <path d={area} style={{ fill: "var(--bull)", fillOpacity: 0.12 }} stroke="none" />
      <path d={line("benchmark")} className="eq-bench" />
      <path d={line("strategy")} className="eq-strat" />

      {totalReturn != null &&
        (() => {
          // The peak is usually at the top-right, so an unclamped callout
          // hangs off both edges. Keep the whole box inside the plot area.
          const CW = 116;
          const CH = 40;
          const px = x(peak);
          const py = y(points[peak].strategy);
          const cx = Math.min(Math.max(px - CW / 2, PAD.l + 2), W - PAD.r - CW - 2);
          // Prefer above the point; drop below when there isn't room.
          const cy = py - CH - 12 >= PAD.t ? py - CH - 12 : py + 14;
          return (
            <g>
              <circle cx={px} cy={py} r="3.5" className="eq-dot" />
              <line x1={px} y1={py} x2={cx + CW / 2} y2={cy < py ? cy + CH : cy} className="eq-lead" />
              <rect x={cx} y={cy} width={CW} height={CH} className="eq-callout" />
              <text x={cx + CW / 2} y={cy + 15} className="eq-callout-k">
                TOTAL RETURN
              </text>
              <text x={cx + CW / 2} y={cy + 32} className="eq-callout-v">
                {totalReturn >= 0 ? "+" : ""}
                {totalReturn.toFixed(1)}%
              </text>
            </g>
          );
        })()}

      <g transform={`translate(${PAD.l + 8}, ${PAD.t + 12})`}>
        <line x1="0" x2="18" y1="0" y2="0" className="eq-strat" />
        <text x="24" y="4" className="eq-legend">
          STRATEGY
        </text>
        <line x1="0" x2="18" y1="15" y2="15" className="eq-bench" />
        <text x="24" y="19" className="eq-legend">
          BUY &amp; HOLD (SPY)
        </text>
      </g>
    </svg>
  );
}
