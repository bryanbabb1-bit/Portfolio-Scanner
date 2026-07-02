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
        background: `conic-gradient(${color} ${score}%, rgba(120,140,190,0.14) 0)`,
        boxShadow: `0 0 18px ${hi ? "rgba(52,211,153,0.45)" : "rgba(56,189,248,0.40)"}`,
      }}
    >
      <div className="inner">
        {score.toFixed(0)}
        <span className="ring-cap">score</span>
      </div>
    </div>
  );
}
