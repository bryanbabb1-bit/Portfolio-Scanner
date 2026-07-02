"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ConvictionSignal } from "../lib/api";
import { money } from "./format";
import { BulletList } from "./BulletList";

const LEGACY_KEY = "pscan-dismissed-signals";

// Full-screen conviction alert. Dismissal is SERVER-SIDE (per signal id):
// dismissed signals vanish from the popup and the strip on every device.
// A new fire — different rule, or the same rule after its cooldown — mints
// a new id and pops again, so suppressing today never mutes tomorrow.
export function SignalSlap({
  signals,
  onDismissed,
}: {
  signals: ConvictionSignal[];
  onDismissed: (ids: string[]) => void;
}) {
  const [idx, setIdx] = useState(0);

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

  const pending = signals.filter((s) => !s.dismissed);
  if (!pending.length) return null;
  const s = pending[Math.min(idx, pending.length - 1)];
  const buy = s.side === "buy";

  async function dismiss(all = false) {
    const ids = all ? pending.map((p) => p.id) : [s.id];
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
          <h4>The What</h4>
          <p>{s.what}</p>
        </div>
        <div className="slap-sec">
          <h4>The Why</h4>
          <BulletList items={s.why} kind="insight" />
        </div>
        <div className="slap-levels">
          <div className="slap-level">
            <span className="label">{buy ? "Target" : "Downside risk"}</span>
            <span>{s.target}</span>
          </div>
          <div className="slap-level">
            <span className="label">{buy ? "Invalidation / stop" : "What reverses this"}</span>
            <span>{s.stop}</span>
          </div>
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
