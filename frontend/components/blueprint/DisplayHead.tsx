import type { ReactNode } from "react";

/* The page head: two lines set in the display serif, the second coloured, a
   short brass rule underneath, then a mono subtitle. It was a condensed
   poster head under the blueprint skin; the type changed, the structure did
   not. */
export function DisplayHead({
  line1,
  line2,
  tone = "alt",
  sub,
}: {
  line1: string;
  /** second line, coloured */
  line2?: string;
  /** "alt" = navy, "hot" = brass */
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
