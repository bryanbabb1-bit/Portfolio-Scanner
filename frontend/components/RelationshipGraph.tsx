"use client";
import { useEffect, useRef, useState } from "react";
import { api, GraphData } from "../lib/api";

// Relationship graph — a force-directed correlation web of the holdings.
// Tightly-correlated names pull together into clusters, so you can SEE that the
// book is really one big co-moving bet rather than diversified positions.
// Ink-range categorical ramp — the blueprint has no neon, so themes are
// separated by value and warmth rather than by hue saturation.
const PALETTE = ["#C4551F", "#3D4A2A", "#8A6D1F", "#B3341C", "#5C6B4A", "#7A5230", "#4A5A63", "#6B6558"];

type N = { symbol: string; theme: string; weight: number; x: number; y: number; vx: number; vy: number; r: number; color: string };

export function RelationshipGraph() {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>(0);
  const [data, setData] = useState<GraphData | null>(null);

  useEffect(() => { api.graph().then(setData).catch(() => {}); }, []);

  useEffect(() => {
    const canvas = canvasRef.current, wrap = wrapRef.current;
    if (!data || !canvas || !wrap || data.nodes.length < 2) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const W = wrap.clientWidth || 340, H = 330;
    canvas.width = W * dpr; canvas.height = H * dpr;
    canvas.style.width = W + "px"; canvas.style.height = H + "px";
    ctx.scale(dpr, dpr);

    const themes = Array.from(new Set(data.nodes.map((n) => n.theme)));
    const colorOf = (t: string) => PALETTE[themes.indexOf(t) % PALETTE.length];
    const cx = W / 2, cy = H / 2;
    const nodes: N[] = data.nodes.map((n, i) => {
      const a = (i / data.nodes.length) * Math.PI * 2;
      return {
        ...n, color: colorOf(n.theme),
        r: 7 + Math.sqrt(n.weight) * 34,
        x: cx + Math.cos(a) * 90, y: cy + Math.sin(a) * 90, vx: 0, vy: 0,
      };
    });
    const idx: Record<string, N> = {};
    nodes.forEach((n) => (idx[n.symbol] = n));
    const edges = data.edges.map((e) => ({ a: idx[e.a], b: idx[e.b], corr: e.corr })).filter((e) => e.a && e.b);

    const step = () => {
      // repulsion (softer, so correlated groups can clump)
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i], b = nodes[j];
          let dx = a.x - b.x, dy = a.y - b.y;
          let d2 = dx * dx + dy * dy || 0.01;
          const f = 1700 / d2;
          const d = Math.sqrt(d2);
          dx /= d; dy /= d;
          a.vx += dx * f; a.vy += dy * f; b.vx -= dx * f; b.vy -= dy * f;
        }
      }
      // strong attraction along correlated edges — pull co-movers together
      for (const e of edges) {
        let dx = e.b.x - e.a.x, dy = e.b.y - e.a.y;
        const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
        const rest = 34;
        const f = (d - rest) * 0.03 * e.corr;
        dx /= d; dy /= d;
        e.a.vx += dx * f; e.a.vy += dy * f; e.b.vx -= dx * f; e.b.vy -= dy * f;
      }
      // gentle centering + damping + integrate
      for (const n of nodes) {
        n.vx += (cx - n.x) * 0.0022; n.vy += (cy - n.y) * 0.0022;
        n.vx *= 0.82; n.vy *= 0.82;
        n.x += n.vx; n.y += n.vy;
        n.x = Math.max(n.r + 4, Math.min(W - n.r - 4, n.x));
        n.y = Math.max(n.r + 4, Math.min(H - n.r - 4, n.y));
      }
    };

    const draw = () => {
      ctx.clearRect(0, 0, W, H);
      for (const e of edges) {
        ctx.strokeStyle = `rgba(20,20,15,${Math.min(0.45, (e.corr - 0.35) * 0.85)})`;
        ctx.lineWidth = 0.5 + e.corr * 1.6;
        ctx.beginPath(); ctx.moveTo(e.a.x, e.a.y); ctx.lineTo(e.b.x, e.b.y); ctx.stroke();
      }
      for (const n of nodes) {
        ctx.fillStyle = n.color;
        ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, 7); ctx.fill();
        ctx.fillStyle = "#FAF7F0"; ctx.font = `600 ${Math.max(9, Math.min(12, n.r * 0.7))}px ui-monospace, monospace`;
        ctx.textAlign = "center"; ctx.textBaseline = "middle";
        ctx.fillText(n.symbol, n.x, n.y);
      }
    };

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      for (let i = 0; i < 300; i++) step();
      draw();
      return;
    }
    let frames = 0;
    const loop = () => {
      step(); draw(); frames++;
      if (frames < 460) rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
  }, [data]);

  if (data && data.nodes.length < 2) return null;
  const avg = data?.avg_corr;
  const verdict = avg == null ? ""
    : avg >= 0.6 ? "These names move largely as one — diversification is thin."
    : avg >= 0.4 ? "Moderately correlated — real but partial diversification."
    : "Loosely correlated — the names move fairly independently.";

  return (
    <div className="card graph">
      <div className="chart-head" style={{ marginBottom: 6 }}>
        <div className="section-title" style={{ margin: 0 }}>How your book moves together</div>
        {avg != null && <span className="graph-avg">avg corr {avg.toFixed(2)}</span>}
      </div>
      <div className="graph-sub">{verdict} <span className="mut">Bigger dot = larger position · line = names that move together.</span></div>
      <div className="graph-canvas-wrap" ref={wrapRef}><canvas ref={canvasRef} /></div>
    </div>
  );
}
