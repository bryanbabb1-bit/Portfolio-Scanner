// Typed client for the Portfolio Scanner backend.
// Default is same-origin: Next rewrites proxy /api/* to FastAPI server-side,
// so the app works identically on localhost and through a tunnel/PWA install.
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "";

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
  rsi_prev?: number;
  rsi_min_10d?: number;
  ret_5d_pct?: number;
  ret_20d_pct?: number;
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
  earnings_date?: string | null;
  days_to_earnings?: number | null;
}

export interface RunnerCandidate {
  symbol: string;
  name?: string;
  theme?: string;
  price: number;
  change_pct: number;
  runner_score: number;
  stage: "coiled" | "igniting" | "extended" | "cooling";
  float_shares?: number | null;
  market_cap?: number | null;
  short_pct_float?: number | null;
  float_pct?: number | null;
  recent_ipo: boolean;
  volume_ratio?: number | null;
  ret_5d_pct?: number | null;
  ret_20d_pct?: number | null;
  rsi?: number | null;
  reasons: string[];
  caution?: string | null;
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
  thesis_points?: string[];
}

export interface AdvisorNote {
  symbol: string;
  persona: string;
  engine: string;
  generated_at: string;
  summary: string;
  posture?: "act" | "watch" | null;
  call?: string | null;   // standing one-word stance: BUY/ADD/HOLD/TRIM/SELL/WATCH
  insights: string[];
  actions: string[];
  risks: string[];
  scout?: string[];
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
  cash: number;
  source: string;
  by_theme: Record<string, number>;
  realized_pl: number;
  total_return: number;
  total_return_pct: number;
}

export interface PortfolioAlert {
  symbol: string;
  severity: "critical" | "warning" | "opportunity";
  label: string;
  detail: string;
  id?: string;
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

export interface ConvictionSignal {
  id: string;
  symbol: string;
  dismissed?: boolean;
  side: "buy" | "sell";
  rule: string;
  label: string;
  headline: string;
  what: string;
  why: string[];
  entry?: string;
  size?: string;
  target: string;
  stop: string;
  price: number;
  theme?: string;
  held?: boolean;
  generated_at: string;
}

export interface Pin {
  id: string;
  symbol?: string | null;
  source: string;
  text: string;
  points: string[];
  status: "open" | "done";
  created_at: string;
  done_at?: string | null;
}

export interface JournalEntry {
  id: string;
  symbol?: string | null;
  action: "buy" | "sell" | "note";
  date: string;
  shares?: number | null;
  price?: number | null;
  note: string;
  source: string;
  cost_basis?: number | null;
  realized_pl?: number | null;
}

export interface JournalDraft {
  symbol?: string | null;
  action: "buy" | "sell" | "note";
  date?: string;
  shares?: number | null;
  price?: number | null;
  note?: string;
  cost_basis?: number | null;
  realized_pl?: number | null;
}

export interface StrategyDoc {
  goals: {
    target_value?: number | null;
    horizon?: string | null;
    monthly_contribution?: number | null;
    risk_appetite?: string | null;
    notes?: string | null;
  };
  thesis: string;
  short_term: string[];
  long_term: string[];
  allocation_targets: Record<string, number>;
  guardrails: string[];
  milestones: string[];
  approved: boolean;
  generated_at: string;
  updated_at?: string;
}

export interface Watchpoint {
  id: string;
  symbol: string;
  kind: "price_below" | "price_above" | "rsi_below" | "rsi_above";
  level: number;
  note: string;
  side: "buy" | "sell";
  confirm?: "touch" | "close";
  source: string;
  status: "armed" | "triggered";
  created_at: string;
  triggered_at?: string;
}

export interface ScorecardRule {
  rule: string;
  signals: number;
  win_rate: number;
  avg_effective_pct: number;
  best_pct: number;
  worst_pct: number;
}

export interface Scorecard {
  count: number;
  overall_win_rate: number | null;
  overall_avg_pct: number | null;
  rules: ScorecardRule[];
  signals: {
    id: string; symbol: string; side: string; rule: string; date: string;
    price: number; current: number; effective_pct: number; age_days: number;
  }[];
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
  cash?: number;
  core_convictions?: string[];
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
  rsi?: number | null;
}

export interface PriceHistory {
  symbol: string;
  range: string;
  source: string;
  candles: Candle[];
}

export type ChartRange = "1d" | "5d" | "1mo" | "3mo" | "6mo" | "1y";

export const CHART_RANGES: ChartRange[] = ["1d", "5d", "1mo", "3mo", "6mo", "1y"];
export const RANGE_LABELS: Record<ChartRange, string> = {
  "1d": "1D",
  "5d": "1W",
  "1mo": "1M",
  "3mo": "3M",
  "6mo": "6M",
  "1y": "1Y",
};

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

export interface AskAnswer {
  engine: string;
  answer: string;
  points: string[];
  generated_at: string;
}

export interface Recommendation {
  engine: string;
  generated_at: string;
  action: "BUY" | "ADD" | "TRIM" | "SELL" | "HOLD" | "AVOID";
  headline: string;
  what: string;
  why: string[];
  entry?: string;
  size?: string;
  target: string;
  stop: string;
  // freshness receipt — the exact price/time this call reasoned from
  price?: number | null;
  change_pct?: number | null;
  data_source?: string | null;
  as_of?: string | null;
}

async function put<T>(path: string, body: unknown): Promise<T> {
  return send<T>(path, "PUT", body);
}

async function post<T>(path: string, body: unknown): Promise<T> {
  return send<T>(path, "POST", body);
}

async function send<T>(path: string, method: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
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

export interface DailyBrief {
  type: "morning" | "eod";
  date: string;
  generated_at: string;
  engine: string;
  headline: string;
  summary: string;
  watch: string[];
  recap: string[];
}

export interface PlanGate {
  level: number;
  current: number;
  distance_pct: number;
  direction: "rise" | "fall";
  met: boolean;
  rsi?: boolean;
}

export interface PlanMove {
  id: string;
  source: "trigger" | "pin" | "signal";
  symbol?: string | null;
  side: "buy" | "sell" | "hold";
  text: string;
  amount?: number | null;
  gate?: PlanGate | null;
  funded_by?: string | null;
  status: "ready" | "waiting" | "guard";
  wait_reason?: string | null;
  stop?: boolean;
  pin_id?: string;
  wp_id?: string;
}

export interface PlanIdea {
  id: string;
  symbol: string;
  tag: "high" | "spec" | "idea";
  text: string;
  order: string;
  size?: string | null;
  entry?: string | null;
  target?: string | null;
}

export interface GamePlanData {
  dry_powder: number;
  queued_buys: number;
  fits: boolean;
  leftover: number;
  over_by: number;
  funded_by_sale: boolean;
  funders: string[];
  ready: PlanMove[];
  waiting: PlanMove[];
  guards: PlanMove[];
  ideas: PlanIdea[];
  count: number;
}

export interface GraphNode { symbol: string; theme: string; weight: number; }
export interface GraphEdge { a: string; b: string; corr: number; }
export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  avg_corr: number | null;
  source: string;
  pairs: number;
}

export const api = {
  plan: () => get<GamePlanData>("/api/plan"),
  graph: () => get<GraphData>("/api/graph"),
  health: () => get<{ status: string; data_mode: string; advisor_enabled: boolean }>("/api/health"),
  summary: () => get<{ brief: DailyBrief | null; dismissed: boolean }>("/api/summary"),
  generateBrief: (kind: "morning" | "eod") =>
    post<DailyBrief>(`/api/summary/generate?kind=${kind}`, {}),
  dismissBrief: () => post<{ dismissed: string | null }>("/api/summary/dismiss", {}),
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
  adviseStock: (symbol: string, force = false, deep = false) =>
    get<AdvisorNote>(`/api/advisor/stock/${symbol}?force=${force}&deep=${deep}`),
  adviseBreakout: (symbol: string, force = false, deep = false) =>
    get<AdvisorNote>(`/api/advisor/breakout/${symbol}?force=${force}&deep=${deep}`),
  advisePortfolio: (force = false, deep = false) =>
    get<AdvisorNote>(`/api/advisor/portfolio?force=${force}&deep=${deep}`),
  recommend: (symbol: string, event: string, kind = "alert") =>
    post<Recommendation>("/api/advisor/recommend", { symbol, event, kind }),
  lastAdvisorNote: (kind: "portfolio" | "stock" | "breakout", symbol?: string) =>
    get<AdvisorNote>(
      `/api/advisor/last?kind=${kind}${symbol ? `&symbol=${symbol}` : ""}`
    ).catch(() => null as AdvisorNote | null),
  askAdvisor: (
    kind: "portfolio" | "stock" | "breakout" | "strategy",
    symbol: string | undefined,
    question: string,
    deep = false
  ) => post<AskAnswer>("/api/advisor/ask", { kind, symbol, question, deep }),
  watchpoints: () => get<{ count: number; results: Watchpoint[] }>("/api/watchpoints"),
  addWatchpoint: (wp: { symbol: string; kind: Watchpoint["kind"]; level: number; note?: string; side?: "buy" | "sell"; confirm?: "touch" | "close" }) =>
    post<Watchpoint>("/api/watchpoints", wp),
  scorecard: () => get<Scorecard>("/api/scorecard"),
  deleteWatchpoint: (id: string) =>
    send<{ deleted: string }>(`/api/watchpoints/${id}`, "DELETE"),
  extractWatchpoints: () =>
    send<{ created: number; results: Watchpoint[] }>("/api/watchpoints/extract", "POST"),
  strategy: () => get<StrategyDoc>("/api/strategy").catch(() => null as StrategyDoc | null),
  generateStrategy: (inputs: {
    target_value?: number;
    horizon?: string;
    monthly_contribution?: number;
    risk_appetite?: string;
    notes?: string;
    deep?: boolean;
  }) => post<StrategyDoc>("/api/strategy/generate", inputs),
  saveStrategy: (doc: StrategyDoc) => put<StrategyDoc>("/api/strategy", doc),
  insights: () => get<PortfolioInsights>("/api/insights"),
  dismissAlert: (id?: string) =>
    send<{ dismissed: number }>(
      `/api/insights/dismiss${id ? `?id=${encodeURIComponent(id)}` : ""}`,
      "POST"
    ),
  signals: (demo = false) =>
    get<{ count: number; results: ConvictionSignal[] }>(`/api/signals?demo=${demo}`),
  dismissSignal: (id?: string) =>
    send<{ dismissed: number }>(
      `/api/signals/dismiss${id ? `?id=${encodeURIComponent(id)}` : ""}`,
      "POST"
    ),
  pins: () => get<{ count: number; results: Pin[] }>("/api/pins"),
  journal: (days = 30) =>
    get<{ count: number; results: JournalEntry[] }>(`/api/journal?days=${days}`),
  addJournal: (draft: JournalDraft) => post<JournalEntry>("/api/journal", draft),
  updateJournal: (id: string, draft: Partial<JournalDraft>) =>
    send<JournalEntry>(`/api/journal/${id}`, "PATCH", draft),
  deleteJournal: (id: string) => send<{ deleted: string }>(`/api/journal/${id}`, "DELETE"),
  clearJournal: () => post<{ cleared: number }>("/api/journal/clear", {}),
  addPin: (pin: { symbol?: string | null; source: string; text: string; points?: string[] }) =>
    post<Pin>("/api/pins", pin),
  setPinStatus: (id: string, status: "open" | "done") =>
    send<Pin>(`/api/pins/${id}`, "PATCH", { status }),
  deletePin: (id: string) => send<{ deleted: string }>(`/api/pins/${id}`, "DELETE"),
  discover: (minScore = 0, limit = 24) =>
    get<{ count: number; universe: number; source: string; results: BreakoutCandidate[] }>(
      `/api/discover?min_score=${minScore}&limit=${limit}`
    ),
  runners: (extra: string[] = []) =>
    get<{ count: number; universe: number; live_movers: number; source: string; results: RunnerCandidate[] }>(
      `/api/runners?limit=60${extra.length ? `&extra=${encodeURIComponent(extra.join(","))}` : ""}`
    ),
  news: (limit = 40) =>
    get<{ count: number; source: string; results: PortfolioNewsItem[] }>(
      `/api/news?limit=${limit}`
    ),
};
