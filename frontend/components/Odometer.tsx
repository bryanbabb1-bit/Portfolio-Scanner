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
/* The strip repeats the run several times so a wrap always has somewhere to
   travel to. RUNS only has to cover one roll plus a roll that interrupts it —
   the column normalises back to REST as soon as it settles. */
const RUNS = 4;
const CELLS = DIGITS.length * RUNS;
const REST = 10; // the run a resting column sits in: cells 10..19

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

  // The column's ABSOLUTE cell index on the strip — not a running total of
  // wraps. It used to be `turns * 10 + n` with `turns` only ever counting up,
  // so after three wraps the offset walked past the end of the strip and the
  // column went blank. A fast-moving digit (the cents) burned through that in
  // minutes, which is what left half the number missing.
  const [pos, setPos] = useState(REST + n);
  // While true the column is repositioned WITHOUT animating — used to drop
  // back a whole run, which lands on the same glyph so nothing moves on screen.
  const [snap, setSnap] = useState(false);
  const posRef = useRef(REST + n);
  const prev = useRef(n);

  useEffect(() => {
    if (!animate) {
      prev.current = n;
      return;
    }
    // Always roll FORWARD, so 9 -> 0 wraps past the seam instead of spinning
    // backwards through eight digits.
    const delta = (n - prev.current + 10) % 10;
    prev.current = n;
    if (!delta) return;

    const target = posRef.current + delta;
    if (target > CELLS - 1) {
      // No strip left — this only happens if rolls stack up faster than they
      // settle. Take the position without animating rather than roll into
      // empty space.
      setSnap(true);
      posRef.current = REST + n;
    } else {
      posRef.current = target;
    }
    setPos(posRef.current);
  }, [n, animate]);

  // Once the roll lands, drop back to the resting run so the next roll always
  // has a full run of strip ahead of it. Same glyph, so the reset is invisible.
  const settle = () => {
    if (posRef.current === REST + n) return;
    setSnap(true);
    posRef.current = REST + n;
    setPos(posRef.current);
  };

  // Re-arm the transition on the frame after a snap. The transform doesn't
  // change here, so nothing animates on the way back.
  useEffect(() => {
    if (!snap) return;
    const id = requestAnimationFrame(() => setSnap(false));
    return () => cancelAnimationFrame(id);
  }, [snap]);

  return (
    <span className="odo-d" aria-hidden>
      {/* Sizes the column to a real glyph in the real font. Widest digit, not
          "0", so nothing clips when the strip rolls past it. */}
      <span className="odo-ghost">4</span>
      <span
        className="odo-strip"
        onTransitionEnd={settle}
        style={{
          // --odo-h is the cell height; one step must travel exactly one cell.
          transform: `translateY(calc(var(--odo-h) * -${pos}))`,
          transition: animate && !snap ? undefined : "none",
        }}
      >
        {Array.from({ length: CELLS }, (_, i) => (
          <span key={i}>{DIGITS[i % 10]}</span>
        ))}
      </span>
    </span>
  );
}
