"""Market data adapter.

Primary source is Yahoo Finance via yfinance. When Yahoo is unreachable
(offline dev, blocked egress) or DATA_MODE=mock, the adapter transparently
serves deterministic mock data so the whole app keeps working. A small in-
process TTL cache avoids hammering the source during a scan.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import pandas as pd

from ..config import settings
from . import mock_data

# ------------------------------------------------------------------ cache
_cache: dict[str, tuple[float, object]] = {}


def _cache_get(key: str):
    hit = _cache.get(key)
    if hit and (time.time() - hit[0]) < settings.CACHE_TTL:
        return hit[1]
    return None


def _cache_put(key: str, value):
    _cache[key] = (time.time(), value)
    return value


@dataclass
class MarketData:
    symbol: str
    name: str
    history: pd.DataFrame  # daily OHLCV
    analyst: dict
    news: list[dict]
    source: str  # "live" | "mock"


# --------------------------------------------------------------- yfinance
def _fetch_live(symbol: str) -> MarketData:
    import yfinance as yf  # imported lazily so mock mode has no hard dep

    tkr = yf.Ticker(symbol)
    hist = tkr.history(period="1y", auto_adjust=True)
    if hist is None or hist.empty:
        raise RuntimeError(f"no history for {symbol}")

    info = {}
    try:
        info = tkr.get_info() or {}
    except Exception:
        info = {}

    name = info.get("shortName") or info.get("longName") or symbol.upper()

    price = float(hist["Close"].iloc[-1])
    analyst = {
        "recommendation": info.get("recommendationKey"),
        "mean_target": info.get("targetMeanPrice"),
        "high_target": info.get("targetHighPrice"),
        "low_target": info.get("targetLowPrice"),
        "num_analysts": info.get("numberOfAnalystOpinions"),
    }
    if not analyst.get("mean_target"):
        # Fall back to a synthesized consensus so the UI always has something.
        analyst = mock_data.analyst(symbol, price)

    news_items = []
    try:
        for n in (tkr.news or [])[:6]:
            content = n.get("content", n)
            news_items.append({
                "title": content.get("title") or n.get("title"),
                "publisher": (content.get("provider", {}) or {}).get("displayName")
                             or n.get("publisher"),
                "link": (content.get("canonicalUrl", {}) or {}).get("url")
                        or n.get("link"),
                "published": content.get("pubDate") or n.get("providerPublishTime"),
            })
    except Exception:
        pass
    news_items = [n for n in news_items if n.get("title")]
    if not news_items:
        news_items = mock_data.news(symbol)

    return MarketData(symbol.upper(), name, hist, analyst, news_items, "live")


def _fetch_mock(symbol: str) -> MarketData:
    hist = mock_data.history(symbol)
    price = float(hist["Close"].iloc[-1])
    return MarketData(
        symbol.upper(),
        mock_data.company_name(symbol),
        hist,
        mock_data.analyst(symbol, price),
        mock_data.news(symbol),
        "mock",
    )


def get_market_data(symbol: str) -> MarketData:
    key = f"md:{symbol.upper()}"
    cached = _cache_get(key)
    if cached is not None:
        return cached

    mode = settings.DATA_MODE
    if mode == "mock":
        return _cache_put(key, _fetch_mock(symbol))

    try:
        return _cache_put(key, _fetch_live(symbol))
    except Exception as exc:  # network blocked, delisted, etc.
        if mode == "live":
            raise
        # auto mode: degrade gracefully
        data = _fetch_mock(symbol)
        print(f"[market_data] live fetch failed for {symbol} ({exc!r}); using mock")
        return _cache_put(key, data)
