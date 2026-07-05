// Service worker for the installable PWA. API data is NEVER cached — this is
// a real-time trading app, a stale /api response (old alerts, mock prices)
// must never be served. Only static assets and page shells get an offline
// fallback. Bumping CACHE purges every prior cache on activate.
const CACHE = "pscan-v2";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Never touch the cache for API calls — always live from the network.
  if (url.pathname.startsWith("/api/")) {
    e.respondWith(fetch(req));
    return;
  }

  // Static assets + page shells: network-first, cache only as an offline
  // fallback so the app opens without a connection.
  e.respondWith(
    fetch(req)
      .then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
        }
        return res;
      })
      .catch(() => caches.match(req))
  );
});
