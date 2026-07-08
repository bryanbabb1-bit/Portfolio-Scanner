import "./globals.css";
import type { Metadata, Viewport } from "next";
import { DM_Sans } from "next/font/google";
import { Nav } from "../components/Nav";
import { PwaRegister } from "../components/PwaRegister";
import { TickerTape } from "../components/TickerTape";

// Self-hosted at build time — no external font requests at runtime, so the
// PWA and tunnel keep working offline.
const dmSans = DM_Sans({ subsets: ["latin"], variable: "--font-dm" });

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
    statusBarStyle: "black-translucent",
    title: "Scanner",
  },
};

export const viewport: Viewport = {
  themeColor: "#090b11",
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
    <html lang="en" className={dmSans.variable}>
      <body>
        <PwaRegister />
        <Nav />
        <TickerTape />
        <main className="container page">{children}</main>
      </body>
    </html>
  );
}
