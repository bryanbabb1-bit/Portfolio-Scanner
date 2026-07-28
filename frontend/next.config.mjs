/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Advisor calls (especially deep research) can run 1-5 minutes; the default
  // rewrite-proxy timeout kills them mid-flight and surfaces as a 500.
  experimental: { proxyTimeout: 600_000 },
  // Same-origin API proxy: the browser (and phone, via the tunnel) only ever
  // talks to this Next server; /api/* is forwarded to FastAPI server-side.
  // One tunnel to :3000 therefore exposes the whole app, and CORS never applies.
  async rewrites() {
    const backend = process.env.BACKEND_ORIGIN || "http://localhost:8000";
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
  // Retired surfaces. Strategy, Transition and Clean Sheet were removed when
  // the app collapsed to one voice, but the phone app remembers its last
  // route and browsers keep history and bookmarks — landing on a hard 404 is
  // a dead end. Send them home instead. Temporary (307) so these paths stay
  // reusable and nothing caches the redirect permanently.
  async redirects() {
    return ["/strategy", "/transition", "/cleansheet"].map((source) => ({
      source,
      destination: "/",
      permanent: false,
    }));
  },
};

export default nextConfig;
