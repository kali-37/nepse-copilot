export interface DashboardStats {
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
    market_value: number;
    unrealized_pnl: number;
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
