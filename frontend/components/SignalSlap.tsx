"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ConvictionSignal } from "../lib/api";
import { money } from "./format";
import { AdvisorChat } from "./AdvisorChat";
import { BulletList } from "./BulletList";

const LEGACY_KEY = "pscan-dismissed-signals";

// Full-screen conviction alert. Dismissal is SERVER-SIDE (per signal id):
// dismissed signals vanish from the popup and the strip on every device.
// A new fire — different rule, or the same rule after its cooldown — mints
// a new id and pops again, so suppressing today never mutes tomorrow.
export function SignalSlap({
  signals,
  onDismissed,
  focusId,
}: {
  signals: ConvictionSignal[];
  onDismissed: (ids: string[]) => void;
  focusId?: string | null;
}) {
  const [idx, setIdx] = useState(0);
  // Signals dismissed this session — overrides focusId so "Got it" actually
  // closes a slap you opened from a notification tap.
  const [localDismissed, setLocalDismissed] = useState<Set<string>>(new Set());

  // One-time migration: ids dismissed under the old localStorage scheme get
  // dismissed server-side so they don't re-pop after the upgrade.
  useEffect(() => {
    try {
      const legacy: string[] = JSON.parse(localStorage.getItem(LEGACY_KEY) || "[]");
      if (legacy.length) {
        const active = new Set(signals.map((s) => s.id));
        const toMigrate = legacy.filter((id) => active.has(id));
        Promise.all(toMigrate.map((id) => api.dismissSignal(id).catch(() => {})))
          .then(() => {
            if (toMigrate.length) onDismissed(toMigrate);
          });
        localStorage.removeItem(LEGACY_KEY);
      }
    } catch {}
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // A tapped notification (focusId) surfaces that exact signal first — even if
  // it was dismissed elsewhere — UNLESS it was dismissed in this view.
  let pending = signals.filter((s) => !s.dismissed && !localDismissed.has(s.id));
  if (focusId && !localDismissed.has(focusId)) {
    const focused = signals.find((s) => s.id === focusId && !localDismissed.has(s.id));
    if (focused) pending = [focused, ...pending.filter((s) => s.id !== focusId)];
  }
  if (!pending.length) return null;
  const s = pending[Math.min(idx, pending.length - 1)];
  const buy = s.side === "buy";
  const action = (s as any).action as string | undefined;

  async function dismiss(all = false) {
    const ids = all ? pending.map((p) => p.id) : [s.id];
    setLocalDismissed((prev) => {
      const n = new Set(prev);
      ids.forEach((i) => n.add(i));
      return n;
    });
    onDismissed(ids); // optimistic — hide immediately
    setIdx(0);
    try {
      if (all) await api.dismissSignal();
      else await api.dismissSignal(s.id);
    } catch {}
  }

  return (
    <div className="slap-overlay" role="alertdialog" aria-label="Conviction signal">
      <div className={`slap-card ${buy ? "buy" : "sell"}`}>
        <div className={`slap-banner ${buy ? "buy" : "sell"}`}>
          {buy ? "BUYING OPPORTUNITY" : "STRONG SELL SIGNAL"}
          <button className="slap-close" onClick={() => dismiss()} aria-label="Dismiss">✕</button>
        </div>
        <div className="slap-head">
          <span className="slap-sym">{s.symbol}</span>
          <span className="slap-price">{money(s.price)}</span>
          {s.theme && <span className="theme-tag">{s.theme}</span>}
          {s.held != null && (
            <span className="mut" style={{ fontSize: 12 }}>{s.held ? "in your portfolio" : "new name"}</span>
          )}
          {pending.length > 1 && (
            <span className="slap-count">{Math.min(idx, pending.length - 1) + 1} of {pending.length}</span>
          )}
        </div>
        <div className="slap-headline">{s.headline}</div>

        <div className="slap-sec">
          <h4>{action ? `Advisor: ${action}` : "The What"}</h4>
          <p>{s.what}</p>
        </div>
        <div className="slap-sec">
          <h4>The Why</h4>
          <BulletList items={s.why} kind="insight" />
        </div>
        {(s.entry || s.size || s.target || s.stop) && (
          <div className="slap-plan">
            {s.entry && (
              <div className="slap-level"><span className="label">Entry</span><span>{s.entry}</span></div>
            )}
            {s.size && (
              <div className="slap-level"><span className="label">Size</span><span>{s.size}</span></div>
            )}
            {s.target && (
              <div className="slap-level"><span className="label">{buy ? "Target" : "Downside risk"}</span><span>{s.target}</span></div>
            )}
            {s.stop && (
              <div className="slap-level"><span className="label">{buy ? "Stop / invalidation" : "What reverses this"}</span><span>{s.stop}</span></div>
            )}
          </div>
        )}

        <div className="slap-sec">
          <h4>Ask the advisor</h4>
          <AdvisorChat kind="stock" symbol={s.symbol} />
        </div>

        <div className="slap-actions">
          <Link href={`/stock/${s.symbol}`} className="btn" onClick={() => dismiss()}>
            Open {s.symbol}
          </Link>
          <button
            className="btn ghost"
            onClick={async () => {
              try {
                await api.addPin({
                  symbol: s.symbol,
                  source: "signal",
                  text: s.what,
                  points: [s.target, s.stop].filter(Boolean),
                });
              } catch {}
              dismiss();
            }}
          >
            Pin action
          </button>
          {pending.length > 1 && idx < pending.length - 1 && (
            <button className="btn ghost" onClick={() => setIdx(idx + 1)}>
              Next signal
            </button>
          )}
          <button className="btn ghost" onClick={() => dismiss()}>
            Got it
          </button>
          {pending.length > 1 && (
            <button className="btn ghost" onClick={() => dismiss(true)}>
              Dismiss all
            </button>
          )}
        </div>
        <p className="mut" style={{ fontSize: 11, marginTop: 10 }}>
          Rule: {s.label} · {s.generated_at} · Not personalized investment advice.
        </p>
      </div>
    </div>
  );
}
