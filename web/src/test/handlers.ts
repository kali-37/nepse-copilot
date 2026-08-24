import { http, HttpResponse } from 'msw';
import * as fx from './fixtures';

/**
 * Default happy-path handlers. Individual tests override per-endpoint with
 * `server.use(...)` — see ./server.ts.
 *
 * Paths are wildcard-prefixed (`*\/api/...`) so they match the relative URLs the
 * client builds (`/api/...`) regardless of the jsdom origin.
 */
export const handlers = [
  http.get('*/api/health', () => HttpResponse.json({ status: 'ok' })),

  http.get('*/api/dashboard', () => HttpResponse.json(fx.dashboardStats)),

  http.get('*/api/market-breadth', () => HttpResponse.json(fx.marketBreadth)),

  http.get('*/api/movers', () => HttpResponse.json(fx.movers)),

  http.get('*/api/symbols', () => HttpResponse.json(fx.symbols)),

  http.get('*/api/symbols/:symbol/prices', () => HttpResponse.json(fx.prices)),

  http.get('*/api/symbols/:symbol/signals', () => HttpResponse.json(fx.signals)),

  http.get('*/api/symbols/:symbol/quant', () => HttpResponse.json(fx.quantStats)),

  http.get('*/api/symbols/:symbol/fundamentals', () =>
    HttpResponse.json(fx.fundamentals)
  ),

  http.get('*/api/portfolio', () => HttpResponse.json(fx.portfolio)),

  http.get('*/api/backtest/screen', () => HttpResponse.json(fx.screenRows)),

  http.get('*/api/backtest/run', () => HttpResponse.json(fx.backtestRun)),

  http.post('*/api/ingest', () =>
    HttpResponse.json({
      business_date: '2026-08-22',
      per_source: { merolagani: 244, nepalipaisa: 240 },
      errors: {},
      total_bars: 484,
      total_indices: 12,
    })
  ),

  http.get('*/api/advisor/latest', () => HttpResponse.json(fx.rashifal)),
  http.get('*/api/advisor/doses/latest', () => HttpResponse.json(fx.doseRun)),
  http.get('*/api/journal/history', () => HttpResponse.json([])),
  http.post('*/api/auction/advice', () => HttpResponse.json(fx.auctionAdvice)),
  http.get('*/api/auction/history', () => HttpResponse.json([fx.auctionAdvice])),
  http.get('*/api/settings/meroshare', () => HttpResponse.json(fx.meroshareSetting)),
  http.put('*/api/settings/meroshare', () => HttpResponse.json(fx.meroshareSetting)),
  http.post('*/api/advisor/run', () => HttpResponse.json(fx.rashifal)),
  http.get('*/api/meroshare/status', () => HttpResponse.json(fx.meroshareStatus)),
  http.get('*/api/meroshare/holdings', () => HttpResponse.json(fx.meroshareHoldings)),
  http.get('*/api/meroshare/compare', () => HttpResponse.json({ rows: [], summary: {} })),
  http.post('*/api/meroshare/sync', () => HttpResponse.json({ ok: true, method: 'api', holdings: 1, transactions: 1, error: '', ran_at: '2026-08-22T10:00:00Z' })),
  http.post('*/api/meroshare/import', () => HttpResponse.json({ ok: true, method: 'csv', holdings: 1, transactions: 0, error: '', ran_at: '2026-08-22T10:00:00Z' })),
  http.get('*/api/rag/stats', () => HttpResponse.json(fx.ragStats)),
  http.get('*/api/rag/search', () => HttpResponse.json(fx.ragSearch)),
  http.get('*/api/news', () => HttpResponse.json([])),
  http.get('*/api/ai/budget', () => HttpResponse.json(fx.aiBudget)),
  http.get('*/api/settings/watchlist', () => HttpResponse.json(fx.watchlist)),
  http.put('*/api/settings/watchlist', () => HttpResponse.json(fx.watchlist)),
];
