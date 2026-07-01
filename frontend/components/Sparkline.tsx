// Tiny inline-SVG sparkline for card previews. Colors by net direction.
export function Sparkline({
  data,
  width = 96,
  height = 30,
}: {
  data?: number[];
  width?: number;
  height?: number;
}) {
  if (!data || data.length < 2) {
    return <div className="spark-empty" style={{ width, height }} />;
  }
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const n = data.length;
  const x = (i: number) => (i / (n - 1)) * width;
  const y = (v: number) => height - ((v - min) / span) * (height - 4) - 2;

  const up = data[n - 1] >= data[0];
  const stroke = up ? "var(--bull)" : "var(--bear)";
  const id = `sg${up ? "u" : "d"}`;

  const line = data.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const area = `${line}L${width},${height}L0,${height}Z`;

  return (
    <svg className="spark" width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <defs>
        <linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.35" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${id})`} />
      <path d={line} fill="none" stroke={stroke} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}
