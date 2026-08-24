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
  AuctionAdvice,
  AuctionAdviceRequest,
  DoseRun,
  HoldingComparison,
  JournalEntry,
  MeroShareHolding,
  MeroShareSetting,
  MeroShareStatus,
  MeroShareSyncResult,
  NewsItem,
  RagSearchResponse,
  RagStats,
  RashifalRun,
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

  watchlist: () => fetchJson<WatchlistSettings>('/settings/watchlist'),

  updateWatchlist: (symbols: string[]) =>
    fetchJson<WatchlistSettings>('/settings/watchlist', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbols }),
    }),
};
