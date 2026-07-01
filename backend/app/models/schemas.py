"""Pydantic response/request models shared across routers."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class Quote(BaseModel):
    symbol: str
    name: Optional[str] = None
    price: float
    change: float
    change_pct: float
    currency: str = "USD"
    market_cap: Optional[float] = None
    volume: Optional[float] = None
    source: str = "live"  # "live" | "mock"


class Indicators(BaseModel):
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None
    sma20: Optional[float] = None
    sma50: Optional[float] = None
    sma200: Optional[float] = None
    ema20: Optional[float] = None
    atr: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_lower: Optional[float] = None
    high_52w: Optional[float] = None
    low_52w: Optional[float] = None
    pct_from_52w_high: Optional[float] = None
    avg_volume_20: Optional[float] = None
    volume_ratio: Optional[float] = None  # today's volume / 20d avg
    trend: Optional[str] = None  # "uptrend" | "downtrend" | "sideways"


class AnalystView(BaseModel):
    recommendation: Optional[str] = None
    mean_target: Optional[float] = None
    high_target: Optional[float] = None
    low_target: Optional[float] = None
    num_analysts: Optional[int] = None
    upside_pct: Optional[float] = None


class NewsItem(BaseModel):
    title: str
    publisher: Optional[str] = None
    link: Optional[str] = None
    published: Optional[str] = None


class Signal(BaseModel):
    label: str
    kind: str  # "bullish" | "bearish" | "neutral"
    detail: str


class StockReport(BaseModel):
    symbol: str
    theme: Optional[str] = None
    quote: Quote
    indicators: Indicators
    analyst: AnalystView
    news: list[NewsItem] = []
    signals: list[Signal] = []
    # Position economics (present only for held names)
    shares: Optional[float] = None
    cost_basis: Optional[float] = None
    market_value: Optional[float] = None
    unrealized_pl: Optional[float] = None
    unrealized_pl_pct: Optional[float] = None


class BreakoutCandidate(BaseModel):
    symbol: str
    theme: Optional[str] = None
    score: float  # 0-100 composite breakout readiness
    price: float
    quote: Quote
    indicators: Indicators
    signals: list[Signal] = []
    thesis: Optional[str] = None  # short deterministic thesis; AI thesis via advisor


class AdvisorNote(BaseModel):
    symbol: str
    persona: str
    engine: str  # "claude" | "fallback"
    generated_at: str
    summary: str
    technical_read: str
    recommendation: str
    risks: str
    raw: Optional[str] = None


class PortfolioSummary(BaseModel):
    total_market_value: float
    total_cost: float
    total_unrealized_pl: float
    total_unrealized_pl_pct: float
    day_change: float
    day_change_pct: float
    positions: int
    source: str
    by_theme: dict[str, float] = {}
