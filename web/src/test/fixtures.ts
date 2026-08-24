import type {
  BacktestRun,
  DashboardStats,
  Fundamentals,
  MarketBreadth,
  MoversResponse,
  PortfolioSummary,
  QuantStats,
  ReconciledPrice,
  ScreenRow,
  Signal,
  AiBudget,
  AuctionAdvice,
  DoseRun,
  JournalEntry,
  MeroShareHolding,
  MeroShareStatus,
  RagSearchResponse,
  RagStats,
  RashifalRun,
  WatchlistSettings,
} from '../api/types';

/**
 * Fixtures mirroring the FastAPI response shapes in nepse_trader/web/api.py.
 */

export const dashboardStats: DashboardStats = {
  symbols_with_data: 248,
  price_bar_rows: 154_320,
  reconciled_rows: 51_440,
  price_date_earliest: '2023-01-02',
  price_date_latest: '2026-08-22',
  reconciled_date_earliest: '2023-01-02',
  reconciled_date_latest: '2026-08-22',
  sources_with_data: 3,
  signal_strategies: 4,
  signal_rows: 8_912,
  ingest_log_rows: 621,
  latest_reconciled_date: '2026-08-22',
  latest_symbols: 244,
  latest_avg_confidence: 0.9231,
  latest_disputed: 2,
  paper_trades: 17,
};

export const marketBreadth: MarketBreadth = {
  business_date: '2026-08-22',
  symbols: 244,
  advancers: 130,
  decliners: 96,
  unchanged: 18,
  total_turnover: 4_512_000_000,
  avg_confidence: 0.9231,
  disputed: 2,
};

export const emptyMarketBreadth: MarketBreadth = {
  business_date: '2026-08-22',
  symbols: 0,
  advancers: 0,
  decliners: 0,
  unchanged: 0,
  total_turnover: 0,
  avg_confidence: null,
  disputed: 0,
};

export const movers: MoversResponse = {
  gainers: [
    { symbol: 'NABIL', close: 1234.5, change_percent: 9.87 },
    { symbol: 'NICA', close: 876.25, change_percent: 6.42 },
  ],
  losers: [
    { symbol: 'HBL', close: 543.1, change_percent: -7.15 },
    { symbol: 'SCB', close: 412.8, change_percent: -4.33 },
  ],
};

export const emptyMovers: MoversResponse = { gainers: [], losers: [] };

export const symbols: string[] = ['NABIL', 'NICA', 'HBL', 'SCB', 'ADBL'];

export const prices: ReconciledPrice[] = [
  {
    business_date: '2026-08-20',
    open: 1200,
    high: 1240,
    low: 1195,
    close: 1220,
    volume: 45_000,
    turnover: 54_900_000,
    confidence: 0.95,
  },
  {
    business_date: '2026-08-21',
    open: 1220,
    high: 1260,
    low: 1218,
    close: 1250,
    volume: 52_000,
    turnover: 65_000_000,
    confidence: 0.93,
  },
  {
    business_date: '2026-08-22',
    open: 1250,
    high: 1290,
    low: 1245,
    close: 1275,
    volume: 61_000,
    turnover: 77_775_000,
    confidence: 0.97,
  },
];

export const signals: Signal[] = [
  {
    business_date: '2026-08-21',
    strategy: 'sma_cross',
    action: 'BUY',
    strength: 0.8,
    reason: 'fast SMA crossed above slow SMA',
    price: 1250,
  },
  {
    business_date: '2026-08-22',
    strategy: 'sma_cross',
    action: 'HOLD',
    strength: 0.1,
    reason: null,
    price: 1272.5,
  },
];

export const quantStats: QuantStats = {
  symbol: 'NABIL',
  n: 512,
  last_close: 1275,
  total_return_pct: 42.18,
  annualized_return_pct: 18.35,
  annualized_vol_pct: 27.9,
  sharpe: 0.658,
  sortino: 0.912,
  max_drawdown_pct: -31.44,
  skewness: 0.221,
  kurtosis: 4.87,
  var_95_pct: -2.84,
};

export const fundamentals: Fundamentals = {
  company_name: 'Nabil Bank Limited',
  sector: 'Commercial Banks',
  // Deliberately a shade off the reconciled close (1275) — fundamentals come
  // from a different upstream, and distinct values keep assertions unambiguous.
  market_price: 1280,
  eps: 43.21,
  pe_ratio: 29.51,
  book_value: 312.4,
  pbv: 4.08,
  dividend_pct: 12.5,
  market_cap: 21_500_000_000,
  shares_outstanding: 16_862_745,
  high_52w: 1390,
  low_52w: 780,
  avg_volume_30d: 48_300,
};

export const portfolio: PortfolioSummary = {
  initial_cash: 100_000,
  cash: 42_500.75,
  realized_pnl: 3_210.5,
  investor: 'paper',
  positions: [
    {
      symbol: 'NABIL',
      quantity: 40,
      avg_cost: 1180.25,
      market_value: 51_000,
      unrealized_pnl: 3_790,
    },
    {
      symbol: 'HBL',
      quantity: 15,
      avg_cost: 580.4,
      market_value: 8_146.5,
      unrealized_pnl: -559.5,
    },
  ],
  trades: 6,
};

export const emptyPortfolio: PortfolioSummary = {
  initial_cash: 100_000,
  cash: 100_000,
  realized_pnl: 0,
  investor: 'paper',
  positions: [],
  trades: 0,
};

export const screenRows: ScreenRow[] = [
  {
    symbol: 'NABIL',
    strategy: 'sma_cross',
    total_return_pct: 42.18,
    cagr_pct: 18.35,
    sharpe: 0.658,
    max_drawdown_pct: -31.44,
    win_rate_pct: 54.5,
    num_trades: 22,
    exposure_pct: 61,
    final_equity: 142_180,
    bars: 512,
  },
  {
    symbol: 'HBL',
    strategy: 'rsi_reversion',
    total_return_pct: -8.4,
    cagr_pct: -3.9,
    sharpe: -0.212,
    max_drawdown_pct: -22.1,
    win_rate_pct: 41.2,
    num_trades: 17,
    exposure_pct: 44,
    final_equity: 91_600,
    bars: 498,
  },
];

export const backtestRun: BacktestRun = {
  summary: {
    total_return_pct: 42.18,
    cagr_pct: 18.35,
    sharpe: 0.658,
    max_drawdown_pct: -31.44,
    num_trades: 22,
    win_rate_pct: 54.5,
    exposure_pct: 61,
    final_equity: 142_180,
  },
  equity_curve: [
    ['2026-08-20', 138_000],
    ['2026-08-21', 140_500],
    ['2026-08-22', 142_180],
  ],
  trades: [{ symbol: 'NABIL', action: 'BUY', quantity: 40, price: 1180.25 }],
};

export const confidence = {
  value: 0.72,
  band: 'LIKELY',
  label: 'more likely than not',
  basis: 'mechanical panel',
};

export const rashifal: RashifalRun = {
  run_id: 1,
  run_date: '2026-08-22',
  mode: 'normal',
  horizon: 'week',
  online: false,
  equity: 100_000,
  regime: 'advancing',
  sector_of_the_day: 'Banks (+1.2%)',
  cards: [
    {
      symbol: 'NABIL',
      action: 'accumulate',
      reference_price: 1275,
      entry_low: 1260,
      entry_high: 1285,
      stop: 1200,
      targets: [1420, 1500],
      quantity: 10,
      horizon_days: 10,
      earliest_sell_date: '2026-09-07',
      conviction: 4,
      rationale: 'Panel votes favour accumulation',
      gross_pnl: 1350,
      net_pnl: 1140,
      entry_cost: 40,
      exit_cost: 60,
      capital_gains_tax: 110,
      note: '',
      signals: ['sma_cross:buy'],
      confidence,
    },
  ],
  sell_queue: [],
  do_not_touch: [],
  breadth: { symbols: 244, advancers: 130 },
  banner: '',
  thesis: 'Breadth is constructive but position size remains bounded by the stop.',
  generated_at: '2026-08-22T10:00:00Z',
};

export const doseRun: DoseRun = {
  run_id: 1,
  run_date: '2026-08-22',
  mode: 'normal',
  capital: 100_000,
  deployed_capital: 10_000,
  expected_gross_pnl: 1350,
  expected_net_pnl: 1140,
  confidence,
  banner: '',
  generated_at: '2026-08-22T10:00:00Z',
  doses: [
    {
      horizon: 'day', horizon_days: 3, allocation_pct: 0.1, allocated_capital: 10_000,
      deployed_capital: 10_000, symbols: ['NABIL'], card_count: 1, cards: rashifal.cards,
      expected_gross_pnl: 1350, expected_net_pnl: 1140, expected_return_pct: 11.4,
      expected_costs: 100, expected_tax: 110, confidence, earliest_sell_date: '2026-08-27',
      reading: 'Day dose: review after three sessions.',
    },
    ...(['week', 'month', 'year'] as const).map((horizon, index) => ({
      horizon, horizon_days: horizon === 'week' ? 10 : horizon === 'month' ? 22 : 250,
      allocation_pct: [0.2, 0.3, 0.4][index], allocated_capital: [20_000, 30_000, 40_000][index],
      deployed_capital: 0, symbols: [], card_count: 0, cards: [], expected_gross_pnl: 0,
      expected_net_pnl: 0, expected_return_pct: 0, expected_costs: 0, expected_tax: 0,
      confidence, earliest_sell_date: null, reading: 'No card assigned.',
    })),
  ],
};

export const journalHistory: JournalEntry[] = [
  {
    id: 2, prediction_id: 'prediction:nabil:2', symbol: 'NABIL', made_on: '2026-08-01',
    horizon: 'week', horizon_days: 10, deadline: '2026-08-15', action: 'accumulate',
    entry_low: 1200, entry_high: 1220, stop: 1150, target_1: 1320,
    expected_net_pnl: 900, confidence: 0.72, confidence_band: 'LIKELY',
    confidence_basis: '8/12 comparable calls', status: 'retired', outcome: 'TARGET_HIT',
    realized_net_pnl: 840, hit: 1, review: 'The breakout held on improving breadth.',
    lesson: 'Require breadth confirmation before sizing the next bank breakout.',
  },
  {
    id: 1, prediction_id: 'prediction:hbl:1', symbol: 'HBL', made_on: '2026-08-10',
    horizon: 'day', horizon_days: 3, deadline: '2026-08-13', action: 'hold',
    entry_low: 540, entry_high: 550, stop: 520, target_1: 590,
    expected_net_pnl: 300, confidence: 0.45, confidence_band: 'COIN_FLIP',
    confidence_basis: 'house prior', status: 'open', outcome: null,
    realized_net_pnl: null, hit: null, review: null, lesson: null,
  },
];

export const meroshareStatus: MeroShareStatus = {
  enabled: true,
  credentials_configured: true,
  credentials_missing: [],
  credential_source: 'env',
  keyring_available: false,
  keyring_note: '',
  holdings: 1,
  transactions: 4,
  attempts: 2,
  last_attempt_at: '2026-08-22T10:00:00Z',
  last_method: 'csv',
  last_status: 'ok',
  last_error: null,
  last_success_at: '2026-08-22T10:00:00Z',
  total_cost_basis: 11802.5,
};

export const meroshareHoldings: MeroShareHolding[] = [{
  symbol: 'NABIL', current_balance: 10, previous_balance: 10, pledged_balance: 0,
  wacc: 1180.25, previous_closing_price: 1275, cost_basis: 11802.5,
  market_value: 12750, isin: 'NPE000A', script_desc: 'Nabil Bank', demat_last4: '0001',
  last_transaction_date: '2026-08-01', source: 'csv',
}];

export const ragStats: RagStats = { total: 1250, per_kind: { price: 800, news: 450 }, uses_fts: true };
export const ragSearch: RagSearchResponse = {
  query: 'NABIL', uses_fts: true, count: 1,
  hits: [{ doc_id: 'doc-1', kind: 'news', symbol: 'NABIL', title: 'NABIL update', body: 'A local evidence item.', url: null, source: 'local', business_date: '2026-08-22', score: 0.9, matched_terms: ['nabil'] }],
  evidence: { markers: ['[1]'], kinds: ['news'], symbols: ['NABIL'], truncated: false, considered: 1, citations: { '[1]': 'doc-1' }, rendered: '[1] NABIL update - A local evidence item.' },
};

export const aiBudget: AiBudget = {
  day: '2026-08-22', week: '2026-W34', calls: 2, max_calls: 20, calls_left: 18,
  tokens: 1000, max_tokens: 10000, tokens_left: 9000, deep_passes: 0, max_deep_passes: 2,
  deep_passes_left: 2, cached_calls: 1, failed_calls: 0, exhausted: false, history: [],
};

export const watchlist: WatchlistSettings = { symbols: ['NABIL'], source: 'database', env_watchlist: [], updated_at: '2026-08-22T10:00:00Z', max_symbols: 25 };

export const auctionAdvice: AuctionAdvice = {
  advice_id: 'auction:test-1', symbol: 'NABIL', auction_date: '2026-08-22', units: 100,
  min_bid_price: 100, market_price: 120, recommended_bid: 100, max_sensible_bid: 108,
  walk_away_price: 120, breakeven_price: 112, quantity: 10, outlay: 1004,
  expected_exit_price: 140, expected_gross_pnl: 400, expected_net_pnl: 315,
  expected_return_pct: 31.37, horizon_days: 10, earliest_sell_date: '2026-09-07',
  confidence: 0.45, confidence_band: 'COIN_FLIP', confidence_basis: 'house prior',
  verdict: 'bid', rationale: 'Manual bid only: the minimum is below the conservative maximum.',
  created_at: '2026-08-22T10:00:00Z', manual_only: true, bid_submitted: false,
};

export const meroshareSetting = {
  enabled: true as const,
  source: 'database' as const,
  env_enabled: false,
  updated_at: '2026-08-22T10:00:00Z',
};
