"""Technical analysis.

Indicators are computed directly with pandas/numpy (no native TA-Lib build
required). Everything operates on a daily OHLCV DataFrame from market_data.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..models.schemas import Indicators, Quote, Signal


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _macd(close: pd.Series):
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal, macd - signal


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period).mean()


def _f(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    return None if (np.isnan(f) or np.isinf(f)) else round(f, 4)


def compute_indicators(df: pd.DataFrame) -> Indicators:
    close = df["Close"]
    macd, macd_sig, macd_hist = _macd(close)
    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()
    std20 = close.rolling(20).std()
    atr = _atr(df)
    rsi = _rsi(close)
    vol20 = df["Volume"].rolling(20).mean()

    last = -1
    price = float(close.iloc[last])
    high_52w = float(close.tail(252).max())
    low_52w = float(close.tail(252).min())

    s20 = _f(sma20.iloc[last])
    s50 = _f(sma50.iloc[last])
    s200 = _f(sma200.iloc[last])

    trend = "sideways"
    if s50 and s200:
        if price > s50 > s200:
            trend = "uptrend"
        elif price < s50 < s200:
            trend = "downtrend"

    vol_ratio = None
    if _f(vol20.iloc[last]):
        vol_ratio = _f(float(df["Volume"].iloc[last]) / float(vol20.iloc[last]))

    ret_5d = ((price / float(close.iloc[-6]) - 1) * 100) if len(close) > 5 else None
    ret_20d = ((price / float(close.iloc[-21]) - 1) * 100) if len(close) > 20 else None

    return Indicators(
        rsi=_f(rsi.iloc[last]),
        rsi_prev=_f(rsi.iloc[-2]) if len(rsi) > 1 else None,
        rsi_min_10d=_f(rsi.tail(10).min()),
        ret_5d_pct=_f(ret_5d),
        ret_20d_pct=_f(ret_20d),
        macd=_f(macd.iloc[last]),
        macd_signal=_f(macd_sig.iloc[last]),
        macd_hist=_f(macd_hist.iloc[last]),
        sma20=s20, sma50=s50, sma200=s200,
        ema20=_f(close.ewm(span=20, adjust=False).mean().iloc[last]),
        atr=_f(atr.iloc[last]),
        bb_upper=_f((sma20 + 2 * std20).iloc[last]),
        bb_lower=_f((sma20 - 2 * std20).iloc[last]),
        high_52w=_f(high_52w),
        low_52w=_f(low_52w),
        pct_from_52w_high=_f((price / high_52w - 1) * 100) if high_52w else None,
        avg_volume_20=_f(vol20.iloc[last]),
        volume_ratio=vol_ratio,
        trend=trend,
    )


def indicator_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Point-in-time indicators for EVERY bar, as columns.

    `compute_indicators` answers "what do the indicators say today" by taking
    .iloc[-1] off each series. The backtest needs the same answer for all 1,250
    bars, and recomputing the whole stack per bar is ~1,250x the work for
    identical numbers. This keeps the series instead of the last value, so one
    vectorized pass yields the whole history.

    Column names match the `Indicators` field names exactly, so a row can be
    fed straight to the live rule engine — that is what keeps the backtest and
    production on one definition of every rule.

    Strictly causal: every column at bar i uses only bars <= i. `high_52w` is a
    TRAILING 252-bar max (not the whole-sample max), or the backtest would know
    the future.
    """
    close, volume = df["Close"], df["Volume"]
    macd, macd_sig, macd_hist = _macd(close)
    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()
    std20 = close.rolling(20).std()
    rsi = _rsi(close)
    vol20 = volume.rolling(20).mean()

    high_52w = close.rolling(252, min_periods=1).max()
    low_52w = close.rolling(252, min_periods=1).min()

    trend = pd.Series("sideways", index=close.index, dtype=object)
    trend[(close > sma50) & (sma50 > sma200)] = "uptrend"
    trend[(close < sma50) & (sma50 < sma200)] = "downtrend"

    out = pd.DataFrame(
        {
            "price": close,
            "change_pct": close.pct_change() * 100,
            "rsi": rsi,
            "rsi_prev": rsi.shift(1),
            "rsi_min_10d": rsi.rolling(10).min(),
            "ret_5d_pct": (close / close.shift(5) - 1) * 100,
            "ret_20d_pct": (close / close.shift(20) - 1) * 100,
            "macd": macd,
            "macd_signal": macd_sig,
            "macd_hist": macd_hist,
            "sma20": sma20,
            "sma50": sma50,
            "sma200": sma200,
            "ema20": close.ewm(span=20, adjust=False).mean(),
            "atr": _atr(df),
            "bb_upper": sma20 + 2 * std20,
            "bb_lower": sma20 - 2 * std20,
            "high_52w": high_52w,
            "low_52w": low_52w,
            "pct_from_52w_high": (close / high_52w - 1) * 100,
            "avg_volume_20": vol20,
            "volume_ratio": volume / vol20.replace(0, np.nan),
        }
    )
    out["trend"] = trend
    return out.replace([np.inf, -np.inf], np.nan)


def current_price(md) -> tuple[float, float] | None:
    """(price, previous close) for a symbol — THE authoritative pair.

    The daily history is the authoritative session ledger and it updates
    intraday, so it is the source of truth. yfinance's get_info()/fast_info
    have been observed to lag a full trading day in this environment
    (regularMarketPrice = YESTERDAY's close), which once inverted a green day
    into a red one. So anchor on the bars, and reach for a live tick ONLY
    off-session, where a fresh tick genuinely beats the last completed bar.

    Extracted so the hero total and the portfolio chart cannot disagree. They
    did: the chart overrode its last point with md.live_price unconditionally,
    which put every holding a few dollars above the hero and made the two
    numbers on the same screen drift by ~$40.
    """
    close = md.history["Close"].dropna()
    if len(close) == 0:
        return None
    last_close = float(close.iloc[-1])
    prev_bar = float(close.iloc[-2]) if len(close) > 1 else last_close

    live = getattr(md, "live_price", None)
    if live is not None and not np.isfinite(live):
        live = None  # a NaN/inf live tick is worse than the last real bar

    from datetime import datetime
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    last_bar_day = str(close.index[-1])[:10]  # last VALID bar, not a NaN today-bar

    if last_bar_day == today:
        # Today's bar exists (regular session, updating live): it IS the price;
        # the prior bar is the true previous close. Ignore a stale get_info tick.
        return last_close, prev_bar
    # No bar for today yet (pre-market, or the source hasn't posted): the last
    # completed bar is the previous close and a live tick is the price.
    return (float(live) if live else last_close), last_close


def build_quote(md, ind: Indicators) -> Quote:
    # Drop NaN closes first: this environment's data source has been observed to
    # return a daily bar whose Close is NaN (empty/unposted session), which used
    # to poison last_close -> change -> the whole portfolio day_change sum with a
    # NaN and 500 the JSON response. dropna() anchors us on the last REAL bar.
    close = md.history["Close"].dropna()
    if len(close) == 0:
        # No valid price data at all — degrade gracefully instead of crashing.
        return Quote(symbol=md.symbol, name=md.name, price=0.0, change=0.0,
                     change_pct=0.0, volume=0.0, source=md.source)
    # Same rule as the chart — see current_price() for why the daily bars win
    # over a live tick during the session.
    price, prev = current_price(md)
    change = price - prev
    vol = float(md.history["Volume"].iloc[-1])
    if not np.isfinite(vol):
        vol = 0.0
    return Quote(
        symbol=md.symbol,
        name=md.name,
        price=round(price, 2),
        change=round(change, 2),
        change_pct=round((change / prev * 100) if prev else 0.0, 2),
        volume=vol,
        source=md.source,
    )


def derive_signals(quote: Quote, ind: Indicators) -> list[Signal]:
    """Human-readable technical signals used across reports and the screener."""
    sig: list[Signal] = []
    p = quote.price

    if ind.rsi is not None:
        if ind.rsi >= 70:
            sig.append(Signal(label="RSI overbought", kind="bearish",
                              detail=f"RSI {ind.rsi:.0f} — extended, watch for pullback"))
        elif ind.rsi <= 30:
            sig.append(Signal(label="RSI oversold", kind="bullish",
                              detail=f"RSI {ind.rsi:.0f} — potential mean-reversion bounce"))
        elif 55 <= ind.rsi < 70:
            sig.append(Signal(label="RSI strong", kind="bullish",
                              detail=f"RSI {ind.rsi:.0f} — healthy momentum, not yet extended"))

    if ind.macd is not None and ind.macd_signal is not None:
        if ind.macd > ind.macd_signal and (ind.macd_hist or 0) > 0:
            sig.append(Signal(label="MACD bullish", kind="bullish",
                              detail="MACD above signal line — upside momentum"))
        elif ind.macd < ind.macd_signal:
            sig.append(Signal(label="MACD bearish", kind="bearish",
                              detail="MACD below signal line — momentum fading"))

    if ind.sma50 and ind.sma200:
        if ind.sma50 > ind.sma200:
            sig.append(Signal(label="Golden-cross regime", kind="bullish",
                              detail="50-day above 200-day — long-term uptrend intact"))
        else:
            sig.append(Signal(label="Death-cross regime", kind="bearish",
                              detail="50-day below 200-day — long-term downtrend"))

    if ind.pct_from_52w_high is not None and ind.pct_from_52w_high >= -3:
        sig.append(Signal(label="Near 52-week high", kind="bullish",
                          detail=f"Within {abs(ind.pct_from_52w_high):.1f}% of 52w high — breakout zone"))

    if ind.volume_ratio and ind.volume_ratio >= 1.5:
        sig.append(Signal(label="Volume surge", kind="bullish",
                          detail=f"Volume {ind.volume_ratio:.1f}x the 20-day average"))

    if ind.bb_upper and p > ind.bb_upper:
        sig.append(Signal(label="Above upper Bollinger", kind="bullish",
                          detail="Price pushing above upper band — strong thrust"))

    if not sig:
        sig.append(Signal(label="Neutral", kind="neutral",
                          detail="No strong technical signal right now"))
    return sig
