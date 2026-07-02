/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Same-origin API proxy: the browser (and phone, via the tunnel) only ever
  // talks to this Next server; /api/* is forwarded to FastAPI server-side.
  // One tunnel to :3000 therefore exposes the whole app, and CORS never applies.
  async rewrites() {
    const backend = process.env.BACKEND_ORIGIN || "http://localhost:8000";
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
