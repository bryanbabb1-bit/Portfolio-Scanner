/* The desk's ground. One soft lamp from above and nothing else — no dot grid,
   no canvas, no rAF loop. The blueprint skin drew graph paper because it was
   pretending to be a drafting table; this room is lit, not printed. */
export function DeskBackground() {
  return <div className="desk-bg" aria-hidden />;
}
