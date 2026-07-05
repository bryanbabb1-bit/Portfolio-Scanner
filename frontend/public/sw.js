// Self-destructing service worker. The PWA cache caused stale API data
// (old alerts/prices served after they were gone on the backend), and the
// native app doesn't use this SW — so it's retired. When a browser checks
// for an sw.js update (that check always hits the network, bypassing any
// cache), it gets THIS: it wipes all caches, unregisters itself, and reloads
// open tabs so nothing stale survives.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => {
  e.waitUntil(
    (async () => {
      try {
        const keys = await caches.keys();
        await Promise.all(keys.map((k) => caches.delete(k)));
        await self.registration.unregister();
        const clients = await self.clients.matchAll({ type: "window" });
        clients.forEach((c) => c.navigate(c.url));
      } catch {}
    })()
  );
});
