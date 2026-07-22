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
};
