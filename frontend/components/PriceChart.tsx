"use client";
import { useEffect, useMemo, useState } from "react";
import { api, Candle, CHART_RANGES, ChartRange, PriceHistory, RANGE_LABELS } from "../lib/api";
import { money } from "./format";

// Pure inline-SVG chart — no external charting lib, so it stays self-contained
// (works under a strict CSP and adds zero npm dependencies).
export function PriceChart({ symbol }: { symbol: string }) {
  const [range, setRange] = useState<ChartRange>("6mo");
  const [data, setData] = useState<PriceHistory | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setErr(null);
    api
      .history(symbol, range)
      .then((d) => live && setData(d))
      .catch((e) => live && setErr(e.message))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [symbol, range]);

  const candles = data?.candles ?? [];

  const geom = useMemo(() => {
    if (candles.length < 2) return null;
    const W = 720;
    const padL = 52;
    const padR = 12;
    const padT = 12;
    const priceH = 210;
    const volTop = priceH + 24;
    const volH = 48;
    const rsiTop = volTop + volH + 26;
    const rsiH = 76;
    const H = rsiTop + rsiH + 16;

    const closes = candles.map((c) => c.close);
    const highs = candles.map((c) => c.high);
    const lows = candles.map((c) => c.low);
    const smas = candles.flatMap((c) =>
      [c.sma20, c.sma50].filter((v): v is number => v != null)
    );
    const yMax = Math.max(...highs, ...smas);
    const yMin = Math.min(...lows, ...smas);
    const pad = (yMax - yMin) * 0.06 || 1;
    const lo = yMin - pad;
    const hi = yMax + pad;

    const vMax = Math.max(...candles.map((c) => c.volume), 1);
    const innerW = W - padL - padR;
    const x = (i: number) => padL + (i / (candles.length - 1)) * innerW;
    const y = (p: number) => padT + (1 - (p - lo) / (hi - lo)) * priceH;
    const vy = (v: number) => volTop + (1 - v / vMax) * volH;
    const ry = (v: number) => rsiTop + (1 - v / 100) * rsiH;

    const rsiLine = candles
      .map((c, i) => (c.rsi == null ? null : `${x(i)},${ry(c.rsi)}`))
      .filter(Boolean)
      .reduce((acc: string, pt, idx) => acc + (idx === 0 ? "M" : "L") + pt, "");

    const line = (key: "close" | "sma20" | "sma50") =>
      candles
        .map((c, i) => {
          const val = c[key];
          if (val == null) return null;
          return `${x(i)},${y(val)}`;
        })
        .filter(Boolean)
        .reduce((acc: string, pt, idx) => acc + (idx === 0 ? "M" : "L") + pt, "");

    const area =
      `M${x(0)},${y(candles[0].close)}` +
      candles.map((c, i) => `L${x(i)},${y(c.close)}`).join("") +
      `L${x(candles.length - 1)},${padT + priceH}L${x(0)},${padT + priceH}Z`;

    // ~5 horizontal price gridlines.
    const ticks = Array.from({ length: 5 }, (_, k) => lo + ((hi - lo) * k) / 4);

    return { W, H, padL, padR, padT, priceH, volTop, volH, rsiTop, rsiH, x, y, vy, ry, rsiLine, line, area, ticks, lo, hi };
  }, [candles]);

  const first = candles[0]?.close;
  const last = candles[candles.length - 1]?.close;
  const chg = first != null && last != null ? ((last / first - 1) * 100) : 0;
  const up = chg >= 0;
  const stroke = up ? "var(--bull)" : "var(--bear)";

  const lastRsi = [...candles].reverse().find((c) => c.rsi != null)?.rsi ?? null;
  const rsiZone =
    lastRsi == null ? null : lastRsi <= 32 ? "buy" : lastRsi >= 70 ? "sell" : "neutral";

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="chart-head">
        <div className="section-title" style={{ margin: 0 }}>Price</div>
        <div className="range-toggle">
          {CHART_RANGES.map((r) => (
            <button
              key={r}
              className={r === range ? "active" : ""}
              onClick={() => setRange(r)}
            >
              {RANGE_LABELS[r]}
            </button>
          ))}
        </div>
      </div>

      {loading && <div className="loading">Loading chart…</div>}
      {err && <div className="err">Chart unavailable ({err}).</div>}

      {!loading && !err && geom && (
        <>
          <div className="chart-meta">
            <span className={up ? "pos" : "neg"} style={{ fontWeight: 700 }}>
              {up ? "▲" : "▼"} {Math.abs(chg).toFixed(2)}%
            </span>
            <span className="mut" style={{ fontSize: 12 }}>
              over {RANGE_LABELS[range]} · {data?.source}
            </span>
            {lastRsi != null && (
              <span className={`rsi-pill ${rsiZone}`}>
                RSI {lastRsi.toFixed(0)} ·{" "}
                {rsiZone === "buy" ? "BUY ZONE" : rsiZone === "sell" ? "SELL ZONE" : "neutral"}
              </span>
            )}
            <span className="chart-legend">
              <i style={{ background: stroke }} /> Close
              <i style={{ background: "var(--accent)" }} /> SMA20
              <i style={{ background: "var(--gold)" }} /> SMA50
            </span>
          </div>

          <svg
            className="price-chart"
            viewBox={`0 0 ${geom.W} ${geom.H}`}
            preserveAspectRatio="none"
            onMouseLeave={() => setHover(null)}
            onMouseMove={(e) => {
              const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
              const px = ((e.clientX - rect.left) / rect.width) * geom.W;
              const rel = (px - geom.padL) / (geom.W - geom.padL - geom.padR);
              const i = Math.round(rel * (candles.length - 1));
              setHover(Math.max(0, Math.min(candles.length - 1, i)));
            }}
          >
            {/* gridlines + price axis labels */}
            {geom.ticks.map((t, k) => (
              <g key={k}>
                <line
                  x1={geom.padL}
                  x2={geom.W - geom.padR}
                  y1={geom.y(t)}
                  y2={geom.y(t)}
                  stroke="var(--border)"
                  strokeWidth={1}
                />
                <text x={8} y={geom.y(t) + 4} fill="var(--muted)" fontSize={11}>
                  {money(t, t > 1000 ? 0 : 2)}
                </text>
              </g>
            ))}

            {/* volume bars */}
            {candles.map((c, i) => {
              const h = geom.volTop + geom.volH - geom.vy(c.volume);
              return (
                <rect
                  key={i}
                  x={geom.x(i) - Math.max(1, 260 / candles.length / 2)}
                  y={geom.vy(c.volume)}
                  width={Math.max(1.5, 260 / candles.length)}
                  height={Math.max(0, h)}
                  fill="var(--accent-dim)"
                />
              );
            })}

            {/* close area + lines */}
            <defs>
              <linearGradient id="fill" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor={stroke} stopOpacity="0.22" />
                <stop offset="100%" stopColor={stroke} stopOpacity="0" />
              </linearGradient>
            </defs>
            <path d={geom.area} fill="url(#fill)" />
            <path d={geom.line("sma50")} fill="none" stroke="var(--gold)" strokeWidth={1.4} opacity={0.9} />
            <path d={geom.line("sma20")} fill="none" stroke="var(--accent)" strokeWidth={1.4} opacity={0.9} />
            <path d={geom.line("close")} fill="none" stroke={stroke} strokeWidth={2} />

            {/* ------------- RSI pane: oversold = buy zone, overbought = sell */}
            <g>
              <text x={geom.padL} y={geom.rsiTop - 8} fill="var(--muted)" fontSize={10} letterSpacing="0.06em">
                RSI (14)
              </text>
              {/* sell zone band: RSI 70-100 */}
              <rect x={geom.padL} y={geom.ry(100)} width={geom.W - geom.padL - geom.padR}
                height={geom.ry(70) - geom.ry(100)} fill="rgba(251, 92, 107, 0.08)" />
              {/* buy zone band: RSI 0-30 */}
              <rect x={geom.padL} y={geom.ry(30)} width={geom.W - geom.padL - geom.padR}
                height={geom.ry(0) - geom.ry(30)} fill="rgba(52, 211, 153, 0.10)" />
              {[70, 30].map((lvl) => (
                <g key={lvl}>
                  <line x1={geom.padL} x2={geom.W - geom.padR} y1={geom.ry(lvl)} y2={geom.ry(lvl)}
                    stroke={lvl === 30 ? "var(--bull)" : "var(--bear)"} strokeDasharray="4 4"
                    strokeWidth={0.8} opacity={0.7} />
                  <text x={8} y={geom.ry(lvl) + 3.5} fill="var(--muted)" fontSize={10}>{lvl}</text>
                </g>
              ))}
              <text x={geom.W - geom.padR - 4} y={geom.ry(15) + 3} fill="var(--bull)" fontSize={9}
                fontWeight={800} textAnchor="end" letterSpacing="0.08em" opacity={0.85}>
                BUY ZONE
              </text>
              <text x={geom.W - geom.padR - 4} y={geom.ry(85) + 3} fill="var(--bear)" fontSize={9}
                fontWeight={800} textAnchor="end" letterSpacing="0.08em" opacity={0.85}>
                SELL ZONE
              </text>
              <path d={geom.rsiLine} fill="none" stroke="var(--accent-2)" strokeWidth={1.8} />
              {hover != null && candles[hover]?.rsi != null && (
                <circle cx={geom.x(hover)} cy={geom.ry(candles[hover].rsi as number)} r={3} fill="var(--accent-2)" />
              )}
            </g>

            {/* hover crosshair + marker */}
            {hover != null && candles[hover] && (
              <g>
                <line
                  x1={geom.x(hover)}
                  x2={geom.x(hover)}
                  y1={geom.padT}
                  y2={geom.rsiTop + geom.rsiH}
                  stroke="var(--muted)"
                  strokeDasharray="3 3"
                  strokeWidth={1}
                />
                <circle cx={geom.x(hover)} cy={geom.y(candles[hover].close)} r={3.5} fill={stroke} />
              </g>
            )}
          </svg>

          <div className="chart-readout mut">
            {hover != null && candles[hover] ? (
              <>
                <strong style={{ color: "var(--text)" }}>{candles[hover].date}</strong>
                {"  "}O {money(candles[hover].open)} · H {money(candles[hover].high)} · L{" "}
                {money(candles[hover].low)} · C{" "}
                <strong style={{ color: "var(--text)" }}>{money(candles[hover].close)}</strong>
                {"  "}Vol {Intl.NumberFormat("en", { notation: "compact" }).format(candles[hover].volume)}
                {candles[hover].rsi != null && (
                  <>
                    {"  "}· RSI{" "}
                    <strong style={{ color: "var(--accent-2)" }}>
                      {(candles[hover].rsi as number).toFixed(0)}
                    </strong>
                  </>
                )}
              </>
            ) : (
              <>
                Hover for OHLC, volume and RSI per bar. RSI below 30 = oversold
                (buy zone) · above 70 = overbought (sell zone) · momentum is
                healthiest 40-65.
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}
