import type { ReactNode } from "react";

/* The house panel: hairline border, drawn corner ticks, mono caption rule.
   Use instead of .card on every blueprint surface. */
export function SpecPanel({
  title,
  aux,
  plus = true,
  className = "",
  children,
}: {
  /** mono caption on the head rule, e.g. "RISK STATUS" */
  title?: string;
  /** right-aligned secondary caption, e.g. "LAST UPDATE 2 MIN AGO" */
  aux?: ReactNode;
  /** the poster's "+" affordance mark */
  plus?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={`spec-panel ${className}`}>
      <i className="ct tl" aria-hidden />
      <i className="ct tr" aria-hidden />
      <i className="ct bl" aria-hidden />
      <i className="ct br" aria-hidden />
      {title && (
        <header className="sp-head">
          <span>{title}</span>
          <span className="sp-aux">
            {aux}
            {plus && <span className="sp-plus"> +</span>}
          </span>
        </header>
      )}
      {children}
    </section>
  );
}
