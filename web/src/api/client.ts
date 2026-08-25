import type {
  BacktestRun,
  DashboardStats,
  Fundamentals,
  IngestReport,
  MarketBreadth,
  MoversResponse,
  PortfolioSummary,
  QuantStats,
  ReconciledPrice,
  ScreenRow,
  Signal,
  AiBudget,
  AiModelsResponse,
  AiTestResult,
  AuctionAdvice,
  AuctionAdviceRequest,
  BulkSignalsResponse,
  BulkStatsResponse,
  CorporateActionRow,
  DoseRun,
  HealthReport,
  HealthSnapshot,
  HoldingComparison,
  Job,
  JobKind,
  JobList,
  JournalEntry,
  MeroShareHolding,
  MeroShareSetting,
  MeroShareStatus,
  MeroShareSyncResult,
  NewsItem,
  PaperTradeResult,
  PaperTradeRow,
  RagSearchResponse,
  RagStats,
  RashifalRun,
  SourcesResponse,
  TablePage,
  TableSummary,
  WatchlistSettings,
} from './types';

const BASE = '/api';

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { Accept: 'application/json', ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`${res.status} ${res.statusText}${body ? `: ${body}` : ''}`);
  }
  return res.json();
}

function postJson<T>(url: string, body: unknown): Promise<T> {
  return fetchJson<T>(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export const api = {
  health: () => fetchJson<{ status: string }>('/health'),

  dashboard: () => fetchJson<DashboardStats>('/dashboard'),

  marketBreadth: (date?: string) => {
    const q = date ? `?business_date=${date}` : '';
    return fetchJson<MarketBreadth>(`/market-breadth${q}`);
  },

  movers: (top = 5, date?: string) => {
    const params = new URLSearchParams({ top: String(top) });
    if (date) params.set('business_date', date);
    return fetchJson<MoversResponse>(`/movers?${params}`);
  },

  symbols: () => fetchJson<string[]>('/symbols'),

  symbolPrices: (
    symbol: string,
    opts?: { start?: string; end?: string; limit?: number }
  ) => {
    const params = new URLSearchParams();
    if (opts?.start) params.set('start', opts.start);
    if (opts?.end) params.set('end', opts.end);
    if (opts?.limit) params.set('limit', String(opts.limit));
    const qs = params.toString();
    return fetchJson<ReconciledPrice[]>(
      `/symbols/${encodeURIComponent(symbol)}/prices${qs ? `?${qs}` : ''}`
    );
  },

  symbolSignals: (symbol: string, strategy = 'sma_cross') =>
    fetchJson<Signal[]>(
      `/symbols/${encodeURIComponent(symbol)}/signals?strategy=${encodeURIComponent(strategy)}`
    ),

  symbolQuant: (symbol: string) =>
    fetchJson<QuantStats>(`/symbols/${encodeURIComponent(symbol)}/quant`),

  symbolFundamentals: (symbol: string) =>
    fetchJson<Fundamentals>(`/symbols/${encodeURIComponent(symbol)}/fundamentals`),

  portfolio: (cash = 100_000) =>
    fetchJson<PortfolioSummary>(`/portfolio?cash=${cash}`),

  backtestScreen: (opts?: {
    strategies?: string;
    cash?: number;
    min_bars?: number;
    rank_by?: string;
    top?: number;
  }) => {
    const params = new URLSearchParams();
    if (opts?.strategies) params.set('strategies', opts.strategies);
    if (opts?.cash) params.set('cash', String(opts.cash));
    if (opts?.min_bars) params.set('min_bars', String(opts.min_bars));
    if (opts?.rank_by) params.set('rank_by', opts.rank_by);
    if (opts?.top) params.set('top', String(opts.top));
    return fetchJson<ScreenRow[]>(`/backtest/screen?${params}`);
  },

  backtestRun: (symbol: string, strategy = 'sma_cross', cash = 100_000) =>
    fetchJson<BacktestRun>(
      `/backtest/run?symbol=${encodeURIComponent(symbol)}&strategy=${encodeURIComponent(strategy)}&cash=${cash}`
    ),

  ingest: (date?: string, allSources = true, asyncMode = false) => {
    const params = new URLSearchParams();
    if (date) params.set('business_date', date);
    params.set('all_sources', String(allSources));
    params.set('async', String(asyncMode));
    return fetchJson<IngestReport>(`/ingest?${params}`, { method: 'POST' });
  },

  runAdvisor: (body: {
    mode: 'normal' | 'ai';
    horizon: 'day' | 'week' | 'month' | 'year';
    online: boolean;
    symbols?: string[];
    equity: number;
  }) =>
    fetchJson<RashifalRun>('/advisor/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),

  advisorLatest: () => fetchJson<RashifalRun>('/advisor/latest'),

  advisorHistory: (limit = 30) =>
    fetchJson<Array<Record<string, unknown>>>(`/advisor/history?limit=${limit}`),

  doseLatest: () => fetchJson<DoseRun>('/advisor/doses/latest'),

  journalHistory: (opts?: { symbol?: string; status?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.symbol) params.set('symbol', opts.symbol);
    if (opts?.status) params.set('status', opts.status);
    params.set('limit', String(opts?.limit ?? 100));
    return fetchJson<JournalEntry[]>(`/journal/history?${params}`);
  },

  auctionAdvice: (body: AuctionAdviceRequest) =>
    fetchJson<AuctionAdvice>('/auction/advice', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),

  auctionHistory: (opts?: { symbol?: string; limit?: number }) => {
    const params = new URLSearchParams({ limit: String(opts?.limit ?? 50) });
    if (opts?.symbol) params.set('symbol', opts.symbol);
    return fetchJson<AuctionAdvice[]>(`/auction/history?${params}`);
  },

  meroshareSetting: () =>
    fetchJson<MeroShareSetting>('/settings/meroshare'),

  updateMeroShareSetting: (enabled: boolean | null) =>
    fetchJson<MeroShareSetting>('/settings/meroshare', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    }),

  meroshareStatus: () => fetchJson<MeroShareStatus>('/meroshare/status'),

  meroshareHoldings: () => fetchJson<MeroShareHolding[]>('/meroshare/holdings'),

  meroshareSync: (withTransactions = true) =>
    fetchJson<MeroShareSyncResult>(
      `/meroshare/sync?with_transactions=${withTransactions}`,
      { method: 'POST' }
    ),

  meroshareImport: (csvText: string) =>
    fetchJson<MeroShareSyncResult>('/meroshare/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ csv_text: csvText }),
    }),

  meroshareHistory: (limit = 20) =>
    fetchJson<Array<Record<string, unknown>>>(`/meroshare/history?limit=${limit}`),

  meroshareCompare: (cash = 100_000) =>
    fetchJson<{ rows: HoldingComparison[]; summary: Record<string, number> }>(
      `/meroshare/compare?cash=${cash}`
    ),

  ragSearch: (query: string, opts?: { limit?: number; symbol?: string; kind?: string }) => {
    const params = new URLSearchParams({ q: query, limit: String(opts?.limit ?? 8) });
    if (opts?.symbol) params.set('symbol', opts.symbol);
    if (opts?.kind) params.set('kind', opts.kind);
    return fetchJson<RagSearchResponse>(`/rag/search?${params}`);
  },

  ragStats: () => fetchJson<RagStats>('/rag/stats'),

  news: (limit = 20, symbol?: string) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (symbol) params.set('symbol', symbol);
    return fetchJson<NewsItem[]>(`/news?${params}`);
  },

  aiBudget: () => fetchJson<AiBudget>('/ai/budget'),

  healthReport: (record = false) =>
    fetchJson<HealthReport>(`/health/report${record ? '?record=true' : ''}`),

  healthHistory: (limit = 30) =>
    fetchJson<HealthSnapshot[]>(`/health/history?limit=${limit}`),

  watchlist: () => fetchJson<WatchlistSettings>('/settings/watchlist'),

  updateWatchlist: (symbols: string[]) =>
    fetchJson<WatchlistSettings>('/settings/watchlist', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbols }),
    }),

  // ------------------------------------------------------------------- jobs
  submitJob: (kind: JobKind, params: Record<string, unknown> = {}) =>
    postJson<Job>('/jobs', { kind, params }),

  jobs: (limit = 20) => fetchJson<JobList>(`/jobs?limit=${limit}`),

  job: (id: string) => fetchJson<Job>(`/jobs/${encodeURIComponent(id)}`),

  cancelJob: (id: string) =>
    fetchJson<Job>(`/jobs/${encodeURIComponent(id)}/cancel`, { method: 'POST' }),

  // ------------------------------------------------------------- operations
  sources: () => fetchJson<SourcesResponse>('/sources'),

  tables: () => fetchJson<{ tables: TableSummary[] }>('/tables'),

  table: (name: string, opts?: { limit?: number; offset?: number }) => {
    const params = new URLSearchParams({
      limit: String(opts?.limit ?? 100),
      offset: String(opts?.offset ?? 0),
    });
    return fetchJson<TablePage>(`/tables/${encodeURIComponent(name)}?${params}`);
  },

  corporateActions: (symbol?: string) => {
    const q = symbol ? `?symbol=${encodeURIComponent(symbol)}` : '';
    return fetchJson<CorporateActionRow[]>(`/corporate-actions${q}`);
  },

  addCorporateAction: (body: {
    symbol: string;
    ex_date: string;
    action_type: string;
    ratio_numerator: number;
    ratio_denominator: number;
    notes?: string;
  }) => postJson<CorporateActionRow>('/corporate-actions', body),

  paperTrades: (limit = 100) => fetchJson<PaperTradeRow[]>(`/paper/trades?limit=${limit}`),

  recordPaperTrade: (body: {
    symbol: string;
    side: 'buy' | 'sell';
    price: number;
    quantity: number;
    business_date?: string;
    cash?: number;
  }) => postJson<PaperTradeResult>('/paper/trades', body),

  bulkStats: (opts?: { symbols?: string; top?: number; periods?: number }) => {
    const params = new URLSearchParams({ top: String(opts?.top ?? 25) });
    if (opts?.symbols) params.set('symbols', opts.symbols);
    if (opts?.periods) params.set('periods', String(opts.periods));
    return fetchJson<BulkStatsResponse>(`/stats?${params}`);
  },

  bulkSignals: (opts?: {
    strategy?: string;
    symbols?: string;
    top?: number;
    actionableOnly?: boolean;
  }) => {
    const params = new URLSearchParams({
      strategy: opts?.strategy ?? 'sma_cross',
      top: String(opts?.top ?? 25),
    });
    if (opts?.symbols) params.set('symbols', opts.symbols);
    if (opts?.actionableOnly) params.set('actionable_only', 'true');
    return fetchJson<BulkSignalsResponse>(`/signals?${params}`);
  },

  strategies: () => fetchJson<{ strategies: string[] }>('/strategies'),

  aiModels: () => fetchJson<AiModelsResponse>('/ai/models'),

  aiTest: (tier: 'bulk' | 'synthesis' = 'synthesis') =>
    postJson<AiTestResult>('/ai/test', { tier }),

  // ---------------------------------------------------------------- journal
  journalReviewQueue: (limit = 100) =>
    fetchJson<JournalEntry[]>(`/journal/review-queue?limit=${limit}`),

  journalCalibration: (opts?: { symbol?: string; horizon?: string; limit?: number }) => {
    const params = new URLSearchParams({ limit: String(opts?.limit ?? 200) });
    if (opts?.symbol) params.set('symbol', opts.symbol);
    if (opts?.horizon) params.set('horizon', opts.horizon);
    return fetchJson<Array<Record<string, unknown>>>(`/journal/calibration?${params}`);
  },

  journalScore: (limit = 25) => postJson<Array<Record<string, unknown>>>('/journal/score', { limit }),

  journalReview: (predictionId: string, review: string) =>
    postJson<JournalEntry>(`/journal/${encodeURIComponent(predictionId)}/review`, { review }),

  journalDistill: (predictionId: string, lesson: string) =>
    postJson<{ prediction_id: string; lesson_id: number }>(
      `/journal/${encodeURIComponent(predictionId)}/distill`,
      { lesson }
    ),

  journalRetire: (predictionId: string) =>
    fetchJson<JournalEntry>(`/journal/${encodeURIComponent(predictionId)}/retire`, {
      method: 'POST',
    }),
};
