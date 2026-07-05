"use client";
import { useEffect } from "react";

// The service worker was retired (it caused stale cached data). This actively
// unregisters any previously-installed SW and clears its caches so no browser
// keeps serving old snapshots. Registers nothing new.
export function PwaRegister() {
  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker
        .getRegistrations()
        .then((regs) => regs.forEach((r) => r.unregister()))
        .catch(() => {});
    }
    if (typeof caches !== "undefined") {
      caches.keys().then((keys) => keys.forEach((k) => caches.delete(k))).catch(() => {});
    }
  }, []);
  return null;
}
