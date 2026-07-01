import "./globals.css";
import type { Metadata } from "next";
import { Nav } from "../components/Nav";

export const metadata: Metadata = {
  title: "Portfolio Scanner",
  description:
    "Scan your portfolio for news, trends, ratings and technicals with an AI senior advisor and a live breakout radar.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <Nav />
        <main className="container page">{children}</main>
      </body>
    </html>
  );
}
