# Portfolio Scanner — Backend (FastAPI)

Python API powering the hub: portfolio scanning, technical analysis, breakout
screening, and the headless-Claude advisor.

## Run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Docs: http://localhost:8000/docs

## Layout

```
app/
  main.py              FastAPI app + CORS + routers
  config.py            env-driven settings
  data/portfolio.json  YOUR holdings + watchlist + themes
  models/schemas.py    pydantic response models
  services/
    market_data.py     yfinance adapter + TTL cache + mock fallback
    mock_data.py        deterministic OHLCV/analyst/news generator
    technical.py       RSI/MACD/SMA/EMA/Bollinger/ATR + signals
    screener.py        breakout scoring (0-100) + thesis
    portfolio.py       report assembly + portfolio aggregation
    advisor.py         `claude -p` headless wrapper + fallback
  routers/             portfolio / scan / breakouts / advisor
```

## Configuration

See `.env.example`. Key flags: `DATA_MODE` (auto|live|mock),
`ADVISOR_ENABLED`, `CLAUDE_MODEL`, `CACHE_TTL`.

## Notes

- **No API key** for AI: the advisor invokes your local `claude` CLI. If the CLI
  is missing/times out, a deterministic fallback note is returned so endpoints
  never hard-fail.
- **No key** for market data: yfinance uses public Yahoo endpoints; mock data
  fills in when live is unreachable.
