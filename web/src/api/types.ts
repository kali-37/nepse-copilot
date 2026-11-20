export interface DashboardStats {
  history_ready_symbols?: number;
  trading_days?: number;
  symbols_with_data: number;
  price_bar_rows: number;
  reconciled_rows: number;
  price_date_earliest: string | null;
  price_date_latest: string | null;
  reconciled_date_earliest: string | null;
  reconciled_date_latest: string | null;
  sources_with_data: number;
  signal_strategies: number;
  signal_rows: number;
  ingest_log_rows: number;
  latest_reconciled_date: string | null;
  latest_symbols: number | null;
  latest_avg_confidence: number | null;
  latest_disputed: number | null;
  paper_trades: number;
}

export interface MarketBreadth {
  business_date: string;
  symbols: number;
  advancers: number;
  decliners: number;
  unchanged: number;
  total_turnover: number;
  avg_confidence: number | null;
  disputed: number;
}

export interface Mover {
  symbol: string;
  close: number;
  change_percent: number;
}

export interface MoversResponse {
  gainers: Mover[];
  losers: Mover[];
}

export interface ReconciledPrice {
  business_date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
  turnover: number | null;
  confidence: number;
}

export interface Signal {
  business_date: string;
  strategy: string;
  action: string;
  strength: number;
  reason: string | null;
  price: number | null;
}

export interface QuantStats {
  symbol: string;
  n: number;
  last_close: number | null;
  total_return_pct: number;
  annualized_return_pct: number;
  annualized_vol_pct: number;
  sharpe: number;
  sortino: number;
  max_drawdown_pct: number;
  skewness: number;
  kurtosis: number;
  var_95_pct: number;
}

export interface Fundamentals {
  company_name: string;
  sector: string | null;
  market_price: number | null;
  eps: number | null;
  pe_ratio: number | null;
  book_value: number | null;
  pbv: number | null;
  dividend_pct: number | null;
  market_cap: number | null;
  shares_outstanding: number | null;
  high_52w: number | null;
  low_52w: number | null;
  avg_volume_30d: number | null;
}

export interface PortfolioSummary {
  initial_cash: number;
  cash: number;
  realized_pnl: number;
  investor: string;
  positions: Array<{
    symbol: string;
    quantity: number;
    avg_cost: number;
    market_value: number | null;
    unrealized_pnl: number | null;
  }>;
  trades: number;
}

export interface BacktestSummary {
  total_return_pct: number;
  cagr_pct: number;
  sharpe: number;
  max_drawdown_pct: number;
  num_trades: number;
  win_rate_pct: number;
  exposure_pct: number;
  final_equity: number;
}

export interface BacktestRun {
  summary: BacktestSummary;
  equity_curve: [string, number][];
  trades: Record<string, unknown>[];
}

export interface ScreenRow {
  symbol: string;
  strategy: string;
  total_return_pct: number;
  cagr_pct: number;
  sharpe: number;
  max_drawdown_pct: number;
  win_rate_pct: number;
  num_trades: number;
  exposure_pct: number;
  final_equity: number;
  bars: number;
}

export interface IngestReport {
  business_date: string | null;
  per_source: Record<string, number>;
  errors: Record<string, string>;
  total_bars: number;
  total_indices: number;
}

export interface Confidence {
  value: number;
  band: string;
  label: string;
  basis: string;
}

export interface PlanCard {
  symbol: string;
  action: string;
  reference_price: number;
  entry_low: number;
  entry_high: number;
  stop: number;
  targets: number[];
  quantity: number;
  horizon_days: number;
  earliest_sell_date: string;
  conviction: number;
  rationale: string;
  gross_pnl: number;
  net_pnl: number;
  entry_cost: number;
  exit_cost: number;
  capital_gains_tax: number;
  note: string;
  /** AI mode only, and not persisted — absent on a run loaded from history. */
  signals?: string[];
  confidence?: Confidence;
}

export interface RashifalRun {
  run_id: number | null;
  run_date: string;
  mode: 'normal' | 'ai';
  horizon: string;
  online: boolean;
  equity: number;
  regime: string;
  sector_of_the_day: string;
  cards: PlanCard[];
  sell_queue: Array<{
    symbol: string;
    quantity: number;
    reference_price: number;
    reason: string;
    earliest_sell_date: string;
    stop: number | null;
    target: number | null;
  }>;
  do_not_touch: Array<{ symbol: string; reason: string }>;
  breadth: Record<string, number | string | null>;
  banner: string;
  thesis: string;
  generated_at: string | null;
  doses?: DoseRun;
  predictions?: Array<{ prediction_id: string; symbol: string; status: string }>;
}

export interface Dose {
  horizon: 'day' | 'week' | 'month' | 'year';
  horizon_days: number;
  allocation_pct: number;
  allocated_capital: number;
  deployed_capital: number;
  symbols: string[];
  card_count: number;
  cards: PlanCard[];
  expected_gross_pnl: number;
  expected_net_pnl: number;
  expected_return_pct: number;
  expected_costs: number;
  expected_tax: number;
  confidence: Confidence;
  earliest_sell_date: string | null;
  reading: string;
}

export interface DoseRun {
  run_id: number | null;
  run_date: string;
  mode: string;
  capital: number;
  deployed_capital: number;
  expected_gross_pnl: number;
  expected_net_pnl: number;
  confidence: Confidence;
  banner: string;
  generated_at: string;
  doses: Dose[];
}

export interface JournalEntry {
  id: number;
  prediction_id: string;
  symbol: string;
  made_on: string;
  horizon: string;
  horizon_days: number;
  deadline: string;
  action: string;
  entry_low: number | null;
  entry_high: number | null;
  stop: number | null;
  target_1: number | null;
  expected_net_pnl: number | null;
  confidence: number;
  confidence_band: string;
  confidence_basis: string;
  status: 'open' | 'scored' | 'reviewed' | 'retired';
  outcome: string | null;
  realized_net_pnl: number | null;
  hit: number | null;
  review: string | null;
  lesson: string | null;
}

export interface AuctionAdviceRequest {
  symbol: string;
  auction_date?: string;
  units: number;
  min_bid_price: number;
  market_price: number;
  expected_exit_price?: number;
  horizon_days: number;
  quantity?: number;
  confidence?: number;
  edge_buffer_pct: number;
}

export interface AuctionAdvice {
  id?: number;
  advice_id: string;
  symbol: string;
  auction_date: string;
  units: number;
  min_bid_price: number;
  market_price: number;
  recommended_bid: number;
  max_sensible_bid: number;
  walk_away_price: number;
  breakeven_price: number;
  quantity: number;
  outlay: number;
  expected_exit_price: number;
  expected_gross_pnl: number;
  expected_net_pnl: number;
  expected_return_pct: number;
  horizon_days: number;
  earliest_sell_date: string;
  confidence: number;
  confidence_band: string;
  confidence_basis: string;
  verdict: 'bid' | 'skip';
  rationale: string;
  created_at?: string;
  manual_only?: boolean;
  bid_submitted?: boolean;
}

export interface MeroShareStatus {
  enabled: boolean;
  enabled_source?: string;
  enabled_updated_at?: string | null;
  credentials_configured: boolean;
  credentials_missing: string[];
  credential_source: string;
  keyring_available: boolean;
  keyring_note: string;
  holdings: number;
  transactions: number;
  attempts: number;
  last_attempt_at: string | null;
  last_method: string | null;
  last_status: string | null;
  last_error: string | null;
  last_success_at: string | null;
  total_cost_basis: number;
}

export interface MeroShareSetting {
  enabled: boolean;
  source: 'database' | 'env';
  env_enabled: boolean;
  updated_at: string | null;
}

export interface MeroShareHolding {
  symbol: string;
  current_balance: number;
  previous_balance: number | null;
  pledged_balance: number | null;
  wacc: number | null;
  previous_closing_price: number | null;
  cost_basis: number | null;
  market_value: number | null;
  isin: string | null;
  script_desc: string | null;
  demat_last4: string | null;
  last_transaction_date: string | null;
  source: string;
}

export interface MeroShareSyncResult {
  ok: boolean;
  method: string;
  holdings: number;
  transactions: number;
  error: string;
  ran_at: string;
}

export interface HoldingComparison {
  symbol: string;
  real_quantity: number;
  paper_quantity: number;
  real_wacc: number | null;
  paper_avg_cost: number | null;
  quantity_delta: number;
  only_in: string | null;
  agrees: boolean;
}

export interface RagHit {
  doc_id: string;
  kind: string;
  symbol: string | null;
  title: string;
  body: string;
  url: string | null;
  source: string;
  business_date: string | null;
  score: number;
  matched_terms: string[];
}

export interface RagSearchResponse {
  query: string;
  uses_fts: boolean;
  count: number;
  hits: RagHit[];
  evidence: {
    markers: string[];
    kinds: string[];
    symbols: string[];
    truncated: boolean;
    considered: number;
    citations: Record<string, string>;
    rendered: string;
  };
}

export interface RagStats {
  total: number;
  per_kind: Record<string, number>;
  uses_fts: boolean;
}

export interface NewsItem {
  doc_id: string;
  symbol: string | null;
  title: string;
  body: string;
  url: string | null;
  source: string;
  business_date: string | null;
  fetched_at: string | null;
}

export interface AiBudget {
  day: string;
  week: string;
  calls: number;
  max_calls: number;
  calls_left: number;
  tokens: number;
  max_tokens: number;
  tokens_left: number;
  deep_passes: number;
  max_deep_passes: number;
  deep_passes_left: number;
  cached_calls: number;
  failed_calls: number;
  exhausted: boolean;
  history: Array<Record<string, unknown>>;
}

export interface WatchlistSettings {
  symbols: string[];
  source: string;
  env_watchlist: string[];
  updated_at: string | null;
  max_symbols: number;
}

export type HealthStatus = 'ok' | 'warn' | 'fail' | 'off';

export interface HealthCheck {
  name: string;
  status: HealthStatus;
  detail: string;
  metrics: Record<string, unknown>;
}

export interface HealthReport {
  status: HealthStatus;
  generated_at: string;
  counts: Record<string, number>;
  checks: HealthCheck[];
  snapshot_id?: number;
}

export interface HealthSnapshot {
  id: number;
  captured_at: string;
  status: HealthStatus;
  ok: number;
  warn: number;
  fail: number;
  off: number;
}

// --------------------------------------------------------------- background jobs
export type JobKind = 'refresh-today' | 'ingest' | 'reconcile' | 'run-daily' | 'rag-index' | 'screen' | 'backfill' | 'fundamentals' | 'floorsheet';

export type JobStatus = 'queued' | 'running' | 'done' | 'failed' | 'cancelled';

export type JobStageStatus = 'pending' | 'running' | 'ok' | 'failed' | 'skipped';

export interface JobStage {
  name: string;
  label: string;
  status: JobStageStatus;
  detail: string;
  /** Items processed. 0/0 means the stage cannot count its work. */
  current: number;
  total: number;
}

export interface Job {
  id: string;
  kind: JobKind;
  params: Record<string, unknown>;
  status: JobStatus;
  stages: JobStage[];
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  cancel_requested: boolean;
  /** Absent on the list endpoint, which omits log bodies. */
  log?: string[];
}

export interface JobList {
  jobs: Job[];
  running: string | null;
  kinds: string[];
}

// ------------------------------------------------------------------ operations
export interface SourceEndpoint {
  name: string;
  path: string;
  method: string;
}

export interface SourceInfo {
  name: string;
  enabled: boolean;
  base_url: string;
  access_method: string;
  confidence: string | null;
  endpoints: SourceEndpoint[];
}

export interface SourcesResponse {
  enabled_in_settings: string[];
  sources: SourceInfo[];
}

export interface TableSummary {
  name: string;
  rows: number;
}

export interface TablePage {
  name: string;
  columns: string[];
  rows: Array<Record<string, unknown>>;
  total: number;
  limit: number;
  offset: number;
}

export interface CorporateActionRow {
  symbol: string;
  ex_date: string;
  action_type: string;
  ratio_numerator: number;
  ratio_denominator: number;
  factor: number;
  source: string;
  notes: string;
  description: string;
}

export interface PaperTradeRow {
  trade_id: string;
  symbol: string;
  side: string;
  business_date: string;
  quantity: number;
  price: number;
  gross_amount: number;
  broker_commission: number;
  sebon_fee: number;
  dp_charge: number;
  cgt: number;
  net_amount: number;
  strategy: string | null;
}

export interface PaperTradeResult {
  trade: Omit<PaperTradeRow, 'trade_id' | 'strategy'>;
  portfolio: PortfolioSummary;
}

export interface BulkStatsResponse {
  symbols: string[];
  periods_per_year?: number;
  rows: Array<Record<string, unknown>>;
}

export interface BulkSignalRow {
  symbol: string;
  business_date: string;
  strategy: string;
  action: string;
  strength: number | null;
  reason: string;
  price: number | null;
}

export interface BulkSignalsResponse {
  strategy: string;
  count: number;
  rows: BulkSignalRow[];
}

export interface AiProviderLeg {
  name: string;
  known: boolean;
  available: boolean;
  model: string | null;
}

export interface AiCacheStats {
  entries: number;
  oldest: string | null;
  newest: string | null;
  ttl_hours: number;
  enabled: boolean;
}

export interface AiModelsResponse {
  online: boolean;
  tiers: Record<string, AiProviderLeg[]>;
  usable_legs: number;
  banner: string | null;
  /** The same caps as `/ai/budget`, without the ledger rows. */
  budget: Omit<AiBudget, 'history'>;
  cache: AiCacheStats;
}

export interface AiTestResult {
  ok: boolean;
  tier: string;
  provider: string | null;
  model: string | null;
  total_tokens: number;
  text: string;
  error: string | null;
}
