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

    return Indicators(
        rsi=_f(rsi.iloc[last]),
        rsi_prev=_f(rsi.iloc[-2]) if len(rsi) > 1 else None,
        rsi_min_10d=_f(rsi.tail(10).min()),
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


def build_quote(md, ind: Indicators) -> Quote:
    close = md.history["Close"]
    price = float(close.iloc[-1])
    prev = float(close.iloc[-2]) if len(close) > 1 else price
    change = price - prev
    return Quote(
        symbol=md.symbol,
        name=md.name,
        price=round(price, 2),
        change=round(change, 2),
        change_pct=round((change / prev * 100) if prev else 0.0, 2),
        volume=float(md.history["Volume"].iloc[-1]),
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
