"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { NotificationBell } from "./NotificationBell";
import { ThemeSwitch } from "./ThemeSwitch";

type Item = { href: string; label: string };
type Entry = Item | { label: string; items: Item[] };

// Twelve destinations is too many for one row. "Desk" holds the hedge-fund
// surfaces (the system reasoning about your book); "Research" holds the
// scanners (finding things to reason about).
const NAV: Entry[] = [
  { href: "/", label: "Dashboard" },
  { href: "/book", label: "The Book" },
  {
    label: "Desk",
    items: [
      { href: "/risk", label: "Risk Desk" },
      { href: "/debate", label: "Agent Debate" },
      { href: "/backtest", label: "Backtest" },
      { href: "/paper", label: "Paper Lab" },
      { href: "/loop", label: "Learning Loop" },
    ],
  },
  {
    label: "Research",
    items: [
      { href: "/scan", label: "Scan Hub" },
      { href: "/breakouts", label: "Breakout Radar" },
      { href: "/discover", label: "Discovery" },
      { href: "/runners", label: "Runner Radar" },
      { href: "/news", label: "News Wire" },
    ],
  },
  { href: "/settings", label: "Settings" },
];

const isGroup = (e: Entry): e is { label: string; items: Item[] } => "items" in e;

export function Nav() {
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const [menu, setMenu] = useState<string | null>(null);
  const navRef = useRef<HTMLElement>(null);

  const isActive = (href: string) =>
    href === "/" ? path === "/" : path.startsWith(href);

  // Close the drawer and any open group menu whenever the route changes.
  useEffect(() => {
    setOpen(false);
    setMenu(null);
  }, [path]);

  // A group menu should dismiss on an outside click, like any real dropdown.
  useEffect(() => {
    if (!menu) return;
    const onDown = (e: MouseEvent) => {
      if (!navRef.current?.contains(e.target as Node)) setMenu(null);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [menu]);

  return (
    <nav className="nav" ref={navRef}>
      <div className="container nav-inner">
        <Link href="/" className="brand">
          Watch<span>dog</span>
        </Link>

        {/* wide screens: inline tabs, groups as dropdowns */}
        <div className="nav-links wide">
          {NAV.map((e) =>
            isGroup(e) ? (
              <div
                key={e.label}
                className={`nav-group ${
                  e.items.some((i) => isActive(i.href)) ? "active" : ""
                }`}
              >
                <button
                  onClick={() => setMenu((m) => (m === e.label ? null : e.label))}
                  aria-expanded={menu === e.label}
                >
                  {e.label}
                  <span className="caret">▼</span>
                </button>
                {menu === e.label && (
                  <div className="nav-menu">
                    {e.items.map((i) => (
                      <Link
                        key={i.href}
                        href={i.href}
                        className={isActive(i.href) ? "active" : ""}
                      >
                        {i.label}
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <Link
                key={e.href}
                href={e.href}
                className={isActive(e.href) ? "active" : ""}
              >
                {e.label}
              </Link>
            )
          )}
        </div>

        <div className="nav-right">
          <ThemeSwitch />
          <NotificationBell />
          {/* narrow screens: hamburger */}
          <button
            className="hamburger"
            aria-label="Menu"
            aria-expanded={open}
            onClick={() => setOpen((o) => !o)}
          >
            {open ? (
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            ) : (
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M3 6h18M3 12h18M3 18h18" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* narrow screens: dropdown drawer — groups flatten into labelled sections */}
      {open && (
        <div className="nav-drawer">
          {NAV.map((e) =>
            isGroup(e) ? (
              <div key={e.label} className="drawer-group">
                <div className="drawer-label">{e.label}</div>
                {e.items.map((i) => (
                  <Link
                    key={i.href}
                    href={i.href}
                    className={isActive(i.href) ? "active" : ""}
                    onClick={() => setOpen(false)}
                  >
                    {i.label}
                  </Link>
                ))}
              </div>
            ) : (
              <Link
                key={e.href}
                href={e.href}
                className={isActive(e.href) ? "active" : ""}
                onClick={() => setOpen(false)}
              >
                {e.label}
              </Link>
            )
          )}
        </div>
      )}
    </nav>
  );
}
