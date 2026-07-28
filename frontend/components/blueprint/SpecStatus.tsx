import type { ReactNode } from "react";

/* "STATUS: ACTIVE ●" telemetry chip. */
export function SpecStatus({
  label = "Status",
  value,
  tone = "live",
}: {
  label?: string;
  value: string;
  tone?: "live" | "idle" | "alert";
}) {
  return (
    <span className={`spec-status ${tone === "live" ? "" : tone}`}>
      {label}: <b>{value}</b>
      <span className="dot" />
    </span>
  );
}

/* Honest empty state — says what is missing instead of printing a fake number.
   Used wherever a metric needs more history than the book currently has. */
export function SpecEmpty({ children }: { children: ReactNode }) {
  return <div className="spec-empty">{children}</div>;
}
