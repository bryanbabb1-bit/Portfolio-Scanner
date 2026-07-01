# Portfolio Scanner 📈

A personal **stock portfolio intelligence hub**. It scans your holdings and
watchlist for price action, technical signals, analyst ratings & price targets,
and news — then layers on an AI **"senior Schwab financial advisor"** for
technical analysis and a **live breakout radar** that makes the case for names
poised to break out.

Built around the themes you care about: **AI, tech, AI/tech infrastructure,
energy, and compute power.**

---

## What it does

| Feature | Description |
|---|---|
| 📊 **Dashboard** | Portfolio value, day change, unrealized P/L, allocation by theme, and a report card per holding. |
| 🔎 **Scan Hub** | Holdings **+ watchlist** scanned for signals, ratings, targets and news — sorted by bullish tilt, filterable by theme. |
| 🎯 **AI Senior Advisor** | On-demand, per-stock narrative from a "senior Charles Schwab advisor" persona: plain-English take, technical read, recommendation, and risks/invalidation level. |
| 🚀 **Breakout Radar** | Every name scored 0–100 for breakout readiness (momentum · proximity to 52w high · volume expansion · trend · volatility squeeze), each with an AI bull case incl. entry zone, confirmation level and stop. |
| 🧠 **Technical engine** | RSI, MACD, SMA/EMA (20/50/200), Bollinger Bands, ATR, 52-week range, volume ratio, trend classification. |

The AI layer runs through your **local Claude subscription** (the `claude` CLI
in headless mode) — **no API key required**.

---

## Architecture

```
┌─────────────────────────┐        HTTP/JSON        ┌──────────────────────────────┐
│  Next.js frontend        │  ───────────────────▶  │  FastAPI backend             │
│  (dashboard, radar, TA)  │                        │                              │
└─────────────────────────┘                        │  services/                   │
                                                    │   ├─ market_data  (yfinance) │
                                                    │   │     └─ mock fallback     │
                                                    │   ├─ technical    (RSI/MACD…)│
                                                    │   ├─ screener     (breakouts)│
                                                    │   ├─ portfolio    (P/L, agg.)│
                                                    │   └─ advisor  ──▶ `claude -p`│  headless
                                                    └──────────────────────────────┘   (subscription)
```

- **Backend** — Python / FastAPI. Market data from **yfinance** (free, no key),
  with a **deterministic mock fallback** so the app runs fully offline or in
  sandboxes where Yahoo is blocked.
- **Frontend** — Next.js (App Router) + TypeScript, dark finance UI, zero-config.
- **AI** — the backend shells out to `claude -p --output-format json`, using
  your signed-in subscription.

---

## Quick start — Docker (recommended)

The easiest path: **no Python or Node install needed**, just Docker.

Prereq: [Docker Desktop](https://www.docker.com/products/docker-desktop/)
(Mac/Windows) or Docker Engine (Linux).

```bash
git clone https://github.com/bryanbabb1-bit/portfolio-scanner.git
cd portfolio-scanner
git checkout claude/stock-portfolio-hub-m3mj1g
docker compose up --build
```

First run builds the images (a few minutes); after that it's seconds. Then open:

- **http://localhost:3000** — the app
- http://localhost:8000/docs — the API

Stop with `Ctrl+C`, or `docker compose down`. To rebuild after editing code,
`docker compose up --build` again.

### Enabling the AI advisor in Docker

The core app (dashboard, scan, breakout radar, technicals) works out of the box.
The **AI advisor** needs Claude credentials inside the container — pick one:

| You have | Do this |
|---|---|
| Claude Code CLI logged in on **Linux/WSL** | Nothing — compose mounts your `~/.claude` login automatically. |
| Claude Code on **macOS/Windows** (login is in the OS keychain, not a file) | Run `claude setup-token`, then `export CLAUDE_CODE_OAUTH_TOKEN=<token>` before `docker compose up`. |
| An **Anthropic API key** | `export ANTHROPIC_API_KEY=sk-ant-...` before `docker compose up`. |
| Nothing | Advisor returns a deterministic rule-based note instead (labeled "auto"). |

> On Mac/Windows the subscription login is stored in the OS keychain, which a
> Linux container can't read — that's why those platforms use the token/key path.

---

## Quick start — without Docker

Prereqs: **Python 3.11+**, **Node 18+**, and the **`claude` CLI** signed in
(for the AI advisor — optional).

```bash
./run.sh
```

That boots the backend on **http://localhost:8000** (API docs at `/docs`) and the
frontend on **http://localhost:3000**.

### Or run each side manually

**Backend**
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # optional
uvicorn app.main:app --reload --port 8000
```

**Frontend**
```bash
cd frontend
npm install
cp .env.local.example .env.local   # optional (defaults to localhost:8000)
npm run dev
```

---

## Configuring your portfolio

Edit **`backend/app/data/portfolio.json`** — set your `holdings` (symbol, shares,
cost basis, theme) and `watchlist`. Everything (dashboard P/L, scan, breakout
radar, advisor) flows from this file. No rebuild needed; just refresh.

---

## Data modes

Set `DATA_MODE` in `backend/.env`:

- `auto` *(default)* — try live yfinance, fall back to mock on any failure.
- `live` — force live data (errors surface).
- `mock` — deterministic demo data; works with **no network**.

> ℹ️ yfinance uses public Yahoo Finance endpoints. On your own machine this
> "just works." In locked-down/CI environments where Yahoo egress is blocked,
> the app automatically serves realistic mock data so nothing breaks.

---

## API surface

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Service status, data mode, advisor flag |
| `GET /api/portfolio` | Summary + per-holding report cards |
| `GET /api/scan?include_watchlist=true` | Full scan feed (holdings + watchlist) |
| `GET /api/breakouts?min_score=0&limit=20` | Ranked breakout candidates |
| `GET /api/stock/{symbol}` | Deep report for any symbol |
| `GET /api/advisor/stock/{symbol}` | AI advisor note for a stock |
| `GET /api/advisor/breakout/{symbol}` | AI bull case for a breakout candidate |
| `GET /api/config` | Raw portfolio config |

Interactive docs: **http://localhost:8000/docs**

---

## Roadmap / ideas

- Scheduled background scans + push/email digest of the day's top signals.
- Persist advisor notes and price history to a database for trend tracking.
- Sector/theme heat map and correlation view.
- Alerting when a watchlist name crosses its breakout confirmation level.
- Options flow / IV overlay for breakout timing.

---

## Disclaimer

This tool is for **research and educational purposes only**. It is **not
personalized investment advice**. The "advisor" persona is an AI generating
commentary from technical data. Do your own due diligence.
