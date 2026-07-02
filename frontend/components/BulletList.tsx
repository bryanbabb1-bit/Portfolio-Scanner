// Shared scannable bullet list — the house style for insights, actions and
// risks everywhere in the app (never render advisor output as prose walls).
export function BulletList({
  items,
  kind,
}: {
  items?: string[];
  kind?: "insight" | "action" | "risk";
}) {
  if (!items?.length) return null;
  return (
    <ul className={`bullets ${kind || "insight"}`}>
      {items.map((t, i) => (
        <li key={i}>{t}</li>
      ))}
    </ul>
  );
}
