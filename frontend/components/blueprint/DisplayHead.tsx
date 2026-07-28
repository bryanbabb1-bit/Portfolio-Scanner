import type { ReactNode } from "react";

/* The big condensed poster head: two lines, the second in olive or orange,
   a short orange rule underneath, then a mono subtitle. */
export function DisplayHead({
  line1,
  line2,
  tone = "alt",
  sub,
}: {
  line1: string;
  /** second line, coloured */
  line2?: string;
  /** "alt" = olive, "hot" = orange */
  tone?: "alt" | "hot";
  sub?: ReactNode;
}) {
  return (
    <div>
      <h1 className="display-head">
        {line1}
        {line2 && (
          <>
            <br />
            <span className={tone === "hot" ? "dh-hot" : "dh-alt"}>{line2}</span>
          </>
        )}
      </h1>
      <div className="dh-rule" />
      {sub && <div className="dh-sub">{sub}</div>}
    </div>
  );
}
