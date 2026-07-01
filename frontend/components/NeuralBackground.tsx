"use client";
import { useEffect, useRef } from "react";

// Self-contained animated "neural network" backdrop: drifting nodes wired by
// synapses that light up as they near each other (and the cursor). Canvas +
// requestAnimationFrame, no libraries, no assets. Sits fixed behind all content.
export function NeuralBackground() {
  const ref = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduce =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

    let w = 0;
    let h = 0;
    let dpr = Math.min(window.devicePixelRatio || 1, 2);

    type Node = { x: number; y: number; vx: number; vy: number; r: number; p: number };
    let nodes: Node[] = [];
    const mouse = { x: -9999, y: -9999 };

    const rand = (a: number, b: number) => a + Math.random() * (b - a);

    const build = () => {
      w = canvas.clientWidth;
      h = canvas.clientHeight;
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      // Density scales with area, capped for perf.
      const count = Math.min(90, Math.floor((w * h) / 18000));
      nodes = Array.from({ length: count }, () => ({
        x: rand(0, w),
        y: rand(0, h),
        vx: rand(-0.18, 0.18),
        vy: rand(-0.18, 0.18),
        r: rand(1, 2.4),
        p: rand(0, Math.PI * 2),
      }));
    };

    const LINK = 150; // px distance to draw a synapse
    let raf = 0;
    let t = 0;

    const draw = () => {
      t += 0.016;
      ctx.clearRect(0, 0, w, h);

      for (const n of nodes) {
        if (!reduce) {
          n.x += n.vx;
          n.y += n.vy;
        }
        // Gentle mouse repulsion so the field "reacts" to the cursor.
        const mdx = n.x - mouse.x;
        const mdy = n.y - mouse.y;
        const md2 = mdx * mdx + mdy * mdy;
        if (md2 < 140 * 140) {
          const f = (1 - Math.sqrt(md2) / 140) * 0.6;
          n.x += (mdx / (Math.sqrt(md2) || 1)) * f;
          n.y += (mdy / (Math.sqrt(md2) || 1)) * f;
        }
        if (n.x < 0 || n.x > w) n.vx *= -1;
        if (n.y < 0 || n.y > h) n.vy *= -1;
        n.x = Math.max(0, Math.min(w, n.x));
        n.y = Math.max(0, Math.min(h, n.y));
      }

      // Synapses
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i];
          const b = nodes[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const d2 = dx * dx + dy * dy;
          if (d2 < LINK * LINK) {
            const d = Math.sqrt(d2);
            const alpha = (1 - d / LINK) * 0.5;
            const mnear =
              Math.min(
                (a.x - mouse.x) ** 2 + (a.y - mouse.y) ** 2,
                (b.x - mouse.x) ** 2 + (b.y - mouse.y) ** 2
              ) <
              180 * 180;
            ctx.strokeStyle = mnear
              ? `rgba(103, 232, 249, ${alpha + 0.25})` // cyan near cursor
              : `rgba(90, 130, 255, ${alpha * 0.7})`; // blue/violet baseline
            ctx.lineWidth = mnear ? 1 : 0.6;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();
          }
        }
      }

      // Nodes (with a soft pulse)
      for (const n of nodes) {
        const pulse = reduce ? 1 : 0.75 + 0.25 * Math.sin(t * 2 + n.p);
        const r = n.r * pulse;
        const g = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, r * 4);
        g.addColorStop(0, "rgba(129, 236, 255, 0.9)");
        g.addColorStop(1, "rgba(129, 236, 255, 0)");
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(n.x, n.y, r * 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "rgba(160, 245, 255, 0.95)";
        ctx.beginPath();
        ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
        ctx.fill();
      }

      raf = requestAnimationFrame(draw);
    };

    const onMove = (e: MouseEvent) => {
      mouse.x = e.clientX;
      mouse.y = e.clientY;
    };
    const onLeave = () => {
      mouse.x = -9999;
      mouse.y = -9999;
    };
    const onResize = () => build();

    build();
    draw();
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseout", onLeave);
    window.addEventListener("resize", onResize);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseout", onLeave);
      window.removeEventListener("resize", onResize);
    };
  }, []);

  return <canvas ref={ref} className="neural-bg" aria-hidden="true" />;
}
