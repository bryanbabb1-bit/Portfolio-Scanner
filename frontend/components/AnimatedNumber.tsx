"use client";
import { useEffect, useRef, useState } from "react";

// Eases a numeric display toward its new value — the dashboard breathes
// instead of snapping. requestAnimationFrame, no dependencies.
export function AnimatedNumber({
  value,
  format,
  duration = 700,
}: {
  value: number;
  format: (n: number) => string;
  duration?: number;
}) {
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  const raf = useRef<number>(0);

  useEffect(() => {
    const start = performance.now();
    const begin = from.current;
    const delta = value - begin;
    if (delta === 0) return;
    cancelAnimationFrame(raf.current);
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3); // ease-out cubic
      setShown(begin + delta * eased);
      if (t < 1) raf.current = requestAnimationFrame(step);
      else from.current = value;
    };
    raf.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf.current);
  }, [value, duration]);

  return <>{format(shown)}</>;
}
