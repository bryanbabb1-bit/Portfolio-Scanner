// The permanent backend URL — the named Cloudflare tunnel on Bryan's domain
// pointing at the PC backend (frontend proxies /api/* to FastAPI). Set up in
// Phase 3; until then this host won't resolve.
export const BACKEND_URL = "https://watchdog.trueforecasting.app";
