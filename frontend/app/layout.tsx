import "./globals.css";
import type { Metadata, Viewport } from "next";
import { Anton, DM_Sans, IBM_Plex_Mono } from "next/font/google";
import { AdvisorDock } from "../components/AdvisorDock";
import { Nav } from "../components/Nav";
import { BlueprintBackground } from "../components/blueprint/BlueprintBackground";
import { PwaRegister } from "../components/PwaRegister";
import { TickerTape } from "../components/TickerTape";
import { THEME_BOOT_SCRIPT } from "../lib/theme";

// All self-hosted at build time — no external font requests at runtime, so the
// PWA and tunnel keep working offline.
// DM Sans   = body prose
// Anton     = heavy condensed display heads (the poster type)
// Plex Mono = every spec label, data readout and telemetry strip
const dmSans = DM_Sans({ subsets: ["latin"], variable: "--font-dm" });
const anton = Anton({ subsets: ["latin"], weight: "400", variable: "--font-display" });
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
  themeColor: "#F2EEE4",
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
      className={`${dmSans.variable} ${anton.variable} ${plexMono.variable}`}
      suppressHydrationWarning
    >
      <head>
        {/* Resolves the theme before first paint — see lib/theme.ts. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />
      </head>
      <body>
        <BlueprintBackground />
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
