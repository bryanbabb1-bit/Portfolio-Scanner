"use client";
import { useEffect, useRef, useState } from "react";
import { PortfolioSummary } from "../lib/api";
import { money, pct } from "./format";

/* The balance, and nothing else, at the top of the sheet.
 *
 * It used to sit third — under the masthead, the watchdog strip and last
 * night's rulings — so the first number on the page was never the number you
 * opened the app for. It is now the first thing rendered, and a condensed bar
 * takes over as soon as it scrolls out of view, so the account value is on
 * screen the entire time you are on the dashboard.
 */
/** Height of the sticky nav the condensed bar tucks under. */
const NAV_H = 62;

export function BalanceBar({ summary }: { summary: PortfolioSummary }) {
  const head = useRef<HTMLElement>(null);
  const [stuck, setStuck] = useState(false);

  useEffect(() => {
    // Measured on scroll rather than observed: an IntersectionObserver on a
    // zero-height sentinel reports the bar as stuck before you have scrolled
    // at all on a tall viewport.
    const onScroll = () => {
      const r = head.current?.getBoundingClientRect();
      setStuck(!!r && r.bottom < NAV_H);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);

  const dayCls = summary.day_change >= 0 ? "up" : "down";
  const totalCls = summary.total_return >= 0 ? "up" : "down";

  return (
    <>
      <header className="mfx-head" ref={head}>
        <div className="lead">
          <div className="eyebrow">
            <span className="pulse" /> Book · {summary.positions} positions · {summary.source} data
          </div>
          {/* Set, not animated. The odometer rolled every digit on a 60s poll,
              which drew the eye to the cents and away from the number. */}
          <div className="val">{money(summary.total_market_value, 2)}</div>
          <div className="deltas">
            <span className={`mfx-chip ${dayCls}`}>
              <span className="k">Today</span>
              {money(summary.day_change, 0)} ({pct(summary.day_change_pct)})
            </span>
            <span className={`mfx-chip ${summary.total_unrealized_pl >= 0 ? "up" : "down"}`}>
              <span className="k">Unrealized</span>
              {money(summary.total_unrealized_pl, 0)} ({pct(summary.total_unrealized_pl_pct)})
            </span>
            {summary.realized_pl !== 0 && (
              <span className={`mfx-chip ${summary.realized_pl >= 0 ? "up" : "down"}`}>
                <span className="k">Realized</span>
                {money(summary.realized_pl, 0)}
              </span>
            )}
            <span className={`mfx-chip total ${totalCls}`}>
              <span className="k">Total return</span>
              {money(summary.total_return, 0)} ({pct(summary.total_return_pct)})
            </span>
          </div>
        </div>
        <div className="quickstats">
          {/* Position count is already in the eyebrow — this rail is the money. */}
          <div className="qs">
            <div className="l">Cost basis</div>
            <div className="v">{money(summary.total_cost, 0)}</div>
          </div>
          <div className="qs">
            <div className="l">Dry powder</div>
            <div className="v">{money(summary.cash, 0)}</div>
          </div>
        </div>
      </header>
      <div className={`bal-stick ${stuck ? "show" : ""}`} aria-hidden={!stuck}>
        <div className="container bal-stick-inner">
          <span className="bs-val">{money(summary.total_market_value, 0)}</span>
          <span className={`mfx-chip ${dayCls}`}>
            <span className="k">Today</span>
            {money(summary.day_change, 0)} ({pct(summary.day_change_pct)})
          </span>
          <span className={`mfx-chip total ${totalCls}`}>
            <span className="k">Total</span>
            {money(summary.total_return, 0)} ({pct(summary.total_return_pct)})
          </span>
          <span className="bs-cash">
            <span className="k">Cash</span>
            {money(summary.cash, 0)}
          </span>
        </div>
      </div>
    </>
  );
}
