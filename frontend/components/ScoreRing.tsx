"use client";

export function ScoreRing({ score }: { score: number }) {
  const hi = score >= 60;
  const color = hi ? "var(--bull)" : "var(--accent)";
  return (
    <div
      className="score-ring"
      style={{
        // @ts-ignore custom prop
        "--v": score,
        // Straight token references: the ring re-paints on a theme change
        // without this component knowing a theme exists.
        background: `conic-gradient(${color} ${score}%, var(--chart-grid) 0)`,
        border: `1px solid ${hi ? "var(--bull)" : "var(--rule)"}`,
      }}
    >
      <div className="inner">
        {score.toFixed(0)}
        <span className="ring-cap">score</span>
      </div>
    </div>
  );
}
