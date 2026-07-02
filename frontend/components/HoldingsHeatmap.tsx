"use client";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { StockReport } from "../lib/api";
import { money, pct } from "./format";

// Squarified treemap: tile area = market value, color = day move or total P/L.

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

function worstRatio(row: number[], side: number): number {
  const s = row.reduce((a, b) => a + b, 0);
  const mx = Math.max(...row);
  const mn = Math.min(...row);
  return Math.max((side * side * mx) / (s * s), (s * s) / (side * side * mn));
}

function squarify(values: number[], bounds: Rect): Rect[] {
  const total = values.reduce((a, b) => a + b, 0);
  const scale = (bounds.w * bounds.h) / total;
  const areas = values.map((v) => v * scale);
  const out: Rect[] = [];
  let { x, y, w, h } = bounds;
  let i = 0;
  while (i < areas.length) {
    const side = Math.min(w, h);
    const row: number[] = [];
    let best = Infinity;
    while (i < areas.length) {
      row.push(areas[i]);
      const cur = worstRatio(row, side);
      if (cur > best) {
        row.pop();
        break;
      }
      best = cur;
      i++;
    }
    const rowArea = row.reduce((a, b) => a + b, 0);
    const thickness = rowArea / side;
    let offset = 0;
    if (w >= h) {
      for (const a of row) {
        const hh = a / thickness;
        out.push({ x, y: y + offset, w: thickness, h: hh });
        offset += hh;
      }
      x += thickness;
      w -= thickness;
    } else {
      for (const a of row) {
        const ww = a / thickness;
        out.push({ x: x + offset, y, w: ww, h: thickness });
        offset += ww;
      }
      y += thickness;
      h -= thickness;
    }
  }
  return out;
}

const BASE = { r: 23, g: 31, b: 50 };
const BULL = { r: 13, g: 148, b: 100 };
const BEAR = { r: 190, g: 54, b: 70 };

function heatColor(metric: number, cap: number): string {
  const t = Math.max(-1, Math.min(1, metric / cap));
  const target = t >= 0 ? BULL : BEAR;
  const k = Math.abs(t);
  const mix = (a: number, b: number) => Math.round(a + (b - a) * k);
  return `rgb(${mix(BASE.r, target.r)},${mix(BASE.g, target.g)},${mix(BASE.b, target.b)})`;
}

type Mode = "day" | "total";

export function HoldingsHeatmap({ holdings }: { holdings: StockReport[] }) {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("day");
  // On phones a tall portrait canvas keeps tile labels readable.
  const [compact, setCompact] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 640px)");
    const update = () => setCompact(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  const W = compact ? 600 : 1000;
  const H = compact ? 640 : 380;

  const tiles = useMemo(() => {
    const held = holdings
      .filter((r) => (r.market_value ?? 0) > 0)
      .sort((a, b) => (b.market_value ?? 0) - (a.market_value ?? 0));
    if (!held.length) return [];
    const rects = squarify(
      held.map((r) => r.market_value as number),
      { x: 0, y: 0, w: W, h: H }
    );
    return held.map((r, i) => ({ r, rect: rects[i] }));
  }, [holdings, W, H]);

  if (!tiles.length) return null;

  return (
    <div className="card" style={{ marginBottom: 28 }}>
      <div className="chart-head">
        <div className="section-title" style={{ margin: 0 }}>
          Portfolio Heatmap{" "}
          <span className="mut" style={{ textTransform: "none", letterSpacing: 0 }}>
            · size = value · color = {mode === "day" ? "today's move" : "total return"}
          </span>
        </div>
        <div className="range-toggle">
          <button className={mode === "day" ? "active" : ""} onClick={() => setMode("day")}>
            Day
          </button>
          <button className={mode === "total" ? "active" : ""} onClick={() => setMode("total")}>
            Total
          </button>
        </div>
      </div>
      <svg className="heatmap" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img">
        {tiles.map(({ r, rect }) => {
          const metric = mode === "day" ? r.quote.change_pct : r.unrealized_pl_pct ?? 0;
          const cap = mode === "day" ? 4 : 40;
          const showText = rect.w > 68 && rect.h > 40;
          const showPct = rect.w > 68 && rect.h > 64;
          const fs = Math.min(26, Math.max(12, Math.sqrt(rect.w * rect.h) / 7));
          return (
            <g
              key={r.symbol}
              className="hm-tile"
              onClick={() => router.push(`/stock/${r.symbol}`)}
            >
              <title>
                {`${r.symbol} · ${money(r.market_value, 0)} · day ${pct(r.quote.change_pct)} · total ${pct(r.unrealized_pl_pct)}`}
              </title>
              <rect
                x={rect.x + 1.5}
                y={rect.y + 1.5}
                width={Math.max(rect.w - 3, 0)}
                height={Math.max(rect.h - 3, 0)}
                rx={6}
                fill={heatColor(metric, cap)}
              />
              {showText && (
                <text
                  x={rect.x + rect.w / 2}
                  y={rect.y + rect.h / 2 + (showPct ? -4 : 5)}
                  textAnchor="middle"
                  className="hm-sym"
                  fontSize={fs}
                >
                  {r.symbol}
                </text>
              )}
              {showPct && (
                <text
                  x={rect.x + rect.w / 2}
                  y={rect.y + rect.h / 2 + fs * 0.85}
                  textAnchor="middle"
                  className="hm-pct"
                  fontSize={Math.max(10, fs * 0.55)}
                >
                  {pct(metric, 1)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
