"""Market data adapter.

Primary source is Yahoo Finance via yfinance. When Yahoo is unreachable
(offline dev, blocked egress) or DATA_MODE=mock, the adapter transparently
serves deterministic mock data so the whole app keeps working. A small in-
process TTL cache avoids hammering the source during a scan.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import pandas as pd

from ..config import settings
from . import mock_data

# ------------------------------------------------------------------ cache
_cache: dict[str, tuple[float, object]] = {}
_cache_lock = threading.Lock()


def _market_hours() -> bool:
    """US equities extended window (pre-market through after-hours), ET.
    Duplicated tiny check to avoid a circular import with conviction."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    et = datetime.now(ZoneInfo("America/New_York"))
    if et.weekday() >= 5:
        return False
    mins = et.hour * 60 + et.minute
    return 7 * 60 <= mins < 20 * 60


def _cache_get(key: str):
    with _cache_lock:
        hit = _cache.get(key)
    # During market hours prices move — keep the cache tight (60s) so the
    # advisor never reasons off a 5-minute-old tick. Off-hours, prices are
    # static, so the full TTL avoids hammering the source.
    ttl = min(settings.CACHE_TTL, 60) if _market_hours() else settings.CACHE_TTL
    if hit and (time.time() - hit[0]) < ttl:
        return hit[1]
    return None


def _cache_put(key: str, value):
    with _cache_lock:
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
    earnings_date: str | None = None  # next report date (YYYY-MM-DD), if known
    structure: dict | None = None     # float, market cap, short % — runner DNA
    live_price: float | None = None   # current tick (fast_info) — beats daily close
    prev_close: float | None = None   # prior session close, for today's % change
    as_of: str | None = None          # when this data was pulled (ISO ET)


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

    # LIVE price — the daily-history close lags intraday and ignores extended
    # hours entirely. fast_info.last_price is the current tick; fall back to
    # info's regular-market fields, then to the daily close. This is what the
    # advisor and every quote should reason from.
    live_price = prev_close = None
    try:
        fi = tkr.fast_info
        live_price = float(getattr(fi, "last_price", None) or fi["lastPrice"])
    except Exception:
        pass
    try:
        fi = tkr.fast_info
        prev_close = float(getattr(fi, "previous_close", None) or fi["previousClose"])
    except Exception:
        pass
    if live_price is None:
        v = info.get("regularMarketPrice") or info.get("currentPrice")
        live_price = float(v) if isinstance(v, (int, float)) and v > 0 else None
    if prev_close is None:
        v = info.get("regularMarketPreviousClose") or info.get("previousClose")
        prev_close = float(v) if isinstance(v, (int, float)) and v > 0 else None

    # Structural DNA of a runner: a tiny float is the fuel — MGRT ran 1000%+
    # on a 2M-share float. shares_out lets us derive float % (tight = recent
    # IPO / insider-heavy), and history length proxies IPO recency.
    def _numf(*keys):
        for k in keys:
            v = info.get(k)
            if isinstance(v, (int, float)) and v > 0:
                return float(v)
        return None

    float_shares = _numf("floatShares")
    shares_out = _numf("sharesOutstanding", "impliedSharesOutstanding")
    structure = {
        "float_shares": float_shares,
        "shares_outstanding": shares_out,
        "market_cap": _numf("marketCap"),
        "short_pct_float": _numf("shortPercentOfFloat"),
        "float_pct": round(float_shares / shares_out * 100, 1)
        if float_shares and shares_out else None,
        "history_days": int(len(hist)),  # < ~250 => less than a year public
    }

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
            published = content.get("pubDate") or n.get("providerPublishTime")
            # Older yfinance schema gives a raw Unix epoch — normalize to ISO
            # so sorting and "time ago" rendering work downstream.
            if isinstance(published, (int, float)):
                published = time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime(published))
            news_items.append({
                "title": content.get("title") or n.get("title"),
                "publisher": (content.get("provider", {}) or {}).get("displayName")
                             or n.get("publisher"),
                "link": (content.get("canonicalUrl", {}) or {}).get("url")
                        or n.get("link"),
                "published": published,
            })
    except Exception:
        pass
    news_items = [n for n in news_items if n.get("title")]
    if not news_items:
        news_items = mock_data.news(symbol)

    # Next earnings date — binary-event risk the advisor must respect.
    earnings_date = None
    try:
        cal = tkr.calendar or {}
        ed = cal.get("Earnings Date")
        if isinstance(ed, (list, tuple)) and ed:
            ed = ed[0]
        if ed is not None:
            earnings_date = str(pd.Timestamp(ed).date())
    except Exception:
        pass

    return MarketData(symbol.upper(), name, hist, analyst, news_items, "live",
                      earnings_date=earnings_date, structure=structure,
                      live_price=round(live_price, 2) if live_price else None,
                      prev_close=round(prev_close, 4) if prev_close else None,
                      as_of=time.strftime("%Y-%m-%dT%H:%M:%S"))


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
        structure=mock_data.structure(symbol),
    )


def _fetch_live_prices(symbol: str) -> MarketData:
    """History-only live fetch — skips get_info/news, which dominate latency.

    Used by the Discovery scanner where ~70 outside tickers only need OHLCV
    for indicator/score math."""
    import yfinance as yf

    hist = yf.Ticker(symbol).history(period="1y", auto_adjust=True)
    if hist is None or hist.empty:
        raise RuntimeError(f"no history for {symbol}")
    return MarketData(symbol.upper(), symbol.upper(), hist, {}, [], "live")


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


def get_price_data(symbol: str) -> MarketData:
    """Like get_market_data but price-history only (no analyst/news)."""
    full = _cache_get(f"md:{symbol.upper()}")
    if full is not None:  # a richer report is already cached — reuse it
        return full
    key = f"px:{symbol.upper()}"
    cached = _cache_get(key)
    if cached is not None:
        return cached

    mode = settings.DATA_MODE
    if mode == "mock":
        return _cache_put(key, _fetch_mock(symbol))
    try:
        return _cache_put(key, _fetch_live_prices(symbol))
    except Exception as exc:
        if mode == "live":
            raise
        data = _fetch_mock(symbol)
        print(f"[market_data] live price fetch failed for {symbol} ({exc!r}); using mock")
        return _cache_put(key, data)


# ---------------------------------------------------------------- intraday
_INTRADAY_SPEC = {"1d": ("1d", "5m"), "5d": ("5d", "30m")}


def get_intraday(symbol: str, range_: str = "1d") -> tuple[pd.DataFrame, str]:
    """Intraday OHLCV bars: 5-min for 1d, 30-min for 5d. Returns (df, source)."""
    period, interval = _INTRADAY_SPEC.get(range_, _INTRADAY_SPEC["1d"])
    key = f"intra:{symbol.upper()}:{range_}"
    cached = _cache_get(key)
    if cached is not None:
        return cached

    mode = settings.DATA_MODE
    if mode == "mock":
        return _cache_put(key, (mock_data.intraday(symbol, range_), "mock"))
    try:
        import yfinance as yf

        hist = yf.Ticker(symbol).history(period=period, interval=interval,
                                         auto_adjust=True)
        if hist is None or hist.empty:
            raise RuntimeError(f"no intraday for {symbol}")
        return _cache_put(key, (hist, "live"))
    except Exception as exc:
        if mode == "live":
            raise
        print(f"[market_data] intraday failed for {symbol} ({exc!r}); using mock")
        return _cache_put(key, (mock_data.intraday(symbol, range_), "mock"))


def warm_intraday(symbols: list[str], range_: str, max_workers: int = 8) -> None:
    todo = [s for s in dict.fromkeys(sym.upper() for sym in symbols)
            if _cache_get(f"intra:{s}:{range_}") is None]
    if len(todo) <= 1:
        return

    def _one(sym: str) -> None:
        try:
            get_intraday(sym, range_)
        except Exception:
            pass

    with ThreadPoolExecutor(max_workers=min(max_workers, len(todo))) as pool:
        list(pool.map(_one, todo))


def warm_cache(symbols: list[str], max_workers: int = 8, light: bool = False) -> None:
    """Prefetch market data for many symbols concurrently.

    Scans previously fetched 19+ tickers one at a time; warming the cache in
    parallel makes a full-universe scan bound by the slowest single fetch
    instead of the sum of all of them. Failures are swallowed here — callers
    hit them (or the mock fallback) again through get_market_data().
    light=True prefetches price history only (Discovery's ~70-ticker sweep).
    """
    fetch = get_price_data if light else get_market_data

    def _is_cached(s: str) -> bool:
        if _cache_get(f"md:{s}") is not None:
            return True
        return light and _cache_get(f"px:{s}") is not None

    todo = [s for s in dict.fromkeys(sym.upper() for sym in symbols)
            if not _is_cached(s)]
    if len(todo) <= 1:
        return

    def _one(sym: str) -> None:
        try:
            fetch(sym)
        except Exception:
            pass

    with ThreadPoolExecutor(max_workers=min(max_workers, len(todo))) as pool:
        list(pool.map(_one, todo))
