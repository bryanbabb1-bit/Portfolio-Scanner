// Typed client for the Portfolio Scanner backend.
export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export interface Quote {
  symbol: string;
  name?: string;
  price: number;
  change: number;
  change_pct: number;
  currency: string;
  market_cap?: number;
  volume?: number;
  source: string;
}

export interface Indicators {
  rsi?: number;
  macd?: number;
  macd_signal?: number;
  macd_hist?: number;
  sma20?: number;
  sma50?: number;
  sma200?: number;
  ema20?: number;
  atr?: number;
  bb_upper?: number;
  bb_lower?: number;
  high_52w?: number;
  low_52w?: number;
  pct_from_52w_high?: number;
  avg_volume_20?: number;
  volume_ratio?: number;
  trend?: string;
}

export interface AnalystView {
  recommendation?: string;
  mean_target?: number;
  high_target?: number;
  low_target?: number;
  num_analysts?: number;
  upside_pct?: number;
}

export interface NewsItem {
  title: string;
  publisher?: string;
  link?: string;
  published?: string;
}

export interface Signal {
  label: string;
  kind: "bullish" | "bearish" | "neutral";
  detail: string;
}

export interface StockReport {
  symbol: string;
  theme?: string;
  quote: Quote;
  indicators: Indicators;
  analyst: AnalystView;
  news: NewsItem[];
  signals: Signal[];
  shares?: number;
  cost_basis?: number;
  market_value?: number;
  unrealized_pl?: number;
  unrealized_pl_pct?: number;
  spark?: number[];
}

export interface BreakoutCandidate {
  symbol: string;
  theme?: string;
  score: number;
  price: number;
  quote: Quote;
  indicators: Indicators;
  signals: Signal[];
  thesis?: string;
}

export interface AdvisorNote {
  symbol: string;
  persona: string;
  engine: string;
  generated_at: string;
  summary: string;
  technical_read: string;
  recommendation: string;
  risks: string;
  raw?: string;
}

export interface PortfolioSummary {
  total_market_value: number;
  total_cost: number;
  total_unrealized_pl: number;
  total_unrealized_pl_pct: number;
  day_change: number;
  day_change_pct: number;
  positions: number;
  source: string;
  by_theme: Record<string, number>;
}

export interface PortfolioAlert {
  symbol: string;
  severity: "critical" | "warning" | "opportunity";
  label: string;
  detail: string;
}

export interface RiskMetrics {
  beta?: number;
  volatility_pct?: number;
  sharpe?: number;
  max_drawdown_pct?: number;
  best_day_pct?: number;
  best_day_date?: string;
  worst_day_pct?: number;
  worst_day_date?: string;
  top_symbol?: string;
  top_weight_pct?: number;
  top5_weight_pct?: number;
}

export interface PortfolioInsights {
  source: string;
  risk: RiskMetrics;
  alerts: PortfolioAlert[];
}

export interface PortfolioNewsItem {
  title: string;
  symbols: string[];
  publisher?: string;
  link?: string;
  published?: string;
}

export interface Holding {
  symbol: string;
  shares: number;
  cost_basis: number;
  theme?: string;
}

export interface WatchItem {
  symbol: string;
  theme?: string;
}

export interface PortfolioConfig {
  owner: string;
  advisor_persona: string;
  themes: Record<string, string>;
  holdings: Holding[];
  watchlist: WatchItem[];
}

export interface Candle {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  sma20?: number;
  sma50?: number;
}

export interface PriceHistory {
  symbol: string;
  range: string;
  source: string;
  candles: Candle[];
}

export type ChartRange = "1mo" | "3mo" | "6mo" | "1y";

export interface ValuePoint {
  date: string;
  value: number;
}

export interface PortfolioHistory {
  range: string;
  source: string;
  cost_basis: number;
  points: ValuePoint[];
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} on ${path}`);
  return res.json();
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      if (j?.detail) {
        detail = Array.isArray(j.detail)
          ? j.detail.map((d: any) => `${d.loc?.slice(1).join(".")}: ${d.msg}`).join("; ")
          : j.detail;
      }
    } catch {}
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  health: () => get<{ status: string; data_mode: string; advisor_enabled: boolean }>("/api/health"),
  portfolio: () =>
    get<{ summary: PortfolioSummary; holdings: StockReport[] }>("/api/portfolio"),
  scan: (watchlist = true) =>
    get<{ count: number; source: string; results: StockReport[] }>(
      `/api/scan?include_watchlist=${watchlist}`
    ),
  breakouts: (minScore = 0, limit = 20) =>
    get<{ count: number; source: string; results: BreakoutCandidate[] }>(
      `/api/breakouts?min_score=${minScore}&limit=${limit}`
    ),
  stock: (symbol: string) => get<StockReport>(`/api/stock/${symbol}`),
  history: (symbol: string, range: ChartRange = "6mo") =>
    get<PriceHistory>(`/api/stock/${symbol}/history?range=${range}`),
  portfolioHistory: (range: ChartRange = "6mo") =>
    get<PortfolioHistory>(`/api/portfolio/history?range=${range}`),
  watchlist: () =>
    get<{ count: number; source: string; results: StockReport[] }>("/api/watchlist"),
  config: () => get<PortfolioConfig>("/api/config"),
  saveConfig: (cfg: PortfolioConfig) => put<PortfolioConfig>("/api/config", cfg),
  quotes: (symbols: string[]) =>
    get<{ quotes: Record<string, { price: number | null; source: string }> }>(
      `/api/quotes?symbols=${encodeURIComponent(symbols.join(","))}`
    ),
  adviseStock: (symbol: string, force = false) =>
    get<AdvisorNote>(`/api/advisor/stock/${symbol}?force=${force}`),
  adviseBreakout: (symbol: string, force = false) =>
    get<AdvisorNote>(`/api/advisor/breakout/${symbol}?force=${force}`),
  advisePortfolio: (force = false) =>
    get<AdvisorNote>(`/api/advisor/portfolio?force=${force}`),
  insights: () => get<PortfolioInsights>("/api/insights"),
  discover: (minScore = 0, limit = 24) =>
    get<{ count: number; universe: number; source: string; results: BreakoutCandidate[] }>(
      `/api/discover?min_score=${minScore}&limit=${limit}`
    ),
  news: (limit = 40) =>
    get<{ count: number; source: string; results: PortfolioNewsItem[] }>(
      `/api/news?limit=${limit}`
    ),
};
