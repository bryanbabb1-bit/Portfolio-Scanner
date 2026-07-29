"use client";
import { useEffect, useRef, useState } from "react";

/* Odometer — digits ROLL to their new value instead of snapping.
 *
 * The app already had AnimatedNumber, which eases the underlying number and
 * re-renders the text. That reads as a blur of changing glyphs. A real
 * odometer moves each digit column independently, so you see the mechanism —
 * which is the whole point: it should feel like an instrument, not a label.
 *
 * Non-digits (currency marks, separators, decimal points) are rendered as
 * static characters so the column count stays stable while the value changes.
 */

const DIGITS = "0123456789";

export function Odometer({
  value,
  prefix = "",
  decimals = 2,
  className = "",
}: {
  value: number;
  prefix?: string;
  decimals?: number;
  className?: string;
}) {
  const text =
    prefix +
    Math.abs(value)
      .toFixed(decimals)
      .replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const chars = (value < 0 ? "-" : "") + text;

  // Render nothing animated until mounted, so the server and first client
  // paint agree and the digits don't visibly jump on hydration.
  const [ready, setReady] = useState(false);
  useEffect(() => setReady(true), []);

  return (
    <span className={`odo ${className}`} aria-label={chars}>
      {chars.split("").map((ch, i) =>
        ch >= "0" && ch <= "9" ? (
          <Digit key={i} char={ch} animate={ready} />
        ) : (
          <span key={i} className="odo-sep" aria-hidden>
            {ch}
          </span>
        )
      )}
    </span>
  );
}

function Digit({ char, animate }: { char: string; animate: boolean }) {
  const n = DIGITS.indexOf(char);
  const prev = useRef(n);
  // Track how far we've travelled so 9 -> 0 rolls FORWARD past the wrap
  // instead of spinning backwards through eight digits.
  const [turns, setTurns] = useState(0);

  useEffect(() => {
    if (!animate) return;
    if (n < prev.current) setTurns((t) => t + 1);
    prev.current = n;
  }, [n, animate]);

  // Travel in EM, not percent. Percent resolves against the strip's own
  // height (30 digits = 30em), so a "10%" step moved three digits at a time
  // and the column showed two glyphs at once.
  const steps = turns * 10 + n;

  return (
    <span className="odo-d" aria-hidden>
      {/* Sizes the column to a real glyph in the real font. Widest digit, not
          "0", so nothing clips when the strip rolls past it. */}
      <span className="odo-ghost">4</span>
      <span
        className="odo-strip"
        style={{
          // --odo-h is the cell height; one step must travel exactly one cell.
          transform: `translateY(calc(var(--odo-h) * -${steps}))`,
          transition: animate ? undefined : "none",
        }}
      >
        {/* Two full runs so a wrap always has somewhere to travel to. */}
        {(DIGITS + DIGITS + DIGITS).split("").map((d, i) => (
          <span key={i}>{d}</span>
        ))}
      </span>
    </span>
  );
}
