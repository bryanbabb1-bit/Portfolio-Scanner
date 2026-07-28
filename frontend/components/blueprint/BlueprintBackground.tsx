/* Graph-paper backdrop. Replaces the old animated NeuralBackground canvas —
   the blueprint language wants a printed grid, not a glow, and this costs no
   JS and no rAF loop (the canvas ran continuously on a 24/7 dashboard). */
export function BlueprintBackground() {
  return <div className="blueprint-bg" aria-hidden />;
}
