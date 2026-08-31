import "./globals.css";
import type { Metadata, Viewport } from "next";
import { Cormorant_Garamond, IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import { AdvisorDock } from "../components/AdvisorDock";
import { Nav } from "../components/Nav";
import { DeskBackground } from "../components/blueprint/BlueprintBackground";
import { PwaRegister } from "../components/PwaRegister";
import { TickerTape } from "../components/TickerTape";
import { THEME_BOOT_SCRIPT } from "../lib/theme";

// All self-hosted at build time — no external font requests at runtime, so the
// PWA and tunnel keep working offline.
//
// Cormorant = the display face, and it is doing one job: giving the two or
//   three numbers that matter (the balance, sleeve equity, a result in R) the
//   presence a printed research note gives them. It replaced Anton, whose
//   condensed uppercase read as a poster — the right answer to the hedge-fund
//   brief in July and the wrong room for a private desk.
// Plex Sans = everything you actually read.
// Plex Mono = every label, column and readout. Tabular figures throughout, so
//   digits line up down a column and a changing price does not shuffle.
const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-dm",
});
const cormorant = Cormorant_Garamond({
  subsets: ["latin"],
  weight: ["500", "600"],
  style: ["normal", "italic"],
  variable: "--font-display",
});
const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "Portfolio Scanner",
  description:
    "Scan your portfolio for news, trends, ratings and technicals with an AI senior advisor and a live breakout radar.",
  manifest: "/manifest.webmanifest",
  icons: {
    icon: "/icon-192.png",
    apple: "/apple-touch-icon.png",
  },
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "Scanner",
  },
};

export const viewport: Viewport = {
  themeColor: "#EEEDE8",
  width: "device-width",
  initialScale: 1,
  // Lock zoom so the app can't pinch/double-tap-zoom like a webpage — it
  // should feel like a fixed native surface, not a scrollable document.
  maximumScale: 1,
  userScalable: false,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${plexSans.variable} ${cormorant.variable} ${plexMono.variable}`}
      suppressHydrationWarning
    >
      <head>
        {/* Resolves the theme before first paint — see lib/theme.ts. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />
      </head>
      <body>
        <DeskBackground />
        <PwaRegister />
        <Nav />
        <TickerTape />
        <main className="container page">{children}</main>
        {/* Always-open line to the advisor — every page, no brief required. */}
        <AdvisorDock />
      </body>
    </html>
  );
}
