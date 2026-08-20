"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { API_BASE } from "../lib/api";

/* The partner trade hiding inside a holding.
 *
 * Built after MRNA ran 177% on a Phase 3 readout whose sponsor, MRK, was
 * already in the book. MRK rose 12.6% on the same news. The partner is the
 * leveraged version of a result you were already exposed to, and the registry
 * has published that pairing since 2023.
 *
 * There is deliberately no countdown on this panel. The trial that moved
 * Moderna is registered to complete in 2029 — event-driven endpoints read out
 * when the events land, not on the filed date, so a date here would be a
 * confident-looking lie. The ranking is leverage.
 */

interface Partner {
  name: string;
  symbol: string;
  market_cap: number | null;
  leverage: number | null;
}

interface Trial {
  nct: string;
  title: string;
  status: string;
  primary_completion: string | null;
  last_update: string | null;
  phases: string[];
  sponsor: string;
  holding: string;
  conditions: string[];
  partners: Partner[];
}

interface CatalystMap {
  ts: number;
  covered: string[];
  uncovered: string[];
  trials: Trial[];
  note: string;
}

const cap = (v: number | null) =>
  v == null ? "" : v >= 1e12 ? `$${(v / 1e12).toFixed(1)}T`
    : v >= 1e9 ? `$${(v / 1e9).toFixed(0)}B`
    : `$${(v / 1e6).toFixed(0)}M`;

export function CatalystMap() {
  const [m, setM] = useState<CatalystMap | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/catalysts`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d && Array.isArray(d.trials) && setM(d))
      .catch(() => {});
  }, []);

  if (!m || !m.trials.length) return null;

  return (
    <>
      <div className="mfx-label">Partner leverage · late-stage trials on names you hold</div>
      <div className="card cat">
        <p className="cat-lead">
          Every row is a Phase 3 trial run by a company in your book, with
          enrolment closed, that has a listed partner on the other side of it.
          If the data is good you make money on the holding — and{" "}
          <strong>the partner makes multiples of it</strong>, because the
          partner is the smaller company — the multiple beside each one is how
          much smaller. That is the whole MRNA trade: same
          readout, MRK +12.6%, Moderna +177%.
        </p>

        <div className="cat-list">
          {m.trials.map((t) => (
            <div key={t.nct} className="cat-row">
              <span className="cat-hold">{t.holding}</span>
              <span className="cat-arrow">→</span>
              <span className="cat-partners">
                {t.partners.map((p) => (
                  <Link key={p.symbol} href={`/stock/${p.symbol}`} className="cat-partner">
                    <span className="cp-sym">{p.symbol}</span>
                    {p.leverage != null && (
                      <span className="cp-lev" title={`${p.leverage}x smaller than ${t.holding}`}>
                        {p.leverage}x
                      </span>
                    )}
                    {p.market_cap != null && <span className="cp-cap">{cap(p.market_cap)}</span>}
                  </Link>
                ))}
              </span>
              <span className="cat-what">
                <span className="cat-title">{t.title}</span>
                <span className="cat-meta">
                  {t.nct}
                  {t.conditions.length > 0 && ` · ${t.conditions.slice(0, 2).join(", ")}`}
                  {t.primary_completion && ` · filed to complete ${t.primary_completion}`}
                </span>
              </span>
              <a
                className="cat-go"
                href={`https://clinicaltrials.gov/study/${t.nct}`}
                target="_blank"
                rel="noreferrer"
              >
                Registry →
              </a>
            </div>
          ))}
        </div>

        <p className="cat-warn">
          The filed completion dates are a plan, not a forecast. The trial that
          moved Moderna 177% is registered to complete in <strong>2029</strong>{" "}
          and read out in 2026 — event-driven endpoints land when the events do.
          Rank these by leverage, never by date.
        </p>

        {m.uncovered.length > 0 && (
          <p className="cat-cover">
            Covers {m.covered.join(", ")}. The other {m.uncovered.length} names
            in the book run no registered trials — this map has nothing to say
            about them.
          </p>
        )}
      </div>
    </>
  );
}
