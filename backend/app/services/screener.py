"""Breakout screener.

Scores each symbol 0-100 for breakout readiness by blending momentum, proximity
to the 52-week high, volume expansion, trend structure and volatility squeeze.
Produces a short deterministic thesis; the richer narrative comes from the
Claude advisor service.
"""
from __future__ import annotations

import pandas as pd

from ..models.schemas import BreakoutCandidate, Indicators, Quote, Signal


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def breakout_score(ind: Indicators, quote: Quote,
                   df: pd.DataFrame | None = None) -> float:
    score = 0.0

    # Proximity to 52-week high (up to 30 pts) — closer = more coiled.
    if ind.pct_from_52w_high is not None:
        dist = abs(ind.pct_from_52w_high)  # 0 == at the high
        score += _clamp(30 * (1 - dist / 20), 0, 30)  # within 20% earns points

    # Momentum via RSI in the sweet spot 55-68 (up to 20 pts).
    if ind.rsi is not None:
        if 55 <= ind.rsi <= 68:
            score += 20
        elif 50 <= ind.rsi < 55:
            score += 12
        elif 68 < ind.rsi <= 75:
            score += 10
        elif ind.rsi > 75:
            score += 3  # overbought — risk of exhaustion

    # MACD confirmation (up to 15 pts).
    if ind.macd is not None and ind.macd_signal is not None:
        if ind.macd > ind.macd_signal:
            score += 10
            if (ind.macd_hist or 0) > 0:
                score += 5

    # Volume expansion (up to 20 pts).
    if ind.volume_ratio is not None:
        score += _clamp(20 * (ind.volume_ratio - 1) / 1.5, 0, 20)

    # Trend structure (up to 10 pts).
    if ind.trend == "uptrend":
        score += 10
    elif ind.trend == "sideways":
        score += 4

    # Volatility squeeze: tight Bollinger band width relative to price (up to 5).
    if ind.bb_upper and ind.bb_lower and quote.price:
        width = (ind.bb_upper - ind.bb_lower) / quote.price
        if width < 0.10:
            score += 5
        elif width < 0.15:
            score += 3

    return round(_clamp(score), 1)


def build_thesis_points(symbol: str, score: float, ind: Indicators, quote: Quote,
                        signals: list[Signal]) -> list[str]:
    """Short scannable bullets — the UI renders these as a list, never prose."""
    points: list[str] = []
    if ind.pct_from_52w_high is not None:
        points.append(
            f"{abs(ind.pct_from_52w_high):.1f}% "
            f"{'below' if ind.pct_from_52w_high < 0 else 'above'} the 52-week high"
        )
    if ind.trend:
        points.append(f"Structure: {ind.trend}")
    points.extend(s.detail for s in signals if s.kind == "bullish")
    return points[:5]


def evaluate(symbol: str, theme, md) -> BreakoutCandidate:
    from .technical import build_quote, compute_indicators, derive_signals

    ind = compute_indicators(md.history)
    quote = build_quote(md, ind)
    signals = derive_signals(quote, ind)
    score = breakout_score(ind, quote, md.history)
    points = build_thesis_points(symbol, score, ind, quote, signals)
    return BreakoutCandidate(
        symbol=symbol.upper(),
        theme=theme,
        score=score,
        price=quote.price,
        quote=quote,
        indicators=ind,
        signals=[s for s in signals if s.kind == "bullish"] or signals,
        thesis=" · ".join(points),
        thesis_points=points,
    )
