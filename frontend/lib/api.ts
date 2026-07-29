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

export interface StayCourse {
  posture: "hold" | "act";
  headline: string;
  reasons: string[];
  closer: string;
  engine: string;
  generated_at: string;
  metrics: {
    value: number;
    day_pct: number;
    total_return_pct: number;
    unrealized_pct: number;
    above_trend: number;
    holdings: number;
    realized: number;
    ready_count: number;
    critical_count: number;
    resilience?: { symbol: string; low: number; price: number; gain_pct: number } | null;
    goal?: { target: number; progress_pct: number; remaining: number; horizon: string };
  };
}

export interface AdvisorStep {
  n: number;
  when: string;
  do: string;
  why?: string;
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
  mix?: string[];         // allocation health vs strategy targets
  positions?: string[];   // per-name color on notable holdings
  actions: string[];
  risks: string[];
  scout?: string[];
  sequence?: AdvisorStep[];
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

export interface RuleHealth {
  rule: string;
  side: "buy" | "sell";
  verdict: "EARNING" | "MARGINAL" | "RETUNE" | "RETIRE";
  reason: string;
  backtest_signals: number;
  backtest_win_rate: number | null;
  backtest_avg_pct: number | null;
  profit_factor: number | null;
  live_signals: number;
  live_win_rate: number | null;
  live_avg_pct: number | null;
  knob: string | null;
  proposal: string | null;
  accepted: { rule: string; accepted_at: string; note: string } | null;
  retired: boolean;
}

export interface Learning {
  as_of: string;
  rules: RuleHealth[];
  counts: Record<string, number>;
  backtest_as_of: string | null;
  backtest_period: { start: string; end: string } | null;
  live_signals_graded: number;
  live_win_rate: number | null;
  has_backtest: boolean;
  robustness?: Robustness | null;
  notes: string[];
}

export interface BacktestRule {
  rule: string;
  side: "buy" | "sell";
  signals: number;
  win_rate: number;
  avg_5: number;
  avg_20: number;
  avg_60: number;
  best: number;
  worst: number;
  profit_factor: number | null;
  avg_mae: number;
  symbols: number;
}

export interface TransitionStep {
  n: number;
  trigger: string;
  sell: string;
  buy: string;
  buy_symbol: string;
  buy_level: number;
  sell_symbol: string;
  sell_level: number;
  why: string;
  realizes: string;
  done: boolean;
  blocked?: boolean;
  blocked_reason?: string;
}

export interface Coherence {
  target_source: string;
  strategy_approved: boolean;
  core_convictions: string[];
  clean: boolean;
  conflicts: {
    symbol: string;
    severity: "critical" | "warning" | "info";
    detail: string;
    resolution: string;
  }[];
}

export interface TransitionAnalysis {
  equity: number;
  cash: number;
  target_source: string;
  drift_pct: number;
  total_return_pct: number;
  gap: { theme: string; target_pct: number; current_pct: number; delta: number }[];
  funding: {
    symbol: string;
    theme: string;
    value: number;
    weight_pct: number;
    pl_pct: number;
    suggested_trim: number;
    in_target_book: boolean;
    standing_call?: string;
    tax: { at_loss: boolean; term: string; held_days: number | null; detail: string };
  }[];
  acquire: {
    symbol: string;
    theme: string;
    target_pct: number;
    target_dollars: number;
    price: number | null;
    stop: number | null;
    why: string;
  }[];
}

export interface TransitionPlan {
  ts: number;
  as_of?: string;
  engine: string;
  headline?: string;
  approach?: string;
  first_move?: string;
  steps: TransitionStep[];
  guardrails?: string[];
  analysis: TransitionAnalysis;
  coherence?: Coherence;
  activated?: boolean;
  activated_at?: string;
  watched?: string[];
  watchpoints_created?: number;
  error: string | null;
}

export interface CleanSheetThemeRow {
  theme: string;
  target_pct: number;
  current_pct: number;
  delta: number;
}

export interface CleanSheetPick {
  symbol: string;
  theme: string;
  pct: number;
  why: string;
}

export interface CleanSheet {
  ts: number;
  as_of?: string;
  engine: string;
  equity?: number;
  thesis?: string;
  allocation: { theme: string; pct: number; why: string }[];
  picks: CleanSheetPick[];
  avoided?: string[];
  diff: {
    themes: CleanSheetThemeRow[];
    held_picks: string[];
    new_picks: string[];
    overlap_pct: number;
    name_overlap_pct: number;
    blind_spots: CleanSheetThemeRow[];
    overweight: CleanSheetThemeRow[];
    equity: number;
  } | null;
  verdict?: "ALIGNED" | "PARTIAL" | "DIVERGENT";
  headline?: string;
  method?: string;
  error: string | null;
}

export interface RobustnessCell {
  n: number;
  avg: number | null;
  win_rate: number | null;
  thin: boolean;
}

export interface RobustnessRow {
  rule: string;
  side: "buy" | "sell";
  signals: number;
  cells: Record<string, RobustnessCell>;
  verdict: "ROBUST" | "FRAGILE" | "BROKEN" | "UNPROVEN";
  reason: string;
}

export interface Robustness {
  columns: string[];
  horizons: string[];
  regimes: string[];
  rules: RobustnessRow[];
  min_cell: number;
  regime_signal_counts: Record<string, number>;
  unclassified: number;
  definition: string;
  retirement_warnings: string[];
  note?: string;
}

export interface BacktestCurvePoint {
  date: string;
  strategy: number;
  benchmark: number;
}

export interface Backtest {
  ts: number;
  as_of: string;
  elapsed_s: number;
  years: number;
  universe: number;
  symbols_tested: number;
  skipped: string[];
  period: { start: string; end: string } | null;
  signals: number;
  win_rate: number | null;
  avg_return_pct: number | null;
  profit_factor: number | null;
  max_drawdown_pct: number | null;
  grade_horizon_days: number;
  rules: BacktestRule[];
  curve: {
    points: BacktestCurvePoint[];
    strategy_return_pct?: number;
    benchmark_return_pct?: number;
    max_drawdown_pct?: number;
    days_invested_pct?: number;
    note: string;
  };
  robustness?: Robustness;
  caveats: string[];
}

export interface DebateAgent {
  key: "bull" | "bear" | "macro" | "risk" | "execution";
  name: string;
  round: 1 | 2;
  position: "BULLISH" | "BEARISH" | "NEUTRAL";
  confidence: number;
  points: string[];
  strongest: string;
  ok: boolean;
}

export interface Debate {
  symbol: string;
  name?: string;
  price: number;
  ts: number;
  as_of: string;
  engine: string;
  agents: DebateAgent[];
  agents_reporting: number;
  tally: { bullish: number; bearish: number; neutral: number };
  verdict: "APPROVE" | "REJECT" | null;
  action: string;
  score: number;
  headline: string;
  rationale: string[];
  dissent: string[];
  entry: string;
  target: string;
  stop: string;
  sizing: PositionPlan;
  error: string | null;
}

export interface PositionRisk {
  symbol: string;
  price: number;
  market_value: number;
  weight_pct: number;
  stop?: number;
  stop_basis?: string;
  stop_distance_pct?: number;
  risk_amount?: number;
  risk_pct_of_equity?: number;
  over_size: boolean;
}

export interface PositionPlan {
  symbol: string;
  price: number;
  stop?: number;
  stop_basis?: string;
  risk_per_share?: number;
  dollars: number;
  shares: number;
  pct_of_equity: number;
  risk_amount: number;
  capped_by?: string;
  note: string;
}

export interface RiskDesk {
  equity: number;
  invested: number;
  cash: number;
  status: "PROTECTED" | "ELEVATED" | "BREACHED";
  risk_per_trade_pct: number;
  risk_budget_amount: number;
  daily_loss_limit_pct: number;
  daily_loss_limit_amount: number;
  day_pl: number;
  day_pl_pct: number;
  limit_breached: boolean;
  portfolio_risk_pct?: number;
  portfolio_risk_amount?: number;
  exposure_utilization_pct: number;
  positions: PositionRisk[];
  max_drawdown_pct?: number;
  var95_pct?: number;
  var95_amount?: number;
  beta?: number;
  avg_correlation?: number;
  liquidity?: string;
  history_days: number;
  notes: string[];
  metrics: RiskMetrics;
  source: string;
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
  quiet_unowned_low_cash?: boolean;
  signals_owned_only?: boolean;
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

/** One recorded turn of the ongoing advisor conversation. */
export interface ChatTurn {
  ts: string;
  q: string;
  a: string;
  points: string[];
}

export interface AskAnswer {
  engine: string;
  answer: string;
  points: string[];
  generated_at: string;
}

// Deep asks run web research for 1-5 min. The Cloudflare tunnel kills any
// single request at ~100s (524), so we never hold one open: start a background
// job, then poll a fast status endpoint until it finishes. Each poll is
// instant, so tunnel + proxy timeouts never fire regardless of research length.
/** Poll a backgrounded advisor job to completion.
 *
 * Every long advisor call goes through this. A single request that runs past
 * ~100s is killed at the Cloudflare edge with a 524, which is what the brief
 * started doing once it also had to produce the staged plan. Short polls never
 * hit that ceiling.
 */
async function pollAdvisorJob<T>(jobId: string, label: string): Promise<T> {
  const intervalMs = 2500;
  const maxAttempts = Math.ceil((8 * 60 * 1000) / intervalMs);
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise((r) => setTimeout(r, intervalMs));
    const s = await get<{
      status: "pending" | "done" | "error" | "gone";
      result?: T;
      error?: string;
    }>(`/api/advisor/job/${jobId}`);
    if (s.status === "done" && s.result) return s.result;
    if (s.status === "error") throw new Error(s.error || `${label} failed`);
    if (s.status === "gone")
      throw new Error("The advisor restarted mid-run — please try again.");
  }
  throw new Error("The advisor is taking unusually long — please try again.");
}

async function advisePortfolioPolling(
  force: boolean,
  deep: boolean
): Promise<AdvisorNote> {
  const { job_id } = await post<{ job_id: string }>(
    `/api/advisor/portfolio/start?force=${force}&deep=${deep}`,
    {}
  );
  return pollAdvisorJob<AdvisorNote>(job_id, "Brief");
}

async function adviseStockPolling(
  symbol: string,
  force: boolean,
  deep: boolean
): Promise<AdvisorNote> {
  const { job_id } = await post<{ job_id: string }>(
    `/api/advisor/stock/${symbol}/start?force=${force}&deep=${deep}`,
    {}
  );
  return pollAdvisorJob<AdvisorNote>(job_id, "Stock review");
}

async function askAdvisorPolling(
  kind: "portfolio" | "stock" | "breakout",
  symbol: string | undefined,
  question: string,
  deep: boolean
): Promise<AskAnswer> {
  const { job_id } = await post<{ job_id: string }>("/api/advisor/ask/start", {
    kind,
    symbol,
    question,
    deep,
  });
  // Poll up to ~8 min (deep research rarely exceeds this). Interval is short so
  // a quick answer still feels immediate.
  const intervalMs = 2500;
  const maxAttempts = Math.ceil((8 * 60 * 1000) / intervalMs);
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise((r) => setTimeout(r, intervalMs));
    const s = await get<{
      status: "pending" | "done" | "error" | "gone";
      result?: AskAnswer;
      error?: string;
    }>(`/api/advisor/ask/status/${job_id}`);
    if (s.status === "done" && s.result) return s.result;
    if (s.status === "error") throw new Error(s.error || "Advisor ask failed");
    if (s.status === "gone")
      throw new Error("The advisor restarted mid-answer — please ask again.");
  }
  throw new Error("The advisor is taking unusually long — please try again.");
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

export interface OptionsTrade {
  symbol: string;
  side: string;
  expiration: string;
  dte: number;
  strike: number;
  premium: number;
  cost_per_contract: number;
  breakeven: number;
  delta: number;
  iv_pct: number;
  open_interest: number;
  volume: number;
  spread_pct: number | null;
  spot: number;
  target?: number;
  value_at_target?: number;
  profit_at_target?: number;
  return_at_target_x?: number | null;
}

export interface OptionsAdvice {
  engine: string;
  generated_at: string;
  thesis: string;
  contract: string;
  sizing: string;
  risk: string;
}

export interface OptionsIdea {
  symbol: string;
  spot: number;
  side: string;
  stance?: string | null;
  held?: boolean;
  target: number;
  trade: OptionsTrade | null;
  advice?: OptionsAdvice | null;
}

export const api = {
  plan: () => get<GamePlanData>("/api/plan"),
  optionsIdea: (symbol: string, side?: string) =>
    get<OptionsIdea>(`/api/options/${symbol}${side ? `?side=${side}` : ""}`),
  optionsThesis: (symbol: string, side?: string) =>
    get<OptionsIdea>(`/api/options/${symbol}/thesis${side ? `?side=${side}` : ""}`),
  dismissIdea: (symbol: string) =>
    post<{ dismissed: string }>(`/api/plan/idea/dismiss?symbol=${encodeURIComponent(symbol)}`, {}),
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
  // These generate; they can take minutes, so they poll a background job
  // rather than holding one request open past the tunnel's 100s ceiling.
  adviseStock: (symbol: string, force = false, deep = false) =>
    adviseStockPolling(symbol, force, deep),
  adviseBreakout: (symbol: string, force = false, deep = false) =>
    get<AdvisorNote>(`/api/advisor/breakout/${symbol}?force=${force}&deep=${deep}`),
  advisePortfolio: (force = false, deep = false) =>
    advisePortfolioPolling(force, deep),
  stayTheCourse: () =>
    get<StayCourse>(`/api/advisor/stay-the-course`).catch(() => null as StayCourse | null),
  recommend: (symbol: string, event: string, kind = "alert") =>
    post<Recommendation>("/api/advisor/recommend", { symbol, event, kind }),
  lastAdvisorNote: (kind: "portfolio" | "stock" | "breakout", symbol?: string) =>
    get<AdvisorNote>(
      `/api/advisor/last?kind=${kind}${symbol ? `&symbol=${symbol}` : ""}`
    ).catch(() => null as AdvisorNote | null),
  askAdvisor: (
    kind: "portfolio" | "stock" | "breakout",
    symbol: string | undefined,
    question: string,
    deep = false
  ) => askAdvisorPolling(kind, symbol, question, deep),
  // The recorded conversation, so the thread is the same on every device rather
  // than living in one browser's localStorage.
  advisorChat: (kind = "portfolio", symbol?: string) =>
    get<{ turns: ChatTurn[] }>(
      `/api/advisor/chat?kind=${kind}${symbol ? `&symbol=${symbol}` : ""}`
    ).catch(() => ({ turns: [] as ChatTurn[] })),
  clearAdvisorChat: (kind = "portfolio", symbol?: string) =>
    send<{ cleared: number }>(
      `/api/advisor/chat?kind=${kind}${symbol ? `&symbol=${symbol}` : ""}`,
      "DELETE"
    ),
  watchpoints: () => get<{ count: number; results: Watchpoint[] }>("/api/watchpoints"),
  addWatchpoint: (wp: { symbol: string; kind: Watchpoint["kind"]; level: number; note?: string; side?: "buy" | "sell"; confirm?: "touch" | "close" }) =>
    post<Watchpoint>("/api/watchpoints", wp),
  scorecard: () => get<Scorecard>("/api/scorecard"),
  deleteWatchpoint: (id: string) =>
    send<{ deleted: string }>(`/api/watchpoints/${id}`, "DELETE"),
  extractWatchpoints: () =>
    send<{ created: number; results: Watchpoint[] }>("/api/watchpoints/extract", "POST"),
  insights: () => get<PortfolioInsights>("/api/insights"),
  risk: () => get<RiskDesk>("/api/risk"),
  learning: () => get<Learning>("/api/learning"),
  acceptProposal: (rule: string, note = "") =>
    post<RuleHealth["accepted"]>(
      `/api/learning/accept/${encodeURIComponent(rule)}?note=${encodeURIComponent(note)}`,
      {}
    ),
  unacceptProposal: (rule: string) =>
    send<{ removed: boolean }>(
      `/api/learning/accept/${encodeURIComponent(rule)}`,
      "DELETE"
    ),
  backtest: () => get<Backtest | null>("/api/backtest"),
  startBacktest: (years = 5) =>
    post<{ job_id: string }>(`/api/backtest?years=${years}`, {}),
  backtestJob: (jobId: string) =>
    get<{ status: "pending" | "done" | "error"; result: Backtest | null; error?: string }>(
      `/api/backtest/job/${jobId}`
    ),
  debate: (symbol: string) =>
    get<Debate | null>(`/api/debate/${symbol}`),
  debates: (limit = 20) =>
    get<{ results: Debate[] }>(`/api/debate?limit=${limit}`),
  startDebate: (symbol: string, force = false) =>
    post<{ job_id: string | null; result: Debate | null; cached: boolean }>(
      `/api/debate/${symbol}?force=${force}`,
      {}
    ),
  debateJob: (jobId: string) =>
    get<{ status: "pending" | "done" | "error"; result: Debate | null; error?: string }>(
      `/api/debate/job/${jobId}`
    ),
  sizePosition: (symbol: string) =>
    get<PositionPlan>(`/api/risk/size/${symbol}`),
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
