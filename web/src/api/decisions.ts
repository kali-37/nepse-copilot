import { fetchJson } from './client';

export interface EvidenceScore {
  value: number; label: string; basis: string;
  historical_hits?: number; historical_samples?: number;
}
export interface PricePoint { date: string; close: number }
export interface BuyIdea {
  symbol: string; horizon: 'day' | 'month'; horizon_days: number;
  reference_price: number; entry_low: number; entry_high: number;
  stop: number; target: number; quantity: number; outlay: number;
  estimated_net: number; estimated_fees: number; earliest_sell_date: string;
  confidence: EvidenceScore; rationale: string[]; chart: PricePoint[];
  metrics: { rsi: number; volume_ratio: number; trend_20: number; trend_50: number };
}
export interface OwnedAdvice {
  symbol: string; quantity: number; cost_basis: number | null; average_cost: number | null;
  reference_price: number | null; quote_date: string | null; unrealized_pnl: number | null;
  net_exit_pnl?: number | null; action: 'sell' | 'hold' | 'review'; reason: string;
  stop: number | null; target: number | null; horizon_days: number;
  bought_on: string | null; earliest_sell_date: string | null; settled: boolean | null;
  source: string; confidence: EvidenceScore; chart: PricePoint[];
}
export interface DecisionBoard {
  id?: string; requested_date: string; market_date: string | null; generated_at: string;
  session: 'closed' | 'trading_day'; session_phase?: string; earliest_entry_date?: string; stale: boolean; available_cash: number;
  planned_outlay: number; cash_reserved: number;
  buys: { day: BuyIdea[]; month: BuyIdea[] }; holdings: OwnedAdvice[];
  coverage: { symbols: number; analysable: number }; confidence_note: string;
  refresh?: { sources: Record<string, number>; warnings: string[]; downloaded_prices: number };
}
export interface TradeRecord {
  symbol: string; side: 'buy' | 'sell'; quantity: number; price: number;
  business_date: string; record_id?: string; horizon_days: number; stop?: number; target?: number;
}
export const decisionApi = {
  board: () => fetchJson<DecisionBoard>('/decisions'),
  cash: (cash: number) => fetchJson<DecisionBoard>('/decisions/cash', {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ cash }),
  }),
  plan: (symbol: string, plan: { quantity: number; stop: number; target: number; average_cost?: number; bought_on?: string }) => fetchJson<DecisionBoard>(`/decisions/holdings/${encodeURIComponent(symbol)}/plan`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(plan),
  }),
  record: (trade: TradeRecord) => fetchJson<{ board: DecisionBoard; record: { order_submitted: false } }>('/decisions/trades', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(trade),
  }),
};
