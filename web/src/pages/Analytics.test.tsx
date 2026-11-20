import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AnalyticsPage } from './Analytics';
import { renderWithProviders } from '../test/renderWithProviders';
import { server } from '../test/server';

const market = { business_date: '2026-11-19', sectors: [{ sector: 'Banks', symbols: 3, advancers: 2, decliners: 1, mean_change_pct: 1.2, turnover: 100000 }], broker_flows: [], broker_rows: 0, indices: [] };

describe('Analytics', () => {
  it('shows stored sector breadth and the missing broker-data action', async () => {
    server.use(http.get('*/api/research/market', () => HttpResponse.json(market)));
    renderWithProviders(<AnalyticsPage />);
    expect(await screen.findByRole('table', { name: 'Sector breadth' })).toBeInTheDocument();
    expect(screen.getByText('Banks')).toBeInTheDocument();
    expect(screen.getByText(/Download broker trades in Operations/)).toBeInTheDocument();
  });

  it('runs walk-forward for the first selected symbol and displays validation returns', async () => {
    let requestedSymbol = '';
    server.use(http.get('*/api/research/market', () => HttpResponse.json(market)),
      http.get('*/api/research/walk-forward', ({ request }) => {
        requestedSymbol = new URL(request.url).searchParams.get('symbol') ?? '';
        return HttpResponse.json({ symbol: 'NABIL', strategy_name: 'sma_cross', avg_is_return_pct: 4, avg_oos_return_pct: 2,
          folds: [{ train_start: '2026-01-01', train_end: '2026-03-01', val_start: '2026-03-02', val_end: '2026-04-01', best_params: { fast: 10, slow: 30 }, in_sample_return_pct: 4, out_of_sample_return_pct: 2 }] });
      }));
    renderWithProviders(<AnalyticsPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Run walk-forward' }));
    expect(await screen.findByRole('table', { name: 'Validation folds' })).toBeInTheDocument();
    expect(requestedSymbol).toBe('NABIL');
    expect(screen.getByText('2.00%')).toBeInTheDocument();
  });

  it('shows research errors without losing the form', async () => {
    server.use(http.get('*/api/research/market', () => HttpResponse.json(market)),
      http.get('*/api/research/portfolio', () => HttpResponse.json({ detail: 'Download history' }, { status: 400 })));
    renderWithProviders(<AnalyticsPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Run portfolio backtest' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Download history');
    expect(screen.getByRole('button', { name: 'Run portfolio backtest' })).toBeEnabled();
  });
});
