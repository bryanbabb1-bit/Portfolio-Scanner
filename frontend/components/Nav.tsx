"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { NotificationBell } from "./NotificationBell";

const LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/strategy", label: "Strategy" },
  { href: "/scan", label: "Scan Hub" },
  { href: "/breakouts", label: "Breakout Radar" },
  { href: "/discover", label: "Discovery" },
  { href: "/runners", label: "Runner Radar" },
  { href: "/news", label: "News Wire" },
  { href: "/settings", label: "Settings" },
];

export function Nav() {
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const isActive = (href: string) =>
    href === "/" ? path === "/" : path.startsWith(href);

  // Close the drawer whenever the route changes.
  useEffect(() => setOpen(false), [path]);

  return (
    <nav className="nav">
      <div className="container nav-inner">
        <Link href="/" className="brand">
          Portfolio<span>Scanner</span>
        </Link>

        {/* wide screens: inline tabs */}
        <div className="nav-links wide">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href} className={isActive(l.href) ? "active" : ""}>
              {l.label}
            </Link>
          ))}
        </div>

        <div className="nav-right">
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

      {/* narrow screens: dropdown drawer */}
      {open && (
        <div className="nav-drawer">
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={isActive(l.href) ? "active" : ""}
              onClick={() => setOpen(false)}
            >
              {l.label}
            </Link>
          ))}
        </div>
      )}
    </nav>
  );
}
