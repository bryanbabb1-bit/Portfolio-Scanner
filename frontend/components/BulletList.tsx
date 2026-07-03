"use client";
import { useState } from "react";

// Shared scannable bullet list — the house style for insights, actions and
// risks everywhere in the app (never render advisor output as prose walls).
// Pass onPin to make each bullet pinnable to the persistent action list.
export function BulletList({
  items,
  kind,
  onPin,
}: {
  items?: string[];
  kind?: "insight" | "action" | "risk";
  onPin?: (text: string) => Promise<unknown> | void;
}) {
  const [pinned, setPinned] = useState<Set<string>>(new Set());
  if (!items?.length) return null;

  async function pin(text: string) {
    if (!onPin || pinned.has(text)) return;
    await onPin(text);
    setPinned((prev) => new Set(prev).add(text));
  }

  return (
    <ul className={`bullets ${kind || "insight"}`}>
      {items.map((t, i) => (
        <li key={i} className={onPin ? "pinnable" : ""}>
          {t}
          {onPin && (
            <button
              className={`pin-btn${pinned.has(t) ? " pinned" : ""}`}
              title={pinned.has(t) ? "Pinned to your action list" : "Pin to your action list"}
              onClick={(e) => {
                e.preventDefault();
                pin(t);
              }}
            >
              {pinned.has(t) ? "Pinned" : "Pin"}
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}
