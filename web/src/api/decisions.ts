import { fetchJson } from './client';

export interface FundamentalReport {
  asset_kind?: 'stock' | 'mutual_fund';
  source: string; snapshot_date: string | null;
  rating: 'supported' | 'caution' | 'expensive' | 'unsupported' | 'missing' | 'stale' | 'incomplete' | 'fund_review';
  eps: number | null; book_value: number | null; current_pe: number | null; current_pbv: number | null;
  multiplier: number; needs_refresh: boolean; reasons: string[]; limitations: string[];
}
export interface EvidenceScore {
  value: number; label: string; basis: string;
  historical_hits?: number; historical_samples?: number;
}
export interface PricePoint { date: string; close: number }
export interface BuyIdea {
  fundamental_report?: FundamentalReport; symbol: string; horizon: 'day' | 'month'; horizon_days: number;
  reference_price: number; entry_low: number; entry_high: number;
  stop: number; target: number; quantity: number; outlay: number;
  estimated_net: number; estimated_fees: number; earliest_sell_date: string;
  confidence: EvidenceScore; rationale: string[]; chart: PricePoint[];
  metrics: { rsi: number; volume_ratio: number; trend_20: number; trend_50: number };
}
export interface EntryPlan {
  id: string; confidence_horizon_days?: number | null; opened_on: string | null; horizon_days: number; purchase_price: number | null;
  rationale: string[]; confidence: EvidenceScore | null;
  stop: number | null; target: number | null;
  origin: { requested_date: string; market_date: string | null } | null;
}
export interface AdviceEvent {
  market_date: string | null; action: string; previous_action: string | null;
  trigger_code: string; reason: string; evaluated_at: string; plan_key: string;
}
export interface InvestmentIdea {
  symbol: string; company_name: string; sector: string; horizon_days: number;
  reference_price: number; rationale: string[]; owned: boolean; reconsider_after?: string; score: number;
  historical_net_annual_return: number; max_drawdown: number; annual_volatility: number;
  history_from: string; history_to: string; snapshot_date: string;
  pe: number; pbv: number; eps: number; declared_dividend_pct: number | null;
  confidence: EvidenceScore; chart: PricePoint[]; limitations: string;
}
export interface OwnedAdvice {
  symbol: string; quantity: number; cost_basis: number | null; average_cost: number | null;
  reference_price: number | null; quote_date: string | null; unrealized_pnl: number | null;
  net_exit_pnl?: number | null; action: 'sell' | 'hold' | 'review'; reason: string;
  stop: number | null; target: number | null; horizon_days: number;
  bought_on: string | null; earliest_sell_date: string | null; settled: boolean | null;
  fundamental_report?: FundamentalReport; original_plan?: EntryPlan | null; review_on?: string | null; holding_horizon?: string;
  trend_confirmations?: number; confirmations_required?: number; plan_key?: string;
  advice_history?: AdviceEvent[]; plan_revision?: number; plan_reviewed_on?: string | null;
  source: string; confidence: EvidenceScore; chart: PricePoint[];
}
export interface DecisionBoard {
  id?: string; requested_date: string; market_date: string | null; generated_at: string;
  session: 'closed' | 'trading_day'; session_phase?: string; earliest_entry_date?: string; stale: boolean; available_cash: number;
  planned_outlay: number; cash_reserved: number;
  buys: { day: BuyIdea[]; month: BuyIdea[] }; holdings: OwnedAdvice[];
  investments?: { candidates: InvestmentIdea[]; checked_fundamentals: number; fundamentals_missing: number; criteria: string; note: string };
  recent_exits?: { symbol: string; reconsider_after: string }[];
  coverage: { symbols: number; analysable: number }; confidence_note: string;
  refresh?: { sources: Record<string, number>; warnings: string[]; downloaded_prices: number };
}
export interface StockHistory {
  symbol: string;
  trades: { side: string; quantity: number; price: string; business_date: string; entry_plan: EntryPlan | null }[];
  events: { market_date: string | null; previous_action: string | null; action: string; reason: string; evaluated_at: string }[];
}
export interface TradeRecord {
  symbol: string; side: 'buy' | 'sell'; quantity: number; price: number;
  business_date: string; record_id?: string; origin_decision_id?: string; origin_horizon?: 'day' | 'month' | 'investment'; horizon_days: number; stop?: number; target?: number;
}
export interface RecommendationPerformance {
  engine_version: string; total: number; resolved: number; tracking_since: string | null;
  status: 'collecting_evidence' | 'measured_history'; outcomes: Record<string, number>;
  method: string; note: string;
  buckets: { lower: number; upper: number; samples: number; profitable_rate: number | null;
    interval_low: number | null; interval_high: number | null; mean_score: number | null;
    mean_net_return: number | null; mean_excess_return: number | null }[];
  recent: { prediction_id: string; symbol: string; made_on: string; horizon: string;
    confidence: number; outcome: string | null; status: string; evaluation_net_return: number | null }[];
}
export const decisionApi = {
  performance: () => fetchJson<RecommendationPerformance>('/decisions/performance'),
  history: (symbol: string) => fetchJson<StockHistory>(`/decisions/history/${encodeURIComponent(symbol)}`),
  fundamentals: (symbol: string) => fetchJson<FundamentalReport>(`/decisions/fundamentals/${encodeURIComponent(symbol)}`),
  board: () => fetchJson<DecisionBoard>('/decisions'),
  cash: (cash: number) => fetchJson<DecisionBoard>('/decisions/cash', {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ cash }),
  }),
  plan: (symbol: string, plan: { quantity: number; stop: number; target: number; average_cost?: number; bought_on?: string; horizon_days?: number }) => fetchJson<DecisionBoard>(`/decisions/holdings/${encodeURIComponent(symbol)}/plan`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(plan),
  }),
  record: (trade: TradeRecord) => fetchJson<{ board: DecisionBoard; record: { order_submitted: false } }>('/decisions/trades', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(trade),
  }),
};
