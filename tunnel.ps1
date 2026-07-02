# Expose Portfolio Scanner to your phone via a Cloudflare quick tunnel.
#
# Prereqs: backend on :8000 and frontend on :3000 (run.ps1). The frontend
# proxies /api/* to the backend, so this single tunnel serves the whole app —
# including the Claude advisor, since everything still executes on this PC.
#
# Prints a https://<random>.trycloudflare.com URL. Open it on your phone and
# use Share > "Add to Home Screen" to install the PWA. The random URL changes
# each time the tunnel restarts; upgrade to a named tunnel (requires a domain
# on Cloudflare) for a permanent address.
$cloudflared = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
& $cloudflared tunnel --url http://localhost:3000
