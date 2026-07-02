"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ConvictionSignal } from "../lib/api";
import { money } from "./format";
import { BulletList } from "./BulletList";

const DISMISSED_KEY = "pscan-dismissed-signals";

function loadDismissed(): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(DISMISSED_KEY) || "[]"));
  } catch {
    return new Set();
  }
}

function saveDismissed(ids: Set<string>) {
  try {
    localStorage.setItem(DISMISSED_KEY, JSON.stringify(Array.from(ids).slice(-100)));
  } catch {}
}

// Full-screen conviction alert: when the engine sees a strong buy or sell
// setup, this takes over the screen until acknowledged.
export function SignalSlap({ signals }: { signals: ConvictionSignal[] }) {
  const [dismissed, setDismissed] = useState<Set<string> | null>(null);
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    setDismissed(loadDismissed());
  }, []);

  if (!dismissed) return null;
  const pending = signals.filter((s) => !dismissed.has(s.id));
  if (!pending.length) return null;
  const s = pending[Math.min(idx, pending.length - 1)];
  const buy = s.side === "buy";

  function dismiss(all = false) {
    const next = new Set(dismissed as Set<string>);
    if (all) pending.forEach((p) => next.add(p.id));
    else next.add(s.id);
    setDismissed(next);
    saveDismissed(next);
    setIdx(0);
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
                const { api } = await import("../lib/api");
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
