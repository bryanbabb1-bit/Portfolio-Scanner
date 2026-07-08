"use client";
import { useEffect, useRef, useState } from "react";
import { api, Scorecard } from "../lib/api";

// Probability Lattice — a Galton board of the advisor's fired calls. Each
// signal drops into a win/loss bin by its realized edge; the pile that builds
// up IS the track record. Inspired by the "law of large numbers" quincunx.
const EDGES = [-20, -10, -5, 0, 5, 10, 20]; // 8 bins; index 4+ = profit side
const NBINS = EDGES.length + 1;
const PAL = {
  green: "#1ec98a", red: "#f0616e", greyBall: "#5a6376", mut: "#868ea3",
  peg: "#2b3140", lossTint: "rgba(240,97,110,0.05)", profitTint: "rgba(30,201,138,0.06)",
  line: "rgba(255,255,255,0.22)", base: "rgba(255,255,255,0.12)",
};

function binOf(pct: number) {
  let i = 0;
  for (const e of EDGES) if (pct >= e) i++;
  return i;
}

export function ProbabilityLattice() {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>(0);
  const [sc, setSc] = useState<Scorecard | null>(null);
  const [landed, setLanded] = useState(0);

  useEffect(() => { api.scorecard().then(setSc).catch(() => {}); }, []);

  useEffect(() => {
    const canvas = canvasRef.current, wrap = wrapRef.current;
    if (!sc || !canvas || !wrap || !sc.signals.length) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const cssW = wrap.clientWidth || 340;
    const cssH = 250;
    canvas.width = cssW * dpr; canvas.height = cssH * dpr;
    canvas.style.width = cssW + "px"; canvas.style.height = cssH + "px";
    ctx.scale(dpr, dpr);

    const padX = 10, topY = 20, floorY = cssH - 26;
    const boardW = cssW - padX * 2;
    const binW = boardW / NBINS;
    const r = Math.max(2.5, Math.min(binW / 3.4, 5));
    const gap = 1.5;
    const spawnX = padX + boardW / 2;

    const signals = [...sc.signals].reverse();
    const stack = new Array(NBINS).fill(0);
    const balls = signals.map((s, i) => {
      const bin = binOf(s.effective_pct);
      const slot = stack[bin]++;
      const green = bin >= NBINS / 2;
      return {
        green,
        targetX: padX + binW * (bin + 0.5),
        restY: floorY - r - slot * (2 * r + gap),
        color: green ? PAL.green : s.effective_pct < -10 ? PAL.red : PAL.greyBall,
        start: i * 85,
        wob: (i % 2 ? 1 : -1) * binW * 0.5,
      };
    });

    // decorative peg grid
    const pegs: [number, number][] = [];
    const pegRows = 6;
    for (let row = 0; row < pegRows; row++) {
      const ry = topY + 12 + row * ((floorY - topY - 44) / pegRows);
      const n = row + 3;
      const spread = binW * (row + 1) * 0.95;
      for (let c = 0; c < n; c++) {
        pegs.push([spawnX - spread / 2 + (spread / Math.max(n - 1, 1)) * c, ry]);
      }
    }

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const DUR = 850, t0 = performance.now();
    let lastLanded = -1;
    const beX = padX + binW * (NBINS / 2);
    const easeIn = (t: number) => t * t;

    const frame = (now: number) => {
      const el = reduce ? 1e9 : now - t0;
      ctx.clearRect(0, 0, cssW, cssH);

      ctx.fillStyle = PAL.lossTint; ctx.fillRect(padX, topY, beX - padX, floorY - topY);
      ctx.fillStyle = PAL.profitTint; ctx.fillRect(beX, topY, padX + boardW - beX, floorY - topY);
      ctx.strokeStyle = PAL.line; ctx.setLineDash([4, 4]); ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(beX, topY - 5); ctx.lineTo(beX, floorY + 2); ctx.stroke();
      ctx.setLineDash([]);

      ctx.fillStyle = PAL.peg;
      for (const [px, py] of pegs) { ctx.beginPath(); ctx.arc(px, py, 1.3, 0, 7); ctx.fill(); }

      let landedCount = 0;
      for (const b of balls) {
        const lt = (el - b.start) / DUR;
        if (lt >= 1) {
          landedCount++;
          ctx.fillStyle = b.color;
          ctx.beginPath(); ctx.arc(b.targetX, b.restY, r, 0, 7); ctx.fill();
        } else if (lt > 0) {
          const y = topY + (b.restY - topY) * easeIn(lt);
          const x = spawnX + (b.targetX - spawnX) * lt + b.wob * Math.sin(lt * Math.PI * 3) * (1 - lt);
          ctx.fillStyle = b.color;
          ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill();
        }
      }

      ctx.strokeStyle = PAL.base; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(padX, floorY + 3); ctx.lineTo(padX + boardW, floorY + 3); ctx.stroke();

      ctx.font = "10px ui-monospace, monospace"; ctx.textAlign = "left";
      ctx.fillStyle = PAL.mut; ctx.fillText("LOSS", padX + 4, topY + 9);
      ctx.textAlign = "right"; ctx.fillStyle = PAL.green; ctx.fillText("PROFIT", padX + boardW - 4, topY + 9);
      ctx.textAlign = "left";

      if (landedCount !== lastLanded) { lastLanded = landedCount; setLanded(landedCount); }
      if (el < balls[balls.length - 1].start + DUR + 60) rafRef.current = requestAnimationFrame(frame);
    };
    rafRef.current = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(rafRef.current);
  }, [sc]);

  if (sc && sc.count === 0) return null;
  const wr = sc?.overall_win_rate;
  const avg = sc?.overall_avg_pct;

  return (
    <div className="card lattice">
      <div className="section-title" style={{ marginBottom: 4 }}>Do the calls work? · Probability Lattice</div>
      <div className="lat-sub">Every signal the advisor has fired drops into a win or loss bin — the pile that builds is its real edge.</div>
      <div className="lat-body">
        <div className="lat-stats">
          <div className="ls"><span className="k">Calls dropped</span><span className="v">{landed}</span></div>
          <div className="ls"><span className="k">Landed green</span><span className="v pos">{wr != null ? `${wr.toFixed(0)}%` : "—"}</span></div>
          <div className="ls"><span className="k">Avg edge / call</span><span className={`v ${(avg ?? 0) >= 0 ? "pos" : "neg"}`}>{avg != null ? `${avg >= 0 ? "+" : ""}${avg.toFixed(2)}%` : "—"}</span></div>
          <div className="ls"><span className="k">Tracked all-time</span><span className="v">{sc?.count ?? 0}</span></div>
          <div className="lat-tag">Law of large numbers — the edge only needs repetition.</div>
        </div>
        <div className="lat-canvas-wrap" ref={wrapRef}>
          <canvas ref={canvasRef} />
          <div className="lat-note">last {sc?.signals.length ?? 0} calls</div>
        </div>
      </div>
    </div>
  );
}
