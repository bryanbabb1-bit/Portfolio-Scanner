"use client";
import { useEffect, useMemo, useState } from "react";
import { api, ChartRange, PortfolioHistory } from "../lib/api";
import { money } from "./format";

const RANGES: ChartRange[] = ["1mo", "3mo", "6mo", "1y"];

// Portfolio market value over time (area) with a dashed cost-basis baseline.
// Same dependency-free inline-SVG approach as the per-stock chart.
export function PortfolioChart() {
  const [range, setRange] = useState<ChartRange>("6mo");
  const [data, setData] = useState<PortfolioHistory | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setErr(null);
    api
      .portfolioHistory(range)
      .then((d) => live && setData(d))
      .catch((e) => live && setErr(e.message))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [range]);

  const pts = data?.points ?? [];

  const geom = useMemo(() => {
    if (pts.length < 2) return null;
    const W = 960;
    const H = 260;
    const padL = 60;
    const padR = 14;
    const padT = 14;
    const plotH = H - 42;

    const vals = pts.map((p) => p.value);
    const cost = data?.cost_basis ?? 0;
    const yMax = Math.max(...vals, cost);
    const yMin = Math.min(...vals, cost);
    const pad = (yMax - yMin) * 0.08 || 1;
    const lo = yMin - pad;
    const hi = yMax + pad;

    const innerW = W - padL - padR;
    const x = (i: number) => padL + (i / (pts.length - 1)) * innerW;
    const y = (v: number) => padT + (1 - (v - lo) / (hi - lo)) * plotH;

    const line = pts.reduce((acc, p, i) => acc + (i === 0 ? "M" : "L") + `${x(i)},${y(p.value)}`, "");
    const area = `${line}L${x(pts.length - 1)},${padT + plotH}L${x(0)},${padT + plotH}Z`;
    const ticks = Array.from({ length: 5 }, (_, k) => lo + ((hi - lo) * k) / 4);
    return { W, H, padL, padR, padT, plotH, x, y, line, area, ticks, cost };
  }, [pts, data?.cost_basis]);

  const first = pts[0]?.value;
  const last = pts[pts.length - 1]?.value;
  const chg = first != null && last != null && first ? ((last / first - 1) * 100) : 0;
  const up = chg >= 0;
  const stroke = up ? "var(--bull)" : "var(--bear)";

  return (
    <div className="card panel-glow" style={{ marginBottom: 28 }}>
      <div className="chart-head">
        <div>
          <div className="section-title" style={{ margin: 0 }}>Portfolio Value</div>
          {last != null && (
            <div className="pf-value">
              {money(last, 0)}{" "}
              <span className={up ? "pos" : "neg"} style={{ fontSize: 13, fontWeight: 700 }}>
                {up ? "▲" : "▼"} {Math.abs(chg).toFixed(2)}% · {range.toUpperCase()}
              </span>
            </div>
          )}
        </div>
        <div className="range-toggle">
          {RANGES.map((r) => (
            <button key={r} className={r === range ? "active" : ""} onClick={() => setRange(r)}>
              {r.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {loading && <div className="loading">Loading portfolio history…</div>}
      {err && <div className="err">History unavailable ({err}).</div>}

      {!loading && !err && geom && (
        <>
          <svg
            className="price-chart"
            viewBox={`0 0 ${geom.W} ${geom.H}`}
            preserveAspectRatio="none"
            onMouseLeave={() => setHover(null)}
            onMouseMove={(e) => {
              const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
              const px = ((e.clientX - rect.left) / rect.width) * geom.W;
              const rel = (px - geom.padL) / (geom.W - geom.padL - geom.padR);
              const i = Math.round(rel * (pts.length - 1));
              setHover(Math.max(0, Math.min(pts.length - 1, i)));
            }}
          >
            {geom.ticks.map((t, k) => (
              <g key={k}>
                <line x1={geom.padL} x2={geom.W - geom.padR} y1={geom.y(t)} y2={geom.y(t)} stroke="var(--border)" strokeWidth={1} />
                <text x={8} y={geom.y(t) + 4} fill="var(--muted)" fontSize={11}>{money(t, 0)}</text>
              </g>
            ))}

            {/* cost-basis baseline */}
            {geom.cost > 0 && (
              <g>
                <line x1={geom.padL} x2={geom.W - geom.padR} y1={geom.y(geom.cost)} y2={geom.y(geom.cost)} stroke="var(--gold)" strokeDasharray="5 4" strokeWidth={1.2} opacity={0.8} />
                <text x={geom.W - geom.padR} y={geom.y(geom.cost) - 5} fill="var(--gold)" fontSize={10} textAnchor="end">cost {money(geom.cost, 0)}</text>
              </g>
            )}

            <defs>
              <linearGradient id="pffill" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor={stroke} stopOpacity="0.28" />
                <stop offset="100%" stopColor={stroke} stopOpacity="0" />
              </linearGradient>
            </defs>
            <path d={geom.area} fill="url(#pffill)" />
            <path d={geom.line} fill="none" stroke={stroke} strokeWidth={2.4} />

            {hover != null && pts[hover] && (
              <g>
                <line x1={geom.x(hover)} x2={geom.x(hover)} y1={geom.padT} y2={geom.padT + geom.plotH} stroke="var(--muted)" strokeDasharray="3 3" strokeWidth={1} />
                <circle cx={geom.x(hover)} cy={geom.y(pts[hover].value)} r={4} fill={stroke} />
              </g>
            )}
          </svg>

          <div className="chart-readout mut">
            {hover != null && pts[hover] ? (
              <>
                <strong style={{ color: "var(--text)" }}>{pts[hover].date}</strong>
                {"  "}value <strong style={{ color: "var(--text)" }}>{money(pts[hover].value, 0)}</strong>
                {geom.cost > 0 && (
                  <> {"  "}vs cost{" "}
                    <span className={pts[hover].value >= geom.cost ? "pos" : "neg"}>
                      {money(pts[hover].value - geom.cost, 0)}
                    </span>
                  </>
                )}
              </>
            ) : (
              <>Hover to inspect portfolio value on any day. Gold dashes = total cost basis.</>
            )}
          </div>
        </>
      )}
    </div>
  );
}
