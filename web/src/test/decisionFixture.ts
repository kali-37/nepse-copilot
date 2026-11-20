import type { DecisionBoard, BuyIdea } from '../api/decisions';
const idea = (symbol: string, horizon: 'day' | 'month', score: number): BuyIdea => ({
  symbol, horizon, horizon_days: horizon === 'day' ? 3 : 22, reference_price: 100,
  entry_low: 99, entry_high: 101, stop: 95, target: 115, quantity: 100, outlay: 10160,
  estimated_net: 1100, estimated_fees: 240, earliest_sell_date: '2026-11-24',
  confidence: { value: score, label: 'Moderate evidence', basis: '12/20 comparable setups; trend and source agreement.', historical_hits: 12, historical_samples: 20 },
  rationale: ['Price is above its 20-session trend', 'Medium-term trend is rising', 'Recent momentum is positive', 'Volume confirms interest'],
  chart: [{ date: '2026-11-18', close: 97 }, { date: '2026-11-19', close: 100 }],
  metrics: { rsi: 55, volume_ratio: 1.4, trend_20: 98, trend_50: 90 },
});
export const decisionBoard: DecisionBoard = {
  requested_date: '2026-11-20', market_date: '2026-11-19', generated_at: '2026-11-20T10:00:00Z',
  session: 'closed', stale: false, available_cash: 100000, planned_outlay: 20320, cash_reserved: 79680,
  buys: { day: [idea('NABIL', 'day', .64)], month: [idea('EBL', 'month', .73)] },
  holdings: [{ symbol: 'NICA', quantity: 40, cost_basis: 20000, average_cost: 500, reference_price: 550,
    quote_date: '2026-11-19', unrealized_pnl: 2000, action: 'sell', reason: 'Price has reached your saved take-profit target.',
    stop: 470, target: 540, horizon_days: 22, bought_on: '2026-10-01', earliest_sell_date: '2026-10-05',
    settled: true, source: 'tracked', confidence: { value: .88, label: 'Exit trigger', basis: 'Saved target hit using reconciled quote.' }, chart: [] }],
  coverage: { symbols: 348, analysable: 341 }, confidence_note: 'Confidence measures evidence, not a guaranteed win probability.',
};
