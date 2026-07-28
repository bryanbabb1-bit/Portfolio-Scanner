"use client";
import { DebateAgent } from "../lib/api";

/* The five-agent ring from sheet 03/08. Nodes light up as each agent reports;
   dashed chords are the debate links, the centre is the judge. */

const ORDER: DebateAgent["key"][] = ["bull", "bear", "execution", "risk", "macro"];
const LABEL: Record<DebateAgent["key"], string> = {
  bull: "Bull",
  bear: "Bear",
  execution: "Execution",
  risk: "Risk",
  macro: "Macro",
};

const W = 640;
const H = 470;
const CX = W / 2;
const CY = 232;
const R = 168;
const NODE_R = 52;

function nodePos(i: number) {
  // start at the top and go clockwise
  const a = -Math.PI / 2 + (i * 2 * Math.PI) / 5;
  return { x: CX + R * Math.cos(a), y: CY + R * Math.sin(a) };
}

export function DebatePentagon({
  agents,
  running,
}: {
  agents: DebateAgent[];
  running: boolean;
}) {
  const byKey = new Map(agents.map((a) => [a.key, a]));
  const pts = ORDER.map((_, i) => nodePos(i));

  return (
    <svg
      className="debate-ring"
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label="Five-agent debate ring"
    >
      {/* debate links: every agent challenges every other */}
      {pts.map((p, i) =>
        pts.slice(i + 1).map((q, j) => (
          <line
            key={`${i}-${j}`}
            x1={p.x}
            y1={p.y}
            x2={q.x}
            y2={q.y}
            className="dr-link"
          />
        ))
      )}

      {/* the judge at the centre */}
      <g className="dr-core">
        <rect x={CX - 26} y={CY - 26} width="52" height="52" className="dr-core-box" />
        <path
          d={`M${CX - 16} ${CY - 6} L${CX} ${CY - 15} L${CX + 16} ${CY - 6} L${CX + 16} ${CY + 9} L${CX} ${CY + 18} L${CX - 16} ${CY + 9} Z`}
          className="dr-core-cube"
        />
        <path d={`M${CX - 16} ${CY - 6} L${CX} ${CY + 3} L${CX + 16} ${CY - 6}`} className="dr-core-cube" />
        <path d={`M${CX} ${CY + 3} L${CX} ${CY + 18}`} className="dr-core-cube" />
        <text x={CX} y={CY + 46} className="dr-core-label">
          JUDGE
        </text>
      </g>

      {ORDER.map((key, i) => {
        const a = byKey.get(key);
        const { x, y } = pts[i];
        const state = !a
          ? running
            ? "waiting"
            : "idle"
          : !a.ok
          ? "silent"
          : a.position.toLowerCase();
        return (
          <g key={key} className={`dr-node ${state}`}>
            <circle cx={x} cy={y} r={NODE_R} className="dr-ring-bg" />
            {/* confidence arc */}
            {a?.ok && <ConfidenceArc x={x} y={y} pct={a.confidence} />}
            <text x={x} y={y - 6} className="dr-name">
              {LABEL[key].toUpperCase()}
            </text>
            <text x={x} y={y + 12} className="dr-pos">
              {a?.ok ? a.position : running ? "…" : a ? "SILENT" : "—"}
            </text>
            {a?.ok && (
              <text x={x} y={y + 28} className="dr-conf">
                {a.confidence}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

function ConfidenceArc({ x, y, pct }: { x: number; y: number; pct: number }) {
  const r = NODE_R;
  const frac = Math.max(0, Math.min(100, pct)) / 100;
  const circ = 2 * Math.PI * r;
  return (
    <circle
      cx={x}
      cy={y}
      r={r}
      className="dr-arc"
      strokeDasharray={`${circ * frac} ${circ}`}
      transform={`rotate(-90 ${x} ${y})`}
    />
  );
}
