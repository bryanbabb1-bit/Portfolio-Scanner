"use client";
import { useEffect, useState } from "react";
import {
  applyTheme,
  marketOpen,
  previewTheme,
  THEME_KEY,
  ThemePref,
  Theme,
} from "../lib/theme";

/* The After Hours control. Cycles auto → day → night → auto.
 *
 * The label states the PREFERENCE and the icon states the RESULT, so on auto
 * you can see both that it is deciding for you and what it decided. */

const NEXT: Record<ThemePref, ThemePref> = {
  auto: "day",
  day: "night",
  night: "auto",
};

const TITLE: Record<ThemePref, string> = {
  auto: "Theme follows the market session — click to pin the paper desk",
  day: "Pinned to the paper desk — click to pin the after-hours terminal",
  night: "Pinned to the after-hours terminal — click to follow the market",
};

export function ThemeSwitch() {
  const [pref, setPref] = useState<ThemePref>("auto");
  const [theme, setTheme] = useState<Theme>("day");
  const [ready, setReady] = useState(false);
  // ?theme= wins until the switch is touched, then the real preference resumes.
  const [preview, setPreview] = useState<Theme | null>(null);

  const settle = (p: ThemePref, pv: Theme | null): Theme =>
    pv ?? (p === "auto" ? (marketOpen() ? "day" : "night") : p);

  // Adopt whatever the boot script already resolved, then own it from here.
  useEffect(() => {
    const stored = localStorage.getItem(THEME_KEY) as ThemePref | null;
    const p: ThemePref =
      stored === "day" || stored === "night" || stored === "auto" ? stored : "auto";
    const pv = previewTheme();
    setPref(p);
    setPreview(pv);
    setTheme(settle(p, pv));
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    const t = settle(pref, preview);
    setTheme(t);
    applyTheme(t);
    localStorage.setItem(THEME_KEY, pref);
  }, [pref, preview, ready]);

  // On auto, the 9:30 and 16:00 boundaries have to actually arrive. Checking
  // once a minute is plenty and costs nothing; applyTheme is idempotent.
  useEffect(() => {
    if (!ready || pref !== "auto" || preview) return;
    const tick = () => {
      const t = marketOpen() ? "day" : "night";
      setTheme(t);
      applyTheme(t);
    };
    const id = setInterval(tick, 60_000);
    return () => clearInterval(id);
  }, [pref, preview, ready]);

  // Render the markup on the server but leave it inert until we know the real
  // preference — otherwise the label flashes the wrong state for a frame.
  return (
    <button
      className={`theme-switch ${theme}`}
      onClick={() => {
        setPreview(null);
        setPref(NEXT[pref]);
      }}
      title={TITLE[pref]}
      aria-label={TITLE[pref]}
      suppressHydrationWarning
    >
      <Glyph theme={theme} auto={pref === "auto"} />
      <span className="ts-label" suppressHydrationWarning>
        {ready ? pref.toUpperCase() : ""}
      </span>
    </button>
  );
}

function Glyph({ theme, auto }: { theme: Theme; auto: boolean }) {
  const common = {
    width: 15,
    height: 15,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.7,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
  return (
    <span className="ts-glyph" aria-hidden>
      {theme === "night" ? (
        // A crescent — the desk after the close.
        <svg {...common}>
          <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z" />
        </svg>
      ) : (
        // A drafting sun: the paper desk, drawn rather than filled.
        <svg {...common}>
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4" />
        </svg>
      )}
      {/* On auto, a dot marks that the session is driving the choice. */}
      {auto && <span className="ts-auto" />}
    </span>
  );
}
