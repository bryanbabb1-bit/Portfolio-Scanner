import { BLUEPRINT } from "../../lib/palette";

/* Big-figure stat tile with a mono caption and the poster's small jagged
   trace underneath. Pass `series` to draw the trace; omit it and the tile
   simply doesn't draw one (we never invent a shape for missing data). */
export function StatTile({
  label,
  value,
  tone = "plain",
  foot,
  series,
}: {
  label: string;
  /** already-formatted display string, e.g. "-13.7%" or "1.42" */
  value: string;
  tone?: "plain" | "pos" | "neg";
  foot?: string;
  series?: number[];
}) {
  return (
    <div className="stat-tile">
      <div className="st-label">{label}</div>
      <div className={`st-value ${tone === "plain" ? "" : tone}`}>{value}</div>
      {foot && <div className="st-foot">{foot}</div>}
      {series && series.length > 1 && (
        <Trace series={series} color={tone === "neg" ? BLUEPRINT.bear : BLUEPRINT.ink} />
      )}
    </div>
  );
}

function Trace({ series, color }: { series: number[]; color: string }) {
  const w = 120;
  const h = 26;
  const min = Math.min(...series);
  const max = Math.max(...series);
  const span = max - min || 1;
  const step = w / (series.length - 1);
  const d = series
    .map((v, i) => {
      const x = (i * step).toFixed(2);
      const y = (h - ((v - min) / span) * (h - 3) - 1.5).toFixed(2);
      return `${i === 0 ? "M" : "L"}${x} ${y}`;
    })
    .join(" ");
  return (
    <svg className="st-spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden>
      <path d={d} fill="none" stroke={color} strokeWidth="1.2" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
