"use client";
import { useEffect, useRef, useState } from "react";

/* Reveal a list one item at a time.
 *
 * The debate arrives from the server as one finished object. Rendering it all
 * at once makes it a document; releasing it in sequence makes it an event —
 * which is what it actually was. No extra model calls, no extra latency: the
 * work is already done, this only controls how it lands.
 *
 * Returns how many items should currently be visible. Jumps straight to the
 * full count for a cached result (nothing to dramatise about re-reading a
 * saved ruling) and for reduced-motion users.
 */
export function useStagedReveal(
  total: number,
  { stepMs = 1100, live = true }: { stepMs?: number; live?: boolean } = {}
) {
  const [shown, setShown] = useState(live ? 0 : total);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    timers.current.forEach(clearTimeout);
    timers.current = [];

    const reduce =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (!live || reduce || total === 0) {
      setShown(total);
      return;
    }
    setShown(0);
    for (let i = 1; i <= total; i++) {
      timers.current.push(setTimeout(() => setShown(i), i * stepMs));
    }
    return () => {
      timers.current.forEach(clearTimeout);
      timers.current = [];
    };
  }, [total, stepMs, live]);

  return shown;
}
