import type { ReactNode } from "react";

/* The poster's footer spec bar: drawing metadata on the flanks, the tagline
   in the middle. Purely decorative chrome — never put real data here. */
export function TelemetryStrip({
  left = [
    ["Grid", "8PT"],
    ["Baseline", "4PT"],
    ["Origin", "(0,0)"],
  ],
  right = [
    ["Engine", "LOCAL"],
    ["Model", "CLAUDE"],
    ["Data", "LIVE"],
  ],
  line1,
  line2,
}: {
  left?: [string, string][];
  right?: [string, string][];
  line1: ReactNode;
  line2?: ReactNode;
}) {
  return (
    <div className="telemetry">
      <div>
        {left.map(([k, v]) => (
          <div key={k}>
            <span className="tel-k">{k}:</span>
            <span className="tel-v">{v}</span>
          </div>
        ))}
      </div>
      <div className="tel-mid">
        <span>{line1}</span>
        {line2 && <span className="hot">{line2}</span>}
      </div>
      <div>
        {right.map(([k, v]) => (
          <div key={k}>
            <span className="tel-k">{k}:</span>
            <span className="tel-v">{v}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
