import { fetchJson } from './client';
import type { FinancialVerification } from './decisions';
import type { BacktestRun } from './types';

export interface WalkForwardFold {
  train_start: string;
  train_end: string;
  val_start: string;
  val_end: string;
  best_params: Record<string, number>;
  in_sample_return_pct: number;
  out_of_sample_return_pct: number;
}

export interface WalkForwardResult {
  symbol: string;
  strategy_name: string;
  folds: WalkForwardFold[];
  avg_is_return_pct: number;
  avg_oos_return_pct: number;
}

export interface MarketResearch {
  business_date: string;
  sectors: Array<{ sector: string; symbols: number; advancers: number; decliners: number; mean_change_pct: number | null; turnover: number }>;
  broker_flows: Array<{ symbol: string; broker: string; buy_quantity: number; sell_quantity: number; net_quantity: number; net_amount: number }>;
  broker_rows: number;
  indices: Array<{ name: string; value: number; change_percent: number | null; source: string }>;
}

export interface FinancialCoverage {
  provider_symbols: number;
  matched_symbols: number;
  complete_symbols: number;
  symbols: Array<{
    symbol: string;
    period_end: string | null;
    period_basis: string | null;
    metrics: string[];
    status: FinancialVerification['status'];
  }>;
}

export const researchApi = {
  financialEvidence: (signal?: AbortSignal) =>
    fetchJson<FinancialCoverage>('/research/financial-evidence', { signal }),
  portfolio: (symbols: string, strategy: string, cash: number, mode: 'shared' | 'equal', rebalanceEvery: number) =>
    fetchJson<BacktestRun>(`/research/portfolio?${new URLSearchParams({ symbols, strategy, cash: String(cash), mode, rebalance_every: String(rebalanceEvery) })}`),
  walkForward: (symbol: string, strategy: string, rolling: boolean) =>
    fetchJson<WalkForwardResult>(`/research/walk-forward?${new URLSearchParams({ symbol, strategy, rolling: String(rolling) })}`),
  market: (businessDate?: string) =>
    fetchJson<MarketResearch>(`/research/market${businessDate ? `?business_date=${encodeURIComponent(businessDate)}` : ''}`),
};
