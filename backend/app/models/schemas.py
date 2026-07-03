"""Pydantic response/request models shared across routers."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator


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
    # Recent close series (~30 pts) for an inline sparkline on cards.
    spark: list[float] = []


class BreakoutCandidate(BaseModel):
    symbol: str
    theme: Optional[str] = None
    score: float  # 0-100 composite breakout readiness
    price: float
    quote: Quote
    indicators: Indicators
    signals: list[Signal] = []
    thesis: Optional[str] = None       # joined fallback for older clients
    thesis_points: list[str] = []      # bullet form — preferred by the UI


class AdvisorNote(BaseModel):
    """Advisor output is bullet-first: short scannable points, never prose walls."""
    symbol: str
    persona: str
    engine: str  # "claude" | "fallback"
    generated_at: str
    summary: str                # 1-2 sentence overall take
    insights: list[str] = []    # technical / portfolio-health observations
    actions: list[str] = []     # concrete recommendations (ticker + level each)
    risks: list[str] = []       # each risk paired with its confirming signal
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


class PinCreate(BaseModel):
    """Pin an advisor recommendation to the persistent action list."""
    symbol: Optional[str] = None
    source: str = "advisor"  # "brief" | "advisor" | "ask" | "signal"
    text: str = Field(min_length=1, max_length=1000)
    points: list[str] = []


class PinUpdate(BaseModel):
    status: str  # "open" | "done"

    @field_validator("status")
    @classmethod
    def _valid_status(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in {"open", "done"}:
            raise ValueError("status must be open or done")
        return v


class JournalCreate(BaseModel):
    """A manually recorded move for the action journal."""
    symbol: Optional[str] = None
    action: str  # "buy" | "sell" | "note"
    date: Optional[str] = None       # YYYY-MM-DD; default today
    shares: Optional[float] = Field(default=None, ge=0)
    price: Optional[float] = Field(default=None, ge=0)
    note: str = ""

    @field_validator("action")
    @classmethod
    def _valid_action(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in {"buy", "sell", "note"}:
            raise ValueError("action must be buy, sell or note")
        return v


class JournalUpdate(BaseModel):
    symbol: Optional[str] = None
    action: Optional[str] = None
    date: Optional[str] = None
    shares: Optional[float] = Field(default=None, ge=0)
    price: Optional[float] = Field(default=None, ge=0)
    note: Optional[str] = None


class AskRequest(BaseModel):
    """A follow-up question about a prior advisor note."""
    kind: str  # "portfolio" | "stock" | "breakout" | "strategy"
    symbol: Optional[str] = None
    question: str = Field(min_length=1, max_length=2000)
    deep: bool = False  # allow web research (slower, live news/sentiment)

    @field_validator("kind")
    @classmethod
    def _valid_kind(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in {"portfolio", "stock", "breakout", "strategy"}:
            raise ValueError("kind must be portfolio, stock, breakout or strategy")
        return v


class StrategyGenRequest(BaseModel):
    """Client goals feeding strategy generation."""
    target_value: Optional[float] = Field(default=None, ge=0)
    horizon: Optional[str] = None            # e.g. "5 years"
    monthly_contribution: Optional[float] = Field(default=None, ge=0)
    risk_appetite: Optional[str] = None      # conservative | balanced | aggressive
    notes: Optional[str] = Field(default=None, max_length=2000)
    deep: bool = False


# ------------------------------------------------------------- intelligence
class PortfolioAlert(BaseModel):
    """A rule-derived attention item for the dashboard alerts panel."""
    symbol: str
    severity: str  # "critical" | "warning" | "opportunity"
    label: str
    detail: str


class RiskMetrics(BaseModel):
    beta: Optional[float] = None              # vs SPY, ~6mo daily returns
    volatility_pct: Optional[float] = None    # annualized stdev of daily returns
    sharpe: Optional[float] = None            # annualized, 4% risk-free
    max_drawdown_pct: Optional[float] = None  # worst peak-to-trough, 1y
    best_day_pct: Optional[float] = None
    best_day_date: Optional[str] = None
    worst_day_pct: Optional[float] = None
    worst_day_date: Optional[str] = None
    top_symbol: Optional[str] = None          # largest position
    top_weight_pct: Optional[float] = None
    top5_weight_pct: Optional[float] = None


class PortfolioInsights(BaseModel):
    source: str  # "live" | "mock"
    risk: RiskMetrics
    alerts: list[PortfolioAlert] = []


class PortfolioNewsItem(BaseModel):
    """A news headline tagged with the symbol(s) it came from."""
    title: str
    symbols: list[str] = []
    publisher: Optional[str] = None
    link: Optional[str] = None
    published: Optional[str] = None


# --------------------------------------------------------------- config I/O
class Holding(BaseModel):
    """A held position. shares/cost_basis drive the P/L math."""
    symbol: str
    shares: float = Field(ge=0)
    cost_basis: float = Field(ge=0)
    theme: Optional[str] = None

    @field_validator("symbol")
    @classmethod
    def _upper_symbol(cls, v: str) -> str:
        v = (v or "").strip().upper()
        if not v:
            raise ValueError("symbol is required")
        return v


class WatchItem(BaseModel):
    """A name you're watching but don't hold."""
    symbol: str
    theme: Optional[str] = None

    @field_validator("symbol")
    @classmethod
    def _upper_symbol(cls, v: str) -> str:
        v = (v or "").strip().upper()
        if not v:
            raise ValueError("symbol is required")
        return v


class PortfolioConfig(BaseModel):
    """The full editable portfolio config persisted to portfolio.json."""
    owner: str = "You"
    advisor_persona: str = "senior financial advisor at Charles Schwab"
    themes: dict[str, str] = {}
    holdings: list[Holding] = []
    watchlist: list[WatchItem] = []


# ----------------------------------------------------------------- charting
class Candle(BaseModel):
    date: str          # ISO date (YYYY-MM-DD) or "YYYY-MM-DD HH:MM" intraday
    open: float
    high: float
    low: float
    close: float
    volume: float
    sma20: Optional[float] = None
    sma50: Optional[float] = None
    rsi: Optional[float] = None  # RSI(14) over the same bars, for the RSI pane


class PriceHistory(BaseModel):
    symbol: str
    range: str          # "1mo" | "3mo" | "6mo" | "1y"
    source: str         # "live" | "mock"
    candles: list[Candle] = []


class ValuePoint(BaseModel):
    date: str           # ISO date (YYYY-MM-DD)
    value: float        # portfolio market value on that day


class PortfolioHistory(BaseModel):
    range: str          # "1mo" | "3mo" | "6mo" | "1y"
    source: str         # "live" | "mock"
    cost_basis: float   # flat total cost baseline
    points: list[ValuePoint] = []
