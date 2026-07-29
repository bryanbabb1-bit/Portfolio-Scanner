"use client";
import { useEffect, useRef, useState } from "react";

/* Split-flap — a solari departure board.
 *
 * The most recognisable object in finance, and it belongs in the blueprint
 * language for the same reason the crosshairs and spec panels do: it is an
 * ANALOG INSTRUMENT, not a web widget.
 *
 * It flips only when a value actually CHANGES. A board that churns on every
 * poll is a screensaver; one that moves when the market moves is information.
 */

const GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,+-$% ";

export function SplitFlapText({
  value,
  width,
  className = "",
}: {
  value: string;
  /** Fixed cell count so the board never reflows as values change. */
  width: number;
  className?: string;
}) {
  const target = value.slice(0, width).padEnd(width, " ");
  return (
    <span className={`sf ${className}`} aria-label={value.trim()}>
      {target.split("").map((ch, i) => (
        <Cell key={i} char={ch} delay={i * 45} />
      ))}
    </span>
  );
}

function Cell({ char, delay }: { char: string; delay: number }) {
  const [shown, setShown] = useState(char);
  const [spinning, setSpinning] = useState(false);
  const settled = useRef(char);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    if (char === settled.current) return;
    settled.current = char;

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setShown(char);
      return;
    }

    timers.current.forEach(clearTimeout);
    timers.current = [];
    // Stagger by column so the board resolves left to right, the way a real
    // one does — every cell landing at once looks like a text swap.
    timers.current.push(
      setTimeout(() => {
        setSpinning(true);
        const steps = 7 + Math.floor(Math.random() * 6);
        let n = 0;
        const tick = () => {
          n += 1;
          if (n >= steps) {
            setShown(char);
            setSpinning(false);
            return;
          }
          setShown(GLYPHS[Math.floor(Math.random() * GLYPHS.length)]);
          timers.current.push(setTimeout(tick, 38));
        };
        tick();
      }, delay)
    );

    return () => {
      timers.current.forEach(clearTimeout);
      timers.current = [];
    };
  }, [char, delay]);

  return (
    <span className={`sf-cell ${spinning ? "spin" : ""}`} aria-hidden>
      {shown === " " ? " " : shown}
    </span>
  );
}
