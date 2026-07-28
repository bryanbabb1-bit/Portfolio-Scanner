"use client";
import { BLUEPRINT } from "../lib/palette";

export function ScoreRing({ score }: { score: number }) {
  const hi = score >= 60;
  const color = hi ? "var(--bull)" : "var(--accent)";
  return (
    <div
      className="score-ring"
      style={{
        // @ts-ignore custom prop
        "--v": score,
        background: `conic-gradient(${color} ${score}%, ${BLUEPRINT.grid} 0)`,
        border: `1px solid ${hi ? BLUEPRINT.olive : BLUEPRINT.rule}`,
      }}
    >
      <div className="inner">
        {score.toFixed(0)}
        <span className="ring-cap">score</span>
      </div>
    </div>
  );
}
