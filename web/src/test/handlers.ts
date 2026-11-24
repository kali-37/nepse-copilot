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

  // The bare probe above and the full report below are deliberately separate
  // endpoints: polling liveness must never run ten checks.
  http.get('*/api/health/report', ({ request }) => {
    const record = new URL(request.url).searchParams.get('record') === 'true';
    return HttpResponse.json(
      record ? { ...fx.healthReport, snapshot_id: 3 } : fx.healthReport
    );
  }),

  http.get('*/api/health/history', () => HttpResponse.json(fx.healthHistory)),

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

  // ------------------------------------------------------------- operations
  // The default is an idle server: no job running, none in history. Tests that
  // care about a live job override with `server.use(...)`.
  http.get('*/api/jobs', () =>
    HttpResponse.json({
      jobs: [],
      running: null,
      kinds: ['ingest', 'rag-index', 'reconcile', 'run-daily', 'screen'],
    })
  ),
  http.post('*/api/jobs', () => HttpResponse.json(fx.doneJob)),
  http.get('*/api/jobs/:id', () => HttpResponse.json(fx.doneJob)),
  http.post('*/api/jobs/:id/cancel', () =>
    HttpResponse.json({ ...fx.runningJob, cancel_requested: true })
  ),

  http.get('*/api/sources', () => HttpResponse.json(fx.sources)),
  http.get('*/api/strategies', () =>
    HttpResponse.json({
      strategies: ['bollinger', 'donchian', 'ichimoku', 'macd', 'mean_reversion', 'rsi', 'sma_cross', 'supertrend'],
    })
  ),

  http.get('*/api/tables', () => HttpResponse.json({ tables: fx.tableSummaries })),
  http.get('*/api/tables/:name', ({ params, request }) => {
    const offset = Number(new URL(request.url).searchParams.get('offset') ?? 0);
    return HttpResponse.json({ ...fx.tablePage, name: String(params.name), offset });
  }),

  http.get('*/api/corporate-actions', () => HttpResponse.json(fx.corporateActions)),
  http.post('*/api/corporate-actions', () => HttpResponse.json(fx.corporateActions[0])),

  http.get('*/api/paper/trades', () => HttpResponse.json(fx.paperTrades)),
  http.post('*/api/paper/trades', () =>
    HttpResponse.json({ trade: fx.paperTrades[0], portfolio: fx.portfolio })
  ),

  http.get('*/api/stats', () => HttpResponse.json(fx.bulkStats)),
  http.get('*/api/signals', () => HttpResponse.json(fx.bulkSignals)),

  http.get('*/api/ai/models', () => HttpResponse.json(fx.aiModels)),
  http.post('*/api/ai/test', () => HttpResponse.json(fx.aiTestOk)),

  http.get('*/api/decisions/history/:symbol', ({params}) => HttpResponse.json({ symbol: params.symbol, trades: [], events: [] })),
  http.get('*/api/decisions/fundamentals/:symbol', () => HttpResponse.json({
    source: 'MeroLagani public snapshot', snapshot_date: '2026-11-19', rating: 'supported',
    eps: 50, book_value: 500, current_pe: 25.5, current_pbv: 2.55, multiplier: 1,
    needs_refresh: false, reasons: ['Positive reported earnings and moderate valuation.'],
    limitations: ['Cash flow, debt and bank bad loans are not verified.'],
  })),

  // ---------------------------------------------------------------- journal
  http.get('*/api/journal/review-queue', () => HttpResponse.json([fx.journalHistory[1]])),
  http.get('*/api/journal/calibration', () => HttpResponse.json(fx.journalCalibration)),
  http.post('*/api/journal/score', () => HttpResponse.json([])),
  http.post('*/api/journal/:id/review', () => HttpResponse.json(fx.journalHistory[0])),
  http.post('*/api/journal/:id/distill', ({ params }) =>
    HttpResponse.json({ prediction_id: String(params.id), lesson_id: 4 })
  ),
  http.post('*/api/journal/:id/retire', () =>
    HttpResponse.json({ ...fx.journalHistory[1], status: 'retired' })
  ),
];
