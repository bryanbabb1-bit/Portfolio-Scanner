"""Deterministic mock market data.

Generates a repeatable ~1 year OHLCV series per symbol so the entire pipeline
(technical indicators, screener, advisor) works offline or in sandboxes where
Yahoo Finance is blocked. Deterministic => identical output across runs, which
keeps the UI stable and makes the app demoable without network access.
"""
from __future__ import annotations

import hashlib
import math

import numpy as np
import pandas as pd

# Rough anchor prices / profiles so mock output resembles reality per name.
_PROFILE = {
    "NVDA": (135, 0.35), "MSFT": (455, 0.22), "GOOGL": (185, 0.25),
    "AMD": (165, 0.40), "AVGO": (175, 0.33), "VRT": (110, 0.45),
    "CEG": (300, 0.38), "SMCI": (45, 0.60), "PLTR": (40, 0.55),
    "TSM": (190, 0.30), "MU": (105, 0.42), "ARM": (140, 0.50),
    "ANET": (400, 0.35), "VST": (185, 0.48), "NEE": (75, 0.20),
    "ETN": (330, 0.28), "DLR": (175, 0.25), "TSLA": (250, 0.50),
    "AMZN": (185, 0.28), "META": (600, 0.30),
}

_NAMES = {
    "NVDA": "NVIDIA Corporation", "MSFT": "Microsoft Corporation",
    "GOOGL": "Alphabet Inc.", "AMD": "Advanced Micro Devices",
    "AVGO": "Broadcom Inc.", "VRT": "Vertiv Holdings",
    "CEG": "Constellation Energy", "SMCI": "Super Micro Computer",
    "PLTR": "Palantir Technologies", "TSM": "Taiwan Semiconductor",
    "MU": "Micron Technology", "ARM": "Arm Holdings",
    "ANET": "Arista Networks", "VST": "Vistra Corp.",
    "NEE": "NextEra Energy", "ETN": "Eaton Corporation",
    "DLR": "Digital Realty Trust", "TSLA": "Tesla, Inc.",
    "AMZN": "Amazon.com, Inc.", "META": "Meta Platforms, Inc.",
}


def _seed(symbol: str) -> int:
    return int(hashlib.md5(symbol.encode()).hexdigest()[:8], 16)


def company_name(symbol: str) -> str:
    return _NAMES.get(symbol.upper(), f"{symbol.upper()} Corp.")


def history(symbol: str, days: int = 260) -> pd.DataFrame:
    """Return a deterministic daily OHLCV DataFrame indexed by date."""
    sym = symbol.upper()
    anchor, vol = _PROFILE.get(sym, (100.0, 0.35))
    rng = np.random.default_rng(_seed(sym))

    daily_sigma = vol / math.sqrt(252)
    # Slight upward drift + a gentle sine cycle so trends/consolidations appear.
    drift = 0.0004
    steps = rng.normal(drift, daily_sigma, days)
    cycle = 0.0025 * np.sin(np.linspace(0, 6 * math.pi, days))
    log_path = np.cumsum(steps + cycle)

    # End the series near the anchor price.
    close = anchor * np.exp(log_path - log_path[-1])
    close = np.maximum(close, 0.5)

    intraday = np.abs(rng.normal(0, daily_sigma, days))
    high = close * (1 + intraday)
    low = close * (1 - intraday)
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum.reduce([high, open_, close])
    low = np.minimum.reduce([low, open_, close])

    base_vol = 5_000_000 + (_seed(sym) % 40) * 1_000_000
    volume = (base_vol * (1 + 0.6 * np.abs(rng.normal(0, 1, days)))).astype(np.int64)
    # Occasional volume spikes to make the screener interesting.
    spikes = rng.integers(0, days, size=max(3, days // 60))
    volume[spikes] = (volume[spikes] * rng.uniform(2.0, 3.5, len(spikes))).astype(np.int64)

    idx = pd.date_range(end=pd.Timestamp("2025-12-31"), periods=days, freq="B")
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=idx,
    )


def intraday(symbol: str, range_: str = "1d") -> pd.DataFrame:
    """Deterministic intraday OHLCV: 5-min bars for 1d, 30-min bars for 5d."""
    sym = symbol.upper()
    daily = history(sym)
    last_close = float(daily["Close"].iloc[-1])
    rng = np.random.default_rng(_seed(sym) ^ (0x1D if range_ == "1d" else 0x5D))

    if range_ == "1d":
        days, per_day, freq, sigma = 1, 78, "5min", 0.0011
    else:
        days, per_day, freq, sigma = 5, 13, "30min", 0.0032

    stamps: list[pd.Timestamp] = []
    for day in pd.DatetimeIndex(daily.index[-days:]):
        stamps.extend(pd.date_range(
            day.normalize() + pd.Timedelta(hours=9, minutes=30),
            periods=per_day, freq=freq))
    idx = pd.DatetimeIndex(stamps)

    steps = rng.normal(0, sigma, len(idx))
    log_path = np.cumsum(steps)
    close = last_close * np.exp(log_path - log_path[-1])  # end at last close

    intrabar = np.abs(rng.normal(0, sigma, len(idx)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum.reduce([close * (1 + intrabar), open_, close])
    low = np.minimum.reduce([close * (1 - intrabar), open_, close])
    base_vol = 800_000 + (_seed(sym) % 30) * 40_000
    volume = (base_vol * (1 + 0.8 * np.abs(rng.normal(0, 1, len(idx))))).astype(np.int64)

    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=idx,
    )


def structure(symbol: str) -> dict:
    """Deterministic structural DNA (float, market cap, short %) for mock mode.

    A few seeded symbols mimic a low-float runner so the Runner Radar has
    something to show offline; the rest look like normal mid/large caps.
    """
    sym = symbol.upper()
    rng = np.random.default_rng(_seed(sym) ^ 0xF10A7)
    runners = {"MGRT", "SNDK", "AAOI", "SOUN", "RGTI", "QBTS"}
    if sym in runners:
        shares = float(rng.integers(8_000_000, 40_000_000))
        float_pct = float(rng.uniform(12, 35))
        short = float(rng.uniform(0.03, 0.22))
    else:
        shares = float(rng.integers(200_000_000, 4_000_000_000))
        float_pct = float(rng.uniform(78, 98))
        short = float(rng.uniform(0.005, 0.06))
    float_shares = shares * float_pct / 100
    anchor = _PROFILE.get(sym, (100.0, 0.35))[0]
    return {
        "float_shares": round(float_shares),
        "shares_outstanding": round(shares),
        "market_cap": round(shares * anchor),
        "short_pct_float": round(short, 4),
        "float_pct": round(float_pct, 1),
        "history_days": int(140 if sym in runners else 252),
    }


def analyst(symbol: str, price: float) -> dict:
    """Deterministic analyst consensus consistent with the mock price."""
    rng = np.random.default_rng(_seed(symbol.upper()) ^ 0xABCD)
    upside = rng.uniform(0.05, 0.30)
    mean_target = round(price * (1 + upside), 2)
    recs = ["strong_buy", "buy", "buy", "hold", "outperform"]
    return {
        "recommendation": recs[_seed(symbol.upper()) % len(recs)],
        "mean_target": mean_target,
        "high_target": round(mean_target * rng.uniform(1.08, 1.20), 2),
        "low_target": round(price * rng.uniform(0.85, 0.98), 2),
        "num_analysts": int(rng.integers(18, 52)),
    }


def news(symbol: str) -> list[dict]:
    sym = symbol.upper()
    name = company_name(sym)
    templates = [
        (f"{name} extends AI infrastructure roadmap", "MarketPulse"),
        (f"Analysts weigh in on {sym} after sector rotation", "Street Signal"),
        (f"{name} data-center demand cited as key catalyst", "Compute Daily"),
        (f"{sym} technicals flash momentum as volume builds", "TA Wire"),
        (f"Power and cooling suppliers ride {name} tailwind", "Grid Report"),
    ]
    out = []
    for i, (title, pub) in enumerate(templates):
        out.append({
            "title": title,
            "publisher": pub,
            "link": f"https://example.com/news/{sym.lower()}/{i}",
            "published": f"2025-12-{20 + i:02d}T14:30:00Z",
        })
    return out
